#!/bin/bash
# Script para configurar cron jobs de ETL
# Ejecuta los ETLs automáticamente cada día

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
# Detectar python environment
if [ -f "$SERVER_DIR/siea/venv/bin/python" ]; then
    PYTHON_BIN="$SERVER_DIR/siea/venv/bin/python"
else
    PYTHON_BIN="/usr/bin/python3"  # Fallback a sistema
fi

echo "=============================================="
echo "Configuración de ETL Automático"
echo "Usando Python: $PYTHON_BIN"
echo "=============================================="
echo ""

# Crear directorio de logs si no existe
mkdir -p "$SERVER_DIR/logs/etl"

# Definir cron jobs
CRON_METRICS="0 6 * * * cd $SERVER_DIR && $PYTHON_BIN etl/etl_xm_to_sqlite.py >> $SERVER_DIR/logs/etl/metrics.log 2>&1"
CRON_TRANSMISSION="30 6 * * * cd $SERVER_DIR && $PYTHON_BIN etl/etl_transmision.py --days 7 --clean >> $SERVER_DIR/logs/etl/transmision.log 2>&1"
CRON_DISTRIBUTION="0 7 * * * cd $SERVER_DIR && $PYTHON_BIN etl/etl_distribucion.py >> $SERVER_DIR/logs/etl/distribucion.log 2>&1"
CRON_COMMERCIAL="30 7 * * * cd $SERVER_DIR && $PYTHON_BIN etl/etl_comercializacion.py >> $SERVER_DIR/logs/etl/comercializacion.log 2>&1"

# Obtener crontab actual
TEMP_CRON=$(mktemp)
crontab -l > "$TEMP_CRON" 2>/dev/null || true

# Helper function
add_cron_if_missing() {
    local JOB="$1"
    local SCRIPT_NAME="$2"
    local DESC="$3"
    
    if grep -q "$SCRIPT_NAME" "$TEMP_CRON"; then
        echo "⚠️  $DESC ya está configurado"
    else
        echo "$JOB" >> "$TEMP_CRON"
        echo "✅ Agregado $DESC"
    fi
}

add_cron_if_missing "$CRON_METRICS" "etl/etl_xm_to_sqlite.py" "ETL de métricas (6:00 AM)"
add_cron_if_missing "$CRON_TRANSMISSION" "etl/etl_transmision.py" "ETL de transmisión (6:30 AM)"
add_cron_if_missing "$CRON_DISTRIBUTION" "etl/etl_distribucion.py" "ETL de distribución (7:00 AM)"
add_cron_if_missing "$CRON_COMMERCIAL" "etl/etl_comercializacion.py" "ETL de comercialización (7:30 AM)"

# Instalar nuevo crontab
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

echo ""
echo "=============================================="
echo "Cron Jobs Activos:"
echo "=============================================="
crontab -l | grep "etl/"

echo ""
echo "=============================================="
echo "Instalación completada correctamente."
echo "=============================================="
