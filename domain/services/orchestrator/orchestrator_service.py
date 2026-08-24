"""
ChatbotOrchestratorService — slim orchestrator.

Hereda comportamiento de todos los handler-mixins. Esta clase solo
contiene el núcleo de infra: __init__, orchestrate, _get_intent_handler,
_create_error_response y dos utilidades estáticas.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

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
from domain.services.orchestrator.handlers.subsidios_handler import SubsidiosHandlerMixin
from domain.services.orchestrator.handlers.comunidades_handler import ComunidadesHandlerMixin
from domain.services.orchestrator.handlers.supervision_handler import SupervisionHandlerMixin
from domain.services.orchestrator.handlers.presupuesto_handler import PresupuestoHandlerMixin
from domain.services.orchestrator.handlers.ontologia_handler import OntologiaHandlerMixin
from domain.services.orchestrator.handlers.hidrocarburos_handler import HidrocarburosHandlerMixin
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
    SubsidiosHandlerMixin,
    ComunidadesHandlerMixin,
    SupervisionHandlerMixin,
    PresupuestoHandlerMixin,
    OntologiaHandlerMixin,
    HidrocarburosHandlerMixin,
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

    # Excepciones puntuales al TOTAL_TIMEOUT general — hallazgo real
    # (2026-08-22): 'informe_ejecutivo' encadena hasta 3 llamadas
    # secuenciales con timeout propio (noticias ~15s + resumen ~20s +
    # generación IA ~60s = ~95s en el peor caso) — con TOTAL_TIMEOUT=60 el
    # límite general competía en carrera contra el timeout interno de la
    # IA, matando la tarea COMPLETA (sin dar oportunidad al respaldo sin IA
    # `_generar_informe_fallback`, que sí existe y funciona) en vez de
    # dejar que la degradación con gracia ya implementada se completara.
    # Reproducido en vivo durante un bloqueo de red hacia Gemini —
    # confirmado que el propio orquestador, no solo el proveedor de IA,
    # era el punto de falla real.
    _TIMEOUTS_EXTENDIDOS = {
        # 150s (no 120s): el timeout interno de la llamada a IA subió de
        # 60s a 90s el mismo día (2026-08-22) al agregarle failover real
        # Gemini→Groq (agent.completar() ahora puede intentar 2
        # proveedores en secuencia) — 120s ya no dejaba margen suficiente
        # sumado a los ~35s de pasos previos (noticias).
        "informe_ejecutivo": 150,
    }

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
                timeout=self._TIMEOUTS_EXTENDIDOS.get(request.intent, self.TOTAL_TIMEOUT),
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
            "panorama_climatico": self._handle_panorama_climatico,

            "anomalias_sector": self._handle_anomalias_detectadas,
            "anomalias_detectadas": self._handle_anomalias_detectadas,
            "problemas_sistema": self._handle_anomalias_detectadas,
            "detectar_anomalias": self._handle_anomalias_detectadas,
            "alertas": self._handle_anomalias_detectadas,

            "mas_informacion": self._handle_menu,
            "gestion_sector": self._handle_gestion_sector,
            "sector_energetico": self._handle_gestion_sector,
            "mas_opciones": self._handle_mas_opciones,

            # ── Tableros del portal ─────────────────────────────────────
            "comunidades_menu": self._handle_comunidades_menu,
            "comunidades": self._handle_comunidades_menu,
            "comunidades_implementadas": self._handle_comunidades_implementadas,
            "contratos_or_menu": self._handle_contratos_or_menu,
            "contratos_or": self._handle_contratos_or_menu,
            "fenoge_menu": self._handle_fenoge_menu,
            "fenoge": self._handle_fenoge_menu,
            "colombia_solar_menu": self._handle_colombia_solar_menu,
            "colombia_solar": self._handle_colombia_solar_menu,
            "supervision_menu": self._handle_supervision_menu,
            "supervision": self._handle_supervision_menu,
            "presupuesto_menu": self._handle_presupuesto_menu,
            "presupuesto": self._handle_presupuesto_menu,
            "subsidios_menu": self._handle_subsidios_menu,
            "subsidios": self._handle_subsidios_menu,
            "subsidios_pagos_menu": self._handle_subsidios_pagos_menu,
            "subsidios_deficit_historico": self._handle_subsidios_deficit_historico,
            "subsidios_validaciones": self._handle_subsidios_validaciones,

            "hidrocarburos_presupuesto": self._handle_hidrocarburos_presupuesto,
            "hidrocarburos_produccion": self._handle_hidrocarburos_produccion,

            "resumen_departamento": self._handle_resumen_departamento,
            "vista_departamento": self._handle_resumen_departamento,
            "ontologia_departamento": self._handle_resumen_departamento,
            "resumen_municipio": self._handle_resumen_municipio,
            "vista_municipio": self._handle_resumen_municipio,

            # ── Fase 9: tools del Asistente IA (ontología/RAG/grafo/riesgo) ──
            "buscar_texto_rag": self._handle_buscar_texto_rag,
            "buscar_empresa": self._handle_buscar_empresa,
            "vecindario_empresa": self._handle_vecindario_empresa,
            "riesgo_atraso_contratos_or": self._handle_riesgo_atraso_or,
            "listar_proyectos": self._handle_listar_proyectos,

            # ── Fase 12: ontología de métricas y variables ──────────────
            "buscar_metrica": self._handle_buscar_metrica,
            "calidad_datos_ontologia": self._handle_calidad_datos_ontologia,
            "detalle_recurso": self._handle_detalle_recurso,
            "detalle_contrato": self._handle_detalle_contrato,
            "resumen_portal": self._handle_resumen_portal,

            # ── Sub-opciones de "Más información" ───────────────────────
            "informe_ejecutivo": self._handle_informe_ejecutivo,
            "generar_informe": self._handle_informe_ejecutivo,
            "informe_completo": self._handle_informe_ejecutivo,
            "reporte_ejecutivo": self._handle_informe_ejecutivo,

            "noticias_sector": self._handle_noticias_sector,
            "noticias": self._handle_noticias_sector,
            "news": self._handle_noticias_sector,

            "noticias_hidrocarburos": self._handle_noticias_hidrocarburos,
            "hidrocarburos": self._handle_noticias_hidrocarburos,

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
            "cu_evolucion": self._handle_cu_evolucion,
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

            # ── Subsidios energéticos — 8 módulos ──────────────────────
            "subsidios_deuda_total":   self._handle_subsidios_deuda_total,
            "subsidios_deuda_empresa": self._handle_subsidios_deuda_empresa,
            "subsidios_trimestre":     self._handle_subsidios_trimestre,
            "subsidios_resoluciones":  self._handle_subsidios_resoluciones,
            "subsidios_estado":        self._handle_subsidios_estado,
            "subsidios_pct_pagado":    self._handle_subsidios_pct_pagado,
            "subsidios_deuda_fondo":   self._handle_subsidios_deuda_fondo,
            "subsidios_pagado_anio":   self._handle_subsidios_pagado_anio,
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
