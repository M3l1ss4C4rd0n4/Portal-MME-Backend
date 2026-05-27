"""
Endpoints: Informes Ejecutivos PDF

OE5: Generación de informes del sistema eléctrico colombiano en PDF.
Usa report_service.generar_pdf_informe() (WeasyPrint 68.1).

Endpoints:
    GET /v1/reports/daily-pdf?fecha=YYYY-MM-DD          → PDF download
    GET /v1/reports/available-dates                     → fechas disponibles
    GET /v1/reports/boletines-energeticos/latest        → boletín más reciente (SharePoint)
    GET /v1/reports/informes-diarios-xm/paquete         → ZIP 3 informes XM con fallback
    GET /v1/reports/informe-diario-xm/latest            → alias boletines (compatibilidad)
"""

BOLETINES_ENERGETICOS_FOLDER = (
    "https://minenergiacol-my.sharepoint.com/:f:/g/personal/"
    "dmgutierrez_minenergia_gov_co/IgBa3I-9XSaFSbrXfNDFt7pZAdfgSDIrupFx2hIH8hYyHnM"
)

INFORMES_DIARIOS_XM_FOLDER = (
    "https://minenergiacol-my.sharepoint.com/:f:/g/personal/"
    "dmgutierrez_minenergia_gov_co/IgDtJ4pD_cSfTaOYhzHY833bAVLgyP7fJhhCDJmIfgQo-tw"
)

# Tipos de informe diario XM (orden de inclusión en el ZIP)
INFORME_DIARIO_TIPOS: list[tuple[str, str]] = [
    ("SeguimientoDespacho", "Seguimiento de despacho"),
    ("VariablesOperativas", "Variables operativas"),
    ("VariablesHidrologicas", "Variables hidrológicas"),
]

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}

_CATALOG_CACHE: dict = {"ts": 0.0, "data": None}
_CATALOG_TTL_SEC = 300

import asyncio
import io
import logging
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response

from api.dependencies import get_api_key
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger("reports_router")
router = APIRouter()


def _build_context_from_db(fecha: date) -> dict:
    """
    Construye contexto_datos mínimo con datos reales de cu_daily
    para poblar el PDF sin necesitar el orquestador IA.
    """
    cm = PostgreSQLConnectionManager()
    ctx: dict = {}
    try:
        with cm.get_connection() as conn:
            cur = conn.cursor()
            # CU del día solicitado o el más reciente
            cur.execute(
                """
                SELECT fecha, cu_total, componente_g, componente_t,
                       componente_d, componente_c, componente_p,
                       componente_r, demanda_gwh, generacion_gwh,
                       perdidas_pct, confianza
                FROM cu_daily
                WHERE fecha <= %s
                ORDER BY fecha DESC
                LIMIT 1
                """,
                (fecha,),
            )
            row = cur.fetchone()
            if row:
                ctx["cu_actual"] = {
                    "fecha": str(row[0]),
                    "cu_total": float(row[1]) if row[1] else 0.0,
                    "componente_g": float(row[2]) if row[2] else 0.0,
                    "componente_t": float(row[3]) if row[3] else 0.0,
                    "componente_d": float(row[4]) if row[4] else 0.0,
                    "componente_c": float(row[5]) if row[5] else 0.0,
                    "componente_p": float(row[6]) if row[6] else 0.0,
                    "componente_r": float(row[7]) if row[7] else 0.0,
                    "demanda_gwh": float(row[8]) if row[8] else 0.0,
                    "generacion_gwh": float(row[9]) if row[9] else 0.0,
                    "perdidas_pct": float(row[10]) if row[10] else 0.0,
                    "confianza": row[11],
                }
    except Exception as e:
        logger.warning(f"[REPORTS] Error leyendo cu_daily: {e}")
    return ctx


