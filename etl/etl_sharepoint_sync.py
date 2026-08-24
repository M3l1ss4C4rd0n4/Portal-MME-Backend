#!/usr/bin/env python3
"""
ETL: Sincronización automática Excel SharePoint → data/ → PostgreSQL
=====================================================================

Descarga archivos Excel desde SharePoint del Ministerio (vía Microsoft Graph API),
detecta cambios por hash SHA-256 y ejecuta el ETL correspondiente en PostgreSQL.

Archivos configurados:
  1. Matriz_General_Reparto   → Matriz_General_Reparto.xlsx → schema supervision (3 tablas)
  2. Acuerdos_Gestion_DEE_2026 → Acuerdos_Gestion_DEE_2026.xlsx → schema presupuesto
  3. Base_Subsidios_DDE       → Base_Subsidios_DDE.xlsx      → schema subsidios (pagos, validaciones, empresas, mapa, kpis)
  4. Seguimiento_Contratos_CE → Seguimiento_Contratos_CE.xlsx → contratos_or.seguimiento
  5. Comunidades_Seguimiento_FENOGE → comunidades_seguimiento_fenoge.xlsx → fenoge.seguimiento
  6. Deficit_Historico_Subsidios → Deficit_Historico_Subsidios.xlsx → subsidios.deficit_historico
  7. Comunidades_Energeticas_FENOGE → Comunidades_Energeticas_fenoge.xlsx → fenoge.comunidades
  8. Colombia_Solar_OR        → Colombia_Solar_OR.xlsx       → schema colombia_solar
  9. Resumen_Implementacion_CE → Data_Implementadas_Tablero.xlsx → schema comunidades (base)

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
# Configuración lazy: evita que `import etl_sharepoint_sync` (desde el watcher)
# redirija los logs del watcher al archivo de sync.
_logger_configured = False


def _configure_logging() -> None:
    global _logger_configured
    if _logger_configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_DIR / "etl_sharepoint_sync.log", encoding="utf-8")]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ETL_SP_SYNC] %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    _logger_configured = True


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
    {
        "nombre": "Resumen_Implementacion_CE",
        "url": "https://minenergiacol-my.sharepoint.com/:x:/g/personal/comunidadesenergeticas_minenergia_gov_co/IQDjuOxtfwEAT7KS_SEpACKwAVKE3fhMVzccudibTHL10t4?email=mjcardona%40minenergia.gov.co&e=QRBMFH",
        "archivo_local": "Data_Implementadas_Tablero.xlsx",
        "directorio": "base_de_datos_comunidades_energeticas",
        "etl_handler": "etl_comunidades",
        "activo": True,
    },
    {
        "nombre": "Direccion_Hidrocarburos",
        "url": "https://minenergiacol-my.sharepoint.com/:x:/r/personal/dmgutierrez_minenergia_gov_co/Documents/4.%20Data/Direcci%C3%B3n_Hidrocarburos.xlsx?d=wc4558874485d46d48a540eb02497649b&csf=1&web=1&e=1qAT6b",
        "archivo_local": "Direccion_Hidrocarburos.xlsx",
        "directorio": "onedrive",
        "etl_handler": "etl_hidrocarburos",
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
        timeout=30,  # sin esto, msal cuelga indefinidamente si login.microsoftonline.com no responde
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


def _resolve_drive_id(reference_share_url: str) -> str:
    """Obtiene drive_id de SharePoint a partir de un link de referencia en la misma biblioteca."""
    token = _get_access_token()
    sharing_token = _encode_sharing_url(reference_share_url)
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=(15, 30),
    )
    resp.raise_for_status()
    drive_id = resp.json().get("parentReference", {}).get("driveId")
    if not drive_id:
        raise RuntimeError("No se pudo resolver drive_id desde el link de referencia")
    return drive_id


def _get_drive_item_metadata(reference_share_url: str, graph_path: str) -> dict | None:
    """Metadata de un archivo por ruta dentro del drive (cuando no hay link :x: válido)."""
    try:
        drive_id = _resolve_drive_id(reference_share_url)
        token = _get_access_token()
        resp = requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{graph_path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=(15, 30),
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "lastModifiedDateTime": data.get("lastModifiedDateTime", ""),
            "eTag": data.get("eTag", ""),
            "size": data.get("size", 0),
            "name": data.get("name", ""),
        }
    except Exception as exc:
        logger.warning("  ⚠️  No se pudo leer metadata Graph path %s: %s", graph_path, exc)
        return None


def descargar_por_graph_path(
    reference_share_url: str,
    graph_path: str,
    destino: Path,
    timeout: tuple = (30, 1800),
) -> None:
    """Descarga un archivo por ruta Graph API (misma biblioteca que reference_share_url)."""
    drive_id = _resolve_drive_id(reference_share_url)
    meta = _get_drive_item_metadata(reference_share_url, graph_path)
    if meta:
        logger.info("  Archivo remoto: %s", meta.get("name", graph_path))

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    token = _get_access_token()
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{graph_path}:/content",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        stream=True,
    )
    resp.raise_for_status()
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            if chunk:
                f.write(chunk)
    if not _es_excel_valido(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"El archivo en {graph_path} no es un Excel válido")
    tmp.replace(destino)
    logger.info("  ✅ Descarga Graph path exitosa (%.1f KB)", destino.stat().st_size / 1024)


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


def _fetch_sharepoint_metadata(share_link: str) -> dict | None:
    """Obtiene lastModifiedDateTime, eTag y size desde Graph API."""
    try:
        token = _get_access_token()
        sharing_token = _encode_sharing_url(share_link)
        resp = requests.get(
            f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=(15, 30),
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "lastModifiedDateTime": data.get("lastModifiedDateTime", ""),
            "eTag": data.get("eTag", ""),
            "size": data.get("size", 0),
        }
    except Exception as exc:
        logger.warning("  ⚠️  No se pudo leer metadata SharePoint: %s", exc)
        return None


def _mark_etl_success(
    nombre: str,
    share_link: str,
    content_hash: str,
    graph_path: str | None = None,
) -> None:
    """Actualiza estado unificado tras ETL exitoso (hash + metadata SharePoint)."""
    state = {}
    if HASH_CACHE_FILE.exists():
        try:
            state = json.loads(HASH_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    entry = state.get(nombre, {}) if isinstance(state.get(nombre), dict) else {}
    entry["content_hash"] = content_hash
    entry["last_etl_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry["last_etl_ok"] = True

    if graph_path:
        meta = _get_drive_item_metadata(share_link, graph_path)
    else:
        meta = _fetch_sharepoint_metadata(share_link)
    if meta:
        entry.update(meta)

    state[nombre] = entry
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
    table_name_overrides: dict | None = None,
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
    tname_overrides = table_name_overrides or {}
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
                    table_name = tname_overrides.get(sheet, _clean_col(sheet))
                    if skip_duplicate_tables and table_name in loaded_tables:
                        continue
                    loaded_tables.add(table_name)
                    cur.execute(f'DROP TABLE IF EXISTS {schema}."{table_name}" CASCADE;')

            loaded_tables.clear()
            for sheet in xl.sheet_names:
                if sheet in exclude:
                    logger.info("  Hoja '%s' excluida por configuración", sheet)
                    continue

                table_name = tname_overrides.get(sheet, _clean_col(sheet))
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
    Carga Base_Subsidios_DDE.xlsx → subsidios_pagos, subsidios_validaciones,
    subsidios_empresas, subsidios_mapa, kpis_resumen.
    Usa el ETL especializado de etl_subsidios.py (con hashes y lógica de dedup).
    """
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_subsidios import (
        get_connection,
        ensure_schema,
        importar_pagos,
        importar_empresas,
        importar_mapa,
        importar_validaciones,
    )

    logger.info("  ETL subsidios: %s", xlsx_path.name)
    conn = get_connection()
    try:
        ensure_schema(conn)
        r_pagos         = importar_pagos(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_empresas      = importar_empresas(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_mapa          = importar_mapa(xlsx_path, conn, fecha_fuente=fecha_fuente)
        r_validaciones  = importar_validaciones(xlsx_path, conn)
        r_kpis          = _importar_kpis_resumen(xlsx_path, conn)

        # Alerta temprana: si la BD quedó con menos del 80% de filas del Excel, algo falló
        filas_excel = r_pagos.get("filas_leidas", 0)
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

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subsidios.subsidios_validaciones")
            filas_val = cur.fetchone()[0]
        logger.info(
            "  ✅ Validaciones: BD=%d filas (Excel=%d)",
            filas_val,
            r_validaciones.get("filas_importadas", 0),
        )

        return {
            "pagos": r_pagos,
            "empresas": r_empresas,
            "mapa": r_mapa,
            "validaciones": r_validaciones,
            "kpis_resumen": r_kpis,
        }
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
    Carga Seguimiento_Contratos_CE.xlsx -> schema contratos_or.
    El Excel se reestructuró: ahora tiene 6 hojas en lugar de "Hoja1".
    Los headers están en fila 2 (index 1) en varias hojas.
    """
    logger.info("  ETL contratos_or: %s", xlsx_path.name)
    return _load_sheets_to_schema(
        xlsx_path, schema="contratos_or", truncate=True,
        header_overrides={
            "Seguimiento_Avance_Fisico": 1,
            "Seguimiento_Avance_Documental": 1,
            "Seguimiento Electrocqueta": 1,
        },
        drop_orphan_tables=False,
        fecha_carga_override=fecha_fuente,
    )


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

    CORRECCIONES (2026-06-20):
    - Detecta y loguea valores anómalos en % desembolsos (> 100%)
    - Detecta y loguea valores financieros con escala incorrecta (> 1e15)
    - Estos valores se cargan a la BD pero el backend los filtra.
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
                # Coerce object columns that contain datetime values to ISO strings
                # to avoid numeric/timestamp mismatch in PostgreSQL.
                # Limpiar columnas de moneda COP ($ 297.983.971,00) antes de la inferencia de tipos
                # Excluir columnas de porcentaje (avance, porcentaje) — sus valores son decimales 0-1,
                # no moneda COP, y _parse_cop_currency destruiría el punto decimal ("0.70" → 70).
                for col in df.select_dtypes(include="object").columns:
                    if col and any(kw in col.lower() for kw in ("valor", "desembols", "apoyo", "monto", "pesos", "presupuesto", "financier")) \
                            and not any(skip in col.lower() for skip in ("porcentaje", "avance", "%")):
                        try:
                            df[col] = _parse_cop_currency(df[col])
                        except Exception:
                            pass

                # ─── Validación de datos anómalos (2026-06-20) ────────────────────
                _validate_supervision_data(df, sheet)

                for col in df.select_dtypes(include="object").columns:
                    if df[col].dropna().apply(lambda v: isinstance(v, __import__("datetime").datetime)).any():
                        df[col] = df[col].apply(
                            lambda v: v.isoformat() if isinstance(v, __import__("datetime").datetime) else v
                        )
                n = load_dataframe(conn, "supervision", table, df, truncate=True, commit=False, fecha_carga_override=fecha_fuente)
                results[table] = n

            conn.commit()
            logger.info("  ✅ Transacción commiteada: %d tablas cargadas", len(results))
        except Exception as e:
            conn.rollback()
            logger.error("  ❌ Error atómico en supervision — ROLLBACK ejecutado: %s", e, exc_info=True)
            raise

    return results


def _validate_supervision_data(df: "pd.DataFrame", sheet_name: str) -> None:
    """
    Detecta valores anómalos en el DataFrame de supervisión y los loguea.
    No modifica el DataFrame — solo reporta para auditoría.
    """
    import pandas as pd

    # 1. Detectar % desembolsos > 100%
    pct_cols = [c for c in df.columns if "porcentaje" in c.lower() and "desembols" in c.lower()]
    for col in pct_cols:
        numeric = pd.to_numeric(df[col], errors="coerce")
        anomalous = df[(numeric > 1.0) | (numeric < 0.0)]
        if not anomalous.empty:
            logger.warning(
                "  ⚠️  Hoja '%s' — Columna '%s': %d filas con %% desembolsos fuera de rango [0-1]",
                sheet_name, col, len(anomalous),
            )
            # Loguear primeros 5 ejemplos
            for idx, row in anomalous.head(5).iterrows():
                contrato = row.get("CONTRATO", "N/A")
                val = row.get(col, "N/A")
                logger.warning("     Ejemplo: contrato=%s, %s=%s", contrato, col, val)

    # 2. Detectar valores financieros con escala incorrecta (> 1e15)
    fin_cols = [c for c in df.columns if any(kw in c.lower() for kw in ("valor", "desembols", "monto"))]
    for col in fin_cols:
        numeric = pd.to_numeric(df[col], errors="coerce")
        anomalous = df[numeric > 1e15]
        if not anomalous.empty:
            logger.warning(
                "  ⚠️  Hoja '%s' — Columna '%s': %d filas con valor financiero > 1e15 (escala incorrecta)",
                sheet_name, col, len(anomalous),
            )
            for idx, row in anomalous.head(5).iterrows():
                contrato = row.get("CONTRATO", "N/A")
                val = row.get(col, "N/A")
                logger.warning("     Ejemplo: contrato=%s, %s=%s", contrato, col, val)

    # 3. Detectar valor desembolsado > valor proyecto × 10
    vp_col = next((c for c in df.columns if "valor por proyecto" in c.lower()), None)
    vd_col = next((c for c in df.columns if "valor desembolsado" in c.lower()), None)
    if vp_col and vd_col:
        vp = pd.to_numeric(df[vp_col], errors="coerce")
        vd = pd.to_numeric(df[vd_col], errors="coerce")
        anomalous = df[(vd > vp * 10) & (vp > 0)]
        if not anomalous.empty:
            logger.warning(
                "  ⚠️  Hoja '%s': %d filas donde desembolsado > 10× valor proyecto",
                sheet_name, len(anomalous),
            )
            for idx, row in anomalous.head(5).iterrows():
                contrato = row.get("CONTRATO", "N/A")
                logger.warning(
                    "     Ejemplo: contrato=%s, VP=%s, VD=%s",
                    contrato, row.get(vp_col, "N/A"), row.get(vd_col, "N/A"),
                )


_FENOGE_SEG_MAP = {
    "region": "region",
    "comunidad": "nombre_comunidad",
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

    # Limpiar columnas de moneda COP que el Excel trae como strings con formato "$ X.XXX.XXX,YY"
    for col in ("real_financiero", "programado", "real_acumulado_pesos", "programado_acumulado_pesos"):
        if col in df.columns and df[col].dtype == object:
            df[col] = _parse_cop_currency(df[col])

    # Limpiar columnas de porcentaje con formato colombiano ("75,5%", "1.234,56")
    for col in ("avance_real_pct", "avance_programado_pct", "avance_real_acumulado_pct", "avance_programado_acumulado_pct"):
        if col in df.columns and df[col].dtype == object:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(r"[\$\s]", "", regex=True)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

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
    "Curva S_GECELCA",          # columnas con tipos mixtos (num+datetime) — no usadas por la API
    "Curva S_Becerril",         # idem
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


# ─── Column mappings para Data_Implementadas_Tablero.xlsx ─────────────────
# Hoja "LISTADO RCE" → comunidades.base (formato desde 2026-07-31: hoja única
# con usuarios/beneficiarios partidos en INICIAL/OPERACIÓN — se combinan en
# _combinar_usuarios_beneficiarios() — y fechas de vuelta).
# "TIPO DE RCE" es el sucesor de la vieja "Estado Actual RCE" — mismo concepto
# (Resolución 40509 de 2024), por eso se mapea al mismo campo `estado_actual`.
_COM_BASE_MAP: dict[str, str] = {
    "NURIN": "nurin",
    "ID": "id_comunidad",
    "COMUNIDAD ENERGÉTICA": "nombre_de_la_organizacion",
    "DEPARTAMENTO": "departamento",
    "MUNICIPIO": "municipio",
    "TIPO DE COMUNIDAD": "tipo_ce",
    "TIPO DE RCE (Res. 40509 de 2024)": "estado_actual",
    "NÚMERO DE RESOLUCIÓN": "no_resolucion",
    "NÚMERO DE USUARIOS EN INICIAL": "usuarios_inicial_tmp",
    "NÚMERO DE USUARIOS EN OPERACIÓN": "usuarios_operacion_tmp",
    "NÚMERO DE PERSONAS BENEFICIADAS EN INICIAL": "beneficiarios_inicial_tmp",
    "NÚMERO DE PERSONAS BENEFICIADAS EN OPERACIÓN": "beneficiarios_operacion_tmp",
    "ZONA": "zona_sin_zni_mixto",
    "ETNIA": "etnia",
    "EJECUTOR": "ejecutor",
    "TIPO DE SOLUCIÓN ENERGÉTICA": "fuentes_energia",
    "CAPACIDAD INSTALADA (kWp)": "capacidad_de_generacion_kwp",
    "INVERSIÓN REPORTADA": "inversion_estimada",
    "LATITUD": "latitud",
    "LONGITUD": "longitud",
    "FECHA PUESTA EN  MARCHA": "fecha_operacion",
    "FECHA DE REGISTRO": "fecha_registro",
}

def _apply_col_map(df: "pd.DataFrame", col_map: dict[str, str]) -> "pd.DataFrame":
    """Renombra columnas del DataFrame según el mapa. Solo las que existen."""
    present = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=present)
    # Quedarse solo con las columnas que están en el mapa (más fecha_carga se agrega después)
    expected = set(present.values())
    df = df[[c for c in df.columns if c in expected]]
    return df


def _com_numeric(series: "pd.Series"):
    """Normaliza una columna numérica con formato inconsistente (fórmulas rotas,
    placeholders de texto, coma decimal '9,82' vs coma de miles) a float real.

    Sin esto, una sola celda como "Sin Información" o "9,82" hace que pandas
    infiera la columna entera como texto (rompe SUM() en SQL más adelante), y
    una coma decimal sin normalizar se leería como 982 en vez de 9.82.
    Cualquier celda que no se pueda interpretar como número queda en NULL —
    no bloquea la carga ni el resto de la suma.
    """
    import pandas as pd

    _placeholders = {"", "sin información", "sin informacion", "por definir", "n/a", "nd", "-", "—"}

    def _parse(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if s.lower() in _placeholders:
            return None
        s = s.replace("$", "").replace(" ", "").replace("\xa0", "")
        if "," in s and "." not in s:
            s = s.replace(",", ".")  # coma decimal ("9,82" -> 9.82)
        else:
            s = s.replace(",", "")  # coma de miles ("1,234" -> 1234)
        try:
            return float(s)
        except ValueError:
            return None

    return series.apply(_parse)


def _com_money(series: "pd.Series"):
    """Normaliza una columna de moneda colombiana ('$ X.XXX.XXX,XX') a float.

    A diferencia de _com_numeric, aquí el punto SIEMPRE es separador de miles
    (nunca decimal) — necesario porque, a diferencia de capacidad/usuarios
    (números pequeños donde el punto ya es un decimal correcto), esta columna
    mezcla valores ya numéricos con texto tipo "$ 508.274.150,04" donde
    _com_numeric confundiría el punto de miles con un decimal y perdería el dato.
    """
    import pandas as pd

    _placeholders = {"", "sin información", "sin informacion", "por definir", "n/a", "nd", "-", "—"}

    def _parse(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if s.lower() in _placeholders:
            return None
        s = s.replace("$", "").replace(" ", "").replace("\xa0", "")
        if "," in s:
            s = s.replace(".", "").replace(",", ".")  # punto=miles, coma=decimal
        else:
            s = s.replace(".", "")  # solo miles, sin decimales
        try:
            return float(s)
        except ValueError:
            return None

    return series.apply(_parse)


def _normalize_case_by_frequency(series: "pd.Series"):
    """Agrupa valores que solo difieren en mayúsculas/minúsculas y los reemplaza
    por la variante más frecuente de cada grupo (no title-case genérico, para no
    dañar siglas como SSFV/IPSE/FENOGE que deben quedar en mayúscula)."""
    import pandas as pd

    non_null = series.dropna()
    if non_null.empty:
        return series
    freq = non_null.value_counts()
    canonical: dict[str, object] = {}
    for val, count in freq.items():
        key = str(val).strip().lower()
        if key not in canonical or count > freq[canonical[key]]:
            canonical[key] = val
    return series.apply(lambda v: canonical.get(str(v).strip().lower(), v) if pd.notna(v) else v)


def handler_etl_comunidades(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Data_Implementadas_Tablero.xlsx → comunidades.base.

    La hoja y la fila de encabezado se detectan dinámicamente (ya cambiaron de
    formato varias veces): se busca la hoja por nombre aproximado ("rce") y,
    dentro de ella, la primera fila que contenga "DEPARTAMENTO" como encabezado
    real (algunas versiones traen una fila de título fusionada encima).

    "Implementada" = cualquier valor de Tipo de RCE (estado_actual) EXCEPTO
    "Desistida" (incluye vacío/sin registrar/inicial/operación/prórroga).
    """
    import pandas as pd

    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_nuevos_dashboards import load_dataframe
    from infrastructure.database.connection import connection_manager

    logger.info("  ETL comunidades: %s", xlsx_path.name)
    xl = pd.ExcelFile(xlsx_path)
    logger.info("  Hojas disponibles: %s", xl.sheet_names)

    # Buscar hoja principal: si solo hay una, usarla; si hay varias, la que
    # contenga "rce" evitando las de control/conciliación (ej. "02_DIF_CLAVE_RCE").
    if len(xl.sheet_names) == 1:
        base_sheet = xl.sheet_names[0]
    else:
        candidates = [s for s in xl.sheet_names if "rce" in s.lower()]
        base_sheet = next((s for s in candidates if not s.strip().lower().startswith(("02_", "control"))), candidates[0] if candidates else None)

    if not base_sheet:
        raise ValueError(f"No se encontró hoja principal en {xlsx_path.name} (hojas: {xl.sheet_names})")

    # Detectar la fila real de encabezados (puede no ser la fila 0 si hay un título fusionado encima)
    raw_peek = pd.read_excel(xlsx_path, sheet_name=base_sheet, header=None, nrows=5)
    header_row_idx = 0
    for i in range(len(raw_peek)):
        if any("DEPARTAMENTO" in str(v).upper() for v in raw_peek.iloc[i].tolist()):
            header_row_idx = i
            break
    logger.info("  Fila de encabezado detectada: %d", header_row_idx)

    results: dict = {}

    with connection_manager.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS comunidades.base CASCADE")
                cur.execute("DROP TABLE IF EXISTS comunidades.implementadas CASCADE")
            conn.commit()

            # ── Cargar hoja principal → comunidades.base ──────────────
            logger.info("  Leyendo hoja '%s' → comunidades.base", base_sheet)
            df_base = pd.read_excel(xlsx_path, sheet_name=base_sheet, header=header_row_idx)
            df_base = df_base.dropna(how="all").dropna(axis=1, how="all")
            logger.info("    Filas leídas: %d, Columnas originales: %d", len(df_base), len(df_base.columns))

            # Limpiar nombres de columna: normalizar saltos de línea y espacios
            df_base.columns = [str(c).replace("\n", " ").strip() for c in df_base.columns]
            logger.info("    Columnas disponibles: %s", list(df_base.columns))

            df_base = _apply_col_map(df_base, _COM_BASE_MAP)
            # Normalizar columnas numéricas: evita que celdas rotas ("Sin Información",
            # "9,82" con coma decimal) tumben el tipo de columna o corrompan la suma.
            for _num_col in ("capacidad_de_generacion_kwp", "usuarios_inicial_tmp", "usuarios_operacion_tmp", "beneficiarios_inicial_tmp", "beneficiarios_operacion_tmp"):
                if _num_col in df_base.columns:
                    df_base[_num_col] = _com_numeric(df_base[_num_col])
            # Inversión usa su propio parser: el punto es siempre separador de miles aquí
            # (a diferencia de capacidad, donde el punto ya es un decimal correcto).
            if "inversion_estimada" in df_base.columns:
                df_base["inversion_estimada"] = _com_money(df_base["inversion_estimada"])
            # Usuarios/beneficiarios vienen partidos en INICIAL/OPERACIÓN (mutuamente
            # excluyentes por fila) — se combinan en el campo único que espera la API.
            for _campo, _col_inicial, _col_operacion in [
                ("usuarios_equivalentes", "usuarios_inicial_tmp", "usuarios_operacion_tmp"),
                ("beneficiarios_equivalentes", "beneficiarios_inicial_tmp", "beneficiarios_operacion_tmp"),
            ]:
                if _col_inicial in df_base.columns or _col_operacion in df_base.columns:
                    inicial = df_base.get(_col_inicial, pd.Series(0, index=df_base.index)).fillna(0)
                    operacion = df_base.get(_col_operacion, pd.Series(0, index=df_base.index)).fillna(0)
                    df_base[_campo] = inicial + operacion
                    df_base = df_base.drop(columns=[c for c in (_col_inicial, _col_operacion) if c in df_base.columns])
            # Normalizar mayúsculas/minúsculas duplicadas (ej. "Otros" vs "OTROS"):
            # se agrupan y se usa la variante más frecuente como forma canónica.
            for _cat_col in ("tipo_ce", "ejecutor", "fuentes_energia"):
                if _cat_col in df_base.columns:
                    df_base[_cat_col] = _normalize_case_by_frequency(df_base[_cat_col])
            # Fechas mezclan datetime nativo con texto "dd/mm/yyyy" y placeholders
            # ("SIN INFORMACIÓN", "EN FIRMA") — sin esto la columna queda TEXT en vez
            # de TIMESTAMP y rompe MIN()/MAX() más adelante en la API.
            for _date_col in ("fecha_operacion", "fecha_registro"):
                if _date_col in df_base.columns:
                    df_base[_date_col] = pd.to_datetime(df_base[_date_col], format="mixed", dayfirst=True, errors="coerce")
            # "Implementada" = todo lo que no sea "Desistida" en Tipo de RCE (estado_actual)
            df_base["implementado"] = df_base.get("estado_actual", pd.Series(dtype=object)).apply(
                lambda v: "No" if isinstance(v, str) and v.strip().lower() == "desistida" else "Si"
            )
            # "0" en Zona (texto o numérico) es un error de captura del Excel — se agrupa
            # con los valores en blanco, que la API ya reporta como "Sin clasificar"
            if "zona_sin_zni_mixto" in df_base.columns:
                df_base["zona_sin_zni_mixto"] = df_base["zona_sin_zni_mixto"].apply(
                    lambda v: None if not (isinstance(v, float) and pd.isna(v)) and str(v).strip() == "0" else v
                )
            logger.info("    Columnas finales (%d): %s", len(df_base.columns), list(df_base.columns))
            logger.info("    implementado: %s", df_base["implementado"].value_counts().to_dict())

            n_base = load_dataframe(conn, "comunidades", "base", df_base, truncate=True, commit=False, fecha_carga_override=fecha_fuente)
            results["base"] = n_base
            logger.info("  ✅ comunidades.base: %d filas", n_base)

            # Garantizar columnas que la API espera (load_dataframe puede eliminarlas si son todas NULL)
            with conn.cursor() as cur2:
                for col, dtype in [("latitud", "DOUBLE PRECISION"), ("longitud", "DOUBLE PRECISION"), ("zona_sin_zni_mixto", "TEXT")]:
                    cur2.execute(f"""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                           WHERE table_schema='comunidades' AND table_name='base' AND column_name='{col}') THEN
                                EXECUTE 'ALTER TABLE comunidades.base ADD COLUMN {col} {dtype}';
                            END IF;
                        END $$;
                    """)

            conn.commit()
            logger.info("  ✅ Transacción commiteada")

        except Exception as e:
            conn.rollback()
            logger.error("  ❌ Error atómico en comunidades — ROLLBACK: %s", e, exc_info=True)
            raise

    logger.info("  comunidades: %s", results)
    return results


def handler_etl_hidrocarburos(xlsx_path: Path, fecha_fuente: datetime | None = None) -> dict:
    """
    Carga Direccion_Hidrocarburos.xlsx → schema hidrocarburos.
    Usa el ETL especializado de etl_hidrocarburos.py (parsing manual: ambas
    hojas tienen layout irregular, no aplica el loader genérico por hoja).
    """
    sys.path.insert(0, str(BASE_DIR))
    from etl.etl_hidrocarburos import run_etl

    logger.info("  ETL hidrocarburos: %s", xlsx_path.name)
    return run_etl(xlsx_path)


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
    "etl_comunidades": handler_etl_comunidades,
    "etl_hidrocarburos": handler_etl_hidrocarburos,
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
    graph_path = cfg.get("graph_path")

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
                if graph_path:
                    descargar_por_graph_path(url, graph_path, destino, timeout=timeout_dl)
                else:
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

        # 4. Persistir hash y metadata SharePoint solo tras ETL exitoso
        if not solo_descarga and etl_ok:
            _mark_etl_success(nombre, url, hash_actual, graph_path=graph_path)
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

    # Limpiar lock huérfano si el PID dueño ya no existe
    if LOCK_FILE.exists():
        try:
            pid_str = LOCK_FILE.read_text(encoding="utf-8").strip()
            if pid_str.isdigit():
                stale_pid = int(pid_str)
                try:
                    os.kill(stale_pid, 0)
                except OSError:
                    logger.warning(
                        "⚠️  Lock huérfano (PID %d no activo) — eliminando %s",
                        stale_pid,
                        LOCK_FILE,
                    )
                    LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass

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
    """Libera el lock file y elimina el archivo para evitar locks huérfanos visibles."""
    import fcntl
    global _lock_fd
    try:
        if _lock_fd is not None:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            _lock_fd = None
        LOCK_FILE.unlink(missing_ok=True)
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
    _configure_logging()
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
    _configure_logging()
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
