#!/bin/bash
#############################################################################
# Verificador Rápido del Sistema - Portal Energético MME
# Ejecutar después de limpieza/optimización para verificar estado
#############################################################################

echo "════════════════════════════════════════════════════════════════"
echo "  🔍 VERIFICADOR DE SISTEMA - Portal Energético MME"
echo "════════════════════════════════════════════════════════════════"
echo ""

cd /home/admonctrlxm/server

# 1. Espacio en disco
echo "💾 ESPACIO EN DISCO:"
echo "────────────────────────────────────────────"
df -h / | tail -1 | awk '{print "   Total: "$2"  |  Usado: "$3" ("$5")  |  Disponible: "$4}'
DISK_USED=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
if [ $DISK_USED -gt 80 ]; then
    echo "   ⚠️  Advertencia: Uso de disco >80%"
else
    echo "   ✅ Uso de disco OK"
fi
echo ""

# 2. Espacio del proyecto
echo "📁 TAMAÑO DEL PROYECTO:"
echo "────────────────────────────────────────────"
PROJECT_SIZE=$(du -sh . | cut -f1)
echo "   Proyecto total: $PROJECT_SIZE"

if [ -f portal_energetico.db ]; then
    DB_SIZE=$(du -h portal_energetico.db | cut -f1)
    echo "   Base de datos: $DB_SIZE"
fi

if [ -d logs ]; then
    LOGS_SIZE=$(du -sh logs | cut -f1)
    echo "   Logs: $LOGS_SIZE"
fi

if [ -d backups ]; then
    BACKUPS_SIZE=$(du -sh backups 2>/dev/null | cut -f1)
    echo "   Backups: $BACKUPS_SIZE"
fi
echo ""

# 3. Uso de RAM
echo "🧠 MEMORIA RAM:"
echo "────────────────────────────────────────────"
free -h | grep "Mem:" | awk '{print "   Total: "$2"  |  Usado: "$3"  |  Disponible: "$7}'
RAM_USED=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
if [ $RAM_USED -gt 85 ]; then
    echo "   ⚠️  Advertencia: Uso de RAM >85%"
else
    echo "   ✅ Uso de RAM OK ($RAM_USED%)"
fi
echo ""

# 4. Procesos Gunicorn
echo "🚀 PROCESOS GUNICORN:"
echo "────────────────────────────────────────────"
GUNICORN_COUNT=$(ps aux | grep -c "[g]unicorn.*app:server")
if [ $GUNICORN_COUNT -gt 0 ]; then
    echo "   ✅ Gunicorn activo: $GUNICORN_COUNT procesos"
    ps aux | grep "[g]unicorn.*app:server" | awk '{print "      PID "$2": "$11" "$12" "$13}' | head -5
else
    echo "   ⚠️  Gunicorn NO está corriendo"
fi
echo ""

# 5. Servicio systemd
echo "⚙️  SERVICIO SYSTEMD:"
echo "────────────────────────────────────────────"
if systemctl is-active --quiet dashboard-mme.service; then
    echo "   ✅ dashboard-mme.service ACTIVO"
else
    echo "   ⚠️  dashboard-mme.service INACTIVO"
fi
echo ""

