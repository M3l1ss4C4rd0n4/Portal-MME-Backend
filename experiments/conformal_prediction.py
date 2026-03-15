#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  FASE 16 — PREDICCIÓN CONFORMAL SOBRE MODELOS EXISTENTES
  Portal Energético MME — Ministerio de Minas y Energía de Colombia
  Fecha: 2026-03-08
═══════════════════════════════════════════════════════════════════════

Problema: Los modelos actuales (RF MAPE≈16%, LightGBM MAPE≈17% para
PRECIO_BOLSA) reportan un único número puntual. El Ministerio y los
operadores del sistema necesitan intervalos de predicción calibrados
para cuantificar la incertidumbre y tomar decisiones de cobertura.

Solución: Predicción Conformal (Conformal Prediction) — produce
intervalos [lower_t, upper_t] con cobertura *garantizada* sin
necesidad de asumir distribución paramétrica alguna.

Variantes implementadas:
  1. ICP  (Inductive Conformal Prediction / Split Conformal)
         — baseline clásico, intervalos simétricos de ancho constante.
         Ref: Papadopoulos et al. (2002); Vovk et al. (2005).

  2. CQR  (Conformalized Quantile Regression)
         — LightGBM en modo cuantil produce intervalos asimétricos que
           capturan skewness del precio (spikes El Niño). La calibración
           conformal garantiza cobertura real ≥ 1-α.
         Ref: Romano, Patterson & Candès (2019). NeurIPS.

  3. ACI  (Adaptive Conformal Inference)
         — α_t rodante que se actualiza en cada paso con feedback real.
           No requiere intercambiabilidad: funciona con series no
           estacionarias y cambios de régimen. Ideal para energía.
         Ref: Gibbs & Candès (2021). NeurIPS.

Métricas de evaluación:
  PICP  (Prediction Interval Coverage Probability) — debe ≥ 1-α
  PINAW (Prediction Interval Normalized Average Width) — eficiencia
  Winkler Score — balance cobertura/eficiencia (menor = mejor)
  Coverage Gap  — PICP - (1-α), positivo = sobre-cobertura, ok
  MAPE punto    — calidad de la estimación puntual

Salidas:
  experiments/results/{METRICA}_conformal_comparacion.csv
  experiments/results/{METRICA}_conformal_predicciones.csv
  experiments/results/{METRICA}_conformal_intervalos.html
  experiments/results/{METRICA}_conformal_cobertura.html

Uso:
  python experiments/conformal_prediction.py --metrica PRECIO_BOLSA
  python experiments/conformal_prediction.py --metrica DEMANDA
  python experiments/conformal_prediction.py --metrica ALL --alpha 0.10
  python experiments/conformal_prediction.py --metrica PRECIO_BOLSA --cal-dias 60

