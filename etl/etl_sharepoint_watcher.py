#!/usr/bin/env python3
"""
Watcher de cambios en SharePoint — Portal Energético MME
=========================================================

Corre cada 5 min vía cron. Para cada archivo en SHAREPOINT_FILES:
  1. Consulta lastModifiedDateTime via Graph API (sin descargar el archivo)
  2. Compara con el estado guardado en .sp_watcher_state.json
  3. Si cambió → ejecuta el ETL de ese archivo (--forzar --archivo N)
  4. Guarda el nuevo estado

Cron:
  */5 * * * * cd /home/admonctrlxm/server && venv/bin/python3 etl/etl_sharepoint_watcher.py >> logs/sp_watcher.log 2>&1
"""

import sys
import json
import os
import fcntl
import base64
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
STATE_FILE = Path(__file__).parent / ".sp_watcher_state.json"
LOG_DIR    = BASE_DIR / "logs"
ETL_SCRIPT = Path(__file__).parent / "etl_sharepoint_sync.py"
PYTHON     = BASE_DIR / "venv" / "bin" / "python3"
LOCK_FILE  = Path("/tmp/etl_sharepoint_watcher.lock")
_lock_fd   = None

LOG_DIR.mkdir(exist_ok=True)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [SP_WATCHER] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger = logging.getLogger("sp_watcher")
logger.handlers.clear()
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

