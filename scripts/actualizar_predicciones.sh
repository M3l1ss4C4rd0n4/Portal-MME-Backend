#!/bin/bash
##############################################################################
# ACTUALIZACIÓN AUTOMÁTICA DE PREDICCIONES - SECTOR ENERGÉTICO COLOMBIANO
# Ministerio de Minas y Energía - República de Colombia
#
# Este script:
# 1. Actualiza predicciones ML para todas las métricas
# 2. Monitorea calidad ex-post de predicciones (FASE 5.A)
# 3. Ejecuta sistema de alertas
# 4. Genera reportes para Viceministro
# 5. Envía notificaciones si hay alertas críticas
#
# Frecuencia recomendada: Semanal (domingo 2:00 AM)
# Duración estimada: 20-30 minutos
##############################################################################

set -e  # Exit on error

# Configuración
SCRIPT_DIR="/home/admonctrlxm/server"
VENV_PYTHON="$SCRIPT_DIR/whatsapp_bot/venv/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/actualizacion_predicciones_$TIMESTAMP.log"

# Crear directorio de logs si no existe
mkdir -p "$LOG_DIR"

# Función para logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Función para manejar errores
handle_error() {
    log "❌ ERROR: $1"
    log "   Ver detalles en: $LOG_FILE"
    exit 1
}

##############################################################################
# INICIO DEL PROCESO
##############################################################################

log "================================================================================================"
log "🇨🇴 ACTUALIZACIÓN AUTOMÁTICA DE PREDICCIONES - SECTOR ENERGÉTICO"
log "   Ministerio de Minas y Energía - República de Colombia"
log "================================================================================================"

##############################################################################
# PASO 1: VERIFICAR ENTORNO
##############################################################################

log ""
log "📋 PASO 1: Verificando entorno..."

# Verificar que existe el entorno virtual
if [ ! -f "$VENV_PYTHON" ]; then
    handle_error "No se encuentra Python del entorno virtual en: $VENV_PYTHON"
fi

# Verificar conexión a base de datos
log "   → Verificando conexión a PostgreSQL..."
if ! $VENV_PYTHON -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from infrastructure.database.connection import PostgreSQLConnectionManager
manager = PostgreSQLConnectionManager()
import psycopg2
conn_params = {
    'host': manager.host,
    'port': manager.port,
    'database': manager.database,
    'user': manager.user
}
if manager.password:
    conn_params['password'] = manager.password
conn = psycopg2.connect(**conn_params)
conn.close()
print('✅ Conexión exitosa')
" >> "$LOG_FILE" 2>&1; then
    handle_error "No se pudo conectar a PostgreSQL"
fi

log "   ✅ Entorno verificado correctamente"

##############################################################################
# PASO 1.5: ETL IDEAM — Datos meteorológicos (FASE 18)
#   • Fuente: datos.gov.co (Socrata SODA API) — IDEAM Colombia
#   • Variables: velocidad_viento, precipitación, temperatura
#   • Ejecuta ANTES de predicciones para tener datos frescos
#   • Si falla: predicciones usan datos IDEAM existentes (o sin ellos)
##############################################################################

log ""
log "🌍 PASO 1.5: ETL IDEAM — Datos meteorológicos (velocidad viento, precipitación, temperatura)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/etl/etl_ideam.py" --dias 14 --timeout 90 >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ ETL IDEAM completado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  ETL IDEAM falló (${DURATION}s) — Predicciones continuarán con datos existentes"
fi

##############################################################################
# PASO 2: ACTUALIZAR PREDICCIONES DE GENERACIÓN
##############################################################################

log ""
log "🔋 PASO 2: Actualizando predicciones de GENERACIÓN por fuentes..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_postgres.py" >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ Predicciones de generación actualizadas (${DURATION}s)"
else
    handle_error "Falló actualización de predicciones de generación"
fi

##############################################################################
# PASO 3: ACTUALIZAR PREDICCIONES SECTORIALES
##############################################################################

log ""
log "📊 PASO 3: Actualizando predicciones SECTORIALES (demanda, precios, hidrología)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ Predicciones sectoriales actualizadas (${DURATION}s)"
else
    handle_error "Falló actualización de predicciones sectoriales"
fi

##############################################################################
# PASO 3.5: HORIZONTE DUAL — LightGBM + TCN (FASE 8)
#   • Ejecuta DESPUÉS del ensemble (PASO 3)
#   • DEMANDA: reemplaza ensemble con LightGBM(1-7d) + TCN(8-90d)
#   • Si falla: las predicciones ensemble de PASO 3 permanecen intactas
#   • Quality gate: MAPE > 50% descarta automáticamente
##############################################################################

