"""
Cliente de las publicaciones/estudios técnicos de la UPME (www.upme.gov.co).

Distinto de infrastructure/creg/gestor_normativo_client.py::ENTIDAD_UPME (que
cubre la NORMATIVA de la UPME — resoluciones/circulares, vía la plataforma
Alejandría de Avance Jurídico). Este cliente cubre el OTRO tipo de contenido
que publica la UPME en su propio sitio: informes/estudios técnicos (Plan
Energético Nacional, Boletín Estadístico, estudios sectoriales, etc.).

Investigado en vivo (2026-08-20): el sitio corre en WordPress y expone la
API REST estándar `/wp-json/wp/v2/media` (716 PDFs catalogados, sin auth) —
pero buscar por nombre de familia de informe ("Plan de Expansion", "PROURE")
no encuentra los PDFs vigentes (sus nombres de archivo reales no siempre
coinciden con el nombre oficial del informe, ej. la edición 2025 del Plan
Energético Nacional está en una ruta que no calza con ningún término de
búsqueda obvio). La fuente más confiable resultó ser la propia página de
inicio del sitio (www.upme.gov.co) — la UPME la usa para destacar sus
publicaciones vigentes, así que se autoactualiza sin mantenimiento nuestro.

Estrategia: listar los PDFs enlazados desde páginas curadas del sitio bajo
docs.upme.gov.co (ver PAGINAS_UPME), excluyendo patrones administrativos/de
trámite ya cubiertos por otras fuentes o sin valor narrativo (Normatividad/,
Circular_, Formato_, Boletin_Convocatorias, Mapa_del_sitio) — mismo
principio de curación por relevancia que el resto del RAG del proyecto,
aplicado aquí como lista de EXCLUSIÓN (más fácil de mantener que adivinar
cada nombre de informe nuevo).

Ampliación (2026-08-20, misma investigación): la portada sola solo capta lo
que UPME destaca HOY (6 documentos) — la página "estudios-y-publicaciones"
tiene un catálogo mucho más rico y estable (27 documentos reales: serie
completa de resúmenes ejecutivos de conflictividad social 1-20, guías
metodológicas, boletines históricos) — se indexan ambas páginas.

Nunca lanza excepción — un fallo degrada a lista vacía / None.
"""

import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; PortalMME/1.0; +https://portalviceministerioenergia.minenergia.gov.co)"

_RE_PDF_DOCS = re.compile(r"^https://docs\.upme\.gov\.co/.*\.pdf$", re.IGNORECASE)

# Patrones de exclusión — trámites/formularios/normativa (ya cubierta por
# gestor_normativo_client.py) sin valor narrativo para el RAG.
_PATRONES_EXCLUIDOS = (
    "/normatividad/", "circular_", "formato_", "boletin_convocatorias",
    "mapa_del_sitio",
)

# Páginas curadas de www.upme.gov.co con contenido real (ver docstring
# arriba) — verificado en vivo (2026-08-20) que "estudios-y-publicaciones"
# tiene un catálogo mucho más rico (27 documentos reales: resúmenes
# ejecutivos de conflictividad social, guías metodológicas, boletines
# históricos) que la portada sola (6 documentos, los que UPME destaca hoy)
# — se mantienen ambas, se complementan.
PAGINAS_UPME = [
    "https://www.upme.gov.co/",
    "https://www.upme.gov.co/home/estudios-y-publicaciones/",
]


def listar_publicaciones_pagina(url_pagina: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Lista los PDFs de estudios/informes técnicos enlazados desde una
    página curada de www.upme.gov.co (excluyendo trámites/normativa/
    formularios — ver _PATRONES_EXCLUIDOS).

    Retorna una lista de {url_pdf, nombre_archivo} — sin metadata de fecha
    (las páginas no la exponen consistentemente por enlace), la
    deduplicación por hash de contenido del pipeline ya existente cubre la
    idempotencia (incluida la que aparece en más de una página curada).
    """
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = client.get(url_pagina)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning(f"[UPME_PUBLICACIONES] Error obteniendo '{url_pagina}': {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    vistos = set()
    documentos: List[Dict[str, Any]] = []
    for enlace in soup.find_all("a", href=True):
        url_pdf = enlace["href"].strip()
        if not _RE_PDF_DOCS.match(url_pdf):
            continue
        url_lower = url_pdf.lower()
        if any(patron in url_lower for patron in _PATRONES_EXCLUIDOS):
            continue
        if url_pdf in vistos:
            continue
        vistos.add(url_pdf)
        nombre_archivo = url_pdf.rsplit("/", 1)[-1]
        documentos.append({"url_pdf": url_pdf, "nombre_archivo": nombre_archivo})
    return documentos


async def descargar_pdf(url_pdf: str, timeout: float = 120.0) -> Optional[bytes]:
    """Descarga el contenido binario de un PDF de docs.upme.gov.co. Timeout
    generoso (algunos informes, ej. el Plan Energético Nacional, superan
    los 90MB)."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = await client.get(url_pdf)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"[UPME_PUBLICACIONES] Error descargando '{url_pdf}': {e}")
        return None
