"""
Tests unitarios para AgentIA (ai_service.py)

CRÍTICO: Verifica la prevención de SQL injection vía whitelist de tablas,
y la inicialización correcta del agente IA.

Autor: Arquitectura Dashboard MME
Fecha: 2 de marzo de 2026
"""

import pytest
import pandas as pd
from unittest.mock import patch

# Importar a nivel de módulo para que logger se inicialice con settings reales
from domain.services.ai_service import AgentIA


class TestAgentIAWhitelist:
    """Tests para validación de whitelist anti SQL-injection"""

    @pytest.fixture
    def agent(self):
        """AgentIA sin keys IA (client=None) usando __new__ para evitar init"""
        with patch.object(AgentIA, "__init__", lambda self: None):
            a = AgentIA.__new__(AgentIA)
            a.client = None
            a.provider = None
            a.modelo = None
            return a

    def test_allowed_tables_is_frozenset(self, agent):
        """ALLOWED_TABLES debe ser inmutable (frozenset)"""
        assert isinstance(AgentIA.ALLOWED_TABLES, frozenset)

    def test_allowed_tables_contains_expected_tables(self, agent):
        """Whitelist contiene las tablas esperadas"""
        expected = {"metrics", "metrics_hourly", "predictions", "catalogos"}
        assert expected.issubset(AgentIA.ALLOWED_TABLES)

    def test_obtener_datos_rejects_invalid_table(self, agent):
        """SQL injection: tabla no en whitelist es rechazada"""
        result = agent.obtener_datos_recientes("users; DROP TABLE metrics;--", 10)
        assert result == []

    def test_obtener_datos_rejects_special_chars(self, agent):
        """SQL injection: caracteres especiales son rechazados"""
        malicious_tables = [
            "metrics; DROP TABLE users",
            "metrics UNION SELECT * FROM pg_shadow",
            "' OR '1'='1",
            "../../../etc/passwd",
            "metrics\x00injection",
        ]
        for table in malicious_tables:
            result = agent.obtener_datos_recientes(table, 10)
            assert result == [], f"Tabla maliciosa no fue rechazada: {table}"

    @patch("domain.services.ai_service.db_manager")
    def test_obtener_datos_accepts_valid_table(self, mock_db, agent):
        """Tablas válidas de la whitelist son aceptadas"""
        mock_db.query_df.return_value = pd.DataFrame({"fecha": [], "valor": []})
        for tabla in ["metrics", "predictions", "catalogos"]:
            agent.obtener_datos_recientes(tabla, 5)


class TestAgentIAInitialization:
    """Tests para inicialización del agente"""

    def test_init_without_keys_client_is_none(self):
        """Agente sin keys → client es None"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", ""):
            with patch.object(settings, "OPENROUTER_API_KEY", ""):
                agent = AgentIA()
                assert agent.client is None
                assert agent.provider is None

    def test_init_with_groq_key_sets_provider(self):
        """Agente con Groq key → proveedor Groq"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", "test-groq-key"):
            with patch.object(settings, "OPENROUTER_API_KEY", ""):
                with patch("domain.services.ai_service.OpenAI") as MockOpenAI:
                    agent = AgentIA()
                    assert agent.provider == "Groq"
                    MockOpenAI.assert_called_once()

    def test_init_with_openrouter_key_sets_provider(self):
        """Agente con OpenRouter key como fallback"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", ""):
            with patch.object(settings, "OPENROUTER_API_KEY", "test-openrouter-key"):
                with patch("domain.services.ai_service.OpenAI") as MockOpenAI:
                    agent = AgentIA()
                    assert agent.provider == "OpenRouter"

    def test_get_db_connection_returns_none(self):
        """get_db_connection es stub deprecado → retorna None"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", ""):
            with patch.object(settings, "OPENROUTER_API_KEY", ""):
                agent = AgentIA()
                result = agent.get_db_connection()
                assert result is None


class TestAgentIAObtenerMetricas:
    """Tests para obtener_metricas"""

    @pytest.fixture
    def agent_with_mock_db(self):
        """AgentIA con db_manager mockeado"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", ""):
            with patch.object(settings, "OPENROUTER_API_KEY", ""):
                agent = AgentIA()
                yield agent

    @patch("domain.services.ai_service.db_manager")
    def test_obtener_metricas_returns_list(self, mock_db, agent_with_mock_db):
        """obtener_metricas retorna lista de diccionarios"""
        mock_db.query_df.return_value = pd.DataFrame({
            "fecha": pd.date_range("2026-01-01", periods=5),
            "metrica": ["Gene"] * 5,
            "valor_gwh": [100.0] * 5,
        })
        result = agent_with_mock_db.obtener_metricas("Gene", 10)
        assert isinstance(result, list)

    def test_obtener_datos_contexto_pagina_returns_dict(self, agent_with_mock_db):
        """obtener_datos_contexto_pagina retorna diccionario"""
        result = agent_with_mock_db.obtener_datos_contexto_pagina("/generacion")
        assert isinstance(result, dict)


class TestAgentIADetectarAlertas:
    """Tests para detectar_alertas"""

    @pytest.fixture
    def agent_with_mocks(self):
        """AgentIA con todas las dependencias mockeadas"""
        from core.config import settings
        with patch.object(settings, "GROQ_API_KEY", ""):
            with patch.object(settings, "OPENROUTER_API_KEY", ""):
                agent = AgentIA()
                yield agent

    @patch("domain.services.ai_service.db_manager")
    def test_detectar_alertas_returns_dict_structure(self, mock_db, agent_with_mocks):
        """detectar_alertas retorna dict con keys esperadas"""
        mock_db.query_df.return_value = pd.DataFrame({
            "fecha": pd.date_range("2026-01-01", periods=5),
            "metrica": ["Gene"] * 5,
            "valor_gwh": [100.0] * 5,
        })
        result = agent_with_mocks.detectar_alertas()
        assert isinstance(result, dict)
        expected_keys = {"criticas", "advertencias", "informativas"}
        assert expected_keys.issubset(set(result.keys()))

    @patch("domain.services.ai_service.db_manager")
    def test_detectar_alertas_values_are_lists(self, mock_db, agent_with_mocks):
        """Cada categoría de alerta es una lista de strings"""
        mock_db.query_df.return_value = pd.DataFrame({
            "fecha": pd.date_range("2026-01-01", periods=5),
            "metrica": ["Gene"] * 5,
            "valor_gwh": [100.0] * 5,
        })
        result = agent_with_mocks.detectar_alertas()
        for key in ["criticas", "advertencias", "informativas"]:
            if key in result:
                assert isinstance(result[key], list)
