"""
WhatsApp Message Sender
Envía mensajes a WhatsApp usando Twilio, Meta API o WhatsApp Web
"""
import logging
from typing import Optional, List
from twilio.rest import Client
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Clientes
twilio_client = None
if settings.WHATSAPP_PROVIDER == "twilio" and settings.TWILIO_ACCOUNT_SID:
    twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send_whatsapp_message(
    to: str,
    body: str,
    media_url: Optional[str] = None
) -> dict:
    """
    Envía mensaje a WhatsApp
    
    Args:
        to: Número de destino (formato: +573001234567)
        body: Texto del mensaje
        media_url: URL de imagen/archivo adjunto (opcional)
    
    Returns:
        Dict con información del mensaje enviado
    """
    if settings.WHATSAPP_PROVIDER == "twilio":
        return await send_via_twilio(to, body, media_url)
    elif settings.WHATSAPP_PROVIDER == "meta":
        return await send_via_meta(to, body, media_url)
    elif settings.WHATSAPP_PROVIDER == "whatsapp-web":
        return await send_via_whatsapp_web(to, body, media_url)
    else:
        raise ValueError(f"Proveedor no soportado: {settings.WHATSAPP_PROVIDER}")


async def send_via_twilio(
    to: str,
    body: str,
    media_url: Optional[str] = None
) -> dict:
    """
    Envía mensaje vía Twilio
    """
    try:
        # Asegurar formato correcto
        if not to.startswith("+"):
            to = f"+{to}"
        
        from_number = settings.TWILIO_WHATSAPP_NUMBER
        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        
        to_whatsapp = f"whatsapp:{to}"
        
        # Preparar parámetros
        message_params = {
            "from_": from_number,
            "to": to_whatsapp,
            "body": body
        }
        
        # Agregar media si existe
        if media_url:
            message_params["media_url"] = [media_url]
        
        # Enviar mensaje
        message = twilio_client.messages.create(**message_params)
        
        logger.info(f"✅ Mensaje Twilio enviado - SID: {message.sid}")
        
        return {
            "sid": message.sid,
            "status": message.status,
            "to": to,
            "provider": "twilio"
        }
    
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje Twilio: {str(e)}")
        raise


async def send_via_meta(
    to: str,
    body: str,
    media_url: Optional[str] = None
) -> dict:
    """
    Envía mensaje vía Meta WhatsApp Business API
    """
    try:
        url = f"https://graph.facebook.com/v18.0/{settings.META_PHONE_NUMBER_ID}/messages"
        
        headers = {
            "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Payload básico
        payload = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", ""),
            "type": "text" if not media_url else "image",
        }
        
        if media_url:
            payload["image"] = {
                "link": media_url,
                "caption": body
            }
        else:
            payload["text"] = {
                "body": body
            }
        
        # Enviar request
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        
        message_id = result["messages"][0]["id"]
        logger.info(f"✅ Mensaje Meta enviado - ID: {message_id}")
        
        return {
            "message_id": message_id,
            "status": "sent",
            "to": to,
            "provider": "meta"
        }
    
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Error HTTP Meta API: {e.response.text}")
        raise
    
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje Meta: {str(e)}")
        raise


async def send_via_whatsapp_web(
    to: str,
    body: str,
    media_url: Optional[str] = None
) -> dict:
    """
    Envía mensaje vía whatsapp-web.js (GRATIS)
    
    Args:
        to: Número de destino (ej: +573001234567)
        body: Texto del mensaje
        media_url: URL de media (opcional)
    
    Returns:
        Dict con información del mensaje enviado
    """
    try:
        # Asegurar formato correcto
        if not to.startswith("+"):
            to = f"+{to}"
        
        # URL del servicio whatsapp-web
        whatsapp_web_url = getattr(settings, 'WHATSAPP_WEB_URL', 'http://localhost:3000')
        
        # Preparar payload
        payload = {
            "to": to,
            "message": body
        }
        
        if media_url:
            payload["media_url"] = media_url
        
        # Enviar petición al servicio Node.js
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{whatsapp_web_url}/send",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
        
        logger.info(f"✅ Mensaje WhatsApp Web enviado a {to}")
        
        return {
            "message_id": result.get("message_id"),
            "status": "sent",
            "to": to,
            "provider": "whatsapp-web",
            "success": result.get("success", True)
        }
    
    except httpx.ConnectError:
        logger.error(f"❌ No se puede conectar al servicio WhatsApp Web en {whatsapp_web_url}")
        logger.error("   Asegúrate de que el servicio esté ejecutándose: cd whatsapp-web-service && node server.js")
        raise Exception("Servicio WhatsApp Web no disponible")
    
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json() if e.response.headers.get('content-type') == 'application/json' else e.response.text
        logger.error(f"❌ Error HTTP WhatsApp Web: {error_detail}")
        raise
    
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje WhatsApp Web: {str(e)}")
        raise


async def send_bulk_messages(
    recipients: List[str],
    body: str,
    media_url: Optional[str] = None
) -> List[dict]:
    """
    Envía mensaje a múltiples destinatarios
    
    Args:
        recipients: Lista de números de teléfono
        body: Texto del mensaje
        media_url: URL de media (opcional)
    
    Returns:
        Lista de resultados
    """
    results = []
    
    for recipient in recipients:
        try:
            result = await send_whatsapp_message(recipient, body, media_url)
            results.append({
                "recipient": recipient,
                "success": True,
                "result": result
            })
        except Exception as e:
            logger.error(f"Error enviando a {recipient}: {str(e)}")
            results.append({
                "recipient": recipient,
                "success": False,
                "error": str(e)
            })
    
    return results
