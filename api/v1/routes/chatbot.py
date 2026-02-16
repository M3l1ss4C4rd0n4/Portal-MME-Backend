"""
Endpoint Orquestador para Chatbot

Este módulo implementa el endpoint único que consume el chatbot
conforme a las especificaciones del documento
"Requerimientos – Endpoint Orquestador para Chatbot".

Cumple con:
- Contrato de entrada/salida definido
- Manejo de errores robusto
- Seguridad (API Key obligatoria)
- Rate limiting
- Logging estructurado
- Timeouts configurados

Autor: Portal Energético MME
Fecha: 9 de febrero de 2026
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging

from api.dependencies import get_api_key
from domain.schemas.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    ErrorDetail
)
from domain.services.orchestrator_service import ChatbotOrchestratorService

# Configuración
logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/orchestrator",
    response_model=OrchestratorResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Respuesta exitosa (SUCCESS, PARTIAL_SUCCESS o ERROR)",
            "model": OrchestratorResponse
        },
        400: {
            "description": "Request inválido - Error de validación",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ERROR",
                        "message": "Error de validación en el request",
                        "data": {},
                        "errors": [
                            {
                                "code": "VALIDATION_ERROR",
                                "message": "sessionId no puede estar vacío",
                                "field": "sessionId"
                            }
                        ]
                    }
                }
            }
        },
        401: {
            "description": "No autorizado - API Key inválida o faltante",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "API Key inválida o faltante"
                    }
                }
            }
        },
        429: {
            "description": "Límite de rate excedido",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded: 100 per 1 minute"
                    }
                }
            }
        },
        500: {
            "description": "Error interno del servidor",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ERROR",
                        "message": "Error interno del servidor",
                        "data": {},
                        "errors": [
                            {
                                "code": "INTERNAL_ERROR",
                                "message": "Ocurrió un error inesperado"
                            }
                        ]
                    }
                }
            }
        }
    },
    summary="🤖 Orquestador de Chatbot",
    description="""
    **Endpoint único para consumo del chatbot - Indicadores Clave del Viceministro**
    
    Este endpoint actúa como orquestador central enfocado en 3 indicadores clave:
    - ⚡ Generación Total del Sistema (GWh)
    - 💰 Precio de Bolsa Nacional (COP/kWh)
    - 💧 Porcentaje de Embalses (%)
    
    Funcionalidades:
    - Recibe intents del chatbot con sus parámetros
    - Los mapea a los servicios backend apropiados
    - Consolida las respuestas
    - Maneja errores de forma robusta
    - Retorna respuestas estructuradas
    
    ## 🔐 Autenticación
    
    Requiere API Key en el header `X-API-Key`.
    
    ## 📋 Intents del Menú Principal (4 opciones)
    
    ### 1️⃣ Estado Actual del Sector
    - `estado_actual`, `como_esta_sistema`, `status_sistema`
    - Retorna 3 fichas con los indicadores clave: Generación Total, Precio de Bolsa, % Embalses
    - **Sin parámetros requeridos**
    
    ### 2️⃣ Predicciones del Sector
    - `predicciones_sector`, `predicciones_indicadores`
    - Predicciones de los 3 indicadores clave con horizonte temporal seleccionable
    - **Parámetros:**
      - `horizonte`: `1_semana`, `1_mes`, `6_meses`, `1_ano`, `personalizado`
      - `fecha_personalizada` (DD-MM-AAAA): Solo cuando horizonte es `personalizado`
    - **Ejemplo:**
      ```json
      {"intent": "predicciones_sector", "parameters": {"horizonte": "1_mes"}}
      ```
    
    ### 3️⃣ Anomalías Detectadas
    - `anomalias_sector`, `anomalias_detectadas`, `alertas`
    - Anomalías en estado actual + predicciones de los 3 indicadores
    - **Parámetros opcionales:**
      - `severidad_minima`: `WARNING`, `ALERT`, `CRITICAL`
    
    ### 4️⃣ Más Información → Sub-menú
    
    #### 4.1 Informe Ejecutivo Completo
    - `informe_ejecutivo`, `generar_informe`, `informe_completo`, `reporte_ejecutivo`
    - Todas las métricas con KPIs, predicciones, análisis estadístico y recomendaciones
    - **Parámetros opcionales:**
      - `sections` (array): Secciones específicas a incluir
      - `fecha_inicio`, `fecha_fin`: Rango de análisis
    
    #### 4.2 Pregunta Libre
    - `pregunta_libre`, `pregunta`, `consulta_libre`
    - El usuario escribe su pregunta y la IA responde con datos reales
    - **Parámetros:**
      - `pregunta` (string, requerido): La pregunta en lenguaje natural
    - **Ejemplo:**
      ```json
      {"intent": "pregunta_libre", "parameters": {"pregunta": "¿Cuánta energía solar se generó ayer?"}}
      ```
    
    ### 📋 Menú / Ayuda
    - `menu`, `ayuda`, `help`, `opciones`, `inicio`, `start`
    - Retorna el menú principal con las 4 opciones y sub-menús estructurados
    
    ### Intents Específicos (siguen disponibles para preguntas avanzadas)
    - Generación: `generacion_electrica`, `consultar_generacion`, `generacion`
    - Hidrología: `hidrologia`, `consultar_embalses`, `embalses`
    - Demanda: `demanda_sistema`, `consultar_demanda`, `demanda`
    - Precios: `precio_bolsa`, `precios_bolsa`, `consultar_precios`
    - Predicciones por fuente: `predicciones`, `pronostico`, `forecast`
    - Métricas generales: `metricas_generales`, `resumen_sistema`
    
    ## 📊 Estados de Respuesta
    
    - **SUCCESS**: Operación completamente exitosa
    - **PARTIAL_SUCCESS**: Respuesta parcial (algunos servicios fallaron)
    - **ERROR**: Error total en el procesamiento
    
    ## ⏱️ Timeouts
    
    - **Por servicio:** 10 segundos
    - **Total:** 30 segundos
    
    ## 🚦 Rate Limiting
    
    - **Límite:** 100 requests por minuto por IP
    
    ## 📝 Ejemplo de Request
    
    ```json
    {
      "sessionId": "chat_123456789",
      "intent": "generacion_electrica",
      "parameters": {
        "fecha": "2026-02-01",
        "recurso": "hidraulica"
      }
    }
    ```
    
    ## 📝 Ejemplo de Response (SUCCESS)
    
    ```json
    {
      "status": "SUCCESS",
      "message": "Consulta ejecutada exitosamente",
      "data": {
        "generacion_total_gwh": 245.6,
        "generacion_promedio_gwh": 245.6,
        "periodo": {
          "inicio": "2026-02-01",
          "fin": "2026-02-01"
        },
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
    }
    ```
    
    ## 📝 Ejemplo de Response (PARTIAL_SUCCESS)
    
    ```json
    {
      "status": "PARTIAL_SUCCESS",
      "message": "Consulta ejecutada parcialmente. Algunos servicios no disponibles.",
      "data": {
        "generacion_total_gwh": 245.6
      },
      "errors": [
        {
          "code": "PARTIAL_DATA",
          "message": "No se pudo obtener el detalle por recurso"
        }
      ],
      "timestamp": "2026-02-09T15:30:00Z",
      "sessionId": "chat_123456789",
      "intent": "generacion_electrica"
    }
    ```
    
    ## 📝 Ejemplo de Response (ERROR)
    
    ```json
    {
      "status": "ERROR",
      "message": "Intent no reconocido",
      "data": {},
      "errors": [
        {
          "code": "UNKNOWN_INTENT",
          "message": "El intent 'consultar_xyz' no está soportado",
          "field": "intent"
        }
      ],
      "timestamp": "2026-02-09T15:30:00Z",
      "sessionId": "chat_123456789",
      "intent": "consultar_xyz"
    }
    ```
    
    ## 🔒 Seguridad
    
    - ✅ Autenticación mediante API Key
    - ✅ Validación estricta de entrada (Pydantic)
    - ✅ Sanitización de parámetros
    - ✅ Sin exposición de detalles internos
    - ✅ Rate limiting
    - ✅ Timeouts configurados
    
    ## 📊 Monitoreo
    
    - Logs estructurados de cada request
    - Tracking por sessionId
    - Medición de tiempos de respuesta
    - Registro de errores detallado
    """,
    tags=["🤖 Chatbot"]
)
@limiter.limit("100/minute")
async def chatbot_orchestrator(
    request_data: OrchestratorRequest,
    request: Request,
    api_key: str = Depends(get_api_key)
) -> OrchestratorResponse:
    """
    Endpoint orquestador para el chatbot
    
    Recibe intents del chatbot y los orquesta a través de los servicios backend.
    
    Args:
        request_data: Request del chatbot con sessionId, intent y parameters
        request: Request HTTP de FastAPI (para rate limiting)
        api_key: API Key para autenticación (inyectada por dependencia)
        
    Returns:
        OrchestratorResponse con status, message, data y errors
        
    Raises:
        HTTPException: En caso de errores de validación (manejado automáticamente)
    """
    # Logging del request
    logger.info(
        f"[CHATBOT_ENDPOINT] Recibiendo request | "
        f"SessionId: {request_data.sessionId} | "
        f"Intent: {request_data.intent} | "
        f"IP: {request.client.host}"
    )
    
    try:
        # Instanciar el servicio orquestador
        orchestrator = ChatbotOrchestratorService()
        
        # Ejecutar orquestación
        response = await orchestrator.orchestrate(request_data)
        
        # Log del resultado
        logger.info(
            f"[CHATBOT_ENDPOINT] Respondiendo | "
            f"SessionId: {request_data.sessionId} | "
            f"Status: {response.status} | "
            f"Errors: {len(response.errors)}"
        )
        
        return response
        
    except Exception as e:
        # Este catch es para errores no manejados por el orquestador
        logger.error(
            f"[CHATBOT_ENDPOINT] Error crítico | "
            f"SessionId: {request_data.sessionId} | "
            f"Error: {str(e)}",
            exc_info=True
        )
        
        # Retornar error genérico sin exponer detalles internos
        return OrchestratorResponse(
            status="ERROR",
            message="Error interno del servidor",
            data={},
            errors=[
                ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Ocurrió un error inesperado al procesar la solicitud"
                )
            ],
            sessionId=request_data.sessionId,
            intent=request_data.intent
        )


@router.get(
    "/health",
    summary="Health Check del Orquestador",
    description="Verifica que el endpoint orquestador esté operativo",
    tags=["🤖 Chatbot"]
)
async def health_check():
    """
    Health check simple del orquestador
    
    Returns:
        Dict con status y timestamp
    """
    from datetime import datetime
    return {
        "status": "healthy",
        "service": "chatbot-orchestrator",
        "timestamp": datetime.utcnow().isoformat()
    }
