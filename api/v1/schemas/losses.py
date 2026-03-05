"""
Esquemas Pydantic para endpoints de pérdidas

Define modelos de respuesta para datos de pérdidas de energía.

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
Actualización FASE 3: 3 de marzo de 2026 — Pérdidas No Técnicas
"""

from typing import List, Optional
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


# ================================================================
# FASE 3: Esquemas Pérdidas No Técnicas
# ================================================================

class LossesDetailedRecord(BaseModel):
    """Un registro diario de losses_detailed."""
    fecha: DateType
    perdidas_total_pct: Optional[float] = None
    perdidas_tecnicas_pct: Optional[float] = None
    perdidas_nt_pct: Optional[float] = None
    perdidas_stn_pct: Optional[float] = None
    generacion_gwh: Optional[float] = None
    demanda_gwh: Optional[float] = None
    perdidas_total_gwh: Optional[float] = None
    perdidas_tecnicas_gwh: Optional[float] = None
    perdidas_nt_gwh: Optional[float] = None
    costo_nt_mcop: Optional[float] = None
    precio_bolsa_cop_kwh: Optional[float] = None
    confianza: Optional[str] = None
    anomalia_detectada: Optional[bool] = None
    fuentes_ok: Optional[int] = None


class LossesDetailedResponse(BaseModel):
    """Respuesta del endpoint /losses/detailed."""
    status: str = Field(default="ok", description="Estado de la respuesta")
    start_date: DateType = Field(..., description="Fecha inicial del rango")
    end_date: DateType = Field(..., description="Fecha final del rango")
    total_records: int = Field(..., description="Registros retornados")
    data: List[LossesDetailedRecord] = Field(..., description="Registros diarios de pérdidas")


class LossesNTSummaryResponse(BaseModel):
    """Respuesta del endpoint /losses/nt-summary."""
    status: str = Field(default="ok", description="Estado de la respuesta")
    total_dias: Optional[int] = Field(None, description="Total días con datos")
    pct_promedio_total: Optional[float] = Field(None, description="% pérdidas totales promedio")
    pct_promedio_tecnicas: Optional[float] = Field(None, description="% pérdidas técnicas promedio")
    pct_promedio_nt: Optional[float] = Field(None, description="% PNT promedio histórico")
    pct_promedio_nt_30d: Optional[float] = Field(None, description="% PNT promedio últimos 30 días")
    pct_promedio_nt_12m: Optional[float] = Field(None, description="% PNT promedio últimos 12 meses")
    pct_promedio_total_30d: Optional[float] = Field(None, description="% pérdidas totales últimos 30 días")
    anomalias_30d: Optional[int] = Field(None, description="Días con anomalía en últimos 30 días")
    tendencia_nt: Optional[str] = Field(None, description="Tendencia PNT: MEJORANDO/ESTABLE/EMPEORANDO")
    dias_anomalia: Optional[int] = Field(None, description="Total días con anomalía")
    costo_nt_historico_mcop: Optional[float] = Field(None, description="Costo PNT acumulado (Millones COP)")
    costo_nt_12m_mcop: Optional[float] = Field(None, description="Costo PNT últimos 12 meses (Millones COP)")
