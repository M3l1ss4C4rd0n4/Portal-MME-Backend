"""
Esquemas Pydantic para endpoints de restricciones

Define modelos de respuesta para datos de restricciones operativas.

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class RestrictionsResponse(BaseModel):
    """Respuesta de restricciones operativas"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    restriction_type: Optional[str] = Field(None, description="Tipo de restricción")
    data: List[MetricPoint] = Field(..., description="Serie temporal de restricciones")
    total_records: int = Field(..., description="Número total de registros")
