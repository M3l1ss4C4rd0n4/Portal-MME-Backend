#!/usr/bin/env python3
"""
Cliente XMLA para los cubos OLAP de SICOM (SQL Server Analysis Services).

Sustituye el paso manual que describe el "Informe de Consolidación y Análisis de
Información de Combustibles": en vez de que alguien abra Excel, se conecte al
cubo, arme una tabla dinámica y la pegue como tabla, aquí se consulta el mismo
origen por programa y se obtiene la tabla plana directamente.

Endpoint: https://bi.sicom.gov.co/OLAP/msmdpump.dll  (IIS + msmdpump, SSAS)
Protocolo: XMLA sobre SOAP/HTTP, autenticación básica.

Dos detalles del servidor que condicionan el diseño:

  1. **No envía su certificado intermedio.** El certificado de hoja es legítimo
     (*.sicom.gov.co, emitido por DigiCert a nombre del Ministerio), pero la
     cadena queda incompleta y cualquier cliente la rechaza. Se resuelve
     aportando el intermedio en config/sicom_ca_chain.pem. Nunca con verify=False.
  2. **Responde MDDataSet, no una tabla.** Las celdas vienen separadas de los ejes
     y de forma dispersa; hay que cruzar CellOrdinal contra las tuplas del eje de
     filas para reconstruir cada registro. Eso es lo que hace _iter_mddataset.

Las credenciales viven cifradas en el vault del proyecto (core/secrets.py), nunca
en el código ni en git.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Iterator, Sequence

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger(__name__)

URL_CUBOS_LIQUIDOS = "https://bi.sicom.gov.co/OLAP/msmdpump.dll"
URL_CUBOS_GCV = "https://bi.sicom.gov.co/OLAP_GCV/msmdpump.dll"
CA_BUNDLE = BASE_DIR / "config" / "sicom_ca_chain.pem"

# (connect, read). Un MDX de un año de compras puede tardar varios minutos.
TIMEOUT = (30, 900)

NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "xmla": "urn:schemas-microsoft-com:xml-analysis",
    "rowset": "urn:schemas-microsoft-com:xml-analysis:rowset",
    "mdd": "urn:schemas-microsoft-com:xml-analysis:mddataset",
}


class SicomOlapError(RuntimeError):
    """Error de protocolo o de negocio devuelto por el servidor XMLA."""


def _credenciales() -> tuple[str, str]:
    """Usuario y contraseña desde el vault; repliegue a variables de entorno."""
    usuario = contrasena = None
    try:
        from core.secrets import get_secret

        usuario = get_secret("SICOM_XMLA_USER")
        contrasena = get_secret("SICOM_XMLA_PASSWORD")
    except Exception as exc:  # vault no disponible (p. ej. entorno de desarrollo)
        logger.warning("No se pudo leer el vault (%s); se intentará con el entorno", exc)

    usuario = usuario or os.getenv("SICOM_XMLA_USER")
    contrasena = contrasena or os.getenv("SICOM_XMLA_PASSWORD")

    if not usuario or not contrasena:
        raise SicomOlapError(
            "Faltan credenciales de SICOM. Guárdalas con:\n"
            "  from core.secrets import set_secret\n"
            "  set_secret('SICOM_XMLA_USER', ...); set_secret('SICOM_XMLA_PASSWORD', ...)"
        )
    return usuario, contrasena


def _sesion() -> requests.Session:
    """Sesión con reintentos — mismo patrón que infrastructure/external/pdo_service.py.

    Se permite reintentar POST porque en XMLA tanto Discover como Execute son
    operaciones de lectura: repetirlas no tiene efectos secundarios.
    """
    sesion = requests.Session()
    retry = Retry(
        total=3,
        read=0,          # una consulta que ya llegó al servidor NO se repite: un
                         # MDX de un año tarda ~1 min y reintentarlo cuadruplica
                         # el tiempo con la transacción abierta
        backoff_factor=2,
        status_forcelist=[429, 502, 503, 504],   # 500 NO: msmdpump devuelve los
                                                 # SOAP Fault con 500 y hay que
                                                 # leer el mensaje, no reintentar
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=retry)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def _xml_escape(texto: str) -> str:
    return (
        texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


class SicomOlapClient:
    """Cliente XMLA mínimo: Discover y Execute sobre msmdpump.dll."""

    def __init__(self, url: str = URL_CUBOS_LIQUIDOS, ca_bundle: Path | str = CA_BUNDLE):
        if not Path(ca_bundle).exists():
            raise SicomOlapError(
                f"No existe la cadena de CA {ca_bundle}. Es necesaria porque el "
                f"servidor de SICOM no envía su certificado intermedio."
            )
        self.url = url
        self.ca_bundle = str(ca_bundle)
        self._auth = _credenciales()
        self._sesion = _sesion()

    def close(self) -> None:
        """Cierra la sesión HTTP. El cliente también sirve como context manager."""
        self._sesion.close()

    def __enter__(self) -> "SicomOlapClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── transporte ────────────────────────────────────────────────────────────

    def _post(self, cuerpo: str, accion: str, stream: bool = False) -> requests.Response:
        sobre = (
            '<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
            f"<Body>{cuerpo}</Body></Envelope>"
        )
        resp = self._sesion.post(
            self.url,
            data=sobre.encode("utf-8"),
            auth=self._auth,
            verify=self.ca_bundle,
            timeout=TIMEOUT,
            stream=stream,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"urn:schemas-microsoft-com:xml-analysis:{accion}"',
            },
        )
        if resp.status_code == 401:
            resp.close()
            raise SicomOlapError("Credenciales de SICOM rechazadas (401).")
        if resp.status_code >= 400:
            # msmdpump devuelve los errores de MDX como SOAP Fault con HTTP 500.
            # Sin leer el cuerpo, el mensaje real ("columna inexistente", "sintaxis
            # inválida"…) se pierde y solo queda un 500 opaco.
            cuerpo = resp.content
            resp.close()
            detalle = ""
            try:
                raiz = etree.fromstring(cuerpo)
                detalle = " ".join(t.strip() for t in raiz.itertext() if t.strip())
            except Exception:
                detalle = cuerpo[:600].decode("utf-8", "replace")
            raise SicomOlapError(
                f"HTTP {resp.status_code} del servidor XMLA: {detalle[:600]}"
            )
        return resp

    @staticmethod
    def _revisar_fault(raiz: etree._Element) -> None:
        fault = raiz.find(".//soap:Fault", NS)
        if fault is not None:
            detalle = " ".join(t.strip() for t in fault.itertext() if t.strip())
            raise SicomOlapError(f"El servidor XMLA devolvió un fallo: {detalle[:600]}")

    # ── Discover ──────────────────────────────────────────────────────────────

    def discover(
        self,
        request_type: str,
        restricciones: dict[str, str] | None = None,
        propiedades: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """Metadatos del servidor (catálogos, cubos, dimensiones, medidas…)."""
        r = "".join(
            f"<{k}>{_xml_escape(v)}</{k}>" for k, v in (restricciones or {}).items()
        )
        p = "".join(
            f"<{k}>{_xml_escape(v)}</{k}>" for k, v in (propiedades or {}).items()
        )
        cuerpo = (
            '<Discover xmlns="urn:schemas-microsoft-com:xml-analysis">'
            f"<RequestType>{request_type}</RequestType>"
            f"<Restrictions><RestrictionList>{r}</RestrictionList></Restrictions>"
            f"<Properties><PropertyList>{p}</PropertyList></Properties>"
            "</Discover>"
        )
        resp = self._post(cuerpo, "Discover")
        contenido = resp.content
        resp.close()
        raiz = etree.fromstring(contenido)
        self._revisar_fault(raiz)

        filas = []
        for fila in raiz.iter(f"{{{NS['rowset']}}}row"):
            filas.append(
                {etree.QName(c).localname: (c.text or "") for c in fila}
            )
        return filas

    def catalogos(self) -> list[str]:
        return [
            f["CATALOG_NAME"]
            for f in self.discover("DBSCHEMA_CATALOGS")
            if f.get("CATALOG_NAME")
        ]

    # ── Execute (MDX) ─────────────────────────────────────────────────────────

    def execute_mdx(
        self, mdx: str, catalogo: str, columnas: Sequence[str] | None = None
    ) -> Iterator[dict[str, str | None]]:
        """Ejecuta un MDX y entrega las filas ya aplanadas, una a una.

        `columnas` renombra las jerarquías del eje de filas en el orden en que
        aparecen en el MDX. Si no se indica, se usa el nombre de la jerarquía.

        Es un generador a propósito: las bases grandes se escriben directo al
        buffer de COPY sin materializar la tabla completa en memoria.
        """
        cuerpo = (
            '<Execute xmlns="urn:schemas-microsoft-com:xml-analysis">'
            f"<Command><Statement><![CDATA[{mdx}]]></Statement></Command>"
            "<Properties><PropertyList>"
            f"<Catalog>{_xml_escape(catalogo)}</Catalog>"
            "<Format>Multidimensional</Format><Content>Data</Content>"
            "</PropertyList></Properties></Execute>"
        )
        resp = self._post(cuerpo, "Execute", stream=True)
        try:
            resp.raw.decode_content = True
            yield from _iter_mddataset(resp.raw, columnas)
        finally:
            resp.close()


def _iter_mddataset(
    origen, columnas: Sequence[str] | None = None
) -> Iterator[dict[str, str | None]]:
    """Convierte un MDDataSet en filas planas, una por fila lógica.

    Estructura que devuelve SSAS:
      Axes/Axis[@name='Axis0'] → las medidas (columnas)
      Axes/Axis[@name='Axis1'] → una tupla por fila, con un Member por jerarquía
      CellData/Cell[@CellOrdinal] → los valores, **dispersos**: las celdas vacías
        simplemente no vienen.

    Con M medidas en Axis0, la celda de ordinal `o` corresponde a la fila
    `o // M` y a la medida `o % M`. Como el ordinal es fila-mayor, las celdas de
    una misma fila llegan consecutivas: se acumulan y se emite una sola fila con
    todas sus medidas. **Emitir una fila por celda duplicaría cada registro tantas
    veces como medidas tenga la consulta.**

    Las tuplas del eje de filas se mantienen en memoria (son el grueso) y las
    celdas se consumen en streaming. Los captions se internan porque se repiten
    muchísimo (departamentos, productos, códigos DANE).
    """
    mdd = NS["mdd"]
    eje_actual: str | None = None
    medidas: list[str] = []
    filas_eje: list[tuple[str, ...]] = []
    jerarquias: list[str] = []
    nombres: list[str] | None = None
    cache: dict[str, str] = {}

    pendiente_idx: int | None = None
    pendiente: dict[str, str | None] = {}

    contexto = etree.iterparse(
        origen, events=("start", "end"), huge_tree=True, recover=False
    )

    for evento, elem in contexto:
        etiqueta = etree.QName(elem).localname

        if evento == "start":
            if etiqueta == "Axis":
                eje_actual = elem.get("name")
            continue

        # ── eventos de cierre ──
        if etiqueta in ("Fault", "Exception") or (
            etiqueta == "Error" and elem.getparent() is not None
        ):
            detalle = " ".join(t.strip() for t in elem.itertext() if t.strip())
            atributos = " ".join(f"{k}={v}" for k, v in elem.attrib.items())
            raise SicomOlapError(
                f"El servidor XMLA devolvió un error: {atributos} {detalle}"[:600]
            )

        if etiqueta == "Tuple" and elem.tag == f"{{{mdd}}}Tuple":
            miembros = elem.findall(f"{{{mdd}}}Member")
            if eje_actual == "Axis0":
                medidas.append(_nombre_medida(miembros[0]) if miembros else "")
            elif eje_actual == "Axis1":
                if not jerarquias:
                    jerarquias = [m.get("Hierarchy", "") for m in miembros]
                filas_eje.append(
                    tuple(cache.setdefault(c, c) for c in (_caption(m) for m in miembros))
                )
            _liberar(elem)

        elif etiqueta == "Axis":
            eje_actual = None

        elif etiqueta == "Cell" and elem.tag == f"{{{mdd}}}Cell":
            # A partir de aquí los ejes ya están completos.
            if not medidas:
                medidas = ["valor"]
            if not filas_eje:
                # Consulta sin eje de filas (solo medidas): es el caso de la
                # consulta de total general que se usa para conciliar.
                filas_eje = [()]
            if nombres is None:
                nombres = (
                    list(columnas)
                    if columnas
                    else [_nombre_corto(h) for h in jerarquias]
                )

            ordinal_txt = elem.get("CellOrdinal")
            if ordinal_txt is None:
                raise SicomOlapError("Celda sin CellOrdinal: respuesta XMLA inconsistente")
            idx_fila, idx_medida = divmod(int(ordinal_txt), len(medidas))
            if idx_fila >= len(filas_eje):
                raise SicomOlapError(
                    f"CellOrdinal {ordinal_txt} apunta fuera del eje de filas "
                    f"({len(filas_eje)} tuplas): respuesta XMLA inconsistente"
                )

            if pendiente_idx is not None and idx_fila != pendiente_idx:
                yield _componer(filas_eje[pendiente_idx], nombres, pendiente)
                pendiente = {}
            pendiente_idx = idx_fila

            valor_el = elem.find(f"{{{mdd}}}Value")
            pendiente[medidas[idx_medida]] = (
                valor_el.text if valor_el is not None else None
            )
            _liberar(elem)

    if pendiente_idx is not None and nombres is not None:
        yield _componer(filas_eje[pendiente_idx], nombres, pendiente)


def _liberar(elem: etree._Element) -> None:
    """Libera un nodo ya procesado y los hermanos que quedaron detrás.

    `elem.clear()` por sí solo vacía el contenido pero deja el nodo colgando del
    padre: en un documento de cientos de miles de tuplas, el árbol sigue
    creciendo. Hay que borrar también los hermanos previos.
    """
    elem.clear()
    padre = elem.getparent()
    if padre is not None:
        while elem.getprevious() is not None:
            del padre[0]


def _nombre_medida(miembro: etree._Element) -> str:
    """Nombre de una medida a partir de su UName: `[Measures].[VOLUMEN
    COMPRADO]` → `VOLUMEN COMPRADO`.

    Se usa el UName y no el Caption porque el Caption es la etiqueta *visible*:
    si el servidor la devolviera traducida o con otra capitalización, el ETL no
    encontraría la medida y la columna entera quedaría en nulo sin dar error.
    El UName es el identificador del modelo y no cambia.
    """
    uname = miembro.find(f"{{{NS['mdd']}}}UName")
    texto = (uname.text or "") if uname is not None else ""
    if texto.endswith("]") and "[" in texto:
        return texto[texto.rfind("[") + 1 : -1]
    return texto or _caption(miembro)


def _caption(miembro: etree._Element) -> str:
    """Etiqueta visible de un miembro, o cadena vacía si no tiene valor.

    Importante: cuando el atributo es nulo en el origen, SSAS devuelve un
    Caption vacío y un UName técnico del tipo
    `[AGENTE].[OPERADA POR].&[]`. Caer al UName metería ese texto en los datos,
    así que un Caption vacío se trata como ausencia de valor.
    """
    cap = miembro.find(f"{{{NS['mdd']}}}Caption")
    if cap is not None:
        return cap.text or ""
    uname = miembro.find(f"{{{NS['mdd']}}}UName")
    texto = (uname.text or "") if uname is not None else ""
    return "" if texto.endswith(".&[]") else texto


def _nombre_corto(jerarquia: str) -> str:
    """'[AGENTE].[TIPO ESTACION]' → 'TIPO ESTACION'."""
    partes = [p for p in jerarquia.replace("[", "").split("]") if p.strip(". ")]
    return partes[-1].strip(". ") if partes else jerarquia


def _componer(
    valores: tuple[str, ...], nombres: Sequence[str], medidas: dict[str, str | None]
) -> dict[str, str | None]:
    """Una fila: atributos del eje + todas las medidas que tuvieran celda."""
    fila: dict[str, str | None] = {
        nombre: (valores[i] if i < len(valores) else None)
        for i, nombre in enumerate(nombres)
    }
    fila.update(medidas)
    return fila
