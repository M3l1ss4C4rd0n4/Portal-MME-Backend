#!/bin/bash
# Script para ejecutar la API RESTful en modo desarrollo
# Uso: ./api/run_dev.sh

echo "🚀 Iniciando API RESTful del Portal Energético MME"
echo "=================================================="

# Verificar que estamos en el directorio correcto
if [ ! -f "api/main.py" ]; then
    echo "❌ Error: Ejecutar desde la raíz del proyecto (/home/admonctrlxm/server)"
    exit 1
fi

# Verificar que uvicorn está instalado
if ! command -v uvicorn &> /dev/null; then
    echo "⚠️  uvicorn no encontrado. Instalando..."
    pip install uvicorn[standard]
fi

# Cargar variables de entorno
if [ -f ".env" ]; then
    echo "✅ Cargando variables de entorno desde .env"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  Archivo .env no encontrado"
fi

# Ejecutar API en modo desarrollo
echo ""
echo "📡 Servidor corriendo en http://localhost:${API_PORT:-8000}"
echo "📚 Documentación en http://localhost:${API_PORT:-8000}/api/docs"
echo ""
echo "Presiona Ctrl+C para detener"
echo ""

uvicorn api.main:app \
    --reload \
    --host 0.0.0.0 \
    --port ${API_PORT:-8000} \
    --log-level info
