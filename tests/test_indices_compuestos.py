"""Tests unitarios para índices compuestos del informe ejecutivo.

2026-08-25 (a pedido del usuario — "no quiero inventar datos que no vengan
directamente de la normativa oficial de la CREG"): ISH/IPM ya no se calculan
con una fórmula autocontenida (% crudo de embalse, precio vs. promedio 7
días propio) — ahora consultan la senda de referencia real y los precios de
escasez reales vía core/umbrales_oficiales.py, que a su vez consultan la
base de datos (con una tabla de respaldo estática si la BD no responde).
Para que estos tests sigan siendo deterministas (no dependan de qué día se
corran ni de qué haya hoy en la BD), se mockean esas 2 consultas con valores
fijos y conocidos — mismo principio que scripts/verificar_sincronia_
umbrales.py ya usa para comparar Python↔TypeScript sin depender de la BD.
"""
from unittest.mock import patch

import pandas as pd
import pytest

from domain.services.orchestrator.handlers.informe_handler import InformeHandlerMixin


class _HandlerStub(InformeHandlerMixin):
    """Instancia mínima para probar métodos del mixin."""


@pytest.fixture
def handler():
    return _HandlerStub()


# Senda/precios de escasez fijos y conocidos para que ISH/IPM sean
# deterministas en los tests — NO son los valores reales vigentes, son
# solo un fixture de prueba.
SENDA_FIJA_TEST = 70.0
PEI_FIJO_TEST, PE_FIJO_TEST, PES_FIJO_TEST = 300.0, 550.0, 800.0


@pytest.fixture(autouse=True)
def _mockear_fuentes_creg_para_tests(monkeypatch):
    """Aísla los tests de la BD real: fija la senda de referencia y los
    precios de escasez a valores conocidos, y evita que las consultas de
    HSIN/PBP del Estatuto (que si no encuentran datos suficientes dejan la
    condición oficial como 'SIN DATO OFICIAL', un resultado válido y ya
    cubierto por otro test) dependan de qué haya hoy en la BD real."""
    monkeypatch.setattr(
        "core.umbrales_oficiales.obtener_senda_referencia",
        lambda fecha=None: SENDA_FIJA_TEST,
    )
    monkeypatch.setattr(
        "domain.services.orchestrator.handlers.informe_handler.obtener_precios_escasez_vigentes",
        lambda fecha=None: {"pei": PEI_FIJO_TEST, "pe": PE_FIJO_TEST, "pes": PES_FIJO_TEST, "origen": "test"},
    )
    with patch("infrastructure.database.manager.db_manager.query_df", return_value=pd.DataFrame()), \
         patch(
             "infrastructure.database.repositories.metrics_repository.MetricsRepository.get_metric_data",
             return_value=pd.DataFrame(),
         ):
        yield


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
    # Con senda de referencia fija de prueba = 70.0 (ver fixture), un
    # embalse al 72.87% queda 'SOBRE SENDA' (Índice NE oficial) — la
    # etiqueta que se muestra es la palabra exacta de clasificar_visual_
    # embalse(), no una reclasificación propia del número.
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, [])
    assert indices["ish"]["nivel"] == "SOBRE SENDA"
    # El número interno (75 + hasta 15 por margen sobre la senda) sigue
    # existiendo como insumo de IES, pero ya no es lo que se muestra como
    # estado principal — solo se verifica que quede dentro de la banda.
    assert 75 <= indices["ish"]["valor"] <= 90


def test_indices_ipm_positivo_cuando_precio_sobre_promedio(handler):
    # Con PEI/PE/PES fijos de prueba (300/550/800, ver fixture), un precio
    # de 582.82 supera PE y queda en 'ALTA PRESIÓN' (Res. CREG 101 066/2024).
    indices = handler._build_indices_compuestos(FICHAS_ESTADO_ACTUAL, {}, [])
    assert indices["ipm"]["nivel"] == "ALTA PRESIÓN"
    assert indices["ipm"]["valor"] > 0
    assert 50 <= indices["ipm"]["valor"] <= 75


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
    # 'indice_ne_oficial': el ISH ya no se toma directo de la ficha del
    # orquestador, se reclasifica contra la senda de referencia oficial.
    assert comp["ish_fuente"] == "indice_ne_oficial"


def test_indices_ish_fallback_sin_ficha_embalse(handler):
    fichas_sin_emb = [f for f in FICHAS_ESTADO_ACTUAL if "embalse" not in f["indicador"].lower()]
    indices = handler._build_indices_compuestos(fichas_sin_emb, {}, [])
    comp = indices["componentes"]
    assert indices["ish"]["valor"] == 50
    assert comp["ish_fuente"] == "fallback_50"
    assert comp["ish_embalse_pct"] is None
