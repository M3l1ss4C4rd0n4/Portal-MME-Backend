#!/bin/bash
# Script para reiniciar el dashboard de forma segura

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Reiniciando Dashboard MME...${NC}"

# Obtener PIDs de Gunicorn (buscar por app:server que es más específico)
PIDS=$(pgrep -f "gunicorn.*app:server")

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}⚠️  No se encontraron procesos Gunicorn en ejecución${NC}"
else
    echo -e "${YELLOW}🛑 Deteniendo procesos Gunicorn...${NC}"
    for PID in $PIDS; do
        echo "   Matando proceso $PID"
        kill -TERM $PID 2>/dev/null
    done
    sleep 3
    
    # Verificar si aún hay procesos y forzar si es necesario
    REMAINING=$(pgrep -f "gunicorn.*app:server")
    if [ ! -z "$REMAINING" ]; then
        echo -e "${YELLOW}   Forzando detención de procesos restantes...${NC}"
        for PID in $REMAINING; do
            kill -9 $PID 2>/dev/null
        done
        sleep 2
    fi
fi

# Limpiar PID file si existe
rm -f /tmp/gunicorn_dashboard_mme.pid

# Iniciar Gunicorn
cd /home/admonctrlxm/server
echo -e "${GREEN}🚀 Iniciando Gunicorn...${NC}"
nohup gunicorn -c gunicorn_config.py app:server > /dev/null 2>&1 &

sleep 3

# Verificar
NEW_PIDS=$(pgrep -f "gunicorn.*app:server")
if [ ! -z "$NEW_PIDS" ]; then
    echo -e "${GREEN}✅ Dashboard reiniciado exitosamente${NC}"
    echo -e "${GREEN}   Procesos activos: $(echo "$NEW_PIDS" | wc -l)${NC}"
    echo -e "${GREEN}   PIDs: $(echo $NEW_PIDS | tr '\n' ' ')${NC}"
else
    echo -e "${RED}❌ Error al reiniciar el dashboard${NC}"
    echo -e "${RED}   Verificar logs en: logs/gunicorn_error.log${NC}"
    exit 1
fi
