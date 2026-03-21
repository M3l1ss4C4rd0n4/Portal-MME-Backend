"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         CACHE MODULE - Fase 4 Performance                     ║
║                                                                               ║
║  Sistema de caché centralizado con Redis para optimizar performance          ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    from core.cache import cache_manager, cached
    
    # Decorador para funciones
    @cached(ttl=300)  # 5 minutos
    def get_expensive_data(param):
        return expensive_query(param)
    
    # Uso manual
    cache_manager.set("key", value, ttl=600)
    value = cache_manager.get("key")
"""

import json
import pickle
import hashlib
from infrastructure.logging.logger import get_logger
from functools import wraps
from typing import Any, Optional, Callable, Union
from datetime import datetime, timedelta

from infrastructure.cache.redis_client import get_redis_client

logger = get_logger(__name__)


class CacheManager:
    """
    Gestor de caché centralizado con Redis.
    
    Proporciona:
    - Caché de objetos Python (con pickle)
    - Caché de JSON (strings)
    - Decoradores para funciones
    - Invalidación de caché
    - Estadísticas de uso
    """
    
    # TTL por defecto para diferentes tipos de datos (en segundos)
    DEFAULT_TTLS = {
        'metrics': 300,        # 5 minutos - métricas en tiempo real
        'predictions': 3600,   # 1 hora - predicciones no cambian frecuentemente
        'catalogs': 86400,     # 24 horas - catálogos son estáticos
        'kpi': 600,           # 10 minutos - KPIs del dashboard
        'default': 300,       # 5 minutos - default
    }
    
    def __init__(self):
        self._redis = None
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
        }
    
    def _get_redis(self):
        """Obtiene cliente Redis (lazy initialization)."""
        if self._redis is None:
            try:
                self._redis = get_redis_client()
            except Exception as e:
                logger.warning(f"Redis no disponible: {e}")
                return None
        return self._redis
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Genera una clave de caché única.
        
        Args:
            prefix: Prefijo para la clave
            args: Argumentos posicionales
            kwargs: Argumentos nombrados
            
        Returns:
            Clave única para caché
        """
        # Crear representación de los argumentos
        key_data = f"{prefix}:{str(args)}:{str(sorted(kwargs.items()))}"
        
        # Hashear para claves muy largas
        if len(key_data) > 200:
            hash_suffix = hashlib.md5(key_data.encode()).hexdigest()[:16]
            key_data = f"{prefix}:{hash_suffix}"
        
        return key_data
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor del caché.
        
        Args:
            key: Clave del caché
            default: Valor por defecto si no existe
            
        Returns:
            Valor cacheado o default
        """
        redis = self._get_redis()
        if redis is None:
            return default
        
        try:
            # Intentar obtener como JSON primero
            value = redis.get(f"json:{key}")
            if value:
                self._stats['hits'] += 1
                data = json.loads(value)
                # Reconstruir DataFrame si fue serializado con marcador de tipo
                if isinstance(data, dict) and data.get("__dataframe__"):
                    import pandas as pd
                    return pd.DataFrame(data.get("records", []))
                return data
            
            # Intentar obtener como pickle
            value = redis.get(f"pickle:{key}")
            if value:
                self._stats['hits'] += 1
                return pickle.loads(value)
            
            self._stats['misses'] += 1
            return default
            
        except Exception as e:
            logger.warning(f"Error leyendo caché: {e}")
            return default
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        use_pickle: bool = False
    ) -> bool:
        """
        Guarda un valor en el caché.
        
        Args:
            key: Clave del caché
            value: Valor a guardar
            ttl: Tiempo de vida en segundos
            use_pickle: Usar pickle en lugar de JSON
            
        Returns:
            True si se guardó correctamente
        """
        redis = self._get_redis()
        if redis is None:
            return False
        
        ttl = ttl or self.DEFAULT_TTLS['default']
        
        try:
            if use_pickle:
                serialized = pickle.dumps(value)
                redis.setex(f"pickle:{key}", ttl, serialized)
            else:
                # DataFrames must use a typed JSON marker — decode_responses=True
                # on the Redis client prevents storing binary pickle directly.
                try:
                    import pandas as pd
                    if isinstance(value, pd.DataFrame):
                        serialized = json.dumps({
                            "__dataframe__": True,
                            "records": value.to_dict(orient="records"),
                        })
                    else:
                        serialized = json.dumps(value)
                    redis.setex(f"json:{key}", ttl, serialized)
                except (TypeError, ValueError):
                    # Non-serializable objects: skip caching, log warning
                    logger.debug(f"Valor no cacheable para clave {key}: {type(value).__name__}")
                    return False
            
            self._stats['sets'] += 1
            return True
            
        except Exception as e:
            logger.warning(f"Error guardando en caché: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Elimina una clave del caché.
        
        Args:
            key: Clave a eliminar
            
        Returns:
            True si se eliminó
        """
        redis = self._get_redis()
        if redis is None:
            return False
        
        try:
            redis.delete(f"json:{key}")
            redis.delete(f"pickle:{key}")
            self._stats['deletes'] += 1
            return True
        except Exception as e:
            logger.warning(f"Error eliminando caché: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Elimina claves que coincidan con un patrón.
        
        Args:
            pattern: Patrón de búsqueda (ej: "metrics:*")
            
        Returns:
            Número de claves eliminadas
        """
        redis = self._get_redis()
        if redis is None:
            return 0
        
        try:
            # Buscar en ambos prefijos
            keys = []
            keys.extend(redis.keys(f"json:{pattern}"))
            keys.extend(redis.keys(f"pickle:{pattern}"))
            
            if keys:
                return redis.delete(*keys)
            return 0
            
        except Exception as e:
            logger.warning(f"Error eliminando patrón: {e}")
            return 0
    
    def get_or_set(
        self,
        key: str,
        getter: Callable[[], Any],
        ttl: Optional[int] = None,
        use_pickle: bool = False
    ) -> Any:
        """
        Obtiene del caché o computa y guarda.
        
        Args:
            key: Clave del caché
            getter: Función para obtener el valor si no está en caché
            ttl: Tiempo de vida
            use_pickle: Usar pickle
            
        Returns:
            Valor (del caché o computado)
        """
        # Intentar obtener del caché
        value = self.get(key)
        if value is not None:
            return value
        
        # Computar y guardar
        value = getter()
        self.set(key, value, ttl, use_pickle)
        return value
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de uso del caché."""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (
            (self._stats['hits'] / total_requests * 100)
            if total_requests > 0 else 0
        )
        
        return {
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'sets': self._stats['sets'],
            'deletes': self._stats['deletes'],
            'hit_rate_percent': round(hit_rate, 2),
            'total_requests': total_requests,
        }
    
    def clear_stats(self):
        """Limpia las estadísticas."""
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
        }
    
    def flush_all(self) -> bool:
        """
        ⚠️  LIMPIA TODO EL CACHÉ. Usar con precaución.
        
        Returns:
            True si se limpió correctamente
        """
        redis = self._get_redis()
        if redis is None:
            return False
        
        try:
            # Solo limpiar claves de nuestra aplicación
            keys = redis.keys("json:*") + redis.keys("pickle:*")
            if keys:
                redis.delete(*keys)
            logger.warning("Caché limpiado completamente")
            return True
        except Exception as e:
            logger.error(f"Error limpiando caché: {e}")
            return False


