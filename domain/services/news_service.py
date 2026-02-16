"""
Servicio de noticias del sector energético colombiano.

Responsabilidades:
- Obtener noticias vía NewsClient (GNews).
- Aplicar scoring para priorizar noticias "de ministro".
- Cache in-memory con TTL de 30 minutos.
- Devolver top 3 noticias depuradas.
"""

import logging
import re
import time
from typing import List, Dict, Optional
from infrastructure.news.news_client import NewsClient

logger = logging.getLogger(__name__)

# ── Scoring keywords ──────────────────────────────────────

# +2 puntos si el título/lead menciona Colombia + energía
KEYWORDS_HIGH = [
    "colombia", "energía", "eléctrico", "electricidad",
    "embalses", "generación", "sector eléctrico",
]

# +1 si menciona gobierno/regulador/instituciones clave
KEYWORDS_GOVT = [
    "gobierno", "ministro", "ministerio", "creg", "xm",
    "isa", "epm", "decreto", "regulador", "minminas",
    "minenergía", "minenergia", "viceministro", "anla",
    "upme", "transición energética", "racionamiento",
    "suministro", "interconexión",
]

# -2 si es puramente financiera/corporativa sin impacto sistémico
KEYWORDS_PENALIZE = [
    "acción", "acciones", "dividendo", "bolsa de valores",
    "cotización", "nasdaq", "nyse", "s&p",
]

# -3 si es política/diplomacia sin relación energética directa
KEYWORDS_NOISE = [
    "trump", "canciller", "cancillería", "deportación",
    "inmigración", "ofac", "sanciones", "rendición de cuentas",
    "fútbol", "selección", "farándula", "entretenimiento",
    "accidente de tránsito", "homicidio", "secuestro",
    "elecciones", "campaña electoral", "senado", "congreso",
]


def _compute_score(title: str, description: str) -> int:
    """Calcula score de relevancia para una noticia."""
    text = f"{title} {description}".lower()
    score = 0

    # +2 por keywords de alto impacto
    high_hits = sum(1 for kw in KEYWORDS_HIGH if kw in text)
    if high_hits >= 2:
        score += 2
    elif high_hits >= 1:
        score += 1

    # +1 por Keywords de gobierno/regulador
    govt_hits = sum(1 for kw in KEYWORDS_GOVT if kw in text)
    if govt_hits >= 1:
        score += min(govt_hits, 2)  # máx +2

    # -2 por keywords financieras sin impacto sistémico
    pen_hits = sum(1 for kw in KEYWORDS_PENALIZE if kw in text)
    if pen_hits >= 1:
        score -= 2

    # -3 por ruido: política, deportes, farándula, etc.
    noise_hits = sum(1 for kw in KEYWORDS_NOISE if kw in text)
    if noise_hits >= 1:
        score -= 3

    return score


def _clean_text(text: str, max_len: int = 120) -> str:
    """Limpia y trunca texto para resumen corto."""
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        # Cortar en última oración completa antes de max_len
        cut = text[:max_len].rfind('. ')
        if cut > 40:
            text = text[:cut + 1]
        else:
            text = text[:max_len].rstrip() + '…'
    return text


class NewsService:
    """Servicio de noticias con scoring y cache."""

    CACHE_TTL = 1800  # 30 minutos en segundos

    def __init__(self, api_key: Optional[str] = None):
        self.client = NewsClient(api_key=api_key)
        self._cache: Dict[str, dict] = {}  # key → {data, timestamp}

    def _get_cached(self, key: str) -> Optional[List[Dict]]:
        cached = self._cache.get(key)
        if cached and (time.time() - cached["timestamp"]) < self.CACHE_TTL:
            logger.info(f"[NEWS_SERVICE] Cache hit para '{key}'")
            return cached["data"]
        return None

    def _set_cache(self, key: str, data: List[Dict]):
        self._cache[key] = {"data": data, "timestamp": time.time()}

    async def get_top_news(self, max_items: int = 3) -> List[Dict]:
        """
        Obtiene las top N noticias relevantes para el sector energético.

        Returns:
            Lista de dicts: {titulo, resumen_corto, url, fuente, fecha_publicacion}
        """
        cache_key = "top_news"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached[:max_items]

        # Obtener artículos crudos
        raw_articles = await self.client.fetch_raw_news(
            max_results=10, country="co", lang="es"
        )

        if not raw_articles:
            # Intentar query regional si no hay resultados para CO
            logger.info("[NEWS_SERVICE] Sin resultados para CO, probando región")
            for country in ["co", ""]:
                for query in [
                    "energía eléctrica Colombia",
                    "sector energético Colombia embalses",
                ]:
                    raw_articles = await self.client.fetch_raw_news(
                        query=query, country=country, max_results=10
                    )
                    if raw_articles:
                        break
                if raw_articles:
                    break

        if not raw_articles:
            logger.warning("[NEWS_SERVICE] No se encontraron noticias")
            result = []
            self._set_cache(cache_key, result)
            return result

        # Aplicar scoring
        scored = []
        seen_titles = set()
        for art in raw_articles:
            title = art.get("title", "").strip()
            if not title:
                continue
            # Deduplicar por título similar
            title_key = re.sub(r'\W+', '', title.lower())[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            score = _compute_score(title, art.get("description", ""))
            scored.append((score, art))

        # Ordenar por score desc, luego por fecha desc
        scored.sort(key=lambda x: (x[0], x[1].get("publishedAt", "")), reverse=True)

        # Filtrar noticias con score < 0 (ruido)
        scored = [(s, a) for s, a in scored if s >= 0]

        # Construir resultado limpio
        result = []
        for score, art in scored[:max_items]:
            fecha_raw = art.get("publishedAt", "")
            # Formatear fecha: "2026-02-16T10:30:00Z" → "16 Feb 2026"
            fecha_fmt = fecha_raw[:10] if fecha_raw else ""

            result.append({
                "titulo": art["title"],
                "resumen_corto": _clean_text(art.get("description", "")),
                "url": art.get("url", ""),
                "fuente": art.get("source", ""),
                "fecha_publicacion": fecha_fmt,
                "_score": score,  # útil para debug
            })

        logger.info(
            f"[NEWS_SERVICE] {len(result)} noticias seleccionadas "
            f"(scores: {[r['_score'] for r in result]})"
        )
        self._set_cache(cache_key, result)
        return result
