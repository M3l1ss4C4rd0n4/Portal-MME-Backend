"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         CACHE MANAGER - REDIS                                 ║
║                                                                               ║
║  Sistema de caché centralizado para el Portal Energético                     ║
║  Implementa Flask-Caching con backend Redis                                  ║
║                                                                               ║
║  Uso:                                                                          ║
║     from core.cache_manager import cache, cache_dataframe, memoize            ║
║                                                                               ║
║     @cache.memoize(timeout=300)                                              ║
║     def get_expensive_data():                                                ║
║         return expensive_query()                                             ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""
import hashlib
import json
import pickle
import logging
from functools import wraps
from datetime import timedelta
from typing import Any, Callable, Optional, Union

import redis
from flask_caching import Cache

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE REDIS
# ═══════════════════════════════════════════════════════════════════════════════

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'decode_responses': False,  # Necesario para pickle
    'socket_connect_timeout': 5,
    'socket_timeout': 5,
    'health_check_interval': 30,
}

# Cliente Redis directo para operaciones avanzadas
redis_client = redis.Redis(**REDIS_CONFIG)


def check_redis_connection() -> bool:
    """
    Verifica si Redis está disponible.
    
    Returns:
        bool: True si Redis responde, False en caso contrario
    """
    try:
        return redis_client.ping()
    except Exception as e:
        logger.warning(f"⚠️ Redis no disponible: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# FLASK-CACHING CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

cache_config = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}/{REDIS_CONFIG['db']}",
    'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutos por defecto
    'CACHE_KEY_PREFIX': 'mme_portal_',
}

# Instancia de Flask-Caching (se inicializa en app_factory)
cache = Cache(config=cache_config)


# ═══════════════════════════════════════════════════════════════════════════════
# DECORADORES PERSONALIZADOS
# ═══════════════════════════════════════════════════════════════════════════════

