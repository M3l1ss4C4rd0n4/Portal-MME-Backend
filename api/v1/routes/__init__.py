"""
Rutas de la API v1

Exporta todos los routers disponibles
"""

from api.v1.routes import metrics, predictions

__all__ = ["metrics", "predictions"]
