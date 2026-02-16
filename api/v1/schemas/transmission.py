"""
Esquemas Pydantic para endpoints de transmisión

Define modelos de respuesta para:
- Líneas de transmisión
- Flujos de potencia
- Intercambios internacionales

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import List, Dict, Any, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field


class TransmissionLinesResponse(BaseModel):
    """Respuesta de catálogo de líneas de transmisión"""
    total_lines: int = Field(..., description="Número total de líneas")
    voltage_filter: Optional[int] = Field(None, description="Filtro de tensión aplicado (kV)")
    operator_filter: Optional[str] = Field(None, description="Filtro de operador aplicado")
    lines: List[Dict[str, Any]] = Field(..., description="Lista de líneas")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_lines": 2,
                "voltage_filter": 500,
                "operator_filter": None,
                "lines": [
                    {
                        "name": "Bolívar-Cuestecitas 500 kV",
                        "from_substation": "Bolívar",
                        "to_substation": "Cuestecitas",
                        "voltage_kv": 500,
                        "operator": "ISA",
                        "length_km": 584.5,
                        "capacity_mw": 1200
                    }
                ]
            }
        }


class TransmissionFlowsResponse(BaseModel):
    """Respuesta de flujos de potencia"""
    date: DateType = Field(..., description="Fecha de los flujos")
    flows: List[Dict[str, Any]] = Field(..., description="Flujos por línea")
    total_records: int = Field(..., description="Número total de registros")


class TransmissionInternationalResponse(BaseModel):
    """Respuesta de intercambios internacionales"""
    metric: str = Field(..., description="Identificador de la métrica")
    description: str = Field(..., description="Descripción de la métrica")
    unit: str = Field(..., description="Unidad de medida (GWh)")
    start_date: DateType = Field(..., description="Fecha inicial")
    end_date: DateType = Field(..., description="Fecha final")
    data: List[Dict[str, Any]] = Field(..., description="Serie temporal de intercambios")
    total_records: int = Field(..., description="Número total de registros")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric": "international_exchanges",
                "description": "Intercambios internacionales de energía",
                "unit": "GWh",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "data": [
                    {
                        "date": "2026-01-01",
                        "country": "Ecuador",
                        "import_gwh": 5.2,
                        "export_gwh": 12.3,
                        "net_gwh": 7.1
                    }
                ],
                "total_records": 1
            }
        }
