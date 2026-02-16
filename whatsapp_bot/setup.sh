#!/bin/bash

# ═══════════════════════════════════════════════════════════
# Script de Setup Rápido - WhatsApp Bot
# ═══════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  🤖 WhatsApp Bot - Portal Energético MME"
echo "  Setup y Configuración Inicial"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Función de ayuda
print_step() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# ═══════════════════════════════════════════════════════════
# 1. Verificar dependencias
# ═══════════════════════════════════════════════════════════
echo "📦 Verificando dependencias del sistema..."

# Verificar Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 no está instalado"
    exit 1
fi
print_step "Python 3 $(python3 --version | cut -d' ' -f2) encontrado"

# Verificar pip
if ! command -v pip3 &> /dev/null; then
    print_error "pip3 no está instalado"
    exit 1
fi
print_step "pip3 encontrado"

# ═══════════════════════════════════════════════════════════
# 2. Crear entorno virtual
# ═══════════════════════════════════════════════════════════
echo ""
echo "🐍 Configurando entorno virtual..."

if [ -d "venv" ]; then
    print_warning "Entorno virtual ya existe, saltando creación"
else
    python3 -m venv venv
    print_step "Entorno virtual creado"
fi

# Activar entorno
source venv/bin/activate
print_step "Entorno virtual activado"

# ═══════════════════════════════════════════════════════════
# 3. Instalar dependencias
# ═══════════════════════════════════════════════════════════
echo ""
echo "📚 Instalando dependencias..."

pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
print_step "Dependencias instaladas"

# Descargar modelo spaCy
echo ""
echo "🔤 Descargando modelo de lenguaje español..."
python -m spacy download es_core_news_sm
print_step "Modelo spaCy instalado"

# ═══════════════════════════════════════════════════════════
# 4. Configurar .env
# ═══════════════════════════════════════════════════════════
echo ""
echo "⚙️  Configurando variables de entorno..."

if [ -f ".env" ]; then
    print_warning "Archivo .env ya existe"
    read -p "¿Deseas sobrescribirlo? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.example .env
        print_step "Archivo .env creado desde plantilla"
    fi
else
    cp .env.example .env
    print_step "Archivo .env creado desde plantilla"
fi

# ═══════════════════════════════════════════════════════════
# 5. Crear directorios necesarios
# ═══════════════════════════════════════════════════════════
echo ""
echo "📁 Creando directorios..."

mkdir -p logs
mkdir -p data
mkdir -p celery_data

print_step "Directorios creados"

# ═══════════════════════════════════════════════════════════
# 6. Configuración interactiva (opcional)
# ═══════════════════════════════════════════════════════════
echo ""
echo "🔧 Configuración de credenciales"
echo ""
read -p "¿Deseas configurar credenciales ahora? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "📱 Credenciales Twilio (obtener en https://console.twilio.com):"
    read -p "TWILIO_ACCOUNT_SID: " twilio_sid
    read -p "TWILIO_AUTH_TOKEN: " twilio_token
    
    echo ""
    echo "🤖 API Key de Groq (obtener en https://console.groq.com):"
    read -p "GROQ_API_KEY: " groq_key
    
    # Actualizar .env
    if [ -n "$twilio_sid" ]; then
        sed -i "s/TWILIO_ACCOUNT_SID=.*/TWILIO_ACCOUNT_SID=$twilio_sid/" .env
    fi
    if [ -n "$twilio_token" ]; then
        sed -i "s/TWILIO_AUTH_TOKEN=.*/TWILIO_AUTH_TOKEN=$twilio_token/" .env
    fi
    if [ -n "$groq_key" ]; then
        sed -i "s/GROQ_API_KEY=.*/GROQ_API_KEY=$groq_key/" .env
    fi
    
    print_step "Credenciales guardadas en .env"
fi

# ═══════════════════════════════════════════════════════════
# 7. Verificar instalación
# ═══════════════════════════════════════════════════════════
echo ""
echo "✅ Verificando instalación..."

python -c "import fastapi; import twilio; import openai; import plotly" 2>/dev/null
if [ $? -eq 0 ]; then
    print_step "Todas las dependencias principales instaladas correctamente"
else
    print_error "Algunas dependencias faltan, verifica el log arriba"
fi

# ═══════════════════════════════════════════════════════════
# 8. Instrucciones finales
# ═══════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "  ${GREEN}✅ Setup completado exitosamente!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📝 Próximos pasos:"
echo ""
echo "1. Editar .env con tus credenciales:"
echo "   nano .env"
echo ""
echo "2. Iniciar el bot en modo desarrollo:"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload --port 8001"
echo ""
echo "3. O con Docker Compose (recomendado):"
echo "   docker-compose up -d"
echo ""
echo "4. Exponer webhook para testing (en otra terminal):"
echo "   ngrok http 8001"
echo ""
echo "5. Configurar webhook en Twilio Console:"
echo "   https://console.twilio.com → Messaging → WhatsApp Sandbox"
echo "   URL: https://xxxx.ngrok.io/webhook/whatsapp"
echo ""
echo "📚 Documentación completa en:"
echo "   - README.md"
echo "   - ../docs/ARQUITECTURA_WHATSAPP_BOT_COMPLETO.md"
echo ""
echo "═══════════════════════════════════════════════════════════"
