"""
Endpoints de pérdidas de energía

Proporciona acceso a datos de:
- Pérdidas técnicas
- Pérdidas no técnicas
- Pérdidas por operador

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
from api.v1.schemas.losses import LossesResponse
from domain.services.losses_service import LossesService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/data",
    response_model=LossesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Pérdidas de energía",
    description="""
    Obtiene datos de pérdidas de energía en el sistema.
    
    **Tipos de pérdidas:**
    - Técnicas: Pérdidas por transmisión/distribución
    - No técnicas: Hurto, fraude, errores de medición
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    - `loss_type`: Tipo de pérdida (opcional: 'technical', 'non_technical', 'total')
    """
)
@limiter.limit("100/minute")
async def get_losses_data(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    loss_type: str = Query(
        default="total",
        description="Tipo de pérdida (technical, non_technical, total)"
    ),
    api_key: str = Depends(get_api_key)
) -> LossesResponse:
    """Obtiene datos de pérdidas"""
    try:
        service = LossesService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_losses_data(start_date, end_date, loss_type)
        
        if df.empty:
            return LossesResponse(
                metric="energy_losses",
                description=f"Pérdidas de energía ({loss_type})",
                unit="GWh",
                start_date=start_date,
                end_date=end_date,
                loss_type=loss_type,
                data=[],
                total_records=0
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row.get('perdidas', 0), 2),
                metadata={
                    "unit": "GWh",
                    "loss_type": loss_type,
                    "percentage": round(row.get('porcentaje', 0), 2) if 'porcentaje' in row else None
                }
            )
            for _, row in df.iterrows()
        ]
        
        return LossesResponse(
            metric="energy_losses",
            description=f"Pérdidas de energía ({loss_type})",
            unit="GWh",
            start_date=start_date,
            end_date=end_date,
            loss_type=loss_type,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo pérdidas: {str(e)}"
        )
