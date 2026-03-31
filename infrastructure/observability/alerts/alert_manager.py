"""
Alert Manager

Sistema de alertas para notificar cuando ocurren condiciones críticas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import asyncio
import threading
import logging

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Severidad de alertas."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Alert:
    """Representa una alerta."""
    id: str = field(default_factory=lambda: str(datetime.utcnow().timestamp()))
    title: str = ""
    description: str = ""
    severity: AlertSeverity = AlertSeverity.MEDIUM
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class NotificationChannel(ABC):
    """Canal de notificación."""
    
    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Envía una alerta."""
        pass


class LogNotificationChannel(NotificationChannel):
    """Canal que loguea alertas."""
    
    def send(self, alert: Alert) -> bool:
        level = {
            AlertSeverity.CRITICAL: logging.CRITICAL,
            AlertSeverity.HIGH: logging.ERROR,
            AlertSeverity.MEDIUM: logging.WARNING,
            AlertSeverity.LOW: logging.INFO,
            AlertSeverity.INFO: logging.INFO
        }.get(alert.severity, logging.WARNING)
        
        logger.log(level, f"[ALERT] {alert.severity.value.upper()}: {alert.title} - {alert.description}")
        return True


class EmailNotificationChannel(NotificationChannel):
    """Canal de notificación por email."""
    
    def __init__(self, recipients: List[str], smtp_host: str = "localhost", smtp_port: int = 25):
        self.recipients = recipients
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
    
    async def send(self, alert: Alert) -> bool:
        # Implementación básica - en producción usar aiosmtplib
        logger.info(f"[EMAIL] Would send to {self.recipients}: {alert.title}")
        return True


class WebhookNotificationChannel(NotificationChannel):
    """Canal de notificación via webhook."""
    
    def __init__(self, webhook_url: str, headers: Dict[str, str] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}
    
    async def send(self, alert: Alert) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=alert.to_dict(),
                    headers=self.headers,
                    timeout=30
                ) as response:
                    return response.status < 400
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False


@dataclass
class AlertRule:
    """Regla para generar alertas."""
    name: str
    condition: Callable[[Any], bool]
    alert_factory: Callable[[Any], Alert]
    cooldown_seconds: int = 300  # 5 minutos por defecto
    _last_triggered: Optional[datetime] = field(default=None, init=False)
    
    def evaluate(self, data: Any) -> Optional[Alert]:
        """Evalúa la regla y retorna alerta si aplica."""
        # Verificar cooldown
        if self._last_triggered:
            elapsed = (datetime.utcnow() - self._last_triggered).total_seconds()
            if elapsed < self.cooldown_seconds:
                return None
        
        if self.condition(data):
            self._last_triggered = datetime.utcnow()
            return self.alert_factory(data)
        
        return None


