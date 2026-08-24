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
import html
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from infrastructure.news.news_client import NewsClient
from infrastructure.news.mediastack_client import MediastackClient
from infrastructure.news.google_news_rss import fetch_google_news_rss
from infrastructure.news.larepublica_rss import fetch_larepublica_rss
from infrastructure.news.article_extractor import extraer_texto_completo
from infrastructure.cache.redis_client import redis_get_json, redis_set_json
from domain.services.news_keywords import filter_tier1, filter_tier2_fill
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

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
    "precio del gas", "producción de gas",
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
    # Transición energética / descarbonización / hidrógeno
    "hidrógeno verde", "hidrogeno verde", "descarbonización", "descarbonizacion",
    "transición justa", "transicion justa", "metales de transición",
    "materiales críticos", "electrificación rural",
    # Ecopetrol / proyectos estratégicos
    "ecopetrol", "hidroituango", "reficar", "regalías", "regalias",
    "canon minero", "canon petrolero", "reservas probadas", "yacimiento",
    # Hidrocarburos específicos
    "combustible", "diésel", "diesel", "gasolina", "acpm", "fuel oil",
    "precio del barril", "brent", "wti", "opep",
    "offshore", "aguas profundas", "shale", "gas de esquisto",
    # Minería estratégica
    "litio", "cobre", "esmeralda", "zona franca", "minería ilegal",
    "minería artesanal", "formalización minera", "formalizacion minera",
    "drummond", "cerrejón", "cerrejon", "prodeco", "puerto de carbón",
    "exportación de carbón",
    # Sistema eléctrico específico
    "zni", "zona no interconectada", "autogeneración", "autogeneracion",
    "autogenerador", "comunidad energética", "planta térmica",
    "generador térmico", "mem", "mercado de corto plazo",
    "corte de energía", "corte de energia", "suspensión del servicio",
    "hurto de energía", "hurto de energia", "conexiones ilegales",
    "subsidio de energía", "subsidio de energia", "tarifa social",
    # Clima / eventos que afectan el sector
    "fenómeno del niño", "fenomeno del niño", "fenómeno de el niño",
    "sequía", "sequia", "precipitación", "precipitacion",
    "contrabando de combustible",
]

# +2 puntos si el título/lead menciona Colombia + energía
KEYWORDS_HIGH = [
    "colombia", "energía", "eléctrico", "electricidad",
    "embalses", "generación", "sector eléctrico",
    "tarifas de energía", "minería", "hidrocarburos", "gas natural",
    "petróleo", "renovables", "eólico", "fotovoltaica",
    "transmisión", "interconexión", "transición energética",
    "racionamiento", "apagón", "embalse",
    # Temas estratégicos para el MME
    "hidrógeno verde", "descarbonización", "ecopetrol", "fenómeno del niño",
    "litio", "regalías", "hidroituango", "minería ilegal",
    "cerrejón", "offshore", "transición justa", "hurto de energía",
    "combustible", "precio del barril", "autogeneración",
]

