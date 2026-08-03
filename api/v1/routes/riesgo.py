"""
Endpoints de riesgo de atraso (Fase 4 — analítica predictiva expandida, Palantir-IA)

Puramente analítico/informativo: ranking de contratos OR por riesgo de atraso, basado
en su cronograma de obra. No expone ninguna acción de escritura sobre contratos.
Ver domain/services/risk_service.py.
"""

import logging

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_risk_service
from domain.services.risk_service import RiskService

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/contratos-or",
    summary="Ranking de contratos OR por riesgo de atraso (cronograma de obra)",
)
@limiter.limit("30/minute")
async def riesgo_contratos_or(
    request: Request,
    api_key: str = Depends(get_api_key),
    service: RiskService = Depends(get_risk_service),
):
    ranking = service.riesgo_atraso_contratos_or()
    return {
        "ranking": ranking,
        "nota": (
            "Score informativo de riesgo de atraso basado en el cronograma de obra "
            "(contratos_or.cronograma_obra). No modifica el estado de ningún contrato."
        ),
    }
