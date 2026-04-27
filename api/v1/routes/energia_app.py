"""
Endpoints para la app móvil EnergIA

Fase 0 del plan de desarrollo:
  - GET  /audio/informe-diario   → MP3 con resumen ejecutivo narrado por IA
  - POST /audio/consulta         → MP3 de respuesta a una consulta libre
  - POST /push/registrar         → Registra FCM token de un dispositivo
  - DELETE /push/registrar       → Elimina FCM token (logout)

Seguridad: requiere X-API-Key en todos los endpoints.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field

from api.dependencies import get_api_key, get_orchestrator_service
from core.config import settings
from domain.schemas.orchestrator import OrchestratorRequest
from domain.services.orchestrator_service import ChatbotOrchestratorService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════

class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000, description="Texto de la consulta del usuario")
    session_id: str = Field(default="app-energia", description="Identificador de sesión")


class PushRegistroRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, description="Token FCM del dispositivo")
    usuario_id: str = Field(..., description="Identificador único del usuario")
    dispositivo: Optional[str] = Field(default=None, description="Nombre o modelo del dispositivo")


class PushRegistroResponse(BaseModel):
    success: bool
    message: str


# ═══════════════════════════════════════════════════════════
# HELPERS TTS  (gTTS)
# ═══════════════════════════════════════════════════════════


def _sintetizar_audio_sync(texto: str) -> bytes:
    """Sintetiza texto a MP3 usando una sola llamada a gTTS."""
    try:
        from gtts import gTTS
        import io as _io

        # Evita cortar y recombinar múltiples MP3, que introduce pausas audibles.
        tts = gTTS(text=texto, lang="es", tld="com.co", slow=False)
        buf = _io.BytesIO()
        tts.write_to_fp(buf)
        audio = buf.getvalue()
        logger.info(f"[ENERGIA-APP-TTS] gTTS OK (single-pass, {len(audio)} bytes)")
        return audio
    except Exception as gtts_err:
        logger.error(f"[ENERGIA-APP-TTS] gTTS falló: {gtts_err}")
        raise


async def _sintetizar_audio(texto: str) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sintetizar_audio_sync, texto)


def _extraer_indicadores(data: dict) -> dict:
    """Extrae los tres indicadores clave y las noticias del sector."""
    ctx = data.get("contexto_datos") or {}
    fichas = ctx.get("estado_actual", {}).get("fichas", [])
    resultado: dict = {}
    for ficha in fichas:
        ind = (ficha.get("indicador") or "").lower()
        c = ficha.get("contexto", {})
        if "generación total" in ind:
            resultado["generacion"] = {
                "valor": ficha.get("valor"),
                "unidad": ficha.get("unidad", "GWh"),
                "variacion_pct": c.get("variacion_vs_promedio_pct"),
                "tendencia": c.get("tendencia", ""),
            }
        elif "precio" in ind:
            resultado["precio"] = {
                "valor": ficha.get("valor"),
                "unidad": ficha.get("unidad", "COP/kWh"),
                "variacion_pct": c.get("variacion_vs_promedio_pct"),
                "tendencia": c.get("tendencia", ""),
            }
        elif "embalse" in ind:
            resultado["embalses"] = {
                "valor": ficha.get("valor"),
                "unidad": ficha.get("unidad", "%"),
                "estado": c.get("estado", ""),
                "variacion_vs_historico": c.get("variacion_vs_historico_pct"),
            }

    # Noticias del sector (top 3 por _score)
    prensa = ctx.get("prensa_del_dia", {})
    noticias_raw = prensa.get("noticias", [])
    # Tomar los titulares del día si no hay noticias con estructura completa
    titulares = prensa.get("titulares_del_dia", [])
    noticias_top3 = []
    for n in sorted(noticias_raw, key=lambda x: x.get("_score", 0), reverse=True)[:3]:
        titulo = n.get("titulo", "")
        resumen = n.get("resumen_corto", "").replace("&nbsp;", " ").strip()
        # Evitar que resumen === titulo (cuando RSS repite el título)
        if resumen and resumen.lower() != titulo.lower() and len(resumen) > len(titulo) + 5:
            noticias_top3.append(f"{titulo}: {resumen}")
        else:
            noticias_top3.append(titulo)
    # Fallback a titulares si no hay noticias estructuradas
    if not noticias_top3 and titulares:
        noticias_top3 = titulares[:3]

    resultado["noticias"] = noticias_top3
    resultado["resumen_prensa"] = prensa.get("resumen_prensa", "")
    return resultado


async def _boletin_del_dia(data: dict) -> str:
    """
    Boletín de voz de ~55 segundos:
    - P1: saludo + fecha (Python directo)
    - P2: indicadores con valores exactos + estado del sistema (Python directo)
    - P3: 3 noticias del sector (determinista, sin LLM)
    - Cierre (Python directo)
    """
    import re as _re
    fecha_raw = data.get("fecha_generacion", "")
    fecha = fecha_raw.split(" ")[0] if fecha_raw else "hoy"
    ind = _extraer_indicadores(data)
    texto_informe = data.get("informe", "")

    # ── P1: saludo ──────────────────────────────────────────
    try:
        from datetime import datetime
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        meses = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        fecha_legible = f"{dt.day} de {meses[dt.month - 1]} de {dt.year}"
    except Exception:
        fecha_legible = fecha
    p1 = f"Buenos días. Hoy es {fecha_legible}. Le presentamos el boletín energético matutino del Ministerio de Minas y Energía de Colombia."

    # ── P2: indicadores (construido en Python, sin LLM) ─────
    frases_ind = []
    if "generacion" in ind:
        g = ind["generacion"]
        var = g["variacion_pct"]
        signo = "más" if (var or 0) >= 0 else "menos"
        pct = abs(var or 0)
        frases_ind.append(
            f"La generación total del sistema se ubicó en {g['valor']} gigavatios hora, "
            f"un {pct}% {signo} que el promedio de los últimos siete días."
        )
    if "embalses" in ind:
        e = ind["embalses"]
        estado_limpio = _re.sub(r'[^\w\s%áéíóúÁÉÍÓÚñÑ]', '', e["estado"]).strip()
        frases_ind.append(
            f"Los embalses registran el {e['valor']}% de su capacidad, con nivel {estado_limpio}."
        )
    if "precio" in ind:
        p = ind["precio"]
        var = p["variacion_pct"]
        signo = "por encima" if (var or 0) >= 0 else "por debajo"
        pct = abs(var or 0)
        frases_ind.append(
            f"El precio de bolsa nacional se situó en {p['valor']} pesos por kilovatio hora, "
            f"un {pct}% {signo} del promedio semanal."
        )
    # Calificación del sistema
    cal_match = _re.search(r'\*\*(EN\s+\w+(?:\s+\w+)?)\*\*', texto_informe)
    calificacion = cal_match.group(1) if cal_match else "EN VIGILANCIA"
    frases_ind.append(
        f"El sistema eléctrico nacional se encuentra {calificacion.lower()}, "
        "lo que exige seguimiento permanente para garantizar el suministro."
    )
    p2 = " ".join(frases_ind)

    # ── P3: noticias (determinista para evitar truncados del LLM) ──────────
    noticias = ind.get("noticias", [])
    if noticias:
        titulares = []
        for n in noticias[:3]:
            # Si viene "titulo: resumen", usar solo el título para una locución más estable.
            titulo = n.split(":", 1)[0] if ":" in n else n
            titulo = _re.sub(r"\s+", " ", titulo).strip(" .,;:-")
            if titulo:
                titulares.append(titulo)

        if len(titulares) >= 3:
            p3 = (
                f"En noticias del sector, {titulares[0]}. "
                f"Además, {titulares[1]}. "
                f"Finalmente, {titulares[2]}."
            )
        elif titulares:
            p3 = "En noticias del sector: " + ". ".join(titulares) + "."
        else:
            p3 = "Mantente al tanto de las novedades del sector a través del portal energético del Ministerio."
    else:
        p3 = "Mantente al tanto de las novedades del sector a través del portal energético del Ministerio."

    # ── Cierre ───────────────────────────────────────────────
    cierre = "Este ha sido el boletín de EnergIA. Hasta mañana."

    return "\n\n".join([p1, p2, p3, cierre])


async def _narrar_para_audio(texto: str) -> str:
    """Convierte texto libre en locución oral natural (usado para /audio/consulta)."""
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com")
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres el asistente de voz EnergIA del Ministerio de Minas y Energía de Colombia. "
                        "Convierte la respuesta que recibes en una locución oral natural y fluida. "
                        "Español colombiano formal. Sin bullets, asteriscos ni markdown. Solo texto corrido. "
                        "Máximo 500 caracteres."
                    )
                },
                {"role": "user", "content": texto[:4000]}
            ],
            temperature=0.4,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[ENERGIA-APP-NARRACION] Falló LLM, usando texto limpio: {e}")
        import re
        return re.sub(r'[*_`~\[\]#]', '', texto).strip()


# ═══════════════════════════════════════════════════════════
# ENDPOINT 1: Informe diario en audio
# ═══════════════════════════════════════════════════════════

@router.get(
    "/audio/informe-diario",
    response_class=Response,
    responses={
        200: {
            "content": {"audio/mpeg": {}},
            "description": "MP3 con el resumen ejecutivo narrado por IA"
        }
    },
    summary="Informe diario en audio",
    description="Genera y devuelve el informe ejecutivo del día como archivo MP3, narrado con voz IA natural."
)
async def get_informe_diario_audio(
    _api_key: str = Depends(get_api_key),
    service: ChatbotOrchestratorService = Depends(get_orchestrator_service),
):
    """
    Genera el informe ejecutivo del día y lo devuelve como MP3.
    Usado por la app EnergIA para reproducir el informe automáticamente a las 8am.
    """
    try:
        logger.info("[ENERGIA-APP] Generando informe diario en audio…")

        # 1. Obtener informe del orquestador
        req = OrchestratorRequest(sessionId="app-informe-diario", intent="informe_ejecutivo", parameters={})
        result = await service.orchestrate(req)

        if result.status == "ERROR":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo generar el informe. Intenta más tarde."
            )

        # 2. Extraer datos estructurados del resultado
        data = result.data or {}

        # 3. Generar boletín de voz (3 indicadores + interpretación + 3 hechos clave)
        texto_narrado = await _boletin_del_dia(data)
        logger.info(f"[ENERGIA-APP] Boletín generado ({len(texto_narrado)} chars): {texto_narrado[:120]}…")

        # 4. Sintetizar a MP3
        audio_bytes = await _sintetizar_audio(texto_narrado)

        logger.info(f"[ENERGIA-APP] Informe audio generado ({len(audio_bytes)} bytes)")
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=informe-diario.mp3"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENERGIA-APP] Error generando informe audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno generando el audio.")


# ═══════════════════════════════════════════════════════════
# ENDPOINT 2: Consulta libre en audio
# ═══════════════════════════════════════════════════════════

@router.post(
    "/audio/consulta",
    response_class=Response,
    responses={
        200: {
            "content": {"audio/mpeg": {}},
            "description": "MP3 con la respuesta a la consulta"
        }
    },
    summary="Consulta libre en audio",
    description="Recibe texto de una pregunta y devuelve la respuesta como MP3 narrado."
)
async def post_consulta_audio(
    request: ConsultaRequest,
    _api_key: str = Depends(get_api_key),
    service: ChatbotOrchestratorService = Depends(get_orchestrator_service),
):
    """
    Recibe texto transcrito desde la app (Whisper en cliente o servidor)
    y devuelve la respuesta del orquestador como MP3.
    """
    try:
        logger.info(f"[ENERGIA-APP] Consulta audio: '{request.texto[:80]}'")

        # 1. Llamar al orquestador con pregunta libre
        req = OrchestratorRequest(sessionId=request.session_id, intent="pregunta_libre", parameters={"pregunta": request.texto})
        result = await service.orchestrate(req)

        # 2. Extraer texto de respuesta
        data = result.data or {}
        texto_respuesta = (
            data.get("respuesta") or
            data.get("texto") or
            data.get("answer") or
            "No pude obtener una respuesta en este momento."
        )

        if result.status == "ERROR":
            texto_respuesta = "Lo siento, hubo un problema al procesar tu consulta. Por favor intenta de nuevo."

        # 3. Narrar y sintetizar
        texto_narrado = await _narrar_para_audio(texto_respuesta)
        audio_bytes = await _sintetizar_audio(texto_narrado)

        logger.info(f"[ENERGIA-APP] Consulta audio respondida ({len(audio_bytes)} bytes)")
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=respuesta.mp3"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENERGIA-APP] Error en consulta audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno generando la respuesta.")


# ═══════════════════════════════════════════════════════════
# ENDPOINT 3: Registrar token FCM (notificaciones push)
# ═══════════════════════════════════════════════════════════

@router.post(
    "/push/registrar",
    response_model=PushRegistroResponse,
    summary="Registrar dispositivo para notificaciones push",
    description="Guarda el token FCM del dispositivo para recibir el informe diario automático."
)
async def registrar_push(
    request: PushRegistroRequest,
    _api_key: str = Depends(get_api_key),
):
    """
    Registra el FCM token de un dispositivo en la base de datos.
    La app llama a este endpoint al iniciar sesión.
    """
    try:
        from infrastructure.database.connection import get_connection
        import asyncio
        loop = asyncio.get_event_loop()

        def _insert():
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO energia_app_dispositivos (usuario_id, fcm_token, dispositivo, activo, updated_at)
                    VALUES (%s, %s, %s, TRUE, NOW())
                    ON CONFLICT (usuario_id)
                    DO UPDATE SET fcm_token = %s, dispositivo = %s, activo = TRUE, updated_at = NOW()
                    """,
                    (request.usuario_id, request.fcm_token,
                     request.dispositivo or "desconocido",
                     request.fcm_token, request.dispositivo or "desconocido"),
                )
                conn.commit()

        await loop.run_in_executor(None, _insert)
        logger.info(f"[ENERGIA-APP-PUSH] Token registrado para usuario {request.usuario_id}")
        return PushRegistroResponse(success=True, message="Dispositivo registrado correctamente.")

    except Exception as e:
        logger.error(f"[ENERGIA-APP-PUSH] Error registrando token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error registrando el dispositivo.")


