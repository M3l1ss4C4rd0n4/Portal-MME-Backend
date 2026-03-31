"""
Patrones comunes de manejo de errores para reemplazar except Exception genéricos.

Uso:
    from core.error_patterns import handle_service_init_error, handle_db_operation_error
    
    # En lugar de:
    try:
        service = MyService()
    except Exception as e:
        logger.error(e)
    
    # Usar:
    try:
        service = MyService()
    except (ImportError, ModuleNotFoundError) as e:
        handle_service_init_error("MyService", e)
    except Exception as e:
        logger.error(f"Error inesperado inicializando MyService: {e}", exc_info=True)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def handle_service_init_error(service_name: str, error: Exception, logger_instance: Optional[logging.Logger] = None) -> None:
    """
    Maneja errores de inicialización de servicios.
    
    Args:
        service_name: Nombre del servicio
        error: Excepción ocurrida
        logger_instance: Logger opcional (usa logger global si no se proporciona)
    """
    log = logger_instance or logger
    error_type = type(error).__name__
    
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        log.warning(f"[{service_name}] Dependencia no disponible: {error}")
    elif isinstance(error, (ConnectionError, TimeoutError)):
        log.error(f"[{service_name}] Error de conexión: {error}")
    else:
        log.error(f"[{service_name}] Error de inicialización ({error_type}): {error}")


def handle_db_operation_error(operation: str, error: Exception, logger_instance: Optional[logging.Logger] = None) -> None:
    """
    Maneja errores de operaciones de base de datos.
    
    Args:
        operation: Descripción de la operación
        error: Excepción ocurrida
        logger_instance: Logger opcional
    """
    log = logger_instance or logger
    error_type = type(error).__name__
    
    log.error(f"[DB] Error en '{operation}' ({error_type}): {error}")


def handle_api_call_error(api_name: str, error: Exception, logger_instance: Optional[logging.Logger] = None) -> None:
    """
    Maneja errores de llamadas a APIs externas.
    
    Args:
        api_name: Nombre de la API
        error: Excepción ocurrida
        logger_instance: Logger opcional
    """
    log = logger_instance or logger
    error_type = type(error).__name__
    
    if isinstance(error, TimeoutError):
        log.warning(f"[{api_name}] Timeout: {error}")
    elif isinstance(error, ConnectionError):
        log.error(f"[{api_name}] Error de conexión: {error}")
    else:
        log.error(f"[{api_name}] Error ({error_type}): {error}")
