#!/usr/bin/env python3
"""
ETL — NASA POWER API → PostgreSQL
==================================
Reemplaza permanentemente las 4 métricas de Renovables que XM discontinuó
el 16-Dic-2025 (IrrGlobal, IrrPanel, TempPanel, TempAmbSolar).

Fuente: NASA POWER v2.5 (https://power.larc.nasa.gov/)
  - Sin API key, sin rate limits comerciales.
  - Lag: ~1-5 días para parámetros solares, 2-3 días para meteorológicos.
  - Historia disponible: desde 1981 (parámetros solares) / 1984 (met.).
  - Resolución: diaria, punto geográfico (0.5° × 0.625° interpolado).

Modos de operación:
  --modo solar  (default): zonas de generación solar/eólica, community=RE
                Parámetros: ALLSKY_SFC_SW_DWN, CLRSKY_SFC_SW_DWN, T2M, RH2M, WS10M
                Zonas: LA_GUAJIRA, COSTA_CARIBE, ALTIPLANO

  --modo hidro: cuencas hidrológicas principales, community=AG
                Parámetros: PRECTOTCORR (precipitación mm/día), T2M, RH2M
                Zonas: MAGDALENA_ALTO, CAUCA_MEDIO, SANTANDER_CUENCA, PACIFICO_CUENCA
                → Precipitación satelital para predicción APORTES_HIDRICOS (FASE 19)

Uso:
  # Backfill completo 2020→hoy (solo la primera vez, ~5 min)
  python etl/etl_nasa_power.py --inicio 2020-01-01
  python etl/etl_nasa_power.py --inicio 2020-01-01 --modo hidro

  # Actualización diaria (cron, toma los últimos 10 días)
  python etl/etl_nasa_power.py --dias 10
  python etl/etl_nasa_power.py --dias 10 --modo hidro

  # Solo un punto geográfico
  python etl/etl_nasa_power.py --dias 10 --zona LA_GUAJIRA
"""

import sys
import os
import time
import logging
import argparse
from datetime import datetime, timedelta, date
from typing import Optional

import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.database.manager import db_manager

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# ─── Configuración ────────────────────────────────────────────────────────────
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_TIMEOUT   = 60            # segundos por request
NASA_MAX_DAYS  = 366           # límite de la API por petición (puede ser menos)

# ── Modo SOLAR (default) ──────────────────────────────────────────────────────
NASA_COMMUNITY_SOLAR = "RE"    # Renewable Energy community

PARAMETROS_SOLAR = [
    "ALLSKY_SFC_SW_DWN",  # Irradiancia global en superficie   → NASA_IrrGlobal
    "CLRSKY_SFC_SW_DWN",  # Irradiancia cielo despejado        → NASA_IrrCielo
    "T2M",                # Temperatura a 2m                   → NASA_Temp2M
    "RH2M",               # Humedad relativa a 2m              → NASA_RH2M
    "WS10M",              # Velocidad viento a 10m             → NASA_Viento10M
]

PARAM_META_SOLAR = {
    "ALLSKY_SFC_SW_DWN": ("NASA_IrrGlobal",   "kWh/m2/d"),
    "CLRSKY_SFC_SW_DWN": ("NASA_IrrCielo",    "kWh/m2/d"),
    "T2M":               ("NASA_Temp2M",      "°C"),
    "RH2M":              ("NASA_RH2M",        "%"),
    "WS10M":             ("NASA_Viento10M",   "m/s"),
}

# Puntos geográficos — centros de zonas de generación solar+eólica en Colombia
ZONAS_SOLAR = {
    "LA_GUAJIRA": {
        "lat": 11.5,
        "lon": -72.9,
        "descripcion": "La Guajira — mayor parque solar+eólico de Colombia",
    },
    "COSTA_CARIBE": {
        "lat": 10.4,
        "lon": -75.5,
        "descripcion": "Costa Caribe — Córdoba, Bolívar, Atlántico",
    },
    "ALTIPLANO": {
        "lat": 4.7,
        "lon": -74.1,
        "descripcion": "Altiplano — Cundinamarca, Boyacá, Tolima",
    },
}

# ── Modo HIDRO (FASE 19) ──────────────────────────────────────────────────────
NASA_COMMUNITY_HIDRO = "AG"    # Agroclimatology community — tiene precipitación

PARAMETROS_HIDRO = [
    "PRECTOTCORR",  # Precipitación corregida (mm/día)         → NASA_Precipitacion
    "T2M",          # Temperatura a 2m (°C)                    → NASA_Temp2M_Hidro
    "RH2M",         # Humedad relativa (%)                     → NASA_RH2M_Hidro
]

