#!/bin/bash
# =============================================================================
# SCRIPT DE GESTIÓN SIMPLIFICADO - Dashboard MME
# =============================================================================

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DOMAIN="vps-0c525a03.vps.ovh.ca"
APP_DIR="/home/admonctrlxm/server"

# Función para mostrar el menú
show_menu() {
    clear
    echo -e "${BLUE}=================================================${NC}"
    echo -e "${BLUE}    GESTIÓN DEL SERVIDOR - Dashboard MME${NC}"
    echo -e "${BLUE}=================================================${NC}"
    echo ""
    echo -e "${GREEN}📊 ESTADO Y MONITOREO:${NC}"
    echo "   1) Ver estado de la aplicación"
    echo "   2) Verificar conectividad web"
    echo "   3) Ver procesos activos"
    echo "   4) Ver logs de la aplicación"
    echo ""
    echo -e "${YELLOW}🔧 GESTIÓN DE LA APLICACIÓN:${NC}"
    echo "   5) Iniciar/Reiniciar aplicación"
    echo "   6) Detener aplicación"
    echo "   7) Actualizar desde Git (manual)"
    echo "   8) Actualizar desde Git (automático)"
    echo "   9) Configurar actualizaciones automáticas"
    echo ""
    echo -e "${BLUE}⚙️  SISTEMA:${NC}"
    echo "   10) Ver uso de recursos"
    echo "   11) Limpiar logs antiguos"
    echo "   12) Reiniciar nginx"
    echo ""
    echo -e "${GREEN}🔐 SSL:${NC}"
    echo "   13) Ver estado de certificados"
    echo "   14) Renovar certificados SSL"
    echo ""
    echo "   0) Salir"
    echo ""
    echo -e "${BLUE}=================================================${NC}"
    echo -n "Selecciona una opción: "
}

# Funciones principales
show_status() {
    echo -e "${GREEN}📊 Estado de la Aplicación:${NC}"
    if pgrep -f "python.*app.py" > /dev/null; then
        echo "✅ Aplicación corriendo"
        echo "PID: $(pgrep -f 'python.*app.py')"
    else
        echo "❌ Aplicación NO está corriendo"
    fi
    echo ""
}

check_web() {
    echo -e "${GREEN}🌐 Verificando Conectividad:${NC}"
    HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}" https://$DOMAIN/)
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "✅ Web funcionando (HTTP $HTTP_STATUS)"
    else
        echo "❌ Problema en web (HTTP $HTTP_STATUS)"
    fi
    
    if curl -s http://127.0.0.1:8056/ > /dev/null; then
        echo "✅ Aplicación local funcionando"
    else
        echo "❌ Aplicación local no responde"
    fi
    echo ""
}

start_app() {
    echo -e "${YELLOW}🚀 Iniciando/Reiniciando Aplicación...${NC}"
    cd $APP_DIR
    
    # Detener proceso existente
    pkill -f "python.*app.py" 2>/dev/null || true
    sleep 2
    
    # Iniciar nueva instancia
    source dashboard_env/bin/activate
    nohup python app.py > logs/app.log 2>&1 &
    sleep 3
    
    if pgrep -f "python.*app.py" > /dev/null; then
        echo "✅ Aplicación iniciada correctamente"
    else
        echo "❌ Error al iniciar la aplicación"
    fi
}

stop_app() {
    echo -e "${RED}⏹️ Deteniendo Aplicación...${NC}"
    pkill -f "python.*app.py" 2>/dev/null
    sleep 1
    if ! pgrep -f "python.*app.py" > /dev/null; then
        echo "✅ Aplicación detenida"
    else
        echo "❌ Error al detener la aplicación"
    fi
}

view_logs() {
    echo -e "${GREEN}📝 Logs de la Aplicación (Ctrl+C para salir):${NC}"
    tail -f $APP_DIR/logs/app.log
}

update_app() {
    echo -e "${YELLOW}🔄 Actualizando desde Git (manual)...${NC}"
    cd $APP_DIR
    git pull origin main
    echo "✅ Código actualizado. Reiniciando aplicación..."
    start_app
}

auto_update_app() {
    echo -e "${YELLOW}🔄 Actualizando con script automático...${NC}"
    cd $APP_DIR
    ./auto-update.sh update
}

setup_auto_updates() {
    echo -e "${BLUE}⚙️ Configurando actualizaciones automáticas...${NC}"
    cd $APP_DIR
    ./setup-auto-update.sh
}

show_resources() {
    echo -e "${GREEN}📈 Uso de Recursos:${NC}"
    echo "Memoria:"
    free -h | grep Mem
    echo "Disco:"
    df -h / | tail -1
    echo "Procesos Python:"
    ps aux | grep python | grep -v grep | head -5
    echo ""
}

# Función principal
main() {
    while true; do
        show_menu
        read -r option
        
        case $option in
            1) clear; show_status; read -p "Enter para continuar..."; ;;
            2) clear; check_web; read -p "Enter para continuar..."; ;;
            3) clear; echo "🔍 Procesos:"; ps aux | grep -E "(python|nginx)" | grep -v grep; read -p "Enter para continuar..."; ;;
            4) clear; view_logs; ;;
            5) clear; start_app; read -p "Enter para continuar..."; ;;
            6) clear; stop_app; read -p "Enter para continuar..."; ;;
            7) clear; update_app; read -p "Enter para continuar..."; ;;
            8) clear; auto_update_app; read -p "Enter para continuar..."; ;;
            9) clear; setup_auto_updates; read -p "Enter para continuar..."; ;;
            10) clear; show_resources; read -p "Enter para continuar..."; ;;
            11) clear; echo "🧹 Limpiando logs..."; find $APP_DIR/logs -name "*.log" -mtime +7 -delete 2>/dev/null; echo "✅ Logs limpiados"; read -p "Enter para continuar..."; ;;
            12) clear; echo "🔄 Reiniciando nginx..."; sudo systemctl restart nginx; echo "✅ Nginx reiniciado"; read -p "Enter para continuar..."; ;;
            13) clear; echo "🔐 Certificados SSL:"; sudo certbot certificates; read -p "Enter para continuar..."; ;;
            14) clear; echo "🔄 Renovando SSL..."; sudo certbot renew; sudo systemctl reload nginx; echo "✅ SSL renovado"; read -p "Enter para continuar..."; ;;
            0) echo -e "${GREEN}👋 ¡Hasta luego!${NC}"; exit 0; ;;
            *) echo -e "${RED}❌ Opción inválida${NC}"; sleep 1; ;;
        esac
    done
}

main
