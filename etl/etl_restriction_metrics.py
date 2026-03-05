#!/usr/bin/env python3
"""
ETL: metrics → restriction_metrics
Portal Energético MME
=====================

Pobla la tabla restriction_metrics leyendo datos de la tabla metrics (NO de XM API).

Métricas:
  - RestAliv:      Restricciones Aliviadas (Millones COP)
  - RestSinAliv:   Restricciones No Aliviadas (Millones COP)
  - RespComerAGC:  Reconciliación AGC (Millones COP)

Ejecución:
    Manual:   python3 etl/etl_restriction_metrics.py
    Backfill: python3 etl/etl_restriction_metrics.py --desde 2020-01-01 --hasta 2026-03-01
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import argparse
from datetime import datetime

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [ETL_RESTRICTION_METRICS] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuración -----------------------------------------------------------

RESTRICTION_METRICS = {
    'RestAliv': {
        'tipo_restriccion': 'aliviada',
        'unidad': 'Millones COP',
    },
    'RestSinAliv': {
        'tipo_restriccion': 'no_aliviada',
        'unidad': 'Millones COP',
    },
    'RespComerAGC': {
        'tipo_restriccion': 'reconciliacion_agc',
        'unidad': 'Millones COP',
    },
}

ENTITY_FILTER = 'Sistema'


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
    Lee datos de la tabla metrics para las métricas de restricciones.
    Retorna dict: { metrica: [(fecha, valor), ...] }
    """
    metric_codes = list(RESTRICTION_METRICS.keys())
    placeholders = ','.join(['%s'] * len(metric_codes))

    query = f"""
        SELECT fecha::date AS fecha, metrica, valor_gwh
        FROM metrics
        WHERE metrica IN ({placeholders})
          AND entidad = %s
          AND fecha >= %s
          AND fecha <= %s
        ORDER BY fecha, metrica
    """
    params = metric_codes + [ENTITY_FILTER, fecha_desde, fecha_hasta]

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()

    result = {}
    for fecha, metrica, valor in rows:
        result.setdefault(metrica, {})[fecha] = valor

    return result


def insert_data(conn, source_data: dict) -> dict:
    """
    Hace UPSERT en restriction_metrics.
    Retorna stats: {inserted, skipped}.
    """
    stats = {'inserted': 0, 'skipped': 0}

    upsert_sql = """
        INSERT INTO restriction_metrics
            (metric_code, fecha, valor, unidad, recurso, tipo_restriccion)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (metric_code, fecha, recurso)
        DO UPDATE SET valor = EXCLUDED.valor,
                      unidad = EXCLUDED.unidad,
                      tipo_restriccion = EXCLUDED.tipo_restriccion
    """

    cur = conn.cursor()
    batch = []

    for metrica, config in RESTRICTION_METRICS.items():
        metric_data = source_data.get(metrica, {})
        if not metric_data:
            logger.warning(f"Sin datos para {metrica}")
            continue

        for fecha, valor in metric_data.items():
            batch.append((
                metrica,
                fecha,
                round(valor, 6),
                config['unidad'],
                ENTITY_FILTER,
                config['tipo_restriccion'],
            ))

    if batch:
        psycopg2.extras.execute_batch(cur, upsert_sql, batch, page_size=500)
        stats['inserted'] = len(batch)
        conn.commit()
        logger.info(f"✅ UPSERT {len(batch)} registros en restriction_metrics")
    else:
        logger.warning("Sin registros para insertar")

    cur.close()
    return stats


def run_etl(fecha_desde: str, fecha_hasta: str):
    """Ejecuta el ETL completo."""
    logger.info(f"Iniciando ETL restriction_metrics: {fecha_desde} → {fecha_hasta}")

    conn = get_connection()
    try:
        # 1. Leer datos fuente
        source_data = fetch_source_data(conn, fecha_desde, fecha_hasta)
        for m in RESTRICTION_METRICS:
            count = len(source_data.get(m, {}))
            logger.info(f"  {m}: {count} registros fuente")

        # 2. Insertar
        stats = insert_data(conn, source_data)

        # 3. Verificar
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM restriction_metrics")
        total = cur.fetchone()[0]
        cur.close()

        logger.info(f"✅ ETL completado. restriction_metrics tiene {total} registros totales")
        logger.info(f"   Stats: {stats}")
        return stats

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error en ETL: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='ETL: metrics → restriction_metrics')
    parser.add_argument('--desde', default='2020-01-01', help='Fecha inicio (YYYY-MM-DD)')
    parser.add_argument('--hasta', default=datetime.now().strftime('%Y-%m-%d'),
                        help='Fecha fin (YYYY-MM-DD)')
    args = parser.parse_args()

    run_etl(args.desde, args.hasta)


if __name__ == '__main__':
    main()
