#!/bin/bash
# Script de verificación del estado del sistema ETL
# Muestra información sobre los cron jobs, última ejecución y estado de la base de datos

SERVER_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
DB_PATH="$SERVER_DIR/portal_energetico.db"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        ESTADO DEL SISTEMA ETL AUTOMATIZADO                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 1. Verificar cron jobs
echo "📅 CRON JOBS CONFIGURADOS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
crontab -l 2>/dev/null | grep -E "(etl_xm_to_sqlite|etl_transmision)" | while read line; do
    if [[ $line == *"etl_xm_to_sqlite"* ]]; then
        echo "✅ ETL Métricas:     $line"
    elif [[ $line == *"etl_transmision"* ]]; then
        echo "✅ ETL Transmisión:  $line"
    fi
done
echo ""

# 2. Estado de la base de datos
echo "💾 ESTADO DE LA BASE DE DATOS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Transmisión
TRANS_DATA=$(sqlite3 "$DB_PATH" "SELECT COUNT(DISTINCT codigo_linea), MAX(fecha_registro), COUNT(*) FROM lineas_transmision;" 2>/dev/null)
if [ ! -z "$TRANS_DATA" ]; then
    IFS='|' read -r lineas fecha registros <<< "$TRANS_DATA"
    if [ "$lineas" != "0" ]; then
        echo "✅ Transmisión:      $lineas líneas únicas | Última fecha: $fecha | Total registros: $registros"
    else
        echo "⚠️  Transmisión:      Sin datos"
    fi
else
    echo "❌ Transmisión:      Error consultando DB"
fi

# Métricas
METRICS_DATA=$(sqlite3 "$DB_PATH" "SELECT COUNT(*), MAX(fecha), COUNT(DISTINCT metrica) FROM metrics;" 2>/dev/null)
if [ ! -z "$METRICS_DATA" ]; then
    IFS='|' read -r registros fecha metricas <<< "$METRICS_DATA"
    if [ "$registros" != "0" ]; then
        echo "✅ Métricas:         $metricas métricas | Última fecha: $fecha | Total registros: $registros"
    else
        echo "⚠️  Métricas:         Sin datos"
    fi
else
    echo "❌ Métricas:         Error consultando DB"
fi
echo ""

# 3. Logs recientes
echo "📋 LOGS RECIENTES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Log de transmisión
TRANS_LOG="$SERVER_DIR/logs/etl/transmision.log"
if [ -f "$TRANS_LOG" ]; then
    LAST_RUN=$(tail -20 "$TRANS_LOG" | grep "Fin:" | tail -1 | awk '{print $2, $3}')
    if [ ! -z "$LAST_RUN" ]; then
        echo "✅ ETL Transmisión:  Última ejecución: $LAST_RUN"
    else
        echo "⚠️  ETL Transmisión:  Log existe pero sin fecha de ejecución"
    fi
    
    # Verificar errores
    ERRORS=$(tail -50 "$TRANS_LOG" | grep -c "Error\|❌")
    if [ "$ERRORS" -gt 0 ]; then
        echo "   ⚠️  $ERRORS errores encontrados en últimas 50 líneas"
    fi
else
    echo "⚠️  ETL Transmisión:  Log no encontrado"
fi

# Log de métricas (último archivo)
LATEST_METRICS_LOG=$(ls -t "$SERVER_DIR/logs/etl_diario_"*.log 2>/dev/null | head -1)
if [ -f "$LATEST_METRICS_LOG" ]; then
    LOG_DATE=$(basename "$LATEST_METRICS_LOG" | sed 's/etl_diario_\(.*\)\.log/\1/')
    LOG_SIZE=$(du -h "$LATEST_METRICS_LOG" | awk '{print $1}')
    echo "✅ ETL Métricas:     Último log: $LOG_DATE (${LOG_SIZE})"
else
    echo "⚠️  ETL Métricas:     Log no encontrado"
fi
echo ""

# 4. Próxima ejecución
echo "⏰ PRÓXIMA EJECUCIÓN:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CURRENT_TIME=$(date +"%H:%M")
CURRENT_DATE=$(date +"%Y-%m-%d")

# Calcular próxima ejecución de métricas (2:00 AM)
if [[ "$CURRENT_TIME" < "02:00" ]]; then
    echo "📊 ETL Métricas:     Hoy a las 02:00 AM"
else
    NEXT_DAY=$(date -d "tomorrow" +"%Y-%m-%d")
    echo "📊 ETL Métricas:     $NEXT_DAY a las 02:00 AM"
fi

# Calcular próxima ejecución de transmisión (6:30 AM)
if [[ "$CURRENT_TIME" < "06:30" ]]; then
    echo "🔌 ETL Transmisión:  Hoy a las 06:30 AM"
else
    NEXT_DAY=$(date -d "tomorrow" +"%Y-%m-%d")
    echo "🔌 ETL Transmisión:  $NEXT_DAY a las 06:30 AM"
fi
echo ""

# 5. Comandos útiles
echo "🔧 COMANDOS ÚTILES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Ver logs en tiempo real:"
echo "  tail -f $TRANS_LOG"
echo ""
echo "Ejecutar ETL manualmente:"
echo "  $SERVER_DIR/siea/venv/bin/python $SERVER_DIR/etl/etl_transmision.py --days 7 --clean"
echo ""
echo "Ver todos los cron jobs:"
echo "  crontab -l"
echo ""
echo "╚════════════════════════════════════════════════════════════╝"
