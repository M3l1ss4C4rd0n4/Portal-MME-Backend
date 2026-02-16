"""
Endpoints de restricciones operativas

Proporciona acceso a datos de:
- Restricciones por generación térmica
- Restricciones por red de transporte
- Restricciones por seguridad del sistema

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
from api.v1.schemas.restrictions import RestrictionsResponse
from domain.services.restrictions_service import RestrictionsService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/data",
    response_model=RestrictionsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Restricciones operativas",
    description="""
    Obtiene datos de restricciones operativas del sistema.
    
    **Tipos de restricciones:**
    - Generación térmica obligada (seguridad)
    - Restricciones por congestión de red
    - Restricciones por condiciones operativas
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    - `restriction_type`: Tipo de restricción (opcional)
    """
)
@limiter.limit("100/minute")
async def get_restrictions_data(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    restriction_type: Optional[str] = Query(
        default=None,
        description="Tipo de restricción (generation, network, security)"
    ),
    api_key: str = Depends(get_api_key)
) -> RestrictionsResponse:
    """Obtiene datos de restricciones"""
    try:
        service = RestrictionsService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_restrictions_data(start_date, end_date, restriction_type)
        
        if df.empty:
            return RestrictionsResponse(
                metric="operational_restrictions",
                description="Restricciones operativas del sistema",
                unit="GWh",
                start_date=start_date,
                end_date=end_date,
                restriction_type=restriction_type,
                data=[],
                total_records=0
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row.get('restricciones', 0), 2),
                metadata={
                    "unit": "GWh",
                    "restriction_type": row.get('tipo', restriction_type),
                    "cost_mcop": round(row.get('costo_mcop', 0), 2) if 'costo_mcop' in row else None
                }
            )
            for _, row in df.iterrows()
        ]
        
        return RestrictionsResponse(
            metric="operational_restrictions",
            description="Restricciones operativas del sistema",
            unit="GWh",
            start_date=start_date,
            end_date=end_date,
            restriction_type=restriction_type,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo restricciones: {str(e)}"
        )
