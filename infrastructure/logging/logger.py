"""
Sistema de Logging Centralizado para Portal Energético MME
Versión refactorizada con mejor organización

Este módulo proporciona configuración estandarizada de logging con:
- Rotación automática de archivos
- Niveles de log configurables via settings
- Formateo consistente con timestamps
- Separación de logs de error
- Compatibilidad con desarrollo y producción
- Integración con core.config

Uso:
    from shared.logging.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Mensaje informativo")
    logger.error("Error crítico", exc_info=True)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Importar settings si está disponible, sino usar valores por defecto
try:
    from core.config import settings, get_logs_dir
    USE_SETTINGS = True
except ImportError:
    USE_SETTINGS = False
    settings = None


class LoggerManager:
    """Gestor centralizado de loggers (Singleton)"""
    
    _instance: Optional['LoggerManager'] = None
    _loggers: dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_logger(
        self,
        name: str,
        log_dir: Optional[Path] = None,
        level: Optional[str] = None,
        max_bytes: Optional[int] = None,
        backup_count: Optional[int] = None
    ) -> logging.Logger:
        """
        Obtiene o crea un logger configurado
        
        Args:
            name: Nombre del logger (típicamente __name__ del módulo)
            log_dir: Directorio donde guardar archivos de log (None = usar settings)
            level: Nivel de logging (None = usar settings)
            max_bytes: Tamaño máximo de archivo antes de rotar (None = usar settings)
            backup_count: Número de archivos de respaldo (None = usar settings)
        
        Returns:
            logging.Logger: Logger configurado
        """
        # Si el logger ya existe, retornarlo
        if name in self._loggers:
            return self._loggers[name]
        
        # Crear nuevo logger
        logger = logging.getLogger(name)
        
        # Evitar duplicación si ya tiene handlers
        if logger.handlers:
            self._loggers[name] = logger
            return logger
        
        # Configurar nivel de logging
        if level is None and USE_SETTINGS:
            level = settings.LOG_LEVEL
        elif level is None:
            level = "INFO"
        
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(log_level)
        
        # Configurar directorio de logs
        if log_dir is None and USE_SETTINGS:
            log_dir = get_logs_dir()
        elif log_dir is None:
            log_dir = Path("logs")
        
        log_dir = Path(log_dir)
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # Configurar tamaños
        if max_bytes is None and USE_SETTINGS:
            max_bytes = settings.LOG_MAX_BYTES
        elif max_bytes is None:
            max_bytes = 10 * 1024 * 1024  # 10MB
        
        if backup_count is None and USE_SETTINGS:
            backup_count = settings.LOG_BACKUP_COUNT
        elif backup_count is None:
            backup_count = 5
        
        # Formato detallado para archivos
        if USE_SETTINGS:
            file_format = settings.LOG_FORMAT
            date_format = settings.LOG_DATE_FORMAT
        else:
            file_format = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
            date_format = "%Y-%m-%d %H:%M:%S"
        
        file_formatter = logging.Formatter(
            fmt=file_format,
            datefmt=date_format
        )
        
        # Formato simplificado para consola
        console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Handler de archivo rotativo para logs generales
        general_log_file = log_dir / "app.log"
        file_handler = RotatingFileHandler(
            general_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Handler de archivo para errores críticos
        error_log_file = log_dir / "errors.log"
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        logger.addHandler(error_handler)
        
        # Handler de consola (solo en desarrollo o si está habilitado)
        if (USE_SETTINGS and settings.DASH_ENV == "development") or not USE_SETTINGS:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # Prevenir propagación a logger raíz (evita duplicados)
        logger.propagate = False
        
        # Guardar en cache
        self._loggers[name] = logger
        
        return logger


# Instancia global del gestor
_manager = LoggerManager()


def get_logger(name: str, **kwargs) -> logging.Logger:
    """
    Función principal para obtener un logger configurado
    
    Args:
        name: Nombre del logger (típicamente __name__)
        **kwargs: Argumentos adicionales para personalizar el logger
    
    Returns:
        logging.Logger: Logger configurado y listo para usar
    
    Ejemplo:
        >>> from shared.logging.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Aplicación iniciada")
        >>> logger.error("Error al procesar datos", exc_info=True)
    """
    return _manager.get_logger(name, **kwargs)


def configure_root_logger():
    """
    Configura el logger raíz de la aplicación
    
    Útil para configurar logging globalmente al inicio de la aplicación.
    Debe llamarse una sola vez al inicio.
    """
    root_logger = logging.getLogger()
    
    # Si ya está configurado, no hacer nada
    if root_logger.handlers:
        return
    
    # Configurar nivel
    if USE_SETTINGS:
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    else:
        level = logging.INFO
    
    root_logger.setLevel(level)
    
    # Crear handler de consola básico
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)


def set_logger_level(logger_name: str, level: str):
    """
    Cambia el nivel de logging de un logger específico
    
    Args:
        logger_name: Nombre del logger (e.g., 'werkzeug', 'urllib3')
        level: Nuevo nivel (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Ejemplo:
        >>> set_logger_level('werkzeug', 'WARNING')
        >>> set_logger_level('urllib3', 'ERROR')
    """
    logger = logging.getLogger(logger_name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)


def reduce_noisy_loggers():
    """
    Reduce la verbosidad de loggers ruidosos (werkzeug, urllib3, etc.)
    
    Llamar al inicio de la aplicación para limpiar logs
    """
    noisy_loggers = [
        'werkzeug',
        'urllib3',
        'requests',
        'matplotlib',
        'PIL',
    ]
    
    for logger_name in noisy_loggers:
        set_logger_level(logger_name, 'WARNING')
    
    # Dash en INFO para mantener info importante
    set_logger_level('dash', 'INFO')


# ═══════════════════════════════════════════════════════════════
# COMPATIBILIDAD CON CÓDIGO VIEJO
# ═══════════════════════════════════════════════════════════════

def setup_logger(
    name: str,
    log_dir: str = "logs",
    level: str = None,
    max_bytes: int = 10485760,
    backup_count: int = 5
) -> logging.Logger:
    """
    Función legacy para compatibilidad con código viejo
    
    Mantiene la misma firma que utils.logger.setup_logger()
    pero usa el nuevo sistema internamente
    """
    return get_logger(
        name,
        log_dir=Path(log_dir) if log_dir else None,
        level=level,
        max_bytes=max_bytes,
        backup_count=backup_count
    )


if __name__ == "__main__":
    # Test del sistema de logging
    print("Testing logging system...")
    
    # Configurar logger raíz
    configure_root_logger()
    
    # Crear loggers de prueba
    logger1 = get_logger("test.module1")
    logger2 = get_logger("test.module2")
    
    # Probar niveles
    logger1.debug("Debug message")
    logger1.info("Info message")
    logger1.warning("Warning message")
    logger1.error("Error message")
    
    # Verificar que el mismo logger se reutiliza
    logger1_again = get_logger("test.module1")
    assert logger1 is logger1_again, "Logger should be cached"
    
    print("✅ Logging system test passed")