@router.delete(
    "/push/registrar",
    response_model=PushRegistroResponse,
    summary="Eliminar registro de dispositivo",
    description="Desactiva las notificaciones push para el usuario (logout o desinstalación)."
)
async def eliminar_push(
    usuario_id: str,
    _api_key: str = Depends(get_api_key),
):
    try:
        from infrastructure.database.connection import get_connection
        import asyncio
        loop = asyncio.get_event_loop()

        def _update():
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE energia_app_dispositivos SET activo = FALSE, updated_at = NOW() WHERE usuario_id = %s",
                    (usuario_id,),
                )
                conn.commit()

        await loop.run_in_executor(None, _update)
        logger.info(f"[ENERGIA-APP-PUSH] Token desactivado para usuario {usuario_id}")
        return PushRegistroResponse(success=True, message="Dispositivo desregistrado.")
    except Exception as e:
        logger.error(f"[ENERGIA-APP-PUSH] Error eliminando token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error eliminando el registro.")


# ═══════════════════════════════════════════════════════════
# ENDPOINT TEMPORAL - DESCARGA REPO MAVEN LOCAL
# Eliminar después de instalar la app
# ═══════════════════════════════════════════════════════════

import re as _re

_MAVEN_ZIP = "/home/admonctrlxm/server/data/local-maven-temp.zip"
_MAVEN_PARTS_DIR = "/home/admonctrlxm/server/data"

