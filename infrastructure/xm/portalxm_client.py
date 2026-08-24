"""
Cliente del explorador público de archivos de XM (Fase 33).

Encontrado por inspección de red (no es una API documentada por XM):
la página https://www.xm.com.co/operación/planeación/... usa un widget
JS que consulta `api-portalxm.xm.com.co` para listar y descargar los
archivos del mismo árbol que XM expone también por FTPS
(`/INFORMACION_XM/PUBLICO/...`, según el propio texto de esas páginas).

Sin autenticación, verificado con descargas reales. Advertencia: al no
ser un contrato público documentado, XM podría cambiar este mecanismo
sin aviso — mismo nivel de riesgo que cualquier scraping de un sitio de
terceros, aplicado aquí a un API en vez de HTML.

Nunca lanza excepción — un fallo (API caída, ruta inexistente, timeout)
degrada con gracia a None/lista vacía.
"""

from typing import Any, Dict, List, Optional

import httpx

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api-portalxm.xm.com.co/administracion-archivos"
_CONTENEDOR = "storageportalxm"
_USER_AGENT = "Mozilla/5.0 (compatible; PortalMME/1.0; +https://portalviceministerioenergia.minenergia.gov.co)"

# idTipoContenido observado en vivo: 1=texto plano, 2=carpeta, 4=PDF, 8=zip, 18=xlsm.
TIPO_CARPETA = 2
TIPO_PDF = 4


async def listar_ficheros(
    ruta: str, timeout: float = 15.0, pagina: int = 1, resultados_por_pagina: int = 100
) -> List[Dict[str, Any]]:
    """Lista el contenido (carpetas/archivos) de una ruta del repositorio público de XM.
    Una sola página — para carpetas con más de `resultados_por_pagina` items, usar
    `listar_todos_ficheros()`."""
    params = {
        "ruta": ruta,
        "contenedor": _CONTENEDOR,
        "ordenarPor": "nombre",
        "orden": "ASC",
        "pagina": pagina,
        "resultadosPorPagina": resultados_por_pagina,
        "nombre": "",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(f"{_BASE_URL}/ficheros", params=params)
            resp.raise_for_status()
            return resp.json().get("ficheros", [])
    except Exception as e:
        logger.warning(f"[PORTALXM] Error listando '{ruta[:100]}': {e}")
        return []


async def listar_todos_ficheros(
    ruta: str, timeout: float = 15.0, max_paginas: int = 20
) -> List[Dict[str, Any]]:
    """Pagina `listar_ficheros()` hasta agotar resultados — necesario para
    carpetas planas con cientos de archivos (ej. BoletinEnergetico, 356 PDFs
    en un solo nivel, sin subcarpetas por año) donde una sola página de 100
    se queda corta. `max_paginas` es un límite defensivo (2000 archivos),
    mismo espíritu que MAX_PROFUNDIDAD_PLANEACION_XM en el indexador."""
    todos: List[Dict[str, Any]] = []
    pagina = 1
    while pagina <= max_paginas:
        items = await listar_ficheros(ruta, timeout=timeout, pagina=pagina)
        if not items:
            break
        todos.extend(items)
        pagina += 1
    return todos


async def descargar_fichero(ruta: str, timeout: float = 30.0) -> Optional[bytes]:
    """Descarga el contenido crudo de un archivo por su ruta absoluta."""
    params = {"ruta": ruta, "nombreBlobContainer": _CONTENEDOR}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(f"{_BASE_URL}/ficheros/descarga-archivo", params=params)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"[PORTALXM] Error descargando '{ruta[:100]}': {e}")
        return None
