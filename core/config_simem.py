"""
Configuración SIMEM (Stub)
Recreado para satisfacer dependencias faltantes durante refactor
"""
import pandas as pd

METRICAS_SIMEM_POR_CATEGORIA = {
    "Precios": ["PrecBolsNaci", "PrecOferIdea", "PrecEscasez"],
    "Generacion": ["Gene", "GeneIdea", "AporEner"],
    "Demanda": ["DemaReal", "DemaCome", "DemaSIN"],
    "Transmision": ["Dispo", "IndiFalla"],
    "Restricciones": ["Restricciones"],
}

METRICAS_SIMEM_CRITICAS = ["PrecBolsNaci", "Gene", "DemaReal", "AporEner"]

_NOMBRES_SIMEM = {
    "PrecBolsNaci": "Precio de Bolsa Nacional",
    "PrecOferIdea": "Precio de Oferta Ideal",
    "PrecEscasez": "Precio de Escasez",
    "Gene": "Generación Real",
    "GeneIdea": "Generación Ideal",
    "AporEner": "Aportes de Energía",
    "DemaReal": "Demanda Real del SIN",
    "DemaCome": "Demanda Comercial",
    "DemaSIN": "Demanda Total SIN",
    "Dispo": "Disponibilidad del Sistema",
    "IndiFalla": "Índice de Fallas",
    "Restricciones": "Restricciones Operativas",
}

def obtener_listado_simem(categoria=None):
    """Obtiene listado de métricas SIMEM. Retorna DataFrame con columnas CodigoVariable y Nombre."""
    if categoria:
        codigos = METRICAS_SIMEM_POR_CATEGORIA.get(categoria, [])
    else:
        codigos = [m for sublist in METRICAS_SIMEM_POR_CATEGORIA.values() for m in sublist]
    return pd.DataFrame({
        "CodigoVariable": codigos,
        "Nombre": [_NOMBRES_SIMEM.get(c, c) for c in codigos],
    })
