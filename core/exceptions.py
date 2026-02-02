class PortalError(Exception):
    """Excepción base para el Portal Energético"""
    pass

class DateRangeError(PortalError):
    """Error en rango de fechas"""
    pass

class InvalidParameterError(PortalError):
    """Parámetro inválido"""
    pass

class DataNotFoundError(PortalError):
    """Datos no encontrados"""
    pass

class ExternalAPIError(PortalError):
    """Error en API externa (XM, etc)"""
    pass

class DatabaseError(PortalError):
    """Error en operaciones de base de datos"""
    pass