log ""
log "🧠 PASO 3.5: Horizonte Dual — LightGBM + TCN (FASE 8) para DEMANDA..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" --horizonte_dual DEMANDA >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ Horizonte Dual (DEMANDA) actualizado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  Horizonte Dual falló (${DURATION}s) — Predicciones ensemble de PASO 3 se mantienen"
fi

##############################################################################
# PASO 3.6: LGBM DIRECTO — APORTES_HIDRICOS (FASE 11)
#   • Ejecuta DESPUÉS del ensemble (PASO 3) y horizonte dual (PASO 3.5)
#   • APORTES_HIDRICOS: reemplaza ensemble (16.78% MAPE) con LGBM directo (~11-13%)
#   • Si falla: las predicciones ensemble de PASO 3 permanecen intactas
#   • Quality gate: MAPE > 30% genera advertencia
##############################################################################

log ""
log "🌿 PASO 3.6: LightGBM directo — APORTES_HIDRICOS (FASE 11)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" --lgbm_aportes >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ LightGBM directo (APORTES_HIDRICOS) actualizado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  LightGBM APORTES falló (${DURATION}s) — Predicciones ensemble de PASO 3 se mantienen"
fi

##############################################################################
# PASO 3.7: LGBM DIRECTO — TÉRMICA (FASE 12)
#   • Ejecuta DESPUÉS de APORTES LGBM (PASO 3.6)
#   • Térmica: reemplaza ensemble (16.81% MAPE) con LGBM directo (~11-13%)
#   • Usa regresores: embalses_pct, demanda_gwh, aportes_gwh (correlación inversa)
#   • Si falla: las predicciones ensemble de PASO 2 permanecen intactas
#   • Quality gate: MAPE > 30% genera advertencia
##############################################################################

log ""
log "🔥 PASO 3.7: LightGBM directo — Térmica (FASE 12)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" --lgbm_termica >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ LightGBM directo (Térmica) actualizado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  LightGBM Térmica falló (${DURATION}s) — Predicciones ensemble de PASO 2 se mantienen"
fi

##############################################################################
# PASO 3.8: LGBM DIRECTO — SOLAR (FASE 13)
#   • Ejecuta DESPUÉS de Térmica LGBM (PASO 3.7)
#   • Solar: reemplaza ensemble (19.76% MAPE) con LGBM directo (~13-16%)
#   • Usa regresores XM: IrrGlobal, TempAmbSolar, embalses, demanda
#   • Si falla: las predicciones ensemble de PASO 2 permanecen intactas
##############################################################################

log ""
log "☀️ PASO 3.8: LightGBM directo — Solar (FASE 13)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" --lgbm_solar >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ LightGBM directo (Solar) actualizado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  LightGBM Solar falló (${DURATION}s) — Predicciones ensemble de PASO 2 se mantienen"
fi

##############################################################################
# PASO 3.9: LGBM DIRECTO — EÓLICA (FASE 13 + FASE 18 IDEAM)
#   • Ejecuta DESPUÉS de Solar LGBM (PASO 3.8)
#   • Eólica: LGBM directo con viento IDEAM La Guajira como regresor
#   • FASE 18: velocidad_viento IDEAM integrada → mejora esperada vs baseline
#   • Si falla: las predicciones ensemble de PASO 2 permanecen intactas
##############################################################################

log ""
log "💨 PASO 3.9: LightGBM directo — Eólica (FASE 13)..."

START_TIME=$(date +%s)

if $VENV_PYTHON "$SCRIPT_DIR/scripts/train_predictions_sector_energetico.py" --lgbm_eolica >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ✅ LightGBM directo (Eólica) actualizado (${DURATION}s)"
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "   ⚠️  LightGBM Eólica falló (${DURATION}s) — Predicciones ensemble de PASO 2 se mantienen"
fi

##############################################################################
# PASO 4: MONITOREO EX-POST DE PREDICCIONES (FASE 5.A)
##############################################################################

log ""
log "📈 PASO 4: Ejecutando monitoreo ex-post de calidad de predicciones..."

START_TIME=$(date +%s)

MONITOR_OUTPUT=$($VENV_PYTHON "$SCRIPT_DIR/scripts/monitor_predictions_quality.py" 2>&1) || true

# Extraer resumen del monitor
echo "$MONITOR_OUTPUT" >> "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Contar alertas del monitor (buscar líneas de alerta en el output)
MONITOR_CRITICOS=$(echo "$MONITOR_OUTPUT" | grep -c "🔴" || true)
MONITOR_DRIFTS=$(echo "$MONITOR_OUTPUT" | grep -c "🟡 DRIFT" || true)
MONITOR_OK=$(echo "$MONITOR_OUTPUT" | grep -c "✅ OK" || true)

