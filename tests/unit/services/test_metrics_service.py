"""
Tests unitarios para MetricsService.
"""

import pytest
import pandas as pd
from datetime import date
from unittest.mock import Mock, create_autospec

from domain.services.metrics_service import MetricsService
from domain.interfaces.repositories import IMetricsRepository


class TestMetricsService:
    """Tests para MetricsService."""
    
    @pytest.fixture
    def mock_repo(self):
        """Mock de IMetricsRepository con todos los métodos."""
        repo = create_autospec(IMetricsRepository, instance=True)
        return repo
    
    @pytest.fixture
    def service(self, mock_repo):
        """Instancia de MetricsService con mock."""
        return MetricsService(repository=mock_repo)
    
    def test_get_latest_date_success(self, service, mock_repo):
        """Test get_latest_date con datos exitosos."""
        # Arrange
        mock_repo.get_latest_date.return_value = "2026-03-20"
        
        # Act
        result = service.get_latest_date()
        
        # Assert
        assert result == "2026-03-20"
        mock_repo.get_latest_date.assert_called_once()
    
    def test_get_latest_date_none(self, service, mock_repo):
        """Test get_latest_date sin datos."""
        # Arrange
        mock_repo.get_latest_date.return_value = None
        
        # Act
        result = service.get_latest_date()
        
        # Assert
        assert result is None
    
    def test_get_total_records_success(self, service, mock_repo):
        """Test get_total_records."""
        # Arrange
        mock_repo.get_total_records.return_value = 1000000
        
        # Act
        result = service.get_total_records()
        
        # Assert
        assert result == 1000000
        mock_repo.get_total_records.assert_called_once()
    
    def test_list_metrics_success(self, service, mock_repo):
        """Test list_metrics."""
        # Arrange
        expected_metrics = [
            {"MetricId": "Gene", "MetricName": "Generación"},
            {"MetricId": "Dema", "MetricName": "Demanda"}
        ]
        mock_repo.list_metrics.return_value = expected_metrics
        
        # Act
        result = service.list_metrics()
        
        # Assert
        assert result == expected_metrics
        assert len(result) == 2
    
    def test_get_metric_series_success(self, service, mock_repo):
        """Test get_metric_series con datos."""
        # Arrange
        df_data = {
            'fecha': pd.date_range('2026-01-01', periods=3),
            'valor': [100.0, 200.0, 300.0]
        }
        mock_df = pd.DataFrame(df_data)
        mock_repo.get_metric_data.return_value = mock_df
        
        # Act
        result = service.get_metric_series("Gene", "2026-01-01", "2026-01-03")
        
        # Assert
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        mock_repo.get_metric_data.assert_called_once_with(
            "Gene", "2026-01-01", "2026-01-03", None
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
