"""
Servicio Orquestador para Chatbot

Este servicio actúa como orquestador central que recibe intents del chatbot
y los mapea a los servicios backend apropiados del Portal Energético MME.

Implementa:
- Mapeo de intents a servicios
- Manejo de timeouts
- Gestión de errores
- Respuestas parciales cuando algunos servicios fallan
- Logging estructurado

Autor: Portal Energético MME
Fecha: 9 de febrero de 2026
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, date, timedelta
from functools import wraps

from domain.services.generation_service import GenerationService
from domain.services.hydrology_service import HydrologyService
from domain.services.metrics_service import MetricsService
from domain.services.predictions_service import PredictionsService
from domain.services.intelligent_analysis_service import (
    IntelligentAnalysisService,
    SeverityLevel,
    Anomalia
)
from domain.services.executive_report_service import ExecutiveReportService
from domain.services.confianza_politica import (
    get_confianza_politica,
    obtener_disclaimer,
    enriquecer_ficha_con_confianza,
)
from domain.services.news_service import NewsService
from domain.schemas.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    ErrorDetail
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DECORADORES
# ═══════════════════════════════════════════════════════════

def handle_service_error(func):
    """Decorador para capturar errores de servicios"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TimeoutError:
            logger.warning(f"Timeout en servicio {func.__name__}")
            return None, ErrorDetail(
                code="TIMEOUT",
                message="El servicio tardó demasiado en responder"
            )
        except Exception as e:
            logger.error(f"Error en servicio {func.__name__}: {str(e)}", exc_info=True)
            return None, ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar el servicio"
            )
    return wrapper


# ═══════════════════════════════════════════════════════════
# SERVICIO ORQUESTADOR
# ═══════════════════════════════════════════════════════════

