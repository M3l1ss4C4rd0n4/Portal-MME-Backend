"""
Palabras clave para clasificar noticias del sector Hidrocarburos.

Fuente única compartida entre `news_service.get_hydrocarbon_news()` y el
fallback de `libre_noticias_handler._handle_noticias_hidrocarburos()` —
antes existían dos copias idénticas que podían desalinearse con el tiempo.

Dos niveles:
  - HYDROCARBON_TIER1_KEYWORDS: petróleo/gas/combustibles genuinos. Siempre
    tienen prioridad.
  - HYDROCARBON_TIER2_KEYWORDS: minería (carbón, litio, cobre, níquel...).
    Solo se usan para RELLENAR si tier 1 no alcanza el mínimo de noticias
    pedido — nunca deben desplazar a una noticia de tier 1.

El match usa límites de palabra (`\b`), no substring plano: keywords cortas
como "gas" o "cobre" NO deben matchear dentro de nombres propios como
"Promigas" o "Descubre" — ese bug concreto causó que una noticia de fusiones
empresariales (que solo mencionaba "Promigas") se etiquetara como hidrocarburos.
"""

import re

HYDROCARBON_TIER1_KEYWORDS = [
    "petróleo", "petroleo", "gas", "combustible", "gasolina", "acpm",
    "gas natural", "glp", "oleoducto", "gasoducto", "exploración",
    "exploracion", "refinación", "refinacion", "barril", "brent", "wti",
    "opep", "ecopetrol", "reficar", "yacimiento", "pozo petrolero",
    "hidrocarburo", "downstream", "upstream", "midstream",
    "regalías petroleras", "regalias petroleras",
    "diésel", "diesel", "fuel oil", "gas licuado", "gnl", "lng",
    "shale", "fracking", "offshore",
    "crudo", "precio del crudo", "crudo colombiano", "producción petrolera",
    "derivado del petróleo", "derivado del petroleo",
    "petroquímica", "petroquimica", "estación de servicio",
    "gasolinera", "gasocentro", "grifo",
    "anh",
]

HYDROCARBON_TIER2_KEYWORDS = [
    "carbón", "carbon mineral", "minería", "mineria",
    "niquel", "litio", "cobre",
    "drummond", "cerrejón", "cerrejon", "prodeco",
    "exportación de carbón", "puerto de carbón",
]

# Compatibilidad: unión de ambos niveles para código que aún no distingue tiers.
HYDROCARBON_FILTER_KEYWORDS = HYDROCARBON_TIER1_KEYWORDS + HYDROCARBON_TIER2_KEYWORDS


def _article_text(art: dict) -> str:
    return (
        (art.get("titulo") or "").lower() + " " +
        (art.get("resumen") or "").lower()
    )


def _matches_any(text: str, keywords: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords)


def filter_tier1(articles: list[dict]) -> list[dict]:
    """Artículos que mencionan petróleo/gas genuino (tier 1, prioridad)."""
    return [a for a in articles if _matches_any(_article_text(a), HYDROCARBON_TIER1_KEYWORDS)]


def filter_tier2_fill(articles: list[dict], already_included: list[dict]) -> list[dict]:
    """
    Artículos que mencionan minería (tier 2), excluyendo los ya incluidos en
    tier 1 — solo deben usarse para rellenar cuando tier 1 no alcanza.
    """
    excluded_urls = {a.get("url") for a in already_included}
    return [
        a for a in articles
        if a.get("url") not in excluded_urls and _matches_any(_article_text(a), HYDROCARBON_TIER2_KEYWORDS)
    ]
