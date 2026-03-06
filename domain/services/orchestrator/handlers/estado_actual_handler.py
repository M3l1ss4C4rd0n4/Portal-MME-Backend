"""
Mixin: Estado actual + helpers de datos históricos y de construcción de bloques.
Este mixin define los 11 métodos compartidos que otros mixins consumen vía MRO.
"""
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = logging.getLogger(__name__)


class EstadoActualHandlerMixin:
    """
    Mixin que agrupa:
    - _handle_estado_actual          (handler principal)
    - _evaluar_nivel_embalses_historico
    - _get_real_e_historico          (shared helper para anomalías)
    - _get_embalses_real_e_historico (shared helper para anomalías)
    - _get_historical_avg_30d        (shared helper para predicciones)
    - _get_embalses_avg_30d          (shared helper para predicciones)
    - _get_media_historica_embalses_2020_2025
    - _build_generacion_por_fuente
    - _build_embalses_detalle
    - _build_predicciones_mes_resumen
    - _build_tabla_indicadores_clave
    - _deduplicar_anomalias          (@staticmethod)
    """

    @handle_service_error
    async def _handle_estado_actual(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler principal 1️⃣: Estado actual del sector.

        Retorna SOLO los 3 indicadores clave del Viceministro:
        - Generación Total del Sistema (GWh)
        - Precio de Bolsa Nacional (COP/kWh)
        - Porcentaje de Embalses (%)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        fichas: List[Dict[str, Any]] = []

        hoy = date.today()
        ayer = hoy - timedelta(days=1)
        hace_7_dias = hoy - timedelta(days=7)

        # ─── FICHA 1: GENERACIÓN TOTAL DEL SISTEMA ───
        try:
            df_gen = await asyncio.wait_for(
                asyncio.to_thread(
                    self.generation_service.get_daily_generation_system,
                    hace_7_dias, ayer
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            if not df_gen.empty:
                ultimo_dia = df_gen.sort_values('fecha').iloc[-1]
                valor_ultimo = float(ultimo_dia['valor_gwh'])
                fecha_raw = ultimo_dia['fecha']
                fecha_dato = fecha_raw.strftime('%Y-%m-%d') if hasattr(fecha_raw, 'strftime') else str(fecha_raw)[:10]
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
                        "referencia_comparacion": "Comparado con el promedio de los últimos 7 días.",
                    }
                })
            else:
                fichas.append({"indicador": "Generación Total del Sistema", "emoji": "⚡", "valor": None, "unidad": "GWh", "error": "Sin datos disponibles"})
        except Exception as e:
            logger.warning(f"Error obteniendo generación: {e}")
            fichas.append({"indicador": "Generación Total del Sistema", "emoji": "⚡", "valor": None, "unidad": "GWh", "error": "Error consultando datos"})

        # ─── FICHA 2: PRECIO DE BOLSA NACIONAL ───
        try:
            df_precio = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'PrecBolsNaci', hace_7_dias.isoformat(), ayer.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )
            if not df_precio.empty and 'Value' in df_precio.columns:
                df_precio_sorted = df_precio.sort_values('Date') if 'Date' in df_precio.columns else df_precio
                ultimo_precio = float(df_precio_sorted['Value'].iloc[-1])
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
                        "referencia_comparacion": "Comparado con el promedio de los últimos 7 días.",
                    }
                })
            else:
                fichas.append({"indicador": "Precio de Bolsa Nacional", "emoji": "💰", "valor": None, "unidad": "COP/kWh", "error": "Sin datos disponibles"})
        except Exception as e:
            logger.warning(f"Error obteniendo precio: {e}")
            fichas.append({"indicador": "Precio de Bolsa Nacional", "emoji": "💰", "valor": None, "unidad": "COP/kWh", "error": "Error consultando datos"})

        # ─── FICHA 3: PORCENTAJE DE EMBALSES ───
        try:
            nivel_pct = None
            energia_gwh = None
            fecha_embalses = None

            for dias_atras in range(1, 8):
                fecha_intento = (hoy - timedelta(days=dias_atras)).isoformat()
                _pct, _gwh, _fecha = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.hydrology_service.get_reservas_hidricas, fecha_intento
                    ),
                    timeout=self.SERVICE_TIMEOUT
                )
                if _pct is not None:
                    nivel_pct, energia_gwh, fecha_embalses = _pct, _gwh, _fecha
                    if dias_atras > 1:
                        logger.info(f"[EMBALSES] Dato encontrado {dias_atras}d atrás ({fecha_embalses})")
                    break

            if nivel_pct is not None:
                estado_embalse, referencia_hist, prom_hist = self._evaluar_nivel_embalses_historico(nivel_pct)
                variacion_hist = round((nivel_pct - prom_hist) / prom_hist * 100, 1) if prom_hist > 0 else 0
                promedio_30d, dias_30d = await asyncio.to_thread(self._get_embalses_avg_30d)
                media_hist_2020_2025 = await asyncio.to_thread(self._get_media_historica_embalses_2020_2025)
                desviacion_media_hist = None
                if media_hist_2020_2025 is not None and media_hist_2020_2025 > 0:
                    desviacion_media_hist = round((nivel_pct - media_hist_2020_2025) / media_hist_2020_2025 * 100, 1)
                fichas.append({
                    "indicador": "Porcentaje de Embalses",
                    "emoji": "💧",
                    "valor": round(nivel_pct, 2),
                    "unidad": "%",
                    "fecha": fecha_embalses or ayer.isoformat(),
                    "contexto": {
                        "energia_embalsada_gwh": round(energia_gwh, 2) if energia_gwh else None,
                        "estado": estado_embalse,
                        "referencia_historica": referencia_hist,
                        "promedio_historico_mes": prom_hist,
                        "variacion_vs_historico_pct": variacion_hist,
                        "variacion_vs_promedio_pct": desviacion_media_hist,
                        "etiqueta_variacion": "vs Media 2020-2025",
                        "promedio_30d": round(promedio_30d, 2) if promedio_30d else None,
                        "dias_con_datos_30d": dias_30d,
                        "media_historica_2020_2025": round(media_hist_2020_2025, 2) if media_hist_2020_2025 else None,
                        "desviacion_pct_media_historica_2020_2025": desviacion_media_hist,
                        "nota_embalses": (
                            f"Dato del {fecha_embalses}. XM publica embalses cada 1-3 días. "
                            "Se seleccionó el último dato completo en ventana de 7 días."
                        ),
                    }
                })
            else:
                fichas.append({"indicador": "Porcentaje de Embalses", "emoji": "💧", "valor": None, "unidad": "%", "error": "Sin datos disponibles en los últimos 7 días"})
        except Exception as e:
            logger.warning(f"Error obteniendo embalses: {e}")
            fichas.append({"indicador": "Porcentaje de Embalses", "emoji": "💧", "valor": None, "unidad": "%", "error": "Error consultando datos"})

        data['fichas'] = fichas
        data['fecha_consulta'] = datetime.utcnow().isoformat()
        data['opcion_regresar'] = {"id": "menu", "titulo": "🔙 Regresar al menú principal"}

        fichas_con_error = [f for f in fichas if f.get('valor') is None]
        for f in fichas_con_error:
            errors.append(ErrorDetail(code="PARTIAL_DATA", message=f"No se obtuvieron datos para: {f['indicador']}"))

        logger.info(
            f"[ESTADO_ACTUAL] Fichas generadas: {len(fichas)} | "
            f"Con datos: {len(fichas) - len(fichas_con_error)}/{len(fichas)}"
        )
        return data, errors

    # ── Helper: Evaluar nivel de embalses con percentiles históricos ──

    def _evaluar_nivel_embalses_historico(
        self,
        nivel_pct: float,
    ) -> Tuple[str, str, float]:
        """
        Evalúa el nivel de embalses actual comparándolo con los
        percentiles 25/75 del histórico para el mismo mes.

        Returns: (estado_emoji_texto, referencia_historica_texto, promedio_historico)
        """
        try:
            from infrastructure.database.manager import db_manager
            hoy = date.today()
            mes_actual = hoy.month
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap,
                           COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END) as n_vol,
                           COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) as n_cap
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
                WHERE n_cap > 0 AND n_vol::float / n_cap >= 0.80
                ORDER BY fecha ASC
            """
            df = db_manager.query_df(query, params=(mes_actual, hoy.isoformat()))
            if df is not None and len(df) >= 10:
                import numpy as _np
                p25 = float(_np.percentile(df['pct'].values, 25))
                p75 = float(_np.percentile(df['pct'].values, 75))
                avg = float(df['pct'].mean())
                anio_min = max(2020, hoy.year - 6)
                MESES_ES = {
                    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
                }
                mes_nombre = MESES_ES.get(mes_actual, str(mes_actual))
                if nivel_pct >= p75:
                    estado = "🟢 Nivel alto"
                    ref = (
                        f"Por encima del 75% de los valores históricos de {mes_nombre} "
                        f"({anio_min}–{hoy.year - 1}). Percentil 75 ≈ {p75:.0f}%, promedio ≈ {avg:.0f}%."
                    )
                elif nivel_pct >= p25:
                    estado = "🟡 Nivel medio"
                    ref = (
                        f"Dentro del rango típico de {mes_nombre} ({anio_min}–{hoy.year - 1}): "
                        f"entre {p25:.0f}% y {p75:.0f}%. Promedio ≈ {avg:.0f}%."
                    )
                else:
                    estado = "🟠 Nivel bajo"
                    ref = (
                        f"Por debajo del 25% de los valores históricos de {mes_nombre} "
                        f"({anio_min}–{hoy.year - 1}). Percentil 25 ≈ {p25:.0f}%, promedio ≈ {avg:.0f}%."
                    )
                return estado, ref, round(avg, 1)
            else:
                logger.info("[EMBALSES] Histórico insuficiente, usando umbrales fijos")
        except Exception as e:
            logger.warning(f"Error calculando percentiles embalses: {e}")

        if nivel_pct >= 70:
            return "🟢 Nivel alto", "Referencia: umbral fijo ≥70%", 60.0
        elif nivel_pct >= 50:
            return "🟡 Nivel medio", "Referencia: umbral fijo 50-70%", 60.0
        elif nivel_pct >= 30:
            return "🟠 Nivel bajo", "Referencia: umbral fijo 30-50%", 60.0
        else:
            return "🔴 Nivel crítico", "Referencia: umbral fijo <30%", 60.0

    # ── Shared helpers utilizados por AnomaliaHandlerMixin vía MRO ──

    def _get_real_e_historico(
        self,
        metric_id: str,
        entity: str,
        fecha_desde: date,
        fecha_hasta: date,
    ) -> Tuple[Optional[float], Optional[str], Optional[float], int]:
        """
        Obtiene el último valor real y el promedio histórico 30d para una métrica/entidad.
        Returns: (valor_actual, fecha_dato_str, avg_hist, dias_con_datos)
        """
        try:
            df = self.metrics_service.get_metric_series_by_entity(
                metric_id=metric_id, entity=entity,
                start_date=fecha_desde.isoformat(), end_date=fecha_hasta.isoformat()
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
        Filtra días con datos incompletos (<80% cobertura).
        """
        try:
            hoy = date.today()
            hace_30 = hoy - timedelta(days=30)
            from infrastructure.database.manager import db_manager
            query = """
                WITH emb_conteo AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap,
                           COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END) as n_vol,
                           COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) as n_cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND fecha >= %s AND fecha <= %s
                    GROUP BY fecha
                    HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                )
                SELECT fecha, vol / cap * 100 as pct
                FROM emb_conteo
                WHERE n_cap > 0
                  AND n_vol::float / n_cap >= 0.80
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

    # ── Shared helpers utilizados por PrediccionesHandlerMixin vía MRO ──

    def _get_historical_avg_30d(
        self,
        metric_id: str,
        entity: str = 'Sistema',
    ) -> Tuple[Optional[float], int]:
        """Obtiene promedio de los últimos 30 días reales para una métrica."""
        hoy = date.today()
        hace_30 = hoy - timedelta(days=30)
        try:
            df = self.metrics_service.get_metric_series_by_entity(
                metric_id=metric_id, entity=entity,
                start_date=hace_30.isoformat(), end_date=hoy.isoformat()
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
        """Obtiene promedio % de embalses de los últimos 30 días."""
        hoy = date.today()
        hace_30 = hoy - timedelta(days=30)
        try:
            from infrastructure.database.manager import db_manager
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap,
                           COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END) as n_vol,
                           COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) as n_cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND fecha >= %s AND fecha <= %s
                    GROUP BY fecha
                )
                SELECT COUNT(*) as dias, AVG(vol / NULLIF(cap, 0) * 100) as avg_pct
                FROM emb_diario
                WHERE cap > 0 AND n_cap > 0 AND n_vol::float / n_cap >= 0.80
            """
            df = db_manager.query_df(query, params=(hace_30.isoformat(), hoy.isoformat()))
            if not df.empty and df['avg_pct'].iloc[0] is not None:
                return float(df['avg_pct'].iloc[0]), int(df['dias'].iloc[0])
            return None, 0
        except Exception as e:
            logger.warning(f"Error obteniendo histórico 30d de embalses: {e}")
            return None, 0

    def _get_media_historica_embalses_2020_2025(self) -> Optional[float]:
        """Calcula la media histórica de embalses (%) del periodo 2020–2025."""
        try:
            from infrastructure.database.manager import db_manager
            query = """
                WITH emb_diario AS (
                    SELECT fecha,
                           SUM(CASE WHEN metrica='VoluUtilDiarEner' THEN valor_gwh ELSE 0 END) as vol,
                           SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) as cap,
                           COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END) as n_vol,
                           COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END) as n_cap
                    FROM metrics
                    WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner')
                    AND entidad = 'Embalse'
                    AND fecha >= '2020-01-01'
                    AND fecha <= '2025-12-31'
                    GROUP BY fecha
                    HAVING SUM(CASE WHEN metrica='CapaUtilDiarEner' THEN valor_gwh ELSE 0 END) > 0
                )
                SELECT AVG(vol / cap * 100) as media_pct,
                       COUNT(*) as dias_con_datos
                FROM emb_diario
                WHERE n_cap > 0 AND n_vol::float / n_cap >= 0.80
            """
            df = db_manager.query_df(query)
            if df is not None and not df.empty and df['media_pct'].iloc[0] is not None:
                dias = int(df['dias_con_datos'].iloc[0])
                media = float(df['media_pct'].iloc[0])
                logger.info(f"[EMBALSES] Media histórica 2020-2025: {media:.1f}% ({dias} días con datos)")
                return media
            return None
        except Exception as e:
            logger.warning(f"Error calculando media histórica 2020-2025 embalses: {e}")
            return None

    # ── Helpers de construcción de bloques para InformeHandlerMixin vía MRO ──

    async def _build_generacion_por_fuente(self) -> Dict[str, Any]:
        """
        Construye desglose de generación por tipo de fuente para el último
        día disponible (ventana 7 días hacia atrás).
        """
        hoy = date.today()
        _NOMBRES_FUENTE = {
            'HIDRAULICA': 'Hidráulica', 'TERMICA': 'Térmica',
            'EOLICA': 'Eólica', 'SOLAR': 'Solar',
            'COGENERADOR': 'Biomasa/Cogeneración',
        }
        for dias_atras in range(1, 8):
            fecha_intento = hoy - timedelta(days=dias_atras)
            try:
                df_mix = await asyncio.wait_for(
                    asyncio.to_thread(self.generation_service.get_generation_mix, fecha_intento),
                    timeout=self.SERVICE_TIMEOUT,
                )
                if df_mix is not None and not df_mix.empty:
                    total_gwh = float(df_mix['generacion_gwh'].sum())
                    fuentes = []
                    for _, row in df_mix.iterrows():
                        tipo_raw = str(row['tipo']).upper().strip()
                        fuentes.append({
                            "fuente": _NOMBRES_FUENTE.get(tipo_raw, tipo_raw.capitalize()),
                            "gwh": round(float(row['generacion_gwh']), 2),
                            "porcentaje": round(float(row['porcentaje']), 1),
                        })
                    fuentes.sort(key=lambda f: f['porcentaje'], reverse=True)
                    logger.info(f"[INFORME] generacion_por_fuente OK: {len(fuentes)} fuentes, total={total_gwh:.1f} GWh, fecha={fecha_intento}")
                    return {
                        "fecha_dato": fecha_intento.isoformat(),
                        "total_gwh": round(total_gwh, 2),
                        "fuentes": fuentes,
                        "nota": f"Mix energético del {fecha_intento.isoformat()}. XM puede publicar con 1-3 días de retraso.",
                    }
            except Exception as e:
                logger.debug(f"[INFORME] Mix fecha {fecha_intento} no disponible: {e}")
                continue
        logger.warning("[INFORME] generacion_por_fuente: sin datos en ventana 7d")
        return {"error": "Sin datos de mix energético en los últimos 7 días"}

    def _build_embalses_detalle(
        self,
        fichas: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Consolida datos de embalses en un bloque detallado para el informe."""
        ficha_emb = None
        for f in fichas:
            if f.get('indicador') == 'Porcentaje de Embalses':
                ficha_emb = f
                break
        if ficha_emb is None or ficha_emb.get('valor') is None:
            return {"error": "Sin datos de embalses disponibles"}
        ctx = ficha_emb.get('contexto', {})
        valor_actual = ficha_emb['valor']
        prom_30d = ctx.get('promedio_30d')
        media_hist = ctx.get('media_historica_2020_2025')
        desviacion = ctx.get('desviacion_pct_media_historica_2020_2025')
        return {
            "fecha_dato": ficha_emb.get('fecha'),
            "valor_actual_pct": valor_actual,
            "promedio_30d_pct": prom_30d,
            "media_historica_2020_2025_pct": round(media_hist, 2) if media_hist else None,
            "desviacion_pct_media_historica": desviacion,
            "energia_embalsada_gwh": ctx.get('energia_embalsada_gwh'),
            "estado": ctx.get('estado', 'Sin evaluación'),
            "referencia_historica": ctx.get('referencia_historica', ''),
            "nota": (
                "Valor actual: último dato con completitud >= 80% "
                "en ventana de 7 días. Media histórica calculada sobre "
                "2020-01-01 a 2025-12-31 con misma fórmula VoluUtil/CapaUtil."
            ),
        }

    def _build_predicciones_mes_resumen(
        self,
        fichas: List[Dict[str, Any]],
        predicciones_mes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Construye bloque compacto de predicciones a 1 mes para las 3 métricas clave.
        """
        metricas_clave = predicciones_mes.get('metricas_clave', {})
        _MAP_INDICADOR = {
            'generacion': 'Generación Total del Sistema',
            'precio_bolsa': 'Precio de Bolsa Nacional',
            'embalses': 'Porcentaje de Embalses',
        }
        _MAP_UNIDAD = {
            'generacion': 'GWh',
            'precio_bolsa': 'COP/kWh',
            'embalses': '%',
        }
        valores_actuales: Dict[str, Any] = {}
        for f in fichas:
            for clave, nombre_ind in _MAP_INDICADOR.items():
                if f.get('indicador') == nombre_ind and f.get('valor') is not None:
                    valores_actuales[clave] = f['valor']

        resultado = []
        for clave in ['generacion', 'precio_bolsa', 'embalses']:
            pred = metricas_clave.get(clave, {})
            if not pred:
                continue
            prom_proyectado = pred.get('promedio_periodo')
            cambio_pct = pred.get('cambio_pct_vs_historico')
            if cambio_pct is not None:
                if cambio_pct > 5:
                    tendencia = "Creciente"
                elif cambio_pct < -5:
                    tendencia = "Decreciente"
                else:
                    tendencia = "Estable"
            else:
                tendencia_raw = pred.get('tendencia', '')
                if 'Creciente' in tendencia_raw:
                    tendencia = "Creciente"
                elif 'Decreciente' in tendencia_raw:
                    tendencia = "Decreciente"
                else:
                    tendencia = "Estable"
            resultado.append({
                "indicador": _MAP_INDICADOR[clave],
                "unidad": _MAP_UNIDAD[clave],
                "valor_actual": valores_actuales.get(clave),
                "promedio_proyectado_1m": prom_proyectado,
                "rango_min": pred.get('rango_min'),
                "rango_max": pred.get('rango_max'),
                "cambio_pct_vs_prom30d": cambio_pct,
                "tendencia": tendencia,
                "confianza_modelo": pred.get('confianza_modelo'),
            })
        return {
            "horizonte": predicciones_mes.get('horizonte', 'Próximo mes'),
            "fecha_inicio": predicciones_mes.get('fecha_inicio'),
            "fecha_fin": predicciones_mes.get('fecha_fin'),
            "metricas": resultado,
            "nota": (
                "Resumen compacto de predicciones 1 mes. "
                "Tendencia: Creciente (>+5%), Estable (±5%), Decreciente (<-5%) "
                "respecto al promedio real de los últimos 30 días."
            ),
        }

    def _build_tabla_indicadores_clave(
        self,
        fichas: List[Dict[str, Any]],
        anomalias_lista: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Construye tabla de indicadores clave con semáforo para el informe.
        Reglas de semáforo documentadas inline.
        """
        anomalias_por_ind: Dict[str, str] = {}
        for a in anomalias_lista:
            nombre = a.get('indicador', '')
            sev = a.get('severidad', 'normal')
            if sev in ('alerta', 'crítico'):
                anomalias_por_ind[nombre] = max(
                    anomalias_por_ind.get(nombre, ''),
                    sev,
                    key=lambda x: {'': 0, 'normal': 0, 'alerta': 1, 'crítico': 2}.get(x, 0)
                )

        tabla = []
        for ficha in fichas:
            ind_nombre = ficha.get('indicador', '')
            valor = ficha.get('valor')
            unidad = ficha.get('unidad', '')
            ctx = ficha.get('contexto', {})
            variacion = ctx.get('variacion_vs_promedio_pct', 0) or 0

            if variacion > 2:
                tendencia = "Alza"
            elif variacion < -2:
                tendencia = "Baja"
            else:
                tendencia = "Estable"

            estado = "Normal"
            _anom_key = ind_nombre

            if 'Generación' in ind_nombre:
                if abs(variacion) > 15:
                    estado = "Crítico"
                elif abs(variacion) > 8:
                    estado = "Alerta"
                _anom_key = 'Generación Total'
            elif 'Precio' in ind_nombre:
                if abs(variacion) > 25:
                    estado = "Crítico"
                elif abs(variacion) > 12:
                    estado = "Alerta"
                _anom_key = 'Precio de Bolsa'
            elif 'Embalses' in ind_nombre:
                if valor is not None:
                    if valor < 30:
                        estado = "Crítico"
                    elif valor < 40 or valor > 85:
                        estado = "Alerta"
                _anom_key = 'Embalses'

            anom_sev = anomalias_por_ind.get(_anom_key, '')
            if anom_sev == 'crítico' and estado != 'Crítico':
                estado = "Crítico"
            elif anom_sev == 'alerta' and estado == 'Normal':
                estado = "Alerta"

            tabla.append({
                "indicador": ind_nombre,
                "valor_actual": valor,
                "unidad": unidad,
                "fecha": ficha.get('fecha'),
                "tendencia": tendencia,
                "variacion_pct": round(variacion, 1),
                "estado": estado,
            })
        return tabla

    @staticmethod
    def _deduplicar_anomalias(
        anomalias: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Elimina anomalías duplicadas manteniendo la más severa.
        Dos anomalías son duplicadas si comparten (indicador, descripcion).
        """
        if not anomalias:
            return anomalias

        _SEV_RANK = {'normal': 0, 'alerta': 1, 'crítico': 2}
        vistos: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for a in anomalias:
            clave = (
                a.get('indicador', ''),
                a.get('descripcion', a.get('detalle', '')),
            )
            if clave in vistos:
                existente = vistos[clave]
                if _SEV_RANK.get(a.get('severidad', 'normal'), 0) > _SEV_RANK.get(existente.get('severidad', 'normal'), 0):
                    vistos[clave] = a
            else:
                vistos[clave] = a

        deduplicadas = list(vistos.values())
        if len(deduplicadas) < len(anomalias):
            logger.info(f"[INFORME] Anomalías deduplicadas: {len(anomalias)} → {len(deduplicadas)}")
        return deduplicadas
