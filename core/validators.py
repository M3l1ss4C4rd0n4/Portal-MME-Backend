from datetime import datetime
from core.exceptions import DateRangeError, InvalidParameterError


def validate_date_range(start_date, end_date, max_days=None):
    """
    Valida un rango de fechas.
    Retorna (start_dt, end_dt) como objetos date, o lanza DateRangeError.
    """
    if not start_date or not end_date:
        raise DateRangeError("Las fechas de inicio y fin son obligatorias.")

    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        elif hasattr(start_date, 'date'):
            start_date = start_date.date()

        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        elif hasattr(end_date, 'date'):
            end_date = end_date.date()
    except ValueError as e:
        raise DateRangeError(f"Formato de fecha inválido: {e}")

    if start_date > end_date:
        raise DateRangeError("La fecha de inicio no puede ser mayor que la fecha de fin.")

    if max_days is not None:
        delta = (end_date - start_date).days
        if delta > max_days:
            raise DateRangeError(
                f"El rango de fechas excede el máximo permitido de {max_days} días "
                f"(seleccionados: {delta} días)."
            )

    return start_date, end_date


def validate_string(s, min_length=1, max_length=None, name=None):
    """
    Valida que un string cumpla con los requisitos de longitud.
    Retorna el string limpio (strip) o lanza InvalidParameterError.
    """
    field = name or "campo"
    if s is None:
        raise InvalidParameterError(f"El {field} no puede ser nulo.")
    if not isinstance(s, str):
        raise InvalidParameterError(f"El {field} debe ser un texto.")
    stripped = s.strip()
    if len(stripped) < min_length:
        raise InvalidParameterError(
            f"El {field} debe tener al menos {min_length} caracteres."
        )
    if max_length and len(stripped) > max_length:
        raise InvalidParameterError(
            f"El {field} no puede exceder {max_length} caracteres."
        )
    return stripped
