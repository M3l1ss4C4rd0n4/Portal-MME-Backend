#!/usr/bin/env python3
"""
ETL: Sincronización automática Excel SharePoint → data/ → PostgreSQL
=====================================================================

Descarga archivos Excel desde SharePoint del Ministerio (vía Microsoft Graph API),
detecta cambios por hash SHA-256 y ejecuta el ETL correspondiente en PostgreSQL.

Archivos configurados:
  1. Matriz_Subsidios_DEE     → Base_Subsidios_DDE.xlsx      → tablas subsidios_*
  2. Matriz_Ejecucion_2026    → Matriz_Ejecucion_Presupuestal_2026.xlsx → schema presupuesto
  3. Matriz_Subsidios_KPIs    → Matriz_Subsidios_KPIs.xlsx   → schema subsidios_kpis
  4. Seguimiento_Contratos_CE → Seguimiento_Contratos_CE.xlsx → contratos_or.seguimiento

Uso:
    python etl/etl_sharepoint_sync.py                  # sincronizar todos
    python etl/etl_sharepoint_sync.py --archivo 1      # solo primer archivo (1-indexed)
    python etl/etl_sharepoint_sync.py --nombre Matriz_Subsidios_DEE
    python etl/etl_sharepoint_sync.py --forzar         # ignora hash, siempre re-procesa
    python etl/etl_sharepoint_sync.py --solo-descarga  # descarga sin correr ETL

Prerrequisitos en .env:
    MS_TENANT_ID     = <tenant-id del Ministerio>
    MS_CLIENT_ID     = <client-id del App Registration>
    MS_CLIENT_SECRET = <client-secret>

Autor: Portal Energético MME
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
HASH_CACHE_FILE = Path(__file__).resolve().parent / ".sharepoint_hashes.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ETL_SP_SYNC] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "etl_sharepoint_sync.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─── Cargar .env ──────────────────────────────────────────────────────────────
# Carga el .env raíz primero; si no tiene credenciales MS, usa el de arcgis como fallback.
try:
    from dotenv import load_dotenv
    _env_root = BASE_DIR / ".env"
    _env_arcgis = BASE_DIR / "scripts" / "arcgis" / ".env"
    if _env_root.exists():
        load_dotenv(_env_root, override=False)
    # Fallback: si aún faltan credenciales MS, cargar desde scripts/arcgis/.env
    if not os.getenv("MS_TENANT_ID") and _env_arcgis.exists():
        load_dotenv(_env_arcgis, override=False)
        logger.debug("Credenciales MS cargadas desde scripts/arcgis/.env")
except ImportError:
    pass

MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")

# ─── Configuración de archivos a sincronizar ──────────────────────────────────
# Cada entrada define:
#   nombre        → identificador legible (usado en logs y --nombre)
#   url           → link de compartir de SharePoint
#   archivo_local → nombre del archivo a guardar en data/<directorio>/
#   directorio    → subdirectorio dentro de data/
#   etl_handler   → función ETL a ejecutar tras la descarga (ver ETL_HANDLERS)
#   activo        → False para desactivar sin borrar

SHAREPOINT_FILES = [
    {
        "nombre": "Matriz_Subsidios_DEE",
        "url": "https://minenergiacol.sharepoint.com/:x:/s/DireccindeEnergaElctrica-DEE_Supervision/IQBYSwSMTWDaRZPZAV-5u2BHAccGnbwJQhONS1qjMMsOYKU?e=iNVWid",
        "archivo_local": "Base_Subsidios_DDE.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_subsidios",
        "activo": True,
    },
    {
        "nombre": "Matriz_Ejecucion_Presupuestal_2026",
        "url": "https://minenergiacol.sharepoint.com/:x:/s/msteams_c07b9d_609752/IQDnE_TXa3bUS66FeXe-jVH_AYBsfPzb348f45qNxMoHYZ8?e=5flCbn",
        "archivo_local": "Matriz_Ejecucion_Presupuestal_2026.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_presupuesto_onedrive",
        "activo": True,
    },
    {
        "nombre": "Matriz_Subsidios_KPIs",
        "url": "https://minenergiacol.sharepoint.com/:x:/s/msteams_c07b9d_609752/IQCyIRV1_hUAQ6FABQZ9FC-2AbK6HZb4M2CL0K8ni4EqJpo?e=qBpr6A",
        "archivo_local": "Matriz_Subsidios_KPIs.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_subsidios_kpis",
        "activo": True,
    },
    {
        "nombre": "Seguimiento_Contratos_CE",
        "url": "https://minenergiacol.sharepoint.com/:x:/s/msteams_c07b9d_609752/IQCnUGoKW1TeTY2hiXvFRtI-ARDDBUjf4MQK0SFbENA5NCI?e=3lEaeM",
        "archivo_local": "Seguimiento_Contratos_CE.xlsx",
        "directorio": "base_de_datos_contratos_or",
        "etl_handler": "etl_contratos_or_onedrive",
        "activo": True,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN MICROSOFT GRAPH API
# ═══════════════════════════════════════════════════════════════════════════════

_access_token: str = ""
_token_expiry: float = 0.0


def _get_access_token() -> str:
    """Obtiene o renueva el access token de Microsoft Graph (Client Credentials)."""
    global _access_token, _token_expiry
    if _access_token and time.time() < _token_expiry - 60:
        return _access_token

    if not (MS_TENANT_ID and MS_CLIENT_ID and MS_CLIENT_SECRET):
        raise RuntimeError(
            "Faltan credenciales de Microsoft Graph en .env:\n"
            "  MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET\n"
            "Ver scripts/arcgis/ACTUALIZACIONES_ARCGIS.md para instrucciones."
        )

    try:
        import msal
    except ImportError:
        raise RuntimeError("Librería 'msal' no instalada. Ejecuta: pip install msal")

    logger.info("🔑 Autenticando con Microsoft Graph (Client Credentials)...")
    app = msal.ConfidentialClientApplication(
        client_id=MS_CLIENT_ID,
        client_credential=MS_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(
            f"Error autenticando con Microsoft Graph: "
            f"{result.get('error_description', result.get('error', 'desconocido'))}"
        )
    _access_token = result["access_token"]
    _token_expiry = time.time() + result.get("expires_in", 3600)
    logger.info("  ✅ Token obtenido (expira en %ds)", result.get("expires_in", 3600))
    return _access_token


def _encode_sharing_url(share_link: str) -> str:
    """Codifica un link de SharePoint en base64url para Graph API /shares/."""
    encoded = base64.urlsafe_b64encode(share_link.encode()).decode().rstrip("=")
    return f"u!{encoded}"


# ═══════════════════════════════════════════════════════════════════════════════
# DESCARGA
# ═══════════════════════════════════════════════════════════════════════════════

def _es_excel_valido(path: Path) -> bool:
    """Verifica que el archivo sea un Excel real (no HTML de login page)."""
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"PK" or magic[:4] == b"\xd0\xcf\x11\xe0":
        return True
    with open(path, "rb") as f:
        inicio = f.read(500).lower()
    return b"<html" not in inicio and b"<!doctype" not in inicio


def descargar_desde_sharepoint(share_link: str, destino: Path) -> None:
    """
    Descarga un archivo de SharePoint al path indicado.
    Intenta primero descarga pública, luego autenticada vía Graph API.

    Raises:
        RuntimeError si la descarga falla después de ambas estrategias.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")

    # Estrategia 1: descarga pública (?download=1)
    sep = "&" if "?" in share_link else "?"
    public_url = f"{share_link}{sep}download=1"
    try:
        logger.info("  Intentando descarga pública...")
        resp = requests.get(
            public_url,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
        if _es_excel_valido(tmp):
            tmp.replace(destino)
            logger.info("  ✅ Descarga pública exitosa (%.1f KB)", destino.stat().st_size / 1024)
            return
        logger.warning("  Descarga pública devolvió HTML (login). Usando autenticación...")
        tmp.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("  Descarga pública falló: %s. Usando autenticación...", e)
        tmp.unlink(missing_ok=True)

    # Estrategia 2: Microsoft Graph API autenticado
    token = _get_access_token()
    sharing_token = _encode_sharing_url(share_link)
    headers = {"Authorization": f"Bearer {token}"}

    meta_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem",
        headers=headers,
        timeout=30,
    )
    if meta_resp.status_code == 401:
        raise RuntimeError("Token rechazado (401). Verifica MS_CLIENT_SECRET en .env.")
    if meta_resp.status_code == 403:
        raise RuntimeError(
            "Acceso denegado (403). La cuenta no tiene permisos en este archivo de SharePoint."
        )
    meta_resp.raise_for_status()
    nombre_remoto = meta_resp.json().get("name", destino.name)
    logger.info("  Archivo remoto: %s", nombre_remoto)

    dl_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem/content",
        headers=headers,
        timeout=300,
        stream=True,
    )
    dl_resp.raise_for_status()
    total = 0
    with open(tmp, "wb") as f:
        for chunk in dl_resp.iter_content(8192):
            if chunk:
                f.write(chunk)
                total += len(chunk)

    if not _es_excel_valido(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "El archivo descargado no es un Excel válido. "
            "Verifica que las credenciales tengan acceso al archivo."
        )

    tmp.replace(destino)
    logger.info("  ✅ Descarga autenticada exitosa (%.1f KB)", total / 1024)


