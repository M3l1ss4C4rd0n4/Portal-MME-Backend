#!/bin/bash
#
# Script ETL para actualizar predicciones diarias
# Ejecuta entrenamiento de modelos ML y guarda predicciones en BD
# 
# Cron sugerido: 0 2 * * * /home/admonctrlxm/server/scripts/etl_predictions.sh >> /home/admonctrlxm/server/logs/etl_predictions.log 2>&1

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/siea/venv/bin/python"
TRAINING_SCRIPT="$SCRIPT_DIR/train_predictions.py"
LOG_DIR="$PROJECT_DIR/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Crear directorio de logs si no existe
mkdir -p "$LOG_DIR"

echo "===================================================================================================="
echo "🚀 ETL PREDICCIONES - Inicio: $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================================================================="

# PASO 1: Validar predicciones anteriores vs datos reales
echo ""
echo "📊 PASO 1: Validando predicciones anteriores..."
"$VENV_PYTHON" "$SCRIPT_DIR/validate_predictions.py"
VALIDATION_EXIT=$?

if [ $VALIDATION_EXIT -ne 0 ]; then
    echo "⚠️  Advertencia: Validación falló (código $VALIDATION_EXIT), continuando con entrenamiento..."
fi

# Verificar que el script de entrenamiento existe
if [ ! -f "$TRAINING_SCRIPT" ]; then
    echo "❌ Error: No se encontró el script de entrenamiento en $TRAINING_SCRIPT"
    exit 1
fi

# Verificar que el intérprete de Python existe
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: No se encontró el intérprete de Python en $VENV_PYTHON"
    exit 1
fi

# PASO 2: Ejecutar entrenamiento
echo ""
echo "🤖 PASO 2: Entrenando modelos ML..."
cd "$PROJECT_DIR"

"$VENV_PYTHON" "$TRAINING_SCRIPT"
EXIT_CODE=$?

echo ""
echo "===================================================================================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ ETL PREDICCIONES - Completado exitosamente: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "❌ ETL PREDICCIONES - Falló con código $EXIT_CODE: $(date '+%Y-%m-%d %H:%M:%S')"
fi
echo "===================================================================================================="

exit $EXIT_CODE