PARAM_META_HIDRO = {
    "PRECTOTCORR": ("NASA_Precipitacion", "mm/d"),
    "T2M":         ("NASA_Temp2M_Hidro",  "°C"),
    "RH2M":        ("NASA_RH2M_Hidro",    "%"),
}

# Cuencas hidrológicas principales de Colombia
# Representan los ríos que generan ~85% de los aportes energéticos
ZONAS_HIDRO = {
    "MAGDALENA_ALTO": {
        "lat": 3.5,
        "lon": -75.2,
        "descripcion": "Alto Magdalena — Huila/Tolima (El Quimbo, Betania, Prado)",
    },
    "CAUCA_MEDIO": {
        "lat": 6.0,
        "lon": -75.6,
        "descripcion": "Cauca Medio — Antioquia (Porce, San Carlos, Guadalupe, Ituango)",
    },
    "SANTANDER_CUENCA": {
        "lat": 6.8,
        "lon": -73.1,
        "descripcion": "Chicamocha/Lebrija — Santander/Boyacá (Sogamoso, Bata)",
    },
    "PACIFICO_CUENCA": {
        "lat": 4.2,
        "lon": -76.5,
        "descripcion": "Cuencas del Pacífico — Valle/Chocó (Anchicayá, Salvajina, Calima)",
    },
}


# =============================================================================
# API FETCH
# =============================================================================

def _chunk_dateranges(start: date, end: date, max_days: int = NASA_MAX_DAYS):
    """Divide un rango largo en chunks de max_days días."""
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def fetch_nasa_power(lat: float, lon: float,
                     fecha_inicio: date, fecha_fin: date,
                     parametros: list, community: str,
                     param_meta: dict) -> Optional[pd.DataFrame]:
    """
    Consulta NASA POWER API para un punto geográfico y rango de fechas.

    Args:
        parametros: lista de parámetros NASA (e.g. ["PRECTOTCORR", "T2M"])
        community:  community NASA ("RE" para solar, "AG" para precipitación)

    Returns:
        DataFrame con columnas [fecha, param1, param2, ...] o None si falla.
    """
    all_frames = []

    for chunk_start, chunk_end in _chunk_dateranges(fecha_inicio, fecha_fin):
        params = {
            "parameters": ",".join(parametros),
            "community":  community,
            "longitude":  lon,
            "latitude":   lat,
            "start":      chunk_start.strftime("%Y%m%d"),
            "end":        chunk_end.strftime("%Y%m%d"),
            "format":     "JSON",
        }

        try:
            r = requests.get(NASA_POWER_URL, params=params, timeout=NASA_TIMEOUT)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error(f"  ❌ Error HTTP NASA POWER ({chunk_start}→{chunk_end}): {e}")
            return None

        data = r.json()

        try:
            properties = data["properties"]["parameter"]
        except KeyError:
            log.warning(f"  ⚠️ Estructura inesperada en respuesta NASA POWER")
            log.debug(f"  Respuesta: {str(data)[:300]}")
            return None

        # Construir DataFrame del chunk
        records = {}
        for param, valores in properties.items():
            if param not in param_meta:
                continue
            for fecha_str, val in valores.items():
                if fecha_str not in records:
                    records[fecha_str] = {}
                # NASA POWER usa -999 para valor faltante
                records[fecha_str][param] = float(val) if float(val) != -999.0 else None

        if not records:
            log.warning(f"  ⚠️ Sin datos en chunk {chunk_start}→{chunk_end}")
            continue

        chunk_df = pd.DataFrame.from_dict(records, orient='index')
        chunk_df.index = pd.to_datetime(chunk_df.index, format="%Y%m%d")
        chunk_df.index.name = "fecha"
        all_frames.append(chunk_df)

        log.info(f"  ✅ Chunk {chunk_start}→{chunk_end}: {len(chunk_df)} días")
        time.sleep(0.5)   # cortesía hacia la API de NASA

    if not all_frames:
        return None

    df = pd.concat(all_frames).sort_index()
    df = df[~df.index.duplicated(keep='last')]  # si hay solapamiento entre chunks
    return df


# =============================================================================
# INSERT EN BD
# =============================================================================

