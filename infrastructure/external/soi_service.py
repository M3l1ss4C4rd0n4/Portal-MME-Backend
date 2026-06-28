"""
SOI (Southern Oscillation Index) Service — NOAA CPC
=====================================================

Descarga el índice SOI mensual histórico desde NOAA CPC e interpola a resolución diaria.

Fuente:
  https://www.cpc.ncep.noaa.gov/data/indices/soi
  Formato: texto fixed-width con año y meses como columnas.

El SOI mide la diferencia de presión superficial entre Tahití y Darwin (Australia).
Complementa el ONI (oceánico) con la señal atmosférica de ENSO:
  SOI < -1: El Niño (baja presión en Tahití, alta en Darwin)
  SOI > +1: La Niña (alta presión en Tahití, baja en Darwin)

Rango típico: -35 a +35 (estandarizado). Se almacena sin offset (valores raw).
"""

import logging
import time
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('soi_service')

NOAA_SOI_URL = 'https://www.cpc.ncep.noaa.gov/data/indices/soi'

_MONTH_COLS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
               'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
_MISSING_VALUES = {-999.9, -99.9, 999.9}


def _get_session() -> requests.Session:
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


def fetch_soi_historical(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Descarga y parsea el índice SOI desde NOAA CPC.

    Returns:
        DataFrame con columnas [fecha (día 15 del mes), soi_value]
        o None si falla la descarga.

    Formato fuente (fixed-width):
        STANDARDIZED    SOI    DATA

         YEAR  JAN  FEB  MAR  APR  MAY  JUN  JUL  AUG  SEP  OCT  NOV  DEC
         1951  0.7  0.9  1.3  0.7  0.1  0.1  0.9 -0.2  0.1  0.3  0.7  0.0
    """
    session = _get_session()
    logger.info("⬇️  Descargando SOI desde NOAA CPC...")

    try:
        t0 = time.time()
        r = session.get(NOAA_SOI_URL, timeout=timeout)
        elapsed = time.time() - t0

        if r.status_code != 200:
            logger.error(f"❌ NOAA CPC SOI HTTP {r.status_code}: {r.text[:200]}")
            return None

        logger.info(f"✅ SOI descargado ({elapsed:.1f}s, {len(r.content)} bytes)")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red al descargar SOI: {e}")
        return None

    rows = []
    for line in r.text.strip().split('\n'):
        # El formato NOAA es ancho-fijo: 4 chars de año + 12 × 6 chars de valor.
        # Cuando un valor negativo precede a -999.9 no hay espacio separador
        # (e.g. "  -0.9-999.9"), por lo que split() falla — se usa slicing.
        if len(line) < 5:
            continue
        year_str = line[:4].strip()
        if not year_str.isdigit() or len(year_str) != 4:
            continue
        try:
            year = int(year_str)
            for month_idx in range(1, 13):
                start = 4 + (month_idx - 1) * 6
                end = start + 6
                if end > len(line):
                    break
                val_str = line[start:end].strip()
                if not val_str:
                    break
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                if val in _MISSING_VALUES or abs(val) > 500:
                    continue
                fecha = pd.Timestamp(year=year, month=month_idx, day=15)
                rows.append({'fecha': fecha, 'soi_value': val})
        except (ValueError, IndexError):
            continue

    if not rows:
        logger.error("❌ No se parsearon filas válidas de SOI")
        return None

    df = pd.DataFrame(rows).sort_values('fecha').drop_duplicates('fecha').reset_index(drop=True)
    logger.info(
        f"📊 SOI: {len(df)} meses | "
        f"{df['fecha'].min().date()} → {df['fecha'].max().date()} | "
        f"μ={df['soi_value'].mean():.2f} σ={df['soi_value'].std():.2f}"
    )
    return df


def interpolate_monthly_to_daily(df_monthly: pd.DataFrame, value_col: str = 'soi_value') -> pd.DataFrame:
    """
    Interpola valores mensuales (día 15) a resolución diaria mediante interpolación lineal.
    """
    if df_monthly is None or df_monthly.empty:
        return pd.DataFrame(columns=['fecha', value_col])

    df = df_monthly.copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.sort_values('fecha').set_index('fecha')

    idx_diario = pd.date_range(df.index.min(), df.index.max(), freq='D')
    df_daily = df.reindex(idx_diario)
    df_daily[value_col] = df_daily[value_col].interpolate(method='time')
    df_daily = df_daily.reset_index().rename(columns={'index': 'fecha'})
    df_daily['fecha'] = pd.to_datetime(df_daily['fecha']).dt.normalize()

    logger.info(
        f"📅 SOI interpolado: {len(df_daily)} días | "
        f"{df_daily['fecha'].min().date()} → {df_daily['fecha'].max().date()}"
    )
    return df_daily[['fecha', value_col]].dropna()


def get_soi_complete(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Pipeline completo: descarga histórico SOI e interpola a diario.

    Returns:
        DataFrame con [fecha, soi_value] (diario) o None si falla.
    """
    df_hist = fetch_soi_historical(timeout=timeout)
    if df_hist is None:
        return None
    return interpolate_monthly_to_daily(df_hist, 'soi_value')
