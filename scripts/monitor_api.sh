#!/bin/bash
# Monitoreo de la API — reinicia vía systemd si no responde
# Cron: */5 * * * *
# NOTA: La API corre como portal-api.service (systemd), no como PM2.
#       Si en el futuro cambia, actualizar SERVICE_NAME y API_URL.

API_URL="http://127.0.0.1:8000/health"
MAX_RETRIES=3
LOG_FILE="/home/admonctrlxm/server/logs/api-monitor.log"
SERVICE_NAME="portal-api.service"

echo "[$(date)] Verificando API ($API_URL)..." >> "$LOG_FILE"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s -f -m 5 "$API_URL" > /dev/null 2>&1; then
        echo "[$(date)] ✅ API OK" >> "$LOG_FILE"
        exit 0
    fi
    echo "[$(date)] ⚠️ Intento $i/$MAX_RETRIES falló" >> "$LOG_FILE"
    sleep 2
done

echo "[$(date)] ❌ API no responde — reiniciando vía systemctl..." >> "$LOG_FILE"
sudo systemctl restart "$SERVICE_NAME" >> "$LOG_FILE" 2>&1
echo "[$(date)] Reinicio systemctl completado (exit $?)" >> "$LOG_FILE"
