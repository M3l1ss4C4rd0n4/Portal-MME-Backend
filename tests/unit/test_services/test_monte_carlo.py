"""
Tests para run_monte_carlo() en SimulationService.
OE6 — Monte Carlo sobre escenarios de simulación.
"""
import pytest
from domain.services.simulation_service import SimulationService


@pytest.fixture(scope="module")
def svc():
    return SimulationService()


def test_monte_carlo_returns_percentiles(svc):
    result = svc.run_monte_carlo("expansion_renovables", n_simulations=100)
    assert "cu_p10" in result
    assert "cu_p50" in result
    assert "cu_p90" in result
    assert result["cu_p10"] <= result["cu_p50"] <= result["cu_p90"]
    assert result["n_simulations"] == 100
    assert len(result["histogram_data"]) == 100


def test_monte_carlo_all_escenarios(svc):
    """Todos los escenarios predefinidos deben correr sin error."""
    for escenario in [
        "sequia_moderada",
        "sequia_severa",
        "reforma_perdidas_reduccion",
        "expansion_renovables",
    ]:
        result = svc.run_monte_carlo(escenario, n_simulations=50)
        assert result["escenario"] == escenario
        assert result["cu_p10"] <= result["cu_p50"] <= result["cu_p90"]
        assert result["cu_base"] > 0


def test_monte_carlo_histogram_size(svc):
    for n in [100, 500]:
        result = svc.run_monte_carlo("expansion_renovables", n_simulations=n)
        assert len(result["histogram_data"]) == n


def test_monte_carlo_unknown_escenario(svc):
    """Escenario no conocido debe usar defaults sin lanzar excepción."""
    result = svc.run_monte_carlo("escenario_inexistente", n_simulations=50)
    assert result["cu_p50"] > 0
    assert len(result["histogram_data"]) == 50


def test_monte_carlo_reduccion_direccion(svc):
    """expansion_renovables debe reducir el CU (reduccion_cu_p50 > 0)."""
    result = svc.run_monte_carlo("expansion_renovables", n_simulations=200)
    # P50 debe ser menor al base → reducción positiva
    assert result["reduccion_cu_p50"] > 0, (
        f"Se esperaba reducción, got {result['reduccion_cu_p50']:.2f}%"
    )


def test_monte_carlo_sequia_aumenta_cu(svc):
    """Escenario sequía debe incrementar el CU (reduccion_cu_p50 < 0)."""
    result = svc.run_monte_carlo("sequia_severa", n_simulations=200)
    assert result["reduccion_cu_p50"] < 0, (
        f"Sequía debería subir CU, got {result['reduccion_cu_p50']:.2f}%"
    )
