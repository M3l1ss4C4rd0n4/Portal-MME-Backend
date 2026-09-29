from typing import Optional, Tuple

import numpy as np

# Fuente/metric_id (case-insensitive) -> (piso, techo) físico conocido.
# Todo lo que no esté listado devuelve (None, None) y no se clampa.
_BOUNDS = {
    'EMBALSES_PCT': (0.0, 100.0),
    'PORCVOLUUTILDIAR': (0.0, 100.0),
    'PERDIDAS_TOTALES': (None, 100.0),
    'PERDIDAS_TOTAL_PCT': (None, 100.0),
}


def get_physical_bounds(nombre: str) -> Tuple[Optional[float], Optional[float]]:
    """Piso/techo físico conocido para una fuente o metric_id."""
    return _BOUNDS.get((nombre or '').upper(), (None, None))


def clamp_intervalo_prediccion(central, inferior, superior, piso=None, techo=None):
    """
    Aplica límites físicos [piso, techo] a una predicción central + intervalo
    de confianza. piso/techo=None desactiva ese lado (no cambia nada).

    Garantiza que el clamp nunca invierta el intervalo (inferior <= central
    <= superior) incluso si el ensanchamiento previo del IC lo había roto.
    """
    central = np.asarray(central, dtype=float)
    inferior = np.asarray(inferior, dtype=float)
    superior = np.asarray(superior, dtype=float)

    if piso is not None:
        central = np.maximum(central, piso)
        inferior = np.maximum(inferior, piso)
        superior = np.maximum(superior, piso)
    if techo is not None:
        central = np.minimum(central, techo)
        inferior = np.minimum(inferior, techo)
        superior = np.minimum(superior, techo)

    inferior = np.minimum(inferior, central)
    superior = np.maximum(superior, central)
    return central, inferior, superior
