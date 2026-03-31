"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                      ERROR HANDLERS - Manejo de Excepciones                   ║
║                                                                               ║
║  Utilidades para manejo consistente de errores en toda la aplicación         ║
║  Fase 2 - Estabilidad: Reemplaza 'except Exception' genéricos                ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    from core.error_handlers import handle_db_error, handle_api_error
    
    try:
        db_operation()
    except psycopg2.Error as e:
        handle_db_error(e, operation="INSERT metrics")
"""

import logging
import functools
from typing import Callable, TypeVar, Optional, Any
import psycopg2
import requests

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ═══════════════════════════════════════════════════════════════
# Database Errors
# ═══════════════════════════════════════════════════════════════

class DatabaseConnectionError(Exception):
    """Error de conexión a base de datos."""
    pass


class DatabaseQueryError(Exception):
    """Error en query SQL."""
    pass


class DatabaseIntegrityError(Exception):
    """Error de integridad (constraint violation, etc.)."""
    pass


def handle_db_error(error: psycopg2.Error, operation: str = "", query: str = "") -> None:
    """
    Maneja errores de PostgreSQL de forma específica.
    
    Args:
        error: Excepción de psycopg2
        operation: Descripción de la operación
        query: Query SQL (opcional, truncada en logs)
    """
    error_msg = str(error)
    query_snippet = query[:50] + "..." if len(query) > 50 else query
    
    # Clasificar tipo de error
    if isinstance(error, psycopg2.OperationalError):
        logger.error(
            f"[DB CONNECTION ERROR] {operation} | {error_msg}",
            extra={"operation": operation, "error_type": "connection"}
        )
        raise DatabaseConnectionError(f"Error de conexión en {operation}: {error_msg}") from error
    
    elif isinstance(error, psycopg2.IntegrityError):
        logger.error(
            f"[DB INTEGRITY ERROR] {operation} | {error_msg} | Query: {query_snippet}",
            extra={"operation": operation, "error_type": "integrity", "query": query_snippet}
        )
        raise DatabaseIntegrityError(f"Error de integridad en {operation}: {error_msg}") from error
    
    elif isinstance(error, psycopg2.ProgrammingError):
        logger.error(
            f"[DB PROGRAMMING ERROR] {operation} | {error_msg} | Query: {query_snippet}",
            extra={"operation": operation, "error_type": "programming", "query": query_snippet}
        )
        raise DatabaseQueryError(f"Error SQL en {operation}: {error_msg}") from error
    
    else:
        logger.error(
            f"[DB ERROR] {operation} | {error_msg} | Query: {query_snippet}",
            extra={"operation": operation, "error_type": "unknown", "query": query_snippet}
        )
        raise DatabaseQueryError(f"Error de base de datos en {operation}: {error_msg}") from error


# ═══════════════════════════════════════════════════════════════
# API Errors
# ═══════════════════════════════════════════════════════════════

class APIConnectionError(Exception):
    """Error de conexión a API externa."""
    pass


class APIResponseError(Exception):
    """Error en respuesta de API (status code != 2xx)."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class APITimeoutError(Exception):
    """Timeout en request a API."""
    pass


class ServiceError(Exception):
    """Error general en servicio de dominio."""
    def __init__(self, message: str, service: str = "", operation: str = ""):
        super().__init__(message)
        self.service = service
        self.operation = operation


class ServiceUnavailableError(ServiceError):
    """Servicio temporalmente no disponible."""
    pass


class ValidationError(ServiceError):
    """Error de validación de datos."""
    pass


