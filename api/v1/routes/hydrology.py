"""
Endpoints de hidrología y recursos hídricos

Proporciona acceso a datos de:
- Aportes hídricos a embalses
- Niveles de embalses
- Volúmenes almacenados
- Energía embalsada (GWh-día)
- Históricos hidrológicos

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
from api.v1.schemas.hydrology import (
    HydrologyAportesResponse,
    HydrologyReservoirsResponse,
    HydrologyEnergyResponse
)
from domain.services.hydrology_service import HydrologyService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/aportes",
    response_model=HydrologyAportesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Aportes hídricos a embalses",
    description="""
    Obtiene los aportes hídricos diarios al sistema de embalses en m³/s.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional, por defecto: hace 30 días)
    - `end_date`: Fecha final (opcional, por defecto: hoy)
    - `reservoir`: Filtrar por embalse específico (opcional, por defecto: Sistema)
    """
)
@limiter.limit("100/minute")
async def get_hydrology_aportes(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    reservoir: str = Query(
        default="Sistema",
        description="Embalse específico o 'Sistema' para total nacional"
    ),
    api_key: str = Depends(get_api_key)
) -> HydrologyAportesResponse:
    """Obtiene aportes hídricos"""
    try:
        service = HydrologyService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_aportes_diarios(start_date, end_date, reservoir)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de aportes para {start_date} - {end_date}"
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor'], 2),
                resource=reservoir,
                metadata={"unit": "m³/s"}
            )
            for _, row in df.iterrows()
        ]
        
        return HydrologyAportesResponse(
            metric="hydrology_aportes",
            description="Aportes hídricos diarios a embalses",
            unit="m³/s",
            start_date=start_date,
            end_date=end_date,
            reservoir=reservoir,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo aportes hídricos: {str(e)}"
        )


@router.get(
    "/reservoirs",
    response_model=HydrologyReservoirsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Embalses no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Listado de embalses",
    description="""
    Obtiene el catálogo de embalses del sistema nacional.
    
    **Respuesta:** Lista de embalses con su capacidad útil y energética.
    """
)
@limiter.limit("100/minute")
async def get_hydrology_reservoirs(
    request: Request,
    api_key: str = Depends(get_api_key)
) -> HydrologyReservoirsResponse:
    """Obtiene listado de embalses"""
    try:
        service = HydrologyService()
        
        df = service.get_embalses()
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron embalses en el catálogo"
            )
        
        reservoirs = [
            {
                "name": row.get('embalse', ''),
                "capacity_gwh": round(row.get('capacidad_util_gwh', 0), 2) if row.get('capacidad_util_gwh') else None,
                "river": row.get('rio', None),
                "region": row.get('region', None)
            }
            for _, row in df.iterrows()
        ]
        
        return HydrologyReservoirsResponse(
            total_reservoirs=len(reservoirs),
            reservoirs=reservoirs
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo embalses: {str(e)}"
        )


@router.get(
    "/energy",
    response_model=HydrologyEnergyResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Energía embalsada (GWh-día)",
    description="""
    Obtiene la energía embalsada total del sistema en GWh-día.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    """
)
@limiter.limit("100/minute")
async def get_hydrology_energy(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> HydrologyEnergyResponse:
    """Obtiene energía embalsada"""
    try:
        service = HydrologyService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_energia_embalsada(start_date, end_date)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de energía embalsada"
            )
        
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor'], 2),
                resource="Sistema",
                metadata={"unit": "GWh-día"}
            )
            for _, row in df.iterrows()
        ]
        
        return HydrologyEnergyResponse(
            metric="hydrology_energy",
            description="Energía embalsada del sistema nacional",
            unit="GWh-día",
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
            detail=f"Error obteniendo energía embalsada: {str(e)}"
        )
