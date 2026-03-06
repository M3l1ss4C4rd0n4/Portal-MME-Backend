"""
Funciones puras de serialización para el orquestador.
"""
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Tuple


def sanitize_numpy_types(obj: Any) -> Any:
    """
    Convierte recursivamente tipos numpy a tipos nativos de Python
    para serialización JSON/Pydantic.
    """
    if isinstance(obj, dict):
        return {k: sanitize_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    elif isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    from datetime import datetime, date
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj
