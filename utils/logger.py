"""
Sistema de Logging Centralizado para Portal Energético MME

Este módulo proporciona configuración estandarizada de logging con:
- Rotación automática de archivos
- Niveles de log configurables
- Formateo consistente con timestamps
- Separación de logs de error
- Compatibilidad con desarrollo y producción

Uso:
    from utils.logger import setup_logger
    logger = setup_logger(__name__)
    logger.info("Mensaje informativo")
    logger.error("Error crítico", exc_info=True)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path


def setup_logger(
    name: str,
    log_dir: str = "logs",
    level: str = None,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Configura y retorna un logger con handlers de archivo y consola.
    
    Args:
        name: Nombre del logger (típicamente __name__ del módulo)
        log_dir: Directorio donde guardar archivos de log
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Si es None, usa variable de entorno LOG_LEVEL o INFO por defecto
        max_bytes: Tamaño máximo de cada archivo de log antes de rotar
        backup_count: Número de archivos de respaldo a mantener
    
    Returns:
        logging.Logger: Logger configurado
    
    Ejemplo:
        >>> logger = setup_logger(__name__)
        >>> logger.info("Aplicación iniciada correctamente")
        >>> logger.error("Error al conectar con API", exc_info=True)
    """
    
    # Crear logger
    logger = logging.getLogger(name)
    
    # Evitar duplicación de handlers si el logger ya fue configurado
    if logger.handlers:
        return logger
    
    # Determinar nivel de logging
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    log_level = getattr(logging, level, logging.INFO)
    logger.setLevel(log_level)
    
    # Crear directorio de logs si no existe
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Formato de log detallado
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Formato simplificado para consola
    console_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # === HANDLER 1: Archivo principal con rotación ===
    log_filename = f"portal_energetico_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        filename=log_path / log_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # === HANDLER 2: Archivo solo de errores ===
    error_filename = "errors.log"
    error_handler = RotatingFileHandler(
        filename=log_path / error_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)
    
    # === HANDLER 3: Consola (solo en desarrollo) ===
    if os.getenv("DASH_ENV", "development") == "development":
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger existente o crea uno nuevo.
    
    Args:
        name: Nombre del logger
    
    Returns:
        logging.Logger: Logger configurado
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Logger para el módulo actual
logger = setup_logger(__name__)


# === FUNCIONES DE UTILIDAD ===

def log_function_call(func):
    """
    Decorador para loggear entrada y salida de funciones.
    
    Uso:
        @log_function_call
        def mi_funcion(arg1, arg2):
            return resultado
    """
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_logger = get_logger(func.__module__)
        func_logger.debug(f"→ Llamando {func.__name__} con args={args[:3]}... kwargs={list(kwargs.keys())}")
        try:
            result = func(*args, **kwargs)
            func_logger.debug(f"✓ {func.__name__} completado exitosamente")
            return result
        except Exception as e:
            func_logger.error(f"✗ {func.__name__} falló: {e}", exc_info=True)
            raise
    
    return wrapper


def log_dataframe_info(df, name: str = "DataFrame", logger_instance=None):
    """
    Loggea información resumida de un pandas DataFrame.
    
    Args:
        df: pandas DataFrame
        name: Nombre descriptivo del DataFrame
        logger_instance: Logger a usar (usa logger del módulo si es None)
    """
    if logger_instance is None:
        logger_instance = logger
    
    if df is None:
        logger_instance.warning(f"{name} es None")
        return
    
    try:
        logger_instance.info(
            f"{name}: shape={df.shape}, "
            f"memoria={df.memory_usage(deep=True).sum() / 1024**2:.2f}MB, "
            f"nulos={df.isnull().sum().sum()}"
        )
    except Exception as e:
        logger_instance.warning(f"No se pudo loggear info de {name}: {e}")


def log_execution_time(logger_instance=None):
    """
    Decorador para medir y loggear tiempo de ejecución de funciones.
    
    Uso:
        @log_execution_time()
        def funcion_lenta():
            time.sleep(2)
    """
    import functools
    import time
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger_instance
            if logger_instance is None:
                logger_instance = get_logger(func.__module__)
            
            start = time.time()
            logger_instance.debug(f"⏱️ Iniciando {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger_instance.info(f"⏱️ {func.__name__} completado en {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger_instance.error(f"⏱️ {func.__name__} falló después de {elapsed:.2f}s: {e}")
                raise
        
        return wrapper
    return decorator


# === CONFIGURACIÓN INICIAL ===

def configure_root_logger():
    """
    Configura el logger raíz de la aplicación.
    Llamar esto una vez al inicio de app.py
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Reducir verbosidad de loggers de terceros
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    
    logger.info("Sistema de logging configurado correctamente")


if __name__ == "__main__":
    # Test del sistema de logging
    test_logger = setup_logger("test_module")
    
    test_logger.debug("Mensaje de debug")
    test_logger.info("Mensaje informativo")
    test_logger.warning("Mensaje de advertencia")
    test_logger.error("Mensaje de error")
    
    # Test de decorador
    @log_execution_time()
    def test_function():
        import time
        time.sleep(0.1)
        return "OK"
    
    result = test_function()
    test_logger.info(f"Test completado: {result}")
