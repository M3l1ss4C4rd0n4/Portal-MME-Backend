"""
Tests para el clamp físico [0,100] de PredictorMetricaSectorial.predecir()
(scripts/train_predictions_sector_energetico.py).

Reproduce el bug real encontrado en producción para EMBALSES_PCT: el
ensanchamiento del intervalo de confianza (calibración por horizonte +
asimetría El Niño) podía dejar intervalo_inferior negativo e
intervalo_superior muy por encima de 100% (llegó a 289% en producción).
El fix agrega un techo simétrico al piso que ya existía.
"""

import numpy as np
import pandas as pd
from unittest.mock import MagicMock

from scripts.train_predictions_sector_energetico import PredictorMetricaSectorial


def _build_predictor(oni_val, factor_calibracion, horizonte=340, techo_historico=100.0):
    config = {
        'dias_validacion': 180,
    }
    if techo_historico is not None:
        config['techo_historico'] = techo_historico

    p = PredictorMetricaSectorial('EMBALSES_PCT', config)
    p.modelo_sarima = None  # fuerza la rama solo-Prophet, sin SARIMAX
    p.pesos = {'prophet': 1.0, 'sarima': 0.0}
    p.metricas = {'factor_calibracion': factor_calibracion, 'factor_calibracion_pendiente': 0.0}
    p.regresores_nombres = []

    n_hist = 900
    fechas_hist = pd.date_range('2023-01-01', periods=n_hist, freq='D')
    fechas_fut = pd.date_range(fechas_hist[-1] + pd.Timedelta(days=1), periods=horizonte, freq='D')
    fechas_todas = fechas_hist.append(fechas_fut)

    p.modelo_prophet = MagicMock()
    p.modelo_prophet.history = pd.DataFrame({'ds': fechas_hist})
    future_df = pd.DataFrame({'ds': fechas_todas})
    p.modelo_prophet.make_future_dataframe.return_value = future_df

    pred = future_df.copy()
    # Semi-ancho amplio (45) a propósito — junto al factor de calibración,
    # reproduce la magnitud real observada en producción (IC llegando a
    # cientos de puntos porcentuales de ancho tras el ensanchamiento).
    pred['yhat'] = 75.0
    pred['yhat_lower'] = 30.0
    pred['yhat_upper'] = 120.0
    p.modelo_prophet.predict.return_value = pred

    p.regresores_completo = pd.DataFrame({'oni_index': oni_val}, index=fechas_todas)
    return p


def test_predecir_embalses_pct_respeta_0_100_con_oni_alto_y_horizonte_largo():
    p = _build_predictor(oni_val=1.81, factor_calibracion=4.0, horizonte=340)

    df = p.predecir(340, allow_negative=False)

    assert (df['intervalo_superior'] <= 100.0 + 1e-9).all()
    assert (df['intervalo_inferior'] >= 0.0 - 1e-9).all()
    assert (df['intervalo_superior'] >= df['intervalo_inferior']).all()
    assert (df['valor_predicho'] >= 0.0 - 1e-9).all()
    assert (df['valor_predicho'] <= 100.0 + 1e-9).all()


def test_predecir_sin_techo_configurado_preserva_comportamiento_anterior():
    """Sin techo_historico en config, intervalo_superior sigue sin acotar —
    confirma que el fix no cambia el comportamiento de métricas no tocadas
    (ej. DEMANDA, GENE_TOTAL, PRECIO_BOLSA)."""
    p = _build_predictor(oni_val=1.81, factor_calibracion=4.0, horizonte=200, techo_historico=None)

    df = p.predecir(200, allow_negative=False)

    assert (df['intervalo_inferior'] >= 0.0 - 1e-9).all()  # el piso en 0 sí seguía existiendo
    assert df['intervalo_superior'].max() > 100.0  # sin cambios: sigue sin techo


def test_predecir_oni_asof_fecha_de_entrenamiento_no_fecha_actual():
    """El ONI usado para la asimetría debe leerse a la fecha de corte de
    entrenamiento del modelo (history.max()), no el último valor disponible
    en la serie completa — evita la fuga temporal del backtest histórico."""
    p = _build_predictor(oni_val=0.0, factor_calibracion=1.0, horizonte=10)

    fecha_corte = p.modelo_prophet.history['ds'].max()
    serie = p.regresores_completo['oni_index'].copy()
    # ONI real "as of" la fecha de corte: neutro (no dispara asimetría).
    serie.loc[serie.index <= fecha_corte] = 0.0
    # ONI "del futuro" (post-corte, ej. el de HOY en un backtest histórico):
    # muy alto — si predecir() lo leyera por error, sí dispararía asimetría.
    serie.loc[serie.index > fecha_corte] = 3.0
    p.regresores_completo['oni_index'] = serie

    df_neutro = p.predecir(10, allow_negative=False)

    # Con ONI post-corte también alto, para comparar que SÍ cambia algo
    # cuando el valor real (as-of corte) es el que dispara la asimetría.
    p2 = _build_predictor(oni_val=3.0, factor_calibracion=1.0, horizonte=10)
    df_nino = p2.predecir(10, allow_negative=False)

    # Si predecir() leyera el ONI "del futuro" (3.0) en vez del real de la
    # fecha de corte (0.0), df_neutro tendría la misma asimetría que df_nino
    # (intervalo_inferior desplazado hacia abajo por El Niño). Al leer
    # correctamente el ONI as-of-corte (0.0, neutro), no se aplica ninguna
    # asimetría, así que su intervalo_inferior debe quedar MÁS ALTO (menos
    # ensanchado hacia abajo) que el del escenario con Niño real.
    assert df_neutro['intervalo_inferior'].iloc[0] > df_nino['intervalo_inferior'].iloc[0]
