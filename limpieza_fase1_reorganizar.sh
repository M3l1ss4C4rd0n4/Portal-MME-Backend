#!/bin/bash
#############################################################################
# Script de Limpieza Fase 1 - Portal Energético MME
# Descripción: Limpieza inmediata de archivos innecesarios y reorganización
# Tiempo estimado: 30 minutos
# Espacio a liberar: ~6 GB
#############################################################################

set -e  # Exit on error

cd /home/admonctrlxm/server

echo "════════════════════════════════════════════════════════════════"
echo "  🧹 LIMPIEZA FASE 1 - Portal Energético MME"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "⚠️  ADVERTENCIA: Este script reorganizará archivos."
echo "   Se recomienda hacer un backup antes de continuar."
echo ""
read -p "¿Desea continuar? (s/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "❌ Cancelado por el usuario"
    exit 1
fi

# Crear carpetas de organización
echo ""
echo "📁 Creando estructura de carpetas..."
mkdir -p backups/database
mkdir -p docs/analisis_historicos
mkdir -p docs/informes_mensuales
mkdir -p docs/referencias
mkdir -p docs/tecnicos
mkdir -p scripts/analisis_historico
mkdir -p scripts/utilidades
mkdir -p tests/verificaciones
mkdir -p logs/archived
echo "✅ Carpetas creadas"

# Mover backup gigante (5.8 GB)
echo ""
echo "📦 Moviendo backup antiguo (5.8 GB)..."
if [ -f "backup_antes_correccion_hidrologia_20251217_055200.db" ]; then
    mv backup_antes_correccion_hidrologia_20251217_055200.db backups/database/
    echo "✅ Backup movido a backups/database/"
else
    echo "⚠️  Archivo de backup no encontrado (ya movido?)"
fi

# Eliminar archivos innecesarios
echo ""
echo "🗑️  Eliminando archivos innecesarios..."
rm -f sqlite3_3.45.1-1ubuntu2.5_amd64.deb && echo "   ✓ sqlite3 .deb eliminado"

# Mover documentación de análisis
echo ""
echo "📝 Organizando documentación de análisis..."
for file in ANALISIS_*.md CORRECCION_*.md INFORME_INSPECCION_ETL_DB.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/analisis_historicos/
        echo "   ✓ $file → docs/analisis_historicos/"
    fi
done

# Mover informes mensuales
echo ""
echo "📊 Organizando informes mensuales..."
if [ -f "INFORME_DICIEMBRE_2025.md" ]; then
    mv INFORME_DICIEMBRE_2025.md docs/informes_mensuales/
    echo "   ✓ INFORME_DICIEMBRE_2025.md → docs/informes_mensuales/"
fi
if [ -f "INFORME_INSPECCION_SISTEMA_20260128.md" ]; then
    mv INFORME_INSPECCION_SISTEMA_20260128.md docs/informes_mensuales/
    echo "   ✓ INFORME_INSPECCION_SISTEMA_20260128.md → docs/informes_mensuales/"
fi

# Mover documentación técnica
echo ""
echo "📚 Organizando documentación técnica..."
if [ -f "DOCUMENTACION_TECNICA_IA_ML.md" ]; then
    mv DOCUMENTACION_TECNICA_IA_ML.md docs/tecnicos/
    echo "   ✓ DOCUMENTACION_TECNICA_IA_ML.md → docs/tecnicos/"
fi

# Mover referencias externas
echo ""
echo "📖 Moviendo referencias externas..."
if [ -f "E-2010-006481 convenio utp-creg 02 Informe final tomo 1 R1.pdf" ]; then
    mv "E-2010-006481 convenio utp-creg 02 Informe final tomo 1 R1.pdf" docs/referencias/
    echo "   ✓ PDF movido a docs/referencias/"
fi

# Mover scripts de análisis one-time
echo ""
echo "🔧 Organizando scripts de análisis..."
for file in analizar_metricas_sospechosas.py inspeccionar_etl_completo.py inspeccionar_etl_db.py; do
    if [ -f "$file" ]; then
        mv "$file" scripts/analisis_historico/
        echo "   ✓ $file → scripts/analisis_historico/"
    fi
done

# Mover resultados de análisis
echo ""
echo "📄 Moviendo resultados de análisis..."
for file in analisis_metricas_sospechosas.txt inspeccion_resultado.txt; do
    if [ -f "$file" ]; then
        mv "$file" docs/analisis_historicos/
        echo "   ✓ $file → docs/analisis_historicos/"
    fi
done

