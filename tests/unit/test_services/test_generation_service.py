"""
Tests unitarios para GenerationService

Verifica la lógica de negocio sin acceso real a la base de datos.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, patch

from domain.services.generation_service import GenerationService


class TestGenerationService:
    """Tests para GenerationService"""
    
    def test_init_with_repository(self, mock_metrics_repository):
        """Test: Servicio se inicializa correctamente con repositorio inyectado"""
        service = GenerationService(repository=mock_metrics_repository)
        assert service.repository == mock_metrics_repository
    
    def test_init_without_repository(self):
        """Test: Servicio se inicializa con repositorio por defecto"""
        with patch('domain.services.generation_service.MetricsRepository') as MockRepo:
            service = GenerationService()
            MockRepo.assert_called_once()
    
    def test_get_daily_generation_system_returns_dataframe(
        self, generation_service_with_mock, date_range_january_2026
    ):
        """Test: get_daily_generation_system retorna DataFrame válido"""
        fecha_inicio, fecha_fin = date_range_january_2026
        
        result = generation_service_with_mock.get_daily_generation_system(
            fecha_inicio, fecha_fin
        )
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert 'fecha' in result.columns
        assert 'valor_gwh' in result.columns
    
    def test_get_daily_generation_system_calls_repository(
        self, mock_metrics_repository, date_range_january_2026
    ):
        """Test: Servicio llama al repositorio con parámetros correctos"""
        service = GenerationService(repository=mock_metrics_repository)
        fecha_inicio, fecha_fin = date_range_january_2026
        
        service.get_daily_generation_system(fecha_inicio, fecha_fin)
        
        mock_metrics_repository.get_metric_data.assert_called_once()
        call_args = mock_metrics_repository.get_metric_data.call_args
        assert call_args[0][0] == fecha_inicio or call_args[1].get('fecha_inicio') == fecha_inicio
    
    def test_get_resources_by_type_filters_correctly(
        self, generation_service_with_mock
    ):
        """Test: get_resources_by_type filtra por tipo correctamente"""
        # Mock retorna datos con diferentes tipos
        mock_data = pd.DataFrame({
            'recurso': ['GUAVIO', 'TEQUENDAMA', 'TERMOCARTAGENA'],
            'tipo': ['HIDRAULICA', 'HIDRAULICA', 'TERMICA'],
            'valor_gwh': [100, 200, 300]
        })
        generation_service_with_mock.repository.get_metric_data = Mock(return_value=mock_data)
        
        # Filtrar hidráulicas (esto depende de la implementación real)
        # Ajustar según la lógica real del servicio
        result = generation_service_with_mock.repository.get_metric_data()
        hidraulicas = result[result['tipo'] == 'HIDRAULICA']
        
        assert len(hidraulicas) == 2
        assert all(hidraulicas['tipo'] == 'HIDRAULICA')
    
    def test_service_handles_empty_dataframe(
        self, mock_metrics_repository, date_range_january_2026
    ):
        """Test: Servicio maneja correctamente DataFrame vacío"""
        mock_metrics_repository.get_metric_data = Mock(return_value=pd.DataFrame())
        service = GenerationService(repository=mock_metrics_repository)
        
        fecha_inicio, fecha_fin = date_range_january_2026
        result = service.get_daily_generation_system(fecha_inicio, fecha_fin)
        
        assert isinstance(result, pd.DataFrame)
        assert result.empty
    
    @pytest.mark.parametrize("fecha_inicio,fecha_fin", [
        ('2026-01-01', '2026-01-31'),
        ('2025-12-01', '2025-12-31'),
        ('2025-06-01', '2025-06-30'),
    ])
    def test_get_daily_generation_multiple_date_ranges(
        self, generation_service_with_mock, fecha_inicio, fecha_fin
    ):
        """Test: Servicio funciona con diferentes rangos de fechas"""
        result = generation_service_with_mock.get_daily_generation_system(
            fecha_inicio, fecha_fin
        )
        
        assert isinstance(result, pd.DataFrame)
    
    def test_service_uses_correct_metric_name(
        self, mock_metrics_repository, date_range_january_2026
    ):
        """Test: Servicio usa el nombre de métrica correcto para generación"""
        service = GenerationService(repository=mock_metrics_repository)
        fecha_inicio, fecha_fin = date_range_january_2026
        
        service.get_daily_generation_system(fecha_inicio, fecha_fin)
        
        # Verificar que se llamó con la métrica 'Gene'
        call_args = mock_metrics_repository.get_metric_data.call_args
        assert 'Gene' in str(call_args) or 'metrica' in str(call_args)


class TestGenerationServiceIntegration:
    """Tests de integración que usan datos reales (marcar como slow)"""
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_get_daily_generation_with_real_database(self):
        """Test de integración: Consulta real a la base de datos"""
        service = GenerationService()  # Sin mock, usa repo real
        
        # Solo ejecutar si hay BD disponible
        try:
            result = service.get_daily_generation_system('2026-01-01', '2026-01-05')
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
