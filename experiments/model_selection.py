#!/usr/bin/env python3
"""
FASE 6 — MODEL SELECTION EXPERIMENT
====================================
Ministerio de Minas y Energía — República de Colombia

Compara 6 modelos ML para 3 métricas prioritarias del sector energético:
  1. PRECIO_BOLSA  (prioridad máxima  — ensemble actual ~40% MAPE)
  2. DEMANDA        (prioridad alta    — ensemble actual ~3.6% MAPE)
  3. APORTES_HIDRICOS (prioridad media — ensemble actual ~16% MAPE)

Modelos:
  1. Ensemble actual (Prophet + SARIMA)    — baseline producción
  2. XGBoost                                — FASE 5.B baseline
  3. LightGBM                               — alternativa rápida
  4. Random Forest                          — menos overfitting
  5. LSTM (PyTorch)                         — deep learning secuencial
  6. Hybrid (mejor tree-model + ensemble)   — combina paradigmas

Validación: Temporal holdout (30 días). NO random split.
Salidas:   CSVs + gráficos Plotly en experiments/results/

Uso:
  python experiments/model_selection.py --metrica PRECIO_BOLSA
  python experiments/model_selection.py --metrica DEMANDA
  python experiments/model_selection.py --metrica APORTES_HIDRICOS
  python experiments/model_selection.py --metrica ALL

⚠️  Experimento offline — NO modifica producción.
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

# ─── Directorios ───
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─── Parámetros globales ───
HOLDOUT_DIAS = 30
RANDOM_STATE = 42

# ─── Configuración por métrica ───
METRICAS_EXPERIMENT = {
    'PRECIO_BOLSA': {
        'metrica_bd': 'PrecBolsNaci',
        'agg': 'AVG',
        'entidad_filtro': 'Sistema',
        'prefer_sistema': False,
        'ventana_meses': 15,
        'piso': 86.0,
        'unidad': '$/kWh',
        'regresores_bd': {
            'embalses_pct': {
                'metrica_bd': 'PorcVoluUtilDiar',
                'entidad': 'Sistema',
                'agg': 'AVG',
                'escala': 100,
            },
            'demanda_gwh': {
                'metrica_bd': 'DemaReal',
                'prefer_sistema': True,
                'agg': 'SUM',
                'escala': 1,
            },
            'aportes_gwh': {
                'metrica_bd': 'AporEner',
                'agg': 'SUM',
                'escala': 1,
            },
        },
        'usar_calendario': True,
        'tipo_filtro_parciales': None,  # precios: no filtrar parciales
    },
    'DEMANDA': {
        'metrica_bd': 'DemaReal',
        'agg': 'SUM',
        'entidad_filtro': None,
        'prefer_sistema': True,
        'ventana_meses': None,   # toda la historia
        'piso': 0.0,
        'unidad': 'GWh',
        'regresores_bd': {},     # DEMANDA no usa regresores BD
        'usar_calendario': True,
        'tipo_filtro_parciales': 'energia',
    },
    'APORTES_HIDRICOS': {
        'metrica_bd': 'AporEner',
        'agg': 'SUM',
        'entidad_filtro': None,
        'prefer_sistema': False,
        'ventana_meses': None,
        'piso': 0.0,
        'unidad': 'GWh',
        'regresores_bd': {
            'embalses_pct': {
                'metrica_bd': 'PorcVoluUtilDiar',
                'entidad': 'Sistema',
                'agg': 'AVG',
                'escala': 100,
            },
        },
        'usar_calendario': True,
        'tipo_filtro_parciales': 'energia',
    },
}


# =============================================================================
# CARGA DE DATOS
# =============================================================================

def get_postgres_connection():
    """Conexión a PostgreSQL usando infraestructura del sistema."""
    import psycopg2
    from infrastructure.database.connection import PostgreSQLConnectionManager
    manager = PostgreSQLConnectionManager()
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user
    }
    if manager.password:
        conn_params['password'] = manager.password
    return psycopg2.connect(**conn_params)


def _cargar_serie_bd(metrica_bd, agg, fecha_inicio, entidad_filtro=None,
                     prefer_sistema=False):
    """Carga una serie diaria de métricas desde PostgreSQL."""
    conn = get_postgres_connection()

    if prefer_sistema and not entidad_filtro:
        query = f"""
        SELECT fecha,
          CASE WHEN MAX(CASE WHEN entidad='Sistema' THEN 1 ELSE 0 END) = 1
               THEN {agg}(CASE WHEN entidad='Sistema' THEN valor_gwh END)
               ELSE {agg}(valor_gwh)
          END as valor
        FROM metrics
        WHERE metrica = %s AND fecha >= %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica_bd, fecha_inicio)
    elif entidad_filtro:
        query = f"""
        SELECT fecha, {agg}(valor_gwh) as valor
        FROM metrics
        WHERE metrica = %s AND fecha >= %s AND entidad = %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica_bd, fecha_inicio, entidad_filtro)
    else:
        query = f"""
        SELECT fecha, {agg}(valor_gwh) as valor
        FROM metrics
        WHERE metrica = %s AND fecha >= %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica_bd, fecha_inicio)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df.sort_values('fecha').set_index('fecha')


