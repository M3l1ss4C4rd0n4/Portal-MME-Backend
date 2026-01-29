"""
Utilidades para manejo de fechas y tiempos
Funciones comunes para trabajar con fechas en el Portal Energético MME
"""

from datetime import datetime, date, timedelta
from typing import Optional, Union, List, Tuple
import pandas as pd

# Importar constantes si están disponibles
try:
    from core.constants import (
        DATE_FORMAT,
        DATETIME_FORMAT,
        DATE_FORMAT_DISPLAY,
        DATETIME_FORMAT_DISPLAY,
        DATE_FORMAT_FILENAME,
        DATETIME_FORMAT_FILENAME
    )
except ImportError:
    # Valores por defecto si no hay constantes
    DATE_FORMAT = "%Y-%m-%d"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATE_FORMAT_DISPLAY = "%d/%m/%Y"
    DATETIME_FORMAT_DISPLAY = "%d/%m/%Y %H:%M"
    DATE_FORMAT_FILENAME = "%Y%m%d"
    DATETIME_FORMAT_FILENAME = "%Y%m%d_%H%M%S"


def today() -> date:
    """Obtiene la fecha de hoy"""
    return date.today()


def now() -> datetime:
    """Obtiene fecha y hora actual"""
    return datetime.now()


def format_date(fecha: Union[date, datetime, str], formato: str = DATE_FORMAT) -> str:
    """
    Formatea una fecha a string
    
    Args:
        fecha: Fecha a formatear (date, datetime, o string)
        formato: Formato de salida (por defecto ISO: YYYY-MM-DD)
    
    Returns:
        str: Fecha formateada
    
    Ejemplo:
        >>> format_date(date(2026, 1, 28))
        '2026-01-28'
        >>> format_date(date(2026, 1, 28), DATE_FORMAT_DISPLAY)
        '28/01/2026'
    """
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    return fecha.strftime(formato)


def format_datetime(dt: Union[datetime, str], formato: str = DATETIME_FORMAT) -> str:
    """
    Formatea un datetime a string
    
    Args:
        dt: Datetime a formatear
        formato: Formato de salida
    
    Returns:
        str: Datetime formateado
    """
    if isinstance(dt, str):
        dt = parse_datetime(dt)
    
    return dt.strftime(formato)


def parse_date(fecha_str: str, formato: Optional[str] = None) -> date:
    """
    Parsea un string a date
    
    Args:
        fecha_str: String con la fecha
        formato: Formato del string (None = intentar varios formatos)
    
    Returns:
        date: Fecha parseada
    
    Raises:
        ValueError: Si no se puede parsear la fecha
    """
    if formato:
        return datetime.strptime(fecha_str, formato).date()
    
    # Intentar múltiples formatos
    formatos = [
        DATE_FORMAT,           # 2026-01-28
        DATE_FORMAT_DISPLAY,   # 28/01/2026
        "%Y/%m/%d",            # 2026/01/28
        "%d-%m-%Y",            # 28-01-2026
        DATE_FORMAT_FILENAME,  # 20260128
    ]
    
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt).date()
        except ValueError:
            continue
    
    raise ValueError(f"No se pudo parsear la fecha: {fecha_str}")


def parse_datetime(dt_str: str, formato: Optional[str] = None) -> datetime:
    """
    Parsea un string a datetime
    
    Args:
        dt_str: String con el datetime
        formato: Formato del string (None = intentar varios formatos)
    
    Returns:
        datetime: Datetime parseado
    """
    if formato:
        return datetime.strptime(dt_str, formato)
    
    # Intentar múltiples formatos
    formatos = [
        DATETIME_FORMAT,              # 2026-01-28 17:30:00
        DATETIME_FORMAT_DISPLAY,      # 28/01/2026 17:30
        "%Y-%m-%d %H:%M",              # 2026-01-28 17:30
        "%Y/%m/%d %H:%M:%S",           # 2026/01/28 17:30:00
        DATETIME_FORMAT_FILENAME,      # 20260128_173000
    ]
    
    for fmt in formatos:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"No se pudo parsear el datetime: {dt_str}")


def date_range(
    start: Union[date, str],
    end: Union[date, str],
    step_days: int = 1
) -> List[date]:
    """
    Genera un rango de fechas
    
    Args:
        start: Fecha inicial
        end: Fecha final
        step_days: Paso en días (default 1)
    
    Returns:
        List[date]: Lista de fechas
    
    Ejemplo:
        >>> dates = date_range('2026-01-01', '2026-01-05')
        >>> len(dates)
        5
    """
    if isinstance(start, str):
        start = parse_date(start)
    if isinstance(end, str):
        end = parse_date(end)
    
    dates = []
    current = start
    
    while current <= end:
        dates.append(current)
        current += timedelta(days=step_days)
    
    return dates


def days_between(fecha1: Union[date, str], fecha2: Union[date, str]) -> int:
    """
    Calcula días entre dos fechas
    
    Args:
        fecha1: Primera fecha
        fecha2: Segunda fecha
    
    Returns:
        int: Número de días (positivo si fecha2 > fecha1)
    
    Ejemplo:
        >>> days_between('2026-01-01', '2026-01-10')
        9
    """
    if isinstance(fecha1, str):
        fecha1 = parse_date(fecha1)
    if isinstance(fecha2, str):
        fecha2 = parse_date(fecha2)
    
    return (fecha2 - fecha1).days


