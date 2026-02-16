#!/bin/bash

# Script para instalar dependencias de Chrome/Chromium necesarias para whatsapp-web.js
# Requiere permisos de sudo

echo "📦 Instalando dependencias de Chrome para WhatsApp Web Service"
echo "=============================================================="
echo ""
echo "Este script instalará las librerías necesarias para que Chromium"
echo "funcione en modo headless (necesario para whatsapp-web.js)"
echo ""

sudo apt-get update

echo "📥 Instalando librerías del sistema..."
sudo apt-get install -y \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libnspr4 \
    libnss3 \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    wget

echo ""
echo "✅ Dependencias instaladas correctamente"
echo ""
echo "Ahora puedes ejecutar:"
echo "  cd /home/admonctrlxm/server/whatsapp_bot"
echo "  ./start-whatsapp-web.sh"
