"""Tests para GenerationService."""
import pytest
from domain.services.generation_service import GenerationService


class TestGenerationService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = GenerationService()
        assert service is not None
        assert hasattr(service, 'repo')
