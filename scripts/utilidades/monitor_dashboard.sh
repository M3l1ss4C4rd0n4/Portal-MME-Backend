#!/bin/bash
# Monitoreo continuo del dashboard

CHECK_INTERVAL=60  # Segundos entre checks

while true; do
    # Verificar si Gunicorn está corriendo
    if ! pgrep -f "gunicorn.*dashboard-mme" > /dev/null; then
        echo "[$(date)] ⚠️ Dashboard no está corriendo. Reiniciando..."
        /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh
    fi
    
    # Verificar health endpoint
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8050/health)
    if [ "$HEALTH" != "200" ]; then
        echo "[$(date)] ⚠️ Health check falló (HTTP $HEALTH). Reiniciando..."
        /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh
    fi
    
    sleep $CHECK_INTERVAL
done
