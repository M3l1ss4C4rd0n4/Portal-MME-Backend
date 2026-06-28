"""
PDO (Pacific Decadal Oscillation) Service — NOAA NCEI
=======================================================

Descarga el índice PDO mensual histórico desde NOAA e interpola a resolución diaria.

Fuente:
  https://www.ncdc.noaa.gov/teleconnections/pdo/data.csv
  Formato CSV: Date (YYYYMM), Value

El PDO modula la amplitud de El Niño en escalas decadales:
  PDO+ (fase cálida) amplifica El Niño, refuerza déficit hídrico colombiano
  PDO- (fase fría) amortigua El Niño

El período 2020-2030 está documentado como PDO+ → El Niño 2026 será más
intenso de lo esperado solo con ONI histórico.

Rango típico: -3.0 a +3.0°C (desviaciones estandarizadas de temperatura
superficial del Pacífico Norte). Se almacena sin offset (valores raw).
"""

import logging
import time
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('pdo_service')

# URL principal (NOAA PSL) — formato de texto con año+valores mensuales por línea
NOAA_PDO_URL_PSL = 'https://psl.noaa.gov/data/correlation/pdo.data'
# URL alternativa (NCEI teleconnections CSV)
NOAA_PDO_URL_CSV = 'https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/pdo.latest'


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


def fetch_pdo_historical(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Descarga y parsea el índice PDO desde NOAA PSL.

    Returns:
        DataFrame con columnas [fecha (día 15 del mes), pdo_value]
        o None si falla la descarga.

    Formato fuente PSL (texto):
        PDO  1900  2024
          1900
          -0.40  0.26 -0.37 ...  (12 valores mensuales, ene-dic)
          1901
          ...
        Última línea puede ser -9.99 para meses sin dato.
    """
    session = _get_session()
    logger.info("⬇️  Descargando PDO desde NOAA PSL...")

    text = None
    for url in [NOAA_PDO_URL_PSL, NOAA_PDO_URL_CSV]:
        try:
            t0 = time.time()
            r = session.get(url, timeout=timeout)
            elapsed = time.time() - t0
            if r.status_code == 200 and len(r.content) > 100:
                logger.info(f"✅ PDO descargado desde {url} ({elapsed:.1f}s, {len(r.content)} bytes)")
                text = r.text
                break
            logger.warning(f"⚠️  {url} HTTP {r.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️  {url}: {e}")

    if text is None:
        logger.error("❌ No se pudo descargar PDO de ninguna fuente NOAA")
        return None

    rows = []
    lines = text.strip().split('\n')

    for line in lines:
        parts = line.split()
        if not parts:
            continue

        # Formato PSL: YYYY  v1  v2  ... v12  (13 tokens, año + 12 mensuales)
        if len(parts) >= 13 and parts[0].isdigit() and len(parts[0]) == 4:
            try:
                year = int(parts[0])
                for month_idx, tok in enumerate(parts[1:13], start=1):
                    val = float(tok)
                    if val <= -9.0:
                        continue  # missing
                    rows.append({'fecha': pd.Timestamp(year=year, month=month_idx, day=15),
                                 'pdo_value': val})
            except (ValueError, IndexError):
                continue
            continue

        # Formato CSV: YYYYMM,value
        if len(parts) >= 2:
            try:
                date_str = parts[0].replace(',', '')
                val_str = parts[1].replace(',', '')
                if len(date_str) == 6 and date_str.isdigit():
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    val = float(val_str)
                    if 1 <= month <= 12 and val > -99:
                        rows.append({'fecha': pd.Timestamp(year=year, month=month, day=15),
                                     'pdo_value': val})
            except (ValueError, IndexError):
                pass

    if not rows:
        logger.error("❌ No se parsearon filas válidas de PDO")
        return None

    df = pd.DataFrame(rows).sort_values('fecha').drop_duplicates('fecha').reset_index(drop=True)
    logger.info(
        f"📊 PDO: {len(df)} meses | "
        f"{df['fecha'].min().date()} → {df['fecha'].max().date()} | "
        f"μ={df['pdo_value'].mean():.2f} σ={df['pdo_value'].std():.2f}"
    )
    return df


def interpolate_monthly_to_daily(df_monthly: pd.DataFrame, value_col: str = 'pdo_value') -> pd.DataFrame:
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
        f"📅 PDO interpolado: {len(df_daily)} días | "
        f"{df_daily['fecha'].min().date()} → {df_daily['fecha'].max().date()}"
    )
    return df_daily[['fecha', value_col]].dropna()


def get_pdo_complete(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Pipeline completo: descarga histórico PDO e interpola a diario.

    Returns:
        DataFrame con [fecha, pdo_value] (diario) o None si falla.
    """
    df_hist = fetch_pdo_historical(timeout=timeout)
    if df_hist is None:
        return None
    return interpolate_monthly_to_daily(df_hist, 'pdo_value')
