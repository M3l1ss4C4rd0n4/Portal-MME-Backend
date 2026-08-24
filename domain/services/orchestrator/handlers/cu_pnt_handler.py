"""
Mixin: CU/PNT/SIM handlers (Costo Unitario, Pérdidas No Técnicas, Simulación).
Fase 7 del Portal Energético MME.
"""
import asyncio
from infrastructure.logging.logger import get_logger
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = get_logger(__name__)


class CuPntHandlerMixin:
    """Mixin para handlers de Costo Unitario, Pérdidas No Técnicas y Simulación."""

    # ─── COSTO UNITARIO (Fase 7) ─────────────────────────────

    @handle_service_error
    async def _handle_cu_actual(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de Costo Unitario."""
        data = {}
        errors = []

        try:
            from core.container import get_cu_service
            cu = await asyncio.to_thread(
                get_cu_service().get_cu_current
            )
            if not cu:
                data['respuesta'] = "No hay datos de CU disponibles en este momento."
                return data, errors

            cu_total = cu.get('cu_total', 0)
            g = cu.get('componente_g', 0) or 0
            d = cu.get('componente_d', 0) or 0
            c = cu.get('componente_c', 0) or 0
            t = cu.get('componente_t', 0) or 0
            p = cu.get('componente_p', 0) or 0

            total_comp = g + d + c + t + p
            pct_g = (g / total_comp * 100) if total_comp > 0 else 0

            resp = (
                f"El Costo Unitario actual es "
                f"**{cu_total:.2f} COP/kWh** "
                f"(fecha: {cu.get('fecha', 'N/D')}).\n\n"
                f"El componente de generación representa "
                f"el {pct_g:.1f}% del total.\n\n"
                f"**Desglose (COP/kWh):**\n"
                f"▸ Generación: {g:.2f}\n"
                f"▸ Distribución: {d:.2f}\n"
                f"▸ Comercialización: {c:.2f}\n"
                f"▸ Transmisión: {t:.2f}\n"
                f"▸ Pérdidas: {p:.2f}"
            )

            data['respuesta'] = resp
            data['cu'] = {
                'cu_total': round(cu_total, 2),
                'fecha': str(cu.get('fecha', '')),
                'componentes': {
                    'g': round(g, 2), 'd': round(d, 2),
                    'c': round(c, 2), 't': round(t, 2),
                    'p': round(p, 2),
                },
                'confianza': cu.get('confianza'),
            }
        except Exception as e:
            logger.error(f"Error en CU actual: {e}", exc_info=True)
            data['respuesta'] = "No hay datos de CU disponibles en este momento."
            errors.append(ErrorDetail(
                code="CU_ERROR", message="Error al consultar CU"
            ))

        return data, errors

    async def _handle_cu_evolucion(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: evolución histórica + pronóstico del Costo Unitario (CU).
        Envuelve CUService.get_cu_historico()/get_cu_forecast() (ambos ya
        existentes, usados hoy solo por el tablero, nunca por el orquestador) —
        ambos retornan un DataFrame diario crudo, así que este handler lo
        resume (promedio/min/max/tendencia) en vez de volcarlo entero al LLM,
        mismo principio que _build_prediction_ficha en predicciones_handler.py.

        parameters:
            dias_historico: días hacia atrás a resumir (default 30)
            dias_pronostico: días hacia adelante a proyectar (default 30, la
                herramienta interna lo acota a 1-90)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        dias_historico = int(parameters.get("dias_historico") or 30)
        dias_pronostico = int(parameters.get("dias_pronostico") or 30)

        from core.container import get_cu_service
        cu_service = get_cu_service()
        hoy = date.today()

        try:
            df_hist = await asyncio.to_thread(
                cu_service.get_cu_historico, hoy - timedelta(days=dias_historico), hoy
            )
            if df_hist is not None and not df_hist.empty:
                serie = df_hist["cu_total"].dropna()
                if not serie.empty:
                    mitad = max(1, len(serie) // 2)
                    promedio_primera_mitad = float(serie.iloc[:mitad].mean())
                    promedio_segunda_mitad = float(serie.iloc[mitad:].mean())
                    data["historico"] = {
                        "dias_analizados": dias_historico,
                        "promedio_cu": round(float(serie.mean()), 2),
                        "minimo_cu": round(float(serie.min()), 2),
                        "maximo_cu": round(float(serie.max()), 2),
                        "ultimo_valor_cu": round(float(serie.iloc[-1]), 2),
                        "ultima_fecha": str(df_hist["fecha"].iloc[-1]),
                        "tendencia": (
                            "creciente" if promedio_segunda_mitad > promedio_primera_mitad * 1.01
                            else "decreciente" if promedio_segunda_mitad < promedio_primera_mitad * 0.99
                            else "estable"
                        ),
                    }
        except Exception as e:
            logger.error(f"[CU_EVOLUCION] Error en histórico: {e}", exc_info=True)
            errors.append(ErrorDetail(code="CU_ERROR", message="Error al consultar histórico de CU"))

        try:
            df_fc = await asyncio.to_thread(cu_service.get_cu_forecast, dias_pronostico)
            if df_fc is not None and not df_fc.empty:
                serie_fc = df_fc["cu_predicho"].dropna()
                if not serie_fc.empty:
                    data["pronostico"] = {
                        "dias_proyectados": len(df_fc),
                        "promedio_cu_predicho": round(float(serie_fc.mean()), 2),
                        "minimo_cu_predicho": round(float(serie_fc.min()), 2),
                        "maximo_cu_predicho": round(float(serie_fc.max()), 2),
                        "confianza": (
                            round(float(df_fc["confianza"].dropna().mean()), 2)
                            if df_fc["confianza"].notna().any() else None
                        ),
                        "modelo": df_fc["modelo"].dropna().iloc[0] if df_fc["modelo"].notna().any() else None,
                    }
        except Exception as e:
            logger.error(f"[CU_EVOLUCION] Error en pronóstico: {e}", exc_info=True)
            errors.append(ErrorDetail(code="CU_ERROR", message="Error al consultar pronóstico de CU"))

        if not data:
            errors.append(ErrorDetail(code="NO_DATA", message="Sin datos de evolución de CU disponibles"))

        return data, errors

    # ─── PÉRDIDAS NO TÉCNICAS (Fase 7) ───────────────────────

    @handle_service_error
    async def _handle_perdidas_nt(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de Pérdidas No Técnicas."""
        data = {}
        errors = []

        try:
            from core.container import get_losses_nt_service
            stats = await asyncio.to_thread(
                get_losses_nt_service().get_losses_statistics
            )
            if not stats:
                data['respuesta'] = "No hay datos de P_NT disponibles."
                return data, errors

            pnt_30d = stats.get('pct_promedio_nt_30d', 0)
            pnt_12m = stats.get('pct_promedio_nt_12m', 0)
            tendencia = stats.get('tendencia_nt', 'N/D')
            costo_12m = stats.get('costo_nt_12m_mcop', 0)

            resp = (
                f"**Pérdidas No Técnicas (P_NT):**\n\n"
                f"▸ Promedio 30d: **{pnt_30d:.2f}%**\n"
                f"▸ Promedio 12m: {pnt_12m:.2f}%\n"
                f"▸ Tendencia: {tendencia}\n"
                f"▸ Costo estimado 12m: {costo_12m:,.0f} MCOP\n\n"
                f"_Nota: P_NT estimado por método residuo "
                f"Gene−DemaReal. Precisión validada: "
                f"0.000026% sobre 1,985 días._"
            )

            data['respuesta'] = resp
            data['pnt'] = {
                'pct_promedio_nt_30d': round(pnt_30d, 2),
                'pct_promedio_nt_12m': round(pnt_12m, 2),
                'tendencia': tendencia,
                'costo_nt_12m_mcop': round(costo_12m, 0),
                'total_dias': stats.get('total_dias', 0),
            }
        except Exception as e:
            logger.error(f"Error en P_NT: {e}", exc_info=True)
            data['respuesta'] = "No hay datos de P_NT disponibles."
            errors.append(ErrorDetail(
                code="PNT_ERROR", message="Error al consultar P_NT"
            ))

        return data, errors

    # ─── SIMULACIÓN CREG (Fase 7) ────────────────────────────

    @handle_service_error
    async def _handle_simulacion(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler para intent de simulación.
        Si el mensaje menciona sequía → sequia_moderada
        Si menciona renovables → expansion_renovables
        Si menciona pérdidas → reforma_perdidas_reduccion
        Si no es claro → listar escenarios disponibles
        """
        data = {}
        errors = []

        try:
            from core.container import container
            svc = container.simulation_service

            pregunta = parameters.get('pregunta', '').lower()

            # Detectar escenario por keywords
            escenario_id = None
            if any(w in pregunta for w in ['sequía', 'sequia', 'niño', 'nino', 'embalse']):
                escenario_id = 'sequia_moderada'
            elif any(w in pregunta for w in ['severa', 'crisis', '2022', '2023']):
                escenario_id = 'sequia_severa'
            elif any(w in pregunta for w in ['renovable', 'solar', 'eólica', 'eolica']):
                escenario_id = 'expansion_renovables'
            elif any(w in pregunta for w in ['pérdida', 'perdida', 'hurto', 'reforma']):
                escenario_id = 'reforma_perdidas_reduccion'

            if escenario_id:
                # Ejecutar escenario predefinido
                presets = svc.get_escenarios_predefinidos()
                preset = next((p for p in presets if p['id'] == escenario_id), None)
                if preset:
                    resultado = await asyncio.to_thread(
                        svc.simular_escenario,
                        preset['parametros'],
                        preset['nombre'],
                    )
                    cu_sim = resultado.get('cu_simulado', 0)
                    delta = resultado.get('delta_pct', 0)
                    factura = resultado.get('impacto_estrato3', {}).get('factura_sim_cop', 0)
                    dir_icon = '↑' if delta > 0 else '↓'

                    resp = (
                        f"**Simulación: {preset['nombre']}**\n\n"
                        f"▸ CU simulado: **{cu_sim:.2f} COP/kWh** "
                        f"({dir_icon} {delta:+.1f}%)\n"
                        f"▸ Factura estrato 3: ${factura:,.0f} COP/mes\n\n"
                        f"_{preset['descripcion']}_"
                    )
                    if resultado.get('advertencias'):
                        resp += "\n\n⚠️ " + " | ".join(resultado['advertencias'][:2])

                    data['respuesta'] = resp
                    data['simulacion'] = resultado
                    return data, errors

            # Si no se detectó → listar escenarios disponibles
            presets = svc.get_escenarios_predefinidos()
            lista = "\n".join(
                f"▸ **{p['nombre']}**: {p['descripcion']}"
                for p in presets
            )
            data['respuesta'] = (
                f"**Escenarios de simulación disponibles:**\n\n"
                f"{lista}\n\n"
                f"_Menciona un escenario específico para ejecutarlo. "
                f"Ej: \"simular sequía moderada\"_"
            )
            data['escenarios_disponibles'] = [
                {'id': p['id'], 'nombre': p['nombre']}
                for p in presets
            ]

        except Exception as e:
            logger.error(f"Error en simulación: {e}", exc_info=True)
            data['respuesta'] = "El simulador no está disponible en este momento."
            errors.append(ErrorDetail(
                code="SIMULATION_ERROR",
                message="Error al ejecutar simulación"
            ))

        return data, errors
