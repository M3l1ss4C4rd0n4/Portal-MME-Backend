#!/usr/bin/env python3
"""
Backfill maestro: corrige el bug de 1-fila/día en 49 métricas con múltiples recursos.

El ETL histórico guardaba solo 1 recurso/agente/río/embalse por día para TODAS las
métricas desagregadas. Este script repara cada métrica afectada desde la API XM.

Métricas con entidad Sistema (totales correctos) NO se tocan — solo las desagregadas.

Orden de ejecución (por impacto en tableros):
  GRUPO 1 — Hidrología:     AporEner/Rio, AporCaudal/Rio, AporCaudalMediHist/Rio,
                             PorcApor/Rio, AporEnerMediHist/Rio
  GRUPO 2 — Embalses:       VoluUtilDiarEner/Embalse, CapaUtilDiarEner/Embalse,
                             PorcVoluUtilDiar/Embalse, CapaUtilDiarMasa/Embalse,
                             VoluUtilDiarMasa/Embalse, VolTurbMasa/Embalse
  GRUPO 3 — Generación:     GeneFueraMerito/Recurso, GeneProgDesp/Recurso,
                             GeneProgRedesp/Recurso, GeneSeguridad/Recurso,
                             GeneIdea/Recurso, EmisionesCO2Eq/Recurso
  GRUPO 4 — Demanda:        DemaCome/Agente, DemaReal/Agente, DemaRealReg/Agente,
                             DemaRealNoReg/Agente
  GRUPO 5 — Disponibilidad: DispoCome/Recurso, DispoDeclarada/Recurso, DispoReal/Recurso
  GRUPO 6 — Comercial:      RecoNegEner/Recurso, RecoPosEner/Recurso,
                             RecoNegMoneda/Recurso, RecoPosMoneda/Recurso,
                             PerdidasEner/Agente, PerdidasEnerReg/Agente,
                             PerdidasEnerNoReg/Agente, PrecCargConf/Recurso
  GRUPO 7 — Residual:       VertEner/Embalse, VertMasa/Embalse,
                             TempAmbSolar/Recurso, TempPanel/Recurso,
                             ConsCombAprox/RecursoComb, PrecOferDesp/Recurso,
                             CompBolsaTIEEner/Agente, VentBolsaTIEEner/Agente,
                             ComContRespEner/Recurso,
                             DemaComeNoReg/Agente, DemaComeNoReg/CIIU,
                             CompBolsNaciEner/Agente, VentContEner/Agente,
                             CompContEner/Agente

Uso:
    python scripts/backfill_maestro.py                          # todos los grupos
    python scripts/backfill_maestro.py --grupo 1                # solo hidrología
    python scripts/backfill_maestro.py --grupo 1,2              # hidrología + embalses
    python scripts/backfill_maestro.py --metrica AporEner:Rio   # métrica individual
    python scripts/backfill_maestro.py --dry-run                # sin escribir
    python scripts/backfill_maestro.py --desde 2023-01-01       # desde fecha
    python scripts/backfill_maestro.py --solo-limpiar           # solo borra datos malos
"""

import sys
import os
import argparse
import logging
import time
import psycopg2
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOG_FILE = '/home/admonctrlxm/server/logs/backfill_maestro.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)]
)
logger = logging.getLogger(__name__)

DB_PARAMS = dict(dbname='portal_energetico', user='postgres', host='localhost')

# Fecha de corte: a partir de aquí los datos nuevos son correctos (ETL fijo)
FECHA_CORTE = date(2026, 3, 13)
FECHA_INICIO_DEFAULT = date(2020, 1, 1)

