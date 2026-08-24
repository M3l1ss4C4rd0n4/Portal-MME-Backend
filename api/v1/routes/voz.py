"""
Asistente de voz en tiempo real — Fase 19 (Gemini Live API).

Dos endpoints:
  - POST /v1/voz/token: protegido con Depends(get_api_key) como el resto del
    backend, entrega un token efímero de un solo uso.
  - WS   /v1/voz/ws: el navegador no puede mandar el header X-API-Key con la
    misma facilidad en un WebSocket, así que valida el token del punto
    anterior (query string) en vez de un header — el token es lo único que
    protege abrir una sesión de Gemini Live, que sí cuesta dinero real.

Esta ronda (backend únicamente, ver plan Fase 19): se prueba con un script
cliente WebSocket simple, no con la interfaz del portal todavía.
"""

import logging

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from domain.services.voz_ia_service import (
    crear_sesion_token,
    ejecutar_sesion_voz,
    validar_y_consumir_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/token",
    summary="Genera un token efímero de un solo uso para abrir una sesión de voz",
    tags=["🎙️ Asistente de voz"],
)
@limiter.limit("10/minute")
async def generar_token_voz(request: Request, api_key: str = Depends(get_api_key)):
    token = crear_sesion_token()
    logger.info(f"[VOZ] Token de sesión generado | IP: {request.client.host}")
    return {"token": token, "vigencia_seg": 60}


@router.websocket("/ws")
async def websocket_voz(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not validar_y_consumir_token(token):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Token inválido o expirado")

    await websocket.accept()
    logger.info("[VOZ] Sesión de voz iniciada")
    await ejecutar_sesion_voz(websocket)
    logger.info("[VOZ] Sesión de voz finalizada")
