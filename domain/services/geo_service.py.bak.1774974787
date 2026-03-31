"""
Servicio de Georreferenciación y Coordenadas
Reemplaza utils.embalses_coordenadas
"""

REGIONES_COORDENADAS = {
    "ANTIOQUIA": {"lat": 6.949021, "lon": -75.244383, "nombre": "Antioquia"},
    "CENTRO": {"lat": 4.975762, "lon": -74.283125, "nombre": "Centro"},
    "ORIENTE": {"lat": 5.378940, "lon": -72.822396, "nombre": "Oriente"},
    "VALLE": {"lat": 3.791557, "lon": -76.324203, "nombre": "Valle"},
    "CARIBE": {"lat": 9.773820, "lon": -74.201662, "nombre": "Caribe"},
    "NORDESTE": {"lat": 7.155834, "lon": -73.181155, "nombre": "Nordeste"}, 
    "CALDAS": {"lat": 5.253037, "lon": -75.464177, "nombre": "Caldas"},
    "CHOCO": {"lat": 5.518473, "lon": -76.840618, "nombre": "Chocó"},
    "HUILA": {"lat": 2.502859, "lon": -75.337770, "nombre": "Huila"},
    "TOLIMA": {"lat": 3.961026, "lon": -75.143818, "nombre": "Tolima"},
    "CAUCA": {"lat": 2.454238, "lon": -76.666991, "nombre": "Cauca"},
    "NARINO": {"lat": 1.481541, "lon": -77.387135, "nombre": "Nariño"},
    "SANTANDER": {"lat": 6.634674, "lon": -73.342129, "nombre": "Santander"},
    "NORTE SANTANDER": {"lat": 7.893910, "lon": -72.930062, "nombre": "Norte de Santander"},
    "BOYACA": {"lat": 5.670984, "lon": -73.284755, "nombre": "Boyacá"},
    "CUNDINAMARCA": {"lat": 4.887955, "lon": -74.208889, "nombre": "Cundinamarca"},
}

def obtener_coordenadas_region(region_name: str) -> dict:
    """Obtiene lat/lon para una región dada"""
    if not region_name:
        return {"lat": 4.5709, "lon": -74.2973} # Default Colombia
    
    # Normalizar
    key = region_name.upper().strip()
    return REGIONES_COORDENADAS.get(key, {"lat": 4.5709, "lon": -74.2973})