def _construir_calendario(fechas_index):
    """Festivos colombianos + DOW dummies."""
    from scripts.train_predictions_sector_energetico import _FESTIVOS_CO
    dates = pd.to_datetime(fechas_index)
    dow = dates.dayofweek
    df_cal = pd.DataFrame(index=dates)
    df_cal['es_festivo'] = [1.0 if d.date() in _FESTIVOS_CO else 0.0 for d in dates]
    for i, nombre in enumerate(['dow_lun', 'dow_mar', 'dow_mie',
                                'dow_jue', 'dow_vie', 'dow_sab']):
        df_cal[nombre] = (dow == i).astype(float)
    return df_cal


def _filtrar_parciales(df, tipo):
    """Filtra datos parciales recientes (XM) para métricas de energía."""
    if tipo != 'energia' or len(df) <= 95:
        return df
    mediana = df['valor'].iloc[-95:-5].median()
    if mediana <= 0:
        return df
    umbral = mediana * 0.5
    ultimos = df.tail(5)
    parciales = ultimos[ultimos['valor'] < umbral]
    if len(parciales) > 0:
        fechas_excl = parciales.index.date.tolist()
        df = df.drop(parciales.index)
        print(f"  ⚠️  Excluidos {len(parciales)} datos parciales: {fechas_excl}")
    return df


def build_dataset(metrica_nombre):
    """
    Construye dataset multivariable para una métrica.

    Returns:
        df: DataFrame con 'valor' (target) + features, indexed by date
        feature_cols: list of feature column names
        config: dict de configuración de la métrica
    """
    config = METRICAS_EXPERIMENT[metrica_nombre]
    from dateutil.relativedelta import relativedelta

    ventana = config['ventana_meses']
    if ventana:
        fecha_inicio = (datetime.now() - relativedelta(months=ventana)).strftime('%Y-%m-%d')
    else:
        fecha_inicio = '2020-01-01'

    print(f"\n{'─'*60}")
    print(f"  📊 Construyendo dataset: {metrica_nombre}")
    print(f"{'─'*60}")
    print(f"  Desde: {fecha_inicio}")

    # 1. Target
    df = _cargar_serie_bd(
        config['metrica_bd'], config['agg'], fecha_inicio,
        config['entidad_filtro'], config['prefer_sistema']
    )
    df = _filtrar_parciales(df, config['tipo_filtro_parciales'])
    print(f"  Target: {len(df)} registros "
          f"({df.index.min().date()} → {df.index.max().date()})")
    print(f"  μ={df['valor'].mean():.2f}, σ={df['valor'].std():.2f} {config['unidad']}")

    # 2. Regresores BD
    for reg_nombre, reg_cfg in config['regresores_bd'].items():
        df_reg = _cargar_serie_bd(
            reg_cfg['metrica_bd'], reg_cfg['agg'], fecha_inicio,
            reg_cfg.get('entidad'), reg_cfg.get('prefer_sistema', False)
        )
        if reg_cfg.get('escala', 1) != 1:
            df_reg['valor'] = df_reg['valor'] * reg_cfg['escala']
        df[reg_nombre] = df_reg['valor']
        print(f"  Regresor BD: {reg_nombre} ({len(df_reg)} rows)")

    # 3. Lags
    df['y_lag1'] = df['valor'].shift(1)
    df['y_lag7'] = df['valor'].shift(7)

    # 4. Calendario
    if config['usar_calendario']:
        df_cal = _construir_calendario(df.index)
        df = df.join(df_cal)

    # 5. Limpiar NaN (lags + join holes)
    n_antes = len(df)
    df = df.ffill().bfill()
    df = df.dropna()
    print(f"  Eliminadas {n_antes - len(df)} filas NaN")

    feature_cols = [c for c in df.columns if c != 'valor']
    print(f"  Dataset final: {len(df)} × {len(feature_cols)+1} "
          f"(target + {len(feature_cols)} features)")
    print(f"  Features: {feature_cols}")

    return df, feature_cols, config


