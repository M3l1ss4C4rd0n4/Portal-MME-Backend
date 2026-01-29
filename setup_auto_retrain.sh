#!/bin/bash
# Script para configurar reentrenamiento automático semanal

echo "📋 Configurando reentrenamiento automático de predicciones..."

# Crear log directory si no existe
mkdir -p /home/admonctrlxm/server/logs

# Agregar tarea cron (cada lunes a las 3 AM)
(crontab -l 2>/dev/null | grep -v "train_predictions"; echo "0 3 * * 1 cd /home/admonctrlxm/server && source siea/venv/bin/activate && python3 scripts/train_predictions.py >> logs/predictions_training.log 2>&1") | crontab -

echo "✅ Configuración completada"
echo ""
echo "📅 El modelo se reentrenará automáticamente:"
echo "   - Cada LUNES a las 3:00 AM"
echo "   - Logs en: /home/admonctrlxm/server/logs/predictions_training.log"
echo ""
echo "🔧 Para entrenar ahora manualmente:"
echo "   python3 /home/admonctrlxm/server/scripts/train_predictions.py"
