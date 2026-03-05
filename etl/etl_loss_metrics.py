#!/usr/bin/env python3
"""
ETL: metrics → loss_metrics
Portal Energético MME
=====================

Pobla la tabla loss_metrics leyendo datos de la tabla metrics (NO de XM API).
Calcula perdidas_pct = PerdidasEner / Gene * 100 y valida rango 3-20%.

Métricas:
  - PerdidasEner: Pérdidas totales de energía (GWh)
  - PerdidasEnerReg: Pérdidas reguladas / técnicas (GWh)
  - PerdidasEnerNoReg: Pérdidas no reguladas / no técnicas (GWh)
  - Gene: Generación del sistema (GWh) — solo para cálculo de %

Ejecución:
    Manual:   python3 etl/etl_loss_metrics.py
    Backfill: python3 etl/etl_loss_metrics.py --desde 2020-01-01 --hasta 2026-03-01
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import argparse
import json
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [ETL_LOSS_METRICS] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuración -----------------------------------------------------------

LOSS_METRICS = ['PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg']
GENERATION_METRIC = 'Gene'
ENTITY_FILTER = 'Sistema'
UNIDAD = 'GWh'

# Rango de validación para pérdidas como % de generación
PERDIDAS_PCT_MIN = 3.0
PERDIDAS_PCT_MAX = 20.0


def get_connection():
    """Conexión directa a PostgreSQL."""
    return psycopg2.connect(
        dbname='portal_energetico',
        user='postgres',
        host='localhost',
        port=5432
    )


def fetch_source_data(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    """
    Lee datos de la tabla metrics para las métricas de pérdidas + generación.
    Retorna dict: { metrica: [(fecha, valor), ...] }
    """
    all_metrics = LOSS_METRICS + [GENERATION_METRIC]
    placeholders = ','.join(['%s'] * len(all_metrics))

    query = f"""
        SELECT fecha::date AS fecha, metrica, valor_gwh
        FROM metrics
        WHERE metrica IN ({placeholders})
          AND entidad = %s
          AND fecha >= %s
          AND fecha <= %s
        ORDER BY fecha, metrica
    """
    params = all_metrics + [ENTITY_FILTER, fecha_desde, fecha_hasta]

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()

    result = {}
    for fecha, metrica, valor in rows:
        result.setdefault(metrica, {})[fecha] = valor

    return result


def calculate_and_insert(conn, source_data: dict) -> dict:
    """
    Calcula pérdidas_pct y hace UPSERT en loss_metrics.
    Retorna stats: {inserted, updated, skipped, warnings}.
    """
    gene_data = source_data.get(GENERATION_METRIC, {})
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'warnings': 0}

    upsert_sql = """
        INSERT INTO loss_metrics (metric_code, fecha, valor, unidad, agente, extra_data)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (metric_code, fecha, agente)
        DO UPDATE SET valor = EXCLUDED.valor,
                      unidad = EXCLUDED.unidad,
                      extra_data = EXCLUDED.extra_data
    """

    cur = conn.cursor()
    batch = []

    for metrica in LOSS_METRICS:
        metric_data = source_data.get(metrica, {})
        if not metric_data:
            logger.warning(f"Sin datos para {metrica}")
            continue

        for fecha, valor in metric_data.items():
            extra = {}

            # Calcular porcentaje solo para PerdidasEner
            if metrica == 'PerdidasEner' and fecha in gene_data:
                gene_val = gene_data[fecha]
                if gene_val and gene_val > 0:
                    pct = (valor / gene_val) * 100
                    extra['perdidas_pct'] = round(pct, 4)
                    extra['generacion_gwh'] = round(gene_val, 6)

                    if pct < PERDIDAS_PCT_MIN or pct > PERDIDAS_PCT_MAX:
                        logger.warning(
                            f"⚠️ {fecha} perdidas_pct={pct:.2f}% fuera de rango "
                            f"[{PERDIDAS_PCT_MIN}-{PERDIDAS_PCT_MAX}%]"
                        )
                        extra['fuera_de_rango'] = True
                        stats['warnings'] += 1

            extra_json = json.dumps(extra) if extra else None

            batch.append((
                metrica,
                fecha,
                round(valor, 6),
                UNIDAD,
                ENTITY_FILTER,
                extra_json
            ))

    if batch:
        psycopg2.extras.execute_batch(cur, upsert_sql, batch, page_size=500)
        stats['inserted'] = len(batch)
        conn.commit()
        logger.info(f"✅ UPSERT {len(batch)} registros en loss_metrics")
    else:
        logger.warning("Sin registros para insertar")

    cur.close()
    return stats


def run_etl(fecha_desde: str, fecha_hasta: str):
    """Ejecuta el ETL completo."""
    logger.info(f"Iniciando ETL loss_metrics: {fecha_desde} → {fecha_hasta}")

    conn = get_connection()
    try:
        # 1. Leer datos fuente
        source_data = fetch_source_data(conn, fecha_desde, fecha_hasta)
        for m in LOSS_METRICS + [GENERATION_METRIC]:
            count = len(source_data.get(m, {}))
            logger.info(f"  {m}: {count} registros fuente")

        # 2. Calcular e insertar
        stats = calculate_and_insert(conn, source_data)

        # 3. Verificar resultado
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM loss_metrics")
        total = cur.fetchone()[0]
        cur.close()

        logger.info(f"✅ ETL completado. loss_metrics tiene {total} registros totales")
        logger.info(f"   Stats: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error en ETL: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='ETL: metrics → loss_metrics')
    parser.add_argument('--desde', default='2020-01-01', help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--hasta', default=datetime.now().strftime('%Y-%m-%d'),
                        help='Fecha fin (YYYY-MM-DD)')
    args = parser.parse_args()

    run_etl(args.desde, args.hasta)


if __name__ == '__main__':
    main()
