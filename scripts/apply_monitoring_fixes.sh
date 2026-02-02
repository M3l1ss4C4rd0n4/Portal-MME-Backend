#!/bin/bash
# Script para aplicar las mejoras al sistema de monitoreo

echo "🔧 APLICANDO MEJORAS AL SISTEMA MME"
echo "===================================="
echo ""

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Copiar servicio template de Celery
echo -e "${YELLOW}[1/6]${NC} Configurando workers únicos de Celery..."
sudo cp /home/admonctrlxm/server/config/celery-worker@.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Detener worker antiguo
echo -e "${YELLOW}[2/6]${NC} Deteniendo worker antiguo..."
sudo systemctl stop celery-worker 2>/dev/null || true
sudo systemctl disable celery-worker 2>/dev/null || true

# 3. Habilitar nuevos workers con nombres únicos
echo -e "${YELLOW}[3/6]${NC} Habilitando 2 workers con nombres únicos..."
sudo systemctl enable celery-worker@1
sudo systemctl enable celery-worker@2

# 4. Reiniciar servicios críticos
echo -e "${YELLOW}[4/6]${NC} Reiniciando servicios..."
sudo systemctl restart celery-worker@1
sudo systemctl restart celery-worker@2
sudo systemctl restart celery-beat
sudo systemctl restart dashboard-mme
sleep 3

# 5. Verificar estado
echo -e "${YELLOW}[5/6]${NC} Verificando estado de servicios..."
echo ""

services=("redis-server" "celery-worker@1" "celery-worker@2" "celery-beat" "dashboard-mme" "prometheus")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo -e "  ${GREEN}✅${NC} $service"
    else
        echo -e "  ${RED}❌${NC} $service"
    fi
done

echo ""
echo -e "${YELLOW}[6/6]${NC} Probando endpoint de métricas..."
sleep 2

# Test endpoint /metrics
if curl -s http://localhost:8050/metrics | head -1 | grep -q "HELP"; then
    echo -e "  ${GREEN}✅${NC} Endpoint /metrics funcionando correctamente"
else
    echo -e "  ${RED}❌${NC} Endpoint /metrics no responde"
fi

# Test Prometheus targets
if curl -s http://localhost:9090/api/v1/targets 2>/dev/null | grep -q "portal_dashboard"; then
    echo -e "  ${GREEN}✅${NC} Prometheus detecta portal_dashboard"
else
    echo -e "  ${YELLOW}⚠️${NC}  Prometheus aún no detecta portal_dashboard (esperar scrape interval)"
fi

echo ""
echo "===================================="
echo -e "${GREEN}✅ MEJORAS APLICADAS${NC}"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "  1. Verificar logs: journalctl -u dashboard-mme -f"
echo "  2. Ver workers: celery -A tasks inspect stats"
echo "  3. Prometheus UI: http://localhost:9090/targets"
echo "  4. Flower: http://localhost:5555"
echo ""
