#!/bin/bash

# Script de configuración rápida para Telegram Bot
# Portal Energético - Ministerio de Minas y Energía

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Configuración Rápida - Telegram Bot                   ║"
echo "║   Portal Energético - MME                                ║"
echo "║   ⚡ 100% GRATIS - Sin límites                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

WHATSAPP_BOT_DIR="/home/admonctrlxm/server/whatsapp_bot"
ENV_FILE="$WHATSAPP_BOT_DIR/.env"

cd "$WHATSAPP_BOT_DIR"

echo -e "${BLUE}📋 Guía Rápida para Telegram Bot${NC}"
echo ""
echo "Telegram Bot es:"
echo "  ✅ 100% GRATIS - sin costos por mensaje"
echo "  ✅ ILIMITADO - sin límite de mensajes"
echo "  ✅ RÁPIDO - configuración en 5-10 minutos"
echo "  ✅ FÁCIL - no requiere verificación empresarial"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar si ya tiene configuración de Telegram
if grep -q "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
    if [ -n "$TOKEN" ] && [ "$TOKEN" != '""' ]; then
        echo -e "${YELLOW}⚠️  Ya tienes un token de Telegram configurado${NC}"
        echo ""
        echo "Token actual: ${TOKEN:0:15}...${TOKEN: -10}"
        echo ""
        echo -e "${YELLOW}¿Deseas reconfigurar? (s/n)${NC}"
        read -r reconfig
        if [ "$reconfig" != "s" ]; then
            echo ""
            echo -e "${GREEN}Manteniendo configuración actual${NC}"
            exit 0
        fi
    fi
fi

echo -e "${BLUE}Paso 1: Crear bot en Telegram${NC}"
echo ""
echo "1. Abre Telegram y busca: ${YELLOW}@BotFather${NC}"
echo "2. Envía el comando: ${YELLOW}/newbot${NC}"
echo "3. Sigue las instrucciones de BotFather:"
echo "   - Nombre del bot: ${YELLOW}Portal Energético MME${NC}"
echo "   - Username: ${YELLOW}PortalEnergeticoMME_bot${NC} (o similar)"
echo "4. BotFather te dará un TOKEN"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo -e "${YELLOW}¿Ya creaste el bot y tienes el TOKEN? (s/n)${NC}"
read -r has_token

if [ "$has_token" != "s" ]; then
    echo ""
    echo -e "${BLUE}No hay problema!${NC}"
    echo ""
    echo "Crea el bot primero siguiendo estos pasos:"
    echo ""
    echo "1. Abre Telegram"
    echo "2. Busca @BotFather (verificado ✓)"
    echo "3. Envía: /newbot"
    echo "4. Sigue las instrucciones"
    echo ""
    echo "Cuando tengas el TOKEN, vuelve a ejecutar este script:"
    echo "  ${GREEN}./configurar_telegram.sh${NC}"
    echo ""
    echo "📚 Guía completa disponible en:"
    echo "  ${GREEN}cat GUIA_TELEGRAM_BOT_PASO_A_PASO.md${NC}"
    echo ""
    exit 0
fi

echo ""
echo -e "${BLUE}Paso 2: Ingresar el TOKEN del bot${NC}"
echo ""
echo "El TOKEN se ve así: ${YELLOW}123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567${NC}"
echo ""
echo -e "${YELLOW}Pega el TOKEN de tu bot:${NC}"
read -r TELEGRAM_BOT_TOKEN

# Verificar que no esté vacío
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo ""
    echo -e "${RED}✗ Error: El TOKEN no puede estar vacío${NC}"
    exit 1
fi

