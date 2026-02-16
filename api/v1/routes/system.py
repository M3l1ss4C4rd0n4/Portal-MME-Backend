"""
Endpoints de sistema eléctrico (demanda, precios)

Proporciona acceso a datos de:
- Demanda real de energía
- Demanda máxima
- Precios de bolsa
- Precios por hora

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import Optional
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from api.v1.schemas.common import ErrorResponse, MetricPoint
from api.v1.schemas.system import DemandResponse, PricesResponse
from domain.services.metrics_service import MetricsService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/demand",
    response_model=DemandResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Demanda real de energía",
    description="""
    Obtiene la demanda real de energía del sistema nacional en GWh.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional, por defecto: hace 30 días)
    - `end_date`: Fecha final (opcional, por defecto: hoy)
    """
)
@limiter.limit("100/minute")
async def get_system_demand(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> DemandResponse:
    """Obtiene demanda real del sistema"""
    try:
        service = MetricsService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_metric_data(
            metric_id='DemaReal',
            entity='Sistema',
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de demanda"
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor_gwh'], 2),
                resource="Sistema",
                metadata={"unit": "GWh"}
            )
            for _, row in df.iterrows()
        ]
        
        return DemandResponse(
            metric="demand_real",
            description="Demanda real de energía del sistema nacional",
            unit="GWh",
            start_date=start_date,
            end_date=end_date,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo demanda: {str(e)}"
        )


@router.get(
    "/prices",
    response_model=PricesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Precios de bolsa",
    description="""
    Obtiene el precio promedio de bolsa de energía en $/kWh.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    """
)
@limiter.limit("100/minute")
async def get_system_prices(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> PricesResponse:
    """Obtiene precios de bolsa"""
    try:
        service = MetricsService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_metric_data(
            metric_id='PrecBols',
            entity='Sistema',
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de precios"
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor_original'], 2),
                resource="Sistema",
                metadata={"unit": "$/kWh"}
            )
            for _, row in df.iterrows()
        ]
        
        return PricesResponse(
            metric="prices_bolsa",
            description="Precio promedio de bolsa de energía",
            unit="$/kWh",
            start_date=start_date,
            end_date=end_date,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo precios: {str(e)}"
        )
