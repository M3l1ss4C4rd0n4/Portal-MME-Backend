"""
Cliente de la API Mediastack para noticias del sector energético.

Documentación: https://mediastack.com/documentation
Plan gratuito: 500 peticiones/mes, máx 25 artículos por request.

Configurar en .env:
    MEDIASTACK_API_KEY=tu_api_key_aqui
"""

import logging
import httpx
from typing import List, Dict, Optional
from core.config import get_settings

logger = logging.getLogger(__name__)

MEDIASTACK_URL = "http://api.mediastack.com/v1/news"

# Keywords energéticas para filtro en la API
ENERGY_KEYWORDS = (
    "energy,electricity,power,oil,gas,mining,renewable,"
    "energía,eléctrico,embalses,tarifas,petróleo,minería,"
    "hidrocarburos,renovable,solar,eólico"
)


class MediastackClient:
    """Cliente HTTP para la API de Mediastack (segunda fuente de noticias)."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 10.0):
        settings = get_settings()
        self.api_key = api_key or getattr(settings, "MEDIASTACK_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            logger.info(
                "[MEDIASTACK] MEDIASTACK_API_KEY no configurada — "
                "esta fuente quedará deshabilitada"
            )

    @property
    def is_available(self) -> bool:
        """Retorna True si el cliente tiene API key configurada."""
        return bool(self.api_key)

    async def fetch_energy_news(self, limit: int = 20) -> List[Dict]:
        """
        Busca noticias de energía/minería en Mediastack.

        Filtra por idioma español, país Colombia (+ región),
        y keywords de energía/minas.

        Returns:
            Lista de dicts con keys: title, description, url,
            source, published_at, country, language.
            Lista vacía si falla o no hay key.
        """
        if not self.api_key:
            return []

        params = {
            "access_key": self.api_key,
            "keywords": ENERGY_KEYWORDS,
            "languages": "es",
            "countries": "co,ec,pe,br,mx",
            "sort": "published_desc",
            "limit": min(limit, 25),  # free plan: máx 25
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(MEDIASTACK_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()

            # Mediastack devuelve {"data": [...], "pagination": {...}}
            articles = payload.get("data", [])
            logger.info(
                f"[MEDIASTACK] Devolvió {len(articles)} artículos"
            )

            results = []
            for art in articles:
                title = (art.get("title") or "").strip()
                if not title:
                    continue
                results.append({
                    "title": title,
                    "description": (art.get("description") or "").strip(),
                    "url": art.get("url", ""),
                    "source": art.get("source") or "",
                    "published_at": art.get("published_at") or "",
                    "country": art.get("country") or "",
                    "language": art.get("language") or "es",
                })
            return results

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[MEDIASTACK] HTTP {e.response.status_code}: {e}"
            )
            return []
        except Exception as e:
            logger.warning(f"[MEDIASTACK] Error: {e}")
            return []