# ─────────────────────────────────────────────────────────────────────────────
# Definición de grupos de métricas
# ─────────────────────────────────────────────────────────────────────────────
GRUPOS = {
    1: {
        'nombre': 'Hidrología - Ríos',
        'descripcion': 'Aportes energéticos y caudales por río (tablero hidrología)',
        'metricas': [
            # (metric, entity, batch_dias, fecha_inicio_override)
            ('AporEner',         'Rio',   15, FECHA_INICIO_DEFAULT),
            ('AporCaudal',       'Rio',   15, FECHA_INICIO_DEFAULT),
            ('AporEnerMediHist', 'Rio',   15, FECHA_INICIO_DEFAULT),
            ('AporCaudalMediHist','Rio',  15, FECHA_INICIO_DEFAULT),
            ('PorcApor',         'Rio',   15, FECHA_INICIO_DEFAULT),
        ]
    },
    2: {
        'nombre': 'Hidrología - Embalses',
        'descripcion': 'Volúmenes y capacidades por embalse',
        'metricas': [
            ('VoluUtilDiarEner',  'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('CapaUtilDiarEner',  'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('PorcVoluUtilDiar',  'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('CapaUtilDiarMasa',  'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('VoluUtilDiarMasa',  'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('VolTurbMasa',       'Embalse', 30, FECHA_INICIO_DEFAULT),
            ('DescMasa',          'Embalse', 30, FECHA_INICIO_DEFAULT),
        ]
    },
    3: {
        'nombre': 'Generación por recurso',
        'descripcion': 'Generación fuera de mérito, ideal, programada, seguridad, emisiones',
        'metricas': [
            ('GeneFueraMerito',  'Recurso', 15, date(2021, 1, 1)),
            ('GeneProgDesp',     'Recurso', 15, date(2021, 1, 1)),
            ('GeneProgRedesp',   'Recurso', 15, date(2021, 1, 1)),
            ('GeneSeguridad',    'Recurso', 15, FECHA_INICIO_DEFAULT),
            ('GeneIdea',         'Recurso', 15, date(2021, 1, 1)),
            ('EmisionesCO2Eq',   'Recurso', 30, date(2021, 1, 1)),
        ]
    },
    4: {
        'nombre': 'Demanda por agente',
        'descripcion': 'Demanda comercial y real desagregada por agente (tablero distribución)',
        'metricas': [
            ('DemaCome',      'Agente', 7, FECHA_INICIO_DEFAULT),
            ('DemaReal',      'Agente', 7, FECHA_INICIO_DEFAULT),
            ('DemaRealReg',   'Agente', 7, FECHA_INICIO_DEFAULT),
            ('DemaRealNoReg', 'Agente', 7, FECHA_INICIO_DEFAULT),
        ]
    },
    5: {
        'nombre': 'Disponibilidad por recurso',
        'descripcion': 'Disponibilidad comercial, declarada y real por central',
        'metricas': [
            ('DispoCome',      'Recurso', 15, FECHA_INICIO_DEFAULT),
            ('DispoDeclarada', 'Recurso', 15, FECHA_INICIO_DEFAULT),
            ('DispoReal',      'Recurso', 15, FECHA_INICIO_DEFAULT),
        ]
    },
    6: {
        'nombre': 'Mercado - Recoveries y pérdidas',
        'descripcion': 'Recuperos económicos, pérdidas y cargo por confiabilidad',
        'metricas': [
            ('RecoNegEner',      'Recurso', 30, date(2021, 1, 1)),
            ('RecoPosEner',      'Recurso', 30, date(2021, 1, 1)),
            ('RecoNegMoneda',    'Recurso', 30, date(2021, 1, 1)),
            ('RecoPosMoneda',    'Recurso', 30, date(2021, 1, 1)),
            ('PerdidasEner',     'Agente',  30, date(2021, 1, 1)),
            ('PerdidasEnerReg',  'Agente',  30, date(2021, 1, 1)),
            ('PerdidasEnerNoReg','Agente',  30, date(2021, 1, 1)),
            ('PrecCargConf',     'Recurso', 30, date(2021, 1, 1)),
        ]
    },
    7: {
        'nombre': 'Residual - Vertimientos, solares, TIE y mercado',
        'descripcion': 'Combos con bug no cubiertos por G1-G6: vertimientos, temperaturas, TIE, demanda no regulada, compras/ventas',
        'metricas': [
            # Vertimientos por embalse
            ('VertEner',         'Embalse',     30, date(2021, 1, 1)),
            ('VertMasa',         'Embalse',     30, date(2021, 1, 1)),
            # Temperatura solar (parques fotovoltaicos)
            ('TempAmbSolar',     'Recurso',     30, date(2021, 1, 1)),
            ('TempPanel',        'Recurso',     30, date(2021, 1, 1)),
            # Consumo de combustible
            ('ConsCombAprox',    'RecursoComb', 30, date(2021, 1, 1)),
            # Precios oferta despacho
            ('PrecOferDesp',     'Recurso',     30, date(2021, 1, 1)),
            # Transacciones internacionales de energía (TIE)
            ('CompBolsaTIEEner', 'Agente',      15, date(2021, 1, 1)),
            ('VentBolsaTIEEner', 'Agente',      15, date(2021, 1, 1)),
            # Responsabilidad contratos (COP → MCOP)
            ('ComContRespEner',  'Recurso',     30, date(2021, 1, 1)),
            # Demanda no regulada por agente y CIIU
            ('DemaComeNoReg',    'Agente',       7, date(2021, 1, 1)),
            ('DemaComeNoReg',    'CIIU',        15, date(2021, 1, 1)),
            # Compras y ventas en bolsa y contratos
            ('CompBolsNaciEner', 'Agente',      15, date(2021, 1, 1)),
            ('VentContEner',     'Agente',      15, date(2021, 1, 1)),
            ('CompContEner',     'Agente',      15, date(2021, 1, 1)),
        ]
    },
    8: {
        'nombre': 'Residual 2 - Emisiones, costos, desviaciones, demanda y TIE',
        'descripcion': 'Combos con bug no cubiertos por G1-G7: emisiones CO2/CH4/N2O, combustibles, costos rec, desviaciones, demanda OR/regulada, irradiancia, exportaciones, TIE moneda y contratos SICEP/Reg/NoReg',
        'metricas': [
            # Emisiones por recurso de combustión
            ('EmisionesCO2',      'RecursoComb', 30, date(2021, 1, 1)),
            ('EmisionesCH4',      'RecursoComb', 30, date(2021, 1, 1)),
            ('EmisionesN2O',      'RecursoComb', 30, date(2021, 1, 1)),
            # Consumo de combustible (MBTU)
            ('ConsCombustibleMBTU', 'Combustible', 30, date(2021, 1, 1)),
            ('ConsCombustibleMBTU', 'Recurso',     30, date(2021, 1, 1)),
            # Costos de redespacho por área y subárea
            ('CostRecPos',        'Area',        30, date(2021, 1, 1)),
            ('CostRecNeg',        'Area',        30, date(2021, 1, 1)),
            ('CostRecPos',        'SubArea',     30, date(2021, 1, 1)),
            ('CostRecNeg',        'SubArea',     30, date(2021, 1, 1)),
            # Desviaciones por recurso
            ('DesvEner',          'Recurso',     30, date(2021, 1, 1)),
            ('DesvMoneda',        'Recurso',     30, date(2021, 1, 1)),
            ('VentContRespEner',  'Recurso',     30, date(2021, 1, 1)),
            ('DesvGenVariableDesp',   'Recurso', 30, date(2021, 1, 1)),
            ('DesvGenVariableRedesp', 'Recurso', 30, date(2021, 1, 1)),
            # Demanda no atendida por área y subárea
            ('DemaNoAtenProg',    'Area',        30, FECHA_INICIO_DEFAULT),
            ('DemaNoAtenNoProg',  'Area',        30, FECHA_INICIO_DEFAULT),
            ('DemaNoAtenProg',    'Subarea',     30, date(2021, 1, 1)),
            ('DemaNoAtenNoProg',  'Subarea',     30, date(2021, 1, 1)),
            # Demanda OR y demanda comercial regulada
            ('DemaOR',            'Agente',       7, date(2021, 1, 1)),
            ('DemaCome',          'MercadoComercializacion', 7, date(2021, 1, 1)),
            ('DemaComeReg',       'Agente',       7, date(2021, 1, 1)),
            # Compras/ventas contratos SICEP, regulados y no regulados
            ('CompContEnerSICEP', 'Agente',      15, date(2021, 1, 1)),
            ('VentContEnerSICEP', 'Agente',      15, date(2021, 1, 1)),
            ('CompContEnerReg',   'Agente',      15, date(2021, 1, 1)),
            ('CompContEnerNoReg', 'Agente',      15, date(2021, 1, 1)),
            ('VentBolsNaciEner',  'Agente',      15, date(2021, 1, 1)),
            # TIE en moneda (COP → MCOP)
            ('VentBolsaTIEMoneda','Agente',      15, date(2021, 1, 1)),
            ('CompBolsaTIEMoneda','Agente',      15, date(2021, 1, 1)),
            # Irradiancia solar (parques FV) — datos hasta 2025-12
            ('IrrPanel',          'Recurso',     30, date(2021, 1, 1)),
            ('IrrGlobal',         'Recurso',     30, date(2021, 1, 1)),
            # Exportaciones de energía (métricas nuevas 2025)
            ('ExpoEner',          'Enlace',      30, date(2025, 10, 1)),
            ('ExpoMoneda',        'Enlace',      30, date(2025, 12, 1)),
            # Índice de recurso marginal y precio oferta ideal
            ('IndRecMargina',     'Recurso',     30, date(2021, 1, 1)),
            ('PrecOferIdeal',     'Recurso',     30, date(2021, 1, 1)),
        ]
    },
}


def contar_filas_bug(metric, entity, fecha_corte):
    """Conta filas históricas con el bug (1 recurso/día)."""
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT fecha), COUNT(DISTINCT recurso) "
        "FROM metrics WHERE metrica=%s AND entidad=%s AND fecha < %s",
        (metric, entity, fecha_corte)
    )
    cnt, dias, recursos = cur.fetchone()
    conn.close()
    return cnt, dias, recursos


def limpiar_filas_bug(metric, entity, fecha_corte, dry_run=False):
    """Borra las filas históricas corruptas."""
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM metrics WHERE metrica=%s AND entidad=%s AND fecha < %s",
        (metric, entity, fecha_corte)
    )
    cnt = cur.fetchone()[0]
    if cnt == 0:
        conn.close()
        return 0
    if not dry_run:
        cur.execute(
            "DELETE FROM metrics WHERE metrica=%s AND entidad=%s AND fecha < %s",
            (metric, entity, fecha_corte)
        )
        conn.commit()
    conn.close()
    return cnt


