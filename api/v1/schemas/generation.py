"""
Esquemas Pydantic para endpoints de generación eléctrica

Define modelos de respuesta específicos para datos de generación:
- Generación total del sistema
- Generación por fuente energética
- Catálogo de recursos generadores
- Mix energético

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Dict, Any
from datetime import date as DateType
from pydantic import BaseModel, Field

from api.v1.schemas.common import MetricPoint


class GenerationSystemResponse(BaseModel):
    """Respuesta de generación total del sistema"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    data: List[MetricPoint] = Field(..., description="Serie temporal de datos")
    total_records: int = Field(..., description="Número total de registros")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric": "generation_system",
                "description": "Generación eléctrica total del sistema nacional",
                "unit": "GWh",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "data": [
                    {"date": "2026-01-01", "value": 234.56, "resource": "Sistema", "metadata": {"unit": "GWh"}},
                    {"date": "2026-01-02", "value": 238.12, "resource": "Sistema", "metadata": {"unit": "GWh"}}
                ],
                "total_records": 2
            }
        }


class GenerationBySourceResponse(BaseModel):
    """Respuesta de generación por fuente energética"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    sources: List[str] = Field(..., description="Fuentes energéticas incluidas")
    data: List[MetricPoint] = Field(..., description="Serie temporal por fuente")
    total_records: int = Field(..., description="Número total de registros")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric": "generation_by_source",
                "description": "Generación eléctrica por tipo de fuente energética",
                "unit": "GWh",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "sources": ["HIDRAULICA", "TERMICA", "EOLICA"],
                "data": [
                    {"date": "2026-01-01", "value": 150.0, "resource": "HIDRAULICA", "metadata": {"unit": "GWh"}},
                    {"date": "2026-01-01", "value": 80.0, "resource": "TERMICA", "metadata": {"unit": "GWh"}}
                ],
                "total_records": 2
            }
        }


class GenerationResourcesResponse(BaseModel):
    """Respuesta de catálogo de recursos generadores"""
    total_resources: int = Field(..., description="Número total de recursos")
    source_type: str = Field(..., description="Tipo de fuente filtrada")
    resources: List[Dict[str, Any]] = Field(..., description="Lista de recursos")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_resources": 3,
                "source_type": "HIDRAULICA",
                "resources": [
                    {"name": "GUAVIO", "type": "HIDRAULICA", "active": True},
                    {"name": "BETANIA", "type": "HIDRAULICA", "active": True},
                    {"name": "CHIVOR", "type": "HIDRAULICA", "active": True}
                ]
            }
        }


class GenerationMixResponse(BaseModel):
    """Respuesta de mix energético (participación por fuente)"""
    date: DateType = Field(..., description="Fecha del mix energético")
    total_generation_gwh: float = Field(..., description="Generación total en GWh")
    mix: List[Dict[str, Any]] = Field(..., description="Participación de cada fuente")
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-04",
                "total_generation_gwh": 234.56,
                "mix": [
                    {"source": "HIDRAULICA", "generation_gwh": 150.0, "percentage": 63.9},
                    {"source": "TERMICA", "generation_gwh": 70.0, "percentage": 29.8},
                    {"source": "EOLICA", "generation_gwh": 10.0, "percentage": 4.3},
                    {"source": "SOLAR", "generation_gwh": 4.56, "percentage": 1.9}
                ]
            }
        }
