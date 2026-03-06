"""
ChatbotOrchestratorService — slim orchestrator.

Hereda comportamiento de todos los handler-mixins. Esta clase solo
contiene el núcleo de infra: __init__, orchestrate, _get_intent_handler,
_create_error_response y dos utilidades estáticas.
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from domain.services.generation_service import GenerationService
from domain.services.hydrology_service import HydrologyService
from domain.services.metrics_service import MetricsService
from domain.services.predictions_service import PredictionsService
from domain.services.intelligent_analysis_service import (
    IntelligentAnalysisService,
    Anomalia,
)
from domain.services.executive_report_service import ExecutiveReportService
from domain.services.news_service import NewsService
from domain.schemas.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    ErrorDetail,
)

from domain.services.orchestrator.handlers.estado_actual_handler import EstadoActualHandlerMixin
from domain.services.orchestrator.handlers.predicciones_handler import PrediccionesHandlerMixin
from domain.services.orchestrator.handlers.anomalias_handler import AnomaliaHandlerMixin
from domain.services.orchestrator.handlers.cu_pnt_handler import CuPntHandlerMixin
from domain.services.orchestrator.handlers.metricas_handler import MetricasHandlerMixin
from domain.services.orchestrator.handlers.informe_handler import InformeHandlerMixin
from domain.services.orchestrator.handlers.libre_noticias_handler import LibreNoticiasHandlerMixin
from domain.services.orchestrator.utils.serializers import sanitize_numpy_types

logger = logging.getLogger(__name__)


class ChatbotOrchestratorService(
    EstadoActualHandlerMixin,
    PrediccionesHandlerMixin,
    AnomaliaHandlerMixin,
    CuPntHandlerMixin,
    MetricasHandlerMixin,
    InformeHandlerMixin,
    LibreNoticiasHandlerMixin,
):
    """
    Orquestador central para el chatbot.

    Los handlers están distribuidos en mixins; esta clase provee:
    - __init__ (inyección de servicios)
    - orchestrate (método público)
    - _get_intent_handler (mapeo de 50+ intents)
    - _create_error_response / _sanitize_numpy_types / _serialize_anomalia
    """

    SERVICE_TIMEOUT = 10
    TOTAL_TIMEOUT = 60

    def __init__(self) -> None:
        self.generation_service = GenerationService()
        self.hydrology_service = HydrologyService()
        self.metrics_service = MetricsService()
        self.intelligent_analysis = IntelligentAnalysisService()
        self.executive_report_service = ExecutiveReportService()

        # Cache diario del informe IA — Redis principal + dict local fallback
        self._informe_ia_cache: Dict[str, Any] = {}
        try:
            from infrastructure.cache.redis_client import get_redis_client
            self._redis = get_redis_client()
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Redis no disponible: {e}")
            self._redis = None

        try:
            self.predictions_service = PredictionsService()
        except Exception as e:
            logger.warning(f"PredictionsService no disponible: {e}")
            self.predictions_service = None

        try:
            self.news_service = NewsService()
        except Exception as e:
            logger.warning(f"NewsService no disponible: {e}")
            self.news_service = None

    # ─────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL
    # ─────────────────────────────────────────────────────────

    async def orchestrate(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """Método principal de orquestación."""
        start_time = datetime.utcnow()

        logger.info(
            f"[ORCHESTRATOR] SessionId: {request.sessionId} | "
            f"Intent: {request.intent} | Parameters: {request.parameters}"
        )

        try:
            handler = self._get_intent_handler(request.intent)

            if not handler:
                return self._create_error_response(
                    request=request,
                    message=f"Intent '{request.intent}' no reconocido",
                    errors=[ErrorDetail(
                        code="UNKNOWN_INTENT",
                        message=f"El intent '{request.intent}' no está soportado",
                        field="intent",
                    )],
                )

            data, errors = await asyncio.wait_for(
                handler(request.parameters),
                timeout=self.TOTAL_TIMEOUT,
            )

            if errors:
                if data:
                    status_code = "PARTIAL_SUCCESS"
                    message = "Consulta ejecutada parcialmente. Algunos servicios no disponibles."
                else:
                    status_code = "ERROR"
                    message = "Error al procesar la solicitud"
            else:
                status_code = "SUCCESS"
                message = "Consulta ejecutada exitosamente"

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"[ORCHESTRATOR] SessionId: {request.sessionId} | "
                f"Status: {status_code} | Elapsed: {elapsed:.2f}s"
            )

            return OrchestratorResponse(
                status=status_code,
                message=message,
                data=self._sanitize_numpy_types(data or {}),
                errors=errors,
                timestamp=datetime.utcnow(),
                sessionId=request.sessionId,
                intent=request.intent,
            )

        except asyncio.TimeoutError:
            logger.error(f"[ORCHESTRATOR] Timeout total para sessionId: {request.sessionId}")
            return self._create_error_response(
                request=request,
                message="La solicitud tardó demasiado en procesarse",
                errors=[ErrorDetail(
                    code="TOTAL_TIMEOUT",
                    message="El procesamiento excedió el tiempo máximo permitido",
                )],
            )
        except Exception as e:
            logger.error(
                f"[ORCHESTRATOR] Error inesperado para sessionId {request.sessionId}: {e}",
                exc_info=True,
            )
            return self._create_error_response(
                request=request,
                message="Error interno del servidor",
                errors=[ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Ocurrió un error inesperado al procesar la solicitud",
                )],
            )

    # ─────────────────────────────────────────────────────────
    # MAPEO DE INTENTS
    # ─────────────────────────────────────────────────────────

    def _get_intent_handler(self, intent: str):
        """Mapea un intent a su handler correspondiente."""
        intent_map = {
            # ── Menú principal ──────────────────────────────────────────
            "estado_actual": self._handle_estado_actual,
            "como_esta_sistema": self._handle_estado_actual,
            "status_sistema": self._handle_estado_actual,

            "predicciones_sector": self._handle_predicciones_sector,
            "predicciones_indicadores": self._handle_predicciones_sector,

            "anomalias_sector": self._handle_anomalias_detectadas,
            "anomalias_detectadas": self._handle_anomalias_detectadas,
            "problemas_sistema": self._handle_anomalias_detectadas,
            "detectar_anomalias": self._handle_anomalias_detectadas,
            "alertas": self._handle_anomalias_detectadas,

            "mas_informacion": self._handle_menu,

            # ── Sub-opciones de "Más información" ───────────────────────
            "informe_ejecutivo": self._handle_informe_ejecutivo,
            "generar_informe": self._handle_informe_ejecutivo,
            "informe_completo": self._handle_informe_ejecutivo,
            "reporte_ejecutivo": self._handle_informe_ejecutivo,

            "noticias_sector": self._handle_noticias_sector,
            "noticias": self._handle_noticias_sector,
            "news": self._handle_noticias_sector,

            "pregunta_libre": self._handle_pregunta_libre,
            "pregunta": self._handle_pregunta_libre,
            "consulta_libre": self._handle_pregunta_libre,

            # ── Intents específicos ─────────────────────────────────────
            "generacion_electrica": self._handle_generacion_electrica,
            "consultar_generacion": self._handle_generacion_electrica,
            "generacion": self._handle_generacion_electrica,

            "hidrologia": self._handle_hidrologia,
            "consultar_embalses": self._handle_hidrologia,
            "embalses": self._handle_hidrologia,
            "nivel_embalses": self._handle_hidrologia,

            "demanda_sistema": self._handle_demanda_sistema,
            "consultar_demanda": self._handle_demanda_sistema,
            "demanda": self._handle_demanda_sistema,

            "precio_bolsa": self._handle_precio_bolsa,
            "precios_bolsa": self._handle_precio_bolsa,
            "consultar_precios": self._handle_precio_bolsa,

            "predicciones": self._handle_predicciones,
            "pronostico": self._handle_predicciones,
            "forecast": self._handle_predicciones,

            "metricas_generales": self._handle_metricas_generales,
            "resumen_sistema": self._handle_metricas_generales,
            "estado_sistema": self._handle_metricas_generales,
            "resumen_completo": self._handle_metricas_generales,

            # ── Menú / ayuda ────────────────────────────────────────────
            "menu": self._handle_menu,
            "ayuda": self._handle_menu,
            "help": self._handle_menu,
            "opciones": self._handle_menu,
            "inicio": self._handle_menu,
            "start": self._handle_menu,

            # ── Costo unitario, pérdidas NT, simulación (Fase 7) ────────
            "cu_actual": self._handle_cu_actual,
            "costo_unitario": self._handle_cu_actual,
            "tarifa_energia": self._handle_cu_actual,
            "cop_kwh": self._handle_cu_actual,

            "perdidas_nt": self._handle_perdidas_nt,
            "perdidas_no_tecnicas": self._handle_perdidas_nt,
            "hurto_energia": self._handle_perdidas_nt,

            "simulacion": self._handle_simulacion,
            "simular": self._handle_simulacion,
            "escenario": self._handle_simulacion,
            "que_pasa_si": self._handle_simulacion,
        }
        return intent_map.get(intent.lower())

    # ─────────────────────────────────────────────────────────
    # UTILIDADES
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_numpy_types(obj: Any) -> Any:
        """Delega a la función de módulo para evitar recursión de clase."""
        return sanitize_numpy_types(obj)

    def _serialize_anomalia(self, anomalia: Anomalia) -> Dict[str, Any]:
        """Convierte un objeto Anomalia a diccionario para JSON."""
        return {
            'sector': anomalia.sector,
            'metrica': anomalia.metric,
            'severidad': anomalia.severity.name,
            'severidad_nivel': anomalia.severity.value,
            'valor_actual': anomalia.current_value,
            'valor_esperado': anomalia.expected_value,
            'umbral': anomalia.threshold,
            'descripcion': anomalia.description,
            'timestamp': anomalia.timestamp.isoformat() if anomalia.timestamp else None,
        }

    def _create_error_response(
        self,
        request: OrchestratorRequest,
        message: str,
        errors: List[ErrorDetail],
    ) -> OrchestratorResponse:
        """Crea una respuesta de error estándar."""
        return OrchestratorResponse(
            status="ERROR",
            message=message,
            data={},
            errors=errors,
            timestamp=datetime.utcnow(),
            sessionId=request.sessionId,
            intent=request.intent,
        )
