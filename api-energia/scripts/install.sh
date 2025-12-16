#!/bin/bash
# ========================================
# INSTALACIÓN Y CONFIGURACIÓN COMPLETA
# API Energía Colombia + DeepSeek IA
# ========================================

set -e  # Salir si hay error

echo "🚀 Instalación API Energía Colombia"
echo "===================================="
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ========================================
# 1. Verificar Node.js
# ========================================
echo -e "${YELLOW}📦 Verificando Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js no está instalado${NC}"
    echo "Instalando Node.js LTS..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

node_version=$(node --version)
echo -e "${GREEN}✅ Node.js $node_version${NC}"
echo ""

# ========================================
# 2. Crear archivo ~/.openrouter
# ========================================
echo -e "${YELLOW}🔑 Configurando OpenRouter API Key...${NC}"

if [ ! -f ~/.openrouter ]; then
    echo "export OPENROUTER_API_KEY=\"\"" > ~/.openrouter
    echo -e "${YELLOW}⚠️  Archivo ~/.openrouter creado${NC}"
    echo -e "${RED}IMPORTANTE: Edita ~/.openrouter y añade tu API Key${NC}"
    echo ""
    echo "1. Obtén tu API Key en: https://openrouter.ai/settings/keys"
    echo "2. Edita: nano ~/.openrouter"
    echo "3. Añade: export OPENROUTER_API_KEY=\"tu-api-key-aqui\""
    echo ""
else
    echo -e "${GREEN}✅ Archivo ~/.openrouter ya existe${NC}"
fi

# Añadir al .bashrc si no existe
if ! grep -q "source ~/.openrouter" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# OpenRouter API Key" >> ~/.bashrc
    echo "source ~/.openrouter" >> ~/.bashrc
    echo -e "${GREEN}✅ Añadido a ~/.bashrc${NC}"
fi

# Cargar variables
source ~/.openrouter 2>/dev/null || true

echo ""

# ========================================
# 3. Instalar dependencias NPM
# ========================================
echo -e "${YELLOW}📦 Instalando dependencias NPM...${NC}"
npm install
echo -e "${GREEN}✅ Dependencias instaladas${NC}"
echo ""

# ========================================
# 4. Crear base de datos
# ========================================
echo -e "${YELLOW}🗄️  Inicializando base de datos...${NC}"
npm run db:init
echo -e "${GREEN}✅ Base de datos creada${NC}"
echo ""

# ========================================
# 5. Crear directorios necesarios
# ========================================
echo -e "${YELLOW}📁 Creando directorios...${NC}"
mkdir -p logs
mkdir -p src/db
echo -e "${GREEN}✅ Directorios creados${NC}"
echo ""

# ========================================
# 6. Configurar PM2
# ========================================
echo -e "${YELLOW}⚙️  Configurando PM2...${NC}"

if ! command -v pm2 &> /dev/null; then
    echo "Instalando PM2 globalmente..."
    sudo npm install -g pm2
fi

pm2_version=$(pm2 --version)
echo -e "${GREEN}✅ PM2 $pm2_version${NC}"
echo ""

# ========================================
# 7. Verificar API Key
# ========================================
echo -e "${YELLOW}🔍 Verificando configuración...${NC}"

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo -e "${RED}❌ OPENROUTER_API_KEY no está configurada${NC}"
    echo ""
    echo "Pasos para configurar:"
    echo "1. Obtén tu API Key en: https://openrouter.ai/settings/keys"
    echo "2. Edita: nano ~/.openrouter"
    echo "3. Añade: export OPENROUTER_API_KEY=\"tu-api-key-aqui\""
    echo "4. Recarga: source ~/.openrouter"
    echo "5. Verifica: echo \$OPENROUTER_API_KEY"
    echo ""
else
    echo -e "${GREEN}✅ OPENROUTER_API_KEY configurada${NC}"
    echo "API Key: ${OPENROUTER_API_KEY:0:20}..."
fi

echo ""

# ========================================
# 8. Resumen
# ========================================
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ INSTALACIÓN COMPLETADA${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "📚 Comandos disponibles:"
echo ""
echo "  Desarrollo:"
echo "    npm run dev              # Servidor con auto-reload"
echo ""
echo "  Producción:"
echo "    npm start                # Iniciar servidor"
echo "    npm run db:init          # Inicializar base de datos"
echo ""
echo "  PM2 (Producción):"
echo "    pm2 start ecosystem.config.cjs    # Iniciar con PM2"
echo "    pm2 logs api-energia              # Ver logs"
echo "    pm2 restart api-energia           # Reiniciar"
echo "    pm2 stop api-energia              # Detener"
echo "    pm2 monit                         # Monitor"
echo ""
echo "📡 Endpoints de prueba:"
echo "    http://localhost:3000/"
echo "    http://localhost:3000/health"
echo "    http://localhost:3000/api/resumen"
echo ""
echo "🤖 Agente IA:"
echo "    POST http://localhost:3000/api/ia/analizar"
echo "    GET  http://localhost:3000/api/ia/resumen-dashboard"
echo ""

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo -e "${RED}⚠️  RECUERDA CONFIGURAR OPENROUTER_API_KEY${NC}"
    echo ""
fi
