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
from infrastructure.news.google_news_rss import fetch_google_news_rss

logger = logging.getLogger(__name__)

# ── Scoring keywords ──────────────────────────────────────

# PUERTA DE RELEVANCIA: el artículo DEBE mencionar al menos 1
# de estos términos para ser considerado.  Sin esto → descartado.
KEYWORDS_GATE = [
    # Sector eléctrico
    "energía", "energético", "energetico", "eléctric", "electric",
    "generación", "generacion", "transmisión", "transmision",
    "distribución eléctrica", "embalse", "hidroeléctric",
    "termoeléctr", "termoeléctrica", "renovable", "eólico", "eólica",
    "fotovoltaic", "panel solar", "granja solar", "parque solar",
    "parque eólico", "bioenergía", "biomasa", "geotérm",
    # Gas / petróleo / minería
    "gas natural", "regasificación", "regasificacion",
    "petróleo", "petroleo", "hidrocarburo", "gasoducto",
    "oleoducto", "refinería", "refineria", "gnl", "lng",
    "fracking", "exploración petrolera", "minería", "mineria",
    "carbón", "carbon mineral", "niquel", "oro minero",
    " gas ", "precio del gas", "producción de gas",
    "importar gas", "exportar gas", "suministro de gas",
    # Institucional / regulación
    "minminas", "minenergía", "minenergia", "creg", "upme",
    "anh", "anla", "xm s.a", "isa ", "isagén", "isagen",
    "celsia", "enel colombia", "codensa", "epm", "epsa",
    "transporte de gas", "promigas", "tgi",
    # Política energética
    "tarifa eléctric", "tarifa de energía", "tarifa de gas",
    "racionamiento", "apagón", "apagon", "subsidio energétic",
    "transición energética", "transicion energetica",
    "interconexión eléctrica", "interconexion electrica",
    "operación del sistema", "despacho de energía",
    "suministro eléctric", "suministro de gas",
    "importación de gas", "importacion de gas",
    "precio de energía", "plan energético",
    # Movilidad eléctrica
    "vehículo eléctric", "vehiculo electric", "movilidad eléctric",
    "carro eléctric", "bus eléctric", "electrolinera",
]

# +2 puntos si el título/lead menciona Colombia + energía
KEYWORDS_HIGH = [
    "colombia", "energía", "eléctrico", "electricidad",
    "embalses", "generación", "sector eléctrico",
    "tarifas de energía", "minería", "hidrocarburos", "gas natural",
    "petróleo", "renovables", "eólico", "fotovoltaica",
    "transmisión", "interconexión", "transición energética",
    "racionamiento", "apagón", "embalse",
]

# +1-2 si menciona gobierno/regulador/instituciones clave
KEYWORDS_GOVT = [
    "gobierno", "ministro de minas", "ministerio de minas",
    "creg", "xm", "isa", "epm", "decreto",
    "regulador", "minminas", "minenergía", "minenergia",
    "viceministro", "anla", "upme", "anh",
    "racionamiento", "suministro",
    "celsia", "enel", "isagén", "codensa",
]

# -2 si es puramente financiera/corporativa sin impacto sistémico
KEYWORDS_PENALIZE = [
    "acción", "acciones", "dividendo", "bolsa de valores",
    "cotización", "nasdaq", "nyse", "s&p",
]

# -3 si es política/diplomacia/entretenimiento sin relación energética
KEYWORDS_NOISE = [
    # Política internacional no energética
    "trump", "canciller", "cancillería", "deportación",
    "inmigración", "rendición de cuentas", "imposición de condiciones",
    "aranceles", "visa", "pasaporte", "embajada",
    # Entretenimiento / farándula
    "fútbol", "selección colombia futbol", "farándula",
    "entretenimiento", "accidente de tránsito", "homicidio",
    "secuestro", "celebridad", "gol", "reality",
    "cantante", "artista", "concierto", "recital",
    "reggaeton", "turizo", "shakira", "influencer",
    "instagram", "tiktok", "youtube", "streamer",
    # Electoral
    "elecciones", "campaña electoral", "senado", "congreso",
    "senador", "representante a la cámara",
    # Astronomía (falso positivo por "solar")
    "eclipse solar", "anillo de fuego", "eclipse anular",
    "eclipse lunar", "lluvia de estrellas", "meteorito",
    # Desastres no energéticos (caridad genérica)
    "damnificados", "recaudaron", "donación benéfica",
]

# Patrones que cancelan falsos positivos de KEYWORDS_HIGH
# Si alguno de estos aparece, eliminar score de "solar"/"eléctric"
FALSE_POSITIVE_PATTERNS = [
    r"eclipse\s+solar",
    r"anillo\s+de\s+fuego",
    r"eclipse\s+anular",
    r"carro\s+(?:de|para)\s+juguete",
    r"bicicleta\s+eléctrica\s+(?:robada|hurtada)",
]


