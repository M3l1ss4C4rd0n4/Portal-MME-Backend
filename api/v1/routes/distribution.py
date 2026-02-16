"""
Endpoints de distribución eléctrica

Proporciona acceso a datos de:
- Datos de distribución por operador
- Energía distribuida
- Métricas de calidad del servicio

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import Optional, List
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from api.v1.schemas.common import ErrorResponse, MetricPoint
from api.v1.schemas.distribution import (
    DistributionDataResponse,
    DistributionOperatorsResponse
)
from domain.services.distribution_service import DistributionService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/data",
    response_model=DistributionDataResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Datos de distribución",
    description="""
    Obtiene datos agregados de distribución de energía.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    - `operator`: Filtrar por operador (opcional)
    """
)
@limiter.limit("100/minute")
async def get_distribution_data(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    operator: Optional[str] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> DistributionDataResponse:
    """Obtiene datos de distribución"""
    try:
        service = DistributionService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_distribution_data(start_date, end_date, operator)
        
        if df.empty:
            return DistributionDataResponse(
                metric="distribution_energy",
                description="Energía distribuida por operadores",
                unit="GWh",
                start_date=start_date,
                end_date=end_date,
                operator=operator,
                data=[],
                total_records=0
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row.get('valor', 0), 2),
                agent=row.get('operador', operator),
                metadata={"unit": "GWh"}
            )
            for _, row in df.iterrows()
        ]
        
        return DistributionDataResponse(
            metric="distribution_energy",
            description="Energía distribuida por operadores",
            unit="GWh",
            start_date=start_date,
            end_date=end_date,
            operator=operator,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo datos de distribución: {str(e)}"
        )


@router.get(
    "/operators",
    response_model=DistributionOperatorsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Operadores no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Catálogo de operadores de distribución",
    description="""
    Obtiene el listado de operadores de red de distribución.
    """
)
@limiter.limit("100/minute")
async def get_distribution_operators(
    request: Request,
    api_key: str = Depends(get_api_key)
) -> DistributionOperatorsResponse:
    """Obtiene listado de operadores"""
    try:
        service = DistributionService()
        
        df = service.get_operators()
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron operadores de distribución"
            )
        
        operators = [
            {
                "name": row.get('operador', ''),
                "region": row.get('region', None),
                "coverage_area": row.get('area_cobertura', None)
            }
            for _, row in df.iterrows()
        ]
        
        return DistributionOperatorsResponse(
            total_operators=len(operators),
            operators=operators
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo operadores: {str(e)}"
        )
