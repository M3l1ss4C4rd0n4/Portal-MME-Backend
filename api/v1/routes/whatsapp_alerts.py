"""
Endpoint para envío de alertas al WhatsApp Bot

El sistema de alertas llama a este endpoint, que reenvía al bot de Oscar.
El bot se encarga de hacer broadcast a TODOS los usuarios que alguna vez
hayan usado el chatbot. El chatbot es libre y cualquiera lo puede usar.

Ruta: /api/v1/chatbot/send-alert
Método: POST
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import logging
import httpx

from api.dependencies import get_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Configuración del WhatsApp Bot de Oscar
WHATSAPP_BOT_CONFIG = {
    'base_url': 'http://localhost:8001',
    'broadcast_endpoint': '/api/broadcast-alert',
    'status_endpoint': '/api/known-users',
    'timeout': 60
}


class AlertBroadcast(BaseModel):
    """Schema para broadcast de alerta via el bot de WhatsApp"""
    message: str = Field(..., description="Texto de la alerta a enviar a todos los usuarios")
    severity: str = Field(default="ALERT", description="NORMAL, WARNING, ALERT, o CRITICAL")
    metrica: Optional[str] = Field(None, description="Métrica que generó la alerta")
    valor: Optional[float] = Field(None, description="Valor de la métrica")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "⚠️ *ALERTA* - Demanda eléctrica alta: 275.5 GWh/día (umbral: 250)",
                "severity": "ALERT",
                "metrica": "DEMANDA",
                "valor": 275.5
            }
        }


# Mantener compatibilidad con el schema anterior
class AlertNotification(BaseModel):
    """Schema legacy para notificación individual (redirige a broadcast)"""
    phone: Optional[str] = Field(None, description="Ignorado - se envía a todos los usuarios del bot")
    message: str = Field(..., description="Texto de la alerta")
    severity: str = Field(default="ALERT", description="Severidad")
    metrica: Optional[str] = Field(None, description="Métrica que generó la alerta")
    valor: Optional[float] = Field(None, description="Valor de la métrica")


@router.post(
    "/send-alert",
    status_code=status.HTTP_200_OK,
    summary="� Broadcast Alerta a todos los usuarios del bot",
    description="""
    Envía una alerta a TODOS los usuarios que alguna vez hayan usado el chatbot de WhatsApp.
    
    ## Flujo:
    1. Sistema de alertas (Celery) detecta condición anómala
    2. Llama a este endpoint con el mensaje de alerta
    3. Este endpoint reenvía al bot de Oscar (puerto 8001) → /api/broadcast-alert
    4. El bot envía el mensaje a TODOS los usuarios registrados
    
    El bot es público - cualquier persona que alguna vez le haya escrito
    recibirá las alertas automáticamente.
    """,
    tags=["🤖 Chatbot"]
)
async def send_alert_to_whatsapp(
    request: Request,
    api_key: str = Depends(get_api_key),
) -> dict:
    """
    Broadcast de alerta via el WhatsApp Bot de Oscar.
    Acepta tanto AlertBroadcast como AlertNotification (legacy).
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    message = body.get('message', body.get('mensaje', ''))
    severity = body.get('severity', body.get('severidad', 'ALERT'))
    
    if not message:
        raise HTTPException(status_code=400, detail="Campo 'message' es requerido")
    
    logger.info(
        f"[BROADCAST_ALERT] Nueva alerta | "
        f"Severidad: {severity} | "
        f"Métrica: {body.get('metrica', 'N/A')}"
    )
    
    try:
        # Enviar al bot de Oscar → broadcast a todos los usuarios
        bot_url = f"{WHATSAPP_BOT_CONFIG['base_url']}{WHATSAPP_BOT_CONFIG['broadcast_endpoint']}"
        
        bot_payload = {
            'message': message,
            'severity': severity,
        }
        
        async with httpx.AsyncClient(timeout=WHATSAPP_BOT_CONFIG['timeout']) as client:
            response = await client.post(bot_url, json=bot_payload)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(
                f"[BROADCAST_ALERT] ✅ Broadcast exitoso | "
                f"Enviados: {result.get('sent', 0)}/{result.get('users_count', 0)}"
            )
            return {
                'success': True,
                'message': 'Alerta enviada a todos los usuarios del bot',
                'users_reached': result.get('sent', 0),
                'total_users': result.get('users_count', 0),
                'bot_response': result
            }
        else:
            logger.error(
                f"[BROADCAST_ALERT] ❌ Error del bot | "
                f"Status: {response.status_code} | "
                f"Response: {response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WhatsApp Bot respondió con error: {response.status_code}"
            )
    
    except httpx.TimeoutException:
        logger.error(f"[BROADCAST_ALERT] ⏱️ Timeout conectando al WhatsApp Bot")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout conectando al WhatsApp Bot"
        )
    
    except httpx.ConnectError:
        logger.error(f"[BROADCAST_ALERT] 🔌 Error de conexión al WhatsApp Bot")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp Bot no disponible"
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"[BROADCAST_ALERT] ❌ Error inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar alerta"
        )


@router.get(
    "/whatsapp-bot-status",
    summary="📊 Estado del WhatsApp Bot",
    description="Verifica si el WhatsApp Bot está disponible",
    tags=["🤖 Chatbot"]
)
async def check_whatsapp_bot_status(
    api_key: str = Depends(get_api_key),
) -> dict:
    """Verificar conectividad con el WhatsApp Bot y cantidad de usuarios"""
    try:
        bot_health_url = f"{WHATSAPP_BOT_CONFIG['base_url']}/health"
        bot_users_url = f"{WHATSAPP_BOT_CONFIG['base_url']}{WHATSAPP_BOT_CONFIG['status_endpoint']}"
        
        async with httpx.AsyncClient(timeout=5) as client:
            health_response = await client.get(bot_health_url)
        
        users_info = {}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                users_response = await client.get(bot_users_url)
            if users_response.status_code == 200:
                users_info = users_response.json()
        except Exception as e:
            pass
        
        return {
            'whatsapp_bot_available': health_response.status_code == 200,
            'bot_url': WHATSAPP_BOT_CONFIG['base_url'],
            'total_users': users_info.get('total_users', 0),
            'broadcast_ready': users_info.get('total_users', 0) > 0,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        return {
            'whatsapp_bot_available': False,
            'bot_url': WHATSAPP_BOT_CONFIG['base_url'],
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
