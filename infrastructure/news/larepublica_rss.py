"""
Cliente RSS de La República — sección Economía y Empresas.

Alimenta el NewsService con noticias del sector energético
directamente desde la revista económica que sigue el Viceministro.

Feeds usados:
    https://www.larepublica.co/rss/economia  (60 artículos)
    https://www.larepublica.co/rss/empresas  (60 artículos)

Sin API key. Sin límite de peticiones.
"""

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

_FEEDS = [
    "https://www.larepublica.co/rss/economia",
    "https://www.larepublica.co/rss/empresas",
]


def _parse_date(rfc2822: str) -> str:
    """Convierte fecha RFC-2822 a YYYY-MM-DD."""
    if not rfc2822:
        return ""
    try:
        return parsedate_to_datetime(rfc2822).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _parse_feed(xml_bytes: bytes) -> List[dict]:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as e:
        logger.warning("[LR_RSS] XML inválido: %s", e)
        return []

    items = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        cat_el = item.find("category")

        titulo = (title_el.text or "").strip() if title_el is not None else ""
        url = (link_el.text or "").strip() if link_el is not None else ""
        resumen = (desc_el.text or "").strip() if desc_el is not None else ""
        fecha = _parse_date((pub_el.text or "").strip() if pub_el is not None else "")
        categoria = (cat_el.text or "").strip() if cat_el is not None else ""

        if titulo and url:
            items.append({
                "titulo": titulo,
                "resumen": resumen,
                "url": url,
                "fuente": "La República",
                "source_url": "https://www.larepublica.co",
                "fecha": fecha,
                "categoria": categoria,
                "pais": "co",
                "idioma": "es",
                "origen_api": "larepublica_rss",
                "imagen": "",
            })
    return items


async def fetch_larepublica_rss(
    timeout: float = 12.0,
) -> List[dict]:
    """
    Descarga los feeds RSS de La República (Economía + Empresas)
    y retorna artículos normalizados al formato común del NewsService.
    """
    all_items: List[dict] = []
    seen_urls: set = set()

    async with httpx.AsyncClient(timeout=timeout) as client:
        for feed_url in _FEEDS:
            try:
                resp = await client.get(
                    feed_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; PortalMME/1.0)"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                items = _parse_feed(resp.content)
                new = 0
                for item in items:
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        all_items.append(item)
                        new += 1
                logger.info("[LR_RSS] %s → %d artículos nuevos", feed_url, new)
            except Exception as e:
                logger.warning("[LR_RSS] Error en %s: %s", feed_url, e)

    logger.info("[LR_RSS] Total La República: %d artículos", len(all_items))
    return all_items
