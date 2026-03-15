"""Tests básicos para PredictionsService"""

import pytest
import numpy as np
import pandas as pd
from domain.services.predictions_service import PredictionsService
from domain.services.predictions_service_extended import PredictionsService as PredictionsServiceExtended


# ═══════════════════════════════════════════════════════════════════════
# FASE 16 — Tests de Predicción Conformal
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def svc_extended():
    return PredictionsServiceExtended.__new__(PredictionsServiceExtended)


@pytest.fixture
def synthetic_historical():
    np.random.seed(7)
    n = 120
    dates = pd.date_range('2025-01-01', periods=n, freq='D')
    vals = 200 + 10 * np.sin(np.arange(n) * 2 * np.pi / 7) + np.random.randn(n) * 5
    return pd.DataFrame({'date': dates, 'value': vals})


@pytest.fixture
def synthetic_forecast():
    fut_dates = pd.date_range('2025-05-01', periods=14, freq='D')
    vals = 200 + np.zeros(14)
    return pd.DataFrame({
        'date': fut_dates,
        'value': vals,
        'lower': vals * 0.9,
        'upper': vals * 1.1,
    })


class TestBuildTimeFeatures:
    def test_returns_six_columns(self, svc_extended):
        dates = pd.Series(pd.date_range('2025-01-01', periods=10, freq='D'))
        feats = svc_extended._build_time_features(dates)
        assert list(feats.columns) == ['doy_sin', 'doy_cos', 'dow_sin', 'dow_cos', 'month', 'day']

    def test_shape_matches_input(self, svc_extended):
        dates = pd.Series(pd.date_range('2025-03-01', periods=30, freq='D'))
        feats = svc_extended._build_time_features(dates)
        assert feats.shape == (30, 6)

    def test_cyclic_features_bounded(self, svc_extended):
        dates = pd.Series(pd.date_range('2025-01-01', periods=365, freq='D'))
        feats = svc_extended._build_time_features(dates)
        for col in ['doy_sin', 'doy_cos', 'dow_sin', 'dow_cos']:
            assert feats[col].between(-1.001, 1.001).all(), f"{col} debe estar en [-1, 1]"

    def test_no_nan(self, svc_extended):
        dates = pd.Series(pd.date_range('2025-06-01', periods=20, freq='D'))
        assert not svc_extended._build_time_features(dates).isna().any().any()


class TestApplyConformalCalibration:
    def test_output_has_required_columns(self, svc_extended, synthetic_historical, synthetic_forecast):
        result = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        for col in ('lower', 'upper', 'confidence'):
            assert col in result.columns

    def test_confidence_field_matches_target(self, svc_extended, synthetic_historical, synthetic_forecast):
        result = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        assert (result['confidence'] == 0.90).all()

    def test_intervals_are_symmetric(self, svc_extended, synthetic_historical, synthetic_forecast):
        """ICP produce intervalos simétricos: upper - value == value - lower."""
        result = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        half_above = (result['upper'] - result['value']).round(6)
        half_below = (result['value'] - result['lower']).round(6)
        pd.testing.assert_series_equal(half_above, half_below, check_names=False)

    def test_intervals_positive_width(self, svc_extended, synthetic_historical, synthetic_forecast):
        result = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        assert (result['upper'] > result['lower']).all()

    def test_q_is_finite_and_positive(self, svc_extended, synthetic_historical, synthetic_forecast):
        result = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        q = (result['upper'] - result['value']).iloc[0]
        assert np.isfinite(q) and q > 0

    def test_insufficient_data_returns_unchanged(self, svc_extended, synthetic_forecast):
        tiny_hist = pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=20, freq='D'),
            'value': np.ones(20) * 100,
        })
        result = svc_extended._apply_conformal_calibration(
            tiny_hist, synthetic_forecast, confidence_level=0.90, cal_days=30
        )
        pd.testing.assert_frame_equal(result, synthetic_forecast)

    def test_tighter_intervals_at_80pct_vs_95pct(self, svc_extended, synthetic_historical, synthetic_forecast):
        r80 = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.80, cal_days=30
        )
        r95 = svc_extended._apply_conformal_calibration(
            synthetic_historical, synthetic_forecast, confidence_level=0.95, cal_days=30
        )
        w80 = (r80['upper'] - r80['lower']).mean()
        w95 = (r95['upper'] - r95['lower']).mean()
        assert w80 < w95, f"Intervalo 80% ({w80:.2f}) debe ser más estrecho que 95% ({w95:.2f})"


