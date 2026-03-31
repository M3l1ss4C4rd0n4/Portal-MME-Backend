"""
Tests unitarios para Dependency Container.
"""

import pytest
from unittest.mock import Mock

from core.container import DependencyContainer
from domain.interfaces.repositories import IMetricsRepository


class TestDependencyContainer:
    """Tests para DependencyContainer."""
    
    @pytest.fixture
    def container(self):
        """Container limpio para cada test."""
        return DependencyContainer()
    
    def test_register_and_resolve(self, container):
        """Test registro y resolución básica."""
        # Arrange
        mock_repo = Mock(spec=IMetricsRepository)
        container.register(IMetricsRepository, mock_repo)
        
        # Act
        result = container.resolve(IMetricsRepository)
        
        # Assert
        assert result is mock_repo
    
    def test_register_singleton(self, container):
        """Test registro de singleton."""
        # Arrange
        mock_repo = Mock(spec=IMetricsRepository)
        container.register_singleton(IMetricsRepository, mock_repo)
        
        # Act
        result1 = container.resolve(IMetricsRepository)
        result2 = container.resolve(IMetricsRepository)
        
        # Assert
        assert result1 is result2 is mock_repo
    
    def test_resolve_not_registered(self, container):
        """Test resolución de interfaz no registrada."""
        # Act & Assert
        with pytest.raises(KeyError):
            container.resolve(IMetricsRepository)
    
    def test_try_resolve_not_registered(self, container):
        """Test try_resolve de interfaz no registrada."""
        # Act
        result = container.try_resolve(IMetricsRepository)
        
        # Assert
        assert result is None
    
    def test_is_registered(self, container):
        """Test verificación de registro."""
        # Arrange
        mock_repo = Mock()
        container.register(IMetricsRepository, mock_repo)
        
        # Act & Assert
        assert container.is_registered(IMetricsRepository) is True
        assert container.is_registered(str) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