@router.get("/dev/maven-local", include_in_schema=False)
async def download_maven_local(api_key: str = Depends(get_api_key)):
    """Endpoint temporal para descargar el repo Maven local (uso interno dev)."""
    if not os.path.exists(_MAVEN_ZIP):
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(
        path=_MAVEN_ZIP,
        media_type="application/zip",
        filename="local-maven.zip",
    )

@router.get("/dev/maven-part/{part}", include_in_schema=False)
async def download_maven_part(part: str, api_key: str = Depends(get_api_key)):
    """Endpoint temporal - descarga una parte del repo Maven (chunks de 25MB)."""
    if not _re.match(r'^[a-z]{2}$', part):
        raise HTTPException(status_code=404)
    path = f"{_MAVEN_PARTS_DIR}/local-maven-part-{part}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Parte '{part}' no disponible")
    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=f"local-maven-part-{part}",
    )

@router.get("/dev/gradle-86", include_in_schema=False)
async def download_gradle_86(api_key: str = Depends(get_api_key)):
    """Endpoint temporal - Gradle 8.6 bin zip para build EnergIA."""
    path = "/home/admonctrlxm/server/data/gradle-8.6-bin.zip"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo aún no disponible, reintenta en un momento")
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename="gradle-8.6-bin.zip",
    )

@router.get("/dev/kgp-patch", include_in_schema=False)
async def download_kgp_patch(api_key: str = Depends(get_api_key)):
    """Endpoint temporal - parche KGP variant JARs (gradle85 + .module) para fix getIsolatedProjects()."""
    path = "/home/admonctrlxm/server/data/kgp-patch.zip"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename="kgp-patch.zip",
    )

@router.get("/dev/deps-patch", include_in_schema=False)
async def download_deps_patch(api_key: str = Depends(get_api_key)):
    """Endpoint temporal - deps Maven (gson, guava, kotlin-stdlib, etc.) para included build."""
    path = "/home/admonctrlxm/server/data/deps-only.zip"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename="deps-only.zip",
    )

@router.get("/dev/ppn-energia", include_in_schema=False)
async def download_ppn_energia(api_key: str = Depends(get_api_key)):
    """Endpoint temporal - modelo Porcupine wake word 'energía' para Android."""
    path = "/home/admonctrlxm/server/energia_app/android/app/src/main/assets/energia_es_android.ppn"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename="energia_es_android.ppn",
    )
