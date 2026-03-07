"""
Endpoints del Motor de Simulación CREG

Proporciona acceso a:
- Simulación paramétrica (POST /run)
- Escenarios predefinidos (GET /scenarios)
- Ejecución de escenario predefinido (GET /scenarios/{id}/run)
- Información baseline actual (GET /baseline)
- Historial de simulaciones guardadas (GET /history)

FASE 6 — Motor de Simulación CREG
"""

import json
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_simulation_service
from api.v1.schemas.simulation import (
    ParametrosSimulacion,
    SimulacionResponse,
    BaselineResponse,
    EscenarioResponse,
    HistorialItem,
)
from api.v1.schemas.common import ErrorResponse
from domain.services.simulation_service import SimulationService

logger = logging.getLogger("simulation_api")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ─── Redis Cache ─────────────────────────────────────────────────────────────
_redis_client = None
CACHE_TTL_BASELINE = 3600     # 1h
CACHE_TTL_SCENARIOS = 86400   # 24h
CACHE_TTL_HISTORY = 300       # 5m


def _get_redis():
    """Obtener cliente Redis con conexión lazy y fallback graceful."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.Redis(
            host='localhost', port=6379, db=0,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        logger.info("✅ Redis conectado para cache simulación")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Redis no disponible — simulation sin cache: {e}")
        _redis_client = None
        return None


def _cache_get(key: str) -> Optional[dict]:
    r = _get_redis()
    if r is None:
        return None
    try:
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Sim cache get error: %s", e)
    return None


def _cache_set(key: str, data: dict, ttl: int = 3600):
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.debug("Sim cache set error: %s", e)


# ─── POST /run — Simulación personalizada ────────────────────────────────────

@router.post(
    "/run",
    summary="Ejecutar simulación CREG",
    description=(
        "Simula un escenario regulatorio modificando parámetros CREG. "
        "Retorna el CU simulado, impacto en estrato 3, sensibilidad y serie temporal."
    ),
    response_model=SimulacionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)
@limiter.limit("20/minute")
async def run_simulation(
    request: Request,
    body: ParametrosSimulacion,
    api_key: str = Depends(get_api_key),
    svc: SimulationService = Depends(get_simulation_service),
):
    """Ejecuta una simulación paramétrica CREG."""
    try:
        # Construir dict de parámetros (solo los modificados respecto a defaults)
        params = {}
        if body.precio_bolsa_factor != 1.0:
            params['precio_bolsa_factor'] = body.precio_bolsa_factor
        if body.factor_perdidas != 0.085:
            params['factor_perdidas'] = body.factor_perdidas
        if body.cargo_restricciones_kw is not None:
            params['cargo_restricciones_kw'] = body.cargo_restricciones_kw
        if body.tasa_transmision != 1.0:
            params['tasa_transmision'] = body.tasa_transmision
        if body.tasa_comercializacion != 1.0:
            params['tasa_comercializacion'] = body.tasa_comercializacion
        if body.demanda_factor != 1.0:
            params['demanda_factor'] = body.demanda_factor

        # Si no se modificó ningún parámetro, incluir precio_bolsa_factor=1.0
        # para que el simulador retorne el baseline
        if not params:
            params['precio_bolsa_factor'] = 1.0

        resultado = svc.simular_escenario(
            parametros=params,
            nombre=body.nombre,
            tipo=body.tipo,
        )

        # Guardar si se solicitó
        if body.guardar:
            svc.guardar_simulacion(
                nombre=body.nombre,
                parametros=params,
                resultado=resultado,
                tipo=body.tipo,
            )

        return resultado

    except Exception as e:
        logger.error(f"Error en simulación: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── GET /scenarios — Lista escenarios predefinidos ──────────────────────────

@router.get(
    "/scenarios",
    summary="Escenarios predefinidos",
    description="Retorna la lista de escenarios CREG predefinidos con contexto histórico.",
    response_model=List[EscenarioResponse],
)
async def get_scenarios(
    api_key: str = Depends(get_api_key),
    svc: SimulationService = Depends(get_simulation_service),
):
    """Lista todos los escenarios predefinidos."""
    cache_key = "sim:scenarios:all"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = svc.get_escenarios_predefinidos()
    _cache_set(cache_key, data, CACHE_TTL_SCENARIOS)
    return data


# ─── GET /scenarios/{scenario_id}/run — Ejecutar escenario predefinido ───────

@router.get(
    "/scenarios/{scenario_id}/run",
    summary="Ejecutar escenario predefinido",
    description="Ejecuta un escenario CREG predefinido por su ID.",
    response_model=SimulacionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Escenario no encontrado"},
    },
)
@limiter.limit("30/minute")
async def run_scenario(
    request: Request,
    scenario_id: str,
    api_key: str = Depends(get_api_key),
    svc: SimulationService = Depends(get_simulation_service),
):
    """Ejecuta un escenario predefinido por ID."""
    escenarios = svc.get_escenarios_predefinidos()
    escenario = next(
        (e for e in escenarios if e['id'] == scenario_id), None
    )
    if not escenario:
        raise HTTPException(
            status_code=404,
            detail=f"Escenario '{scenario_id}' no encontrado. "
                   f"IDs válidos: {[e['id'] for e in escenarios]}",
        )

    resultado = svc.simular_escenario(
        parametros=escenario['parametros'],
        nombre=escenario['nombre'],
        tipo=escenario['tipo'],
    )
    return resultado


# ─── GET /baseline — Información baseline actual ─────────────────────────────

@router.get(
    "/baseline",
    summary="Baseline actual",
    description="Retorna los parámetros base actuales del sistema energético.",
    response_model=BaselineResponse,
)
async def get_baseline(
    api_key: str = Depends(get_api_key),
    svc: SimulationService = Depends(get_simulation_service),
):
    """Retorna información del baseline actual."""
    cache_key = "sim:baseline:current"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = svc.get_baseline_info()
    _cache_set(cache_key, data, CACHE_TTL_BASELINE)
    return data


# ─── GET /history — Historial de simulaciones guardadas ──────────────────────

@router.get(
    "/history",
    summary="Historial de simulaciones",
    description="Retorna las últimas N simulaciones guardadas.",
    response_model=List[HistorialItem],
)
async def get_history(
    limite: int = Query(20, ge=1, le=100, description="Número máximo de resultados"),
    api_key: str = Depends(get_api_key),
    svc: SimulationService = Depends(get_simulation_service),
):
    """Lista historial de simulaciones guardadas."""
    cache_key = f"sim:history:{limite}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = svc.get_historial(limite=limite)
    _cache_set(cache_key, data, CACHE_TTL_HISTORY)
    return data
