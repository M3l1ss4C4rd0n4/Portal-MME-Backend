"""
Mixin: Predicciones handlers (fichas de predicción, horizonte temporal, comparación vs histórico).
"""
import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = logging.getLogger(__name__)


class PrediccionesHandlerMixin:
    """
    Mixin para handlers de predicciones del sector energético.
    Depende de métodos definidos en EstadoActualHandlerMixin:
      - _get_historical_avg_30d
      - _get_embalses_avg_30d
    Estos se resuelven vía MRO en la clase final.
    """

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
        """
        ficha: Dict[str, Any] = {
            "indicador": indicador,
            "emoji": emoji,
            "unidad": unidad,
        }

        if df_pred.empty or len(df_pred) < min_puntos_requeridos:
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

        # ── FASE 7B: Verificar confianza real del modelo ──
        CONFIANZA_MINIMA_PRED = 0.60
        confianza_modelo = None
        if 'confianza' in df_pred.columns:
            vals_conf = [float(c) for c in df_pred['confianza'] if c is not None]
            if vals_conf:
                confianza_modelo = vals_conf[0]

        valores = [float(r['valor_gwh_predicho']) for _, r in df_pred.iterrows()]
        avg_pred = sum(valores) / len(valores)
        min_pred = min(valores)
        max_pred = max(valores)

        inf_values = [float(r['intervalo_inferior']) for _, r in df_pred.iterrows() if pd.notna(r.get('intervalo_inferior'))]
        sup_values = [float(r['intervalo_superior']) for _, r in df_pred.iterrows() if pd.notna(r.get('intervalo_superior'))]

        ficha["confiable"] = True
        ficha["total_dias_prediccion"] = len(valores)

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

        # ── Comparación vs histórico 30d ──
        if avg_hist_30d is not None and avg_hist_30d > 0:
            cambio_pct = ((avg_pred - avg_hist_30d) / avg_hist_30d) * 100
            ficha["resumen"]["promedio_30d_historico"] = round(avg_hist_30d, 2)
            ficha["resumen"]["cambio_pct"] = round(cambio_pct, 1)
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
            ficha["resumen"]["promedio_30d_historico"] = None
            ficha["resumen"]["cambio_pct"] = None
            if dias_hist < 7:
                ficha["resumen"]["nota_historico"] = f"Solo {dias_hist} días de histórico disponibles (insuficiente para comparación confiable)"
            else:
                ficha["resumen"]["nota_historico"] = "Histórico no disponible para esta métrica"
            ficha["tendencia"] = "➡️ Sin referencia histórica"

        ficha["valor_predicho"] = round(avg_pred, 2)

        if ficha["resumen"].get("cambio_pct") is not None:
            signo = "+" if ficha["resumen"]["cambio_pct"] > 0 else ""
            ficha["variacion_pct"] = f"{signo}{ficha['resumen']['cambio_pct']}% vs últ. 30d"

        return ficha

    @handle_service_error
    async def _handle_predicciones_sector(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler 2️⃣: Predicciones de los 3 indicadores clave.

        Acepta horizonte temporal:
        - 1_semana (7 días)
        - 1_mes (30 días)
        - 6_meses (180 días)
        - 1_ano (365 días)
        - personalizado (fecha específica en formato DD-MM-AAAA o YYYY-MM-DD)
        """
        from domain.services.confianza_politica import enriquecer_ficha_con_confianza

        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        predicciones: List[Dict[str, Any]] = []

        horizonte = parameters.get('horizonte', '1_semana')
        fecha_personalizada = parameters.get('fecha_personalizada')
        hoy = date.today()

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
                if '-' in fecha_personalizada and len(fecha_personalizada.split('-')[0]) == 4:
                    fecha_fin = datetime.strptime(fecha_personalizada, '%Y-%m-%d').date()
                else:
                    fecha_fin = datetime.strptime(fecha_personalizada, '%d-%m-%Y').date()
                dias_horizonte = (fecha_fin - hoy).days
                if dias_horizonte <= 0:
                    errors.append(ErrorDetail(code="INVALID_DATE", message="La fecha debe ser futura"))
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
            errors.append(ErrorDetail(code="SERVICE_UNAVAILABLE", message="El servicio de predicciones no está disponible"))
            return data, errors

        # ── Históricos 30d en paralelo ──
        hist_gen_avg, hist_gen_dias = await asyncio.to_thread(
            self._get_historical_avg_30d, 'Gene', 'Sistema'
        )
        hist_precio_avg, hist_precio_dias = await asyncio.to_thread(
            self._get_historical_avg_30d, 'PrecBolsNaci', 'Sistema'
        )
        hist_emb_avg, hist_emb_dias = await asyncio.to_thread(self._get_embalses_avg_30d)

        min_puntos = max(3, min(dias_horizonte // 2, 30))

        # ── PREDICCIÓN 1: GENERACIÓN TOTAL ──
        try:
            df_pred_gen = self.predictions_service.get_predictions(
                metric_id='GENE_TOTAL',
                start_date=hoy.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            if df_pred_gen.empty:
                fuentes = ['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa']
                gen_agg: Dict[str, Any] = {}
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
            enriquecer_ficha_con_confianza(ficha_gen, 'GENE_TOTAL')
            predicciones.append(ficha_gen)
        except Exception as e:
            logger.warning(f"Error predicciones generación: {e}")
            predicciones.append({"indicador": "Generación Total del Sistema", "emoji": "⚡", "confiable": False, "error": "Error consultando predicciones de generación"})

        # ── PREDICCIÓN 2: PRECIO DE BOLSA ──
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
            enriquecer_ficha_con_confianza(ficha_precio, 'PRECIO_BOLSA')
            predicciones.append(ficha_precio)
        except Exception as e:
            logger.warning(f"Error predicciones precio: {e}")
            predicciones.append({"indicador": "Precio de Bolsa Nacional", "emoji": "💰", "confiable": False, "error": "Error consultando predicciones de precio"})

        # ── PREDICCIÓN 3: EMBALSES ──
        try:
            df_pred_embalses = self.predictions_service.get_predictions(
                metric_id='EMBALSES_PCT',
                start_date=hoy.isoformat(),
                end_date=fecha_fin.isoformat()
            )
            if df_pred_embalses.empty:
                df_pred_embalses = self.predictions_service.get_predictions(
                    metric_id='EMBALSES',
                    start_date=hoy.isoformat(),
                    end_date=fecha_fin.isoformat()
                )
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
            enriquecer_ficha_con_confianza(ficha_emb, 'EMBALSES_PCT')
            predicciones.append(ficha_emb)
        except Exception as e:
            logger.warning(f"Error predicciones embalses: {e}")
            predicciones.append({"indicador": "Porcentaje de Embalses", "emoji": "💧", "confiable": False, "error": "Error consultando predicciones de embalses"})

        data['predicciones'] = predicciones
        data['fecha_consulta'] = datetime.utcnow().isoformat()
        data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}

        pred_con_error = [p for p in predicciones if p.get('error')]
        for p in pred_con_error:
            errors.append(ErrorDetail(
                code="PREDICTION_UNAVAILABLE",
                message=f"Predicción no disponible: {p['indicador']}"
            ))

        logger.info(
            f"[PREDICCIONES_SECTOR] Horizonte={horizonte} ({dias_horizonte} días) | "
            f"Disponibles: {len(predicciones) - len(pred_con_error)}/{len(predicciones)}"
        )
        return data, errors

    @handle_service_error
    async def _handle_predicciones(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler para intent de predicciones de generación por fuentes.

        Parámetros esperados:
        - fuente: Hidráulica, Térmica, Eólica, Solar, Biomasa (default: Hidráulica)
        - horizonte: días de predicción (default: 7)
        - fecha_inicio: fecha inicial (default: hoy)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        if not self.predictions_service:
            errors.append(ErrorDetail(code="SERVICE_UNAVAILABLE", message="El servicio de predicciones no está disponible"))
            return data, errors

        fuente = parameters.get('fuente', '')
        tipo = parameters.get('tipo', '')
        horizonte_dias = parameters.get('horizonte', 7)
        fecha_inicio_param = parameters.get('fecha_inicio')

        try:
            tipo_a_fuente = {
                'precios': 'PRECIO_BOLSA', 'precio': 'PRECIO_BOLSA', 'bolsa': 'PRECIO_BOLSA',
                'embalses': 'EMBALSES', 'embalse': 'EMBALSES',
                'generacion': 'GENE_TOTAL', 'generacion_total': 'GENE_TOTAL',
                'demanda': 'DEMANDA', 'aportes': 'APORTES_HIDRICOS', 'perdidas': 'PERDIDAS',
            }
            fuentes_validas = {
                'hidraulica': 'Hidráulica', 'termica': 'Térmica', 'eolica': 'Eólica',
                'solar': 'Solar', 'biomasa': 'Biomasa', 'gene_total': 'GENE_TOTAL',
                'precio_bolsa': 'PRECIO_BOLSA', 'embalses': 'EMBALSES',
                'embalses_pct': 'EMBALSES_PCT', 'demanda': 'DEMANDA',
                'aportes_hidricos': 'APORTES_HIDRICOS', 'perdidas': 'PERDIDAS',
            }
            _FUENTES_PERMITIDAS = {
                'Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa',
                'GENE_TOTAL', 'PRECIO_BOLSA', 'EMBALSES', 'EMBALSES_PCT',
                'DEMANDA', 'APORTES_HIDRICOS', 'PERDIDAS',
            }

            if tipo and tipo.lower() in tipo_a_fuente:
                fuente_normalizada = tipo_a_fuente[tipo.lower()]
            elif fuente and isinstance(fuente, str) and fuente.lower() in fuentes_validas:
                fuente_normalizada = fuentes_validas[fuente.lower()]
            elif fuente and isinstance(fuente, str) and fuente in _FUENTES_PERMITIDAS:
                fuente_normalizada = fuente
            else:
                fuente_normalizada = 'Hidráulica'

            if fecha_inicio_param:
                if isinstance(fecha_inicio_param, str):
                    fecha_inicio = datetime.strptime(fecha_inicio_param, '%Y-%m-%d').date()
                else:
                    fecha_inicio = fecha_inicio_param
            else:
                fecha_inicio = date.today()

            fecha_fin = fecha_inicio + timedelta(days=horizonte_dias)

            df_predicciones = self.predictions_service.get_predictions(
                metric_id=fuente_normalizada,
                start_date=fecha_inicio.isoformat(),
                end_date=fecha_fin.isoformat()
            )

            if df_predicciones.empty:
                data['fuente'] = fuente_normalizada
                data['horizonte_dias'] = horizonte_dias
                data['predicciones'] = []
                data['mensaje'] = f'No hay predicciones disponibles para {fuente_normalizada}'
                data['sugerencia'] = 'Ejecute el script train_predictions_postgres.py para generar predicciones'
            else:
                predicciones = []
                for _, row in df_predicciones.iterrows():
                    pred = {
                        'fecha': row['fecha_prediccion'].isoformat() if hasattr(row['fecha_prediccion'], 'isoformat') else str(row['fecha_prediccion']),
                        'valor_gwh': float(row['valor_gwh_predicho']),
                        'intervalo_inferior': float(row['intervalo_inferior']) if pd.notna(row.get('intervalo_inferior')) else None,
                        'intervalo_superior': float(row['intervalo_superior']) if pd.notna(row.get('intervalo_superior')) else None,
                    }
                    predicciones.append(pred)

                valores = [p['valor_gwh'] for p in predicciones]
                promedio = sum(valores) / len(valores) if valores else 0
                minimo = min(valores) if valores else 0
                maximo = max(valores) if valores else 0

                data['fuente'] = fuente_normalizada
                data['horizonte_dias'] = horizonte_dias
                data['total_predicciones'] = len(predicciones)
                data['predicciones'] = predicciones
                data['estadisticas'] = {
                    'promedio_gwh': round(promedio, 2),
                    'minimo_gwh': round(minimo, 2),
                    'maximo_gwh': round(maximo, 2),
                }
                data['modelo'] = 'ENSEMBLE_v1.0'
                data['mensaje'] = f'Predicciones de {fuente_normalizada} para los próximos {len(predicciones)} días'

                conclusiones = []
                cv_pred = (np.std(valores) / promedio * 100) if promedio > 0 else 0
                conclusiones.append(
                    f"📊 Las predicciones de {fuente_normalizada} para los próximos {len(predicciones)} días "
                    f"muestran un promedio de {round(promedio, 2)} GWh/día (rango: {round(minimo, 2)} - {round(maximo, 2)} GWh)"
                )
                if cv_pred < 3:
                    conclusiones.append(f"✅ Se espera alta estabilidad en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)")
                elif cv_pred > 10:
                    conclusiones.append(f"⚠️ Se anticipan fluctuaciones significativas en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)")
                else:
                    conclusiones.append(f"📈 Variabilidad normal esperada en la generación {fuente_normalizada.lower()} (CV={round(cv_pred, 1)}%)")

                if len(valores) >= 3:
                    tendencia_pred = valores[-1] - valores[0]
                    if abs(tendencia_pred) > promedio * 0.05:
                        dir_text = "creciente" if tendencia_pred > 0 else "decreciente"
                        conclusiones.append(
                            f"📉 Tendencia {dir_text} en el horizonte de predicción: "
                            f"de {round(valores[0], 2)} a {round(valores[-1], 2)} GWh/día"
                        )

                data['conclusiones'] = conclusiones

                recomendaciones = []
                recomendaciones.append(f"📋 Monitorear la generación {fuente_normalizada.lower()} real vs predicha para validar el modelo")
                if fuente_normalizada == 'Hidráulica' and promedio < 150:
                    recomendaciones.append(
                        "⚡ Generación hidráulica predicha por debajo del umbral histórico. "
                        "Verificar niveles de embalses y disponibilidad de respaldo térmico"
                    )
                elif fuente_normalizada == 'Hidráulica' and promedio > 200:
                    recomendaciones.append("💧 Generación hidráulica predicha en niveles altos, favorable para el sistema")
                if cv_pred > 10:
                    recomendaciones.append("🔧 La alta variabilidad anticipada sugiere preparar capacidad de respaldo flexible")
                data['recomendaciones'] = recomendaciones

                logger.info(f"✅ Predicciones obtenidas: {fuente_normalizada}, {len(predicciones)} días")

        except Exception as e:
            logger.error(f"Error en handle_predicciones: {e}", exc_info=True)
            errors.append(ErrorDetail(code="SERVICE_ERROR", message=f"Error al consultar predicciones: {str(e)}"))

        return data, errors
