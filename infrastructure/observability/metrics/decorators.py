"""
Metrics Decorators

Decoradores para instrumentar funciones automáticamente.
"""

import functools
import time
from typing import Callable, Optional, Dict, Any
from .collector import metrics_collector


def timed(name: Optional[str] = None, description: Optional[str] = None, 
          labels: Optional[Dict[str, str]] = None):
    """
    Decorador para medir tiempo de ejecución de una función.
    
    Args:
        name: Nombre de la métrica (default: function_name_duration_seconds)
        description: Descripción de la métrica
        labels: Labels estáticos adicionales
        
    Example:
        @timed(description="Tiempo de consulta a base de datos")
        def get_data():
            return db.query()
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or f"{func.__name__}_duration_seconds"
        metric_desc = description or f"Tiempo de ejecución de {func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.time() - start_time
                # Extraer labels dinámicas si se proporciona una función
                dynamic_labels = labels.copy() if labels else {}
                metrics_collector.histogram(
                    metric_name, 
                    metric_desc, 
                    elapsed,
                    dynamic_labels
                )
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.time() - start_time
                dynamic_labels = labels.copy() if labels else {}
                metrics_collector.histogram(
                    metric_name,
                    metric_desc,
                    elapsed,
                    dynamic_labels
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    
    return decorator


def counter(name: Optional[str] = None, description: Optional[str] = None,
            labels: Optional[Dict[str, str]] = None, value: float = 1.0,
            on_error: bool = False):
    """
    Decorador para contar llamadas a una función.
    
    Args:
        name: Nombre de la métrica
        description: Descripción
        labels: Labels estáticos
        value: Valor a incrementar
        on_error: Si True, solo cuenta cuando hay excepción
        
    Example:
        @counter(description="Número de solicitudes procesadas")
        def process_request():
            return do_work()
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or f"{func.__name__}_total"
        metric_desc = description or f"Contador de llamadas a {func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if not on_error:
                    dynamic_labels = labels.copy() if labels else {}
                    dynamic_labels['status'] = 'success'
                    metrics_collector.counter(metric_name, metric_desc, dynamic_labels, value)
                return result
            except Exception as e:
                dynamic_labels = labels.copy() if labels else {}
                dynamic_labels['status'] = 'error'
                dynamic_labels['error_type'] = type(e).__name__
                metrics_collector.counter(metric_name, metric_desc, dynamic_labels, value)
                raise
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                if not on_error:
                    dynamic_labels = labels.copy() if labels else {}
                    dynamic_labels['status'] = 'success'
                    metrics_collector.counter(metric_name, metric_desc, dynamic_labels, value)
                return result
            except Exception as e:
                dynamic_labels = labels.copy() if labels else {}
                dynamic_labels['status'] = 'error'
                dynamic_labels['error_type'] = type(e).__name__
                metrics_collector.counter(metric_name, metric_desc, dynamic_labels, value)
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    
    return decorator


def gauge(name: Optional[str] = None, description: Optional[str] = None,
          value_fn: Optional[Callable] = None):
    """
    Decorador para actualizar un gauge con el resultado de la función.
    
    Args:
        name: Nombre de la métrica
        description: Descripción
        value_fn: Función para extraer el valor del resultado
        
    Example:
        @gauge(description="Número de registros en cache")
        def get_cache_size():
            return len(cache)
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or f"{func.__name__}_value"
        metric_desc = description or f"Valor de {func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            value = value_fn(result) if value_fn else result
            if isinstance(value, (int, float)):
                metrics_collector.gauge(metric_name, metric_desc, float(value))
            return result
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            value = value_fn(result) if value_fn else result
            if isinstance(value, (int, float)):
                metrics_collector.gauge(metric_name, metric_desc, float(value))
            return result
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    
    return decorator


# Import asyncio para detectar funciones async
import asyncio
