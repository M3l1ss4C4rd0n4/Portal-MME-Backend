#!/usr/bin/env python3
"""
FASE 7 — SOTA TIME SERIES MODELS EXPERIMENT
=============================================
Ministerio de Minas y Energía — República de Colombia

Compara 5 modelos Estado-del-Arte (SOTA) de series temporales contra los
ganadores de FASE 6 (RandomForest, LightGBM) para determinar si las
arquitecturas neuronales modernas superan los tree-models con feature
engineering manual.

SOTA Models:
  1. PatchTST       — Transformer con patches (Nie et al., 2023)
  2. N-BEATS        — Neural Basis Expansion (Oreshkin et al., 2020)
  3. TCN            — Temporal Convolutional Network (Bai et al., 2018)
  4. N-HiTS         — Neural Hierarchical Interpolation (Challu et al., 2023)
  5. Chronos        — Foundation Model zero-shot (Ansari et al., 2024)

  Nota: NeuralProphet (Prophet 2.0) es incompatible con pytorch-lightning 2.x
  requerido por neuralforecast. Se sustituyó por N-HiTS (sucesor de N-BEATS).

Baselines FASE 6:
  - RandomForest    (ganador PRECIO_BOLSA: 16.03% MAPE)
  - LightGBM        (ganador DEMANDA: 1.30% MAPE)

NOTA METODOLÓGICA:
  Los modelos SOTA realizan forecasting multi-paso genuino (recursivo o
  directo), mientras que los tree-models de FASE 6 usan features de lag
  (y_lag1, y_lag7) calculados con valores reales del holdout. Esto otorga
  una ventaja implícita a los tree-models. Si un modelo SOTA iguala o
  supera a los tree-models, es un resultado significativamente más fuerte.

Validación: Temporal holdout (30 días). Mismo periodo que FASE 6.
Salidas:   CSVs + gráficos Plotly en experiments/results/

Uso:
  python experiments/sota_models.py --metrica PRECIO_BOLSA
  python experiments/sota_models.py --metrica DEMANDA
  python experiments/sota_models.py --metrica ALL

Flags opcionales:
  --skip PatchTST Chronos    Omitir modelos específicos
  --chronos-model tiny       Usar chronos-t5-tiny (más rápido, ~8M params)

⚠️  Experimento offline — NO modifica producción.
"""

import sys
import os
import argparse
import time
import warnings
import logging

warnings.filterwarnings('ignore')

# Suppress verbose logging from PyTorch Lightning / neuralforecast
for logger_name in ['pytorch_lightning', 'lightning.pytorch', 'lightning',
                    'lightning.fabric', 'torch', 'neuralforecast',
                    'neuralprophet', 'cmdstanpy', 'prophet']:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import pandas as pd
import numpy as np
import torch
from datetime import datetime
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error

# Reuse FASE 6 infrastructure
from model_selection import (
    build_dataset,
    HOLDOUT_DIAS,
    RANDOM_STATE,
    RESULTS_DIR,
    train_evaluate,
)

# ─── Constantes ───
CALENDAR_COLS = ['es_festivo', 'dow_lun', 'dow_mar', 'dow_mie',
                 'dow_jue', 'dow_vie', 'dow_sab']
SOTA_METRICAS = ['PRECIO_BOLSA', 'DEMANDA']


# =============================================================================
# HELPERS
# =============================================================================

def _calc_metrics(y_true, y_pred, piso=0.0):
    """Calcula MAPE, RMSE, MAE con piso aplicado."""
    y_pred_f = np.maximum(np.asarray(y_pred, dtype=np.float64), piso)
    y_true_f = np.asarray(y_true, dtype=np.float64)
    n = min(len(y_true_f), len(y_pred_f))
    y_true_f, y_pred_f = y_true_f[:n], y_pred_f[:n]
    return {
        'mape': mean_absolute_percentage_error(y_true_f, y_pred_f),
        'rmse': np.sqrt(mean_squared_error(y_true_f, y_pred_f)),
        'mae': float(np.mean(np.abs(y_true_f - y_pred_f))),
    }


# =============================================================================
# DATA PREPARATION
# =============================================================================

