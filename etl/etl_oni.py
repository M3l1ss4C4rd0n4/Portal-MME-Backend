#!/usr/bin/env python3
"""
ETL: ONI (NOAA CPC) → PostgreSQL
==================================
Portal Energético MME

Descarga el índice ONI mensual histórico desde NOAA CPC, genera un pronóstico
de persistencia para los próximos 9 meses, interpola a resolución diaria y
almacena en la tabla metrics de PostgreSQL.

Métrica: ONI_Index | Entidad: NOAA | Recurso: Sistema | Unidad: °C_anom_offset5

IMPORTANTE: Los valores se almacenan con offset +5.0 (oni_valor + 5.0)
para cumplir el requisito de la arquitectura de metrics (valor_gwh > 0).
El offset se revierte al cargar como regresor en el modelo Prophet.
Ver: infrastructure/external/oni_service.py → ONI_STORAGE_OFFSET

Ejecución:
    Manual:         python3 etl/etl_oni.py
    Solo histórico: python3 etl/etl_oni.py --meses_hist 36
    Backfill total: python3 etl/etl_oni.py --meses_hist 0
    Verificar:      python3 etl/etl_oni.py --verificar
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import time
from datetime import datetime

from infrastructure.database.manager import db_manager
from infrastructure.external.oni_service import (
    get_oni_complete,
    ONI_STORAGE_OFFSET,
)

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
            os.path.join(LOG_DIR, f'etl_oni_{datetime.now():%Y%m%d}.log'),
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger('etl_oni')

METRICA_BD = 'ONI_Index'
ENTIDAD = 'NOAA'
RECURSO = 'Sistema'
UNIDAD = '°C_anom_offset5'


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------
def run_etl_oni(
    meses_historico: int = 36,
    meses_pronostico: int = 9,
    timeout: int = 60,
) -> dict:
    """
    Ejecuta el pipeline ETL ONI → PostgreSQL.

    Args:
        meses_historico: Meses de historia a cargar (0 = todos desde 1950)
        meses_pronostico: Meses de pronóstico de persistencia a generar
        timeout: Timeout HTTP en segundos

    Returns:
        dict con {status, registros_historico, registros_pronostico, tiempo_s}
    """
    t0 = time.time()
    logger.info("=" * 70)
    logger.info(
        f"🌊 ONI ETL — histórico: {meses_historico}m | "
        f"pronóstico: {meses_pronostico}m"
    )
    logger.info("=" * 70)

    df = get_oni_complete(
        meses_historico=meses_historico,
        meses_pronostico=meses_pronostico,
        timeout=timeout,
    )

    if df is None or df.empty:
        elapsed = time.time() - t0
        logger.error("❌ No se pudieron obtener datos ONI de NOAA CPC")
        return {
            'status': 'ERROR',
            'registros_historico': 0,
            'registros_pronostico': 0,
            'tiempo_s': elapsed,
            'error': 'Sin datos de NOAA CPC',
        }

    metrics_to_insert = []
    for _, row in df.iterrows():
        oni_raw = float(row['oni_value'])
        # Aplicar offset +5.0 para mantener valor_gwh > 0
        oni_stored = oni_raw + ONI_STORAGE_OFFSET

        metrics_to_insert.append((
            row['fecha'].strftime('%Y-%m-%d'),
            METRICA_BD,
            ENTIDAD,
            RECURSO,
            oni_stored,
            UNIDAD,
        ))

    try:
        n_inserted = db_manager.upsert_metrics_bulk(metrics_to_insert)
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"❌ Error al insertar en BD: {e}", exc_info=True)
        return {
            'status': 'ERROR',
            'registros_historico': 0,
            'registros_pronostico': 0,
            'tiempo_s': elapsed,
            'error': str(e),
        }

    n_hist = int((~df['es_pronostico']).sum())
    n_prono = int(df['es_pronostico'].sum())
    elapsed = time.time() - t0

    logger.info(f"\n✅ ONI ETL completado:")
    logger.info(f"   Histórico:   {n_hist:5d} días → BD")
    logger.info(f"   Pronóstico:  {n_prono:5d} días → BD")
    logger.info(f"   Total upsert: {n_inserted} registros en {elapsed:.1f}s")

    oni_actual = df[~df['es_pronostico']].sort_values('fecha').iloc[-1]['oni_value']
    logger.info(f"   ONI actual:  {oni_actual:.2f} °C")
    if oni_actual >= 0.5:
        logger.info(f"   Estado: EL NIÑO ({oni_actual:.2f})")
    elif oni_actual <= -0.5:
        logger.info(f"   Estado: LA NIÑA ({oni_actual:.2f})")
    else:
        logger.info(f"   Estado: NEUTRO ({oni_actual:.2f})")

    return {
        'status': 'OK',
        'registros_historico': n_hist,
        'registros_pronostico': n_prono,
        'registros_total': n_inserted,
        'oni_actual': oni_actual,
        'tiempo_s': elapsed,
    }


def verificar_datos_oni():
    """Verifica datos ONI existentes en PostgreSQL."""
    logger.info("\n📋 Verificación de datos ONI en PostgreSQL:")

    # Valores hardcodeados como constantes de módulo — no son input de usuario
    query = f"""
    SELECT
        COUNT(*) as n,
        MIN(fecha) as desde,
        MAX(fecha) as hasta,
        AVG(valor_gwh - 5.0) as oni_medio,
        STDDEV(valor_gwh - 5.0) as oni_std,
        SUM(CASE WHEN fecha > CURRENT_DATE THEN 1 ELSE 0 END) as dias_pronostico
    FROM metrics
    WHERE metrica = '{METRICA_BD}' AND entidad = '{ENTIDAD}' AND recurso = '{RECURSO}'
    """
    try:
        df = db_manager.query_df(query)

        if df.empty or df.iloc[0]['n'] == 0:
            logger.info("  ⚠️ No hay datos ONI en la BD. Ejecutar etl_oni.py primero.")
            return

        row = df.iloc[0]
        logger.info(
            f"  {METRICA_BD:20s} | {row['n']:5d} días | "
            f"{str(row['desde'])[:10]} → {str(row['hasta'])[:10]} | "
            f"μ={row['oni_medio']:.2f} σ={row['oni_std']:.2f} | "
            f"pronóstico: {int(row['dias_pronostico'])} días"
        )
    except Exception as e:
        logger.error(f"  ❌ Error verificando ONI: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='ETL ONI (NOAA CPC) → PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python etl/etl_oni.py                        # Últimos 36 meses + 9 meses pronóstico
  python etl/etl_oni.py --meses_hist 0         # Histórico completo desde 1950
  python etl/etl_oni.py --meses_hist 12        # Solo últimos 12 meses
  python etl/etl_oni.py --verificar            # Verificar datos en BD
        """,
    )
    parser.add_argument('--meses_hist', type=int, default=36,
                        help='Meses de historia a cargar (0=todo desde 1950, default: 36)')
    parser.add_argument('--meses_prono', type=int, default=9,
                        help='Meses de pronóstico de persistencia (default: 9)')
    parser.add_argument('--timeout', type=int, default=60,
                        help='Timeout HTTP en segundos (default: 60)')
    parser.add_argument('--verificar', action='store_true',
                        help='Solo verificar datos existentes en BD')

    args = parser.parse_args()

    if args.verificar:
        verificar_datos_oni()
        return

    resultado = run_etl_oni(
        meses_historico=args.meses_hist,
        meses_pronostico=args.meses_prono,
        timeout=args.timeout,
    )

    sys.exit(0 if resultado['status'] == 'OK' else 1)


if __name__ == '__main__':
    main()
