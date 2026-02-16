#!/bin/bash

# ═══════════════════════════════════════════════════════════
# Script de Inicio Rápido - WhatsApp Bot
# ═══════════════════════════════════════════════════════════

set -e

echo "🤖 Iniciando WhatsApp Bot..."

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verificar .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Archivo .env no encontrado, copiando desde .env.example${NC}"
    cp .env.example .env
    echo "⚙️  Por favor edita .env con tus credenciales:"
    echo "   nano .env"
    exit 1
fi

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✓${NC} Entorno virtual activado"
else
    echo -e "${YELLOW}⚠️  No se encontró entorno virtual. Ejecuta primero:${NC}"
    echo "   ./setup.sh"
    exit 1
fi

# Crear directorios
mkdir -p logs data celery_data

# Iniciar servidor
echo ""
echo "🚀 Iniciando servidor en http://0.0.0.0:8001"
echo "📝 Logs: logs/whatsapp_bot.log"
echo ""
echo "Para detener: Ctrl+C"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
