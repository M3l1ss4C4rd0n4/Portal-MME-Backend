"""
ONI (Oceanic Niño Index) Service — NOAA CPC
============================================

Descarga el índice ONI mensual histórico desde NOAA Climate Prediction Center
e interpola a resolución diaria para uso como regresor en modelos de predicción.

Fuente:
  - Histórico: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
    Formato: SEAS YR TOTAL ANOM (valores estacionales confirmados)
  - Pronóstico: extensión de persistencia climática (último valor extendido
    con decaimiento lineal hacia 0) — se actualiza semanalmente hasta que
    se integre el pronóstico CFSv2 de NOAA.

NOTA DE ALMACENAMIENTO:
  ONI se guarda en la tabla metrics con un offset de +5.0 para mantener
  todos los valores positivos (el filtro metrics.valor_gwh > 0 excluiría
  La Niña si se guardase sin offset). El offset se revierte al cargar como
  regresor mediante la clave 'offset': -5.0 en la config del regresor.

  Rango histórico ONI: ~-2.5 (La Niña fuerte) a ~+3.0 (El Niño fuerte)
  Con offset +5.0: mínimo ~2.5, máximo ~8.0 — siempre > 0.
"""

import logging
import time
from datetime import date
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('oni_service')

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
NOAA_ONI_URL = 'https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt'
NOAA_ENSO_STRENGTHS_URL = 'https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/'

ONI_STORAGE_OFFSET = 5.0   # sumado al ONI antes de guardar en BD
ONI_LOAD_OFFSET = -5.0     # restado al cargar desde BD (revierte el offset)

# Mapea código de estación de 3 letras al mes central
_SEASON_TO_MONTH = {
    'DJF': 1,  'JFM': 2,  'FMA': 3,  'MAM': 4,
    'AMJ': 5,  'MJJ': 6,  'JJA': 7,  'JAS': 8,
    'ASO': 9,  'SON': 10, 'OND': 11, 'NDJ': 12,
}

# Puntos medios de los 9 bins de intensidad NOAA (°C):
# ≤-2.0, -1.5↔-2.0, -1.0↔-1.5, -0.5↔-1.0, -0.5↔+0.5, +0.5↔+1.0, +1.0↔+1.5, +1.5↔+2.0, ≥+2.0
# El último bin usa 2.25 (conservador; históricamente el El Niño muy fuerte promedía ~2.3-2.4°C)
_ONI_BIN_MIDPOINTS = [-2.25, -1.75, -1.25, -0.75, 0.0, 0.75, 1.25, 1.75, 2.25]


# ---------------------------------------------------------------------------
# HTTP SESSION
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# FETCH HISTÓRICO
# ---------------------------------------------------------------------------
def fetch_oni_historical(timeout: int = 60) -> Optional[pd.DataFrame]:
    """
    Descarga y parsea oni.ascii.txt de NOAA CPC.

    Returns:
        DataFrame con columnas [fecha (día 15 del mes central), oni_value]
        o None si falla la descarga.

    Formato fuente:
        SEAS  YR    TOTAL  ANOM
        DJF  1950  26.60   0.53
        ...
    """
    session = _get_session()
    logger.info(f"⬇️  Descargando ONI histórico desde NOAA CPC...")

    try:
        t0 = time.time()
        r = session.get(NOAA_ONI_URL, timeout=timeout)
        elapsed = time.time() - t0

        if r.status_code != 200:
            logger.error(f"❌ NOAA CPC HTTP {r.status_code}: {r.text[:200]}")
            return None

        logger.info(f"✅ Descarga OK ({elapsed:.1f}s, {len(r.content)} bytes)")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de red al descargar ONI: {e}")
        return None

    lines = r.text.strip().split('\n')

    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        seas = parts[0]
        if seas not in _SEASON_TO_MONTH:
            continue  # header or malformed line

        try:
            year = int(parts[1])
            anom = float(parts[3])
        except (ValueError, IndexError):
            continue

        month = _SEASON_TO_MONTH[seas]
        fecha = pd.Timestamp(year=year, month=month, day=15)
        rows.append({'fecha': fecha, 'oni_value': anom})

    if not rows:
        logger.error("❌ No se parsearon filas válidas de oni.ascii.txt")
        return None

    df = pd.DataFrame(rows).sort_values('fecha').reset_index(drop=True)
    logger.info(
        f"📊 ONI histórico: {len(df)} meses | "
        f"{df['fecha'].min().date()} → {df['fecha'].max().date()} | "
        f"μ={df['oni_value'].mean():.2f} σ={df['oni_value'].std():.2f}"
    )
    return df


