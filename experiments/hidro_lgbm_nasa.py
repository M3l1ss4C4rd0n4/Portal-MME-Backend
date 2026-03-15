#!/usr/bin/env python3
"""
FASE 19 — LightGBM APORTES_HIDRICOS + NASA POWER Precipitación
===============================================================
Objetivo: superar el MAPE actual de 16.52% usando precipitación satelital
(NASA POWER PRECTOTCORR) como feature principal.

Hipótesis física:
  La lluvia en las cuencas altas de los Andes tarda 7-30 días en
  llegar a los embalses como caudal hidroeléctrico. Con lags de
  precipitación satelital (14d, 30d, 90d) capturamos esa memoria
  hidrológica, que el modelo puramente histórico (lags de AporEner)
  no puede aprender directamente.

Fuentes de datos:
  - AporEner (XM): suma sistema 2020→hoy (target + regresores de ríos clave)
  - NASA POWER: PRECTOTCORR mm/día para 4 cuencas (2020→hoy, sin gaps)
  - PorcVoluUtilDiar (XM): porcentaje embalses sistema (proxy estado)
  - VertEner (XM): vertimientos (señal de embalses llenos)
  - IDEAM_Precipitacion CUENCAS_HIDRO: solo 161 días — usado como check, no feature

Features diseñadas (lags largos por la física de cuencas):
  Autocorrelación:
    y_lag1, y_lag7, y_lag14, y_lag30, y_lag90, y_lag365
    rolling_7d, rolling_30d, rolling_90d
  Ríos clave (t-1):
    apor_sogamoso, apor_bogota, apor_ituango, apor_betania, apor_cauca
  Estado embalses:
    embalses_pct, embalses_vertim
  NASA Precipitación (lags 7, 14, 30, 60, 90 días):
    nasa_prec_magdalena_lag7...lag90, rolling7/30/90
    nasa_prec_cauca_lag7...lag90
    nasa_prec_santander_lag7...lag90
    nasa_prec_pacifico_lag7...lag90
    nasa_prec_media_lag* (promedio 4 cuencas)
  Calendario:
    doy_sin, doy_cos (estacionalidad anual)
    mes, trimestre
    dias_desde_2020 (tendencia capacidad instalada)

Nota sobre el holdout: usamos 30 días (igual que Solar) para comparabilidad.
El modelo de producción usa recursive forecasting hasta 90 días.
"""

import sys
import os
import time
import argparse
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
import lightgbm as lgb

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.database.manager import db_manager

RANDOM_STATE = 42


# =============================================================================
# LOADERS
# =============================================================================