# =============================================================================
# CARGAR BASELINE ENSEMBLE DESDE BD
# =============================================================================

def cargar_metricas_ensemble(metrica_nombre):
    """Lee MAPE/RMSE del ensemble actual desde tabla predictions."""
    conn = get_postgres_connection()
    try:
        query = """
        SELECT mape_validacion, rmse_validacion
        FROM predictions WHERE fuente = %s LIMIT 1
        """
        df = pd.read_sql_query(query, conn, params=(metrica_nombre,))
        if len(df) > 0 and df['mape_validacion'].iloc[0] is not None:
            return {
                'mape': float(df['mape_validacion'].iloc[0]),
                'rmse': float(df['rmse_validacion'].iloc[0])
                       if df['rmse_validacion'].iloc[0] is not None else None,
            }
    except Exception:
        pass
    finally:
        conn.close()
    return {'mape': None, 'rmse': None}


# =============================================================================
# MODELOS
# =============================================================================

def _train_xgboost(X_train, y_train, X_test, y_test):
    from xgboost import XGBRegressor
    modelo = XGBRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=RANDOM_STATE, n_jobs=-1, verbosity=0,
        early_stopping_rounds=50,
    )
    modelo.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    return modelo, modelo.feature_importances_


def _train_lightgbm(X_train, y_train, X_test, y_test):
    import lightgbm as lgb
    modelo = lgb.LGBMRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        reg_alpha=0.1, reg_lambda=1.0, n_jobs=-1, verbosity=-1,
        random_state=RANDOM_STATE,
    )
    modelo.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    return modelo, modelo.feature_importances_


def _train_random_forest(X_train, y_train, X_test, y_test):
    from sklearn.ensemble import RandomForestRegressor
    modelo = RandomForestRegressor(
        n_estimators=300, max_depth=12, min_samples_leaf=5,
        random_state=RANDOM_STATE, n_jobs=-1,
    )
    modelo.fit(X_train, y_train)
    return modelo, modelo.feature_importances_