class TestSchemaFromDataframe:
    def test_lowercase_columns_handled(self):
        from api.v1.schemas.predictions import PredictionResponse
        df = pd.DataFrame({
            'date': pd.date_range('2026-03-01', periods=5, freq='D'),
            'value': [100.0, 102.0, 98.0, 105.0, 101.0],
            'lower': [90.0, 92.0, 88.0, 95.0, 91.0],
            'upper': [110.0, 112.0, 108.0, 115.0, 111.0],
        })
        resp = PredictionResponse.from_dataframe(
            df=df, metric_id='TEST', entity='Sistema',
            model_type='prophet', horizon_days=5, confidence_level=0.90
        )
        assert resp.data[0].lower == 90.0
        assert resp.data[0].upper == 110.0

    def test_all_points_present(self):
        from api.v1.schemas.predictions import PredictionResponse
        df = pd.DataFrame({
            'date': pd.date_range('2026-03-01', periods=7, freq='D'),
            'value': np.linspace(100, 110, 7),
            'lower': np.linspace(90, 100, 7),
            'upper': np.linspace(110, 120, 7),
        })
        resp = PredictionResponse.from_dataframe(
            df=df, metric_id='X', entity='Y', model_type='ensemble', horizon_days=7
        )
        assert len(resp.data) == 7


def test_predictions_count():
    service = PredictionsService()
    total = service.count_predictions()
    assert total >= 0


def test_predictions_latest_date():
    service = PredictionsService()
    latest = service.get_latest_prediction_date()
    # Puede ser None si no hay predicciones, o date si hay
    from datetime import date as date_type
    assert latest is None or isinstance(latest, (str, date_type))


# ── Tests OE4: Predicciones largo plazo (365 días) ──────────────────────────

def test_long_term_predictions_classified_experimental():
    """Predicciones >90d deben clasificarse como EXPERIMENTAL y devolver ≤365 filas."""
    svc = PredictionsServiceExtended()
    df = svc.generate_long_term_predictions('GENE_TOTAL', horizonte_dias=365)

    assert isinstance(df, pd.DataFrame), "Debe retornar un DataFrame"
    assert len(df) > 0, "Debe haber al menos una predicción"
    assert len(df) <= 365, "No puede exceder 365 filas"
    assert 'clasificacion_confianza' in df.columns, "Debe incluir clasificacion_confianza"
    assert df['clasificacion_confianza'].iloc[0] == 'EXPERIMENTAL', (
        "Horizonte 365d debe clasificarse como EXPERIMENTAL"
    )
    assert df['horizonte_dias'].iloc[0] == 365, "horizonte_dias debe ser 365"


def test_predictions_have_confidence_intervals():
    """Las predicciones deben incluir intervalos de confianza válidos."""
    svc = PredictionsServiceExtended()
    df = svc.generate_long_term_predictions('PRECIO_BOLSA', horizonte_dias=180)

    assert 'intervalo_inferior' in df.columns, "Debe incluir intervalo_inferior"
    assert 'intervalo_superior' in df.columns, "Debe incluir intervalo_superior"
    assert (df['intervalo_superior'] >= df['intervalo_inferior']).all(), (
        "intervalo_superior debe ser >= intervalo_inferior en todas las filas"
    )


def test_short_term_predictions_classified_confiable():
    """Predicciones ≤30d deben clasificarse como CONFIABLE."""
    svc = PredictionsServiceExtended()
    df = svc.generate_long_term_predictions('DEMANDA', horizonte_dias=30)

    assert df['clasificacion_confianza'].iloc[0] == 'CONFIABLE'
    assert df['confianza'].iloc[0] > 0.90, "confianza numérica debe ser alta para corto plazo"


def test_medium_term_predictions_classified_moderada():
    """Predicciones 31–90d deben clasificarse como MODERADA."""
    svc = PredictionsServiceExtended()
    df = svc.generate_long_term_predictions('EMBALSES', horizonte_dias=90)

    assert df['clasificacion_confianza'].iloc[0] == 'MODERADA'


def test_long_term_confianza_is_numeric():
    """La columna 'confianza' persisted en BD debe ser numérica, no string."""
    svc = PredictionsServiceExtended()
    df = svc.generate_long_term_predictions('GENE_TOTAL', horizonte_dias=365)

    assert 'confianza' in df.columns, "Debe incluir columna numérica 'confianza'"
    assert pd.to_numeric(df['confianza'], errors='coerce').notna().all(), (
        "'confianza' debe ser numérica (compatible con columna NUMERIC de BD)"
    )
