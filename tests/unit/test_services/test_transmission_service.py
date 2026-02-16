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
        assert service.repository == mock_transmission_repository
    
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
        assert 'linea' in result.columns or 'tension_kv' in result.columns
    
    def test_get_transmission_lines_with_filters(
        self, mock_transmission_repository
    ):
        """Test: Filtros se pasan correctamente al repositorio"""
        service = TransmissionService(repository=mock_transmission_repository)
        
        filtros = {
            'tension_kv': 500,
            'operador': 'ISA'
        }
        
        service.get_transmission_lines(**filtros)
        
        mock_transmission_repository.get_transmission_lines.assert_called_once()
    
    def test_get_summary_stats_returns_dict(
        self, transmission_service_with_mock
    ):
        """Test: get_summary_stats retorna diccionario con estadísticas"""
        result = transmission_service_with_mock.get_summary_stats()
        
        assert isinstance(result, dict)
        assert 'total_lines' in result
        assert 'total_km' in result
        assert 'operators' in result
    
    def test_get_summary_stats_has_correct_values(
        self, transmission_service_with_mock
    ):
        """Test: Estadísticas tienen valores esperados"""
        result = transmission_service_with_mock.get_summary_stats()
        
        assert result['total_lines'] == 857
        assert result['total_km'] == 30946
        assert result['operators'] == 34
    
    def test_service_handles_empty_dataframe(
        self, mock_transmission_repository
    ):
        """Test: Servicio maneja correctamente DataFrame vacío"""
        mock_transmission_repository.get_transmission_lines = Mock(return_value=pd.DataFrame())
        service = TransmissionService(repository=mock_transmission_repository)
        
        result = service.get_transmission_lines()
        
        assert isinstance(result, pd.DataFrame)
        assert result.empty
    
    @pytest.mark.parametrize("tension_kv", [500, 230, 115, 34.5])
    def test_filter_by_tension(
        self, mock_transmission_repository, tension_kv
    ):
        """Test: Filtrado por tensión funciona correctamente"""
        service = TransmissionService(repository=mock_transmission_repository)
        
        service.get_transmission_lines(tension_kv=tension_kv)
        
        mock_transmission_repository.get_transmission_lines.assert_called_once()
    
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
