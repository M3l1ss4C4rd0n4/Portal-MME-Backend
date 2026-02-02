"""
Configuración SIMEM (Stub)
Recreado para satisfacer dependencias faltantes durante refactor
"""

METRICAS_SIMEM_POR_CATEGORIA = {
    "Precios": ["PrecBolsNaci", "PrecOferIdea", "PrecEscasez"],
    "Generacion": ["Gene", "GeneIdea", "AporEner"],
    "Demanda": ["DemaReal", "DemaCome", "DemaSIN"],
    "Transmision": ["Dispo", "IndiFalla"],
    "Restricciones": ["Restricciones"],
}

METRICAS_SIMEM_CRITICAS = ["PrecBolsNaci", "Gene", "DemaReal", "AporEner"]

def obtener_listado_simem(categoria=None):
    """Obtiene listado de métricas SIMEM por categoría"""
    if categoria:
        return METRICAS_SIMEM_POR_CATEGORIA.get(categoria, [])
    # Flatten list
    return [m for sublist in METRICAS_SIMEM_POR_CATEGORIA.values() for m in sublist]
