"""
Schemas para el Endpoint Orquestador del Chatbot

Este módulo define los contratos de entrada y salida del endpoint
orquestador conforme a los requerimientos definidos en el documento
"Requerimientos – Endpoint Orquestador para Chatbot".

Autor: Portal Energético MME
Fecha: 9 de febrero de 2026
"""

from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE REQUEST
# ═══════════════════════════════════════════════════════════

class OrchestratorRequest(BaseModel):
    """
    Schema del request del orquestador
    
    Cumple con especificaciones del documento de requerimientos sección 5.
    """
    sessionId: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador único de la conversación/sesión del chatbot",
        examples=["chat_123456789", "session_abc123"]
    )
    
    intent: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Intención detectada por el chatbot",
        examples=["generacion_electrica", "consultar_embalses", "precio_bolsa"]
    )
    
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros dinámicos según la intención",
        examples=[
            {"fecha": "2026-02-01", "recurso": "hidraulica"},
            {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"}
        ]
    )
    
    @validator('sessionId')
    def validate_session_id(cls, v):
        """Validar que sessionId no contenga caracteres especiales peligrosos"""
        if not v or not v.strip():
            raise ValueError("sessionId no puede estar vacío")
        # Sanitización básica
        dangerous_chars = ['<', '>', '&', '"', "'", '\\', '/', '\x00']
        if any(char in v for char in dangerous_chars):
            raise ValueError("sessionId contiene caracteres no permitidos")
        return v.strip()
    
    @validator('intent')
    def validate_intent(cls, v):
        """Validar que intent sea alfanumérico con guiones bajos"""
        if not v or not v.strip():
            raise ValueError("intent no puede estar vacío")
        # Permitir solo letras, números y guiones bajos
        if not all(c.isalnum() or c in ['_', '-'] for c in v):
            raise ValueError("intent solo puede contener letras, números, guiones y guiones bajos")
        return v.strip().lower()

    class Config:
        json_schema_extra = {
            "example": {
                "sessionId": "chat_123456789",
                "intent": "generacion_electrica",
                "parameters": {
                    "fecha": "2026-02-01",
                    "recurso": "hidraulica"
                }
            }
        }


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE RESPONSE
# ═══════════════════════════════════════════════════════════

class ErrorDetail(BaseModel):
    """Detalle de un error específico"""
    code: str = Field(
        ...,
        description="Código del error",
        examples=["VALIDATION_ERROR", "SERVICE_UNAVAILABLE", "TIMEOUT"]
    )
    message: str = Field(
        ...,
        description="Mensaje descriptivo del error (apto para usuario final)",
        examples=["Parámetro 'fecha' es requerido", "Servicio temporalmente no disponible"]
    )
    field: Optional[str] = Field(
        None,
        description="Campo relacionado con el error (para errores de validación)",
        examples=["parameters.fecha", "intent"]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "VALIDATION_ERROR",
                "message": "El parámetro 'fecha' es requerido para esta consulta",
                "field": "parameters.fecha"
            }
        }


