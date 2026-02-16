"""
Rate Limiting - Control de tasa de mensajes
"""
import redis
import time
import logging
from typing import Tuple
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Limita la tasa de mensajes por usuario
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=4,  # DB separada para rate limiting
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
        self.max_messages = settings.RATE_LIMIT_MESSAGES
        self.window_seconds = settings.RATE_LIMIT_WINDOW
    
    def check_rate_limit(self, user_id: str) -> Tuple[bool, int]:
        """
        Verifica si el usuario ha excedido el límite
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Tupla (allowed: bool, remaining: int)
        
        Raises:
            HTTPException: Si se excede el límite
        """
        try:
            key = f"ratelimit:{user_id}"
            
            # Obtener contador actual
            current = self.redis_client.get(key)
            
            if current is None:
                # Primera solicitud
                self.redis_client.setex(key, self.window_seconds, 1)
                return (True, self.max_messages - 1)
            
            current_count = int(current)
            
            # Verificar límite
            if current_count >= self.max_messages:
                ttl = self.redis_client.ttl(key)
                logger.warning(f"Rate limit excedido para {user_id}")
                
                raise HTTPException(
                    status_code=429,
                    detail=f"Límite de {self.max_messages} mensajes por {self.window_seconds}s excedido. "
                           f"Intenta nuevamente en {ttl} segundos."
                )
            
            # Incrementar contador
            self.redis_client.incr(key)
            remaining = self.max_messages - current_count - 1
            
            return (True, remaining)
        
        except HTTPException:
            raise
        
        except Exception as e:
            logger.error(f"Error en rate limiting: {str(e)}")
            # En caso de error, permitir el mensaje
            return (True, self.max_messages)
    
    def reset_user_limit(self, user_id: str):
        """
        Resetea el límite para un usuario (admin)
        """
        try:
            key = f"ratelimit:{user_id}"
            self.redis_client.delete(key)
            logger.info(f"Rate limit reseteado para {user_id}")
        except Exception as e:
            logger.error(f"Error reseteando rate limit: {str(e)}")
    
    def get_user_usage(self, user_id: str) -> dict:
        """
        Obtiene info de uso del usuario
        """
        try:
            key = f"ratelimit:{user_id}"
            current = self.redis_client.get(key)
            ttl = self.redis_client.ttl(key)
            
            if current is None:
                return {
                    "used": 0,
                    "limit": self.max_messages,
                    "remaining": self.max_messages,
                    "reset_in": 0
                }
            
            used = int(current)
            
            return {
                "used": used,
                "limit": self.max_messages,
                "remaining": max(0, self.max_messages - used),
                "reset_in": ttl
            }
        
        except Exception as e:
            logger.error(f"Error obteniendo uso: {str(e)}")
            return {"error": str(e)}


# Singleton
rate_limiter = RateLimiter()