def _build_narrative(ctx: dict, fecha: date) -> str:
    """Genera texto Markdown estructurado desde los datos de BD."""
    cu = ctx.get("cu_actual", {})
    cu_total = cu.get("cu_total", 0.0)
    demanda = cu.get("demanda_gwh", 0.0)
    perdidas = cu.get("perdidas_pct", 0.0)
    confianza = cu.get("confianza", "N/D")

    return f"""# Informe Ejecutivo del Sistema Eléctrico Colombiano

**Fecha:** {fecha.strftime('%d de %B de %Y')}
**Generado por:** ENERTRACE v1.2.0
**Confianza de datos:** {confianza}

## Resumen Ejecutivo

El Costo Unitario de la energía para el período analizado se sitúa en
**{cu_total:.2f} COP/kWh**, con una demanda de {demanda:.1f} GWh y pérdidas
estimadas del {perdidas:.2f}%.

## Descomposición del CU (COP/kWh)

| Componente | Valor |
|---|---|
| Generación (G) | {cu.get('componente_g', 0):.4f} |
| Transmisión (T) | {cu.get('componente_t', 0):.4f} |
| Distribución (D) | {cu.get('componente_d', 0):.4f} |
| Comercialización (C) | {cu.get('componente_c', 0):.4f} |
| Pérdidas (P) | {cu.get('componente_p', 0):.4f} |
| Restricciones (R) | {cu.get('componente_r', 0):.4f} |
| **CU Total** | **{cu_total:.4f}** |

## Variables del Sistema

- **Demanda:** {demanda:.1f} GWh
- **Generación:** {cu.get('generacion_gwh', 0):.1f} GWh
- **Pérdidas estimadas:** {perdidas:.2f}%

## Nota

Informe generado automáticamente. Los datos corresponden al registro
disponible más próximo a la fecha solicitada.

*Fuente: XM Colombia / Portal ENERTRACE. CREG fórmula G+T+D+C+P+R.*
"""


def _generate_pdf_sync(fecha: date) -> bytes:
    """
    Genera el PDF de forma síncrona.
    Obtiene datos de BD, construye narrativa, llama a report_service.
    """
    from domain.services.report_service import generar_pdf_informe

    ctx = _build_context_from_db(fecha)
    informe_texto = _build_narrative(ctx, fecha)

    fecha_str = fecha.strftime("%Y-%m-%d %H:%M")
    pdf_path = generar_pdf_informe(
        informe_texto=informe_texto,
        fecha_generacion=fecha_str,
        generado_con_ia=False,
        contexto_datos=ctx,
    )

    if not pdf_path or not os.path.isfile(pdf_path):
        raise RuntimeError("generar_pdf_informe no produjo archivo válido")

    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()

    # Limpiar archivo temporal
    try:
        os.remove(pdf_path)
    except Exception as e:
        pass

    return pdf_bytes


def _graph_list_all_children(
    headers: dict,
    drive_id: str,
    item_id: str,
) -> list[dict]:
    """Lista todos los hijos de un item, siguiendo paginación de Graph API."""
    import requests

    items: list[dict] = []
    url: str | None = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children"
        f"?$select=id,name,lastModifiedDateTime,file,folder"
    )
    while url:
        resp = requests.get(url, headers=headers, timeout=(15, 30))
        resp.raise_for_status()
        body = resp.json()
        items.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
    return items


def _sp_headers() -> dict:
    """Token + headers para Microsoft Graph."""
    from etl.etl_sharepoint_sync import _get_access_token

    token = _get_access_token()
    return {"Authorization": f"Bearer {token}"}


def _sp_open_folder(share_url: str) -> tuple[dict, str, str]:
    """Abre carpeta SharePoint compartida → (headers, drive_id, root_id)."""
    import requests
    from etl.etl_sharepoint_sync import _encode_sharing_url

    headers = _sp_headers()
    sharing_token = _encode_sharing_url(share_url)
    meta_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem",
        headers=headers,
        timeout=(15, 30),
    )
    if meta_resp.status_code != 200:
        raise RuntimeError(
            f"No se pudo acceder a SharePoint ({meta_resp.status_code})"
        )
    meta = meta_resp.json()
    return headers, meta["parentReference"]["driveId"], meta["id"]


def _sp_download_item(
    headers: dict,
    drive_id: str,
    item: dict,
    read_timeout: int = 600,
) -> bytes:
    """Descarga bytes de un driveItem de SharePoint."""
    import requests

    file_meta = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item['id']}",
        headers=headers,
        timeout=(15, 30),
    )
    file_meta.raise_for_status()
    download_url = file_meta.json().get("@microsoft.graph.downloadUrl")
    if not download_url:
        raise RuntimeError(f"Sin URL de descarga para {item.get('name')}")

    pdf_resp = requests.get(
        download_url,
        headers={"Cache-Control": "no-cache"},
        timeout=(15, read_timeout),
        stream=True,
    )
    pdf_resp.raise_for_status()
    chunks: list[bytes] = []
    for chunk in pdf_resp.iter_content(chunk_size=1024 * 256):
        if chunk:
            chunks.append(chunk)
    return b"".join(chunks)