def insertar_en_bd(df: pd.DataFrame, zona: str, param_meta: dict) -> int:
    """
    Inserta/actualiza registros NASA POWER en la tabla metrics.

    Usa ON CONFLICT DO UPDATE → idempotente, seguro para re-ejecuciones.
    Retorna número de filas procesadas.
    """
    registros = []

    for fecha, row in df.iterrows():
        for param, (metrica, unidad) in param_meta.items():
            if param not in row or pd.isna(row[param]):
                continue
            registros.append((
                fecha.date(),      # fecha
                metrica,           # metrica
                'NASA_POWER',      # entidad
                zona,              # recurso (nombre de la zona)
                float(row[param]), # valor_gwh (el campo numérico genérico de la BD)
                unidad,            # unidad real
            ))

    if not registros:
        log.warning(f"  ⚠️ Sin registros para insertar ({zona})")
        return 0

    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO metrics
                    (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (fecha, metrica, entidad, recurso)
                DO UPDATE SET
                    valor_gwh          = EXCLUDED.valor_gwh,
                    unidad             = EXCLUDED.unidad,
                    fecha_actualizacion = CURRENT_TIMESTAMP
            """, registros)
            conn.commit()

        log.info(f"  💾 {len(registros)} registros insertados/actualizados ({zona})")
        return len(registros)

    except Exception as e:
        log.error(f"  ❌ Error BD ({zona}): {e}")
        return 0


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ETL NASA POWER → PostgreSQL (solar y precipitación hidrológica)"
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--inicio",
        type=str,
        help="Fecha de inicio backfill (YYYY-MM-DD). Ej: 2020-01-01",
    )
    grupo.add_argument(
        "--dias",
        type=int,
        default=10,
        help="Número de días hacia atrás desde hoy (default: 10). Para cron diario.",
    )
    parser.add_argument(
        "--modo",
        choices=["solar", "hidro"],
        default="solar",
        help=(
            "solar (default): zonas de generación solar/eólica, community=RE. "
            "hidro: cuencas hidrológicas + PRECTOTCORR, community=AG (FASE 19)."
        ),
    )
    parser.add_argument(
        "--zona",
        default=None,
        help="Procesar solo una zona por nombre (default: todas las del modo).",
    )
    args = parser.parse_args()

    # ── Selección de config según modo ────────────────────────────────
    if args.modo == "hidro":
        zonas_cfg   = ZONAS_HIDRO
        parametros  = PARAMETROS_HIDRO
        community   = NASA_COMMUNITY_HIDRO
        param_meta  = PARAM_META_HIDRO
        titulo      = "ETL NASA POWER (HIDRO — PRECTOTCORR cuencas hidrológicas)"
    else:
        zonas_cfg   = ZONAS_SOLAR
        parametros  = PARAMETROS_SOLAR
        community   = NASA_COMMUNITY_SOLAR
        param_meta  = PARAM_META_SOLAR
        titulo      = "ETL NASA POWER (SOLAR — irradiancia y meteorología)"

    # Validar --zona contra el modo activo
    if args.zona:
        if args.zona not in zonas_cfg:
            parser.error(
                f"--zona '{args.zona}' no válida para modo '{args.modo}'. "
                f"Opciones: {list(zonas_cfg.keys())}"
            )
        zonas_a_procesar = {args.zona: zonas_cfg[args.zona]}
    else:
        zonas_a_procesar = zonas_cfg

    # ── Rango de fechas ────────────────────────────────────────────────
    hoy = date.today()
    if args.inicio:
        fecha_inicio = datetime.strptime(args.inicio, "%Y-%m-%d").date()
    else:
        fecha_inicio = hoy - timedelta(days=args.dias)
    fecha_fin = hoy

    log.info("╔══════════════════════════════════════════════════════════════╗")
    log.info(f"║  {titulo[:58]:<58}  ║")
    log.info("╚══════════════════════════════════════════════════════════════╝")
    log.info(f"📅 Rango: {fecha_inicio} → {fecha_fin} "
             f"({(fecha_fin - fecha_inicio).days + 1} días)")
    log.info(f"🌍 Zonas: {list(zonas_a_procesar.keys())}")
    log.info(f"📡 Parámetros: {parametros}")

    total_registros = 0
    t0 = time.time()

    for zona_nombre, zona_info in zonas_a_procesar.items():
        log.info(f"\n{'='*70}")
        log.info(f"🌍 Zona: {zona_nombre} — {zona_info['descripcion']}")
        log.info(f"   Coordenadas: {zona_info['lat']}°N, {zona_info['lon']}°W")

        df = fetch_nasa_power(
            lat=zona_info["lat"],
            lon=zona_info["lon"],
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            parametros=parametros,
            community=community,
            param_meta=param_meta,
        )

        if df is None or df.empty:
            log.warning(f"  ⚠️ Sin datos de NASA POWER para {zona_nombre}")
            continue

        log.info(f"  📊 Descargados {len(df)} días para {zona_nombre}")
        n = insertar_en_bd(df, zona_nombre, param_meta)
        total_registros += n

    elapsed = time.time() - t0
    log.info(f"\n{'='*70}")
    log.info(f"✅ ETL NASA POWER completado en {elapsed:.1f}s")
    log.info(f"💾 Total registros procesados: {total_registros:,}")
    n_zonas = max(len(zonas_a_procesar), 1)
    log.info(f"   (~{total_registros // n_zonas} registros/zona × {len(param_meta)} parámetros)")


if __name__ == "__main__":
    main()
