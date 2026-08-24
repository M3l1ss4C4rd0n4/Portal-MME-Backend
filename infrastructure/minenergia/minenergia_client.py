"""
Cliente del repositorio de documentos del sitio institucional del Ministerio
de Minas y Energía (minenergia.gov.co) — plataforma Liferay (confirmado:
URLs `/documents/<id>/<archivo>.pdf`, patrón estándar de Document Library
de Liferay).

Distinto de:
- infrastructure/creg/gestor_normativo_client.py::ENTIDAD_MME (normativa del
  Ministerio — resoluciones/circulares, vía la plataforma Alejandría de
  Avance Jurídico, ya indexada).
- infrastructure/upme/upme_wp_client.py (publicaciones de la UPME, entidad
  distinta al Ministerio aunque relacionada).

Este cliente cubre contenido misional propio del sitio del Ministerio —
hallazgo real (2026-08-20): el "Plan de Expansión de Referencia
Generación-Transmisión" (uno de los documentos de planeación más
importantes del sector, define qué proyectos de generación/transmisión se
necesitan a futuro) NO estaba en ningún corpus ya indexado — se encontró
en `/es/misional/energia-electrica-2/planes-expansion/`, con la edición
vigente (`Plan-Expansion-Transmision-2025-2039.pdf`) y ediciones anteriores.

La misma página también lista resoluciones/circulares/procedimientos de
declaratoria de utilidad pública de proyectos específicos (menor relevancia
general, caso a caso) — se excluyen por patrón de nombre de archivo, mismo
principio de curación por relevancia del resto del RAG del proyecto.

Nunca lanza excepción — degrada a lista vacía / None en fallo.
"""

import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://www.minenergia.gov.co"
_USER_AGENT = "Mozilla/5.0 (compatible; PortalMME/1.0; +https://portalviceministerioenergia.minenergia.gov.co)"

_RE_PDF = re.compile(r"^/documents/\d+/.*\.pdf$", re.IGNORECASE)

# Patrones de exclusión — resoluciones/circulares/procedimientos de
# proyectos puntuales y documentos placeholder, sin valor narrativo general.
# "resol" (no "resoluci") a propósito — verificado en vivo que también hay
# que cubrir variantes de nombre de archivo como "Resol_Ejecutiva_132...",
# "res_ejecutiva_348..." y el typo real "Resoluicon-90923..." (todas
# contienen "resol").
_PATRONES_EXCLUIDOS = ("circular", "resol", "pendiente_documento", "procedimiento", "ejecutiva")

# Páginas misionales curadas del sitio del Ministerio con contenido técnico
# real (a diferencia de /es/servicio-al-ciudadano/informes-publicaciones/,
# verificada y descartada: 162 PDFs, casi todos reportes de PQRS/atención al
# ciudadano sin valor de negocio para el RAG).
PAGINAS_MISIONALES = [
    ("MME_PLANES_EXPANSION", "/es/misional/energia-electrica-2/planes-expansion/"),
]


def listar_publicaciones_pagina(ruta: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Lista los PDFs de una página misional del sitio del Ministerio,
    excluyendo patrones administrativos (ver _PATRONES_EXCLUIDOS)."""
    url = f"{_BASE_URL}{ruta}"
    try:
        with httpx.Client(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning(f"[MME_SITIO] Error obteniendo '{ruta}': {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    vistos = set()
    documentos: List[Dict[str, Any]] = []
    for enlace in soup.find_all("a", href=True):
        href = enlace["href"].strip()
        if not _RE_PDF.match(href):
            continue
        href_lower = href.lower()
        if any(p in href_lower for p in _PATRONES_EXCLUIDOS):
            continue
        if href in vistos:
            continue
        vistos.add(href)
        nombre_archivo = href.rsplit("/", 1)[-1]
        documentos.append({"url_pdf": f"{_BASE_URL}{href}", "nombre_archivo": nombre_archivo})
    return documentos


async def descargar_pdf(url_pdf: str, timeout: float = 120.0) -> Optional[bytes]:
    """Descarga el contenido binario de un PDF del repositorio del
    Ministerio. Timeout generoso — mismo criterio que UPME."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = await client.get(url_pdf)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"[MME_SITIO] Error descargando '{url_pdf}': {e}")
        return None
