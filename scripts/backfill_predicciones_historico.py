#!/usr/bin/env python3
"""
Backfill de datos históricos XM (2000-2019) para métricas usadas en predicciones.
===================================================================================

La API XM (pydataxm) tiene datos desde ~2000 pero nuestra BD solo tiene desde 2020.
Este script descarga las métricas clave para mejorar los modelos predictivos,
especialmente APORTES_HIDRICOS (AporEner) y EMBALSES_PCT (PorcVoluUtilDiar).

Uso:
    # Descarga completa 2000-2019 (puede tomar 60-120 min):
    python scripts/backfill_predicciones_historico.py

    # Rango específico:
    python scripts/backfill_predicciones_historico.py --desde 2010-01-01 --hasta 2019-12-31

    # Solo una métrica:
    python scripts/backfill_predicciones_historico.py --desde 2000-01-01 --metrica AporEner

    # Modo dry-run (solo verifica disponibilidad, sin insertar):
    python scripts/backfill_predicciones_historico.py --dry-run

Beneficios esperados:
    - AporEner/PorcVoluUtilDiar: 2,300 → ~9,500 observaciones (+20 años)
    - APORTES_HIDRICOS MAPE: posible mejora de 21% → 12-15% (más ciclos hídricos)
    - Base de datos suficiente para experimentos con redes neuronales (N-HiTS/NHITS)

Notas:
    - PRECIO_BOLSA NO se incluye (ventana_meses=15 hardcoded por cambio de régimen tarifario)
    - Eólica NO existe en Colombia antes de 2022 (parques Guajira)
    - DemaReal/Sistema como entidad no retorna datos históricos; Gene/Sistema sí (horario)
    - La API puede ser lenta (~1-3 s/petición); tolerar esperas largas
"""

import sys
import os
import argparse
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# ─── Métricas objetivo para predicciones ─────────────────────────────────────
# Cada entrada es una config compatible con poblar_metrica() del ETL principal.
# Excluimos PRECIO_BOLSA (ventana_meses=15), Gene/Recurso (no beneficia ensemble),
# y métricas que solo existen post-2020.
METRICAS_BACKFILL = [
    {
        'metric': 'AporEner',
        'entity': 'Sistema',
        'conversion': 'Wh_a_GWh',      # API devuelve Wh, convertir a GWh
        'batch_size': 365,              # 1 año por batch (datos ya diarios)
        '_descripcion': 'Aportes hídricos — MAYOR BENEFICIO para APORTES_HIDRICOS MAPE',
    },
    {
        'metric': 'PorcVoluUtilDiar',
        'entity': 'Sistema',
        'conversion': None,             # Ya en porcentaje
        'batch_size': 365,
        '_descripcion': 'Porcentaje volumen útil embalses — mejora EMBALSES_PCT',
    },
    {
        'metric': 'CapaUtilDiarEner',
        'entity': 'Sistema',
        'conversion': 'kWh_a_GWh',     # API devuelve kWh
        'batch_size': 365,
        '_descripcion': 'Capacidad útil diaria de energía — mejora EMBALSES',
    },
    {
        'metric': 'Gene',
        'entity': 'Sistema',
        'conversion': 'horas_a_diario',  # Values_Hour01-24 en kWh → sumar → GWh
        'batch_size': 90,               # Batches más pequeños (horario es más pesado)
        '_descripcion': 'Generación total — mejora GENE_TOTAL ensemble',
    },
    # PrecEsca: mecanismo introducido ~2012 en Colombia; no existe en datos 2000-2011.
    # No se incluye aquí; el modelo PRECIO_ESCASEZ ya tiene datos suficientes desde 2020.
]


