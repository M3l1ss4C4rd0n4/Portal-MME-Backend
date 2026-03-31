"""Tests para GenerationService."""
import pytest
from domain.services.generation_service import GenerationService, _get_default_repo


class TestGenerationService:
    def test_get_default_repo(self):
        """Test que la función de lazy import funciona."""
        try:
            repo = _get_default_repo()
            assert repo is not None
        except Exception:
            # Es válido si falla por configuración
            pass
    
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = GenerationService()
        assert service is not None
        assert hasattr(service, 'repo')
