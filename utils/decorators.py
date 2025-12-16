"""
Decoradores de utilidad para Portal Energético MME

Este módulo proporciona decoradores para manejo de errores, retry,
cache, timing y otras funcionalidades transversales.

Decoradores disponibles:
    - @handle_errors: Manejo centralizado de errores
    - @retry: Reintentar operaciones fallidas
    - @timing: Medir tiempo de ejecución
    - @cache_result: Cachear resultados de funciones
    - @require_api: Validar que API esté disponible

Uso:
    from utils.decorators import handle_errors, retry, timing
    
    @handle_errors(default_return=[])
    @retry(max_attempts=3)
    @timing
    def fetch_data():
        return api.get_data()
"""

import functools
import time
from typing import Any, Callable, Optional, Type, Union
from datetime import datetime, timedelta

from utils.logger import setup_logger
from utils.exceptions import (
    PortalEnergeticoError,
    APIError,
    DataError,
    CacheError
)

logger = setup_logger(__name__)


# ============================================================================
# MANEJO DE ERRORES
# ============================================================================

def handle_errors(
    exceptions: Union[Type[Exception], tuple] = Exception,
    default_return: Any = None,
    log_level: str = "error",
    reraise: bool = False
):
    """
    Decorador para manejo centralizado de errores.
    
    Args:
        exceptions: Excepción o tupla de excepciones a capturar
        default_return: Valor a retornar si hay error
        log_level: Nivel de log ("debug", "info", "warning", "error")
        reraise: Si True, re-lanza la excepción después de loggear
    
    Ejemplo:
        @handle_errors(exceptions=APIError, default_return=[])
        def fetch_data():
            return api.get_data()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                # Loggear según nivel
                log_func = getattr(logger, log_level, logger.error)
                log_func(
                    f"Error en {func.__name__}: {e}",
                    exc_info=True,
                    extra={'function': func.__name__, 'args': args[:3], 'kwargs': list(kwargs.keys())}
                )
                
                if reraise:
                    raise
                
                return default_return
        
        return wrapper
    return decorator


# ============================================================================
# RETRY
# ============================================================================

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], tuple] = Exception,
    on_retry: Optional[Callable] = None
):
    """
    Decorador para reintentar operaciones fallidas con backoff exponencial.
    
    Args:
        max_attempts: Número máximo de intentos
        delay: Delay inicial entre intentos (segundos)
        backoff: Factor multiplicador para cada reintento (exponencial)
        exceptions: Excepciones que deben activar retry
        on_retry: Función opcional a llamar antes de cada reintento
    
    Ejemplo:
        @retry(max_attempts=3, delay=1, backoff=2)
        def fetch_from_api():
            return requests.get(url).json()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} falló después de {max_attempts} intentos: {e}",
                            exc_info=True
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} falló (intento {attempt}/{max_attempts}), "
                        f"reintentando en {current_delay:.1f}s: {e}"
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            # No debería llegar aquí, pero por si acaso
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


# ============================================================================
# TIMING
# ============================================================================

def timing(log_level: str = "info", threshold: Optional[float] = None):
    """
    Decorador para medir y loggear tiempo de ejecución de funciones.
    
    Args:
        log_level: Nivel de log para el timing
        threshold: Si se especifica, solo loggea si el tiempo excede el threshold (segundos)
    
    Ejemplo:
        @timing(threshold=1.0)  # Solo loggea si tarda más de 1 segundo
        def slow_function():
            time.sleep(2)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                # Solo loggear si excede threshold o si no hay threshold
                if threshold is None or elapsed > threshold:
                    log_func = getattr(logger, log_level, logger.info)
                    log_func(f"⏱️ {func.__name__} completado en {elapsed:.2f}s")
                
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"⏱️ {func.__name__} falló después de {elapsed:.2f}s: {e}")
                raise
        
        return wrapper
    
    if callable(log_level):
        # Si se usa @timing sin paréntesis
        func = log_level
        log_level = "info"
        return decorator(func)
    
    return decorator


# ============================================================================
# CACHE DE RESULTADOS
# ============================================================================

def cache_result(ttl: int = 3600):
    """
    Decorador simple para cachear resultados de funciones en memoria.
    
    Args:
        ttl: Time-to-live del cache en segundos
    
    Nota: Este es un cache en memoria simple. Para cache persistente,
          usar el CacheManager del proyecto.
    
    Ejemplo:
        @cache_result(ttl=600)  # Cache por 10 minutos
        def get_expensive_data(param):
            return expensive_operation(param)
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Crear key del cache
            cache_key = str(args) + str(kwargs)
            
            # Verificar si está en cache y no ha expirado
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if datetime.now() < timestamp + timedelta(seconds=ttl):
                    logger.debug(f"Cache hit para {func.__name__}")
                    return result
                else:
                    logger.debug(f"Cache expirado para {func.__name__}")
                    del cache[cache_key]
            
            # Ejecutar función y cachear resultado
            logger.debug(f"Cache miss para {func.__name__}, ejecutando función")
            result = func(*args, **kwargs)
            cache[cache_key] = (result, datetime.now())
            
            return result
        
        # Añadir método para limpiar cache
        wrapper.clear_cache = lambda: cache.clear()
        
        return wrapper
    return decorator


