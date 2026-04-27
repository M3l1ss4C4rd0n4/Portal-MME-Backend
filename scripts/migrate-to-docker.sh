#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Script de Migración: Systemd → Docker Compose
# Portal Energético MME
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "  🐳 MIGRACIÓN: Systemd → Docker Compose"
echo "  Portal Energético MME"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 1. PRE-CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

echo "🔍 Paso 1/6: Verificando requisitos..."

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker no está instalado${NC}"
    echo "Instala Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Verificar Docker Compose
if ! docker compose version &> /dev/null && ! docker-compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose no está instalado${NC}"
    exit 1
fi

echo -e "${GREEN}✅${NC} Docker y Docker Compose instalados"

# Verificar que estamos en el directorio correcto
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ No se encontró docker-compose.yml${NC}"
    echo "Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

echo -e "${GREEN}✅${NC} Estructura de proyecto correcta"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 2. BACKUP DE DATOS EXISTENTES
# ═══════════════════════════════════════════════════════════════════════════════

echo "💾 Paso 2/6: Creando backup de datos..."

BACKUP_DIR="./backups/docker-migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup de la base de datos si existe
if command -v pg_dump &> /dev/null; then
    echo "  Creando backup de PostgreSQL..."
    pg_dump -h localhost -U postgres portal_energetico > "$BACKUP_DIR/database.sql" 2>/dev/null || echo "  ⚠️  No se pudo hacer backup de BD (¿está corriendo?)"
fi

# Backup de configuraciones
echo "  Guardando configuraciones actuales..."
cp .env "$BACKUP_DIR/.env.backup" 2>/dev/null || true
cp whatsapp_bot/.env "$BACKUP_DIR/.env.telegram.backup" 2>/dev/null || true

# Backup de logs
echo "  Guardando logs..."
cp -r logs "$BACKUP_DIR/logs-backup" 2>/dev/null || true

echo -e "${GREEN}✅${NC} Backup creado en: $BACKUP_DIR"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 3. DETENER SERVICIOS SYSTEMD
# ═══════════════════════════════════════════════════════════════════════════════

echo "🛑 Paso 3/6: Deteniendo servicios Systemd..."

SERVICIOS=(
    "telegram-polling.service"
    "celery-beat.service"
    "celery-worker.service"
    "celery-flower.service"
    "dashboard-mme.service"
    "api-mme.service"
)

for servicio in "${SERVICIOS[@]}"; do
    if systemctl is-active "$servicio" &> /dev/null; then
        echo "  Deteniendo $servicio..."
        sudo systemctl stop "$servicio" 2>/dev/null || true
        sudo systemctl disable "$servicio" 2>/dev/null || true
    else
        echo "  $servicio no está activo"
    fi
done

# Matar procesos huérfanos si existen
echo "  Limpiando procesos huérfanos..."
pkill -f "gunicorn.*api.main" 2>/dev/null || true
pkill -f "telegram_polling.py" 2>/dev/null || true
pkill -f "celery.*worker" 2>/dev/null || true
pkill -f "celery.*beat" 2>/dev/null || true

echo -e "${GREEN}✅${NC} Servicios Systemd detenidos"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONFIGURAR ENTORNO DOCKER
# ═══════════════════════════════════════════════════════════════════════════════

echo "⚙️  Paso 4/6: Configurando entorno Docker..."

# Crear .env si no existe
if [ ! -f ".env" ]; then
    if [ -f ".env.docker" ]; then
        echo "  Creando .env desde .env.docker..."
        cp .env.docker .env
        echo -e "${YELLOW}⚠️  IMPORTANTE: Revisa y actualiza el archivo .env${NC}"
        echo "     Especialmente las contraseñas y tokens sensibles"
    else
        echo -e "${RED}❌ No se encontró .env.docker${NC}"
        exit 1
    fi
else
    echo "  El archivo .env ya existe, preservando..."
    echo -e "${YELLOW}⚠️  Asegúrate de que las variables de Docker estén configuradas:${NC}"
    echo "     - POSTGRES_HOST=postgres (no localhost)"
    echo "     - REDIS_HOST=redis (no localhost)"
fi

# Crear directorios necesarios
echo "  Creando estructura de directorios..."
mkdir -p logs/{api,dashboard,celery,telegram}
mkdir -p data
mkdir -p whatsapp_bot/informes

echo -e "${GREEN}✅${NC} Entorno configurado"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 5. CONSTRUIR E INICIAR CONTENEDORES
# ═══════════════════════════════════════════════════════════════════════════════

echo "🏗️  Paso 5/6: Construyendo e iniciando contenedores..."

# Verificar si hay una BD existente que migrar
if [ -f "$BACKUP_DIR/database.sql" ]; then
    echo -e "${YELLOW}⚠️  Se detectó backup de base de datos${NC}"
    read -p "¿Quieres restaurar la BD desde el backup? (s/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        echo "  La BD se restaurará después de iniciar PostgreSQL"
        RESTORE_DB=true
    fi
fi

# Construir imágenes
echo "  Construyendo imágenes Docker..."
docker compose build --no-cache

# Iniciar infraestructura primero
echo "  Iniciando PostgreSQL y Redis..."
docker compose up -d postgres redis

# Esperar a que PostgreSQL esté listo
echo "  Esperando a que PostgreSQL esté listo..."
sleep 10
until docker compose exec -T postgres pg_isready -U postgres; do
    echo "  Esperando PostgreSQL..."
    sleep 2
done

# Restaurar BD si es necesario
if [ "$RESTORE_DB" = true ]; then
    echo "  Restaurando base de datos desde backup..."
    docker compose exec -T postgres psql -U postgres -d portal_energetico < "$BACKUP_DIR/database.sql" || echo "  ⚠️  Error al restaurar BD"
fi

# Iniciar resto de servicios
echo "  Iniciando aplicaciones..."
docker compose up -d api dashboard telegram-bot celery-worker celery-beat

echo -e "${GREEN}✅${NC} Contenedores iniciados"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 6. VERIFICACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

echo "🔍 Paso 6/6: Verificando servicios..."

sleep 5

# Verificar API
if curl -s http://localhost:8000/health | grep -q '"status":"healthy"'; then
    echo -e "${GREEN}✅${NC} API REST: http://localhost:8000"
else
    echo -e "${RED}❌${NC} API REST no responde"
fi

# Verificar Dashboard
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8050 | grep -q "200\|302"; then
    echo -e "${GREEN}✅${NC} Dashboard: http://localhost:8050"
else
    echo -e "${YELLOW}⚠️${NC} Dashboard puede estar iniciando..."
fi

# Verificar contenedores
echo ""
echo "Estado de contenedores:"
docker compose ps

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ MIGRACIÓN COMPLETADA${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "📋 Resumen:"
echo "  • Backup guardado en: $BACKUP_DIR"
echo "  • Servicios Systemd detenidos y deshabilitados"
echo "  • Contenedores Docker ejecutándose"
echo ""
echo "🚀 Comandos útiles:"
echo "  docker compose logs -f          # Ver logs en tiempo real"
echo "  docker compose ps               # Ver estado de contenedores"
echo "  docker compose restart api      # Reiniciar solo la API"
echo "  docker compose down             # Detener todos los servicios"
echo "  docker compose up -d            # Iniciar todos los servicios"
echo ""
echo "📚 Documentación:"
echo "  docker/README.md"
echo ""
