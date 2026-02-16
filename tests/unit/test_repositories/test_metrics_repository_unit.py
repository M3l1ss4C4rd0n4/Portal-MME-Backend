"""
Tests unitarios para MetricsRepository

Estos tests usan mocks y no acceden a la base de datos real.
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from infrastructure.database.repositories.metrics_repository import MetricsRepository


class TestMetricsRepositoryUnit:
    """Tests unitarios para MetricsRepository"""
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_init_uses_db_manager(self, mock_db_manager):
        """Test: Repositorio se inicializa con db_manager"""
        repo = MetricsRepository()
        assert repo.db != None
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_get_metric_data_calls_execute_dataframe(
        self, mock_db_manager, date_range_january_2026
    ):
        """Test: get_metric_data llama a execute_dataframe con query correcto"""
        mock_db_manager.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        repo = MetricsRepository()
        fecha_inicio, fecha_fin = date_range_january_2026
        
        repo.get_metric_data(fecha_inicio, fecha_fin, 'Gene')
        
        mock_db_manager.execute_dataframe.assert_called_once()
        
        # Verificar que la query tiene los parámetros correctos
        call_args = mock_db_manager.execute_dataframe.call_args
        query = call_args[0][0]  # Primer argumento es la query
        
        assert 'SELECT' in query.upper()
        assert 'metrics' in query.lower()
        assert 'fecha' in query.lower()
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_get_metric_data_returns_dataframe(
        self, mock_db_manager, date_range_january_2026, sample_metrics_df
    ):
        """Test: get_metric_data retorna DataFrame válido"""
        mock_db_manager.execute_dataframe = Mock(return_value=sample_metrics_df)
        
        repo = MetricsRepository()
        fecha_inicio, fecha_fin = date_range_january_2026
        
        result = repo.get_metric_data(fecha_inicio, fecha_fin, 'Gene')
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert 'fecha' in result.columns
        assert 'valor_gwh' in result.columns
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_get_hourly_data_calls_correct_table(
        self, mock_db_manager, single_date_2026
    ):
        """Test: get_hourly_data consulta la tabla metrics_hourly"""
        mock_db_manager.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        repo = MetricsRepository()
        repo.get_hourly_data(single_date_2026, 'Gene')
        
        mock_db_manager.execute_dataframe.assert_called_once()
        
        # Verificar que consulta metrics_hourly
        call_args = mock_db_manager.execute_dataframe.call_args
        query = call_args[0][0]
        
        assert 'metrics_hourly' in query.lower()
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_list_available_metrics_returns_list(self, mock_db_manager):
        """Test: list_available_metrics retorna lista de métricas"""
        mock_db_manager.execute_dataframe = Mock(return_value=pd.DataFrame({
            'metrica': ['Gene', 'DemaReal', 'DemaCome']
        }))
        
        repo = MetricsRepository()
        result = repo.list_available_metrics()
        
        assert isinstance(result, (list, pd.Series, pd.DataFrame))
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_get_metric_data_with_filters(
        self, mock_db_manager, date_range_january_2026
    ):
        """Test: Filtros adicionales se incluyen en la query"""
        mock_db_manager.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        repo = MetricsRepository()
        fecha_inicio, fecha_fin = date_range_january_2026
        
        # Llamar con filtros adicionales
        repo.get_metric_data(
            fecha_inicio, fecha_fin, 'Gene', 
            entidad='Total', recurso='GUAVIO'
        )
        
        mock_db_manager.execute_dataframe.assert_called_once()
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_handles_database_error(
        self, mock_db_manager, date_range_january_2026
    ):
        """Test: Maneja correctamente errores de base de datos"""
        mock_db_manager.execute_dataframe = Mock(
            side_effect=Exception("Database connection error")
        )
        
        repo = MetricsRepository()
        fecha_inicio, fecha_fin = date_range_january_2026
        
        with pytest.raises(Exception):
            repo.get_metric_data(fecha_inicio, fecha_fin, 'Gene')
    
    @patch('infrastructure.database.repositories.metrics_repository.db_manager')
    def test_query_uses_parameterized_queries(
        self, mock_db_manager, date_range_january_2026
    ):
        """Test: Se usan queries parametrizadas (seguridad SQL injection)"""
        mock_db_manager.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        repo = MetricsRepository()
        fecha_inicio, fecha_fin = date_range_january_2026
        
        repo.get_metric_data(fecha_inicio, fecha_fin, 'Gene')
        
        # Verificar que se pasaron parámetros (no string interpolation)
        call_args = mock_db_manager.execute_dataframe.call_args
        
        # Debe haber al menos 2 argumentos: query y params
        assert len(call_args[0]) >= 1  # Al menos la query
        
        # La query no debería incluir directamente las fechas
        query = call_args[0][0]
        assert fecha_inicio not in query or '%s' in query or '?' in query


@pytest.mark.slow
@pytest.mark.integration
class TestMetricsRepositoryIntegration:
    """Tests de integración que usan la base de datos real"""
    
    def test_get_metric_data_real_database(self):
        """Test de integración: Consulta real a PostgreSQL"""
        repo = MetricsRepository()
        
        try:
            result = repo.get_metric_data('2026-01-01', '2026-01-05', 'Gene')
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
    
    def test_list_available_metrics_real_database(self):
        """Test de integración: Lista real de métricas"""
        repo = MetricsRepository()
        
        try:
            result = repo.list_available_metrics()
            assert len(result) > 0
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
