"""
Tests unitarios para Dependency Container.
"""

import pytest
from unittest.mock import Mock

from core.container import DependencyContainer
from domain.interfaces.repositories import IMetricsRepository, ITransmissionRepository


class TestDependencyContainer:
    """Tests para DependencyContainer."""
    
    @pytest.fixture
    def container(self):
        """Container limpio para cada test."""
        c = DependencyContainer()
        yield c
        c.reset()
    
    def test_container_instantiation(self, container):
        """Test que el container se puede instanciar."""
        assert container is not None
    
    def test_override_and_get_metrics_repository(self, container):
        """Test que override_metrics_repository() inyecta el mock correctamente."""
        # Arrange
        mock_repo = Mock(spec=IMetricsRepository)
        container.override_metrics_repository(mock_repo)
        
        # Act
        result = container.get_metrics_repository()
        
        # Assert
        assert result is mock_repo
    
    def test_override_transmission_repository(self, container):
        """Test que override_transmission_repository() inyecta el mock correctamente."""
        mock_repo = Mock(spec=ITransmissionRepository)
        container.override_transmission_repository(mock_repo)
        
        assert container.get_transmission_repository() is mock_repo
    
    def test_reset_clears_all_overrides(self, container):
        """Test que reset() limpia todas las dependencias inyectadas."""
        # Arrange
        mock_repo = Mock(spec=IMetricsRepository)
        container.override_metrics_repository(mock_repo)
        assert container._metrics_repository is mock_repo
        
        # Act
        container.reset()
        
        # Assert: vuelve a None — siguiente get() creará instancia real
        assert container._metrics_repository is None
    
    def test_singleton_behavior_after_override(self, container):
        """Test que el getter devuelve la misma instancia en llamadas sucesivas."""
        mock_repo = Mock(spec=IMetricsRepository)
        container.override_metrics_repository(mock_repo)
        
        result1 = container.get_metrics_repository()
        result2 = container.get_metrics_repository()
        
        assert result1 is result2 is mock_repo
    
    def test_reset_restores_lazy_init(self, container):
        """Test que después de reset, un override nuevo funciona limpio."""
        mock_a = Mock(spec=IMetricsRepository)
        mock_b = Mock(spec=IMetricsRepository)
        
        container.override_metrics_repository(mock_a)
        assert container.get_metrics_repository() is mock_a
        
        container.reset()
        container.override_metrics_repository(mock_b)
        assert container.get_metrics_repository() is mock_b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

    pytest.main([__file__, "-v"])
