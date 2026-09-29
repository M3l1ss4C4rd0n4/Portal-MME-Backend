"""
Endpoints — Balance Oferta-Demanda del SIN (Fase 45).

Sirve el tablero que evalúa con datos la hipótesis de que la crisis de
suministro fue causada por retrasos de proyectos UPME. Ver
domain/services/balance_oferta_demanda_service.py para la metodología y
las notas de gobernanza de datos (esto NO reemplaza ni se mezcla con los
índices oficiales CREG de core/umbrales_oficiales.py / api/v1/routes/
sector_snapshot.py).
"""

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_balance_oferta_demanda_service
from domain.services.balance_oferta_demanda_service import BalanceOfertaDemandaService
from infrastructure.database.repositories.balance_oferta_demanda_repository import (
    FECHA_INICIO_DISPO_CONFIABLE,
)
from infrastructure.database.repositories.upme_proyectos_repository import (
    ESTADOS_VALIDOS as _ESTADOS_VALIDOS,
    TIPOS_VALIDOS as _TIPOS_VALIDOS,
)

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_RANGO_MAX_DIAS = 10_000  # ~27 años — cobertura real desde 2000-01-01 tras el backfill del 2026-09-23


def _validar_rango(fecha_inicio: Optional[date], fecha_fin: Optional[date]) -> tuple[date, date]:
    fin = fecha_fin or date.today()
    inicio = fecha_inicio or FECHA_INICIO_DISPO_CONFIABLE
    if inicio > fin:
        raise HTTPException(status_code=400, detail="fecha_inicio no puede ser posterior a fecha_fin")
    if (fin - inicio).days > _RANGO_MAX_DIAS:
        raise HTTPException(status_code=400, detail=f"Rango máximo permitido: {_RANGO_MAX_DIAS} días")
    return inicio, fin


@router.get("/historico", summary="Serie histórica nacional de oferta, demanda y margen de reserva")
@limiter.limit("60/minute")
async def get_historico(
    request: Request,
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    api_key: str = Depends(get_api_key),
    service: BalanceOfertaDemandaService = Depends(get_balance_oferta_demanda_service),
):
    inicio, fin = _validar_rango(fecha_inicio, fecha_fin)
    try:
        return service.get_balance_historico(inicio, fin)
    except Exception as e:
        logger.error("[balance-oferta-demanda/historico] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al calcular el balance oferta-demanda")


@router.get("/demanda-no-atendida-regional", summary="Demanda no atendida diaria por área operativa")
@limiter.limit("60/minute")
async def get_demanda_no_atendida_regional(
    request: Request,
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    api_key: str = Depends(get_api_key),
    service: BalanceOfertaDemandaService = Depends(get_balance_oferta_demanda_service),
):
    inicio, fin = _validar_rango(fecha_inicio, fecha_fin)
    try:
        return service.get_demanda_no_atendida_regional(inicio, fin)
    except Exception as e:
        logger.error("[balance-oferta-demanda/demanda-no-atendida-regional] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al obtener demanda no atendida regional")


@router.get("/proyectos-upme", summary="Proyectos de expansión UPME con retraso calculado")
@limiter.limit("60/minute")
async def get_proyectos_upme(
    request: Request,
    tipo: Optional[str] = Query(None),
    tecnologia: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    api_key: str = Depends(get_api_key),
    service: BalanceOfertaDemandaService = Depends(get_balance_oferta_demanda_service),
):
    if tipo is not None and tipo not in _TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"tipo debe ser uno de {sorted(_TIPOS_VALIDOS)}")
    if estado is not None and estado not in _ESTADOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"estado debe ser uno de {sorted(_ESTADOS_VALIDOS)}")
    try:
        proyectos = service.get_proyectos_upme(tipo=tipo, tecnologia=tecnologia, estado=estado)
        return {
            "proyectos": proyectos,
            "nota": (
                "Datos curados manualmente del Plan de Expansión de la UPME y "
                "seguimiento público — no provienen de una API oficial de XM. Cada "
                "proyecto lleva su fuente documental (campo 'fuente')."
            ),
        }
    except Exception as e:
        logger.error("[balance-oferta-demanda/proyectos-upme] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al obtener proyectos UPME")


@router.get("/correlacion-retraso", summary="Correlación mensual entre MW retrasados y margen de reserva")
@limiter.limit("30/minute")
async def get_correlacion_retraso(
    request: Request,
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    api_key: str = Depends(get_api_key),
    service: BalanceOfertaDemandaService = Depends(get_balance_oferta_demanda_service),
):
    inicio, fin = _validar_rango(fecha_inicio, fecha_fin)
    try:
        return service.get_correlacion_retraso_deficit(inicio, fin)
    except Exception as e:
        logger.error("[balance-oferta-demanda/correlacion-retraso] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al calcular la correlación retraso-déficit")


class SimularContrafactualRequest(BaseModel):
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    proyecto_ids: Optional[List[int]] = Field(
        default=None,
        max_length=200,  # no hay más de unas decenas de proyectos UPME reales — evita DoS de CPU con listas gigantes
        description="IDs de proyectos a asumir 'a tiempo'. Si se omite, incluye todos los que tienen fecha y capacidad.",
    )


@router.post("/simular-contrafactual", summary="Simulación contrafactual: proyectos UPME 'a tiempo'")
@limiter.limit("30/minute")
async def post_simular_contrafactual(
    request: Request,
    body: SimularContrafactualRequest,
    api_key: str = Depends(get_api_key),
    service: BalanceOfertaDemandaService = Depends(get_balance_oferta_demanda_service),
):
    inicio, fin = _validar_rango(body.fecha_inicio, body.fecha_fin)
    try:
        return service.simular_contrafactual(inicio, fin, proyecto_ids=body.proyecto_ids)
    except Exception as e:
        logger.error("[balance-oferta-demanda/simular-contrafactual] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al simular el escenario contrafactual")
