#!/bin/bash
# Script de instalación y configuración del Agente IA
# Para Dashboard Ministerio de Minas y Energía

set -e  # Salir si hay errores

echo "========================================="
echo "🤖 INSTALACIÓN AGENTE IA - DASHBOARD MME"
echo "========================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directorio base
BASE_DIR="/home/admonctrlxm/server"
API_DIR="$BASE_DIR/api-energia"

# ========================================
# 1. Verificar Node.js
# ========================================
echo -e "${BLUE}📦 Verificando Node.js...${NC}"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓ Node.js instalado: $NODE_VERSION${NC}"
else
    echo -e "${RED}✗ Node.js NO instalado${NC}"
    echo -e "${YELLOW}Instalando Node.js 18.x...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
    echo -e "${GREEN}✓ Node.js instalado${NC}"
fi

# ========================================
# 2. Instalar dependencias de la API
# ========================================
echo ""
echo -e "${BLUE}📦 Instalando dependencias de la API...${NC}"
cd "$API_DIR"

if [ -f "package.json" ]; then
    npm install
    echo -e "${GREEN}✓ Dependencias instaladas${NC}"
else
    echo -e "${RED}✗ package.json no encontrado${NC}"
    exit 1
fi

# ========================================
# 3. Verificar dependencias Python
# ========================================
echo ""
echo -e "${BLUE}🐍 Verificando dependencias Python para Dashboard...${NC}"
cd "$BASE_DIR"

# Agregar requests si no está en requirements.txt
if ! grep -q "requests" requirements.txt; then
    echo "requests>=2.31.0" >> requirements.txt
    echo -e "${YELLOW}→ Agregado 'requests' a requirements.txt${NC}"
fi

# Instalar/actualizar
pip3 install -r requirements.txt --quiet
echo -e "${GREEN}✓ Dependencias Python actualizadas${NC}"

# ========================================
# 4. Configurar variables de entorno
# ========================================
echo ""
echo -e "${BLUE}🔐 Configurando variables de entorno...${NC}"

# Verificar si ya existe OPENROUTER_API_KEY
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  OPENROUTER_API_KEY no configurada${NC}"
    echo ""
    echo -e "${BLUE}Para obtener tu API Key:${NC}"
    echo -e "  1. Ve a: ${GREEN}https://openrouter.ai/settings/keys${NC}"
    echo -e "  2. Crea una nueva clave"
    echo -e "  3. Copia la clave (formato: sk-or-v1-...)"
    echo ""
    read -p "¿Deseas configurarla ahora? (s/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        read -p "Pega tu API Key de OpenRouter: " API_KEY
        
        # Guardar en .bashrc
        echo "" >> ~/.bashrc
        echo "# OpenRouter API Key para Dashboard MME" >> ~/.bashrc
        echo "export OPENROUTER_API_KEY=\"$API_KEY\"" >> ~/.bashrc
        
        # Aplicar ahora
        export OPENROUTER_API_KEY="$API_KEY"
        
        # También en .env de la API
        cd "$API_DIR"
        if grep -q "^OPENROUTER_API_KEY=" .env; then
            sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$API_KEY|" .env
        else
            echo "OPENROUTER_API_KEY=$API_KEY" >> .env
        fi
        
        echo -e "${GREEN}✓ API Key configurada${NC}"
    else
        echo -e "${YELLOW}⚠️  Configúrala manualmente después:${NC}"
        echo -e "   ${BLUE}echo 'export OPENROUTER_API_KEY=\"tu-clave\"' >> ~/.bashrc${NC}"
        echo -e "   ${BLUE}source ~/.bashrc${NC}"
    fi
else
    echo -e "${GREEN}✓ OPENROUTER_API_KEY ya configurada${NC}"
fi

# ========================================
# 5. Inicializar base de datos
# ========================================
echo ""
echo -e "${BLUE}🗄️  Inicializando base de datos de la API...${NC}"
cd "$API_DIR"

if [ -f "scripts/initDatabase.js" ]; then
    node scripts/initDatabase.js
    echo -e "${GREEN}✓ Base de datos inicializada${NC}"
else
    echo -e "${YELLOW}⚠️  Script de inicialización no encontrado${NC}"
fi

# ========================================
# 6. Verificar componente de chat
# ========================================
echo ""
echo -e "${BLUE}💬 Verificando componente de Chat IA...${NC}"
cd "$BASE_DIR"

if [ -f "componentes/chat_ia.py" ]; then
    echo -e "${GREEN}✓ Componente de chat creado${NC}"
else
    echo -e "${RED}✗ Componente de chat NO encontrado${NC}"
