"""
Tests para el sistema de tracing distribuido.
"""

import pytest
from datetime import datetime
from infrastructure.observability.tracing import Tracer, Span, SpanContext, SpanKind, SpanStatus


class TestSpanContext:
    """Tests para SpanContext."""
    
    def test_default_creation(self):
        """Test creación con valores por defecto."""
        ctx = SpanContext()
        
        assert ctx.trace_id
        assert ctx.span_id
        assert ctx.sampled is True
        assert ctx.parent_span_id is None
    
    def test_to_w3c_traceparent(self):
        """Test conversión a W3C traceparent."""
        ctx = SpanContext(
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b7ad6b7169203331",
            sampled=True
        )
        
        traceparent = ctx.to_w3c_traceparent()
        
        assert traceparent.startswith("00-")
        assert "b7ad6b7169203331" in traceparent
    
    def test_from_w3c_traceparent(self):
        """Test parseo de W3C traceparent."""
        header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        
        ctx = SpanContext.from_w3c_traceparent(header)
        
        assert ctx is not None
        assert ctx.span_id == "b7ad6b7169203331"
        assert ctx.sampled is True


class TestSpan:
    """Tests para Span."""
    
    def test_span_creation(self):
        """Test creación de span."""
        ctx = SpanContext()
        span = Span("test_operation", ctx)
        
        assert span.name == "test_operation"
        assert span.context == ctx
        assert span.status == SpanStatus.UNSET
        assert not span.end_time
    
    def test_set_attribute(self):
        """Test establecer atributo."""
        span = Span("test", SpanContext())
        
        span.set_attribute("key", "value")
        
        assert span.attributes["key"] == "value"
    
    def test_add_event(self):
        """Test añadir evento."""
        span = Span("test", SpanContext())
        
        span.add_event("event_name", {"detail": "value"})
        
        assert len(span.events) == 1
        assert span.events[0]["name"] == "event_name"
    
    def test_record_exception(self):
        """Test registrar excepción."""
        span = Span("test", SpanContext())
        exception = ValueError("Test error")
        
        span.record_exception(exception)
        
        assert span.status == SpanStatus.ERROR
        assert span.attributes["error.type"] == "ValueError"
    
    def test_end(self):
        """Test finalizar span."""
        span = Span("test", SpanContext())
        
        span.end()
        
        assert span.end_time is not None
    
    def test_duration_ms(self):
        """Test cálculo de duración."""
        import time
        span = Span("test", SpanContext())
        
        time.sleep(0.01)
        duration = span.duration_ms()
        
        assert duration >= 10  # Al menos 10ms


class TestTracer:
    """Tests para Tracer."""
    
    def test_start_span(self):
        """Test iniciar span."""
        tracer = Tracer()
        
        span = tracer.start_span("operation")
        
        assert span.name == "operation"
        assert span.context.trace_id
    
    def test_start_span_with_parent(self):
        """Test iniciar span con padre."""
        tracer = Tracer()
        parent_ctx = SpanContext()
        
        span = tracer.start_span("child", context=parent_ctx)
        
        assert span.context.trace_id == parent_ctx.trace_id
        assert span.context.parent_span_id == parent_ctx.span_id
    
    def test_end_span(self):
        """Test finalizar span."""
        tracer = Tracer()
        span = tracer.start_span("test")
        
        tracer.end_span(span)
        
        assert span.end_time is not None
    
    def test_exporter(self):
        """Test exporter de spans."""
        from infrastructure.observability.tracing.tracer import InMemorySpanExporter
        
        tracer = Tracer()
        exporter = InMemorySpanExporter()
        tracer.add_exporter(exporter)
        
        span = tracer.start_span("test")
        tracer.end_span(span)
        tracer.force_flush()
        
        assert len(exporter.spans) == 1
    
    def test_shutdown(self):
        """Test shutdown del tracer."""
        tracer = Tracer()
        
        tracer.shutdown()
        
        # Después de shutdown no se deben aceptar más spans
        # o deben manejarse de forma especial


class TestSpanContextManager:
    """Tests para SpanContextManager."""
    
    def test_context_manager(self):
        """Test uso con with."""
        from infrastructure.observability.tracing.tracer import InMemorySpanExporter
        
        tracer = Tracer()
        exporter = InMemorySpanExporter()
        tracer.add_exporter(exporter)
        
        with tracer.start_as_current_span("operation") as span:
            span.set_attribute("test", "value")
        
        tracer.force_flush()
        
        assert len(exporter.spans) == 1
        assert exporter.spans[0].attributes.get("test") == "value"
    
    def test_exception_handling(self):
        """Test manejo de excepciones."""
        from infrastructure.observability.tracing.tracer import InMemorySpanExporter
        
        tracer = Tracer()
        exporter = InMemorySpanExporter()
        tracer.add_exporter(exporter)
        
        try:
            with tracer.start_as_current_span("operation") as span:
                raise ValueError("Test error")
        except ValueError:
            pass
        
        tracer.force_flush()
        
        assert len(exporter.spans) == 1
        assert exporter.spans[0].status == SpanStatus.ERROR