# ---------------------------------------------------------------------------
# PRONÓSTICO (TABLA DE PROBABILIDADES NOAA — MÉTODO CIENTÍFICO)
# ---------------------------------------------------------------------------
def fetch_enso_strength_probabilities(timeout: int = 30) -> Optional[pd.DataFrame]:
    """
    Descarga la tabla de probabilidades de intensidad ENSO de NOAA CPC.

    La tabla tiene 9 temporadas solapadas hacia adelante (MJJ→JFM) y
    9 bins de probabilidad por categoría de intensidad ONI (en %).

    Returns:
        DataFrame normalizado con columnas [season_code, bin_0, ..., bin_8]
        donde season_code es el código de 3 letras (ej. 'MJJ') y los bins
        son probabilidades enteras (0-100), o None si falla.
    """
    from io import StringIO as _StringIO

    session = _get_session()
    try:
        r = session.get(NOAA_ENSO_STRENGTHS_URL, timeout=timeout)
        if r.status_code != 200:
            logger.warning(f"⚠️ NOAA ENSO strengths HTTP {r.status_code}")
            return None

        tables = pd.read_html(_StringIO(r.text))
        if not tables:
            logger.warning("⚠️ No se encontraron tablas HTML en la página de probabilidades")
            return None

        for tbl in tables:
            if tbl.shape[1] < 10:
                continue
            # El season code ocupa los primeros 3 caracteres de la primera columna
            # ("MJJ May Jun Jul" → "MJJ", o simplemente "MJJ")
            codes = tbl.iloc[:, 0].astype(str).str.strip().str[:3].str.upper()
            if codes.isin(_SEASON_TO_MONTH).sum() >= 8:
                tbl = tbl.copy()
                tbl['_season_code'] = codes
                logger.info(
                    f"✅ Tabla NOAA: {len(tbl)} temporadas, "
                    f"{len(tbl.columns) - 1} bins de probabilidad"
                )
                return tbl

        logger.warning("⚠️ Ninguna tabla HTML contenía códigos de estación ENSO válidos")
        return None

    except Exception as e:
        logger.warning(f"⚠️ Error al descargar/parsear tabla ENSO: {e}")
        return None


