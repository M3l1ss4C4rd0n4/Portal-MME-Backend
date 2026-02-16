"""
Servicio de noticias del sector energético colombiano.

Responsabilidades:
- Obtener noticias de MÚLTIPLES fuentes (GNews, Mediastack, etc.).
- Normalizar a formato común.
- Deduplicar por URL y título.
- Aplicar scoring "revisión bibliográfica" para priorizar noticias.
- Cache in-memory con TTL de 30 minutos.
- Devolver top 3 + lista extendida (máx. 7 adicionales).
- Generar resumen general IA con los titulares del día.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from infrastructure.news.news_client import NewsClient
from infrastructure.news.mediastack_client import MediastackClient

logger = logging.getLogger(__name__)

# ── Scoring keywords ──────────────────────────────────────

# +2 puntos si el título/lead menciona Colombia + energía
KEYWORDS_HIGH = [
    "colombia", "energía", "eléctrico", "electricidad",
    "embalses", "generación", "sector eléctrico",
    "tarifas", "minería", "hidrocarburos", "gas natural",
    "petróleo", "renovables", "eólico", "solar",
    "transmisión", "interconexión", "transición energética",
]

# +1-2 si menciona gobierno/regulador/instituciones clave
KEYWORDS_GOVT = [
    "gobierno", "ministro", "ministerio", "creg", "xm",
    "isa", "epm", "decreto", "regulador", "minminas",
    "minenergía", "minenergia", "viceministro", "anla",
    "upme", "racionamiento", "suministro", "anh",
    "celsia", "enel", "isagén", "codensa",
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
    "celebridad", "gol", "reality",
]


def _compute_score(title: str, description: str,
                   country: Optional[str] = None) -> int:
    """Calcula score de relevancia para una noticia (revisión bibliográfica)."""
    text = f"{title} {description}".lower()
    score = 0

    # +2 por keywords de alto impacto
    high_hits = sum(1 for kw in KEYWORDS_HIGH if kw in text)
    if high_hits >= 2:
        score += 2
    elif high_hits >= 1:
        score += 1

    # +1-2 por Keywords de gobierno/regulador
    govt_hits = sum(1 for kw in KEYWORDS_GOVT if kw in text)
    if govt_hits >= 1:
        score += min(govt_hits, 2)  # máx +2

    # +2 si país es Colombia o texto menciona "colombia"
    if country and country.lower() in ("co", "colombia"):
        score += 2
    elif "colombia" in text:
        score += 2

    # +1 si país es de la región andina/sudamericana
    if country and country.lower() in ("ec", "pe", "br", "mx", "cl"):
        if any(kw in text for kw in ["interconexión", "mercado regional",
                                      "exportación", "importación"]):
            score += 1

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


def _normalize_gnews(raw: dict) -> dict:
    """Normaliza un artículo crudo de GNews al formato común."""
    fecha_raw = raw.get("publishedAt", "")
    return {
        "titulo": (raw.get("title") or "").strip(),
        "resumen": (raw.get("description") or "").strip(),
        "url": raw.get("url", ""),
        "fuente": raw.get("source", ""),
        "fecha": fecha_raw[:10] if fecha_raw else "",
        "pais": "co",  # GNews ya filtramos por CO
        "idioma": "es",
        "origen_api": "gnews",
    }


def _normalize_mediastack(raw: dict) -> dict:
    """Normaliza un artículo crudo de Mediastack al formato común."""
    fecha_raw = raw.get("published_at", "")
    # Mediastack fecha: "2026-02-16T10:30:00+00:00"
    fecha_fmt = fecha_raw[:10] if fecha_raw else ""
    return {
        "titulo": (raw.get("title") or "").strip(),
        "resumen": (raw.get("description") or "").strip(),
        "url": raw.get("url", ""),
        "fuente": raw.get("source", ""),
        "fecha": fecha_fmt,
        "pais": raw.get("country", ""),
        "idioma": raw.get("language", "es"),
        "origen_api": "mediastack",
    }


def _dedup_key(titulo: str) -> str:
    """Genera clave de dedup a partir del título."""
    return re.sub(r'\W+', '', titulo.lower())[:80]


class NewsService:
    """Servicio de noticias multi-fuente con scoring y cache."""

    CACHE_TTL = 1800  # 30 minutos en segundos

    def __init__(self, api_key: Optional[str] = None):
        self.gnews_client = NewsClient(api_key=api_key)
        self.mediastack_client = MediastackClient()
        self._cache: Dict[str, dict] = {}  # key → {data, timestamp}

    def _get_cached(self, key: str) -> Optional[dict]:
        cached = self._cache.get(key)
        if cached and (time.time() - cached["timestamp"]) < self.CACHE_TTL:
            logger.info(f"[NEWS_SERVICE] Cache hit para '{key}'")
            return cached["data"]
        return None

    def _set_cache(self, key: str, data: dict):
        self._cache[key] = {"data": data, "timestamp": time.time()}

    async def _fetch_all_sources(self) -> List[dict]:
        """
        Obtiene noticias de todas las fuentes disponibles en paralelo,
        normaliza y fusiona en una lista común.
        """
        all_normalized: List[dict] = []

        # ── GNews (fuente primaria) ──
        try:
            gnews_raw = await self.gnews_client.fetch_raw_news(
                max_results=10, country="co", lang="es"
            )
            if not gnews_raw:
                # Fallback: queries alternativas
                for query in [
                    "energía eléctrica Colombia",
                    "sector energético Colombia embalses",
                ]:
                    gnews_raw = await self.gnews_client.fetch_raw_news(
                        query=query, country="", max_results=10
                    )
                    if gnews_raw:
                        break

            for art in gnews_raw:
                all_normalized.append(_normalize_gnews(art))
            logger.info(
                f"[NEWS_SERVICE] GNews aportó {len(gnews_raw)} artículos"
            )
        except Exception as e:
            logger.warning(f"[NEWS_SERVICE] Error GNews: {e}")

        # ── Mediastack (fuente secundaria, solo si hay key) ──
        if self.mediastack_client.is_available:
            try:
                ms_raw = await self.mediastack_client.fetch_energy_news(limit=20)
                for art in ms_raw:
                    all_normalized.append(_normalize_mediastack(art))
                logger.info(
                    f"[NEWS_SERVICE] Mediastack aportó {len(ms_raw)} artículos"
                )
            except Exception as e:
                logger.warning(f"[NEWS_SERVICE] Error Mediastack: {e}")

        return all_normalized

    def _score_and_rank(
        self, articles: List[dict]
    ) -> List[dict]:
        """
        Deduplicar, aplicar scoring, filtrar ruido y ordenar.
        Retorna lista ordenada por score desc.
        """
        seen_urls: set = set()
        seen_titles: set = set()
        scored: List[dict] = []

        for art in articles:
            titulo = art.get("titulo", "").strip()
            url = art.get("url", "").strip()
            if not titulo:
                continue

            # Dedup por URL
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            # Dedup por título similar
            tkey = _dedup_key(titulo)
            if tkey in seen_titles:
                continue
            seen_titles.add(tkey)

            score = _compute_score(
                titulo,
                art.get("resumen", ""),
                art.get("pais"),
            )
            art["_score"] = score
            scored.append(art)

        # Filtrar score < 0 (ruido)
        scored = [a for a in scored if a["_score"] >= 0]

        # Ordenar por score desc, luego fecha desc
        scored.sort(
            key=lambda x: (x["_score"], x.get("fecha", "")),
            reverse=True,
        )
        return scored

    async def get_top_news(
        self, max_items: int = 3
    ) -> List[Dict]:
        """
        Compatibilidad: devuelve solo las top N noticias.
        Usa internamente get_enriched_news().

        Returns:
            Lista de dicts: {titulo, resumen_corto, url, fuente,
                            fecha_publicacion, _score}
        """
        result = await self.get_enriched_news(
            max_top=max_items, max_extra=0
        )
        return result["top"]

    async def get_enriched_news(
        self,
        max_top: int = 3,
        max_extra: int = 7,
    ) -> Dict:
        """
        Obtiene noticias enriquecidas con fusión multi-fuente.

        Returns:
            {
                "top": [ {titulo, resumen_corto, url, fuente,
                          fecha_publicacion, origen_api, _score}, ... ],
                "otras": [ ... ],  # máx max_extra adicionales
                "fuentes_usadas": ["gnews", "mediastack", ...],
                "total_analizadas": int,
            }
        """
        cache_key = "enriched_news"
        cached = self._get_cached(cache_key)
        if cached is not None:
            # Ajustar slicing al max pedido
            return {
                "top": cached["top"][:max_top],
                "otras": cached["otras"][:max_extra],
                "fuentes_usadas": cached["fuentes_usadas"],
                "total_analizadas": cached["total_analizadas"],
            }

        # Obtener artículos de todas las fuentes
        all_articles = await self._fetch_all_sources()

        if not all_articles:
            logger.warning("[NEWS_SERVICE] No se encontraron noticias en ninguna fuente")
            empty = {
                "top": [],
                "otras": [],
                "fuentes_usadas": [],
                "total_analizadas": 0,
            }
            self._set_cache(cache_key, empty)
            return empty

        # Scoring y ranking
        ranked = self._score_and_rank(all_articles)

        # Fuentes que aportaron artículos
        fuentes = list({a.get("origen_api", "?") for a in all_articles})

        # Formatear noticias al formato de salida
        def _fmt(art: dict) -> dict:
            return {
                "titulo": art["titulo"],
                "resumen_corto": _clean_text(art.get("resumen", ""), 180),
                "url": art.get("url", ""),
                "fuente": art.get("fuente", ""),
                "fecha_publicacion": art.get("fecha", ""),
                "origen_api": art.get("origen_api", ""),
                "_score": art.get("_score", 0),
            }

        top = [_fmt(a) for a in ranked[:max_top]]
        otras = [_fmt(a) for a in ranked[max_top:max_top + max_extra]]

        result = {
            "top": top,
            "otras": otras,
            "fuentes_usadas": fuentes,
            "total_analizadas": len(all_articles),
        }

        logger.info(
            f"[NEWS_SERVICE] {len(top)} top + {len(otras)} extra "
            f"(total analizadas: {len(all_articles)}, "
            f"fuentes: {fuentes}, "
            f"scores top: {[r['_score'] for r in top]})"
        )
        self._set_cache(cache_key, result)
        return result

