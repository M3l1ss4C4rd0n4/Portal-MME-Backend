"""Tests para IndicatorsService."""
import pytest
from domain.services.indicators_service import IndicatorsService


class TestIndicatorsService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = IndicatorsService()
        assert service is not None