class ChatbotOrchestratorService:
    """
    Orquestador central para el chatbot
    
    Mapea intents a servicios backend y gestiona la integración.
    """
    
    # Timeout por servicio (10 segundos como especifica el documento)
    SERVICE_TIMEOUT = 10
    
    # Timeout total de la request (30 segundos)
    TOTAL_TIMEOUT = 30
    
    def __init__(self):
        """Inicializa el orquestador"""
        self.generation_service = GenerationService()
        self.hydrology_service = HydrologyService()
        self.metrics_service = MetricsService()
        
        # Servicio de análisis inteligente (clave para detectar anomalías)
        self.intelligent_analysis = IntelligentAnalysisService()
        
        # Servicio de informes ejecutivos (completo con análisis estadístico)
        self.executive_report_service = ExecutiveReportService()
        
        # El predictions_service puede no estar siempre disponible
        try:
            self.predictions_service = PredictionsService()
        except Exception as e:
            logger.warning(f"PredictionsService no disponible: {e}")
            self.predictions_service = None
        
        # Servicio de noticias del sector (puede no tener API key)
        try:
            self.news_service = NewsService()
        except Exception as e:
            logger.warning(f"NewsService no disponible: {e}")
            self.news_service = None
    
    # ─────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL
    # ─────────────────────────────────────────────────────────
    
    async def orchestrate(
        self, 
        request: OrchestratorRequest
    ) -> OrchestratorResponse:
        """
        Método principal de orquestación
        
        Args:
            request: Request del chatbot con sessionId, intent y parameters
            
        Returns:
            OrchestratorResponse con status, message, data y errors
        """
        start_time = datetime.utcnow()
        
        logger.info(
            f"[ORCHESTRATOR] SessionId: {request.sessionId} | "
            f"Intent: {request.intent} | Parameters: {request.parameters}"
        )
        
        try:
            # Mapear intent a handler con timeout total
            handler = self._get_intent_handler(request.intent)
            
            if not handler:
                return self._create_error_response(
                    request=request,
                    message=f"Intent '{request.intent}' no reconocido",
                    errors=[ErrorDetail(
                        code="UNKNOWN_INTENT",
                        message=f"El intent '{request.intent}' no está soportado",
                        field="intent"
                    )]
                )
            
            # Ejecutar handler con timeout
            data, errors = await asyncio.wait_for(
                handler(request.parameters),
                timeout=self.TOTAL_TIMEOUT
            )
            
            # Determinar status según errores
            if errors:
                if data:
                    # Hay datos parciales
                    status_code = "PARTIAL_SUCCESS"
                    message = "Consulta ejecutada parcialmente. Algunos servicios no disponibles."
                else:
                    # Sin datos, solo errores
                    status_code = "ERROR"
                    message = "Error al procesar la solicitud"
            else:
                # Todo exitoso
                status_code = "SUCCESS"
                message = "Consulta ejecutada exitosamente"
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"[ORCHESTRATOR] SessionId: {request.sessionId} | "
                f"Status: {status_code} | Elapsed: {elapsed:.2f}s"
            )
            
            # Sanitizar tipos numpy antes de serializar
            sanitized_data = self._sanitize_numpy_types(data or {})
            
            return OrchestratorResponse(
                status=status_code,
                message=message,
                data=sanitized_data,
                errors=errors,
                timestamp=datetime.utcnow(),
                sessionId=request.sessionId,
                intent=request.intent
            )
            
        except asyncio.TimeoutError:
            logger.error(
                f"[ORCHESTRATOR] Timeout total para sessionId: {request.sessionId}"
            )
            return self._create_error_response(
                request=request,
                message="La solicitud tardó demasiado en procesarse",
                errors=[ErrorDetail(
                    code="TOTAL_TIMEOUT",
                    message="El procesamiento excedió el tiempo máximo permitido"
                )]
            )
        except Exception as e:
            logger.error(
                f"[ORCHESTRATOR] Error inesperado para sessionId {request.sessionId}: {e}",
                exc_info=True
            )
            return self._create_error_response(
                request=request,
                message="Error interno del servidor",
                errors=[ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Ocurrió un error inesperado al procesar la solicitud"
                )]
            )
    
    # ─────────────────────────────────────────────────────────
    # MAPEO DE INTENTS
    # ─────────────────────────────────────────────────────────
    
    def _get_intent_handler(self, intent: str):
        """
        Mapea un intent a su handler correspondiente
        
        Args:
            intent: Nombre del intent
            
        Returns:
            Función handler o None si no existe
        """
        intent_map = {
            # ═══════════════════════════════════════════════════════════
            # MENÚ PRINCIPAL (4 opciones del Viceministro)
            # ═══════════════════════════════════════════════════════════
            
            # 1️⃣ Estado actual (3 fichas: Generación, Precio, Embalses)
            "estado_actual": self._handle_estado_actual,
            "como_esta_sistema": self._handle_estado_actual,
            "status_sistema": self._handle_estado_actual,
            
            # 2️⃣ Predicciones del sector (3 indicadores + horizonte)
            "predicciones_sector": self._handle_predicciones_sector,
            "predicciones_indicadores": self._handle_predicciones_sector,
            
            # 3️⃣ Anomalías detectadas (estado actual + predicciones)
            "anomalias_sector": self._handle_anomalias_detectadas,
            "anomalias_detectadas": self._handle_anomalias_detectadas,
            "problemas_sistema": self._handle_anomalias_detectadas,
            "detectar_anomalias": self._handle_anomalias_detectadas,
            "alertas": self._handle_anomalias_detectadas,
            
            # 4️⃣ Más información → sub-menú
            "mas_informacion": self._handle_menu,  # Muestra sub-menú
            
            # ═══════════════════════════════════════════════════════════
            # SUB-OPCIONES DE "MÁS INFORMACIÓN"
            # ═══════════════════════════════════════════════════════════
            
            # Informe ejecutivo completo
            "informe_ejecutivo": self._handle_informe_ejecutivo,
            "generar_informe": self._handle_informe_ejecutivo,
            "informe_completo": self._handle_informe_ejecutivo,
            "reporte_ejecutivo": self._handle_informe_ejecutivo,
            
            # Noticias del sector
            "noticias_sector": self._handle_noticias_sector,
            "noticias": self._handle_noticias_sector,
            "news": self._handle_noticias_sector,
            
            # Pregunta libre (el usuario escribe lo que quiera)
            "pregunta_libre": self._handle_pregunta_libre,
            "pregunta": self._handle_pregunta_libre,
            "consulta_libre": self._handle_pregunta_libre,
            
            # ═══════════════════════════════════════════════════════════
            # INTENTS ESPECÍFICOS (siguen funcionando para preguntas libres)
            # ═══════════════════════════════════════════════════════════
            
            # Generación eléctrica
            "generacion_electrica": self._handle_generacion_electrica,
            "consultar_generacion": self._handle_generacion_electrica,
            "generacion": self._handle_generacion_electrica,
            
            # Hidrología
            "hidrologia": self._handle_hidrologia,
            "consultar_embalses": self._handle_hidrologia,
            "embalses": self._handle_hidrologia,
            "nivel_embalses": self._handle_hidrologia,
            
            # Demanda del sistema
            "demanda_sistema": self._handle_demanda_sistema,
            "consultar_demanda": self._handle_demanda_sistema,
            "demanda": self._handle_demanda_sistema,
            
            # Precios de bolsa
            "precio_bolsa": self._handle_precio_bolsa,
            "precios_bolsa": self._handle_precio_bolsa,
            "consultar_precios": self._handle_precio_bolsa,
            
            # Predicciones por fuente (handler original más detallado)
            "predicciones": self._handle_predicciones,
            "pronostico": self._handle_predicciones,
            "forecast": self._handle_predicciones,
            
            # Métricas generales
            "metricas_generales": self._handle_metricas_generales,
            "resumen_sistema": self._handle_metricas_generales,
            "estado_sistema": self._handle_metricas_generales,
            "resumen_completo": self._handle_metricas_generales,
            
            # ═══════════════════════════════════════════════════════════
            # MENÚ / AYUDA
            # ═══════════════════════════════════════════════════════════
            "menu": self._handle_menu,
            "ayuda": self._handle_menu,
            "help": self._handle_menu,
            "opciones": self._handle_menu,
            "inicio": self._handle_menu,
            "start": self._handle_menu,
        }
        
        return intent_map.get(intent.lower())
    
    # ─────────────────────────────────────────────────────────
    # HANDLERS DE INTENTS
    # ─────────────────────────────────────────────────────────
    
    # ═══════════════════════════════════════════════════════════
    # HANDLERS PRINCIPALES - LAS 2 PREGUNTAS CLAVE 
    # ═══════════════════════════════════════════════════════════
    
    @handle_service_error
    async def _handle_estado_actual(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler principal 1️⃣: Estado actual del sector
        
        Retorna SOLO los 3 indicadores clave del Viceministro:
        - Generación Total del Sistema (GWh)
        - Precio de Bolsa Nacional (COP/kWh)
        - Porcentaje de Embalses (%)
        """
        data = {}
        errors = []
        fichas = []
        
        # Fechas de consulta
        hoy = date.today()
        ayer = hoy - timedelta(days=1)
        hace_7_dias = hoy - timedelta(days=7)
        
        # ─── FICHA 1: GENERACIÓN TOTAL DEL SISTEMA ───
        try:
            df_gen = await asyncio.wait_for(
                asyncio.to_thread(
                    self.generation_service.get_daily_generation_system,
                    hace_7_dias,
                    ayer
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if not df_gen.empty:
                # Último día disponible
                ultimo_dia = df_gen.sort_values('fecha').iloc[-1]
                valor_ultimo = float(ultimo_dia['valor_gwh'])
                # Normalizar fecha a YYYY-MM-DD (sin hora ni timezone)
                fecha_raw = ultimo_dia['fecha']
                fecha_dato = fecha_raw.strftime('%Y-%m-%d') if hasattr(fecha_raw, 'strftime') else str(fecha_raw)[:10]
                
                # Promedio de la semana para contexto
                promedio_semana = float(df_gen['valor_gwh'].mean())
                variacion = ((valor_ultimo - promedio_semana) / promedio_semana * 100) if promedio_semana > 0 else 0
                
                fichas.append({
                    "indicador": "Generación Total del Sistema",
                    "emoji": "⚡",
                    "valor": round(valor_ultimo, 2),
                    "unidad": "GWh",
                    "fecha": fecha_dato,
                    "contexto": {
                        "promedio_7_dias": round(promedio_semana, 2),
                        "variacion_vs_promedio_pct": round(variacion, 1),
                        "tendencia": "↗️ Por encima" if variacion > 2 else ("↘️ Por debajo" if variacion < -2 else "➡️ Estable"),
                        "referencia_comparacion": "Comparado con el promedio de los últimos 7 días."
                    }
                })
            else:
                fichas.append({
                    "indicador": "Generación Total del Sistema",
                    "emoji": "⚡",
                    "valor": None,
                    "unidad": "GWh",
                    "error": "Sin datos disponibles"
                })
        except Exception as e:
            logger.warning(f"Error obteniendo generación: {e}")
            fichas.append({
                "indicador": "Generación Total del Sistema",
                "emoji": "⚡",
                "valor": None,
                "unidad": "GWh",
                "error": "Error consultando datos"
            })
        
        # ─── FICHA 2: PRECIO DE BOLSA NACIONAL ───
        try:
            df_precio = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'PrecBolsNaci',
                    hace_7_dias.isoformat(),
                    ayer.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if not df_precio.empty and 'Value' in df_precio.columns:
                # Último valor disponible
                df_precio_sorted = df_precio.sort_values('Date') if 'Date' in df_precio.columns else df_precio
                ultimo_precio = float(df_precio_sorted['Value'].iloc[-1])
                # Normalizar fecha a YYYY-MM-DD (sin hora ni timezone)
                if 'Date' in df_precio_sorted.columns:
                    fecha_raw_precio = df_precio_sorted['Date'].iloc[-1]
                    fecha_precio = fecha_raw_precio.strftime('%Y-%m-%d') if hasattr(fecha_raw_precio, 'strftime') else str(fecha_raw_precio)[:10]
                else:
                    fecha_precio = ayer.isoformat()
                
                promedio_precio = float(df_precio['Value'].mean())
                variacion_precio = ((ultimo_precio - promedio_precio) / promedio_precio * 100) if promedio_precio > 0 else 0
                
                fichas.append({
                    "indicador": "Precio de Bolsa Nacional",
                    "emoji": "💰",
                    "valor": round(ultimo_precio, 2),
                    "unidad": "COP/kWh",
                    "fecha": fecha_precio,
                    "contexto": {
                        "promedio_7_dias": round(promedio_precio, 2),
                        "maximo_7_dias": round(float(df_precio['Value'].max()), 2),
                        "minimo_7_dias": round(float(df_precio['Value'].min()), 2),
                        "variacion_vs_promedio_pct": round(variacion_precio, 1),
                        "tendencia": "↗️ Al alza" if variacion_precio > 5 else ("↘️ A la baja" if variacion_precio < -5 else "➡️ Estable"),
                        "referencia_comparacion": "Comparado con el promedio de los últimos 7 días."
                    }
                })
            else:
                fichas.append({
                    "indicador": "Precio de Bolsa Nacional",
                    "emoji": "💰",
                    "valor": None,
                    "unidad": "COP/kWh",
                    "error": "Sin datos disponibles"
                })
        except Exception as e:
            logger.warning(f"Error obteniendo precio: {e}")
            fichas.append({
                "indicador": "Precio de Bolsa Nacional",
                "emoji": "💰",
                "valor": None,
                "unidad": "COP/kWh",
                "error": "Error consultando datos"
            })
        
        # ─── FICHA 3: PORCENTAJE DE EMBALSES ───
        try:
            nivel_pct, energia_gwh, fecha_embalses = await asyncio.wait_for(
                asyncio.to_thread(
                    self.hydrology_service.get_reservas_hidricas,
                    ayer.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            # Si ayer no hay datos, intentar con antes de ayer
            if nivel_pct is None:
                anteayer = hoy - timedelta(days=2)
                nivel_pct, energia_gwh, fecha_embalses = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.hydrology_service.get_reservas_hidricas,
                        anteayer.isoformat()
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
            
            if nivel_pct is not None:
                # Evaluar estado con percentiles históricos del mismo mes
                estado_embalse, referencia_hist = self._evaluar_nivel_embalses_historico(nivel_pct)
                
                fichas.append({
                    "indicador": "Porcentaje de Embalses",
                    "emoji": "💧",
                    "valor": round(nivel_pct, 2),
                    "unidad": "%",
                    "fecha": fecha_embalses or ayer.isoformat(),
                    "contexto": {
                        "energia_embalsada_gwh": round(energia_gwh, 2) if energia_gwh else None,
                        "estado": estado_embalse,
                        "referencia_historica": referencia_hist
                    }
                })
            else:
                fichas.append({
                    "indicador": "Porcentaje de Embalses",
                    "emoji": "💧",
                    "valor": None,
                    "unidad": "%",
                    "error": "Sin datos disponibles"
                })
        except Exception as e:
            logger.warning(f"Error obteniendo embalses: {e}")
            fichas.append({
                "indicador": "Porcentaje de Embalses",
                "emoji": "💧",
                "valor": None,
                "unidad": "%",
                "error": "Error consultando datos"
            })
        
        data['fichas'] = fichas
        data['fecha_consulta'] = datetime.utcnow().isoformat()
        data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}
        
        # Verificar si hay fichas sin datos
        fichas_con_error = [f for f in fichas if f.get('valor') is None]
        if fichas_con_error:
            for f in fichas_con_error:
                errors.append(ErrorDetail(
                    code="PARTIAL_DATA",
                    message=f"No se obtuvieron datos para: {f['indicador']}"
                ))
        
        logger.info(
            f"[ESTADO_ACTUAL] Fichas generadas: {len(fichas)} | "
            f"Con datos: {len(fichas) - len(fichas_con_error)}/{len(fichas)}"
        )
        
        return data, errors
    
    # ── Helper: Evaluar nivel de embalses con percentiles históricos ──
    
    def _evaluar_nivel_embalses_historico(
        self,
        nivel_pct: float,
    ) -> Tuple[str, str]:
        """
        Evalúa el nivel de embalses actual comparándolo con los
        percentiles 25/75 del histórico para el mismo mes del año
        (datos 2020-presente).
        
        Returns:
            (estado_emoji_texto, referencia_historica_texto)
            Ejemplo: ("🟢 Nivel alto", "Por encima del percentil 75 del histórico 2020-2025 para este mes")
        """
        try:
            from infrastructure.database.manager import db_manager
            hoy = date.today()
            mes_actual = hoy.month
            
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND EXTRACT(MONTH FROM fecha) = %s
                    AND fecha < %s
                    GROUP BY fecha
                    HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                )
                SELECT vol / cap * 100 as pct
                FROM emb_diario
                ORDER BY fecha ASC
            """
            df = db_manager.query_df(query, params=(mes_actual, hoy.isoformat()))
            
            if df is not None and len(df) >= 10:
                import numpy as _np
                p25 = float(_np.percentile(df['pct'].values, 25))
                p75 = float(_np.percentile(df['pct'].values, 75))
                avg = float(df['pct'].mean())
                anio_min = max(2020, hoy.year - 6)
                
                # Nombre del mes en español para texto didáctico
                MESES_ES = {
                    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
                }
                mes_nombre = MESES_ES.get(mes_actual, str(mes_actual))
                
                if nivel_pct >= p75:
                    estado = "🟢 Nivel alto"
                    ref = (
                        f"Por encima del 75% de los valores históricos "
                        f"de {mes_nombre} ({anio_min}–{hoy.year - 1}). "
                        f"Percentil 75 ≈ {p75:.0f}%, promedio ≈ {avg:.0f}%."
                    )
                elif nivel_pct >= p25:
                    estado = "🟡 Nivel medio"
                    ref = (
                        f"Dentro del rango típico de {mes_nombre} "
                        f"({anio_min}–{hoy.year - 1}): entre {p25:.0f}% y {p75:.0f}%. "
                        f"Promedio ≈ {avg:.0f}%."
                    )
                else:
                    estado = "🟠 Nivel bajo"
                    ref = (
                        f"Por debajo del 25% de los valores históricos "
                        f"de {mes_nombre} ({anio_min}–{hoy.year - 1}). "
                        f"Percentil 25 ≈ {p25:.0f}%, promedio ≈ {avg:.0f}%."
                    )
                
                return estado, ref
            else:
                # Fallback: sin suficiente histórico, usar umbrales fijos
                logger.info("[EMBALSES] Histórico insuficiente, usando umbrales fijos")
        except Exception as e:
            logger.warning(f"Error calculando percentiles embalses: {e}")
        
        # Fallback simple (mismos umbrales originales)
        if nivel_pct >= 70:
            return "🟢 Nivel alto", "Referencia: umbral fijo ≥70%"
        elif nivel_pct >= 50:
            return "🟡 Nivel medio", "Referencia: umbral fijo 50-70%"
        elif nivel_pct >= 30:
            return "🟠 Nivel bajo", "Referencia: umbral fijo 30-50%"
        else:
            return "🔴 Nivel crítico", "Referencia: umbral fijo <30%"
    
    @handle_service_error
    async def _handle_anomalias_detectadas(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler 2️⃣: ¿Qué problemas hay?
        
        Detecta anomalías comparando el último dato real de cada indicador
        clave contra:
          1. Promedio histórico 30 días (delta_hist).
          2. Valor predicho para esa fecha, si existe (delta_pred).
        
        Severidad:
          - < 15 %  →  sin anomalía
          - 15–30 % →  "alerta"
          - > 30 %  →  "crítico"
        
        Solo lectura — no modifica nada.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        
        try:
            anomalias = await self._detect_anomalias_clave()
            
            # Ordenar por severidad descendente (crítico primero)
            orden_sev = {'crítico': 0, 'alerta': 1, 'normal': 2}
            anomalias.sort(key=lambda a: orden_sev.get(a.get('severidad', 'normal'), 9))
            
            # Filtrar solo las que son anomalía real (severidad != normal)
            anomalias_reales = [a for a in anomalias if a.get('severidad') != 'normal']
            
            data['anomalias'] = anomalias_reales
            data['total_evaluadas'] = len(anomalias)
            data['total_anomalias'] = len(anomalias_reales)
            data['fecha_analisis'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            data['detalle_completo'] = anomalias  # incluye normales para debug
            
            # Resumen ejecutivo
            criticas = [a for a in anomalias_reales if a['severidad'] == 'crítico']
            alertas = [a for a in anomalias_reales if a['severidad'] == 'alerta']
            
            if criticas:
                nombres = ', '.join(a['indicador'] for a in criticas[:3])
                data['resumen'] = (
                    f"Se detectan {len(criticas)} anomalía(s) crítica(s) en {nombres}. "
                    f"Además hay {len(alertas)} alerta(s)."
                )
            elif alertas:
                nombres = ', '.join(a['indicador'] for a in alertas[:3])
                data['resumen'] = (
                    f"Se detectan {len(alertas)} alerta(s) de desvío en {nombres}. "
                    f"Sin anomalías críticas."
                )
            else:
                data['resumen'] = (
                    "No se detectaron anomalías significativas para la fecha "
                    "de los datos disponibles."
                )
            
            logger.info(
                f"[ANOMALIAS] Evaluadas={len(anomalias)} | "
                f"Críticas={len(criticas)} | Alertas={len(alertas)}"
            )
            
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El análisis de anomalías tardó demasiado"
            ))
        except Exception as e:
            logger.error(f"Error en _handle_anomalias_detectadas: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="ANALYSIS_ERROR",
                message="Error al detectar anomalías del sistema"
            ))
        
        return data, errors
    
    # ── Helper: Detectar anomalías clave (real vs hist vs pred) ───
    
    async def _detect_anomalias_clave(self) -> List[Dict[str, Any]]:
        """
        Evalúa los 3 indicadores clave comparando:
          - valor_actual (último dato real en BD)
          - avg_hist_30d (promedio 30 días reales)
          - valor_predicho (predicción para la fecha del dato real)
        
        Retorna lista de dicts con estructura limpia para el bot.
        """
        hoy = date.today()
        ayer = hoy - timedelta(days=1)
        hace_30 = hoy - timedelta(days=30)
        
        # ── Definir métricas a evaluar ──
        indicadores = [
            {
                'indicador': 'Generación Total',
                'emoji': '⚡',
                'unidad': 'GWh',
                'metric_id': 'Gene',
                'entity': 'Sistema',
                'fuente_pred': 'GENE_TOTAL',
            },
            {
                'indicador': 'Precio de Bolsa',
                'emoji': '💰',
                'unidad': 'COP/kWh',
                'metric_id': 'PrecBolsNaci',
                'entity': 'Sistema',
                'fuente_pred': 'PRECIO_BOLSA',
            },
            {
                'indicador': 'Embalses',
                'emoji': '💧',
                'unidad': '%',
                'metric_id': None,  # caso especial: cálculo VoluUtil/CapaUtil
                'entity': None,
                'fuente_pred': 'EMBALSES_PCT',
            },
        ]
        
        resultados = []
        
        for ind in indicadores:
            try:
                ficha = await self._evaluar_indicador_anomalia(
                    indicador=ind['indicador'],
                    emoji=ind['emoji'],
                    unidad=ind['unidad'],
                    metric_id=ind['metric_id'],
                    entity=ind['entity'],
                    fuente_pred=ind['fuente_pred'],
                    fecha_desde=hace_30,
                    fecha_hasta=ayer,
                )
                resultados.append(ficha)
            except Exception as e:
                logger.warning(f"Error evaluando anomalía {ind['indicador']}: {e}")
                resultados.append({
                    'indicador': ind['indicador'],
                    'emoji': ind['emoji'],
                    'unidad': ind['unidad'],
                    'severidad': 'normal',
                    'error': f"No se pudo evaluar: {str(e)}"
                })
        
        return resultados
    
    async def _evaluar_indicador_anomalia(
        self,
        indicador: str,
        emoji: str,
        unidad: str,
        metric_id: Optional[str],
        entity: Optional[str],
        fuente_pred: str,
        fecha_desde: date,
        fecha_hasta: date,
    ) -> Dict[str, Any]:
        """
        Evalúa un indicador individual para anomalías.
        
        Pasos:
        1. Obtener valor_actual (último dato real)
        2. Obtener avg_hist_30d (promedio 30 días)
        3. Obtener valor_predicho para fecha del dato real (si existe)
        4. Calcular desviaciones y severidad
        """
        resultado: Dict[str, Any] = {
            'indicador': indicador,
            'emoji': emoji,
            'unidad': unidad,
        }
        
        # ── 1. Valor actual y serie histórica ──
        if metric_id is None and fuente_pred == 'EMBALSES_PCT':
            # Caso especial: embalses calculados
            valor_actual, fecha_dato, avg_hist, dias_hist = await asyncio.to_thread(
                self._get_embalses_real_e_historico
            )
        else:
            valor_actual, fecha_dato, avg_hist, dias_hist = await asyncio.to_thread(
                self._get_real_e_historico, metric_id, entity, fecha_desde, fecha_hasta
            )
        
        if valor_actual is None or avg_hist is None:
            resultado['severidad'] = 'normal'
            resultado['error'] = 'Datos insuficientes para evaluar'
            return resultado
        
        resultado['valor_actual'] = round(valor_actual, 2)
        resultado['fecha_dato'] = fecha_dato
        resultado['promedio_hist_30d'] = round(avg_hist, 2)
        resultado['dias_con_datos'] = dias_hist
        
        # ── 2. Delta vs histórico ──
        if avg_hist != 0:
            delta_hist_pct = abs((valor_actual - avg_hist) / avg_hist) * 100
        else:
            delta_hist_pct = 0.0
        resultado['delta_hist_pct'] = round(delta_hist_pct, 1)
        
        # ── 3. Predicción para la fecha del dato real (si existe) ──
        # FASE 7 (política categórica): Usar nivel de POLITICA_CONFIANZA
        # como criterio principal para decidir si la predicción influye
        # en la severidad. Compatible con el umbral numérico FASE 8B.
        # Fuente: POLITICA_CONFIANZA_PREDICCIONES.md
        politica_pred = get_confianza_politica(fuente_pred)
        nivel_confianza = politica_pred['nivel']
        
        delta_pred_pct = None
        valor_predicho = None
        confianza_pred = None
        try:
            if self.predictions_service and fecha_dato:
                from infrastructure.database.manager import db_manager
                # FASE 7B: Buscar predicción más cercana (±2 días) en lugar
                # de match exacto.  Tras reentrenar, las predicciones
                # empiezan el día siguiente al último dato real, así que
                # la fecha del dato actual ya no está cubierta.
                df_pred = db_manager.query_df(
                    "SELECT valor_gwh_predicho, confianza "
                    "FROM predictions "
                    "WHERE fuente = %s "
                    "  AND fecha_prediccion::date BETWEEN "
                    "      (%s::date - interval '2 days') AND "
                    "      (%s::date + interval '2 days') "
                    "ORDER BY ABS(fecha_prediccion::date - %s::date) ASC, "
                    "       fecha_generacion DESC "
                    "LIMIT 1",
                    params=(fuente_pred, fecha_dato, fecha_dato, fecha_dato)
                )
                if df_pred is not None and not df_pred.empty:
                    valor_predicho = float(df_pred['valor_gwh_predicho'].iloc[0])
                    confianza_pred = float(df_pred['confianza'].iloc[0]) if 'confianza' in df_pred.columns and df_pred['confianza'].iloc[0] is not None else 0.0
                    resultado['valor_predicho'] = round(valor_predicho, 2)
                    resultado['confianza_prediccion'] = round(confianza_pred, 2)
                    
                    # FASE 7: Decidir uso de predicción según nivel categórico
                    # MUY_CONFIABLE / CONFIABLE → calcular delta_pred y usarlo
                    # ACEPTABLE / EXPERIMENTAL / DESCONOCIDO → excluir de severidad
                    if nivel_confianza in ('MUY_CONFIABLE', 'CONFIABLE'):
                        if valor_predicho != 0:
                            delta_pred_pct = abs((valor_actual - valor_predicho) / valor_predicho) * 100
                        resultado['delta_pred_pct'] = round(delta_pred_pct, 1) if delta_pred_pct is not None else None
                    else:
                        # ACEPTABLE / EXPERIMENTAL / DESCONOCIDO:
                        # Mostrar predicción como contexto, pero NO usarla para severidad
                        resultado['prediccion_excluida'] = True
                        resultado['motivo_exclusion'] = (
                            f"Nivel de confianza '{nivel_confianza}'. "
                            "Severidad basada solo en histórico 30 días."
                        )
                        logger.info(
                            f"[ANOMALIAS] Predicción de {indicador} excluida por política "
                            f"de confianza: nivel={nivel_confianza}, fuente={fuente_pred}"
                        )
        except Exception as e:
            logger.warning(f"No se pudo obtener predicción para {indicador}: {e}")
        
        # ── 4. Desviación máxima y severidad ──
        # FASE 7: Solo incluir delta_pred si la predicción NO fue excluida
        # (nivel MUY_CONFIABLE o CONFIABLE en POLITICA_CONFIANZA)
        desviaciones = [delta_hist_pct]
        if delta_pred_pct is not None and not resultado.get('prediccion_excluida'):
            desviaciones.append(delta_pred_pct)
        
        desviacion_pct = max(desviaciones) if desviaciones else 0.0
        resultado['desviacion_pct'] = round(desviacion_pct, 1)
        
        # Clasificar severidad — umbrales por métrica
        # Generación y embalses son más estables: 10%/25%
        # Precios son volátiles: 20%/40%
        # Calibración empírica (feb-2025 a feb-2026, delta vs avg30d):
        #   Gen:     8% días >10%, 0% días >25%  → bien calibrado
        #   Embalses: 8% días >10%, 0.3% días >25% → bien calibrado
        #   Precio: 52% días >20%, 25% días >40% → alta volatilidad intrínseca;
        #           con filtro de predicción (FASE 8B) la tasa efectiva baja
        #           significativamente. Revisar en FASE futura si se necesita ajustar.
        UMBRALES = {
            'Generación Total':  {'alerta': 10, 'critico': 25},
            'Embalses':          {'alerta': 10, 'critico': 25},
            'Precio de Bolsa':   {'alerta': 20, 'critico': 40},
        }
        umb = UMBRALES.get(indicador, {'alerta': 15, 'critico': 30})
        
        if desviacion_pct > umb['critico']:
            resultado['severidad'] = 'crítico'
        elif desviacion_pct > umb['alerta']:
            resultado['severidad'] = 'alerta'
        else:
            resultado['severidad'] = 'normal'
        
        # ── 5. Comentario descriptivo ──
        direccion = 'por encima' if valor_actual > avg_hist else 'por debajo'
        resultado['comentario'] = (
            f"{indicador}: {valor_actual:.1f} {unidad} ({direccion} del promedio "
            f"de 30 días: {avg_hist:.1f} {unidad}, desvío {desviacion_pct:.0f}%)"
        )
        if resultado.get('prediccion_excluida') and confianza_pred is not None:
            resultado['comentario'] += (
                f". ⚠️ Predicción disponible pero no utilizada en la evaluación "
                f"(confianza {confianza_pred:.0%}). "
                f"Detección basada únicamente en el promedio histórico de 30 días."
            )
        elif valor_predicho is not None and confianza_pred is not None:
            resultado['comentario'] += (
                f". Predicción para esa fecha: {valor_predicho:.1f} {unidad} "
                f"(confianza {confianza_pred:.0%})."
            )
        elif valor_predicho is not None:
            resultado['comentario'] += f". Predicción para esa fecha: {valor_predicho:.1f} {unidad}."
        
        # ── FASE 6/7: Enriquecer con política de confianza (POLITICA_CONFIANZA_PREDICCIONES.md) ──
        # Nota: politica_pred y nivel_confianza ya calculados en paso 3 (FASE 7)
        resultado['fuente_prediccion'] = fuente_pred
        resultado['nivel_confianza_prediccion'] = nivel_confianza
        resultado['aplicar_disclaimer_prediccion'] = politica_pred['disclaimer']
        resultado['disclaimer_confianza'] = obtener_disclaimer(fuente_pred)
        
        # FASE 7: Comentario breve de confianza para el renderer
        if resultado.get('prediccion_excluida'):
            resultado['comentario_confianza'] = (
                f"Predicción {nivel_confianza.lower().replace('_', ' ')}, "
                "no influyó en la severidad."
            )
        elif nivel_confianza == 'CONFIABLE':
            resultado['comentario_confianza'] = (
                "Predicción confiable con precisión moderada. "
                "Severidad incluye dato predicho."
            )
        else:
            resultado['comentario_confianza'] = ''
        
        return resultado
    
    def _get_real_e_historico(
        self,
        metric_id: str,
        entity: str,
        fecha_desde: date,
        fecha_hasta: date,
    ) -> Tuple[Optional[float], Optional[str], Optional[float], int]:
        """
        Obtiene el último valor real y el promedio histórico 30d
        para una métrica/entidad.
        
        Returns: (valor_actual, fecha_dato_str, avg_hist, dias_con_datos)
        """
        try:
            df = self.metrics_service.get_metric_series_by_entity(
                metric_id=metric_id,
                entity=entity,
                start_date=fecha_desde.isoformat(),
                end_date=fecha_hasta.isoformat()
            )
            if df.empty or 'Value' not in df.columns:
                return None, None, None, 0
            
            df_clean = df.dropna(subset=['Value']).sort_values('Date')
            if df_clean.empty:
                return None, None, None, 0
            
            valor_actual = float(df_clean['Value'].iloc[-1])
            fecha_dato = df_clean['Date'].iloc[-1]
            if hasattr(fecha_dato, 'strftime'):
                fecha_dato = fecha_dato.strftime('%Y-%m-%d')
            else:
                fecha_dato = str(fecha_dato)[:10]
            
            avg_hist = float(df_clean['Value'].mean())
            dias = len(df_clean)
            
            return valor_actual, fecha_dato, avg_hist, dias
        except Exception as e:
            logger.warning(f"Error leyendo {metric_id}/{entity}: {e}")
            return None, None, None, 0
    
    def _get_embalses_real_e_historico(
        self,
    ) -> Tuple[Optional[float], Optional[str], Optional[float], int]:
        """
        Obtiene el último % de embalses y el promedio 30d.
        Calcula VoluUtilDiarEner/CapaUtilDiarEner × 100 por día.
        """
        try:
            hoy = date.today()
            hace_30 = hoy - timedelta(days=30)
            
            from infrastructure.database.manager import db_manager
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND fecha >= %s AND fecha <= %s
                    GROUP BY fecha
                    HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                )
                SELECT fecha, vol / cap * 100 as pct
                FROM emb_diario
                ORDER BY fecha ASC
            """
            df = db_manager.query_df(query, params=(hace_30.isoformat(), hoy.isoformat()))
            
            if df is None or df.empty:
                return None, None, None, 0
            
            valor_actual = float(df['pct'].iloc[-1])
            fecha_dato = str(df['fecha'].iloc[-1])[:10]
            avg_hist = float(df['pct'].mean())
            dias = len(df)
            
            return valor_actual, fecha_dato, avg_hist, dias
        except Exception as e:
            logger.warning(f"Error calculando embalses real+hist: {e}")
            return None, None, None, 0
    
    # ═══════════════════════════════════════════════════════════
    # HANDLER: PREDICCIONES DEL SECTOR (3 indicadores clave)
    # ═══════════════════════════════════════════════════════════
    
    # ── Helper: Construir ficha de predicción con contexto histórico ──
    
    def _build_prediction_ficha(
        self,
        indicador: str,
        emoji: str,
        unidad: str,
        df_pred: pd.DataFrame,
        avg_hist_30d: Optional[float],
        dias_hist: int,
        dias_horizonte: int,
        min_puntos_requeridos: int = 5,
    ) -> Dict[str, Any]:
        """
        Construye una ficha de predicción enriquecida con:
        - Promedio/min/max del periodo predicho
        - Comparación vs histórico 30d real
        - cambio_pct derivado del histórico
        - Tendencia calculada (no hardcodeada)
        - Fallback "no confiable" si datos insuficientes
        
        Args:
            indicador: Nombre del indicador
            emoji: Emoji para la ficha
            unidad: Unidad de medida
            df_pred: DataFrame con predicciones (fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior)
            avg_hist_30d: Promedio real de últimos 30 días (None si no disponible)
            dias_hist: Cantidad de días con datos históricos (para evaluar confiabilidad)
            dias_horizonte: Horizonte solicitado en días
            min_puntos_requeridos: Mínimo de puntos de predicción para considerar confiable
        """
        ficha = {
            "indicador": indicador,
            "emoji": emoji,
            "unidad": unidad,
        }
        
        if df_pred.empty or len(df_pred) < min_puntos_requeridos:
            # ─── FALLBACK: NO CONFIABLE ───
            puntos_disponibles = len(df_pred) if not df_pred.empty else 0
            razon = []
            if puntos_disponibles == 0:
                razon.append("no hay predicciones entrenadas para este horizonte")
            elif puntos_disponibles < min_puntos_requeridos:
                razon.append(f"solo {puntos_disponibles} puntos disponibles (mínimo {min_puntos_requeridos})")
            
            ficha["confiable"] = False
            ficha["error"] = f"Sin predicción confiable: {'; '.join(razon)}."
            ficha["puntos_disponibles"] = puntos_disponibles
            return ficha
        
        # ─── FASE 7B: Verificar confianza real del modelo ───
        CONFIANZA_MINIMA_PRED = 0.60
        confianza_modelo = None
        if 'confianza' in df_pred.columns:
            vals_conf = [float(c) for c in df_pred['confianza'] if c is not None]
            if vals_conf:
                confianza_modelo = vals_conf[0]  # misma confianza para toda la fuente
        
        # ─── Cálculos de predicción ───
        valores = [float(r['valor_gwh_predicho']) for _, r in df_pred.iterrows()]
        avg_pred = sum(valores) / len(valores)
        min_pred = min(valores)
        max_pred = max(valores)
        
        # Intervalos de confianza agregados (si disponibles)
        inf_values = [float(r['intervalo_inferior']) for _, r in df_pred.iterrows() if pd.notna(r.get('intervalo_inferior'))]
        sup_values = [float(r['intervalo_superior']) for _, r in df_pred.iterrows() if pd.notna(r.get('intervalo_superior'))]
        
        ficha["confiable"] = True
        ficha["total_dias_prediccion"] = len(valores)
        
        # FASE 7B: incluir confianza del modelo y marcar no-confiable si baja
        if confianza_modelo is not None:
            ficha["confianza_modelo"] = round(confianza_modelo, 2)
            if confianza_modelo < CONFIANZA_MINIMA_PRED:
                ficha["confiable"] = False
                ficha["advertencia_confianza"] = (
                    f"Confianza del modelo ({confianza_modelo:.0%}) por debajo "
                    f"del umbral mínimo ({CONFIANZA_MINIMA_PRED:.0%}). "
                    "Interpretar con precaución."
                )
        ficha["resumen"] = {
            "promedio_periodo": round(avg_pred, 2),
            "minimo_periodo": round(min_pred, 2),
            "maximo_periodo": round(max_pred, 2),
        }
        
        if inf_values and sup_values:
            ficha["resumen"]["rango_confianza"] = {
                "inferior": round(min(inf_values), 2),
                "superior": round(max(sup_values), 2),
            }
        
        # ─── Comparación vs histórico 30d ───
        if avg_hist_30d is not None and avg_hist_30d > 0:
            cambio_pct = ((avg_pred - avg_hist_30d) / avg_hist_30d) * 100
            ficha["resumen"]["promedio_30d_historico"] = round(avg_hist_30d, 2)
            ficha["resumen"]["cambio_pct"] = round(cambio_pct, 1)
            
            # Tendencia derivada del cambio_pct (no hardcodeada)
            if cambio_pct > 5:
                ficha["tendencia"] = "↗️ Creciente"
            elif cambio_pct < -5:
                ficha["tendencia"] = "↘️ Decreciente"
            else:
                ficha["tendencia"] = "➡️ Estable"
        elif avg_hist_30d is not None and avg_hist_30d == 0:
            ficha["resumen"]["promedio_30d_historico"] = 0
            ficha["resumen"]["cambio_pct"] = None
            ficha["resumen"]["nota_historico"] = "Promedio histórico es 0; cambio porcentual no calculable"
            ficha["tendencia"] = "➡️ Sin referencia"
        else:
            # Histórico insuficiente
            ficha["resumen"]["promedio_30d_historico"] = None
            ficha["resumen"]["cambio_pct"] = None
            if dias_hist < 7:
                ficha["resumen"]["nota_historico"] = f"Solo {dias_hist} días de histórico disponibles (insuficiente para comparación confiable)"
            else:
                ficha["resumen"]["nota_historico"] = "Histórico no disponible para esta métrica"
            ficha["tendencia"] = "➡️ Sin referencia histórica"
        
        # Valor representativo para el renderer (promedio del periodo)
        ficha["valor_predicho"] = round(avg_pred, 2)
        
        # Variación para renderer (compatibilidad con render_predicciones_resultado)
        if ficha["resumen"].get("cambio_pct") is not None:
            signo = "+" if ficha["resumen"]["cambio_pct"] > 0 else ""
            ficha["variacion_pct"] = f"{signo}{ficha['resumen']['cambio_pct']}% vs últ. 30d"
        
        return ficha
    
    def _get_historical_avg_30d(
        self,
        metric_id: str,
        entity: str = 'Sistema',
    ) -> Tuple[Optional[float], int]:
        """
        Obtiene promedio de los últimos 30 días reales para una métrica.
        
        Returns:
            (promedio, dias_con_datos) — promedio es None si no hay datos
        """
        hoy = date.today()
        hace_30 = hoy - timedelta(days=30)
        
        try:
            df = self.metrics_service.get_metric_series_by_entity(
                metric_id=metric_id,
                entity=entity,
                start_date=hace_30.isoformat(),
                end_date=hoy.isoformat()
            )
            if not df.empty and 'Value' in df.columns:
                df_clean = df.dropna(subset=['Value'])
                if not df_clean.empty:
                    return float(df_clean['Value'].mean()), len(df_clean)
            return None, 0
        except Exception as e:
            logger.warning(f"Error obteniendo histórico 30d para {metric_id}: {e}")
            return None, 0
    
    def _get_embalses_avg_30d(self) -> Tuple[Optional[float], int]:
        """
        Obtiene promedio % de embalses de los últimos 30 días.
        Calcula VoluUtilDiarEner/CapaUtilDiarEner × 100 por día, luego promedia.
        Consistente con la fórmula de HydrologyService.
        """
        hoy = date.today()
        hace_30 = hoy - timedelta(days=30)
        
        try:
            from infrastructure.database.manager import db_manager
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND fecha >= %s AND fecha <= %s
                    GROUP BY fecha
                )
                SELECT COUNT(*) as dias, AVG(vol / NULLIF(cap, 0) * 100) as avg_pct
                FROM emb_diario WHERE cap > 0
            """
            df = db_manager.query_df(query, params=(hace_30.isoformat(), hoy.isoformat()))
            if not df.empty and df['avg_pct'].iloc[0] is not None:
                return float(df['avg_pct'].iloc[0]), int(df['dias'].iloc[0])
            return None, 0
        except Exception as e:
            logger.warning(f"Error obteniendo histórico 30d de embalses: {e}")
            return None, 0
    
    @handle_service_error
    async def _handle_predicciones_sector(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler 2️⃣: Predicciones de los 3 indicadores clave
        
        Acepta horizonte temporal:
        - 1_semana (7 días)
        - 1_mes (30 días)
        - 6_meses (180 días)
        - 1_ano (365 días)
        - personalizado (fecha específica en formato DD-MM-AAAA o YYYY-MM-DD)
        
        Retorna predicciones enriquecidas con:
        - Promedio/min/max del periodo predicho
        - Comparación vs promedio real últimos 30 días
        - Cambio porcentual y tendencia derivada
        - Fallback "no confiable" si datos insuficientes
        """
        data = {}
        errors = []
        predicciones = []
        
        # Determinar horizonte
        horizonte = parameters.get('horizonte', '1_semana')
        fecha_personalizada = parameters.get('fecha_personalizada')
        
        hoy = date.today()
        
        # Calcular fecha fin según horizonte
        horizonte_map = {
            '1_semana': 7,
            '1_mes': 30,
            '6_meses': 180,
            '1_ano': 365,
        }
        
        horizonte_titulo = {
            '1_semana': 'Próxima semana',
            '1_mes': 'Próximo mes',
            '6_meses': 'Próximos 6 meses',
            '1_ano': 'Próximo año',
        }
        
        if horizonte == 'personalizado' and fecha_personalizada:
            try:
                # Aceptar DD-MM-AAAA o YYYY-MM-DD
                if '-' in fecha_personalizada and len(fecha_personalizada.split('-')[0]) == 4:
                    fecha_fin = datetime.strptime(fecha_personalizada, '%Y-%m-%d').date()
                else:
                    fecha_fin = datetime.strptime(fecha_personalizada, '%d-%m-%Y').date()
                dias_horizonte = (fecha_fin - hoy).days
                if dias_horizonte <= 0:
                    errors.append(ErrorDetail(
                        code="INVALID_DATE",
                        message="La fecha debe ser futura"
                    ))
                    return data, errors
            except ValueError:
                errors.append(ErrorDetail(
                    code="INVALID_DATE_FORMAT",
                    message="Formato de fecha inválido. Use DD-MM-AAAA (ej: 15-03-2026)"
                ))
                return data, errors
        else:
            dias_horizonte = horizonte_map.get(horizonte, 7)
            fecha_fin = hoy + timedelta(days=dias_horizonte)
        
        data['horizonte'] = horizonte
        data['horizonte_titulo'] = horizonte_titulo.get(horizonte, f'Hasta {fecha_fin.isoformat()}')
        data['dias_horizonte'] = dias_horizonte
        data['fecha_inicio'] = hoy.isoformat()
        data['fecha_fin'] = fecha_fin.isoformat()
        
        if not self.predictions_service:
            errors.append(ErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="El servicio de predicciones no está disponible"
            ))
            return data, errors
        
        # ─── Obtener históricos 30d en paralelo (solo lectura) ───
        hist_gen_avg, hist_gen_dias = await asyncio.to_thread(
            self._get_historical_avg_30d, 'Gene', 'Sistema'
        )
        hist_precio_avg, hist_precio_dias = await asyncio.to_thread(
            self._get_historical_avg_30d, 'PrecBolsNaci', 'Sistema'
        )
        hist_emb_avg, hist_emb_dias = await asyncio.to_thread(
            self._get_embalses_avg_30d
        )
        
        # Mínimo de puntos requeridos según horizonte
        min_puntos = max(3, min(dias_horizonte // 2, 30))
        
        # ─── PREDICCIÓN 1: GENERACIÓN TOTAL ───
        try:
            # Usar GENE_TOTAL directo (más consistente que sumar 5 fuentes)
            df_pred_gen = self.predictions_service.get_predictions(
                metric_id='GENE_TOTAL',
                start_date=hoy.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            
            # Fallback: sumar 5 fuentes si GENE_TOTAL no disponible
            if df_pred_gen.empty:
                fuentes = ['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa']
                gen_agg = {}
                for fuente in fuentes:
                    df_f = self.predictions_service.get_predictions(
                        metric_id=fuente,
                        start_date=hoy.isoformat(),
                        end_date=fecha_fin.isoformat()
                    )
                    if not df_f.empty:
                        for _, row in df_f.iterrows():
                            k = str(row['fecha_prediccion'])
                            if k not in gen_agg:
                                gen_agg[k] = {'valor_gwh_predicho': 0, 'intervalo_inferior': 0, 'intervalo_superior': 0}
                            gen_agg[k]['valor_gwh_predicho'] += float(row['valor_gwh_predicho'])
                            if pd.notna(row.get('intervalo_inferior')):
                                gen_agg[k]['intervalo_inferior'] += float(row['intervalo_inferior'])
                            if pd.notna(row.get('intervalo_superior')):
                                gen_agg[k]['intervalo_superior'] += float(row['intervalo_superior'])
                if gen_agg:
                    rows = [{'fecha_prediccion': k, **v} for k, v in sorted(gen_agg.items())]
                    df_pred_gen = pd.DataFrame(rows)
            
            ficha_gen = self._build_prediction_ficha(
                indicador="Generación Total del Sistema",
                emoji="⚡",
                unidad="GWh",
                df_pred=df_pred_gen,
                avg_hist_30d=hist_gen_avg,
                dias_hist=hist_gen_dias,
                dias_horizonte=dias_horizonte,
                min_puntos_requeridos=min_puntos,
            )
            # FASE 6: enriquecer con política de confianza (POLITICA_CONFIANZA_PREDICCIONES.md)
            enriquecer_ficha_con_confianza(ficha_gen, 'GENE_TOTAL')
            predicciones.append(ficha_gen)
        except Exception as e:
            logger.warning(f"Error predicciones generación: {e}")
            predicciones.append({
                "indicador": "Generación Total del Sistema",
                "emoji": "⚡",
                "confiable": False,
                "error": "Error consultando predicciones de generación"
            })
        
        # ─── PREDICCIÓN 2: PRECIO DE BOLSA ───
        try:
            df_pred_precio = self.predictions_service.get_predictions(
                metric_id='PRECIO_BOLSA',
                start_date=hoy.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            
            ficha_precio = self._build_prediction_ficha(
                indicador="Precio de Bolsa Nacional",
                emoji="💰",
                unidad="COP/kWh",
                df_pred=df_pred_precio,
                avg_hist_30d=hist_precio_avg,
                dias_hist=hist_precio_dias,
                dias_horizonte=dias_horizonte,
                min_puntos_requeridos=min_puntos,
            )
            # FASE 6: enriquecer con política de confianza (POLITICA_CONFIANZA_PREDICCIONES.md)
            enriquecer_ficha_con_confianza(ficha_precio, 'PRECIO_BOLSA')
            predicciones.append(ficha_precio)
        except Exception as e:
            logger.warning(f"Error predicciones precio: {e}")
            predicciones.append({
                "indicador": "Precio de Bolsa Nacional",
                "emoji": "💰",
                "confiable": False,
                "error": "Error consultando predicciones de precio"
            })
        
        # ─── PREDICCIÓN 3: EMBALSES (usar EMBALSES_PCT en %, no EMBALSES en GWh) ───
        try:
            df_pred_embalses = self.predictions_service.get_predictions(
                metric_id='EMBALSES_PCT',
                start_date=hoy.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            
            # Fallback a EMBALSES (GWh) si EMBALSES_PCT no disponible
            if df_pred_embalses.empty:
                df_pred_embalses = self.predictions_service.get_predictions(
                    metric_id='EMBALSES',
                    start_date=hoy.isoformat(),
                    end_date=fecha_fin.isoformat()
                )
                # Si cae en fallback GWh, no comparar vs promedio % histórico
                hist_emb_avg_use = None
                hist_emb_dias_use = 0
                unidad_emb = "GWh"
            else:
                hist_emb_avg_use = hist_emb_avg
                hist_emb_dias_use = hist_emb_dias
                unidad_emb = "%"
            
            ficha_emb = self._build_prediction_ficha(
                indicador="Porcentaje de Embalses",
                emoji="💧",
                unidad=unidad_emb,
                df_pred=df_pred_embalses,
                avg_hist_30d=hist_emb_avg_use,
                dias_hist=hist_emb_dias_use,
                dias_horizonte=dias_horizonte,
                min_puntos_requeridos=min_puntos,
            )
            # FASE 6: enriquecer con política de confianza (POLITICA_CONFIANZA_PREDICCIONES.md)
            enriquecer_ficha_con_confianza(ficha_emb, 'EMBALSES_PCT')
            predicciones.append(ficha_emb)
        except Exception as e:
            logger.warning(f"Error predicciones embalses: {e}")
            predicciones.append({
                "indicador": "Porcentaje de Embalses",
                "emoji": "💧",
                "confiable": False,
                "error": "Error consultando predicciones de embalses"
            })
        
        data['predicciones'] = predicciones
        data['fecha_consulta'] = datetime.utcnow().isoformat()
        data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}
        
        # Resumen de errores en predicciones
        pred_con_error = [p for p in predicciones if p.get('error')]
        if pred_con_error:
            for p in pred_con_error:
                errors.append(ErrorDetail(
                    code="PREDICTION_UNAVAILABLE",
                    message=f"Predicción no disponible: {p['indicador']}"
                ))
        
        logger.info(
            f"[PREDICCIONES_SECTOR] Horizonte={horizonte} ({dias_horizonte} días) | "
            f"Disponibles: {len(predicciones) - len(pred_con_error)}/{len(predicciones)} | "
            f"Hist30d: gen={hist_gen_avg}, precio={hist_precio_avg}, emb={hist_emb_avg}"
        )
        
        return data, errors
    
    # ═══════════════════════════════════════════════════════════
    # HANDLER: PREGUNTA LIBRE (responde cualquier pregunta)
    # ═══════════════════════════════════════════════════════════
    
    @handle_service_error
    async def _handle_pregunta_libre(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Pregunta libre del usuario
        
        Recibe una pregunta en lenguaje natural y la responde
        usando los servicios disponibles del portal energético.
        
        El bot de Oscar debe enviar:
        {
            "intent": "pregunta_libre",
            "parameters": {"pregunta": "¿cuánta energía solar se generó ayer?"}
        }
        """
        data = {}
        errors = []
        
        pregunta = parameters.get('pregunta', '').strip()
        
        if not pregunta:
            errors.append(ErrorDetail(
                code="MISSING_QUESTION",
                message="Debes enviar una pregunta en el parámetro 'pregunta'"
            ))
            return data, errors
        
        pregunta_lower = pregunta.lower()
        
        try:
            # Intentar detectar la intención de la pregunta y responder
            # con datos reales del sistema
            
            respuesta_partes = []
            datos_consultados = {}
            
            # ¿Pregunta sobre generación?
            if any(w in pregunta_lower for w in ['generación', 'generacion', 'generar', 'producción', 'produccion', 'energía', 'energia', 'solar', 'eólica', 'eolica', 'hidráulica', 'hidraulica', 'térmica', 'termica', 'biomasa']):
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=7)
                df_gen = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.generation_service.get_daily_generation_system,
                        start_date, end_date
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if not df_gen.empty:
                    datos_consultados['generacion'] = {
                        'total_gwh': round(float(df_gen['valor_gwh'].sum()), 2),
                        'promedio_diario_gwh': round(float(df_gen['valor_gwh'].mean()), 2),
                        'ultimo_dia_gwh': round(float(df_gen.sort_values('fecha').iloc[-1]['valor_gwh']), 2),
                        'periodo': f"{start_date} a {end_date}"
                    }
            
            # ¿Pregunta sobre precio?
            if any(w in pregunta_lower for w in ['precio', 'bolsa', 'costo', 'tarifa', 'cop', 'kwh']):
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=7)
                df_precio = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.metrics_service.get_metric_series,
                        'PrecBolsNaci', start_date.isoformat(), end_date.isoformat()
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if not df_precio.empty and 'Value' in df_precio.columns:
                    datos_consultados['precio_bolsa'] = {
                        'promedio_cop_kwh': round(float(df_precio['Value'].mean()), 2),
                        'maximo_cop_kwh': round(float(df_precio['Value'].max()), 2),
                        'minimo_cop_kwh': round(float(df_precio['Value'].min()), 2),
                        'periodo': f"{start_date} a {end_date}"
                    }
            
            # ¿Pregunta sobre embalses/hidrología?
            if any(w in pregunta_lower for w in ['embalse', 'embalses', 'agua', 'hidrología', 'hidrologia', 'reserva', 'nivel']):
                ayer = (date.today() - timedelta(days=1)).isoformat()
                nivel_pct, energia_gwh, fecha_dato_emb = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.hydrology_service.get_reservas_hidricas, ayer
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if nivel_pct is not None:
                    datos_consultados['embalses'] = {
                        'nivel_porcentaje': round(nivel_pct, 2),
                        'energia_embalsada_gwh': round(energia_gwh, 2) if energia_gwh else None,
                        'fecha': fecha_dato_emb or ayer
                    }
            
            # ¿Pregunta sobre demanda?
            if any(w in pregunta_lower for w in ['demanda', 'consumo', 'carga']):
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=7)
                df_dem = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.metrics_service.get_metric_series,
                        'DemaCome', start_date.isoformat(), end_date.isoformat()
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if not df_dem.empty and 'Value' in df_dem.columns:
                    datos_consultados['demanda'] = {
                        'promedio_gwh': round(float(df_dem['Value'].mean()), 2),
                        'maximo_gwh': round(float(df_dem['Value'].max()), 2),
                        'periodo': f"{start_date} a {end_date}"
                    }
            
            # ¿Pregunta sobre predicciones?
            if any(w in pregunta_lower for w in ['predicción', 'prediccion', 'pronóstico', 'pronostico', 'futuro', 'va a', 'será', 'será', 'espera']):
                if self.predictions_service:
                    for fuente_pred in ['Hidráulica', 'PRECIO_BOLSA', 'EMBALSES']:
                        df_pred = self.predictions_service.get_predictions(
                            metric_id=fuente_pred,
                            start_date=date.today().isoformat()
                        )
                        if not df_pred.empty:
                            vals = df_pred['valor_gwh_predicho'].tolist()
                            datos_consultados[f'prediccion_{fuente_pred}'] = {
                                'dias_disponibles': len(vals),
                                'promedio': round(float(sum(vals) / len(vals)), 2),
                                'rango': f"{round(float(min(vals)), 2)} - {round(float(max(vals)), 2)}"
                            }
            
            # Si no se detectó ningún tema específico, consultar los 3 KPIs generales
            if not datos_consultados:
                # Dar datos generales
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=7)
                
                df_gen = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.generation_service.get_daily_generation_system,
                        start_date, end_date
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if not df_gen.empty:
                    datos_consultados['generacion'] = {
                        'ultimo_dia_gwh': round(float(df_gen.sort_values('fecha').iloc[-1]['valor_gwh']), 2)
                    }
                
                nivel_pct, _, _ = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.hydrology_service.get_reservas_hidricas,
                        end_date.isoformat()
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if nivel_pct:
                    datos_consultados['embalses'] = {'nivel_porcentaje': round(nivel_pct, 2)}
            
            data['pregunta'] = pregunta
            data['datos_consultados'] = datos_consultados
            data['nota'] = (
                "Estos son los datos reales del sistema energético colombiano "
                "relacionados con tu pregunta. El bot puede usar estos datos "
                "para generar una respuesta en lenguaje natural con IA."
            )
            data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}
            
            logger.info(
                f"[PREGUNTA_LIBRE] Pregunta='{pregunta[:50]}...' | "
                f"Datos encontrados: {list(datos_consultados.keys())}"
            )
            
            # FASE D: Análisis con IA opcional
            if parameters.get('con_analisis_ia') and datos_consultados:
                try:
                    from domain.services.ai_service import AgentIA
                    from domain.services.confianza_politica import get_confianza_politica
                    agent = AgentIA()
                    if agent.client:
                        import json as _json2
                        contexto_ia = {
                            "pregunta": pregunta,
                            "datos": datos_consultados,
                        }
                        # Solo incluir confianza de métricas presentes en datos
                        confianza_relevante = {}
                        mapa_confianza = {
                            'precio_bolsa': 'PRECIO_BOLSA',
                            'generacion': 'Hidráulica',
                            'embalses': 'EMBALSES',
                            'prediccion_PRECIO_BOLSA': 'PRECIO_BOLSA',
                            'prediccion_Hidráulica': 'Hidráulica',
                            'prediccion_EMBALSES': 'EMBALSES',
                        }
                        for clave_dato, metrica in mapa_confianza.items():
                            if clave_dato in datos_consultados:
                                confianza_relevante[metrica] = get_confianza_politica(metrica)
                        if confianza_relevante:
                            contexto_ia["confianza_modelos"] = confianza_relevante
                        sys_p = (
                            "Eres un asesor energético del Ministerio de Minas "
                            "de Colombia. Responde la pregunta del usuario "
                            "usando SOLO los datos suministrados.\n"
                            "Máximo 200 palabras, usa bullets, en español.\n"
                            "Si en 'datos' hay clave 'precio_bolsa' y en "
                            "'confianza_modelos' su nivel es EXPERIMENTAL, "
                            "indícalo UNA vez al final. Si NO hay clave "
                            "'precio_bolsa' en los datos, NO menciones "
                            "nada sobre modelos experimentales.\n"
                            "NO inventes datos. Redondea a 2 decimales."
                        )
                        usr_p = (
                            f"Datos:\n```json\n"
                            f"{_json2.dumps(contexto_ia, ensure_ascii=False, default=str)}"
                            f"\n```\n\nPregunta: {pregunta}"
                        )
                        def _call_ia():
                            return agent.client.chat.completions.create(
                                model=agent.modelo,
                                messages=[
                                    {"role": "system", "content": sys_p},
                                    {"role": "user", "content": usr_p},
                                ],
                                temperature=0.4,
                                max_tokens=600,
                            )
                        resp_ia = await asyncio.wait_for(
                            asyncio.to_thread(_call_ia), timeout=20
                        )
                        data['analisis_ia'] = resp_ia.choices[0].message.content.strip()
                        logger.info(f"[PREGUNTA_LIBRE] IA analysis generated ({len(data['analisis_ia'])} chars)")
                except Exception as e:
                    logger.warning(f"[PREGUNTA_LIBRE] IA analysis failed: {e}")
                    data['analisis_ia'] = None
            
        except Exception as e:
            logger.error(f"Error en pregunta libre: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="QUERY_ERROR",
                message="Error al procesar la pregunta"
            ))
        
        return data, errors
    
    # ═══════════════════════════════════════════════════════════
    # HANDLERS ESPECÍFICOS POR SECTOR
    # ═══════════════════════════════════════════════════════════
    
    @handle_service_error
    async def _handle_generacion_electrica(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de generación eléctrica"""
        data = {}
        errors = []
        
        # Extraer parámetros
        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')
        recurso = parameters.get('recurso')
        
        # Determinar fechas
        if fecha_str:
            # Fecha específica
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            # Rango de fechas
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            # Por defecto: últimos 7 días
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
        
        try:
            # Obtener generación del sistema
            df_system = await asyncio.wait_for(
                asyncio.to_thread(
                    self.generation_service.get_daily_generation_system,
                    start_date,
                    end_date
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if not df_system.empty:
                # Calcular estadísticas
                total = df_system['valor_gwh'].sum()
                promedio = df_system['valor_gwh'].mean()
                
                data['generacion_total_gwh'] = round(total, 2)
                data['generacion_promedio_gwh'] = round(promedio, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }
                
                # Si es una fecha específica, dar detalle por recursos
                if fecha_str:
                    try:
                        df_resources = await asyncio.wait_for(
                            asyncio.to_thread(
                                self.generation_service.get_generation_by_source,
                                start_date,
                                end_date
                            ),
                            timeout=self.SERVICE_TIMEOUT
                        )
                        
                        if not df_resources.empty:
                            # Agrupar por fuente
                            por_recurso = {}
                            for fuente in df_resources['fuente'].unique():
                                df_fuente = df_resources[df_resources['fuente'] == fuente]
                                por_recurso[fuente.lower()] = round(df_fuente['valor_gwh'].sum(), 2)
                            
                            data['por_recurso'] = por_recurso
                    except Exception as e:
                        logger.warning(f"Error obteniendo recursos: {e}")
                        errors.append(ErrorDetail(
                            code="PARTIAL_DATA",
                            message="No se pudo obtener el detalle por recurso"
                        ))
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message=f"No hay datos de generación para el periodo solicitado"
                ))
                
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de generación tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_generacion_electrica: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de generación"
            ))
        
        return data, errors
    
    @handle_service_error
    async def _handle_hidrologia(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de hidrología/embalses"""
        data = {}
        errors = []
        
        # Extraer parámetros
        fecha_str = parameters.get('fecha')
        embalse = parameters.get('embalse')
        
        # Determinar fecha (por defecto: hoy)
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        else:
            fecha = date.today()
        
        try:
            # Obtener datos de embalses usando método correcto
            nivel_pct, energia_gwh, fecha_dato_emb = await asyncio.wait_for(
                asyncio.to_thread(
                    self.hydrology_service.get_reservas_hidricas,
                    fecha.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if nivel_pct is not None and energia_gwh is not None:
                data['nivel_promedio_sistema'] = round(nivel_pct, 2)
                data['energia_embalsada_gwh'] = round(energia_gwh, 2)
                data['fecha'] = fecha_dato_emb or fecha.isoformat()
                
                # Si pidió un embalse específico, informar que no está disponible
                if embalse:
                    errors.append(ErrorDetail(
                        code="NOT_IMPLEMENTED",
                        message="Consulta por embalse específico no implementada en esta versión"
                    ))
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de embalses para la fecha solicitada"
                ))
                
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de hidrología tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_hidrologia: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de embalses"
            ))
        
        return data, errors
    
    @handle_service_error
    async def _handle_demanda_sistema(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de demanda del sistema"""
        data = {}
        errors = []
        
        # Extraer parámetros
        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')
        
        # Determinar fechas
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            # Por defecto: últimos 7 días
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
        
        try:
            # Obtener demanda desde metrics (DemaCome)
            df_demand = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'DemaCome',
                    start_date.isoformat(),
                    end_date.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if not df_demand.empty and 'Value' in df_demand.columns:
                total = df_demand['Value'].sum()
                promedio = df_demand['Value'].mean()
                maximo = df_demand['Value'].max()
                
                data['demanda_total_gwh'] = round(total, 2)
                data['demanda_promedio_gwh'] = round(promedio, 2)
                data['demanda_maxima_gwh'] = round(maximo, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de demanda para el periodo solicitado"
                ))
                
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de demanda tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_demanda_sistema: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de demanda"
            ))
        
        return data, errors
    
    @handle_service_error
    async def _handle_precio_bolsa(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de precios de bolsa"""
        data = {}
        errors = []
        
        # Extraer parámetros
        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')
        
        # Determinar fechas
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            # Por defecto: últimos 7 días
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
        
        try:
            # Obtener precios desde metrics (PrecBolsNaci)
            df_prices = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'PrecBolsNaci',
                    start_date.isoformat(),
                    end_date.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            
            if not df_prices.empty and 'Value' in df_prices.columns:
                promedio = df_prices['Value'].mean()
                maximo = df_prices['Value'].max()
                minimo = df_prices['Value'].min()
                
                data['precio_promedio_cop_kwh'] = round(promedio, 2)
                data['precio_maximo_cop_kwh'] = round(maximo, 2)
                data['precio_minimo_cop_kwh'] = round(minimo, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de precios para el periodo solicitado"
                ))
                
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de precios tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_precio_bolsa: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de precios"
            ))
        
        return data, errors
    
    @handle_service_error
    async def _handle_predicciones(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler para intent de predicciones de generación por fuentes
        
        Parámetros esperados:
        - fuente: Hidráulica, Térmica, Eólica, Solar, Biomasa (opcional, default: Hidráulica)
        - horizonte: Días de predicción (opcional, default: 7)
        - fecha_inicio: Fecha inicial (opcional, default: hoy)
        """
        data = {}
        errors = []
        
        if not self.predictions_service:
            errors.append(ErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="El servicio de predicciones no está disponible"
            ))
            return data, errors
        
        # Obtener parámetros
        fuente = parameters.get('fuente', '')
        tipo = parameters.get('tipo', '')
        horizonte_dias = parameters.get('horizonte', 7)
        fecha_inicio_param = parameters.get('fecha_inicio')
        
        try:
            # Mapeo de tipo → fuente en BD
            tipo_a_fuente = {
                'precios': 'PRECIO_BOLSA',
                'precio': 'PRECIO_BOLSA',
                'bolsa': 'PRECIO_BOLSA',
                'embalses': 'EMBALSES',
                'embalse': 'EMBALSES',
                'generacion': 'GENE_TOTAL',
                'generacion_total': 'GENE_TOTAL',
                'demanda': 'DEMANDA',
                'aportes': 'APORTES_HIDRICOS',
                'perdidas': 'PERDIDAS',
            }
            
            # Normalizar nombre de fuente (incluye fuentes de generación + sectoriales)
            fuentes_validas = {
                'hidraulica': 'Hidráulica',
                'termica': 'Térmica',
                'eolica': 'Eólica',
                'solar': 'Solar',
                'biomasa': 'Biomasa',
                'gene_total': 'GENE_TOTAL',
                'precio_bolsa': 'PRECIO_BOLSA',
                'embalses': 'EMBALSES',
                'embalses_pct': 'EMBALSES_PCT',
                'demanda': 'DEMANDA',
                'aportes_hidricos': 'APORTES_HIDRICOS',
                'perdidas': 'PERDIDAS',
            }
            
            # Prioridad: tipo → fuente → default
            if tipo and tipo.lower() in tipo_a_fuente:
                fuente_normalizada = tipo_a_fuente[tipo.lower()]
            elif fuente and isinstance(fuente, str) and fuente.lower() in fuentes_validas:
                fuente_normalizada = fuentes_validas[fuente.lower()]
            elif fuente and isinstance(fuente, str):
                # Intentar match directo (ej: PRECIO_BOLSA ya viene correcto)
                fuente_normalizada = fuente if fuente in ['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa', 'GENE_TOTAL', 'PRECIO_BOLSA', 'EMBALSES', 'EMBALSES_PCT', 'DEMANDA', 'APORTES_HIDRICOS', 'PERDIDAS'] else 'Hidráulica'
            else:
                fuente_normalizada = 'Hidráulica'
            
            # Calcular rango de fechas
            if fecha_inicio_param:
                from datetime import datetime, timedelta
                if isinstance(fecha_inicio_param, str):
                    fecha_inicio = datetime.strptime(fecha_inicio_param, '%Y-%m-%d').date()
                else:
                    fecha_inicio = fecha_inicio_param
            else:
                from datetime import date, timedelta
                fecha_inicio = date.today()
            
            fecha_fin = fecha_inicio + timedelta(days=horizonte_dias)
            
            # Consultar predicciones del servicio
            df_predicciones = self.predictions_service.get_predictions(
                metric_id=fuente_normalizada,
                start_date=fecha_inicio.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            
            # Verificar si hay predicciones
            if df_predicciones.empty:
                data['fuente'] = fuente_normalizada
                data['horizonte_dias'] = horizonte_dias
                data['predicciones'] = []
                data['mensaje'] = f'No hay predicciones disponibles para {fuente_normalizada}'
                data['sugerencia'] = 'Ejecute el script train_predictions_postgres.py para generar predicciones'
                
                logger.warning(f"No hay predicciones para {fuente_normalizada}")
                
            else:
                # Formatear predicciones
                predicciones = []
                for idx, row in df_predicciones.iterrows():
                    pred = {
                        'fecha': row['fecha_prediccion'].isoformat() if hasattr(row['fecha_prediccion'], 'isoformat') else str(row['fecha_prediccion']),
                        'valor_gwh': float(row['valor_gwh_predicho']),
                        'intervalo_inferior': float(row['intervalo_inferior']) if pd.notna(row.get('intervalo_inferior')) else None,
                        'intervalo_superior': float(row['intervalo_superior']) if pd.notna(row.get('intervalo_superior')) else None
                    }
                    predicciones.append(pred)
                
                # Calcular estadísticas
                valores = [p['valor_gwh'] for p in predicciones]
                promedio = sum(valores) / len(valores) if valores else 0
                minimo = min(valores) if valores else 0
                maximo = max(valores) if valores else 0
                
                # Construir respuesta
                data['fuente'] = fuente_normalizada
                data['horizonte_dias'] = horizonte_dias
                data['total_predicciones'] = len(predicciones)
                data['predicciones'] = predicciones
                data['estadisticas'] = {
                    'promedio_gwh': round(promedio, 2),
                    'minimo_gwh': round(minimo, 2),
                    'maximo_gwh': round(maximo, 2)
                }
                data['modelo'] = 'ENSEMBLE_v1.0'
                data['mensaje'] = f'Predicciones de {fuente_normalizada} para los próximos {len(predicciones)} días'
                
                # CONCLUSIONES basadas en análisis de predicciones
                conclusiones = []
                rango = maximo - minimo
                cv_pred = (np.std(valores) / promedio * 100) if promedio > 0 else 0
                
                conclusiones.append(
                    f"📊 Las predicciones de {fuente_normalizada} para los próximos {len(predicciones)} días "
                    f"muestran un promedio de {round(promedio, 2)} GWh/día (rango: {round(minimo, 2)} - {round(maximo, 2)} GWh)"
                )
                
                if cv_pred < 3:
                    conclusiones.append(
                        f"✅ Se espera alta estabilidad en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)"
                    )
                elif cv_pred > 10:
                    conclusiones.append(
                        f"⚠️ Se anticipan fluctuaciones significativas en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)"
                    )
                else:
                    conclusiones.append(
                        f"📈 Variabilidad normal esperada en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)"
                    )
                
                # Tendencia en predicciones
                if len(valores) >= 3:
                    tendencia_pred = valores[-1] - valores[0]
                    if abs(tendencia_pred) > promedio * 0.05:
                        dir_text = "creciente" if tendencia_pred > 0 else "decreciente"
                        conclusiones.append(
                            f"📉 Tendencia {dir_text} en el horizonte de predicción: "
                            f"de {round(valores[0], 2)} a {round(valores[-1], 2)} GWh/día"
                        )
                
                data['conclusiones'] = conclusiones
                
                # RECOMENDACIONES
                recomendaciones = []
                recomendaciones.append(
                    f"📋 Monitorear la generación {fuente_normalizada.lower()} real vs predicha para validar el modelo"
                )
                
                if fuente_normalizada == 'Hidráulica' and promedio < 150:
                    recomendaciones.append(
                        "⚡ Generación hidráulica predicha por debajo del umbral histórico. "
                        "Verificar niveles de embalses y disponibilidad de respaldo térmico"
                    )
                elif fuente_normalizada == 'Hidráulica' and promedio > 200:
                    recomendaciones.append(
                        "💧 Generación hidráulica predicha en niveles altos, favorable para el sistema"
                    )
                
                if cv_pred > 10:
                    recomendaciones.append(
                        "🔧 La alta variabilidad anticipada sugiere preparar capacidad de respaldo flexible"
                    )
                
                data['recomendaciones'] = recomendaciones
                
                logger.info(f"✅ Predicciones obtenidas: {fuente_normalizada}, {len(predicciones)} días")
            
        except Exception as e:
            logger.error(f"Error en handle_predicciones: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message=f"Error al consultar predicciones: {str(e)}"
            ))
        
        return data, errors
    
    @handle_service_error
    async def _handle_metricas_generales(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler para métricas generales/resumen del sistema
        
        ACTUALIZADO: Ahora usa el análisis inteligente completo
        """
        data = {}
        errors = []
        
        try:
            # Usar análisis inteligente en lugar de consultas simples
            result = await asyncio.wait_for(
                self.intelligent_analysis.analyze_complete_sector(),
                timeout=self.TOTAL_TIMEOUT - 5
            )
            
            if result:
                # Versión simplificada para métricas generales
                data['estado_general'] = result['estado_general']
                data['resumen'] = result['resumen_ejecutivo']
                
                # KPIs principales de cada sector
                data['sectores'] = {}
                for sector_name, sector_status in result['sectores'].items():
                    data['sectores'][sector_name] = {
                        'estado': sector_status.get('estado', 'normal'),
                        'kpis_principales': sector_status.get('kpis', {})
                    }
                
                # Anomalías más importantes (solo críticas y alertas)
                critical_anomalies = []
                for a in result.get('anomalias_criticas', []):
                    sev = a.get('severidad', a.get('severity', 'INFO'))
                    if isinstance(sev, str):
                        sev_name = sev.upper()
                    elif isinstance(sev, SeverityLevel):
                        sev_name = sev.name
                    else:
                        continue
                    
                    if sev_name in ['CRITICAL', 'ALERT']:
                        critical_anomalies.append(a)
                
                if critical_anomalies:
                    data['alertas'] = critical_anomalies[:5]  # Top 5
                else:
                    data['alertas'] = []
                
                data['fecha'] = datetime.utcnow().isoformat()
                
                logger.info(
                    f"[METRICAS_GENERALES] Estado={data['estado_general']} | "
                    f"Alertas={len(critical_anomalies)}"
                )
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No se pudieron obtener las métricas generales"
                ))
                
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El análisis de métricas tardó demasiado en ejecutarse"
            ))
        except Exception as e:
            logger.error(f"Error en _handle_metricas_generales: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar métricas generales"
            ))
        
        return data, errors
    
    # ═══════════════════════════════════════════════════════════
    # HANDLER: INFORME EJECUTIVO IA (FASE 5)
    # ═══════════════════════════════════════════════════════════

    @handle_service_error
    async def _handle_informe_ejecutivo(
        self, 
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Informe Ejecutivo con IA
        
        Recopila datos de estado_actual, predicciones (1 mes + 6 meses)
        y anomalías detectadas. Arma un contexto JSON estructurado y
        lo envía a la IA (Groq/OpenRouter) para redacción de un informe
        ejecutivo de 4 secciones dirigido al Viceministro.
        
        Fallback: si la IA no responde, se genera un informe degradado
        con tablas de datos numéricos.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        
        try:
            # ── 1. Recopilar datos de los 3 módulos existentes en paralelo ──
            logger.info("[INFORME_EJECUTIVO_IA] Recopilando datos de contexto…")
            
            estado_task = self._handle_estado_actual(parameters)
            pred_1m_task = self._handle_predicciones_sector({'horizonte': '1_mes'})
            pred_6m_task = self._handle_predicciones_sector({'horizonte': '6_meses'})
            anomalias_task = self._handle_anomalias_detectadas(parameters)
            
            results = await asyncio.gather(
                estado_task, pred_1m_task, pred_6m_task, anomalias_task,
                return_exceptions=True
            )
            
            # Desempaquetar (cada handler retorna (data, errors))
            def _safe_unpack(result):
                if isinstance(result, Exception):
                    logger.warning(f"[INFORME_EJECUTIVO_IA] Excepción recopilando datos: {result}")
                    return {}, []
                if isinstance(result, tuple) and len(result) == 2:
                    return result[0] or {}, result[1] or []
                return {}, []
            
            data_estado, _ = _safe_unpack(results[0])
            data_pred_1m, _ = _safe_unpack(results[1])
            data_pred_6m, _ = _safe_unpack(results[2])
            data_anomalias, _ = _safe_unpack(results[3])
            
            # ── 1b. Obtener noticias filtradas (best-effort) ──
            noticias_ctx = {}
            try:
                if self.news_service:
                    enriched = await asyncio.wait_for(
                        self.news_service.get_enriched_news(max_top=3, max_extra=5),
                        timeout=15,
                    )
                    top_noticias = enriched.get("top", [])
                    otras_noticias = enriched.get("otras", [])
                    
                    # Construir resumen compacto para la IA
                    titulares = []
                    for n in top_noticias + otras_noticias:
                        t = n.get("titulo", "")
                        f = n.get("fuente", "")
                        if t:
                            titulares.append(f"{t} ({f})" if f else t)
                    
                    # Obtener resumen IA de noticias (puede estar en cache)
                    resumen_prensa = None
                    noticias_result = await asyncio.wait_for(
                        self._handle_noticias_sector(parameters),
                        timeout=20,
                    )
                    if isinstance(noticias_result, tuple):
                        noticias_data = noticias_result[0] if noticias_result[0] else {}
                        resumen_prensa = noticias_data.get("resumen_general")
                    
                    if titulares:
                        noticias_ctx = {
                            "titulares_del_dia": titulares[:8],
                            "resumen_prensa": resumen_prensa or "",
                            "total_fuentes": len(enriched.get("fuentes_usadas", [])),
                        }
                        logger.info(
                            f"[INFORME_EJECUTIVO_IA] Noticias inyectadas: "
                            f"{len(titulares)} titulares, "
                            f"resumen={'sí' if resumen_prensa else 'no'}"
                        )
            except Exception as e:
                logger.warning(
                    f"[INFORME_EJECUTIVO_IA] Noticias no disponibles "
                    f"(no crítico): {e}"
                )
            
            # ── 2. Construir contexto estructurado para la IA ──
            hoy = date.today().strftime('%Y-%m-%d')
            
            contexto = {
                "fecha_consulta": hoy,
                "estado_actual": {
                    "fichas": data_estado.get('fichas', []),
                },
                "predicciones": {
                    "1_mes": {
                        "horizonte_titulo": data_pred_1m.get('horizonte_titulo', 'Próximo mes'),
                        "fecha_inicio": data_pred_1m.get('fecha_inicio'),
                        "fecha_fin": data_pred_1m.get('fecha_fin'),
                        "indicadores": data_pred_1m.get('predicciones', []),
                    },
                    "6_meses": {
                        "horizonte_titulo": data_pred_6m.get('horizonte_titulo', 'Próximos 6 meses'),
                        "fecha_inicio": data_pred_6m.get('fecha_inicio'),
                        "fecha_fin": data_pred_6m.get('fecha_fin'),
                        "indicadores": data_pred_6m.get('predicciones', []),
                    },
                },
                "anomalias": {
                    "total_evaluadas": data_anomalias.get('total_evaluadas', 0),
                    "total_anomalias": data_anomalias.get('total_anomalias', 0),
                    "lista": data_anomalias.get('anomalias', []),
                    "detalle_completo": data_anomalias.get('detalle_completo', []),
                    "resumen": data_anomalias.get('resumen', ''),
                },
                "confianza_modelos": {
                    "resumen": (
                        "Cada indicador predictivo tiene un nivel de confianza "
                        "determinado por validación holdout (MAPE). Los niveles "
                        "MUY_CONFIABLE y CONFIABLE permiten conclusiones firmes; "
                        "ACEPTABLE y EXPERIMENTAL requieren cautela."
                    ),
                    "por_indicador": {
                        fuente: {
                            "nivel": pol["nivel"],
                            "mape_max": pol["mape_max"],
                            "usar_intervalos": pol["usar_intervalos"],
                            "disclaimer": obtener_disclaimer(fuente),
                        }
                        for fuente, pol in [
                            ("GENE_TOTAL",   get_confianza_politica("GENE_TOTAL")),
                            ("PRECIO_BOLSA", get_confianza_politica("PRECIO_BOLSA")),
                            ("EMBALSES_PCT", get_confianza_politica("EMBALSES_PCT")),
                        ]
                    },
                    "fuentes_experimentales": ["PRECIO_BOLSA"],
                },
                "notas_negocio": {
                    "umbrales_embalses": {
                        "critico_bajo": 30,
                        "alerta_bajo": 40,
                        "optimo_min": 50,
                        "optimo_max": 85,
                    },
                    "umbrales_anomalias": {
                        "generacion_embalses": {"normal": "<10%", "alerta": "10-25%", "critico": ">25%"},
                        "precio_bolsa": {"normal": "<20%", "alerta": "20-40%", "critico": ">40%"},
                    },
                    "suposiciones": [
                        "Datos de XM pueden tener retraso de 1-3 días.",
                        "Predicciones basadas en modelo ENSEMBLE entrenado sobre histórico 2020+.",
                        "Precios en COP/kWh, generación en GWh, embalses en %.",
                        "Política de confianza: MUY_CONFIABLE/CONFIABLE → conclusión firme; "
                        "ACEPTABLE/EXPERIMENTAL → alta incertidumbre, no usar para decisiones críticas.",
                        "PRECIO_BOLSA es EXPERIMENTAL (sin validación holdout): "
                        "no proyectar tendencias de precio con certeza.",
                    ],
                },
            }
            
            # Inyectar noticias si disponibles
            if noticias_ctx:
                contexto["prensa_del_dia"] = noticias_ctx
            
            logger.info(
                f"[INFORME_EJECUTIVO_IA] Contexto armado: "
                f"fichas={len(contexto['estado_actual']['fichas'])}, "
                f"pred_1m={len(contexto['predicciones']['1_mes']['indicadores'])}, "
                f"pred_6m={len(contexto['predicciones']['6_meses']['indicadores'])}, "
                f"anomalías={contexto['anomalias']['total_anomalias']}"
            )
            
            # ── 3. Llamar a la IA para redactar el informe ──
            informe_texto = await self._generar_informe_con_ia(contexto)
            
            if informe_texto:
                data['informe'] = informe_texto
                data['generado_con_ia'] = True
            else:
                # Fallback sin IA
                logger.warning("[INFORME_EJECUTIVO_IA] IA no disponible, generando fallback")
                data['informe'] = self._generar_informe_fallback(contexto)
                data['generado_con_ia'] = False
                data['nota_fallback'] = (
                    "Informe generado sin análisis textual de IA por "
                    "indisponibilidad temporal del servicio; se muestran "
                    "datos numéricos consolidados."
                )
            
            data['fecha_generacion'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            data['contexto_datos'] = contexto  # Para debug/FASE 5+ futura
            
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="La generación del informe tardó demasiado"
            ))
        except Exception as e:
            logger.error(f"[INFORME_EJECUTIVO_IA] Error: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="REPORT_ERROR",
                message="Error al generar el informe ejecutivo"
            ))
        
        return data, errors
    
    # ── Helper: Llamar a la IA (Groq/OpenRouter) ──
    
    async def _generar_informe_con_ia(
        self,
        contexto: Dict[str, Any],
    ) -> Optional[str]:
        """
        Envía el contexto estructurado a Groq/OpenRouter y recibe
        un informe ejecutivo redactado en 4 secciones.
        
        Returns:
            Texto Markdown del informe, o None si falla.
        """
        try:
            from domain.services.ai_service import AgentIA
            agent = AgentIA()
            
            if not agent.client:
                logger.warning("[INFORME_IA] Cliente de IA no configurado")
                return None
            
            import json as _json
            contexto_json = _json.dumps(contexto, ensure_ascii=False, default=str)
            
            system_prompt = (
                "Eres un ingeniero eléctrico senior que asesora al Viceministro "
                "de Minas y Energía de Colombia. Recibes un JSON con estado actual, "
                "predicciones, anomalías del sistema eléctrico y, opcionalmente, "
                "titulares de prensa energética del día.\n\n"
                "Elabora un informe ejecutivo en 4 secciones:\n"
                "1) **Situación actual del sistema** — un bullet por indicador: "
                "valor, unidad y fecha del dato.\n"
                "2) **Tendencias y proyecciones** — un sub-bloque por indicador "
                "con promedio esperado, rango, cambio vs 30d y tendencia. "
                "Para cada indicador, usa máximo 2 líneas de texto.\n"
                "3) **Riesgos y oportunidades** — bullets cortos (1-2 líneas cada "
                "uno), empezando por los críticos. Incluye tres sub-apartados:\n"
                "   3.1 Riesgos operativos (embalses, precios, generación).\n"
                "   3.2 Oportunidades de transición (renovables, movilidad eléctrica, etc.).\n"
                "   3.3 Perspectiva de prensa — Si el JSON contiene 'prensa_del_dia', "
                "escribe 2-3 frases que conecten los titulares energéticos del día con "
                "los riesgos/oportunidades ya detectados por datos. Ejemplo: 'Los titulares "
                "de hoy sobre diálogos de gas con Venezuela refuerzan el riesgo de dependencia "
                "externa…'. NO repitas los titulares literalmente, solo interpreta su impacto "
                "en el sector. Si no hay 'prensa_del_dia' en el JSON, omite esta sub-sección.\n"
                "4) **Recomendaciones técnicas** — 3-5 bullets concretos y "
                "accionables. Si las noticias sugieren riesgos adicionales "
                "(caída de gas, retrasos regulatorios, conflictos regionales), "
                "incluye recomendaciones específicas asociadas a esos temas.\n\n"
                "FORMATO Y ESTILO:\n"
                "- Máximo 550 palabras. Párrafos de 2-3 líneas máximo.\n"
                "- Usa bullets (- o •) en vez de párrafos largos.\n"
                "- Redondea rangos a enteros (ej. '180–298 GWh', '63–77%').\n"
                "- Valores principales: máximo 2 decimales.\n"
                "- NO inventes datos: usa EXCLUSIVAMENTE los valores del JSON.\n"
                "- Menciona siempre unidades (GWh, COP/kWh, %) y fechas.\n"
                "- Usa Markdown con negritas y bullets. Escribe en español.\n\n"
                "REGLAS DE CONFIANZA DE PREDICCIONES:\n"
                "- Consulta 'confianza_modelos' en el JSON.\n"
                "- MUY_CONFIABLE/CONFIABLE → conclusiones firmes.\n"
                "- ACEPTABLE → señalar alta incertidumbre.\n"
                "- EXPERIMENTAL (ej. PRECIO_BOLSA) → NO formular conclusiones "
                "fuertes. Mencionar UNA sola vez, al final del sub-bloque de "
                "precios: 'Estas cifras provienen de un modelo experimental y "
                "sirven solo como referencia direccional.'\n"
                "- Al inicio de sección 2, incluir una frase breve: "
                "'Las proyecciones de Generación y Embalses son de alta "
                "confianza; las de Precio de Bolsa son experimentales.'\n"
                "- NO repetir el disclaimer de experimental en cada párrafo.\n"
                "- En sección 3, si mencionas tendencia o aumento de precio "
                "de bolsa, añade 'según un modelo experimental' en la misma "
                "línea para que la frase nunca quede sin contexto."
            )
            
            user_prompt = (
                f"Genera el informe ejecutivo del sector eléctrico colombiano "
                f"con los siguientes datos del sistema:\n\n"
                f"```json\n{contexto_json}\n```\n\n"
                f"Estructura tu respuesta con los títulos:\n"
                f"## 1. Situación actual del sistema\n"
                f"## 2. Tendencias y proyecciones\n"
                f"## 3. Riesgos y oportunidades\n"
                f"## 4. Recomendaciones técnicas"
            )
            
            # Llamada síncrona envuelta en thread para no bloquear
            def _call_ai():
                return agent.client.chat.completions.create(
                    model=agent.modelo,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=1800,
                )
            
            response = await asyncio.wait_for(
                asyncio.to_thread(_call_ai),
                timeout=25  # 25s para IA dentro del TOTAL_TIMEOUT de 30s
            )
            
            texto = response.choices[0].message.content.strip()
            
            if len(texto) < 100:
                logger.warning(f"[INFORME_IA] Respuesta muy corta ({len(texto)} chars)")
                return None
            
            logger.info(
                f"[INFORME_IA] Informe generado con {agent.provider}/{agent.modelo} "
                f"({len(texto)} chars)"
            )
            return texto
            
        except asyncio.TimeoutError:
            logger.warning("[INFORME_IA] Timeout esperando respuesta de IA")
            return None
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                logger.warning("[INFORME_IA] Rate limit alcanzado en IA")
            else:
                logger.error(f"[INFORME_IA] Error llamando IA: {e}")
            return None
    
    # ── Helper: Informe degradado sin IA (fallback) ──
    
    def _generar_informe_fallback(self, contexto: Dict[str, Any]) -> str:
        """
        Genera un informe de texto plano a partir del contexto,
        sin depender del servicio de IA.
        """
        hoy = contexto.get('fecha_consulta', '?')
        lines = []
        lines.append("📊 *INFORME EJECUTIVO — SECTOR ELÉCTRICO*")
        lines.append(f"📅 Fecha: {hoy}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        
        # ── Sección 1: Situación actual ──
        lines.append("*1. Situación actual del sistema*")
        fichas = contexto.get('estado_actual', {}).get('fichas', [])
        if fichas:
            for f in fichas:
                emoji_f = f.get('emoji', '•')
                ind = f.get('indicador', '?')
                val = f.get('valor', '?')
                und = f.get('unidad', '')
                fecha_f = f.get('fecha', '?')
                lines.append(f"  {emoji_f} {ind}: *{val} {und}* ({fecha_f})")
                ctx = f.get('contexto', {})
                if 'variacion_vs_promedio_pct' in ctx:
                    lines.append(f"     Variación vs 7d: {ctx['variacion_vs_promedio_pct']}%")
        else:
            lines.append("  Sin datos disponibles.")
        lines.append("")
        
        # ── Sección 2: Predicciones ──
        lines.append("*2. Tendencias y proyecciones*")
        for horizonte_key in ['1_mes', '6_meses']:
            pred_data = contexto.get('predicciones', {}).get(horizonte_key, {})
            titulo = pred_data.get('horizonte_titulo', horizonte_key)
            lines.append(f"  *{titulo}*:")
            for p in pred_data.get('indicadores', []):
                r = p.get('resumen', {})
                emoji_p = p.get('emoji', '•')
                ind = p.get('indicador', '?')[:25]
                avg = r.get('promedio_periodo', '?')
                hist = r.get('promedio_30d_historico', '?')
                cambio = r.get('cambio_pct', '?')
                tend = p.get('tendencia', '?')
                und = p.get('unidad', '')
                lines.append(f"    {emoji_p} {ind}: {avg} {und} (hist 30d: {hist}, cambio: {cambio}%) {tend}")
        lines.append("")
        
        # ── Sección 3: Anomalías ──
        lines.append("*3. Riesgos y oportunidades*")
        anom_data = contexto.get('anomalias', {})
        anomalias_list = anom_data.get('lista', [])
        if anomalias_list:
            sev_emoji = {'crítico': '🔴', 'alerta': '🟠'}
            for a in anomalias_list:
                se = sev_emoji.get(a.get('severidad', ''), '⚪')
                lines.append(
                    f"  {se} {a.get('indicador', '?')}: {a.get('valor_actual', '?')} "
                    f"{a.get('unidad', '')} — desvío {a.get('desviacion_pct', '?')}% "
                    f"({a.get('severidad', '?')})"
                )
        else:
            lines.append("  ✅ No se detectaron anomalías significativas.")
        lines.append("")
        
        # ── Sección 4: Recomendaciones ──
        lines.append("*4. Recomendaciones técnicas*")
        lines.append("  • Monitorear indicadores con desvío > 15%.")
        lines.append("  • Verificar niveles de embalses semanalmente.")
        lines.append("  • Revisar tendencia de precios si cambio > 20%.")
        lines.append("")
        lines.append("_⚠️ Informe generado sin IA (servicio no disponible)._")
        
        return "\n".join(lines)
    
    # ═══════════════════════════════════════════════════════════
    # HANDLER: NOTICIAS DEL SECTOR
    # ═══════════════════════════════════════════════════════════
    
    @handle_service_error
    async def _handle_noticias_sector(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Noticias relevantes del sector energético colombiano.
        Usa NewsService multi-fuente: top 3 + lista extendida + resumen IA.
        """
        data = {}
        errors = []
        
        if not self.news_service:
            errors.append(ErrorDetail(
                code="NEWS_UNAVAILABLE",
                message="Servicio de noticias no disponible. Configura GNEWS_API_KEY en .env"
            ))
            return data, errors
        
        try:
            enriched = await asyncio.wait_for(
                self.news_service.get_enriched_news(max_top=3, max_extra=7),
                timeout=self.SERVICE_TIMEOUT
            )
            
            top = enriched.get("top", [])
            otras = enriched.get("otras", [])
            
            # Top 3 noticias (contrato existente — sin cambios)
            data["noticias"] = [
                {
                    "titulo": n["titulo"],
                    "resumen": n["resumen_corto"],
                    "url": n["url"],
                    "fuente": n["fuente"],
                    "fecha": n["fecha_publicacion"],
                }
                for n in top
            ]
            data["total"] = len(top)
            data["opcion_regresar"] = {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal"
            }
            
            # Lista extendida (nuevo campo)
            if otras:
                data["otras_noticias"] = [
                    {
                        "titulo": n["titulo"],
                        "resumen": n["resumen_corto"],
                        "url": n["url"],
                        "fuente": n["fuente"],
                        "fecha": n["fecha_publicacion"],
                    }
                    for n in otras
                ]
            
            if not top:
                data["nota"] = (
                    "No se encontraron noticias relevantes sobre "
                    "el sector energético para hoy."
                )
            
            # Resumen general IA (best-effort)
            data["resumen_general"] = None
            all_for_summary = top + otras
            if len(all_for_summary) >= 3:
                try:
                    resumen = await self._generar_resumen_noticias(all_for_summary)
                    data["resumen_general"] = resumen
                except Exception as e:
                    logger.warning(f"[NOTICIAS] Resumen IA falló (no crítico): {e}")
            
            logger.info(
                f"[NOTICIAS] {len(top)} principales + "
                f"{len(otras)} extras, "
                f"fuentes={enriched.get('fuentes_usadas', [])}, "
                f"resumen={'sí' if data.get('resumen_general') else 'no'}"
            )
            
        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="NEWS_TIMEOUT",
                message="El servicio de noticias tardó demasiado"
            ))
        except Exception as e:
            logger.error(f"Error en noticias: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="NEWS_ERROR",
                message="Error al obtener noticias del sector"
            ))
        
        return data, errors
    
    async def _generar_resumen_noticias(
        self, noticias: List[Dict]
    ) -> Optional[str]:
        """
        Genera un resumen general de 3-4 frases con los titulares
        del día, orientado al Viceministro.
        
        Reutiliza AgentIA (Groq/OpenRouter) con patrón threadpool.
        Retorna None si la IA no está disponible o falla.
        """
        try:
            from domain.services.ai_service import AgentIA
            agent = AgentIA()
            
            if not agent.client:
                return None
            
            # Construir contexto con titulares
            titulares_ctx = "\n".join(
                f"- {n.get('titulo', '')} (Fuente: {n.get('fuente', '?')}, "
                f"Fecha: {n.get('fecha_publicacion', n.get('fecha', '?'))})"
                for n in noticias[:10]
            )
            
            system_prompt = (
                "Eres un analista senior del sector energético colombiano "
                "que asesora al Viceministro de Minas y Energía.\n\n"
                "Se te proporcionan los titulares de noticias del día.\n\n"
                "TAREA: Escribe un resumen ejecutivo de exactamente 3-4 frases "
                "que identifique los 2-3 grandes temas del día.\n\n"
                "REGLAS:\n"
                "- Centra el análisis en implicaciones para política pública "
                "y operación del sistema eléctrico colombiano.\n"
                "- NO repitas literalmente los titulares.\n"
                "- NO uses bullets ni listas; solo párrafo continuo.\n"
                "- Evita detalles triviales.\n"
                "- Máximo 120 palabras.\n"
                "- Escribe en español, tono profesional."
            )
            
            user_prompt = (
                f"Titulares de noticias energéticas de hoy:\n\n"
                f"{titulares_ctx}\n\n"
                f"Genera el resumen ejecutivo breve."
            )
            
            def _call_ai():
                return agent.client.chat.completions.create(
                    model=agent.modelo,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=300,
                )
            
            response = await asyncio.wait_for(
                asyncio.to_thread(_call_ai),
                timeout=15,
            )
            
            texto = response.choices[0].message.content.strip()
            if len(texto) < 30:
                logger.warning(
                    f"[NOTICIAS_RESUMEN] Respuesta demasiado corta "
                    f"({len(texto)} chars)"
                )
                return None
            
            logger.info(
                f"[NOTICIAS_RESUMEN] Resumen generado con "
                f"{agent.provider}/{agent.modelo} ({len(texto)} chars)"
            )
            return texto
            
        except asyncio.TimeoutError:
            logger.warning("[NOTICIAS_RESUMEN] Timeout IA")
            return None
        except Exception as e:
            logger.warning(f"[NOTICIAS_RESUMEN] Error IA: {e}")
            return None
    
    # ═══════════════════════════════════════════════════════════
    # HANDLER: MENÚ / AYUDA - Opciones del Chatbot WhatsApp
    # ═══════════════════════════════════════════════════════════
    
    @handle_service_error
    async def _handle_menu(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Menú principal del chatbot (4 opciones simplificadas)
        
        Enfocado en los 3 indicadores clave del Viceministro:
        - Generación Total del Sistema (GWh)
        - Precio de Bolsa (COP/kWh)
        - Porcentaje de Embalses (%)
        """
        data = {
            "mensaje_bienvenida": (
                "¡Hola! 👋 Soy el asistente del *Portal Energético* del "
                "Ministerio de Minas y Energía de Colombia.\n\n"
                "Puedo informarte sobre los indicadores clave del sector "
                "energético. También puedes escribirme cualquier pregunta "
                "en cualquier momento."
            ),
            "indicadores_clave": [
                "⚡ Generación Total del Sistema (GWh)",
                "💰 Precio de Bolsa Nacional (COP/kWh)",
                "💧 Porcentaje de Embalses (%)"
            ],
            "menu_principal": [
                {
                    "numero": 1,
                    "id": "estado_actual",
                    "titulo": "Estado actual del sector",
                    "emoji": "📊",
                    "descripcion": "Muestra las 3 fichas de indicadores clave: Generación Total, Precio de Bolsa y Porcentaje de Embalses con sus valores actuales."
                },
                {
                    "numero": 2,
                    "id": "predicciones_sector",
                    "titulo": "Predicciones del sector",
                    "emoji": "🔮",
                    "descripcion": "Predicciones de los 3 indicadores clave. Puedes elegir el horizonte temporal.",
                    "sub_menu": {
                        "instruccion": "¿Para qué periodo deseas las predicciones?",
                        "opciones_horizonte": [
                            {"numero": 1, "id": "1_semana", "titulo": "Una semana", "dias": 7},
                            {"numero": 2, "id": "1_mes", "titulo": "Un mes", "dias": 30},
                            {"numero": 3, "id": "6_meses", "titulo": "Los próximos 6 meses", "dias": 180},
                            {"numero": 4, "id": "1_ano", "titulo": "El próximo año", "dias": 365},
                            {"numero": 5, "id": "personalizado", "titulo": "Fecha personalizada", "formato": "DD-MM-AAAA", "descripcion": "Escribe la fecha exacta en formato día-mes-año"}
                        ]
                    }
                },
                {
                    "numero": 3,
                    "id": "anomalias_sector",
                    "titulo": "Anomalías detectadas del sector",
                    "emoji": "🚨",
                    "descripcion": "Anomalías en el estado actual de los 3 indicadores clave y anomalías en las predicciones disponibles."
                },
                {
                    "numero": 4,
                    "id": "noticias_sector",
                    "titulo": "Noticias del sector",
                    "emoji": "📰",
                    "descripcion": "Las 3 noticias más relevantes sobre el sector energético colombiano."
                },
                {
                    "numero": 5,
                    "id": "mas_informacion",
                    "titulo": "Más información del sector energético",
                    "emoji": "📋",
                    "descripcion": "Accede al informe ejecutivo completo o haz una pregunta específica.",
                    "sub_menu": {
                        "instruccion": "¿Qué información necesitas?",
                        "opciones": [
                            {
                                "numero": 1,
                                "id": "informe_ejecutivo",
                                "titulo": "Informe ejecutivo completo",
                                "descripcion": "Todas las métricas del sector con KPIs, predicciones, análisis estadístico y recomendaciones técnicas."
                            },
                            {
                                "numero": 2,
                                "id": "pregunta_libre",
                                "titulo": "Preguntar algo específico",
                                "descripcion": "Escribe tu pregunta y la IA te responderá con datos del sector energético."
                            }
                        ]
                    }
                }
            ],
            "nota_libre": (
                "💡 En cualquier momento puedes escribir tu pregunta directamente "
                "sin necesidad de usar el menú. La IA analizará tu consulta y "
                "te responderá con datos actualizados del sector energético."
            ),
            "opcion_regresar": {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal"
            }
        }
        
        return data, []
    
    # ─────────────────────────────────────────────────────────
    # UTILIDADES
    # ─────────────────────────────────────────────────────────
    
    @staticmethod
    def _sanitize_numpy_types(obj):
        """
        Convierte recursivamente tipos numpy a tipos nativos de Python
        para serialización JSON/Pydantic.
        """
        if isinstance(obj, dict):
            return {k: ChatbotOrchestratorService._sanitize_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [ChatbotOrchestratorService._sanitize_numpy_types(item) for item in obj]
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        elif isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return obj

    def _serialize_anomalia(self, anomalia: Anomalia) -> Dict[str, Any]:
        """
        Convierte un objeto Anomalia a diccionario para JSON
        
        Args:
            anomalia: Objeto Anomalia
            
        Returns:
            Diccionario con datos de la anomalía
        """
        return {
            'sector': anomalia.sector,
            'metrica': anomalia.metric,
            'severidad': anomalia.severity.name,
            'severidad_nivel': anomalia.severity.value,
            'valor_actual': anomalia.current_value,
            'valor_esperado': anomalia.expected_value,
            'umbral': anomalia.threshold,
            'descripcion': anomalia.description,
            'timestamp': anomalia.timestamp.isoformat() if anomalia.timestamp else None
        }
    
    def _create_error_response(
        self,
        request: OrchestratorRequest,
        message: str,
        errors: List[ErrorDetail]
    ) -> OrchestratorResponse:
        """Crea una respuesta de error estándar"""
        return OrchestratorResponse(
            status="ERROR",
            message=message,
            data={},
            errors=errors,
            timestamp=datetime.utcnow(),
            sessionId=request.sessionId,
            intent=request.intent
        )