# Instancia global
cache_manager = CacheManager()


def cached(
    ttl: Optional[int] = None,
    prefix: Optional[str] = None,
    use_pickle: bool = False,
    key_func: Optional[Callable] = None
):
    """
    Decorador para cachear resultados de funciones.
    
    Args:
        ttl: Tiempo de vida en segundos
        prefix: Prefijo para la clave de caché
        use_pickle: Usar pickle para serialización
        key_func: Función para generar la clave (recibe *args, **kwargs)
        
    Uso:
        @cached(ttl=300, prefix="metrics")
        def get_metric_data(metric_id, start_date, end_date):
            return db.query(...)
    """
    def decorator(func: Callable) -> Callable:
        cache_prefix = prefix or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_key(cache_prefix, *args, **kwargs)
            
            # Intentar obtener del caché
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Caché hit: {cache_key}")
                return cached_value
            
            # Ejecutar función y guardar en caché
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl, use_pickle)
            logger.debug(f"Caché set: {cache_key}")
            
            return result
        
        # Agregar método para invalidar caché
        wrapper.cache_delete = lambda *args, **kwargs: cache_manager.delete(
            key_func(*args, **kwargs) if key_func else cache_manager._generate_key(cache_prefix, *args, **kwargs)
        )
        
        return wrapper
    return decorator


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalida caché por patrón.
    
    Args:
        pattern: Patrón de búsqueda
        
    Returns:
        Número de claves eliminadas
    """
    return cache_manager.delete_pattern(pattern)


# Funciones de conveniencia para tipos específicos

def cache_metrics(key: str, value: Any, ttl: int = 300) -> bool:
    """Guarda métricas en caché (TTL: 5 min por defecto)."""
    return cache_manager.set(f"metrics:{key}", value, ttl or CacheManager.DEFAULT_TTLS['metrics'])


def get_cached_metrics(key: str, default: Any = None) -> Any:
    """Obtiene métricas del caché."""
    return cache_manager.get(f"metrics:{key}", default)


def cache_prediction(key: str, value: Any, ttl: int = 3600) -> bool:
    """Guarda predicciones en caché (TTL: 1 hora por defecto)."""
    return cache_manager.set(f"predictions:{key}", value, ttl or CacheManager.DEFAULT_TTLS['predictions'])


def get_cached_prediction(key: str, default: Any = None) -> Any:
    """Obtiene predicciones del caché."""
    return cache_manager.get(f"predictions:{key}", default)


def cache_kpi(key: str, value: Any, ttl: int = 600) -> bool:
    """Guarda KPIs en caché (TTL: 10 min por defecto)."""
    return cache_manager.set(f"kpi:{key}", value, ttl or CacheManager.DEFAULT_TTLS['kpi'])


def get_cached_kpi(key: str, default: Any = None) -> Any:
    """Obtiene KPIs del caché."""
    return cache_manager.get(f"kpi:{key}", default)


__all__ = [
    'CacheManager',
    'cache_manager',
    'cached',
    'invalidate_cache_pattern',
    'cache_metrics',
    'get_cached_metrics',
    'cache_prediction',
    'get_cached_prediction',
    'cache_kpi',
    'get_cached_kpi',
]
