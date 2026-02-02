#!/bin/bash
# ejecutar_etl_completo.sh - Script para ejecutar ETL y cargar datos históricos

echo "════════════════════════════════════════"
echo "🚀 EJECUTANDO ETL COMPLETO"
echo "════════════════════════════════════════"
echo ""
echo "⏱️ ADVERTENCIA: Este proceso puede tomar 5-10 minutos"
echo "   Consultará datos de XM de los últimos 3-6 meses"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "etl/etl_todas_metricas_xm.py" ]; then
    echo "❌ ERROR: Debes ejecutar este script desde /home/admonctrlxm/server"
    exit 1
fi

# Verificar que Python esté disponible
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: python3 no encontrado"
    exit 1
fi

# Timestamp inicio
START_TIME=$(date +%s)
echo "📅 Inicio: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Ejecutar ETL
echo "🔄 Ejecutando ETL de todas las métricas XM..."
python3 etl/etl_todas_metricas_xm.py

ETL_EXIT_CODE=$?

# Timestamp fin
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

echo ""
echo "════════════════════════════════════════"

if [ $ETL_EXIT_CODE -eq 0 ]; then
    echo "✅ ETL COMPLETADO EXITOSAMENTE"
    echo "⏱️ Duración: ${DURATION_MIN}m ${DURATION_SEC}s"
    echo ""
    
    # Mostrar estadísticas de la BD
    if [ -f "data/metricas_xm.db" ]; then
        echo "📊 Estadísticas de la base de datos:"
        echo ""
        sqlite3 data/metricas_xm.db << 'SQL'
.mode box
SELECT 
    metrica,
    COUNT(*) as registros,
    MIN(fecha) as fecha_min,
    MAX(fecha) as fecha_max
FROM metrics 
WHERE metrica IN ('AporEner', 'Gene', 'RestAliv', 'RestSinAliv', 'VoluUtilDiarEner')
GROUP BY metrica
ORDER BY metrica;
SQL
    fi
    
    echo ""
    echo "🎉 DATOS CARGADOS CORRECTAMENTE"
    echo ""
    echo "📝 PRÓXIMOS PASOS:"
    echo "   1. Reiniciar servicios: sudo systemctl restart dashboard-mme celery-worker"
    echo "   2. Verificar dashboard: http://localhost:8050"
    echo "   3. Ejecutar validación: bash validate_fixes.sh"
    
else
    echo "❌ ETL FALLÓ (código: $ETL_EXIT_CODE)"
    echo "⏱️ Duración: ${DURATION_MIN}m ${DURATION_SEC}s"
    echo ""
    echo "🔍 Revisa los logs para más detalles:"
    echo "   tail -50 logs/app.log"
fi

echo "════════════════════════════════════════"
echo ""
