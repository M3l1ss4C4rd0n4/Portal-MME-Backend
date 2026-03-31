"""
Distributed Tracer

Sistema de tracing distribuido para el Portal Energético MME.
Similar a Jaeger/Zipkin para seguimiento de requests.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from contextvars import ContextVar
import uuid
import time
import threading
import logging

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Tipo de span."""
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"
    INTERNAL = "internal"


class SpanStatus(Enum):
    """Estado de un span."""
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class SpanContext:
    """Contexto de tracing."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    parent_span_id: Optional[str] = None
    sampled: bool = True
    baggage: Dict[str, str] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        """Verifica si el contexto es válido."""
        return bool(self.trace_id and self.span_id)
    
    def to_w3c_traceparent(self) -> str:
        """Convierte a formato W3C traceparent."""
        flags = "01" if self.sampled else "00"
        return f"00-{self.trace_id.replace('-', '')}-{self.span_id}-{flags}"
    
    @classmethod
    def from_w3c_traceparent(cls, header: str) -> Optional['SpanContext']:
        """Parsea header W3C traceparent."""
        try:
            parts = header.split('-')
            if len(parts) >= 3:
                trace_id = f"{parts[1][:8]}-{parts[1][8:12]}-{parts[1][12:16]}-{parts[1][16:]}"
                span_id = parts[2]
                sampled = len(parts) > 3 and parts[3] == "01"
                return cls(trace_id=trace_id, span_id=span_id, sampled=sampled)
        except Exception:
            pass
        return None


@dataclass
class Span:
    """Representa una operación en el trace."""
    name: str
    context: SpanContext
    kind: SpanKind = SpanKind.INTERNAL
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    links: List[SpanContext] = field(default_factory=list)
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Establece un atributo."""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None) -> None:
        """Añade un evento al span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {}
        })
    
    def set_status(self, status: SpanStatus, description: str = None) -> None:
        """Establece el estado del span."""
        self.status = status
        if description:
            self.set_attribute("status.description", description)
    
    def record_exception(self, exception: Exception) -> None:
        """Registra una excepción."""
        self.set_status(SpanStatus.ERROR)
        self.set_attribute("error.type", type(exception).__name__)
        self.set_attribute("error.message", str(exception))
        self.add_event("exception", {
            "exception.type": type(exception).__name__,
            "exception.message": str(exception)
        })
    
    def end(self) -> None:
        """Finaliza el span."""
        self.end_time = datetime.utcnow()
    
    def duration_ms(self) -> float:
        """Calcula duración en milisegundos."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return (datetime.utcnow() - self.start_time).total_seconds() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return {
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.context.parent_span_id,
            "kind": self.kind.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms(),
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events
        }


