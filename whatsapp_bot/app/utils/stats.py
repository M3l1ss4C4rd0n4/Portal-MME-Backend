"""
Estadísticas del bot
"""
import redis
from datetime import datetime, timedelta
from typing import Dict
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Cliente Redis para stats
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=3,  # DB separada para stats
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)


def increment_stat(stat_name: str, value: int = 1):
    """
    Incrementa una estadística
    """
    try:
        redis_client.incr(f"stats:{stat_name}", value)
    except Exception as e:
        logger.error(f"Error incrementando stat {stat_name}: {str(e)}")


def get_bot_stats() -> Dict:
    """
    Obtiene estadísticas del bot
    """
    try:
        stats = {
            "messages_received": int(redis_client.get("stats:messages_received") or 0),
            "messages_sent": int(redis_client.get("stats:messages_sent") or 0),
            "messages_failed": int(redis_client.get("stats:messages_failed") or 0),
            "charts_generated": int(redis_client.get("stats:charts_generated") or 0),
            "ai_queries": int(redis_client.get("stats:ai_queries") or 0),
            "active_users_24h": get_active_users_count(hours=24),
            "uptime": get_uptime()
        }
        
        # Calcular tasa de éxito
        total = stats["messages_received"]
        if total > 0:
            stats["success_rate"] = round((stats["messages_sent"] / total) * 100, 2)
        else:
            stats["success_rate"] = 100.0
        
        return stats
    
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return {"error": str(e)}


def get_active_users_count(hours: int = 24) -> int:
    """
    Cuenta usuarios activos en las últimas X horas
    """
    try:
        # Obtener todos los usuarios que han interactuado
        pattern = "user:*:last_interaction"
        keys = redis_client.keys(pattern)
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        active = 0
        
        for key in keys:
            last_interaction = redis_client.get(key)
            if last_interaction:
                interaction_time = datetime.fromisoformat(last_interaction)
                if interaction_time > cutoff_time:
                    active += 1
        
        return active
    
    except Exception as e:
        logger.error(f"Error contando usuarios activos: {str(e)}")
        return 0


def get_uptime() -> str:
    """
    Obtiene tiempo de actividad del bot
    """
    try:
        start_time = redis_client.get("stats:start_time")
        if not start_time:
            # Primera vez, guardar tiempo actual
            start_time = datetime.now().isoformat()
            redis_client.set("stats:start_time", start_time)
            return "Just started"
        
        start = datetime.fromisoformat(start_time)
        delta = datetime.now() - start
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"
    
    except Exception as e:
        logger.error(f"Error calculando uptime: {str(e)}")
        return "unknown"
