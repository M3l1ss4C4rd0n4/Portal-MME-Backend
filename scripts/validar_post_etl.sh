#!/bin/bash
#
# ╔══════════════════════════════════════════════════════════════╗
# ║           CRON: VALIDACIÓN POST-ETL AUTOMÁTICA               ║
# ║                                                              ║
# ║  Ejecuta validación 15 minutos después de cada ETL           ║
# ║  ETL corre: 06:30, 12:30, 20:30                             ║
# ║  Validación corre: 06:45, 12:45, 20:45                      ║
# ╚══════════════════════════════════════════════════════════════╝

cd /home/admonctrlxm/server

echo "════════════════════════════════════════════════════════════"
echo "🔍 VALIDACIÓN POST-ETL - $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════"

# 1. Auto-corrección (dry-run primero para ver qué haría)
echo ""
echo "🔧 Ejecutando auto-corrección..."
python3 scripts/autocorreccion.py --dry-run 2>&1 | tee logs/autocorreccion_dryrun_$(date +%Y%m%d_%H%M%S).log

# Si hay correcciones pendientes, ejecutar en modo real
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Auto-corrección completada (dry-run)"
    
    # Preguntar si hay correcciones necesarias (en logs)
    CORRECCIONES=$(grep -E "Total de correcciones: [1-9]" logs/autocorreccion_dryrun_*.log | tail -1)
    
    if [ ! -z "$CORRECCIONES" ]; then
        echo "⚠️  Hay correcciones pendientes, ejecutando en modo real..."
        python3 scripts/autocorreccion.py 2>&1 | tee logs/autocorreccion_$(date +%Y%m%d_%H%M%S).log
    fi
else
    echo "❌ Error en auto-corrección"
fi

# 2. Validación contra API
echo ""
echo "🌐 Validando contra API XM..."
python3 scripts/validar_etl.py 2>&1 | tee logs/validacion_$(date +%Y%m%d_%H%M%S).log

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Validación exitosa"
else
    echo ""
    echo "❌ Validación falló - revisar logs"
    
    # TODO: Enviar alerta por email/Slack
    # echo "ALERTA: Validación ETL falló en $(date)" | mail -s "⚠️ Alerta Dashboard MME" admin@ejemplo.com
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ Validación completada - $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════"
