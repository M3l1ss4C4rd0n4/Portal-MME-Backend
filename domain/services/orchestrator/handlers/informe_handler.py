"""
Mixin: Informe ejecutivo IA — recopila contexto de todos los demás handlers,
llama a Groq/OpenRouter, cachea en Redis y genera un fallback sin IA.
"""
import asyncio
import logging
import re as _re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.confianza_politica import get_confianza_politica, obtener_disclaimer
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = logging.getLogger(__name__)


class InformeHandlerMixin:
    """
    Mixin que agrupa:
    - _handle_informe_ejecutivo  (handler principal)
    - _postprocess_informe_ia
    - _generar_informe_con_ia
    - _generar_informe_fallback
    """

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
        ejecutivo de 5 secciones dirigido al Viceministro.

        Fallback: si la IA no responde, se genera un informe degradado
        con tablas de datos numéricos.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        try:
            # ── 1. Recopilar datos de los 3 módulos existentes en paralelo ──
            logger.info("[INFORME_EJECUTIVO_IA] Recopilando datos de contexto…")

            estado_task = self._handle_estado_actual(parameters)
            pred_1s_task = self._handle_predicciones_sector({'horizonte': '1_semana'})
            pred_1m_task = self._handle_predicciones_sector({'horizonte': '1_mes'})
            pred_6m_task = self._handle_predicciones_sector({'horizonte': '6_meses'})
            pred_1a_task = self._handle_predicciones_sector({'horizonte': '1_ano'})
            anomalias_task = self._handle_anomalias_detectadas(parameters)

            results = await asyncio.gather(
                estado_task, pred_1s_task, pred_1m_task, pred_6m_task,
                pred_1a_task, anomalias_task,
                return_exceptions=True
            )

            def _safe_unpack(result):
                if isinstance(result, Exception):
                    logger.warning(f"[INFORME_EJECUTIVO_IA] Excepción recopilando datos: {result}")
                    return {}, []
                if isinstance(result, tuple) and len(result) == 2:
                    return result[0] or {}, result[1] or []
                return {}, []

            data_estado, _ = _safe_unpack(results[0])
            data_pred_1s, _ = _safe_unpack(results[1])
            data_pred_1m, _ = _safe_unpack(results[2])
            data_pred_6m, _ = _safe_unpack(results[3])
            data_pred_1a, _ = _safe_unpack(results[4])
            data_anomalias, _ = _safe_unpack(results[5])

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

                    titulares = []
                    for n in top_noticias + otras_noticias:
                        t = n.get("titulo", "")
                        f = n.get("fuente", "")
                        if t:
                            titulares.append(f"{t} ({f})" if f else t)

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
                            "noticias": top_noticias[:3],
                        }
                        logger.info(
                            f"[INFORME_EJECUTIVO_IA] Noticias inyectadas: "
                            f"{len(titulares)} titulares, "
                            f"resumen={'sí' if resumen_prensa else 'no'}"
                        )
            except Exception as e:
                logger.warning(f"[INFORME_EJECUTIVO_IA] Noticias no disponibles (no crítico): {e}")

            # ── 2. Construir contexto estructurado para la IA ──
            hoy = date.today().strftime('%Y-%m-%d')

            contexto = {
                "fecha_consulta": hoy,
                "estado_actual": {
                    "fichas": data_estado.get('fichas', []),
                },
                "predicciones": {
                    "1_semana": {
                        "horizonte_titulo": data_pred_1s.get('horizonte_titulo', 'Próxima semana'),
                        "fecha_inicio": data_pred_1s.get('fecha_inicio'),
                        "fecha_fin": data_pred_1s.get('fecha_fin'),
                        "indicadores": data_pred_1s.get('predicciones', []),
                    },
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
                    "1_ano": {
                        "horizonte_titulo": data_pred_1a.get('horizonte_titulo', 'Próximo año'),
                        "fecha_inicio": data_pred_1a.get('fecha_inicio'),
                        "fecha_fin": data_pred_1a.get('fecha_fin'),
                        "indicadores": data_pred_1a.get('predicciones', []),
                    },
                },
                "anomalias": {
                    "total_evaluadas": data_anomalias.get('total_evaluadas', 0),
                    "total_anomalias": data_anomalias.get('total_anomalias', 0),
                    "lista": self._deduplicar_anomalias(
                        data_anomalias.get('anomalias', [])
                    ),
                    "detalle_completo": self._deduplicar_anomalias(
                        data_anomalias.get('detalle_completo', [])
                    ),
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

            # ── 2b. Construir nodo "predicciones_mes" ──
            pred_1m_indicadores = data_pred_1m.get('predicciones', [])
            predicciones_mes: Dict[str, Any] = {}
            _PRED_MES_MAP = {
                "Generación Total del Sistema": "generacion",
                "Precio de Bolsa Nacional": "precio_bolsa",
                "Porcentaje de Embalses": "embalses",
            }
            _PRED_MES_ORDEN = ["generacion", "precio_bolsa", "embalses"]

            for ind in pred_1m_indicadores:
                nombre = ind.get("indicador", "")
                clave = _PRED_MES_MAP.get(nombre)
                if clave:
                    resumen = ind.get("resumen", {})
                    predicciones_mes[clave] = {
                        "indicador": nombre,
                        "emoji": ind.get("emoji", ""),
                        "unidad": ind.get("unidad", ""),
                        "confiable": ind.get("confiable", False),
                        "promedio_periodo": resumen.get("promedio_periodo"),
                        "rango_min": resumen.get("minimo_periodo"),
                        "rango_max": resumen.get("maximo_periodo"),
                        "promedio_30d_historico": resumen.get("promedio_30d_historico"),
                        "cambio_pct_vs_historico": resumen.get("cambio_pct"),
                        "tendencia": ind.get("tendencia", ""),
                        "rango_confianza": resumen.get("rango_confianza"),
                        "confianza_modelo": ind.get("confianza_modelo"),
                        "advertencia_confianza": ind.get("advertencia_confianza"),
                    }

            predicciones_mes_ordenadas = {
                clave: predicciones_mes[clave]
                for clave in _PRED_MES_ORDEN
                if clave in predicciones_mes
            }

            contexto["predicciones_mes"] = {
                "horizonte": data_pred_1m.get('horizonte_titulo', 'Próximo mes'),
                "fecha_inicio": data_pred_1m.get('fecha_inicio'),
                "fecha_fin": data_pred_1m.get('fecha_fin'),
                "metricas_clave": predicciones_mes_ordenadas,
                "nota": (
                    "Estas son las predicciones a 1 mes de las 3 métricas "
                    "prioritarias. Usar ANTES del análisis cualitativo en la "
                    "sección 2 del informe."
                ),
            }

            if noticias_ctx:
                contexto["prensa_del_dia"] = noticias_ctx

            logger.info(
                f"[INFORME_EJECUTIVO_IA] Contexto base armado: "
                f"fichas={len(contexto['estado_actual']['fichas'])}, "
                f"pred_1s={len(contexto['predicciones']['1_semana']['indicadores'])}, "
                f"pred_1m={len(contexto['predicciones']['1_mes']['indicadores'])}, "
                f"pred_6m={len(contexto['predicciones']['6_meses']['indicadores'])}, "
                f"pred_1a={len(contexto['predicciones']['1_ano']['indicadores'])}, "
                f"anomalías={contexto['anomalias']['total_anomalias']}"
            )

            # ── 2c. Enriquecer contexto con campos adicionales ──
            _fichas = contexto['estado_actual']['fichas']
            _anomalias_lista = contexto['anomalias'].get('lista', [])

            try:
                contexto['generacion_por_fuente'] = await self._build_generacion_por_fuente()
            except Exception as e:
                logger.warning(f"[INFORME] generacion_por_fuente falló (no crítico): {e}")
                contexto['generacion_por_fuente'] = {"error": str(e)}

            try:
                contexto['embalses_detalle'] = self._build_embalses_detalle(_fichas)
            except Exception as e:
                logger.warning(f"[INFORME] embalses_detalle falló (no crítico): {e}")
                contexto['embalses_detalle'] = {"error": str(e)}

            try:
                contexto['variables_mercado'] = self._build_variables_mercado()
            except Exception as e:
                logger.warning(f"[INFORME] variables_mercado falló (no crítico): {e}")
                contexto['variables_mercado'] = {}

            try:
                contexto['embalses_regionales'] = self._build_embalses_regionales()
            except Exception as e:
                logger.warning(f"[INFORME] embalses_regionales falló (no crítico): {e}")
                contexto['embalses_regionales'] = {}

            try:
                contexto['predicciones_mes_resumen'] = self._build_predicciones_mes_resumen(
                    _fichas,
                    contexto.get('predicciones_mes', {}),
                )
            except Exception as e:
                logger.warning(f"[INFORME] predicciones_mes_resumen falló (no crítico): {e}")
                contexto['predicciones_mes_resumen'] = {"error": str(e)}

            try:
                contexto['tabla_indicadores_clave'] = self._build_tabla_indicadores_clave(
                    _fichas,
                    _anomalias_lista,
                )
            except Exception as e:
                logger.warning(f"[INFORME] tabla_indicadores_clave falló (no crítico): {e}")
                contexto['tabla_indicadores_clave'] = []

            # (e) Anomalías recientes de BD
            try:
                from infrastructure.database.manager import db_manager
                _df_alertas = db_manager.query_df("""
                    SELECT metrica, severidad, descripcion
                    FROM alertas_historial
                    WHERE fecha_evaluacion >= CURRENT_DATE - INTERVAL '1 day'
                      AND severidad NOT IN ('NORMAL', 'INFO')
                    ORDER BY CASE severidad
                        WHEN 'CRITICA' THEN 1 WHEN 'CRITICO' THEN 1
                        WHEN 'ALERTA' THEN 2 ELSE 3
                    END
                    LIMIT 10
                """)
                if not _df_alertas.empty:
                    _seen_keys = set()
                    _alertas_bd = []
                    for _rec in _df_alertas.to_dict('records'):
                        _key = (
                            str(_rec.get('metrica', '')).strip().upper(),
                            str(_rec.get('descripcion', '')).strip()[:80],
                        )
                        if _key not in _seen_keys:
                            _seen_keys.add(_key)
                            _alertas_bd.append({
                                'indicador': str(_rec.get('metrica', '')).strip(),
                                'severidad': str(_rec.get('severidad', 'alerta')).lower(),
                                'descripcion': str(_rec.get('descripcion', '')).strip(),
                            })
                    _existing_keys = {
                        (a.get('indicador', '').upper(), a.get('descripcion', '')[:80])
                        for a in contexto['anomalias'].get('lista', [])
                    }
                    _nuevas = [a for a in _alertas_bd
                               if (a['indicador'].upper(), a['descripcion'][:80])
                               not in _existing_keys]
                    if _nuevas:
                        contexto['anomalias']['lista'].extend(_nuevas)
                        logger.info(
                            f"[INFORME] +{len(_nuevas)} anomalías de BD inyectadas al contexto IA"
                        )
            except Exception as e:
                logger.warning(f"[INFORME] alertas_historial falló (no crítico): {e}")

            contexto['anomalias']['total_anomalias'] = len(
                contexto['anomalias'].get('lista', [])
            )

            # (f) Costo Unitario y Pérdidas No Técnicas
            try:
                from core.container import container as _ctnr
                _cu = await asyncio.to_thread(_ctnr.get_cu_service().get_cu_current)
                _pnt = await asyncio.to_thread(_ctnr.losses_nt_service.get_losses_statistics)
                if _cu or _pnt:
                    contexto['cu_pnt'] = {}
                    if _cu:
                        contexto['cu_pnt']['costo_unitario'] = {
                            'cu_total_cop_kwh': round(_cu.get('cu_total', 0), 2),
                            'fecha': str(_cu.get('fecha', '')),
                            'componente_g_pct': round(
                                (_cu.get('componente_g', 0) /
                                 max(_cu.get('cu_total', 1), 1)) * 100, 1
                            ),
                            'confianza': _cu.get('confianza'),
                        }
                    if _pnt:
                        contexto['cu_pnt']['perdidas_nt'] = {
                            'pct_promedio_nt_30d': round(_pnt.get('pct_promedio_nt_30d', 0), 2),
                            'tendencia': _pnt.get('tendencia_nt', 'N/D'),
                            'costo_nt_12m_mcop': round(_pnt.get('costo_nt_12m_mcop', 0), 0),
                        }
                    logger.info(
                        f"[INFORME] CU/PNT inyectado: "
                        f"cu={'sí' if _cu else 'no'}, pnt={'sí' if _pnt else 'no'}"
                    )
            except Exception as e:
                logger.warning(f"[INFORME] cu_pnt falló (no crítico): {e}")

            logger.info(
                f"[INFORME_EJECUTIVO_IA] Contexto enriquecido: "
                f"gen_fuentes={'ok' if 'fuentes' in contexto.get('generacion_por_fuente', {}) else 'no'}, "
                f"embalses_det={'ok' if 'valor_actual_pct' in contexto.get('embalses_detalle', {}) else 'no'}, "
                f"pred_resumen={len(contexto.get('predicciones_mes_resumen', {}).get('metricas', []))}, "
                f"tabla_kpi={len(contexto.get('tabla_indicadores_clave', []))}, "
                f"anomalías_dedup={contexto['anomalias']['total_anomalias']}"
            )

            # ── 3. Verificar cache diario antes de llamar a la IA ──
            hoy_cache = datetime.utcnow().strftime('%Y-%m-%d')
            cache_key = f"informe_ia:{hoy_cache}"
            informe_texto = None

            if self._redis:
                try:
                    import json as _json
                    cached_raw = self._redis.get(cache_key)
                    if cached_raw:
                        cached = _json.loads(cached_raw) if isinstance(cached_raw, str) else _json.loads(cached_raw.decode())
                        if cached and cached.get('texto'):
                            logger.info(
                                f"[INFORME_IA] Usando cache Redis del día ({len(cached['texto'])} chars, "
                                f"generado a las {cached.get('hora', '?')})"
                            )
                            informe_texto = cached['texto']
                except Exception as e:
                    logger.warning(f"[INFORME_IA] Error leyendo cache Redis: {e}")

            if not informe_texto:
                cached = self._informe_ia_cache.get(hoy_cache)
                if cached and cached.get('texto'):
                    logger.info(
                        f"[INFORME_IA] Usando cache local del día ({len(cached['texto'])} chars, "
                        f"generado a las {cached.get('hora', '?')})"
                    )
                    informe_texto = cached['texto']

            if not informe_texto:
                informe_texto = await self._generar_informe_con_ia(contexto)
                if informe_texto:
                    informe_texto = self._postprocess_informe_ia(informe_texto)
                if informe_texto:
                    cache_value = {
                        'texto': informe_texto,
                        'hora': datetime.utcnow().strftime('%H:%M'),
                    }
                    self._informe_ia_cache = {hoy_cache: cache_value}
                    if self._redis:
                        try:
                            import json as _json
                            self._redis.setex(cache_key, 86400, _json.dumps(cache_value))
                            logger.info(f"[INFORME_IA] Cache guardado en Redis con TTL 24h")
                        except Exception as e:
                            logger.warning(f"[INFORME_IA] Error guardando cache Redis: {e}")

            if informe_texto:
                data['informe'] = informe_texto
                data['generado_con_ia'] = True
            else:
                logger.warning("[INFORME_EJECUTIVO_IA] IA no disponible, generando fallback")
                contexto['_generado_con_ia'] = False
                data['informe'] = self._generar_informe_fallback(contexto)
                data['generado_con_ia'] = False
                data['nota_fallback'] = (
                    "Informe generado sin análisis textual de IA por "
                    "indisponibilidad temporal del servicio; se muestran "
                    "datos numéricos consolidados."
                )

            data['fecha_generacion'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            data['contexto_datos'] = contexto

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

    # ── Helper: Post-procesar narrativa IA ──

    def _postprocess_informe_ia(self, texto: str) -> Optional[str]:
        """
        Limpia y valida el texto generado por la IA antes de usarlo.
        """
        if not texto or len(texto.strip()) < 100:
            logger.warning("[INFORME_IA_POST] Texto demasiado corto, rechazado")
            return None

        original_len = len(texto)

        _JSON_FIELD_PATTERNS = [
            r'`[a-z_]{5,60}`',
            r'\b(el|del|al|según el|según la|en el)\s+campo\s+[`\'"]\w+[`\'"]',
            r'\bsegún\s+(el|la|los)\s+[`\'"]\w+[`\'"]',
            r'desviacion_pct_media_historica[_\w]*',
            r'cambio_pct_vs_historico',
            r'variacion_vs_promedio_pct',
            r'promedio_30d_historico',
            r'media_historica_2020_2025',
            r'valor_actual_pct',
            r'promedio_proyectado_1m',
            r'rango_min|rango_max',
            r'cambio_pct_vs_prom30d',
            r'estado_actual\.fichas',
            r'predicciones_mes\.metricas_clave',
            r'generacion_por_fuente',
            r'embalses_detalle',
            r'semaforo_kpi',
            r'confianza_modelo',
        ]

        n_replacements = 0
        for pattern in _JSON_FIELD_PATTERNS:
            texto_new = _re.sub(pattern, '', texto, flags=_re.IGNORECASE)
            if texto_new != texto:
                n_replacements += 1
                texto = texto_new

        texto = _re.sub(r'`([^`\n]{1,80})`', r'\1', texto)
        texto = _re.sub(r'  +', ' ', texto)
        texto = _re.sub(r'\n{4,}', '\n\n\n', texto)

        _FRASES_VACIAS = [
            r',?\s*según el campo\s*',
            r',?\s*como se refleja en los datos\s*',
            r',?\s*de acuerdo (?:con|a) los datos proporcionados\s*',
        ]
        for pattern in _FRASES_VACIAS:
            texto = _re.sub(pattern, '', texto, flags=_re.IGNORECASE)

        section_headers = _re.findall(r'^##\s+', texto, flags=_re.MULTILINE)
        n_sections = len(section_headers)

        if n_sections < 3:
            logger.warning(
                f"[INFORME_IA_POST] Solo {n_sections} secciones detectadas (mínimo 3). Rechazado."
            )
            return None

        if len(texto.strip()) < 400:
            logger.warning(
                f"[INFORME_IA_POST] Texto muy corto post-limpieza ({len(texto.strip())} chars). Rechazado."
            )
            return None

        if n_replacements > 0:
            logger.info(
                f"[INFORME_IA_POST] Limpieza: {n_replacements} patrones JSON eliminados, "
                f"{original_len}→{len(texto)} chars, {n_sections} secciones OK"
            )
        else:
            logger.info(
                f"[INFORME_IA_POST] Texto limpio ({len(texto)} chars, {n_sections} secciones). Sin correcciones."
            )

        MAX_CHARS = 3200
        texto = texto.strip()
        if len(texto) > MAX_CHARS:
            _sec5_match = _re.search(r'\n(## 5\..*)', texto, _re.DOTALL)
            if _sec5_match:
                _sec5_text = _sec5_match.group(1).strip()
                _before_sec5 = texto[:_sec5_match.start()]
                _budget = MAX_CHARS - len(_sec5_text) - 4
                if _budget > MAX_CHARS * 0.5:
                    cutoff = _before_sec5[:_budget].rfind('\n\n')
                    if cutoff > _budget * 0.5:
                        _before_sec5 = _before_sec5[:cutoff].rstrip()
                    else:
                        _before_sec5 = _before_sec5[:_budget].rstrip()
                    texto = _before_sec5 + '\n\n' + _sec5_text
                else:
                    texto = texto[:MAX_CHARS].rstrip()
            else:
                cutoff = texto[:MAX_CHARS].rfind('\n\n')
                if cutoff > MAX_CHARS * 0.5:
                    texto = texto[:cutoff].rstrip()
                else:
                    texto = texto[:MAX_CHARS].rstrip()
            logger.info(
                f"[INFORME_IA_POST] Texto truncado de {original_len} a {len(texto)} chars para caber en 1 página PDF"
            )

        return texto

    # ── Helper: Llamar a la IA (Groq/OpenRouter) ──

    async def _generar_informe_con_ia(
        self,
        contexto: Dict[str, Any],
    ) -> Optional[str]:
        """
        Envía el contexto estructurado a Groq/OpenRouter y recibe
        un informe ejecutivo redactado en 5 secciones.
        """
        try:
            from domain.services.ai_service import AgentIA
            import json as _json

            agent = AgentIA()
            if not agent.client:
                logger.warning("[INFORME_IA] Cliente de IA no configurado")
                return None

            contexto_ia = {
                "fecha": contexto.get("fecha_consulta"),
                "estado_actual": contexto.get("estado_actual"),
                "predicciones_mes": contexto.get("predicciones_mes"),
                "anomalias": {
                    "total": contexto.get("anomalias", {}).get("total_anomalias", 0),
                    "lista": contexto.get("anomalias", {}).get("lista", []),
                    "resumen": contexto.get("anomalias", {}).get("resumen", ""),
                },
            }
            gen_fuente = contexto.get("generacion_por_fuente", {})
            if gen_fuente:
                contexto_ia["generacion_por_fuente"] = gen_fuente
            emb_det = contexto.get("embalses_detalle", {})
            if emb_det and "error" not in emb_det:
                contexto_ia["embalses_detalle"] = emb_det
            vmercado = contexto.get("variables_mercado", {})
            if vmercado:
                contexto_ia["variables_mercado"] = vmercado
            emb_reg = contexto.get("embalses_regionales", {})
            if emb_reg and "regiones" in emb_reg:
                # Versión compacta para IA: solo region, pct, estado
                contexto_ia["embalses_regionales"] = {
                    "fecha_dato": emb_reg.get("fecha_dato", ""),
                    "regiones": [
                        {
                            "region": r["region"],
                            "pct": r["pct_promedio"],
                            "estado": r["estado"],
                        }
                        for r in emb_reg["regiones"]
                    ],
                }
            tabla_kpi = contexto.get("tabla_indicadores_clave", [])
            if tabla_kpi:
                contexto_ia["semaforo_kpi"] = tabla_kpi
            conf = contexto.get("confianza_modelos", {})
            if conf:
                contexto_ia["confianza"] = {
                    "experimentales": conf.get("fuentes_experimentales", []),
                    "resumen": conf.get("resumen", ""),
                }
            notas = contexto.get("notas_negocio", {})
            if notas:
                contexto_ia["umbrales"] = {
                    "embalses": notas.get("umbrales_embalses", {}),
                    "anomalias": notas.get("umbrales_anomalias", {}),
                }
            prensa = contexto.get("prensa_del_dia", {})
            if prensa:
                noticias_trim = []
                for n in prensa.get("noticias", [])[:5]:
                    entry = {"titulo": n.get("titulo", ""), "fuente": n.get("fuente", "")}
                    resumen = n.get("resumen", "")
                    if resumen:
                        entry["resumen"] = resumen[:250]
                    noticias_trim.append(entry)
                contexto_ia["noticias"] = {
                    "resumen_dia": prensa.get("resumen_general", ""),
                    "titulares": noticias_trim,
                }

            contexto_json = _json.dumps(contexto_ia, ensure_ascii=False, default=str)
            logger.info(
                f"[INFORME_IA] Contexto optimizado: {len(contexto_json)} chars "
                f"(~{len(contexto_json)//4} tokens)"
            )

            system_prompt = (
                "Eres un analista experto del sector energético colombiano "
                "(MME, XM, UPME). Genera un INFORME EJECUTIVO de EXACTAMENTE "
                "5 secciones numeradas.\n\n"
                "DATOS QUE RECIBES (JSON):\n"
                "• fichas: 3 KPIs (Generación, Precio Bolsa, Embalses) con valor, "
                "tendencia y contexto histórico.\n"
                "• generacion_por_fuente: participación por tipo con GWh y %.\n"
                "• embalses_detalle: nivel actual vs media histórica 2020–2025.\n"
                "• variables_mercado: precio escasez, precio máx oferta nacional, "
                "PPP precio bolsa y demanda regulada/no regulada (GWh/día del SIN).\n"
                "• embalses_regionales: nivel de llenado promedio por región hidrológica "
                "(Antioquia, Centro, Huila, etc.) con % y estado semáforo.\n"
                "• predicciones_mes: proyecciones 1 mes (promedio, rango, tendencia).\n"
                "• anomalias: alertas con severidad y desvío.\n"
                "• noticias.titulares: noticias del sector (puede estar vacío).\n\n"
                "═══ REGLAS OBLIGATORIAS ═══\n\n"
                "R1 — NO REPITAS NÚMEROS: La página 1 del PDF ya muestra una TABLA "
                "SEMÁFORO con los 3 indicadores, sus valores exactos, tendencia y estado. "
                "Tu texto va en la página 4. PROHIBIDO mencionar valores específicos. "
                "Usa lenguaje CUALITATIVO.\n\n"
                "R2 — LONGITUD: Máximo 600 palabras / ≤3000 caracteres.\n\n"
                "R3 — ESTRUCTURA EXACTA: Exactamente 5 secciones, ni más ni menos.\n\n"
                "R4 — NUNCA uses nombres de campos JSON, backticks, guiones bajos.\n\n"
                "R5a — NUNCA inventes datos ni detalles que no estén en el JSON.\n\n"
                "R5b — ANOMALÍAS: Si existen en el contexto, son OBLIGATORIAS en "
                "sección 3.1. Cada una con causa probable e implicación operativa.\n\n"
                "R5c — NOTICIAS: Solo integra noticias si el contexto incluye "
                "titulares Y son directamente relevantes al sector energético colombiano. "
                "Si no hay noticias pertinentes, omite esa referencia por completo. "
                "NUNCA menciones titulares inventados.\n\n"
                "R6 — PRECIO_BOLSA es experimental. Generación y Embalses son de alta confianza.\n\n"
                "═══ ESTRUCTURA OBLIGATORIA (5 secciones) ═══\n\n"
                "## 1. Contexto general del sistema\n"
                "## 2. Señales clave y evolución\n"
                "### 2.1 Proyecciones del próximo mes\n"
                "### 2.2 Análisis cualitativo\n"
                "## 3. Riesgos y oportunidades\n"
                "### 3.1 Riesgos operativos (corto plazo)\n"
                "### 3.2 Riesgos estructurales (mediano plazo)\n"
                "### 3.3 Oportunidades\n"
                "## 4. Recomendaciones para el Viceministro\n"
                "### 4.1 Corto plazo (días/semana)\n"
                "### 4.2 Mediano plazo (semanas/meses)\n"
                "## 5. Calificación del sistema\n"
                "OBLIGATORIO. Elige una: ESTABLE / EN VIGILANCIA / PREOCUPANTE "
                "y justifica en 2-3 frases.\n\n"
                "═══ EJEMPLOS DE ESTILO (sigue este tono exacto) ═══\n\n"
                "SECCIÓN 1 — bien escrita:\n"
                "\"El Sistema Interconectado Nacional opera con oferta ajustada. "
                "La generación hidráulica lidera el despacho, sostenida por embalses "
                "que se ubican por encima de su media histórica para este período. "
                "La demanda mantiene su tendencia estacional sin eventos atípicos relevantes.\"\n\n"
                "SECCIÓN 3.1 — bien escrita:\n"
                "\"La principal alerta es una desviación significativa en la generación "
                "térmica respecto a su media histórica, asociada a restricciones de "
                "combustible en plantas del interior. Esta condición eleva la dependencia "
                "hidráulica y puede presionar el precio de bolsa si los aportes hídricos "
                "no compensan el déficit.\"\n\n"
                "SECCIÓN 5 — bien escrita:\n"
                "\"**EN VIGILANCIA.** La combinación de embalses por debajo del umbral de "
                "alerta y demanda en tendencia alcista configura un riesgo moderado para "
                "las próximas semanas. Se recomienda seguimiento diario de aportes "
                "hídricos y activación temprana de la reserva térmica disponible.\"\n\n"
                "═══ ESTILO ═══\n"
                "Español técnico-profesional. ## para secciones, ### para sub-secciones.\n"
                "Empieza directamente con el análisis. Evita frases introductorias genéricas."
            )

            _anomalias_para_prompt = []
            for _a in contexto_ia.get("anomalias", {}).get("lista", []):
                _sev = _a.get("severidad", "alerta").upper()
                _ind = _a.get("indicador", _a.get("metrica", "desconocida"))
                _desc = _a.get("descripcion", _a.get("detalle", "sin detalle"))
                _anomalias_para_prompt.append(f"  - [{_sev}] {_ind}: {_desc}")

            if _anomalias_para_prompt:
                _bloque_anomalias = (
                    "\n\n⚠️ ANOMALÍAS DETECTADAS HOY (OBLIGATORIO incluirlas en sección 3.1):\n"
                    + "\n".join(_anomalias_para_prompt)
                    + "\n\nCada una DEBE aparecer en '3.1 Riesgos operativos' con su "
                    "magnitud, causa probable e implicación."
                )
            else:
                _bloque_anomalias = ""

            # Bloque condicional de noticias (D5 — nunca forces noticias vacías)
            _noticias_count = len(contexto_ia.get("noticias", {}).get("titulares", []))
            if _noticias_count > 0:
                _bloque_noticias_user = (
                    f"\n\n📰 HAY {_noticias_count} NOTICIAS en el contexto JSON. "
                    "Integra solo las directamente relacionadas con el sector energético "
                    "colombiano (SIN, XM, precios, generación, embalses, regulación). "
                    "Si un titular no es relevante, no lo forces en el texto."
                )
            else:
                _bloque_noticias_user = (
                    "\n\n📰 No hay noticias disponibles hoy. "
                    "Omite cualquier referencia a prensa o titulares en el informe."
                )

            user_prompt = (
                f"Datos del sistema eléctrico colombiano para hoy:\n\n"
                f"```json\n{contexto_json}\n```"
                f"{_bloque_anomalias}"
                f"{_bloque_noticias_user}\n\n"
                f"Genera el informe ejecutivo con EXACTAMENTE 5 secciones numeradas.\n\n"
                f"RECORDATORIOS CRÍTICOS:\n"
                f"- NO menciones valores numéricos específicos. Usa lenguaje cualitativo.\n"
                f"- Cada anomalía → sección 3.1 con causa probable e implicación operativa.\n"
                f"- Sección 5 es OBLIGATORIA: elige ESTABLE / EN VIGILANCIA / PREOCUPANTE.\n"
                f"- Máximo 600 palabras."
            )

            def _call_ai():
                return agent.client.chat.completions.create(
                    model=agent.modelo,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(_call_ai),
                timeout=60
            )

            texto = response.choices[0].message.content.strip()
            if len(texto) < 100:
                logger.warning(f"[INFORME_IA] Respuesta muy corta ({len(texto)} chars)")
                return None

            logger.info(
                f"[INFORME_IA] Informe generado con {agent.provider}/{agent.modelo} ({len(texto)} chars)"
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
        Genera un informe de texto plano a partir del contexto, sin depender de IA.
        """
        lines = []

        # ── Sección 1: Contexto general ──
        lines.append("## 1. Contexto general del sistema")
        fichas = contexto.get('estado_actual', {}).get('fichas', [])
        if fichas:
            for f in fichas:
                emoji_f = f.get('emoji', '•')
                ind = f.get('indicador', '?')
                val = f.get('valor', '?')
                und = f.get('unidad', '')
                fecha_f = f.get('fecha', '?')
                lines.append(f"- {emoji_f} **{ind}:** {val} {und} ({fecha_f})")
                ctx = f.get('contexto', {})
                if 'variacion_vs_promedio_pct' in ctx:
                    etiq = ctx.get('etiqueta_variacion', 'vs 7d')
                    lines.append(f"  - Variación {etiq}: **{ctx['variacion_vs_promedio_pct']}%**")
                if 'variacion_vs_historico_pct' in ctx:
                    prom_h = ctx.get('promedio_historico_mes', '?')
                    var_h = ctx['variacion_vs_historico_pct']
                    estado_e = ctx.get('estado', '')
                    lines.append(f"  - Variación vs histórico mes: **{var_h}%** (prom. histórico: {prom_h}%)")
                    lines.append(f"  - Estado: {estado_e}")
                if ctx.get('media_historica_2020_2025') is not None:
                    media_h = ctx['media_historica_2020_2025']
                    desv_h = ctx.get('desviacion_pct_media_historica_2020_2025')
                    if desv_h is not None:
                        dir_txt = "por encima" if desv_h >= 0 else "por debajo"
                        lines.append(
                            f"  - Media histórica 2020-2025: **{media_h}%** → "
                            f"nivel actual **{abs(desv_h)}%** {dir_txt}"
                        )
        else:
            lines.append("Sin datos disponibles.")
        lines.append("")

        # ── Sección 2: Señales clave ──
        lines.append("## 2. Señales clave y evolución reciente")
        lines.append("### 2.1 Proyecciones del próximo mes (3 métricas clave)")
        pred_mes = contexto.get('predicciones_mes', {}).get('metricas_clave', {})
        for clave in ['generacion', 'precio_bolsa', 'embalses']:
            pm = pred_mes.get(clave, {})
            if pm:
                emoji_pm = pm.get('emoji', '•')
                ind_pm = pm.get('indicador', clave)
                avg_pm = pm.get('promedio_periodo', '?')
                und_pm = pm.get('unidad', '')
                rmin = pm.get('rango_min', '?')
                rmax = pm.get('rango_max', '?')
                cambio_pm = pm.get('cambio_pct_vs_historico', '?')
                tend_pm = pm.get('tendencia', '?')
                lines.append(
                    f"- {emoji_pm} **{ind_pm}:** {avg_pm} {und_pm} "
                    f"(rango: {rmin}–{rmax}), "
                    f"cambio **{cambio_pm}%** vs histórico → {tend_pm}"
                )
        lines.append("")
        lines.append("### 2.2 Datos de predicción 1 mes (detalle)")
        pred_data = contexto.get('predicciones', {}).get('1_mes', {})
        for p in pred_data.get('indicadores', []):
            r = p.get('resumen', {})
            emoji_p = p.get('emoji', '•')
            ind = p.get('indicador', '?')[:25]
            avg = r.get('promedio_periodo', '?')
            cambio = r.get('cambio_pct', '?')
            tend = p.get('tendencia', '?')
            und = p.get('unidad', '')
            rmin2 = r.get('rango_min', r.get('minimo_periodo', '?'))
            rmax2 = r.get('rango_max', r.get('maximo_periodo', '?'))
            lines.append(f"- {emoji_p} **{ind}:** proyección {avg} {und} (rango: {rmin2}–{rmax2}), cambio **{cambio}%** → {tend}")
        lines.append("")

        # ── Sección 3: Riesgos y oportunidades ──
        lines.append("## 3. Riesgos y oportunidades")
        lines.append("### 3.1 Riesgos operativos y de corto plazo")
        anomalias_list = contexto.get('anomalias', {}).get('lista', [])
        if anomalias_list:
            sev_emoji = {'crítico': '🔴', 'alerta': '🟠'}
            for a in anomalias_list:
                se = sev_emoji.get(a.get('severidad', ''), '⚪')
                indicador = a.get('indicador', '?')
                valor = a.get('valor_actual', '?')
                unidad = a.get('unidad', '')
                desv = a.get('desviacion_pct', '?')
                sev = a.get('severidad', '?')
                lines.append(
                    f"- {se} **{indicador}:** {valor} {unidad} — desvío **{desv}%** ({sev})"
                )
                if 'embalse' in indicador.lower() or 'porcentaje' in indicador.lower():
                    try:
                        v = float(valor) if valor != '?' else None
                    except (ValueError, TypeError):
                        v = None
                    if v is not None:
                        if v < 30:
                            lines.append("  - → Nivel **CRÍTICO**: riesgo de racionamiento eléctrico.")
                        elif v < 40:
                            lines.append("  - → Nivel de **ALERTA**: reservas hídricas por debajo del óptimo.")
                elif 'precio' in indicador.lower() or 'bolsa' in indicador.lower():
                    try:
                        d = float(desv) if desv != '?' else 0
                    except (ValueError, TypeError):
                        d = 0
                    if d > 40:
                        lines.append("  - → Desvío **CRÍTICO** en precios: posible estrés de mercado.")
                    elif d > 20:
                        lines.append("  - → Volatilidad moderada en precio de bolsa.")
                elif 'generaci' in indicador.lower():
                    lines.append("  - → Evaluar composición de la matriz y disponibilidad térmica.")
        else:
            lines.append("- ✅ No se detectaron anomalías significativas en los indicadores.")
        lines.append("")

        lines.append("### 3.2 Riesgos estructurales y de mediano plazo")
        for p in pred_data.get('indicadores', []):
            r = p.get('resumen', {})
            ind_name = p.get('indicador', '?')
            cambio = r.get('cambio_pct', 0)
            tend = p.get('tendencia', '?')
            try:
                cambio_f = float(cambio) if cambio != '?' else 0
            except (ValueError, TypeError):
                cambio_f = 0
            if abs(cambio_f) > 10:
                direction = 'incremento' if cambio_f > 0 else 'descenso'
                lines.append(
                    f"- ⚠️ **{ind_name}:** {direction} proyectado de **{abs(cambio_f):.1f}%** "
                    f"respecto al histórico → tendencia {tend}."
                )
            else:
                lines.append(
                    f"- {ind_name}: estable (cambio **{cambio_f:+.1f}%**), tendencia {tend}."
                )
        lines.append("")

        lines.append("### 3.3 Oportunidades")
        emb_val = None
        for f in fichas:
            if 'embalse' in f.get('indicador', '').lower() or 'porcentaje' in f.get('indicador', '').lower():
                try:
                    emb_val = float(f.get('valor', 0))
                except (ValueError, TypeError):
                    pass
        if emb_val and emb_val > 70:
            lines.append(f"- Embalses en **{emb_val}%**: condición favorable para exportación de energía y reducción de costos.")
        elif emb_val and emb_val < 50:
            lines.append(f"- Embalses en **{emb_val}%**: oportunidad para acelerar proyectos renovables no convencionales.")
        lines.append("- Potencial de expansión en generación solar y eólica.")
        lines.append("- Oportunidades en eficiencia energética y gestión de demanda.")
        lines.append("")

        # ── Sección 4: Recomendaciones ──
        lines.append("## 4. Recomendaciones técnicas para el Viceministro")
        lines.append("### 4.1 Recomendaciones de corto plazo")
        recomendaciones_cp = []
        if anomalias_list:
            for a in anomalias_list:
                indicador = a.get('indicador', '').lower()
                try:
                    desv = float(a.get('desviacion_pct', 0))
                except (ValueError, TypeError):
                    desv = 0
                if 'precio' in indicador or 'bolsa' in indicador:
                    if desv > 20:
                        recomendaciones_cp.append(f"- Revisar contratos bilaterales ante volatilidad de precios ({desv:.0f}% de desvío).")
                if 'embalse' in indicador or 'porcentaje' in indicador:
                    recomendaciones_cp.append("- Intensificar monitoreo de embalses y coordinar con IDEAM.")
                if 'generaci' in indicador:
                    recomendaciones_cp.append("- Verificar disponibilidad de plantas térmicas de respaldo.")
        if not recomendaciones_cp:
            recomendaciones_cp.append("- Monitorear indicadores con desvío > 15%.")
        recomendaciones_cp.append("- Verificar pronóstico hidrológico del IDEAM para despacho semanal.")
        seen = set()
        for r in recomendaciones_cp:
            if r not in seen:
                seen.add(r)
                lines.append(r)
        lines.append("")

        lines.append("### 4.2 Recomendaciones de mediano plazo")
        lines.append("- Evaluar cumplimiento de metas de transición energética.")
        lines.append("- Revisar cronograma de proyectos de generación y transmisión en regiones críticas.")
        lines.append("- Diseñar medidas de gestión de demanda si se espera estrechez prolongada.")
        lines.append("")

        # ── Sección 5: Cierre ejecutivo ──
        lines.append("## 5. Cierre ejecutivo")
        n_criticos = sum(1 for a in anomalias_list if a.get('severidad') == 'crítico')
        n_alertas = sum(1 for a in anomalias_list if a.get('severidad') == 'alerta')
        if n_criticos > 0:
            lines.append("El sistema presenta señales de **PREOCUPACIÓN** que requieren atención inmediata del Despacho.")
        elif n_alertas > 0:
            lines.append("El sistema se encuentra en zona de **VIGILANCIA**. Se recomienda seguimiento cercano de los indicadores señalados.")
        else:
            lines.append("El sistema opera dentro de parámetros **normales**. No se requieren acciones inmediatas extraordinarias.")
        lines.append("")

        if not contexto.get('_generado_con_ia', True):
            lines.append("_⚠️ Informe generado sin IA (servicio no disponible)._")

        return "\n".join(lines)
