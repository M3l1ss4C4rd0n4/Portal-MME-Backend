"""
Esquemas Pydantic para endpoints del Costo Unitario (CU)

Define modelos de respuesta para:
- CU actual (último día disponible)
- CU histórico (serie temporal)
- Desglose de componentes
- CU forecast (predicción ML)

Autor: Arquitectura Dashboard MME — FASE 2
Actualizado: FASE 4 (forecast endpoint)
"""

from typing import List, Optional
from datetime import date as DateType
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# MODELOS BASE
# ═══════════════════════════════════════════════════════════

class CUComponente(BaseModel):
    """Un componente del CU con valor y porcentaje."""
    nombre: str = Field(..., description="Nombre del componente")
    codigo: str = Field(..., description="Código corto (G, T, D, C, P, R)")
    valor_cop_kwh: float = Field(..., description="Valor en COP/kWh")
    porcentaje: float = Field(..., description="Porcentaje sobre el CU total")

    class Config:
        json_schema_extra = {
            "example": {
                "nombre": "Generación",
                "codigo": "G",
                "valor_cop_kwh": 114.6,
                "porcentaje": 48.2
            }
        }


class CUDatoResponse(BaseModel):
    """Un registro de CU diario."""
    fecha: DateType = Field(..., description="Fecha del cálculo")
    componente_g: Optional[float] = Field(None, description="Componente Generación (COP/kWh)")
    componente_t: float = Field(..., description="Componente Transmisión (COP/kWh)")
    componente_d: float = Field(..., description="Componente Distribución (COP/kWh)")
    componente_c: float = Field(..., description="Componente Comercialización (COP/kWh)")
    componente_p: Optional[float] = Field(None, description="Componente Pérdidas (COP/kWh)")
    componente_r: Optional[float] = Field(None, description="Componente Restricciones (COP/kWh)")
    cu_total: float = Field(..., description="CU total (COP/kWh)")
    demanda_gwh: Optional[float] = Field(None, description="Demanda comercial (GWh)")
    generacion_gwh: Optional[float] = Field(None, description="Generación total (GWh)")
    perdidas_gwh: Optional[float] = Field(None, description="Pérdidas energía (GWh)")
    perdidas_pct: Optional[float] = Field(None, description="Pérdidas totales (%)")
    fuentes_ok: int = Field(..., description="Número de fuentes con dato")
    confianza: str = Field(..., description="Nivel de confianza: alta, media, baja")
    notas: Optional[str] = Field(None, description="Notas de cálculo")

    class Config:
        json_schema_extra = {
            "example": {
                "fecha": "2026-02-25",
                "componente_g": 114.6,
                "componente_t": 8.5,
                "componente_d": 35.0,
                "componente_c": 12.0,
                "componente_p": 17.8,
                "componente_r": 1.2,
                "cu_total": 189.1,
                "demanda_gwh": 243.7,
                "generacion_gwh": 243.7,
                "perdidas_gwh": 4.36,
                "perdidas_pct": 10.29,
                "fuentes_ok": 5,
                "confianza": "alta",
                "notas": None
            }
        }


# ═══════════════════════════════════════════════════════════
# RESPUESTAS DE ENDPOINTS
# ═══════════════════════════════════════════════════════════

class CUCurrentResponse(BaseModel):
    """Respuesta del endpoint /cu/current."""
    status: str = Field("ok", description="Estado de la respuesta")
    fecha: DateType = Field(..., description="Fecha del CU")
    cu_total: float = Field(..., description="CU total en COP/kWh")
    confianza: str = Field(..., description="Nivel de confianza")
    componente_g: Optional[float] = None
    componente_t: float = 0
    componente_d: float = 0
    componente_c: float = 0
    componente_p: Optional[float] = None
    componente_r: Optional[float] = None
    demanda_gwh: Optional[float] = None
    generacion_gwh: Optional[float] = None
    perdidas_pct: Optional[float] = None
    fuentes_ok: int = 0
    notas: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "fecha": "2026-02-25",
                "cu_total": 189.1,
                "confianza": "alta",
                "componente_g": 114.6,
                "componente_t": 8.5,
                "componente_d": 35.0,
                "componente_c": 12.0,
                "componente_p": 17.8,
                "componente_r": 1.2,
                "demanda_gwh": 243.7,
                "generacion_gwh": 243.7,
                "perdidas_pct": 10.29,
                "fuentes_ok": 5,
                "notas": None
            }
        }


