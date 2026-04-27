#!/bin/bash
# Script para reiniciar todos los servicios del Portal Energético

echo "🔄 Reiniciando servicios del Portal Energético..."

# Limpiar caché de Python
echo "Limpiando caché de Python..."
cd /home/admonctrlxm/server
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Reiniciar API
echo "Reiniciando API..."
pkill -f "gunicorn.*api.main" 2>/dev/null
sleep 2

nohup /home/admonctrlxm/server/venv/bin/gunicorn api.main:app \
    --workers 2 --threads 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --max-requests 1000 --max-requests-jitter 100 \
    --access-logfile /home/admonctrlxm/server/logs/api-access.log \
    --error-logfile /home/admonctrlxm/server/logs/api-error.log \
    --log-level info \
    > /tmp/gunicorn_api.log 2>&1 &

sleep 3

# Verificar API
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "✅ API reiniciada correctamente"
else
    echo "❌ Error reiniciando API"
fi

# Reiniciar Telegram Bot
echo "Reiniciando Telegram Bot..."
sudo systemctl restart telegram-polling.service 2>/dev/null || echo "⚠️  No se pudo reiniciar el servicio del bot (puede necesitar sudo)"

echo ""
echo "✅ Reinicio completado"
echo "Los cambios en el PDF deberían estar visibles ahora"
