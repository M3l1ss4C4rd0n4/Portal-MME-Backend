"""
Observability Routes

Endpoints para monitoreo y observabilidad del sistema.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
import asyncio

from infrastructure.observability import (
    metrics_collector,
    health_checker,
    tracer,
    alert_manager
)
from infrastructure.observability.health.health_checker import (
    DatabaseHealthCheck,
    RedisHealthCheck,
    DiskSpaceHealthCheck,
    MemoryHealthCheck
)
from infrastructure.observability.alerts.alert_manager import (
    create_default_rules,
    LogNotificationChannel
)

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics")
async def get_metrics() -> str:
    """
    Endpoint Prometheus para métricas.
    
    Returns:
        Métricas en formato Prometheus
    """
    return metrics_collector.get_all_metrics()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check completo del sistema.
    
    Returns:
        Estado de salud de todos los componentes
    """
    # Registrar checks básicos si no están registrados
    if not health_checker._checks:
        health_checker.register(DiskSpaceHealthCheck("/"))
        health_checker.register(MemoryHealthCheck())
    
    result = await health_checker.run_all_checks()
    
    # Determinar status code basado en salud
    if result["status"] == "unhealthy":
        from fastapi import status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result
        )
    
    return result


@router.get("/health/live")
async def liveness_probe() -> Dict[str, str]:
    """
    Kubernetes liveness probe.
    
    Returns:
        Estado básico del servicio
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe() -> Dict[str, Any]:
    """
    Kubernetes readiness probe.
    
    Returns:
        Estado de disponibilidad
    """
    # Verificar componentes críticos
    critical_components = []
    
    # Aquí se pueden agregar checks específicos para readiness
    
    if critical_components:
        return {
            "status": "not_ready",
            "reason": "Some critical components are not ready"
        }
    
    return {"status": "ready"}


@router.get("/traces")
async def get_traces(
    service: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Obtiene traces recientes.
    
    Args:
        service: Filtrar por servicio
        limit: Número máximo de traces
        
    Returns:
        Lista de traces
    """
    # En producción, esto consultaría Jaeger o similar
    return {
        "traces": [],
        "total": 0,
        "service": service,
        "limit": limit
    }


@router.get("/alerts")
async def get_alerts(
    severity: Optional[str] = None,
    active_only: bool = True
) -> Dict[str, Any]:
    """
    Obtiene alertas del sistema.
    
    Args:
        severity: Filtrar por severidad (critical, high, medium, low)
        active_only: Solo alertas no resueltas
        
    Returns:
        Lista de alertas
    """
    from infrastructure.observability.alerts.alert_manager import AlertSeverity
    
    # Inicializar alert manager con reglas por defecto si es necesario
    if not alert_manager._rules:
        for rule in create_default_rules():
            alert_manager.add_rule(rule)
    
    if not alert_manager._channels:
        alert_manager.add_channel(LogNotificationChannel())
    
    # Filtrar por severidad si se especifica
    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity.lower())
        except ValueError:
            pass
    
    alerts = alert_manager.get_active_alerts(severity=severity_filter)
    
    return {
        "alerts": [alert.to_dict() for alert in alerts],
        "total": len(alerts),
        "severity_filter": severity,
        "active_only": active_only
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str) -> Dict[str, bool]:
    """
    Reconoce una alerta.
    
    Args:
        alert_id: ID de la alerta
        
    Returns:
        Estado de la operación
    """
    success = alert_manager.acknowledge_alert(alert_id)
    return {"acknowledged": success}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str) -> Dict[str, bool]:
    """
    Resuelve una alerta.
    
    Args:
        alert_id: ID de la alerta
        
    Returns:
        Estado de la operación
    """
    success = alert_manager.resolve_alert(alert_id)
    return {"resolved": success}


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """
    Estado general del sistema.
    
    Returns:
        Información consolidada del sistema
    """
    health = await health_checker.run_all_checks()
    
    return {
        "status": health["status"],
        "timestamp": health["timestamp"],
        "components": {
            "health_checks": health["summary"],
            "active_alerts": len(alert_manager.get_active_alerts())
        },
        "version": "1.0.0"
    }
