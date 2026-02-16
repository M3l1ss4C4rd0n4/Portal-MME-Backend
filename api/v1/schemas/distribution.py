"""
Esquemas Pydantic para endpoints de distribución

Define modelos de respuesta para datos de distribución eléctrica.

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Dict, Any, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class DistributionDataResponse(BaseModel):
    """Respuesta de datos de distribución"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    operator: Optional[str] = Field(None, description="Operador filtrado")
    data: List[MetricPoint] = Field(..., description="Serie temporal de datos")
    total_records: int = Field(..., description="Número total de registros")


class DistributionOperatorsResponse(BaseModel):
    """Respuesta de catálogo de operadores"""
    total_operators: int = Field(..., description="Número total de operadores")
    operators: List[Dict[str, Any]] = Field(..., description="Lista de operadores")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_operators": 2,
                "operators": [
                    {"name": "CODENSA", "region": "Cundinamarca", "coverage_area": "Bogotá"},
                    {"name": "EPM", "region": "Antioquia", "coverage_area": "Medellín"}
                ]
            }
        }
