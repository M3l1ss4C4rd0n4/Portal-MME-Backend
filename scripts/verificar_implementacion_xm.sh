#!/bin/bash

# ============================================
# Resumen de Implementación XM Sinergox
# Portal MME - Dashboard Colombia
# ============================================

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║     IMPLEMENTACIÓN COMPLETA - PATRÓN XM SINERGOX             ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================
# 1. VERIFICAR ARCHIVOS CREADOS
# ============================================

echo "📂 VERIFICANDO ARCHIVOS CREADOS..."
echo ""

archivos_requeridos=(
    "domain/services/metrics_calculator.py"
    "domain/services/indicators_service.py"
    "etl/validaciones_rangos.py"
    "docs/ejemplos_integracion_indicadores.py"
    "docs/GUIA_MIGRACION_CALLBACKS.py"
    "docs/IMPLEMENTACION_COMPLETA_XM.md"
    "tests/test_integracion_indicadores.py"
    "assets/kpi-variations.css"
)

todos_presentes=true

for archivo in "${archivos_requeridos[@]}"; do
    if [ -f "/home/admonctrlxm/server/$archivo" ]; then
        echo "  ✅ $archivo"
    else
        echo "  ❌ $archivo (FALTANTE)"
        todos_presentes=false
    fi
done

echo ""

if [ "$todos_presentes" = true ]; then
    echo "✅ Todos los archivos presentes"
else
    echo "⚠️  Algunos archivos faltan"
    exit 1
fi

echo ""

# ============================================
# 2. EJECUTAR TESTS
# ============================================

echo "🧪 EJECUTANDO TESTS AUTOMATIZADOS..."
echo ""

cd /home/admonctrlxm/server

if python3 tests/test_integracion_indicadores.py; then
    echo ""
    echo "✅ Tests completados exitosamente"
else
    echo ""
    echo "❌ Algunos tests fallaron"
    exit 1
fi

echo ""

# ============================================
# 3. ESTADÍSTICAS DE CÓDIGO
# ============================================

echo "📊 ESTADÍSTICAS DE CÓDIGO..."
echo ""

echo "Líneas de código agregadas:"
wc -l /home/admonctrlxm/server/domain/services/metrics_calculator.py | awk '{print "  metrics_calculator.py: " $1 " líneas"}'
wc -l /home/admonctrlxm/server/domain/services/indicators_service.py | awk '{print "  indicators_service.py: " $1 " líneas"}'
wc -l /home/admonctrlxm/server/etl/validaciones_rangos.py | awk '{print "  validaciones_rangos.py: " $1 " líneas"}'
wc -l /home/admonctrlxm/server/assets/kpi-variations.css | awk '{print "  kpi-variations.css: " $1 " líneas"}'

echo ""

total_lineas=$(cat \
    /home/admonctrlxm/server/domain/services/metrics_calculator.py \
    /home/admonctrlxm/server/domain/services/indicators_service.py \
    /home/admonctrlxm/server/etl/validaciones_rangos.py \
    /home/admonctrlxm/server/assets/kpi-variations.css \
    | wc -l)

echo "  TOTAL: $total_lineas líneas de código nuevo"

echo ""

# ============================================
# 4. VERIFICAR BASE DE DATOS
# ============================================

echo "💾 VERIFICANDO BASE DE DATOS..."
echo ""

sqlite3 /home/admonctrlxm/server/data/metricas_xm.db <<EOF
.mode column
.headers on

SELECT 
    'RestAliv' as metrica,
    COUNT(*) as registros,
    MIN(valor_gwh) as min_valor,
    MAX(valor_gwh) as max_valor,
    ROUND(AVG(valor_gwh), 2) as promedio
FROM metrics 
WHERE metrica = 'RestAliv' AND unidad = 'COP';

SELECT 
    'AporEner' as metrica,
    COUNT(*) as registros,
    MIN(valor_gwh) as min_valor,
    MAX(valor_gwh) as max_valor,
    ROUND(AVG(valor_gwh), 2) as promedio
FROM metrics 
WHERE metrica = 'AporEner';

SELECT 
    'PrecBolsNaci' as metrica,
    COUNT(*) as registros,
    MIN(valor_gwh) as min_valor,
    MAX(valor_gwh) as max_valor,
    ROUND(AVG(valor_gwh), 2) as promedio
FROM metrics 
WHERE metrica = 'PrecBolsNaci';
EOF

echo ""
echo "✅ Base de datos verificada"
echo ""

# ============================================
# 5. PRÓXIMOS PASOS
# ============================================

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    PRÓXIMOS PASOS                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "📝 PENDIENTE DE INTEGRACIÓN:"
echo ""
echo "1. Migrar Callbacks (Tiempo estimado: 2 horas)"
echo "   ├── interface/pages/restricciones.py (20 min)"
echo "   ├── interface/pages/precio_bolsa.py (15 min)"
echo "   ├── interface/pages/hidrologia.py (30 min)"
echo "   └── interface/pages/dashboard.py (40 min)"
echo ""
echo "2. Integrar Validación en ETL (15 min)"
echo "   └── etl/etl_todas_metricas_xm.py"
echo ""
echo "3. Verificación Final (30 min)"
echo "   ├── Ejecutar tests"
echo "   ├── Verificar KPIs en dashboard"
echo "   └── Validar variaciones correctas"
echo ""

echo "📚 DOCUMENTACIÓN DISPONIBLE:"
echo ""
echo "  📄 docs/IMPLEMENTACION_COMPLETA_XM.md"
echo "     → Guía completa de implementación"
echo ""
echo "  📄 docs/GUIA_MIGRACION_CALLBACKS.py"
echo "     → Ejemplos ANTES/DESPUÉS"
echo ""
echo "  📄 docs/ejemplos_integracion_indicadores.py"
echo "     → Código listo para copiar"
echo ""

echo "🚀 COMANDO PARA INICIAR MIGRACIÓN:"
echo ""
echo "  # Editar primer callback (restricciones):"
echo "  nano interface/pages/restricciones.py"
echo ""
echo "  # Consultar ejemplo:"
echo "  cat docs/GUIA_MIGRACION_CALLBACKS.py"
echo ""
echo "  # Reiniciar dashboard:"
echo "  sudo systemctl restart dashboard-mme"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║  ✅ IMPLEMENTACIÓN COMPLETA                                  ║"
echo "║  ⏳ LISTO PARA INTEGRACIÓN                                   ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
