"""
Decoradores compartidos del orquestador de chatbot.
"""
import logging
from functools import wraps

from domain.schemas.orchestrator import ErrorDetail

logger = logging.getLogger(__name__)


def handle_service_error(func):
    """Decorador para capturar errores de servicios"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TimeoutError:
            logger.warning(f"Timeout en servicio {func.__name__}")
            return None, ErrorDetail(
                code="TIMEOUT",
                message="El servicio tardó demasiado en responder"
            )
        except Exception as e:
            logger.error(f"Error en servicio {func.__name__}: {str(e)}", exc_info=True)
            return None, ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar el servicio"
            )
    return wrapper