def handle_api_error(error: Exception, api_name: str = "API", endpoint: str = "") -> None:
    """
    Maneja errores de APIs externas de forma específica.
    
    Args:
        error: Excepción (requests.RequestException, etc.)
        api_name: Nombre de la API (XM, SIMEM, etc.)
        endpoint: Endpoint llamado
    """
    if isinstance(error, requests.Timeout):
        logger.error(
            f"[API TIMEOUT] {api_name} | Endpoint: {endpoint}",
            extra={"api": api_name, "endpoint": endpoint, "error_type": "timeout"}
        )
        raise APITimeoutError(f"Timeout en {api_name} ({endpoint})") from error
    
    elif isinstance(error, requests.ConnectionError):
        logger.error(
            f"[API CONNECTION ERROR] {api_name} | Endpoint: {endpoint} | Error: {error}",
            extra={"api": api_name, "endpoint": endpoint, "error_type": "connection"}
        )
        raise APIConnectionError(f"Error de conexión a {api_name}") from error
    
    elif isinstance(error, requests.HTTPError):
        status_code = error.response.status_code if hasattr(error, 'response') else None
        logger.error(
            f"[API HTTP ERROR] {api_name} | Status: {status_code} | Endpoint: {endpoint}",
            extra={"api": api_name, "endpoint": endpoint, "status_code": status_code, "error_type": "http"}
        )
        raise APIResponseError(
            f"Error HTTP {status_code} en {api_name}",
            status_code=status_code
        ) from error
    
    else:
        logger.error(
            f"[API ERROR] {api_name} | Endpoint: {endpoint} | Error: {error}",
            extra={"api": api_name, "endpoint": endpoint, "error_type": "unknown"}
        )
        raise APIConnectionError(f"Error en {api_name}: {error}") from error


# ═══════════════════════════════════════════════════════════════
# Decoradores
# ═══════════════════════════════════════════════════════════════

def safe_db_operation(operation_name: str = ""):
    """
    Decorador para operaciones de base de datos seguras.
    
    Args:
        operation_name: Nombre descriptivo de la operación
        
    Uso:
        @safe_db_operation("INSERT metrics")
        def save_metrics(data):
            # ... operación DB
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except psycopg2.Error as e:
                handle_db_error(e, operation=operation_name or func.__name__)
            except Exception as e:
                # Solo capturar si no es ya una excepción nuestra
                if not isinstance(e, (DatabaseConnectionError, DatabaseQueryError, DatabaseIntegrityError)):
                    logger.error(f"[UNEXPECTED DB ERROR] {operation_name}: {e}", exc_info=True)
                    raise DatabaseQueryError(f"Error inesperado en {operation_name}: {e}") from e
                raise
        return wrapper
    return decorator


def safe_api_call(api_name: str = "API"):
    """
    Decorador para llamadas a APIs externas seguras.
    
    Args:
        api_name: Nombre de la API
        
    Uso:
        @safe_api_call("XM API")
        def fetch_xm_data():
            # ... llamada API
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
                handle_api_error(e, api_name=api_name, endpoint=func.__name__)
            except Exception as e:
                if not isinstance(e, (APIConnectionError, APIResponseError, APITimeoutError)):
                    logger.error(f"[UNEXPECTED API ERROR] {api_name}: {e}", exc_info=True)
                    raise APIConnectionError(f"Error inesperado en {api_name}: {e}") from e
                raise
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# Context Managers
# ═══════════════════════════════════════════════════════════════

class SafeDBContext:
    """
    Context manager para operaciones de base de datos seguras.
    
    Uso:
        with SafeDBContext("INSERT metrics") as ctx:
            cursor.execute(query)
            ctx.success()  # Marcar como exitoso
    """
    
    def __init__(self, operation: str = "", conn=None):
        self.operation = operation
        self.conn = conn
        self._success = False
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if issubclass(exc_type, psycopg2.Error):
                handle_db_error(exc_val, operation=self.operation)
            return False  # No suprimir otras excepciones
        
        if not self._success and self.conn:
            # Si no se marcó como exitoso, hacer rollback
            try:
                self.conn.rollback()
            except Exception:
                pass
        
        return True
    
    def success(self):
        """Marca la operación como exitosa."""
        self._success = True
        if self.conn:
            self.conn.commit()


