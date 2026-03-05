"""
Cliente Redis centralizado para el Portal Energético MME.

Singleton que reutiliza la misma conexión Redis en toda la aplicación.
Usado por: caché de API, caché de informe IA, Celery broker (por URL).

NO crear nuevas instancias de redis.Redis() en otros módulos.
Importar siempre desde aquí:
    from infrastructure.cache.redis_client import get_redis_client
"""

import json
import logging
from typing import Optional, Any

import redis

from core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Obtiene el cliente Redis singleton.
    
    Returns:
        redis.Redis conectado a la instancia configurada en .env
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            _redis_client.ping()
            logger.info("[REDIS] Conexión establecida — %s:%s/%s",
                        settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
        except redis.ConnectionError:
            logger.warning("[REDIS] No se pudo conectar a Redis — cache deshabilitado")
    return _redis_client


def redis_get_json(key: str) -> Optional[Any]:
    """Lee un valor JSON del cache Redis. Retorna None si no existe o hay error."""
    try:
        client = get_redis_client()
        raw = client.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("[REDIS] Error leyendo key '%s': %s", key, e)
    return None


def redis_set_json(key: str, value: Any, ttl: int = 86400) -> bool:
    """Guarda un valor JSON en Redis con TTL (default 24h). Retorna True si éxito."""
    try:
        client = get_redis_client()
        client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning("[REDIS] Error escribiendo key '%s': %s", key, e)
        return False
