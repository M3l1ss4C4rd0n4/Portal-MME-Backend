#!/usr/bin/env bash
# =============================================================================
# Recalcula TODOS los Excels con LibreOffice y ejecuta ETL completo
# Aplica a: presupuesto, supervision, comunidades, contratos_or
# =============================================================================
set -euo pipefail

BASE_DIR="/home/admonctrlxm/server"
LOG_FILE="${BASE_DIR}/logs/etl/dashboards_libreoffice.log"
TMP_OUT="/tmp/libreoffice_out"
TMP_PROFILE="/tmp/libreoffice_profile"

# Stubs de librerías gráficas necesarias para LibreOffice headless
export LD_LIBRARY_PATH=/tmp:${LD_LIBRARY_PATH:-}

SOFFICE="/tmp/squashfs-root/opt/libreoffice26.2/program/soffice.bin"

# Lista de Excels a recalcular: (nombre descriptivo | ruta relativa)
declare -a EXCELS=(
    "presupuesto|data/ejecucion_presupuestal/Acuerdos de Gestión DEE 2026.xlsx"
    "supervision|data/base_de_datos_supervision/Matriz General de Reparto.xlsx"
    "comunidades|data/base_de_datos_comunidades_energeticas/Resumen_Implementación.xlsx"
    "contratos_or|data/base_de_datos_contratos_or/Seguimiento Completo_CE_Contratos.xlsx"
    "subsidios|data/onedrive/2026-02-17 Info Subs y Cont - Info tablero (1).xlsx"
)

mkdir -p "${TMP_OUT}" "${BASE_DIR}/logs/etl"
TS=$(date '+%Y-%m-%d %H:%M:%S')

echo "[${TS}] ============================================" >> "${LOG_FILE}"
echo "[${TS}] Iniciando recálculo de todos los dashboards" >> "${LOG_FILE}"

# ─── Verificar LibreOffice ─────────────────────────────────────────────────
if [[ ! -x "${SOFFICE}" ]]; then
    echo "[${TS}] ERROR: LibreOffice no encontrado en ${SOFFICE}" >> "${LOG_FILE}"
    exit 1
fi

# ─── 1. Recalcular cada Excel ──────────────────────────────────────────────
for item in "${EXCELS[@]}"; do
    IFS='|' read -r name path <<< "$item"
    excel_path="${BASE_DIR}/${path}"
    
    if [[ ! -f "${excel_path}" ]]; then
        echo "[${TS}] ⚠️  ${name}: No existe ${excel_path}, se omite" >> "${LOG_FILE}"
        continue
    fi
    
    echo "[${TS}] 📊 Recalculando ${name}: ${path}" >> "${LOG_FILE}"
    
    # Limpiar salida anterior
    excel_basename=$(basename "${excel_path}")
    rm -f "${TMP_OUT}/${excel_basename}"
    
    # Recalcular con LibreOffice
    "${SOFFICE}" \
        --headless \
        -env:UserInstallation=file://${TMP_PROFILE} \
        --calc \
        --convert-to xlsx:"Calc MS Excel 2007 XML" \
        "${excel_path}" \
        --outdir "${TMP_OUT}/" \
        >> "${LOG_FILE}" 2>&1
    
    if [[ -f "${TMP_OUT}/${excel_basename}" ]]; then
        # Backup
        backup_name="${excel_basename}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "${excel_path}" "$(dirname "${excel_path}")/${backup_name}"
        
        # Reemplazar
        cp "${TMP_OUT}/${excel_basename}" "${excel_path}"
        rm -f "${TMP_OUT}/${excel_basename}"
        rm -f "$(dirname "${excel_path}")/${backup_name}"
        
        echo "[${TS}] ✅ ${name}: recalculado y reemplazado" >> "${LOG_FILE}"
    else
        echo "[${TS}] ⚠️  ${name}: LibreOffice no generó salida, se conserva el original" >> "${LOG_FILE}"
    fi
done

# ─── 2. Ejecutar ETL completo (todos los schemas) ──────────────────────────
echo "[${TS}] 🗄️  Ejecutando ETL completo..." >> "${LOG_FILE}"

cd "${BASE_DIR}"
source venv/bin/activate
python etl/etl_nuevos_dashboards.py >> "${LOG_FILE}" 2>&1

ETL_STATUS=$?
if [[ ${ETL_STATUS} -eq 0 ]]; then
    echo "[${TS}] ✅ ETL completado exitosamente (todos los schemas)" >> "${LOG_FILE}"
else
    echo "[${TS}] ❌ ETL falló con código ${ETL_STATUS}" >> "${LOG_FILE}"
    exit 1
fi

echo "[${TS}] Proceso completado. Portal actualizado." >> "${LOG_FILE}"
echo "[${TS}] ============================================" >> "${LOG_FILE}"