def _train_lstm(X_train, y_train, X_test, y_test, seq_len=14):
    """LSTM secuencial con PyTorch."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    # ── Normalización (Z-score, ajustada solo en train) ──
    mean_X = X_train.mean(axis=0)
    std_X = X_train.std(axis=0) + 1e-8
    mean_y = y_train.mean()
    std_y = y_train.std() + 1e-8

    X_tr_norm = (X_train.values - mean_X.values) / std_X.values
    X_te_norm = (X_test.values - mean_X.values) / std_X.values
    y_tr_norm = (y_train.values - mean_y) / std_y

    # ── Crear secuencias ──
    def make_sequences(X, y, seq_len):
        Xs, ys = [], []
        for i in range(len(X) - seq_len):
            Xs.append(X[i:i+seq_len])
            ys.append(y[i+seq_len] if y is not None else 0)
        return np.array(Xs), np.array(ys)

    X_seq_tr, y_seq_tr = make_sequences(X_tr_norm, y_tr_norm, seq_len)
    # Para test: usar últimas seq_len filas de train + test
    X_full_test = np.vstack([X_tr_norm[-seq_len:], X_te_norm])
    X_seq_te, _ = make_sequences(X_full_test, None, seq_len)

    if len(X_seq_tr) < 30 or len(X_seq_te) == 0:
        print("    ⚠️  Datos insuficientes para LSTM, skip")
        return None, None

    n_features = X_seq_tr.shape[2]

    # ── Modelo ──
    class LSTMModel(nn.Module):
        def __init__(self, input_size, hidden_size=64, num_layers=2):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                                batch_first=True, dropout=0.2)
            self.fc = nn.Linear(hidden_size, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :]).squeeze(-1)

    device = torch.device('cpu')
    model = LSTMModel(n_features).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    # DataLoader
    ds_train = TensorDataset(
        torch.tensor(X_seq_tr, dtype=torch.float32),
        torch.tensor(y_seq_tr, dtype=torch.float32)
    )
    loader = DataLoader(ds_train, batch_size=32, shuffle=True)

    # ── Entrenamiento ──
    model.train()
    best_loss = float('inf')
    patience, patience_counter = 20, 0
    for epoch in range(200):
        epoch_loss = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        avg_loss = epoch_loss / len(loader)
        if avg_loss < best_loss - 1e-4:
            best_loss = avg_loss
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    # ── Predicción ──
    model.eval()
    with torch.no_grad():
        X_te_tensor = torch.tensor(X_seq_te, dtype=torch.float32).to(device)
        y_pred_norm = model(X_te_tensor).cpu().numpy()

    # Des-normalizar
    y_pred = y_pred_norm * std_y + mean_y

    # Ajustar longitud al test set real
    # X_seq_te puede tener len(X_test) secuencias (necesitamos exactamente len(y_test))
    y_pred = y_pred[:len(y_test)]

    # LSTM no tiene feature importance nativa → None
    return y_pred, None


def train_evaluate(modelo_nombre, X_train, y_train, X_test, y_test, piso=0.0):
    """
    Entrena un modelo y calcula MAPE, RMSE, MAE.
    Returns: dict con métricas + y_pred + importances (o None).
    """
    t0 = time.time()

    importances = None

    if modelo_nombre == 'XGBoost':
        model, importances = _train_xgboost(X_train, y_train, X_test, y_test)
        y_pred = model.predict(X_test)

    elif modelo_nombre == 'LightGBM':
        model, importances = _train_lightgbm(X_train, y_train, X_test, y_test)
        y_pred = model.predict(X_test)

    elif modelo_nombre == 'RandomForest':
        model, importances = _train_random_forest(X_train, y_train, X_test, y_test)
        y_pred = model.predict(X_test)

    elif modelo_nombre == 'LSTM':
        y_pred, importances = _train_lstm(X_train, y_train, X_test, y_test)
        if y_pred is None:
            return None

    elif modelo_nombre == 'Ensemble_BD':
        # Baseline: leer métricas del ensemble actual desde BD
        # No se re-entrena — solo se reportan sus métricas almacenadas
        return None  # Handled separately in main loop

    elif modelo_nombre == 'Hybrid':
        # Hybrid: promedio del mejor tree-model y ensemble actual
        return None  # Handled separately in main loop

    else:
        raise ValueError(f"Modelo desconocido: {modelo_nombre}")

    # Aplicar piso
    y_pred = np.maximum(y_pred, piso)

    elapsed = time.time() - t0

    mape = mean_absolute_percentage_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = float(np.mean(np.abs(y_test.values - y_pred)))

    return {
        'mape': mape,
        'rmse': rmse,
        'mae': mae,
        'y_pred': y_pred,
        'importances': importances,
        'tiempo_s': elapsed,
    }


# =============================================================================
# ENSEMBLE PROPHET+SARIMA (re-entrenado con holdout idéntico)
# =============================================================================

def _train_ensemble_prophet_sarima(df, feature_cols, config, holdout_dias=30):
    """
    Re-entrena Prophet+SARIMA con el MISMO holdout que los tree-models
    para una comparación justa (mismos 30 días de test).
    """
    from prophet import Prophet
    from pmdarima import auto_arima
    import logging
    logging.getLogger('prophet').setLevel(logging.ERROR)
    logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

    df_train = df.iloc[:-holdout_dias]
    df_test = df.iloc[-holdout_dias:]
    y_test = df_test['valor']

    # ── Prophet ──
    df_p = pd.DataFrame({'ds': df_train.index, 'y': df_train['valor'].values})
    modelo_p = Prophet(
        growth='flat' if config.get('piso', 0) > 0 else 'linear',
        yearly_seasonality=len(df_train) >= 365,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.95,
        changepoint_prior_scale=0.05,
        seasonality_mode='multiplicative'
          if config['metrica_bd'] == 'PrecBolsNaci' else 'additive',
        mcmc_samples=0,
    )
    modelo_p.fit(df_p)

    future_p = pd.DataFrame({'ds': df_test.index})
    pred_p = modelo_p.predict(future_p)
    y_prophet = pred_p['yhat'].values

    # ── SARIMA ──
    serie_train = df_train['valor']
    try:
        modelo_s = auto_arima(
            serie_train.dropna(), seasonal=True, m=7,
            max_order=5, suppress_warnings=True,
            error_action='ignore', stepwise=True, n_jobs=-1,
        )
        y_sarima = modelo_s.predict(n_periods=holdout_dias)
    except Exception:
        y_sarima = y_prophet.copy()  # fallback

    # ── Pesos basados en MAPE individual ──
    mape_p = mean_absolute_percentage_error(y_test, np.maximum(y_prophet, config.get('piso', 0)))
    mape_s = mean_absolute_percentage_error(y_test, np.maximum(y_sarima, config.get('piso', 0)))

    if mape_p + mape_s > 0:
        w_p = (1 / mape_p) / (1 / mape_p + 1 / mape_s) if mape_p > 0 else 0.5
        w_s = 1 - w_p
    else:
        w_p, w_s = 0.6, 0.4

    y_ensemble = w_p * y_prophet + w_s * y_sarima
    piso = config.get('piso', 0)
    y_ensemble = np.maximum(y_ensemble, piso)

    mape = mean_absolute_percentage_error(y_test, y_ensemble)
    rmse = np.sqrt(mean_squared_error(y_test, y_ensemble))
    mae = float(np.mean(np.abs(y_test.values - y_ensemble)))

    return {
        'mape': mape,
        'rmse': rmse,
        'mae': mae,
        'y_pred': y_ensemble,
        'importances': None,
        'tiempo_s': 0,
        'pesos_ensemble': {'prophet': round(w_p, 3), 'sarima': round(w_s, 3)},
    }


# =============================================================================
# GRÁFICOS
# =============================================================================

def generar_graficos(metrica_nombre, resultados, y_test, config):
    """Genera gráficos Plotly: barras MAPE + líneas predicción."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    modelos = list(resultados.keys())
    mapes = [resultados[m]['mape'] * 100 for m in modelos]
    rmses = [resultados[m]['rmse'] for m in modelos]

    # ── 1. Barras MAPE + RMSE ──
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[f'MAPE (%) — {metrica_nombre}',
                        f'RMSE ({config["unidad"]}) — {metrica_nombre}']
    )
    colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3']
    for i, (m, mape_val, rmse_val) in enumerate(zip(modelos, mapes, rmses)):
        fig.add_trace(go.Bar(
            name=m, x=[m], y=[mape_val],
            marker_color=colors[i % len(colors)],
            text=[f'{mape_val:.2f}%'], textposition='outside',
            showlegend=False
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            name=m, x=[m], y=[rmse_val],
            marker_color=colors[i % len(colors)],
            text=[f'{rmse_val:.1f}'], textposition='outside',
            showlegend=False
        ), row=1, col=2)

    fig.update_layout(
        title=f'FASE 6 — Model Selection: {metrica_nombre}',
        height=450, width=900,
        template='plotly_white',
    )
    path_bar = os.path.join(RESULTS_DIR, f'{metrica_nombre}_comparacion_barras.html')
    fig.write_html(path_bar)
    print(f"  📊 Gráfico barras: {path_bar}")

    # ── 2. Líneas predicción vs real ──
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=y_test.index, y=y_test.values,
        mode='lines+markers', name='Real',
        line=dict(color='black', width=2),
    ))
    for i, m in enumerate(modelos):
        y_pred = resultados[m]['y_pred']
        fig2.add_trace(go.Scatter(
            x=y_test.index, y=y_pred,
            mode='lines', name=m,
            line=dict(color=colors[i % len(colors)], dash='dash'),
        ))
    fig2.update_layout(
        title=f'Holdout {HOLDOUT_DIAS} días — {metrica_nombre} ({config["unidad"]})',
        xaxis_title='Fecha',
        yaxis_title=config['unidad'],
        height=450, width=1000,
        template='plotly_white',
    )
    path_line = os.path.join(RESULTS_DIR, f'{metrica_nombre}_holdout_lineas.html')
    fig2.write_html(path_line)
    print(f"  📈 Gráfico líneas: {path_line}")