class OrchestratorResponse(BaseModel):
    """
    Schema del response del orquestador
    
    Cumple con especificaciones del documento de requerimientos sección 6.
    """
    status: Literal["SUCCESS", "PARTIAL_SUCCESS", "ERROR"] = Field(
        ...,
        description=(
            "Estado de la operación:\n"
            "- SUCCESS: Procesamiento exitoso completo\n"
            "- PARTIAL_SUCCESS: Respuesta parcial por fallos en servicios internos\n"
            "- ERROR: Error total en el procesamiento"
        )
    )
    
    message: str = Field(
        ...,
        description="Mensaje descriptivo del resultado (apto para usuario final)",
        examples=[
            "Consulta ejecutada exitosamente",
            "Datos obtenidos parcialmente, algunos servicios no disponibles",
            "Error al procesar la solicitud"
        ]
    )
    
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Datos de respuesta según el intent ejecutado"
    )
    
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="Lista de errores (vacía si status=SUCCESS)"
    )
    
    # Metadatos adicionales útiles (no obligatorios pero recomendados)
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de la respuesta en UTC"
    )
    
    sessionId: Optional[str] = Field(
        None,
        description="Echo del sessionId enviado en el request (útil para tracking)"
    )
    
    intent: Optional[str] = Field(
        None,
        description="Echo del intent procesado (útil para tracking)"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                # Ejemplo SUCCESS
                {
                    "status": "SUCCESS",
                    "message": "Datos de generación eléctrica obtenidos exitosamente",
                    "data": {
                        "fecha": "2026-02-01",
                        "generacion_total_gwh": 245.6,
                        "por_recurso": {
                            "hidraulica": 156.2,
                            "termica": 68.4,
                            "solar": 15.3,
                            "eolica": 5.7
                        }
                    },
                    "errors": [],
                    "timestamp": "2026-02-09T15:30:00Z",
                    "sessionId": "chat_123456789",
                    "intent": "generacion_electrica"
                },
                # Ejemplo PARTIAL_SUCCESS
                {
                    "status": "PARTIAL_SUCCESS",
                    "message": "Datos obtenidos parcialmente. Servicio de predicciones no disponible",
                    "data": {
                        "historico": {
                            "demanda_promedio_mw": 8500
                        }
                    },
                    "errors": [
                        {
                            "code": "SERVICE_UNAVAILABLE",
                            "message": "Servicio de predicciones temporalmente no disponible"
                        }
                    ],
                    "timestamp": "2026-02-09T15:30:00Z",
                    "sessionId": "chat_123456789",
                    "intent": "demanda_sistema"
                },
                # Ejemplo ERROR
                {
                    "status": "ERROR",
                    "message": "Error al procesar la solicitud",
                    "data": {},
                    "errors": [
                        {
                            "code": "VALIDATION_ERROR",
                            "message": "El parámetro 'fecha' es obligatorio para este intent",
                            "field": "parameters.fecha"
                        }
                    ],
                    "timestamp": "2026-02-09T15:30:00Z",
                    "sessionId": "chat_123456789",
                    "intent": "generacion_electrica"
                }
            ]
        }


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE INTENTS (Estructuras de datos específicas)
# ═══════════════════════════════════════════════════════════

class IntentParameters(BaseModel):
    """Base class para parámetros de intents"""
    pass


class GeneracionElectricaParams(IntentParameters):
    """Parámetros para intent 'generacion_electrica'"""
    fecha: Optional[str] = Field(None, description="Fecha en formato YYYY-MM-DD")
    fecha_inicio: Optional[str] = Field(None, description="Fecha inicial para rango")
    fecha_fin: Optional[str] = Field(None, description="Fecha final para rango")
    recurso: Optional[str] = Field(None, description="Tipo de recurso: hidraulica, termica, solar, eolica")
    

class HidrologiaParams(IntentParameters):
    """Parámetros para intent 'hidrologia' o 'consultar_embalses'"""
    fecha: Optional[str] = Field(None, description="Fecha en formato YYYY-MM-DD")
    embalse: Optional[str] = Field(None, description="Nombre del embalse específico")
    

class DemandaSistemaParams(IntentParameters):
    """Parámetros para intent 'demanda_sistema'"""
    fecha: Optional[str] = Field(None, description="Fecha en formato YYYY-MM-DD")
    fecha_inicio: Optional[str] = Field(None, description="Fecha inicial para rango")
    fecha_fin: Optional[str] = Field(None, description="Fecha final para rango")


class PreciosBolsaParams(IntentParameters):
    """Parámetros para intent 'precio_bolsa' o 'precios_bolsa'"""
    fecha: Optional[str] = Field(None, description="Fecha en formato YYYY-MM-DD")
    fecha_inicio: Optional[str] = Field(None, description="Fecha inicial para rango")
    fecha_fin: Optional[str] = Field(None, description="Fecha final para rango")


