"""
Endpoints de predicciones con Machine Learning

Proporciona acceso a predicciones generadas con:
- Prophet (Facebook)
- ARIMA (auto-tuning)
- Ensemble (combinación de modelos)

Sigue las convenciones de datos en docs/api_data_conventions.md

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import Optional, Literal
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_predictions_service
from api.v1.schemas.predictions import PredictionResponse
from api.v1.schemas.common import ErrorResponse
from domain.services.predictions_service_extended import PredictionsService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/{metric_id}",
    response_model=PredictionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Métrica no encontrada o sin datos históricos"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Generar predicción ML para una métrica",
    description="""
    Genera predicciones a futuro para una métrica energética usando Machine Learning.
    
    **Modelos disponibles:**
    - `prophet`: Facebook Prophet (recomendado para series con estacionalidad)
    - `arima`: ARIMA auto-tuning (recomendado para series estacionarias)
    - `ensemble`: Combinación de múltiples modelos (mayor precisión)
    
    **Parámetros:**
    - `metric_id`: Código de la métrica (Gene, DemaReal, Aportes, etc.)
    - `entity`: Entidad a predecir (Sistema, HIDRAULICA, etc.)
    - `horizon_days`: Días de proyección (7, 30, 90, 365)
    - `model_type`: Tipo de modelo ML a usar
    
    **Respuesta:**
    Predicciones con intervalos de confianza según formato en `docs/api_data_conventions.md`
    """
)
@limiter.limit("20/minute")
async def get_prediction(
    request: Request,
    metric_id: str,
    entity: Optional[str] = Query(
        default="Sistema",
        description="Entidad a predecir (Sistema, Recurso, etc.)"
    ),
    horizon_days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Días de proyección (1-365)"
    ),
    model_type: Literal["prophet", "arima", "ensemble"] = Query(
        default="prophet",
        description="Tipo de modelo ML a usar"
    ),
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> PredictionResponse:
    """
    Genera predicción ML para una métrica específica
    
    Args:
        request: Request de FastAPI (para rate limiting)
        metric_id: Código de la métrica XM
        entity: Entidad a predecir
        horizon_days: Días de proyección futura
        model_type: Tipo de modelo ML
        api_key: API Key validada
        service: Servicio de predicciones inyectado
        
    Returns:
        Predicción con intervalos de confianza
        
    Raises:
        HTTPException 404: Si la métrica no existe o no tiene datos históricos
        HTTPException 400: Si los parámetros son inválidos
        HTTPException 500: Error interno del servidor o error del modelo ML
    """
    try:
        # Generar predicción usando el servicio de dominio
        df_prediction = service.forecast_metric(
            metric_id=metric_id,
            horizon_days=horizon_days,
            model_type=model_type
        )
        
        # Verificar si se generó la predicción
        if df_prediction is None or df_prediction.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudo generar predicción para '{metric_id}'. Verifique que existan datos históricos suficientes."
            )
        
        # Convertir DataFrame a formato API
        return PredictionResponse.from_dataframe(
            df=df_prediction,
            metric_id=metric_id,
            entity=entity,
            model_type=model_type,
            horizon_days=horizon_days
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        # Errores de validación del modelo ML
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Errores internos del modelo ML
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar predicción: {str(e)}"
        )


@router.post(
    "/{metric_id}/train",
    response_model=dict,
    responses={
        404: {"model": ErrorResponse, "description": "Métrica no encontrada"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Entrenar modelo ML para una métrica",
    description="""
    Entrena y guarda un modelo ML específico para una métrica.
    
    **Nota:** Este endpoint puede tardar varios minutos dependiendo del tamaño de los datos.
    
    **Parámetros:**
    - `metric_id`: Código de la métrica
    - `model_type`: Tipo de modelo a entrenar
    - `save_model`: Si se debe guardar el modelo entrenado (default: True)
    
    **Respuesta:**
    Métricas de evaluación del modelo entrenado
    """
)
@limiter.limit("5/hour")
async def train_model(
    request: Request,
    metric_id: str,
    model_type: Literal["prophet", "arima", "ensemble"] = Query(
        default="prophet",
        description="Tipo de modelo ML a entrenar"
    ),
    save_model: bool = Query(
        default=True,
        description="Guardar modelo entrenado para uso futuro"
    ),
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> dict:
    """
    Entrena modelo ML para una métrica específica
    
    Args:
        request: Request de FastAPI (para rate limiting)
        metric_id: Código de la métrica XM
        model_type: Tipo de modelo ML
        save_model: Guardar modelo entrenado
        api_key: API Key validada
        service: Servicio de predicciones inyectado
        
    Returns:
        Métricas de evaluación del modelo
        
    Raises:
        HTTPException 404: Si la métrica no existe
        HTTPException 400: Si los parámetros son inválidos
        HTTPException 500: Error durante el entrenamiento
    """
    try:
        # Entrenar modelo
        metrics = service.train_and_save_model(
            metric_id=metric_id,
            model_type=model_type,
            save=save_model
        )
        
        return {
            "metric_id": metric_id,
            "model_type": model_type,
            "status": "trained",
            "saved": save_model,
            "metrics": metrics
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al entrenar modelo: {str(e)}"
        )