# Verificar formato básico del token
if [[ ! "$TELEGRAM_BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo ""
    echo -e "${YELLOW}⚠️  Advertencia: El formato del token parece incorrecto${NC}"
    echo "Un token válido se ve así: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567"
    echo ""
    echo -e "${YELLOW}¿Continuar de todos modos? (s/n)${NC}"
    read -r continue_anyway
    if [ "$continue_anyway" != "s" ]; then
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}Paso 3: Verificando el TOKEN...${NC}"
echo ""

# Verificar token con la API de Telegram
TOKEN_CHECK=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe")

if echo "$TOKEN_CHECK" | grep -q '"ok":true'; then
    BOT_USERNAME=$(echo "$TOKEN_CHECK" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
    BOT_NAME=$(echo "$TOKEN_CHECK" | grep -o '"first_name":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✓ Token válido${NC}"
    echo "  Bot: $BOT_NAME (@$BOT_USERNAME)"
    echo ""
else
    echo -e "${RED}✗ Token inválido${NC}"
    echo "Verifica que copiaste el token correctamente"
    echo ""
    echo "Respuesta de Telegram:"
    echo "$TOKEN_CHECK" | head -3
    exit 1
fi

echo -e "${BLUE}Paso 4: Configurando webhook...${NC}"
echo ""

WEBHOOK_URL="https://portalenergetico.minenergia.gov.co/whatsapp/webhook/telegram"

# Configurar webhook
WEBHOOK_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"${WEBHOOK_URL}\"}")

if echo "$WEBHOOK_RESULT" | grep -q '"ok":true'; then
    echo -e "${GREEN}✓ Webhook configurado correctamente${NC}"
    echo "  URL: $WEBHOOK_URL"
else
    echo -e "${YELLOW}⚠️  Advertencia: No se pudo configurar el webhook automáticamente${NC}"
    echo "  Inténtalo manualmente después de iniciar el bot"
    echo ""
    echo "Comando manual:"
    echo "  curl -X POST \"https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook\" \\"
    echo "    -H \"Content-Type: application/json\" \\"
    echo "    -d '{\"url\": \"${WEBHOOK_URL}\"}'"
fi

echo ""
echo -e "${BLUE}Paso 5: Actualizando configuración...${NC}"
echo ""

# Hacer backup del .env
if [ -f "$ENV_FILE" ]; then
    BACKUP_FILE="$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo -e "${GREEN}✓ Backup creado: $BACKUP_FILE${NC}"
fi

# Actualizar o agregar configuración de Telegram
if grep -q "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    # Actualizar token existente
    sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN|" "$ENV_FILE"
else
    # Agregar sección de Telegram si no existe
    if ! grep -q "# ===== TELEGRAM BOT =====" "$ENV_FILE" 2>/dev/null; then
        echo "" >> "$ENV_FILE"
        echo "# ===== TELEGRAM BOT - 100% GRATIS =====" >> "$ENV_FILE"
    fi
    echo "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN" >> "$ENV_FILE"
fi

# Habilitar Telegram
if grep -q "^TELEGRAM_ENABLED=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s/^TELEGRAM_ENABLED=.*/TELEGRAM_ENABLED=true/" "$ENV_FILE"
else
    echo "TELEGRAM_ENABLED=true" >> "$ENV_FILE"
fi

echo -e "${GREEN}✓ Configuración actualizada${NC}"

# Ajustar permisos
chmod 600 "$ENV_FILE"
echo -e "${GREEN}✓ Permisos del .env ajustados${NC}"

echo ""
echo -e "${BLUE}Paso 6: Instalando dependencias...${NC}"
echo ""

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✓ Entorno virtual activado${NC}"
else
    echo -e "${YELLOW}⚠️  No se encontró entorno virtual${NC}"
    echo "Creando uno nuevo..."
    python3 -m venv venv
    source venv/bin/activate
    echo -e "${GREEN}✓ Entorno virtual creado${NC}"
fi

# Instalar python-telegram-bot
echo "Instalando python-telegram-bot..."
pip install python-telegram-bot==20.7 -q

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencias instaladas${NC}"
else
    echo -e "${RED}✗ Error instalando dependencias${NC}"
    echo "Intenta manualmente:"
    echo "  pip install python-telegram-bot==20.7"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${GREEN}✅ ¡Configuración completada exitosamente!${NC}"
echo ""
echo -e "${BLUE}Tu bot de Telegram está listo:${NC}"
echo "  🤖 Bot: $BOT_NAME"
echo "  📱 Username: @$BOT_USERNAME"
echo "  🔗 Link directo: https://t.me/$BOT_USERNAME"
echo ""
echo -e "${BLUE}Siguientes pasos:${NC}"
echo ""
echo "1. Reiniciar el bot:"
echo "   ${YELLOW}pkill -f 'uvicorn app.main:app'${NC}"
echo "   ${YELLOW}uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &${NC}"
echo ""
echo "2. Abrir Telegram y buscar tu bot:"
echo "   ${YELLOW}@$BOT_USERNAME${NC}"
echo ""
echo "3. Enviar /start para iniciar"
echo ""
echo "4. ¡Probar comandos!"
echo "   • ${YELLOW}/precio${NC} - Ver precio actual"
echo "   • ${YELLOW}/generacion${NC} - Ver generación"
echo "   • ${YELLOW}/demanda${NC} - Ver demanda"
echo "   • ${YELLOW}/ayuda${NC} - Ver todos los comandos"
echo ""
echo -e "${GREEN}📚 Guía completa:${NC}"
echo "   GUIA_TELEGRAM_BOT_PASO_A_PASO.md"
echo ""
echo -e "${GREEN}💰 Costo: $0 USD - 100% GRATIS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Mostrar QR code para el bot
echo -e "${BLUE}🔗 Compartir el bot:${NC}"
echo ""
echo "Link directo:"
echo "  https://t.me/$BOT_USERNAME"
echo ""
echo "Puedes compartir este link en:"
echo "  • Sitio web del ministerio"
echo "  • Redes sociales"
echo "  • Emails internos"
echo ""
