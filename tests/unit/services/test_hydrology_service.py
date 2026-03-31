"""Tests para HydrologyService."""
import pytest
from domain.services.hydrology_service import HydrologyService


class TestHydrologyService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = HydrologyService()
        assert service is not None
