"""Tests para DistributionService."""
import pytest
from domain.services.distribution_service import DistributionService


class TestDistributionService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = DistributionService()
        assert service is not None
