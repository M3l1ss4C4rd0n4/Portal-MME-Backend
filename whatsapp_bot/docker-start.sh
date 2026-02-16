#!/bin/bash

# ═══════════════════════════════════════════════════════════
# Script de Ejecución con Docker Compose
# ═══════════════════════════════════════════════════════════

echo "🐳 Iniciando WhatsApp Bot con Docker Compose..."

# Verificar .env
if [ ! -f ".env" ]; then
    echo "⚠️  Copiando .env.example a .env"
    cp .env.example .env
    echo "⚙️  Por favor edita .env con tus credenciales antes de continuar:"
    echo "   nano .env"
    echo ""
    read -p "Presiona ENTER cuando hayas configurado .env..."
fi

# Build imágenes
echo "📦 Construyendo imágenes Docker..."
docker-compose build

# Iniciar servicios
echo "🚀 Iniciando servicios..."
docker-compose up -d

# Esperar un momento
sleep 5

# Verificar estado
echo ""
echo "✅ Servicios iniciados:"
docker-compose ps

echo ""
echo "📊 Ver logs:"
echo "   docker-compose logs -f whatsapp-bot"
echo ""
echo "🔍 Health check:"
echo "   curl http://localhost:8001/health"
echo ""
echo "🛑 Detener servicios:"
echo "   docker-compose down"
