"""Tests básicos para PredictionsRepository"""

from infrastructure.database.repositories.predictions_repository import PredictionsRepository


def test_predictions_repo_count():
    repo = PredictionsRepository()
    total = repo.count_predictions()
    assert total >= 0


def test_predictions_repo_latest_date():
    repo = PredictionsRepository()
    latest = repo.get_latest_prediction_date()
    assert latest is None or isinstance(latest, str)
