"""
Metrics Collector

Sistema de métricas Prometheus para el Portal Energético MME.
"""

from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading
import time
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """Valor de una métrica."""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Colector de métricas para Prometheus.
    
    Soporta:
    - Counters (incrementales)
    - Gauges (valores instantáneos)
    - Histograms (distribución de valores)
    - Summaries (percentiles)
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        
        # Métricas
        self._counters: Dict[str, Dict[str, float]] = {}  # name -> {labels_hash -> value}
        self._gauges: Dict[str, Dict[str, MetricValue]] = {}  # name -> {labels_hash -> value}
        self._histograms: Dict[str, Dict[str, List[float]]] = {}  # name -> {labels_hash -> values}
        self._summaries: Dict[str, Dict[str, deque]] = {}  # name -> {labels_hash -> deque of values}
        
        # Metadatos
        self._descriptions: Dict[str, str] = {}
        self._buckets: Dict[str, List[float]] = {}
        
        # Callbacks
        self._custom_collectors: List[Callable] = []
    
    def _get_labels_hash(self, labels: Dict[str, str]) -> str:
        """Genera hash para labels."""
        return ','.join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def describe(self, name: str, description: str) -> None:
        """Describe una métrica."""
        self._descriptions[name] = description
    
    def counter(self, name: str, description: str, labels: Dict[str, str] = None, value: float = 1.0) -> None:
        """
        Incrementa un contador.
        
        Args:
            name: Nombre de la métrica
            description: Descripción
            labels: Labels opcionales
            value: Valor a incrementar (default 1)
        """
        self._descriptions[name] = description
        labels = labels or {}
        labels_hash = self._get_labels_hash(labels)
        
        with self._lock:
            if name not in self._counters:
                self._counters[name] = {}
            
            if labels_hash not in self._counters[name]:
                self._counters[name][labels_hash] = 0.0
            
            self._counters[name][labels_hash] += value
    
    def gauge(self, name: str, description: str, value: float, labels: Dict[str, str] = None) -> None:
        """
        Establece un valor gauge.
        
        Args:
            name: Nombre de la métrica
            description: Descripción
            value: Valor actual
            labels: Labels opcionales
        """
        self._descriptions[name] = description
        labels = labels or {}
        labels_hash = self._get_labels_hash(labels)
        
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}
            
            self._gauges[name][labels_hash] = MetricValue(
                value=value,
                labels=labels
            )
    
    def histogram(self, name: str, description: str, value: float, 
                  labels: Dict[str, str] = None, buckets: List[float] = None) -> None:
        """
        Registra un valor en un histograma.
        
        Args:
            name: Nombre de la métrica
            description: Descripción
            value: Valor a registrar
            labels: Labels opcionales
            buckets: Buckets personalizados (default [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
        """
        self._descriptions[name] = description
        default_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        self._buckets[name] = buckets or default_buckets
        labels = labels or {}
        labels_hash = self._get_labels_hash(labels)
        
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {}
            
            if labels_hash not in self._histograms[name]:
                self._histograms[name][labels_hash] = []
            
            self._histograms[name][labels_hash].append(value)
            
            # Limitar memoria (mantener últimos 10000 valores)
            if len(self._histograms[name][labels_hash]) > 10000:
                self._histograms[name][labels_hash] = self._histograms[name][labels_hash][-10000:]
    
    def summary(self, name: str, description: str, value: float, 
                labels: Dict[str, str] = None, max_age: int = 600) -> None:
        """
        Registra un valor en un summary (percentiles).
        
        Args:
            name: Nombre de la métrica
            description: Descripción
            value: Valor a registrar
            labels: Labels opcionales
            max_age: Segundos para mantener valores (default 10 minutos)
        """
        self._descriptions[name] = description
        labels = labels or {}
        labels_hash = self._get_labels_hash(labels)
        now = datetime.utcnow()
        
        with self._lock:
            if name not in self._summaries:
                self._summaries[name] = {}
            
            if labels_hash not in self._summaries[name]:
                self._summaries[name][labels_hash] = deque(maxlen=1000)
            
            self._summaries[name][labels_hash].append((now, value))
            
            # Limpiar valores antiguos
            cutoff = now - timedelta(seconds=max_age)
            self._summaries[name][labels_hash] = deque(
                [(t, v) for t, v in self._summaries[name][labels_hash] if t > cutoff],
                maxlen=1000
            )
    
    def time(self, name: str, description: str, labels: Dict[str, str] = None) -> 'TimerContext':
        """
        Crea un context manager para medir tiempo de ejecución.
        
        Args:
            name: Nombre de la métrica
            description: Descripción
            labels: Labels opcionales
            
        Returns:
            TimerContext para usar con 'with'
        """
        return TimerContext(self, name, description, labels or {})
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Obtiene todas las métricas en formato Prometheus."""
        with self._lock:
            metrics = []
            
            # Counters
            for name, values in self._counters.items():
                desc = self._descriptions.get(name, '')
                metrics.append(f"# HELP {name} {desc}")
                metrics.append(f"# TYPE {name} counter")
                for labels_hash, value in values.items():
                    if labels_hash:
                        metrics.append(f'{name}{{{labels_hash}}} {value}')
                    else:
                        metrics.append(f'{name} {value}')
            
            # Gauges
            for name, values in self._gauges.items():
                desc = self._descriptions.get(name, '')
                metrics.append(f"# HELP {name} {desc}")
                metrics.append(f"# TYPE {name} gauge")
                for labels_hash, metric in values.items():
                    labels_str = self._get_labels_hash(metric.labels)
                    if labels_str:
                        metrics.append(f'{name}{{{labels_str}}} {metric.value}')
                    else:
                        metrics.append(f'{name} {metric.value}')
            
            # Histograms
            for name, values in self._histograms.items():
                desc = self._descriptions.get(name, '')
                buckets = self._buckets.get(name, [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
                
                for labels_hash, vals in values.items():
                    metrics.append(f"# HELP {name} {desc}")
                    metrics.append(f"# TYPE {name} histogram")
                    
                    # Calcular buckets
                    for bucket in buckets:
                        count = sum(1 for v in vals if v <= bucket)
                        metrics.append(f'{name}_bucket{{le="{bucket}"}} {count}')
                    
                    # +Inf bucket
                    metrics.append(f'{name}_bucket{{le="+Inf"}} {len(vals)}')
                    metrics.append(f'{name}_sum {sum(vals)}')
                    metrics.append(f'{name}_count {len(vals)}')
            
            # Summaries
            for name, values in self._summaries.items():
                desc = self._descriptions.get(name, '')
                
                for labels_hash, vals_deque in values.items():
                    if not vals_deque:
                        continue
                    
                    metrics.append(f"# HELP {name} {desc}")
                    metrics.append(f"# TYPE {name} summary")
                    
                    vals = [v for _, v in vals_deque]
                    vals.sort()
                    
                    # Calcular percentiles
                    for quantile in [0.5, 0.9, 0.99]:
                        idx = int(len(vals) * quantile)
                        if idx < len(vals):
                            metrics.append(f'{name}{{quantile="{quantile}"}} {vals[idx]}')
                    
                    metrics.append(f'{name}_sum {sum(vals)}')
                    metrics.append(f'{name}_count {len(vals)}')
            
            return '\n'.join(metrics)
    
    def register_custom_collector(self, collector: Callable) -> None:
        """Registra un colector de métricas personalizado."""
        self._custom_collectors.append(collector)


class TimerContext:
    """Context manager para medir tiempo de ejecución."""
    
    def __init__(self, collector: MetricsCollector, name: str, description: str, labels: Dict[str, str]):
        self.collector = collector
        self.name = name
        self.description = description
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        self.collector.histogram(self.name, self.description, elapsed, self.labels)
        return False


# Instancia global
metrics_collector = MetricsCollector()