# 6. Base de datos (PostgreSQL)
echo "🗄️  BASE DE DATOS (PostgreSQL):"
echo "────────────────────────────────────────────"
if psql -U postgres -d portal_energetico -c "SELECT 1;" >/dev/null 2>&1; then
    RECORDS=$(psql -U postgres -d portal_energetico -t -c "SELECT COUNT(*) FROM metrics;" 2>/dev/null | xargs)
    INDICES=$(psql -U postgres -d portal_energetico -t -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';" 2>/dev/null | xargs)
    
    echo "   Registros: $(printf "%'d" $RECORDS)"
    echo "   Índices: $INDICES"
    echo "   ✅ Conexión PostgreSQL: OK"
    
    # Fecha de últimos datos
    LAST_DATE=$(psql -U postgres -d portal_energetico -t -c "SELECT MAX(fecha) FROM metrics WHERE metrica='Gene' AND entidad='Sistema';" 2>/dev/null | xargs)
    if [ ! -z "$LAST_DATE" ]; then
        echo "   Última actualización: $LAST_DATE"
        
        # Calcular días de antigüedad
        DAYS_OLD=$(( ($(date +%s) - $(date -d "$LAST_DATE" +%s)) / 86400 ))
        if [ $DAYS_OLD -gt 3 ]; then
            echo "   ⚠️  Datos desactualizados: $DAYS_OLD días"
        else
            echo "   ✅ Datos actualizados (${DAYS_OLD} días)"
        fi
    fi
else
    echo "   ❌ No se puede conectar a PostgreSQL"
fi
echo ""

# 7. Health Check
echo "🏥 HEALTH CHECK:"
echo "────────────────────────────────────────────"
HEALTH_RESPONSE=$(curl -s http://localhost:8050/health 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "   ✅ Endpoint /health responde"
    HEALTH_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$HEALTH_STATUS" = "healthy" ]; then
        echo "   ✅ Estado: HEALTHY"
    elif [ "$HEALTH_STATUS" = "degraded" ]; then
        echo "   ⚠️  Estado: DEGRADED"
    else
        echo "   ❌ Estado: UNHEALTHY"
    fi
else
    echo "   ❌ No se puede conectar al dashboard"
fi
echo ""

# 8. Archivos cache Python
echo "🐍 CACHE PYTHON:"
echo "────────────────────────────────────────────"
PYCACHE_COUNT=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
PYC_COUNT=$(find . -name "*.pyc" 2>/dev/null | wc -l)

if [ $PYCACHE_COUNT -gt 100 ] || [ $PYC_COUNT -gt 1000 ]; then
    echo "   ⚠️  Cache acumulado:"
    echo "      __pycache__: $PYCACHE_COUNT directorios"
    echo "      .pyc files: $PYC_COUNT archivos"
    echo "   💡 Ejecutar limpieza: ./limpieza_fase1_reorganizar.sh"
else
    echo "   ✅ Cache limpio:"
    echo "      __pycache__: $PYCACHE_COUNT directorios"
    echo "      .pyc files: $PYC_COUNT archivos"
fi
echo ""

# 9. Logs
echo "📋 LOGS:"
echo "────────────────────────────────────────────"
if [ -d logs ]; then
    LOG_COUNT=$(find logs/ -name "*.log" 2>/dev/null | wc -l)
    OLD_LOGS=$(find logs/ -name "*.log" -mtime +30 2>/dev/null | wc -l)
    
    echo "   Total logs: $LOG_COUNT archivos"
    
    if [ $OLD_LOGS -gt 0 ]; then
        echo "   ⚠️  Logs antiguos (>30 días): $OLD_LOGS"
        echo "   💡 Considerar ejecutar limpieza"
    else
        echo "   ✅ Sin logs antiguos"
    fi
    
    # Último log de dashboard
    if [ -f logs/dashboard.log ]; then
        LAST_LOG_LINE=$(tail -1 logs/dashboard.log 2>/dev/null)
        if [ ! -z "$LAST_LOG_LINE" ]; then
            echo "   Último log: $(echo $LAST_LOG_LINE | cut -c1-60)..."
        fi
    fi
else
    echo "   ⚠️  Directorio logs/ no encontrado"
fi
echo ""

# 10. Estructura de carpetas
echo "📁 ESTRUCTURA:"
echo "────────────────────────────────────────────"
EXPECTED_DIRS="pages utils etl componentes assets tests scripts docs logs backups"
for dir in $EXPECTED_DIRS; do
    if [ -d "$dir" ]; then
        echo "   ✅ $dir/"
    else
        echo "   ⚠️  $dir/ (no existe)"
    fi
done
echo ""

# Resumen final
echo "════════════════════════════════════════════════════════════════"
echo "  📊 RESUMEN"
echo "════════════════════════════════════════════════════════════════"
echo ""

ISSUES=0

# Contar problemas
[ $DISK_USED -gt 80 ] && ((ISSUES++))
[ $RAM_USED -gt 85 ] && ((ISSUES++))
[ $GUNICORN_COUNT -eq 0 ] && ((ISSUES++))
[ "$INTEGRITY" != "ok" ] && ((ISSUES++))
[ $DAYS_OLD -gt 3 ] && ((ISSUES++))
[ "$HEALTH_STATUS" != "healthy" ] && ((ISSUES++))
[ $OLD_LOGS -gt 50 ] && ((ISSUES++))

if [ $ISSUES -eq 0 ]; then
    echo "   ✅ SISTEMA EN PERFECTO ESTADO"
    echo ""
    echo "   Todo funciona correctamente."
    echo "   No se requieren acciones inmediatas."
elif [ $ISSUES -le 2 ]; then
    echo "   ⚠️  SISTEMA CON ADVERTENCIAS MENORES"
    echo ""
    echo "   Se detectaron $ISSUES problemas menores."
    echo "   El sistema está operativo pero puede mejorar."
else
    echo "   ❌ SISTEMA REQUIERE ATENCIÓN"
    echo ""
    echo "   Se detectaron $ISSUES problemas."
    echo "   Se recomienda ejecutar plan de limpieza/optimización."
fi

echo ""
echo "📚 Documentación:"
echo "   • PLAN_LIMPIEZA_OPTIMIZACION.md"
echo "   • RESUMEN_EJECUTIVO_LIMPIEZA.md"
echo "   • INFORME_INSPECCION_SISTEMA_20260128.md"
echo ""
echo "🔧 Scripts disponibles:"
echo "   • ./limpieza_fase1_reorganizar.sh (limpieza rápida)"
echo "   • ./limpieza_fase2_optimizar_db.sh (optimización BD)"
echo ""
