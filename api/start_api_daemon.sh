#!/bin/bash
# Script para iniciar la API en modo daemon
# Se asegura de que solo haya una instancia corriendo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="/tmp/api-mme.pid"

cd "$SERVER_DIR" || exit 1

# Verificar si ya está corriendo
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ La API ya está corriendo (PID: $PID)"
        exit 0
    else
        echo "⚠️  PID file existe pero el proceso no. Limpiando..."
        rm -f "$PID_FILE"
    fi
fi

echo "🚀 Iniciando API RESTful Portal Energético MME..."

# Iniciar gunicorn en modo daemon
gunicorn api.main:app \
    --workers 4 \
    --threads 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile logs/api-access.log \
    --error-logfile logs/api-error.log \
    --log-level info \
    --daemon \
    --pid "$PID_FILE"

# Esperar un poco para que inicie
sleep 3

# Verificar que esté corriendo
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ API iniciada correctamente (PID: $PID)"
        echo "📡 Disponible en http://127.0.0.1:8000/"
        echo "📚 Documentación: http://127.0.0.1:8000/docs"
        exit 0
    fi
fi

echo "❌ Error al iniciar la API. Revisa logs/api-error.log"
exit 1
