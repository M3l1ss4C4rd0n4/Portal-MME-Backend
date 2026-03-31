"""
Tests para el sistema de health checks.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, MagicMock

from infrastructure.observability.health import (
    HealthChecker, HealthCheck, HealthStatus, HealthResult
)


class MockHealthCheck(HealthCheck):
    """Health check de prueba."""
    
    def __init__(self, name: str, status: HealthStatus, **kwargs):
        super().__init__(name, **kwargs)
        self.status = status
    
    async def check(self) -> HealthResult:
        return HealthResult(
            status=self.status,
            component=self.name,
            message=f"Test {self.status.value}"
        )


class TestHealthChecker:
    """Tests para HealthChecker."""
    
    def test_register_and_run_checks(self):
        """Test registro y ejecución de checks."""
        checker = HealthChecker()
        
        check = MockHealthCheck("test", HealthStatus.HEALTHY)
        checker.register(check)
        
        result = asyncio.run(checker.run_all_checks())
        
        assert result["status"] == "healthy"
        assert result["summary"]["total"] == 1
        assert result["summary"]["healthy"] == 1
    
    def test_critical_failure_makes_unhealthy(self):
        """Test que fallo crítico hace sistema unhealthy."""
        checker = HealthChecker()
        
        checker.register(MockHealthCheck("db", HealthStatus.UNHEALTHY, critical=True))
        checker.register(MockHealthCheck("cache", HealthStatus.HEALTHY, critical=True))
        
        result = asyncio.run(checker.run_all_checks())
        
        assert result["status"] == "unhealthy"
        assert result["summary"]["unhealthy"] == 1
    
    def test_degraded_status(self):
        """Test estado degradado."""
        checker = HealthChecker()
        
        checker.register(MockHealthCheck("db", HealthStatus.DEGRADED, critical=False))
        checker.register(MockHealthCheck("app", HealthStatus.HEALTHY))
        
        result = asyncio.run(checker.run_all_checks())
        
        assert result["status"] == "degraded"
        assert result["summary"]["degraded"] == 1
    
    def test_all_healthy(self):
        """Test todos los checks saludables."""
        checker = HealthChecker()
        
        checker.register(MockHealthCheck("db", HealthStatus.HEALTHY))
        checker.register(MockHealthCheck("cache", HealthStatus.HEALTHY))
        checker.register(MockHealthCheck("queue", HealthStatus.HEALTHY))
        
        result = asyncio.run(checker.run_all_checks())
        
        assert result["status"] == "healthy"
        assert result["summary"]["healthy"] == 3
    
    def test_get_last_result(self):
        """Test obtener último resultado."""
        checker = HealthChecker()
        
        # Sin checks ejecutados
        assert checker.get_last_result("test") is None
    
    def test_is_healthy_no_checks(self):
        """Test is_healthy sin checks."""
        checker = HealthChecker()
        
        assert checker.is_healthy()  # Sin checks = saludable por defecto


class TestDiskSpaceHealthCheck:
    """Tests para DiskSpaceHealthCheck."""
    
    def test_disk_space_check(self):
        """Test check de espacio en disco."""
        from infrastructure.observability.health.health_checker import DiskSpaceHealthCheck
        
        check = DiskSpaceHealthCheck("/", warning_threshold=99, critical_threshold=99.9)
        result = asyncio.run(check.check())
        
        assert result.component == "disk_space"
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "usage_percent" in result.metadata


class TestMemoryHealthCheck:
    """Tests para MemoryHealthCheck."""
    
    def test_memory_check(self):
        """Test check de memoria."""
        from infrastructure.observability.health.health_checker import MemoryHealthCheck
        
        check = MemoryHealthCheck(warning_threshold=99, critical_threshold=99.9)
        result = asyncio.run(check.check())
        
        assert result.component == "memory"
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "percent_used" in result.metadata