class PrediccionesParams(IntentParameters):
    """Parámetros para intent 'predicciones'"""
    tipo: Optional[str] = Field(
        None, 
        description="Tipo de predicción: demanda, generacion, precios"
    )
    horizonte: Optional[int] = Field(
        None,
        description="Horizonte de predicción en días",
        ge=1,
        le=90
    )


# ═══════════════════════════════════════════════════════════
# SCHEMAS PARA ANÁLISIS INTELIGENTE (NUEVOS)
# ═══════════════════════════════════════════════════════════

class AnomaliaSchema(BaseModel):
    """Schema para una anomalía detectada"""
    sector: str = Field(..., description="Sector donde se detectó la anomalía")
    metrica: str = Field(..., description="Métrica afectada")
    severidad: str = Field(
        ..., 
        description="Nivel de severidad: CRITICAL, ALERT, WARNING, INFO, NORMAL"
    )
    severidad_nivel: int = Field(..., description="Nivel numérico de severidad (0-4)")
    valor_actual: Optional[float] = Field(None, description="Valor actual de la métrica")
    valor_esperado: Optional[float] = Field(None, description="Valor esperado o normal")
    umbral: Optional[float] = Field(None, description="Umbral definido para esta métrica")
    descripcion: str = Field(..., description="Descripción legible de la anomalía")
    timestamp: Optional[str] = Field(None, description="Timestamp de la detección")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sector": "hidrologia",
                "metrica": "nivel_embalses",
                "severidad": "ALERT",
                "severidad_nivel": 3,
                "valor_actual": 38.5,
                "valor_esperado": 60.0,
                "umbral": 40.0,
                "descripcion": "Nivel de embalses por debajo del 40% - Situación de alerta",
                "timestamp": "2026-02-09T15:30:00Z"
            }
        }


class SectorStatusSchema(BaseModel):
    """Schema para el estado de un sector"""
    estado: str = Field(
        ..., 
        description="Estado del sector: EXCELLENT, GOOD, REGULAR, CRITICAL"
    )
    kpis: Dict[str, Any] = Field(
        default_factory=dict,
        description="Indicadores clave del sector"
    )
    tendencias: Dict[str, str] = Field(
        default_factory=dict,
        description="Tendencias detectadas: UP, DOWN, STABLE"
    )
    numero_anomalias: int = Field(0, description="Número total de anomalías detectadas")
    anomalias_criticas: List[AnomaliaSchema] = Field(
        default_factory=list,
        description="Lista de anomalías críticas y alertas"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "estado": "REGULAR",
                "kpis": {
                    "nivel_promedio": 38.5,
                    "energia_embalsada_gwh": 5240.3,
                    "aportes_diarios_gwh": 45.2
                },
                "tendencias": {
                    "nivel_embalses": "DOWN",
                    "aportes": "STABLE"
                },
                "numero_anomalias": 2,
                "anomalias_criticas": [
                    {
                        "sector": "hidrologia",
                        "metrica": "nivel_embalses",
                        "severidad": "ALERT",
                        "severidad_nivel": 3,
                        "valor_actual": 38.5,
                        "valor_esperado": 60.0,
                        "umbral": 40.0,
                        "descripcion": "Nivel de embalses por debajo del 40%",
                        "timestamp": "2026-02-09T15:30:00Z"
                    }
                ]
            }
        }


class EstadoActualParams(IntentParameters):
    """Parámetros para intent 'estado_actual' o 'como_esta_sistema'"""
    incluir_predicciones: Optional[bool] = Field(
        False,
        description="Si incluir predicciones SARIMA en el análisis"
    )
    sectores: Optional[List[str]] = Field(
        None,
        description="Lista de sectores específicos a analizar (si no se especifica, analiza todos)"
    )


