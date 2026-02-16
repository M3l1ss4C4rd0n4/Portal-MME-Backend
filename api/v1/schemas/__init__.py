"""
Esquemas Pydantic de la API v1

Define modelos de datos para:
- Validación de entrada
- Serialización de respuestas
- Documentación automática de OpenAPI

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from api.v1.schemas.common import ErrorResponse, MetricPoint, PredictionPoint
from api.v1.schemas.metrics import MetricSeriesResponse, MetricListResponse
from api.v1.schemas.predictions import PredictionResponse

__all__ = [
    "ErrorResponse",
    "MetricPoint",
    "PredictionPoint",
    "MetricSeriesResponse",
    "MetricListResponse",
    "PredictionResponse"
]
