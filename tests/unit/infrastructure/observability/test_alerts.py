"""
Tests para el sistema de alertas.
"""

import pytest
from datetime import datetime
from infrastructure.observability.alerts import (
    AlertManager, Alert, AlertSeverity, AlertRule
)


class TestAlert:
    """Tests para Alert."""
    
    def test_alert_creation(self):
        """Test creación de alerta."""
        alert = Alert(
            title="Test Alert",
            description="Test description",
            severity=AlertSeverity.HIGH,
            source="test"
        )
        
        assert alert.title == "Test Alert"
        assert alert.severity == AlertSeverity.HIGH
        assert not alert.acknowledged
        assert not alert.resolved
    
    def test_to_dict(self):
        """Test conversión a diccionario."""
        alert = Alert(
            title="Test",
            description="Desc",
            severity=AlertSeverity.MEDIUM,
            source="source"
        )
        
        data = alert.to_dict()
        
        assert data["title"] == "Test"
        assert data["severity"] == "medium"
        assert "timestamp" in data


class TestAlertRule:
    """Tests para AlertRule."""
    
    def test_rule_evaluation_true(self):
        """Test evaluación que dispara alerta."""
        rule = AlertRule(
            name="high_error_rate",
            condition=lambda data: data["errors"] > 10,
            alert_factory=lambda data: Alert(
                title="High Errors",
                description=f"Errors: {data['errors']}",
                severity=AlertSeverity.HIGH,
                source="test"
            )
        )
        
        alert = rule.evaluate({"errors": 15})
        
        assert alert is not None
        assert alert.title == "High Errors"
    
    def test_rule_evaluation_false(self):
        """Test evaluación que no dispara alerta."""
        rule = AlertRule(
            name="high_error_rate",
            condition=lambda data: data["errors"] > 10,
            alert_factory=lambda data: Alert(title="Test", description="", severity=AlertSeverity.LOW, source="test")
        )
        
        alert = rule.evaluate({"errors": 5})
        
        assert alert is None
    
    def test_cooldown(self):
        """Test cooldown entre alertas."""
        rule = AlertRule(
            name="test",
            condition=lambda data: True,
            alert_factory=lambda data: Alert(title="Test", description="", severity=AlertSeverity.LOW, source="test"),
            cooldown_seconds=60
        )
        
        # Primera evaluación dispara
        alert1 = rule.evaluate({})
        assert alert1 is not None
        
        # Segunda evaluación no dispara (cooldown)
        alert2 = rule.evaluate({})
        assert alert2 is None


class TestAlertManager:
    """Tests para AlertManager."""
    
    def test_send_alert(self):
        """Test envío de alerta."""
        manager = AlertManager()
        
        # Añadir canal de log para test
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        alert = Alert(
            title="Test Alert",
            description="Test",
            severity=AlertSeverity.MEDIUM,
            source="test"
        )
        
        result = manager.send_alert(alert)
        
        assert result is True
    
    def test_deduplication(self):
        """Test deduplicación de alertas."""
        manager = AlertManager()
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        # Crear alerta con ID específico
        alert1 = Alert(id="test-dedup-1", title="Same Alert", description="Test", severity=AlertSeverity.LOW, source="test")
        alert2 = Alert(id="test-dedup-1", title="Same Alert", description="Test", severity=AlertSeverity.LOW, source="test")
        
        result1 = manager.send_alert(alert1)
        result2 = manager.send_alert(alert2)
        
        assert result1 is True
        assert result2 is False  # Deduplicada por mismo ID
    
    def test_get_active_alerts(self):
        """Test obtener alertas activas."""
        manager = AlertManager()
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        manager.send_alert(Alert(
            title="Alert 1",
            description="Test",
            severity=AlertSeverity.CRITICAL,
            source="test"
        ))
        
        alerts = manager.get_active_alerts(severity=AlertSeverity.CRITICAL)
        
        assert len(alerts) == 1
        assert alerts[0].title == "Alert 1"
    
    def test_acknowledge_alert(self):
        """Test reconocimiento de alerta."""
        manager = AlertManager()
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        alert = Alert(title="Test", description="", severity=AlertSeverity.LOW, source="test")
        manager.send_alert(alert)
        
        result = manager.acknowledge_alert(alert.id)
        
        assert result is True
        assert manager._alerts[alert.id].acknowledged
    
    def test_resolve_alert(self):
        """Test resolución de alerta."""
        manager = AlertManager()
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        alert = Alert(title="Test", description="", severity=AlertSeverity.LOW, source="test")
        manager.send_alert(alert)
        
        result = manager.resolve_alert(alert.id)
        
        assert result is True
        assert manager._alerts[alert.id].resolved
        assert manager._alerts[alert.id].resolved_at is not None
    
    def test_evaluate_rules(self):
        """Test evaluación de reglas."""
        manager = AlertManager()
        from infrastructure.observability.alerts.alert_manager import LogNotificationChannel
        manager.add_channel(LogNotificationChannel())
        
        rule = AlertRule(
            name="test_rule",
            condition=lambda data: data["trigger"] == True,
            alert_factory=lambda data: Alert(
                title="Triggered",
                description="",
                severity=AlertSeverity.MEDIUM,
                source="rule"
            )
        )
        manager.add_rule(rule)
        
        alerts = manager.evaluate_rules({"trigger": True})
        
        assert len(alerts) == 1
        assert alerts[0].title == "Triggered"


class TestCreateDefaultRules:
    """Tests para reglas por defecto."""
    
    def test_default_rules_creation(self):
        """Test creación de reglas por defecto."""
        from infrastructure.observability.alerts.alert_manager import create_default_rules
        
        rules = create_default_rules()
        
        assert len(rules) == 3  # error_rate, latency, memory
        
        rule_names = [r.name for r in rules]
        assert "high_error_rate" in rule_names
        assert "high_latency" in rule_names
        assert "high_memory" in rule_names
    
    def test_error_rate_rule(self):
        """Test regla de tasa de error."""
        from infrastructure.observability.alerts.alert_manager import create_default_rules
        
        rules = create_default_rules()
        error_rule = next(r for r in rules if r.name == "high_error_rate")
        
        # Debe disparar con error rate > 10%
        alert = error_rule.evaluate({"error_rate": 0.15})
        assert alert is not None
        assert alert.severity == AlertSeverity.HIGH
        
        # No debe disparar con error rate < 10%
        no_alert = error_rule.evaluate({"error_rate": 0.05})
        assert no_alert is None
    
    def test_latency_rule(self):
        """Test regla de latencia."""
        from infrastructure.observability.alerts.alert_manager import create_default_rules
        
        rules = create_default_rules()
        latency_rule = next(r for r in rules if r.name == "high_latency")
        
        # Debe disparar con latencia > 5000ms
        alert = latency_rule.evaluate({"p95_latency_ms": 6000})
        assert alert is not None
        
        # No debe disparar con latencia < 5000ms
        no_alert = latency_rule.evaluate({"p95_latency_ms": 3000})
        assert no_alert is None
    
    def test_memory_rule(self):
        """Test regla de memoria."""
        from infrastructure.observability.alerts.alert_manager import create_default_rules
        
        rules = create_default_rules()
        memory_rule = next(r for r in rules if r.name == "high_memory")
        
        # Debe disparar con uso de memoria > 90%
        alert = memory_rule.evaluate({"memory_percent": 95})
        assert alert is not None
        assert alert.severity == AlertSeverity.HIGH
        
        # No debe disparar con uso de memoria < 90%
        no_alert = memory_rule.evaluate({"memory_percent": 80})
        assert no_alert is None
