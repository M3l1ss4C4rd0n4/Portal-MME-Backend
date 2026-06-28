#!/usr/bin/env python3
"""
ETL: PDO + SOI (NOAA) → PostgreSQL
=====================================
Portal Energético MME

Descarga los índices climáticos PDO (Pacific Decadal Oscillation) y SOI
(Southern Oscillation Index) desde NOAA, interpola a resolución diaria y
almacena en la tabla metrics de PostgreSQL.

Métricas almacenadas:
  - PDO_Index | entidad=NOAA_ESRL  | recurso=Sistema | unidad=°C_anom_std
  - SOI_Index | entidad=NOAA_CPC   | recurso=Sistema | unidad=hPa_std

Valores almacenados sin offset (la BD ya acepta valores negativos; ver:
la restricción valor_gwh > 0 fue corregida a IS NOT NULL en el esquema).

Ejecución:
    Manual:         python3 etl/etl_pdo_soi.py
    Solo PDO:       python3 etl/etl_pdo_soi.py --solo pdo
    Solo SOI:       python3 etl/etl_pdo_soi.py --solo soi
    Verificar:      python3 etl/etl_pdo_soi.py --verificar
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import time
from datetime import datetime

from infrastructure.database.manager import db_manager
from infrastructure.external.pdo_service import get_pdo_complete
from infrastructure.external.soi_service import get_soi_complete

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
            os.path.join(LOG_DIR, f'etl_pdo_soi_{datetime.now():%Y%m%d}.log'),
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger('etl_pdo_soi')

PDO_METRICA = 'PDO_Index'
PDO_ENTIDAD = 'NOAA_ESRL'
PDO_RECURSO = 'Sistema'
PDO_UNIDAD = '°C_anom_std'

SOI_METRICA = 'SOI_Index'
SOI_ENTIDAD = 'NOAA_CPC'
SOI_RECURSO = 'Sistema'
SOI_UNIDAD = 'hPa_std'


# ---------------------------------------------------------------------------
# PDO ETL
# ---------------------------------------------------------------------------
def run_etl_pdo(timeout: int = 60) -> dict:
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("🌊 PDO ETL — Pacific Decadal Oscillation → PostgreSQL")
    logger.info("=" * 70)

    df = get_pdo_complete(timeout=timeout)
    if df is None or df.empty:
        elapsed = time.time() - t0
        logger.error("❌ No se pudieron obtener datos PDO")
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': 'Sin datos NOAA NCEI'}

    metrics_to_insert = []
    for _, row in df.iterrows():
        metrics_to_insert.append((
            row['fecha'].strftime('%Y-%m-%d'),
            PDO_METRICA,
            PDO_ENTIDAD,
            PDO_RECURSO,
            float(row['pdo_value']),
            PDO_UNIDAD,
        ))

    try:
        n_inserted = db_manager.upsert_metrics_bulk(metrics_to_insert)
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"❌ Error al insertar PDO en BD: {e}", exc_info=True)
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': str(e)}

    elapsed = time.time() - t0
    pdo_actual = df.sort_values('fecha').iloc[-1]['pdo_value']
    logger.info(f"\n✅ PDO ETL completado: {n_inserted} registros en {elapsed:.1f}s")
    logger.info(f"   PDO actual: {pdo_actual:.2f} ({'PDO+ (amplifica El Niño)' if pdo_actual > 0 else 'PDO-'})")
    return {'status': 'OK', 'registros': n_inserted, 'tiempo_s': elapsed}


# ---------------------------------------------------------------------------
# SOI ETL
# ---------------------------------------------------------------------------
def run_etl_soi(timeout: int = 60) -> dict:
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("🌀 SOI ETL — Southern Oscillation Index → PostgreSQL")
    logger.info("=" * 70)

    df = get_soi_complete(timeout=timeout)
    if df is None or df.empty:
        elapsed = time.time() - t0
        logger.error("❌ No se pudieron obtener datos SOI")
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': 'Sin datos NOAA CPC'}

    metrics_to_insert = []
    for _, row in df.iterrows():
        metrics_to_insert.append((
            row['fecha'].strftime('%Y-%m-%d'),
            SOI_METRICA,
            SOI_ENTIDAD,
            SOI_RECURSO,
            float(row['soi_value']),
            SOI_UNIDAD,
        ))

    try:
        n_inserted = db_manager.upsert_metrics_bulk(metrics_to_insert)
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"❌ Error al insertar SOI en BD: {e}", exc_info=True)
        return {'status': 'ERROR', 'registros': 0, 'tiempo_s': elapsed, 'error': str(e)}

    elapsed = time.time() - t0
    soi_actual = df.sort_values('fecha').iloc[-1]['soi_value']
    logger.info(f"\n✅ SOI ETL completado: {n_inserted} registros en {elapsed:.1f}s")
    estado = "NEUTRO"
    if soi_actual < -1:
        estado = "EL NIÑO (SOI negativo)"
    elif soi_actual > 1:
        estado = "LA NIÑA (SOI positivo)"
    logger.info(f"   SOI actual: {soi_actual:.2f} ({estado})")
    return {'status': 'OK', 'registros': n_inserted, 'tiempo_s': elapsed}


# ---------------------------------------------------------------------------
# VERIFICAR
# ---------------------------------------------------------------------------
def verificar_datos():
    logger.info("\n📋 Verificación PDO + SOI en PostgreSQL:")
    for metrica, entidad, recurso in [
        (PDO_METRICA, PDO_ENTIDAD, PDO_RECURSO),
        (SOI_METRICA, SOI_ENTIDAD, SOI_RECURSO),
    ]:
        query = f"""
        SELECT COUNT(*) as n, MIN(fecha) as desde, MAX(fecha) as hasta,
               ROUND(AVG(valor_gwh)::numeric, 2) as media,
               ROUND(STDDEV(valor_gwh)::numeric, 2) as std
        FROM metrics
        WHERE metrica = '{metrica}' AND entidad = '{entidad}' AND recurso = '{recurso}'
        """
        try:
            df = db_manager.query_df(query)
            if df.empty or df.iloc[0]['n'] == 0:
                logger.info(f"  ⚠️ {metrica}: sin datos en BD")
            else:
                row = df.iloc[0]
                logger.info(
                    f"  {metrica:12s} | {row['n']:5d} días | "
                    f"{str(row['desde'])[:10]} → {str(row['hasta'])[:10]} | "
                    f"μ={row['media']:.2f} σ={row['std']:.2f}"
                )
        except Exception as e:
            logger.error(f"  ❌ Error verificando {metrica}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='ETL PDO + SOI (NOAA) → PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python etl/etl_pdo_soi.py              # PDO + SOI completos
  python etl/etl_pdo_soi.py --solo pdo   # Solo PDO
  python etl/etl_pdo_soi.py --solo soi   # Solo SOI
  python etl/etl_pdo_soi.py --verificar  # Verificar datos en BD
        """,
    )
    parser.add_argument('--solo', choices=['pdo', 'soi'],
                        help='Ejecutar solo PDO o solo SOI')
    parser.add_argument('--timeout', type=int, default=60,
                        help='Timeout HTTP en segundos (default: 60)')
    parser.add_argument('--verificar', action='store_true',
                        help='Solo verificar datos existentes en BD')

    args = parser.parse_args()

    if args.verificar:
        verificar_datos()
        return

    resultados = {}
    if args.solo != 'soi':
        resultados['pdo'] = run_etl_pdo(timeout=args.timeout)
    if args.solo != 'pdo':
        resultados['soi'] = run_etl_soi(timeout=args.timeout)

    errores = [k for k, v in resultados.items() if v['status'] != 'OK']
    sys.exit(0 if not errores else 1)


if __name__ == '__main__':
    main()
