#!/usr/bin/env python3
"""
ETL: IDEAM → PostgreSQL
Portal Energético MME — FASE 18
================================

Descarga datos meteorológicos del IDEAM (datos.gov.co) y los almacena
en la tabla `metrics` de PostgreSQL, listos para ser usados como regresores
en los modelos de predicción (Eólica, Solar, APORTES_HIDRICOS).

Variables:
  - IDEAM_VelViento        Velocidad del viento (m/s) — La Guajira
  - IDEAM_VelViento_Nac    Velocidad del viento nacional (m/s)
  - IDEAM_Precipitacion    Precipitación (mm) — cuencas hídricas
  - IDEAM_Temperatura      Temperatura del aire (°C) — zonas solares
  - IDEAM_Temperatura_Nac  Temperatura nacional (°C)

Ejecución:
    Manual:       python3 etl/etl_ideam.py
    Solo viento:  python3 etl/etl_ideam.py --solo viento
    Backfill:     python3 etl/etl_ideam.py --dias 365
    Cron:         Incluir en actualizar_predicciones.sh (antes de predicciones)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import time
from datetime import datetime, timedelta, date

from infrastructure.database.manager import db_manager
from infrastructure.external.ideam_service import (
    ESTACIONES_EOLICA,
    ESTACIONES_EOLICA_PARQUES,
    ESTACIONES_SOLAR,
    ESTACIONES_HIDRO,
    fetch_and_aggregate,
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
            os.path.join(LOG_DIR, f'etl_ideam_{datetime.now():%Y%m%d}.log'),
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger('etl_ideam')


# ---------------------------------------------------------------------------
# PIPELINE CONFIG
# ---------------------------------------------------------------------------
# Each entry defines: dataset_key, departamentos, metrica_bd, entidad, unidad
# Multiple entries per dataset_key allow zone-specific storage.

ETL_PIPELINE = [
    # --- VIENTO ---
    {
        'nombre': 'Viento La Guajira',
        'dataset_key': 'velocidad_viento',
        'departamentos': ESTACIONES_EOLICA['departamentos'],
        'metrica_bd': 'IDEAM_VelViento',
        'entidad': 'IDEAM',
        'recurso': 'LA_GUAJIRA',
        'unidad': 'm/s',
    },
    {
        # FASE 28: Solo URIBIA — municipio con los parques reales (Jepirachi, Guajira I/II)
        'nombre': 'Viento Alta Guajira (Parques)',
        'dataset_key': 'velocidad_viento',
        'departamentos': ESTACIONES_EOLICA_PARQUES['departamentos'],
        'municipios': ESTACIONES_EOLICA_PARQUES['municipios'],
        'metrica_bd': 'IDEAM_VelViento',
        'entidad': 'IDEAM',
        'recurso': 'EOLICA_ALTA_GUAJIRA',
        'unidad': 'm/s',
    },
    {
        'nombre': 'Viento Nacional',
        'dataset_key': 'velocidad_viento',
        'departamentos': ESTACIONES_EOLICA['departamentos']
                         + ESTACIONES_SOLAR['departamentos'],
        'metrica_bd': 'IDEAM_VelViento',
        'entidad': 'IDEAM',
        'recurso': 'NACIONAL',
        'unidad': 'm/s',
    },
    # --- PRECIPITACIÓN ---
    {
        'nombre': 'Precipitación Cuencas',
        'dataset_key': 'precipitacion',
        'departamentos': ESTACIONES_HIDRO['departamentos'],
        'metrica_bd': 'IDEAM_Precipitacion',
        'entidad': 'IDEAM',
        'recurso': 'CUENCAS_HIDRO',
        'unidad': 'mm',
    },
    # --- TEMPERATURA ---
    {
        'nombre': 'Temperatura Zonas Solares',
        'dataset_key': 'temperatura',
        'departamentos': ESTACIONES_SOLAR['departamentos'],
        'metrica_bd': 'IDEAM_Temperatura',
        'entidad': 'IDEAM',
        'recurso': 'ZONAS_SOLAR',
        'unidad': '°C',
    },
    {
        'nombre': 'Temperatura Nacional',
        'dataset_key': 'temperatura',
        'departamentos': ESTACIONES_SOLAR['departamentos']
                         + ESTACIONES_HIDRO['departamentos'],
        'metrica_bd': 'IDEAM_Temperatura',
        'entidad': 'IDEAM',
        'recurso': 'NACIONAL',
        'unidad': '°C',
    },
]

# Mapping for --solo flag
SOLO_MAP = {
    'viento': ['Viento La Guajira', 'Viento Alta Guajira (Parques)', 'Viento Nacional'],
    'viento_guajira': ['Viento La Guajira'],
    'viento_alta_guajira': ['Viento Alta Guajira (Parques)'],
    'viento_nacional': ['Viento Nacional'],
    'precipitacion': ['Precipitación Cuencas'],
    'temperatura': ['Temperatura Zonas Solares', 'Temperatura Nacional'],
}


def run_etl_pipeline(
    dias_atras: int = 30,
    filtro_nombres: list = None,
    timeout: int = 120,
) -> dict:
    """
    Ejecuta el pipeline ETL IDEAM → PostgreSQL.

    Args:
        dias_atras: Días hacia atrás a descargar
        filtro_nombres: Si se especifica, solo ejecuta estos nombres de pipeline
        timeout: Timeout por request HTTP

    Returns:
        dict con estadísticas {nombre: {'status', 'registros', 'dias', 'tiempo_s'}}
    """
    fecha_inicio = date.today() - timedelta(days=dias_atras)
    fecha_fin = date.today()
    resultados = {}

    pipeline = ETL_PIPELINE
    if filtro_nombres:
        pipeline = [p for p in ETL_PIPELINE if p['nombre'] in filtro_nombres]

    logger.info("=" * 70)
    logger.info(f"🌍 IDEAM ETL — {fecha_inicio} → {fecha_fin} ({dias_atras} días)")
    logger.info(f"   Pipelines: {len(pipeline)}")
    logger.info("=" * 70)

    total_registros = 0
    t_total = time.time()

    for i, cfg in enumerate(pipeline, 1):
        nombre = cfg['nombre']
        logger.info(f"\n--- [{i}/{len(pipeline)}] {nombre} ---")
        t0 = time.time()

        try:
            df_daily = fetch_and_aggregate(
                dataset_key=cfg['dataset_key'],
                departamentos=cfg['departamentos'],
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                timeout=timeout,
                municipios=cfg.get('municipios'),  # FASE 28: filtro por municipio opcional
            )

            if df_daily is None or df_daily.empty:
                logger.warning(f"  ⚠️ Sin datos para {nombre}")
                resultados[nombre] = {
                    'status': 'SIN_DATOS', 'registros': 0,
                    'dias': 0, 'tiempo_s': time.time() - t0,
                }
                continue

            # Preparar tuplas para upsert: (fecha, metrica, entidad, recurso, valor, unidad)
            # NOTA: valor_gwh > 0 se usa en queries de regresores, así que
            # reemplazamos 0.0 exacto con epsilon para que no se filtren
            # días sin precipitación o sin viento.
            metrics_to_insert = []
            for _, row in df_daily.iterrows():
                val = float(row['valor'])
                if val == 0.0:
                    val = 0.0001  # epsilon para pasar filtro > 0
                metrics_to_insert.append((
                    row['fecha'].strftime('%Y-%m-%d'),
                    cfg['metrica_bd'],
                    cfg['entidad'],
                    cfg['recurso'],
                    val,
                    cfg['unidad'],
                ))

            n_inserted = db_manager.upsert_metrics_bulk(metrics_to_insert)
            elapsed = time.time() - t0
            total_registros += n_inserted

            logger.info(f"  ✅ {nombre}: {n_inserted} registros → PostgreSQL "
                        f"({elapsed:.1f}s)")

            resultados[nombre] = {
                'status': 'OK',
                'registros': n_inserted,
                'dias': len(df_daily),
                'tiempo_s': elapsed,
                'valor_medio': df_daily['valor'].mean(),
                'valor_std': df_daily['valor'].std(),
            }

        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"  ❌ Error en {nombre}: {e}", exc_info=True)
            resultados[nombre] = {
                'status': 'ERROR',
                'registros': 0,
                'dias': 0,
                'tiempo_s': elapsed,
                'error': str(e),
            }

        # Rate limiting entre pipelines
        if i < len(pipeline):
            time.sleep(2)

    elapsed_total = time.time() - t_total

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 RESUMEN ETL IDEAM")
    logger.info("=" * 70)
    for nombre, res in resultados.items():
        status_icon = {'OK': '✅', 'SIN_DATOS': '⚠️', 'ERROR': '❌'}.get(
            res['status'], '?')
        logger.info(f"  {status_icon} {nombre:30s} | {res['registros']:5d} regs "
                    f"| {res['dias']:4d} días | {res['tiempo_s']:.1f}s")
    logger.info(f"\n  Total: {total_registros} registros en {elapsed_total:.1f}s")

    return resultados


def verificar_datos_ideam():
    """Verifica datos IDEAM existentes en PostgreSQL."""
    logger.info("\n📋 Verificación de datos IDEAM en PostgreSQL:")

    query = """
    SELECT metrica, recurso, COUNT(*) as n,
           MIN(fecha) as desde, MAX(fecha) as hasta,
           AVG(valor_gwh) as media, STDDEV(valor_gwh) as std
    FROM metrics
    WHERE metrica LIKE 'IDEAM_%'
    GROUP BY metrica, recurso
    ORDER BY metrica, recurso
    """
    try:
        df = db_manager.query_df(query)
        if df.empty:
            logger.info("  ⚠️ No hay datos IDEAM en la BD")
            return

        for _, row in df.iterrows():
            logger.info(
                f"  {row['metrica']:25s} | {row['recurso']:15s} | "
                f"{row['n']:5d} días | {row['desde']} → {row['hasta']} | "
                f"μ={row['media']:.2f} σ={row['std']:.2f}"
            )
    except Exception as e:
        logger.error(f"  ❌ Error verificando: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def run_etl_backfill(
    dias_atras: int,
    chunk_dias: int = 30,
    filtro_nombres: list = None,
    timeout: int = 120,
) -> dict:
    """
    Ejecuta backfill dividiendo el rango en trozos para evitar timeouts.

    La API de datos.gov.co admite ~30-60 días en una sola query antes de
    timeout. Para rangos largos (> 60 días) se segmenta automáticamente.

    Args:
        dias_atras:    Días totales hacia atrás a cubrir
        chunk_dias:    Tamaño de cada trozo (default: 30 días)
        filtro_nombres: Filtro de pipelines (mismo que run_etl_pipeline)
        timeout:       Timeout HTTP por chunk

    Returns:
        dict acumulado {nombre: {'status', 'registros', ...}}
    """
    from datetime import date, timedelta

    hoy = date.today()
    fecha_min = hoy - timedelta(days=dias_atras)

    # Construir lista de rangos [inicio, fin] en orden cronológico
    rangos = []
    cursor = fecha_min
    while cursor < hoy:
        fin = min(cursor + timedelta(days=chunk_dias - 1), hoy)
        rangos.append((cursor, fin))
        cursor = fin + timedelta(days=1)

    logger.info("=" * 70)
    logger.info(f"🗓️  IDEAM BACKFILL — {fecha_min} → {hoy}")
    logger.info(f"   Total días: {dias_atras} | Chunks: {len(rangos)} × {chunk_dias}d")
    logger.info("=" * 70)

    # Acumular resultados por nombre
    totales: dict = {}
    pipeline = ETL_PIPELINE
    if filtro_nombres:
        pipeline = [p for p in ETL_PIPELINE if p['nombre'] in filtro_nombres]

    for idx, (inicio, fin) in enumerate(rangos, 1):
        dias_chunk = (fin - inicio).days + 1
        logger.info(f"\n── Chunk {idx}/{len(rangos)}: {inicio} → {fin} ({dias_chunk}d) ──")

        for cfg in pipeline:
            nombre = cfg['nombre']
            try:
                df_daily = fetch_and_aggregate(
                    dataset_key=cfg['dataset_key'],
                    departamentos=cfg['departamentos'],
                    fecha_inicio=inicio,
                    fecha_fin=fin,
                    timeout=timeout,
                    municipios=cfg.get('municipios'),  # FASE 28: filtro municipio
                )

                if df_daily is None or df_daily.empty:
                    logger.warning(f"  ⚠️ Sin datos: {nombre} [{inicio}→{fin}]")
                    if nombre not in totales:
                        totales[nombre] = {'status': 'SIN_DATOS', 'registros': 0}
                    continue

                metrics_to_insert = []
                for _, row in df_daily.iterrows():
                    val = float(row['valor'])
                    if val == 0.0:
                        val = 0.0001
                    metrics_to_insert.append((
                        row['fecha'].strftime('%Y-%m-%d'),
                        cfg['metrica_bd'],
                        cfg['entidad'],
                        cfg['recurso'],
                        val,
                        cfg['unidad'],
                    ))

                n = db_manager.upsert_metrics_bulk(metrics_to_insert)
                logger.info(f"  ✅ {nombre}: +{n} registros")

                if nombre not in totales:
                    totales[nombre] = {'status': 'OK', 'registros': 0}
                totales[nombre]['registros'] += n
                totales[nombre]['status'] = 'OK'

            except Exception as e:
                logger.error(f"  ❌ {nombre} [{inicio}→{fin}]: {e}")
                if nombre not in totales:
                    totales[nombre] = {'status': 'ERROR', 'registros': 0, 'error': str(e)}

        # Pausa entre chunks para no saturar la API
        if idx < len(rangos):
            time.sleep(3)

    # Resumen
    logger.info("\n" + "=" * 70)
    logger.info("📊 RESUMEN BACKFILL IDEAM")
    for nombre, res in totales.items():
        icon = {'OK': '✅', 'SIN_DATOS': '⚠️', 'ERROR': '❌'}.get(res['status'], '?')
        logger.info(f"  {icon} {nombre:30s} | {res['registros']:6d} registros totales")
    logger.info("=" * 70)

    return totales


def main():
    parser = argparse.ArgumentParser(
        description='ETL IDEAM → PostgreSQL (FASE 18)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python etl/etl_ideam.py                         # Últimos 30 días
  python etl/etl_ideam.py --dias 30 --solo viento # Solo viento 30 días
  python etl/etl_ideam.py --backfill --dias 730   # Backfill 2 años en chunks
  python etl/etl_ideam.py --backfill --dias 730 --solo viento --chunk_dias 30
  python etl/etl_ideam.py --solo precipitacion
  python etl/etl_ideam.py --verificar
        """,
    )
    parser.add_argument('--dias', type=int, default=30,
                        help='Días hacia atrás a descargar (default: 30)')
    parser.add_argument('--solo', type=str, choices=['viento', 'viento_guajira', 'viento_alta_guajira', 'viento_nacional', 'precipitacion', 'temperatura'],
                        help='Solo descargar una variable')
    parser.add_argument('--timeout', type=int, default=120,
                        help='Timeout HTTP en segundos (default: 120)')
    parser.add_argument('--verificar', action='store_true',
                        help='Solo verificar datos existentes en BD')
    parser.add_argument('--backfill', action='store_true',
                        help='Modo backfill: divide el rango en chunks para evitar timeouts')
    parser.add_argument('--chunk_dias', type=int, default=30,
                        help='Tamaño de chunk en días para --backfill (default: 30)')

    args = parser.parse_args()

    if args.verificar:
        verificar_datos_ideam()
        return

    filtro = SOLO_MAP.get(args.solo) if args.solo else None

    if args.backfill:
        resultados = run_etl_backfill(
            dias_atras=args.dias,
            chunk_dias=args.chunk_dias,
            filtro_nombres=filtro,
            timeout=args.timeout,
        )
    else:
        resultados = run_etl_pipeline(
            dias_atras=args.dias,
            filtro_nombres=filtro,
            timeout=args.timeout,
        )

    # Exit code: 0 si al menos un pipeline exitoso
    any_ok = any(r['status'] == 'OK' for r in resultados.values())
    sys.exit(0 if any_ok else 1)


if __name__ == '__main__':
    main()
