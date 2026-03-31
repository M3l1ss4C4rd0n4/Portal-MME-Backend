#!/usr/bin/env python3
"""
ETL: Detección de anomalías PNT via Isolation Forest → tabla anomalies

Modos:
  - Sin args       : procesa últimos 30 días (incremental, omite fechas ya existentes)
  - --backfill     : procesa último año completo (365 días atrás)
  - --desde YYYY-MM-DD [--hasta YYYY-MM-DD]  : rango específico

Requiere venv (sklearn):
  venv/bin/python3 etl/etl_anomalies_pnt.py
  venv/bin/python3 etl/etl_anomalies_pnt.py --backfill
  venv/bin/python3 etl/etl_anomalies_pnt.py --desde 2025-01-01 --hasta 2025-12-31
"""

import sys
import os
import argparse
import json
import logging
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.services.losses_nt_service import LossesNTService
from infrastructure.database.connection import connection_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

METRICA = 'PNT'
MODELO = 'isolation_forest_v1'

# Mapeo severidad Isolation Forest → CHECK constraint en tabla anomalies
# La tabla acepta: INFO, AVISO, ALERTA, CRITICA
SEV_MAP = {
    'CRITICO': 'CRITICA',
    'ALERTA':  'ALERTA',
    'NORMAL':  None,   # filas normales no se insertan
}


def _get_existing_dates(cur, metrica: str) -> set:
    """Retorna el conjunto de fechas ya presentes en anomalies para la métrica."""
    cur.execute("SELECT fecha FROM anomalies WHERE metrica = %s", (metrica,))
    return {row[0] for row in cur.fetchall()}


def _insert_anomalies(df, conn) -> tuple[int, int]:
    """
    Inserta filas anómalas (anomaly == -1) en la tabla anomalies.
    Omite fechas que ya existen para evitar duplicados.
    Retorna (insertados, omitidos).
    """
    cur = conn.cursor()
    existing = _get_existing_dates(cur, METRICA)
    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        # Solo procesar filas detectadas como anomalía
        if row['anomaly'] != -1:
            continue

        sev_raw = str(row.get('severidad', ''))
        severidad = SEV_MAP.get(sev_raw)
        if severidad is None:
            # Fila NORMAL etiquetada como -1 (no debería ocurrir), ignorar
            continue

        # Normalizar fecha a date
        fecha = row['fecha']
        if hasattr(fecha, 'date'):
            fecha = fecha.date()

        # Evitar duplicados sin necesitar constraint única en BD
        if fecha in existing:
            skipped += 1
            continue

        valor_detectado = float(row['pnt_pct']) if row['pnt_pct'] is not None else None
        valor_esperado = (
            float(row['promedio_movil_30d'])
            if row.get('promedio_movil_30d') is not None
            else None
        )

        if valor_detectado is not None and valor_esperado and valor_esperado != 0:
            desviacion_pct = round(
                abs((valor_detectado - valor_esperado) / valor_esperado * 100), 4
            )
        else:
            desviacion_pct = None

        detalles = {
            'anomaly_score': (
                float(row['anomaly_score']) if row.get('anomaly_score') is not None else None
            ),
            'variacion_diaria': (
                float(row['variacion_diaria']) if row.get('variacion_diaria') is not None else None
            ),
        }

        try:
            cur.execute(
                """
                INSERT INTO anomalies
                    (metrica, fecha, valor_detectado, valor_esperado, desviacion_pct,
                     severidad, modelo, detalles, notificado, fecha_deteccion, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW(), NOW())
                """,
                (
                    METRICA,
                    fecha,
                    valor_detectado,
                    valor_esperado,
                    desviacion_pct,
                    severidad,
                    MODELO,
                    json.dumps(detalles),
                ),
            )
            conn.commit()
            inserted += 1
            existing.add(fecha)  # prevenir re-insert si fecha aparece dos veces en df
        except Exception as exc:
            logger.warning(f"  ⚠️  Error insertando {fecha}: {exc}")
            conn.rollback()

    cur.close()
    return inserted, skipped


def run(desde: date, hasta: date) -> None:
    logger.info(f"🔍 Iniciando detección anomalías PNT: {desde} → {hasta}")

    svc = LossesNTService()
    df = svc.detect_anomalies_isolation_forest(desde, hasta)

    if df is None or df.empty:
        logger.warning("⚠️  DataFrame vacío — datos insuficientes para Isolation Forest (mínimo 12 registros)")
        return

    total = len(df)
    n_anomalos = int((df['anomaly'] == -1).sum())
    n_criticos = int((df['severidad'] == 'CRITICO').sum())
    n_alertas = int((df['severidad'] == 'ALERTA').sum())
    logger.info(
        f"📊 Isolation Forest: {total} registros evaluados "
        f"→ {n_anomalos} anomalías ({n_criticos} CRITICO, {n_alertas} ALERTA)"
    )

    with connection_manager.get_connection() as conn:
        inserted, skipped = _insert_anomalies(df, conn)

    logger.info(f"✅ Insertados: {inserted} | Ya existían (omitidos): {skipped}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='ETL anomalías PNT (Isolation Forest) → tabla anomalies'
    )
    parser.add_argument(
        '--backfill',
        action='store_true',
        help='Procesar último año completo (365 días)',
    )
    parser.add_argument('--desde', type=str, help='Fecha inicio YYYY-MM-DD')
    parser.add_argument('--hasta', type=str, help='Fecha fin YYYY-MM-DD (default: antes de ayer)')
    args = parser.parse_args()

    # El más reciente siempre es antes de ayer para evitar datos parciales del día
    hasta_default = date.today() - timedelta(days=2)

    if args.desde:
        desde_val = date.fromisoformat(args.desde)
        hasta_val = date.fromisoformat(args.hasta) if args.hasta else hasta_default
    elif args.backfill:
        hasta_val = hasta_default
        desde_val = hasta_val - timedelta(days=365)
    else:
        # incremental: último mes
        hasta_val = hasta_default
        desde_val = hasta_val - timedelta(days=30)

    run(desde_val, hasta_val)
