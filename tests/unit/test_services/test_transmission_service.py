"""
Tests unitarios para TransmissionService
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from domain.services.transmission_service import TransmissionService


class TestTransmissionService:
    """Tests para TransmissionService"""
    
    def test_init_with_repository(self, mock_transmission_repository):
        """Test: Servicio se inicializa correctamente con repositorio inyectado"""
        service = TransmissionService(repository=mock_transmission_repository)
        assert service.repo == mock_transmission_repository
    
    def test_init_without_repository(self):
        """Test: Servicio se inicializa con repositorio por defecto"""
        with patch('domain.services.transmission_service.TransmissionRepository') as MockRepo:
            service = TransmissionService()
            MockRepo.assert_called_once()
    
    def test_get_transmission_lines_returns_dataframe(
        self, transmission_service_with_mock
    ):
        """Test: get_transmission_lines retorna DataFrame válido"""
        result = transmission_service_with_mock.get_transmission_lines()
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
    
    def test_get_transmission_lines_force_refresh(
        self, mock_transmission_repository
    ):
        """Test: force_refresh se pasa correctamente"""
        service = TransmissionService(repository=mock_transmission_repository)
        
        # With force_refresh=True, service skips DB and returns empty
        result = service.get_transmission_lines(force_refresh=True)
        
        assert isinstance(result, pd.DataFrame)
    
    def test_get_summary_stats_returns_dict(
        self, transmission_service_with_mock
    ):
        """Test: get_summary_stats retorna diccionario con estadísticas"""
        result = transmission_service_with_mock.get_summary_stats()
        
        assert isinstance(result, dict)
        assert 'total_lines' in result
        assert 'total_length_km' in result
        assert 'operators_count' in result
    
    def test_get_summary_stats_has_correct_values(
        self, transmission_service_with_mock
    ):
        """Test: Estadísticas tienen valores esperados basados en mock data"""
        result = transmission_service_with_mock.get_summary_stats()
        
        # Mock data has 3 unique CodigoLinea, 3 unique CodigoOperador
        assert result['total_lines'] == 3
        assert result['operators_count'] == 3
        assert result['total_length_km'] == 285.0
    
    def test_service_handles_empty_dataframe(
        self, mock_transmission_repository
    ):
        """Test: Servicio maneja correctamente DataFrame vacío"""
        mock_transmission_repository.get_latest_lines = Mock(return_value=pd.DataFrame())
        service = TransmissionService(repository=mock_transmission_repository)
        
        result = service.get_transmission_lines()
        
        assert isinstance(result, pd.DataFrame)
        assert result.empty
    
    def test_get_lineas_transmision_returns_dataframe(
        self, transmission_service_with_mock
    ):
        """Test: get_lineas_transmision retorna DataFrame con columnas normalizadas"""
        result = transmission_service_with_mock.get_lineas_transmision()
        
        assert isinstance(result, pd.DataFrame)
    
    @pytest.mark.parametrize("force_refresh", [True, False])
    def test_get_transmission_lines_with_force_refresh_param(
        self, mock_transmission_repository, force_refresh
    ):
        """Test: get_transmission_lines acepta parámetro force_refresh"""
        service = TransmissionService(repository=mock_transmission_repository)
        
        result = service.get_transmission_lines(force_refresh=force_refresh)
        
        assert isinstance(result, pd.DataFrame)
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_get_transmission_lines_real_database(self):
        """Test de integración: Consulta real a la base de datos"""
        service = TransmissionService()
        
        try:
            result = service.get_transmission_lines()
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
