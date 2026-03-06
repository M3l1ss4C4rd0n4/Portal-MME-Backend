"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║   IDEAM Data Service — Datos Abiertos Colombia (datos.gov.co)               ║
║                                                                               ║
║   FASE 18: ETL meteorológico para regresores de predicciones                 ║
║                                                                               ║
║   Fuentes:                                                                    ║
║     - Velocidad del viento  (sgfv-3yp8) → Eólica                            ║
║     - Precipitación         (s54a-sgyg) → APORTES_HIDRICOS                   ║
║     - Temperatura           (sbwg-7ju4) → Solar, general                     ║
║                                                                               ║
║   API: Socrata Open Data API (SODA) — sin autenticación requerida           ║
║   Rate limit: ~1000 req/hora sin token                                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
import time
from datetime import date
from typing import Optional, Dict, List

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('ideam_service')

# ---------------------------------------------------------------------------
# CONFIGURACIÓN DE DATASETS (Socrata resource IDs)
# ---------------------------------------------------------------------------
IDEAM_BASE_URL = 'https://www.datos.gov.co/resource'

IDEAM_DATASETS = {
    'velocidad_viento': {
        'resource_id': 'sgfv-3yp8',
        'descripcion': 'Velocidad del viento (m/s)',
        'unidad': 'm/s',
        'metrica_bd': 'IDEAM_VelViento',      # nombre en tabla metrics
        'agg_diaria': 'mean',                  # promedio diario
        'valor_min': 0,                        # validación
        'valor_max': 50,                       # m/s (Cat 5 hurricaine ~70)
    },
    'precipitacion': {
        'resource_id': 's54a-sgyg',
        'descripcion': 'Precipitación (mm)',
        'unidad': 'mm',
        'metrica_bd': 'IDEAM_Precipitacion',
        'agg_diaria': 'sum',                   # acumulado diario
        'valor_min': 0,
        'valor_max': 500,                      # mm/día (extremo tropical)
    },
    'temperatura': {
        'resource_id': 'sbwg-7ju4',
        'descripcion': 'Temperatura del aire (°C)',
        'unidad': '°C',
        'metrica_bd': 'IDEAM_Temperatura',
        'agg_diaria': 'mean',                  # promedio diario
        'valor_min': -10,                      # páramos
        'valor_max': 50,                       # costa caribe
    },
}

# ---------------------------------------------------------------------------
# ESTACIONES ESTRATÉGICAS POR ZONA ENERGÉTICA
# ---------------------------------------------------------------------------
# Colombia's wind farms are concentrated in La Guajira (Jepirachi, Guajira I).
# Solar farms are distributed across several departments.
# Hydro inflows come from the major river basins (Magdalena, Cauca, etc.).

ESTACIONES_EOLICA = {
    # La Guajira — Zona principal de parques eólicos
    'departamentos': ['LA GUAJIRA'],
    'municipios_prioritarios': ['URIBIA', 'MAICAO', 'RIOHACHA', 'MANAURE'],
}

ESTACIONES_SOLAR = {
    # Nacional — Solar distribuido
    'departamentos': ['CESAR', 'LA GUAJIRA', 'ATLANTICO', 'BOLIVAR',
                      'MAGDALENA', 'SANTANDER', 'META', 'TOLIMA'],
}

ESTACIONES_HIDRO = {
    # Cuencas principales de aportes hídricos
    'departamentos': ['ANTIOQUIA', 'CALDAS', 'BOYACA', 'CUNDINAMARCA',
                      'SANTANDER', 'HUILA', 'TOLIMA', 'CAUCA', 'NARIÑO'],
}


