import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/informes", tags=["informes-tableros"])

TABLEROS_VALIDOS = {
    "subsidios", "fenoge", "contratos-or", "supervision",
    "presupuesto", "comunidades", "pagos", "validaciones",
    "energia", "colombia-solar", "predicciones",
}


@router.get("/{tablero}")
async def descargar_informe_tablero(tablero: str, request: Request):
    if tablero not in TABLEROS_VALIDOS:
        raise HTTPException(
            status_code=404,
            detail=f"Tablero '{tablero}' no encontrado. Validos: {', '.join(sorted(TABLEROS_VALIDOS))}"
        )

    # Collect all query params as filters (exclude any path-derived params)
    params: dict[str, str] = dict(request.query_params)

    try:
        from domain.services.portal_report_service import generate_tablero_pdf

        pdf_bytes = await generate_tablero_pdf(tablero, params)

        if pdf_bytes is None:
            raise HTTPException(
                status_code=500,
                detail=f"Error al generar informe para el tablero '{tablero}'"
            )

        filename = f"Informe_{tablero.replace('-', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        }

        return Response(
            content=pdf_bytes,
            headers=headers,
            media_type="application/pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en endpoint informe {tablero}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al generar informe: {str(e)}"
        )


@router.get("/catalogo")
async def catalogo_informes():
    return {
        "tableros": sorted(TABLEROS_VALIDOS),
        "total": len(TABLEROS_VALIDOS)
    }
