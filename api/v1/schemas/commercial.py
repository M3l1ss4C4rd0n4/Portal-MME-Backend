"""
Esquemas Pydantic para endpoints comerciales

Define modelos de respuesta para datos comerciales y precios.

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class CommercialPricesResponse(BaseModel):
    """Respuesta de precios comerciales"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida ($/kWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    agent: Optional[str] = Field(None, description="Agente filtrado")
    data: List[MetricPoint] = Field(..., description="Serie temporal de precios")
    total_records: int = Field(..., description="Número total de registros")
