#!/bin/bash
# Script de monitoreo que reinicia la API si se cae
# Para usar con cron cada 5 minutos

API_URL="http://127.0.0.1:8000/"
MAX_RETRIES=3
RESTART_SCRIPT="/home/admonctrlxm/server/api/start_api_daemon.sh"
STOP_SCRIPT="/home/admonctrlxm/server/api/stop_api.sh"
LOG_FILE="/home/admonctrlxm/server/logs/api-monitor.log"

echo "[$(date)] Verificando API..." >> "$LOG_FILE"

# Verificar si la API responde
for i in $(seq 1 $MAX_RETRIES); do
    if curl -s -f -m 5 "$API_URL" > /dev/null 2>&1; then
        echo "[$(date)] ✅ API funcionando correctamente" >> "$LOG_FILE"
        exit 0
    fi
    echo "[$(date)] ⚠️ Intento $i/$MAX_RETRIES falló" >> "$LOG_FILE"
    sleep 2
done

# Si llegamos aquí, la API no responde
echo "[$(date)] ❌ API no responde. Reiniciando..." >> "$LOG_FILE"

# Detener procesos zombie
pkill -9 -f "gunicorn api.main:app" 2>> "$LOG_FILE"
sleep 3

# Reiniciar API
$RESTART_SCRIPT >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date)] ✅ API reiniciada exitosamente" >> "$LOG_FILE"
else
    echo "[$(date)] ❌ ERROR al reiniciar API" >> "$LOG_FILE"
fi
