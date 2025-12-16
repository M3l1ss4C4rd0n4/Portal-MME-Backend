"""
Excepciones personalizadas para Portal Energético MME

Este módulo define excepciones específicas del dominio para mejorar
el manejo de errores y proporcionar contexto más claro sobre los problemas.

Jerarquía:
    PortalEnergeticoError (base)
    ├── DataError
    │   ├── DataNotFoundError
    │   ├── DataValidationError
    │   └── DataFormatError
    ├── APIError
    │   ├── APIConnectionError
    │   ├── APITimeoutError
    │   └── APIResponseError
    ├── CacheError
    │   ├── CacheCorruptedError
    │   └── CacheExpiredError
    └── ConfigurationError
        ├── DateRangeError
        └── InvalidParameterError

Uso:
    from utils.exceptions import DataNotFoundError
    
    if not data:
        raise DataNotFoundError("No se encontraron datos para la métrica especificada")
"""

from typing import Optional, Any


class PortalEnergeticoError(Exception):
    """
    Excepción base para todas las excepciones del Portal Energético.
    
    Todas las excepciones personalizadas deben heredar de esta clase.
    """
    
    def __init__(self, message: str, details: Optional[dict] = None):
        """
        Args:
            message: Mensaje descriptivo del error
            details: Diccionario opcional con detalles adicionales del error
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message} | Detalles: {self.details}"
        return self.message


# ============================================================================
# ERRORES DE DATOS
# ============================================================================

class DataError(PortalEnergeticoError):
    """Error base para problemas relacionados con datos."""
    pass


class DataNotFoundError(DataError):
    """
    Se lanza cuando no se encuentran datos para los parámetros solicitados.
    
    Ejemplo:
        raise DataNotFoundError(
            "No se encontraron datos de demanda",
            details={'fecha': '2024-01-01', 'metrica': 'DemaEner'}
        )
    """
    pass


class DataValidationError(DataError):
    """
    Se lanza cuando los datos no cumplen con las validaciones esperadas.
    
    Ejemplo:
        raise DataValidationError(
            "Datos contienen valores nulos en columnas críticas",
            details={'columnas_nulas': ['Value', 'Date']}
        )
    """
    pass


class DataFormatError(DataError):
    """
    Se lanza cuando los datos tienen un formato incorrecto.
    
    Ejemplo:
        raise DataFormatError(
            "DataFrame no tiene la estructura esperada",
            details={'columnas_esperadas': ['Date', 'Value'], 'columnas_recibidas': ['Fecha']}
        )
    """
    pass


# ============================================================================
# ERRORES DE API
# ============================================================================

class APIError(PortalEnergeticoError):
    """Error base para problemas con la API de XM."""
    pass


class APIConnectionError(APIError):
    """
    Se lanza cuando no se puede conectar con la API de XM.
    
    Ejemplo:
        raise APIConnectionError(
            "No se pudo establecer conexión con API XM",
            details={'timeout': 30, 'intentos': 3}
        )
    """
    pass


class APITimeoutError(APIError):
    """
    Se lanza cuando una consulta a la API excede el tiempo límite.
    
    Ejemplo:
        raise APITimeoutError(
            "Consulta a API XM excedió timeout",
            details={'timeout': 60, 'metrica': 'AporEner'}
        )
    """
    pass


class APIResponseError(APIError):
    """
    Se lanza cuando la API retorna una respuesta inesperada o con error.
    
    Ejemplo:
        raise APIResponseError(
            "API retornó código de error",
            details={'status_code': 500, 'response': 'Internal Server Error'}
        )
    """
    pass


# ============================================================================
# ERRORES DE CACHE
# ============================================================================

class CacheError(PortalEnergeticoError):
    """Error base para problemas con el sistema de cache."""
    pass


class CacheCorruptedError(CacheError):
    """
    Se lanza cuando un archivo de cache está corrupto.
    
    Ejemplo:
        raise CacheCorruptedError(
            "Archivo de cache corrupto",
            details={'archivo': 'cache_demanda_20241101.pkl'}
        )
    """
    pass


class CacheExpiredError(CacheError):
    """
    Se lanza cuando se intenta usar cache expirado (opcional, para control explícito).
    
    Ejemplo:
        raise CacheExpiredError(
            "Cache ha expirado",
            details={'archivo': 'cache.pkl', 'expiracion': '2024-01-01 10:00:00'}
        )
    """
    pass


# ============================================================================
# ERRORES DE CONFIGURACIÓN
# ============================================================================

class ConfigurationError(PortalEnergeticoError):
    """Error base para problemas de configuración o parámetros."""
    pass


class DateRangeError(ConfigurationError):
    """
    Se lanza cuando el rango de fechas es inválido.
    
    Ejemplo:
        raise DateRangeError(
            "Rango de fechas inválido: fecha fin anterior a fecha inicio",
            details={'inicio': '2024-01-15', 'fin': '2024-01-01'}
        )
    """
    pass


class InvalidParameterError(ConfigurationError):
    """
    Se lanza cuando un parámetro tiene un valor inválido.
    
    Ejemplo:
        raise InvalidParameterError(
            "Métrica no válida",
            details={'metrica': 'INVALIDA', 'metricas_validas': ['DemaEner', 'GeneReal']}
        )
    """
    pass


# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def raise_if_empty(data: Any, message: str = "No se encontraron datos", **details):
    """
    Helper para lanzar DataNotFoundError si los datos están vacíos.
    
    Args:
        data: Datos a verificar (DataFrame, list, dict, etc.)
        message: Mensaje de error
        **details: Detalles adicionales para incluir en la excepción
    
    Raises:
        DataNotFoundError: Si los datos están vacíos
    
    Ejemplo:
        df = fetch_data()
        raise_if_empty(df, "No hay datos de demanda", fecha='2024-01-01')
    """
    import pandas as pd
    
    is_empty = False
    
    if data is None:
        is_empty = True
    elif isinstance(data, pd.DataFrame) and data.empty:
        is_empty = True
    elif isinstance(data, (list, dict, str)) and len(data) == 0:
        is_empty = True
    
    if is_empty:
        raise DataNotFoundError(message, details=details)


def raise_if_invalid_dates(start_date: str, end_date: str, max_days: Optional[int] = None):
    """
    Helper para validar rangos de fechas.
    
    Args:
        start_date: Fecha de inicio (YYYY-MM-DD)
        end_date: Fecha de fin (YYYY-MM-DD)
        max_days: Número máximo de días permitidos (opcional)
    
    Raises:
        DateRangeError: Si el rango de fechas es inválido
    
    Ejemplo:
        raise_if_invalid_dates('2024-01-01', '2024-12-31', max_days=365)
    """
    from datetime import datetime
    
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError as e:
        raise DateRangeError(
            "Formato de fecha inválido. Use YYYY-MM-DD",
            details={'start': start_date, 'end': end_date, 'error': str(e)}
        )
    
    if end_dt < start_dt:
        raise DateRangeError(
            "Fecha de fin anterior a fecha de inicio",
            details={'inicio': start_date, 'fin': end_date}
        )
    
    if max_days is not None:
        days_diff = (end_dt - start_dt).days
        if days_diff > max_days:
            raise DateRangeError(
                f"Rango de fechas excede el máximo permitido de {max_days} días",
                details={'inicio': start_date, 'fin': end_date, 'dias': days_diff, 'maximo': max_days}
            )


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Tests básicos de las excepciones
    
    print("Testing excepciones personalizadas...\n")
    
    # Test 1: DataNotFoundError
    try:
        raise DataNotFoundError(
            "No se encontraron datos de demanda",
            details={'fecha': '2024-01-01', 'metrica': 'DemaEner'}
        )
    except DataNotFoundError as e:
        print(f"✓ DataNotFoundError: {e}")
    
    # Test 2: APIConnectionError
    try:
        raise APIConnectionError(
            "No se pudo conectar con API XM",
            details={'timeout': 30}
        )
    except APIConnectionError as e:
        print(f"✓ APIConnectionError: {e}")
    
    # Test 3: raise_if_empty
    try:
        raise_if_empty([], "Lista vacía detectada", origen='test')
    except DataNotFoundError as e:
        print(f"✓ raise_if_empty: {e}")
    
    # Test 4: raise_if_invalid_dates
    try:
        raise_if_invalid_dates('2024-12-31', '2024-01-01')
    except DateRangeError as e:
        print(f"✓ raise_if_invalid_dates: {e}")
    
    print("\n✅ Todas las excepciones funcionan correctamente")
