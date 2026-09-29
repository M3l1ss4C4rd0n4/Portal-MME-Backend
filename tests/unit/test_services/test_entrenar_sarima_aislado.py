"""
Tests para PredictorMetricaSectorial._entrenar_arima_aislado() (Fase 43):
aislamiento de auto_arima() en subproceso + fallback a solo-Prophet cuando
el hijo es matado — sin OOM real, sin entrenar modelos SARIMAX reales, sin
depender de recursos del sistema (multiprocessing.get_context() mockeado).
"""
import queue as queue_mod
from unittest.mock import MagicMock, patch

import numpy as np

from scripts.train_predictions_sector_energetico import PredictorMetricaSectorial


def _build_predictor():
    return PredictorMetricaSectorial('EMBALSES_PCT', {'dias_validacion': 180})


def _mockear_proceso(get_side_effect, exitcode, is_alive_return=False):
    """
    is_alive() se llama varias veces dentro de _entrenar_arima_aislado()
    (una vez dentro del loop de polling si la cola está vacía, y siempre 2
    veces más en la limpieza post-join) — usar return_value en vez de una
    lista de side_effect fija evita tener que contar llamadas exactas para
    cada escenario.
    """
    fake_queue = MagicMock()
    fake_queue.get.side_effect = get_side_effect
    fake_proc = MagicMock()
    fake_proc.is_alive.return_value = is_alive_return
    fake_proc.exitcode = exitcode
    fake_ctx = MagicMock()
    fake_ctx.Queue.return_value = fake_queue
    fake_ctx.Process.return_value = fake_proc
    return fake_ctx, fake_proc


@patch('scripts.train_predictions_sector_energetico._calcular_limite_memoria_sarimax',
       return_value=2 * 1024**3)
def test_cae_a_fallback_cuando_el_hijo_es_matado(_mock_mem):
    """
    Simula el escenario real del OOM: el subproceso muere (SIGKILL) SIN
    escribir nada a la cola de resultado. _entrenar_arima_aislado() debe
    caer al fallback de solo-Prophet (retornar None) sin propagar ninguna
    excepción — antes esto mataba TODO el proceso de backtest (exit code
    137, no capturable).
    """
    fake_ctx, fake_proc = _mockear_proceso(
        get_side_effect=queue_mod.Empty,   # nunca hay resultado en la cola
        exitcode=-9,                       # terminado por señal (SIGKILL)
        is_alive_return=False,      # ya murió en el primer poll
    )
    with patch('multiprocessing.get_context', return_value=fake_ctx):
        p = _build_predictor()
        modelo = p._entrenar_arima_aislado(
            np.random.RandomState(0).normal(70, 5, 400), None,
            d_forzado=0, max_order_metrica=4,
        )

    assert modelo is None
    fake_proc.start.assert_called_once()


@patch('scripts.train_predictions_sector_energetico._calcular_limite_memoria_sarimax',
       return_value=None)
def test_no_intenta_subproceso_si_no_hay_memoria_suficiente(_mock_mem):
    """Si la memoria disponible está por debajo del piso, ni se lanza el
    fork (evita gastar tiempo/memoria en un intento condenado)."""
    with patch('multiprocessing.get_context') as mock_get_context:
        p = _build_predictor()
        modelo = p._entrenar_arima_aislado(np.zeros(10), None, d_forzado=0, max_order_metrica=4)
        mock_get_context.assert_not_called()
    assert modelo is None


@patch('scripts.train_predictions_sector_energetico._calcular_limite_memoria_sarimax',
       return_value=2 * 1024**3)
def test_camino_feliz_devuelve_el_modelo_del_subproceso(_mock_mem):
    modelo_falso = object()  # no hace falta un ARIMA real para probar el plumbing de IPC
    fake_ctx, fake_proc = _mockear_proceso(
        get_side_effect=[('ok', modelo_falso)],
        exitcode=0,
        is_alive_return=False,
    )
    with patch('multiprocessing.get_context', return_value=fake_ctx):
        p = _build_predictor()
        modelo = p._entrenar_arima_aislado(np.zeros(10), None, d_forzado=0, max_order_metrica=4)

    assert modelo is modelo_falso


@patch('scripts.train_predictions_sector_energetico._calcular_limite_memoria_sarimax',
       return_value=2 * 1024**3)
def test_memory_error_catchable_cae_a_fallback(_mock_mem):
    """El hijo alcanza SU PROPIO límite de RLIMIT_AS (MemoryError catchable,
    no un SIGKILL externo) — también debe caer al fallback limpiamente."""
    fake_ctx, fake_proc = _mockear_proceso(
        get_side_effect=[('memory_error', None)],
        exitcode=0,
        is_alive_return=False,
    )
    with patch('multiprocessing.get_context', return_value=fake_ctx):
        p = _build_predictor()
        modelo = p._entrenar_arima_aislado(np.zeros(10), None, d_forzado=0, max_order_metrica=4)

    assert modelo is None


@patch('scripts.train_predictions_sector_energetico._calcular_limite_memoria_sarimax',
       return_value=2 * 1024**3)
def test_error_generico_cae_a_fallback(_mock_mem):
    fake_ctx, fake_proc = _mockear_proceso(
        get_side_effect=[('error', 'algo falló dentro de auto_arima')],
        exitcode=0,
        is_alive_return=False,
    )
    with patch('multiprocessing.get_context', return_value=fake_ctx):
        p = _build_predictor()
        modelo = p._entrenar_arima_aislado(np.zeros(10), None, d_forzado=0, max_order_metrica=4)

    assert modelo is None