class SpanExporter(ABC):
    """Interfaz para exportar spans."""
    
    @abstractmethod
    def export(self, spans: List[Span]) -> bool:
        """Exporta spans."""
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cierra el exporter."""
        pass


class ConsoleSpanExporter(SpanExporter):
    """Exporter que imprime spans en consola."""
    
    def export(self, spans: List[Span]) -> bool:
        for span in spans:
            logger.info(f"[TRACE] {span.name}: {span.duration_ms():.2f}ms - {span.status.value}")
        return True
    
    def shutdown(self) -> None:
        pass


class InMemorySpanExporter(SpanExporter):
    """Exporter que guarda spans en memoria para testing."""
    
    def __init__(self):
        self.spans: List[Span] = []
    
    def export(self, spans: List[Span]) -> bool:
        self.spans.extend(spans)
        return True
    
    def shutdown(self) -> None:
        pass
    
    def clear(self) -> None:
        self.spans.clear()


class JaegerSpanExporter(SpanExporter):
    """Exporter para Jaeger."""
    
    def __init__(self, agent_host: str = "localhost", agent_port: int = 6831):
        self.agent_host = agent_host
        self.agent_port = agent_port
        self._buffer: List[Span] = []
        self._lock = threading.Lock()
    
    def export(self, spans: List[Span]) -> bool:
        with self._lock:
            self._buffer.extend(spans)
            # En implementación real, enviaría a Jaeger via UDP/HTTP
            # Por ahora solo logueamos
            for span in spans:
                logger.debug(f"[JAEGER] Exporting span: {span.name}")
        return True
    
    def shutdown(self) -> None:
        pass


# Context variable para el span actual
_current_span: ContextVar[Optional[Span]] = ContextVar('current_span', default=None)


class Tracer:
    """
    Tracer distribuido para seguimiento de requests.
    
    Características:
    - W3C Trace Context compatible
    - Span anidados
    - Atributos y eventos
    - Múltiples exporters
    """
    
    def __init__(self, service_name: str = "portal-mme"):
        self.service_name = service_name
        self._exporters: List[SpanExporter] = []
        self._lock = threading.Lock()
        self._batch: List[Span] = []
        self._batch_size = 100
        self._shutdown = False
    
    def add_exporter(self, exporter: SpanExporter) -> None:
        """Añade un exporter."""
        self._exporters.append(exporter)
    
    def get_current_span(self) -> Optional[Span]:
        """Obtiene el span actual."""
        return _current_span.get()
    
    def start_span(
        self,
        name: str,
        context: Optional[SpanContext] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Dict[str, Any] = None
    ) -> Span:
        """
        Inicia un nuevo span.
        
        Args:
            name: Nombre del span
            context: Contexto padre (None para crear nuevo trace)
            kind: Tipo de span
            attributes: Atributos iniciales
        """
        parent_span = self.get_current_span()
        
        if context is not None:
            # Usar contexto proporcionado, crear nuevo span hijo con ese padre
            new_context = SpanContext(
                trace_id=context.trace_id,
                parent_span_id=context.span_id,
                sampled=context.sampled
            )
        elif parent_span is not None:
            # Crear span hijo del span actual
            new_context = SpanContext(
                trace_id=parent_span.context.trace_id,
                parent_span_id=parent_span.context.span_id,
                sampled=parent_span.context.sampled
            )
        else:
            # Crear nuevo trace
            new_context = SpanContext()
        
        span = Span(
            name=name,
            context=new_context,
            kind=kind,
            attributes=attributes or {}
        )
        
        # Establecer atributos por defecto
        span.set_attribute("service.name", self.service_name)
        span.set_attribute("span.kind", kind.value)
        
        return span
    
    def start_as_current_span(
        self,
        name: str,
        context: Optional[SpanContext] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Dict[str, Any] = None
    ) -> 'SpanContextManager':
        """
        Inicia un span y lo establece como contexto actual.
        
        Uso:
            with tracer.start_as_current_span("operation") as span:
                do_work()
        """
        span = self.start_span(name, context, kind, attributes)
        return SpanContextManager(self, span)
    
    def end_span(self, span: Span) -> None:
        """Finaliza un span y lo exporta."""
        span.end()
        
        with self._lock:
            if not self._shutdown:
                self._batch.append(span)
                
                if len(self._batch) >= self._batch_size:
                    self._flush_batch()
    
    def _flush_batch(self) -> None:
        """Envía el batch a los exporters."""
        if not self._batch:
            return
        
        spans_to_export = self._batch.copy()
        self._batch = []
        
        for exporter in self._exporters:
            try:
                exporter.export(spans_to_export)
            except Exception as e:
                logger.error(f"Failed to export spans: {e}")
    
    def force_flush(self) -> None:
        """Fuerza el envío de spans pendientes."""
        with self._lock:
            self._flush_batch()
    
    def shutdown(self) -> None:
        """Cierra el tracer."""
        with self._lock:
            self._shutdown = True
            self._flush_batch()
            
            for exporter in self._exporters:
                try:
                    exporter.shutdown()
                except Exception as e:
                    logger.error(f"Failed to shutdown exporter: {e}")


class SpanContextManager:
    """Context manager para spans."""
    
    def __init__(self, tracer: Tracer, span: Span):
        self.tracer = tracer
        self.span = span
        self._token = None
    
    def __enter__(self) -> Span:
        self._token = _current_span.set(self.span)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.span.record_exception(exc_val)
        self.tracer.end_span(self.span)
        _current_span.reset(self._token)


# Instancia global
tracer = Tracer()
