"""
Esquemas Pydantic para endpoints de métricas

Define modelos de datos para:
- Respuestas de series temporales
- Listados de métricas disponibles

Sigue las convenciones de docs/api_data_conventions.md

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import pandas as pd

from api.v1.schemas.common import MetricPoint


class MetricSeriesResponse(BaseModel):
    """
    Respuesta de serie temporal para una métrica
    
    Sigue el formato estándar definido en docs/api_data_conventions.md
    
    Attributes:
        metric_id: Código de métrica XM (Gene, DemaReal, etc.)
        entity: Entidad o agrupación (Sistema, Recurso, Embalse, etc.)
        unit: Unidad de medida (GWh, MW, %, m³/s, etc.)
        count: Número de puntos de datos
        data: Array de puntos temporales
    """
    metric_id: str = Field(..., description="Código de métrica XM")
    entity: str = Field(..., description="Entidad o agrupación")
    unit: str = Field(..., description="Unidad de medida")
    count: int = Field(..., description="Número de puntos de datos")
    data: List[MetricPoint] = Field(..., description="Array de puntos temporales")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric_id": "Gene",
                "entity": "Sistema",
                "unit": "GWh",
                "count": 365,
                "data": [
                    {
                        "date": "2026-02-03",
                        "value": 234.56,
                        "resource": "HIDRAULICA",
                        "metadata": {
                            "source": "xm_api",
                            "quality": "validated"
                        }
                    }
                ]
            }
        }
    
    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        metric_id: str,
        entity: str,
        unit: str = "GWh"
    ) -> "MetricSeriesResponse":
        """
        Crea una respuesta desde un DataFrame
        
        Args:
            df: DataFrame con columnas Date y Value
            metric_id: Código de métrica XM
            entity: Entidad o agrupación
            unit: Unidad de medida
            
        Returns:
            MetricSeriesResponse con datos del DataFrame
        """
        # Convertir DataFrame a lista de puntos
        data_points = []
        
        for _, row in df.iterrows():
            point = MetricPoint(
                date=row["Date"] if isinstance(row["Date"], pd.Timestamp) else pd.to_datetime(row["Date"]),
                value=float(row["Value"]) if pd.notna(row["Value"]) else 0.0,
                resource=row.get("Recurso") if "Recurso" in row and pd.notna(row.get("Recurso")) else None,
                agent=row.get("Agente") if "Agente" in row and pd.notna(row.get("Agente")) else None,
                region=row.get("Region") if "Region" in row and pd.notna(row.get("Region")) else None,
                metadata={
                    "source": "hybrid",  # Indica que puede venir de BD o API
                    "quality": "validated"
                }
            )
            data_points.append(point)
        
        return cls(
            metric_id=metric_id,
            entity=entity,
            unit=unit,
            count=len(data_points),
            data=data_points
        )


class MetricInfo(BaseModel):
    """
    Información de una métrica disponible
    
    Attributes:
        metric_id: Código de métrica XM
        name: Nombre descriptivo
        unit: Unidad de medida
        last_date: Última fecha disponible
        total_records: Total de registros en BD
    """
    metric_id: str = Field(..., description="Código de métrica XM")
    name: str = Field(..., description="Nombre descriptivo")
    unit: str = Field(..., description="Unidad de medida")
    last_date: Optional[str] = Field(None, description="Última fecha disponible")
    total_records: int = Field(..., description="Total de registros en BD")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric_id": "Gene",
                "name": "Generación de energía eléctrica",
                "unit": "GWh",
                "last_date": "2026-02-03",
                "total_records": 12500
            }
        }


class MetricListResponse(BaseModel):
    """
    Respuesta con lista de métricas disponibles
    
    Attributes:
        count: Total de métricas disponibles
        metrics: Lista de métricas con metadatos
    """
    count: int = Field(..., description="Total de métricas disponibles")
    metrics: List[Dict[str, Any]] = Field(..., description="Lista de métricas")
    
    class Config:
        json_schema_extra = {
            "example": {
                "count": 3,
                "metrics": [
                    {
                        "metric_id": "Gene",
                        "name": "Generación de energía",
                        "unit": "GWh",
                        "last_date": "2026-02-03",
                        "total_records": 12500
                    },
                    {
                        "metric_id": "DemaReal",
                        "name": "Demanda real de energía",
                        "unit": "GWh",
                        "last_date": "2026-02-03",
                        "total_records": 12500
                    }
                ]
            }
        }
