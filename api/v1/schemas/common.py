"""
Esquemas Pydantic comunes

Define modelos reutilizables en múltiples endpoints:
- ErrorResponse: Respuestas de error estandarizadas
- MetricPoint: Punto de dato en serie temporal
- PredictionPoint: Punto de predicción con intervalo de confianza

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import Optional, Dict, Any
from datetime import date as DateType, datetime
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """
    Respuesta de error estandarizada
    
    Attributes:
        error: Tipo de error
        message: Mensaje descriptivo del error
        details: Detalles adicionales (opcional)
    """
    error: str = Field(..., description="Tipo de error")
    message: str = Field(..., description="Mensaje descriptivo del error")
    details: Optional[Any] = Field(None, description="Detalles adicionales del error")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Not Found",
                "message": "No se encontraron datos para la métrica solicitada",
                "details": None
            }
        }


class MetricPoint(BaseModel):
    """
    Punto de dato en una serie temporal
    
    Sigue el formato definido en docs/api_data_conventions.md
    
    Attributes:
        date: Fecha del punto de dato (ISO 8601: YYYY-MM-DD)
        value: Valor numérico de la métrica
        resource: Tipo de recurso energético (opcional)
        agent: Agente/empresa (opcional)
        region: Región geográfica (opcional)
        metadata: Metadatos adicionales (opcional)
    """
    date: DateType = Field(..., description="Fecha en formato ISO 8601 (YYYY-MM-DD)")
    value: float = Field(..., description="Valor numérico de la métrica")
    resource: Optional[str] = Field(None, description="Tipo de recurso energético")
    agent: Optional[str] = Field(None, description="Agente o empresa")
    region: Optional[str] = Field(None, description="Región geográfica")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-03",
                "value": 234.56,
                "resource": "HIDRAULICA",
                "agent": None,
                "region": None,
                "metadata": {
                    "source": "xm_api",
                    "quality": "validated"
                }
            }
        }


class PredictionPoint(BaseModel):
    """
    Punto de predicción con intervalo de confianza
    
    Sigue el formato definido en docs/api_data_conventions.md
    
    Attributes:
        date: Fecha de la predicción (ISO 8601: YYYY-MM-DD)
        value: Valor predicho
        lower: Límite inferior del intervalo de confianza
        upper: Límite superior del intervalo de confianza
        confidence: Nivel de confianza (0.0 - 1.0)
    """
    date: DateType = Field(..., description="Fecha de la predicción")
    value: float = Field(..., description="Valor predicho")
    lower: float = Field(..., description="Límite inferior del intervalo de confianza")
    upper: float = Field(..., description="Límite superior del intervalo de confianza")
    confidence: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza (0.0 - 1.0)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-03-01",
                "value": 245.78,
                "lower": 230.12,
                "upper": 261.44,
                "confidence": 0.95
            }
        }
