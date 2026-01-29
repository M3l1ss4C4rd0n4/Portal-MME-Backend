"""Tests básicos para página piloto de métricas"""

from presentation.pages import metricas_piloto


def test_metricas_piloto_layout_exists():
    assert metricas_piloto.layout is not None


def test_metricas_piloto_summary_keys():
    summary = metricas_piloto._get_summary()
    assert "latest_metrics_date" in summary
    assert "total_metrics" in summary
    assert "predictions_count" in summary
    assert "latest_prediction_date" in summary
