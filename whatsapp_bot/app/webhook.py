"""
WhatsApp Webhook Handler
Procesa mensajes entrantes de WhatsApp
"""
from fastapi import Request, HTTPException
import logging
import json
from datetime import datetime

from app.config import settings
from app.security import validate_twilio_signature
from app.sender import send_whatsapp_message
from orchestrator.bot import BotOrchestrator
import redis

logger = logging.getLogger(__name__)

# Singleton del orquestador
bot_orchestrator = BotOrchestrator()

# Redis para tracking de usuarios
_redis_users = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=3,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)


def _track_user(phone: str):
    """Registra un usuario en Redis para poder enviarle alertas futuras"""
    try:
        # Set con todos los usuarios conocidos del bot
        _redis_users.sadd('bot:known_users', phone)
        # Timestamp de última interacción
        _redis_users.set(f'user:{phone}:last_interaction', datetime.now().isoformat())
        logger.debug(f"Usuario trackeado: {phone}")
    except Exception as e:
        logger.error(f"Error trackeando usuario {phone}: {e}")


async def handle_whatsapp_webhook(request: Request, signature: str = None) -> dict:
    """
    Maneja webhook de WhatsApp (Twilio o Meta)
    
    Args:
        request: FastAPI Request object
        signature: Firma de seguridad del webhook
    
    Returns:
        Dict con status de procesamiento
    """
    try:
        # Validar firma (solo para Twilio)
        if settings.WHATSAPP_PROVIDER == "twilio" and signature:
            await validate_twilio_signature(request, signature)
        
        # Parsear datos según proveedor
        if settings.WHATSAPP_PROVIDER == "twilio":
            message_data = await parse_twilio_webhook(request)
        else:
            message_data = await parse_meta_webhook(request)
        
        logger.info(f"📱 Mensaje de {message_data['from_number']}: {message_data['body'][:50]}...")
        
        # Registrar usuario para envío de alertas futuras
        _track_user(message_data['from_number'])
        
        # Procesar mensaje con el orquestador
        response = await bot_orchestrator.process_message(
            user_id=message_data['from_number'],
            message=message_data['body'],
            media_url=message_data.get('media_url')
        )
        
        # Enviar respuesta a WhatsApp
        await send_whatsapp_message(
            to=message_data['from_number'],
            body=response.get('body', ''),
            media_url=response.get('media_url')
        )
        
        logger.info(f"✅ Respuesta enviada a {message_data['from_number']}")
        
        return {
            "status": "processed",
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {str(e)}", exc_info=True)
        
        # Intentar enviar mensaje de error al usuario
        try:
            if 'message_data' in locals():
                await send_whatsapp_message(
                    to=message_data['from_number'],
                    body="❌ Lo siento, hubo un error procesando tu mensaje. Por favor intenta nuevamente."
                )
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))


async def parse_twilio_webhook(request: Request) -> dict:
    """
    Parsea webhook de Twilio
    
    Returns:
        Dict con from_number, body, media_url
    """
    form_data = await request.form()
    
    return {
        "from_number": form_data.get("From", "").replace("whatsapp:", "").strip(),
        "to_number": form_data.get("To", "").replace("whatsapp:", "").strip(),
        "body": form_data.get("Body", "").strip(),
        "media_url": form_data.get("MediaUrl0"),
        "num_media": int(form_data.get("NumMedia", 0)),
        "timestamp": datetime.now().isoformat(),
        "provider": "twilio"
    }


async def parse_meta_webhook(request: Request) -> dict:
    """
    Parsea webhook de Meta WhatsApp Business API
    
    Returns:
        Dict con from_number, body, media_url
    """
    body = await request.json()
    
    # Meta envía estructura más compleja
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])
        
        if not messages:
            raise ValueError("No messages in webhook")
        
        message = messages[0]
        
        return {
            "from_number": message["from"],
            "to_number": value["metadata"]["phone_number_id"],
            "body": message.get("text", {}).get("body", ""),
            "media_url": None,  # TODO: extraer media si existe
            "timestamp": message["timestamp"],
            "message_id": message["id"],
            "provider": "meta"
        }
    
    except (KeyError, IndexError) as e:
        logger.error(f"Error parseando webhook Meta: {str(e)}")
        logger.debug(f"Body recibido: {json.dumps(body, indent=2)}")
        raise ValueError(f"Invalid Meta webhook format: {str(e)}")
