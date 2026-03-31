from datetime import date, datetime
from typing import Union


def ensure_date(d: Union[date, datetime, str]) -> date:
    """Convierte string o datetime a date si es necesario."""
    if isinstance(d, str):
        return datetime.strptime(d, '%Y-%m-%d').date()
    if isinstance(d, datetime):
        return d.date()
    return d
