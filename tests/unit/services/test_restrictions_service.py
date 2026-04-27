"""Tests para RestrictionsService."""
import pytest
from domain.services.restrictions_service import RestrictionsService


class TestRestrictionsService:
    def test_service_creation(self):
        """Test que el servicio se puede crear."""
        service = RestrictionsService()
        assert service is not None
