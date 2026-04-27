#!/usr/bin/env bash
# =============================================================================
# Recalcula el Excel de ejecución presupuestal con LibreOffice y actualiza la BD
# =============================================================================
set -euo pipefail

BASE_DIR="/home/admonctrlxm/server"
EXCEL_DIR="${BASE_DIR}/data/ejecucion_presupuestal"
EXCEL_NAME="Acuerdos de Gestión DEE 2026.xlsx"
EXCEL_PATH="${EXCEL_DIR}/${EXCEL_NAME}"
TMP_OUT="/tmp/libreoffice_out"
TMP_PROFILE="/tmp/libreoffice_profile"
LOG_FILE="${BASE_DIR}/logs/etl/presupuesto_libreoffice.log"

# Crear directorios necesarios
mkdir -p "${TMP_OUT}" "${BASE_DIR}/logs/etl"

# Stubs de librerías gráficas necesarias para LibreOffice headless
export LD_LIBRARY_PATH=/tmp:${LD_LIBRARY_PATH:-}

# Timestamp para logs
TS=$(date '+%Y-%m-%d %H:%M:%S')

echo "[${TS}] ============================================" >> "${LOG_FILE}"
echo "[${TS}] Iniciando recálculo presupuesto con LibreOffice" >> "${LOG_FILE}"

# ─── 1. Verificar que el Excel existe ──────────────────────────────────────
if [[ ! -f "${EXCEL_PATH}" ]]; then
    echo "[${TS}] ERROR: No existe ${EXCEL_PATH}" >> "${LOG_FILE}"
    exit 1
fi

# ─── 2. Recalcular con LibreOffice ─────────────────────────────────────────
echo "[${TS}] Recalculando Excel con LibreOffice..." >> "${LOG_FILE}"

SOFFICE="/tmp/squashfs-root/opt/libreoffice26.2/program/soffice.bin"

if [[ ! -x "${SOFFICE}" ]]; then
    echo "[${TS}] ERROR: LibreOffice no encontrado en ${SOFFICE}" >> "${LOG_FILE}"
    exit 1
fi

# Limpiar salida anterior
rm -f "${TMP_OUT}/${EXCEL_NAME}"

"${SOFFICE}" \
    --headless \
    -env:UserInstallation=file://${TMP_PROFILE} \
    --calc \
    --convert-to xlsx:"Calc MS Excel 2007 XML" \
    "${EXCEL_PATH}" \
    --outdir "${TMP_OUT}/" \
    >> "${LOG_FILE}" 2>&1

if [[ ! -f "${TMP_OUT}/${EXCEL_NAME}" ]]; then
    echo "[${TS}] ERROR: LibreOffice no generó el archivo recalculado" >> "${LOG_FILE}"
    exit 1
fi

echo "[${TS}] Excel recalculado OK (${TMP_OUT}/${EXCEL_NAME})" >> "${LOG_FILE}"

# ─── 3. Backup del Excel original ──────────────────────────────────────────
BACKUP_NAME="${EXCEL_NAME}.backup.$(date +%Y%m%d_%H%M%S)"
cp "${EXCEL_PATH}" "${EXCEL_DIR}/${BACKUP_NAME}"
echo "[${TS}] Backup creado: ${BACKUP_NAME}" >> "${LOG_FILE}"

# ─── 4. Reemplazar Excel original con el recalculado ───────────────────────
cp "${TMP_OUT}/${EXCEL_NAME}" "${EXCEL_PATH}"
echo "[${TS}] Excel original reemplazado con versión recalculada" >> "${LOG_FILE}"

# ─── 5. Ejecutar ETL ───────────────────────────────────────────────────────
echo "[${TS}] Ejecutando ETL presupuesto..." >> "${LOG_FILE}"

cd "${BASE_DIR}"
source venv/bin/activate
python etl/etl_nuevos_dashboards.py --schema presupuesto >> "${LOG_FILE}" 2>&1

ETL_STATUS=$?
if [[ ${ETL_STATUS} -eq 0 ]]; then
    echo "[${TS}] ✅ ETL completado exitosamente" >> "${LOG_FILE}"
else
    echo "[${TS}] ❌ ETL falló con código ${ETL_STATUS}" >> "${LOG_FILE}"
    # Restaurar backup
    cp "${EXCEL_DIR}/${BACKUP_NAME}" "${EXCEL_PATH}"
    echo "[${TS}] Excel original restaurado desde backup" >> "${LOG_FILE}"
    exit 1
fi

# ─── 6. Limpiar archivos temporales ────────────────────────────────────────
rm -f "${TMP_OUT}/${EXCEL_NAME}"
rm -f "${EXCEL_DIR}/${BACKUP_NAME}"

echo "[${TS}] Proceso completado. Portal actualizado." >> "${LOG_FILE}"
echo "[${TS}] ============================================" >> "${LOG_FILE}"
