"""
Endpoints internos — solo para servicios del mismo servidor (Telegram bot, Celery).

NO exponer al exterior (nginx debe bloquear /api/v1/internal desde la red pública).
Autenticados con la misma X-API-Key que el resto de la API.

Endpoints:
  POST /internal/telegram-users   — upsert de usuario Telegram
  POST /internal/reports/pdf      — generar PDF y devolver bytes
"""

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.dependencies import get_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
#  Schemas
# ═══════════════════════════════════════════════════════════

class TelegramUserRequest(BaseModel):
    chat_id: int = Field(..., description="Telegram chat_id del usuario")
    username: Optional[str] = Field(None, description="@username de Telegram")
    nombre: Optional[str] = Field(None, description="Nombre visible del usuario")


class PdfReportRequest(BaseModel):
    informe_texto: str = Field(..., description="Narrativa IA en Markdown")
    fecha_generacion: str = Field("", description="Fecha/hora de generación")
    generado_con_ia: bool = Field(True)
    chart_paths: Optional[List[str]] = Field(None, description="Rutas absolutas a PNGs")
    fichas: Optional[List[Dict[str, Any]]] = Field(None)
    predicciones: Optional[Any] = Field(None)
    anomalias: Optional[List[Dict[str, Any]]] = Field(None)
    noticias: Optional[List[Dict[str, Any]]] = Field(None)
    contexto_datos: Optional[Dict[str, Any]] = Field(None)


# ═══════════════════════════════════════════════════════════
#  Endpoint: upsert usuario Telegram
# ═══════════════════════════════════════════════════════════

@router.post(
    "/telegram-users",
    status_code=status.HTTP_200_OK,
    summary="Upsert usuario Telegram",
    tags=["🔒 Internal"],
)
async def upsert_telegram_user(
    body: TelegramUserRequest,
    api_key: str = Depends(get_api_key),
) -> dict:
    """
    Registra o actualiza un usuario de Telegram en PostgreSQL.
    Reemplaza el import directo de `persist_telegram_user` en el bot.
    """
    try:
        from domain.services.notification_service import persist_telegram_user
        ok = persist_telegram_user(body.chat_id, body.username, body.nombre)
        return {"success": ok, "chat_id": body.chat_id}
    except Exception as e:
        logger.error(f"[INTERNAL] Error upsert telegram_user {body.chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registrando usuario Telegram",
        )


# ═══════════════════════════════════════════════════════════
#  Endpoint: generar PDF y devolver bytes
# ═══════════════════════════════════════════════════════════

@router.post(
    "/reports/pdf",
    status_code=status.HTTP_200_OK,
    summary="Generar PDF del informe ejecutivo",
    tags=["🔒 Internal"],
    response_class=Response,
)
async def generate_pdf_report(
    body: PdfReportRequest,
    api_key: str = Depends(get_api_key),
) -> Response:
    """
    Genera el PDF del informe ejecutivo y devuelve los bytes directamente
    como `application/pdf`. El bot escribe los bytes a BytesIO y envía por Telegram.

    Si WeasyPrint no está instalado o hay un error de generación, responde 503.
    """
    try:
        from domain.services.report_service import generar_pdf_informe

        pdf_path = generar_pdf_informe(
            informe_texto=body.informe_texto,
            fecha_generacion=body.fecha_generacion,
            generado_con_ia=body.generado_con_ia,
            chart_paths=body.chart_paths,
            fichas=body.fichas,
            predicciones=body.predicciones,
            anomalias=body.anomalias,
            noticias=body.noticias,
            contexto_datos=body.contexto_datos,
        )

        if not pdf_path or not os.path.exists(pdf_path):
            logger.error("[INTERNAL] generar_pdf_informe retornó None o ruta inexistente")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Fallo al generar PDF (WeasyPrint o datos inválidos)",
            )

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Limpiar el temporal inmediatamente tras leer
        try:
            os.unlink(pdf_path)
        except OSError:
            pass

        logger.info(f"[INTERNAL] PDF generado y enviado ({len(pdf_bytes) // 1024} KB)")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=informe_ejecutivo.pdf"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTERNAL] Error generando PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno generando PDF",
        )
