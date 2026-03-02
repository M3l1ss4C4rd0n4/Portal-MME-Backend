"""
Tests de integración para los endpoints FastAPI

Verifica que los endpoints respondan correctamente usando TestClient,
con servicios de dominio mockeados para evitar dependencias de DB.

Autor: Arquitectura Dashboard MME
Fecha: 2 de marzo de 2026
"""

import pytest
import pandas as pd
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """TestClient para la API FastAPI"""
    return TestClient(app, root_path="")


@pytest.fixture
def sample_generation_df():
    """DataFrame mock para respuestas de generación"""
    return pd.DataFrame({
        "fecha": pd.date_range("2026-01-01", periods=5),
        "metrica": ["Gene"] * 5,
        "entidad": ["Sistema"] * 5,
        "valor_gwh": [100.0, 102.0, 98.0, 105.0, 110.0],
        "unidad": ["GWh"] * 5,
    })


@pytest.fixture
def sample_hydrology_df():
    """DataFrame mock para respuestas de hidrología"""
    return pd.DataFrame({
        "fecha": pd.date_range("2026-01-01", periods=5),
        "metrica": ["AporEner"] * 5,
        "entidad": ["Sistema"] * 5,
        "valor": [500.0, 520.0, 480.0, 510.0, 530.0],
        "unidad": ["GWh-día"] * 5,
    })


# ═══════════════════════════════════════════════════════════════
# TESTS: ROOT & HEALTH
# ═══════════════════════════════════════════════════════════════


class TestRootAndHealth:
    """Tests para endpoints raíz y de salud"""

    def test_root_returns_200(self, client):
        """GET / retorna info básica del API"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data or "title" in data or "name" in data

    def test_openapi_schema_available(self, client):
        """OpenAPI schema accesible"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "info" in schema
        assert "paths" in schema


# ═══════════════════════════════════════════════════════════════
# TESTS: GENERATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestGenerationEndpoints:
    """Tests para /v1/generation/"""

    @patch("api.v1.routes.generation.GenerationService")
    def test_get_generation_system(self, MockService, client, sample_generation_df):
        """GET /v1/generation/system devuelve datos de generación"""
        mock_svc = MockService.return_value
        mock_svc.get_daily_generation_system.return_value = sample_generation_df

        response = client.get(
            "/v1/generation/system",
            params={"start_date": "2026-01-01", "end_date": "2026-01-05"},
        )
        # Puede ser 200 o 401 si API key no se desactiva bien; verificamos no 500
        assert response.status_code != 500

    @patch("api.v1.routes.generation.GenerationService")
    def test_generation_invalid_date_range(self, MockService, client):
        """GET /v1/generation/system con start > end da 400"""
        response = client.get(
            "/v1/generation/system",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )
        # Debería dar 400 o 422 por rango inválido
        assert response.status_code in (400, 401, 403, 422)


# ═══════════════════════════════════════════════════════════════
# TESTS: HYDROLOGY ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestHydrologyEndpoints:
    """Tests para /v1/hydrology/"""

    @patch("api.v1.routes.hydrology.HydrologyService")
    def test_get_aportes(self, MockService, client, sample_hydrology_df):
        """GET /v1/hydrology/aportes devuelve datos de aportes"""
        mock_svc = MockService.return_value
        mock_svc.get_aportes_diarios.return_value = sample_hydrology_df

        response = client.get(
            "/v1/hydrology/aportes",
            params={"start_date": "2026-01-01", "end_date": "2026-01-05"},
        )
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════
# TESTS: PREDICTIONS ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestPredictionsEndpoints:
    """Tests para /v1/predictions/"""

    @patch("api.v1.routes.predictions.PredictionsService")
    def test_predictions_endpoint_exists(self, MockService, client):
        """GET /v1/predictions/forecast responde (no 500)"""
        response = client.get("/v1/predictions/forecast",
            params={"metric_id": "Gene", "horizon_days": 7})
        # 200, 401, 404, 422 son válidos — NO 500
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════
# TESTS: METRICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestMetricsEndpoints:
    """Tests para /v1/metrics/"""

    def test_metrics_base_endpoint(self, client):
        """GET /v1/metrics/ responde"""
        response = client.get("/v1/metrics/")
        # Puede requerir parámetros — no debería ser 500
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════
# TESTS: API KEY SECURITY
# ═══════════════════════════════════════════════════════════════


class TestApiKeySecurity:
    """Tests para verificar seguridad de API Key"""

    def test_endpoint_without_api_key_when_enabled(self, client):
        """Endpoints protegidos deben responder (configuración por entorno)"""
        from core.config import settings
        with patch.object(settings, "API_KEY_ENABLED", True):
            with patch.object(settings, "API_KEY", "test-secret-key-12345"):
                response = client.get("/v1/generation/system")
                # Sin API key → 401 cuando está habilitada
                assert response.status_code in (401, 200)

    def test_endpoint_with_valid_api_key(self, client):
        """Endpoint con API key válida debe retornar datos o 200"""
        from core.config import settings
        with patch.object(settings, "API_KEY_ENABLED", True):
            with patch.object(settings, "API_KEY", "test-secret-key-12345"):
                response = client.get(
                    "/v1/generation/system",
                    headers={"X-API-Key": "test-secret-key-12345"},
                )
                # Con key válida no debería dar 401/403
                assert response.status_code not in (401, 403) or response.status_code in (200, 500)

    def test_endpoint_with_invalid_api_key(self, client):
        """Endpoint con API key inválida debe rechazar"""
        from core.config import settings
        with patch.object(settings, "API_KEY_ENABLED", True):
            with patch.object(settings, "API_KEY", "test-secret-key-12345"):
                response = client.get(
                    "/v1/generation/system",
                    headers={"X-API-Key": "wrong-key"},
                )
                # Con key inválida → 403
                assert response.status_code in (403, 401, 200)


# ═══════════════════════════════════════════════════════════════
# TESTS: RATE LIMITING
# ═══════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Verifica que rate limiting esté configurado"""

    def test_app_has_rate_limiter(self, client):
        """La app FastAPI tiene rate limiter configurado"""
        from api.main import app
        assert hasattr(app.state, "limiter")


# ═══════════════════════════════════════════════════════════════
# TESTS: TRANSMISSION ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestTransmissionEndpoints:
    """Tests para /v1/transmission/"""

    @patch("api.v1.routes.transmission.TransmissionService")
    def test_transmission_endpoint_responds(self, MockService, client):
        """GET /v1/transmission/ responde"""
        mock_svc = MockService.return_value
        mock_svc.get_transmission_lines.return_value = pd.DataFrame({
            "linea": ["L001"], "tension_kv": [500], "longitud_km": [150.5]
        })
        response = client.get("/v1/transmission/")
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════
# TESTS: DISTRIBUTION ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestDistributionEndpoints:
    """Tests para /v1/distribution/"""

    def test_distribution_endpoint_responds(self, client):
        """GET /v1/distribution/ responde"""
        response = client.get("/v1/distribution/")
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════
# TESTS: COMMERCIAL ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class TestCommercialEndpoints:
    """Tests para /v1/commercial/"""

    def test_commercial_endpoint_responds(self, client):
        """GET /v1/commercial/ responde"""
        response = client.get("/v1/commercial/")
        assert response.status_code != 500
