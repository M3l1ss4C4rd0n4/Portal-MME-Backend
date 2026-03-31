"""Tests para CommercialService."""
import pytest
from domain.services.commercial_service import CommercialService, _get_default_repo, _get_xm_service


class TestCommercialService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = CommercialService()
        assert service is not None
