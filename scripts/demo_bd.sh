#!/bin/bash
################################################################################
# DEMOSTRACIÓN VISUAL - Base de Datos PostgreSQL
# Portal Energético MME
################################################################################
# Este script muestra ejemplos prácticos de consultas a la base de datos
################################################################################

cd /home/admonctrlxm/server

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║             🎬 DEMOSTRACIÓN: Base de Datos PostgreSQL - MME                  ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Función para pausar
pause() {
    echo ""
    read -p "⏸️  Presiona ENTER para continuar..." dummy
    echo ""
}

# DEMO 1: Listado de tablas
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 DEMO 1: Listado de Tablas con Tamaños"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import list_tables
list_tables()
"
pause

# DEMO 2: Estructura de tabla
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 DEMO 2: Estructura de la Tabla 'metrics'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import table_info
table_info('metrics')
"
pause

# DEMO 3: Datos recientes
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 DEMO 3: Últimos 10 Registros de la Base de Datos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import execute_query
execute_query('''
SELECT 
    fecha,
    metrica,
    entidad,
    recurso,
    ROUND(valor_gwh::numeric, 2) as valor_gwh
FROM metrics
ORDER BY fecha DESC
LIMIT 10;
''')
"
pause

# DEMO 4: Estadísticas generales
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 DEMO 4: Estadísticas Generales de la Base de Datos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import execute_query
execute_query('''
SELECT 
    \"Total Métricas Únicas\" as indicador,
    COUNT(DISTINCT metrica)::text as valor
FROM metrics
UNION ALL
SELECT 
    \"Total Recursos Únicos\",
    COUNT(DISTINCT recurso)::text
FROM metrics
UNION ALL
SELECT 
    \"Total Días con Datos\",
    COUNT(DISTINCT fecha)::text
FROM metrics
UNION ALL
SELECT 
    \"Último Dato Actualizado\",
    MAX(fecha_actualizacion)::text
FROM metrics;
''')
"
pause

# DEMO 5: Métricas más populares
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 DEMO 5: Top 10 Métricas Más Populares"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import execute_query
execute_query('''
SELECT 
    metrica,
    COUNT(*) as total_registros,
    COUNT(DISTINCT recurso) as recursos_unicos,
    MIN(fecha)::date as fecha_inicio,
    MAX(fecha)::date as fecha_fin
FROM metrics
GROUP BY metrica
ORDER BY total_registros DESC
LIMIT 10;
''')
"
pause

# DEMO 6: Datos horarios recientes
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏰ DEMO 6: Últimos 15 Registros Horarios"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import execute_query
execute_query('''
SELECT 
    fecha::date as fecha,
    hora,
    metrica,
    recurso,
    ROUND(valor_mwh::numeric, 2) as valor_mwh
FROM metrics_hourly
ORDER BY fecha DESC, hora DESC
LIMIT 15;
''')
"
pause

# DEMO 7: Líneas de transmisión
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔌 DEMO 7: Información de Líneas de Transmisión"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.db_explorer import preview_data
preview_data('lineas_transmision', 5)
"
pause

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                        ✅ DEMOSTRACIÓN COMPLETADA                            ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📚 Para acceso interactivo completo, ejecuta:"
echo "   👉 bash scripts/ver_bd.sh"
echo ""
echo "📖 Para más información, consulta:"
echo "   👉 docs/TUTORIAL_RAPIDO_POSTGRESQL.md"
echo "   👉 docs/GUIA_ACCESO_POSTGRESQL.md"
echo ""
