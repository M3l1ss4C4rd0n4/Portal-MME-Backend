#!/bin/bash
# Healthcheck del watcher SharePoint — detecta si dejó de completar ciclos
# Cron: */15 * * * *
#
# Independiente del auto-heal interno de etl_sharepoint_watcher.py (que solo
# actúa si cron sigue invocando el script). Este chequeo no depende del venv
# ni del propio watcher, así que cubre el caso en que cron deje de lanzarlo
# o el auto-heal interno falle por cualquier motivo no previsto.

LOG_FILE="/home/admonctrlxm/server/logs/sp_watcher.log"
ALERT_LOG="/home/admonctrlxm/server/logs/sp_watcher_health.log"
LOCK_FILE="/tmp/etl_sharepoint_watcher.lock"
MAX_AGE_MIN=30

last_line=$(grep "Resumen:" "$LOG_FILE" 2>/dev/null | tail -1)
last_ts=$(echo "$last_line" | grep -oE "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")

if [ -z "$last_ts" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Sin ciclo 'Resumen:' registrado en $LOG_FILE" >> "$ALERT_LOG"
    exit 1
fi

last_epoch=$(date -d "$last_ts" +%s 2>/dev/null)
now_epoch=$(date +%s)
age_min=$(( (now_epoch - last_epoch) / 60 ))

if [ "$age_min" -le "$MAX_AGE_MIN" ]; then
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Watcher SharePoint sin ciclo completo hace ${age_min} min (último: $last_ts)" >> "$ALERT_LOG"

if [ -f "$LOCK_FILE" ]; then
    lock_pid=$(cat "$LOCK_FILE" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
        lock_age=$(( now_epoch - $(stat -c %Y "$LOCK_FILE") ))
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔪 PID $lock_pid tiene el lock hace ${lock_age}s — matando (SIGKILL)" >> "$ALERT_LOG"
        kill -9 "$lock_pid" 2>/dev/null
    fi
    rm -f "$LOCK_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔓 Lock eliminado — el próximo ciclo de cron debería recuperarse" >> "$ALERT_LOG"
fi
