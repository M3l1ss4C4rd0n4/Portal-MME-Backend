"""Informe Semanal de Dirección de Energía — orquestación.

Encadena: recolectar → comparar contra la foto del viernes anterior → guardar
la foto de hoy → renderizar HTML interactivo, PDF y JSON.

Este módulo NO envía nada, y es deliberado: el envío vive en
`tasks/informe_de_tasks.py`, en su propia tarea. Lo que dispara correos y
Telegram de verdad tiene que verse en un solo sitio, no quedar escondido dentro
de una función que se llama "generar".
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from domain.services import informe_de_json
from domain.services.informe_de_modelo import Informe
from domain.services.informe_de_recoleccion import recolectar_secciones
from domain.services.informe_de_render import render
from domain.services.informe_de_snapshot import (
    aplicar_deltas,
    guardar_snapshot,
    leer_snapshot_anterior,
)

logger = logging.getLogger(__name__)

DIRECTORIO = Path(__file__).resolve().parents[2] / "data" / "informes_direccion_energia"
PREFIJO = "Informe_Direccion_Energia"

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(d: date) -> str:
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]} de {d.year}"


def ruta_html(fecha: date) -> Path:
    return DIRECTORIO / f"{PREFIJO}_{fecha.isoformat()}.html"


def ruta_pdf(fecha: date) -> Path:
    return DIRECTORIO / f"{PREFIJO}_{fecha.isoformat()}.pdf"


def ruta_json(fecha: date) -> Path:
    """Los mismos números del PDF, para que la tarea de envío arme el correo."""
    return DIRECTORIO / f"{PREFIJO}_{fecha.isoformat()}.json"


def _a_pdf(html: str) -> bytes:
    """Reutiliza el mismo motor que ya imprime los informes por tablero."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


async def construir_informe(fecha: date | None = None) -> Informe:
    """Recolecta, compara y guarda la foto. Devuelve el informe ya con deltas."""
    fecha = fecha or date.today()

    secciones = await recolectar_secciones()
    anterior, valores = leer_snapshot_anterior(fecha)
    secciones = aplicar_deltas(secciones, fecha, anterior, valores)

    # La foto se guarda DESPUÉS de calcular los deltas: si se guardara antes,
    # leer_snapshot_anterior podría devolver la de hoy y todos los deltas
    # saldrían en cero en una segunda corrida del mismo día.
    guardar_snapshot(fecha, secciones)

    caidas = [s.clave for s in secciones if s.error]
    if caidas:
        logger.warning("[INFORME DE] Secciones sin datos: %s", ", ".join(caidas))

    return Informe(
        fecha=fecha_larga(fecha),
        generado_en=datetime.now().strftime("%d/%m/%Y %H:%M"),
        secciones=secciones,
    )


async def generar_y_guardar(fecha: date | None = None) -> dict:
    """Genera los artefactos de la semana y los deja en disco."""
    _, resultado = await construir_y_publicar(fecha)
    return resultado


async def construir_y_publicar(fecha: date | None = None) -> tuple[Informe, dict]:
    """Igual que `generar_y_guardar`, pero devuelve también el informe en memoria.

    La tarea de envío necesita el objeto, no solo las rutas; el valor de retorno
    de una tarea Celery tiene que ser serializable a JSON y un `Informe` no lo es.
    """
    fecha = fecha or date.today()
    informe = await construir_informe(fecha)

    DIRECTORIO.mkdir(parents=True, exist_ok=True)

    html_interactivo = render(informe, interactivo=True)
    destino_html = ruta_html(fecha)
    destino_html.write_text(html_interactivo, encoding="utf-8")

    destino_json = ruta_json(fecha)
    informe_de_json.escribir(destino_json, informe)

    resultado = {
        "fecha": fecha.isoformat(),
        "html": str(destino_html),
        "json": str(destino_json),
        "pdf": None,
        "secciones": len(informe.secciones_ok),
        "secciones_caidas": [s.clave for s in informe.fallidas],
        "indicadores": sum(len(s.kpis) for s in informe.secciones_ok),
    }

    # Un fallo al imprimir el PDF no puede tumbar el HTML, que ya está en disco.
    try:
        pdf = _a_pdf(render(informe, interactivo=False))
        destino_pdf = ruta_pdf(fecha)
        destino_pdf.write_bytes(pdf)
        resultado["pdf"] = str(destino_pdf)
        resultado["pdf_bytes"] = len(pdf)
    except Exception as exc:  # noqa: BLE001
        logger.error("[INFORME DE] No se pudo generar el PDF: %s", exc, exc_info=True)
        resultado["error_pdf"] = f"{type(exc).__name__}: {exc}"

    logger.info(
        "[INFORME DE] %s · %d secciones · %d indicadores · pdf=%s",
        fecha, resultado["secciones"], resultado["indicadores"], bool(resultado["pdf"]),
    )
    return informe, resultado


def leer_informe_guardado(fecha: date) -> Informe | None:
    """El informe que quedó en disco, o None si ese viernes no se generó."""
    ruta = ruta_json(fecha)
    if not ruta.is_file():
        return None
    return informe_de_json.leer(ruta)


def ultimo_disponible(extension: str = "html") -> Path | None:
    """El informe más reciente en disco. Sirve de respaldo si hoy aún no corrió."""
    if not DIRECTORIO.is_dir():
        return None
    archivos = sorted(DIRECTORIO.glob(f"{PREFIJO}_*.{extension}"))
    return archivos[-1] if archivos else None