def add_days(fecha: Union[date, str], days: int) -> date:
    """
    Suma días a una fecha
    
    Args:
        fecha: Fecha base
        days: Días a sumar (puede ser negativo)
    
    Returns:
        date: Nueva fecha
    """
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    
    return fecha + timedelta(days=days)


def start_of_month(fecha: Union[date, datetime, str]) -> date:
    """Obtiene el primer día del mes de la fecha dada"""
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    return date(fecha.year, fecha.month, 1)


def end_of_month(fecha: Union[date, datetime, str]) -> date:
    """Obtiene el último día del mes de la fecha dada"""
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    # Ir al siguiente mes y restar un día
    if fecha.month == 12:
        return date(fecha.year, 12, 31)
    else:
        next_month = date(fecha.year, fecha.month + 1, 1)
        return next_month - timedelta(days=1)


def get_month_name(fecha: Union[date, datetime, str], locale: str = 'es') -> str:
    """
    Obtiene el nombre del mes
    
    Args:
        fecha: Fecha
        locale: Idioma ('es' o 'en')
    
    Returns:
        str: Nombre del mes
    """
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    meses_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    
    meses_en = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    if locale == 'es':
        return meses_es[fecha.month - 1]
    else:
        return meses_en[fecha.month - 1]


def is_valid_date(fecha_str: str, formato: Optional[str] = None) -> bool:
    """
    Verifica si un string es una fecha válida
    
    Args:
        fecha_str: String a validar
        formato: Formato esperado (None = intentar varios)
    
    Returns:
        bool: True si es válida
    """
    try:
        parse_date(fecha_str, formato)
        return True
    except (ValueError, TypeError):
        return False


def get_data_age_days(fecha_datos: Union[date, datetime, str]) -> int:
    """
    Calcula antigüedad de datos en días
    
    Args:
        fecha_datos: Fecha de los datos
    
    Returns:
        int: Días de antigüedad
    """
    if isinstance(fecha_datos, str):
        fecha_datos = parse_date(fecha_datos)
    if isinstance(fecha_datos, datetime):
        fecha_datos = fecha_datos.date()
    
    return (date.today() - fecha_datos).days


def get_date_range_for_period(
    period: str,
    reference_date: Optional[Union[date, str]] = None
) -> Tuple[date, date]:
    """
    Obtiene rango de fechas para un período
    
    Args:
        period: Período ('today', 'yesterday', 'last_7_days', 'last_30_days', 
                'this_month', 'last_month', 'this_year')
        reference_date: Fecha de referencia (default: hoy)
    
    Returns:
        Tuple[date, date]: (fecha_inicio, fecha_fin)
    
    Ejemplo:
        >>> start, end = get_date_range_for_period('last_7_days')
        >>> days_between(start, end)
        6
    """
    if reference_date is None:
        ref = date.today()
    elif isinstance(reference_date, str):
        ref = parse_date(reference_date)
    else:
        ref = reference_date
    
    if period == 'today':
        return ref, ref
    
    elif period == 'yesterday':
        yesterday = ref - timedelta(days=1)
        return yesterday, yesterday
    
    elif period == 'last_7_days':
        start = ref - timedelta(days=6)
        return start, ref
    
    elif period == 'last_30_days':
        start = ref - timedelta(days=29)
        return start, ref
    
    elif period == 'this_month':
        start = start_of_month(ref)
        return start, ref
    
    elif period == 'last_month':
        first_this_month = start_of_month(ref)
        last_last_month = first_this_month - timedelta(days=1)
        first_last_month = start_of_month(last_last_month)
        return first_last_month, last_last_month
    
    elif period == 'this_year':
        start = date(ref.year, 1, 1)
        return start, ref
    
    else:
        raise ValueError(f"Período no soportado: {period}")


def to_pandas_datetime(fecha: Union[date, datetime, str]) -> pd.Timestamp:
    """
    Convierte una fecha a pd.Timestamp para usar con pandas
    
    Args:
        fecha: Fecha a convertir
    
    Returns:
        pd.Timestamp: Timestamp de pandas
    """
    if isinstance(fecha, str):
        fecha = parse_date(fecha)
    
    return pd.Timestamp(fecha)


def filename_timestamp() -> str:
    """
    Genera timestamp para nombres de archivo
    
    Returns:
        str: Timestamp (ej: '20260128_173045')
    """
    return datetime.now().strftime(DATETIME_FORMAT_FILENAME)


if __name__ == "__main__":
    # Tests
    print("Testing date utilities...")
    
    # Test format
    assert format_date(date(2026, 1, 28)) == "2026-01-28"
    
    # Test parse
    fecha = parse_date("2026-01-28")
    assert fecha.year == 2026
    assert fecha.month == 1
    assert fecha.day == 28
    
    # Test range
    dates = date_range('2026-01-01', '2026-01-05')
    assert len(dates) == 5
    
    # Test days between
    assert days_between('2026-01-01', '2026-01-10') == 9
    
    print("✅ Date utilities test passed")
