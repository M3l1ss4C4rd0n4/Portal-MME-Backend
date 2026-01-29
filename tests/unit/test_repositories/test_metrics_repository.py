"""Tests básicos para MetricsRepository"""

from infrastructure.database.repositories.metrics_repository import MetricsRepository


def test_metrics_repo_total_records():
    repo = MetricsRepository()
    total = repo.get_total_records()
    assert total > 0


def test_metrics_repo_latest_date():
    repo = MetricsRepository()
    latest = repo.get_latest_date()
    assert latest is not None