# +1-2 si menciona gobierno/regulador/instituciones clave
KEYWORDS_GOVT = [
    "gobierno", "ministro de minas", "ministerio de minas",
    "viceministro de energía", "viceministro de minas",
    "creg", "xm", "isa", "epm", "decreto",
    "regulador", "minminas", "minenergía", "minenergia",
    "viceministro", "anla", "upme", "anh", "sspd",
    "superintendencia", "conpes",
    "racionamiento", "suministro",
    "celsia", "enel", "isagén", "codensa",
    "ecopetrol", "hidroituango", "drummond", "cerrejón", "cerrejon",
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
    # Salud / epidemias (falso positivo que pasa por "gas" o "ministerio")
    "minsalud", "ministerio de salud", "viruela", "epidemia",
    "pandemia", "hospital", "vacuna", "vacunación", "síntoma",
    "contagio", "infeccios", "enfermedad", "dengue", "malaria",
    "covid", "coronavirus", "salud pública", "eps ", "ips ",
    "medicamento", "farmacéutic", "clínica ", "urgencias",
    # Deportes / entretenimiento adicional
    "nba", "champions", "mundial", "olimpiadas", "ciclismo",
    # Cultura / sociedad sin relación energética
    "belleza", "miss ", "reina ", "gastronomía", "restaurante",
    "turismo", "hotel ", "playa ", "moda ", "diseñador",
    "apuesta", "casino", "juego de azar", "lotería",
    # Educación / eventos sociales genéricos
    "graduación", "universidad", "colegio", "examen", "icfes",
    # Otros falsos positivos comunes
    "perro", "gato", "mascota", "navidad", "halloween",
    "carrera atlética", "maratón", "ciclismo",
    # Automotriz sin infraestructura energética
    "tesla", "general motors", "ford motor", "bmw", "mercedes benz",
    "ventas de vehículos", "ventas de autos", "mercado automotriz",
    "unidades vendidas", "record de ventas",
    # Macroeconomía sin vínculo energético directo
    "subir tasas", "bajar tasas", "tasa de interés",
    "inflación meta", "banco central europeo", "reserva federal",
    "dólar sube", "dólar baja", "tipo de cambio",
    "deuda neta", "déficit fiscal", "pib trimestral",
    # Comercio exterior genérico sin energía
    "flores", "café colombiano", "exportación de flores",
    "exportación de banano", "turismo receptor",
    # Tech / startup sin energía
    "inteligencia artificial", "startup", "unicornio tecnológico",
    "criptomoneda", "bitcoin", "blockchain", "nft",
]

# Patrones que cancelan falsos positivos de KEYWORDS_HIGH
# Si alguno de estos aparece, eliminar score de "solar"/"eléctric"
FALSE_POSITIVE_PATTERNS = [
    r"eclipse\s+solar",
    r"anillo\s+de\s+fuego",
    r"eclipse\s+anular",
    r"carro\s+(?:de|para)\s+juguete",
    r"bicicleta\s+eléctrica\s+(?:robada|hurtada)",
    # Ventas de vehículos sin relación con infraestructura eléctrica
    r"tesla\s+(?:protagoniza|récord|ventas|entrega|modelo)",
    r"\d[\d.]+\s+vehículos?\s+eléctricos?\s+(?:vendidos?|entregados?)",
    r"salto\s+récord.{0,30}vehículos?\s+eléctricos?",
    # Tasas / macro sin energía en el título
    r"subir\s+tasas\s+no",
    r"tasas?\s+de\s+interés\s+(?:sube|baja|reduce|aumenta)",
    r"banco\s+central\s+(?:sube|baja|mantiene)\s+tasa",
]


def _passes_relevance_gate(title: str, description: str) -> bool:
    """
    Puerta de relevancia estricta: el artículo DEBE mencionar
    al menos 1 término del vocabulario energético para ser considerado.
    Esto evita que noticias genéricas pasen solo por decir "Colombia".
    """
    text = f"{title} {description}".lower()
    return any(kw in text for kw in KEYWORDS_GATE)


def _is_hard_blocked(title: str, description: str) -> bool:
    """
    Bloqueo duro: artículos que coinciden con FALSE_POSITIVE_PATTERNS
    o que tienen términos de ruido prominentes en el TÍTULO se descartan
    completamente, sin importar otros bonos (fuente, frescura, imagen).
    """
    title_lower = title.lower()
    text_lower = f"{title} {description}".lower()
    # Patrón regex en título o descripción
    if any(re.search(pat, text_lower) for pat in FALSE_POSITIVE_PATTERNS):
        return True
    # Ruido en el propio título (no basta que esté en la descripción)
    noise_in_title = sum(1 for kw in KEYWORDS_NOISE if kw in title_lower)
    if noise_in_title >= 1:
        return True
    return False


def _compute_score(title: str, description: str,
                   country: Optional[str] = None) -> int:
    """Calcula score de relevancia para una noticia (revisión bibliográfica)."""
    text = f"{title} {description}".lower()
    score = 0

    # +2 por keywords de alto impacto
    high_hits = sum(1 for kw in KEYWORDS_HIGH if kw in text)
    if high_hits >= 2:
        score += 3
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
    text = html.unescape(text)
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
        "imagen": (raw.get("image") or "").strip(),
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
        "imagen": (raw.get("image") or "").strip(),
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
        "source_url": raw.get("source_url", ""),
        "fecha": fecha_fmt,
        "pais": raw.get("country", "co"),
        "idioma": "es",
        "origen_api": "google_rss",
    }


