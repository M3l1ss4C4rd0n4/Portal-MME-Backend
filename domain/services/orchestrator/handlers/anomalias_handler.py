"""
Mixin: Anomalías handlers (detección comparativa real vs histórico y predicciones).
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = logging.getLogger(__name__)


class AnomaliaHandlerMixin:
    """Mixin para handlers de detección de anomalías."""

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

            orden_sev = {'crítico': 0, 'alerta': 1, 'normal': 2}
            anomalias.sort(key=lambda a: orden_sev.get(a.get('severidad', 'normal'), 9))

            # Solo incluir anomalías reales (alerta o crítico), no 'normal'
            anomalias_reales = [a for a in anomalias if a.get('severidad') != 'normal']

            data['anomalias'] = anomalias_reales
            data['total_evaluadas'] = len(anomalias)
            data['total_anomalias'] = len(anomalias_reales)
            data['fecha_analisis'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            data['detalle_completo'] = anomalias

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
                'metric_id': 'PPPrecBolsNaci',
                'entity': 'Sistema',
                'fuente_pred': 'PRECIO_BOLSA',
            },
            {
                'indicador': 'Embalses',
                'emoji': '💧',
                'unidad': '%',
                'metric_id': None,
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
        from domain.services.confianza_politica import (
            get_confianza_politica,
            obtener_disclaimer,
        )

        resultado: Dict[str, Any] = {
            'indicador': indicador,
            'emoji': emoji,
            'unidad': unidad,
        }

        # ── 1. Valor actual y serie histórica ──
        if metric_id is None and fuente_pred == 'EMBALSES_PCT':
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

        # ── 3. Predicción para la fecha del dato real ──
        politica_pred = get_confianza_politica(fuente_pred)
        nivel_confianza = politica_pred['nivel']

        delta_pred_pct = None
        valor_predicho = None
        confianza_pred = None
        try:
            if self.predictions_service and fecha_dato:
                from infrastructure.database.manager import db_manager
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

                    if nivel_confianza in ('MUY_CONFIABLE', 'CONFIABLE'):
                        if valor_predicho != 0:
                            delta_pred_pct = abs((valor_actual - valor_predicho) / valor_predicho) * 100
                        resultado['delta_pred_pct'] = round(delta_pred_pct, 1) if delta_pred_pct is not None else None
                    else:
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

        # ── 4. Desviación máxima y severidad CONSIDERANDO IMPACTO OPERATIVO ──
        # La severidad depende de la DIRECCIÓN de la desviación, no solo su magnitud
        desviaciones = [delta_hist_pct]
        if delta_pred_pct is not None and not resultado.get('prediccion_excluida'):
            desviaciones.append(delta_pred_pct)

        desviacion_pct = max(desviaciones) if desviaciones else 0.0
        resultado['desviacion_pct'] = round(desviacion_pct, 1)

        # Calcular desviación con signo (positivo = por encima, negativo = por debajo)
        desviacion_signada = ((valor_actual - avg_hist) / avg_hist * 100) if avg_hist != 0 else 0

        # ═══════════════════════════════════════════════════════════════════════
        # UMBRALES POR INDICADOR CON DIRECCIÓN (basado en impacto operativo real)
        # ═══════════════════════════════════════════════════════════════════════
        
        severidad = 'normal'
        razon_severidad = []
        
        if indicador == 'Generación Total':
            # GENERACIÓN: Baja es problema (déficit), alta es normal (cubre demanda)
            # UMBRALES ALINEADOS con _build_tabla_indicadores_clave en estado_actual_handler.py
            if desviacion_signada < -15:
                severidad = 'crítico'
                razon_severidad.append(f"Generación {abs(desviacion_signada):.1f}% por debajo del promedio - riesgo de déficit de oferta")
            elif desviacion_signada < -8:
                severidad = 'alerta'
                razon_severidad.append(f"Generación {abs(desviacion_signada):.1f}% por debajo del promedio - monitorear disponibilidad")
            # Si está por encima (> +15%), es NORMAL (no es malo tener exceso de generación)
            
        elif indicador == 'Precio de Bolsa':
            # PRECIO: Alto es problema (costos), bajo puede ser normal o bueno
            # UMBRALES ALINEADOS con _build_tabla_indicadores_clave en estado_actual_handler.py
            if desviacion_signada > 25:
                severidad = 'crítico'
                razon_severidad.append(f"Precio {desviacion_signada:.1f}% por encima del promedio - impacto severo en costos de suministro")
            elif desviacion_signada > 12:
                severidad = 'alerta'
                razon_severidad.append(f"Precio {desviacion_signada:.1f}% por encima del promedio - presión en costos")
            # Si está por debajo (< -25%), es NORMAL o INFO (bueno para consumidores)
            
        elif indicador == 'Embalses':
            # EMBALSES: Umbrales OFICIALES según IDEAM y UNGRD (Colombia)
            # 
            # POR NIVEL ALTO (riesgo de desbordamiento):
            #   > 95%: Alerta Roja - Acción inmediata, desbordamiento inminente
            #   90-95%: Alerta Naranja - Preparación para descargas preventivas
            #   80-90%: Alerta Amarilla - Vigilancia, monitorear caudales
            #   40-80%: Normal - Operación estable
            #
            # POR NIVEL BAJO (riesgo de desabastecimiento/apagón):
            #   < 27%: Alerta Roja - Riesgo crítico de racionamiento
            #   27-40%: Alerta Naranja/Amarilla - Alerta de seguimiento
            #   40-80%: Normal - Operación estable
            
            # RIESGO POR NIVEL CRÍTICAMENTE BAJO (según IDEAM)
            if valor_actual < 27:
                severidad = 'crítico'
                razon_severidad.append(f"ALERTA ROJA: Nivel crítico ({valor_actual:.1f}%) - Riesgo de racionamiento/apagón. Activar medidas de choque.")
            elif valor_actual < 40:
                severidad = 'alerta'
                razon_severidad.append(f"ALERTA: Nivel bajo ({valor_actual:.1f}%) - Alerta de seguimiento. Preparar medidas preventivas.")
            
            # RIESGO POR NIVEL ALTO (riesgo de desbordamiento)
            elif valor_actual > 95:
                severidad = 'crítico'
                razon_severidad.append(f"ALERTA ROJA: Nivel crítico ({valor_actual:.1f}%) - Desbordamiento inminente. Descargas masivas en curso.")
            elif valor_actual > 90:
                severidad = 'alerta'
                razon_severidad.append(f"ALERTA NARANJA: Nivel muy alto ({valor_actual:.1f}%) - Preparar descargas preventivas. Avisar comunidades aguas abajo.")
            elif valor_actual > 80:
                severidad = 'alerta'
                razon_severidad.append(f"ALERTA AMARILLA: Nivel elevado ({valor_actual:.1f}%) - Vigilancia activa. Monitorear caudales de entrada.")
            
            # RIESGO POR TENDENCIA (cambios rápidos)
            elif desviacion_signada < -25:
                severidad = 'alerta'
                razon_severidad.append(f"Caída acelerada ({desviacion_signada:.1f}%) - Riesgo de agotamiento rápido de reservas")
        else:
            # Indicador genérico: usar desviación simple
            if desviacion_pct > 30:
                severidad = 'crítico'
            elif desviacion_pct > 15:
                severidad = 'alerta'
        
        resultado['severidad'] = severidad
        resultado['desviacion_signada'] = round(desviacion_signada, 1)
        if razon_severidad:
            resultado['razon_severidad'] = '; '.join(razon_severidad)

        # ═══════════════════════════════════════════════════════════════════════
        # MÉTODO HÍBRIDO COMPLETO: 4 Dimensiones de Análisis
        # ═══════════════════════════════════════════════════════════════════════
        
        analisis_hibrido = {}
        
        # DIMENSIÓN 1: Tendencia de Corto Plazo (últimos 7 días)
        tendencia_7d = self._calcular_tendencia_lineal(metric_id, entity, fuente_pred, dias=7)
        if tendencia_7d:
            analisis_hibrido['tendencia_corto_plazo'] = tendencia_7d
            logger.debug(f"[HÍBRIDO] Tendencia 7d para {indicador}: {tendencia_7d['direccion']}")
        
        # DIMENSIÓN 2: Contexto Estacional (YoY) - ya implementado abajo
        # Se mantiene como 'yoy' en el resultado principal
        
        # DIMENSIÓN 3: Percentiles Históricos (5 años)
        percentiles = self._calcular_percentiles_historicos(metric_id, entity, fuente_pred, valor_actual)
        if percentiles:
            analisis_hibrido['percentiles_historicos'] = percentiles
            logger.debug(f"[HÍBRIDO] Percentil para {indicador}: {percentiles['percentil_actual']}")
        
        # DIMENSIÓN 4: Z-Score (último año)
        zscore = self._calcular_zscore(metric_id, entity, fuente_pred, valor_actual)
        if zscore:
            analisis_hibrido['zscore'] = zscore
            logger.debug(f"[HÍBRIDO] Z-score para {indicador}: {zscore['z_score']}")
        
        # Agregar análisis híbrido al resultado si hay datos
        if analisis_hibrido:
            resultado['analisis_hibrido'] = analisis_hibrido
            logger.info(f"[HÍBRIDO] Análisis completo calculado para {indicador}")

        # ── 5. Comparación Year-over-Year (mismo período año anterior) ──
        yoy_data = self._get_yoy_comparison(metric_id, entity, fuente_pred)
        if yoy_data:
            resultado['yoy'] = yoy_data
            yoy_change = yoy_data.get('cambio_pct', 0)
        else:
            yoy_change = None
        
        # ── 6. Comentario descriptivo NATURAL (versión legible para humanos) ──
        comentario = self._generar_descripcion_natural(
            indicador=indicador,
            valor_actual=valor_actual,
            unidad=unidad,
            avg_hist=avg_hist,
            desviacion_pct=desviacion_pct,
            desviacion_signada=desviacion_signada,
            yoy_change=yoy_change,
            yoy_data=yoy_data,
            analisis_hibrido=analisis_hibrido,
            valor_predicho=valor_predicho,
            confianza_pred=confianza_pred,
            prediccion_excluida=resultado.get('prediccion_excluida'),
            severidad=severidad,
            razon_severidad=razon_severidad
        )
        
        resultado['comentario'] = comentario

        resultado['fuente_prediccion'] = fuente_pred
        resultado['nivel_confianza_prediccion'] = nivel_confianza
        resultado['aplicar_disclaimer_prediccion'] = politica_pred['disclaimer']
        resultado['disclaimer_confianza'] = obtener_disclaimer(fuente_pred)

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

    def _get_yoy_comparison(
        self,
        metric_id: Optional[str],
        entity: Optional[str],
        fuente_pred: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene comparación Year-over-Year (mismo período año anterior).
        
        Returns:
            Dict con valor_anio_pasado, cambio_pct, interpretación
            o None si no hay datos suficientes
        """
        try:
            from datetime import datetime, timedelta
            from infrastructure.database.manager import db_manager
            
            # Fecha actual y fecha hace 1 año
            hoy = datetime.now()
            fecha_actual = hoy.strftime('%Y-%m-%d')
            fecha_hace_1y = (hoy - timedelta(days=365)).strftime('%Y-%m-%d')
            
            # Query según tipo de métrica
            if fuente_pred == 'EMBALSES_PCT':
                # Para embalses, calcular porcentaje desde metrics (la tabla embalses_diario está vacía)
                query = """
                    WITH embalses_actual AS (
                        SELECT fecha,
                               SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) /
                               NULLIF(SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END), 0) * 100 as pct
                        FROM metrics
                        WHERE metrica IN ('VoluUtilDiarEner', 'CapaUtilDiarEner')
                          AND entidad = 'Embalse'
                          AND fecha BETWEEN %s AND %s
                        GROUP BY fecha
                        HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                    )
                    SELECT AVG(pct) as valor_promedio
                    FROM embalses_actual
                """
                params = (
                    (hoy - timedelta(days=30)).strftime('%Y-%m-%d'),
                    fecha_actual
                )
            elif metric_id:
                # Para métricas XM
                query = """
                    SELECT AVG(valor_gwh) as valor_promedio
                    FROM metrics
                    WHERE metrica = %s
                      AND fecha BETWEEN %s AND %s
                      AND (%s IS NULL OR entidad = %s)
                """
                params = (
                    metric_id,
                    (hoy - timedelta(days=30)).strftime('%Y-%m-%d'),
                    fecha_actual,
                    entity, entity
                )
            else:
                return None
            
            # Ejecutar query
            df_actual = db_manager.query_df(query, params=params)
            
            # Query año pasado (mismo período)
            fecha_hace_1y_inicio = (hoy - timedelta(days=365+30)).strftime('%Y-%m-%d')
            
            if fuente_pred == 'EMBALSES_PCT':
                query_yp = """
                    WITH embalses_yp AS (
                        SELECT fecha,
                               SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) /
                               NULLIF(SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END), 0) * 100 as pct
                        FROM metrics
                        WHERE metrica IN ('VoluUtilDiarEner', 'CapaUtilDiarEner')
                          AND entidad = 'Embalse'
                          AND fecha BETWEEN %s AND %s
                        GROUP BY fecha
                        HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                    )
                    SELECT AVG(pct) as valor_promedio
                    FROM embalses_yp
                """
                params_yp = (fecha_hace_1y_inicio, fecha_hace_1y)
            else:
                query_yp = """
                    SELECT AVG(valor_gwh) as valor_promedio
                    FROM metrics
                    WHERE metrica = %s
                      AND fecha BETWEEN %s AND %s
                      AND (%s IS NULL OR entidad = %s)
                """
                params_yp = (metric_id, fecha_hace_1y_inicio, fecha_hace_1y, entity, entity)
            
            df_yp = db_manager.query_df(query_yp, params=params_yp)
            
            if df_actual.empty or df_yp.empty:
                return None
                
            valor_actual = df_actual['valor_promedio'].iloc[0]
            valor_yp = df_yp['valor_promedio'].iloc[0]
            
            if pd.isna(valor_actual) or pd.isna(valor_yp) or valor_yp == 0:
                return None
            
            cambio_pct = ((valor_actual - valor_yp) / valor_yp) * 100
            
            # Interpretación
            if abs(cambio_pct) < 5:
                interpretacion = 'estable'
            elif cambio_pct > 10:
                interpretacion = 'crecimiento_fuerte'
            elif cambio_pct > 5:
                interpretacion = 'crecimiento_moderado'
            elif cambio_pct < -10:
                interpretacion = 'caida_fuerte'
            else:
                interpretacion = 'caida_moderada'
            
            return {
                'valor_actual': round(float(valor_actual), 2),
                'valor_anio_pasado': round(float(valor_yp), 2),
                'cambio_pct': round(float(cambio_pct), 1),
                'interpretacion': interpretacion,
                'periodo_comparacion': f"{(hoy - timedelta(days=30)).strftime('%d/%m')} - {hoy.strftime('%d/%m')}"
            }
            
        except Exception as e:
            logger.warning(f"[YoY] Error calculando comparación anual: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODO HÍBRIDO COMPLETO: 4 Dimensiones de Análisis
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _calcular_tendencia_lineal(
        self,
        metric_id: Optional[str],
        entity: Optional[str],
        fuente_pred: str,
        dias: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Dimensión 1: Tendencia de Corto Plazo (regresión lineal)
        
        Calcula la pendiente de la tendencia sobre los últimos N días
        para detectar si el indicador está subiendo o bajando AHORA.
        
        Returns:
            Dict con pendiente, dirección, fuerza y proyección
        """
        try:
            from infrastructure.database.manager import db_manager
            from datetime import datetime, timedelta
            import numpy as np
            
            hoy = datetime.now()
            fecha_inicio = (hoy - timedelta(days=dias)).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
            
            # Obtener serie de datos según tipo de métrica
            if fuente_pred == 'EMBALSES_PCT':
                query = """
                    WITH embalses_diarios AS (
                        SELECT fecha,
                               SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) /
                               NULLIF(SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END), 0) * 100 as pct
                        FROM metrics
                        WHERE metrica IN ('VoluUtilDiarEner', 'CapaUtilDiarEner')
                          AND entidad = 'Embalse'
                          AND fecha >= %s AND fecha <= %s
                        GROUP BY fecha
                        HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                    )
                    SELECT fecha, pct as valor
                    FROM embalses_diarios
                    ORDER BY fecha ASC
                """
                params = (fecha_inicio, fecha_fin)
            elif metric_id:
                query = """
                    SELECT fecha, valor_gwh as valor
                    FROM metrics
                    WHERE metrica = %s
                      AND (%s IS NULL OR entidad = %s)
                      AND fecha >= %s AND fecha <= %s
                    ORDER BY fecha ASC
                """
                params = (metric_id, entity, entity, fecha_inicio, fecha_fin)
            else:
                return None
            
            df = db_manager.query_df(query, params=params)
            
            if df is None or len(df) < 3:  # Necesitamos al menos 3 puntos para tendencia
                return None
            
            # Preparar datos para regresión lineal
            df = df.dropna(subset=['valor'])
            if len(df) < 3:
                return None
            
            # X = días (0, 1, 2, ...), Y = valores
            x = np.arange(len(df))
            y = df['valor'].values
            
            # Regresión lineal: y = mx + b
            m, b = np.polyfit(x, y, 1)  # m = pendiente
            
            # Calcular métricas de la tendencia
            valor_promedio = y.mean()
            if valor_promedio != 0:
                pendiente_pct_diaria = (m / valor_promedio) * 100
            else:
                pendiente_pct_diaria = 0
            
            # Dirección y fuerza
            if pendiente_pct_diaria > 1.0:
                direccion = 'alcista_fuerte'
                emoji = '📈'
                descripcion = f"Subiendo {pendiente_pct_diaria:.1f}% diario"
            elif pendiente_pct_diaria > 0.3:
                direccion = 'alcista'
                emoji = '↗️'
                descripcion = f"Tendencia al alza ({pendiente_pct_diaria:.1f}%/día)"
            elif pendiente_pct_diaria < -1.0:
                direccion = 'bajista_fuerte'
                emoji = '📉'
                descripcion = f"Bajando {abs(pendiente_pct_diaria):.1f}% diario"
            elif pendiente_pct_diaria < -0.3:
                direccion = 'bajista'
                emoji = '↘️'
                descripcion = f"Tendencia a la baja ({abs(pendiente_pct_diaria):.1f}%/día)"
            else:
                direccion = 'estable'
                emoji = '➡️'
                descripcion = "Sin tendencia clara"
            
            # Proyección a 7 días
            proyeccion_7d = y[-1] + (m * 7)
            
            # R² (coeficiente de determinación)
            ss_res = np.sum((y - (m * x + b)) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            
            return {
                'pendiente': round(float(m), 4),
                'pendiente_pct_diaria': round(float(pendiente_pct_diaria), 2),
                'direccion': direccion,
                'emoji': emoji,
                'descripcion': descripcion,
                'proyeccion_7dias': round(float(proyeccion_7d), 2),
                'r_squared': round(float(r_squared), 3),
                'dias_analizados': len(df),
                'confianza_tendencia': 'alta' if r_squared > 0.7 else 'media' if r_squared > 0.4 else 'baja'
            }
            
        except Exception as e:
            logger.warning(f"[TENDENCIA] Error calculando tendencia lineal: {e}")
            return None
    
    def _calcular_percentiles_historicos(
        self,
        metric_id: Optional[str],
        entity: Optional[str],
        fuente_pred: str,
        valor_actual: float
    ) -> Optional[Dict[str, Any]]:
        """
        Dimensión 3: Percentiles Históricos (últimos 5 años)
        
        Calcula en qué percentil del histórico se encuentra el valor actual
        para entender qué tan extremo es.
        
        Returns:
            Dict con percentiles, cuartil y interpretación
        """
        try:
            from infrastructure.database.manager import db_manager
            from datetime import datetime, timedelta
            
            # Período: últimos 5 años
            hoy = datetime.now()
            fecha_inicio = (hoy - timedelta(days=5*365)).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
            
            # Obtener todos los datos históricos según tipo de métrica
            if fuente_pred == 'EMBALSES_PCT':
                query = """
                    WITH embalses_historico AS (
                        SELECT fecha,
                               SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) /
                               NULLIF(SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END), 0) * 100 as pct
                        FROM metrics
                        WHERE metrica IN ('VoluUtilDiarEner', 'CapaUtilDiarEner')
                          AND entidad = 'Embalse'
                          AND fecha >= %s AND fecha <= %s
                        GROUP BY fecha
                        HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                    )
                    SELECT pct as valor
                    FROM embalses_historico
                    WHERE pct IS NOT NULL
                """
                params = (fecha_inicio, fecha_fin)
            elif metric_id:
                query = """
                    SELECT valor_gwh as valor
                    FROM metrics
                    WHERE metrica = %s
                      AND (%s IS NULL OR entidad = %s)
                      AND fecha >= %s AND fecha <= %s
                      AND valor_gwh IS NOT NULL
                """
                params = (metric_id, entity, entity, fecha_inicio, fecha_fin)
            else:
                return None
            
            df = db_manager.query_df(query, params=params)
            
            if df is None or len(df) < 30:  # Necesitamos suficientes datos
                return None
            
            valores = df['valor'].values
            
            # Calcular percentiles
            import numpy as np
            percentiles = {
                'p05': np.percentile(valores, 5),
                'p25': np.percentile(valores, 25),
                'p50': np.percentile(valores, 50),
                'p75': np.percentile(valores, 75),
                'p95': np.percentile(valores, 95),
            }
            
            # Calcular percentil del valor actual
            percentil_actual = (valores < valor_actual).mean() * 100
            
            # Determinar cuartil
            if percentil_actual <= 25:
                cuartil = 'Q1 (bajo)'
                emoji = '🔴'
                interpretacion = f"Nivel bajo (percentil {percentil_actual:.0f}, solo {percentil_actual:.0f}% de días han sido menores)"
            elif percentil_actual <= 50:
                cuartil = 'Q2 (medio-bajo)'
                emoji = '🟡'
                interpretacion = f"Nivel medio-bajo (percentil {percentil_actual:.0f})"
            elif percentil_actual <= 75:
                cuartil = 'Q3 (medio-alto)'
                emoji = '🟢'
                interpretacion = f"Nivel medio-alto (percentil {percentil_actual:.0f})"
            else:
                cuartil = 'Q4 (alto)'
                emoji = '🔴'
                interpretacion = f"Nivel alto (percentil {percentil_actual:.0f}, solo {100-percentil_actual:.0f}% de días han sido mayores)"
            
            return {
                'percentil_actual': round(float(percentil_actual), 1),
                'cuartil': cuartil,
                'emoji': emoji,
                'interpretacion': interpretacion,
                'percentiles_referencia': {k: round(float(v), 2) for k, v in percentiles.items()},
                'total_datos_historicos': len(valores),
                'rango_historico': {
                    'min': round(float(valores.min()), 2),
                    'max': round(float(valores.max()), 2)
                }
            }
            
        except Exception as e:
            logger.warning(f"[PERCENTILES] Error calculando percentiles: {e}")
            return None
    
    def _calcular_zscore(
        self,
        metric_id: Optional[str],
        entity: Optional[str],
        fuente_pred: str,
        valor_actual: float,
        ventana_dias: int = 365
    ) -> Optional[Dict[str, Any]]:
        """
        Dimensión 4: Z-Score (desviación estándar)
        
        Calcula cuántas desviaciones estándar está el valor actual
        del promedio histórico (último año).
        
        Returns:
            Dict con z-score, interpretación y nivel de anomalía
        """
        try:
            from infrastructure.database.manager import db_manager
            from datetime import datetime, timedelta
            import numpy as np
            
            # Período: último año (para tener varianza representativa)
            hoy = datetime.now()
            fecha_inicio = (hoy - timedelta(days=ventana_dias)).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
            
            # Obtener datos históricos
            if fuente_pred == 'EMBALSES_PCT':
                query = """
                    WITH embalses_data AS (
                        SELECT fecha,
                               SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) /
                               NULLIF(SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END), 0) * 100 as pct
                        FROM metrics
                        WHERE metrica IN ('VoluUtilDiarEner', 'CapaUtilDiarEner')
                          AND entidad = 'Embalse'
                          AND fecha >= %s AND fecha <= %s
                        GROUP BY fecha
                        HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                    )
                    SELECT pct as valor
                    FROM embalses_data
                    WHERE pct IS NOT NULL
                """
                params = (fecha_inicio, fecha_fin)
            elif metric_id:
                query = """
                    SELECT valor_gwh as valor
                    FROM metrics
                    WHERE metrica = %s
                      AND (%s IS NULL OR entidad = %s)
                      AND fecha >= %s AND fecha <= %s
                      AND valor_gwh IS NOT NULL
                """
                params = (metric_id, entity, entity, fecha_inicio, fecha_fin)
            else:
                return None
            
            df = db_manager.query_df(query, params=params)
            
            if df is None or len(df) < 30:
                return None
            
            valores = df['valor'].values
            
            # Calcular estadísticos
            media = np.mean(valores)
            desviacion_std = np.std(valores, ddof=1)  # ddof=1 para muestra
            
            if desviacion_std == 0:
                return None
            
            # Z-score
            z_score = (valor_actual - media) / desviacion_std
            
            # Interpretación según magnitud
            abs_z = abs(z_score)
            if abs_z > 3:
                nivel = 'extremo'
                interpretacion = 'Muy anormal (>99.7% de casos)'
                emoji = '🔴'
            elif abs_z > 2:
                nivel = 'muy_alto'
                interpretacion = 'Significativamente anormal (>95% de casos)'
                emoji = '🟠'
            elif abs_z > 1:
                nivel = 'moderado'
                interpretacion = 'Moderadamente inusual (~68% de casos)'
                emoji = '🟡'
            else:
                nivel = 'normal'
                interpretacion = 'Dentro de lo normal (~68% de casos)'
                emoji = '🟢'
            
            # Dirección
            if z_score > 0:
                direccion = 'por_encima'
                texto_direccion = 'por encima'
            else:
                direccion = 'por_debajo'
                texto_direccion = 'por debajo'
            
            return {
                'z_score': round(float(z_score), 2),
                'valor_absoluto': round(float(abs_z), 2),
                'nivel': nivel,
                'interpretacion': interpretacion,
                'emoji': emoji,
                'direccion': direccion,
                'texto_direccion': texto_direccion,
                'media_historica': round(float(media), 2),
                'desviacion_std': round(float(desviacion_std), 2),
                'dias_analizados': len(valores)
            }
            
        except Exception as e:
            logger.warning(f"[ZSCORE] Error calculando Z-score: {e}")
            return None


    def _generar_descripcion_natural(
        self,
        indicador: str,
        valor_actual: float,
        unidad: str,
        avg_hist: float,
        desviacion_pct: float,
        desviacion_signada: float,
        yoy_change: Optional[float],
        yoy_data: Optional[Dict],
        analisis_hibrido: Dict,
        valor_predicho: Optional[float],
        confianza_pred: Optional[float],
        prediccion_excluida: bool,
        severidad: str,
        razon_severidad: List[str]
    ) -> str:
        """
        Genera una descripción natural y entendible para humanos de la anomalía.
        Evita tecnicismos innecesarios y usa lenguaje claro.
        """
        partes = []
        
        # 1. Estado actual (frase inicial clara)
        if indicador == 'Precio de Bolsa':
            partes.append(f"El precio de bolsa está en {valor_actual:.1f} {unidad}")
        elif indicador == 'Generación Total':
            partes.append(f"La generación del sistema es de {valor_actual:.1f} {unidad}")
        elif indicador == 'Embalses':
            partes.append(f"Los embalses se encuentran al {valor_actual:.1f}% de su capacidad")
        else:
            partes.append(f"{indicador}: {valor_actual:.1f} {unidad}")
        
        # 2. Comparación con promedio (solo si hay desviación significativa)
        if desviacion_pct > 5:  # Solo mencionar si es notable
            diferencia = abs(valor_actual - avg_hist)
            if desviacion_signada > 0:
                comparacion = f"{diferencia:.1f} {unidad} por encima del promedio mensual"
            else:
                comparacion = f"{diferencia:.1f} {unidad} por debajo del promedio mensual"
            partes.append(f", {comparacion}")
        
        # 3. Contexto año anterior (simplificado)
        if yoy_change is not None and abs(yoy_change) > 10:
            if yoy_change > 0:
                partes.append(f". Esto representa un aumento del {yoy_change:.1f}% respecto al año pasado")
            else:
                partes.append(f". Esto representa una disminución del {abs(yoy_change):.1f}% respecto al año pasado")
        
        # 4. Tendencia actual (si está disponible)
        if analisis_hibrido and 'tendencia_corto_plazo' in analisis_hibrido:
            t = analisis_hibrido['tendencia_corto_plazo']
            direccion = t.get('texto_direccion', 'estable')
            if 'alcista' in t.get('direccion', ''):
                partes.append(f". La tendencia es alcista {t.get('descripcion', '')}")
            elif 'bajista' in t.get('direccion', ''):
                partes.append(f". La tendencia es a la baja {t.get('descripcion', '')}")
        
        # 5. Nivel de rareza (simplificado)
        if analisis_hibrido and 'percentiles_historicos' in analisis_hibrido:
            p = analisis_hibrido['percentiles_historicos']
            percentil = p.get('percentil_actual', 50)
            if percentil > 80:
                partes.append(f". Este es un valor alto históricamente (percentil {percentil:.0f})")
            elif percentil < 20:
                partes.append(f". Este es un valor bajo históricamente (percentil {percentil:.0f})")
        
        # 6. Predicción (si es relevante)
        if valor_predicho is not None and confianza_pred is not None and confianza_pred > 0.7:
            if prediccion_excluida:
                partes.append(f". La predicción esperaba {valor_predicho:.1f} {unidad}, pero no se usó por baja confianza")
            else:
                diff_pred = abs(valor_actual - valor_predicho)
                if diff_pred > (valor_actual * 0.1):  # Si hay diferencia significativa
                    if valor_actual > valor_predicho:
                        partes.append(f". El valor actual es {diff_pred:.1f} {unidad} mayor al esperado ({valor_predicho:.1f})")
                    else:
                        partes.append(f". El valor actual es {diff_pred:.1f} {unidad} menor al esperado ({valor_predicho:.1f})")
        
        # 7. Razón de severidad (si existe)
        if razon_severidad:
            # Tomar solo la primera razón y simplificarla
            razon = razon_severidad[0]
            if severidad == 'crítico':
                partes.append(f". ⚠️ ATENCIÓN: {razon}")
            elif severidad == 'alerta':
                partes.append(f". ℹ️ Nota: {razon}")
        
        # Unir todo
        descripcion = "".join(partes)
        
        # Limpiar espacios dobles y agregar punto final si falta
        descripcion = descripcion.replace("  ", " ").strip()
        if not descripcion.endswith('.'):
            descripcion += '.'
        
        return descripcion