def backfill_metrica(metric, entity, batch_dias, fecha_inicio, fecha_fin, dry_run=False):
    """Repuebla una métrica desde la API XM.

    poblar_metrica() maneja el batching internamente; solo pasamos el rango
    completo y batch_size. Eliminamos el loop externo para evitar doble batching.
    """
    from etl.etl_xm_to_postgres import poblar_metrica
    from pydataxm.pydataxm import ReadDB

    dias_total = (fecha_fin - fecha_inicio).days + 1
    batches_aprox = (dias_total + batch_dias - 1) // batch_dias
    logger.info(f"  📡 Llamando poblar_metrica | {fecha_inicio}→{fecha_fin} | "
                f"{dias_total} días en ~{batches_aprox} batches de {batch_dias}d.")

    if dry_run:
        logger.info(f"  [DRY-RUN] Sin ejecutar.")
        return 0

    obj_api = ReadDB()
    config = {
        'metric': metric,
        'entity': entity,
        'batch_size': batch_dias,
        'dias_history': dias_total,
        'conversion': _detectar_conversion(metric),
    }

    try:
        n = poblar_metrica(
            obj_api, config,
            fecha_inicio_custom=str(fecha_inicio),
            fecha_fin_custom=str(fecha_fin),
            usar_timeout=False,       # backfill puede tardar más que el timeout normal
        )
        logger.info(f"  ✅ Total insertado por poblar_metrica: {n} registros")
        return n
    except Exception as e:
        logger.error(f"  ❌ poblar_metrica falló para {metric}/{entity}: {e}")
        return 0


