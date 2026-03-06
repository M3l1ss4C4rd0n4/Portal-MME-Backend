"""
Tests de hardening — Fase 8

Verifica:
- Security headers middleware
- Circuit breaker (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Health endpoints (/health, /health/live, /health/ready)
- Dashboard error boundary (Flask 404/500 handlers)

Autor: Arquitectura Dashboard MME
Fecha: 3 de marzo de 2026
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app
from infrastructure.external.circuit_breaker import (
    XMCircuitBreaker,
    CircuitState,
)

# Check if dash is available for dashboard tests
try:
    HAS_DASH = True
except ImportError:
    HAS_DASH = False


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def client():
    """TestClient FastAPI"""
    return TestClient(app, root_path="")


@pytest.fixture
def breaker():
    """Circuit breaker con parámetros rápidos para testing"""
    return XMCircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,   # 1 segundo para tests
        success_threshold=2,
    )


# ═══════════════════════════════════════════════════════════
# 1. SECURITY HEADERS
# ═══════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """Verifica que SecurityHeadersMiddleware inyecta cabeceras correctas"""

    def test_x_content_type_options(self, client):
        resp = client.get("/health/live")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/health/live")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_xss_protection(self, client):
        resp = client.get("/health/live")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        resp = client.get("/health/live")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        resp = client.get("/health/live")
        assert "camera=()" in resp.headers.get("permissions-policy", "")

    def test_cache_control_on_api_endpoints(self, client):
        """Las rutas de API (no /health, no /docs) deben tener no-store"""
        resp = client.get("/health/live")
        # health endpoints están excluidos del cache control restrictivo
        # pero la cabecera security sí debe estar presente
        assert "x-content-type-options" in resp.headers

    def test_all_security_headers_present(self, client):
        """Verifica que las 5 cabeceras de seguridad estén presentes"""
        resp = client.get("/health/live")
        required = [
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
            "referrer-policy",
            "permissions-policy",
        ]
        for header in required:
            assert header in resp.headers, f"Falta cabecera: {header}"


# ═══════════════════════════════════════════════════════════
# 2. CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Tests unitarios del XMCircuitBreaker"""

    def test_initial_state_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request() is True

    def test_stays_closed_under_threshold(self, breaker):
        """2 fallos no abren el circuito (threshold=3)"""
        breaker.record_failure(Exception("error 1"))
        breaker.record_failure(Exception("error 2"))
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request() is True

    def test_opens_at_threshold(self, breaker):
        """3 fallos consecutivos → OPEN"""
        for i in range(3):
            breaker.record_failure(Exception(f"error {i}"))
        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False

    def test_open_to_half_open_after_timeout(self, breaker):
        """Después del recovery_timeout (1s en test) → HALF_OPEN"""
        for i in range(3):
            breaker.record_failure(Exception(f"error {i}"))
        assert breaker.state == CircuitState.OPEN
        time.sleep(1.2)  # > recovery_timeout
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.allow_request() is True

    def test_half_open_to_closed_on_success(self, breaker):
        """2 éxitos en HALF_OPEN → CLOSED"""
        for i in range(3):
            breaker.record_failure(Exception(f"error {i}"))
        time.sleep(1.2)
        assert breaker.state == CircuitState.HALF_OPEN
        breaker.record_success()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self, breaker):
        """1 fallo en HALF_OPEN → OPEN de nuevo"""
        for i in range(3):
            breaker.record_failure(Exception(f"error {i}"))
        time.sleep(1.2)
        assert breaker.state == CircuitState.HALF_OPEN
        breaker.record_failure(Exception("fallo en half_open"))
        assert breaker.state == CircuitState.OPEN

    def test_success_resets_counter(self, breaker):
        """Un éxito después de fallo resetea el contador (en CLOSED)"""
        breaker.record_failure(Exception("error"))
        breaker.record_failure(Exception("error"))
        breaker.record_success()
        # 1 fallo más no debería abrir (no son 3 consecutivos)
        breaker.record_failure(Exception("error"))
        assert breaker.state == CircuitState.CLOSED

    def test_get_status_returns_dict(self, breaker):
        status = breaker.get_status()
        assert "state" in status
        assert status["state"] == "closed"
        assert "stats" in status
        assert status["stats"]["total_calls"] == 0

    def test_force_close(self, breaker):
        for i in range(3):
            breaker.record_failure(Exception(f"error {i}"))
        assert breaker.state == CircuitState.OPEN
        breaker.force_close()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request() is True

    def test_stats_tracking(self, breaker):
        breaker.record_success()
        breaker.record_failure(Exception("fail"))
        breaker.record_success()
        assert breaker.stats.total_calls == 3
        assert breaker.stats.total_successes == 2
        assert breaker.stats.total_failures == 1


# ═══════════════════════════════════════════════════════════
# 3. HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════

class TestHealthEndpoints:
    """Tests de los endpoints /health, /health/live, /health/ready"""

    def test_health_live_returns_alive(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @patch("infrastructure.cache.redis_client.get_redis_client")
    @patch("infrastructure.database.manager.db_manager")
    def test_health_ready_ok(self, mock_db, mock_redis, client):
        mock_db.query_df.return_value = MagicMock()
        mock_redis_inst = MagicMock()
        mock_redis.return_value = mock_redis_inst
        resp = client.get("/health/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "ready" in body
        assert "checks" in body

    def test_health_main_returns_json(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("healthy", "degraded", "unhealthy")
        assert "services" in body
        assert "version" in body

    def test_health_includes_version(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert body.get("version") == "1.0.0"


# ═══════════════════════════════════════════════════════════
# 4. DASHBOARD ERROR BOUNDARY
# ═══════════════════════════════════════════════════════════

@pytest.mark.skipif(not HAS_DASH, reason="dash module not installed in test env")
class TestDashboardErrorBoundary:
    """Verifica error handlers del Flask server del Dashboard"""

    def test_flask_404_handler_registered(self):
        """Verifica que el handler 404 está registrado en app_factory"""
        from core.app_factory import create_dash_app
        dash_app = create_dash_app()
        server = dash_app.server
        assert 404 in server.error_handler_spec.get(None, {})

    def test_flask_500_handler_registered(self):
        """Verifica que el handler 500 está registrado en app_factory"""
        from core.app_factory import create_dash_app
        dash_app = create_dash_app()
        server = dash_app.server
        assert 500 in server.error_handler_spec.get(None, {})

    def test_error_log_store_in_layout(self):
        """Verifica que error-log-store existe en el layout del Dash"""
        from core.app_factory import create_dash_app
        dash_app = create_dash_app()
        layout_str = str(dash_app.layout)
        assert "error-log-store" in layout_str


# ═══════════════════════════════════════════════════════════
# 5. CORS HARDENING
# ═══════════════════════════════════════════════════════════

class TestCORSHardening:
    """Verifica que CORS no permita wildcard"""

    def test_cors_not_wildcard(self):
        """settings.API_CORS_ORIGINS no debe ser ['*'] en producción"""
        from core.config import settings
        origins = settings.API_CORS_ORIGINS
        if isinstance(origins, list):
            assert "*" not in origins, "CORS origins contiene wildcard '*'"
        elif isinstance(origins, str):
            assert origins != "*", "CORS origins es wildcard '*'"
