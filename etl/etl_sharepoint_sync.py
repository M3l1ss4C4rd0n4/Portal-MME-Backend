#!/usr/bin/env python3
"""
ETL: Sincronización automática Excel SharePoint → data/ → PostgreSQL
=====================================================================

Descarga archivos Excel desde SharePoint del Ministerio (vía Microsoft Graph API),
detecta cambios por hash SHA-256 y ejecuta el ETL correspondiente en PostgreSQL.

Archivos configurados:
  1. Matriz_General_Reparto   → Matriz_General_Reparto.xlsx → schema supervision (3 tablas)
  2. Acuerdos_Gestion_DEE_2026 → Acuerdos_Gestion_DEE_2026.xlsx → schema presupuesto
  3. Base_Subsidios_DDE       → Base_Subsidios_DDE.xlsx      → schema subsidios (4 tablas)
  4. Seguimiento_Contratos_CE → Seguimiento_Contratos_CE.xlsx → contratos_or.seguimiento
  5. Comunidades_Seguimiento_FENOGE → comunidades_seguimiento_fenoge.xlsx → fenoge.seguimiento
  6. Deficit_Historico_Subsidios → Deficit_Historico_Subsidios.xlsx → subsidios.deficit_historico
  7. Comunidades_Energeticas_FENOGE → Comunidades_Energeticas_fenoge.xlsx → fenoge.comunidades
  8. Colombia_Solar_OR        → Colombia_Solar_OR.xlsx       → schema colombia_solar

NOTA: Matriz_Subsidios_KPIs.xlsx tiene handler pero NO está en SHAREPOINT_FILES (ver Error #2)

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
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
# Estado unificado: usa .sp_watcher_state.json (compartido con watcher)
HASH_CACHE_FILE = Path(__file__).resolve().parent / ".sp_watcher_state.json"
LOCK_FILE = Path("/tmp/etl_sharepoint_sync.lock")
_lock_fd = None

LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
# Solo StreamHandler en terminal real; evita duplicados cuando cron redirige con >>
_log_handlers = [logging.FileHandler(LOG_DIR / "etl_sharepoint_sync.log", encoding="utf-8")]
if sys.stdout.isatty():
    _log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ETL_SP_SYNC] %(levelname)s - %(message)s",
    handlers=_log_handlers,
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
        "nombre": "Matriz_General_Reparto",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/DireccindeEnergaElctrica-DEE_Supervision/Shared%20Documents/DEE_Supervision/Direccion_Energia/Matriz%20General%20de%20Reparto/Matriz%20General%20de%20Reparto.xlsx?d=w8c044b58604d45da93d9015fb9bb6047&csf=1&web=1&e=Wqa94s",
        "archivo_local": "Matriz_General_Reparto.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_supervision_onedrive",
        "activo": True,
        "timeout_descarga": (60, 3600),  # 83 MB — connect 60s, read 60min (red lenta ~85KB/s necesita ~16min)
        "etl_timeout": 1800,            # 83 MB — subprocess timeout 30min
    },
    {
        "nombre": "Acuerdos_Gestion_DEE_2026",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/08.%20Administrativo%20y%20Planeaci%C3%B3n/03.%20Gesti%C3%B3n%20Presupuestal/Ejecuci%C3%B3n%20presupuetal%202026/Acuerdos%20de%20Gesti%C3%B3n%20DEE%202026.xlsx?d=wd7f413e7766b4bd4ae857977be8d51ff&csf=1&web=1&e=T8S8d6",
        "archivo_local": "Acuerdos_Gestion_DEE_2026.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_presupuesto_onedrive",
        "activo": True,
    },
    {
        "nombre": "Base_Subsidios_DDE",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/06.%20Subsidios/3.%20Base%20datos_subsidios/Base_Subsidios_DDE.xlsx?d=w751521b215fe4300a14005067d142fb6&csf=1&web=1&e=8o5kyO",
        "archivo_local": "Base_Subsidios_DDE.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_subsidios",
        "activo": True,
    },
    {
        "nombre": "Seguimiento_Contratos_CE",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/01.%20Comunidades%20Energ%C3%A9ticas/Data_CE/Seguimiento%20Completo_CE_Contratos.xlsx?d=w0a6a50a7545b4dde8da1897bc546d23e&csf=1&web=1&e=eJXmPx",
        "archivo_local": "Seguimiento_Contratos_CE.xlsx",
        "directorio": "base_de_datos_contratos_or",
        "etl_handler": "etl_contratos_or_onedrive",
        "activo": True,
    },
    {
        "nombre": "Comunidades_Seguimiento_FENOGE",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/01.%20Comunidades%20Energ%C3%A9ticas/Data_CE/comunidades_seguimiento_fenoge.xlsx?d=wf6819f9ff81b413eb7b8e97ea59f6560&csf=1&web=1&e=0f7rbQ",
        "archivo_local": "comunidades_seguimiento_fenoge.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_fenoge_seguimiento",
        "activo": True,
    },
    {
        "nombre": "Deficit_Historico_Subsidios",
        "url": "https://minenergiacol-my.sharepoint.com/:x:/r/personal/dmgutierrez_minenergia_gov_co/Documents/Archivos%20de%20chat%20de%20Microsoft%20Teams/2026-02-17%20Info%20Subs%20y%20Cont%20-%20Info%20tablero%20(1).xlsx?d=wea07217bf77d4ec6a5a5ab58d2158b74&csf=1&web=1&e=tlAXds",
        "archivo_local": "Deficit_Historico_Subsidios.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_deficit_historico",
        "activo": True,
    },
    {
        "nombre": "Comunidades_Energeticas_FENOGE",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/01.%20Comunidades%20Energ%C3%A9ticas/Data_CE/Comunidades%20Energeticas_fenoge.xlsx?d=wa4e9bdf1ac074f2f85b09a714c7f18b9&csf=1&web=1&e=ZLHhBn",
        "archivo_local": "Comunidades_Energeticas_fenoge.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_fenoge_comunidades",
        "activo": True,
    },
    {
        "nombre": "Colombia_Solar_OR",
        "url": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/Shared%20Documents/General/19.%20PMO/1.%20Contratos%20OR/Cuadro%20Inaguraciones_Colombia%20Solar%20Completo_CE_OR.xlsx?d=w8cdcddc1db3c4bf99505c63fcbcafa31&csf=1&web=1&e=vMfvtg",
        "archivo_local": "Colombia_Solar_OR.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_colombia_solar",
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


def _write_chunks_with_rate_limit(resp, f, rate_limit: int | None, chunk_size: int = 1024 * 1024) -> int:
    """Escribe chunks respetando un throughput máximo para evitar throttling.

    Usa un acumulador global (bytes / tiempo transcurrido) en lugar de
    penalizar chunks pequeños que entrega el servidor.

    Args:
        resp: objeto requests.Response con stream=True
        f: file object abierto en modo escritura binaria
        rate_limit: bytes por segundo máximo (None = sin límite)
        chunk_size: tamaño de chunk para iter_content

    Returns:
        Total de bytes escritos.
    """
    total = 0
    t_start = time.monotonic()
    for chunk in resp.iter_content(chunk_size):
        if chunk:
            f.write(chunk)
            f.flush()
            total += len(chunk)
            if rate_limit:
                expected_time = total / rate_limit
                elapsed = time.monotonic() - t_start
                if elapsed < expected_time:
                    time.sleep(expected_time - elapsed)
    return total


def _download_in_chunks(download_url: str, tmp: Path, file_size: int, chunk_size: int = 20 * 1024 * 1024) -> None:
    """Descarga archivo por chunks usando HTTP Range. Más robusto para archivos grandes."""
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    with open(tmp, "wb") as f:
        for start in range(0, file_size, chunk_size):
            end = min(start + chunk_size - 1, file_size - 1)
            chunk_num = start // chunk_size + 1
            logger.info("  ⬇️  Chunk %d/%d: bytes %d-%d", chunk_num, total_chunks, start, end)
            resp = requests.get(
                download_url,
                headers={"Range": f"bytes={start}-{end}"},
                timeout=(30, 300),
            )
            resp.raise_for_status()
            f.write(resp.content)
            f.flush()


def descargar_desde_sharepoint(
    share_link: str,
    destino: Path,
    timeout: tuple = (30, 1800),
    rate_limit_bytes_per_sec: int | None = None,
) -> None:
    """
    Descarga un archivo de SharePoint al path indicado.
    Intenta primero descarga pública, luego autenticada vía Graph API.

    Args:
        timeout: (connect_seconds, read_seconds) para la descarga autenticada.
                 Aumentar para archivos grandes (>50 MB).
        rate_limit_bytes_per_sec: Límite de velocidad en bytes/seg para evitar
                 throttling de SharePoint (ej. 512*1024 = ~500 KB/s).

    Raises:
        RuntimeError si la descarga falla después de ambas estrategias.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    connect_timeout = timeout[0]

    # Estrategia 1: descarga pública (?download=1)
    # Para descarga pública NO usamos reanudación (rara vez soporta Range).
    tmp.unlink(missing_ok=True)
    sep = "&" if "?" in share_link else "?"
    public_url = f"{share_link}{sep}download=1"
    try:
        logger.info("  Intentando descarga pública...")
        resp = requests.get(
            public_url,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
            timeout=(connect_timeout, min(timeout[1], 300)),
            stream=True,
        )
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            _write_chunks_with_rate_limit(resp, f, rate_limit_bytes_per_sec, chunk_size=8192)
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
        timeout=(connect_timeout, 30),
    )
    if meta_resp.status_code == 401:
        raise RuntimeError("Token rechazado (401). Verifica MS_CLIENT_SECRET en .env.")
    if meta_resp.status_code == 403:
        raise RuntimeError(
            "Acceso denegado (403). La cuenta no tiene permisos en este archivo de SharePoint."
        )
    meta_resp.raise_for_status()
    meta_data = meta_resp.json()
    nombre_remoto = meta_data.get("name", destino.name)
    logger.info("  Archivo remoto: %s", nombre_remoto)

    download_url = meta_data.get("@microsoft.graph.downloadUrl")
    if not download_url:
        logger.info("  🐢 downloadUrl no disponible, usando Graph API /content...")
        download_url = f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem/content"
        dl_headers = headers
    else:
        logger.info("  ⚡ Usando downloadUrl (read timeout %ds)...", timeout[1])
        dl_headers = {}

    # ── Reanudación de descarga (HTTP Range) ───────────────────────────────
    resume_from = 0
    if tmp.exists():
        resume_from = tmp.stat().st_size
        if resume_from > 0:
            logger.info("  🔄 Reanudando descarga desde %.1f KB (%d bytes)", resume_from / 1024, resume_from)
            dl_headers["Range"] = f"bytes={resume_from}-"
        else:
            resume_from = 0

    size_remoto = meta_data.get("size", 0)

    # Para archivos grandes (>50 MB) sin reanudación, descarga por chunks (HTTP Range)
    # es más robusta contra conexiones que se cortan silenciosamente.
    if size_remoto > 50 * 1024 * 1024 and resume_from == 0:
        logger.info("  📦 Archivo grande (%.1f MB), usando descarga por chunks...", size_remoto / 1024 / 1024)
        _download_in_chunks(download_url, tmp, size_remoto)
    else:
        dl_resp = requests.get(
            download_url,
            headers=dl_headers if dl_headers else None,
            timeout=timeout,
            stream=True,
        )
        dl_resp.raise_for_status()

        # Si usamos Range y el servidor responde 206, abrimos en append.
        # Si responde 200 (ignoró Range), truncamos y empezamos de cero.
        mode = "ab" if (resume_from > 0 and dl_resp.status_code == 206) else "wb"
        if mode == "wb" and resume_from > 0:
            logger.warning("  Servidor ignoró Range, reiniciando descarga desde cero")
            resume_from = 0

        with open(tmp, mode) as f:
            total = _write_chunks_with_rate_limit(
                dl_resp, f, rate_limit_bytes_per_sec, chunk_size=1024 * 1024
            )

    if not _es_excel_valido(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "El archivo descargado no es un Excel válido. "
            "Verifica que las credenciales tengan acceso al archivo."
        )

    tmp.replace(destino)
    logger.info("  ✅ Descarga autenticada exitosa (%.1f KB)", destino.stat().st_size / 1024)


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
    """Carga el mapa nombre → hash desde el estado unificado.
    El archivo .sp_watcher_state.json tiene formato:
    { "NombreArchivo": { "content_hash": "sha256", "lastModifiedDateTime": ..., ... } }
    """
    if HASH_CACHE_FILE.exists():
        try:
            state = json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
            return {k: v.get("content_hash", "") for k, v in state.items() if isinstance(v, dict)}
        except Exception:
            return {}
    return {}