# ---------------------------------------------------------------------------
# HTTP SESSION CON RETRY
# ---------------------------------------------------------------------------
def _get_session() -> requests.Session:
    """Session HTTP con retry automático y timeouts conservadores."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET'],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


# ---------------------------------------------------------------------------
# FETCH FUNCTIONS
# ---------------------------------------------------------------------------
def fetch_ideam_data(
    dataset_key: str,
    departamentos: List[str],
    fecha_inicio: date,
    fecha_fin: date = None,
    limit: int = 50000,
    timeout: int = 120,
) -> Optional[pd.DataFrame]:
    """
    Fetch datos IDEAM desde datos.gov.co (Socrata SODA API).

    Args:
        dataset_key: Clave en IDEAM_DATASETS ('velocidad_viento', etc.)
        departamentos: Lista de departamentos a filtrar
        fecha_inicio: Fecha inicio (inclusive)
        fecha_fin: Fecha fin (inclusive, default=hoy)
        limit: Max registros por request (Socrata max=50000)
        timeout: Timeout en segundos

    Returns:
        DataFrame con columnas [fecha, valor, estacion, departamento, municipio]
        o None si error
    """
    if dataset_key not in IDEAM_DATASETS:
        logger.error(f"❌ Dataset desconocido: {dataset_key}")
        return None

    cfg = IDEAM_DATASETS[dataset_key]
    resource_id = cfg['resource_id']
    url = f"{IDEAM_BASE_URL}/{resource_id}.json"

    if fecha_fin is None:
        fecha_fin = date.today()

    # Build SoQL WHERE clause
    depto_list = " OR ".join([f"departamento='{d}'" for d in departamentos])
    where_clause = (
        f"fechaobservacion >= '{fecha_inicio.isoformat()}T00:00:00.000' "
        f"AND fechaobservacion <= '{fecha_fin.isoformat()}T23:59:59.000' "
        f"AND ({depto_list})"
    )

    session = _get_session()
    all_rows = []
    offset = 0
    batch_size = min(limit, 50000)

    logger.info(f"🌍 IDEAM fetch: {dataset_key} | {departamentos} | "
                f"{fecha_inicio} → {fecha_fin}")

    while True:
        params = {
            '$where': where_clause,
            '$limit': batch_size,
            '$offset': offset,
            '$order': 'fechaobservacion ASC',
        }
        try:
            t0 = time.time()
            r = session.get(url, params=params, timeout=timeout)
            elapsed = time.time() - t0

            if r.status_code != 200:
                logger.error(f"❌ IDEAM API error: {r.status_code} | {r.text[:200]}")
                break

            batch = r.json()
            if not batch:
                break

            all_rows.extend(batch)
            logger.info(f"  📦 Batch {offset // batch_size + 1}: "
                        f"{len(batch)} registros ({elapsed:.1f}s)")

            if len(batch) < batch_size:
                break  # Last page

            offset += batch_size
            time.sleep(1)  # Rate limiting

        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Timeout ({timeout}s) en offset={offset}")
            break
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error: {e}")
            break

    if not all_rows:
        logger.warning(f"⚠️ Sin datos para {dataset_key}")
        return None

    # Parse to DataFrame
    df = pd.DataFrame(all_rows)
    df = df.rename(columns={
        'fechaobservacion': 'fecha_hora',
        'valorobservado': 'valor_raw',
        'nombreestacion': 'estacion',
        'codigoestacion': 'codigo_estacion',
    })

    # Type conversions
    df['fecha_hora'] = pd.to_datetime(df['fecha_hora'], errors='coerce')
    df['valor_raw'] = pd.to_numeric(df['valor_raw'], errors='coerce')
    df = df.dropna(subset=['fecha_hora', 'valor_raw'])

    # Validación de rango
    v_min, v_max = cfg['valor_min'], cfg['valor_max']
    n_before = len(df)
    df = df[(df['valor_raw'] >= v_min) & (df['valor_raw'] <= v_max)]
    n_filtered = n_before - len(df)
    if n_filtered > 0:
        logger.warning(f"  ⚠️ {n_filtered} registros fuera de rango "
                       f"[{v_min}, {v_max}] eliminados")

    df['fecha'] = df['fecha_hora'].dt.normalize()

    logger.info(f"✅ IDEAM {dataset_key}: {len(df)} registros válidos "
                f"de {len(all_rows)} raw | "
                f"{df['fecha'].nunique()} días únicos")

    return df[['fecha', 'valor_raw', 'estacion', 'departamento', 'municipio',
               'codigo_estacion']].copy()


def agregar_diario(
    df: pd.DataFrame,
    agg_method: str = 'mean',
) -> pd.DataFrame:
    """
    Agrega datos sub-diarios a resolución diaria.

    Args:
        df: DataFrame con columnas [fecha, valor_raw, ...]
        agg_method: 'mean', 'sum', 'max', 'min'

    Returns:
        DataFrame con [fecha, valor] — un valor por día
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=['fecha', 'valor'])

    agg_func = {
        'mean': 'mean',
        'sum': 'sum',
        'max': 'max',
        'min': 'min',
    }.get(agg_method, 'mean')

    df_daily = (df
                .groupby('fecha')['valor_raw']
                .agg(agg_func)
                .reset_index()
                .rename(columns={'valor_raw': 'valor'}))

    return df_daily.sort_values('fecha').reset_index(drop=True)


