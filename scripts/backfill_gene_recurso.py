#!/usr/bin/env python3
"""
Backfill histórico de Gene/Recurso (generación por planta/fuente).

El ETL original cargaba 1 generador/día (datos inútiles) para Gene/Recurso
antes del 13-mar-2026. Este script:
  1. Elimina esas 2,263 filas falsas
  2. Repuebla desde la API XM en batches mensuales de 2020-01-01 → 2026-03-12

Uso:
    python scripts/backfill_gene_recurso.py               # backfill completo
    python scripts/backfill_gene_recurso.py --dry-run      # solo muestra qué haría
    python scripts/backfill_gene_recurso.py --desde 2025-01-01  # año parcial
    python scripts/backfill_gene_recurso.py --solo-limpiar  # solo borra filas malas
"""

import sys
import os
import argparse
import logging
import time
import psycopg2
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/admonctrlxm/server/logs/backfill_gene_recurso.log')
    ]
)
logger = logging.getLogger(__name__)


DB_PARAMS = dict(dbname='portal_energetico', user='postgres', host='localhost')

# Fecha de corte: desde esta fecha en adelante Gene/Recurso está correcto
FECHA_CORTE = date(2026, 3, 13)
# Inicio del histórico disponible en XM
FECHA_INICIO_DEFAULT = date(2020, 1, 1)
# Días por batch (30 días es seguro para la API XM)
BATCH_DIAS = 30


def limpiar_filas_falsas(dry_run=False):
    """Elimina las filas Gene/Recurso pre-2026-03-13 (1 generador/día falso)."""
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*), ROUND(SUM(valor_gwh)::numeric, 2)
        FROM metrics
        WHERE metrica = 'Gene' AND entidad = 'Recurso'
        AND fecha < %s
    """, (FECHA_CORTE,))
    cnt, total_gwh = cur.fetchone()
    logger.info(f"Filas Gene/Recurso pre-{FECHA_CORTE}: {cnt} ({total_gwh} GWh total falso)")

    if cnt == 0:
        logger.info("Nada que limpiar.")
        conn.close()
        return 0

    if dry_run:
        logger.info(f"[DRY-RUN] Se eliminarían {cnt} filas.")
        conn.close()
        return cnt

    cur.execute("""
        DELETE FROM metrics
        WHERE metrica = 'Gene' AND entidad = 'Recurso'
        AND fecha < %s
    """, (FECHA_CORTE,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    logger.info(f"✅ Eliminadas {deleted} filas falsas de Gene/Recurso.")
    return deleted


def backfill_gene_recurso(fecha_inicio: date, fecha_fin: date, dry_run=False):
    """Repuebla Gene/Recurso desde la API XM en batches mensuales."""
    from pydataxm.pydataxm import ReadDB
    from etl.etl_xm_to_postgres import poblar_metrica

    config = {
        'metric': 'Gene',
        'entity': 'Recurso',
        'conversion': 'horas_a_diario',
        'dias_history': BATCH_DIAS,
        'batch_size': BATCH_DIAS,
    }

    try:
        obj_api = ReadDB()
        logger.info("✅ Conexión a API XM inicializada")
    except Exception as e:
        logger.error(f"❌ Error conectando a API XM: {e}")
        return False

    total_insertados = 0
    current = fecha_inicio

    while current <= fecha_fin:
        batch_end = min(current + timedelta(days=BATCH_DIAS - 1), fecha_fin)
        logger.info(f"\n{'='*60}")
        logger.info(f"📦 Batch: {current} → {batch_end}")

        if dry_run:
            logger.info(f"[DRY-RUN] Saltando inserción.")
            current = batch_end + timedelta(days=1)
            continue

        try:
            n = poblar_metrica(
                obj_api,
                config,
                usar_timeout=False,
                fecha_inicio_custom=current.strftime('%Y-%m-%d'),
                fecha_fin_custom=batch_end.strftime('%Y-%m-%d'),
            )
            total_insertados += n
            logger.info(f"✅ Batch insertó {n} registros | acumulado: {total_insertados}")
        except Exception as e:
            logger.error(f"❌ Error en batch {current}–{batch_end}: {e}")

        current = batch_end + timedelta(days=1)
        # Pausa respetuosa entre batches para no saturar la API XM
        time.sleep(1.0)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Backfill completado: {total_insertados} registros insertados/actualizados")
    return True


def verificar_resultado():
    """Imprime un resumen post-backfill."""
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute("""
        SELECT EXTRACT(YEAR FROM fecha) as anio,
               COUNT(DISTINCT fecha::date) as dias,
               COUNT(DISTINCT recurso) as recursos_distintos,
               ROUND(SUM(valor_gwh)::numeric, 2) as total_gwh
        FROM metrics
        WHERE metrica = 'Gene' AND entidad = 'Recurso'
        GROUP BY 1 ORDER BY 1
    """)
    rows = cur.fetchall()
    conn.close()
    print("\n=== Gene/Recurso DESPUÉS del backfill ===")
    print(f"{'Año':<6} | {'Días':<5} | {'Recursos/año':<13} | {'Total GWh':>12}")
    print('-' * 50)
    for r in rows:
        print(f"{int(r[0]):<6} | {r[1]:<5} | {r[2]:<13} | {r[3]:>12}")


def main():
    parser = argparse.ArgumentParser(description='Backfill histórico Gene/Recurso desde API XM')
    parser.add_argument('--dry-run', action='store_true', help='Simular sin escribir en BD')
    parser.add_argument('--solo-limpiar', action='store_true', help='Solo eliminar filas falsas, sin repoblar')
    parser.add_argument('--desde', type=str, default=FECHA_INICIO_DEFAULT.isoformat(),
                        help=f'Fecha inicio backfill (default: {FECHA_INICIO_DEFAULT})')
    parser.add_argument('--hasta', type=str, default=(FECHA_CORTE - timedelta(days=1)).isoformat(),
                        help=f'Fecha fin backfill (default: {FECHA_CORTE - timedelta(days=1)})')
    args = parser.parse_args()

    fecha_inicio = date.fromisoformat(args.desde)
    fecha_fin = date.fromisoformat(args.hasta)

    logger.info(f"🚀 Backfill Gene/Recurso | {fecha_inicio} → {fecha_fin}")
    logger.info(f"   dry_run={args.dry_run} | solo_limpiar={args.solo_limpiar}")

    # Paso 1: Limpiar filas falsas
    limpiar_filas_falsas(dry_run=args.dry_run)

    if args.solo_limpiar:
        logger.info("--solo-limpiar activo, terminando.")
        return

    # Paso 2: Repoblar desde API XM
    ok = backfill_gene_recurso(fecha_inicio, fecha_fin, dry_run=args.dry_run)

    # Paso 3: Verificar resultado
    if not args.dry_run and ok:
        verificar_resultado()


if __name__ == '__main__':
    main()
