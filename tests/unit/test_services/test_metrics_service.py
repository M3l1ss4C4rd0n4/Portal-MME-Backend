"""Tests básicos para MetricsService"""

from domain.services.metrics_service import MetricsService


def test_metrics_total_records():
    service = MetricsService()
    total = service.get_total_records()
    assert total > 0


def test_metrics_latest_date():
    service = MetricsService()
    latest = service.get_latest_date()
    assert latest is not None
