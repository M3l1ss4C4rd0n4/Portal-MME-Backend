#!/bin/bash

# Script de verificación post-ETL
# Ejecutar cuando el ETL haya completado

cd /home/admonctrlxm/server

echo "════════════════════════════════════════════════════════════"
echo "  VERIFICACIÓN POST-ETL - Portal Energético MME"
echo "════════════════════════════════════════════════════════════"
echo ""

# 1. Verificar que el ETL haya terminado
PID_FILE="/tmp/etl_pid.txt"
if [ -f "$PID_FILE" ]; then
    ETL_PID=$(cat "$PID_FILE")
    if ps -p $ETL_PID > /dev/null 2>&1; then
        echo "⚠️  ETL aún está corriendo (PID: $ETL_PID)"
        echo "   Por favor espera a que termine antes de ejecutar este script"
        exit 1
    fi
fi

echo "✅ 1. ETL completado"
echo ""

# 2. Verificar log del ETL
echo "────────────────────────────────────────────────────────────"
echo "📄 2. Verificando log del ETL"
echo "────────────────────────────────────────────────────────────"

LOG_FILE=$(ls -t logs/etl_manual_nohup_*.log 2>/dev/null | head -1)
if [ -f "$LOG_FILE" ]; then
    echo "   Log: $LOG_FILE"
    echo "   Tamaño: $(du -h "$LOG_FILE" | cut -f1)"
    
    # Buscar errores
    ERRORS=$(grep -i "error\|exception\|traceback" "$LOG_FILE" | wc -l)
    if [ $ERRORS -gt 0 ]; then
        echo "   ⚠️ Se encontraron $ERRORS errores en el log:"
        grep -i "error\|exception" "$LOG_FILE" | tail -5
    else
        echo "   ✅ Sin errores detectados"
    fi
    
    # Buscar línea de finalización
    if grep -q "completado\|finalizado" "$LOG_FILE"; then
        echo "   ✅ ETL finalizó correctamente"
    else
        echo "   ⚠️ No se encontró línea de finalización explícita"
    fi
else
    echo "   ⚠️ No se encontró archivo de log"
fi

echo ""

# 3. Verificar base de datos
echo "────────────────────────────────────────────────────────────"
echo "📊 3. Verificando base de datos"
echo "────────────────────────────────────────────────────────────"

python3 << 'PYEOF'
import sqlite3
from datetime import datetime

conn = sqlite3.connect("portal_energetico.db")
cursor = conn.cursor()

# Total de registros
cursor.execute("SELECT COUNT(*) FROM metrics")
total = cursor.fetchone()[0]
print(f"   Total registros: {total:,}")

# Fechas más recientes por métrica clave
print("\n   Fechas más recientes:")
metricas_clave = [
    'VoluUtilDiarEner',
    'AporEner',
    'AporEnerMediHist',
    'Gene',
    'CapaUtilDiarEner'
]

hoy = datetime.now().date()
for metrica in metricas_clave:
    cursor.execute("SELECT MAX(fecha) FROM metrics WHERE metrica = ?", (metrica,))
    result = cursor.fetchone()
    if result[0]:
        fecha = result[0]
        # Calcular días de antigüedad
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        dias_antiguedad = (hoy - fecha_obj).days
        
        # Emoji basado en frescura
        if dias_antiguedad == 0:
            emoji = "🟢"  # Hoy
        elif dias_antiguedad == 1:
            emoji = "🟡"  # Ayer
        elif dias_antiguedad <= 3:
            emoji = "🟠"  # 2-3 días
        else:
            emoji = "🔴"  # >3 días
        
        print(f"   {emoji} {metrica:25} → {fecha} ({dias_antiguedad} días)")

# Verificar que no haya valores astronómicos
print("\n   Verificación de integridad:")
cursor.execute("SELECT COUNT(*) FROM metrics WHERE valor > 1000000000")
valores_astronomicos = cursor.fetchone()[0]
if valores_astronomicos > 0:
    print(f"   ⚠️ {valores_astronomicos} registros con valores > 1B (potencialmente erróneos)")
else:
    print("   ✅ Sin valores astronómicos detectados")

# Verificar registros con fecha de hoy o ayer
cursor.execute("SELECT COUNT(*) FROM metrics WHERE fecha >= date('now', '-1 day')")
registros_recientes = cursor.fetchone()[0]
print(f"   ✅ {registros_recientes:,} registros de últimas 24h")

conn.close()
PYEOF

echo ""

# 4. Verificar crontab
echo "────────────────────────────────────────────────────────────"
echo "📅 4. Verificando configuración crontab"
echo "────────────────────────────────────────────────────────────"

CRON_ETL=$(crontab -l 2>/dev/null | grep "etl_xm_to_sqlite" | grep -v "^#")
if echo "$CRON_ETL" | grep -q "0 2 \* \* \*"; then
    echo "   ✅ ETL configurado para ejecución DIARIA a las 2 AM"
    echo "   $CRON_ETL"
else
    echo "   ⚠️ Configuración de crontab NO es la esperada:"
    echo "   $CRON_ETL"
fi

echo ""

# 5. Verificar servicio dashboard
echo "────────────────────────────────────────────────────────────"
echo "🌐 5. Verificando servicio dashboard"
echo "────────────────────────────────────────────────────────────"

if systemctl is-active --quiet dashboard-mme; then
    echo "   ✅ Dashboard activo"
    UPTIME=$(systemctl show dashboard-mme --property=ActiveEnterTimestamp --value)
    echo "   Última activación: $UPTIME"
else
    echo "   ⚠️ Dashboard NO está activo"
fi

echo ""

# 6. Resumen y recomendaciones
echo "════════════════════════════════════════════════════════════"
echo "📋 RESUMEN Y RECOMENDACIONES"
echo "════════════════════════════════════════════════════════════"
echo ""

# Verificar si necesita restart del dashboard
python3 << 'PYEOF'
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("portal_energetico.db")
cursor = conn.cursor()

# Verificar si tenemos datos de ayer o hoy
cursor.execute("SELECT MAX(fecha) FROM metrics WHERE metrica = 'VoluUtilDiarEner'")
ultima_fecha = cursor.fetchone()[0]

if ultima_fecha:
    fecha_obj = datetime.strptime(ultima_fecha, '%Y-%m-%d').date()
    hoy = datetime.now().date()
    ayer = hoy - timedelta(days=1)
    
    if fecha_obj >= ayer:
        print("✅ Datos actualizados (últimas 24h)")
        print("\n📌 PRÓXIMOS PASOS:")
        print("   1. Reiniciar dashboard para reflejar datos nuevos:")
        print("      sudo systemctl restart dashboard-mme")
        print("   2. Verificar dashboard web en navegador")
        print("   3. Confirmar que las fichas muestran fechas actualizadas")
        print("   4. Esperar a mañana 2 AM para primera ejecución automática")
    else:
        dias = (hoy - fecha_obj).days
        print(f"⚠️ Datos desactualizados ({dias} días)")
        print("\n📌 ACCIONES REQUERIDAS:")
        print("   1. Revisar log del ETL para errores")
        print("   2. Verificar conectividad con API de XM")
        print("   3. Considerar ejecutar ETL manualmente de nuevo")

conn.close()
PYEOF

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
