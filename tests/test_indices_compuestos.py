"""Tests unitarios para índices compuestos del informe ejecutivo."""
import pytest

from domain.services.orchestrator.handlers.informe_handler import InformeHandlerMixin


class _HandlerStub(InformeHandlerMixin):
    """Instancia mínima para probar métodos del mixin."""


@pytest.fixture
def handler():
    return _HandlerStub()


FICHAS_ESTADO_ACTUAL = [
    {
        "indicador": "Generación Total del Sistema",
        "valor": 231.72,
        "unidad": "GWh",
        "contexto": {"promedio_7_dias": 220.0},
    },
    {
        "indicador": "Precio de Bolsa Nacional",
        "valor": 582.82,
        "unidad": "COP/kWh",
        "contexto": {"promedio_7_dias": 520.0},
    },
    {
        "indicador": "Porcentaje de Embalses",
        "valor": 72.87,
        "unidad": "%",
        "contexto": {"promedio_30d": 70.0},
    },
]


def test_ficha_por_keyword_usa_indicador(handler):
    ficha = handler._ficha_por_keyword(FICHAS_ESTADO_ACTUAL, "precio")
    assert ficha is not None
    assert "Precio" in ficha["indicador"]


def test_baseline_precio_desde_promedio_7_dias(handler):
    precio = handler._ficha_por_keyword(FICHAS_ESTADO_ACTUAL, "precio")
    assert handler._baseline_precio_ficha(precio) == 520.0


def test_indices_ish_refleja_embalses(handler):
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, [])
    assert indices["ish"]["valor"] == pytest.approx(72.87, rel=0.01)
    assert indices["ish"]["nivel"] == "ADECUADO"


def test_indices_ipm_positivo_cuando_precio_sobre_promedio(handler):
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, [])
    # (582.82 - 520) / 520 * 100 ≈ 12.08
    assert indices["ipm"]["valor"] > 0
    assert indices["ipm"]["valor"] == pytest.approx(12.08, rel=0.05)


def test_indices_ipm_anomalia_precio_incrementa_score(handler):
    anomalias = [
        {
            "indicador": "Precio de Bolsa",
            "severidad": "alerta",
            "descripcion": "Precio elevado",
        }
    ]
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, anomalias)
    assert indices["ipm"]["valor"] >= 15


def test_normalizar_severidad_sin_acentos(handler):
    assert handler._normalizar_severidad("CRÍTICO") == "critico"
    assert handler._normalizar_severidad("alerta") == "alerta"


def test_indices_contabilizan_anomalias_criticas(handler):
    anomalias = [
        {"indicador": "Embalses", "severidad": "crítico"},
        {"indicador": "Generación", "severidad": "alerta"},
    ]
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, anomalias)
    assert indices["componentes"]["anomalias_criticas"] == 1
    assert indices["componentes"]["anomalias_alertas"] == 1


def test_indices_ish_trazabilidad_embalse(handler):
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, [])
    comp = indices["componentes"]
    assert comp["ish_embalse_pct"] == pytest.approx(72.87, rel=0.01)
    assert comp["ish_fuente"] == "ficha_embalse"


def test_indices_ish_fallback_sin_ficha_embalse(handler):
    fichas_sin_emb = [f for f in FICHAS_ESTADO_ACTUAL if "embalse" not in f["indicador"].lower()]
    indices = handler._build_indices_compuestos(fichas_sin_emb, {}, [])
    comp = indices["componentes"]
    assert indices["ish"]["valor"] == 50
    assert comp["ish_fuente"] == "fallback_50"
    assert comp["ish_embalse_pct"] is None