def memoize(
    timeout: int = 300,
    key_prefix: str = "memo",
    unless: Optional[Callable] = None,
):
    """
    Decorador para cachear resultados de funciones.
    
    Args:
        timeout: Tiempo en segundos que durará el caché
        key_prefix: Prefijo para la clave de caché
        unless: Función que si retorna True, no usa caché
    
    Returns:
        Decorador configurado
    
    Ejemplo:
        @memoize(timeout=600, key_prefix="generacion")
        def get_generacion_data(fecha_inicio, fecha_fin):
            return query_database(fecha_inicio, fecha_fin)
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Verificar si debemos saltar caché
            if unless and unless():
                return f(*args, **kwargs)
            
            # Generar clave única
            cache_key = _generate_cache_key(f, key_prefix, args, kwargs)
            
            # Intentar obtener del caché
            try:
                cached_value = redis_client.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"✅ Cache HIT: {cache_key}")
                    return pickle.loads(cached_value)
            except Exception as e:
                logger.warning(f"⚠️ Error leyendo caché: {e}")
            
            # Ejecutar función
            result = f(*args, **kwargs)
            
            # Guardar en caché
            try:
                redis_client.setex(
                    cache_key,
                    timedelta(seconds=timeout),
                    pickle.dumps(result)
                )
                logger.debug(f"💾 Cache SET: {cache_key}")
            except Exception as e:
                logger.warning(f"⚠️ Error guardando caché: {e}")
            
            return result
        
        # Adjuntar función para invalidar
        wrapper.cache_key_prefix = key_prefix
        wrapper.invalidate = lambda: invalidate_cache_pattern(f"{key_prefix}:*")
        
        return wrapper
    return decorator


def cache_dataframe(
    timeout: int = 300,
    key_prefix: str = "df",
):
    """
    Decorador especializado para cachear DataFrames de pandas.
    
    Args:
        timeout: Tiempo en segundos
        key_prefix: Prefijo para la clave
    
    Ejemplo:
        @cache_dataframe(timeout=600, key_prefix="generacion_fuentes")
        def get_generacion_por_fuente(fecha_inicio, fecha_fin):
            return pd.read_sql(query, engine)
    """
    return memoize(timeout=timeout, key_prefix=key_prefix)


def cache_json(
    timeout: int = 300,
    key_prefix: str = "json",
):
    """
    Decorador para cachear datos JSON serializables.
    Usa JSON en lugar de pickle para mejor interoperabilidad.
    
    Args:
        timeout: Tiempo en segundos
        key_prefix: Prefijo para la clave
    
    Ejemplo:
        @cache_json(timeout=300, key_prefix="api_response")
        def get_api_data(endpoint):
            return requests.get(endpoint).json()
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            cache_key = _generate_cache_key(f, key_prefix, args, kwargs)
            
            try:
                cached_value = redis_client.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"✅ JSON Cache HIT: {cache_key}")
                    return json.loads(cached_value.decode('utf-8'))
            except Exception as e:
                logger.warning(f"⚠️ Error leyendo JSON caché: {e}")
            
            result = f(*args, **kwargs)
            
            try:
                redis_client.setex(
                    cache_key,
                    timedelta(seconds=timeout),
                    json.dumps(result, default=str)
                )
                logger.debug(f"💾 JSON Cache SET: {cache_key}")
            except Exception as e:
                logger.warning(f"⚠️ Error guardando JSON caché: {e}")
            
            return result
        
        wrapper.invalidate = lambda: invalidate_cache_pattern(f"{key_prefix}:*")
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_cache_key(
    func: Callable,
    prefix: str,
    args: tuple,
    kwargs: dict
) -> str:
    """
    Genera una clave de caché única basada en función y argumentos.
    
    Args:
        func: Función a cachear
        prefix: Prefijo para la clave
        args: Argumentos posicionales
        kwargs: Argumentos nombrados
    
    Returns:
        String con la clave de caché
    """
    # Crear string representativo
    key_parts = [
        func.__module__,
        func.__name__,
        str(args),
        str(sorted(kwargs.items()))
    ]
    key_string = "|".join(key_parts)
    
    # Generar hash
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    
    return f"{prefix}:{key_hash}"


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalida todas las claves que coincidan con el patrón.
    
    Args:
        pattern: Patrón de claves (ej: "generacion:*")
    
    Returns:
        Número de claves eliminadas
    
    Ejemplo:
        # Invalidar toda la caché de generación
        invalidate_cache_pattern("generacion:*")
        
        # Invalidar toda la caché
        invalidate_cache_pattern("*")
    """
    try:
        keys = redis_client.keys(pattern)
        if keys:
            count = redis_client.delete(*keys)
            logger.info(f"🗑️ Invalidadas {count} claves con patrón: {pattern}")
            return count
        return 0
    except Exception as e:
        logger.error(f"❌ Error invalidando caché: {e}")
        return 0


def invalidate_cache_by_prefix(prefix: str) -> int:
    """
    Invalida todas las claves con un prefijo específico.
    
    Args:
        prefix: Prefijo de las claves a invalidar
    
    Returns:
        Número de claves eliminadas
    """
    return invalidate_cache_pattern(f"{prefix}:*")


def get_cache_stats() -> dict:
    """
    Obtiene estadísticas del caché de Redis.
    
    Returns:
        Dict con estadísticas
    """
    try:
        info = redis_client.info()
        return {
            'used_memory_human': info.get('used_memory_human', 'N/A'),
            'total_keys': redis_client.dbsize(),
            'connected_clients': info.get('connected_clients', 0),
            'uptime_in_days': info.get('uptime_in_days', 0),
            'hit_rate': info.get('keyspace_hits', 0) / max(
                info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1), 1
            ),
        }
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {e}")
        return {}


def clear_all_cache() -> bool:
    """
    Limpia TODA la caché de Redis. ¡Usar con precaución!
    
    Returns:
        bool: True si se limpió correctamente
    """
    try:
        redis_client.flushdb()
        logger.warning("🗑️ TODA la caché ha sido limpiada")
        return True
    except Exception as e:
        logger.error(f"❌ Error limpiando caché: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT MANAGERS
# ═══════════════════════════════════════════════════════════════════════════════

class CacheContext:
    """
    Context manager para operaciones con caché.
    
    Ejemplo:
        with CacheContext() as ctx:
            data = ctx.get_or_compute("my_key", lambda: expensive_operation())
    """
    
    def __init__(self, timeout: int = 300, prefix: str = "ctx"):
        self.timeout = timeout
        self.prefix = prefix
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def get(self, key: str) -> Any:
        """Obtiene valor del caché."""
        full_key = f"{self.prefix}:{key}"
        try:
            value = redis_client.get(full_key)
            return pickle.loads(value) if value else None
        except Exception:
            return None
    
    def set(self, key: str, value: Any) -> bool:
        """Guarda valor en caché."""
        full_key = f"{self.prefix}:{key}"
        try:
            redis_client.setex(
                full_key,
                timedelta(seconds=self.timeout),
                pickle.dumps(value)
            )
            return True
        except Exception:
            return False
    
    def get_or_compute(self, key: str, compute_func: Callable) -> Any:
        """Obtiene del caché o computa si no existe."""
        cached = self.get(key)
        if cached is not None:
            return cached
        
        result = compute_func()
        self.set(key, result)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def init_cache(app):
    """
    Inicializa el sistema de caché en la aplicación Flask.
    
    Args:
        app: Instancia de la aplicación Flask
    """
    # Inicializar Flask-Caching
    cache.init_app(app)
    
    # Verificar conexión a Redis
    if check_redis_connection():
        logger.info("✅ Redis caché conectado correctamente")
    else:
        logger.warning("⚠️ Redis no disponible, el caché no funcionará")
    
    return cache


# Alias para compatibilidad
setup_cache = init_cache