def _dedup_key(titulo: str) -> str:
    """Genera clave de dedup a partir del título."""
    return re.sub(r'\W+', '', titulo.lower())[:80]


# Stopwords españolas para dedup semántico
_STOPWORDS_ES = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las",
    "por", "un", "para", "con", "no", "una", "su", "al", "lo", "más",
    "o", "este", "ya", "sobre", "entre", "cuando", "todo", "esta", "ser",
    "son", "dos", "también", "fue", "había", "era", "muy", "hasta",
    "desde", "esto", "él", "porque", "qué", "sólo", "han", "yo", "hay",
    "vez", "pueden", "todos", "así", "nos", "ni", "parte", "tiene",
    "uno", "donde", "bien", "tiempo", "mismo", "ese", "ahora", "cada",
    "e", "vida", "otro", "después", "te", "otros", "aunque", "esa",
    "eso", "sea", "sido", "cada", "gran", "puede", "tienen", "están",
    "estado", "cómo", "pero", "además", "según", "sin", "sus", "les",
    "me", "le", "mi", "tu", "tus", "mis", "he", "has", "ha", "hemos",
    "habéis", "tenía", "tuve", "tuvo", "estoy", "estás", "está",
    "estamos", "están", "estaba", "estaré", "estará", "esté", "estés",
    "estén", "estuvo", "estuvieron", "estando", "agua", "dijo", "ante",
    "años", "año", "mes", "día", "hoy", "ayer", "mañana", "solo", "tan",
    "poco", "mucho", "muchos", "muchas", "toda", "todas", "nada", "algo",
    "quien", "quienes", "cual", "cuales", "cuya", "cuyas", "como",
    "cuando", "donde", "mientras", "ademas", "tampoco", "sino", "ni",
    "tanto", "casi", "tal", "tales", "mismo", "mismos", "mismas",
    "propia", "propias", "propios", "ultima", "ultimo", "ultimos",
    "pasado", "pasada", "proximo", "proxima", "actual", "anterior",
}


def _significant_words(titulo: str) -> set:
    """Extrae palabras significativas de un título para comparación semántica."""
    words = re.findall(r'\b[a-záéíóúñ]{4,}\b', titulo.lower())
    return {w for w in words if w not in _STOPWORDS_ES}


def _jaccard_similarity(set1: set, set2: set) -> float:
    """Calcula el índice de Jaccard entre dos conjuntos."""
    if not set1 or not set2:
        return 0.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0


def _normalize_url(url: str) -> str:
    """Normaliza una URL quitando parámetros UTM, fragmentos y trailing slashes."""
    if not url:
        return ""
    # Quitar fragmento
    url = url.split("#")[0]
    # Quitar parámetros UTM y tracking comunes
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for key in list(params.keys()):
        if key.lower().startswith(("utm_", "fbclid", "gclid", "twclid", "cid", "mc_cid", "iclid")):
            del params[key]
    new_query = urlencode(params, doseq=True)
    url = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.params, new_query, ""))
    return url


def _find_similar_article(titulo: str, seen_articles: List[dict], umbral: float = 0.25) -> Optional[int]:
    """
    Busca si existe un artículo ya visto con título semánticamente similar.
    Usa Jaccard sobre palabras significativas + regla de mínimo 3 palabras
    compartidas para capturar noticias del mismo tema con redacción distinta.
    Retorna el índice del artículo similar, o None si no hay coincidencia.
    """
    words_new = _significant_words(titulo)
    if not words_new:
        return None
    for idx, art in enumerate(seen_articles):
        words_existing = _significant_words(art.get("titulo", ""))
        if not words_existing:
            continue
        inter = len(words_new & words_existing)
        union = len(words_new | words_existing)
        jaccard = inter / union if union > 0 else 0.0
        # Duplicado si: Jaccard >= umbral O comparten 2+ palabras significativas
        if jaccard >= umbral or inter >= 2:
            return idx
    return None


