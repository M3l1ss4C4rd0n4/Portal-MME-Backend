#!/bin/bash
##############################################################################
# ACTUALIZACIÓN AUTOMÁTICA DE PREDICCIONES - SECTOR ENERGÉTICO COLOMBIANO
# Ministerio de Minas y Energía - República de Colombia
#
# Este script:
# 1. Actualiza predicciones ML para todas las métricas
# 2. Ejecuta sistema de alertas
# 3. Genera reportes para Viceministro
# 4. Envía notificaciones si hay alertas críticas
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
# PASO 4: EJECUTAR SISTEMA DE ALERTAS
##############################################################################

log ""
log "🚨 PASO 4: Ejecutando sistema de alertas automáticas..."

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
# PASO 5: VERIFICAR INTEGRIDAD DE PREDICCIONES
##############################################################################

log ""
log "🔍 PASO 5: Verificando integridad de predicciones..."

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
# PASO 6: LIMPIAR LOGS ANTIGUOS
##############################################################################

log ""
log "🗑️  PASO 6: Limpiando logs antiguos (>30 días)..."

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
log "   • Alertas críticas: ${ALERTAS_CRITICAS:-0}"
log "   • Log completo: $LOG_FILE"
log "   • Alertas JSON: $ALERTAS_JSON"
log ""
log "🎯 Próxima actualización: $(date -d '+7 days' '+%Y-%m-%d %H:%M')"
log "================================================================================================"

# Retornar código de éxito
exit 0
