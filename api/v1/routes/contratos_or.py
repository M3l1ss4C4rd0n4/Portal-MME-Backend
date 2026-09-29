"""
Endpoint contratos OR — Portal Dirección EE
GET /v1/contratos-or/dashboard → contratos_or.seguimiento_avance_documental (Power BI logic)
GET /v1/contratos-or/actas/catalogo → Lista actas PDF desde SharePoint
GET /v1/contratos-or/actas/descargar → Descarga acta PDF por itemId
"""

import logging
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from api.dependencies import get_api_key
from domain.services.contratos_or_parsing import fetch_contratos_or_kpis, fetch_ratios_consolidados
from infrastructure.database.connection import PostgreSQLConnectionManager

from .reports import _sp_open_folder, _graph_list_children_recent, _sp_download_item

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_cm = PostgreSQLConnectionManager()


@router.get("/dashboard", summary="Dashboard seguimiento contratos OR")
@limiter.limit("60/minute")
async def get_contratos_or_dashboard(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection(use_dict_cursor=True) as conn:
            with conn.cursor() as cur:
                r = fetch_contratos_or_kpis(cur)
                ratios = fetch_ratios_consolidados(cur)

        return JSONResponse({
            "ultima_actualizacion": r["fecha_corte"],
            "nContratos":        r["n_contratos"],
            "avanceGeneral":     r["avance_general"],
            "avanceFinanciero":  r["avance_financiero"],
            "pagosRealizados":   r["pagos_realizados"],
            "pagosPosibles":     r["pagos_posibles"],
            "pctPagosRealizados": r["pct_pagos_realizados"],
            "avanceFisico":      r["avance_fisico"],
            "valorTotal":        r["valor_total"],
            "usuariosTotal":     r["usuarios_total"],
            "potenciaMwpTotal":  r["potencia_mwp_total"],
            "desembolsos": [
                {
                    "numero":            d["numero"],
                    "actNecesarias":     d["actividades_necesarias"],
                    "actCompletas":      d["actividades_completas"],
                    "pctCompletado":     d["pct_completado"],
                    "proyectosPagados":  d["proyectos_pagados"],
                }
                for d in r["desembolsos"]
            ],
            "proyectos": [
                {
                    "nombre":           p["nombre"],
                    "ejecutor":         p["ejecutor"],
                    "departamento":     p["departamento"],
                    "municipio":        p["municipio"],
                    "avanceGeneral":    p["avance_general"],
                    "avanceFisico":     p["avance_fisico"],
                    "avanceFinanciero": p["avance_financiero"],
                    "totalDesembolsos": p["total_desembolsos"],
                    "pagosRealizados":  p["pagos_realizados"],
                    "valor":            p["valor"],
                    "usuarios":         p["usuarios"],
                    "potenciaMwp":      p["potencia_mwp"],
                }
                for p in r["proyectos"]
            ],
            "ratiosConsolidados": {
                "kpis": ratios["kpis"],
                "filas": [
                    {
                        "ejecutor":               f["ejecutor"],
                        "departamento":           f["departamento"],
                        "municipio":              f["municipio"],
                        "proyectado":             f["proyectado"],
                        "obrasCiviles":           f["obrasCiviles"],
                        "instalacionesInternas":  f["instalacionesInternas"],
                        "usuariosEnergizados":    f["usuariosEnergizados"],
                    }
                    for f in ratios["filas"]
                ],
            },
        })
    except Exception as e:
        logger.error("[contratos-or] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener contratos OR")


# ─── Helper: convertir .docx a PDF ────────────────────────────────────────
def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Convierte un archivo .docx en bytes a PDF usando python-docx + reportlab."""
    doc = Document(BytesIO(docx_bytes))
    pdf_buffer = BytesIO()
    doc_template = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    flowables: list = []

    # Párrafos
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            style_name = "Heading1" if para.style and para.style.name == "Heading 1" else "Normal"
            s = styles[style_name] if style_name in styles else styles["Normal"]
            try:
                flowables.append(Paragraph(text, s))
                flowables.append(Spacer(1, 6))
            except Exception:
                flowables.append(Paragraph(text.replace("&", "&amp;"), styles["Normal"]))
                flowables.append(Spacer(1, 6))

    # Tablas
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            row_text = " | ".join(cells)
            if row_text.strip():
                flowables.append(Paragraph(row_text, styles["Normal"]))
                flowables.append(Spacer(1, 3))
        flowables.append(Spacer(1, 8))

    doc_template.build(flowables)
    return pdf_buffer.getvalue()


# ─── SharePoint: Actas de seguimiento ELECTROCAQUETA ────────────────────────

SHARE_URL_ACTAS = (
    "https://minenergiacol.sharepoint.com/:f:/r/sites/"
    "DireccindeEnergaElctrica-DEE_Supervision/Shared%20Documents/"
    "DEE_Supervision/Direccion_Energia/1%20-%20Fondos%20de%20Inversi%C3%B3n/"
    "10.%20COMUNIDADES%20ENERG%C3%89TICAS/ELECTROCAQUETA%20ACTAS"
    "?csf=1&web=1&e=jVfXf9"
)


@router.get("/actas/catalogo", summary="Catálogo de actas de seguimiento")
@limiter.limit("30/minute")
async def get_actas_catalogo(request: Request, api_key: str = Depends(get_api_key)):
    try:
        headers, drive_id, root_id = _sp_open_folder(SHARE_URL_ACTAS)
        children = _graph_list_children_recent(headers, drive_id, root_id, top=50)

        documentos = []
        for item in children:
            if not item.get("file"):
                continue
            name_lower = item["name"].lower()
            if not (name_lower.endswith(".pdf") or name_lower.endswith(".docx")):
                continue
            tipo = "pdf" if name_lower.endswith(".pdf") else "docx"
            documentos.append({
                "id": item["id"],
                "name": item["name"],
                "lastModified": item.get("lastModifiedDateTime"),
                "tipo": tipo,
            })

        return {"actas": documentos, "total": len(documentos)}
    except Exception as e:
        logger.error("[contratos-or/actas/catalogo] %s", e)
        raise HTTPException(status_code=502, detail="Error al obtener actas de SharePoint")


@router.get("/actas/descargar", summary="Descargar acta PDF")
@limiter.limit("30/minute")
async def descargar_acta(
    request: Request,
    item_id: str,
    api_key: str = Depends(get_api_key),
):
    try:
        headers, drive_id, root_id = _sp_open_folder(SHARE_URL_ACTAS)

        # Obtener nombre del archivo
        children = _graph_list_children_recent(headers, drive_id, root_id, top=50)
        filename = "acta.pdf"
        for child in children:
            if child["id"] == item_id:
                filename = child.get("name", "acta.pdf")
                break

        file_bytes = _sp_download_item(headers, drive_id, {"id": item_id, "name": filename})

        # Si es .docx, convertir a PDF antes de enviar
        if filename.lower().endswith(".docx"):
            try:
                file_bytes = _convert_docx_to_pdf_bytes(file_bytes)
                filename = filename.rsplit(".", 1)[0] + ".pdf"
            except Exception as conv_err:
                logger.error("[contratos-or/actas/descargar] Error convirtiendo docx a PDF: %s", conv_err)
                # Si falla la conversión, intentamos enviar el docx original
                return Response(
                    content=file_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Cache-Control": "no-store, no-cache, must-revalidate",
                    },
                )

        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store, no-cache, must-revalidate",
            },
        )
    except Exception as e:
        logger.error("[contratos-or/actas/descargar] %s", e)
        raise HTTPException(status_code=502, detail="Error al descargar acta")
