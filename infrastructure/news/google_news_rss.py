"""
Cliente Google News RSS — noticias del sector energético colombiano.

Ventajas:
- GRATIS, sin API key.
- Sin límite de peticiones.
- Artículos frescos (minutos, no días).
- Múltiples queries para diversificar cobertura.

Se consultan varios feeds RSS con queries especializadas
en el sector energético / minero de Colombia.
"""

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

# Queries RSS especializadas para el sector energético colombiano
RSS_QUERIES = [
    # Sector eléctrico
    "energía eléctrica Colombia",
    "sector energético Colombia embalses",
    "generación eléctrica Colombia renovables",
    # Gas / hidrocarburos
    "gas natural Colombia petróleo minería",
    # Institucional
    "Ministerio Minas Energía Colombia CREG XM",
    # Tarifas / usuario
    "tarifas energía Colombia racionamiento",
]

_BASE_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=es-419&gl=CO&ceid=CO:es-419"
)


def _clean_gnews_title(title: str) -> str:
    """Elimina el ' - Fuente' al final del título de Google News."""
    # Google News agrega " - El Tiempo" al final
    parts = title.rsplit(" - ", 1)
    return parts[0].strip() if len(parts) == 2 else title.strip()


async def fetch_google_news_rss(
    queries: List[str] | None = None,
    max_per_query: int = 15,
    timeout: float = 12.0,
) -> List[Dict]:
    """
    Obtiene noticias frescas de Google News vía RSS.

    Args:
        queries: Lista de queries. Si None usa RSS_QUERIES.
        max_per_query: Máximo artículos por query (Google devuelve ~100).
        timeout: Timeout HTTP en segundos.

    Returns:
        Lista de dicts normalizados:
        {title, description, url, source, publishedAt, country}
    """
    queries = queries or RSS_QUERIES
    all_articles: List[Dict] = []
    seen_titles: set = set()

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Portal Energetico MME)"},
    ) as client:
        for query in queries:
            try:
                encoded_q = httpx.URL(_BASE_URL.format(
                    query=query.replace(" ", "+")
                ))
                resp = await client.get(str(encoded_q))
                resp.raise_for_status()

                root = ElementTree.fromstring(resp.content)
                items = root.findall(".//item")

                count = 0
                for item in items:
                    if count >= max_per_query:
                        break

                    title_el = item.find("title")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")
                    source_el = item.find("source")
                    desc_el = item.find("description")

                    raw_title = title_el.text if title_el is not None else ""
                    if not raw_title:
                        continue

                    # Dedup por título normalizado
                    norm = re.sub(r"\W+", "", raw_title.lower())[:80]
                    if norm in seen_titles:
                        continue
                    seen_titles.add(norm)

                    clean_title = _clean_gnews_title(raw_title)

                    # Parsear fecha
                    pub_date = ""
                    if pub_el is not None and pub_el.text:
                        try:
                            dt = parsedate_to_datetime(pub_el.text)
                            pub_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        except Exception:
                            pub_date = pub_el.text[:25]

                    source_name = ""
                    if source_el is not None and source_el.text:
                        source_name = source_el.text.strip()

                    # Google News description es HTML con enlaces
                    description = ""
                    if desc_el is not None and desc_el.text:
                        # Limpiar HTML
                        description = re.sub(r"<[^>]+>", "", desc_el.text)
                        description = description.strip()[:300]

                    link = ""
                    if link_el is not None and link_el.text:
                        link = link_el.text.strip()

                    all_articles.append({
                        "title": clean_title,
                        "description": description,
                        "url": link,
                        "source": source_name,
                        "publishedAt": pub_date,
                        "country": "co",
                    })
                    count += 1

                logger.debug(
                    f"[GNEWS_RSS] query='{query[:30]}…' → {count} artículos"
                )

            except Exception as e:
                logger.warning(
                    f"[GNEWS_RSS] Error con query '{query[:30]}…': {e}"
                )
                continue

    logger.info(
        f"[GNEWS_RSS] Total artículos obtenidos: {len(all_articles)} "
        f"(de {len(queries)} queries)"
    )
    return all_articles
