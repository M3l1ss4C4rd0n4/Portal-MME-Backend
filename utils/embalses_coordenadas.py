"""
Coordenadas geográficas de las regiones hidrológicas de Colombia
Datos aproximados basados en la ubicación central de cada región
"""

# Coordenadas aproximadas del centro de cada región hidrológica
# Formato: 'REGION': {'nombre': 'Nombre región', 'lat': latitud, 'lon': longitud}
REGIONES_COORDENADAS = {
    'ANTIOQUIA': {'nombre': 'Antioquia', 'lat': 6.5, 'lon': -75.3},
    'CALDAS': {'nombre': 'Caldas', 'lat': 5.3, 'lon': -75.5},
    'CARIBE': {'nombre': 'Caribe', 'lat': 9.0, 'lon': -74.8},
    'CENTRO': {'nombre': 'Centro', 'lat': 4.5, 'lon': -75.0},
    'ORIENTE': {'nombre': 'Oriente', 'lat': 4.8, 'lon': -73.5},
    'SINÚ': {'nombre': 'Sinú', 'lat': 8.0, 'lon': -76.0},
    'VALLE': {'nombre': 'Valle', 'lat': 3.5, 'lon': -76.5},
    'RIOS ESTIMADOS': {'nombre': 'Ríos Estimados', 'lat': 3.3, 'lon': -76.2},
}

def obtener_coordenadas_region(nombre_region):
    """
    Retorna las coordenadas de una región hidrológica
    
    Args:
        nombre_region: Nombre de la región (ej: 'ANTIOQUIA')
    
    Returns:
        dict con 'nombre', 'lat', 'lon' o None si no se encuentra
    """
    # Normalizar nombre de región (mayúsculas, sin espacios extra)
    region_normalizada = nombre_region.strip().upper()
    return REGIONES_COORDENADAS.get(region_normalizada)

def obtener_todas_regiones():
    """
    Retorna lista de todas las regiones con sus coordenadas
    
    Returns:
        list de dicts con 'region', 'nombre', 'lat', 'lon'
    """
    resultado = []
    for region, datos in REGIONES_COORDENADAS.items():
        resultado.append({
            'region': region,
            'nombre': datos['nombre'],
            'lat': datos['lat'],
            'lon': datos['lon']
        })
    return resultado
