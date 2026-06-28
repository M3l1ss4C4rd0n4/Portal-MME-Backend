#!/bin/bash
# Script para detener la API
# NOTA: En producción, usar systemd: sudo systemctl stop portal-api.service

PID_FILE="/tmp/portal-api.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  No se encontró el archivo PID. Buscando procesos..."
    pkill -f "gunicorn api.main:app"
    echo "✅ Procesos de API detenidos"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "🛑 Deteniendo API (PID: $PID)..."
    kill -TERM "$PID"
    sleep 2
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️  Proceso no respondió a SIGTERM, forzando..."
        kill -9 "$PID"
    fi
    
    rm -f "$PID_FILE"
    echo "✅ API detenida"
else
    echo "⚠️  El proceso no está corriendo. Limpiando PID file..."
    rm -f "$PID_FILE"
fi

exit 0
