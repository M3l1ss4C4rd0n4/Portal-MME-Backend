#!/bin/bash
# =============================================================================
# Script de reinicio unificado para el Portal Energético MME
# Reinicia TODOS los servicios necesarios después de cambios en el código
# =============================================================================

set -e  # Salir si algún comando falla

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "  🔄 REINICIANDO SERVICIOS DEL PORTAL ENERGÉTICO MME"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# 1. LIMPIAR CACHÉ DE PYTHON
# =============================================================================
echo "🧹 Paso 1/5: Limpiando caché de Python..."
find /home/admonctrlxm/server -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /home/admonctrlxm/server -name "*.pyc" -delete 2>/dev/null || true
echo -e "${GREEN}✅${NC} Caché limpiada"
echo ""

# =============================================================================
# 2. REINICIAR API REST (Gunicorn)
# =============================================================================
echo "📡 Paso 2/5: Reiniciando API REST..."

# Matar procesos existentes
pkill -f "gunicorn.*api.main" 2>/dev/null || true
sleep 2

# Verificar que se mataron
if pgrep -f "gunicorn.*api.main" > /dev/null; then
    echo -e "${YELLOW}⚠️${NC}  Forzando cierre de procesos antiguos..."
    pkill -9 -f "gunicorn.*api.main" 2>/dev/null || true
    sleep 1
fi

# Iniciar nuevo proceso
cd /home/admonctrlxm/server
nohup /usr/bin/python3 /home/admonctrlxm/.local/bin/gunicorn api.main:app \
    --workers 2 \
    --threads 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /home/admonctrlxm/server/logs/api-access.log \
    --error-logfile /home/admonctrlxm/server/logs/api-error.log \
    --log-level info \
    > /tmp/gunicorn_api.log 2>&1 &

sleep 4

# Verificar que la API responde
if curl -s http://localhost:8000/health | grep -q '"status":"healthy"'; then
    echo -e "${GREEN}✅${NC} API REST reiniciada correctamente (puerto 8000)"
else
    echo -e "${RED}❌${NC} Error: La API no responde"
    exit 1
fi
echo ""

# =============================================================================
# 3. REINICIAR BOT DE TELEGRAM
# =============================================================================
echo "🤖 Paso 3/5: Reiniciando Bot de Telegram..."

# Reiniciar el servicio de systemd
if sudo systemctl restart telegram-polling.service 2>/dev/null; then
    sleep 3
    
    if systemctl is-active telegram-polling.service | grep -q "active"; then
        echo -e "${GREEN}✅${NC} Bot de Telegram reiniciado correctamente"
    else
        echo -e "${RED}❌${NC} Error: El bot no está activo"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️${NC}  No se pudo reiniciar con systemctl, intentando manualmente..."
    
    # Matar proceso manualmente
    pkill -f "telegram_polling.py" 2>/dev/null || true
    sleep 2
    
    # Iniciar manualmente
    cd /home/admonctrlxm/server/whatsapp_bot
    nohup /home/admonctrlxm/server/whatsapp_bot/venv/bin/python \
        /home/admonctrlxm/server/whatsapp_bot/telegram_polling.py \
        > /tmp/telegram_bot.log 2>&1 &
    
    sleep 3
    
    if pgrep -f "telegram_polling.py" > /dev/null; then
        echo -e "${GREEN}✅${NC} Bot de Telegram reiniciado manualmente"
    else
        echo -e "${RED}❌${NC} Error: No se pudo iniciar el bot"
        exit 1
    fi
fi
echo ""

# =============================================================================
# 4. REINICIAR CELERY WORKERS (si es necesario)
# =============================================================================
echo "⚙️  Paso 4/5: Reiniciando Celery Workers..."

# Reiniciar celery beat
sudo systemctl restart celery-beat.service 2>/dev/null || true

# Reiniciar celery workers
sudo systemctl restart celery-worker.service 2>/dev/null || true

sleep 2

echo -e "${GREEN}✅${NC} Celery reiniciado"
echo ""

# =============================================================================
# 5. VERIFICACIÓN FINAL
# =============================================================================
echo "🔍 Paso 5/5: Verificación final..."
echo ""

API_STATUS=$(curl -s http://localhost:8000/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
BOT_STATUS=$(systemctl is-active telegram-polling.service 2>/dev/null || echo "unknown")
CELERY_STATUS=$(systemctl is-active celery-worker.service 2>/dev/null || echo "unknown")

echo "Estado de servicios:"
echo "  📡 API REST:        ${API_STATUS:-'no responde'}"
echo "  🤖 Telegram Bot:    ${BOT_STATUS}"
echo "  ⚙️  Celery Worker:  ${CELERY_STATUS}"
echo ""

# Verificar que todo esté OK
if [ "$API_STATUS" = "healthy" ] && [ "$BOT_STATUS" = "active" ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✅ TODOS LOS SERVICIOS REINICIADOS CORRECTAMENTE${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "📋 Resumen de cambios aplicados:"
    echo "  • Caché de Python limpiada"
    echo "  • API REST reiniciada (puerto 8000)"
    echo "  • Bot de Telegram reiniciado"
    echo "  • Celery workers reiniciados"
    echo ""
    echo "🎯 Los cambios en el código ahora deberían estar activos"
    exit 0
else
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  ⚠️  ALGUNOS SERVICIOS NO ESTÁN FUNCIONANDO CORRECTAMENTE${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