class CUHistoricoResponse(BaseModel):
    """Respuesta del endpoint /cu/history."""
    status: str = Field("ok", description="Estado de la respuesta")
    fecha_inicio: DateType = Field(..., description="Fecha inicial del rango")
    fecha_fin: DateType = Field(..., description="Fecha final del rango")
    total_registros: int = Field(..., description="Registros con dato")
    total_dias: int = Field(..., description="Total de días en el rango")
    cobertura_pct: float = Field(..., description="Porcentaje de días con dato")
    data: List[CUDatoResponse] = Field(..., description="Serie temporal de CU")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "fecha_inicio": "2026-02-01",
                "fecha_fin": "2026-02-25",
                "total_registros": 25,
                "total_dias": 25,
                "cobertura_pct": 100.0,
                "data": []
            }
        }


class CUBreakdownResponse(BaseModel):
    """Respuesta del endpoint /cu/components."""
    status: str = Field("ok", description="Estado de la respuesta")
    fecha: DateType = Field(..., description="Fecha del desglose")
    cu_total: float = Field(..., description="CU total en COP/kWh")
    componentes: List[CUComponente] = Field(..., description="Desglose por componente")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "fecha": "2026-02-25",
                "cu_total": 189.1,
                "componentes": [
                    {"nombre": "Generación", "codigo": "G",
                     "valor_cop_kwh": 114.6, "porcentaje": 60.6},
                    {"nombre": "Transmisión", "codigo": "T",
                     "valor_cop_kwh": 8.5, "porcentaje": 4.5},
                    {"nombre": "Distribución", "codigo": "D",
                     "valor_cop_kwh": 35.0, "porcentaje": 18.5},
                    {"nombre": "Comercialización", "codigo": "C",
                     "valor_cop_kwh": 12.0, "porcentaje": 6.3},
                    {"nombre": "Pérdidas", "codigo": "P",
                     "valor_cop_kwh": 17.8, "porcentaje": 9.4},
                    {"nombre": "Restricciones", "codigo": "R",
                     "valor_cop_kwh": 1.2, "porcentaje": 0.6},
                ]
            }
        }


# ═══════════════════════════════════════════════════════════
# FASE 4: FORECAST (predicción ML del CU)
# ═══════════════════════════════════════════════════════════

class CUForecastPoint(BaseModel):
    """Un punto de la predicción del CU."""
    fecha: DateType = Field(..., description="Fecha predicha")
    valor_predicho: float = Field(..., description="CU predicho (COP/kWh)")
    intervalo_inferior: float = Field(..., description="Límite inferior del intervalo de confianza")
    intervalo_superior: float = Field(..., description="Límite superior del intervalo de confianza")

    class Config:
        json_schema_extra = {
            "example": {
                "fecha": "2026-03-15",
                "valor_predicho": 192.5,
                "intervalo_inferior": 178.3,
                "intervalo_superior": 206.7,
            }
        }


class CUForecastResponse(BaseModel):
    """Respuesta del endpoint /cu/forecast."""
    status: str = Field("ok", description="Estado de la respuesta")
    fuente: str = Field("CU_DIARIO", description="Fuente de la predicción")
    modelo: Optional[str] = Field(None, description="Modelo ML usado (ej: Prophet+SARIMA)")
    cu_actual: Optional[float] = Field(None, description="CU del último día disponible (COP/kWh)")
    fecha_actual: Optional[DateType] = Field(None, description="Fecha del CU actual")
    horizonte_dias: int = Field(..., description="Horizonte de predicción (días)")
    total_puntos: int = Field(..., description="Número de puntos predichos")
    mape_entrenamiento: Optional[float] = Field(None, description="MAPE del modelo en entrenamiento (%)")
    confianza: Optional[str] = Field(None, description="Nivel de confianza del modelo")
    fecha_generacion: Optional[str] = Field(None, description="Fecha de generación de la predicción")
    metodo_fallback: bool = Field(False, description="True si se usa tendencia naive en vez de ML")
    forecast: List[CUForecastPoint] = Field(..., description="Serie de predicciones")
    cache_hit: bool = Field(False, description="True si la respuesta vino de cache Redis")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "fuente": "CU_DIARIO",
                "modelo": "Prophet+SARIMA",
                "cu_actual": 189.1,
                "fecha_actual": "2026-02-27",
                "horizonte_dias": 30,
                "total_puntos": 30,
                "mape_entrenamiento": 3.2,
                "confianza": "alta",
                "fecha_generacion": "2026-02-27T10:00:00",
                "metodo_fallback": False,
                "forecast": [
                    {
                        "fecha": "2026-02-28",
                        "valor_predicho": 190.2,
                        "intervalo_inferior": 176.0,
                        "intervalo_superior": 204.4,
                    }
                ],
                "cache_hit": False,
            }
        }
