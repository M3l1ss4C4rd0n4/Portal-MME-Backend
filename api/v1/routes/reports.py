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
    GET /v1/reports/resumen-ejecutivo/latest            → PDF informe diario (correo/Telegram)
    GET /v1/reports/informe-empalme/latest               → informe de empalme más reciente (SharePoint)
"""

BOLETINES_ENERGETICOS_FOLDER = (
    "https://minenergiacol-my.sharepoint.com/:f:/g/personal/"
    "dmgutierrez_minenergia_gov_co/IgBa3I-9XSaFSbrXfNDFt7pZAdfgSDIrupFx2hIH8hYyHnM"
)

INFORMES_DIARIOS_XM_FOLDER = (
    "https://minenergiacol-my.sharepoint.com/:f:/g/personal/"
    "dmgutierrez_minenergia_gov_co/IgDtJ4pD_cSfTaOYhzHY833bAVLgyP7fJhhCDJmIfgQo-tw"
)

INFORME_EMPALME_FOLDER = (
    "https://minenergiacol-my.sharepoint.com/:f:/g/personal/"
    "dmgutierrez_minenergia_gov_co/IgDTXr0lxDk0T5CU01aasU22Afimb2-f0HlyS-GwUhqWaFI"
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

import asyncio
import io
import json
import logging
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_CATALOG_CACHE: dict = {"ts": 0.0, "payload": None}
# 30 min — los informes diarios solo cambian ~1 vez al día; un TTL corto (antes
# 30s) hacía que casi cada visita disparara el escaneo completo de SharePoint
# (listar carpetas + descargar y parsear los 3 PDFs), lento y propenso a 502
# si SharePoint respondía lento. invalidate_informes_diarios_cache() sigue
# permitiendo refrescar al instante cuando el watcher detecta un cambio real.
_CATALOG_TTL_SEC = 1800
_CATALOG_BUST_FILE = (
    Path(__file__).resolve().parents[3] / "logs" / ".informes_diarios_cache_bust"
)
_BOLETIN_CACHE_DIR = Path(__file__).resolve().parents[3] / "cache" / "boletines"
_INFORME_EMPALME_CACHE_DIR = Path(__file__).resolve().parents[3] / "cache" / "informe_empalme"

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
        resp = requests.get(url, headers=headers, timeout=(20, 45))
        resp.raise_for_status()
        body = resp.json()
        items.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
    return items


def _graph_list_children_recent(
    headers: dict,
    drive_id: str,
    item_id: str,
    *,
    top: int = 30,
) -> list[dict]:
    """Lista hijos recientes ordenados por lastModifiedDateTime (sin paginar todo el drive)."""
    import requests

    url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children"
        f"?$select=id,name,lastModifiedDateTime,file,folder"
        f"&$orderby=lastModifiedDateTime desc&$top={top}"
    )
    resp = requests.get(url, headers=headers, timeout=(20, 60))
    resp.raise_for_status()
    return resp.json().get("value", [])


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
        timeout=(20, 45),
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
        timeout=(20, 45),
    )
    file_meta.raise_for_status()
    download_url = file_meta.json().get("@microsoft.graph.downloadUrl")
    if not download_url:
        raise RuntimeError(f"Sin URL de descarga para {item.get('name')}")

    pdf_resp = requests.get(
        download_url,
        headers={"Cache-Control": "no-cache"},
        timeout=(20, read_timeout),
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
    """folder_date → {pattern_key: driveItem}. Solo escanea carpetas DD_MM_YYYY recientes."""
    folders: dict[date, dict[str, dict]] = {}
    for item in _graph_list_children_recent(headers, drive_id, root_id, top=45):
        if "folder" not in item:
            continue
        folder_date = _parse_folder_date(item["name"])
        if folder_date is None:
            continue
        typed: dict[str, dict] = {}
        for f in _graph_list_children_recent(headers, drive_id, item["id"], top=15):
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


def _catalog_bust_mtime() -> float:
    try:
        return _CATALOG_BUST_FILE.stat().st_mtime
    except OSError:
        return 0.0


def invalidate_informes_diarios_cache() -> None:
    """Invalida caché en todos los workers (archivo bust + memoria local)."""
    _CATALOG_BUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CATALOG_BUST_FILE.write_text(str(time.time()), encoding="utf-8")
    _CATALOG_CACHE["ts"] = 0.0
    _CATALOG_CACHE["payload"] = None
    logger.info("[REPORTS] Caché informes diarios invalidada")


def _build_catalog_resumen(
    folders: dict[date, dict[str, dict]],
    resolved_from: dict[str, date],
    today: date,
) -> dict:
    del_dia = sum(
        1 for pattern, _ in INFORME_DIARIO_TIPOS
        if resolved_from.get(pattern) == today
    )
    pendientes = [
        label for pattern, label in INFORME_DIARIO_TIPOS
        if resolved_from.get(pattern) != today
    ]
    return {
        "fechaConsulta": today.isoformat(),
        "completosDelDia": del_dia,
        "totalTipos": len(INFORME_DIARIO_TIPOS),
        "pendientes": pendientes,
        "completo": del_dia == len(INFORME_DIARIO_TIPOS),
        "actualizadoEn": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
    }


def scan_informes_diarios_status(today: date | None = None) -> dict:
    """
    Escaneo ligero de SharePoint (sin descargar PDFs).
    Usado por el watcher cron para detectar cambios y alertas.
    """
    if today is None:
        today = datetime.now(ZoneInfo("America/Bogota")).date()

    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
    folders = _index_informes_diarios_folders(headers, drive_id, root_id)
    if not folders:
        raise RuntimeError("No se encontraron carpetas de informes diarios")

    resolved, resolved_from = _resolver_informes_diarios(folders, today)
    today_folder = folders.get(today, {})
    resumen = _build_catalog_resumen(folders, resolved_from, today)

    return {
        "resumen": resumen,
        "fingerprint": {
            "fecha": today.isoformat(),
            "carpetaHoy": {
                pattern: today_folder[pattern].get("lastModifiedDateTime")
                for pattern in today_folder
            },
            "resueltos": {
                pattern: {
                    "fecha": resolved_from[pattern].isoformat(),
                    "modificado": resolved[pattern].get("lastModifiedDateTime"),
                }
                for pattern in resolved
            },
        },
    }


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
        # read_timeout bajo a propósito (a diferencia de descargas de archivo
        # completo por acción explícita del usuario, que sí usan 300s más
        # abajo en este archivo): esto es solo una vista previa (título/
        # descripción) del catálogo, refrescado automáticamente cada 2 min
        # por polling del frontend — con red degradada hacia Microsoft
        # Graph, un timeout de 300s aquí mantenía un hilo bloqueado el
        # tiempo suficiente para impedir el apagado ordenado del servicio
        # (systemd terminó forzando SIGKILL de portal-api.service completo
        # el 2026-08-11 ~10:00am, afectando a todos los usuarios del portal,
        # no solo a esta tarjeta). Ya existe un fallback (_preview_fallback)
        # para cuando la descarga falla, así que fallar rápido aquí es
        # estrictamente mejor que esperar hasta 300s.
        content = _sp_download_item(headers, drive_id, item, read_timeout=25)
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


def _catalogo_informes_diarios_sync() -> dict:
    """Metadatos de los 3 informes diarios (título/descripción desde PDF)."""
    now = time.time()
    bust_mtime = _catalog_bust_mtime()
    cached = _CATALOG_CACHE["payload"]
    if (
        cached is not None
        and now - _CATALOG_CACHE["ts"] < _CATALOG_TTL_SEC
        and _CATALOG_CACHE["ts"] >= bust_mtime
    ):
        return cached

    try:
        headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
        today = datetime.now(ZoneInfo("America/Bogota")).date()
        folders = _index_informes_diarios_folders(headers, drive_id, root_id)
        if not folders:
            raise RuntimeError("No se encontraron carpetas de informes diarios")

        resolved, resolved_from = _resolver_informes_diarios(folders, today)
        resumen = _build_catalog_resumen(folders, resolved_from, today)

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

        payload = {"informes": catalogo, "resumen": resumen}
        _CATALOG_CACHE["ts"] = now
        _CATALOG_CACHE["payload"] = payload

        logger.info(
            "[REPORTS] Catálogo informes diarios generado | hidro=%s | oper=%s | desp=%s | %d/%d del día",
            resolved_from.get("VariablesHidrologicas"),
            resolved_from.get("VariablesOperativas"),
            resolved_from.get("SeguimientoDespacho"),
            resumen["completosDelDia"],
            resumen["totalTipos"],
        )
        return payload
    except Exception as exc:
        # Degradación agraciada: si SharePoint/Graph está lento o falla (red
        # degradada, throttling, etc.) y ya tenemos una versión previa en
        # caché — aunque esté vencida — se sirve esa en vez de un error duro.
        # Los informes diarios cambian ~1 vez al día, así que una versión con
        # unos minutos u horas de más sigue siendo correcta para el usuario.
        if cached is not None:
            logger.warning(
                "[REPORTS] Falló actualización del catálogo de informes (%s) — "
                "sirviendo versión en caché de hace %.0fs",
                exc, now - _CATALOG_CACHE["ts"],
            )
            return cached
        raise


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


_BOLETIN_CACHE_TTL_HOURS = 6


def _descargar_ultimo_boletin_sync() -> tuple[bytes, str]:
    """
    Descarga el PDF más reciente de Boletines Energeticos (SharePoint).
    Sirve desde caché local si tiene menos de _BOLETIN_CACHE_TTL_HOURS horas
    para evitar descargar 20 MB de SharePoint en cada solicitud.
    """
    _BOLETIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_pdf = _BOLETIN_CACHE_DIR / "latest.pdf"
    cache_meta = _BOLETIN_CACHE_DIR / "latest.meta.json"

    def _read_cache() -> tuple[bytes, str, dict] | None:
        if not cache_pdf.is_file() or not cache_meta.is_file():
            return None
        try:
            meta = json.loads(cache_meta.read_text(encoding="utf-8"))
            return cache_pdf.read_bytes(), meta["filename"], meta
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def _cache_age_hours(meta: dict) -> float:
        try:
            cached_at = datetime.fromisoformat(meta["cached_at"])
            now = datetime.now(ZoneInfo("America/Bogota"))
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=ZoneInfo("America/Bogota"))
            return (now - cached_at).total_seconds() / 3600
        except (KeyError, ValueError):
            return float("inf")

    # Servir desde caché si es reciente
    cached = _read_cache()
    if cached:
        content, filename, meta = cached
        age_h = _cache_age_hours(meta)
        if age_h < _BOLETIN_CACHE_TTL_HOURS:
            logger.info(
                "[REPORTS] Boletín servido desde caché (%.1fh < %dh TTL): %s, %.1f KB",
                age_h, _BOLETIN_CACHE_TTL_HOURS, filename, len(content) / 1024,
            )
            return content, filename

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            headers, drive_id, root_id = _sp_open_folder(BOLETINES_ENERGETICOS_FOLDER)
            files = [
                f for f in _graph_list_children_recent(headers, drive_id, root_id, top=25)
                if "file" in f and f.get("name", "").lower().endswith(".pdf")
            ]
            if not files:
                raise RuntimeError("No se encontraron boletines en SharePoint")

            latest = max(
                files,
                key=lambda x: (x.get("lastModifiedDateTime", ""), x.get("name", "")),
            )

            # Si el archivo en SharePoint no cambió respecto al caché, devolver caché
            if cached:
                content_c, filename_c, meta_c = cached
                if latest.get("lastModifiedDateTime") == meta_c.get("modificado"):
                    # Actualizar solo el timestamp de caché para reiniciar TTL
                    meta_c["cached_at"] = datetime.now(ZoneInfo("America/Bogota")).isoformat()
                    cache_meta.write_text(json.dumps(meta_c, ensure_ascii=False), encoding="utf-8")
                    logger.info(
                        "[REPORTS] Boletín sin cambios en SharePoint — TTL renovado: %s", filename_c
                    )
                    return content_c, filename_c

            content = _sp_download_item(headers, drive_id, latest, read_timeout=300)
            cache_pdf.write_bytes(content)
            cache_meta.write_text(
                json.dumps(
                    {
                        "filename": latest["name"],
                        "modificado": latest.get("lastModifiedDateTime"),
                        "cached_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logger.info(
                "[REPORTS] Boletín actualizado desde SharePoint: %s | mod=%s | %.1f KB",
                latest["name"],
                latest.get("lastModifiedDateTime"),
                len(content) / 1024,
            )
            return content, latest["name"]
        except Exception as exc:
            last_error = exc
            logger.warning(
                "[REPORTS] Boletín SharePoint intento %d/2 falló: %s",
                attempt + 1,
                exc,
            )

    if cached:
        content, filename, _ = cached
        logger.warning(
            "[REPORTS] Boletín servido desde caché vencida (%s, %.1f KB) — SharePoint no respondió",
            filename,
            len(content) / 1024,
        )
        return content, filename

    raise RuntimeError(f"No se pudo descargar el boletín: {last_error}")


_INFORME_EMPALME_CACHE_TTL_HOURS = 6
_INFORME_EMPALME_FALLBACK_NAME = "Informe_de_Empalme_MME.pdf"


def _descargar_ultimo_informe_empalme_sync() -> tuple[bytes, str]:
    """
    Descarga el PDF más reciente de la carpeta Informe de Empalme (SharePoint).
    Sirve desde caché local si tiene menos de _INFORME_EMPALME_CACHE_TTL_HOURS
    horas para evitar golpear SharePoint en cada clic del botón "Empalme".
    """
    _INFORME_EMPALME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_pdf = _INFORME_EMPALME_CACHE_DIR / "latest.pdf"
    cache_meta = _INFORME_EMPALME_CACHE_DIR / "latest.meta.json"

    def _read_cache() -> tuple[bytes, str, dict] | None:
        if not cache_pdf.is_file() or not cache_meta.is_file():
            return None
        try:
            meta = json.loads(cache_meta.read_text(encoding="utf-8"))
            return cache_pdf.read_bytes(), meta["filename"], meta
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def _cache_age_hours(meta: dict) -> float:
        try:
            cached_at = datetime.fromisoformat(meta["cached_at"])
            now = datetime.now(ZoneInfo("America/Bogota"))
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=ZoneInfo("America/Bogota"))
            return (now - cached_at).total_seconds() / 3600
        except (KeyError, ValueError):
            return float("inf")

    # Servir desde caché si es reciente
    cached = _read_cache()
    if cached:
        content, filename, meta = cached
        age_h = _cache_age_hours(meta)
        if age_h < _INFORME_EMPALME_CACHE_TTL_HOURS:
            logger.info(
                "[REPORTS] Informe de empalme servido desde caché (%.1fh < %dh TTL): %s, %.1f KB",
                age_h, _INFORME_EMPALME_CACHE_TTL_HOURS, filename, len(content) / 1024,
            )
            return content, filename

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            headers, drive_id, root_id = _sp_open_folder(INFORME_EMPALME_FOLDER)
            files = [
                f for f in _graph_list_children_recent(headers, drive_id, root_id, top=25)
                if "file" in f and f.get("name", "").lower().endswith(".pdf")
            ]
            if not files:
                raise RuntimeError("No se encontró el informe de empalme en SharePoint")

            latest = max(
                files,
                key=lambda x: (x.get("lastModifiedDateTime", ""), x.get("name", "")),
            )

            # Si el archivo en SharePoint no cambió respecto al caché, devolver caché
            if cached:
                content_c, filename_c, meta_c = cached
                if latest.get("lastModifiedDateTime") == meta_c.get("modificado"):
                    # Actualizar solo el timestamp de caché para reiniciar TTL
                    meta_c["cached_at"] = datetime.now(ZoneInfo("America/Bogota")).isoformat()
                    cache_meta.write_text(json.dumps(meta_c, ensure_ascii=False), encoding="utf-8")
                    logger.info(
                        "[REPORTS] Informe de empalme sin cambios en SharePoint — TTL renovado: %s",
                        filename_c,
                    )
                    return content_c, filename_c

            content = _sp_download_item(headers, drive_id, latest, read_timeout=300)
            cache_pdf.write_bytes(content)
            cache_meta.write_text(
                json.dumps(
                    {
                        "filename": latest["name"],
                        "modificado": latest.get("lastModifiedDateTime"),
                        "cached_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logger.info(
                "[REPORTS] Informe de empalme actualizado desde SharePoint: %s | mod=%s | %.1f KB",
                latest["name"],
                latest.get("lastModifiedDateTime"),
                len(content) / 1024,
            )
            return content, latest["name"]
        except Exception as exc:
            last_error = exc
            logger.warning(
                "[REPORTS] Informe de empalme SharePoint intento %d/2 falló: %s",
                attempt + 1,
                exc,
            )

    if cached:
        content, filename, _ = cached
        logger.warning(
            "[REPORTS] Informe de empalme servido desde caché vencida (%s, %.1f KB) — SharePoint no respondió",
            filename,
            len(content) / 1024,
        )
        return content, filename

    raise RuntimeError(f"No se pudo descargar el informe de empalme: {last_error}")


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


def _graph_list_all_children_full(
    headers: dict,
    drive_id: str,
    item_id: str,
) -> list[dict]:
    """Como _graph_list_all_children pero incluye el campo size."""
    import requests

    items: list[dict] = []
    url: str | None = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children"
        f"?$select=id,name,lastModifiedDateTime,file,folder,size"
    )
    while url:
        resp = requests.get(url, headers=headers, timeout=(20, 75))
        resp.raise_for_status()
        body = resp.json()
        items.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
    return items


def _listar_boletines_sync(
    pagina: int, limite: int,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict:
    """Lista todos los boletines energéticos de SharePoint con paginación y filtro de fecha."""
    headers, drive_id, root_id = _sp_open_folder(BOLETINES_ENERGETICOS_FOLDER)
    all_files = [
        f for f in _graph_list_all_children_full(headers, drive_id, root_id)
        if "file" in f and f.get("name", "").lower().endswith(".pdf")
    ]
    all_files.sort(key=lambda x: x.get("lastModifiedDateTime", ""), reverse=True)

    if fecha_desde or fecha_hasta:
        def _in_range(f: dict) -> bool:
            raw = f.get("lastModifiedDateTime", "")
            if not raw:
                return True
            try:
                d = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            except ValueError:
                return True
            if fecha_desde and d < fecha_desde:
                return False
            if fecha_hasta and d > fecha_hasta:
                return False
            return True
        all_files = [f for f in all_files if _in_range(f)]

    total = len(all_files)
    inicio = (pagina - 1) * limite
    page_files = all_files[inicio: inicio + limite]
    items = [
        {
            "nombre": f["name"],
            "fecha": f.get("lastModifiedDateTime", ""),
            "driveId": drive_id,
            "itemId": f["id"],
            "tamano": f.get("size", 0),
        }
        for f in page_files
    ]
    return {"items": items, "total": total, "pagina": pagina, "limite": limite}


def _listar_xm_sync(
    pagina: int, limite: int, tipo: str | None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict:
    """
    Lista todos los informes XM históricos de SharePoint con paginación.
    La carpeta raíz contiene subcarpetas DD_MM_YYYY, cada una con 3 PDFs.
    """
    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)

    subfolders = [
        f for f in _graph_list_all_children_full(headers, drive_id, root_id)
        if "folder" in f
    ]

    valid_tipos = {p for p, _ in INFORME_DIARIO_TIPOS}
    tipo_labels = {p: lbl for p, lbl in INFORME_DIARIO_TIPOS}

    all_items: list[dict] = []
    for folder in subfolders:
        folder_date = _parse_folder_date(folder["name"])
        if folder_date is None:
            continue
        if fecha_desde and folder_date < fecha_desde:
            continue
        if fecha_hasta and folder_date > fecha_hasta:
            continue
        for f in _graph_list_all_children_full(headers, drive_id, folder["id"]):
            if "file" not in f:
                continue
            if not f.get("name", "").lower().endswith(".pdf"):
                continue
            tipo_inferido: str | None = None
            for pattern in valid_tipos:
                if pattern in f["name"]:
                    tipo_inferido = pattern
                    break
            if tipo and tipo_inferido != tipo:
                continue
            all_items.append({
                "nombre": f["name"],
                "fecha": folder_date.isoformat(),
                "fechaModificado": f.get("lastModifiedDateTime", ""),
                "tipo": tipo_inferido,
                "tipoLabel": tipo_labels.get(tipo_inferido, tipo_inferido) if tipo_inferido else None,
                "driveId": drive_id,
                "itemId": f["id"],
                "tamano": f.get("size", 0),
            })

    all_items.sort(key=lambda x: x["fecha"], reverse=True)
    total = len(all_items)
    inicio = (pagina - 1) * limite
    page_items = all_items[inicio: inicio + limite]
    return {"items": page_items, "total": total, "pagina": pagina, "limite": limite}


def _descargar_archivo_por_id_sync(drive_id: str, item_id: str) -> tuple[bytes, str]:
    """Descarga cualquier archivo de OneDrive por drive_id + item_id."""
    headers = _sp_headers()
    item = {"id": item_id}
    content = _sp_download_item(headers, drive_id, item, read_timeout=300)
    import requests as _req
    meta = _req.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
        "?$select=name",
        headers=headers,
        timeout=(20, 30),
    )
    filename = meta.json().get("name", f"informe_{item_id}.pdf") if meta.ok else f"informe_{item_id}.pdf"
    return content, filename


def _informes_ejecutivos_dir() -> str:
    """Directorio donde Celery guarda copia del PDF diario (whatsapp_bot/informes)."""
    server_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.path.join(server_root, "whatsapp_bot", "informes")


def _descargar_ultimo_resumen_ejecutivo_sync() -> tuple[bytes, str]:
    """
    Devuelve el PDF más reciente generado por send_daily_summary
    (mismo archivo enviado por correo y Telegram).
    """
    informes_dir = _informes_ejecutivos_dir()
    if not os.path.isdir(informes_dir):
        raise RuntimeError(f"Directorio de informes no encontrado: {informes_dir}")

    candidates: list[tuple[float, str, str]] = []
    for name in os.listdir(informes_dir):
        if not name.startswith("Informe_Ejecutivo_MME_") or not name.endswith(".pdf"):
            continue
        if "_test" in name.lower():
            continue
        path = os.path.join(informes_dir, name)
        if os.path.isfile(path):
            candidates.append((os.path.getmtime(path), name, path))

    if not candidates:
        raise RuntimeError("No hay informes ejecutivos disponibles")

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, filename, path = candidates[0]
    with open(path, "rb") as f:
        pdf_bytes = f.read()

    logger.info("[REPORTS] Resumen ejecutivo servido: %s (%d KB)", filename, len(pdf_bytes) // 1024)
    return pdf_bytes, filename


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
    "/informe-empalme/latest",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Informe de empalme más reciente (SharePoint)",
    description="Descarga el PDF más reciente de la carpeta Informe de Empalme.",
)
async def get_latest_informe_empalme(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_ultimo_informe_empalme_sync
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando informe de empalme: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar el informe de empalme: {e}",
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
        payload = await loop.run_in_executor(None, _catalogo_informes_diarios_sync)
    except Exception as e:
        logger.error("[REPORTS] Error generando catálogo informes: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo obtener el catálogo: {e}",
        )
    informes = payload["informes"]
    return {
        "informes": informes,
        "total": len(informes),
        "resumen": payload["resumen"],
    }


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


@router.get(
    "/boletines-energeticos/lista",
    summary="Lista histórica de boletines energéticos",
    description="Retorna todos los boletines PDF disponibles en SharePoint, paginados y ordenados del más reciente al más antiguo.",
)
async def get_lista_boletines(
    pagina: int = Query(default=1, ge=1, description="Página (desde 1)"),
    limite: int = Query(default=30, ge=1, le=100, description="Resultados por página"),
    fecha_desde: date | None = Query(default=None, description="Filtrar desde esta fecha (YYYY-MM-DD)"),
    fecha_hasta: date | None = Query(default=None, description="Filtrar hasta esta fecha (YYYY-MM-DD)"),
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _listar_boletines_sync, pagina, limite, fecha_desde, fecha_hasta
        )
    except Exception as e:
        logger.error("[REPORTS] Error listando boletines: %s", e)
        raise HTTPException(status_code=502, detail=f"No se pudo listar los boletines: {e}")
    return result


@router.get(
    "/informes-diarios-xm/lista",
    summary="Lista histórica de informes XM",
    description="Retorna todos los informes XM históricos disponibles en SharePoint, paginados. Filtra por tipo y/o fecha.",
)
async def get_lista_informes_xm(
    pagina: int = Query(default=1, ge=1, description="Página (desde 1)"),
    limite: int = Query(default=30, ge=1, le=100, description="Resultados por página"),
    tipo: str | None = Query(
        default=None,
        description="Filtrar por tipo: SeguimientoDespacho | VariablesOperativas | VariablesHidrologicas",
    ),
    fecha_desde: date | None = Query(default=None, description="Filtrar desde esta fecha (YYYY-MM-DD)"),
    fecha_hasta: date | None = Query(default=None, description="Filtrar hasta esta fecha (YYYY-MM-DD)"),
    api_key: str = Depends(get_api_key),
):
    valid_tipos = {p for p, _ in INFORME_DIARIO_TIPOS}
    if tipo and tipo not in valid_tipos:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}. Valores: {sorted(valid_tipos)}")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _listar_xm_sync, pagina, limite, tipo, fecha_desde, fecha_hasta
        )
    except Exception as e:
        logger.error("[REPORTS] Error listando informes XM: %s", e)
        raise HTTPException(status_code=502, detail=f"No se pudo listar los informes XM: {e}")
    return result


@router.get(
    "/archivo",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Descargar archivo por driveId + itemId",
    description="Descarga cualquier archivo histórico de OneDrive usando su driveId e itemId devueltos por los endpoints de lista.",
)
async def get_archivo_por_id(
    drive_id: str = Query(..., description="driveId del archivo (de /lista)"),
    item_id: str = Query(..., description="itemId del archivo (de /lista)"),
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_archivo_por_id_sync, drive_id, item_id
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando archivo %s/%s: %s", drive_id, item_id, e)
        raise HTTPException(status_code=502, detail=f"No se pudo descargar el archivo: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )


@router.get(
    "/resumen-ejecutivo/latest",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Resumen ejecutivo diario (correo/Telegram)",
    description=(
        "Descarga el PDF del informe ejecutivo diario más reciente "
        "(mismo archivo enviado por correo y Telegram a las 8:30 AM)."
    ),
)
async def get_latest_resumen_ejecutivo(
    api_key: str = Depends(get_api_key),
):
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes, filename = await loop.run_in_executor(
            None, _descargar_ultimo_resumen_ejecutivo_sync
        )
    except Exception as e:
        logger.error("[REPORTS] Error descargando resumen ejecutivo: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo descargar el resumen ejecutivo: {e}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            **NO_CACHE_HEADERS,
        },
    )
