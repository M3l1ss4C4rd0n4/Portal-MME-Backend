"""
Tests: InvestmentService.calculate_financial_analysis()
OE7 — TIR, VAN, Payback, CO2, Empleos
"""
import pytest
from domain.services.investment_service import InvestmentService


@pytest.fixture
def svc():
    return InvestmentService()


def test_solar_100mw_capex_y_empleos(svc):
    r = svc.calculate_financial_analysis("solar_fv", 100)
    assert r["capex_total_usd"] == 85_000_000, "100MW × 850K USD/MW"
    assert r["empleos_directos"] == 520, "5.2 empleos/MW × 100"
    assert r["co2_evitado_ton_anual"] > 0
    assert r["payback_años"] < 25


def test_solar_100mw_tir_positivo(svc):
    r = svc.calculate_financial_analysis("solar_fv", 100)
    assert r["tir_pct"] > 0, "TIR debe ser positivo con parámetros base"


def test_eolica_300mw_viabilidad(svc):
    r = svc.calculate_financial_analysis("eolica", 300)
    # Eólica La Guajira factor capacidad 45% → muy rentable
    assert r["tir_pct"] > 8, "TIR mínimo rentable en Colombia (>8%)"
    assert r["co2_evitado_ton_anual"] > 100_000


def test_all_tecnologias_tienen_claves_requeridas(svc):
    required = [
        "capex_total_usd", "tir_pct", "payback_años",
        "co2_evitado_ton_anual", "empleos_directos", "van_usd",
        "empleos_indirectos", "empleos_total", "co2_evitado_total",
        "ingresos_carbono_usd_anual", "generacion_anual_mwh",
    ]
    for tech in ["solar_fv", "eolica", "hidro_pequena"]:
        r = svc.calculate_financial_analysis(tech, 50)
        for key in required:
            assert key in r, f"{key} missing for {tech}"


def test_empleos_indirectos_factor_2_5(svc):
    r = svc.calculate_financial_analysis("solar_fv", 200)
    assert r["empleos_indirectos"] == int(r["empleos_directos"] * 2.5)
    assert r["empleos_total"] == int(r["empleos_directos"] * 3.5)


def test_co2_escala_con_mw(svc):
    r100 = svc.calculate_financial_analysis("eolica", 100)
    r200 = svc.calculate_financial_analysis("eolica", 200)
    # CO2 evitado debe escalar linealmente con MW
    assert abs(r200["co2_evitado_ton_anual"] / r100["co2_evitado_ton_anual"] - 2.0) < 0.01


def test_van_crece_con_mayor_vida_util(svc):
    r25 = svc.calculate_financial_analysis("solar_fv", 100, vida_util_años=25)
    r30 = svc.calculate_financial_analysis("solar_fv", 100, vida_util_años=30)
    assert r30["van_usd"] > r25["van_usd"]


def test_get_benchmarks_retorna_3_tecnologias(svc):
    bm = svc.get_benchmarks()
    assert len(bm) == 3
    nombres = [b["tecnologia"] for b in bm]
    assert "Solar Fotovoltaica" in nombres
    assert "Eólica" in nombres
