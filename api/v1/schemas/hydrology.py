"""
Esquemas Pydantic para endpoints de hidrología

Define modelos de respuesta específicos para datos hidrológicos:
- Aportes hídricos
- Catálogo de embalses
- Energía embalsada

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Dict, Any, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class HydrologyAportesResponse(BaseModel):
    """Respuesta de aportes hídricos"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (m³/s)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    reservoir: str = Field(..., description="Embalse o 'Sistema'")
    data: List[MetricPoint] = Field(..., description="Serie temporal de aportes")
    total_records: int = Field(..., description="Número total de registros")


class HydrologyReservoirsResponse(BaseModel):
    """Respuesta de catálogo de embalses"""
    total_reservoirs: int = Field(..., description="Número total de embalses")
    reservoirs: List[Dict[str, Any]] = Field(..., description="Lista de embalses")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_reservoirs": 2,
                "reservoirs": [
                    {"name": "BETANIA", "capacity_gwh": 1734.5, "river": "Magdalena", "region": "Andina"},
                    {"name": "GUAVIO", "capacity_gwh": 1231.0, "river": "Guavio", "region": "Andina"}
                ]
            }
        }


class HydrologyEnergyResponse(BaseModel):
    """Respuesta de energía embalsada"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh-día)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    data: List[MetricPoint] = Field(..., description="Serie temporal de energía")
    total_records: int = Field(..., description="Número total de registros")
