#!/bin/bash

# Script de monitoreo del ETL en ejecución
# Uso: ./monitorear_etl.sh

cd /home/admonctrlxm/server

PID_FILE="/tmp/etl_pid.txt"
LOG_FILE=$(ls -t logs/etl_manual_nohup_*.log 2>/dev/null | head -1)

echo "════════════════════════════════════════════════════════════"
echo "  MONITOREO ETL - Portal Energético MME"
echo "════════════════════════════════════════════════════════════"
echo ""

# Verificar si existe PID
if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  No se encontró archivo PID"
    echo "   El ETL podría no estar corriendo o no se guardó el PID"
    exit 1
fi

ETL_PID=$(cat "$PID_FILE")

# Verificar si el proceso está corriendo
if ps -p $ETL_PID > /dev/null 2>&1; then
    echo "✅ ETL CORRIENDO"
    echo "   PID: $ETL_PID"
    
    # Tiempo de ejecución
    START_TIME=$(ps -o lstart= -p $ETL_PID)
    echo "   Inicio: $START_TIME"
    
    # Uso de CPU y memoria
    CPU_MEM=$(ps -o %cpu,%mem,rss -p $ETL_PID | tail -1)
    echo "   Recursos: $CPU_MEM (CPU%, MEM%, RSS KB)"
    
else
    echo "✅ ETL COMPLETADO (o terminó con error)"
    echo "   PID $ETL_PID ya no está activo"
fi

echo ""
echo "────────────────────────────────────────────────────────────"
echo "📄 ARCHIVO LOG"
echo "────────────────────────────────────────────────────────────"

if [ -f "$LOG_FILE" ]; then
    echo "   Archivo: $LOG_FILE"
    echo "   Tamaño: $(du -h "$LOG_FILE" | cut -f1)"
    echo "   Líneas: $(wc -l < "$LOG_FILE")"
    echo ""
    
    # Buscar línea de finalización
    if grep -q "completado\|finalizado\|ETL COMPLETO" "$LOG_FILE"; then
        echo "✅ ETL FINALIZÓ EXITOSAMENTE"
        echo ""
        echo "📊 Resumen:"
        grep -A5 "completado\|finalizado\|Total de métricas" "$LOG_FILE" | tail -10
    else
        echo "🔄 ETL EN PROGRESO..."
        echo ""
        echo "📝 Últimas 20 líneas:"
        tail -20 "$LOG_FILE"
    fi
else
    echo "⚠️  No se encontró archivo de log"
fi

echo ""
echo "────────────────────────────────────────────────────────────"
echo "📊 ESTADO DE LA BASE DE DATOS (PostgreSQL)"
echo "────────────────────────────────────────────────────────────"

# Tamaño de la BD PostgreSQL
DB_SIZE=$(psql -U postgres -d portal_energetico -t -c "SELECT pg_size_pretty(pg_database_size('portal_energetico'));" 2>/dev/null | xargs)
echo "   Tamaño PostgreSQL: ${DB_SIZE:-N/A}"

# Verificar fechas más recientes via psql
python3 << 'PYEOF'
import psycopg2, os
try:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "portal_energetico"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    cursor = conn.cursor()
    metricas = ['VoluUtilDiarEner', 'AporEner', 'Gene', 'CapaUtilDiarEner']
    print("\n   Fechas más recientes:")
    for metrica in metricas:
        cursor.execute("SELECT MAX(fecha) FROM metrics WHERE metrica = %s", (metrica,))
        result = cursor.fetchone()
        if result and result[0]:
            print(f"   • {metrica:20} → {result[0]}")
    cursor.execute("SELECT COUNT(*) FROM metrics")
    total = cursor.fetchone()[0]
    print(f"\n   Total registros: {total:,}")
    conn.close()
except Exception as e:
    print(f"   ❌ Error conectando a PostgreSQL: {e}")
PYEOF

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Si el proceso sigue corriendo, ofrecer seguir monitoreando
if ps -p $ETL_PID > /dev/null 2>&1; then
    echo "💡 El ETL sigue corriendo. Opciones:"
    echo "   1. Ejecutar nuevamente este script: ./monitorear_etl.sh"
    echo "   2. Ver log en tiempo real: tail -f $LOG_FILE"
    echo "   3. Esperar a que termine (puede tardar 15-30 minutos)"
fi

echo ""