def main():
    parser = argparse.ArgumentParser(
        description='Backfill histórico XM para predicciones (2000-2019)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--desde', default='2000-01-01',
        help='Fecha inicio descarga (YYYY-MM-DD). Default: 2000-01-01',
    )
    parser.add_argument(
        '--hasta', default='2019-12-31',
        help='Fecha fin descarga (YYYY-MM-DD). Default: 2019-12-31',
    )
    parser.add_argument(
        '--metrica', default=None,
        help='Solo descargar esta métrica (ej: AporEner). Default: todas',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Solo verifica disponibilidad API y conta filas — no inserta en BD',
    )
    args = parser.parse_args()

    # ── Verificar pydataxm disponible ──
    try:
        from pydataxm.pydataxm import ReadDB  # noqa: F401
    except ImportError:
        logger.error("pydataxm no disponible: pip install pydataxm")
        sys.exit(1)

    from etl.etl_xm_to_postgres import poblar_metrica
    from pydataxm.pydataxm import ReadDB

    try:
        api_obj = ReadDB()
    except Exception as ex:
        logger.error(f"No se pudo inicializar pydataxm ReadDB: {ex}")
        sys.exit(1)

    metricas = METRICAS_BACKFILL
    if args.metrica:
        metricas = [m for m in METRICAS_BACKFILL if m['metric'] == args.metrica]
        if not metricas:
            validas = [m['metric'] for m in METRICAS_BACKFILL]
            logger.error(f"Métrica '{args.metrica}' no reconocida. Opciones: {validas}")
            sys.exit(1)

    logger.info("=" * 68)
    logger.info("BACKFILL HISTÓRICO XM → PostgreSQL")
    logger.info(f"Rango:    {args.desde} → {args.hasta}")
    logger.info(f"Métricas: {[m['metric'] for m in metricas]}")
    logger.info(f"Modo:     {'DRY-RUN (solo verifica)' if args.dry_run else 'REAL (inserta en BD)'}")
    logger.info("=" * 68)

    if args.dry_run:
        # En dry-run: solo verificar que la API responde con datos reales
        from datetime import date
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()
        logger.info("\nVerificando disponibilidad en API XM:")
        for cfg in metricas:
            m, e = cfg['metric'], cfg['entity']
            try:
                df = api.request_data(m, e, date(2005, 6, 1), date(2005, 6, 7))
                n = len(df) if df is not None else 0
                status = f"✓ {n} filas/semana" if n > 0 else "✗ sin datos"
            except Exception as ex:
                status = f"✗ error: {ex}"
            logger.info(f"  {m:25s}/{e:10s}: {status}")
        logger.info("\nDry-run completo. Ejecutar sin --dry-run para descargar.")
        return

    t_total = time.time()
    resumen = {}

    for cfg in metricas:
        m = cfg['metric']
        logger.info(f"\n{'─'*68}")
        logger.info(f"📥 {m}/{cfg['entity']} — {cfg.get('_descripcion','')}")

        # poblar_metrica usa los parámetros con nombre 'metric', 'entity', etc.
        # y soporta fecha_inicio_custom / fecha_fin_custom
        t0 = time.time()
        try:
            n = poblar_metrica(
                api_obj,
                cfg,
                usar_timeout=False,
                fecha_inicio_custom=args.desde,
                fecha_fin_custom=args.hasta,
            )
            elapsed = time.time() - t0
            logger.info(f"   ✅ {n} registros insertados ({elapsed/60:.1f} min)")
            resumen[m] = n
        except Exception as ex:
            elapsed = time.time() - t0
            logger.error(f"   ❌ Error en {m}: {ex} ({elapsed:.0f}s)")
            resumen[m] = f"ERROR: {ex}"

    elapsed_total = time.time() - t_total

    # ── Resumen final ──
    logger.info(f"\n\n{'═'*68}")
    logger.info(f"✅ Backfill completado en {elapsed_total/60:.1f} minutos")
    logger.info("─" * 68)
    for metrica, res in resumen.items():
        logger.info(f"  {metrica:25s}: {res}")

    # ── Estado BD post-backfill ──
    try:
        import psycopg2
        from core.config import settings
        params = {'host': settings.POSTGRES_HOST, 'port': settings.POSTGRES_PORT,
                  'database': settings.POSTGRES_DB, 'user': settings.POSTGRES_USER}
        if settings.POSTGRES_PASSWORD:
            params['password'] = settings.POSTGRES_PASSWORD
        conn = psycopg2.connect(**params)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT metrica, COUNT(DISTINCT fecha) as dias,
                       MIN(fecha)::date, MAX(fecha)::date
                FROM sector_energetico.metrics
                WHERE entidad = 'Sistema'
                  AND metrica IN ('Gene','AporEner','PorcVoluUtilDiar',
                                  'CapaUtilDiarEner','PrecEsca')
                GROUP BY metrica ORDER BY metrica
            """)
            rows = cur.fetchall()
        conn.close()
        logger.info("\n📊 Estado BD post-backfill:")
        logger.info("─" * 68)
        for r in rows:
            logger.info(f"  {str(r[0]):25s}: {r[1]:6d} días ({r[2]} → {r[3]})")
    except Exception as ex:
        logger.warning(f"No se pudo leer estado BD: {ex}")

    logger.info("\n📌 Próximo paso — re-entrenar predicciones con histórico extendido:")
    logger.info("   python scripts/train_predictions_sector_energetico.py --lgbm_aportes")
    logger.info("   (o esperar la tarea semanal domingo 02:00 AM)")


if __name__ == '__main__':
    main()