def _parse_folder_date(name: str) -> date | None:
    """Parsea nombre de carpeta DD_MM_YYYY."""
    parts = name.split("_")
    if len(parts) != 3:
        return None
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        return date(year, month, day)
    except ValueError:
        return None


_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _format_fecha_es(d: date) -> str:
    return f"{d.day} de {_MESES_ES[d.month - 1]} de {d.year}"


def _extraer_preview_pdf(content: bytes) -> tuple[str, str]:
    """Extrae título y descripción breve de la primera página del PDF."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if not pdf.pages:
            return "Informe diario de situación energética", ""
        text = (pdf.pages[0].extract_text() or "").strip()

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return "Informe diario de situación energética", ""

    title = lines[0]
    desc_parts: list[str] = []
    for line in lines[1:]:
        if line == title:
            continue
        lower = line.lower()
        if lower.startswith("comportamiento") or lower.startswith("en la siguiente"):
            break
        desc_parts.append(line)
        if len(" ".join(desc_parts)) > 180:
            break

    description = " ".join(desc_parts).strip()
    if len(description) > 220:
        description = description[:217].rsplit(" ", 1)[0] + "…"
    return title, description


def _index_informes_diarios_folders(
    headers: dict, drive_id: str, root_id: str,
) -> dict[date, dict[str, dict]]:
    """folder_date → {pattern_key: driveItem}."""
    folders: dict[date, dict[str, dict]] = {}
    for item in _graph_list_all_children(headers, drive_id, root_id):
        if "folder" not in item:
            continue
        folder_date = _parse_folder_date(item["name"])
        if folder_date is None:
            continue
        typed: dict[str, dict] = {}
        for f in _graph_list_all_children(headers, drive_id, item["id"]):
            if "file" not in f:
                continue
            for pattern, _label in INFORME_DIARIO_TIPOS:
                if pattern in f["name"]:
                    typed[pattern] = f
                    break
        if typed:
            folders[folder_date] = typed
    return folders


def _resolver_informes_diarios(
    folders: dict[date, dict[str, dict]],
    today: date | None = None,
) -> tuple[dict[str, dict], dict[str, date]]:
    """Resuelve un informe por tipo con fallback al día anterior."""
    if today is None:
        today = datetime.now(ZoneInfo("America/Bogota")).date()

    candidate_dates = sorted(
        [d for d in folders if d <= today],
        reverse=True,
    )
    if not candidate_dates:
        candidate_dates = sorted(folders.keys(), reverse=True)

    resolved: dict[str, dict] = {}
    resolved_from: dict[str, date] = {}
    for pattern, _label in INFORME_DIARIO_TIPOS:
        for folder_date in candidate_dates:
            if pattern in folders[folder_date]:
                resolved[pattern] = folders[folder_date][pattern]
                resolved_from[pattern] = folder_date
                break
        if pattern not in resolved:
            raise RuntimeError(f"Informe no encontrado: {pattern}")

    return resolved, resolved_from


def _preview_fallback(label: str, folder_date: date) -> tuple[str, str]:
    titulo = "Informe diario de situación energética"
    descripcion = (
        f"Informe de seguimiento a las {label.lower()} del "
        f"Sistema Interconectado Nacional (SIN), correspondiente al "
        f"{_format_fecha_es(folder_date)}."
    )
    return titulo, descripcion


def _build_catalog_entry(
    pattern: str,
    label: str,
    folder_date: date,
    item: dict,
    headers: dict,
    drive_id: str,
    today: date,
) -> dict:
    try:
        content = _sp_download_item(headers, drive_id, item, read_timeout=300)
        titulo, descripcion = _extraer_preview_pdf(content)
        if not descripcion:
            _, descripcion = _preview_fallback(label, folder_date)
    except Exception as exc:
        logger.warning("[REPORTS] Preview PDF falló (%s): %s", pattern, exc)
        titulo, descripcion = _preview_fallback(label, folder_date)

    return {
        "tipo": pattern,
        "label": label,
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha": _format_fecha_es(folder_date),
        "fechaIso": folder_date.isoformat(),
        "esDelDia": folder_date == today,
        "filename": item["name"],
        "modificado": item.get("lastModifiedDateTime"),
    }


def _catalogo_informes_diarios_sync() -> list[dict]:
    """Metadatos de los 3 informes diarios (título/descripción desde PDF)."""
    now = time.time()
    if _CATALOG_CACHE["data"] is not None and now - _CATALOG_CACHE["ts"] < _CATALOG_TTL_SEC:
        return _CATALOG_CACHE["data"]

    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
    today = datetime.now(ZoneInfo("America/Bogota")).date()
    folders = _index_informes_diarios_folders(headers, drive_id, root_id)
    if not folders:
        raise RuntimeError("No se encontraron carpetas de informes diarios")

    resolved, resolved_from = _resolver_informes_diarios(folders, today)

    tasks = [
        (pattern, label, resolved_from[pattern], resolved[pattern])
        for pattern, label in INFORME_DIARIO_TIPOS
    ]

    catalogo: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(
                _build_catalog_entry,
                pattern, label, folder_date, item, headers, drive_id, today,
            )
            for pattern, label, folder_date, item in tasks
        ]
        catalogo = [f.result() for f in futures]

    _CATALOG_CACHE["ts"] = now
    _CATALOG_CACHE["data"] = catalogo

    logger.info(
        "[REPORTS] Catálogo informes diarios generado | hidro=%s | oper=%s | desp=%s",
        resolved_from.get("VariablesHidrologicas"),
        resolved_from.get("VariablesOperativas"),
        resolved_from.get("SeguimientoDespacho"),
    )
    return catalogo


def _descargar_informe_diario_por_tipo_sync(tipo: str) -> tuple[bytes, str]:
    """Descarga un informe diario XM por tipo (con fallback)."""
    valid = {p for p, _ in INFORME_DIARIO_TIPOS}
    if tipo not in valid:
        raise RuntimeError(f"Tipo de informe inválido: {tipo}")

    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
    folders = _index_informes_diarios_folders(headers, drive_id, root_id)
    resolved, _ = _resolver_informes_diarios(folders)
    item = resolved[tipo]
    content = _sp_download_item(headers, drive_id, item)
    logger.info("[REPORTS] Informe diario descargado: %s (%s)", item["name"], tipo)
    return content, item["name"]


def _descargar_ultimo_boletin_sync() -> tuple[bytes, str]:
    """
    Descarga el PDF más reciente de Boletines Energeticos (SharePoint).
    Consulta en tiempo real — sin caché.
    """
    headers, drive_id, root_id = _sp_open_folder(BOLETINES_ENERGETICOS_FOLDER)
    files = [f for f in _graph_list_all_children(headers, drive_id, root_id) if "file" in f]
    if not files:
        raise RuntimeError("No se encontraron boletines en SharePoint")

    files.sort(
        key=lambda x: (x.get("lastModifiedDateTime", ""), x.get("name", "")),
        reverse=True,
    )
    latest = files[0]
    content = _sp_download_item(headers, drive_id, latest)
    logger.info(
        "[REPORTS] Boletín energético: %s | mod=%s | %.1f KB",
        latest["name"],
        latest.get("lastModifiedDateTime"),
        len(content) / 1024,
    )
    return content, latest["name"]


def _descargar_paquete_informes_diarios_sync() -> tuple[bytes, str]:
    """
    Resuelve los 3 informes diarios XM con fallback por tipo y empaqueta en ZIP.
    """
    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
    today = datetime.now(ZoneInfo("America/Bogota")).date()
    folders = _index_informes_diarios_folders(headers, drive_id, root_id)
    if not folders:
        raise RuntimeError("No se encontraron carpetas de informes diarios")

    resolved, resolved_from = _resolver_informes_diarios(folders, today)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pattern, item in resolved.items():
            content = _sp_download_item(headers, drive_id, item)
            zf.writestr(item["name"], content)

    zip_name = f"Informes_Diarios_XM_{today.strftime('%d_%m_%Y')}.zip"
    logger.info(
        "[REPORTS] Paquete informes diarios %s | hidro=%s | oper=%s | desp=%s",
        zip_name,
        resolved_from.get("VariablesHidrologicas"),
        resolved_from.get("VariablesOperativas"),
        resolved_from.get("SeguimientoDespacho"),
    )
    return buf.getvalue(), zip_name


def _descargar_ultimo_informe_xm_sync() -> tuple[bytes, str]:
    """Alias de compatibilidad → boletines energéticos."""
    return _descargar_ultimo_boletin_sync()


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.get(
    "/daily-pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Informe ejecutivo diario en PDF",
    description=(
        "Genera el informe ejecutivo del sistema eléctrico colombiano "
        "para la fecha indicada. Incluye CU descompuesto, demanda, "
        "generación y pérdidas. Autenticación requerida (X-API-Key)."
    ),
)
async def get_daily_pdf(
    fecha: date = Query(
        default=None,
        description="Fecha del informe (YYYY-MM-DD). Default: ayer.",
    ),
    api_key: str = Depends(get_api_key),
):
    if fecha is None:
        fecha = date.today() - timedelta(days=1)

    if fecha > date.today():
        raise HTTPException(
            status_code=400,
            detail="No se puede generar informe de fecha futura.",
        )

    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None, _generate_pdf_sync, fecha
        )
    except Exception as e:
        logger.error(f"[REPORTS] Error generando PDF para {fecha}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generando PDF: {str(e)}",
        )

    filename = f"ENERTRACE_informe_{fecha.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/available-dates",
    summary="Fechas con datos disponibles para informes",
)
async def get_available_dates(
    limit: int = Query(default=30, ge=1, le=90),
    api_key: str = Depends(get_api_key),
):
    """Retorna las últimas N fechas con registros en cu_daily."""
    cm = PostgreSQLConnectionManager()
    try:
        with cm.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT fecha FROM cu_daily ORDER BY fecha DESC LIMIT %s",
                (limit,),
            )
            fechas = [str(r[0]) for r in cur.fetchall()]
        return {"fechas_disponibles": fechas, "total": len(fechas)}
    except Exception as e:
        logger.error(f"[REPORTS] Error en available-dates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/boletines-energeticos/latest",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Boletín energético más reciente (SharePoint)",
    description="Descarga el PDF más reciente de la carpeta Boletines Energeticos.",
)
async def get_latest_boletin_energetico(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_ultimo_boletin_sync
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando boletín: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar el boletín: {e}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )


@router.get(
    "/informes-diarios-xm/catalogo",
    summary="Catálogo de informes diarios XM para slider",
)
async def get_catalogo_informes_diarios_xm(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        informes = await loop.run_in_executor(None, _catalogo_informes_diarios_sync)
    except Exception as e:
        logger.error("[REPORTS] Error generando catálogo informes: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo obtener el catálogo: {e}",
        )
    return {"informes": informes, "total": len(informes)}


@router.get(
    "/informes-diarios-xm/descargar",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Descargar informe diario XM por tipo",
)
async def get_informe_diario_por_tipo(
    tipo: str = Query(
        ...,
        description="SeguimientoDespacho | VariablesOperativas | VariablesHidrologicas",
    ),
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_informe_diario_por_tipo_sync, tipo
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando informe %s: %s", tipo, e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar el informe: {e}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )


@router.get(
    "/informes-diarios-xm/paquete",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
    summary="Paquete de 3 informes diarios XM (SharePoint)",
    description=(
        "Descarga ZIP con Seguimiento de despacho, Variables operativas "
        "y Variables hidrológicas. Usa fallback al día anterior si falta el de hoy."
    ),
)
async def get_paquete_informes_diarios_xm(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        zip_bytes, filename = await loop.run_in_executor(
            None, _descargar_paquete_informes_diarios_sync
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando paquete informes: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar los informes: {e}",
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )


@router.get(
    "/informe-diario-xm/latest",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="[Compat] Boletín energético más reciente",
    description="Alias de /boletines-energeticos/latest para compatibilidad.",
)
async def get_latest_informe_diario_xm(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_ultimo_boletin_sync
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando boletín: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar el informe: {e}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )
