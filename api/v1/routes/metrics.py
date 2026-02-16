"""
Endpoints de métricas energéticas

Proporciona acceso a series temporales de:
- Generación eléctrica (por recurso)
- Demanda de energía
- Disponibilidad de recursos
- Precios de bolsa
- Intercambios internacionales

Sigue las convenciones de datos en docs/api_data_conventions.md

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import Optional, List
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_metrics_service
from api.v1.schemas.metrics import MetricSeriesResponse, MetricListResponse
from api.v1.schemas.common import ErrorResponse
from domain.services.metrics_service import MetricsService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/{metric_id}",
    response_model=MetricSeriesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Métrica no encontrada"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Obtener serie temporal de una métrica",
    description="""
    Obtiene los datos históricos de una métrica energética específica.
    
    **Métricas disponibles:**
    - `Gene`: Generación total del sistema (GWh)
    - `DemaReal`: Demanda real de energía (GWh)
    - `Dispo`: Disponibilidad efectiva neta (MW)
    - `PrecBols`: Precio de bolsa ($/kWh)
    - `Aportes`: Aportes hídricos (m³/s)
    
    **Parámetros opcionales:**
    - `entity`: Filtrar por entidad específica (ej: "HIDRAULICA", "TERMICA", "Sistema")
    - `start_date`: Fecha inicial (formato YYYY-MM-DD)
    - `end_date`: Fecha final (formato YYYY-MM-DD)
    
    **Respuesta:**
    Sigue el formato estándar definido en `docs/api_data_conventions.md`
    """
)
@limiter.limit("100/minute")
async def get_metric_series(
    request: Request,
    metric_id: str,
    entity: Optional[str] = Query(
        default="Sistema",
        description="Entidad o agrupación (Sistema, Recurso, Embalse, etc.)"
    ),
    start_date: Optional[date] = Query(
        default=None,
        description="Fecha inicial en formato YYYY-MM-DD"
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Fecha final en formato YYYY-MM-DD"
    ),
    api_key: str = Depends(get_api_key),
    service: MetricsService = Depends(get_metrics_service)
) -> MetricSeriesResponse:
    """
    Obtiene serie temporal de una métrica específica
    
    Args:
        request: Request de FastAPI (para rate limiting)
        metric_id: Código de la métrica XM
        entity: Entidad a filtrar (opcional)
        start_date: Fecha inicial (opcional)
        end_date: Fecha final (opcional)
        api_key: API Key validada
        service: Servicio de métricas inyectado
        
    Returns:
        Serie temporal en formato estándar de la API
        
    Raises:
        HTTPException 404: Si la métrica no existe o no tiene datos
        HTTPException 400: Si los parámetros son inválidos
        HTTPException 500: Error interno del servidor
    """
    try:
        # Convertir fechas a string si están presentes
        start_str = start_date.isoformat() if start_date else None
        end_str = end_date.isoformat() if end_date else None
        
        # Validar fechas
        if start_str and end_str and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha inicial debe ser anterior a la fecha final"
            )
        
        # Obtener datos usando el servicio de dominio
        df = service.get_metric_series_hybrid(
            metric_id=metric_id,
            start_date=start_str,
            end_date=end_str
        )
        
        # Verificar si hay datos
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos para la métrica '{metric_id}'"
            )
        
        # Convertir DataFrame a formato API
        return MetricSeriesResponse.from_dataframe(
            df=df,
            metric_id=metric_id,
            entity=entity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener métrica: {str(e)}"
        )


@router.get(
    "/",
    response_model=MetricListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Listar métricas disponibles",
    description="""
    Obtiene la lista de todas las métricas disponibles en la base de datos.
    
    **Respuesta:**
    Lista de métricas con información de:
    - Código de métrica (metric_id)
    - Nombre descriptivo
    - Unidad de medida
    - Última fecha disponible
    - Total de registros
    """
)
@limiter.limit("60/minute")
async def list_metrics(
    request: Request,
    api_key: str = Depends(get_api_key),
    service: MetricsService = Depends(get_metrics_service)
) -> MetricListResponse:
    """
    Lista todas las métricas disponibles
    
    Args:
        request: Request de FastAPI (para rate limiting)
        api_key: API Key validada
        service: Servicio de métricas inyectado
        
    Returns:
        Lista de métricas con metadatos
        
    Raises:
        HTTPException 500: Error interno del servidor
    """
    try:
        metrics_list = service.list_metrics()
        
        return MetricListResponse(
            count=len(metrics_list),
            metrics=metrics_list
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar métricas: {str(e)}"
        )