_BOGOTA = timezone(timedelta(hours=-5))


def _sp_ts_to_bogota(iso: str) -> datetime | None:
    """Convierte timestamp ISO de SharePoint (UTC) a datetime con tz America/Bogota (-5h)."""
    try:
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(_BOGOTA)
    except Exception:
        return None


def _load_fecha_fuente(nombre: str) -> datetime | None:
    """Lee lastModifiedDateTime del estado del watcher para el archivo indicado."""
    try:
        state = json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
        iso = state.get(nombre, {}).get("lastModifiedDateTime", "")
        return _sp_ts_to_bogota(iso) if iso else None
    except Exception:
        return None


def _save_hash_cache(cache: dict) -> None:
    """Guarda los hashes en el estado unificado, preservando metadatos del watcher.
    cache: { "NombreArchivo": "sha256", ... }
    """
    state = {}
    if HASH_CACHE_FILE.exists():
        try:
            state = json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    for nombre, hash_val in cache.items():
        if nombre not in state or not isinstance(state[nombre], dict):
            state[nombre] = {}
        state[nombre]["content_hash"] = hash_val

    HASH_CACHE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


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


def _load_sheets_to_schema(
    xlsx_path: Path,
    schema: str,
    truncate: bool = True,
    header_overrides: dict | None = None,
    fecha_carga_override: datetime | None = None,
    sheets_exclude: set[str] | frozenset[str] | None = None,
    skip_duplicate_tables: bool = True,
    drop_orphan_tables: bool = False,
) -> dict:
    """
    Carga todas las hojas no-vacías de un Excel al schema indicado usando
    el loader genérico de etl_nuevos_dashboards.
    Retorna dict {hoja: filas_cargadas}.
    header_overrides: {nombre_hoja: fila_encabezado} para hojas con filas vacías iniciales.
    sheets_exclude: hojas a omitir (duplicados, vacías, auxiliares).
    skip_duplicate_tables: si dos hojas mapean al mismo nombre de tabla, carga solo la primera.
    drop_orphan_tables: elimina tablas del schema que ya no provienen del Excel actual.

    ATÓMICO: todas las hojas se cargan en una sola transacción.
    Si una hoja falla, se hace ROLLBACK y ninguna tabla se modifica.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_nuevos_dashboards import load_dataframe
    from infrastructure.database.connection import connection_manager

    xl = pd.ExcelFile(xlsx_path)
    logger.info("  Hojas disponibles: %s", xl.sheet_names)
    overrides = header_overrides or {}
    exclude = set(sheets_exclude or [])
    results: dict = {}
    loaded_tables: set[str] = set()

    with connection_manager.get_connection() as conn:
        try:
            # Drop target tables first so new columns from the Excel are picked up on recreate.
            with conn.cursor() as cur:
                for sheet in xl.sheet_names:
                    if sheet in exclude:
                        continue
                    table_name = _clean_col(sheet)
                    if skip_duplicate_tables and table_name in loaded_tables:
                        continue
                    loaded_tables.add(table_name)
                    cur.execute(f'DROP TABLE IF EXISTS {schema}."{table_name}" CASCADE;')

            loaded_tables.clear()
            for sheet in xl.sheet_names:
                if sheet in exclude:
                    logger.info("  Hoja '%s' excluida por configuración", sheet)
                    continue

                table_name = _clean_col(sheet)
                if skip_duplicate_tables and table_name in loaded_tables:
                    logger.info(
                        "  Hoja '%s' omitida (tabla '%s' ya cargada desde otra hoja)",
                        sheet,
                        table_name,
                    )
                    continue

                header_row = overrides.get(sheet, 0)
                df = pd.read_excel(xlsx_path, sheet_name=sheet, header=header_row)
                df = df.dropna(how="all").dropna(axis=1, how="all")
                if df.empty:
                    logger.info("  Hoja '%s' vacía, omitida", sheet)
                    continue
                n = load_dataframe(
                    conn,
                    schema,
                    table_name,
                    df,
                    truncate=truncate,
                    commit=False,
                    fecha_carga_override=fecha_carga_override,
                )
                results[sheet] = n
                loaded_tables.add(table_name)

            if drop_orphan_tables and loaded_tables:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = %s AND table_type = 'BASE TABLE'
                        """,
                        (schema,),
                    )
                    existing = {row[0] for row in cur.fetchall()}
                    for orphan in sorted(existing - loaded_tables):
                        cur.execute(f'DROP TABLE IF EXISTS {schema}."{orphan}" CASCADE;')
                        logger.info("  🗑  Tabla obsoleta eliminada: %s.%s", schema, orphan)

            conn.commit()
            logger.info(
                "  ✅ Transacción commiteada: %d hojas cargadas",
                len([v for v in results.values() if v >= 0]),
            )
        except Exception as e:
            conn.rollback()
            logger.error("  ❌ Error atómico en carga de hojas — ROLLBACK ejecutado: %s", e, exc_info=True)
            raise

    return results


