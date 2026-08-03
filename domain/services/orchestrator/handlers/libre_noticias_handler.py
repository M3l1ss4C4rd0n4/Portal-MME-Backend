"""
Mixin: Pregunta libre, noticias del sector y menú principal.
"""
import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from domain.services.news_keywords import filter_tier1, filter_tier2_fill
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class LibreNoticiasHandlerMixin:
    """
    Mixin que agrupa:
    - _handle_pregunta_libre   (handler)
    - _handle_noticias_sector  (handler)
    - _handle_noticias_hidrocarburos (handler)
    - _generar_resumen_noticias
    - _handle_menu             (handler)
    """

    @handle_service_error
    async def _handle_pregunta_libre(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Pregunta libre del usuario.

        Recibe una pregunta en lenguaje natural y la responde
        usando los servicios disponibles del portal energético.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        pregunta = parameters.get('pregunta', '').strip()
        if not pregunta:
            errors.append(ErrorDetail(
                code="MISSING_QUESTION",
                message="Debes enviar una pregunta en el parámetro 'pregunta'"
            ))
            return data, errors

        pregunta_lower = pregunta.lower()

        try:
            datos_consultados: Dict[str, Any] = {}

            # ¿La pregunta menciona un departamento? -> cruce ontológico multi-dominio
            # (comunidades + contratos OR + FENOGE + Colombia Solar + subsidios + supervisión)
            try:
                from core.container import get_ontologia_service
                from domain.services.orchestrator.handlers.ontologia_handler import (
                    resolver_departamento_en_texto,
                )
                ontologia_service = get_ontologia_service()
                departamentos = await asyncio.to_thread(ontologia_service.listar_departamentos)
                depto_detectado = resolver_departamento_en_texto(pregunta, departamentos)
                if depto_detectado:
                    resumen_depto = await asyncio.to_thread(
                        ontologia_service.resumen_departamento,
                        depto_detectado["codigo_dane_departamento"],
                    )
                    if resumen_depto:
                        datos_consultados["resumen_departamento"] = resumen_depto
            except Exception as e:
                logger.warning(f"[PREGUNTA_LIBRE] Cruce ontológico no disponible: {e}")

            # ¿Pregunta sobre contratos/observaciones (texto libre, no estructurado)?
            # -> RAG: búsqueda semántica sobre objeto de contrato y observaciones
            # jurídicas/técnicas de supervision.contratos (pgvector + embeddings locales).
            if any(w in pregunta_lower for w in [
                'contrato', 'contratista', 'ejecutor', 'dificultad', 'retraso',
                'incumplimiento', 'observación', 'observacion', 'jurídic', 'juridic',
                'técnic', 'tecnic', 'expediente', 'liquidación', 'liquidacion',
                'prone', 'faer', 'fazni', 'pner',
            ]):
                try:
                    from core.container import get_ontologia_service
                    resultados_rag = await asyncio.to_thread(
                        get_ontologia_service().buscar_texto,
                        pregunta, top_k=5, umbral_similitud=0.4,
                    )
                    if resultados_rag:
                        datos_consultados['contratos_relevantes'] = [
                            {
                                'contenido': r['contenido'],
                                'campo': r['campo'],
                                'similitud': round(float(r['similitud']), 2),
                            }
                            for r in resultados_rag
                        ]
                except Exception as e:
                    logger.warning(f"[PREGUNTA_LIBRE] Búsqueda semántica no disponible: {e}")

            # ¿Pregunta sobre riesgo/probabilidad de atraso de contratos OR?
            # -> Fase 4: ranking por Isolation Forest / ranking determinístico
            # (domain/services/risk_service.py) sobre el cronograma de obra real.
            if any(w in pregunta_lower for w in [
                'riesgo', 'probabilidad de atraso', 'van a atrasar', 'se van a atrasar',
                'peligro de atraso', 'en riesgo',
            ]):
                try:
                    from core.container import get_risk_service
                    ranking = await asyncio.to_thread(
                        get_risk_service().riesgo_atraso_contratos_or
                    )
                    if ranking:
                        datos_consultados['riesgo_atraso_contratos_or'] = ranking[:5]
                except Exception as e:
                    logger.warning(f"[PREGUNTA_LIBRE] Riesgo de atraso no disponible: {e}")

            # ¿Pregunta sobre generación?
            if any(w in pregunta_lower for w in [
                'generación', 'generacion', 'generar', 'producción', 'produccion',
                'energía', 'energia', 'solar', 'eólica', 'eolica',
                'hidráulica', 'hidraulica', 'térmica', 'termica', 'biomasa',
            ]):
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
                        'periodo': f"{start_date} a {end_date}",
                    }

            # ¿Pregunta sobre precio?
            if any(w in pregunta_lower for w in ['precio', 'bolsa', 'costo', 'tarifa', 'cop', 'kwh']):
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=7)
                df_precio = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.metrics_service.get_metric_series,
                        'PPPrecBolsNaci', start_date.isoformat(), end_date.isoformat()
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if not df_precio.empty and 'Value' in df_precio.columns:
                    datos_consultados['precio_bolsa'] = {
                        'promedio_cop_kwh': round(float(df_precio['Value'].mean()), 2),
                        'maximo_cop_kwh': round(float(df_precio['Value'].max()), 2),
                        'minimo_cop_kwh': round(float(df_precio['Value'].min()), 2),
                        'periodo': f"{start_date} a {end_date}",
                    }

            # ¿Pregunta sobre embalses/hidrología?
            if any(w in pregunta_lower for w in [
                'embalse', 'embalses', 'agua', 'hidrología', 'hidrologia', 'reserva', 'nivel',
            ]):
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
                        'fecha': fecha_dato_emb or ayer,
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
                        'periodo': f"{start_date} a {end_date}",
                    }

            # ¿Pregunta sobre costo unitario?
            if any(w in pregunta_lower for w in [
                'costo unitario', 'cu ', 'cop/kwh', 'tarifa regulada', 'componente_g',
            ]):
                try:
                    from core.container import get_cu_service
                    cu = await asyncio.to_thread(get_cu_service().get_cu_current)
                    if cu:
                        datos_consultados['costo_unitario'] = {
                            'cu_total_cop_kwh': round(cu.get('cu_total', 0), 2),
                            'fecha': str(cu.get('fecha', '')),
                            'componente_g': round(cu.get('componente_g', 0), 2),
                            'confianza': cu.get('confianza'),
                        }
                except Exception as e:
                    pass

            # ¿Pregunta sobre pérdidas no técnicas?
            if any(w in pregunta_lower for w in [
                'pérdida', 'perdida', 'hurto', 'no técnica', 'no tecnica', 'p_nt', 'pnt',
            ]):
                try:
                    from core.container import get_losses_nt_service
                    stats = await asyncio.to_thread(get_losses_nt_service().get_losses_statistics)
                    if stats:
                        datos_consultados['perdidas_nt'] = {
                            'pct_promedio_nt_30d': round(stats.get('pct_promedio_nt_30d', 0), 2),
                            'tendencia': stats.get('tendencia_nt', 'N/D'),
                            'costo_nt_12m_mcop': round(stats.get('costo_nt_12m_mcop', 0), 0),
                        }
                except Exception as e:
                    pass

            # ¿Pregunta sobre predicciones?
            if any(w in pregunta_lower for w in [
                'predicción', 'prediccion', 'pronóstico', 'pronostico',
                'futuro', 'va a', 'será', 'espera',
            ]):
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
                                'rango': f"{round(float(min(vals)), 2)} - {round(float(max(vals)), 2)}",
                            }

            # Fallback: si no se detectó ningún tema, consultar 2 KPIs generales
            if not datos_consultados:
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
                "relacionados con tu pregunta."
            )
            data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}

            logger.info(
                f"[PREGUNTA_LIBRE] Pregunta='{pregunta[:50]}...' | "
                f"Datos encontrados: {list(datos_consultados.keys())}"
            )

            # Análisis con IA opcional
            if parameters.get('con_analisis_ia') and datos_consultados:
                try:
                    from domain.services.ai_service import AgentIA
                    from domain.services.confianza_politica import get_confianza_politica
                    import json as _json2
                    agent = AgentIA()
                    if agent.client:
                        contexto_ia = {"pregunta": pregunta, "datos": datos_consultados}
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
                            "Eres un asesor energético del Ministerio de Minas de Colombia. "
                            "Responde la pregunta del usuario usando SOLO los datos suministrados "
                            "en el JSON — no menciones campos, claves ni temas que no estén ahí.\n"
                            "Máximo 200 palabras, usa bullets, en español.\n"
                            "Excepción única: si la clave 'precio_bolsa' SÍ está presente en los "
                            "datos y su nivel de confianza es EXPERIMENTAL, indícalo una vez al "
                            "final. Si 'precio_bolsa' no está presente, no la nombres en absoluto.\n"
                            "NO inventes datos. Redondea números a 2 decimales."
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

                        resp_ia = await asyncio.wait_for(asyncio.to_thread(_call_ia), timeout=20)
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

    @handle_service_error
    async def _handle_noticias_sector(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Noticias relevantes del sector energético colombiano.
        Usa NewsService multi-fuente: top 3 + lista extendida + resumen IA.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

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

            data["noticias"] = [
                {
                    "titulo": n["titulo"],
                    "resumen": n["resumen_corto"],
                    "url": n["url"],
                    "fuente": n["fuente"],
                    "source_url": n.get("source_url") or "",
                    "fecha": n["fecha_publicacion"],
                    "imagen": n.get("imagen") or n.get("image") or "",
                }
                for n in top
            ]
            data["total"] = len(top)
            data["opcion_regresar"] = {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal"
            }

            if otras:
                data["otras_noticias"] = [
                    {
                        "titulo": n["titulo"],
                        "resumen": n["resumen_corto"],
                        "url": n["url"],
                        "fuente": n["fuente"],
                        "fecha": n["fecha_publicacion"],
                        "imagen": n.get("imagen") or n.get("image") or "",
                    }
                    for n in otras
                ]

            if not top:
                data["nota"] = (
                    "No se encontraron noticias relevantes sobre "
                    "el sector energético para hoy."
                )

            data["resumen_general"] = None
            all_for_summary = top + otras
            if len(all_for_summary) >= 3:
                try:
                    resumen = await self._generar_resumen_noticias(all_for_summary)
                    data["resumen_general"] = resumen
                except Exception as e:
                    logger.warning(f"[NOTICIAS] Resumen IA falló (no crítico): {e}")

            logger.info(
                f"[NOTICIAS] {len(top)} principales + {len(otras)} extras, "
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

    @handle_service_error
    async def _handle_noticias_hidrocarburos(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: Noticias de hidrocarburos (petróleo, gas, carbón, minería).
        Obtiene un pool más grande del servicio de noticias y filtra
        estrictamente por términos de hidrocarburos.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        if not self.news_service:
            errors.append(ErrorDetail(
                code="NEWS_UNAVAILABLE",
                message="Servicio de noticias no disponible"
            ))
            return data, errors

        try:
            # 1. Intentar servicio dedicado de hidrocarburos
            hydro_result = await asyncio.wait_for(
                self.news_service.get_hydrocarbon_news(max_items=10),
                timeout=self.SERVICE_TIMEOUT
            )

            hydro_items = hydro_result.get("noticias", [])

            logger.info(
                f"[HIDROCARBUROS] {len(hydro_items)} noticias del servicio dedicado"
            )

            selected = list(hydro_items)

            # 2. Si quedan espacios, complementar con pool general filtrado.
            # Prioridad: tier 1 (petróleo/gas genuino) primero; tier 2
            # (minería) solo rellena si tier 1 no alcanza las 3 noticias.
            if len(selected) < 3:
                try:
                    enriched = await asyncio.wait_for(
                        self.news_service.get_enriched_news(max_top=5, max_extra=5),
                        timeout=self.SERVICE_TIMEOUT
                    )
                    top = enriched.get("top", [])
                    otras = enriched.get("otras", [])
                    general_pool = top + otras

                    # Normalizar el campo de resumen ("resumen_corto" en el
                    # pool general) para que los filtros compartidos lo lean.
                    normalized_pool = [
                        {
                            "titulo": n.get("titulo"),
                            "resumen": n.get("resumen_corto") or n.get("resumen"),
                            "url": n.get("url"),
                            "_orig": n,
                        }
                        for n in general_pool
                    ]

                    def _append_matches(matches: list) -> None:
                        for m in matches:
                            if len(selected) >= 3:
                                break
                            if not any(s.get("url") == m["url"] for s in selected):
                                selected.append(m["_orig"])

                    tier1_matches = filter_tier1(normalized_pool)
                    _append_matches(tier1_matches)

                    if len(selected) < 3:
                        tier2_matches = filter_tier2_fill(normalized_pool, already_included=tier1_matches)
                        _append_matches(tier2_matches)

                    logger.info(
                        f"[HIDROCARBUROS] {len(selected)} tras fallback pool general "
                        f"(se agregaron {len(selected) - len(hydro_items)} del pool)"
                    )
                except Exception as e:
                    logger.warning(f"[HIDROCARBUROS] Fallback falló: {e}")

            # 3. Formatear respuesta (máximo 3)
            top3 = selected[:3]
            data["noticias"] = [
                {
                    "titulo": n["titulo"],
                    "resumen": n.get("resumen") or n.get("resumen_corto") or "",
                    "url": n["url"],
                    "fuente": n.get("fuente", ""),
                    "source_url": n.get("source_url") or "",
                    "fecha": n.get("fecha_publicacion") or n.get("fecha") or "",
                    "imagen": n.get("imagen") or n.get("image") or "",
                }
                for n in top3
            ]
            data["total"] = len(top3)

            logger.info(
                f"[HIDROCARBUROS] {len(top3)} noticias devueltas"
            )

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="NEWS_TIMEOUT",
                message="El servicio de noticias tardó demasiado"
            ))
        except Exception as e:
            logger.error(f"Error en noticias hidrocarburos: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="NEWS_ERROR",
                message="Error al obtener noticias de hidrocarburos"
            ))

        return data, errors

    async def _generar_resumen_noticias(
        self,
        noticias: List[Dict],
    ) -> Optional[str]:
        """
        Genera un resumen ejecutivo de 3-4 frases con los titulares del día.
        Retorna None si la IA no está disponible o falla.
        """
        try:
            from domain.services.ai_service import AgentIA
            agent = AgentIA()
            if not agent.client:
                return None

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
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=300,
                )

            response = await asyncio.wait_for(asyncio.to_thread(_call_ai), timeout=15)
            texto = response.choices[0].message.content.strip()
            if len(texto) < 30:
                logger.warning(f"[NOTICIAS_RESUMEN] Respuesta demasiado corta ({len(texto)} chars)")
                return None

            logger.info(
                f"[NOTICIAS_RESUMEN] Resumen generado con "
                f"{agent.provider}/llama-3.1-8b-instant ({len(texto)} chars)"
            )
            return texto

        except asyncio.TimeoutError:
            logger.warning("[NOTICIAS_RESUMEN] Timeout IA")
            return None
        except Exception as e:
            logger.warning(f"[NOTICIAS_RESUMEN] Error IA: {e}")
            return None

    @handle_service_error
    async def _handle_gestion_sector(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Submenú: métricas XM del sector (estado, predicciones, anomalías)."""
        data = {
            "titulo": "Gestión del sector energético",
            "instruccion": (
                "Indicadores del sistema eléctrico (datos XM): generación, "
                "precio de bolsa y embalses."
            ),
            "opciones": [
                {"id": "estado_actual", "titulo": "Estado actual", "emoji": "📊"},
                {"id": "predicciones_sector", "titulo": "Predicciones XM", "emoji": "🔮"},
                {"id": "anomalias_sector", "titulo": "Anomalías detectadas", "emoji": "🚨"},
            ],
            "opcion_regresar": {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal",
            },
        }
        return data, []

    @handle_service_error
    async def _handle_mas_opciones(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Submenú: noticias e informe complementario."""
        data = {
            "titulo": "Más opciones",
            "instruccion": "Selecciona una opción:",
            "opciones": [
                {"id": "noticias_sector", "titulo": "Noticias del sector", "emoji": "📰"},
                {"id": "mas_informacion", "titulo": "Pregunta libre", "emoji": "❓"},
            ],
            "opcion_regresar": {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal",
            },
        }
        return data, []

    @handle_service_error
    async def _handle_menu(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler: Menú principal del chatbot (7 capítulos del portal)."""
        data = {
            "portal_nombre": "Portal de Dirección de Despacho del Viceministro de Minas y Energía",
            "portal_nombre_corto": "Portal de Dirección MME",
            "mensaje_bienvenida": (
                "¡Hola! 👋 Soy el asistente del *Portal de Dirección de Despacho "
                "del Viceministro de Minas y Energía*.\n\n"
                "Consulto los mismos tableros del portal, organizados en capítulos:\n\n"
                "📊 *Cap. 1 — Gestión del sector (XM):* estado, predicciones y anomalías\n"
                "🏘️ *Cap. 2 — Comunidades:* implementadas, Contratos OR, Fenoge y Colombia Solar\n"
                "📋 *Cap. 3 — Subsidios:* déficit histórico, pagos y validaciones\n"
                "🔍 *Cap. 4 — Supervisión* de contratos MinMinas\n"
                "💼 *Cap. 5 — Ejecución presupuestal* DEE\n"
                "📄 *Cap. 6 — Informe ejecutivo* PDF integrado\n\n"
                "También puedes escribirme en cualquier momento."
            ),
            "indicadores_clave": [
                "⚡ Generación Total del Sistema (GWh)",
                "💰 Precio de Bolsa Nacional (COP/kWh)",
                "💧 Porcentaje de Embalses (%)",
            ],
            "menu_principal": [
                {
                    "numero": 1,
                    "id": "gestion_sector",
                    "titulo": "Gestión del sector",
                    "emoji": "📊",
                    "descripcion": (
                        "Métricas XM: estado actual, predicciones y anomalías "
                        "de generación, precio de bolsa y embalses."
                    ),
                    "sub_menu": {
                        "instruccion": "Indicadores del sector energético (datos XM):",
                        "opciones": [
                            {
                                "numero": 1,
                                "id": "estado_actual",
                                "titulo": "Estado actual",
                                "emoji": "📊",
                            },
                            {
                                "numero": 2,
                                "id": "predicciones_sector",
                                "titulo": "Predicciones XM",
                                "emoji": "🔮",
                            },
                            {
                                "numero": 3,
                                "id": "anomalias_sector",
                                "titulo": "Anomalías detectadas",
                                "emoji": "🚨",
                            },
                        ],
                    },
                },
                {
                    "numero": 2,
                    "id": "comunidades_menu",
                    "titulo": "Comunidades energéticas",
                    "emoji": "🏘️",
                    "descripcion": (
                        "Cap. 2: implementadas, Contratos OR, Fenoge 1.0/1.1 "
                        "y Colombia Solar (curva S)."
                    ),
                },
                {
                    "numero": 3,
                    "id": "subsidios_menu",
                    "titulo": "Subsidios",
                    "emoji": "📋",
                    "descripcion": (
                        "Cap. 3: déficit histórico, detalle de pagos FSSRI/FOES "
                        "y validaciones de cuentas."
                    ),
                },
                {
                    "numero": 4,
                    "id": "supervision_menu",
                    "titulo": "Supervisión",
                    "emoji": "🔍",
                    "descripcion": "Cap. 4: KPIs contratos MinMinas — avance físico/financiero y usuarios.",
                },
                {
                    "numero": 5,
                    "id": "presupuesto_menu",
                    "titulo": "Ejecución presupuestal",
                    "emoji": "💼",
                    "descripcion": "Cap. 5: totales DEE y detalle por proyecto.",
                },
                {
                    "numero": 6,
                    "id": "informe_ejecutivo",
                    "titulo": "Informe ejecutivo",
                    "emoji": "📋",
                    "descripcion": (
                        "Cap. 6: informe PDF con todos los capítulos del portal "
                        "más noticias del sector."
                    ),
                },
                {
                    "numero": 7,
                    "id": "mas_opciones",
                    "titulo": "Más opciones",
                    "emoji": "➕",
                    "descripcion": "Noticias del sector y pregunta libre.",
                    "sub_menu": {
                        "instruccion": "Selecciona una opción:",
                        "opciones": [
                            {
                                "numero": 1,
                                "id": "noticias_sector",
                                "titulo": "Noticias del sector",
                                "emoji": "📰",
                            },
                            {
                                "numero": 2,
                                "id": "mas_informacion",
                                "titulo": "Pregunta libre",
                                "emoji": "❓",
                            },
                        ],
                    },
                },
            ],
            "nota_libre": (
                "💡 En cualquier momento puedes escribir tu pregunta directamente "
                "sin necesidad de usar el menú. La IA analizará tu consulta y "
                "te responderá con datos actualizados del sector energético."
            ),
            "opcion_regresar": {
                "id": "menu",
                "titulo": "🔙 Regresar al menú principal",
            },
        }
        return data, []
