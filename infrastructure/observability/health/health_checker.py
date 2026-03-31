"""
Health Checker

Sistema de health checks para monitorear componentes del Portal Energético MME.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import asyncio
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Estados de salud."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthResult:
    """Resultado de un health check."""
    status: HealthStatus
    component: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    response_time_ms: float = 0.0


class HealthCheck(ABC):
    """Interfaz base para health checks."""
    
    def __init__(self, name: str, critical: bool = True, timeout: float = 5.0):
        """
        Inicializa el health check.
        
        Args:
            name: Nombre del componente
            critical: Si es True, fallo afecta estado general
            timeout: Timeout en segundos
        """
        self.name = name
        self.critical = critical
        self.timeout = timeout
    
    @abstractmethod
    async def check(self) -> HealthResult:
        """Ejecuta el health check."""
        pass


class DatabaseHealthCheck(HealthCheck):
    """Health check para base de datos."""
    
    def __init__(self, db_connection_fn: Callable, **kwargs):
        super().__init__("database", **kwargs)
        self.db_connection_fn = db_connection_fn
    
    async def check(self) -> HealthResult:
        import time
        start = time.time()
        
        try:
            # Intentar conexión
            conn = await asyncio.wait_for(
                asyncio.to_thread(self.db_connection_fn),
                timeout=self.timeout
            )
            
            response_time = (time.time() - start) * 1000
            
            return HealthResult(
                status=HealthStatus.HEALTHY,
                component=self.name,
                message="Database connection successful",
                response_time_ms=response_time,
                metadata={"connection_time_ms": response_time}
            )
        except asyncio.TimeoutError:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message="Database connection timeout",
                response_time_ms=self.timeout * 1000,
                metadata={"timeout_seconds": self.timeout}
            )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message=f"Database connection failed: {str(e)}",
                response_time_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)}
            )


class RedisHealthCheck(HealthCheck):
    """Health check para Redis."""
    
    def __init__(self, redis_client: Any, **kwargs):
        super().__init__("redis", **kwargs)
        self.redis_client = redis_client
    
    async def check(self) -> HealthResult:
        import time
        start = time.time()
        
        try:
            # Ping a Redis
            pong = await asyncio.wait_for(
                asyncio.to_thread(self.redis_client.ping),
                timeout=self.timeout
            )
            
            response_time = (time.time() - start) * 1000
            
            if pong:
                # Obtener info adicional
                info = {}
                try:
                    info = await asyncio.wait_for(
                        asyncio.to_thread(lambda: self.redis_client.info()),
                        timeout=2.0
                    )
                except:
                    pass
                
                return HealthResult(
                    status=HealthStatus.HEALTHY,
                    component=self.name,
                    message="Redis is responsive",
                    response_time_ms=response_time,
                    metadata={
                        "used_memory_human": info.get("used_memory_human", "unknown"),
                        "connected_clients": info.get("connected_clients", 0)
                    }
                )
            else:
                return HealthResult(
                    status=HealthStatus.UNHEALTHY,
                    component=self.name,
                    message="Redis ping failed",
                    response_time_ms=response_time
                )
        except asyncio.TimeoutError:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message="Redis connection timeout",
                response_time_ms=self.timeout * 1000
            )
        except Exception as e:
                return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message=f"Redis connection failed: {str(e)}",
                response_time_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)}
            )


class DiskSpaceHealthCheck(HealthCheck):
    """Health check para espacio en disco."""
    
    def __init__(self, path: str = "/", warning_threshold: float = 80.0,
                 critical_threshold: float = 95.0, **kwargs):
        super().__init__("disk_space", **kwargs)
        self.path = path
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def check(self) -> HealthResult:
        import shutil
        import time
        start = time.time()
        
        try:
            total, used, free = shutil.disk_usage(self.path)
            usage_percent = (used / total) * 100
            response_time = (time.time() - start) * 1000
            
            if usage_percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"CRITICAL: Disk usage at {usage_percent:.1f}%"
            elif usage_percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"WARNING: Disk usage at {usage_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk usage at {usage_percent:.1f}%"
            
            return HealthResult(
                status=status,
                component=self.name,
                message=message,
                response_time_ms=response_time,
                metadata={
                    "path": self.path,
                    "usage_percent": usage_percent,
                    "total_gb": total / (1024**3),
                    "free_gb": free / (1024**3)
                }
            )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message=f"Disk check failed: {str(e)}",
                response_time_ms=(time.time() - start) * 1000
            )


class MemoryHealthCheck(HealthCheck):
    """Health check para memoria del sistema."""
    
    def __init__(self, warning_threshold: float = 80.0,
                 critical_threshold: float = 95.0, **kwargs):
        super().__init__("memory", **kwargs)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def check(self) -> HealthResult:
        import psutil
        import time
        start = time.time()
        
        try:
            memory = psutil.virtual_memory()
            response_time = (time.time() - start) * 1000
            
            if memory.percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"CRITICAL: Memory usage at {memory.percent:.1f}%"
            elif memory.percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"WARNING: Memory usage at {memory.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage at {memory.percent:.1f}%"
            
            return HealthResult(
                status=status,
                component=self.name,
                message=message,
                response_time_ms=response_time,
                metadata={
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "percent_used": memory.percent
                }
            )
        except Exception as e:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                component=self.name,
                message=f"Memory check failed: {str(e)}",
                response_time_ms=(time.time() - start) * 1000
            )


class HealthChecker:
    """
    Sistema de health checks.
    
    Gestiona múltiples health checks y proporciona un estado general del sistema.
    """
    
    def __init__(self):
        self._checks: List[HealthCheck] = []
        self._last_results: Dict[str, HealthResult] = {}
    
    def register(self, check: HealthCheck) -> None:
        """Registra un nuevo health check."""
        self._checks.append(check)
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """
        Ejecuta todos los health checks.
        
        Returns:
            Dict con estado general y resultados individuales
        """
        tasks = [check.check() for check in self._checks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        checks_results = {}
        critical_failures = 0
        degraded_count = 0
        
        for check, result in zip(self._checks, results):
            if isinstance(result, Exception):
                result = HealthResult(
                    status=HealthStatus.UNHEALTHY,
                    component=check.name,
                    message=f"Check crashed: {str(result)}"
                )
            
            checks_results[check.name] = {
                "status": result.status.value,
                "message": result.message,
                "response_time_ms": round(result.response_time_ms, 2),
                "timestamp": result.timestamp.isoformat(),
                "metadata": result.metadata
            }
            
            self._last_results[check.name] = result
            
            if result.status == HealthStatus.UNHEALTHY and check.critical:
                critical_failures += 1
            elif result.status == HealthStatus.DEGRADED:
                degraded_count += 1
        
        # Determinar estado general
        if critical_failures > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks_results,
            "summary": {
                "total": len(self._checks),
                "healthy": sum(1 for r in checks_results.values() if r["status"] == "healthy"),
                "degraded": degraded_count,
                "unhealthy": sum(1 for r in checks_results.values() if r["status"] == "unhealthy")
            }
        }
    
    def get_last_result(self, component: str) -> Optional[HealthResult]:
        """Obtiene el último resultado de un componente."""
        return self._last_results.get(component)
    
    def is_healthy(self) -> bool:
        """Verifica si el sistema está saludable."""
        return all(
            r.status == HealthStatus.HEALTHY 
            for r in self._last_results.values()
        )


# Instancia global
health_checker = HealthChecker()