fi

# ========================================
# 7. Crear servicio systemd para la API
# ========================================
echo ""
echo -e "${BLUE}⚙️  Configurando servicio systemd para API...${NC}"

sudo bash -c "cat > /etc/systemd/system/api-energia.service" << 'EOF'
[Unit]
Description=API Energia Colombia - Agente IA
After=network.target postgresql.service

[Service]
Type=simple
User=admonctrlxm
WorkingDirectory=/home/admonctrlxm/server/api-energia
Environment="NODE_ENV=production"
Environment="PATH=/usr/bin:/usr/local/bin"
EnvironmentFile=/home/admonctrlxm/.bashrc
ExecStart=/usr/bin/node /home/admonctrlxm/server/api-energia/src/server.js
Restart=always
RestartSec=10
StandardOutput=append:/home/admonctrlxm/server/api-energia/logs/api.log
StandardError=append:/home/admonctrlxm/server/api-energia/logs/api-error.log

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✓ Servicio systemd creado${NC}"

# ========================================
# 8. Crear directorio de logs
# ========================================
mkdir -p "$API_DIR/logs"
touch "$API_DIR/logs/api.log"
touch "$API_DIR/logs/api-error.log"

# ========================================
# 9. Habilitar e iniciar servicios
# ========================================
echo ""
echo -e "${BLUE}🚀 Habilitando servicios...${NC}"

sudo systemctl daemon-reload
sudo systemctl enable api-energia.service

echo ""
read -p "¿Deseas iniciar la API ahora? (s/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Ss]$ ]]; then
    sudo systemctl start api-energia.service
    sleep 2
    
    if sudo systemctl is-active --quiet api-energia.service; then
        echo -e "${GREEN}✓ API iniciada correctamente${NC}"
        echo ""
        echo -e "${BLUE}Estado del servicio:${NC}"
        sudo systemctl status api-energia.service --no-pager | head -15
    else
        echo -e "${RED}✗ Error al iniciar la API${NC}"
        echo -e "${YELLOW}Revisa los logs:${NC}"
        echo -e "   ${BLUE}sudo journalctl -u api-energia.service -n 50${NC}"
    fi
fi

# ========================================
# 10. Reiniciar Dashboard
# ========================================
echo ""
read -p "¿Deseas reiniciar el Dashboard para aplicar cambios? (s/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Ss]$ ]]; then
    sudo systemctl restart dashboard-mme.service
    sleep 3
    
    if sudo systemctl is-active --quiet dashboard-mme.service; then
        echo -e "${GREEN}✓ Dashboard reiniciado correctamente${NC}"
    else
        echo -e "${RED}✗ Error al reiniciar el Dashboard${NC}"
    fi
fi

# ========================================
# RESUMEN FINAL
# ========================================
echo ""
echo "========================================="
echo -e "${GREEN}✅ INSTALACIÓN COMPLETADA${NC}"
echo "========================================="
echo ""
echo -e "${BLUE}📊 Servicios:${NC}"
echo -e "  • Dashboard Dash: ${GREEN}http://localhost:8050${NC}"
echo -e "  • API Energía:    ${GREEN}http://localhost:3000${NC}"
echo ""
echo -e "${BLUE}🔧 Comandos útiles:${NC}"
echo -e "  • Ver estado API:      ${YELLOW}sudo systemctl status api-energia${NC}"
echo -e "  • Ver logs API:        ${YELLOW}tail -f $API_DIR/logs/api.log${NC}"
echo -e "  • Reiniciar API:       ${YELLOW}sudo systemctl restart api-energia${NC}"
echo -e "  • Ver estado Dashboard:${YELLOW}sudo systemctl status dashboard-mme${NC}"
echo ""
echo -e "${BLUE}🧪 Probar el agente IA:${NC}"
echo -e "  ${YELLOW}curl http://localhost:3000/api/ia/resumen-dashboard${NC}"
echo ""
echo -e "${BLUE}📚 Documentación:${NC}"
echo -e "  ${GREEN}$API_DIR/SETUP_OPENROUTER.md${NC}"
echo -e "  ${GREEN}$API_DIR/README.md${NC}"
echo ""

# Verificar si necesita configurar API Key
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo -e "${RED}⚠️  IMPORTANTE: Configura OPENROUTER_API_KEY para activar el agente IA${NC}"
    echo -e "   Lee: ${GREEN}$API_DIR/SETUP_OPENROUTER.md${NC}"
    echo ""
fi

echo -e "${GREEN}¡Listo! El sistema está configurado.${NC}"
echo ""
