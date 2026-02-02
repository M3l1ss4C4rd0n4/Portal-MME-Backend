"""
Configuración de métricas de distribución a descargar.
"""

# Lista de códigos de métricas de distribución a procesar
DISTRIBUTION_METRICS = [
    'RestAliv',      # Reemplaza TXR
    'RespComerAGC',  # Reemplaza PERCOM
    'DemaReal',      # Reemplaza CONSUM
    'PerdidasEner',  # Reemplaza PERD
    'DemaCome'       # Demanda Comercial
]

# Agentes distribuidores principales (opcional, para filtros)
MAIN_DISTRIBUTORS = [
    'CODENSA',
    'EPM',
    'ENEL',
    'AIR-E',
]