def _detectar_conversion(metric):
    """Devuelve el tipo de conversión correcto para cada métrica.

    Nombres exactos usados por convertir_unidades() en etl_xm_to_postgres.py:
      'Wh_a_GWh'       — API retorna en Wh diarios (ej. AporEner/Rio, VertEner/Embalse)
      'kWh_a_GWh'      — API retorna en kWh diarios (ej. VoluUtilDiarEner/Embalse)
      'horas_a_diario' — API retorna 24 columnas horarias en kWh → suma → GWh
      'COP_a_MCOP'     — API retorna COP diarios → dividir entre 1,000,000
      None             — Sin conversión (m³/s, %, Hm³, MW nativo, $/kWh nativo, °C)
    """
    # Aportes de energía y vertimientos (Wh diarios → GWh)
    if metric in {'AporEner', 'AporEnerMediHist', 'VertEner'}:
        return 'Wh_a_GWh'
    # Embalses energéticos (kWh diarios → GWh)
    if metric in {'VoluUtilDiarEner', 'CapaUtilDiarEner'}:
        return 'kWh_a_GWh'
    # Valores monetarios diarios (COP → Millones COP)
    if metric in {'ComContRespEner'}:
        return 'COP_a_MCOP'
    # Generación / demanda / pérdidas / disponibilidad / TIE (24 horas kWh → suma GWh/MW)
    if metric in {
        'Gene', 'GeneIdea', 'GeneFueraMerito', 'GeneProgDesp', 'GeneProgRedesp',
        'GeneSeguridad',
        'DemaCome', 'DemaReal', 'DemaRealReg', 'DemaRealNoReg', 'DemaComeNoReg',
        'PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg',
        'DispoCome', 'DispoReal', 'DispoDeclarada',
        'RecoNegEner', 'RecoPosEner', 'RecoNegMoneda', 'RecoPosMoneda',
        'ENFICC', 'ObligEnerFirme', 'DDVContratada',
        'CompBolsNaciEner', 'CompContEner', 'CompContEnerNoReg',
        'CompContEnerReg', 'CompContEnerSICEP',
        'VentBolsNaciEner', 'VentContEner', 'VentContEnerSICEP',
        'CompBolsaTIEEner', 'VentBolsaTIEEner',
    }:
        return 'horas_a_diario'
    # Resto: caudales (m³/s), masas (Hm³), porcentajes, precios ($/kWh), °C, etc.
    return None


