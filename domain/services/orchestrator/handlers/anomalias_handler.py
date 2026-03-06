"""
Mixin: Anomalías handlers (detección comparativa real vs histórico y predicciones).
"""
import asyncio
import logging
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
                'metric_id': 'PrecBolsNaci',
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

        # ── 4. Desviación máxima y severidad ──
        desviaciones = [delta_hist_pct]
        if delta_pred_pct is not None and not resultado.get('prediccion_excluida'):
            desviaciones.append(delta_pred_pct)

        desviacion_pct = max(desviaciones) if desviaciones else 0.0
        resultado['desviacion_pct'] = round(desviacion_pct, 1)

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
