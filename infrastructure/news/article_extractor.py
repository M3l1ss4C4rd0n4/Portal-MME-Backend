"""
Extracción de texto completo de artículos de noticias (Fase 32).

Complementa a NewsService (que hoy solo captura titular+resumen corto)
con el cuerpo real del artículo, vía `trafilatura` — misma idea que el
RAG aplica a los PDFs internos: dar al LLM el contenido completo, no
solo un fragmento.

Limitación conocida, verificada en vivo (no teórica): las URLs de
Google News RSS (`news.google.com/rss/articles/...`) son wrappers que
renderizan una SPA de React, no un redirect HTTP simple — no se pueden
abrir para extraer texto sin un truco de decodificación no oficial de
la API interna de Google. Por eso se descartan explícitamente antes de
intentar la descarga, en vez de gastar el timeout en un intento
condenado.

Nunca lanza excepción — un fallo de extracción (sitio caído, artículo
detrás de paywall, timeout) degrada con gracia a None, y el consumidor
sigue usando titular+resumen como hoy.
"""

import asyncio
from typing import Optional

import trafilatura

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; PortalMME/1.0; +https://portalviceministerioenergia.minenergia.gov.co)"


def _extraer_sync(url: str, timeout: float) -> Optional[str]:
    downloaded = trafilatura.fetch_url(
        url,
        config=_config_con_timeout(timeout),
    )
    if not downloaded:
        return None
    texto = trafilatura.extract(
        downloaded,
        favor_precision=True,
        include_comments=False,
    )
    if texto and len(texto) >= 200:
        return texto
    return None


def _config_con_timeout(timeout: float):
    config = trafilatura.settings.use_config()
    config.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(int(timeout)))
    config.set("DEFAULT", "USER_AGENTS", _USER_AGENT)
    return config


async def extraer_texto_completo(url: str, timeout: float = 6.0) -> Optional[str]:
    """
    Descarga y extrae el texto completo de un artículo real (no un
    wrapper de Google News). Retorna None si la URL es un wrapper
    conocido, si falla la descarga, o si el texto extraído es
    demasiado corto para ser el cuerpo real del artículo.
    """
    if "news.google.com" in url:
        return None
    if not url:
        return None
    try:
        return await asyncio.to_thread(_extraer_sync, url, timeout)
    except Exception as e:
        logger.warning(f"[ARTICLE_EXTRACTOR] Error extrayendo {url[:80]}: {e}")
        return None
