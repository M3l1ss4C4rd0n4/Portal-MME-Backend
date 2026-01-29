"""Tests básicos para PredictionsService"""

from domain.services.predictions_service import PredictionsService


def test_predictions_count():
    service = PredictionsService()
    total = service.count_predictions()
    assert total >= 0


def test_predictions_latest_date():
    service = PredictionsService()
    latest = service.get_latest_prediction_date()
    # Puede ser None si no hay predicciones
    assert latest is None or isinstance(latest, str)
