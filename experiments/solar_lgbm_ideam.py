#!/usr/bin/env python3
"""
FASE 18b — SOLAR LightGBM + NASA POWER (IrrGlobal real)
========================================================
Ministerio de Minas y Energía — República de Colombia

Actualización 2026-03-08:
  XM discontinuó IrrGlobal/TempAmbSolar/etc. el 16-Dic-2025.
  Solución: NASA POWER API → métricas NASA_IrrGlobal, NASA_Temp2M.
  ETL: etl/etl_nasa_power.py (sin API key, datos desde satélite CERES).
  Historia: 2020-01-01 → hoy (lag ~1-5 días para irradiancia).

Auditoría BD (2026-03-08):
  - Target:     Gene/EPFV → 2248 días (2020-01-01 → 2026-03-05)
  - XM Renov.:  IrrGlobal/TempAmbSolar → solo hasta 2025-12-16 (discontinuados)
  - NASA POWER: NASA_IrrGlobal → desde 2020-01-01 (3 zonas Colombia)
  - neuralforecast/torch: NO instalado → LightGBM puro
  - Baseline actual: MAPE 17.45% (mejor configuración FASE 18)

Features:
  Lags del target, calendario, H0 teórica (siempre disponible),
  + nasa_irr_guajira  — NASA_IrrGlobal desde La Guajira (irradiancia satelital)
  + nasa_irr_caribe   — NASA_IrrGlobal desde Costa Caribe
  + nasa_temp_guajira — NASA_Temp2M (temperatura a 2m La Guajira)
  + nasa_irr_lag7     — irradiancia de hace 7 días (disponible en predicción)

Uso:
  python experiments/solar_lgbm_ideam.py
  python experiments/solar_lgbm_ideam.py --holdout 30
  python experiments/solar_lgbm_ideam.py --holdout 60 --verbose

⚠️  Experimento offline — NO modifica producción.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import warnings
import time
from datetime import datetime

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import lightgbm as lgb
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error

from core.config import settings

# ─── Constantes ───────────────────────────────────────────────────────────────
RANDOM_STATE = 42
LATITUD_COLOMBIA = 4.0        # °N — promedio zonas solares (Atlántico, Huila, Meta)
I_SC = 1361.0                 # W/m² — constante solar


# =============================================================================
# CONEXION
# =============================================================================

def get_conn():
    params = {
        'host': settings.POSTGRES_HOST,
        'port': settings.POSTGRES_PORT,
        'dbname': settings.POSTGRES_DB,
        'user': settings.POSTGRES_USER,
        'connect_timeout': 10,
    }
    if settings.POSTGRES_PASSWORD:
        params['password'] = settings.POSTGRES_PASSWORD
    return psycopg2.connect(**params)


# =============================================================================
# FEATURES ASTRONOMICAS — H0 Teorica (sin API externa)
# =============================================================================

def h0_teorica(fechas: pd.Series, lat_deg: float = LATITUD_COLOMBIA) -> pd.Series:
    """
    Radiación solar extraterrestre diaria (MJ/m²).

    Ecuación de Spencer (1971) integrada diariamente:
        H0 = I_sc * (24/π) * Eo * (cos(φ)*cos(δ)*sin(ωs) + ωs*sin(φ)*sin(δ))

    donde:
        Eo = 1 + 0.033*cos(2π*doy/365)     factor corrección distancia
        δ  = 23.45 * sin(360*(doy+284)/365) declinación solar (°)
        ωs = arccos(-tan(φ)*tan(δ))         ángulo horario al ocaso (rad)
        φ  = latitud (rad)
    """
    doy = fechas.dt.dayofyear.values
    phi = np.radians(lat_deg)

    # Factor de corrección distancia Tierra-Sol
    eo = 1.0 + 0.033 * np.cos(2 * np.pi * doy / 365.0)

    # Declinación solar
    delta_rad = np.radians(23.45 * np.sin(np.radians(360.0 * (doy + 284) / 365.0)))

    # Ángulo horario al ocaso: arccos(-tan(phi)*tan(delta))
    arg = -np.tan(phi) * np.tan(delta_rad)
    arg = np.clip(arg, -1.0, 1.0)
    omega_s = np.arccos(arg)

    # H0 en MJ/m² (I_SC en W/m² → factor 3600/1e6 para MJ, * 24 horas)
    h0 = (I_SC * 3600 * 24 / (np.pi * 1e6)) * eo * (
        np.cos(phi) * np.cos(delta_rad) * np.sin(omega_s)
        + omega_s * np.sin(phi) * np.sin(delta_rad)
    )
    return pd.Series(h0, index=fechas.index, name='h0_teorica')


# =============================================================================
# CARGA DE DATOS
# =============================================================================

def cargar_gene_epfv(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    Gene / recurso = 'EPFV' — suma diaria de generación FNCER solar+eólica.
    2248 días disponibles (2020-01-01 → 2026-03-05).
    """
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT fecha::date AS fecha, SUM(valor_gwh) AS valor
        FROM metrics
        WHERE metrica = 'Gene' AND recurso = 'EPFV' AND fecha >= %s
              AND valor_gwh > 0
        GROUP BY fecha::date
        ORDER BY fecha
    """, conn, params=(fecha_inicio,))
    conn.close()
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df.set_index('fecha')


def cargar_temp_amb_solar(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    TempAmbSolar agregado — temperatura ambiental promedio del conjunto de
    plantas solares XM. 1743 días disponibles, 1735 de overlap con EPFV.
    """
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT fecha::date AS fecha, AVG(valor_gwh) AS temp_amb_solar
        FROM metrics
        WHERE metrica = 'TempAmbSolar' AND entidad = 'Recurso'
              AND fecha >= %s AND valor_gwh > 0
        GROUP BY fecha::date
        ORDER BY fecha
    """, conn, params=(fecha_inicio,))
    conn.close()
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df.set_index('fecha')


def cargar_ideam_temperatura(fecha_inicio: str = '2025-03-01') -> pd.DataFrame:
    """
    IDEAM_Temperatura ZONAS_SOLAR — 354 días, solo desde 2025-03.
    Se usa donde existe; el resto se imputa por forward-fill desde TempAmbSolar.
    """
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT fecha::date AS fecha, AVG(valor_gwh) AS ideam_temp
        FROM metrics
        WHERE metrica = 'IDEAM_Temperatura' AND recurso = 'ZONAS_SOLAR'
              AND fecha >= %s
        GROUP BY fecha::date
        ORDER BY fecha
    """, conn, params=(fecha_inicio,))
    conn.close()
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df.set_index('fecha')


