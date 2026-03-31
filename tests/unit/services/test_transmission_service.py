"""Tests para TransmissionService."""
import pytest
from domain.services.transmission_service import TransmissionService, _get_default_repo


class TestTransmissionService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = TransmissionService()
        assert service is not None