class AlertManager:
    """
    Gestor de alertas.
    
    Features:
    - Múltiples canales de notificación
    - Reglas de alerta configurables
    - Deduplicación
    - Cooldown entre alertas
    """
    
    def __init__(self):
        self._channels: List[NotificationChannel] = []
        self._rules: List[AlertRule] = []
        self._alerts: Dict[str, Alert] = {}
        self._lock = threading.Lock()
        self._dedup_window_seconds = 3600  # 1 hora
    
    def add_channel(self, channel: NotificationChannel) -> None:
        """Añade un canal de notificación."""
        self._channels.append(channel)
    
    def add_rule(self, rule: AlertRule) -> None:
        """Añade una regla de alerta."""
        self._rules.append(rule)
    
    def send_alert(self, alert: Alert) -> bool:
        """
        Envía una alerta por todos los canales.
        
        Returns:
            True si se envió por al menos un canal
        """
        # Deduplicación simple - solo usar id del alert
        with self._lock:
            if alert.id in self._alerts:
                existing = self._alerts[alert.id]
                if not existing.resolved:
                    elapsed = (datetime.utcnow() - existing.timestamp).total_seconds()
                    if elapsed < self._dedup_window_seconds:
                        logger.debug(f"Alert deduplicated: {alert.title}")
                        return False
            
            self._alerts[alert.id] = alert
        
        # Enviar por todos los canales
        success = False
        for channel in self._channels:
            try:
                if asyncio.iscoroutinefunction(channel.send):
                    asyncio.create_task(channel.send(alert))
                    success = True
                else:
                    if channel.send(alert):
                        success = True
            except Exception as e:
                logger.error(f"Failed to send alert via {type(channel).__name__}: {e}")
        
        return success
    
    def evaluate_rules(self, data: Any) -> List[Alert]:
        """Evalúa todas las reglas contra los datos."""
        triggered = []
        for rule in self._rules:
            alert = rule.evaluate(data)
            if alert:
                self.send_alert(alert)
                triggered.append(alert)
        return triggered
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Obtiene alertas activas."""
        with self._lock:
            alerts = [
                a for a in self._alerts.values() 
                if not a.resolved and (severity is None or a.severity == severity)
            ]
            return sorted(alerts, key=lambda a: a.timestamp, reverse=True)
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Marca una alerta como reconocida."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].acknowledged = True
                return True
            return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Marca una alerta como resuelta."""
        with self._lock:
            if alert_id in self._alerts:
                alert = self._alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.utcnow()
                return True
            return False
    
    def clear_old_alerts(self, max_age_hours: int = 24) -> int:
        """Limpia alertas antiguas."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        with self._lock:
            old_ids = [
                alert_id for alert_id, alert in self._alerts.items()
                if alert.timestamp < cutoff
            ]
            for alert_id in old_ids:
                del self._alerts[alert_id]
            return len(old_ids)


# Import para clear_old_alerts
from datetime import timedelta

# Instancia global
alert_manager = AlertManager()


def create_default_rules() -> List[AlertRule]:
    """Crea reglas de alerta por defecto."""
    rules = []
    
    # Regla: Error rate alto
    def error_rate_condition(metrics: Dict) -> bool:
        error_rate = metrics.get("error_rate", 0)
        return error_rate > 0.1  # 10% de errores
    
    def error_rate_alert(metrics: Dict) -> Alert:
        return Alert(
            title="High Error Rate Detected",
            description=f"Error rate is {metrics.get('error_rate', 0)*100:.1f}%",
            severity=AlertSeverity.HIGH,
            source="monitoring",
            metadata=metrics
        )
    
    rules.append(AlertRule(
        name="high_error_rate",
        condition=error_rate_condition,
        alert_factory=error_rate_alert
    ))
    
    # Regla: Latencia alta
    def latency_condition(metrics: Dict) -> bool:
        p95 = metrics.get("p95_latency_ms", 0)
        return p95 > 5000  # 5 segundos
    
    def latency_alert(metrics: Dict) -> Alert:
        return Alert(
            title="High Latency Detected",
            description=f"P95 latency is {metrics.get('p95_latency_ms', 0):.0f}ms",
            severity=AlertSeverity.MEDIUM,
            source="monitoring",
            metadata=metrics
        )
    
    rules.append(AlertRule(
        name="high_latency",
        condition=latency_condition,
        alert_factory=latency_alert
    ))
    
    # Regla: Memoria alta
    def memory_condition(metrics: Dict) -> bool:
        memory_percent = metrics.get("memory_percent", 0)
        return memory_percent > 90
    
    def memory_alert(metrics: Dict) -> Alert:
        return Alert(
            title="High Memory Usage",
            description=f"Memory usage at {metrics.get('memory_percent', 0):.1f}%",
            severity=AlertSeverity.HIGH,
            source="system",
            metadata=metrics
        )
    
    rules.append(AlertRule(
        name="high_memory",
        condition=memory_condition,
        alert_factory=memory_alert
    ))
    
    return rules
