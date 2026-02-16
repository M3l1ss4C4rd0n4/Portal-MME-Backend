"""
Context Manager - Gestión de contexto conversacional
Permite conversaciones multi-turno con memoria
"""
import redis
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Gestor de contexto conversacional para WhatsApp bot
    Usa Redis para almacenar sesiones de usuario
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=2,  # DB separada para contextos
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
        self.ttl = 3600  # 1 hora de expiración por defecto
    
    def get_context(self, user_id: str) -> Dict:
        """
        Obtiene contexto de usuario
        
        Args:
            user_id: ID del usuario (número WhatsApp)
        
        Returns:
            Dict con contexto del usuario
        """
        try:
            key = f"context:{user_id}"
            data = self.redis_client.get(key)
            
            if data:
                context = json.loads(data)
                logger.debug(f"Contexto recuperado para {user_id}")
                return context
            
            # Contexto nuevo
            context = self._create_new_context(user_id)
            logger.info(f"Nuevo contexto creado para {user_id}")
            return context
        
        except Exception as e:
            logger.error(f"Error obteniendo contexto: {str(e)}")
            return self._create_new_context(user_id)
    
    def update_context(self, user_id: str, updates: Dict):
        """
        Actualiza contexto de usuario
        
        Args:
            user_id: ID del usuario
            updates: Datos a actualizar
        """
        try:
            context = self.get_context(user_id)
            
            # Agregar a historial si es una interacción
            if "last_query" in updates:
                context["conversation_history"].append({
                    "query": updates["last_query"],
                    "intent": updates.get("current_intent"),
                    "timestamp": datetime.now().isoformat()
                })
                
                # Mantener solo últimas 10 interacciones
                context["conversation_history"] = context["conversation_history"][-10:]
            
            # Actualizar campos
            context.update(updates)
            context["last_interaction"] = datetime.now().isoformat()
            
            # Guardar en Redis
            key = f"context:{user_id}"
            self.redis_client.setex(
                key,
                self.ttl,
                json.dumps(context, default=str)
            )
            
            # Actualizar timestamp de usuario para stats
            self.redis_client.set(
                f"user:{user_id}:last_interaction",
                datetime.now().isoformat()
            )
            
            logger.debug(f"Contexto actualizado para {user_id}")
        
        except Exception as e:
            logger.error(f"Error actualizando contexto: {str(e)}")
    
    def clear_context(self, user_id: str):
        """
        Limpia contexto de usuario
        """
        try:
            key = f"context:{user_id}"
            self.redis_client.delete(key)
            logger.info(f"Contexto limpiado para {user_id}")
        except Exception as e:
            logger.error(f"Error limpiando contexto: {str(e)}")
    
    def get_conversation_history(self, user_id: str, limit: int = 5) -> List[Dict]:
        """
        Obtiene historial de conversación
        """
        context = self.get_context(user_id)
        history = context.get("conversation_history", [])
        return history[-limit:]
    
    def set_preference(self, user_id: str, key: str, value):
        """
        Guarda preferencia de usuario
        """
        context = self.get_context(user_id)
        
        if "preferences" not in context:
            context["preferences"] = {}
        
        context["preferences"][key] = value
        self.update_context(user_id, {"preferences": context["preferences"]})
    
    def get_preference(self, user_id: str, key: str, default=None):
        """
        Obtiene preferencia de usuario
        """
        context = self.get_context(user_id)
        return context.get("preferences", {}).get(key, default)
    
    def _create_new_context(self, user_id: str) -> Dict:
        """
        Crea nuevo contexto para usuario
        """
        return {
            "user_id": user_id,
            "conversation_history": [],
            "current_intent": None,
            "last_query": None,
            "preferences": {
                "language": "es",
                "chart_type": "line",
                "notifications": True
            },
            "created_at": datetime.now().isoformat(),
            "last_interaction": datetime.now().isoformat()
        }
    
    def get_active_users_count(self, hours: int = 24) -> int:
        """
        Cuenta usuarios activos en las últimas X horas
        """
        try:
            pattern = "context:*"
            keys = self.redis_client.keys(pattern)
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            active_count = 0
            
            for key in keys:
                data = self.redis_client.get(key)
                if data:
                    context = json.loads(data)
                    last_interaction = datetime.fromisoformat(context["last_interaction"])
                    
                    if last_interaction > cutoff_time:
                        active_count += 1
            
            return active_count
        
        except Exception as e:
            logger.error(f"Error contando usuarios activos: {str(e)}")
            return 0
