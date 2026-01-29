"""
Decoradores reutilizables para el Portal Energético MME
Incluye decoradores para cache, timing, retry, etc.
"""

import time
import functools
from typing import Callable, Optional, Any, Dict
from datetime import datetime, timedelta

# Cache simple en memoria
_cache: Dict[str, Dict[str, Any]] = {}


def cache(ttl_seconds: int = 300):
    """
    Decorador para cachear resultados de funciones
    
    Args:
        ttl_seconds: Tiempo de vida del cache en segundos (default 5 min)
    
    Ejemplo:
        @cache(ttl_seconds=300)
        def get_data():
            # Esta función se ejecutará solo una vez cada 5 minutos
            return expensive_operation()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Crear clave de cache basada en función y argumentos
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Verificar si existe en cache y no ha expirado
            if cache_key in _cache:
                cached_data = _cache[cache_key]
                if datetime.now() < cached_data['expires']:
                    return cached_data['value']
            
            # Ejecutar función y guardar en cache
            result = func(*args, **kwargs)
            
            _cache[cache_key] = {
                'value': result,
                'expires': datetime.now() + timedelta(seconds=ttl_seconds),
                'cached_at': datetime.now()
            }
            
            return result
        
        return wrapper
    return decorator


def timing(func: Callable) -> Callable:
    """
    Decorador para medir tiempo de ejecución de una función
    
    Ejemplo:
        @timing
        def slow_function():
            time.sleep(2)
            return "done"
        
        # Output: slow_function ejecutada en 2.00s
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        elapsed = end_time - start_time
        print(f"{func.__name__} ejecutada en {elapsed:.2f}s")
        
        return result
    
    return wrapper


def retry(max_attempts: int = 3, delay_seconds: float = 1.0, backoff: float = 2.0):
    """
    Decorador para reintentar una función si falla
    
    Args:
        max_attempts: Número máximo de intentos
        delay_seconds: Delay inicial entre reintentos
        backoff: Multiplicador del delay en cada reintento
    
    Ejemplo:
        @retry(max_attempts=3, delay_seconds=1, backoff=2)
        def api_call():
            # Se reintentará hasta 3 veces con delays de 1s, 2s, 4s
            return requests.get(url)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = delay_seconds
            
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    
                    if attempts >= max_attempts:
                        raise
                    
                    print(f"{func.__name__} falló (intento {attempts}/{max_attempts}). "
                          f"Reintentando en {current_delay}s...")
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            return None
        
        return wrapper
    return decorator


def log_execution(logger=None):
    """
    Decorador para loggear ejecución de una función
    
    Args:
        logger: Logger a usar (None = print)
    
    Ejemplo:
        from shared.logging.logger import get_logger
        logger = get_logger(__name__)
        
        @log_execution(logger)
        def process_data():
            return "done"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            
            if logger:
                logger.info(f"Iniciando {func_name}")
            else:
                print(f"[LOG] Iniciando {func_name}")
            
            try:
                result = func(*args, **kwargs)
                
                if logger:
                    logger.info(f"{func_name} completado exitosamente")
                else:
                    print(f"[LOG] {func_name} completado exitosamente")
                
                return result
            
            except Exception as e:
                if logger:
                    logger.error(f"{func_name} falló: {e}", exc_info=True)
                else:
                    print(f"[ERROR] {func_name} falló: {e}")
                
                raise
        
        return wrapper
    return decorator


def validate_args(**validations):
    """
    Decorador para validar argumentos de una función
    
    Args:
        **validations: Validaciones por argumento (name=validator_func)
    
    Ejemplo:
        @validate_args(age=lambda x: x > 0, name=lambda x: len(x) > 0)
        def create_user(name: str, age: int):
            return {"name": name, "age": age}
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Obtener nombres de argumentos
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Validar cada argumento
            for arg_name, validator in validations.items():
                if arg_name in bound_args.arguments:
                    value = bound_args.arguments[arg_name]
                    
                    if not validator(value):
                        raise ValueError(
                            f"Validación falló para argumento '{arg_name}' "
                            f"con valor {value}"
                        )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def singleton(cls):
    """
    Decorador para convertir una clase en Singleton
    
    Ejemplo:
        @singleton
        class Database:
            def __init__(self):
                self.connection = create_connection()
        
        # Siempre retorna la misma instancia
        db1 = Database()
        db2 = Database()
        assert db1 is db2
    """
    instances = {}
    
    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


def deprecated(message: Optional[str] = None):
    """
    Decorador para marcar funciones como deprecadas
    
    Args:
        message: Mensaje personalizado
    
    Ejemplo:
        @deprecated("Usa new_function() en su lugar")
        def old_function():
            return "old"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warning_msg = f"ADVERTENCIA: {func.__name__} está deprecada."
            if message:
                warning_msg += f" {message}"
            
            print(warning_msg)
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def clear_cache():
    """Limpia todo el cache en memoria"""
    global _cache
    _cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas del cache
    
    Returns:
        Dict con estadísticas
    """
    now = datetime.now()
    
    total = len(_cache)
    expired = sum(1 for v in _cache.values() if now >= v['expires'])
    active = total - expired
    
    return {
        'total_entries': total,
        'active_entries': active,
        'expired_entries': expired,
        'cache_keys': list(_cache.keys())
    }


if __name__ == "__main__":
    # Tests
    print("Testing decorators...")
    
    # Test cache
    @cache(ttl_seconds=1)
    def expensive_function(x):
        time.sleep(0.1)
        return x * 2
    
    start = time.time()
    result1 = expensive_function(5)  # Slow
    time1 = time.time() - start
    
    start = time.time()
    result2 = expensive_function(5)  # Fast (cached)
    time2 = time.time() - start
    
    assert result1 == result2 == 10
    assert time2 < time1, "Cache should be faster"
    
    # Test timing
    @timing
    def timed_function():
        time.sleep(0.1)
        return "done"
    
    result = timed_function()
    assert result == "done"
    
    # Test retry
    attempt_count = 0
    
    @retry(max_attempts=3, delay_seconds=0.1)
    def failing_function():
        global attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise ValueError("Not yet")
        return "success"
    
    result = failing_function()
    assert result == "success"
    assert attempt_count == 2
    
    print("✅ Decorators test passed")