def _prepare_nf_data(df, holdout_dias, exog_cols=None):
    """
    Convierte a formato largo de neuralforecast.

    Returns
    -------
    train_df : DataFrame  (unique_id, ds, y [, exog…])
    test_exog_df : DataFrame | None  (unique_id, ds [, exog…])
    valid_exog : list[str]
    """
    data = {
        'unique_id': 'metric',
        'ds': pd.to_datetime(df.index),
        'y': df['valor'].values.astype(np.float32),
    }
    valid_exog = []
    if exog_cols:
        valid_exog = [c for c in exog_cols if c in df.columns]
        for c in valid_exog:
            data[c] = df[c].values.astype(np.float32)

    df_nf = pd.DataFrame(data)
    train_df = df_nf.iloc[:-holdout_dias].reset_index(drop=True)

    test_exog_df = None
    if valid_exog:
        test_exog_df = (
            df_nf.iloc[-holdout_dias:][['unique_id', 'ds'] + valid_exog]
            .reset_index(drop=True)
        )

    return train_df, test_exog_df, valid_exog


# =============================================================================
# SOTA MODEL TRAINERS
# =============================================================================

def _train_patchtst(df, holdout_dias, config, **kw):
    """PatchTST — Transformer con channel-independent patches (univariado).

    Nota: neuralforecast 3.x PatchTST NO soporta futr_exog_list.
    Se usa en modo univariado puro — el modelo aprende patrones
    temporales sin features externas.
    """
    from neuralforecast import NeuralForecast
    from neuralforecast.models import PatchTST

    # Univariado: sin exog (PatchTST 3.x no soporta futr_exog)
    train_df, _, _ = _prepare_nf_data(df, holdout_dias)

    n_train = len(train_df)
    input_size = min(90, max(holdout_dias * 2, n_train // 4))
    val_size = min(30, n_train // 5)

    model = PatchTST(
        h=holdout_dias,
        input_size=input_size,
        max_steps=1000,
        learning_rate=1e-3,
        scaler_type='standard',
        val_check_steps=50,
        early_stop_patience_steps=10,
        random_seed=RANDOM_STATE,
        accelerator='cpu',
    )
    nf = NeuralForecast(models=[model], freq='D')
    nf.fit(df=train_df, val_size=val_size)

    pred = nf.predict()
    return pred['PatchTST'].values


def _train_nbeats(df, holdout_dias, config, **kw):
    """N-BEATS — Neural Basis Expansion Analysis (univariado por diseño)."""
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATS

    train_df, _, _ = _prepare_nf_data(df, holdout_dias)

    n_train = len(train_df)
    input_size = min(90, max(holdout_dias * 2, n_train // 4))
    val_size = min(30, n_train // 5)

    model = NBEATS(
        h=holdout_dias,
        input_size=input_size,
        max_steps=1000,
        learning_rate=1e-3,
        scaler_type='standard',
        val_check_steps=50,
        early_stop_patience_steps=10,
        random_seed=RANDOM_STATE,
        accelerator='cpu',
    )

    nf = NeuralForecast(models=[model], freq='D')
    nf.fit(df=train_df, val_size=val_size)

    pred = nf.predict()
    return pred['NBEATS'].values


def _train_tcn(df, holdout_dias, config, **kw):
    """TCN — Temporal Convolutional Network con dilataciones exponenciales."""
    from neuralforecast import NeuralForecast
    from neuralforecast.models import TCN

    exog_cols = [c for c in CALENDAR_COLS if c in df.columns]
    train_df, test_exog_df, exog_cols = _prepare_nf_data(
        df, holdout_dias, exog_cols
    )

    n_train = len(train_df)
    input_size = min(90, max(holdout_dias * 2, n_train // 4))
    val_size = min(30, n_train // 5)

    model_kwargs = dict(
        h=holdout_dias,
        input_size=input_size,
        kernel_size=3,
        dilations=[1, 2, 4, 8, 16],
        max_steps=1000,
        learning_rate=1e-3,
        scaler_type='standard',
        val_check_steps=50,
        early_stop_patience_steps=10,
        random_seed=RANDOM_STATE,
        accelerator='cpu',
    )
    if exog_cols:
        model_kwargs['futr_exog_list'] = exog_cols

    model = TCN(**model_kwargs)
    nf = NeuralForecast(models=[model], freq='D')
    nf.fit(df=train_df, val_size=val_size)

    predict_kwargs = {}
    if test_exog_df is not None:
        predict_kwargs['futr_df'] = test_exog_df

    pred = nf.predict(**predict_kwargs)
    return pred['TCN'].values


def _train_neuralprophet(df, holdout_dias, config, **kw):
    """NeuralProphet — Prophet 2.0 con AR-Net autoregresivo.

    ⚠️  neuralprophet 0.8.0 es incompatible con pytorch-lightning 2.x
    (requerido por neuralforecast). Múltiples APIs internas rotas:
    - ProgressBar.main_progress_bar → train_progress_bar
    - FitLoop.running_loss eliminado en PL 2.x
    Se usa N-HiTS como sustituto (neuralforecast, arquitectura superior).
    """
    print("    ⚠️  Incompatible con PL 2.x → usando N-HiTS como sustituto")
    return _train_nhits(df, holdout_dias, config)


def _train_nhits(df, holdout_dias, config, **kw):
    """N-HiTS — Neural Hierarchical Interpolation (sustituto de NeuralProphet).

    N-HiTS (Challu et al., 2023) es el sucesor de N-BEATS con
    interpolación jerárquica multi-resolución. Usa pools temporales
    de distintos tamaños para capturar patrones a múltiples escalas.
    """
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NHITS

    train_df, _, _ = _prepare_nf_data(df, holdout_dias)

    n_train = len(train_df)
    input_size = min(90, max(holdout_dias * 2, n_train // 4))
    val_size = min(30, n_train // 5)

    model = NHITS(
        h=holdout_dias,
        input_size=input_size,
        max_steps=1000,
        learning_rate=1e-3,
        scaler_type='standard',
        val_check_steps=50,
        early_stop_patience_steps=10,
        random_seed=RANDOM_STATE,
        accelerator='cpu',
    )

    nf = NeuralForecast(models=[model], freq='D')
    nf.fit(df=train_df, val_size=val_size)

    pred = nf.predict()
    return pred['NHITS'].values


def _train_chronos(df, holdout_dias, config, chronos_model='small', **kw):
    """Chronos — Amazon Foundation Model (zero-shot, sin entrenamiento)."""
    from chronos import ChronosPipeline

    model_name = f"amazon/chronos-t5-{chronos_model}"
    print(f"    Cargando {model_name}...")

    pipeline = ChronosPipeline.from_pretrained(
        model_name,
        device_map="cpu",
        dtype=torch.float32,
    )

    # Univariado: solo la serie objetivo
    train_values = df['valor'].values[:-holdout_dias].astype(np.float32)
    context = torch.tensor(train_values).unsqueeze(0)  # (1, T)

    forecast = pipeline.predict(
        context,
        prediction_length=holdout_dias,
        num_samples=20,
    )

    # forecast: (1, num_samples, prediction_length) → mediana
    y_pred = np.median(forecast[0].numpy(), axis=0)

    return y_pred


# =============================================================================
# FASE 6 BASELINES (re-ejecutados para comparación justa)
# =============================================================================

def _run_fase6_baselines(df, feature_cols, config, holdout_dias):
    """Re-ejecuta RandomForest y LightGBM de FASE 6 con mismo holdout."""
    df_train = df.iloc[:-holdout_dias]
    df_test = df.iloc[-holdout_dias:]
    X_train = df_train[feature_cols]
    y_train = df_train['valor']
    X_test = df_test[feature_cols]
    y_test = df_test['valor']
    piso = config.get('piso', 0)

    baselines = {}

    for modelo in ['RandomForest', 'LightGBM']:
        print(f"    {modelo}...", end=' ')
        try:
            res = train_evaluate(modelo, X_train, y_train, X_test, y_test, piso)
            if res:
                baselines[f'{modelo}_F6'] = {
                    'mape': res['mape'],
                    'rmse': res['rmse'],
                    'mae': res['mae'],
                    'y_pred': res['y_pred'],
                    'tiempo_s': res['tiempo_s'],
                }
                print(f"MAPE={res['mape']*100:.2f}% ({res['tiempo_s']:.1f}s)")
        except Exception as e:
            print(f"❌ {e}")

    return baselines


# =============================================================================
# VISUALIZACIÓN
# =============================================================================

def generar_graficos_sota(metrica_nombre, resultados, y_test, config):
    """Genera gráficos Plotly: barras MAPE + líneas predicción."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    modelos = list(resultados.keys())
    mapes = [resultados[m]['mape'] * 100 for m in modelos]
    rmses = [resultados[m]['rmse'] for m in modelos]

    # Paleta: SOTA→azules/verdes, baselines→naranja/rojo
    PALETTE = {
        'PatchTST': '#636EFA', 'N-BEATS': '#00CC96', 'TCN': '#AB63FA',
        'NeuralProphet': '#19D3F3', 'Chronos': '#FF6692',
        'RandomForest_F6': '#EF553B', 'LightGBM_F6': '#FFA15A',
    }
    colors = [PALETTE.get(m, '#636EFA') for m in modelos]

    # ── 1. Barras MAPE + RMSE ──
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[f'MAPE (%) — {metrica_nombre}',
                        f'RMSE ({config["unidad"]}) — {metrica_nombre}'],
    )
    for i, (m, mape_val, rmse_val) in enumerate(zip(modelos, mapes, rmses)):
        fig.add_trace(go.Bar(
            name=m, x=[m], y=[mape_val],
            marker_color=colors[i],
            text=[f'{mape_val:.2f}%'], textposition='outside',
            showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            name=m, x=[m], y=[rmse_val],
            marker_color=colors[i],
            text=[f'{rmse_val:.1f}'], textposition='outside',
            showlegend=False,
        ), row=1, col=2)

    fig.update_layout(
        title=f'FASE 7 — SOTA vs FASE 6: {metrica_nombre}',
        height=500, width=1050,
        template='plotly_white',
    )
    path_bar = os.path.join(RESULTS_DIR,
                            f'{metrica_nombre}_sota_comparacion.html')
    fig.write_html(path_bar)
    print(f"  📊 Barras: {path_bar}")

    # ── 2. Líneas predicción vs real ──
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=y_test.index, y=y_test.values,
        mode='lines+markers', name='Real',
        line=dict(color='black', width=2.5),
    ))
    for i, m in enumerate(modelos):
        y_pred = resultados[m]['y_pred']
        n = min(len(y_test), len(y_pred))
        fig2.add_trace(go.Scatter(
            x=y_test.index[:n], y=y_pred[:n],
            mode='lines', name=m,
            line=dict(color=colors[i], width=1.5,
                      dash='dash' if '_F6' in m else 'solid'),
        ))

    fig2.update_layout(
        title=f'SOTA Holdout {HOLDOUT_DIAS}d — {metrica_nombre} '
              f'({config["unidad"]})',
        xaxis_title='Fecha', yaxis_title=config['unidad'],
        height=500, width=1100,
        template='plotly_white',
    )
    path_line = os.path.join(RESULTS_DIR,
                             f'{metrica_nombre}_sota_holdout.html')
    fig2.write_html(path_line)
    print(f"  📈 Líneas: {path_line}")


# =============================================================================
# GUARDAR RESULTADOS
# =============================================================================

def guardar_resultados_sota(metrica_nombre, resultados, y_test, config):
    """Guarda CSVs de comparación y predicciones."""
    # 1. Tabla comparativa
    rows = []
    for m, res in resultados.items():
        rows.append({
            'modelo': m,
            'tipo': 'FASE6_baseline' if '_F6' in m else 'SOTA',
            'mape_pct': round(res['mape'] * 100, 2),
            'rmse': round(res['rmse'], 2),
            'mae': round(res['mae'], 2),
            'tiempo_s': round(res.get('tiempo_s', 0), 1),
        })

    df_comp = pd.DataFrame(rows).sort_values('mape_pct')
    df_comp['ranking'] = range(1, len(df_comp) + 1)
    df_comp['ganador'] = ''
    df_comp.iloc[0, df_comp.columns.get_loc('ganador')] = '🏆'

    # Marcar mejor SOTA
    sota_df = df_comp[df_comp['tipo'] == 'SOTA']
    if len(sota_df) > 0:
        best_sota_idx = sota_df.index[0]
        current = df_comp.loc[best_sota_idx, 'ganador']
        df_comp.loc[best_sota_idx, 'ganador'] = (
            f'{current} ⭐SOTA' if current else '⭐SOTA'
        )

    path_comp = os.path.join(RESULTS_DIR,
                             f'{metrica_nombre}_sota_comparacion.csv')
    df_comp.to_csv(path_comp, index=False)
    print(f"\n  💾 Comparación: {path_comp}")

    # 2. Predicciones holdout por modelo
    df_pred = pd.DataFrame({
        'fecha': y_test.index,
        'real': y_test.values,
    })
    for m, res in resultados.items():
        y_p = res['y_pred']
        # Rellenar a longitud completa si hace falta
        if len(y_p) < len(y_test):
            y_full = np.full(len(y_test), np.nan)
            y_full[:len(y_p)] = y_p
            y_p = y_full
        df_pred[f'pred_{m}'] = y_p[:len(y_test)]

    path_pred = os.path.join(RESULTS_DIR,
                             f'{metrica_nombre}_sota_predicciones.csv')
    df_pred.to_csv(path_pred, index=False)
    print(f"  💾 Predicciones: {path_pred}")

    return df_comp


# =============================================================================
# IMPRIMIR RESULTADOS
# =============================================================================

def imprimir_tabla_sota(metrica_nombre, df_comp, config):
    """Tabla de resultados formateada."""
    print(f"\n{'='*82}")
    print(f"  RESULTADOS FASE 7 — {metrica_nombre} ({config['unidad']})")
    print(f"  Holdout: {HOLDOUT_DIAS} días | Modelos: {len(df_comp)}")
    print(f"{'='*82}")
    print(f"  {'#':<3} {'Tipo':<7} {'Modelo':<22} {'MAPE':>8} "
          f"{'RMSE':>10} {'MAE':>10} {'T(s)':>7}")
    print(f"  {'─'*72}")
    for _, row in df_comp.iterrows():
        rank = int(row['ranking'])
        tipo = 'SOTA' if row['tipo'] == 'SOTA' else 'F6'
        flag = ''
        if '🏆' in str(row['ganador']):
            flag += ' 🏆'
        if '⭐' in str(row['ganador']):
            flag += ' ⭐'
        print(f"  {rank:<3} {tipo:<7} {row['modelo']:<22} "
              f"{row['mape_pct']:>7.2f}% {row['rmse']:>10.2f} "
              f"{row['mae']:>10.2f} {row['tiempo_s']:>6.1f}s{flag}")


# =============================================================================
# REGISTRO DE MODELOS SOTA
# =============================================================================

SOTA_MODELS = {
    'PatchTST': {
        'fn': _train_patchtst,
        'desc': 'Transformer + patches (Nie et al. 2023)',
    },
    'N-BEATS': {
        'fn': _train_nbeats,
        'desc': 'Neural Basis Expansion (Oreshkin et al. 2020)',
    },
    'TCN': {
        'fn': _train_tcn,
        'desc': 'Temporal Convolutional Network (Bai et al. 2018)',
    },
    'N-HiTS': {
        'fn': _train_nhits,
        'desc': 'Neural Hierarchical Interpolation (Challu et al. 2023)',
    },
    'NeuralProphet': {
        'fn': _train_neuralprophet,
        'desc': 'N-HiTS sustituto (NeuralProphet incompatible PL 2.x)',
    },
    'Chronos': {
        'fn': _train_chronos,
        'desc': 'Foundation Model zero-shot (Ansari et al. 2024)',
    },
}


# =============================================================================
# EJECUTAR EXPERIMENTO
# =============================================================================

def run_experiment(metrica_nombre, skip_models=None, chronos_model='small'):
    """Ejecuta el experimento SOTA completo para una métrica."""
    skip_models = set(skip_models or [])

    print(f"\n{'#'*82}")
    print(f"# FASE 7 — SOTA MODELS: {metrica_nombre}")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if skip_models:
        print(f"# Omitidos: {', '.join(skip_models)}")
    print(f"{'#'*82}")

    t_total = time.time()

    # 1. Build dataset (reutiliza FASE 6: target + features + calendario)
    df, feature_cols, config = build_dataset(metrica_nombre)
    piso = config.get('piso', 0)

    # Test set
    y_test = df.iloc[-HOLDOUT_DIAS:]['valor']
    print(f"\n  📐 Split: Train={len(df) - HOLDOUT_DIAS} | "
          f"Test={HOLDOUT_DIAS} "
          f"({y_test.index.min().date()} → {y_test.index.max().date()})")

    resultados = {}

    # ── FASE 6 Baselines ──
    print(f"\n  ── FASE 6 Baselines (con lags reales) ──")
    baselines = _run_fase6_baselines(df, feature_cols, config, HOLDOUT_DIAS)
    resultados.update(baselines)

    # ── SOTA Models ──
    # Skip NeuralProphet by default (redirects to N-HiTS which is also direct)
    active_models = {k: v for k, v in SOTA_MODELS.items()
                     if k not in skip_models and k != 'NeuralProphet'}
    n_sota = len(active_models)

    for i, (nombre, info) in enumerate(active_models.items(), 1):
        print(f"\n  [{i}/{n_sota}] {nombre} — {info['desc']}")
        t0 = time.time()
        try:
            extra_kw = {}
            if nombre == 'Chronos':
                extra_kw['chronos_model'] = chronos_model

            y_pred = info['fn'](df, HOLDOUT_DIAS, config, **extra_kw)
            elapsed = time.time() - t0

            if y_pred is None or len(y_pred) == 0:
                print(f"    ⚠️  No devolvió predicciones")
                continue

            y_pred = np.asarray(y_pred, dtype=np.float64)

            # Manejar NaN
            nan_count = np.isnan(y_pred).sum()
            if nan_count > 0:
                print(f"    ⚠️  {nan_count} NaN en predicciones, "
                      f"imputando con último valor válido")
                y_pred = pd.Series(y_pred).ffill().bfill().values

            # Ajustar longitud
            n = min(len(y_test), len(y_pred))
            if n < HOLDOUT_DIAS:
                print(f"    ⚠️  Solo {n}/{HOLDOUT_DIAS} predicciones")

            y_pred_eval = np.maximum(y_pred[:n], piso)
            y_true_eval = y_test.values[:n]

            metrics = _calc_metrics(y_true_eval, y_pred_eval, piso)

            # Guardar con longitud completa (pad si necesario)
            if len(y_pred) < HOLDOUT_DIAS:
                y_pred_full = np.full(HOLDOUT_DIAS, np.nan)
                y_pred_full[:len(y_pred)] = y_pred
            else:
                y_pred_full = y_pred[:HOLDOUT_DIAS]

            y_pred_full = np.maximum(y_pred_full, piso)

            resultados[nombre] = {
                'mape': metrics['mape'],
                'rmse': metrics['rmse'],
                'mae': metrics['mae'],
                'y_pred': y_pred_full,
                'tiempo_s': elapsed,
            }
            print(f"    ✅ MAPE={metrics['mape']*100:.2f}%, "
                  f"RMSE={metrics['rmse']:.2f} ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"    ❌ Falló ({elapsed:.1f}s): {e}")
            import traceback
            traceback.print_exc()

    if not resultados:
        print("\n  ❌ Ningún modelo completó exitosamente.")
        return None

    # ── Guardar resultados ──
    df_comp = guardar_resultados_sota(metrica_nombre, resultados,
                                      y_test, config)
    imprimir_tabla_sota(metrica_nombre, df_comp, config)

    # ── Gráficos ──
    try:
        generar_graficos_sota(metrica_nombre, resultados, y_test, config)
    except Exception as e:
        print(f"  ⚠️  Gráficos fallaron: {e}")

    elapsed_total = time.time() - t_total
    print(f"\n  ⏱  Tiempo total: {elapsed_total:.0f}s")

    # ── Anuncio de ganadores ──
    ganador = df_comp.iloc[0]
    sota_df = df_comp[df_comp['tipo'] == 'SOTA']
    sota_best = sota_df.iloc[0] if len(sota_df) > 0 else None

    print(f"\n{'='*82}")
    print(f"  🏆 GANADOR GLOBAL:  {ganador['modelo']:<22} "
          f"MAPE = {ganador['mape_pct']:.2f}%")
    if sota_best is not None:
        print(f"  ⭐ MEJOR SOTA:      {sota_best['modelo']:<22} "
              f"MAPE = {sota_best['mape_pct']:.2f}%")
        # ¿El SOTA superó al baseline?
        baseline_df = df_comp[df_comp['tipo'] == 'FASE6_baseline']
        if len(baseline_df) > 0:
            best_bl = baseline_df.iloc[0]
            delta = sota_best['mape_pct'] - best_bl['mape_pct']
            if delta < 0:
                print(f"  🚀 SOTA supera baseline por "
                      f"{abs(delta):.2f} pp de MAPE")
            else:
                print(f"  📊 Baseline supera SOTA por "
                      f"{delta:.2f} pp de MAPE")
    print(f"{'='*82}\n")

    return resultados, df_comp


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='FASE 7 — SOTA Time Series Models Experiment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python experiments/sota_models.py --metrica PRECIO_BOLSA
  python experiments/sota_models.py --metrica DEMANDA
  python experiments/sota_models.py --metrica ALL
  python experiments/sota_models.py --metrica PRECIO_BOLSA --skip Chronos
  python experiments/sota_models.py --metrica ALL --chronos-model tiny
        """,
    )
    parser.add_argument(
        '--metrica', type=str, required=True,
        choices=SOTA_METRICAS + ['ALL'],
        help='Métrica a evaluar (o ALL para ambas)',
    )
    parser.add_argument(
        '--skip', nargs='*', default=[],
        choices=list(SOTA_MODELS.keys()),
        help='Modelos SOTA a omitir',
    )
    parser.add_argument(
        '--chronos-model', type=str, default='small',
        choices=['tiny', 'small', 'base'],
        help='Variante de Chronos (default: small ~46M params)',
    )
    args = parser.parse_args()

    print(f"\n{'#'*82}")
    print(f"# FASE 7 — SOTA TIME SERIES MODELS EXPERIMENT")
    print(f"# Ministerio de Minas y Energía — República de Colombia")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"# Modelos SOTA: {', '.join(SOTA_MODELS.keys())}")
    if args.skip:
        print(f"# Omitidos: {', '.join(args.skip)}")
    print(f"# Chronos variant: {args.chronos_model}")
    print(f"# ⚠️  Experimento offline — NO modifica producción")
    print(f"{'#'*82}")

    metricas = SOTA_METRICAS if args.metrica == 'ALL' else [args.metrica]

    all_results = {}
    for met in metricas:
        result = run_experiment(
            met,
            skip_models=args.skip,
            chronos_model=args.chronos_model,
        )
        if result:
            all_results[met] = result

    # ── Resumen global ──
    if len(all_results) > 1:
        print(f"\n{'#'*82}")
        print(f"# RESUMEN GLOBAL — FASE 7 SOTA EXPERIMENT")
        print(f"{'#'*82}")
        for met, (_, df_comp) in all_results.items():
            ganador = df_comp.iloc[0]
            print(f"  {met:<20} 🏆 {ganador['modelo']:<22} "
                  f"MAPE = {ganador['mape_pct']:.2f}%")
            sota_only = df_comp[df_comp['tipo'] == 'SOTA']
            if len(sota_only) > 0:
                sb = sota_only.iloc[0]
                print(f"  {'':20} ⭐ {sb['modelo']:<22} "
                      f"MAPE = {sb['mape_pct']:.2f}% (mejor SOTA)")
        print(f"{'#'*82}\n")

    print("✅ FASE 7 completada.")


if __name__ == '__main__':
    main()