# ═══════════════════════════════════════════════════════════════════════════════
# HASH CACHE (detección de cambios)
# ═══════════════════════════════════════════════════════════════════════════════

def _file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _load_hash_cache() -> dict:
    if HASH_CACHE_FILE.exists():
        try:
            return json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_hash_cache(cache: dict) -> None:
    HASH_CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# ETL HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_col(name: str) -> str:
    """Convierte nombre de columna a snake_case válido para PostgreSQL."""
    name = str(name).strip()
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚüÜñÑ _%]", " ", name)
    name = name.strip().lower()
    name = re.sub(r"\s+", "_", name)
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "ü": "u", "ñ": "n", "Á": "a", "É": "e", "Í": "i",
            "Ó": "o", "Ú": "u", "Ü": "u", "Ñ": "n"}
    for src, dst in repl.items():
        name = name.replace(src, dst)
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or name[0].isdigit():
        name = "col_" + name
    return name[:63]


def _load_sheets_to_schema(xlsx_path: Path, schema: str, truncate: bool = True) -> dict:
    """
    Carga todas las hojas no-vacías de un Excel al schema indicado usando
    el loader genérico de etl_nuevos_dashboards.
    Retorna dict {hoja: filas_cargadas}.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_nuevos_dashboards import load_dataframe
    from infrastructure.database.connection import connection_manager

    xl = pd.ExcelFile(xlsx_path)
    logger.info("  Hojas disponibles: %s", xl.sheet_names)
    results = {}

    with connection_manager.get_connection() as conn:
        for sheet in xl.sheet_names:
            try:
                df = pd.read_excel(xlsx_path, sheet_name=sheet)
                df = df.dropna(how="all").dropna(axis=1, how="all")
                if df.empty:
                    logger.info("  Hoja '%s' vacía, omitida", sheet)
                    continue
                table_name = _clean_col(sheet)
                n = load_dataframe(conn, schema, table_name, df, truncate=truncate)
                results[sheet] = n
            except Exception as e:
                logger.error("  Error cargando hoja '%s': %s", sheet, e, exc_info=True)
                results[sheet] = -1

    return results


def handler_etl_subsidios(xlsx_path: Path) -> dict:
    """
    Carga Base_Subsidios_DDE.xlsx → subsidios_pagos, subsidios_empresas, subsidios_mapa.
    Usa el ETL especializado de etl_subsidios.py (con hashes y lógica de dedup).
    """
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_subsidios import (
        get_connection,
        ensure_schema,
        importar_pagos,
        importar_empresas,
        importar_mapa,
    )

    logger.info("  ETL subsidios: %s", xlsx_path.name)
    conn = get_connection()
    try:
        ensure_schema(conn)
        r_pagos = importar_pagos(xlsx_path, conn)
        r_empresas = importar_empresas(xlsx_path, conn)
        r_mapa = importar_mapa(xlsx_path, conn)
        return {"pagos": r_pagos, "empresas": r_empresas, "mapa": r_mapa}
    finally:
        conn.close()


def handler_etl_presupuesto_onedrive(xlsx_path: Path) -> dict:
    """
    Carga Matriz_Ejecucion_Presupuestal_2026.xlsx → schema presupuesto.
    Carga todas las hojas con datos al schema via loader genérico.
    """
    logger.info("  ETL presupuesto onedrive: %s", xlsx_path.name)
    return _load_sheets_to_schema(xlsx_path, schema="presupuesto", truncate=True)


def handler_etl_subsidios_kpis(xlsx_path: Path) -> dict:
    """
    Carga Matriz_Subsidios_KPIs.xlsx (hojas kpis, validación, pagos, etc.)
    → schema subsidios_kpis en PostgreSQL.
    """
    logger.info("  ETL subsidios_kpis: %s", xlsx_path.name)
    return _load_sheets_to_schema(xlsx_path, schema="subsidios_kpis", truncate=True)


def handler_etl_contratos_or_onedrive(xlsx_path: Path) -> dict:
    """
    Carga Seguimiento_Contratos_CE.xlsx → schema contratos_or.
    """
    logger.info("  ETL contratos_or: %s", xlsx_path.name)
    return _load_sheets_to_schema(xlsx_path, schema="contratos_or", truncate=True)


# Mapa handler_name → función
ETL_HANDLERS = {
    "etl_subsidios": handler_etl_subsidios,
    "etl_presupuesto_onedrive": handler_etl_presupuesto_onedrive,
    "etl_subsidios_kpis": handler_etl_subsidios_kpis,
    "etl_contratos_or_onedrive": handler_etl_contratos_or_onedrive,
}


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def sincronizar_archivo(cfg: dict, forzar: bool = False, solo_descarga: bool = False) -> dict:
    """
    Descarga un archivo desde SharePoint y actualiza la BD si cambió.

    Args:
        cfg:           Entrada de SHAREPOINT_FILES.
        forzar:        Si True, ejecuta el ETL aunque el hash no haya cambiado.
        solo_descarga: Si True, descarga pero no corre el ETL.

    Returns:
        dict con status, archivo, descargado, etl_ejecutado, resultado.
    """
    nombre = cfg["nombre"]
    url = cfg["url"]
    destino = DATA_DIR / cfg["directorio"] / cfg["archivo_local"]
    handler_name = cfg["etl_handler"]

    result = {
        "nombre": nombre,
        "archivo": str(destino),
        "timestamp": datetime.now().isoformat(),
        "descargado": False,
        "etl_ejecutado": False,
        "hash_cambio": False,
        "resultado_etl": None,
        "error": None,
    }

    cache = _load_hash_cache()
    hash_previo = cache.get(nombre, "")

    try:
        # 1. Descargar
        logger.info("=" * 60)
        logger.info("📂 [%s] %s", nombre, cfg["archivo_local"])
        descargar_desde_sharepoint(url, destino)
        result["descargado"] = True

        # 2. Comparar hash
        hash_actual = _file_hash(destino)
        cambio = (hash_actual != hash_previo) or forzar

        if hash_actual != hash_previo:
            logger.info("  📝 Hash cambió → archivo actualizado en disco")
            result["hash_cambio"] = True
        elif forzar:
            logger.info("  🔁 Sin cambios pero --forzar activo → ejecutando ETL")
        else:
            logger.info("  ✓ Sin cambios (hash idéntico), ETL omitido")

        # 3. Actualizar cache
        cache[nombre] = hash_actual
        _save_hash_cache(cache)

        # 4. ETL
        if cambio and not solo_descarga:
            handler = ETL_HANDLERS.get(handler_name)
            if handler is None:
                logger.error("  ❌ Handler '%s' no registrado en ETL_HANDLERS", handler_name)
                result["error"] = f"Handler '{handler_name}' no encontrado"
            else:
                logger.info("  🗄️  Ejecutando ETL: %s", handler_name)
                t0 = time.time()
                resultado = handler(destino)
                duracion = time.time() - t0
                result["etl_ejecutado"] = True
                result["resultado_etl"] = resultado
                logger.info("  ✅ ETL completado en %.1fs → %s", duracion, resultado)

    except Exception as e:
        result["error"] = str(e)
        logger.error("  ❌ Error en [%s]: %s", nombre, e, exc_info=True)

    return result


def run_sync(
    nombres: list = None,
    forzar: bool = False,
    solo_descarga: bool = False,
) -> list:
    """
    Ejecuta la sincronización completa de todos los archivos activos
    (o solo los especificados en `nombres`).

    Args:
        nombres:       Lista de nombres de archivos a sincronizar (None = todos).
        forzar:        Ignorar hash y siempre ejecutar ETL.
        solo_descarga: Descargar archivos sin correr ETL.

    Returns:
        Lista de dicts con resultado por archivo.
    """
    archivos = [f for f in SHAREPOINT_FILES if f.get("activo", True)]
    if nombres:
        archivos = [f for f in archivos if f["nombre"] in nombres]
        if not archivos:
            logger.warning("No se encontraron archivos con los nombres: %s", nombres)

    logger.info("🚀 Iniciando sincronización SharePoint → PostgreSQL")
    logger.info("   Archivos a procesar: %d", len(archivos))
    logger.info("   Modo: %s", "solo descarga" if solo_descarga else ("forzar ETL" if forzar else "normal"))

    resultados = []
    for cfg in archivos:
        r = sincronizar_archivo(cfg, forzar=forzar, solo_descarga=solo_descarga)
        resultados.append(r)

    exitosos = sum(1 for r in resultados if r["error"] is None)
    fallidos = len(resultados) - exitosos
    etl_ejecutados = sum(1 for r in resultados if r["etl_ejecutado"])

    logger.info("=" * 60)
    logger.info("🏁 Sincronización completada")
    logger.info("   Exitosos: %d / %d", exitosos, len(resultados))
    logger.info("   ETLs ejecutados: %d", etl_ejecutados)
    if fallidos:
        logger.error("   ❌ Fallidos: %d", fallidos)
        for r in resultados:
            if r["error"]:
                logger.error("     - %s: %s", r["nombre"], r["error"])

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ETL: Sincronización SharePoint → data/ → PostgreSQL"
    )
    parser.add_argument(
        "--archivo",
        type=int,
        metavar="N",
        help="Procesar solo el archivo número N (1-indexed)",
    )
    parser.add_argument(
        "--nombre",
        type=str,
        metavar="NOMBRE",
        help="Procesar solo el archivo con este nombre (ej: Matriz_Subsidios_DEE)",
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Ignorar hash y ejecutar ETL aunque el archivo no haya cambiado",
    )
    parser.add_argument(
        "--solo-descarga",
        action="store_true",
        help="Solo descargar archivos, sin ejecutar ETL en la BD",
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Listar archivos configurados y salir",
    )
    args = parser.parse_args()

    if args.listar:
        print("\nArchivos configurados:")
        for i, f in enumerate(SHAREPOINT_FILES, 1):
            estado = "✓" if f.get("activo", True) else "✗"
            print(f"  {i}. [{estado}] {f['nombre']}")
            print(f"       → data/{f['directorio']}/{f['archivo_local']}")
            print(f"       → handler: {f['etl_handler']}")
        return

    nombres = None
    if args.archivo:
        if args.archivo < 1 or args.archivo > len(SHAREPOINT_FILES):
            print(f"❌ Número inválido. Use 1-{len(SHAREPOINT_FILES)}")
            sys.exit(1)
        nombres = [SHAREPOINT_FILES[args.archivo - 1]["nombre"]]
    elif args.nombre:
        nombres = [args.nombre]

    resultados = run_sync(
        nombres=nombres,
        forzar=args.forzar,
        solo_descarga=args.solo_descarga,
    )

    # Código de salida: 1 si alguno falló
    if any(r["error"] for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
