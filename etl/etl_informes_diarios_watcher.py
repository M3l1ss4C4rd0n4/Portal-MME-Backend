#!/usr/bin/env python3
"""
Watcher de informes diarios XM en SharePoint — Portal Energético MME
====================================================================

Corre cada 5 min vía cron. Para la carpeta Informes_Diarios_XM/DD_MM_YYYY:
  1. Escanea tipos presentes (sin descargar PDFs)
  2. Si cambió el fingerprint → invalida caché del backend (todos los workers)
  3. Después de las 10:00 AM (Colombia), si faltan tipos del día → alerta Telegram/email (1 vez/día)

Cron:
  */5 * * * * cd /home/admonctrlxm/server && venv/bin/python3 etl/etl_informes_diarios_watcher.py >> logs/informes_diarios_watcher.log 2>&1
"""

from __future__ import annotations

import json
import logging
import os
import fcntl
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path(__file__).parent / ".informes_diarios_watcher_state.json"
LOG_DIR = BASE_DIR / "logs"
LOCK_FILE = Path("/tmp/etl_informes_diarios_watcher.lock")
_lock_fd = None
TZ = ZoneInfo("America/Bogota")
ALERT_AFTER_HOUR = 10

LOG_DIR.mkdir(exist_ok=True)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [INFORMES_XM_WATCHER] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger = logging.getLogger("informes_diarios_watcher")
logger.handlers.clear()
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

sys.path.insert(0, str(BASE_DIR))


def _acquire_lock() -> bool:
    global _lock_fd
    if LOCK_FILE.exists():
        try:
            pid_str = LOCK_FILE.read_text(encoding="utf-8").strip()
            if pid_str.isdigit():
                stale_pid = int(pid_str)
                try:
                    os.kill(stale_pid, 0)
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


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _fingerprint_key(fingerprint: dict) -> str:
    return json.dumps(fingerprint, sort_keys=True, ensure_ascii=False)


def _send_incomplete_alert(pendientes: list[str], resumen: dict) -> None:
    from domain.services.notification_service import broadcast_alert

    fecha = resumen.get("fechaConsulta", "")
    completos = resumen.get("completosDelDia", 0)
    total = resumen.get("totalTipos", 3)
    pendientes_txt = ", ".join(pendientes)

    message = (
        f"⚠️ Informes XM incompletos — {fecha}\n\n"
        f"Solo {completos}/{total} informes corresponden al día de hoy.\n"
        f"Pendientes en SharePoint: {pendientes_txt}\n\n"
        f"El portal usa el último disponible como fallback.\n"
        f"Portal Energético — Ministerio de Minas y Energía"
    )

    broadcast_alert(message=message, severity="WARNING", is_daily=False)
    logger.info("Alerta enviada: pendientes=%s", pendientes_txt)


def check_informes_diarios() -> None:
    from api.v1.routes.reports import (
        invalidate_informes_diarios_cache,
        scan_informes_diarios_status,
    )

    now = datetime.now(TZ)
    today = now.date()
    today_key = today.isoformat()

    logger.info("Verificando informes XM — %s", now.strftime("%Y-%m-%d %H:%M %Z"))

    try:
        scan = scan_informes_diarios_status(today)
    except Exception as exc:
        logger.error("Error escaneando SharePoint: %s", exc)
        return

    resumen = scan["resumen"]
    fingerprint = scan["fingerprint"]
    fp_key = _fingerprint_key(fingerprint)

    state = _load_state()
    prev_fp = state.get("fingerprint")
    changed = prev_fp != fp_key

    logger.info(
        "Estado: %d/%d del día | pendientes=%s | cambio=%s",
        resumen["completosDelDia"],
        resumen["totalTipos"],
        resumen["pendientes"] or "ninguno",
        changed,
    )

    if changed:
        invalidate_informes_diarios_cache()
        state["fingerprint"] = fp_key
        state["last_change"] = now.isoformat()
        logger.info("Caché invalidada — portal refrescará catálogo en próxima consulta")

    pendientes = resumen.get("pendientes") or []
    if (
        now.hour >= ALERT_AFTER_HOUR
        and pendientes
        and state.get("last_incomplete_alert") != today_key
    ):
        try:
            _send_incomplete_alert(pendientes, resumen)
            state["last_incomplete_alert"] = today_key
        except Exception as exc:
            logger.error("No se pudo enviar alerta de incompletos: %s", exc)

    if not prev_fp:
        state["fingerprint"] = fp_key

    _save_state(state)


if __name__ == "__main__":
    if not _acquire_lock():
        logger.warning("⚠️  Otra instancia del watcher ya está corriendo (%s ocupado). Saliendo.", LOCK_FILE)
        sys.exit(0)
    try:
        check_informes_diarios()
    finally:
        _release_lock()
