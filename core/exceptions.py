class PortalError(Exception):
    """Excepción base para el Portal Energético"""

class DateRangeError(PortalError):
    """Error en rango de fechas"""

class InvalidParameterError(PortalError):
    """Parámetro inválido"""

class DataNotFoundError(PortalError):
    """Datos no encontrados"""

class ExternalAPIError(PortalError):
    """Error en API externa (XM, etc)"""

class DatabaseError(PortalError):
    """Error en operaciones de base de datos"""