sys.path.insert(0, str(BASE_DIR))
from etl.etl_sharepoint_sync import (
    _get_access_token,
    SHAREPOINT_FILES,
    _get_drive_item_metadata,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Segundos máximos para que corra el ETL de un archivo antes de rendirse
ETL_TIMEOUT = 600


# ── Lock singleton ────────────────────────────────────────────────────────────

# El watcher corre cada 5 min y un ciclo normal toma segundos a pocos minutos.
# Si un lock lleva más que esto, el proceso dueño no está muerto (os.kill(pid, 0)
# lo vería vivo) pero está colgado (p.ej. una llamada de red sin timeout) — no
# hay forma de distinguirlo de un ciclo lento salvo por antigüedad del lock.
STALE_LOCK_SECONDS = 20 * 60  # 4x el intervalo del cron: margen generoso, cero falsos positivos esperados


def _acquire_lock() -> bool:
    """Intenta adquirir el lock file. Retorna True si se adquirió."""
    global _lock_fd
    if LOCK_FILE.exists():
        try:
            pid_str = LOCK_FILE.read_text(encoding="utf-8").strip()
            lock_age = time.time() - LOCK_FILE.stat().st_mtime
            if pid_str.isdigit():
                stale_pid = int(pid_str)
                try:
                    os.kill(stale_pid, 0)
                    # El proceso existe. ¿Vivo y trabajando, o vivo y colgado?
                    if lock_age > STALE_LOCK_SECONDS:
                        logger.error(
                            "⚠️  Lock de PID %d activo pero colgado hace %.0fs (>%ds) — "
                            "matando proceso y reclamando lock",
                            stale_pid, lock_age, STALE_LOCK_SECONDS,
                        )
                        try:
                            os.kill(stale_pid, 9)  # SIGKILL — no confiar en que responda a SIGTERM
                            time.sleep(1)
                        except (OSError, ProcessLookupError):
                            pass
                        LOCK_FILE.unlink(missing_ok=True)
                except (OSError, ProcessLookupError):
                    logger.warning("⚠️  Lock huérfano (PID %d no activo) — eliminando", stale_pid)
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
        if 'fd' in locals():
            fd.close()
        return False


def _release_lock():
    global _lock_fd
    try:
        if _lock_fd is not None:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            _lock_fd = None
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        _lock_fd = None


# ── Estado persistido ─────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── Graph API ─────────────────────────────────────────────────────────────────

def _encode_sharing_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"u!{encoded}"


def _get_metadata(sharing_token: str, headers: dict) -> dict | None:
    """Devuelve lastModifiedDateTime, eTag, size. Retorna None si falla."""
    meta_url = f"{GRAPH_BASE}/shares/{sharing_token}/driveItem"
    try:
        r = requests.get(meta_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {
                "lastModifiedDateTime": data.get("lastModifiedDateTime", ""),
                "eTag":                 data.get("eTag", ""),
                "size":                 data.get("size", 0),
                "name":                 data.get("name", ""),
            }
        logger.warning("  HTTP %s para %s", r.status_code, meta_url[:60])
    except requests.RequestException as e:
        logger.warning("  Timeout/error de red: %s", e)
    return None


# ── ETL runner ────────────────────────────────────────────────────────────────

def _run_etl(archivo_num: int, nombre: str) -> bool:
    """Corre el ETL para el archivo N. Retorna True si exitoso."""
    cfg = SHAREPOINT_FILES[archivo_num - 1]  # 1-indexed
    timeout = cfg.get("etl_timeout", ETL_TIMEOUT)
    cmd = [str(PYTHON), str(ETL_SCRIPT), "--forzar", "--archivo", str(archivo_num)]
    logger.info("  ▶ Ejecutando ETL #%d (%s) timeout=%ds...", archivo_num, nombre, timeout)
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            logger.info("  ✅ ETL #%d completado en %.0fs", archivo_num, elapsed)
            return True
        else:
            logger.error("  ❌ ETL #%d falló (código %d) en %.0fs",
                         archivo_num, result.returncode, elapsed)
            # Mostrar últimas líneas del stderr para diagnóstico
            for line in (result.stderr or "").strip().splitlines()[-5:]:
                logger.error("     %s", line)
            return False
    except subprocess.TimeoutExpired:
        logger.error("  ⏱ ETL #%d superó timeout de %ds", archivo_num, ETL_TIMEOUT)
        return False


# ── Loop principal ────────────────────────────────────────────────────────────

def check_and_sync(init_only: bool = False):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("=" * 60)
    logger.info("Verificando %d archivos SharePoint — %s", len(SHAREPOINT_FILES), now_utc)
    logger.info("=" * 60)

    # Autenticar una sola vez
    try:
        token = _get_access_token()
    except Exception as e:
        logger.error("❌ No se pudo obtener token Graph API: %s", e)
        return

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    state   = _load_state()
    changed = 0
    errors  = 0

    for i, cfg in enumerate(SHAREPOINT_FILES, 1):
        if not cfg.get("activo", True):
            continue

        nombre = cfg["nombre"]
        url    = cfg["url"]
        graph_path = cfg.get("graph_path")
        logger.info("── #%d %s", i, nombre)

        if graph_path:
            meta = _get_drive_item_metadata(url, graph_path)
        else:
            sharing_token = _encode_sharing_url(url)
            meta = _get_metadata(sharing_token, headers)

        if meta is None:
            logger.warning("  ⚠ No se pudo obtener metadata — se omite")
            errors += 1
            continue

        prev = state.get(nombre, {})
        prev_modified = prev.get("lastModifiedDateTime", "")
        curr_modified  = meta["lastModifiedDateTime"]

        logger.info("  Archivo: %s | %.1f KB | modificado: %s",
                    meta["name"], meta["size"] / 1024, curr_modified[:19])

        if curr_modified == prev_modified:
            logger.info("  ✅ Sin cambios — omitido")
            continue

        if not prev_modified:
            logger.info("  🆕 Primera vez — inicializando estado")
        else:
            logger.info("  🔄 CAMBIO detectado  anterior=%s  actual=%s",
                        prev_modified[:19], curr_modified[:19])

        if init_only:
            # Preservar content_hash si existe (estado unificado con sync)
            prev_hash = state.get(nombre, {}).get("content_hash")
            state[nombre] = {
                "lastModifiedDateTime": curr_modified,
                "eTag":                 meta["eTag"],
                "size":                 meta["size"],
                "last_etl_run":         None,
                "last_etl_ok":          None,
            }
            if prev_hash:
                state[nombre]["content_hash"] = prev_hash
            _save_state(state)
            logger.info("  💾 Estado guardado (--init-only: sin ETL)")
            continue

        ok = _run_etl(i, nombre)

        # Actualizar estado solo si el ETL fue exitoso (o es primera vez)
        if ok or not prev_modified:
            # Preservar content_hash si existe (estado unificado con sync)
            prev_hash = state.get(nombre, {}).get("content_hash")
            state[nombre] = {
                "lastModifiedDateTime": curr_modified,
                "eTag":                 meta["eTag"],
                "size":                 meta["size"],
                "last_etl_run":         now_utc,
                "last_etl_ok":          ok,
            }
            if prev_hash:
                state[nombre]["content_hash"] = prev_hash
            _save_state(state)

        if ok:
            changed += 1
        else:
            errors += 1

        # Pequeña pausa entre archivos para no saturar la API
        time.sleep(1)

    logger.info("=" * 60)
    logger.info("Resumen: %d actualizados | %d sin cambios | %d errores",
                changed,
                len([c for c in SHAREPOINT_FILES if c.get("activo", True)]) - changed - errors,
                errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watcher de cambios SharePoint → ETL portal")
    parser.add_argument(
        "--init-only", action="store_true",
        help="Solo inicializa el estado (guarda metadata actual sin correr ETL). "
             "Útil cuando la BD ya está actualizada y solo quieres armar el baseline.",
    )
    args = parser.parse_args()

    if not _acquire_lock():
        logger.warning("⚠️  Otra instancia del watcher ya está corriendo (%s ocupado). Saliendo.", LOCK_FILE)
        sys.exit(0)
    try:
        check_and_sync(init_only=args.init_only)
    finally:
        _release_lock()
