# Configuración de optimización para el Dashboard
import os

# Configurar nivel de logging para producción
DEBUG_MODE = os.getenv('DASH_DEBUG', 'False').lower() == 'true'

def debug_print(*args, **kwargs):
    """Print debug only si DEBUG_MODE está activo"""
    if DEBUG_MODE:
        print(*args, **kwargs)

# Configuración de caché para datos
CACHE_TIMEOUT = 300  # 5 minutos
ENABLE_CACHE = True

# Configuración de chunks para datos grandes
MAX_RECORDS_PER_REQUEST = 1000
DEFAULT_TABLE_LIMIT = 100

# Configuración de callbacks
CALLBACK_TIMEOUT = 30
PREVENT_INITIAL_CALL_DEFAULT = True