# Consolidadas de 6 a 3 queries (mismos términos, agrupados con OR en menos
# llamadas) para gastar menos de la cuota gratuita de GNews (100/día) — con
# 6 queries por refresco de caché (cada 8h) se agotaba en pocos ciclos.
HYDROCARBON_QUERIES = [
    "petróleo OR gas natural OR hidrocarburos OR crudo OR ANH Colombia",
    "gasolina OR diésel OR combustible OR ecopetrol OR refinería OR "
    "gasoducto OR oleoducto OR yacimiento OR pozo petrolero Colombia",
    "carbón OR carbon mineral OR minería OR cerrejón OR drummond Colombia",
]

# Keywords para filtrar artículos de hidrocarburos: ver domain/services/news_keywords.py
# (fuente única compartida con el fallback de libre_noticias_handler.py).


class NewsService:
    """Servicio de noticias multi-fuente con scoring y cache."""

    CACHE_TTL = 28800  # 8 horas en segundos

    def __init__(self, api_key: Optional[str] = None):
        self.gnews_client = NewsClient(api_key=api_key)
        self.mediastack_client = MediastackClient()
        self._cache: Dict[str, dict] = {}  # key → {data, timestamp}

    def _get_cached(self, key: str) -> Optional[dict]:
        # Redis primero (compartido entre workers); fallback a dict in-memory
        redis_data = redis_get_json(f"news:{key}")
        if redis_data is not None:
            logger.info(f"[NEWS_SERVICE] Cache hit Redis para '{key}'")
            return redis_data
        cached = self._cache.get(key)
        if cached and (time.time() - cached["timestamp"]) < self.CACHE_TTL:
            logger.info(f"[NEWS_SERVICE] Cache hit local para '{key}'")
            return cached["data"]
        return None

    def _set_cache(self, key: str, data: dict):
        # Escribir en Redis (compartido) y en dict local (fallback si Redis cae)
        redis_set_json(f"news:{key}", data, ttl=self.CACHE_TTL)
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

        # ── La República RSS (fuente cuaternaria — revista económica prioritaria) ──
        try:
            lr_raw = await fetch_larepublica_rss()
            for art in lr_raw:
                all_normalized.append(art)
            logger.info(
                f"[NEWS_SERVICE] La República RSS aportó {len(lr_raw)} artículos"
            )
        except Exception as e:
            logger.warning(f"[NEWS_SERVICE] Error La República RSS: {e}")

        return all_normalized

    def _score_and_rank(
        self, articles: List[dict]
    ) -> List[dict]:
        """
        Deduplicar, aplicar puerta de relevancia, scoring, filtrar
        ruido y ordenar.  Retorna lista ordenada por score desc.
        """
        seen_urls: set = set()
        scored: List[dict] = []
        rejected_gate = 0
        duplicates = 0

        for art in articles:
            titulo = art.get("titulo", "").strip()
            url = art.get("url", "").strip()
            if not titulo:
                continue

            # Dedup por URL normalizada
            norm_url = _normalize_url(url)
            if norm_url and norm_url in seen_urls:
                continue
            if norm_url:
                seen_urls.add(norm_url)

            # ── BLOQUEO DURO: falsos positivos por título ──
            if _is_hard_blocked(titulo, art.get("resumen", "")):
                rejected_gate += 1
                continue

            # ── PUERTA DE RELEVANCIA ──
            # El artículo DEBE mencionar al menos 1 término energético.
            if not _passes_relevance_gate(titulo, art.get("resumen", "")):
                rejected_gate += 1
                continue

            score = _compute_score(
                titulo,
                art.get("resumen", ""),
                art.get("pais"),
            )

            # +2 por fuente premium solicitada por el Viceministro
            if art.get("origen_api") == "larepublica_rss":
                score += 2

            # +2 por RCN/Caracol (Fase 32 — fuentes que reportan constantemente
            # sobre el sector; llegan vía Google News RSS con origen_api="google_rss",
            # por eso el bono se detecta por texto de `fuente`, no por origen_api).
            fuente_lower = (art.get("fuente") or "").lower()
            if "rcn" in fuente_lower or "caracol" in fuente_lower:
                score += 2

            # ── BONUS POR FRESCURA (criterio dominante) ──
            # La frescura es el factor más importante tras pasar la puerta.
            fecha_str = art.get("fecha", "")
            if fecha_str and len(fecha_str) >= 10:
                try:
                    fecha_art = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                    dias_antiguedad = (datetime.now().date() - fecha_art).days
                    if dias_antiguedad <= 0:
                        score += 6   # Hoy — prioridad absoluta
                    elif dias_antiguedad == 1:
                        score += 3   # Ayer
                    elif dias_antiguedad == 2:
                        score += 1   # Anteayer
                    elif dias_antiguedad <= 7:
                        score -= 3   # 3-7 días: penalizar
                    else:
                        score -= 6   # Más de 1 semana: penalizar fuerte
                except (ValueError, TypeError):
                    pass

            # ── BONUS POR IMAGEN ──
            # Solo tiebreaker: no afecta frescura
            if art.get("imagen"):
                score += 1

            art["_score"] = score

            # ── DEDUP SEMÁNTICO INTELIGENTE ──
            # Si el título es semánticamente similar a uno ya aceptado,
            # quedarse con el que tenga mayor score final (mejor fuente/imagen/frescura).
            similar_idx = _find_similar_article(titulo, scored)
            if similar_idx is not None:
                existing = scored[similar_idx]
                if score > existing.get("_score", 0):
                    # Reemplazar por la versión con mejor score
                    scored[similar_idx] = art
                    duplicates += 1
                else:
                    duplicates += 1
                continue

            scored.append(art)

        # Filtrar score < 1 (requiere al menos alguna relevancia)
        scored = [a for a in scored if a["_score"] >= 1]

        # Ordenar por score desc, luego bonus_imagen, luego fecha desc
        # Artículos con imagen reciben banda preferencial por empate de score
        scored.sort(
            key=lambda x: (x["_score"], 1 if x.get("imagen") else 0, x.get("fecha", "")),
            reverse=True,
        )

        if rejected_gate:
            logger.info(
                f"[NEWS_SERVICE] Puerta de relevancia descartó "
                f"{rejected_gate} artículos sin vocabulario energético"
            )
        if duplicates:
            logger.info(
                f"[NEWS_SERVICE] Deduplicación semántica descartó/reemplazó "
                f"{duplicates} artículos duplicados"
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
                "source_url": art.get("source_url", ""),
                "fecha_publicacion": art.get("fecha", ""),
                "origen_api": art.get("origen_api", ""),
                "_score": art.get("_score", 0),
                "imagen": art.get("imagen", ""),
            }

        top = [_fmt(a) for a in ranked[:max_top]]
        otras = [_fmt(a) for a in ranked[max_top:max_top + max_extra]]

        # Fase 32: texto completo (scraping) solo para `top` — son los
        # únicos realmente mostrados/usados; `otras` queda en titular+resumen
        # para acotar costo/latencia. Se cachea junto con el resto (8h), así
        # que el scraping real ocurre como máximo una vez cada 8 horas, nunca
        # por request de usuario.
        if top:
            textos = await asyncio.gather(
                *[extraer_texto_completo(n["url"]) for n in top],
                return_exceptions=False,
            )
            for n, texto in zip(top, textos):
                n["contenido_completo"] = texto

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

    async def get_hydrocarbon_news(
        self,
        max_items: int = 3,
    ) -> Dict:
        """
        Obtiene noticias específicas de hidrocarburos usando
        queries dedicadas a GNews + las demás fuentes.
        Cache separado del de noticias generales.
        """
        cache_key = "hydrocarbon_news"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return {
                "noticias": cached["noticias"][:max_items],
                "total": min(len(cached["noticias"]), max_items),
            }

        all_normalized: List[dict] = []

        # ── GNews con queries de hidrocarburos ──
        for query in HYDROCARBON_QUERIES:
            try:
                raw = await self.gnews_client.fetch_raw_news(
                    query=query, country="co", lang="es", max_results=10
                )
                from infrastructure.news.news_client import DEFAULT_QUERY
                for art in raw:
                    all_normalized.append(_normalize_gnews(art))
                logger.info(
                    f"[HYDRO_NEWS] GNews query '{query[:30]}...' "
                    f"aportó {len(raw)} artículos"
                )
                if len(raw) >= 10:
                    break  # Ya tenemos suficientes candidatos
            except Exception as e:
                logger.warning(f"[HYDRO_NEWS] Error GNews query '{query[:30]}': {e}")

        # ── Mediastack ──
        if self.mediastack_client.is_available:
            try:
                ms_raw = await self.mediastack_client.fetch_energy_news(limit=20)
                for art in ms_raw:
                    all_normalized.append(_normalize_mediastack(art))
                logger.info(
                    f"[HYDRO_NEWS] Mediastack aportó {len(ms_raw)} artículos"
                )
            except Exception as e:
                logger.warning(f"[HYDRO_NEWS] Error Mediastack: {e}")

        # ── Google News RSS ──
        try:
            grss_raw = await fetch_google_news_rss(max_per_query=10)
            for art in grss_raw:
                all_normalized.append(_normalize_google_rss(art))
            logger.info(
                f"[HYDRO_NEWS] Google RSS aportó {len(grss_raw)} artículos"
            )
        except Exception as e:
            logger.warning(f"[HYDRO_NEWS] Error Google RSS: {e}")

        # ── La República RSS ──
        try:
            lr_raw = await fetch_larepublica_rss()
            for art in lr_raw:
                all_normalized.append(art)
            logger.info(
                f"[HYDRO_NEWS] La República RSS aportó {len(lr_raw)} artículos"
            )
        except Exception as e:
            logger.warning(f"[HYDRO_NEWS] Error La República RSS: {e}")

        if not all_normalized:
            return {"noticias": [], "total": 0}

        # Filtrar por niveles: tier 1 (petróleo/gas genuino) siempre tiene
        # prioridad; tier 2 (minería) solo rellena si tier 1 no alcanza
        # max_items — nunca debe desplazar a una noticia de tier 1.
        before = len(all_normalized)
        tier1 = filter_tier1(all_normalized)
        ranked_tier1 = self._score_and_rank(tier1)

        if len(ranked_tier1) >= max_items:
            ranked = ranked_tier1
        else:
            tier2 = filter_tier2_fill(all_normalized, already_included=tier1)
            ranked_tier2 = self._score_and_rank(tier2)
            ranked = ranked_tier1 + ranked_tier2

        logger.info(
            f"[HYDRO_NEWS] Filtro: {len(ranked_tier1)} tier1 + "
            f"{max(0, len(ranked) - len(ranked_tier1))} tier2 relleno, "
            f"de {before} artículos totales"
        )

        if not ranked:
            return {"noticias": [], "total": 0}

        def _fmt(art: dict) -> dict:
            return {
                "titulo": art["titulo"],
                "resumen": _clean_text(art.get("resumen", ""), 180),
                "url": art.get("url", ""),
                "fuente": art.get("fuente", ""),
                "source_url": art.get("source_url", ""),
                "fecha_publicacion": art.get("fecha", ""),
                "_score": art.get("_score", 0),
                "imagen": art.get("imagen", ""),
            }

        noticias = [_fmt(a) for a in ranked[:max_items]]

        # Fase 32: texto completo (scraping), mismo criterio que
        # get_enriched_news() — solo los items realmente devueltos,
        # cacheados junto con el resto (scraping real como máximo cada 8h).
        if noticias:
            textos = await asyncio.gather(
                *[extraer_texto_completo(n["url"]) for n in noticias],
                return_exceptions=False,
            )
            for n, texto in zip(noticias, textos):
                n["contenido_completo"] = texto

        result = {
            "noticias": noticias,
            "total": len(noticias),
        }

        self._set_cache(cache_key, result)
        logger.info(
            f"[HYDRO_NEWS] {len(noticias)} noticias de hidrocarburos "
            f"(total analizadas: {len(all_normalized)})"
        )
        return result