⚠️  Experimento offline — NO modifica producción.
"""

import sys
import os
import argparse
import warnings
import time

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
from sklearn.ensemble import RandomForestRegressor
import lightgbm as lgb

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
pio.templates.default = 'plotly_white'

from model_selection import (
    build_dataset,
    HOLDOUT_DIAS,
    RANDOM_STATE,
    RESULTS_DIR,
    METRICAS_EXPERIMENT,
)

# ─── Configuración ─────────────────────────────────────────────────────────
CAL_DIAS_DEFAULT = 90    # Días reservados para calibración conformal
ALPHAS_ALL = [0.10, 0.05, 0.20]   # 90%, 95%, 80% de cobertura
DEFAULT_ALPHA = 0.10               # Cobertura objetivo principal

# Paleta de colores consistente con el proyecto
PALETTE = {
    'ICP_RF':    '#EF553B',
    'ICP_LGBM':  '#FFA15A',
    'CQR_LGBM':  '#636EFA',
    'ACI_RF':    '#00CC96',
    'ACI_LGBM':  '#AB63FA',
    'real':      '#1a1a2e',
    'pi_band':   'rgba(99,110,250,0.15)',
}


# =============================================================================
# ENTRENAMIENTO DE MODELOS BASE (devuelven el objeto modelo)
# =============================================================================

def _fit_rf(X_train, y_train):
    """RandomForest calibrado igual que FASE 6."""
    model = RandomForestRegressor(
        n_estimators=300, max_depth=12, min_samples_leaf=5,
        random_state=RANDOM_STATE, n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def _fit_lgbm(X_train, y_train, X_val, y_val):
    """LightGBM con early stopping, igual que FASE 6."""
    model = lgb.LGBMRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        reg_alpha=0.1, reg_lambda=1.0, n_jobs=-1, verbosity=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    return model


def _fit_lgbm_quantile(X_train, y_train, alpha_q):
    """LightGBM en modo cuantil para CQR (sin early stopping)."""
    model = lgb.LGBMRegressor(
        objective='quantile',
        alpha=alpha_q,
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        reg_alpha=0.1, n_jobs=-1, verbosity=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(X_train, y_train)
    return model


# =============================================================================
# 1. ICP — Inductive Conformal Prediction (Split Conformal)
# =============================================================================

class ICPPredictor:
    """
    Predictor conformal inductivo estándar.

    Algoritmo:
      1. Calibrar: scores_i = |y_i - f(x_i)|  para i en conjunto de cal.
      2. q = quantile(scores, ceil((n+1)(1-α)) / n)  [cuantil finito]
      3. Test: C(x) = [f(x) - q, f(x) + q]

    Garantía: P(y ∈ C(x)) ≥ 1-α bajo intercambiabilidad (marginal).
    """

    def __init__(self, model, alpha=0.10, nombre='ICP', piso=0.0):
        self.model = model
        self.alpha = alpha
        self.nombre = nombre
        self.piso = piso
        self.q = None

    def calibrate(self, X_cal, y_cal):
        preds = self.model.predict(X_cal)
        scores = np.abs(np.asarray(y_cal, dtype=float) - preds)
        n = len(scores)
        # Corrección finita de Vovk et al. 2005
        level = min(np.ceil((n + 1) * (1 - self.alpha)) / n, 1.0)
        self.q = float(np.quantile(scores, level))
        return self

    def predict(self, X_test):
        y_hat = np.maximum(self.model.predict(X_test), self.piso)
        return y_hat, y_hat - self.q, y_hat + self.q


# =============================================================================
# 2. CQR — Conformalized Quantile Regression
# =============================================================================

class CQRPredictor:
    """
    Conformalized Quantile Regression (Romano, Patterson & Candès. NeurIPS 2019).

    Ventajas sobre ICP para series energéticas:
    - Intervalos asimétricos: captura la skewness del precio de bolsa
      (spike alcista El Niño ≫ spike bajista)
    - El ancho varía localmente según la incertidumbre condicional
    - La calibración conformal garantiza cobertura ≥ 1-α igualmente

    Algoritmo:
      1. Entrenar modelo_low (cuantil α/2) y modelo_high (cuantil 1-α/2)
      2. Score_i = max(q_low(x_i) - y_i,  y_i - q_high(x_i))
         [penaliza tanto por arriba como por abajo del intervalo base]
      3. q_conf = quantile(scores, (1-α)(1 + 1/n_cal))
      4. Intervalo final: [model_low(x) - q_conf, model_high(x) + q_conf]
    """

    def __init__(self, model_low, model_high, alpha=0.10, piso=0.0):
        self.model_low = model_low
        self.model_high = model_high
        self.alpha = alpha
        self.piso = piso
        self.nombre = 'CQR_LGBM'
        self.q_conf = None

    def calibrate(self, X_cal, y_cal):
        y = np.asarray(y_cal, dtype=float)
        q_lo = self.model_low.predict(X_cal)
        q_hi = self.model_high.predict(X_cal)
        scores = np.maximum(q_lo - y, y - q_hi)
        n = len(scores)
        level = min(np.ceil((n + 1) * (1 - self.alpha)) / n, 1.0)
        self.q_conf = float(np.quantile(scores, level))
        return self

    def predict(self, X_test):
        q_lo = self.model_low.predict(X_test)
        q_hi = self.model_high.predict(X_test)
        # Punto central: media de los cuantiles entrenados
        y_hat = (q_lo + q_hi) / 2.0
        y_hat = np.maximum(y_hat, self.piso)
        lower = q_lo - self.q_conf
        upper = q_hi + self.q_conf
        return y_hat, lower, upper


# =============================================================================
# 3. ACI — Adaptive Conformal Inference
# =============================================================================

class ACIPredictor:
    """
    Adaptive Conformal Inference (Gibbs & Candès. NeurIPS 2021).

    Crítico para series energéticas colombianas:
    - El precio de bolsa NO es estacionario (fenómenos El Niño/La Niña)
    - ICP clásico falla cuando la distribución de residuos deriva
    - ACI actualiza α_t en cada paso con feedback del valor real observado

    Ecuación de actualización (gradient descent sobre cobertura):
      α_{t+1} = α_t + γ · (α_target - 1[y_t ∉ C(x_t)])
      si y_t fuera del intervalo: α_{t+1} decrece → intervalo se ensancha
      si y_t dentro del intervalo: α_{t+1} crece → intervalo se estrecha

    γ (gamma): velocidad de adaptación. Recomendado: 0.005 – 0.02
    window: buffer rodante de residuos para estimar cuantiles locales.
    """

    def __init__(self, model, alpha=0.10, gamma=0.008, window=60,
                 nombre='ACI', piso=0.0):
        self.model = model
        self.alpha_target = alpha
        self.gamma = gamma
        self.window = window
        self.nombre = nombre
        self.piso = piso

    def fit_predict(self, X_cal, y_cal, X_test, y_test):
        """Calibra sobre X_cal/y_cal y predice rolling sobre X_test."""
        y_cal_arr = np.asarray(y_cal, dtype=float)
        y_test_arr = np.asarray(y_test, dtype=float)

        # Inicializar buffer de residuos con el conjunto de calibración
        cal_preds = self.model.predict(X_cal)
        residuals = list(np.abs(y_cal_arr - cal_preds))

        alpha_t = self.alpha_target
        y_hat_list, lower_list, upper_list, alpha_trace = [], [], [], []

        for i in range(len(X_test)):
            # Cuantil local sobre ventana rodante
            buf = residuals[-self.window:] if len(residuals) >= self.window \
                  else residuals
            q_t = float(np.quantile(buf, np.clip(1.0 - alpha_t, 0.001, 0.999)))

            # Predicción del paso i
            xi = X_test.iloc[[i]] if hasattr(X_test, 'iloc') else X_test[i:i+1]
            y_hat = float(np.maximum(self.model.predict(xi)[0], self.piso))
            lower = y_hat - q_t
            upper = y_hat + q_t

            y_hat_list.append(y_hat)
            lower_list.append(lower)
            upper_list.append(upper)
            alpha_trace.append(alpha_t)

            # Actualización de α_t con el verdadero y_t (feedback)
            covered = float(lower <= y_test_arr[i] <= upper)
            # covered=1 → aumenta α_t (intervalo más estrecho próxima vez)
            # covered=0 → disminuye α_t (intervalo más ancho)
            alpha_t += self.gamma * (self.alpha_target - (1.0 - covered))
            alpha_t = float(np.clip(alpha_t, 0.001, 0.999))

            # Actualizar buffer con residuo real
            residuals.append(abs(y_test_arr[i] - y_hat))

        return (
            np.array(y_hat_list),
            np.array(lower_list),
            np.array(upper_list),
            np.array(alpha_trace),
        )


# =============================================================================
# MÉTRICAS DE EVALUACIÓN DE INTERVALOS
# =============================================================================

def coverage_metrics(y_true, y_hat, lower, upper, alpha=0.10):
    """
    Calcula métricas estándar para intervalos de predicción probabilísticos.

    Retorna dict con:
      picp   — Prediction Interval Coverage Probability (debe ≥ 1-α)
      pinaw  — Pred. Interval Normalized Average Width (menor = más eficiente)
      winkler_mean — Winkler Score promedio (menor = mejor balance)
      mean_width   — Ancho promedio del intervalo (in unidad de la métrica)
      coverage_gap — PICP - (1-α).  >0 ok (conservador).  <0 mal (sub-cubre)
      mape_punto   — MAPE de la estimación puntual (%) — igual que FASE 6
    """
    y = np.asarray(y_true, dtype=float)
    yh = np.asarray(y_hat, dtype=float)
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    n = len(y)

    covered = (y >= lo) & (y <= hi)
    picp = float(covered.mean())
    widths = hi - lo
    rng = float(y.max() - y.min())
    pinaw = float(widths.mean()) / (rng + 1e-8)

    # Winkler Score: penaliza ancho + doble penalización por fallo de cobertura
    winkler_scores = []
    for yi, li, ui in zip(y, lo, hi):
        w = float(ui - li)
        if yi < li:
            w += (2.0 / alpha) * float(li - yi)
        elif yi > ui:
            w += (2.0 / alpha) * float(yi - ui)
        winkler_scores.append(w)

    mape_punto = float(mean_absolute_percentage_error(y, yh) * 100)

    return {
        'picp': round(picp, 4),
        'target_coverage': round(1 - alpha, 4),
        'coverage_gap': round(picp - (1 - alpha), 4),
        'mean_width': round(float(widths.mean()), 2),
        'pinaw': round(pinaw, 4),
        'winkler_mean': round(float(np.mean(winkler_scores)), 2),
        'mape_punto_pct': round(mape_punto, 2),
        'n_test': n,
    }


# =============================================================================
# RUNNER PRINCIPAL
# =============================================================================

def run_conformal_experiment(metrica_nombre, alpha=DEFAULT_ALPHA,
                             cal_dias=CAL_DIAS_DEFAULT):
    """
    Ejecuta ICP + CQR + ACI para una métrica dada.
    Usa la misma infraestructura de datos que FASE 6 (build_dataset).
    """
    print(f"\n{'#'*70}")
    print(f"# FASE 16 — CONFORMAL PREDICTION: {metrica_nombre}")
    print(f"# α={alpha:.2f} → cobertura objetivo {(1-alpha)*100:.0f}%")
    print(f"# Calibración: {cal_dias}d | Holdout: {HOLDOUT_DIAS}d")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*70}")
    t_global = time.time()

    # ─── 1. Datos ──────────────────────────────────────────────────────────
    df, feature_cols, config = build_dataset(metrica_nombre)
    piso = float(config.get('piso', 0.0))
    unidad = config.get('unidad', '')

    total = len(df)
    n_test = HOLDOUT_DIAS
    n_cal = cal_dias
    n_train = total - n_test - n_cal

    if n_train < 60:
        raise ValueError(
            f"Training set demasiado pequeño ({n_train} rows). "
            f"Reduci cal_dias (actual={cal_dias}) o usa --metrica con más historia."
        )

    idx_train_end = n_train
    idx_cal_end = n_train + n_cal

    df_train = df.iloc[:idx_train_end]
    df_cal = df.iloc[idx_train_end:idx_cal_end]
    df_test = df.iloc[idx_cal_end:]

    X_train = df_train[feature_cols]
    y_train = df_train['valor']
    X_cal = df_cal[feature_cols]
    y_cal = df_cal['valor']
    X_test = df_test[feature_cols]
    y_test = df_test['valor']

    print(f"\n  Split temporal:")
    print(f"    Train:   {len(df_train):>4} días  "
          f"({df_train.index.min().date()} → {df_train.index.max().date()})")
    print(f"    Cal:     {len(df_cal):>4} días  "
          f"({df_cal.index.min().date()} → {df_cal.index.max().date()})")
    print(f"    Test:    {len(df_test):>4} días  "
          f"({df_test.index.min().date()} → {df_test.index.max().date()})")
    print(f"    Features: {len(feature_cols)}")

    resultados = {}

    # ─── 2. ICP sobre RandomForest ─────────────────────────────────────────
    print(f"\n  ── [1/5] ICP sobre RandomForest ──")
    t0 = time.time()
    rf_model = _fit_rf(X_train, y_train)
    icp_rf = ICPPredictor(rf_model, alpha=alpha, nombre='ICP_RF', piso=piso)
    icp_rf.calibrate(X_cal, y_cal)
    y_hat_rf, lo_rf, hi_rf = icp_rf.predict(X_test)
    t_rf = time.time() - t0
    m_icp_rf = coverage_metrics(y_test, y_hat_rf, lo_rf, hi_rf, alpha)
    m_icp_rf['tiempo_s'] = round(t_rf, 1)
    resultados['ICP_RF'] = {
        **m_icp_rf,
        'y_hat': y_hat_rf, 'lower': lo_rf, 'upper': hi_rf,
        'q': icp_rf.q,
    }
    print(f"    PICP={m_icp_rf['picp']:.3f} (target={1-alpha:.2f})  "
          f"Ancho={m_icp_rf['mean_width']:.1f} {unidad}  "
          f"MAPE_punto={m_icp_rf['mape_punto_pct']:.2f}%  ({t_rf:.1f}s)")

    # ─── 3. ICP sobre LightGBM ────────────────────────────────────────────
    print(f"\n  ── [2/5] ICP sobre LightGBM ──")
    t0 = time.time()
    # Para early stopping: usar X_cal como validation (proxy, no contamina test)
    lgbm_model = _fit_lgbm(X_train, y_train, X_cal, y_cal)
    icp_lgbm = ICPPredictor(lgbm_model, alpha=alpha, nombre='ICP_LGBM', piso=piso)
    icp_lgbm.calibrate(X_cal, y_cal)
    y_hat_lgbm, lo_lgbm, hi_lgbm = icp_lgbm.predict(X_test)
    t_lgbm = time.time() - t0
    m_icp_lgbm = coverage_metrics(y_test, y_hat_lgbm, lo_lgbm, hi_lgbm, alpha)
    m_icp_lgbm['tiempo_s'] = round(t_lgbm, 1)
    resultados['ICP_LGBM'] = {
        **m_icp_lgbm,
        'y_hat': y_hat_lgbm, 'lower': lo_lgbm, 'upper': hi_lgbm,
        'q': icp_lgbm.q,
    }
    print(f"    PICP={m_icp_lgbm['picp']:.3f} (target={1-alpha:.2f})  "
          f"Ancho={m_icp_lgbm['mean_width']:.1f} {unidad}  "
          f"MAPE_punto={m_icp_lgbm['mape_punto_pct']:.2f}%  ({t_lgbm:.1f}s)")

    # ─── 4. CQR sobre LightGBM cuantil ────────────────────────────────────
    print(f"\n  ── [3/5] CQR sobre LightGBM (cuantil) ──")
    t0 = time.time()
    alpha_lo = alpha / 2.0          # cuantil inferior, p.ej. 0.05
    alpha_hi = 1.0 - alpha / 2.0   # cuantil superior, p.ej. 0.95
    lgbm_q_lo = _fit_lgbm_quantile(X_train, y_train, alpha_lo)
    lgbm_q_hi = _fit_lgbm_quantile(X_train, y_train, alpha_hi)
    cqr = CQRPredictor(lgbm_q_lo, lgbm_q_hi, alpha=alpha, piso=piso)
    cqr.calibrate(X_cal, y_cal)
    y_hat_cqr, lo_cqr, hi_cqr = cqr.predict(X_test)
    t_cqr = time.time() - t0
    m_cqr = coverage_metrics(y_test, y_hat_cqr, lo_cqr, hi_cqr, alpha)
    m_cqr['tiempo_s'] = round(t_cqr, 1)
    resultados['CQR_LGBM'] = {
        **m_cqr,
        'y_hat': y_hat_cqr, 'lower': lo_cqr, 'upper': hi_cqr,
        'q_conf': cqr.q_conf,
    }
    print(f"    PICP={m_cqr['picp']:.3f} (target={1-alpha:.2f})  "
          f"Ancho={m_cqr['mean_width']:.1f} {unidad}  "
          f"MAPE_punto={m_cqr['mape_punto_pct']:.2f}%  ({t_cqr:.1f}s)")

    # ─── 5. ACI sobre RandomForest ────────────────────────────────────────
    print(f"\n  ── [4/5] ACI (adaptativo) sobre RandomForest ──")
    t0 = time.time()
    aci_rf = ACIPredictor(rf_model, alpha=alpha, gamma=0.008,
                          window=60, nombre='ACI_RF', piso=piso)
    y_hat_aci_rf, lo_aci_rf, hi_aci_rf, alpha_trace_rf = \
        aci_rf.fit_predict(X_cal, y_cal, X_test, y_test)
    t_aci_rf = time.time() - t0
    m_aci_rf = coverage_metrics(y_test, y_hat_aci_rf, lo_aci_rf, hi_aci_rf, alpha)
    m_aci_rf['tiempo_s'] = round(t_aci_rf, 1)
    resultados['ACI_RF'] = {
        **m_aci_rf,
        'y_hat': y_hat_aci_rf, 'lower': lo_aci_rf, 'upper': hi_aci_rf,
        'alpha_trace': alpha_trace_rf,
    }
    print(f"    PICP={m_aci_rf['picp']:.3f} (target={1-alpha:.2f})  "
          f"Ancho={m_aci_rf['mean_width']:.1f} {unidad}  "
          f"MAPE_punto={m_aci_rf['mape_punto_pct']:.2f}%  ({t_aci_rf:.1f}s)")

    # ─── 6. ACI sobre LightGBM ────────────────────────────────────────────
    print(f"\n  ── [5/5] ACI (adaptativo) sobre LightGBM ──")
    t0 = time.time()
    aci_lgbm = ACIPredictor(lgbm_model, alpha=alpha, gamma=0.008,
                             window=60, nombre='ACI_LGBM', piso=piso)
    y_hat_aci_lgbm, lo_aci_lgbm, hi_aci_lgbm, alpha_trace_lgbm = \
        aci_lgbm.fit_predict(X_cal, y_cal, X_test, y_test)
    t_aci_lgbm = time.time() - t0
    m_aci_lgbm = coverage_metrics(y_test, y_hat_aci_lgbm,
                                   lo_aci_lgbm, hi_aci_lgbm, alpha)
    m_aci_lgbm['tiempo_s'] = round(t_aci_lgbm, 1)
    resultados['ACI_LGBM'] = {
        **m_aci_lgbm,
        'y_hat': y_hat_aci_lgbm, 'lower': lo_aci_lgbm, 'upper': hi_aci_lgbm,
        'alpha_trace': alpha_trace_lgbm,
    }
    print(f"    PICP={m_aci_lgbm['picp']:.3f} (target={1-alpha:.2f})  "
          f"Ancho={m_aci_lgbm['mean_width']:.1f} {unidad}  "
          f"MAPE_punto={m_aci_lgbm['mape_punto_pct']:.2f}%  ({t_aci_lgbm:.1f}s)")

    print(f"\n  ✅ Experimento completo en {time.time()-t_global:.1f}s")

    return resultados, y_test, config


# =============================================================================
# VISUALIZACIÓN
# =============================================================================

def plot_conformal_results(metrica_nombre, resultados, y_test, config,
                           alpha=DEFAULT_ALPHA):
    """Genera gráficos Plotly interactivos de los intervalos de predicción."""
    unidad = config.get('unidad', '')
    target_cov = f"{(1-alpha)*100:.0f}%"

    fechas = y_test.index
    y_real = y_test.values.astype(float)

    # ─── Gráfico 1: Series con bandas de predicción ────────────────────────
    # Un subplot por método (2×2 + CQR combinado en col 3)
    metodos_plot = ['ICP_RF', 'ICP_LGBM', 'CQR_LGBM', 'ACI_RF', 'ACI_LGBM']
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=[
            f'ICP — RandomForest (PICP={resultados["ICP_RF"]["picp"]:.3f})',
            f'ICP — LightGBM (PICP={resultados["ICP_LGBM"]["picp"]:.3f})',
            f'CQR — LightGBM Cuantil (PICP={resultados["CQR_LGBM"]["picp"]:.3f})',
            f'ACI — RandomForest (PICP={resultados["ACI_RF"]["picp"]:.3f})',
            f'ACI — LightGBM (PICP={resultados["ACI_LGBM"]["picp"]:.3f})',
            'Comparación Winkler Score (menor = mejor)',
        ],
        shared_xaxes=False,
        vertical_spacing=0.10,
        horizontal_spacing=0.08,
    )

    posiciones = [(1,1), (1,2), (2,1), (2,2), (3,1)]
    for (row, col), metodo in zip(posiciones, metodos_plot):
        res = resultados[metodo]
        color = PALETTE.get(metodo, '#636EFA')
        color_rgb = color.lstrip('#')
        r = int(color_rgb[0:2], 16)
        g = int(color_rgb[2:4], 16)
        b = int(color_rgb[4:6], 16)
        fill_color = f'rgba({r},{g},{b},0.18)'

        # Banda superior + inferior
        fig.add_trace(go.Scatter(
            x=np.concatenate([fechas, fechas[::-1]]),
            y=np.concatenate([res['upper'], res['lower'][::-1]]),
            fill='toself', fillcolor=fill_color,
            line=dict(color='rgba(0,0,0,0)'),
            name=f'IC {target_cov} {metodo}',
            showlegend=False, hoverinfo='skip',
        ), row=row, col=col)

        # Predicción puntual
        fig.add_trace(go.Scatter(
            x=fechas, y=res['y_hat'],
            mode='lines', name=f'Pred {metodo}',
            line=dict(color=color, width=1.8, dash='dot'),
            showlegend=False,
        ), row=row, col=col)

        # Real
        fig.add_trace(go.Scatter(
            x=fechas, y=y_real,
            mode='lines+markers', name='Real',
            line=dict(color='black', width=2),
            marker=dict(size=4),
            showlegend=(row == 1 and col == 1),
        ), row=row, col=col)

    # Subplot 3,2: Comparación Winkler Score (barras)
    winkler_vals = [resultados[m]['winkler_mean'] for m in metodos_plot]
    winkler_colors = [PALETTE.get(m, '#636EFA') for m in metodos_plot]
    fig.add_trace(go.Bar(
        x=metodos_plot, y=winkler_vals,
        marker_color=winkler_colors,
        text=[f'{w:.1f}' for w in winkler_vals],
        textposition='outside',
        showlegend=False,
    ), row=3, col=2)

    fig.update_layout(
        title=dict(
            text=(f'FASE 16 — Predicción Conformal: {metrica_nombre} '
                  f'({unidad}) | Cobertura objetivo {target_cov}'),
            font=dict(size=15),
        ),
        height=1050, width=1250,
        template='plotly_white',
        legend=dict(orientation='h', y=1.02, x=0),
    )
    for i in range(1, 7):
        fig.update_yaxes(title_text=unidad,
                         row=(i-1)//2 + 1, col=(i-1) % 2 + 1)

    path1 = os.path.join(RESULTS_DIR,
                          f'{metrica_nombre}_conformal_intervalos.html')
    fig.write_html(path1)
    print(f"  📊 Intervalos: {path1}")

    # ─── Gráfico 2: PICP vs target + PINAW ────────────────────────────────
    fig2 = make_subplots(
        rows=1, cols=3,
        subplot_titles=[
            'PICP (Cobertura Empírica)',
            'PINAW (Ancho Normalizado)',
            'MAPE Punto Central (%)',
        ],
    )
    target_cov_val = 1 - alpha
    metodos_bar = metodos_plot

    picps = [resultados[m]['picp'] for m in metodos_bar]
    pinaws = [resultados[m]['pinaw'] for m in metodos_bar]
    mapes_bar = [resultados[m]['mape_punto_pct'] for m in metodos_bar]
    bar_colors = [PALETTE.get(m, '#636EFA') for m in metodos_bar]

    for mp, vals, row_i, col_i, fmt in [
        ('picp', picps, 1, 1, '.3f'),
        ('pinaw', pinaws, 1, 2, '.3f'),
        ('mape', mapes_bar, 1, 3, '.2f'),
    ]:
        fig2.add_trace(go.Bar(
            x=metodos_bar,
            y=vals,
            marker_color=bar_colors,
            text=[f'{v:{fmt}}' for v in vals],
            textposition='outside',
            showlegend=False,
        ), row=row_i, col=col_i)

    # Línea de cobertura objetivo en subplot PICP
    fig2.add_hline(y=target_cov_val, line_dash='dash', line_color='red',
                   annotation_text=f'Objetivo {target_cov}', row=1, col=1)

    fig2.update_layout(
        title=f'FASE 16 — Métricas Conformal: {metrica_nombre}',
        height=480, width=1100, template='plotly_white',
    )
    path2 = os.path.join(RESULTS_DIR,
                          f'{metrica_nombre}_conformal_cobertura.html')
    fig2.write_html(path2)
    print(f"  📈 Cobertura: {path2}")

    # ─── Gráfico 3: Alpha trace de ACI ────────────────────────────────────
    if 'alpha_trace' in resultados.get('ACI_RF', {}):
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=list(range(len(resultados['ACI_RF']['alpha_trace']))),
            y=resultados['ACI_RF']['alpha_trace'],
            mode='lines', name='ACI_RF α_t',
            line=dict(color=PALETTE['ACI_RF'], width=2),
        ))
        if 'alpha_trace' in resultados.get('ACI_LGBM', {}):
            fig3.add_trace(go.Scatter(
                x=list(range(len(resultados['ACI_LGBM']['alpha_trace']))),
                y=resultados['ACI_LGBM']['alpha_trace'],
                mode='lines', name='ACI_LGBM α_t',
                line=dict(color=PALETTE['ACI_LGBM'], width=2, dash='dash'),
            ))
        fig3.add_hline(y=alpha, line_dash='dot', line_color='red',
                       annotation_text=f'α_target={alpha}')
        fig3.update_layout(
            title=f'ACI — Evolución de α_t durante el holdout ({metrica_nombre})',
            xaxis_title='Paso t (días de holdout)',
            yaxis_title='α_t efectivo',
            height=380, width=900, template='plotly_white',
        )
        path3 = os.path.join(RESULTS_DIR,
                              f'{metrica_nombre}_conformal_aci_trace.html')
        fig3.write_html(path3)
        print(f"  📉 ACI α_t trace: {path3}")


# =============================================================================
# GUARDAR RESULTADOS
# =============================================================================

def save_results(metrica_nombre, resultados, y_test, config, alpha=DEFAULT_ALPHA):
    """Guarda CSVs de comparación y predicciones con intervalos."""
    # 1. Tabla comparativa de métodos
    rows = []
    for metodo, res in resultados.items():
        picp_ok = '✅' if res['picp'] >= (1 - alpha) else '⚠️'
        rows.append({
            'metodo': metodo,
            'picp': res['picp'],
            'target_coverage': res['target_coverage'],
            'coverage_gap': res['coverage_gap'],
            'picp_ok': picp_ok,
            'mean_width': res['mean_width'],
            'pinaw': res['pinaw'],
            'winkler_mean': res['winkler_mean'],
            'mape_punto_pct': res['mape_punto_pct'],
            'tiempo_s': res.get('tiempo_s', 0),
        })

    df_comp = pd.DataFrame(rows)
    # Ordenar por Winkler Score (menor = mejor balance cobertura/eficiencia)
    df_comp = df_comp.sort_values('winkler_mean').reset_index(drop=True)
    df_comp.insert(0, 'ranking', range(1, len(df_comp) + 1))
    df_comp['ganador'] = ''
    df_comp.at[0, 'ganador'] = '🏆'

    path_comp = os.path.join(RESULTS_DIR,
                              f'{metrica_nombre}_conformal_comparacion.csv')
    df_comp.to_csv(path_comp, index=False)
    print(f"\n  💾 Comparación: {path_comp}")

    # 2. Predicciones + intervalos por fecha
    df_pred = pd.DataFrame({'fecha': y_test.index, 'real': y_test.values})
    for metodo, res in resultados.items():
        n = len(y_test)
        df_pred[f'pred_{metodo}'] = res['y_hat'][:n]
        df_pred[f'lower_{metodo}'] = res['lower'][:n]
        df_pred[f'upper_{metodo}'] = res['upper'][:n]
        df_pred[f'cubierto_{metodo}'] = (
            (y_test.values >= res['lower'][:n]) &
            (y_test.values <= res['upper'][:n])
        ).astype(int)

    path_pred = os.path.join(RESULTS_DIR,
                              f'{metrica_nombre}_conformal_predicciones.csv')
    df_pred.to_csv(path_pred, index=False)
    print(f"  💾 Predicciones+intervalos: {path_pred}")

    return df_comp


# =============================================================================
# TABLA RESUMEN EN CONSOLA
# =============================================================================

def print_tabla(metrica_nombre, df_comp, config, alpha):
    """Imprime tabla de resultados formateada en consola."""
    unidad = config.get('unidad', '')
    target = (1 - alpha) * 100

    print(f"\n{'='*88}")
    print(f"  RESULTADOS FASE 16 — CONFORMAL PREDICTION: {metrica_nombre} ({unidad})")
    print(f"  Cobertura objetivo: {target:.0f}%  |  α = {alpha}")
    print(f"  Ordenados por Winkler Score (menor = mejor balance)")
    print(f"{'='*88}")
    print(f"  {'#':<3} {'Método':<13} {'PICP':>6} {'Obj':>5} {'Gap':>6} "
          f"{'Ancho':>9} {'PINAW':>7} {'Winkler':>9} {'MAPE%':>7} {'T(s)':>6}  {'OK?':<3}")
    print(f"  {'─'*84}")
    for _, row in df_comp.iterrows():
        gap_str = f"{row['coverage_gap']:+.3f}"
        print(
            f"  {int(row['ranking']):<3} {row['metodo']:<13} "
            f"{row['picp']:>6.3f} {row['target_coverage']:>5.2f} {gap_str:>6} "
            f"{row['mean_width']:>9.2f} {row['pinaw']:>7.4f} "
            f"{row['winkler_mean']:>9.1f} {row['mape_punto_pct']:>7.2f} "
            f"{row['tiempo_s']:>6.1f}  {row['picp_ok']}"
        )
    print(f"\n  Interpretación:")
    print(f"    PICP ≥ {target:.0f}% → intervalo bien calibrado ✅")
    print(f"    PICP <  {target:.0f}% → sub-cubre, el intervalo es demasiado estrecho ⚠️")
    print(f"    PINAW más bajo → más eficiente (intervalos más estrechos)")
    print(f"    Winkler Score más bajo → mejor balance cobertura/eficiencia")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='FASE 16 — Conformal Prediction sobre RF/LightGBM'
    )
    parser.add_argument(
        '--metrica',
        default='PRECIO_BOLSA',
        choices=list(METRICAS_EXPERIMENT.keys()) + ['ALL'],
        help='Métrica a analizar (default: PRECIO_BOLSA)',
    )
    parser.add_argument(
        '--alpha',
        type=float,
        default=DEFAULT_ALPHA,
        help=f'Nivel de error conformal (default: {DEFAULT_ALPHA} → 90%% cobertura)',
    )
    parser.add_argument(
        '--cal-dias',
        type=int,
        default=CAL_DIAS_DEFAULT,
        help=f'Días para calibración conformal (default: {CAL_DIAS_DEFAULT})',
    )
    parser.add_argument(
        '--no-plots',
        action='store_true',
        help='Omitir generación de gráficos Plotly (más rápido)',
    )
    args = parser.parse_args()

    metricas = (list(METRICAS_EXPERIMENT.keys())
                if args.metrica == 'ALL' else [args.metrica])

    for metrica in metricas:
        try:
            resultados, y_test, config = run_conformal_experiment(
                metrica, alpha=args.alpha, cal_dias=args.cal_dias,
            )
            df_comp = save_results(metrica, resultados, y_test, config, args.alpha)
            print_tabla(metrica, df_comp, config, args.alpha)
            if not args.no_plots:
                plot_conformal_results(metrica, resultados, y_test, config, args.alpha)
        except Exception as exc:
            print(f"\n  ❌ Error en {metrica}: {exc}")
            import traceback
            traceback.print_exc()
            if args.metrica != 'ALL':
                raise

    print(f"\n{'='*70}")
    print("  FASE 16 completada.")
    print(f"  Resultados en: {RESULTS_DIR}/")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