# ============================================================================
# VALIDACIÓN DE API
# ============================================================================

def require_api(default_return: Any = None):
    """
    Decorador para validar que la API esté disponible antes de ejecutar.
    
    Args:
        default_return: Valor a retornar si API no está disponible
    
    Ejemplo:
        @require_api(default_return=[])
        def fetch_metrics():
            return api.get_metrics()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from utils._xm import get_objetoAPI
            
            api = get_objetoAPI()
            if api is None:
                logger.warning(f"{func.__name__} requiere API pero no está disponible")
                return default_return
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# VALIDACIÓN DE PARÁMETROS
# ============================================================================

def validate_params(**validators):
    """
    Decorador para validar parámetros de entrada de funciones.
    
    Args:
        **validators: Diccionario de param_name -> función validadora
    
    Ejemplo:
        def is_valid_date(value):
            return isinstance(value, str) and len(value) == 10
        
        @validate_params(start_date=is_valid_date, end_date=is_valid_date)
        def fetch_data(start_date, end_date):
            return data
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Obtener nombres de parámetros
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Validar cada parámetro
            for param_name, validator in validators.items():
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if not validator(value):
                        from utils.exceptions import InvalidParameterError
                        raise InvalidParameterError(
                            f"Parámetro '{param_name}' no es válido",
                            details={'valor': value, 'funcion': func.__name__}
                        )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# DEPRECATION
# ============================================================================

def deprecated(reason: str = "", version: str = ""):
    """
    Decorador para marcar funciones como deprecated.
    
    Args:
        reason: Razón de la deprecación
        version: Versión en que se deprecó
    
    Ejemplo:
        @deprecated(reason="Use fetch_data_v2 instead", version="2.0")
        def fetch_data():
            return old_implementation()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            msg = f"⚠️ {func.__name__} está deprecated"
            if version:
                msg += f" desde versión {version}"
            if reason:
                msg += f": {reason}"
            
            logger.warning(msg)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# COMBINACIÓN DE DECORADORES
# ============================================================================

def safe_api_call(max_attempts: int = 3, default_return: Any = None):
    """
    Decorador combinado para llamadas seguras a API con retry y manejo de errores.
    
    Combina @retry, @handle_errors y @timing.
    
    Ejemplo:
        @safe_api_call(max_attempts=3, default_return=[])
        def fetch_from_xm():
            return api.get_data()
    """
    def decorator(func: Callable) -> Callable:
        # Aplicar decoradores en orden: timing -> retry -> handle_errors
        decorated = func
        decorated = timing(decorated)
        decorated = retry(max_attempts=max_attempts, exceptions=(APIError, ConnectionError, TimeoutError))(decorated)
        decorated = handle_errors(exceptions=Exception, default_return=default_return)(decorated)
        return decorated
    
    return decorator


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("Testing decoradores...\n")
    
    # Test 1: handle_errors
    @handle_errors(default_return="ERROR")
    def test_error():
        raise ValueError("Test error")
    
    result = test_error()
    print(f"✓ handle_errors: {result}")
    
    # Test 2: retry
    attempt_count = 0
    
    @retry(max_attempts=3, delay=0.1, backoff=1)
    def test_retry():
        global attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ConnectionError("Not ready")
        return "Success"
    
    result = test_retry()
    print(f"✓ retry: {result} (después de {attempt_count} intentos)")
    
    # Test 3: timing
    @timing(threshold=0.05)
    def test_timing():
        time.sleep(0.1)
        return "Done"
    
    result = test_timing()
    print(f"✓ timing: {result}")
    
    # Test 4: cache_result
    call_count = 0
    
    @cache_result(ttl=60)
    def test_cache(x):
        global call_count
        call_count += 1
        return x * 2
    
    r1 = test_cache(5)
    r2 = test_cache(5)  # Debe usar cache
    print(f"✓ cache_result: {r1}, {r2} (llamadas reales: {call_count})")
    
    print("\n✅ Todos los decoradores funcionan correctamente")
