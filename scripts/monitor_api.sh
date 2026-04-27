#!/bin/bash
# Monitoreo de la API — reinicia vía pm2 si no responde
# Cron: */5 * * * *

API_URL="http://127.0.0.1:8000/"
MAX_RETRIES=3
LOG_FILE="/home/admonctrlxm/server/logs/api-monitor.log"
PM2="/home/admonctrlxm/.nvm/versions/node/v20.20.0/bin/pm2"

echo "[$(date)] Verificando API..." >> "$LOG_FILE"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s -f -m 5 "$API_URL" > /dev/null 2>&1; then
        echo "[$(date)] ✅ API OK" >> "$LOG_FILE"
        exit 0
    fi
    echo "[$(date)] ⚠️ Intento $i/$MAX_RETRIES falló" >> "$LOG_FILE"
    sleep 2
done

echo "[$(date)] ❌ API no responde — reiniciando vía pm2..." >> "$LOG_FILE"
$PM2 restart api-mme >> "$LOG_FILE" 2>&1
echo "[$(date)] Reinicio pm2 completado (exit $?)" >> "$LOG_FILE"
