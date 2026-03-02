"""
Tests unitarios para system_service

Verifica las funciones de health check del sistema
con conexiones a PostgreSQL mockeadas.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class TestVerificarSaludSistema:
    """Tests para verificar_salud_sistema()"""

    @patch("domain.services.system_service.psycopg2")
    @patch("domain.services.system_service.settings")
    def test_returns_dict_with_status(self, mock_settings, mock_psycopg2):
        """verificar_salud_sistema retorna dict con campo 'status'"""
        # Setup mock settings
        mock_settings.POSTGRES_HOST = "localhost"
        mock_settings.POSTGRES_PORT = 5432
        mock_settings.POSTGRES_DB = "portal_energetico"
        mock_settings.POSTGRES_USER = "postgres"
        mock_settings.POSTGRES_PASSWORD = ""

        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        from domain.services.system_service import verificar_salud_sistema
        result = verificar_salud_sistema()

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ("healthy", "degraded", "unhealthy")

    @patch("domain.services.system_service.psycopg2")
    @patch("domain.services.system_service.settings")
    def test_returns_timestamp(self, mock_settings, mock_psycopg2):
        """verificar_salud_sistema incluye timestamp"""
        mock_settings.POSTGRES_HOST = "localhost"
        mock_settings.POSTGRES_PORT = 5432
        mock_settings.POSTGRES_DB = "portal_energetico"
        mock_settings.POSTGRES_USER = "postgres"
        mock_settings.POSTGRES_PASSWORD = ""

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.fetchone.return_value = (42,)
        mock_psycopg2.connect.return_value = mock_conn

        from domain.services.system_service import verificar_salud_sistema
        result = verificar_salud_sistema()

        assert "timestamp" in result

    @patch("domain.services.system_service.psycopg2")
    @patch("domain.services.system_service.settings")
    def test_handles_db_connection_error(self, mock_settings, mock_psycopg2):
        """Si PostgreSQL no responde, status debe ser unhealthy/degraded"""
        mock_settings.POSTGRES_HOST = "localhost"
        mock_settings.POSTGRES_PORT = 5432
        mock_settings.POSTGRES_DB = "portal_energetico"
        mock_settings.POSTGRES_USER = "postgres"
        mock_settings.POSTGRES_PASSWORD = ""

        mock_psycopg2.connect.side_effect = Exception("Connection refused")

        from domain.services.system_service import verificar_salud_sistema
        result = verificar_salud_sistema()

        assert isinstance(result, dict)
        assert result["status"] in ("degraded", "unhealthy")


class TestGenerarReporteTexto:
    """Tests para generar_reporte_texto()"""

    def test_generates_string_report(self):
        """generar_reporte_texto convierte dict a texto legible"""
        from domain.services.system_service import generar_reporte_texto

        salud = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {"db": True, "dashboard": True},
            "warnings": [],
            "errors": [],
            "message": "Sistema operando normalmente",
        }

        result = generar_reporte_texto(salud)
        assert isinstance(result, str)
        assert len(result) > 10

    def test_report_includes_status(self):
        """El reporte incluye el estado del sistema"""
        from domain.services.system_service import generar_reporte_texto

        salud = {
            "status": "degraded",
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "warnings": ["Datos desactualizados"],
            "errors": [],
            "message": "Sistema degradado",
        }

        result = generar_reporte_texto(salud)
        assert "degraded" in result.lower() or "degradado" in result.lower()
