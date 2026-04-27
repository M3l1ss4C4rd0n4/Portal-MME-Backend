"""Tests para LossesService."""
import pytest
from domain.services.losses_service import LossesService


class TestLossesService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = LossesService()
        assert service is not None
