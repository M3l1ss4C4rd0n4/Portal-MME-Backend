"""Tests para TransmissionService."""
import pytest
from domain.services.transmission_service import TransmissionService


class TestTransmissionService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = TransmissionService()
        assert service is not None