# Mover archivos de prueba y verificación
echo ""
echo "🧪 Organizando tests y verificaciones..."
if [ -f "test_chatbot_store.py" ]; then
    mv test_chatbot_store.py tests/verificaciones/
    echo "   ✓ test_chatbot_store.py → tests/verificaciones/"
fi
if [ -f "verificar_chatbot.py" ]; then
    mv verificar_chatbot.py tests/verificaciones/
    echo "   ✓ verificar_chatbot.py → tests/verificaciones/"
fi
if [ -f "check_database.py" ]; then
    mv check_database.py scripts/utilidades/
    echo "   ✓ check_database.py → scripts/utilidades/"
fi
if [ -f "pages/comercializacion_test.py" ]; then
    mv pages/comercializacion_test.py tests/
    echo "   ✓ comercializacion_test.py → tests/"
fi

# Limpiar cache Python
echo ""
echo "🐍 Limpiando cache Python..."
PYCACHE_COUNT=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
PYC_COUNT=$(find . -name "*.pyc" 2>/dev/null | wc -l)
echo "   📊 Encontrados: $PYCACHE_COUNT directorios __pycache__, $PYC_COUNT archivos .pyc"

find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

echo "   ✅ Cache Python eliminado"

# Limpiar logs antiguos (>30 días)
echo ""
echo "📋 Limpiando logs antiguos (>30 días)..."
OLD_LOGS=$(find logs/ -name "*.log" -mtime +30 2>/dev/null | wc -l)
echo "   📊 Logs antiguos encontrados: $OLD_LOGS"

if [ $OLD_LOGS -gt 0 ]; then
    find logs/ -name "*.log" -mtime +30 -delete
    echo "   ✅ Logs antiguos eliminados"
else
    echo "   ℹ️  No hay logs > 30 días para eliminar"
fi

# Comprimir logs antiguos (7-30 días)
echo ""
echo "📦 Comprimiendo logs antiguos (7-30 días)..."
COMPRESS_LOGS=$(find logs/ -name "*.log" -mtime +7 -mtime -30 2>/dev/null | wc -l)
echo "   📊 Logs a comprimir: $COMPRESS_LOGS"

if [ $COMPRESS_LOGS -gt 0 ]; then
    find logs/ -name "*.log" -mtime +7 -mtime -30 -exec gzip {} \;
    echo "   ✅ Logs comprimidos con gzip"
else
    echo "   ℹ️  No hay logs para comprimir"
fi

# Agregar entradas a .gitignore si no existen
echo ""
echo "📝 Actualizando .gitignore..."
touch .gitignore

grep -qxF "__pycache__/" .gitignore || echo "__pycache__/" >> .gitignore
grep -qxF "*.pyc" .gitignore || echo "*.pyc" >> .gitignore
grep -qxF "*.pyo" .gitignore || echo "*.pyo" >> .gitignore
grep -qxF "*.log" .gitignore || echo "*.log" >> .gitignore
grep -qxF "logs/*.log" .gitignore || echo "logs/*.log" >> .gitignore
grep -qxF "backups/" .gitignore || echo "backups/" >> .gitignore
grep -qxF "venv/" .gitignore || echo "venv/" >> .gitignore
grep -qxF ".env" .gitignore || echo ".env" >> .gitignore

echo "✅ .gitignore actualizado"

# Resumen final
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ✅ FASE 1 COMPLETADA"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📊 Resumen de limpieza:"
echo "   • Backup movido: 5.8 GB"
echo "   • Archivos organizados: ~25 archivos"
echo "   • Cache Python eliminado: ~11,850 archivos"
echo "   • Logs antiguos limpiados: $OLD_LOGS archivos"
echo "   • Logs comprimidos: $COMPRESS_LOGS archivos"
echo ""
echo "💾 Espacio estimado liberado: ~6 GB"
echo ""
echo "📁 Nueva estructura:"
echo "   backups/database/          - Backups de BD"
echo "   docs/analisis_historicos/  - Análisis pasados"
echo "   docs/informes_mensuales/   - Informes periódicos"
echo "   docs/tecnicos/             - Documentación técnica"
echo "   docs/referencias/          - Referencias externas"
echo "   scripts/analisis_historico/- Scripts one-time"
echo "   scripts/utilidades/        - Scripts de utilidad"
echo "   tests/verificaciones/      - Tests y verificaciones"
echo ""
echo "🎯 Próximo paso: Ejecutar FASE 2 (Optimización BD)"
echo "   ./limpieza_fase2_optimizar_db.sh"
echo ""
