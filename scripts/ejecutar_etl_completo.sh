#!/bin/bash
# Script para ejecutar ETL de todas las secciones en segundo plano
# Guarda logs en logs/etl_completo.log

LOG_FILE="/home/admonctrlxm/server/logs/etl_todas_metricas.log"
SCRIPT_DIR="/home/admonctrlxm/server"

echo "========================================" >> $LOG_FILE
echo "ETL COMPLETO - Inicio: $(date)" >> $LOG_FILE
echo "========================================" >> $LOG_FILE

cd $SCRIPT_DIR

# Lista de secciones a procesar
SECCIONES=("Generación" "Demanda" "Transmisión" "Restricciones" "Precios" "Transacciones" "Pérdidas" "Intercambios" "Hidrología" "Combustibles" "Renovables" "Cargos")

for SECCION in "${SECCIONES[@]}"; do
    echo "" >> $LOG_FILE
    echo "▶ Procesando sección: $SECCION" >> $LOG_FILE
    echo "  Inicio: $(date)" >> $LOG_FILE
    
    python3 etl/etl_todas_metricas_xm.py --seccion "$SECCION" --dias 90 --solo-nuevas >> $LOG_FILE 2>&1
    
    EXIT_CODE=$?
    echo "  Fin: $(date) | Exit code: $EXIT_CODE" >> $LOG_FILE
    
    # Pausa entre secciones
    sleep 5
done

echo "" >> $LOG_FILE
echo "========================================" >> $LOG_FILE
echo "ETL COMPLETO - Fin: $(date)" >> $LOG_FILE
echo "========================================" >> $LOG_FILE

# Mostrar resumen
echo ""
echo "✅ ETL completo finalizado"
echo "📄 Ver log completo: $LOG_FILE"
echo ""
echo "📊 Últimas líneas del log:"
tail -30 $LOG_FILE
