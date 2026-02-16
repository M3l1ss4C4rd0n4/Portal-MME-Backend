"""
Esquemas Pydantic para endpoints de pérdidas

Define modelos de respuesta para datos de pérdidas de energía.

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class LossesResponse(BaseModel):
    """Respuesta de pérdidas de energía"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    loss_type: str = Field(..., description="Tipo de pérdida (technical, non_technical, total)")
    data: List[MetricPoint] = Field(..., description="Serie temporal de pérdidas")
    total_records: int = Field(..., description="Número total de registros")
