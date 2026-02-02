from datetime import datetime, date

def validate_date_range(start_date, end_date):
    """
    Valida un rango de fechas.
    Retorna True si es válido (start <= end), False si no.
    """
    if not start_date or not end_date:
        return False
    
    # Convertir strings a dates si es necesario
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            
        return start_date <= end_date
    except:
        return False

def validate_string(s, min_length=1, max_length=None):
    """
    Valida que un string no sea vacío y tenga longitud mínima y máxima (opcional).
    """
    if s is None:
        return False
    if not isinstance(s, str):
        return False
    stripped = s.strip()
    if len(stripped) < min_length:
        return False
    if max_length and len(stripped) > max_length:
        return False
    return True
