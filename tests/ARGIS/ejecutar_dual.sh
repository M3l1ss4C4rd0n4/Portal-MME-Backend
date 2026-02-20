#!/bin/bash
# ============================================================================
# ejecutar_dual.sh — Ejecuta scripts de actualización ArcGIS para DOS cuentas
# ============================================================================
#
# Uso:
#   ./ejecutar_dual.sh xm          # Solo datos XM (ambas cuentas)
#   ./ejecutar_dual.sh onedrive    # Solo datos OneDrive (ambas cuentas)
#   ./ejecutar_dual.sh todo        # XM + OneDrive (ambas cuentas)
#
# Cuentas:
#   1. Vice_Energia  (.env)
#   2. Adminportal   (.env.adminportal)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/logs"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Asegurar que existe el directorio de logs
mkdir -p "$LOG_DIR"

log() {
    echo "[$TIMESTAMP] $1"
}

# --- Función: Ejecutar script XM para una cuenta ---
run_xm() {
    local env_file="$1"
    local account_name="$2"
    local log_file="$LOG_DIR/actualizacion_xm_arcgis_${account_name}.log"

    log "🔄 XM → $account_name (env: $env_file)"
    python3 "$SCRIPT_DIR/actualizar_datos_xm_online.py" --env-file "$env_file" \
        >> "$log_file" 2>&1 || {
        log "⚠️  XM → $account_name falló (ver $log_file)"
    }
    log "✅ XM → $account_name completado"
}

# --- Función: Ejecutar script OneDrive para una cuenta ---
run_onedrive() {
    local env_file="$1"
    local config_file="$2"
    local account_name="$3"
    local log_file="$LOG_DIR/actualizacion_onedrive_arcgis_${account_name}.log"

    log "🔄 OneDrive → $account_name (env: $env_file, config: $config_file)"
    python3 "$SCRIPT_DIR/actualizar_desde_onedrive.py" \
        --env-file "$env_file" \
        --config-file "$config_file" \
        >> "$log_file" 2>&1 || {
        log "⚠️  OneDrive → $account_name falló (ver $log_file)"
    }
    log "✅ OneDrive → $account_name completado"
}

# --- Principal ---
MODE="${1:-todo}"

case "$MODE" in
    xm)
        log "========== ACTUALIZACIÓN XM (dual) =========="
        run_xm ".env" "vice_energia"
        run_xm ".env.adminportal" "adminportal"
        ;;
    onedrive)
        log "========== ACTUALIZACIÓN ONEDRIVE (dual) =========="
        run_onedrive ".env" "onedrive_archivos.json" "vice_energia"
        run_onedrive ".env.adminportal" "onedrive_archivos_adminportal.json" "adminportal"
        ;;
    todo)
        log "========== ACTUALIZACIÓN COMPLETA (dual) =========="
        run_xm ".env" "vice_energia"
        run_xm ".env.adminportal" "adminportal"
        run_onedrive ".env" "onedrive_archivos.json" "vice_energia"
        run_onedrive ".env.adminportal" "onedrive_archivos_adminportal.json" "adminportal"
        ;;
    *)
        echo "Uso: $0 {xm|onedrive|todo}"
        exit 1
        ;;
esac

log "========== PROCESO DUAL FINALIZADO =========="
