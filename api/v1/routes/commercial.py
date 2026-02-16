"""
Endpoints de datos comerciales y precios

Proporciona acceso a datos de:
- Precios de contratos
- Precios por agente
- Precios promedio

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
from api.v1.schemas.commercial import CommercialPricesResponse
from domain.services.commercial_service import CommercialService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/prices",
    response_model=CommercialPricesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Precios comerciales de energía",
    description="""
    Obtiene precios comerciales de energía en el mercado.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    - `agent`: Filtrar por agente específico (opcional)
    """
)
@limiter.limit("100/minute")
async def get_commercial_prices(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    agent: Optional[str] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> CommercialPricesResponse:
    """Obtiene precios comerciales"""
    try:
        service = CommercialService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_commercial_prices(start_date, end_date, agent)
        
        if df.empty:
            return CommercialPricesResponse(
                metric="commercial_prices",
                description="Precios comerciales de energía",
                unit="$/kWh",
                start_date=start_date,
                end_date=end_date,
                agent=agent,
                data=[],
                total_records=0
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row.get('precio', 0), 2),
                agent=row.get('agente', agent),
                metadata={"unit": "$/kWh"}
            )
            for _, row in df.iterrows()
        ]
        
        return CommercialPricesResponse(
            metric="commercial_prices",
            description="Precios comerciales de energía",
            unit="$/kWh",
            start_date=start_date,
            end_date=end_date,
            agent=agent,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo precios comerciales: {str(e)}"
        )


@router.get(
    "/contracts",
    response_model=CommercialPricesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Precios de contratos",
    description="""
    Obtiene precios de contratos bilaterales de energía.
    
    **Nota:** Funcionalidad en desarrollo.
    """
)
@limiter.limit("100/minute")
async def get_commercial_contracts(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> CommercialPricesResponse:
    """Obtiene precios de contratos (en desarrollo)"""
    try:
        # TODO: Implementar cuando tengamos datos de contratos
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        return CommercialPricesResponse(
            metric="contract_prices",
            description="Precios de contratos bilaterales",
            unit="$/kWh",
            start_date=start_date,
            end_date=end_date,
            agent=None,
            data=[],
            total_records=0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo contratos: {str(e)}"
        )
