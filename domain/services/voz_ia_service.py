"""
Asistente de voz en tiempo real — Fase 19 (Gemini Live API).

Puente bidireccional entre el WebSocket del cliente (api/v1/routes/voz.py) y
una sesión de Gemini Live API — el navegador nunca ve la API key de Gemini ni
llama directamente a Google; todo pasa por este servicio.

Reutiliza, no duplica, lo ya construido para el Asistente IA de texto
(domain/services/asistente_ia_service.py):
  - SYSTEM_PROMPT: misma identidad del asistente en voz que en texto.
  - TOOLS: mismo catálogo de ~20 herramientas — se transforma al formato
    nativo de Gemini (_tools_formato_gemini) en vez de mantener una lista
    paralela a mano.
  - _ejecutar_tool(): mismo despachador hacia orchestrator_service.orchestrate()
    — cada herramienta ya es un intent existente, cero lógica de negocio nueva.

Formato de audio de la Live API: entrada PCM 16-bit / 16kHz / mono; salida
PCM 16-bit / 24kHz / mono (sin envoltorio de archivo, bytes crudos).

Modelo: gemini-2.5-flash-native-audio-latest — se usa el alias "-latest" en
vez de una versión fechada, mismo criterio ya aplicado al Asistente de texto
(Fase 10: un modelo preview fijo se deprecó y rompió producción). Verificado
en vivo contra la API (2026-08-04) que esta alias existe y soporta
bidiGenerateContent — no asumido de memoria, la nomenclatura de Gemini cambia
seguido.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from core.config import settings
from domain.services.asistente_ia_service import SYSTEM_PROMPT, TOOLS, _ejecutar_tool
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

GEMINI_LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"
VOZ_NOMBRE = "Kore"  # una de las voces pre-hechas de Gemini; probar otras en aistudio.google.com/live-api

DURACION_MAXIMA_SESION_SEG = 15 * 60  # control de costo — cierre automático, ver Fase 19 en el plan

# ── Tokens efímeros de sesión ────────────────────────────────────────────
# El WebSocket del navegador no manda el header X-API-Key con la misma
# facilidad que fetch() — en vez de eso, POST /v1/voz/token (sí protegido con
# Depends(get_api_key), igual que el resto del backend) entrega un token de
# un solo uso y corta vigencia, que el WS valida antes de abrir la sesión
# Gemini (la parte que realmente cuesta dinero).
TOKEN_VIGENCIA_SEG = 60
_tokens_activos: Dict[str, float] = {}


def crear_sesion_token() -> str:
    token = secrets.token_urlsafe(32)
    _tokens_activos[token] = time.time() + TOKEN_VIGENCIA_SEG
    return token


def validar_y_consumir_token(token: Optional[str]) -> bool:
    """De un solo uso: se borra al validarlo, se use o no la sesión."""
    if not token:
        return False
    expiracion = _tokens_activos.pop(token, None)
    if expiracion is None:
        return False
    return time.time() < expiracion


def _tools_formato_gemini() -> list[types.Tool]:
    """Convierte TOOLS (formato OpenAI, function-calling del Asistente de
    texto) al formato nativo function_declarations de Gemini — transformación
    mecánica del catálogo existente, no una lista mantenida a mano aparte."""
    declaraciones = [
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"]["description"],
            parameters_json_schema=t["function"]["parameters"],
        )
        for t in TOOLS
    ]
    return [types.Tool(function_declarations=declaraciones)]


async def _reenviar_cliente_a_gemini(client_ws: WebSocket, session, inicio: float) -> None:
    """Recibe audio binario del cliente y lo reenvía a la sesión Gemini Live.
    Corta la sesión si se alcanza DURACION_MAXIMA_SESION_SEG (control de costo)."""
    while True:
        if time.monotonic() - inicio > DURACION_MAXIMA_SESION_SEG:
            logger.info("[VOZ] Sesión alcanzó el límite de duración, cerrando")
            await client_ws.close(code=4408)
            return
        try:
            data = await asyncio.wait_for(client_ws.receive_bytes(), timeout=5.0)
        except asyncio.TimeoutError:
            continue  # solo para poder re-chequear el límite de duración
        await session.send_realtime_input(
            audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
        )


async def _reenviar_gemini_a_cliente(client_ws: WebSocket, session) -> None:
    """Recibe eventos de Gemini Live: audio -> reenvía al cliente; tool_call ->
    despacha vía _ejecutar_tool() (mismo despachador del Asistente de texto)
    y responde con send_tool_response()."""
    async for evento in session.receive():
        contenido = evento.server_content
        if contenido and contenido.model_turn:
            for parte in contenido.model_turn.parts:
                if parte.inline_data and parte.inline_data.data:
                    await client_ws.send_bytes(parte.inline_data.data)

        if evento.tool_call:
            respuestas = []
            for fc in evento.tool_call.function_calls:
                try:
                    resultado = await _ejecutar_tool(fc.name, fc.args or {})
                except Exception as e:
                    logger.error(f"[VOZ] Tool '{fc.name}' falló: {e}")
                    resultado = {"error": f"La herramienta '{fc.name}' falló: {e}"}
                respuestas.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=resultado)
                )
            await session.send_tool_response(function_responses=respuestas)


async def ejecutar_sesion_voz(client_ws: WebSocket) -> None:
    """Abre una sesión de Gemini Live y hace de puente bidireccional con
    client_ws hasta que cualquiera de los dos lados se desconecte."""
    if not settings.GEMINI_API_KEY:
        logger.error("[VOZ] GEMINI_API_KEY no configurada")
        await client_ws.close(code=1011)
        return

    gclient = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT,
        tools=_tools_formato_gemini(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOZ_NOMBRE)
            )
        ),
    )

    inicio = time.monotonic()
    try:
        async with gclient.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as session:
            tarea_entrada = asyncio.create_task(_reenviar_cliente_a_gemini(client_ws, session, inicio))
            tarea_salida = asyncio.create_task(_reenviar_gemini_a_cliente(client_ws, session))
            try:
                terminadas, pendientes = await asyncio.wait(
                    [tarea_entrada, tarea_salida], return_when=asyncio.FIRST_COMPLETED
                )
                for t in pendientes:
                    t.cancel()
                for t in terminadas:
                    if t.exception():
                        raise t.exception()
            finally:
                for t in (tarea_entrada, tarea_salida):
                    if not t.done():
                        t.cancel()
    except WebSocketDisconnect:
        logger.info("[VOZ] Cliente desconectado")
    except Exception as e:
        logger.error(f"[VOZ] Error en sesión de voz: {e}")
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass
