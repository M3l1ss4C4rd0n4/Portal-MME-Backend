"""
Endpoints: Informes Ejecutivos PDF

OE5: Generación de informes del sistema eléctrico colombiano en PDF.
Usa report_service.generar_pdf_informe() (WeasyPrint 68.1).

Endpoints:
    GET /v1/reports/daily-pdf?fecha=YYYY-MM-DD  → PDF download
    GET /v1/reports/available-dates             → fechas disponibles
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta

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
    except Exception:
        pass

    return pdf_bytes


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
