"""
Endpoints de pérdidas de energía

Proporciona acceso a datos de:
- Pérdidas técnicas
- Pérdidas no técnicas
- Pérdidas por operador
- Pérdidas detalladas (FASE 3)
- Resumen PNT (FASE 3)

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
Actualización FASE 3: 3 de marzo de 2026
"""

from typing import Optional
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_losses_nt_service
from api.v1.schemas.common import ErrorResponse, MetricPoint
from api.v1.schemas.losses import (
    LossesResponse,
    LossesDetailedResponse,
    LossesDetailedRecord,
    LossesNTSummaryResponse,
)
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


# ================================================================
# FASE 3: Endpoints Pérdidas No Técnicas
# ================================================================

@router.get(
    "/detailed",
    response_model=LossesDetailedResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Sin datos para el rango"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
    summary="Pérdidas detalladas (técnicas y no técnicas)",
    description="""
    Retorna la serie diaria de pérdidas con desglose completo:
    - Pérdidas totales, técnicas y **no técnicas** (GWh y %)
    - Costos estimados en Millones COP
    - Indicador de confianza y anomalía
    
    **Método:** RESIDUO_BASICO (Gene - DemaCome)
    
    **Parámetros:**
    - `start_date`: Fecha inicial (default: 30 días atrás)
    - `end_date`: Fecha final (default: hoy)
    """,
)
@limiter.limit("100/minute")
async def get_losses_detailed(
    request: Request,
    start_date: Optional[date] = Query(default=None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(default=None, description="Fecha fin (YYYY-MM-DD)"),
    api_key: str = Depends(get_api_key),
) -> LossesDetailedResponse:
    """Obtiene serie diaria de pérdidas detalladas desde losses_detailed."""
    try:
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        service = LossesService()
        df = service.get_losses_detailed(start_date, end_date)

        if df.empty:
            return LossesDetailedResponse(
                status="ok",
                start_date=start_date,
                end_date=end_date,
                total_records=0,
                data=[],
            )

        records = []
        for _, row in df.iterrows():
            records.append(LossesDetailedRecord(
                fecha=row.get("fecha"),
                perdidas_total_pct=row.get("perdidas_total_pct"),
                perdidas_tecnicas_pct=row.get("perdidas_tecnicas_pct"),
                perdidas_nt_pct=row.get("perdidas_nt_pct"),
                perdidas_stn_pct=row.get("perdidas_stn_pct"),
                generacion_gwh=row.get("generacion_gwh"),
                demanda_gwh=row.get("demanda_gwh"),
                perdidas_total_gwh=row.get("perdidas_total_gwh"),
                perdidas_tecnicas_gwh=row.get("perdidas_tecnicas_gwh"),
                perdidas_nt_gwh=row.get("perdidas_nt_gwh"),
                costo_nt_mcop=row.get("costo_nt_mcop"),
                precio_bolsa_cop_kwh=row.get("precio_bolsa_cop_kwh"),
                confianza=row.get("confianza"),
                anomalia_detectada=row.get("anomalia_detectada"),
                fuentes_ok=row.get("fuentes_ok"),
            ))

        return LossesDetailedResponse(
            status="ok",
            start_date=start_date,
            end_date=end_date,
            total_records=len(records),
            data=records,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo pérdidas detalladas: {str(e)}",
        )


@router.get(
    "/nt-summary",
    response_model=LossesNTSummaryResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Sin datos agregados"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
    summary="Resumen estadístico de pérdidas no técnicas",
    description="""
    Estadísticas agregadas de pérdidas no técnicas del SIN:
    
    - **Promedios**: total, técnicas, NT (histórico, 30d, 12m)
    - **Tendencia**: MEJORANDO / ESTABLE / EMPEORANDO 
      (compara promedio NT últimos 6 meses vs 6 meses previos)
    - **Anomalías**: días con P_NT < 0% o P_NT > 25%
    - **Costos**: estimación en Millones COP del impacto económico de PNT
    """,
)
@limiter.limit("100/minute")
async def get_losses_nt_summary(
    request: Request,
    api_key: str = Depends(get_api_key),
) -> LossesNTSummaryResponse:
    """Obtiene resumen estadístico de pérdidas no técnicas."""
    try:
        service = LossesService()
        stats = service.get_losses_nt_summary()

        if "error" in stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=stats["error"],
            )

        return LossesNTSummaryResponse(
            status="ok",
            total_dias=stats.get("total_dias"),
            pct_promedio_total=stats.get("pct_promedio_total"),
            pct_promedio_tecnicas=stats.get("pct_promedio_tecnicas"),
            pct_promedio_nt=stats.get("pct_promedio_nt"),
            pct_promedio_nt_30d=stats.get("pct_promedio_nt_30d"),
            pct_promedio_nt_12m=stats.get("pct_promedio_nt_12m"),
            pct_promedio_total_30d=stats.get("pct_promedio_total_30d"),
            anomalias_30d=stats.get("anomalias_30d"),
            tendencia_nt=stats.get("tendencia_nt"),
            dias_anomalia=stats.get("dias_anomalia"),
            costo_nt_historico_mcop=stats.get("costo_nt_historico_mcop"),
            costo_nt_12m_mcop=stats.get("costo_nt_12m_mcop"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo resumen PNT: {str(e)}",
        )
