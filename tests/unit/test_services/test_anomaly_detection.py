"""
Tests para detect_anomalies_isolation_forest() en LossesNTService.
OE3 — Isolation Forest sobre pérdidas no técnicas.
"""
import pytest
from datetime import date


def test_isolation_forest_basic():
    from domain.services.losses_nt_service import LossesNTService
    svc = LossesNTService()
    df = svc.detect_anomalies_isolation_forest(
        date(2020, 1, 1), date(2025, 12, 31)
    )
    if df.empty:
        pytest.skip("Sin datos suficientes en losses_detailed")

    assert "anomaly" in df.columns
    assert "severidad" in df.columns
    assert "anomaly_score" in df.columns
    assert "pnt_pct" in df.columns
    assert set(df["severidad"].unique()).issubset({"NORMAL", "ALERTA", "CRITICO"})


def test_isolation_forest_anomaly_rate():
    from domain.services.losses_nt_service import LossesNTService
    svc = LossesNTService()
    df = svc.detect_anomalies_isolation_forest(
        date(2020, 1, 1), date(2025, 12, 31), contamination=0.1
    )
    if df.empty:
        pytest.skip("Sin datos suficientes en losses_detailed")

    anomaly_rate = (df["anomaly"] == -1).mean()
    # Con contamination=0.10, tasa debe estar en 5%-25%
    assert 0.05 < anomaly_rate < 0.25, f"Tasa anómala inesperada: {anomaly_rate:.2%}"


def test_isolation_forest_insufficient_data():
    from domain.services.losses_nt_service import LossesNTService
    svc = LossesNTService()
    # Rango de 3 días — insuficiente para IF
    df = svc.detect_anomalies_isolation_forest(
        date(2024, 1, 1), date(2024, 1, 3)
    )
    assert df.empty, "Debe retornar DataFrame vacío con datos insuficientes"


def test_get_series_pnt():
    from domain.services.losses_nt_service import LossesNTService
    svc = LossesNTService()
    df = svc._get_series_pnt(date(2023, 1, 1), date(2023, 12, 31))
    if df.empty:
        pytest.skip("Sin datos en 2023")
    assert "fecha" in df.columns
    assert "pnt_pct" in df.columns
    # No debe haber valores extremadamente negativos
    assert (df["pnt_pct"] > -5).all()