def _oni_expected_from_strength_table(df_strengths: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Calcula E[ONI] = Σ P(bin_i) × midpoint(bin_i) / 100 para cada temporada futura.

    Método: Expectativa matemática sobre los 9 bins de intensidad NOAA.
    Sustento científico: Taylor & Letham (2018), sección sobre regresores climáticos;
    metodología estándar de conversión de probabilidades categóricas a valor continuo.

    Args:
        df_strengths: DataFrame de `fetch_enso_strength_probabilities()`

    Returns:
        DataFrame con [fecha (día 15 del mes central), oni_value (E[ONI] en °C)]
    """
    today = pd.Timestamp.today()
    current_month = today.month
    current_year = today.year

    rows = []
    for _, row in df_strengths.iterrows():
        # Usar la columna normalizada '_season_code' si existe, si no extraer del iloc[0]
        if '_season_code' in df_strengths.columns:
            season = str(row['_season_code']).strip().upper()
        else:
            season = str(row.iloc[0]).strip()[:3].upper()
        if season not in _SEASON_TO_MONTH:
            continue

        central_month = _SEASON_TO_MONTH[season]

        # Asignación de año: las temporadas NOAA van hacia adelante desde el mes actual
        # Si el mes central ya pasó este año, corresponde al año siguiente
        if central_month >= current_month:
            year = current_year
        else:
            year = current_year + 1

        fecha = pd.Timestamp(year=year, month=central_month, day=15)

        # Las 9 probabilidades están en las columnas numéricas (excluir Season y _season_code)
        season_col = df_strengths.columns[0]
        prob_col_names = [
            c for c in df_strengths.columns
            if c not in (season_col, '_season_code')
        ][:9]
        prob_cols = [row[c] for c in prob_col_names if pd.notna(row[c])]
        if len(prob_cols) < 9:
            logger.warning(f"⚠️ Temporada {season}: solo {len(prob_cols)} bins (esperados 9)")
            continue

        try:
            probs = [float(p) for p in prob_cols]
        except (ValueError, TypeError):
            continue

        if abs(sum(probs) - 100.0) > 5.0:
            logger.warning(f"⚠️ Temporada {season}: probabilidades suman {sum(probs):.1f}% (≠100)")

        expected_oni = sum(p * m for p, m in zip(probs, _ONI_BIN_MIDPOINTS)) / 100.0
        rows.append({'fecha': fecha, 'oni_value': expected_oni})

    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values('fecha').reset_index(drop=True)
    peak_idx = df['oni_value'].idxmax()
    logger.info(
        f"📊 E[ONI] por probabilidades NOAA: {len(df)} temporadas | "
        f"pico={df.loc[peak_idx, 'oni_value']:.2f}°C en "
        f"{df.loc[peak_idx, 'fecha'].strftime('%Y-%m')}"
    )
    return df


def _generate_persistence_forecast(
    df_historical: pd.DataFrame, meses_adelante: int = 9
) -> pd.DataFrame:
    """
    Fallback: pronóstico de persistencia con decaimiento lineal hacia 0.
    Solo se usa cuando la tabla NOAA no está disponible.
    """
    if df_historical is None or df_historical.empty:
        return pd.DataFrame(columns=['fecha', 'oni_value'])

    ultimo_mes = df_historical.sort_values('fecha').iloc[-1]
    ultimo_valor = float(ultimo_mes['oni_value'])
    ultima_fecha = pd.Timestamp(ultimo_mes['fecha'])

    rows = []
    for i in range(1, meses_adelante + 1):
        factor = 1.0 - (i / (meses_adelante + 1))
        fecha = (ultima_fecha + pd.DateOffset(months=i)).replace(day=15)
        rows.append({'fecha': fecha, 'oni_value': ultimo_valor * factor})

    df_prono = pd.DataFrame(rows)
    logger.warning(
        f"⚠️ ONI por persistencia (fallback): {ultimo_valor:.2f}°C → "
        f"decay to 0 en {meses_adelante}m"
    )
    return df_prono


def generate_oni_forecast(df_historical: pd.DataFrame, meses_adelante: int = 9) -> pd.DataFrame:
    """
    Genera pronóstico ONI usando la tabla de probabilidades de intensidad NOAA CPC.

    Método preferido: E[ONI] = Σ P(bin_i) × midpoint(bin_i), donde los bins son
    las 9 categorías de intensidad (≤-2.0°C ... ≥+2.0°C) y las probabilidades
    provienen del pronóstico oficial multi-modelo de NOAA.

    Fallback (si NOAA no disponible): persistencia + decaimiento lineal.

    Args:
        df_historical: DataFrame con [fecha, oni_value] — para el fallback
        meses_adelante: Meses de pronóstico a generar (solo para el fallback)

    Returns:
        DataFrame con [fecha, oni_value] para los próximos meses
    """
    df_strengths = fetch_enso_strength_probabilities()
    if df_strengths is not None:
        df_expected = _oni_expected_from_strength_table(df_strengths)
        if df_expected is not None and not df_expected.empty:
            logger.info("✅ Pronóstico ONI: tabla de probabilidades NOAA (método científico)")
            return df_expected
        logger.warning("⚠️ Tabla NOAA descargada pero no se pudo procesar")

    logger.warning("⚠️ Pronóstico ONI: usando persistencia climática (NOAA no disponible)")
    return _generate_persistence_forecast(df_historical, meses_adelante)


# ---------------------------------------------------------------------------
# INTERPOLACIÓN MENSUAL → DIARIO
# ---------------------------------------------------------------------------
def interpolate_monthly_to_daily(df_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Interpola valores mensuales (día 15 de cada mes) a resolución diaria
    mediante interpolación lineal.

    Args:
        df_monthly: DataFrame con [fecha, oni_value] (uno por mes)

    Returns:
        DataFrame con [fecha, oni_value] (uno por día, interpolado)
    """
    if df_monthly is None or df_monthly.empty:
        return pd.DataFrame(columns=['fecha', 'oni_value'])

    df = df_monthly.copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.sort_values('fecha').set_index('fecha')

    fecha_min = df.index.min()
    fecha_max = df.index.max()
    idx_diario = pd.date_range(fecha_min, fecha_max, freq='D')

    df_daily = df.reindex(idx_diario)
    df_daily['oni_value'] = df_daily['oni_value'].interpolate(method='time')

    df_daily = df_daily.reset_index().rename(columns={'index': 'fecha'})
    df_daily['fecha'] = df_daily['fecha'].dt.normalize()

    logger.info(
        f"📅 ONI interpolado: {len(df_daily)} días | "
        f"{df_daily['fecha'].min().date()} → {df_daily['fecha'].max().date()}"
    )
    return df_daily[['fecha', 'oni_value']].dropna()


# ---------------------------------------------------------------------------
# PIPELINE COMPLETO
# ---------------------------------------------------------------------------
def get_oni_complete(
    meses_historico: int = 36,
    meses_pronostico: int = 9,
    timeout: int = 60,
) -> Optional[pd.DataFrame]:
    """
    Pipeline completo: descarga → pronóstico → interpolación diaria.

    Args:
        meses_historico: Meses de historia reciente a cargar (0 = todos desde 1950)
        meses_pronostico: Meses de pronóstico por persistencia
        timeout: Timeout HTTP en segundos

    Returns:
        DataFrame con [fecha, oni_value, es_pronostico] interpolado a diario,
        o None si falla la descarga histórica.
        Las fechas futuras tienen es_pronostico=True.
    """
    df_hist = fetch_oni_historical(timeout=timeout)
    if df_hist is None:
        return None

    if meses_historico > 0:
        fecha_corte = pd.Timestamp.today() - pd.DateOffset(months=meses_historico)
        df_hist = df_hist[df_hist['fecha'] >= fecha_corte]
        if df_hist.empty:
            logger.warning(f"⚠️ Sin datos ONI en los últimos {meses_historico} meses")
            return None

    df_prono = generate_oni_forecast(df_hist, meses_adelante=meses_pronostico)

    df_hist_tag = df_hist.copy()
    df_hist_tag['es_pronostico'] = False
    df_prono_tag = df_prono.copy()
    df_prono_tag['es_pronostico'] = True

    df_combined_monthly = pd.concat([df_hist_tag, df_prono_tag], ignore_index=True)
    df_combined_monthly = df_combined_monthly.sort_values('fecha').reset_index(drop=True)

    df_daily_oni = interpolate_monthly_to_daily(
        df_combined_monthly[['fecha', 'oni_value']]
    )

    hoy = pd.Timestamp.today().normalize()
    df_daily_oni['es_pronostico'] = df_daily_oni['fecha'] > hoy

    return df_daily_oni
