"""Tests unitarios — cálculos puros de BalanceOfertaDemandaService y
validación de input de api/v1/routes/balance_oferta_demanda.py.

Cubren la lógica de margen de reserva y de la simulación contrafactual sin
tocar la base de datos (mismo enfoque que test_indices_compuestos.py:
aislar la lógica de negocio de la capa de datos), más las rutas de
validación de input (_validar_rango, filtros tipo/estado inválidos,
max_length de proyecto_ids) que son la primera línea de defensa de estos
endpoints — señaladas como cobertura faltante en la revisión de seguridad
de la Fase 45.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.v1.routes.balance_oferta_demanda import _validar_rango
from domain.services.balance_oferta_demanda_service import BalanceOfertaDemandaService

AUTH_HEADERS = {"X-API-Key": "test-secret-key-balance"}


@pytest.fixture
def client():
    return TestClient(app, root_path="")


@pytest.fixture
def api_key_enabled():
    """Mismo patrón que TestApiKeySecurity en test_api_endpoints.py: parchea
    settings en vez de mutarlo directamente, para no filtrar estado entre tests."""
    from core.config import settings
    with patch.object(settings, "API_KEY_ENABLED", True), \
         patch.object(settings, "API_KEY", AUTH_HEADERS["X-API-Key"]):
        yield


class TestCalcularMargen:
    def test_margen_positivo_oferta_mayor_a_demanda(self):
        # 20000 MW de oferta vs. una demanda de 216 GWh/día ≈ 9000 MW promedio
        resultado = BalanceOfertaDemandaService.calcular_margen(20000.0, 216.0)
        assert resultado["demandaMwPromedio"] == 9000.0
        assert resultado["margenMw"] == 11000.0
        assert resultado["margenPct"] == pytest.approx(122.22, abs=0.01)

    def test_margen_negativo_deficit(self):
        # Oferta insuficiente frente a la demanda promedio
        resultado = BalanceOfertaDemandaService.calcular_margen(5000.0, 216.0)
        assert resultado["margenMw"] == -4000.0
        assert resultado["margenPct"] < 0

    def test_oferta_none_retorna_todo_none(self):
        resultado = BalanceOfertaDemandaService.calcular_margen(None, 216.0)
        assert resultado == {"demandaMwPromedio": None, "margenMw": None, "margenPct": None}

    def test_demanda_none_retorna_todo_none(self):
        resultado = BalanceOfertaDemandaService.calcular_margen(20000.0, None)
        assert resultado == {"demandaMwPromedio": None, "margenMw": None, "margenPct": None}

    def test_demanda_cero_no_divide_por_cero(self):
        resultado = BalanceOfertaDemandaService.calcular_margen(20000.0, 0.0)
        assert resultado["margenMw"] is None
        assert resultado["margenPct"] is None


class TestDemandaGwhAMwPromedio:
    def test_conversion_24_horas(self):
        # 240 GWh/día = 240_000 MWh/día / 24h = 10_000 MW promedio
        assert BalanceOfertaDemandaService.demanda_gwh_a_mw_promedio(240.0) == 10_000.0


class TestCalcularMargenRegulatorio:
    def test_margen_positivo_enficc_mayor_a_oef(self):
        # Caso real verificado: crisis El Niño 2015-11-15 (ENFICC=209.59, OEF=175.61)
        resultado = BalanceOfertaDemandaService.calcular_margen_regulatorio(209.59, 175.61)
        assert resultado["margenRegulatorioGwh"] == pytest.approx(33.98, abs=0.01)
        assert resultado["margenRegulatorioPct"] == pytest.approx(19.35, abs=0.05)

    def test_margen_negativo_deficit_real(self):
        # Caso real verificado: 2026-09-15 (ENFICC=245.54, OEF=266.03) — déficit
        resultado = BalanceOfertaDemandaService.calcular_margen_regulatorio(245.54, 266.03)
        assert resultado["margenRegulatorioPct"] == pytest.approx(-7.70, abs=0.05)
        assert resultado["margenRegulatorioGwh"] < 0

    def test_enficc_none_retorna_todo_none(self):
        resultado = BalanceOfertaDemandaService.calcular_margen_regulatorio(None, 200.0)
        assert resultado == {"margenRegulatorioGwh": None, "margenRegulatorioPct": None}

    def test_oef_none_retorna_todo_none(self):
        resultado = BalanceOfertaDemandaService.calcular_margen_regulatorio(200.0, None)
        assert resultado == {"margenRegulatorioGwh": None, "margenRegulatorioPct": None}

    def test_oef_cero_no_divide_por_cero(self):
        resultado = BalanceOfertaDemandaService.calcular_margen_regulatorio(200.0, 0.0)
        assert resultado == {"margenRegulatorioGwh": None, "margenRegulatorioPct": None}


class TestMwAEnergiaFirmeGwhDia:
    def test_conversion_24_horas(self):
        # 10_000 MW operando 24h = 240_000 MWh/día = 240 GWh/día — inverso
        # exacto de demanda_gwh_a_mw_promedio(240.0) == 10_000.0
        assert BalanceOfertaDemandaService.mw_a_energia_firme_gwh_dia(10_000.0) == 240.0

    def test_cero_mw_es_cero_energia(self):
        assert BalanceOfertaDemandaService.mw_a_energia_firme_gwh_dia(0.0) == 0.0

    def test_es_inverso_de_demanda_gwh_a_mw_promedio(self):
        gwh_dia = 216.0
        mw = BalanceOfertaDemandaService.demanda_gwh_a_mw_promedio(gwh_dia)
        assert BalanceOfertaDemandaService.mw_a_energia_firme_gwh_dia(mw) == pytest.approx(gwh_dia)


class TestCalcularMwExtraContrafactual:
    FECHA = pd.Timestamp("2024-06-01")

    def test_proyecto_retrasado_suma_capacidad(self):
        proyectos = [{
            "fecha_entrada_planeada_original": pd.Timestamp("2023-01-01"),
            "fecha_entrada_real": None,
            "capacidad_mw": 300.0,
        }]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 300.0

    def test_proyecto_aun_no_planeado_no_suma(self):
        proyectos = [{
            "fecha_entrada_planeada_original": pd.Timestamp("2025-01-01"),  # después de FECHA
            "fecha_entrada_real": None,
            "capacidad_mw": 300.0,
        }]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 0.0

    def test_proyecto_que_ya_entro_de_verdad_no_suma(self):
        # Si en la realidad ya entró en operación antes de la fecha evaluada,
        # el contrafactual no debe duplicar esa capacidad (ya está en la oferta real).
        proyectos = [{
            "fecha_entrada_planeada_original": pd.Timestamp("2023-01-01"),
            "fecha_entrada_real": pd.Timestamp("2024-01-01"),  # antes de FECHA
            "capacidad_mw": 300.0,
        }]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 0.0

    def test_proyecto_que_entrara_despues_de_la_fecha_evaluada_si_suma(self):
        proyectos = [{
            "fecha_entrada_planeada_original": pd.Timestamp("2023-01-01"),
            "fecha_entrada_real": pd.Timestamp("2025-01-01"),  # después de FECHA
            "capacidad_mw": 300.0,
        }]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 300.0

    def test_proyecto_sin_capacidad_o_sin_fecha_se_ignora(self):
        proyectos = [
            {"fecha_entrada_planeada_original": None, "fecha_entrada_real": None, "capacidad_mw": 300.0},
            {"fecha_entrada_planeada_original": pd.Timestamp("2023-01-01"), "fecha_entrada_real": None, "capacidad_mw": None},
        ]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 0.0

    def test_suma_varios_proyectos_retrasados(self):
        proyectos = [
            {"fecha_entrada_planeada_original": pd.Timestamp("2023-01-01"), "fecha_entrada_real": None, "capacidad_mw": 300.0},
            {"fecha_entrada_planeada_original": pd.Timestamp("2023-06-01"), "fecha_entrada_real": None, "capacidad_mw": 150.0},
        ]
        assert BalanceOfertaDemandaService.calcular_mw_extra_contrafactual(self.FECHA, proyectos) == 450.0


class TestValidarRango:
    """_validar_rango es la primera línea de defensa de 4 de los 5 endpoints."""

    def test_rango_invertido_lanza_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validar_rango(date(2024, 6, 1), date(2024, 1, 1))
        assert exc_info.value.status_code == 400

    def test_rango_mayor_a_maximo_lanza_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _validar_rango(date(1970, 1, 1), date(2024, 1, 1))  # > 10 000 días
        assert exc_info.value.status_code == 400

    def test_rango_valido_no_lanza(self):
        inicio, fin = _validar_rango(date(2024, 1, 1), date(2024, 6, 1))
        assert inicio == date(2024, 1, 1)
        assert fin == date(2024, 6, 1)

    def test_sin_fechas_usa_defaults(self):
        inicio, fin = _validar_rango(None, None)
        assert fin == date.today()
        assert inicio < fin

    def test_rango_justo_en_el_limite_no_lanza(self):
        inicio = date(2000, 1, 1)
        fin = inicio + timedelta(days=10_000)
        # No debe lanzar — el límite es inclusive
        _validar_rango(inicio, fin)


class TestValidacionInputRutas:
    """Validación de query params / body en las rutas HTTP (TestClient)."""

    def test_proyectos_upme_tipo_invalido_devuelve_400(self, client, api_key_enabled):
        r = client.get(
            "/v1/balance-oferta-demanda/proyectos-upme",
            params={"tipo": "NO_EXISTE"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400

    def test_proyectos_upme_estado_invalido_devuelve_400(self, client, api_key_enabled):
        r = client.get(
            "/v1/balance-oferta-demanda/proyectos-upme",
            params={"estado": "NO_EXISTE"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400

    def test_historico_rango_invertido_devuelve_400(self, client, api_key_enabled):
        r = client.get(
            "/v1/balance-oferta-demanda/historico",
            params={"fecha_inicio": "2024-06-01", "fecha_fin": "2024-01-01"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400

    def test_simular_contrafactual_lista_ids_demasiado_larga_es_rechazada(self, client, api_key_enabled):
        # El manejador de errores global (core/error_handlers.py) convierte
        # RequestValidationError de Pydantic en 400, no en el 422 por defecto
        # de FastAPI — mismo comportamiento que el resto del proyecto.
        r = client.post(
            "/v1/balance-oferta-demanda/simular-contrafactual",
            json={"proyecto_ids": list(range(201))},  # excede max_length=200
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400
        assert "proyecto_ids" in r.text

    def test_simular_contrafactual_sin_api_key_devuelve_401(self, client, api_key_enabled):
        r = client.post(
            "/v1/balance-oferta-demanda/simular-contrafactual",
            json={},
        )
        assert r.status_code == 401
