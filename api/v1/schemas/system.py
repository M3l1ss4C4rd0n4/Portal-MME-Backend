"""
Esquemas Pydantic para endpoints de sistema

Define modelos de respuesta para:
- Demanda de energía
- Precios de bolsa

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class DemandResponse(BaseModel):
    """Respuesta de demanda de energía"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    data: List[MetricPoint] = Field(..., description="Serie temporal de demanda")
    total_records: int = Field(..., description="Número total de registros")


class PricesResponse(BaseModel):
    """Respuesta de precios de bolsa"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida ($/kWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    data: List[MetricPoint] = Field(..., description="Serie temporal de precios")
    total_records: int = Field(..., description="Número total de registros")