def verificar_resultado(metric, entity):
    """Imprime resumen por año después del backfill."""
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute('''
        SELECT EXTRACT(YEAR FROM fecha) as anio,
               COUNT(*) as filas,
               COUNT(DISTINCT fecha) as dias,
               COUNT(DISTINCT recurso) as recursos,
               ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT fecha),0), 1) as fpd
        FROM metrics WHERE metrica=%s AND entidad=%s
        GROUP BY anio ORDER BY anio
    ''', (metric, entity))
    rows = cur.fetchall()
    conn.close()
    logger.info(f"\n  📊 Resultado final {metric}/{entity}:")
    for r in rows:
        fpd = float(r[4]) if r[4] else 0
        estado = "✅" if fpd > 3 else "⚠️ "
        logger.info(f"    {estado} {int(r[0])}: {r[1]} filas | {r[2]} días | {r[3]} recursos | {fpd:.1f} f/día")


def run_grupo(grupo_id, fecha_inicio_override, fecha_fin_override, dry_run, solo_limpiar):
    """Ejecuta el backfill para un grupo de métricas."""
    grupo = GRUPOS[grupo_id]
    logger.info(f"\n{'='*70}")
    logger.info(f"🔵 GRUPO {grupo_id}: {grupo['nombre']}")
    logger.info(f"   {grupo['descripcion']}")
    logger.info(f"{'='*70}")

    fecha_fin = fecha_fin_override or (FECHA_CORTE - timedelta(days=1))

    for metric, entity, batch_dias, fecha_inicio_default in grupo['metricas']:
        fi = fecha_inicio_override or fecha_inicio_default
        logger.info(f"\n{'─'*60}")
        logger.info(f"🎯 {metric}/{entity} | {fi} → {fecha_fin} | batch={batch_dias}d")

        # 1. Contar filas con bug
        cnt, dias, recursos = contar_filas_bug(metric, entity, FECHA_CORTE)
        if cnt == 0:
            logger.info(f"  ✅ Sin filas históricas corruptas — omitiendo.")
            continue
        fpd = cnt / max(dias, 1)
        logger.info(f"  ⚠️  Bug detectado: {cnt} filas, {dias} días, {recursos} recursos únicos, {fpd:.1f} f/día")

        if fpd > 3:
            logger.info(f"  ✅ f/día={fpd:.1f} ya parece correcto (>3). Omitiendo borrado.")
            continue

        # 2. Limpiar filas corruptas
        deleted = limpiar_filas_bug(metric, entity, FECHA_CORTE, dry_run)
        if dry_run:
            logger.info(f"  [DRY-RUN] Borraría {deleted} filas corruptas.")
        else:
            logger.info(f"  🗑️  Eliminadas {deleted} filas corruptas (f/día era {fpd:.1f}).")

        if solo_limpiar:
            continue

        # 3. Backfill desde API
        logger.info(f"  📡 Descargando desde API XM...")
        n = backfill_metrica(metric, entity, batch_dias, fi, fecha_fin, dry_run)
        if not dry_run:
            logger.info(f"  ✅ Total insertado: {n} registros")
            verificar_resultado(metric, entity)

    logger.info(f"\n✅ Grupo {grupo_id} completado.")


