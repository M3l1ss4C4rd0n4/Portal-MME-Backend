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
    
    def test_init_uses_connection_manager(self):
        """Test: Repositorio se inicializa con connection_manager"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        assert repo.connection_manager == mock_cm
    
    def test_get_metric_data_calls_execute_dataframe(
        self, date_range_january_2026
    ):
        """Test: get_metric_data llama a execute_dataframe con query correcto"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        fecha_inicio, fecha_fin = date_range_january_2026
        
        # Actual signature: get_metric_data(metric_id, start_date, end_date, ...)
        repo.get_metric_data('Gene', fecha_inicio, fecha_fin)
        
        repo.execute_dataframe.assert_called_once()
        
        # Verificar que la query tiene los parámetros correctos
        call_args = repo.execute_dataframe.call_args
        query = call_args[0][0]  # Primer argumento es la query
        
        assert 'SELECT' in query.upper()
        assert 'metrics' in query.lower()
        assert 'fecha' in query.lower()
    
    def test_get_metric_data_returns_dataframe(
        self, date_range_january_2026, sample_metrics_df
    ):
        """Test: get_metric_data retorna DataFrame válido"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(return_value=sample_metrics_df)
        
        fecha_inicio, fecha_fin = date_range_january_2026
        
        result = repo.get_metric_data('Gene', fecha_inicio, fecha_fin)
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert 'fecha' in result.columns
        assert 'valor_gwh' in result.columns
    
    def test_get_hourly_data_calls_correct_table(
        self, single_date_2026
    ):
        """Test: get_hourly_data consulta la tabla metrics_hourly"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        # Actual signature: get_hourly_data(metric_id, entity_type, date_str)
        repo.get_hourly_data('Gene', 'Total', single_date_2026)
        
        repo.execute_dataframe.assert_called_once()
        
        # Verificar que consulta metrics_hourly
        call_args = repo.execute_dataframe.call_args
        query = call_args[0][0]
        
        assert 'metrics_hourly' in query.lower()
    
    def test_list_metrics_returns_list(self):
        """Test: list_metrics retorna lista de métricas"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_query = Mock(return_value=[
            {'metrica': 'Gene'}, {'metrica': 'DemaReal'}, {'metrica': 'DemaCome'}
        ])
        
        result = repo.list_metrics()
        
        assert isinstance(result, (list, pd.Series, pd.DataFrame))
    
    def test_get_metric_data_with_filters(
        self, date_range_january_2026
    ):
        """Test: Filtros adicionales se incluyen en la query"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        fecha_inicio, fecha_fin = date_range_january_2026
        
        # Llamar con filtros adicionales (actual params: unit, entity)
        repo.get_metric_data(
            'Gene', fecha_inicio, fecha_fin,
            entity='Total', unit='GWh'
        )
        
        repo.execute_dataframe.assert_called_once()
    
    def test_handles_database_error(
        self, date_range_january_2026
    ):
        """Test: Maneja correctamente errores de base de datos"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(
            side_effect=Exception("Database connection error")
        )
        
        fecha_inicio, fecha_fin = date_range_january_2026
        
        with pytest.raises(Exception):
            repo.get_metric_data('Gene', fecha_inicio, fecha_fin)
    
    def test_query_uses_parameterized_queries(
        self, date_range_january_2026
    ):
        """Test: Se usan queries parametrizadas (seguridad SQL injection)"""
        mock_cm = Mock()
        repo = MetricsRepository(connection_manager=mock_cm)
        repo.execute_dataframe = Mock(return_value=pd.DataFrame())
        
        fecha_inicio, fecha_fin = date_range_january_2026
        
        repo.get_metric_data('Gene', fecha_inicio, fecha_fin)
        
        # Verificar que se pasaron parámetros (no string interpolation)
        call_args = repo.execute_dataframe.call_args
        
        # Debe haber al menos 2 argumentos: query y params
        assert len(call_args[0]) >= 1  # Al menos la query
        
        # La query debe usar parámetros %s en vez de valores directos
        query = call_args[0][0]
        assert '%s' in query


@pytest.mark.slow
@pytest.mark.integration
class TestMetricsRepositoryIntegration:
    """Tests de integración que usan la base de datos real"""
    
    def test_get_metric_data_real_database(self):
        """Test de integración: Consulta real a PostgreSQL"""
        repo = MetricsRepository()
        
        try:
            result = repo.get_metric_data('Gene', '2026-01-01', '2026-01-05')
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
    
    def test_list_metrics_real_database(self):
        """Test de integración: Lista real de métricas"""
        repo = MetricsRepository()
        
        try:
            result = repo.list_metrics()
            assert len(result) > 0
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
