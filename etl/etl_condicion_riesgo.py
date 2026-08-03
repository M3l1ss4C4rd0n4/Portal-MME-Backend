#!/usr/bin/env python3
"""
ETL: Condición del Estatuto de Riesgo de Desabastecimiento (SIMEM) → PostgreSQL
Portal Energético MME
================================================================================

Trae en vivo, vía `pydatasimem`, el dataset SIMEM `ebc2d1` — "Condición del
sistema según lo establecido en el Estatuto de Riesgo de Desabastecimiento"
(clasificación diaria Normal/Riesgo publicada por XM) y lo guarda en
`sector_energetico.metrics` como métrica `CondicionEstatutoRiesgo`.

No sustituye la Senda de Referencia (Res. CREG 209/2020) — esa es un valor
regulatorio publicado 2 veces al año como XLSX/PDF, sin API (ver
`etl_senda_referencia.py`). Esta métrica es un dato distinto, 100% en vivo,
que da una señal de alerta temprana adicional sin depender de importación
manual.

Codificación (columna numérica `valor_gwh`, no hay columna categórica en el
esquema de `metrics`): Normal = 0, Vigilancia = 1, Riesgo = 2 (severidad
ordinal, mismo criterio que el resto del portal usa para NE/HSIN). `unidad`
se guarda como 'categoria' para dejar explícito que no es una magnitud física.

Ejecución:
    Automático: Cron 1×/día
    Manual: python3 etl/etl_condicion_riesgo.py
    Manual (rango de fechas): python3 etl/etl_condicion_riesgo.py --fecha-inicio 2026-01-01 --fecha-fin 2026-07-06
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
from datetime import datetime, timedelta

from pydataxm.pydatasimem import ReadSIMEM
from infrastructure.database.manager import db_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATASET_ID = "ebc2d1"
METRICA = "CondicionEstatutoRiesgo"
ENTIDAD = "Sistema"
RECURSO = "Sistema"
CODIFICACION = {"Normal": 0, "Vigilancia": 1, "Riesgo": 2}


def ejecutar_etl(fecha_inicio_custom: str = None, fecha_fin_custom: str = None) -> dict:
    fecha_fin = fecha_fin_custom or datetime.now().strftime("%Y-%m-%d")
    fecha_inicio = fecha_inicio_custom or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    logger.info(f"Consultando SIMEM dataset {DATASET_ID} ({fecha_inicio} → {fecha_fin})...")
    try:
        df = ReadSIMEM(DATASET_ID, fecha_inicio, fecha_fin).main()
    except Exception as e:
        logger.error(f"❌ Error consultando SIMEM: {e}")
        return {"exito": False, "error": str(e), "insertados": 0}

    if df is None or df.empty:
        logger.warning("⚠️  SIMEM no devolvió filas para el rango solicitado.")
        return {"exito": True, "insertados": 0}

    filas = []
    descartadas = 0
    for _, row in df.iterrows():
        resultado = row.get("ResultadoEvaluacionEstatuto")
        valor = CODIFICACION.get(resultado)
        if valor is None:
            logger.warning(f"⚠️  Valor inesperado '{resultado}' en fecha {row.get('Fecha')}, se descarta.")
            descartadas += 1
            continue
        filas.append((row["Fecha"], METRICA, ENTIDAD, RECURSO, float(valor), "categoria"))

    insertados = db_manager.upsert_metrics_bulk(filas)
    logger.info(f"✅ {insertados} filas insertadas/actualizadas ({descartadas} descartadas).")
    return {"exito": True, "insertados": insertados, "descartadas": descartadas}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL: Condición Estatuto de Riesgo (SIMEM) → PostgreSQL")
    parser.add_argument("--fecha-inicio", type=str, help="Fecha inicio (YYYY-MM-DD). Por defecto: hace 7 días")
    parser.add_argument("--fecha-fin", type=str, help="Fecha fin (YYYY-MM-DD). Por defecto: hoy")
    args = parser.parse_args()

    resultado = ejecutar_etl(fecha_inicio_custom=args.fecha_inicio, fecha_fin_custom=args.fecha_fin)
    sys.exit(0 if resultado.get("exito", False) else 1)
