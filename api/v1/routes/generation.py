"""
Endpoints de generación eléctrica

Proporciona acceso a datos de:
- Generación total del sistema
- Generación por fuente (hidráulica, térmica, eólica, solar)
- Generación por recurso individual
- Mix energético
- Históricos de generación

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from typing import Optional, List
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from api.v1.schemas.common import ErrorResponse, MetricPoint
from api.v1.schemas.generation import (
    GenerationSystemResponse,
    GenerationBySourceResponse,
    GenerationResourcesResponse,
    GenerationMixResponse
)
from domain.services.generation_service import GenerationService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/system",
    response_model=GenerationSystemResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Generación total del sistema",
    description="""
    Obtiene la generación eléctrica total del sistema nacional en GWh.
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional, por defecto: hace 30 días)
    - `end_date`: Fecha final (opcional, por defecto: hoy)
    
    **Respuesta:**
    Serie temporal con la generación diaria total en GWh.
    """
)
@limiter.limit("100/minute")
async def get_generation_system(
    request: Request,
    start_date: Optional[date] = Query(
        default=None,
        description="Fecha inicial en formato YYYY-MM-DD"
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Fecha final en formato YYYY-MM-DD"
    ),
    api_key: str = Depends(get_api_key)
) -> GenerationSystemResponse:
    """Obtiene generación total del sistema"""
    try:
        service = GenerationService()
        
        # Fechas por defecto: últimos 30 días
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date debe ser menor o igual a end_date"
            )
        
        df = service.get_daily_generation_system(start_date, end_date)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de generación para {start_date} - {end_date}"
            )
        
        # Convertir a formato API
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor_gwh'], 2),
                resource="Sistema",
                metadata={"unit": "GWh"}
            )
            for _, row in df.iterrows()
        ]
        
        return GenerationSystemResponse(
            metric="generation_system",
            description="Generación eléctrica total del sistema nacional",
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
            detail=f"Error obteniendo datos de generación: {str(e)}"
        )


@router.get(
    "/by-source",
    response_model=GenerationBySourceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Generación por fuente energética",
    description="""
    Obtiene la generación eléctrica desagregada por tipo de fuente.
    
    **Fuentes disponibles:**
    - HIDRAULICA: Centrales hidroeléctricas
    - TERMICA: Centrales térmicas (gas, carbón, etc.)
    - EOLICA: Parques eólicos
    - SOLAR: Plantas solares fotovoltaicas
    - COGENERADOR: Plantas de biomasa/cogeneración
    
    **Parámetros:**
    - `start_date`: Fecha inicial (opcional)
    - `end_date`: Fecha final (opcional)
    - `sources`: Lista de fuentes a incluir (opcional, por defecto: todas)
    """
)
@limiter.limit("100/minute")
async def get_generation_by_source(
    request: Request,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    sources: Optional[List[str]] = Query(
        default=None,
        description="Fuentes a incluir (HIDRAULICA, TERMICA, EOLICA, SOLAR, COGENERADOR)"
    ),
    api_key: str = Depends(get_api_key)
) -> GenerationBySourceResponse:
    """Obtiene generación por tipo de fuente"""
    try:
        service = GenerationService()
        
        # Fechas por defecto
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Fuentes por defecto
        if not sources:
            sources = ["HIDRAULICA", "TERMICA", "EOLICA", "SOLAR", "COGENERADOR"]
        
        # Obtener datos por cada fuente
        df = service.get_generation_by_source(start_date, end_date)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron datos de generación por fuente"
            )
        
        # Filtrar fuentes solicitadas
        df_filtered = df[df['tipo'].isin(sources)]
        
        # Convertir a formato API
        data = [
            MetricPoint(
                date=row['fecha'],
                value=round(row['valor_gwh'], 2),
                resource=row['tipo'],
                metadata={"unit": "GWh"}
            )
            for _, row in df_filtered.iterrows()
        ]
        
        return GenerationBySourceResponse(
            metric="generation_by_source",
            description="Generación eléctrica por tipo de fuente energética",
            unit="GWh",
            start_date=start_date,
            end_date=end_date,
            sources=sources,
            data=data,
            total_records=len(data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo generación por fuente: {str(e)}"
        )


@router.get(
    "/resources",
    response_model=GenerationResourcesResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Recursos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Listado de recursos generadores",
    description="""
    Obtiene el catálogo de recursos (plantas generadoras) del sistema.
    
    **Parámetros:**
    - `source_type`: Filtrar por tipo de fuente (opcional)
    - `only_active`: Solo recursos activos (opcional, por defecto: true)
    """
)
@limiter.limit("100/minute")
async def get_generation_resources(
    request: Request,
    source_type: Optional[str] = Query(
        default="TODAS",
        description="Tipo de fuente (HIDRAULICA, TERMICA, EOLICA, SOLAR, COGENERADOR, TODAS)"
    ),
    only_active: bool = Query(
        default=True,
        description="Solo incluir recursos activos"
    ),
    api_key: str = Depends(get_api_key)
) -> GenerationResourcesResponse:
    """Obtiene listado de recursos generadores"""
    try:
        service = GenerationService()
        
        df = service.get_resources_by_type(source_type)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron recursos para el tipo {source_type}"
            )
        
        resources = [
            {
                "name": row['recurso'],
                "type": row['tipo_clasificado'],
                "active": True  # TODO: Implementar lógica de activo/inactivo
            }
            for _, row in df.iterrows()
        ]
        
        return GenerationResourcesResponse(
            total_resources=len(resources),
            source_type=source_type,
            resources=resources
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo recursos: {str(e)}"
        )


@router.get(
    "/mix",
    response_model=GenerationMixResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Datos no encontrados"},
        500: {"model": ErrorResponse, "description": "Error interno"}
    },
    summary="Mix energético (participación por fuente)",
    description="""
    Obtiene el mix energético nacional, mostrando el porcentaje de participación
    de cada fuente en la generación total.
    
    **Parámetros:**
    - `target_date`: Fecha específica (opcional, por defecto: ayer)
    """
)
@limiter.limit("100/minute")
async def get_generation_mix(
    request: Request,
    target_date: Optional[date] = Query(
        default=None,
        description="Fecha específica para calcular el mix"
    ),
    api_key: str = Depends(get_api_key)
) -> GenerationMixResponse:
    """Obtiene mix energético por fecha"""
    try:
        service = GenerationService()
        
        # Fecha por defecto: ayer (datos más recientes completos)
        if not target_date:
            target_date = date.today() - timedelta(days=1)
        
        df = service.get_generation_mix(target_date)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos de mix energético para {target_date}"
            )
        
        mix = [
            {
                "source": row['tipo'],
                "generation_gwh": round(row['generacion_gwh'], 2),
                "percentage": round(row['porcentaje'], 2)
            }
            for _, row in df.iterrows()
        ]
        
        total_generation = sum(item['generation_gwh'] for item in mix)
        
        return GenerationMixResponse(
            date=target_date,
            total_generation_gwh=round(total_generation, 2),
            mix=mix
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo mix energético: {str(e)}"
        )
