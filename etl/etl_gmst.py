#!/usr/bin/env python3
"""
ETL: GMST (Global Mean Surface Temperature anomaly) → PostgreSQL
=================================================================
Portal Energético MME

Descarga la anomalía de temperatura media global desde NASA GISTEMP v4,
interpola a resolución diaria y almacena en la tabla metrics de PostgreSQL.

Métrica almacenada:
  - GMST_Anomalia | entidad=NASA_GISS | recurso=Sistema | unidad=°C_anom

Por qué es útil:
  El calentamiento global intensifica los eventos ENSO (IPCC AR6).
  Agregar GMST al modelo Prophet permite capturar la tendencia secular
  sin asumir estacionariedad. El valor actual (~+1.3°C en 2026) se propaga
  hacia el futuro (futura_ffill) porque el GMST cambia muy lentamente.

Ejecución:
    Manual:       python3 etl/etl_gmst.py
    Verificar:    python3 etl/etl_gmst.py --verificar
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import time
from datetime import datetime

from infrastructure.database.manager import db_manager
from infrastructure.external.gmst_service import get_gmst_complete

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'logs', 'etl')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(LOG_DIR, f'etl_gmst_{datetime.now():%Y%m%d}.log'),
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger('etl_gmst')

GMST_METRICA = 'GMST_Anomalia'
GMST_ENTIDAD = 'NASA_GISS'
GMST_RECURSO = 'Sistema'
GMST_UNIDAD = '°C_anom'


# ---------------------------------------------------------------------------
# ETL principal
# ---------------------------------------------------------------------------
def run_etl_gmst(timeout: int = 60) -> dict:
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("🌡️  GMST ETL — Global Mean Surface Temperature → PostgreSQL")
    logger.info("=" * 70)

    df = get_gmst_complete(timeout=timeout)
    if df is None or df.empty:
        elapsed = time.time() - t0
        logger.error("❌ No se pudieron obtener datos GMST")
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': 'Sin datos NASA/NOAA'}

    metrics_to_insert = []
    for _, row in df.iterrows():
        metrics_to_insert.append((
            row['fecha'].strftime('%Y-%m-%d'),
            GMST_METRICA,
            GMST_ENTIDAD,
            GMST_RECURSO,
            float(row['gmst_value']),
            GMST_UNIDAD,
        ))

    try:
        n_inserted = db_manager.upsert_metrics_bulk(metrics_to_insert)
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"❌ Error al insertar GMST en BD: {e}", exc_info=True)
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': str(e)}

    elapsed = time.time() - t0
    gmst_actual = df.sort_values('fecha').iloc[-1]['gmst_value']
    logger.info(f"\n✅ GMST ETL completado: {n_inserted} registros en {elapsed:.1f}s")
    logger.info(f"   GMST actual: +{gmst_actual:.2f}°C sobre promedio 1951-1980")
    return {'status': 'OK', 'registros': n_inserted, 'tiempo_s': elapsed}


# ---------------------------------------------------------------------------
# VERIFICAR
# ---------------------------------------------------------------------------
def verificar_datos():
    logger.info("\n📋 Verificación GMST en PostgreSQL:")
    query = f"""
    SELECT COUNT(*) as n, MIN(fecha) as desde, MAX(fecha) as hasta,
           ROUND(AVG(valor_gwh)::numeric, 4) as media,
           ROUND(STDDEV(valor_gwh)::numeric, 4) as std,
           MAX(valor_gwh) as maximo
    FROM metrics
    WHERE metrica = '{GMST_METRICA}' AND entidad = '{GMST_ENTIDAD}' AND recurso = '{GMST_RECURSO}'
    """
    try:
        df = db_manager.query_df(query)
        if df.empty or df.iloc[0]['n'] == 0:
            logger.info("  ⚠️ GMST_Anomalia: sin datos en BD. Ejecutar sin --verificar primero.")
        else:
            row = df.iloc[0]
            logger.info(
                f"  {GMST_METRICA:15s} | {row['n']:5d} días | "
                f"{str(row['desde'])[:10]} → {str(row['hasta'])[:10]} | "
                f"μ={row['media']:.3f} σ={row['std']:.3f} max={row['maximo']:.3f} °C"
            )
    except Exception as e:
        logger.error(f"  ❌ Error verificando GMST: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='ETL GMST (NASA GISTEMP) → PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python etl/etl_gmst.py             # Cargar datos GMST completos
  python etl/etl_gmst.py --verificar # Verificar datos en BD
        """,
    )
    parser.add_argument('--timeout', type=int, default=60,
                        help='Timeout HTTP en segundos (default: 60)')
    parser.add_argument('--verificar', action='store_true',
                        help='Solo verificar datos existentes en BD')

    args = parser.parse_args()

    if args.verificar:
        verificar_datos()
        return

    result = run_etl_gmst(timeout=args.timeout)
    sys.exit(0 if result['status'] == 'OK' else 1)


if __name__ == '__main__':
    main()
