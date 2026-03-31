"""Tests para LossesService."""
import pytest
from domain.services.losses_service import LossesService, _get_default_repo, _get_metrics_service


class TestLossesService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = LossesService()
        assert service is not None
