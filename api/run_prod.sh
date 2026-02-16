#!/bin/bash
# Script para ejecutar la API RESTful en modo producción con Gunicorn
# Uso: ./api/run_prod.sh

echo "🚀 Iniciando API RESTful en modo PRODUCCIÓN"
echo "==========================================="

# Verificar que estamos en el directorio correcto
if [ ! -f "api/main.py" ]; then
    echo "❌ Error: Ejecutar desde la raíz del proyecto (/home/admonctrlxm/server)"
    exit 1
fi

# Verificar que gunicorn y uvicorn workers están instalados
if ! command -v gunicorn &> /dev/null; then
    echo "⚠️  gunicorn no encontrado. Instalando..."
    pip install gunicorn uvicorn[standard]
fi

# Cargar variables de entorno
if [ -f ".env" ]; then
    echo "✅ Cargando variables de entorno desde .env"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  Archivo .env no encontrado"
fi

# Configuración de Gunicorn
WORKERS=${GUNICORN_WORKERS:-4}
THREADS=${GUNICORN_THREADS:-4}
BIND="0.0.0.0:${API_PORT:-8000}"
TIMEOUT=${GUNICORN_TIMEOUT:-120}
KEEPALIVE=${GUNICORN_KEEPALIVE:-5}
MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}

echo ""
echo "⚙️  Configuración:"
echo "   Workers: $WORKERS"
echo "   Threads: $THREADS"
echo "   Bind: $BIND"
echo "   Timeout: ${TIMEOUT}s"
echo ""
echo "📡 API disponible en http://$BIND"
echo ""

gunicorn api.main:app \
    --workers $WORKERS \
    --threads $THREADS \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind $BIND \
    --timeout $TIMEOUT \
    --keepalive $KEEPALIVE \
    --max-requests $MAX_REQUESTS \
    --max-requests-jitter 100 \
    --access-logfile logs/api-access.log \
    --error-logfile logs/api-error.log \
    --log-level info \
    --preload
