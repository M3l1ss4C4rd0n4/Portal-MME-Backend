"""
Seguridad y validación de webhooks
"""
from fastapi import Request, HTTPException
from twilio.request_validator import RequestValidator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Validador Twilio
twilio_validator = None
if settings.TWILIO_AUTH_TOKEN:
    twilio_validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)


async def validate_twilio_signature(request: Request, signature: str) -> bool:
    """
    Valida que el webhook viene realmente de Twilio
    
    Args:
        request: FastAPI Request object
        signature: X-Twilio-Signature header
    
    Returns:
        True si la firma es válida
    
    Raises:
        HTTPException: Si la firma es inválida
    """
    if not twilio_validator:
        logger.warning("⚠️ Twilio validator no configurado - saltando validación")
        return True
    
    if not signature:
        logger.error("❌ Falta header X-Twilio-Signature")
        raise HTTPException(status_code=403, detail="Missing signature header")
    
    try:
        # Obtener URL completa
        url = str(request.url)
        
        # Obtener form data
        form_data = dict(await request.form())
        
        # Validar firma
        is_valid = twilio_validator.validate(url, form_data, signature)
        
        if not is_valid:
            logger.error(f"❌ Firma Twilio inválida - URL: {url}")
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        
        logger.debug("✅ Firma Twilio válida")
        return True
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"❌ Error validando firma Twilio: {str(e)}")
        raise HTTPException(status_code=500, detail="Error validating signature")
