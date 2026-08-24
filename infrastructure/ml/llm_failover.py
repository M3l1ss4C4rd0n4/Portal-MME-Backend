"""
Cliente de completions LLM con failover real Gemini→Groq.

Extraído para reutilizar en AgentIA (domain/services/ai_service.py) y en
las llamadas directas a `agent.client`/`agent.modelo` de
informe_handler.py/libre_noticias_handler.py — hallazgo real (2026-08-22):
durante un bloqueo de red hacia Gemini, `AgentIA` elegía UN proveedor al
construirse y nunca reintentaba con otro si fallaba en tiempo de ejecución
(era un "fallback" falso — solo mejoraba el mensaje de error). El Asistente
IA principal (domain/services/asistente_ia_service.py) ya tenía este mismo
problema resuelto desde la Fase 28; este módulo extiende el mismo criterio
al resto de consumidores de IA del proyecto.

No comparte código con asistente_ia_service.py a propósito — ese módulo
tiene su propio failover ya verificado en producción (loop de tool-calling,
streaming SSE, turno_id) y no se quiso arriesgar tocándolo; aquí se
duplica la lista de proveedores (pequeña y estable) en vez de acoplar
ambos módulos.

Nunca lanza una excepción "silenciosa": si todos los proveedores fallan,
propaga la última excepción real — el llamador decide cómo degradar
(mensaje de error amigable, texto de respaldo determinístico, etc.),
igual que ya hacían los try/except existentes en cada consumidor.
"""

from typing import List, Optional, Tuple

import asyncio

import openai

from core.config import settings
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def proveedores_disponibles() -> List[Tuple[str, str, str, str]]:
    """(nombre, base_url, api_key, modelo) en orden de prioridad — Gemini
    primero (Fase 10: 20x más TPM que Groq, sin tope diario aparte), luego
    Groq con su modelo principal, luego Groq con un segundo modelo
    (GROQ_MODEL_BACKUP) — protege contra que Groq descontinúe/tenga una
    caída puntual del modelo principal (ver AI_MODEL), NO contra el tope de
    8.000 TPM de la cuenta (ese tope es de la cuenta/tier, no del modelo:
    verificado en vivo el 22-ago-2026 que gpt-oss-120b y qwen3.6-27b dan el
    mismo error con el mismo prompt grande). Por último, OpenRouter
    (OPENROUTER_BACKUP_MODEL) — proveedor y cuota totalmente independientes
    de Groq, así que sirve exactamente en el caso real visto el 22-ago-2026:
    Groq agotó su cupo DIARIO (no solo por minuto) en ambos modelos. Su
    propia limitación (tier gratuito sin créditos comprados: 50 requests/día
    compartidas entre todos los modelos ':free', no por tokens) lo hace un
    último recurso, no un reemplazo de Groq."""
    candidatos = [
        ("gemini", settings.GEMINI_BASE_URL, settings.GEMINI_API_KEY, settings.GEMINI_MODEL),
        ("groq", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.AI_MODEL),
        ("groq_backup", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL_BACKUP),
        ("openrouter", settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, settings.OPENROUTER_BACKUP_MODEL),
    ]
    disponibles = [p for p in candidatos if p[2]]
    if not disponibles:
        raise RuntimeError(
            "Ningún proveedor de IA configurado (GEMINI_API_KEY/GROQ_API_KEY)"
        )
    return disponibles


def _es_error_de_disponibilidad(e: Exception) -> bool:
    """True si el error indica que ESE proveedor/modelo no está disponible
    ahora mismo (cuota agotada, red, modelo descontinuado, o prompt más
    grande que el TPM de la cuenta) — en cuyo caso tiene sentido reintentar
    con el siguiente proveedor. Cualquier otro error (ej. 400 por contenido
    mal formado) no es de disponibilidad y se deja propagar tal cual."""
    if isinstance(e, (openai.RateLimitError, openai.APIConnectionError, openai.NotFoundError)):
        return True
    if isinstance(e, openai.APIStatusError) and getattr(e, "status_code", None) == 413:
        return True
    return False


def completar_chat(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    etiqueta_log: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Intenta cada proveedor disponible en orden hasta que uno responda
    con éxito. Retorna (texto, proveedor_usado, modelo_usado).

    Solo reintenta con el siguiente proveedor ante un error de
    disponibilidad — ver `_es_error_de_disponibilidad()`: cuota agotada
    (429), red/timeout (`APIConnectionError`, incluye `APITimeoutError`),
    modelo descontinuado (404) o prompt más grande que el TPM de la cuenta
    (413). Cualquier otro error (ej. 400 por contenido mal formado) se
    propaga de inmediato — no tiene sentido reintentar con otro proveedor
    un error que no es de disponibilidad.

    Si todos los proveedores fallan, propaga la última excepción real.
    """
    proveedores = proveedores_disponibles()
    ultima_excepcion: Optional[Exception] = None
    prefijo = f"[{etiqueta_log}] " if etiqueta_log else ""

    for i, (nombre, base_url, api_key, modelo) in enumerate(proveedores):
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        try:
            resp = client.chat.completions.create(
                model=modelo,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if i > 0:
                logger.warning(f"{prefijo}Servido por fallback '{nombre}' (proveedor(es) anterior(es) no disponible(s))")
            return resp.choices[0].message.content, nombre, modelo
        except Exception as e:
            if not _es_error_de_disponibilidad(e):
                raise
            ultima_excepcion = e
            hay_siguiente = i + 1 < len(proveedores)
            logger.warning(
                f"{prefijo}Proveedor '{nombre}' no disponible ({type(e).__name__})"
                + (", probando siguiente..." if hay_siguiente else ", sin más proveedores.")
            )
            continue

    raise ultima_excepcion


async def completar_chat_async(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    etiqueta_log: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Variante async de completar_chat() — despacha el trabajo (síncrono,
    el SDK openai.OpenAI clásico) a un hilo aparte (asyncio.to_thread) para
    no bloquear el event loop mientras la IA responde, mismo cuidado ya
    aplicado en el resto del proyecto (ver asistente_ia_service.py,
    Fase 20)."""
    return await asyncio.to_thread(
        completar_chat, messages, temperature, max_tokens, etiqueta_log
    )