# =============================================================================
# GUARDAR RESULTADOS
# =============================================================================

def guardar_resultados(metrica_nombre, resultados, y_test, feature_cols, config):
    """Guarda CSVs de resultados."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. Tabla comparativa
    rows = []
    for m, res in resultados.items():
        rows.append({
            'modelo': m,
            'mape_pct': round(res['mape'] * 100, 2),
            'rmse': round(res['rmse'], 2),
            'mae': round(res['mae'], 2),
            'tiempo_s': round(res.get('tiempo_s', 0), 1),
        })
    df_comp = pd.DataFrame(rows).sort_values('mape_pct')
    df_comp['ranking'] = range(1, len(df_comp) + 1)
    df_comp['ganador'] = ''
    df_comp.iloc[0, df_comp.columns.get_loc('ganador')] = '🏆'

    path_comp = os.path.join(RESULTS_DIR, f'{metrica_nombre}_comparacion.csv')
    df_comp.to_csv(path_comp, index=False)
    print(f"\n  💾 Comparación: {path_comp}")

    # 2. Predicciones holdout por modelo
    df_pred = pd.DataFrame({'fecha': y_test.index, 'real': y_test.values})
    for m, res in resultados.items():
        df_pred[f'pred_{m}'] = res['y_pred']
    path_pred = os.path.join(RESULTS_DIR, f'{metrica_nombre}_predicciones_holdout.csv')
    df_pred.to_csv(path_pred, index=False)
    print(f"  💾 Predicciones: {path_pred}")

    # 3. Feature importance (solo modelos árbol)
    rows_imp = []
    for m, res in resultados.items():
        if res.get('importances') is not None:
            for feat, imp in zip(feature_cols, res['importances']):
                rows_imp.append({'modelo': m, 'feature': feat, 'importance': imp})
    if rows_imp:
        df_imp = pd.DataFrame(rows_imp)
        path_imp = os.path.join(RESULTS_DIR, f'{metrica_nombre}_feature_importance.csv')
        df_imp.to_csv(path_imp, index=False)
        print(f"  💾 Feature imp.: {path_imp}")

    return df_comp


# =============================================================================
# IMPRIMIR RESULTADOS POR CONSOLA
# =============================================================================

def imprimir_tabla(metrica_nombre, df_comp, config):
    """Imprime tabla de resultados formateada."""
    print(f"\n{'='*75}")
    print(f"  RESULTADOS — {metrica_nombre} ({config['unidad']})")
    print(f"  Holdout: {HOLDOUT_DIAS} días")
    print(f"{'='*75}")
    print(f"  {'#':<3} {'Modelo':<25} {'MAPE':>8} {'RMSE':>10} {'MAE':>10} {'T(s)':>6}")
    print(f"  {'─'*65}")
    for _, row in df_comp.iterrows():
        rank = int(row['ranking'])
        ganador = ' 🏆' if row['ganador'] == '🏆' else ''
        print(f"  {rank:<3} {row['modelo']:<25} {row['mape_pct']:>7.2f}% "
              f"{row['rmse']:>10.2f} {row['mae']:>10.2f} {row['tiempo_s']:>5.1f}s{ganador}")


def imprimir_feature_importance(resultados, feature_cols, top_n=5):
    """Imprime top-N features para cada modelo árbol."""
    for m, res in resultados.items():
        if res.get('importances') is not None:
            print(f"\n  🏆 Feature Importance — {m} (top {top_n}):")
            imp_sorted = sorted(zip(feature_cols, res['importances']),
                                key=lambda x: x[1], reverse=True)
            total = sum(v for _, v in imp_sorted)
            for feat, imp in imp_sorted[:top_n]:
                pct = imp / total * 100 if total > 0 else 0
                bar = '█' * int(pct / 2)
                print(f"    {feat:<20} {pct:5.1f}% {bar}")


# =============================================================================
# EJECUTAR EXPERIMENTO PARA UNA MÉTRICA
# =============================================================================

def run_experiment(metrica_nombre):
    """Ejecuta el experimento completo de model selection para una métrica."""
    print(f"\n{'#'*75}")
    print(f"# FASE 6 — MODEL SELECTION: {metrica_nombre}")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*75}")

    t_total = time.time()

    # 1. Build dataset
    df, feature_cols, config = build_dataset(metrica_nombre)
    piso = config.get('piso', 0)

    # 2. Temporal split
    df_train = df.iloc[:-HOLDOUT_DIAS]
    df_test = df.iloc[-HOLDOUT_DIAS:]
    X_train = df_train[feature_cols]
    y_train = df_train['valor']
    X_test = df_test[feature_cols]
    y_test = df_test['valor']

    print(f"\n  📐 Split: Train={len(df_train)} | Test={len(df_test)} "
          f"({df_test.index.min().date()} → {df_test.index.max().date()})")

    resultados = {}

    # ── Modelo 1: Ensemble Prophet+SARIMA (re-entrenado con MISMO holdout) ──
    print(f"\n  [1/6] Ensemble Prophet+SARIMA...")
    try:
        res_ens = _train_ensemble_prophet_sarima(df, feature_cols, config, HOLDOUT_DIAS)
        resultados['Ensemble_P+S'] = res_ens
        print(f"    MAPE={res_ens['mape']*100:.2f}%, RMSE={res_ens['rmse']:.2f}")
        pesos = res_ens.get('pesos_ensemble', {})
        if pesos:
            print(f"    Pesos: Prophet={pesos.get('prophet','-')}, "
                  f"SARIMA={pesos.get('sarima','-')}")
    except Exception as e:
        print(f"    ❌ Ensemble falló: {e}")

    # ── Modelo 2: XGBoost ──
    print(f"\n  [2/6] XGBoost...")
    try:
        res = train_evaluate('XGBoost', X_train, y_train, X_test, y_test, piso)
        if res:
            resultados['XGBoost'] = res
            print(f"    MAPE={res['mape']*100:.2f}%, RMSE={res['rmse']:.2f} ({res['tiempo_s']:.1f}s)")
    except Exception as e:
        print(f"    ❌ XGBoost falló: {e}")

    # ── Modelo 3: LightGBM ──
    print(f"\n  [3/6] LightGBM...")
    try:
        res = train_evaluate('LightGBM', X_train, y_train, X_test, y_test, piso)
        if res:
            resultados['LightGBM'] = res
            print(f"    MAPE={res['mape']*100:.2f}%, RMSE={res['rmse']:.2f} ({res['tiempo_s']:.1f}s)")
    except Exception as e:
        print(f"    ❌ LightGBM falló: {e}")

    # ── Modelo 4: Random Forest ──
    print(f"\n  [4/6] Random Forest...")
    try:
        res = train_evaluate('RandomForest', X_train, y_train, X_test, y_test, piso)
        if res:
            resultados['RandomForest'] = res
            print(f"    MAPE={res['mape']*100:.2f}%, RMSE={res['rmse']:.2f} ({res['tiempo_s']:.1f}s)")
    except Exception as e:
        print(f"    ❌ Random Forest falló: {e}")

    # ── Modelo 5: LSTM ──
    print(f"\n  [5/6] LSTM (PyTorch)...")
    try:
        res = train_evaluate('LSTM', X_train, y_train, X_test, y_test, piso)
        if res:
            resultados['LSTM'] = res
            print(f"    MAPE={res['mape']*100:.2f}%, RMSE={res['rmse']:.2f} ({res['tiempo_s']:.1f}s)")
    except Exception as e:
        print(f"    ❌ LSTM falló: {e}")

    # ── Modelo 6: Hybrid (mejor tree + ensemble) ──
    print(f"\n  [6/6] Hybrid (mejor tree + ensemble)...")
    try:
        # Encontrar mejor tree-model
        tree_models = {k: v for k, v in resultados.items()
                       if k in ('XGBoost', 'LightGBM', 'RandomForest')}
        if tree_models and 'Ensemble_P+S' in resultados:
            best_tree_name = min(tree_models, key=lambda k: tree_models[k]['mape'])
            best_tree = tree_models[best_tree_name]
            ens = resultados['Ensemble_P+S']

            # Peso inversamente proporcional al MAPE
            mape_t = best_tree['mape']
            mape_e = ens['mape']
            if mape_t + mape_e > 0:
                w_t = (1/mape_t) / (1/mape_t + 1/mape_e)
            else:
                w_t = 0.5
            w_e = 1 - w_t

            y_hybrid = w_t * best_tree['y_pred'] + w_e * ens['y_pred']
            y_hybrid = np.maximum(y_hybrid, piso)

            mape_h = mean_absolute_percentage_error(y_test, y_hybrid)
            rmse_h = np.sqrt(mean_squared_error(y_test, y_hybrid))
            mae_h = float(np.mean(np.abs(y_test.values - y_hybrid)))

            resultados['Hybrid'] = {
                'mape': mape_h, 'rmse': rmse_h, 'mae': mae_h,
                'y_pred': y_hybrid, 'importances': None, 'tiempo_s': 0,
                'detalle': f'{best_tree_name}({w_t:.2f}) + Ensemble({w_e:.2f})',
            }
            print(f"    {best_tree_name}({w_t:.2f}) + Ensemble({w_e:.2f})")
            print(f"    MAPE={mape_h*100:.2f}%, RMSE={rmse_h:.2f}")
        else:
            print(f"    ⚠️  No hay tree-model + ensemble para combinar")
    except Exception as e:
        print(f"    ❌ Hybrid falló: {e}")

    if not resultados:
        print("\n  ❌ Ningún modelo completó exitosamente.")
        return

    # ── Guardar y visualizar ──
    df_comp = guardar_resultados(metrica_nombre, resultados, y_test,
                                 feature_cols, config)
    imprimir_tabla(metrica_nombre, df_comp, config)
    imprimir_feature_importance(resultados, feature_cols)

    # Gráficos Plotly
    try:
        generar_graficos(metrica_nombre, resultados, y_test, config)
    except Exception as e:
        print(f"  ⚠️  Gráficos fallaron: {e}")

    elapsed = time.time() - t_total
    print(f"\n  ⏱  Tiempo total: {elapsed:.0f}s")
    print(f"\n{'='*75}")
    ganador = df_comp.iloc[0]['modelo']
    mape_ganador = df_comp.iloc[0]['mape_pct']
    print(f"  🏆 GANADOR {metrica_nombre}: {ganador} (MAPE {mape_ganador:.2f}%)")
    print(f"{'='*75}\n")

    return resultados, df_comp


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='FASE 6 — Model Selection Experiment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python experiments/model_selection.py --metrica PRECIO_BOLSA
  python experiments/model_selection.py --metrica DEMANDA
  python experiments/model_selection.py --metrica APORTES_HIDRICOS
  python experiments/model_selection.py --metrica ALL
        """
    )
    parser.add_argument(
        '--metrica', type=str, required=True,
        choices=['PRECIO_BOLSA', 'DEMANDA', 'APORTES_HIDRICOS', 'ALL'],
        help='Métrica a evaluar (o ALL para ejecutar las 3)',
    )
    args = parser.parse_args()

    print(f"\n{'#'*75}")
    print(f"# FASE 6 — MODEL SELECTION EXPERIMENT")
    print(f"# Ministerio de Minas y Energía — República de Colombia")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"# ⚠️  Experimento offline — NO modifica producción")
    print(f"{'#'*75}")

    if args.metrica == 'ALL':
        metricas = ['PRECIO_BOLSA', 'DEMANDA', 'APORTES_HIDRICOS']
    else:
        metricas = [args.metrica]

    all_results = {}
    for met in metricas:
        result = run_experiment(met)
        if result:
            all_results[met] = result

    # ── Resumen global si ALL ──
    if len(all_results) > 1:
        print(f"\n{'#'*75}")
        print(f"# RESUMEN GLOBAL — FASE 6 MODEL SELECTION")
        print(f"{'#'*75}")
        for met, (_, df_comp) in all_results.items():
            ganador = df_comp.iloc[0]
            print(f"  {met:<25} 🏆 {ganador['modelo']:<20} "
                  f"MAPE={ganador['mape_pct']:.2f}%")
        print(f"{'#'*75}\n")


if __name__ == '__main__':
    main()
