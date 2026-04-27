"""
Tareas Celery para push notifications de la app EnergIA.

beat_schedule entry (registrado en tasks/__init__.py):
  'energia-app-informe-8am' → cada día a las 8:00 AM (hora Colombia)

Flujo:
  1. Busca en BD los dispositivos activos con FCM token
  2. Genera el informe ejecutivo diario vía orquestador
  3. Narra el texto con Groq LLM (español colombiano oral)
  4. Construye el mensaje FCM con la URL del audio (lazy: el cliente descarga)
  5. Envía push a todos los tokens activos (batches de 500)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import List, Dict, Any

from tasks import app as celery_app

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _get_active_fcm_tokens() -> List[Dict[str, str]]:
    """Devuelve lista de {usuario_id, fcm_token} activos desde BD."""
    from infrastructure.database.connection import get_connection
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT usuario_id, fcm_token FROM energia_app_dispositivos WHERE activo = TRUE"
        )
        rows = cur.fetchall()
    return [{"usuario_id": row[0], "fcm_token": row[1]} for row in rows]


async def _generar_texto_informe() -> str:
    """Obtiene el informe ejecutivo del orquestador y lo narra con LLM."""
    from core.container import container
    from domain.schemas.orchestrator import OrchestratorRequest
    import re

    service = container.get_orchestrator_service()
    req = OrchestratorRequest(
        sessionId="push-informe-diario",
        intent="informe_ejecutivo",
        parameters={}
    )
    result = await service.orchestrate(req)

    data = result.data or {}
    texto_raw = (
        data.get("informe") or
        data.get("resumen") or
        data.get("texto") or
        str(data)
    )

    # Narrar con Groq LLM → español oral natural
    try:
        from groq import AsyncGroq
        from core.config import settings
        client = AsyncGroq(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com")
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres el asistente de voz EnergIA del Ministerio de Minas y Energía. "
                        "Convierte el informe estructurado en una locución oral natural y fluida. "
                        "Español colombiano formal. Sin bullets, asteriscos ni markdown. "
                        "Texto corrido. Máximo 6 oraciones con todos los datos clave."
                    )
                },
                {"role": "user", "content": texto_raw[:4000]}
            ],
            temperature=0.4,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[PUSH-TASK] LLM narración falló, usando texto limpio: {e}")
        return re.sub(r'[*_`~\[\]#]', '', texto_raw).strip()


def _send_fcm_multicast(tokens: List[str], title: str, body: str, data: Dict[str, str]) -> Dict[str, int]:
    """
    Envía push FCM a una lista de tokens (máx 500 por llamada).
    Devuelve {'success': N, 'failure': M}.
    """
    import firebase_admin
    from firebase_admin import credentials, messaging

    # Inicializar Firebase Admin SDK una sola vez (singleton)
    if not firebase_admin._apps:
        from core.config import settings
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        if not cred_path:
            logger.error("[PUSH-TASK] FIREBASE_CREDENTIALS_PATH no configurado en .env")
            return {"success": 0, "failure": len(tokens)}
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    success_total = 0
    failure_total = 0

    # FCM acepta 500 tokens por MulticastMessage
    BATCH = 500
    for i in range(0, len(tokens), BATCH):
        batch_tokens = tokens[i:i + BATCH]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", content_available=True)
                )
            ),
            tokens=batch_tokens,
        )
        try:
            response = messaging.send_each_for_multicast(message)
            success_total += response.success_count
            failure_total += response.failure_count
            logger.info(
                f"[PUSH-TASK] Batch {i//BATCH + 1}: "
                f"{response.success_count} OK / {response.failure_count} FAIL"
            )
            # Desactivar tokens inválidos
            _deactivate_failed_tokens(batch_tokens, response.responses)
        except Exception as e:
            logger.error(f"[PUSH-TASK] Error enviando batch FCM: {e}", exc_info=True)
            failure_total += len(batch_tokens)

    return {"success": success_total, "failure": failure_total}


def _deactivate_failed_tokens(tokens: List[str], responses: list) -> None:
    """Marca como inactivos los tokens que recibieron error de registro."""
    invalid = []
    for token, resp in zip(tokens, responses):
        if not resp.success and resp.exception:
            err = str(resp.exception)
            if "registration-token-not-registered" in err or "invalid-registration-token" in err:
                invalid.append(token)

    if not invalid:
        return

    from infrastructure.database.connection import get_connection
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE energia_app_dispositivos SET activo = FALSE, updated_at = NOW() "
            "WHERE fcm_token = ANY(%s)",
            (invalid,)
        )
        conn.commit()
    logger.info(f"[PUSH-TASK] {len(invalid)} tokens inválidos desactivados")


# ═══════════════════════════════════════════════════════════
# TAREA PRINCIPAL
# ═══════════════════════════════════════════════════════════

@celery_app.task(
    name="tasks.push_tasks.enviar_informe_diario_push",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # reintenta en 5 min si falla
)
def enviar_informe_diario_push(self):
    """
    Tarea diaria 8:00 AM (hora Colombia):
    Genera el informe ejecutivo de energía y lo envía como push FCM
    a todos los dispositivos EnergIA registrados.
    """
    logger.info("[PUSH-TASK] ▶ Iniciando informe diario para app EnergIA…")

    try:
        # 1. Dispositivos activos
        dispositivos = _get_active_fcm_tokens()
        if not dispositivos:
            logger.info("[PUSH-TASK] Sin dispositivos registrados, abortando.")
            return {"status": "skip", "razon": "sin dispositivos"}

        tokens = [d["fcm_token"] for d in dispositivos]
        logger.info(f"[PUSH-TASK] {len(tokens)} dispositivo(s) activos")

        # 2. Generar texto narrado (corre en nuevo event loop en el worker sync)
        texto_narrado = asyncio.run(_generar_texto_informe())
        logger.info(f"[PUSH-TASK] Texto narrado generado ({len(texto_narrado)} chars)")

        # 3. Extraer resumen corto para el cuerpo de la notificación (max 120 chars)
        resumen_notif = texto_narrado[:117] + "…" if len(texto_narrado) > 120 else texto_narrado

        # 4. Construir URL del audio (el cliente descarga al abrir la notificación)
        from core.config import settings
        fecha_hoy = date.today().isoformat()
        audio_url = f"{settings.API_BASE_URL.rstrip('/')}/v1/energia-app/audio/informe-diario"
        api_key   = settings.API_KEY  # el cliente la embede en su build o la pide al splash

        # 5. Enviar FCM multicast
        resultado = _send_fcm_multicast(
            tokens=tokens,
            title=f"📊 Informe Energético — {fecha_hoy}",
            body=resumen_notif,
            data={
                "type": "informe_diario",
                "audio_url": audio_url,
                "fecha": fecha_hoy,
                "texto_narrado": texto_narrado[:1000],  # preview para offline
            },
        )

        logger.info(
            f"[PUSH-TASK] ✅ Completado: "
            f"{resultado['success']} enviados / {resultado['failure']} fallidos"
        )
        return {
            "status": "ok",
            "fecha": fecha_hoy,
            "dispositivos": len(tokens),
            **resultado,
        }

    except Exception as exc:
        logger.error(f"[PUSH-TASK] ❌ Error inesperado: {exc}", exc_info=True)
        raise self.retry(exc=exc)