def _passes_relevance_gate(title: str, description: str) -> bool:
    """
    Puerta de relevancia estricta: el artículo DEBE mencionar
    al menos 1 término del vocabulario energético para ser considerado.
    Esto evita que noticias genéricas pasen solo por decir "Colombia".
    """
    text = f"{title} {description}".lower()
    return any(kw in text for kw in KEYWORDS_GATE)


def _compute_score(title: str, description: str,
                   country: Optional[str] = None) -> int:
    """Calcula score de relevancia para una noticia (revisión bibliográfica)."""
    text = f"{title} {description}".lower()
    score = 0

    # Chequear falsos positivos primero
    is_false_positive = any(
        re.search(pat, text) for pat in FALSE_POSITIVE_PATTERNS
    )

    # +2 por keywords de alto impacto (ignorar si es falso positivo)
    if not is_false_positive:
        high_hits = sum(1 for kw in KEYWORDS_HIGH if kw in text)
        if high_hits >= 2:
            score += 3
        elif high_hits >= 1:
            score += 1
    else:
        score -= 2  # penalizar falsos positivos

    # +1-2 por Keywords de gobierno/regulador
    govt_hits = sum(1 for kw in KEYWORDS_GOVT if kw in text)
    if govt_hits >= 1:
        score += min(govt_hits, 2)  # máx +2

    # +2 si país es Colombia o texto menciona "colombia"
    if country and country.lower() in ("co", "colombia"):
        score += 2
    elif "colombia" in text:
        score += 2

    # +1 si país es de la región andina/sudamericana con contexto energético
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
    if noise_hits >= 2:
        score -= 2  # penalización extra por doble ruido

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


def _normalize_google_rss(raw: dict) -> dict:
    """Normaliza un artículo crudo de Google News RSS al formato común."""
    fecha_raw = raw.get("publishedAt", "")
    fecha_fmt = fecha_raw[:10] if fecha_raw else ""
    return {
        "titulo": (raw.get("title") or "").strip(),
        "resumen": (raw.get("description") or "").strip(),
        "url": raw.get("url", ""),
        "fuente": raw.get("source", ""),
        "fecha": fecha_fmt,
        "pais": raw.get("country", "co"),
        "idioma": "es",
        "origen_api": "google_rss",
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

        # ── Google News RSS (fuente terciaria, gratis, artículos frescos) ──
        try:
            grss_raw = await fetch_google_news_rss(max_per_query=10)
            for art in grss_raw:
                all_normalized.append(_normalize_google_rss(art))
            logger.info(
                f"[NEWS_SERVICE] Google RSS aportó {len(grss_raw)} artículos"
            )
        except Exception as e:
            logger.warning(f"[NEWS_SERVICE] Error Google RSS: {e}")

        return all_normalized

    def _score_and_rank(
        self, articles: List[dict]
    ) -> List[dict]:
        """
        Deduplicar, aplicar puerta de relevancia, scoring, filtrar
        ruido y ordenar.  Retorna lista ordenada por score desc.
        """
        seen_urls: set = set()
        seen_titles: set = set()
        scored: List[dict] = []
        rejected_gate = 0

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

            # ── PUERTA DE RELEVANCIA ──
            # El artículo DEBE mencionar al menos 1 término energético.
            # Esto bloquea noticias genéricas que solo dicen "Colombia".
            if not _passes_relevance_gate(titulo, art.get("resumen", "")):
                rejected_gate += 1
                continue

            score = _compute_score(
                titulo,
                art.get("resumen", ""),
                art.get("pais"),
            )

            # ── BONUS POR FRESCURA ──
            # Artículos recientes tienen prioridad sobre los antiguos
            fecha_str = art.get("fecha", "")
            if fecha_str and len(fecha_str) >= 10:
                try:
                    fecha_art = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                    dias_antiguedad = (datetime.now().date() - fecha_art).days
                    if dias_antiguedad <= 0:
                        score += 3   # Hoy
                    elif dias_antiguedad == 1:
                        score += 2   # Ayer
                    elif dias_antiguedad <= 3:
                        score += 1   # Últimos 3 días
                    elif dias_antiguedad > 14:
                        score -= 2   # Más de 2 semanas: penalizar
                except (ValueError, TypeError):
                    pass

            art["_score"] = score
            scored.append(art)

        # Filtrar score < 1 (requiere al menos alguna relevancia)
        scored = [a for a in scored if a["_score"] >= 1]

        # Ordenar por score desc, luego fecha desc
        scored.sort(
            key=lambda x: (x["_score"], x.get("fecha", "")),
            reverse=True,
        )

        if rejected_gate:
            logger.info(
                f"[NEWS_SERVICE] Puerta de relevancia descartó "
                f"{rejected_gate} artículos sin vocabulario energético"
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

