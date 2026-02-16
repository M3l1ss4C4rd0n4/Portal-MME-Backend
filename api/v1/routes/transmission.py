"""
Endpoints de transmisión eléctrica

Proporciona acceso a datos de:
- Líneas de transmisión
- Flujos de potencia
- Intercambios internacionales
- Cargabilidad de líneas

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import Optional, List
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.transmission import (
    TransmissionLinesResponse,
    TransmissionFlowsResponse,
    TransmissionInternationalResponse
)
from domain.services.transmission_service import TransmissionService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/lines",
    response_model=TransmissionLinesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Líneas no encontradas"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Catálogo de líneas de transmisión",
    description="""
    Obtiene el catálogo completo de líneas de transmisión del Sistema Interconectado Nacional.
    
    **Parámetros:**
    - `voltage_kv`: Filtrar por nivel de tensión (opcional)
    - `operator`: Filtrar por operador (opcional)
    """
)
@limiter.limit("100/minute")
async def get_transmission_lines(
    request: Request,
    voltage_kv: Optional[int] = Query(
        default=None,
        description="Nivel de tensión en kV (ej: 500, 230, 220, 110)"
    ),
    operator: Optional[str] = Query(
        default=None,
        description="Nombre del operador de red"
    ),
    api_key: str = Depends(get_api_key)
) -> TransmissionLinesResponse:
    """Obtiene catálogo de líneas de transmisión"""
    try:
        service = TransmissionService()
        
        df = service.get_lineas_transmision()
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron líneas de transmisión"
            )
        
        # Filtrar por tensión si se especifica
        if voltage_kv:
            df = df[df['tension_kv'] == voltage_kv]
        
        # Filtrar por operador si se especifica
        if operator:
            df = df[df['operador'].str.contains(operator, case=False, na=False)]
        
        lines = [
            {
                "name": row.get('nombre', ''),
                "from_substation": row.get('subestacion_origen', ''),
                "to_substation": row.get('subestacion_destino', ''),
                "voltage_kv": row.get('tension_kv', None),
                "operator": row.get('operador', None),
                "length_km": row.get('longitud_km', None),
                "capacity_mw": row.get('capacidad_mw', None)
            }
            for _, row in df.iterrows()
        ]
        
        return TransmissionLinesResponse(
            total_lines=len(lines),
            voltage_filter=voltage_kv,
            operator_filter=operator,
            lines=lines
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo líneas de transmisión: {str(e)}"
        )


@router.get(
    "/flows",
    response_model=TransmissionFlowsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Flujos de potencia",
    description="""
    Obtiene flujos de potencia en líneas de transmisión.
    
    **Nota:** Funcionalidad en desarrollo. Datos de ejemplo.
    """
)
@limiter.limit("100/minute")
async def get_transmission_flows(
    request: Request,
    target_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> TransmissionFlowsResponse:
    """Obtiene flujos de potencia (en desarrollo)"""
    try:
        # TODO: Implementar cuando tengamos datos de flujos
        return TransmissionFlowsResponse(
            date=target_date or date.today(),
            flows=[],
            total_records=0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo flujos: {str(e)}"
        )


@router.get(
    "/international",
    response_model=TransmissionInternationalResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Intercambios internacionales",
    description="""
    Obtiene datos de intercambios internacionales de energía (importaciones/exportaciones).
    
    **Países conectados:** Ecuador, Venezuela, Panamá
    """
)
@limiter.limit("100/minute")
async def get_transmission_international(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    api_key: str = Depends(get_api_key)
) -> TransmissionInternationalResponse:
    """Obtiene intercambios internacionales"""
    try:
        service = TransmissionService()
        
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        df = service.get_intercambios_internacionales(start_date, end_date)
        
        if df.empty:
            # Retornar respuesta vacía en vez de error
            return TransmissionInternationalResponse(
                metric="international_exchanges",
                description="Intercambios internacionales de energía",
                unit="GWh",
                start_date=start_date,
                end_date=end_date,
                data=[],
                total_records=0
            )
        
        data = [
            {
                "date": row['fecha'],
                "country": row.get('pais', 'Unknown'),
                "import_gwh": round(row.get('importacion_gwh', 0), 2),
                "export_gwh": round(row.get('exportacion_gwh', 0), 2),
                "net_gwh": round(row.get('neto_gwh', 0), 2)
            }
            for _, row in df.iterrows()
        ]
        
        return TransmissionInternationalResponse(
            metric="international_exchanges",
            description="Intercambios internacionales de energía",
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
            detail=f"Error obteniendo intercambios internacionales: {str(e)}"
        )
