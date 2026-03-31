"""Tests para system_service."""
import pytest

from domain.services import system_service


class TestSystemService:
    def test_module_imports(self):
        """Test que el módulo se puede importar."""
        assert system_service is not None
