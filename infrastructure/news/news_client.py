"""
Cliente de la API GNews para noticias del sector energético colombiano.

Documentación: https://gnews.io/docs/v4
Plan gratuito: 100 peticiones/día, máx 10 artículos por request.

Configurar en .env:
    GNEWS_API_KEY=tu_api_key_aqui
"""

import logging
import httpx
from typing import List, Dict, Optional
from core.config import get_settings

logger = logging.getLogger(__name__)

GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"

# Queries optimizadas para noticias energéticas de Colombia
# Se rotan para diversificar resultados
ENERGY_QUERIES = [
    "energía eléctrica Colombia",
    "sector eléctrico Colombia minería gas",
    "embalses tarifas energía renovable Colombia",
]

DEFAULT_QUERY = (
    "energía OR eléctrico OR electricidad OR embalses OR tarifas "
    "OR minería OR hidrocarburos OR gas OR renovables OR eólico "
    "OR solar OR interconexión OR transmisión Colombia"
)


class NewsClient:
    """Cliente HTTP para la API de GNews."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or getattr(settings, "GNEWS_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "[NEWS_CLIENT] GNEWS_API_KEY no configurada. "
                "Añade GNEWS_API_KEY=... a tu .env"
            )

    async def fetch_raw_news(
        self,
        query: str = DEFAULT_QUERY,
        country: str = "co",
        lang: str = "es",
        max_results: int = 10,
    ) -> List[Dict]:
        """
        Busca noticias en GNews.

        Returns:
            Lista de dicts con keys: title, description, url, source, publishedAt
        """
        if not self.api_key:
            logger.error("[NEWS_CLIENT] No hay API key configurada")
            return []

        params = {
            "q": query,
            "country": country,
            "lang": lang,
            "max": min(max_results, 10),  # GNews free: máx 10
            "token": self.api_key,
            "sortby": "publishedAt",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(GNEWS_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            articles = data.get("articles", [])
            logger.info(
                f"[NEWS_CLIENT] GNews devolvió {len(articles)} artículos "
                f"para query='{query[:40]}...'"
            )

            results = []
            for art in articles:
                results.append({
                    "title": art.get("title", ""),
                    "description": art.get("description", ""),
                    "url": art.get("url", ""),
                    "source": art.get("source", {}).get("name", ""),
                    "publishedAt": art.get("publishedAt", ""),
                    "image": art.get("image", ""),
                })
            return results

        except httpx.HTTPStatusError as e:
            logger.error(f"[NEWS_CLIENT] HTTP {e.response.status_code}: {e}")
            return []
        except Exception as e:
            logger.error(f"[NEWS_CLIENT] Error: {e}", exc_info=True)
            return []