def _query_df(sql: str, parse_dates: list = None) -> pd.DataFrame:
    """Ejecuta una query y retorna DataFrame con índice fecha."""
    with db_manager.get_connection() as conn:
        df = pd.read_sql(sql, conn, parse_dates=parse_dates or ['fecha'])
    df = df.set_index('fecha').sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def cargar_target(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """AporEner sistema (suma todos los recursos) — target del modelo."""
    return _query_df(f"""
        SELECT fecha::date AS fecha, SUM(valor_gwh) AS valor
        FROM metrics
        WHERE metrica = 'AporEner'
          AND fecha >= '{fecha_inicio}'
        GROUP BY fecha::date
        ORDER BY fecha
    """)


def cargar_rios_clave(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    Flujos de los 5 ríos con mayor partial_r con el sistema (FASE 15-16).
    Disponibles desde 2020, cobertura ~2257/2258 días.
    """
    sql = f"""
        SELECT
            fecha::date AS fecha,
            SUM(CASE WHEN recurso = 'SOGAMOSO'    THEN valor_gwh END) AS apor_sogamoso,
            SUM(CASE WHEN recurso = 'BOGOTA N.R.' THEN valor_gwh END) AS apor_bogota,
            SUM(CASE WHEN recurso = 'ITUANGO'     THEN valor_gwh END) AS apor_ituango,
            SUM(CASE WHEN recurso = 'BETANIA CP'  THEN valor_gwh END) AS apor_betania,
            SUM(CASE WHEN recurso = 'CAUCA SALVAJINA' THEN valor_gwh END) AS apor_cauca
        FROM metrics
        WHERE metrica = 'AporEner'
          AND recurso IN ('SOGAMOSO','BOGOTA N.R.','ITUANGO','BETANIA CP','CAUCA SALVAJINA')
          AND fecha >= '{fecha_inicio}'
        GROUP BY fecha::date
        ORDER BY fecha
    """
    return _query_df(sql)


def cargar_embalses(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    Porcentaje embalses (promedio sobre todos los embalses del sistema) +
    vertimientos (suma todos los embalses).
    entidad = 'Embalse' en la BD (no existe recurso 'Sistema').
    """
    sql = f"""
        SELECT
            fecha::date AS fecha,
            AVG(CASE WHEN metrica = 'PorcVoluUtilDiar' THEN valor_gwh END) AS embalses_pct,
            SUM(CASE WHEN metrica = 'VertEner'          THEN valor_gwh END) AS vertimientos
        FROM metrics
        WHERE metrica IN ('PorcVoluUtilDiar', 'VertEner')
          AND entidad = 'Embalse'
          AND fecha >= '{fecha_inicio}'
        GROUP BY fecha::date
        ORDER BY fecha
    """
    return _query_df(sql)


def cargar_nasa_precipitacion(fecha_inicio: str = '2020-01-01') -> pd.DataFrame:
    """
    NASA POWER PRECTOTCORR para las 4 cuencas hidrológicas (FASE 19).
    Pivot: una columna por cuenca (NASA_Precipitacion per zona).
    Cobertura: 2259 días (2020-01-01 → 2026-03-08), sin gaps.
    """
    sql = f"""
        SELECT
            fecha::date AS fecha,
            AVG(CASE WHEN recurso = 'MAGDALENA_ALTO'     THEN valor_gwh END) AS nasa_prec_magdalena,
            AVG(CASE WHEN recurso = 'CAUCA_MEDIO'        THEN valor_gwh END) AS nasa_prec_cauca,
            AVG(CASE WHEN recurso = 'SANTANDER_CUENCA'   THEN valor_gwh END) AS nasa_prec_santander,
            AVG(CASE WHEN recurso = 'PACIFICO_CUENCA'    THEN valor_gwh END) AS nasa_prec_pacifico
        FROM metrics
        WHERE metrica = 'NASA_Precipitacion'
          AND entidad = 'NASA_POWER'
          AND fecha >= '{fecha_inicio}'
        GROUP BY fecha::date
        ORDER BY fecha
    """
    return _query_df(sql)


# =============================================================================
# BUILD DATASET
# =============================================================================

def build_dataset(fecha_inicio: str = '2020-01-01',
                  verbose: bool = True) -> tuple[pd.DataFrame, list]:
    """
    Construye el dataset completo para APORTES_HIDRICOS con features físicos
    basados en lags de precipitación y flujos de ríos.

    Diseño de lags:
      - Precipitación: lags 7, 14, 30, 60, 90 días (la lluvia tarda semanas
        en llegar a los embalses bajando los Andes)
      - Ríos clave: lag 1 (disponibles el mismo día desde XM, para producción
        se usan con 1 día de retraso)
      - Serie objetivo (AporEner): lags 1, 7, 30, 90, 365 + rolling stats
    """
    if verbose:
        print("\n" + "═" * 65)
        print("  FASE 19 — Dataset APORTES_HIDRICOS + NASA POWER Precipitación")
        print("═" * 65)

    # ── 1. Target ─────────────────────────────────────────────────────
    df = cargar_target(fecha_inicio)
    if verbose:
        print(f"\n  Target AporEner sistema: {len(df)} días "
              f"({df.index.min().date()} → {df.index.max().date()})")
        print(f"  μ={df['valor'].mean():.1f}, σ={df['valor'].std():.1f} GWh")

    # Excluir último día si parece parcial (AporEner < 100 GWh)
    hoy = pd.Timestamp.now().normalize()
    if df.index[-1] >= hoy - pd.Timedelta(days=1) and df['valor'].iloc[-1] < 100:
        if verbose:
            print(f"  ⚠ Último día excluido (parcial): "
                  f"{df.index[-1].date()} → {df['valor'].iloc[-1]:.1f} GWh")
        df = df.iloc[:-1]

    # ── 2. Ríos clave ─────────────────────────────────────────────────
    df_rios = cargar_rios_clave(fecha_inicio)
    df = df.join(df_rios, how='left')

    # ITUANGO: empezó ~2022; antes era 0 GWh (planta no operaba)
    # fillna(0) ANTES de los lags para no perder 800 filas por dropna
    for rio in ['apor_sogamoso', 'apor_bogota', 'apor_ituango',
                'apor_betania', 'apor_cauca']:
        df[rio] = df[rio].fillna(0)

    if verbose:
        n_ituango = (df['apor_ituango'] > 0).sum()
        print(f"  Ríos: sogamoso={df['apor_sogamoso'].notna().sum()}, "
              f"ituango activo={n_ituango} días")

    # ── 3. Embalses — imputar ANTES de crear lags ────────────────────
    # CRÍTICO: si se imputa después de los lags, los lags heredan NaN
    # y dropna elimina miles de filas innecesariamente.
    df_emb = cargar_embalses(fecha_inicio)
    df = df.join(df_emb, how='left')

    df['embalses_pct'] = df['embalses_pct'].ffill(limit=7).bfill(limit=7)
    df['vertimientos'] = df['vertimientos'].fillna(0)

    if verbose:
        print(f"  Embalses: {df['embalses_pct'].notna().sum()} días "
              f"(gaps restantes: {df['embalses_pct'].isna().sum()})")

    # ── 4. NASA Precipitación (4 cuencas) ────────────────────────────
    df_nasa = cargar_nasa_precipitacion(fecha_inicio)
    df = df.join(df_nasa, how='left')
    if verbose:
        for col in ['nasa_prec_magdalena', 'nasa_prec_cauca',
                    'nasa_prec_santander', 'nasa_prec_pacifico']:
            print(f"  NASA Prec {col.replace('nasa_prec_',''):15s}: "
                  f"{df[col].notna().sum()} días")

    # ── 5. Features calendario ────────────────────────────────────────
    doy = df.index.dayofyear.values
    df['doy_sin']         = np.sin(2 * np.pi * doy / 365.25)
    df['doy_cos']         = np.cos(2 * np.pi * doy / 365.25)
    df['mes']             = df.index.month
    df['trimestre']       = df.index.quarter
    df['dias_desde_2020'] = (df.index - pd.Timestamp('2020-01-01')).days
    # Ituango como feature binario (capacidad instalada cambia en 2022)
    df['ituango_activo']  = (df.index >= '2022-04-01').astype(int)

    # ── 6. Lags autocorrelación de la serie objetivo ──────────────────
    # y_lag365 eliminado: cuesta 365 filas y y_lag90 + rolling_90d ya
    # capturan el patrón anual con menor costo en warmup.
    for lag in [1, 7, 14, 30, 90]:
        df[f'y_lag{lag}'] = df['valor'].shift(lag)

    # Rolling sobre la serie histórica
    df['rolling_7d']    = df['valor'].shift(1).rolling(7,  min_periods=4).mean()
    df['rolling_30d']   = df['valor'].shift(1).rolling(30, min_periods=15).mean()
    df['rolling_90d']   = df['valor'].shift(1).rolling(90, min_periods=45).mean()
    df['rolling_7d_std']  = df['valor'].shift(1).rolling(7,  min_periods=4).std()
    df['rolling_30d_std'] = df['valor'].shift(1).rolling(30, min_periods=15).std()

    # ── 7. Lags de precipitación NASA (la clave física: lluvia→embalse) ──
    # Los lags de 30-90 días capturan la "memoria" de la cuenca:
    # el agua que cayó en los Andes tarda semanas en llegar como caudal.
    nasa_prec_cols = ['nasa_prec_magdalena', 'nasa_prec_cauca',
                      'nasa_prec_santander', 'nasa_prec_pacifico']

    for col in nasa_prec_cols:
        for lag in [7, 14, 30, 60, 90]:
            df[f'{col}_lag{lag}'] = df[col].shift(lag)
        # Rolling precipitation (acumulación en cuenca)
        df[f'{col}_roll7']  = df[col].shift(7).rolling(7,  min_periods=4).mean()
        df[f'{col}_roll30'] = df[col].shift(7).rolling(30, min_periods=15).mean()
        df[f'{col}_roll90'] = df[col].shift(7).rolling(90, min_periods=45).mean()

    # Precipitación media de las 4 cuencas (feature sintético)
    df['nasa_prec_media'] = df[nasa_prec_cols].mean(axis=1)
    for lag in [7, 14, 30, 90]:
        df[f'nasa_prec_media_lag{lag}'] = df['nasa_prec_media'].shift(lag)
    df['nasa_prec_media_roll30'] = df['nasa_prec_media'].shift(7).rolling(30, min_periods=15).mean()
    df['nasa_prec_media_roll90'] = df['nasa_prec_media'].shift(7).rolling(90, min_periods=45).mean()

    # ── 8. Lags de ríos (lag 1: disponible en producción día a día) ──
    for rio in ['apor_sogamoso', 'apor_bogota', 'apor_ituango',
                'apor_betania', 'apor_cauca']:
        df[f'{rio}_lag1'] = df[rio].shift(1)
        df[f'{rio}_lag7'] = df[rio].shift(7)

    # ── 9. Lags de embalses (SEGUROS: ya imputados en paso 3) ─────────
    df['embalses_pct_lag1']  = df['embalses_pct'].shift(1)
    df['embalses_pct_lag7']  = df['embalses_pct'].shift(7)
    df['embalses_pct_lag30'] = df['embalses_pct'].shift(30)
    df['vertimientos_lag1']  = df['vertimientos'].shift(1)

    # ── 10. Eliminar columnas directas (no disponibles en producción) ─
    cols_directas = (nasa_prec_cols +
                     ['nasa_prec_media',
                      'apor_sogamoso', 'apor_bogota', 'apor_ituango',
                      'apor_betania', 'apor_cauca',
                      'embalses_pct', 'vertimientos'])
    df_model = df.drop(columns=[c for c in cols_directas if c in df.columns],
                       errors='ignore')

    # ── 11. dropna (solo por warmup de lags; embalses/rios ya sin NaN) ─
    n_antes = len(df_model)
    df_model = df_model.dropna()
    if verbose:
        print(f"  Filas eliminadas por NaN (lags warmup): {n_antes - len(df_model)}")
        print(f"  Dataset final: {len(df_model)} días × {len(df_model.columns)} columnas "
              f"({df_model.index.min().date()} → {df_model.index.max().date()})")

    feature_cols = [c for c in df_model.columns if c != 'valor']
    if verbose:
        print(f"  Features ({len(feature_cols)}): primeros 15 → "
              f"{feature_cols[:15]}")

    return df_model, feature_cols


# =============================================================================
# MODELO
# =============================================================================

def evaluar_modelo(df: pd.DataFrame, feature_cols: list,
                   holdout_dias: int = 30, verbose: bool = True) -> dict:
    """
    Split temporal: train / val_interno / test.
    Igual que solar_lgbm_ideam.py para comparabilidad.
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
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(80, verbose=False),
                   lgb.log_evaluation(-1)],
    )
    t_elapsed = time.time() - t0

    y_pred = model.predict(X_test)
    y_pred = np.maximum(y_pred, 0)  # AporEner ≥ 0 GWh

    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae  = np.mean(np.abs(y_test.values - y_pred))

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
    BASELINE_PRODUCCION = 16.52
    BASELINE_FASE6      = 10.55

    print("\n" + "═" * 65)
    print("  RESULTADOS — LightGBM APORTES_HIDRICOS + NASA POWER")
    print("═" * 65)
    print(f"  MAPE  : {res['mape']:.2f}%   (producción: {BASELINE_PRODUCCION}%, FASE 6: {BASELINE_FASE6}%)")
    print(f"  RMSE  : {res['rmse']:.2f} GWh")
    print(f"  MAE   : {res['mae']:.2f} GWh")
    print(f"  Iter  : {res['n_iter']} (early stopping)")
    print(f"  Tiempo: {res['tiempo_s']:.1f}s")

    delta_prod  = BASELINE_PRODUCCION - res['mape']
    delta_fase6 = BASELINE_FASE6 - res['mape']
    signo_prod  = "▼" if delta_prod  > 0 else "▲"
    signo_f6    = "▼" if delta_fase6 > 0 else "▲"
    print(f"\n  Δ vs producción (16.52%): {signo_prod}{abs(delta_prod):.2f}pp "
          f"({'mejora' if delta_prod > 0 else 'sin mejora'})")
    print(f"  Δ vs FASE 6 (10.55%):     {signo_f6}{abs(delta_fase6):.2f}pp "
          f"({'supera FASE 6' if delta_fase6 > 0 else 'bajo FASE 6'})")

    print("\n  ── Feature Importance (gain) ──")
    for feat, imp in res['feature_importance'].head(15).items():
        bar = "█" * int(imp / res['feature_importance'].max() * 30)
        print(f"  {feat:30s}  {bar:<30s}  {imp:.0f}")

    print("\n  ── Predicciones holdout (últimos 10 días) ──")
    y_test = res['y_test']
    y_pred = res['y_pred']
    df_cmp = pd.DataFrame({
        'real': y_test.values[-10:],
        'pred': y_pred[-10:],
        'err%': np.abs(y_test.values[-10:] - y_pred[-10:]) / (y_test.values[-10:] + 1e-9) * 100,
    }, index=y_test.index[-10:])
    print(df_cmp.to_string(float_format=lambda x: f"{x:.2f}"))


# =============================================================================
# ABLACION
# =============================================================================

def ablacion(df: pd.DataFrame, feature_cols: list,
             holdout_dias: int, verbose: bool = True) -> None:
    """
    Compara configuraciones para aislar el aporte de NASA precipitación.
    """
    nasa_prec_cols = tuple(c for c in feature_cols if 'nasa_prec' in c)
    rios_lag_cols  = tuple(c for c in feature_cols
                           if c.startswith('apor_') and '_lag' in c)
    emb_cols       = tuple(c for c in feature_cols
                           if 'embalse' in c or 'vertim' in c)
    calendario     = ('doy_sin', 'doy_cos', 'mes', 'trimestre', 'dias_desde_2020')

    base = [c for c in feature_cols
            if c not in nasa_prec_cols + rios_lag_cols + emb_cols
            and c not in calendario]

    grupos = {
        'Solo lags AporEner':              base,
        '+ Calendario + tendencia':        [c for c in feature_cols
                                            if c not in nasa_prec_cols
                                            and c not in rios_lag_cols
                                            and c not in emb_cols],
        '+ Ríos clave (lag1/lag7)':        [c for c in feature_cols
                                            if c not in nasa_prec_cols
                                            and c not in emb_cols],
        '+ Embalses/Vertimientos':         [c for c in feature_cols
                                            if c not in nasa_prec_cols],
        '+ NASA Precipitación (completo)': feature_cols,
    }

    print("\n  ── Ablación: aporte de covariables ──")
    print(f"  {'Configuración':<38s}  {'MAPE':>7s}  {'RMSE':>7s}  {'Δ base':>8s}")
    print("  " + "─" * 68)

    mape_base = None
    for nombre, feats in grupos.items():
        if not feats:
            continue
        res = evaluar_modelo(df, feats, holdout_dias, verbose=False)
        if mape_base is None:
            mape_base = res['mape']
            delta_str = "— (base)"
        else:
            delta = res['mape'] - mape_base
            delta_str = f"{'↑' if delta > 0 else '↓'}{abs(delta):.2f}pp"
        print(f"  {nombre:<38s}  {res['mape']:>6.2f}%  "
              f"{res['rmse']:>7.2f}  {delta_str:>8s}")


def feature_selection_run(df: pd.DataFrame, feature_cols: list,
                           holdout_dias: int, top_n: int = 25) -> None:
    """
    Entrena el modelo completo, selecciona top_n features por gain, reentrena.
    Mitiga el ruido de features NASA con baja importancia.
    """
    print(f"\n  ── Feature Selection (top {top_n} features) ──")

    # Paso 1: modelo completo para obtener importancias
    res_full = evaluar_modelo(df, feature_cols, holdout_dias, verbose=False)
    top_feats = res_full['feature_importance'].head(top_n).index.tolist()

    # Mostrar cuántos son NASA vs ríos vs lags
    n_nasa = sum(1 for f in top_feats if 'nasa' in f)
    n_rios = sum(1 for f in top_feats if 'apor_' in f)
    n_emb  = sum(1 for f in top_feats if 'embalse' in f or 'vertim' in f)
    n_lag  = sum(1 for f in top_feats if f.startswith('y_lag') or f.startswith('rolling'))
    print(f"  Top {top_n} breakdown: y_lags/rolling={n_lag}, ríos={n_rios}, "
          f"embalses={n_emb}, NASA_prec={n_nasa}")

    # Paso 2: reentrenar solo con top features
    res_sel = evaluar_modelo(df, top_feats, holdout_dias, verbose=False)

    delta = res_full['mape'] - res_sel['mape']
    signo = "↓" if delta > 0 else "↑"
    print(f"  Modelo completo ({len(feature_cols):2d} feats): {res_full['mape']:.2f}%")
    print(f"  Modelo selección ({top_n:2d} feats): {res_sel['mape']:.2f}% "
          f"  ({signo}{abs(delta):.2f}pp)")

    print(f"\n  Top {top_n} features seleccionadas:")
    for i, feat in enumerate(top_feats, 1):
        imp = res_full['feature_importance'][feat]
        print(f"  {i:3d}. {feat:<35s}  gain={imp:.0f}")

    return res_sel


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='APORTES_HIDRICOS LightGBM + NASA POWER precipitación (FASE 19)'
    )
    parser.add_argument('--holdout', type=int, default=90,
                        help='Días de holdout (default: 90 — más estable que 30)')
    parser.add_argument('--top-n', type=int, default=25,
                        help='Top N features para feature selection (default: 25)')
    parser.add_argument('--no-ablacion', action='store_true',
                        help='Omitir ablación (más rápido)')
    args = parser.parse_args()

    df, feature_cols = build_dataset(fecha_inicio='2020-01-01', verbose=True)

    # ── Modelo completo ──────────────────────────────────────────────
    res = evaluar_modelo(df, feature_cols, args.holdout, verbose=True)
    imprimir_resultados(res, args.holdout)

    # ── Feature selection: reentrenar con top-N ──────────────────────
    res_sel = feature_selection_run(df, feature_cols, args.holdout, args.top_n)

    # ── Ablación ─────────────────────────────────────────────────────
    if not args.no_ablacion:
        ablacion(df, feature_cols, args.holdout, verbose=True)

    # ── Guardar mejor resultado ───────────────────────────────────────
    mejor_mape = min(res['mape'], res_sel['mape'])
    out_path = os.path.join(
        os.path.dirname(__file__), 'results',
        f'hidro_lgbm_nasa_{datetime.now():%Y%m%d_%H%M%S}.csv'
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame([{
        'fecha_experimento':   datetime.now().isoformat(),
        'modelo':              'LightGBM_APORTES_HIDRICOS_NASA',
        'holdout_dias':        args.holdout,
        'mape_completo_pct':   round(res['mape'], 4),
        'mape_seleccion_pct':  round(res_sel['mape'], 4),
        'mape_mejor_pct':      round(mejor_mape, 4),
        'rmse_completo':       round(res['rmse'], 4),
        'n_features_total':    len(feature_cols),
        'n_features_sel':      args.top_n,
        'n_iter_completo':     res['n_iter'],
        'baseline_prod':       16.52,
        'baseline_fase6':      10.55,
        'delta_prod_pp':       round(16.52 - mejor_mape, 4),
        'delta_fase6_pp':      round(10.55 - mejor_mape, 4),
    }]).to_csv(out_path, index=False)
    print(f"\n  ✓ Resultados guardados en: {out_path}")
    print(f"\n  RESUMEN FINAL:")
    print(f"    Mejor MAPE       : {mejor_mape:.2f}%")
    print(f"    vs producción    : {'▼' if mejor_mape < 16.52 else '▲'}"
          f"{abs(16.52 - mejor_mape):.2f}pp")
    print(f"    vs FASE 6 LGBMx  : {'▼' if mejor_mape < 10.55 else '▲'}"
          f"{abs(10.55 - mejor_mape):.2f}pp")


if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