def agregar_diario_por_zona(
    df: pd.DataFrame,
    agg_method: str = 'mean',
    departamentos_peso: Dict[str, float] = None,
) -> pd.DataFrame:
    """
    Agrega datos a resolución diaria, promediando entre estaciones.
    Opcionalmente aplica pesos por departamento.

    1. Primero agrega por (fecha, estación) → promedio intra-día
    2. Luego agrega por fecha → promedio inter-estaciones
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=['fecha', 'valor'])

    agg_func = agg_method if agg_method != 'sum' else 'mean'

    # Step 1: Promedio intra-día por estación
    df_est = (df
              .groupby(['fecha', 'codigo_estacion', 'departamento'])['valor_raw']
              .agg(agg_func)
              .reset_index()
              .rename(columns={'valor_raw': 'valor_est'}))

    # Step 2: Promedio inter-estaciones (weighted or equal)
    if departamentos_peso:
        df_est['peso'] = df_est['departamento'].map(departamentos_peso).fillna(1.0)
        df_daily = (df_est
                    .groupby('fecha')
                    .apply(lambda g: (g['valor_est'] * g['peso']).sum() / g['peso'].sum(),
                           include_groups=False)
                    .reset_index(name='valor'))
    else:
        df_daily = (df_est
                    .groupby('fecha')['valor_est']
                    .mean()
                    .reset_index()
                    .rename(columns={'valor_est': 'valor'}))

    # Para precipitación: después del promedio inter-estaciones, si el
    # agg_method original era 'sum', el resultado ya es el promedio
    # de los acumulados diarios de cada estación — representativo del
    # aporte hídrico medio de la zona.

    return df_daily.sort_values('fecha').reset_index(drop=True)


def fetch_and_aggregate(
    dataset_key: str,
    departamentos: List[str],
    fecha_inicio: date,
    fecha_fin: date = None,
    timeout: int = 120,
) -> Optional[pd.DataFrame]:
    """
    Pipeline completo: fetch → validate → aggregate to daily.

    Returns:
        DataFrame con [fecha, valor] — un valor por día, o None
    """
    cfg = IDEAM_DATASETS[dataset_key]

    df_raw = fetch_ideam_data(
        dataset_key=dataset_key,
        departamentos=departamentos,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        timeout=timeout,
    )

    if df_raw is None or df_raw.empty:
        return None

    df_daily = agregar_diario_por_zona(df_raw, agg_method=cfg['agg_diaria'])

    logger.info(f"  📊 {dataset_key} agregado diario: {len(df_daily)} días "
                f"| μ={df_daily['valor'].mean():.2f} "
                f"| σ={df_daily['valor'].std():.2f}")

    return df_daily
