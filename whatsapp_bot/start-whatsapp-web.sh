#!/bin/bash

# Script para iniciar whatsapp-web-service
# Este servicio conecta con WhatsApp Web directamente (100% GRATIS)

set -e

echo "🚀 Iniciando WhatsApp Web Service (Método Gratuito)"
echo "==============================================="
echo ""

# Directorio del servicio
SERVICE_DIR="/home/admonctrlxm/server/whatsapp_bot/whatsapp-web-service"

# Verificar que existe
if [ ! -d "$SERVICE_DIR" ]; then
    echo "❌ Error: Directorio $SERVICE_DIR no existe"
    exit 1
fi

cd "$SERVICE_DIR"

# Cargar nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js no está instalado"
    echo "   Ejecuta: nvm install 20"
    exit 1
fi

echo "✅ Node.js: $(node --version)"
echo "✅ npm: $(npm --version)"
echo ""

# Instalar dependencias si no existen
if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependencias..."
    npm install
    echo ""
fi

echo "🔄 Iniciando servicio..."
echo ""
echo "📱 IMPORTANTE:"
echo "   1. Al iniciar verás un código QR en la consola"
echo "   2. Abre WhatsApp en tu teléfono"
echo "   3. Ve a: Menú > Dispositivos vinculados"
echo "   4. Toca 'Vincular dispositivo'"
echo "   5. Escanea el código QR que aparece abajo"
echo ""
echo "⏳ Esperando código QR..."
echo "========================================"
echo ""

# Ejecutar servicio
node server.js