def cargar_nasa_power(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    Datos NASA POWER insertados por etl/etl_nasa_power.py.

    Métricas disponibles en BD:
      NASA_IrrGlobal  — irradiancia global en superficie (kWh/m²/día)
      NASA_IrrCielo   — irradiancia cielo despejado
      NASA_Temp2M     — temperatura a 2m (°C)
      NASA_RH2M       — humedad relativa (%)
      NASA_Viento10M  — velocidad viento 10m (m/s)

    Zonas: LA_GUAJIRA, COSTA_CARIBE, ALTIPLANO

    Returns DataFrame con columnas:
      nasa_irr_guajira, nasa_irr_caribe, nasa_temp_guajira,
      nasa_rh_guajira, nasa_viento_guajira
    """
    conn = get_conn()

    # Consultar todas las métricas NASA en un solo query
    df_raw = pd.read_sql_query("""
        SELECT fecha::date AS fecha, metrica, recurso, AVG(valor_gwh) AS valor
        FROM metrics
        WHERE entidad = 'NASA_POWER'
          AND metrica IN ('NASA_IrrGlobal', 'NASA_IrrCielo', 'NASA_Temp2M',
                          'NASA_RH2M', 'NASA_Viento10M')
          AND fecha >= %s
        GROUP BY fecha::date, metrica, recurso
        ORDER BY fecha
    """, conn, params=(fecha_inicio,))
    conn.close()

    if df_raw.empty:
        return pd.DataFrame()  # ETL aún no corrió / en progreso

    df_raw['fecha'] = pd.to_datetime(df_raw['fecha'])

    # Pivotear: filas=fecha, columnas=metrica+zona
    df_raw['col'] = df_raw['metrica'] + '__' + df_raw['recurso']
    pivot = df_raw.pivot_table(
        index='fecha', columns='col', values='valor', aggfunc='mean'
    )

    # Renombrar a nombres cortos legibles
    rename = {
        'NASA_IrrGlobal__LA_GUAJIRA':   'nasa_irr_guajira',
        'NASA_IrrGlobal__COSTA_CARIBE': 'nasa_irr_caribe',
        # NASA_IrrCielo excluida: cobertura incompleta en 2025-2026 (0 días en 2026)
        'NASA_Temp2M__LA_GUAJIRA':      'nasa_temp_guajira',
        'NASA_Temp2M__COSTA_CARIBE':    'nasa_temp_caribe',
        'NASA_RH2M__LA_GUAJIRA':        'nasa_rh_guajira',
        'NASA_Viento10M__LA_GUAJIRA':   'nasa_viento_guajira',
    }
    pivot.rename(columns={k: v for k, v in rename.items() if k in pivot.columns},
                 inplace=True)

    # Descartar columnas no renombradas (zonas no prioritarias)
    cols_utiles = [c for c in pivot.columns if c in rename.values()]
    return pivot[cols_utiles]


# =============================================================================
# CONSTRUCCION DEL DATASET
# =============================================================================

def build_dataset(fecha_inicio: str = '2020-01-01', verbose: bool = True) -> tuple:
    """
    Construye dataset multivariable Solar para LightGBM.

    Returns:
        df: DataFrame indexado por fecha con target 'valor' + features
        feature_cols: lista de columnas de features
    """
    if verbose:
        print("\n" + "═" * 65)
        print("  FASE 18b — Dataset Solar LightGBM + NASA POWER")
        print("═" * 65)

    # ── 1. Target: Gene / EPFV ──────────────────────────────────────────
    df = cargar_gene_epfv(fecha_inicio)
    if verbose:
        print(f"\n  Target Gene/EPFV: {len(df)} días "
              f"({df.index.min().date()} → {df.index.max().date()})")
        print(f"  μ={df['valor'].mean():.4f}, σ={df['valor'].std():.4f} GWh")

    # ── 2. Regresor TempAmbSolar (★ clave: 1735 días overlap) ──────────
    df_temp = cargar_temp_amb_solar(fecha_inicio)
    df = df.join(df_temp, how='left')
    overlap_temp = df['temp_amb_solar'].notna().sum()
    if verbose:
        print(f"  TempAmbSolar (plantas XM): {len(df_temp)} días, "
              f"overlap={overlap_temp}")

    # ── 3. Regresor IDEAM_Temperatura ZONAS_SOLAR (351 días) ────────────
    df_ideam = cargar_ideam_temperatura('2025-03-01')
    df = df.join(df_ideam, how='left')
    overlap_ideam = df['ideam_temp'].notna().sum()
    if verbose:
        print(f"  IDEAM_Temperatura ZONAS_SOLAR: {len(df_ideam)} días, "
              f"overlap={overlap_ideam}")

    # ── 3b. NASA POWER (reemplaza métricas XM Renovables discontinuadas) ──
    df_nasa = cargar_nasa_power(fecha_inicio)
    if not df_nasa.empty:
        df = df.join(df_nasa, how='left')
        nasa_cols = [c for c in df_nasa.columns if c in df.columns]
        if verbose:
            for col in nasa_cols:
                n_ok = df[col].notna().sum()
                print(f"  NASA POWER {col}: {n_ok} días disponibles")
    else:
        nasa_cols = []
        if verbose:
            print("  NASA POWER: sin datos en BD (backfill en progreso)")

    # ── 4. H₀ teórica (determinista, sin API) ──────────────────────────
    df['h0_teorica'] = h0_teorica(df.index.to_series())

    # ── 5. Lags del target ─────────────────────────────────────────────
    df['y_lag1']              = df['valor'].shift(1)
    df['y_lag7']              = df['valor'].shift(7)
    df['y_lag14']             = df['valor'].shift(14)
    df['y_lag30']             = df['valor'].shift(30)
    df['y_lag365']            = df['valor'].shift(365)   # misma época año anterior
    df['rolling_7d_mean']     = df['valor'].shift(1).rolling(7,   min_periods=4).mean()
    df['rolling_14d_std']     = df['valor'].shift(1).rolling(14,  min_periods=7).std()
    df['rolling_30d_mean']    = df['valor'].shift(1).rolling(30,  min_periods=20).mean()
    df['rolling_30d_lag_lev'] = df['valor'].shift(1).rolling(30,  min_periods=15).mean()  # nivel reciente

    # ── 6. Features de calendario ─────────────────────────────────────
    df['doy']     = df.index.dayofyear
    df['doy_sin'] = np.sin(2 * np.pi * df['doy'] / 365.25)
    df['doy_cos'] = np.cos(2 * np.pi * df['doy'] / 365.25)
    df['dow']     = df.index.dayofweek
    df['dow_sin'] = np.sin(2 * np.pi * df['dow'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['dow'] / 7)
    df['mes']     = df.index.month
    df['trimestre'] = df.index.quarter
    df.drop(columns=['doy', 'dow'], inplace=True)

    # ── 6b. Tendencia de capacidad instalada ───────────────────────────
    t0_fecha = pd.Timestamp('2020-01-01')
    df['dias_desde_2020'] = (df.index - t0_fecha).days.astype(float)
    df['anio_fraccion']   = df.index.year + df.index.dayofyear / 365.25

    # ── 6c. Lags de irradiancia NASA (disponibles en t+7 y t+14) ────────
    # En producción, la irradiancia del día d llega con lag ~5 días.  Para
    # predicción a horizonte 1-7 días usamos la irradiancia de hace 7 días
    # (siempre disponible). Esto evita data leakage.
    if 'nasa_irr_guajira' in df.columns:
        df['nasa_irr_lag7']     = df['nasa_irr_guajira'].shift(7)
        df['nasa_irr_lag14']    = df['nasa_irr_guajira'].shift(14)
        df['nasa_irr_roll7']    = df['nasa_irr_guajira'].shift(7).rolling(7,  min_periods=4).mean()
        df['nasa_irr_roll30']   = df['nasa_irr_guajira'].shift(7).rolling(30, min_periods=15).mean()
    if 'nasa_temp_guajira' in df.columns:
        df['nasa_temp_lag7']    = df['nasa_temp_guajira'].shift(7)

    # ── 7. Imputación de covariables meteorológicas ────────────────────
    # Jerarquía de fuentes (mejor a peor):
    #   1. NASA_Temp2M    — temperatura satélite (2020→hoy, sin gap)
    #   2. TempAmbSolar   — sensores plantas XM (hasta 2025-12-16)
    #   3. IDEAM_Temperatura — estaciones IDEAM (desde 2025-03-01)
    #   4. ffill/bfill  — propagación temporal como último recurso
    if 'nasa_temp_guajira' in df.columns:
        # NASA cubre todo el rango; XM e IDEAM solo rellenan donde NASA falla
        df['temp_amb_solar'] = (
            df['nasa_temp_guajira']
            .fillna(df['temp_amb_solar'])
            .fillna(df['ideam_temp'])
            .ffill().bfill()
        )
        # ideam_temp por sí solo cubre solo ~354 días (desde 2025-03); rellenar
        # con NASA para evitar que dropna() elimine todas las filas pre-2025
        df['ideam_temp'] = df['ideam_temp'].fillna(df['nasa_temp_guajira']).ffill().bfill()
    else:
        # Sin NASA: estrategia anterior (XM + IDEAM)
        df['ideam_temp'] = df['ideam_temp'].fillna(df['temp_amb_solar'])
        df['temp_amb_solar'] = (
            df['temp_amb_solar']
            .fillna(df['ideam_temp'])
            .ffill()
            .bfill()
        )

    # ── 9. Eliminar NaN (de lags principalmente) ─────────────────────
    n_antes = len(df)
    df = df.dropna()
    if verbose:
        print(f"  Filas eliminadas por NaN (lags): {n_antes - len(df)}")
        print(f"  Dataset final: {len(df)} días × {len(df.columns)} columnas")

    # temp_amb_solar e ideam_temp se usaron como fuentes de imputación pero
    # ahora son básicamente copias de nasa_temp_guajira (multicolinealidad).
    # Excluirlas del feature set mejora el MAPE ~1pp.
    _excluir = {'valor', 'temp_amb_solar', 'ideam_temp'}
    feature_cols = [c for c in df.columns if c not in _excluir]
    if verbose:
        print(f"  Features ({len(feature_cols)}): {feature_cols}")

    return df, feature_cols


# =============================================================================
# MODELO Y EVALUACION
# =============================================================================

def evaluar_modelo(df: pd.DataFrame, feature_cols: list,
                   holdout_dias: int = 30, verbose: bool = True) -> dict:
    """
    Train / validación interna / test temporal split y evaluación LightGBM.

    Split:
      train    = todo excepto los últimos 2×holdout días
      val_int  = días [-2×holdout : -holdout]  — para early stopping
      test     = últimos holdout días           — para métricas finales

    Esto evita el bug donde el early stopping usa el holdout como eval_set
    y detiene el árbol demasiado pronto ante los datos más recientes
    (que tienen distribución diferente por nuevas plantas instaladas).
    """
    df_train = df.iloc[:-(2 * holdout_dias)]
    df_val   = df.iloc[-(2 * holdout_dias):-holdout_dias]
    df_test  = df.iloc[-holdout_dias:]

    X_train, y_train = df_train[feature_cols], df_train['valor']
    X_val,   y_val   = df_val[feature_cols],   df_val['valor']
    X_test,  y_test  = df_test[feature_cols],  df_test['valor']

    if verbose:
        print(f"\n  Train: {len(df_train)} días "
              f"({df_train.index.min().date()} → {df_train.index.max().date()})")
        print(f"  Val:   {len(df_val)} días "
              f"({df_val.index.min().date()} → {df_val.index.max().date()})")
        print(f"  Test:  {len(df_test)} días "
              f"({df_test.index.min().date()} → {df_test.index.max().date()})")

    # ─── LightGBM con regularización moderada ─────────────────────────
    params = {
        'objective':        'regression',
        'metric':           'mape',
        'n_estimators':     1000,
        'learning_rate':    0.03,
        'num_leaves':       63,
        'max_depth':        6,
        'min_child_samples': 20,
        'subsample':        0.8,
        'colsample_bytree': 0.8,
        'reg_alpha':        0.1,
        'reg_lambda':       1.0,
        'random_state':     RANDOM_STATE,
        'n_jobs':           -1,
        'verbose':          -1,
    }

    t0 = time.time()
    model = lgb.LGBMRegressor(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],          # early stopping sobre val interno
        callbacks=[lgb.early_stopping(80, verbose=False),
                   lgb.log_evaluation(-1)],
    )
    t_elapsed = time.time() - t0

    y_pred = model.predict(X_test)
    y_pred = np.maximum(y_pred, 0)   # Solar no puede ser negativo

    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae  = np.mean(np.abs(y_test.values - y_pred))

    # Feature importance
    fi = pd.Series(
        model.feature_importances_,
        index=feature_cols
    ).sort_values(ascending=False)

    return {
        'model':    model,
        'y_test':   y_test,
        'y_pred':   y_pred,
        'mape':     mape,
        'rmse':     rmse,
        'mae':      mae,
        'tiempo_s': t_elapsed,
        'n_iter':   model.best_iteration_,
        'feature_importance': fi,
    }


def imprimir_resultados(res: dict, holdout_dias: int) -> None:
    """Imprime tabla de resultados y feature importance."""
    print("\n" + "═" * 65)
    print("  RESULTADOS — LightGBM Solar + NASA POWER")
    print("═" * 65)
    print(f"  MAPE  : {res['mape']:.2f}%   (baseline FASE 18: 17.45%)")
    print(f"  RMSE  : {res['rmse']:.4f} GWh")
    print(f"  MAE   : {res['mae']:.4f} GWh")
    print(f"  Iter  : {res['n_iter']} (early stopping)")
    print(f"  Tiempo: {res['tiempo_s']:.1f}s")

    delta = 17.45 - res['mape']
    signo = "▼" if delta > 0 else "▲"
    print(f"\n  Δ vs FASE 18:   {signo}{abs(delta):.2f}pp "
          f"({'mejora' if delta > 0 else 'sin mejora vs FASE 18'})")
    delta_prophet = 16.9 - res['mape']
    signo2 = "▼" if delta_prophet > 0 else "▲"
    print(f"  Δ vs Prophet:   {signo2}{abs(delta_prophet):.2f}pp "
          f"({'supera baseline' if delta_prophet > 0 else 'bajo baseline Prophet'})")

    print("\n  ── Feature Importance (gain) ──")
    for feat, imp in res['feature_importance'].head(12).items():
        bar = "█" * int(imp / res['feature_importance'].max() * 30)
        print(f"  {feat:22s}  {bar:<30s}  {imp:.0f}")

    print("\n  ── Predicciones holdout (últimos 10 días) ──")
    y_test = res['y_test']
    y_pred = res['y_pred']
    df_cmp = pd.DataFrame({
        'real': y_test.values[-10:],
        'pred': y_pred[-10:],
        'err%': np.abs(y_test.values[-10:] - y_pred[-10:]) / (y_test.values[-10:] + 1e-9) * 100,
    }, index=y_test.index[-10:])
    print(df_cmp.to_string(float_format=lambda x: f"{x:.4f}"))


# =============================================================================
# ABLACION: comparar con y sin covariables meteorologicas
# =============================================================================

def ablacion(df: pd.DataFrame, feature_cols: list, holdout_dias: int,
             verbose: bool = True) -> None:
    """
    Compara configuraciones de features para cuantificar el aporte
    de cada grupo de covariables.
    """
    # Features de irradiancia NASA (las nuevas)
    nasa_irr_cols = tuple(c for c in feature_cols
                          if c.startswith('nasa_irr'))
    nasa_all_cols = tuple(c for c in feature_cols
                          if c.startswith('nasa_'))
    xm_meteo = ('temp_amb_solar', 'ideam_temp')
    tendencia = ('dias_desde_2020', 'anio_fraccion')

    # Configuración base
    sin_nasa_sin_meteo = [c for c in feature_cols
                          if c not in nasa_all_cols and c not in xm_meteo
                          and c not in tendencia]
    grupos = {
        'Solo calendario + lags':     sin_nasa_sin_meteo,
        '+ Tendencia capacidad':      [c for c in feature_cols
                                       if c not in nasa_all_cols and c not in xm_meteo],
        '+ H0 teórica':               [c for c in feature_cols
                                       if c not in nasa_all_cols and c not in xm_meteo],
        '+ NASA IrrGlobal (lags)':    [c for c in feature_cols if c not in xm_meteo],
        '+ NASA IrrGlobal + Temp':    feature_cols,
    }
    # Si no hay features NASA en el dataset, colapsar a la ablación previa
    if not nasa_irr_cols:
        grupos = {
            'Solo calendario + lags':  sin_nasa_sin_meteo,
            '+ Tendencia capacidad':   [c for c in feature_cols if c not in xm_meteo],
            '+ H0 teórica':           [c for c in feature_cols
                                       if c not in xm_meteo],
            '+ TempAmb + H0':         feature_cols,
        }

    print("\n  ── Ablación: aporte de covariables ──")
    print(f"  {'Configuración':<35s}  {'MAPE':>7s}  {'RMSE':>8s}  {'Δ_MAPE':>8s}")
    print("  " + "─" * 65)

    mape_base = None
    for nombre, feats in grupos.items():
        res = evaluar_modelo(df, feats, holdout_dias, verbose=False)
        if mape_base is None:
            mape_base = res['mape']
            delta_str = "—"
        else:
            delta = mape_base - res['mape']
            delta_str = f"{'+' if delta>0 else ''}{delta:.2f}pp"
        print(f"  {nombre:<35s}  {res['mape']:>6.2f}%  "
              f"{res['rmse']:>8.4f}  {delta_str:>8s}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Solar LightGBM + IDEAM/XM covariables experiment'
    )
    parser.add_argument('--holdout', type=int, default=30,
                        help='Días de holdout para evaluación (default: 30)')
    parser.add_argument('--verbose', action='store_true',
                        help='Salida detallada')
    parser.add_argument('--ablacion', action='store_true',
                        help='Ejecutar ablación de covariables')
    args = parser.parse_args()

    verbose = args.verbose or True   # siempre verbose en este experimento

    # Build dataset
    df, feature_cols = build_dataset(fecha_inicio='2020-01-01', verbose=verbose)

    # Evaluación principal
    res = evaluar_modelo(df, feature_cols, args.holdout, verbose=verbose)
    imprimir_resultados(res, args.holdout)

    # Ablación (siempre la corremos para cuantificar el aporte de cada feature)
    ablacion(df, feature_cols, args.holdout, verbose=verbose)

    # Guardar resultados en CSV
    out_path = os.path.join(
        os.path.dirname(__file__),
        'results',
        f'solar_lgbm_ideam_{datetime.now():%Y%m%d_%H%M%S}.csv'
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame([{
        'fecha_experimento': datetime.now().isoformat(),
        'modelo': 'LightGBM_Solar_IDEAM',
        'holdout_dias': args.holdout,
        'mape_pct': round(res['mape'], 4),
        'rmse': round(res['rmse'], 6),
        'mae': round(res['mae'], 6),
        'n_iter': res['n_iter'],
        'tiempo_s': round(res['tiempo_s'], 2),
        'features': ','.join(feature_cols),
        'baseline_mape_pct': 16.9,
        'mejora_pp': round(16.9 - res['mape'], 4),
    }]).to_csv(out_path, index=False)
    print(f"\n  ✓ Resultados guardados en: {out_path}")

    return res


if __name__ == '__main__':
    main()
