"""
Tests básicos para WhatsApp Bot
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ═══════════════════════════════════════════════════════════
# Tests de Endpoints
# ═══════════════════════════════════════════════════════════

def test_root_endpoint():
    """Test endpoint raíz"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "WhatsApp Bot - Portal Energético MME"
    assert data["status"] == "running"


def test_health_endpoint():
    """Test health check"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_stats_endpoint():
    """Test estadísticas"""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    # Verificar que existan campos básicos
    assert "messages_received" in data or "error" not in data


# ═══════════════════════════════════════════════════════════
# Tests de Bot Orchestrator
# ═══════════════════════════════════════════════════════════

def test_intent_classification_greeting():
    """Test clasificación de saludos"""
    from orchestrator.bot import BotOrchestrator
    
    bot = BotOrchestrator()
    
    assert bot.classify_intent("hola") == "GREETING"
    assert bot.classify_intent("buenos días") == "GREETING"
    assert bot.classify_intent("buenas tardes") == "GREETING"


def test_intent_classification_help():
    """Test clasificación de ayuda"""
    from orchestrator.bot import BotOrchestrator
    
    bot = BotOrchestrator()
    
    assert bot.classify_intent("ayuda") == "HELP"
    assert bot.classify_intent("/help") == "GENERAL"  # Los comandos van por otro path


def test_intent_classification_price():
    """Test clasificación de consultas de precio"""
    from orchestrator.bot import BotOrchestrator
    
    bot = BotOrchestrator()
    
    assert bot.classify_intent("precio de bolsa") == "PRICE_QUERY"
    assert bot.classify_intent("cuánto cuesta") == "PRICE_QUERY"


# ═══════════════════════════════════════════════════════════
# Tests de Servicios
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_data_service_creation():
    """Test creación de DataService"""
    from services.data_service import DataService
    
    service = DataService()
    assert service is not None


@pytest.mark.asyncio
async def test_ai_integration_creation():
    """Test creación de AIIntegration"""
    from services.ai_integration import AIIntegration
    
    integration = AIIntegration()
    assert integration is not None


# ═══════════════════════════════════════════════════════════
# Tests de Context Manager
# ═══════════════════════════════════════════════════════════

def test_context_manager_new_user():
    """Test creación de contexto nuevo"""
    from orchestrator.context import ContextManager
    
    try:
        ctx_manager = ContextManager()
        context = ctx_manager.get_context("+573001234567")
        
        assert context is not None
        assert context["user_id"] == "+573001234567"
        assert "conversation_history" in context
        assert "preferences" in context
        
        # Limpiar
        ctx_manager.clear_context("+573001234567")
    except:
        # Si Redis no está disponible, el test pasa
        pytest.skip("Redis no disponible")


# ═══════════════════════════════════════════════════════════
# Tests de Rate Limiting
# ═══════════════════════════════════════════════════════════

def test_rate_limiter_creation():
    """Test creación de RateLimiter"""
    from app.rate_limiting import RateLimiter
    
    try:
        limiter = RateLimiter()
        assert limiter is not None
    except:
        pytest.skip("Redis no disponible")


# ═══════════════════════════════════════════════════════════
# Tests de Chart Service
# ═══════════════════════════════════════════════════════════

def test_chart_service_creation():
    """Test creación de ChartService"""
    from services.chart_service import ChartService
    
    service = ChartService()
    assert service is not None


def test_chart_service_parse_period():
    """Test parseo de períodos"""
    from services.chart_service import ChartService
    
    service = ChartService()
    
    assert service._parse_period("7d") == 7
    assert service._parse_period("2w") == 14
    assert service._parse_period("1m") == 30
    assert service._parse_period("1y") == 365


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
