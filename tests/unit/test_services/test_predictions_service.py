"""Tests básicos para PredictionsService"""

import pytest
import pandas as pd
from domain.services.predictions_service import PredictionsService
from domain.services.predictions_service_extended import PredictionsService as PredictionsServiceExtended


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