if [ "$MONITOR_CRITICOS" -gt 0 ]; then
    log "   🔴 CRÍTICO: $MONITOR_CRITICOS fuentes con MAPE ex-post > 50%"
fi
if [ "$MONITOR_DRIFTS" -gt 0 ]; then
    log "   🟡 DRIFT: $MONITOR_DRIFTS fuentes con degradación > 2× MAPE entrenamiento"
fi
log "   ✅ Monitoreo completado (${DURATION}s): $MONITOR_OK fuentes OK, $MONITOR_CRITICOS críticas, $MONITOR_DRIFTS drift"

# Guardar contadores para resumen final
MONITOR_TOTAL_ALERTAS=$((MONITOR_CRITICOS + MONITOR_DRIFTS))

##############################################################################
# PASO 5: EJECUTAR SISTEMA DE ALERTAS
##############################################################################

log ""
log "🚨 PASO 5: Ejecutando sistema de alertas automáticas..."

if $VENV_PYTHON "$SCRIPT_DIR/scripts/alertas_energeticas.py" >> "$LOG_FILE" 2>&1; then
    log "   ✅ Sistema de alertas ejecutado"
    
    # Verificar si hay alertas críticas
    ALERTAS_JSON="$LOG_DIR/alertas_energeticas.json"
    if [ -f "$ALERTAS_JSON" ]; then
        ALERTAS_CRITICAS=$($VENV_PYTHON -c "
import json
with open('$ALERTAS_JSON', 'r') as f:
    data = json.load(f)
print(data['alertas_criticas'])
" 2>/dev/null || echo "0")
        
        if [ "$ALERTAS_CRITICAS" -gt 0 ]; then
            log "   🚨 ATENCIÓN: $ALERTAS_CRITICAS alertas críticas detectadas"
            log "   📄 Ver detalles en: $ALERTAS_JSON"
        else
            log "   ✅ No hay alertas críticas"
        fi
    fi
else
    log "   ⚠️  Sistema de alertas falló (no crítico)"
fi

##############################################################################
# PASO 6: VERIFICAR INTEGRIDAD DE PREDICCIONES
##############################################################################

log ""
log "🔍 PASO 6: Verificando integridad de predicciones..."

TOTAL_PREDICCIONES=$($VENV_PYTHON -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import psycopg2
from infrastructure.database.connection import PostgreSQLConnectionManager

manager = PostgreSQLConnectionManager()
conn_params = {
    'host': manager.host,
    'port': manager.port,
    'database': manager.database,
    'user': manager.user
}
if manager.password:
    conn_params['password'] = manager.password

conn = psycopg2.connect(**conn_params)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM predictions')
total = cur.fetchone()[0]
print(total)
cur.close()
conn.close()
" 2>/dev/null || echo "0")

if [ "$TOTAL_PREDICCIONES" -ge 800 ]; then
    log "   ✅ Integridad verificada: $TOTAL_PREDICCIONES predicciones en BD"
else
    log "   ⚠️  ADVERTENCIA: Solo $TOTAL_PREDICCIONES predicciones (esperado: ~900)"
fi

##############################################################################
# PASO 7: LIMPIAR LOGS ANTIGUOS
##############################################################################

log ""
log "🗑️  PASO 7: Limpiando logs antiguos (>30 días)..."

# Mantener logs de últimos 30 días
find "$LOG_DIR" -name "actualizacion_predicciones_*.log" -mtime +30 -delete 2>/dev/null || true
find "$LOG_DIR" -name "predictions_*.log" -mtime +30 -delete 2>/dev/null || true

LOGS_RESTANTES=$(find "$LOG_DIR" -name "*.log" | wc -l)
log "   ✅ Limpieza completada ($LOGS_RESTANTES logs activos)"

##############################################################################
# RESUMEN FINAL
##############################################################################

log ""
log "================================================================================================"
log "✅ ACTUALIZACIÓN COMPLETADA EXITOSAMENTE"
log "================================================================================================"
log ""
log "📊 Resumen:"
log "   • Predicciones totales: $TOTAL_PREDICCIONES"
log "   • Monitoreo ex-post: ${MONITOR_OK:-0} OK, ${MONITOR_CRITICOS:-0} críticas, ${MONITOR_DRIFTS:-0} drift"
log "   • Alertas críticas operacionales: ${ALERTAS_CRITICAS:-0}"
log "   • Log completo: $LOG_FILE"
log "   • Alertas JSON: $ALERTAS_JSON"
log ""
log "🎯 Próxima actualización: $(date -d '+7 days' '+%Y-%m-%d %H:%M')"
log "================================================================================================"

# Retornar código de éxito
exit 0