def main():
    parser = argparse.ArgumentParser(description='Backfill maestro de métricas XM')
    parser.add_argument('--grupo', type=str, default=None,
                        help='Número(s) de grupo a ejecutar, separados por coma (ej: 1,2)')
    parser.add_argument('--metrica', type=str, default=None,
                        help='Métrica individual en formato METRICA:ENTIDAD (ej: AporEner:Rio)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo mostrar qué haría, sin modificar BD ni llamar API')
    parser.add_argument('--solo-limpiar', action='store_true',
                        help='Solo borrar filas corruptas, sin repoblar desde API')
    parser.add_argument('--desde', type=str, default=None,
                        help='Fecha inicio override YYYY-MM-DD')
    parser.add_argument('--hasta', type=str, default=None,
                        help='Fecha fin override YYYY-MM-DD')
    args = parser.parse_args()

    from datetime import datetime
    fi_override = datetime.strptime(args.desde, '%Y-%m-%d').date() if args.desde else None
    ff_override = datetime.strptime(args.hasta, '%Y-%m-%d').date() if args.hasta else None

    logger.info(f"🚀 Backfill Maestro XM | dry_run={args.dry_run} | solo_limpiar={args.solo_limpiar}")
    if fi_override:
        logger.info(f"   Rango override: {fi_override} → {ff_override or FECHA_CORTE - timedelta(days=1)}")

    # ── Modo métrica individual ──────────────────────────────────────────────
    if args.metrica:
        parts = args.metrica.split(':')
        if len(parts) != 2:
            logger.error("Formato --metrica debe ser METRICA:ENTIDAD (ej: AporEner:Rio)")
            sys.exit(1)
        metric, entity = parts
        # Buscar configuración en grupos
        batch_dias = 15
        fi_default = FECHA_INICIO_DEFAULT
        for g in GRUPOS.values():
            for m, e, bd, fi in g['metricas']:
                if m == metric and e == entity:
                    batch_dias = bd
                    fi_default = fi
                    break
        fi = fi_override or fi_default
        ff = ff_override or (FECHA_CORTE - timedelta(days=1))

        cnt, dias, recursos = contar_filas_bug(metric, entity, FECHA_CORTE)
        logger.info(f"🎯 {metric}/{entity}: {cnt} filas bug ({cnt/max(dias,1):.1f} f/día)")
        deleted = limpiar_filas_bug(metric, entity, FECHA_CORTE, args.dry_run)
        logger.info(f"🗑️  {'[DRY] Borraría' if args.dry_run else 'Borradas'} {deleted} filas")
        if not args.solo_limpiar:
            n = backfill_metrica(metric, entity, batch_dias, fi, ff, args.dry_run)
            if not args.dry_run:
                verificar_resultado(metric, entity)
        return

    # ── Modo grupos ──────────────────────────────────────────────────────────
    if args.grupo:
        grupo_ids = [int(g.strip()) for g in args.grupo.split(',')]
    else:
        grupo_ids = sorted(GRUPOS.keys())

    resumen = {}
    for gid in grupo_ids:
        if gid not in GRUPOS:
            logger.error(f"Grupo {gid} no existe (disponibles: {list(GRUPOS.keys())})")
            continue
        t0 = __import__('time').time()
        run_grupo(gid, fi_override, ff_override, args.dry_run, args.solo_limpiar)
        resumen[gid] = round(__import__('time').time() - t0, 1)

    logger.info(f"\n{'='*70}")
    logger.info(f"🏁 BACKFILL MAESTRO COMPLETADO")
    for gid, elapsed in resumen.items():
        logger.info(f"   Grupo {gid} ({GRUPOS[gid]['nombre']}): {elapsed:.0f}s")
    logger.info(f"{'='*70}")


if __name__ == '__main__':
    main()
