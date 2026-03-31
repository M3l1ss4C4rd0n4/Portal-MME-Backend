"""
Tests para el sistema de métricas.
"""

import pytest
from datetime import datetime
from infrastructure.observability.metrics import MetricsCollector, MetricValue


class TestMetricsCollector:
    """Tests para MetricsCollector."""
    
    def test_counter_increment(self):
        """Test incremento de contador."""
        collector = MetricsCollector()
        
        collector.counter("requests_total", "Total requests", {"method": "GET"}, 1)
        collector.counter("requests_total", "Total requests", {"method": "GET"}, 1)
        collector.counter("requests_total", "Total requests", {"method": "POST"}, 1)
        
        assert collector._counters["requests_total"]["method=GET"] == 2
        assert collector._counters["requests_total"]["method=POST"] == 1
    
    def test_gauge_set(self):
        """Test establecimiento de gauge."""
        collector = MetricsCollector()
        
        collector.gauge("cpu_usage", "CPU usage", 50.0, {"core": "0"})
        collector.gauge("cpu_usage", "CPU usage", 75.0, {"core": "0"})
        
        assert collector._gauges["cpu_usage"]["core=0"].value == 75.0
    
    def test_histogram_record(self):
        """Test registro en histograma."""
        collector = MetricsCollector()
        
        collector.histogram("request_duration", "Request duration", 0.1)
        collector.histogram("request_duration", "Request duration", 0.5)
        collector.histogram("request_duration", "Request duration", 1.0)
        
        assert len(collector._histograms["request_duration"][""]) == 3
    
    def test_timer_context(self):
        """Test timer context manager."""
        collector = MetricsCollector()
        
        import time
        with collector.time("operation_duration", "Operation duration"):
            time.sleep(0.01)
        
        assert "operation_duration" in collector._histograms
        assert len(collector._histograms["operation_duration"][""]) == 1
    
    def test_get_all_metrics_format(self):
        """Test formato de métricas Prometheus."""
        collector = MetricsCollector()
        
        collector.counter("test_total", "Test counter", {}, 5)
        collector.gauge("test_value", "Test gauge", 42.0)
        
        metrics = collector.get_all_metrics()
        
        assert "# HELP test_total Test counter" in metrics
        assert "# TYPE test_total counter" in metrics
        assert "test_total 5" in metrics
        assert "# TYPE test_value gauge" in metrics
        assert "test_value 42.0" in metrics
    
    def test_multiple_labels(self):
        """Test múltiples labels."""
        collector = MetricsCollector()
        
        collector.counter("requests", "Requests", {"method": "GET", "status": "200"}, 1)
        collector.counter("requests", "Requests", {"method": "POST", "status": "201"}, 1)
        
        # Verificar que se manejan correctamente
        assert len(collector._counters["requests"]) == 2


class TestDecorators:
    """Tests para decoradores de métricas."""
    
    def test_timed_decorator(self):
        """Test decorador timed."""
        from infrastructure.observability.metrics.decorators import timed
        
        @timed(description="Test function")
        def slow_function():
            import time
            time.sleep(0.01)
            return "done"
        
        result = slow_function()
        
        assert result == "done"
        # La métrica debería haberse registrado
    
    def test_counter_decorator_success(self):
        """Test decorador counter con éxito."""
        from infrastructure.observability.metrics.decorators import counter
        
        @counter(description="Test calls")
        def test_function():
            return "success"
        
        result = test_function()
        
        assert result == "success"
    
    def test_counter_decorator_error(self):
        """Test decorador counter con error."""
        from infrastructure.observability.metrics.decorators import counter
        
        @counter(description="Test calls")
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_function()
    
    def test_gauge_decorator(self):
        """Test decorador gauge."""
        from infrastructure.observability.metrics.decorators import gauge
        
        @gauge(description="Cache size")
        def get_size():
            return 100
        
        result = get_size()
        
        assert result == 100
