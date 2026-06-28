"""
GMST (Global Mean Surface Temperature) Service — NASA GISS / NOAA NCEI
=======================================================================

Descarga la anomalía de temperatura media global desde NASA GISTEMP e interpola
a resolución diaria.

Fuente primaria:
  NASA GISS GISTEMP v4
  https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv
  Formato: CSV con año y columnas mensuales. Valores en °C (anomalía vs 1951-1980).
  Missing = '***'

Fuente alternativa:
  NOAA NCEI Global Surface Temperature (ERSST v5)
  https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series/globe/land_ocean/1/12/1880-2025/data.csv
  Formato CSV con 'Year,Value' (anomalía °C vs 1901-2000)

Por qué ayuda al modelo:
  El calentamiento global (~+1.3°C en 2026) intensifica los eventos El Niño
  entre un 10-15% por grado extra (IPCC AR6). Agregar GMST como regresor
  permite al modelo capturar la tendencia secular sin asumir stationarity.
  El valor actual se propaga hacia el futuro (futura_ffill) porque el GMST
  cambia muy lentamente — resetear a 0 sería contraproducente.

Rango típico (período instrumental): −0.5°C (1950s) a +1.4°C (2024).
Se almacena sin offset (valores raw en °C de anomalía).
"""

import logging
import time
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('gmst_service')

NASA_GISTEMP_URL = 'https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv'
NOAA_NCEI_URL = (
    'https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/'
    'global/time-series/globe/land_ocean/1/12/1880-2025/data.csv'
)

_MISSING_MARKERS = {'***', '-999', '-9999', 'nan', ''}


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


def _parse_nasa_gistemp(text: str) -> list[dict]:
    """
    Parsea el CSV de NASA GISTEMP v4.
    Columnas: Year, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec, J-D, ...
    Valores en °C. Meses sin dato = '***'.
    """
    rows = []
    lines = text.strip().split('\n')
    header_found = False
    month_cols = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    col_indices: list[int] = []

    for line in lines:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(',')]

        if not header_found:
            if parts and parts[0].strip().lower() in ('year', 'years'):
                header_found = True
                col_indices = []
                for m_idx, mname in enumerate(month_cols):
                    for i, h in enumerate(parts):
                        if h.strip().lower() == mname.lower():
                            col_indices.append(i)
                            break
            continue

        if not parts or not parts[0].strip().isdigit() or len(parts[0].strip()) != 4:
            continue

        try:
            year = int(parts[0].strip())
            for month_idx, col_i in enumerate(col_indices, start=1):
                if col_i >= len(parts):
                    continue
                val_str = parts[col_i].strip()
                if val_str in _MISSING_MARKERS:
                    continue
                val = float(val_str)
                if abs(val) > 10:
                    continue
                rows.append({'fecha': pd.Timestamp(year=year, month=month_idx, day=15),
                             'gmst_value': val})
        except (ValueError, IndexError):
            continue

    return rows


def _parse_noaa_ncei(text: str) -> list[dict]:
    """
    Parsea el CSV de NOAA NCEI Global Time Series.
    Formato: 'Year,Value' con encabezados variables.
    """
    rows = []
    lines = text.strip().split('\n')
    data_started = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if 'year' in line.lower() and 'value' in line.lower():
            data_started = True
            continue
        if not data_started:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 2:
            continue
        try:
            year_str = parts[0]
            if len(year_str) == 6 and year_str.isdigit():
                year = int(year_str[:4])
                month = int(year_str[4:6])
            elif len(year_str) == 4 and year_str.isdigit():
                year = int(year_str)
                month = 7  # anual → día 15 de julio
            else:
                continue
            val = float(parts[1])
            if abs(val) > 10:
                continue
            rows.append({'fecha': pd.Timestamp(year=year, month=month, day=15),
                         'gmst_value': val})
        except (ValueError, IndexError):
            continue

    return rows


def fetch_gmst_historical(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Descarga y parsea la anomalía GMST desde NASA GISTEMP (primario) o NOAA NCEI (alternativa).

    Returns:
        DataFrame con columnas [fecha (día 15 del mes), gmst_value] en °C
        o None si fallan todas las fuentes.
    """
    session = _get_session()

    sources = [
        (NASA_GISTEMP_URL, 'NASA GISTEMP v4', _parse_nasa_gistemp),
        (NOAA_NCEI_URL, 'NOAA NCEI', _parse_noaa_ncei),
    ]

    for url, name, parser in sources:
        logger.info(f"⬇️  Descargando GMST desde {name}...")
        try:
            t0 = time.time()
            r = session.get(url, timeout=timeout)
            elapsed = time.time() - t0
            if r.status_code != 200 or len(r.content) < 200:
                logger.warning(f"⚠️  {name} HTTP {r.status_code}")
                continue
            logger.info(f"✅ GMST descargado desde {name} ({elapsed:.1f}s, {len(r.content)} bytes)")
            rows = parser(r.text)
            if rows:
                df = (
                    pd.DataFrame(rows)
                    .sort_values('fecha')
                    .drop_duplicates('fecha')
                    .reset_index(drop=True)
                )
                logger.info(
                    f"📊 GMST: {len(df)} meses | "
                    f"{df['fecha'].min().date()} → {df['fecha'].max().date()} | "
                    f"μ={df['gmst_value'].mean():.3f} σ={df['gmst_value'].std():.3f} °C"
                )
                return df
            logger.warning(f"⚠️  {name}: 0 filas válidas parseadas")
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️  {name}: error de red: {e}")

    logger.error("❌ No se pudo descargar GMST de ninguna fuente")
    return None


def interpolate_monthly_to_daily(df_monthly: pd.DataFrame, value_col: str = 'gmst_value') -> pd.DataFrame:
    """Interpola valores mensuales (día 15) a resolución diaria mediante interpolación lineal."""
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
        f"📅 GMST interpolado: {len(df_daily)} días | "
        f"{df_daily['fecha'].min().date()} → {df_daily['fecha'].max().date()}"
    )
    return df_daily[['fecha', value_col]].dropna()


def get_gmst_complete(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Pipeline completo: descarga GMST histórico e interpola a diario.

    Returns:
        DataFrame con [fecha, gmst_value] (diario, °C de anomalía) o None si falla.
    """
    df_hist = fetch_gmst_historical(timeout=timeout)
    if df_hist is None:
        return None
    return interpolate_monthly_to_daily(df_hist, 'gmst_value')
