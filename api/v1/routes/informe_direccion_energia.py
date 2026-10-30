"""Informe Semanal de Dirección de Energía.

GET /v1/informe-direccion-energia            → HTML interactivo
GET /v1/informe-direccion-energia?formato=pdf → PDF
GET /v1/informe-direccion-energia/estado      → metadatos (JSON)

Sirve el artefacto que deja la tarea del viernes a las 7:00. Entre semana no
hay informe del día: se devuelve el del viernes más reciente y se dice en una
cabecera, en vez de fallar. Un informe de la semana pasada es útil; un 404 no.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from domain.services import informe_de_service as servicio

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_SIN_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


def _resolver(extension: str) -> tuple[bytes | None, date | None, bool]:
    """Devuelve (contenido, fecha del archivo, es_de_hoy)."""
    hoy = date.today()
    ruta_hoy = servicio.ruta_html(hoy) if extension == "html" else servicio.ruta_pdf(hoy)
    if ruta_hoy.is_file():
        return ruta_hoy.read_bytes(), hoy, True

    respaldo = servicio.ultimo_disponible(extension)
    if respaldo is None:
        return None, None, False
    try:
        fecha = date.fromisoformat(respaldo.stem.rsplit("_", 1)[-1])
    except ValueError:
        fecha = None
    return respaldo.read_bytes(), fecha, False


@router.get("", summary="Informe Semanal de Dirección de Energía (HTML o PDF)")
@limiter.limit("30/minute")
async def obtener_informe(
    request: Request,
    formato: str = Query("html", pattern="^(html|pdf)$"),
    api_key: str = Depends(get_api_key),
):
    contenido, fecha, es_de_hoy = _resolver(formato)

    if contenido is None:
        # Nunca se ha generado: se genera al vuelo una sola vez.
        logger.info("[INFORME DE] Sin artefacto en disco, generando bajo demanda")
        try:
            await servicio.generar_y_guardar()
        except Exception as exc:  # noqa: BLE001
            logger.error("[INFORME DE] Generación bajo demanda falló: %s", exc, exc_info=True)
            raise HTTPException(status_code=503, detail="El informe aún no está disponible")
        contenido, fecha, es_de_hoy = _resolver(formato)
        if contenido is None:
            raise HTTPException(status_code=503, detail="El informe aún no está disponible")

    cabeceras = {
        **_SIN_CACHE,
        "X-Informe-Fecha": fecha.isoformat() if fecha else "desconocida",
        "X-Informe-Es-De-Hoy": "true" if es_de_hoy else "false",
    }

    if formato == "pdf":
        nombre = f"Informe_Direccion_Energia_{fecha or 'reciente'}.pdf"
        return Response(
            content=contenido,
            media_type="application/pdf",
            headers={**cabeceras, "Content-Disposition": f'inline; filename="{nombre}"'},
        )

    return HTMLResponse(content=contenido.decode("utf-8"), headers=cabeceras)


@router.get("/estado", summary="Metadatos del informe disponible")
@limiter.limit("60/minute")
async def estado_informe(request: Request, api_key: str = Depends(get_api_key)):
    hoy = date.today()
    html = servicio.ruta_html(hoy)
    pdf = servicio.ruta_pdf(hoy)
    respaldo = servicio.ultimo_disponible("html")

    def _modificado(ruta):
        return (
            datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds")
            if ruta.is_file() else None
        )

    return JSONResponse(
        {
            "fecha": hoy.isoformat(),
            "hayInformeDeHoy": html.is_file(),
            "html": _modificado(html),
            "pdf": _modificado(pdf),
            "ultimoDisponible": respaldo.stem.rsplit("_", 1)[-1] if respaldo else None,
            "tableros": 10,
            "secciones": 5,
        },
        headers=_SIN_CACHE,
    )