class AnomaliasParams(IntentParameters):
    """Parámetros para intent 'anomalias_detectadas' o 'problemas_sistema'"""
    severidad_minima: Optional[str] = Field(
        "WARNING",
        description="Severidad mínima a reportar: INFO, WARNING, ALERT, CRITICAL"
    )
    sector: Optional[str] = Field(
        None,
        description="Filtrar anomalías de un sector específico"
    )


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE RESPUESTA COMPLEJA (NUEVOS)
# ═══════════════════════════════════════════════════════════

class EstadoActualResponse(BaseModel):
    """Response estructurado para intent 'estado_actual'"""
    estado_general: str = Field(
        ..., 
        description="Estado general del sistema: EXCELLENT, GOOD, REGULAR, CRITICAL"
    )
    resumen_ejecutivo: str = Field(
        ...,
        description="Resumen ejecutivo en lenguaje natural"
    )
    sectores: Dict[str, SectorStatusSchema] = Field(
        default_factory=dict,
        description="Estado detallado por sector"
    )
    resumen_anomalias: Dict[str, int] = Field(
        default_factory=dict,
        description="Conteo de anomalías por severidad"
    )
    fecha_analisis: str = Field(..., description="Fecha/hora del análisis")
    
    class Config:
        json_schema_extra = {
            "example": {
                "estado_general": "REGULAR",
                "resumen_ejecutivo": "⚠️ SITUACIÓN REGULAR - Sistema operando con algunas alertas. Nivel de embalses en 38.5% (ALERTA). Generación estable. Demanda dentro de rangos normales.",
                "sectores": {
                    "generacion": {
                        "estado": "GOOD",
                        "kpis": {"generacion_actual_gw": 8.5},
                        "tendencias": {"generacion": "STABLE"},
                        "numero_anomalias": 0,
                        "anomalias_criticas": []
                    },
                    "hidrologia": {
                        "estado": "REGULAR",
                        "kpis": {"nivel_promedio": 38.5},
                        "tendencias": {"nivel": "DOWN"},
                        "numero_anomalias": 1,
                        "anomalias_criticas": []
                    }
                },
                "resumen_anomalias": {
                    "total": 2,
                    "criticas": 0,
                    "alertas": 1,
                    "advertencias": 1
                },
                "fecha_analisis": "2026-02-09T15:30:00Z"
            }
        }


class AnomaliasResponse(BaseModel):
    """Response estructurado para intent 'anomalias_detectadas'"""
    total_anomalias: int = Field(..., description="Número total de anomalías detectadas")
    mensaje: str = Field(..., description="Mensaje resumen sobre las anomalías")
    anomalias_por_sector: Dict[str, List[AnomaliaSchema]] = Field(
        default_factory=dict,
        description="Anomalías agrupadas por sector"
    )
    anomalias_por_severidad: Dict[str, List[AnomaliaSchema]] = Field(
        default_factory=dict,
        description="Anomalías agrupadas por nivel de severidad"
    )
    filtros_aplicados: Dict[str, Any] = Field(
        default_factory=dict,
        description="Filtros que se aplicaron en la búsqueda"
    )
    fecha_analisis: str = Field(..., description="Fecha/hora del análisis")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_anomalias": 3,
                "mensaje": "⚠️ Se detectaron 1 anomalías CRÍTICAS que requieren atención inmediata",
                "anomalias_por_sector": {
                    "hidrologia": [
                        {
                            "sector": "hidrologia",
                            "metrica": "nivel_embalses",
                            "severidad": "CRITICAL",
                            "severidad_nivel": 4,
                            "valor_actual": 28.5,
                            "umbral": 30.0,
                            "descripcion": "Nivel crítico de embalses (<30%)",
                            "timestamp": "2026-02-09T15:30:00Z"
                        }
                    ]
                },
                "anomalias_por_severidad": {
                    "CRITICAL": [],
                    "ALERT": []
                },
                "filtros_aplicados": {
                    "severidad_minima": "WARNING",
                    "sector": None
                },
                "fecha_analisis": "2026-02-09T15:30:00Z"
            }
        }
