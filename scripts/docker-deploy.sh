#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Docker Deploy Script - Portal Energético MME
# Script simplificado para deploys diarios
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Función de ayuda
show_help() {
    cat << EOF
Uso: $0 [COMANDO]

Comandos:
    up              Iniciar todos los servicios
    down            Detener todos los servicios
    restart         Reiniciar todos los servicios
    restart-api     Reiniciar solo la API
    restart-bot     Reiniciar solo el bot de Telegram
    rebuild         Reconstruir imágenes y reiniciar
    logs            Ver logs en tiempo real
    logs-api        Ver logs de la API
    logs-bot        Ver logs del bot
    status          Ver estado de los servicios
    backup          Crear backup de la base de datos
    shell-api       Abrir shell en el contenedor de API
    shell-bot       Abrir shell en el contenedor del bot
    update          Actualizar código y redeploy
    help            Mostrar esta ayuda

Ejemplos:
    $0 up           # Iniciar todo
    $0 restart-api  # Reiniciar solo API después de cambios
    $0 logs         # Ver logs en tiempo real
EOF
}

# Función para verificar que Docker está corriendo
check_docker() {
    if ! docker compose ps &> /dev/null; then
        echo -e "${RED}❌ Docker Compose no está inicializado${NC}"
        echo "Ejecuta primero: ./scripts/migrate-to-docker.sh"
        exit 1
    fi
}

# Función para esperar a que un servicio esté healthy
wait_for_healthy() {
    local service=$1
    local port=$2
    local endpoint=${3:-/health}
    
    echo "Esperando a que $service esté listo..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -s "http://localhost:${port}${endpoint}" | grep -q "healthy\|ok"; then
            echo -e "${GREEN}✅${NC} $service listo"
            return 0
        fi
        sleep 2
        ((retries--))
    done
    echo -e "${RED}❌${NC} $service no respondió a tiempo"
    return 1
}

# Parsear comando
COMMAND=${1:-up}

case $COMMAND in
    up)
        echo -e "${BLUE}🚀 Iniciando servicios...${NC}"
        docker compose up -d
        echo ""
        echo "Esperando servicios..."
        wait_for_healthy "API" "8000" "/health"
        echo ""
        docker compose ps
        echo ""
        echo -e "${GREEN}✅ Servicios iniciados:${NC}"
        echo "  API:       http://localhost:8000"
        echo "  Dashboard: http://localhost:8050"
        ;;
        
    down)
        echo -e "${YELLOW}🛑 Deteniendo servicios...${NC}"
        docker compose down
        echo -e "${GREEN}✅ Servicios detenidos${NC}"
        ;;
        
    restart)
        echo -e "${YELLOW}🔄 Reiniciando todos los servicios...${NC}"
        docker compose restart
        sleep 5
        wait_for_healthy "API" "8000" "/health"
        echo -e "${GREEN}✅ Servicios reiniciados${NC}"
        ;;
        
    restart-api)
        echo -e "${YELLOW}🔄 Reiniciando API...${NC}"
        docker compose restart api
        wait_for_healthy "API" "8000" "/health"
        echo -e "${GREEN}✅ API reiniciada${NC}"
        ;;
        
    restart-bot)
        echo -e "${YELLOW}🔄 Reiniciando Bot de Telegram...${NC}"
        docker compose restart telegram-bot
        echo -e "${GREEN}✅ Bot reiniciado${NC}"
        ;;
        
    rebuild)
        echo -e "${YELLOW}🏗️  Reconstruyendo imágenes...${NC}"
        docker compose down
        docker compose build --no-cache
        docker compose up -d
        sleep 5
        wait_for_healthy "API" "8000" "/health"
        echo -e "${GREEN}✅ Rebuild completado${NC}"
        ;;
        
    logs)
        docker compose logs -f --tail=100
        ;;
        
    logs-api)
        docker compose logs -f api --tail=100
        ;;
        
    logs-bot)
        docker compose logs -f telegram-bot --tail=100
        ;;
        
    status)
        echo -e "${BLUE}📊 Estado de servicios:${NC}"
        docker compose ps
        echo ""
        echo -e "${BLUE}Uso de recursos:${NC}"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || echo "Docker stats no disponible"
        ;;
        
    backup)
        BACKUP_FILE="./backups/db-backup-$(date +%Y%m%d-%H%M%S).sql"
        mkdir -p ./backups
        echo -e "${BLUE}💾 Creando backup de base de datos...${NC}"
        docker compose exec -T postgres pg_dump -U postgres portal_energetico > "$BACKUP_FILE"
        echo -e "${GREEN}✅ Backup creado:${NC} $BACKUP_FILE"
        ;;
        
    shell-api)
        docker compose exec api /bin/bash
        ;;
        
    shell-bot)
        docker compose exec telegram-bot /bin/bash
        ;;
        
    update)
        echo -e "${BLUE}📥 Actualizando código...${NC}"
        git pull origin main 2>/dev/null || echo "No es un repositorio git o sin cambios"
        echo -e "${YELLOW}🔄 Reconstruyendo y reiniciando...${NC}"
        docker compose build
        docker compose up -d
        sleep 5
        wait_for_healthy "API" "8000" "/health"
        echo -e "${GREEN}✅ Actualización completada${NC}"
        ;;
        
    help|--help|-h)
        show_help
        ;;
        
    *)
        echo -e "${RED}❌ Comando desconocido: $COMMAND${NC}"
        show_help
        exit 1
        ;;
esac
