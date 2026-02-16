#!/bin/bash

# Script de preparación para Meta WhatsApp Business API
# Portal Energético - Ministerio de Minas y Energía

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Preparación Meta WhatsApp Business API                 ║"
echo "║   Portal Energético - MME                                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
WHATSAPP_BOT_DIR="/home/admonctrlxm/server/whatsapp_bot"
ENV_FILE="$WHATSAPP_BOT_DIR/.env"
ENV_BACKUP="$WHATSAPP_BOT_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"

echo -e "${BLUE}Paso 1: Verificando entorno...${NC}"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d "$WHATSAPP_BOT_DIR" ]; then
    echo -e "${RED}✗ Error: Directorio $WHATSAPP_BOT_DIR no encontrado${NC}"
    exit 1
fi

cd "$WHATSAPP_BOT_DIR"
echo -e "${GREEN}✓ Directorio de trabajo: $WHATSAPP_BOT_DIR${NC}"

# Verificar que existe .env
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}✗ Error: Archivo .env no encontrado${NC}"
    echo -e "${YELLOW}¿Deseas crear uno desde .env.example? (s/n)${NC}"
    read -r create_env
    if [ "$create_env" = "s" ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ Archivo .env creado${NC}"
    else
        exit 1
    fi
fi

echo -e "${GREEN}✓ Archivo .env encontrado${NC}"
echo ""

# Hacer backup del .env actual
echo -e "${BLUE}Paso 2: Creando backup de configuración actual...${NC}"
cp "$ENV_FILE" "$ENV_BACKUP"
echo -e "${GREEN}✓ Backup creado: $ENV_BACKUP${NC}"
echo ""

# Verificar dependencias del bot
echo -e "${BLUE}Paso 3: Verificando dependencias...${NC}"

if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ Entorno virtual no encontrado${NC}"
    echo -e "${YELLOW}¿Deseas crear uno ahora? (s/n)${NC}"
    read -r create_venv
    if [ "$create_venv" = "s" ]; then
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        echo -e "${GREEN}✓ Entorno virtual creado e instalado${NC}"
    fi
else
    echo -e "${GREEN}✓ Entorno virtual existe${NC}"
fi

# Verificar que el bot está instalado
source venv/bin/activate 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Entorno virtual activado${NC}"
else
    echo -e "${YELLOW}⚠ No se pudo activar entorno virtual${NC}"
fi

echo ""

# Verificar servicios necesarios
echo -e "${BLUE}Paso 4: Verificando servicios necesarios...${NC}"

# Redis
if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis; then
    echo -e "${GREEN}✓ Redis está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ Redis no está corriendo (necesario para contexto y rate limiting)${NC}"
fi

# PostgreSQL
if systemctl is-active --quiet postgresql; then
    echo -e "${GREEN}✓ PostgreSQL está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL no está corriendo (necesario para datos)${NC}"
fi

# Nginx
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ Nginx está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ Nginx no está corriendo (necesario para webhook)${NC}"
fi

echo ""

# Verificar webhook
echo -e "${BLUE}Paso 5: Verificando accesibilidad del webhook...${NC}"

WEBHOOK_URL="https://portalenergetico.minenergia.gov.co/whatsapp/health"

if command -v curl &> /dev/null; then
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$WEBHOOK_URL" 2>/dev/null)
    if [ "$HTTP_STATUS" = "200" ]; then
        echo -e "${GREEN}✓ Webhook accesible: $WEBHOOK_URL${NC}"
    else
        echo -e "${YELLOW}⚠ Webhook no responde (código: $HTTP_STATUS)${NC}"
        echo -e "${YELLOW}  Esto es normal si el bot no está iniciado aún${NC}"
    fi
else
    echo -e "${YELLOW}⚠ curl no está instalado, no se puede verificar webhook${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Solicitar información de Meta
echo -e "${BLUE}Ahora vamos a configurar las credenciales de Meta API${NC}"
echo ""
echo -e "${YELLOW}Necesitarás tener a mano:${NC}"
echo "  1. META_ACCESS_TOKEN (token largo de Meta)"
echo "  2. META_PHONE_NUMBER_ID (ID numérico del teléfono)"
echo "  3. META_WABA_ID (ID de cuenta WhatsApp Business)"
echo "  4. META_VERIFY_TOKEN (token que TÚ inventas para verificación)"
echo ""
echo -e "${YELLOW}Si aún no tienes estas credenciales:${NC}"
echo "  → Lee la guía: GUIA_META_API_PASO_A_PASO.md"
echo "  → Sigue los pasos 1-5 para obtenerlas"
echo ""
echo -e "${YELLOW}¿Ya tienes las credenciales de Meta? (s/n)${NC}"
read -r has_credentials

if [ "$has_credentials" != "s" ]; then
    echo ""
    echo -e "${BLUE}No hay problema. Cuando las tengas, ejecuta este script nuevamente.${NC}"
    echo ""
    echo -e "${GREEN}Para obtenerlas, sigue esta guía:${NC}"
    echo "  cat GUIA_META_API_PASO_A_PASO.md | less"
    echo ""
    echo -e "${GREEN}O ábrela en el editor:${NC}"
    echo "  nano GUIA_META_API_PASO_A_PASO.md"
    echo ""
    exit 0
fi

echo ""
echo -e "${BLUE}Perfecto. Vamos a configurar el .env${NC}"
echo ""

# Solicitar credenciales
echo -e "${YELLOW}Ingresa el META_ACCESS_TOKEN:${NC}"
echo "(Comienza con EAAB... y es muy largo)"
read -r META_ACCESS_TOKEN

echo ""
echo -e "${YELLOW}Ingresa el META_PHONE_NUMBER_ID:${NC}"
echo "(Número largo, ejemplo: 102477565833922)"
read -r META_PHONE_NUMBER_ID

echo ""
echo -e "${YELLOW}Ingresa el META_WABA_ID:${NC}"
echo "(Número largo, ejemplo: 104857092476789)"
read -r META_WABA_ID

echo ""
echo -e "${YELLOW}Ingresa el META_VERIFY_TOKEN:${NC}"
echo "(Token que TÚ inventas, ejemplo: MinEnerg1a_S3cr3t_2026)"
read -r META_VERIFY_TOKEN

# Verificar que no estén vacías
if [ -z "$META_ACCESS_TOKEN" ] || [ -z "$META_PHONE_NUMBER_ID" ] || [ -z "$META_WABA_ID" ] || [ -z "$META_VERIFY_TOKEN" ]; then
    echo ""
    echo -e "${RED}✗ Error: Todas las credenciales son obligatorias${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}Paso 6: Actualizando configuración...${NC}"

# Cambiar proveedor a meta
if grep -q "^WHATSAPP_PROVIDER=" "$ENV_FILE"; then
    sed -i 's/^WHATSAPP_PROVIDER=.*/WHATSAPP_PROVIDER=meta/' "$ENV_FILE"
    echo -e "${GREEN}✓ Proveedor cambiado a 'meta'${NC}"
else
    echo "WHATSAPP_PROVIDER=meta" >> "$ENV_FILE"
    echo -e "${GREEN}✓ Proveedor configurado como 'meta'${NC}"
fi

# Agregar o actualizar credenciales Meta
update_or_add_env() {
    local key=$1
    local value=$2
    local file=$3
    
    if grep -q "^$key=" "$file"; then
        sed -i "s|^$key=.*|$key=$value|" "$file"
    else
        echo "$key=$value" >> "$file"
    fi
}

# Agregar sección de Meta si no existe
if ! grep -q "# ===== META WHATSAPP BUSINESS API =====" "$ENV_FILE"; then
    echo "" >> "$ENV_FILE"
    echo "# ===== META WHATSAPP BUSINESS API =====" >> "$ENV_FILE"
fi

update_or_add_env "META_ACCESS_TOKEN" "$META_ACCESS_TOKEN" "$ENV_FILE"
update_or_add_env "META_PHONE_NUMBER_ID" "$META_PHONE_NUMBER_ID" "$ENV_FILE"
update_or_add_env "META_WABA_ID" "$META_WABA_ID" "$ENV_FILE"
update_or_add_env "META_VERIFY_TOKEN" "$META_VERIFY_TOKEN" "$ENV_FILE"
update_or_add_env "META_API_VERSION" "v21.0" "$ENV_FILE"

echo -e "${GREEN}✓ Credenciales de Meta agregadas al .env${NC}"
echo ""

# Verificar configuración
echo -e "${BLUE}Paso 7: Verificando configuración...${NC}"
echo ""
echo "Configuración actual:"
echo "  WHATSAPP_PROVIDER=$(grep '^WHATSAPP_PROVIDER=' $ENV_FILE | cut -d'=' -f2)"
echo "  META_PHONE_NUMBER_ID=$META_PHONE_NUMBER_ID"
echo "  META_WABA_ID=$META_WABA_ID"
echo "  META_ACCESS_TOKEN=${META_ACCESS_TOKEN:0:20}..."
echo "  META_VERIFY_TOKEN=${META_VERIFY_TOKEN:0:10}..."
echo ""

# Ajustar permisos del .env
chmod 600 "$ENV_FILE"
echo -e "${GREEN}✓ Permisos del .env ajustados (solo lectura para usuario)${NC}"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${GREEN}✅ ¡Configuración completada exitosamente!${NC}"
echo ""
echo -e "${BLUE}Siguientes pasos:${NC}"
echo ""
echo "1. Reiniciar el bot con la nueva configuración:"
echo "   ${YELLOW}pkill -f 'uvicorn app.main:app'${NC}"
echo "   ${YELLOW}source venv/bin/activate${NC}"
echo "   ${YELLOW}uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload${NC}"
echo ""
echo "2. Verificar que esté usando Meta:"
echo "   ${YELLOW}curl https://portalenergetico.minenergia.gov.co/whatsapp/health${NC}"
echo "   Debe mostrar: \"provider\": \"meta\""
echo ""
echo "3. Configurar webhook en Meta:"
echo "   → Ve a: https://developers.facebook.com/apps"
echo "   → Selecciona tu app"
echo "   → WhatsApp > Configuración > Webhook"
echo "   → URL: https://portalenergetico.minenergia.gov.co/whatsapp/webhook/whatsapp"
echo "   → Token: $META_VERIFY_TOKEN"
echo "   → Verificar y guardar"
echo ""
echo "4. Probar enviando un mensaje:"
echo "   Envía 'hola' desde WhatsApp al número verificado"
echo ""
echo -e "${GREEN}📚 Guía completa disponible en:${NC}"
echo "   GUIA_META_API_PASO_A_PASO.md"
echo ""
echo -e "${GREEN}💾 Backup de configuración anterior:${NC}"
echo "   $ENV_BACKUP"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