# ═══════════════════════════════════════════════════════════════
# Funciones de utilidad
# ═══════════════════════════════════════════════════════════════

def log_error_with_context(
    error: Exception,
    context: str = "",
    extra_data: Optional[dict] = None,
    level: str = "error"
) -> None:
    """
    Loguea un error con contexto adicional.
    
    Args:
        error: Excepción ocurrida
        context: Descripción del contexto
        extra_data: Datos adicionales para el log
        level: Nivel de log (error, warning, critical)
    """
    log_func = getattr(logger, level, logger.error)
    
    extra = {
        "context": context,
        "error_type": type(error).__name__,
        **(extra_data or {})
    }
    
    log_func(
        f"[{context}] {type(error).__name__}: {error}",
        extra=extra,
        exc_info=True
    )


def safe_execute(
    func: Callable[..., T],
    *args,
    default: Optional[T] = None,
    error_message: str = "",
    **kwargs
) -> Optional[T]:
    """
    Ejecuta una función de forma segura, retornando default en caso de error.
    
    Args:
        func: Función a ejecutar
        args: Argumentos posicionales
        default: Valor por defecto si falla
        error_message: Mensaje de error para log
        kwargs: Argumentos nombrados
        
    Returns:
        Resultado de la función o default
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{error_message}: {e}", exc_info=True)
        return default


def graceful_error_handler(
    default_return=None,
    log_level: str = "warning",
    error_message: str = "",
    reraise: bool = False
):
    """
    Decorador para manejar errores de forma elegante sin detener el flujo.
    
    Útil para operaciones opcionales donde el fallo de una no debe afectar
    el resultado general (ej: construcción de reportes con múltiples secciones).
    
    Args:
        default_return: Valor a retornar si falla
        log_level: Nivel de log (debug, info, warning, error)
        error_message: Mensaje personalizado para el log
        reraise: Si True, relanza la excepción después de loguear
        
    Uso:
        @graceful_error_handler(default_return={})
        def build_optional_section():
            # Si falla, retorna {} y continúa
            return expensive_operation()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                msg = error_message or f"Error en {func.__name__}: {e}"
                log_func = getattr(logger, log_level, logger.warning)
                log_func(msg, extra={
                    "function": func.__name__,
                    "error_type": type(e).__name__,
                    "error": str(e)
                })
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


def catch_specific_errors(
    error_types: tuple = (Exception,),
    default_return=None,
    error_message: str = ""
):
    """
    Decorador para capturar tipos específicos de errores.
    
    Args:
        error_types: Tupla de tipos de excepción a capturar
        default_return: Valor a retornar si se captura el error
        error_message: Mensaje para el log
        
    Uso:
        @catch_specific_errors(
            error_types=(ConnectionError, TimeoutError),
            default_return=None
        )
        def fetch_external_data():
            # Solo captura ConnectionError y TimeoutError
            return api_call()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except error_types as e:
                msg = error_message or f"{type(e).__name__} en {func.__name__}: {e}"
                logger.warning(msg, extra={
                    "function": func.__name__,
                    "error_type": type(e).__name__
                })
                return default_return
            except Exception as e:
                # Otros errores se propagan
                raise
        return wrapper
    return decorator


__all__ = [
    # Excepciones DB
    'DatabaseConnectionError',
    'DatabaseQueryError',
    'DatabaseIntegrityError',
    # Excepciones API
    'APIConnectionError',
    'APIResponseError',
    'APITimeoutError',
    # Excepciones Servicio
    'ServiceError',
    'ServiceUnavailableError',
    'ValidationError',
    # Handlers
    'handle_db_error',
    'handle_api_error',
    # Decoradores
    'safe_db_operation',
    'safe_api_call',
    'graceful_error_handler',
    'catch_specific_errors',
    # Context managers
    'SafeDBContext',
    # Utilidades
    'log_error_with_context',
    'safe_execute',
]
