"""
Cliente del Gestor Normativo Alejandría 2.0 de la CREG (Fase 37).

Encontrado por inspección del HTML/JS servido por gestornormativo.creg.gov.co
(operado por Avance Jurídico Casa Editorial S.A.S. para la CREG) — igual que
el portal público de XM (portalxm_client.py), no es una API documentada, pero
resultó ser contenido 100% estático servido vía XHR, sin autenticación:

- Listado por año: `<tipo>_por_orden_cronologico_<año>.html` (tipo=
  'resoluciones' | 'circulares'), un fragmento HTML con todos los documentos
  de ese año (número, título/resumen, enlace al documento completo).
- Documento completo: la URL indicada en cada entrada del listado
  (ej. `docs/resolucion_creg_0209_2020.htm`), con el texto legal completo
  dentro de un `<div class="panel-documento">`.

Verificado en vivo (2026-08-19/20): funciona igual para resoluciones y
circulares, con datos reales desde 2020 hasta 2026 (78-206 documentos/año).
El panel "MODIFICACIONES" del visor NO tiene datos poblados en esta
plataforma (confirmado leyendo docFunction_v2.js — es el único de los 7
botones del visor sin `sufijoFileToLoad`/fetch asociado) — no sirve como
mecanismo de "qué modificó a este documento"; ver
scripts/ontologia/vigilancia_normativa_creg.py para el enfoque alternativo
(buscar texto de derogación/modificación en los documentos nuevos).

Nunca lanza excepción — un fallo (portal caído, ruta inexistente, timeout)
degrada con gracia a None/lista vacía, mismo criterio que portalxm_client.py.

Ampliación (2026-08-20): la misma plataforma Alejandría, mismo dominio, aloja
también la normativa de la UPME y del Ministerio de Minas y Energía (MME) —
confirmado en vivo (mismo `div.panel-documento`, mismas clases CSS
`opcion-nueva`/`id-documento`/`descripcion-documento` que las páginas por año
de la CREG). Diferencia real: en vez de una página POR AÑO
(`resoluciones_por_orden_cronologico_<año>.html`), UPME y MME tienen UNA
SOLA página con TODOS los años (2000-2026) ya en el HTML servido (no
requiere JS, confirmado con curl plano) — ver `listar_documentos_entidad()`.
"""

import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://gestornormativo.creg.gov.co/gestor/entorno"
_USER_AGENT = "Mozilla/5.0 (compatible; PortalMME/1.0; +https://portalviceministerioenergia.minenergia.gov.co)"

TipoDocumento = str  # 'resoluciones' | 'circulares'

# Slugs verificados en vivo (2026-08-20) de las páginas de compilación por
# entidad — cada una sirve TODOS los años en una sola página.
ENTIDAD_UPME = "unidad_planeacion_minero_energetica_upme"
ENTIDAD_MME = "ministerio_minas_energia_mme"

# Slug SIN el sufijo "_mme" — verificado en vivo (2026-08-21) que la página
# de Conceptos del Ministerio usa un slug distinto al de resoluciones/
# circulares ("compilacion_conceptos_ministerio_minas_energia.html", no
# "..._mme.html") — inconsistencia real de la plataforma, no un error de
# tipeo nuestro. UPME no tiene página de Conceptos en esta plataforma
# (confirmado 404 con y sin sufijo "_upme").
ENTIDAD_MME_CONCEPTOS = "ministerio_minas_energia"

_RE_ANIO_NUMERO = re.compile(r"\bde\s+(\d{4})\b")


async def listar_documentos_anio(
    tipo: TipoDocumento, anio: int, timeout: float = 20.0
) -> List[Dict[str, Any]]:
    """Lista los documentos (resoluciones o circulares) de un año dado.

    Retorna una lista de {numero, titulo, resumen, url_relativa}, donde
    `url_relativa` es la ruta (ej. 'docs/resolucion_creg_0209_2020.htm')
    lista para pasar a `descargar_texto_documento()`.
    """
    url = f"{_BASE_URL}/{tipo}_por_orden_cronologico_{anio}.html"
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.content.decode("iso-8859-1", errors="replace")
    except Exception as e:
        logger.warning(f"[CREG] Error listando {tipo} {anio}: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    documentos: List[Dict[str, Any]] = []
    for opcion in soup.find_all("div", class_="opcion-nueva"):
        enlace = opcion.find("a", href=True)
        id_div = opcion.find("div", class_="id-documento")
        desc_div = opcion.find("div", class_="descripcion-documento")
        if not enlace or not id_div:
            continue
        numero_texto = id_div.get_text(strip=True)
        documentos.append({
            "numero": numero_texto,
            "titulo": numero_texto,
            "resumen": desc_div.get_text(strip=True) if desc_div else "",
            "url_relativa": enlace["href"],
        })
    return documentos


async def listar_documentos_entidad(
    entidad: str, tipo: TipoDocumento, timeout: float = 30.0
) -> List[Dict[str, Any]]:
    """Lista TODOS los documentos (todos los años, 2000-2026) de una entidad
    cuya página de compilación es única (UPME/MME) en vez de por año (CREG).

    Retorna una lista de {numero, titulo, resumen, url_relativa, anio}, mismo
    shape que `listar_documentos_anio()` más el campo `anio` (extraído del
    texto "Resolución 443 de 2026 UPME" vía regex, ya que aquí no viene
    implícito en la URL de listado como sí ocurre con la página por año de
    la CREG) — para poder filtrar por ventana de retención igual que el
    resto del pipeline.
    """
    url = f"{_BASE_URL}/compilacion_{tipo}_{entidad}.html"
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.content.decode("iso-8859-1", errors="replace")
    except Exception as e:
        logger.warning(f"[CREG] Error listando {tipo} de '{entidad}': {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    documentos: List[Dict[str, Any]] = []
    for opcion in soup.find_all("div", class_="opcion-nueva"):
        enlace = opcion.find("a", href=True)
        id_div = opcion.find("div", class_="id-documento")
        desc_div = opcion.find("div", class_="descripcion-documento")
        if not enlace or not id_div:
            continue
        numero_texto = id_div.get_text(strip=True)
        m_anio = _RE_ANIO_NUMERO.search(numero_texto)
        if not m_anio:
            continue
        documentos.append({
            "numero": numero_texto,
            "titulo": numero_texto,
            "resumen": desc_div.get_text(strip=True) if desc_div else "",
            "url_relativa": enlace["href"],
            "anio": int(m_anio.group(1)),
        })
    return documentos


async def descargar_texto_documento(url_relativa: str, timeout: float = 20.0) -> Optional[str]:
    """Descarga un documento (resolución/circular) y extrae su texto legal
    completo desde el contenedor `panel-documento` del visor — descarta menú,
    navegación y botones, que no aportan al RAG."""
    url = f"{_BASE_URL}/{url_relativa}"
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.content.decode("iso-8859-1", errors="replace")
    except Exception as e:
        logger.warning(f"[CREG] Error descargando '{url_relativa}': {e}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    panel = soup.find("div", class_="panel-documento")
    if panel is None:
        return None
    texto = panel.get_text(separator="\n")
    texto = re.sub(r"\n{2,}", "\n\n", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto.strip()