def handler_etl_subsidios(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
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
        r_pagos    = importar_pagos(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_empresas = importar_empresas(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_mapa     = importar_mapa(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_kpis     = _importar_kpis_resumen(xlsx_path, conn)

        # Alerta temprana: si la BD quedó con menos del 80% de filas del Excel, algo falló
        filas_excel = r_pagos.get("filas_leidas", 0)
        filas_bd    = r_pagos.get("filas_leidas", 0) - r_pagos.get("filas_duplicadas", 0)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subsidios.subsidios_pagos")
            filas_bd_real = cur.fetchone()[0]
        if filas_excel > 0 and filas_bd_real < filas_excel * 0.8:
            logger.warning(
                "  ⚠ subsidios_pagos: BD tiene %d filas pero Excel tiene %d — posible pérdida de datos",
                filas_bd_real, filas_excel,
            )
        else:
            logger.info("  ✅ Conteo OK: BD=%d filas (Excel=%d)", filas_bd_real, filas_excel)

        return {"pagos": r_pagos, "empresas": r_empresas, "mapa": r_mapa, "kpis_resumen": r_kpis}
    finally:
        conn.close()


def _importar_kpis_resumen(xlsx_path: Path, conn) -> dict:
    """
    Lee la hoja 'KPI'S Subsidios' de Base_Subsidios_DDE.xlsx y upserta
    los KPIs anuales (asignado, pendiente, resoluciones, déficit) en
    subsidios.kpis_resumen.
    Estructura fija del sheet:
      fila 12: [NaN, 2025, 2026]   ← encabezados de año
      fila 13: ['Deficit', v2025, NaN]
      fila 14: ['Número resoluciones expedidas', v2025, v2026]
      fila 15: ['Valor Asignado Resoluciones', v2025, v2026]
      fila 16: ['Valor Pendiente pago', v2025, v2026]
    """
    import pandas as pd
    import math

    def _num(v):
        if v is None:
            return None
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    try:
        df = pd.read_excel(xlsx_path, sheet_name="KPI'S Subsidios", header=None)
        # Localizar fila de encabezados de año (contiene 2025 y 2026)
        header_row = df[df.apply(lambda r: 2025 in r.values and 2026 in r.values, axis=1)]
        if header_row.empty:
            logger.warning("  kpis_resumen: no se encontró fila de años en el sheet")
            return {}
        hi = header_row.index[0]
        cols = list(df.iloc[hi])
        anios = {str(int(c)): idx for idx, c in enumerate(cols) if str(c) in ("2025", "2026")}

        # Leer filas de datos (hi+1 a hi+4)
        data_rows = df.iloc[hi + 1: hi + 5].reset_index(drop=True)

        def _val(row_offset, anio_str):
            if anio_str not in anios:
                return None
            return _num(data_rows.iloc[row_offset, anios[anio_str]])

        registros = []
        for anio_str in ("2025", "2026"):
            registros.append({
                "anio":            int(anio_str),
                "deficit":         _val(0, anio_str),   # fila Deficit
                "n_resoluciones":  _val(1, anio_str),   # fila Número resoluciones
                "valor_asignado":  _val(2, anio_str),   # fila Valor Asignado
                "valor_pendiente": _val(3, anio_str),   # fila Valor Pendiente
            })

        cur = conn.cursor()
        for r in registros:
            cur.execute("""
                INSERT INTO subsidios.kpis_resumen
                    (anio, valor_asignado, valor_pendiente, n_resoluciones, deficit, fecha_carga)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (anio) DO UPDATE SET
                    valor_asignado  = EXCLUDED.valor_asignado,
                    valor_pendiente = EXCLUDED.valor_pendiente,
                    n_resoluciones  = EXCLUDED.n_resoluciones,
                    deficit         = EXCLUDED.deficit,
                    fecha_carga     = NOW()
            """, (r["anio"], r["valor_asignado"], r["valor_pendiente"],
                  r["n_resoluciones"], r["deficit"]))
        conn.commit()
        logger.info("  kpis_resumen: %d registros upserted", len(registros))
        return {"filas": len(registros)}
    except Exception as e:
        logger.error("  kpis_resumen error: %s", e, exc_info=True)
        return {"error": str(e)}


def handler_etl_presupuesto_onedrive(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Matriz_Ejecucion_Presupuestal_2026.xlsx → schema presupuesto.
    Carga todas las hojas con datos al schema via loader genérico.
    """
    logger.info("  ETL presupuesto onedrive: %s", xlsx_path.name)
    # La hoja 'resumen' tiene 3 filas vacías antes de los encabezados reales
    return _load_sheets_to_schema(
        xlsx_path, schema="presupuesto", truncate=True,
        header_overrides={"resumen": 3},
        fecha_carga_override=fecha_fuente,
    )


def handler_etl_contratos_or_onedrive(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Seguimiento_Contratos_CE.xlsx → schema contratos_or.
    """
    logger.info("  ETL contratos_or: %s", xlsx_path.name)
    return _load_sheets_to_schema(xlsx_path, schema="contratos_or", truncate=True, fecha_carga_override=fecha_fuente)


def _nan_to_none(v):
    """Convierte NaN/NaT/espacios de pandas a None para psycopg2."""
    import math
    import pandas as pd
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _df_to_table(conn, schema: str, table: str, df, cols: list, fecha_carga: "datetime | None" = None) -> int:
    """TRUNCATE + INSERT masivo de un DataFrame a una tabla tipada existente."""
    cursor = conn.cursor()
    cursor.execute(f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY")
    all_cols = cols + (["fecha_carga"] if fecha_carga is not None else [])
    placeholders = ", ".join(["%s"] * len(all_cols))
    col_names = ", ".join(all_cols)
    insert_sql = f"INSERT INTO {schema}.{table} ({col_names}) VALUES ({placeholders})"
    rows = [
        tuple(_nan_to_none(v) for v in row) + ((fecha_carga,) if fecha_carga is not None else ())
        for row in df[cols].itertuples(index=False, name=None)
    ]
    cursor.executemany(insert_sql, rows)

    # Verificar que la BD quedó con el mismo conteo que el DataFrame
    cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
    bd_count = cursor.fetchone()[0]
    if bd_count != len(rows):
        raise RuntimeError(
            f"{schema}.{table}: se esperaban {len(rows)} filas pero la BD tiene {bd_count}"
        )

    conn.commit()
    return len(rows)


def handler_etl_supervision_onedrive(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Matriz_General_Reparto.xlsx → schema supervision.
    Mapea explícitamente cada hoja a la tabla que lee la API del portal.

    ATÓMICO: las 3 tablas se cargan en una sola transacción.
    Si una falla, se hace ROLLBACK y ninguna tabla se modifica.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_nuevos_dashboards import load_dataframe
    from infrastructure.database.connection import connection_manager

    logger.info("  ETL supervision: %s", xlsx_path.name)

    sheet_table_map = {
        "Matriz General de Reparto": "contratos",
        "Grupo liquidacion":         "contratos_liquidacion",
        "Grupo Ejecucion":           "contratos_ejecucion",
    }

    results = {}
    with connection_manager.get_connection() as conn:
        try:
            # Drop tables so new columns from the Excel are picked up on recreate
            with conn.cursor() as cur:
                for table in sheet_table_map.values():
                    cur.execute(f'DROP TABLE IF EXISTS supervision."{table}" CASCADE;')

            for sheet, table in sheet_table_map.items():
                df = pd.read_excel(xlsx_path, sheet_name=sheet, header=0)
                df = df.dropna(how="all").dropna(axis=1, how="all")
                if df.empty:
                    logger.info("  Hoja '%s' vacía, omitida", sheet)
                    continue
                n = load_dataframe(conn, "supervision", table, df, truncate=True, commit=False, fecha_carga_override=fecha_fuente)
                results[table] = n

            conn.commit()
            logger.info("  ✅ Transacción commiteada: %d tablas cargadas", len(results))
        except Exception as e:
            conn.rollback()
            logger.error("  ❌ Error atómico en supervision — ROLLBACK ejecutado: %s", e, exc_info=True)
            raise

    return results


_FENOGE_SEG_MAP = {
    "region": "region",
    "numero_de_contrato": "numero_contrato",
    "dia_actualizacion": "dia_actualizacion",
    "mes_no": "mes_no",
    "real_financiero": "real_financiero",
    "programado": "programado",
    "real_acumulado": "real_acumulado_pesos",
    "programado_acumulado": "programado_acumulado_pesos",
    "seguimiento_avance_de_obra_real": "avance_real_pct",
    "seguimiento_avance_de_obra_programado": "avance_programado_pct",
    "seguimiento_avance_de_obra_real_acumulado": "avance_real_acumulado_pct",
    "seguimiento_avance_de_obra_programado_acumulado": "avance_programado_acumulado_pct",
}

_FENOGE_COM_MAP = {
    "departamento": "departamento",
    "municipio": "municipio",
    "comunidad": "comunidad",
    "latitud": "latitud",
    "longitud": "longitud",
    "kwp": "kwp",
    "beneficiarios": "beneficiarios",
    "valor_del_kwp": "valor_kwp",
    "valor_del_proyecto": "valor_proyecto",
    "fase": "fase",
    "lote": "lote",
    "contratista": "contratista",
    "n_de_contrato": "numero_contrato",
    "fecha_inicio_del_contrato": "fecha_inicio",
    "fecha_final_del_contrato": "fecha_fin",
    "operador_de_red": "operador_red",
}


def handler_etl_fenoge_seguimiento(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga comunidades_seguimiento_fenoge.xlsx → fenoge.seguimiento.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from infrastructure.database.connection import connection_manager

    logger.info("  ETL fenoge.seguimiento: %s", xlsx_path.name)
    df = pd.read_excel(xlsx_path, sheet_name=0)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [_clean_col(c) for c in df.columns]
    df = df.rename(columns=_FENOGE_SEG_MAP)
    db_cols = [c for c in _FENOGE_SEG_MAP.values() if c in df.columns]
    logger.info("  Columnas mapeadas: %s", db_cols)

    # Forzar formato DD/MM/YYYY para fechas (evita MDY por defecto en PostgreSQL)
    if "dia_actualizacion" in df.columns:
        df["dia_actualizacion"] = pd.to_datetime(
            df["dia_actualizacion"], dayfirst=True, errors="coerce"
        ).dt.date

    with connection_manager.get_connection() as conn:
        n = _df_to_table(conn, "fenoge", "seguimiento", df, db_cols, fecha_carga=fecha_fuente)

    logger.info("  fenoge.seguimiento: %d filas cargadas", n)
    return {"filas": n}


def _parse_cop_currency(series):
    """Parsea formato moneda COP: ' $ 6.800.000,00' → 6800000.0"""
    import pandas as pd
    return (
        series.astype(str)
        .str.replace(r"[\$\s]", "", regex=True)   # quitar $ y espacios
        .str.replace(".", "", regex=False)          # quitar separador miles
        .str.replace(",", ".", regex=False)         # coma decimal → punto
        .pipe(pd.to_numeric, errors="coerce")
    )


def handler_etl_fenoge_comunidades(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Comunidades_Energeticas_fenoge.xlsx → fenoge.comunidades.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from infrastructure.database.connection import connection_manager

    logger.info("  ETL fenoge.comunidades: %s", xlsx_path.name)
    df = pd.read_excel(xlsx_path, sheet_name=0)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [_clean_col(c) for c in df.columns]
    df = df.rename(columns=_FENOGE_COM_MAP)
    db_cols = [c for c in _FENOGE_COM_MAP.values() if c in df.columns]
    logger.info("  Columnas mapeadas: %s", db_cols)

    # Limpiar columnas de moneda COP que el Excel trae como strings con formato "$ X.XXX.XXX,YY"
    for col in ("valor_kwp", "valor_proyecto"):
        if col in df.columns and df[col].dtype == object:
            df[col] = _parse_cop_currency(df[col])

    # Coordenadas con coma decimal ("6,66" → 6.66)
    for col in ("latitud", "longitud"):
        if col in df.columns and df[col].dtype == object:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )

    # Normalizar fechas: el Excel mezcla datetime objects y strings "DD/MM/YYYY"
    for col in ("fecha_inicio", "fecha_fin"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    with connection_manager.get_connection() as conn:
        n = _df_to_table(conn, "fenoge", "comunidades", df, db_cols, fecha_carga=fecha_fuente)

    logger.info("  fenoge.comunidades: %d filas cargadas", n)
    return {"filas": n}


def handler_etl_deficit_historico(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Info tablero.xlsx Hoja5 → subsidios.deficit_historico.
    Columnas: anio, subsidios, contribuciones, deficit_anual,
              apropiacion_pgn, recursos_faltantes, deficit_acumulado.
    """
    import pandas as pd
    sys.path.insert(0, str(BASE_DIR))
    from infrastructure.database.connection import connection_manager

    logger.info("  ETL deficit_historico: %s", xlsx_path.name)
    df = pd.read_excel(xlsx_path, sheet_name="Hoja5")
    df = df.dropna(how="all")

    col_map = {
        "Año":                    "anio",
        "Subsidios (SIN+ZNI)":    "subsidios",
        "Contribuciones":         "contribuciones",
        "Déficit Año":            "deficit_anual",
        "Apropiación PGN":        "apropiacion_pgn",
        "Recursos Faltantes Año": "recursos_faltantes",
        "Deficit acumulado":      "deficit_acumulado",
    }
    df = df.rename(columns=col_map)
    db_cols = [v for v in col_map.values() if v in df.columns]

    # Filtrar solo filas con año numérico válido
    df = df[pd.to_numeric(df["anio"], errors="coerce").notna()]
    df["anio"] = df["anio"].astype(int)

    with connection_manager.get_connection() as conn:
        n = _df_to_table(conn, "subsidios", "deficit_historico", df, db_cols, fecha_carga=fecha_fuente)

    logger.info("  deficit_historico: %d filas cargadas", n)
    return {"filas": n}


# Hojas auxiliares o duplicadas que colisionan al normalizar nombre → tabla PG
COLOMBIA_SOLAR_SHEETS_EXCLUDE = frozenset({
    "Gráficas_General",
    "Hoja1",
    "Hoja3",
    "TD ",                      # duplicado de "TD" (misma tabla td)
    "Base General_OR_Inicial",  # duplicado de "Base General OR_Inicial"
})


def handler_etl_colombia_solar(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Colombia_Solar_OR.xlsx → schema colombia_solar.
    Hojas principales:
      - Base General OR_Inicial, Base, TD, Seguimiento Diario
      - Proyectado/Reportado: Obras Civiles, Internas, Usuarios, Potencia
    """
    logger.info("  ETL colombia_solar: %s", xlsx_path.name)
    return _load_sheets_to_schema(
        xlsx_path,
        schema="colombia_solar",
        truncate=True,
        fecha_carga_override=fecha_fuente,
        sheets_exclude=COLOMBIA_SOLAR_SHEETS_EXCLUDE,
        skip_duplicate_tables=True,
        drop_orphan_tables=True,
        header_overrides={
            "Base": 1,
            "Seguimiento Diario": 2,
        },
    )


# Mapa handler_name → función
ETL_HANDLERS = {
    "etl_subsidios": handler_etl_subsidios,
    "etl_presupuesto_onedrive": handler_etl_presupuesto_onedrive,
    "etl_contratos_or_onedrive": handler_etl_contratos_or_onedrive,
    "etl_supervision_onedrive": handler_etl_supervision_onedrive,
    "etl_fenoge_seguimiento": handler_etl_fenoge_seguimiento,
    "etl_fenoge_comunidades": handler_etl_fenoge_comunidades,
    "etl_deficit_historico": handler_etl_deficit_historico,
    "etl_colombia_solar": handler_etl_colombia_solar,
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
        # 1. Descargar (hasta 4 intentos con backoff exponencial)
        timeout_dl = cfg.get("timeout_descarga", (30, 1800))
        if not (isinstance(timeout_dl, tuple) and len(timeout_dl) == 2):
            raise ValueError(f"[{nombre}] timeout_descarga debe ser una tupla (connect, read), got: {timeout_dl!r}")
        logger.info("=" * 60)
        logger.info("📂 [%s] %s", nombre, cfg["archivo_local"])
        max_intentos = 4
        for intento in range(1, max_intentos + 1):
            try:
                rate_limit = cfg.get("rate_limit_bytes_per_sec")
                descargar_desde_sharepoint(url, destino, timeout=timeout_dl, rate_limit_bytes_per_sec=rate_limit)
                result["descargado"] = True
                break
            except Exception as dl_err:
                if intento < max_intentos:
                    espera = min(60 * (2 ** (intento - 1)), 300)  # 60s, 120s, 240s
                    logger.warning("  ⚠️  Intento %d/%d falló (%s). Reintentando en %ds…",
                                   intento, max_intentos, dl_err, espera)
                    time.sleep(espera)
                else:
                    raise

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

        # 3. ETL — el hash solo se persiste si el ETL termina OK (ver paso 4)
        etl_ok = False
        if cambio and not solo_descarga:
            handler = ETL_HANDLERS.get(handler_name)
            if handler is None:
                logger.error("  ❌ Handler '%s' no registrado en ETL_HANDLERS", handler_name)
                result["error"] = f"Handler '{handler_name}' no encontrado"
            else:
                logger.info("  🗄️  Ejecutando ETL: %s", handler_name)
                fecha_fuente = _load_fecha_fuente(nombre)
                if fecha_fuente:
                    logger.info(
                        "  📅 fecha_fuente SharePoint → %s",
                        fecha_fuente.strftime("%d/%m/%Y %H:%M (Bogotá)"),
                    )
                t0 = time.time()
                resultado = handler(destino, fecha_fuente=fecha_fuente)
                duracion = time.time() - t0
                etl_ok = True
                result["etl_ejecutado"] = True
                result["resultado_etl"] = resultado
                logger.info("  ✅ ETL completado en %.1fs → %s", duracion, resultado)

        # 4. Persistir hash solo tras ETL exitoso (o si no hubo cambio — hash ya válido)
        if not solo_descarga and etl_ok:
            cache[nombre] = hash_actual
            _save_hash_cache(cache)
        elif cambio and not solo_descarga and not etl_ok:
            logger.warning(
                "  ⚠️  Hash NO actualizado para [%s] — se reintentará en el próximo ciclo",
                nombre,
            )

    except Exception as e:
        result["error"] = str(e)
        logger.error("  ❌ Error en [%s]: %s", nombre, e, exc_info=True)

    return result


def _acquire_lock() -> bool:
    """Intenta adquirir el lock file. Retorna True si se adquirió, False si ya está ocupado."""
    import fcntl
    global _lock_fd
    try:
        fd = open(LOCK_FILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _lock_fd = fd
        return True
    except (IOError, OSError):
        try:
            fd.close()
        except Exception:
            pass
        return False


def _release_lock():
    """Libera el lock file. NO elimina el archivo para evitar race conditions."""
    import fcntl
    global _lock_fd
    try:
        if _lock_fd is not None:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            _lock_fd = None
    except Exception:
        _lock_fd = None


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

    # ── Lock: evita que watcher y sync manual compitan por el mismo archivo ──
    if not _acquire_lock():
        logger.warning("⚠️  Otro sync ya está corriendo (lock %s ocupado). Saliendo.", LOCK_FILE)
        return [{"nombre": "__lock__", "error": "Sync ya en progreso", "descargado": False}]
    try:
        return _run_sync_impl(archivos, forzar=forzar, solo_descarga=solo_descarga)
    finally:
        _release_lock()


def _run_sync_impl(archivos: list, forzar: bool, solo_descarga: bool) -> list:
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
