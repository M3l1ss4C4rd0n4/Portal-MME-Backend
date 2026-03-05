"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                     CU SERVICE — Costo Unitario de Energía                    ║
║                                                                               ║
║  Calcula el Costo Unitario (CU) diario de energía eléctrica en Colombia     ║
║  y lo persiste en la tabla cu_daily.                                         ║
║                                                                               ║
║  Fórmula:                                                                    ║
║  CU = (comp_G + comp_T + comp_D + comp_C + comp_R) × factor_pérdidas        ║
║                                                                               ║
║  donde:                                                                      ║
║    comp_G = PrecBolsNaci (COP/kWh, dato XM)                                 ║
║    comp_T = cargo_transmision_cop_kwh (CREG, configuración)                  ║
║    comp_D = cargo_distribucion_cop_kwh (CREG, configuración)                 ║
║    comp_C = cargo_comercializacion_cop_kwh (CREG, configuración)             ║
║    comp_R = (RestAliv_mcop × 1e6) / (DemaCome_gwh × 1e6) → COP/kWh         ║
║    factor_pérdidas = 1 / (1 - pérdidas_stn_pct/100                          ║
║                             - factor_pérdidas_distribución)                  ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import date, timedelta, datetime
from typing import Optional, Union

import pandas as pd

from core.config import get_settings
from core.exceptions import DatabaseError
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)

# Prefijo de log para este servicio
_LOG = "[CU_SERVICE]"


def _ensure_date(d: Union[date, str]) -> date:
    """Convierte string a date si es necesario."""
    if isinstance(d, str):
        return datetime.strptime(d, '%Y-%m-%d').date()
    if isinstance(d, datetime):
        return d.date()
    return d


class CUService:
    """
    Servicio de cálculo del Costo Unitario (CU) de energía eléctrica.

    Implementa Arquitectura Limpia:
    - Usa PostgreSQLConnectionManager (no db_manager legacy)
    - Usa get_settings() para cargos CREG
    - Logging con prefijo [CU_SERVICE]
    """

    def __init__(self):
        """Inicializa el servicio con configuración CREG y conexión DB."""
        self._settings = get_settings()
        self._conn_mgr = PostgreSQLConnectionManager()

        # Cargar cargos CREG desde config
        self._cargo_t = self._settings.CARGO_TRANSMISION_COP_KWH
        self._cargo_d = self._settings.CARGO_DISTRIBUCION_COP_KWH
        self._cargo_c = self._settings.CARGO_COMERCIALIZACION_COP_KWH
        self._factor_perdidas_dist = self._settings.FACTOR_PERDIDAS_DISTRIBUCION

        logger.info(
            f"{_LOG} Inicializado — T={self._cargo_t}, D={self._cargo_d}, "
            f"C={self._cargo_c}, factor_perd_dist={self._factor_perdidas_dist}"
        )

    # ════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS — Obtención de datos
    # ════════════════════════════════════════════════════════════

    def _get_daily_components(self, fecha: date) -> dict:
        """
        Obtiene todos los componentes disponibles para una fecha desde
        la tabla metrics (fuente primaria).

        Retorna dict con:
          gene_gwh, dema_gwh, precio_bolsa, rest_aliv_mcop,
          rest_sin_aliv_mcop, perdidas_gwh, perdidas_stn_pct,
          componentes_disponibles (int 0-7)

        Si un dato no existe para esa fecha → None para ese campo.
        Nunca lanza excepción por dato faltante.
        """
        result = {
            'gene_gwh': None,
            'dema_gwh': None,
            'precio_bolsa': None,
            'rest_aliv_mcop': None,
            'rest_sin_aliv_mcop': None,
            'perdidas_gwh': None,
            'perdidas_stn_pct': None,
            'componentes_disponibles': 0,
        }

        query = """
            SELECT metrica, valor_gwh
            FROM metrics
            WHERE fecha::date = %s
              AND entidad = 'Sistema'
              AND metrica IN (
                  'Gene', 'DemaCome', 'PrecBolsNaci',
                  'RestAliv', 'RestSinAliv', 'PerdidasEner'
              )
        """

        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, (fecha,))
                rows = cur.fetchall()
                cur.close()
                conn.commit()

            conteo = 0
            for metrica, valor in rows:
                if valor is None:
                    continue
                if metrica == 'Gene':
                    result['gene_gwh'] = float(valor)
                    conteo += 1
                elif metrica == 'DemaCome':
                    result['dema_gwh'] = float(valor)
                    conteo += 1
                elif metrica == 'PrecBolsNaci':
                    result['precio_bolsa'] = float(valor)
                    conteo += 1
                elif metrica == 'RestAliv':
                    result['rest_aliv_mcop'] = float(valor)
                    conteo += 1
                elif metrica == 'RestSinAliv':
                    result['rest_sin_aliv_mcop'] = float(valor)
                    conteo += 1
                elif metrica == 'PerdidasEner':
                    result['perdidas_gwh'] = float(valor)
                    conteo += 1

            # Calcular pérdidas STN como porcentaje
            if result['perdidas_gwh'] is not None and result['gene_gwh'] and result['gene_gwh'] > 0:
                result['perdidas_stn_pct'] = (result['perdidas_gwh'] / result['gene_gwh']) * 100
                conteo += 1

            result['componentes_disponibles'] = conteo

        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo componentes para {fecha}: {e}")

        return result

    # ════════════════════════════════════════════════════════════
    # MÉTODOS PÚBLICOS — Cálculo del CU
    # ════════════════════════════════════════════════════════════

    def calculate_cu_for_date(self, fecha: date) -> Optional[dict]:
        """
        Calcula el CU para una fecha.

        Retorna dict con todos los campos para cu_daily.
        Retorna None si no hay datos suficientes (< 2 componentes medidos).
        """
        fecha = _ensure_date(fecha)
        comp = self._get_daily_components(fecha)

        # Mínimo: necesitamos precio de bolsa y al menos un componente más
        metricas_medidas = sum(1 for k in ['gene_gwh', 'dema_gwh', 'precio_bolsa',
                                            'rest_aliv_mcop', 'perdidas_gwh']
                              if comp[k] is not None)

        if metricas_medidas < 2:
            logger.debug(f"{_LOG} {fecha}: solo {metricas_medidas} métricas, insuficiente")
            return None

        # --- Componente G: Generación ---
        comp_g = comp['precio_bolsa'] if comp['precio_bolsa'] is not None else None

        # --- Componente T: Transmisión (cargo fijo CREG) ---
        comp_t = self._cargo_t

        # --- Componente D: Distribución (cargo fijo CREG) ---
        comp_d = self._cargo_d

        # --- Componente C: Comercialización (cargo fijo CREG) ---
        comp_c = self._cargo_c

        # --- Componente R: Restricciones ---
        comp_r = None
        if comp['rest_aliv_mcop'] is not None and comp['dema_gwh'] and comp['dema_gwh'] > 0:
            # RestAliv está en Millones COP, DemaCome en GWh
            # comp_R = (RestAliv_mcop × 1e6) / (DemaCome_gwh × 1e6) = RestAliv / DemaCome COP/kWh
            rest_total_mcop = comp['rest_aliv_mcop']
            if comp['rest_sin_aliv_mcop'] is not None:
                rest_total_mcop += comp['rest_sin_aliv_mcop']
            comp_r = rest_total_mcop / comp['dema_gwh']  # Millones COP / GWh = COP/kWh

        # --- Factor de pérdidas ---
        perdidas_stn_frac = 0.0
        if comp['perdidas_stn_pct'] is not None:
            perdidas_stn_frac = comp['perdidas_stn_pct'] / 100.0

        factor_total = perdidas_stn_frac + self._factor_perdidas_dist
        # factor_pérdidas = 1 / (1 - factor_total)
        # Si factor_total >= 1 (imposible teórico), cap a 0.95
        if factor_total >= 0.95:
            logger.warning(f"{_LOG} {fecha}: factor pérdidas {factor_total:.4f} excesivo, capeando a 0.95")
            factor_total = 0.95
        factor_perdidas = 1.0 / (1.0 - factor_total)

        # --- CU Total ---
        suma_base = 0.0
        componentes_ok = 0

        if comp_g is not None:
            suma_base += comp_g
            componentes_ok += 1
        suma_base += comp_t
        componentes_ok += 1
        suma_base += comp_d
        componentes_ok += 1
        suma_base += comp_c
        componentes_ok += 1
        if comp_r is not None:
            suma_base += comp_r
            componentes_ok += 1

        cu_total = suma_base * factor_perdidas

        # --- Clasificar confianza ---
        if componentes_ok >= 5 and comp['perdidas_stn_pct'] is not None:
            confianza = 'alta'
        elif componentes_ok >= 4:
            confianza = 'media'
        else:
            confianza = 'baja'

        # --- Fuente de cálculo ---
        if comp_g is not None and comp_r is not None and comp['perdidas_stn_pct'] is not None:
            fuente = 'XM_COMPLETO'
        elif comp_g is not None:
            fuente = 'XM_PARCIAL'
        else:
            fuente = 'CREG_SOLO'

        # --- Notas ---
        notas_parts = []
        if comp_g is None:
            notas_parts.append('sin_precio_bolsa')
        if comp_r is None:
            notas_parts.append('sin_restricciones')
        if comp['perdidas_stn_pct'] is None:
            notas_parts.append('sin_perdidas_stn')

        return {
            'fecha': fecha,
            'componente_g': round(comp_g, 4) if comp_g is not None else None,
            'componente_t': round(comp_t, 4),
            'componente_d': round(comp_d, 4),
            'componente_c': round(comp_c, 4),
            'componente_p': round((suma_base * factor_perdidas) - suma_base, 4),
            'componente_r': round(comp_r, 4) if comp_r is not None else None,
            'cu_total': round(cu_total, 4),
            'demanda_gwh': round(comp['dema_gwh'], 6) if comp['dema_gwh'] else None,
            'generacion_gwh': round(comp['gene_gwh'], 6) if comp['gene_gwh'] else None,
            'perdidas_gwh': round(comp['perdidas_gwh'], 6) if comp['perdidas_gwh'] else None,
            'perdidas_pct': round(
                (perdidas_stn_frac + self._factor_perdidas_dist) * 100, 4
            ) if comp['perdidas_stn_pct'] is not None else None,
            'fuentes_ok': componentes_ok,
            'confianza': confianza,
            'notas': '; '.join(notas_parts) if notas_parts else None,
            # Extra campos para API (no se guardan en cu_daily)
            '_fuente_calculo': fuente,
            '_perdidas_stn_pct': round(comp['perdidas_stn_pct'], 4) if comp['perdidas_stn_pct'] else None,
            '_factor_perdidas': round(factor_perdidas, 6),
        }

    def save_cu_for_date(self, fecha: date) -> bool:
        """
        Calcula y guarda en cu_daily. Usa ON CONFLICT DO NOTHING.
        Retorna True si se insertó, False si ya existía o sin datos.
        """
        fecha = _ensure_date(fecha)
        cu = self.calculate_cu_for_date(fecha)
        if cu is None:
            return False

        upsert_sql = """
            INSERT INTO cu_daily (
                fecha, componente_g, componente_t, componente_d,
                componente_c, componente_p, componente_r, cu_total,
                demanda_gwh, generacion_gwh, perdidas_gwh, perdidas_pct,
                fuentes_ok, confianza, notas
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (fecha) DO UPDATE SET
                componente_g = EXCLUDED.componente_g,
                componente_t = EXCLUDED.componente_t,
                componente_d = EXCLUDED.componente_d,
                componente_c = EXCLUDED.componente_c,
                componente_p = EXCLUDED.componente_p,
                componente_r = EXCLUDED.componente_r,
                cu_total = EXCLUDED.cu_total,
                demanda_gwh = EXCLUDED.demanda_gwh,
                generacion_gwh = EXCLUDED.generacion_gwh,
                perdidas_gwh = EXCLUDED.perdidas_gwh,
                perdidas_pct = EXCLUDED.perdidas_pct,
                fuentes_ok = EXCLUDED.fuentes_ok,
                confianza = EXCLUDED.confianza,
                notas = EXCLUDED.notas
        """

        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(upsert_sql, (
                    cu['fecha'],
                    cu['componente_g'], cu['componente_t'],
                    cu['componente_d'], cu['componente_c'],
                    cu['componente_p'], cu['componente_r'],
                    cu['cu_total'],
                    cu['demanda_gwh'], cu['generacion_gwh'],
                    cu['perdidas_gwh'], cu['perdidas_pct'],
                    cu['fuentes_ok'], cu['confianza'], cu['notas'],
                ))
                conn.commit()
                cur.close()
            return True
        except Exception as e:
            logger.error(f"{_LOG} Error guardando CU para {fecha}: {e}")
            raise DatabaseError(f"Error guardando CU: {e}")

    def backfill_cu(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        batch_size: int = 30
    ) -> dict:
        """
        Calcula CU para un rango de fechas. Procesa en lotes.

        Retorna: {"insertados": N, "ya_existian": N, "sin_datos": N,
                  "errores": N, "cobertura_pct": float}
        """
        fecha_inicio = _ensure_date(fecha_inicio)
        fecha_fin = _ensure_date(fecha_fin)

        stats = {'insertados': 0, 'ya_existian': 0, 'sin_datos': 0,
                 'errores': 0, 'total_dias': 0}

        current = fecha_inicio
        batch_start = current

        while current <= fecha_fin:
            stats['total_dias'] += 1
            try:
                cu = self.calculate_cu_for_date(current)
                if cu is None:
                    stats['sin_datos'] += 1
                else:
                    inserted = self.save_cu_for_date(current)
                    if inserted:
                        stats['insertados'] += 1
                    else:
                        stats['ya_existian'] += 1
            except Exception as e:
                stats['errores'] += 1
                logger.error(f"{_LOG} Error en backfill {current}: {e}")

            # Log de progreso cada batch_size días
            if (stats['total_dias'] % batch_size) == 0:
                logger.info(
                    f"{_LOG} Procesado {batch_start} → {current} | "
                    f"Insertados: {stats['insertados']}, Sin datos: {stats['sin_datos']}"
                )
                batch_start = current + timedelta(days=1)

            current += timedelta(days=1)

        # Cobertura
        if stats['total_dias'] > 0:
            stats['cobertura_pct'] = round(
                (stats['insertados'] + stats['ya_existian']) / stats['total_dias'] * 100, 2
            )
        else:
            stats['cobertura_pct'] = 0.0

        logger.info(f"{_LOG} Backfill completado: {stats}")
        return stats

    def get_cu_current(self) -> Optional[dict]:
        """
        Retorna el CU del día más reciente disponible en cu_daily.
        Si cu_daily está vacía, calcula on-the-fly sin guardar.
        """
        query = """
            SELECT fecha, componente_g, componente_t, componente_d,
                   componente_c, componente_p, componente_r, cu_total,
                   demanda_gwh, generacion_gwh, perdidas_gwh, perdidas_pct,
                   fuentes_ok, confianza, notas
            FROM cu_daily
            ORDER BY fecha DESC
            LIMIT 1
        """

        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query)
                row = cur.fetchone()
                cur.close()
                conn.commit()

            if row:
                return self._row_to_dict(row)

            # Fallback: calcular on-the-fly para ayer
            logger.info(f"{_LOG} cu_daily vacía, calculando on-the-fly")
            ayer = date.today() - timedelta(days=1)
            for d in range(0, 7):
                cu = self.calculate_cu_for_date(ayer - timedelta(days=d))
                if cu is not None:
                    return cu
            return None

        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo CU actual: {e}")
            return None

    def get_cu_historico(
        self, fecha_inicio: date, fecha_fin: date
    ) -> pd.DataFrame:
        """
        Retorna serie histórica desde cu_daily.
        Si hay gaps (días sin dato), rellena con NaN explícito.
        """
        fecha_inicio = _ensure_date(fecha_inicio)
        fecha_fin = _ensure_date(fecha_fin)

        query = """
            SELECT fecha, componente_g, componente_t, componente_d,
                   componente_c, componente_p, componente_r, cu_total,
                   demanda_gwh, generacion_gwh, perdidas_gwh, perdidas_pct,
                   fuentes_ok, confianza
            FROM cu_daily
            WHERE fecha BETWEEN %s AND %s
            ORDER BY fecha
        """

        try:
            with self._conn_mgr.get_connection() as conn:
                df = pd.read_sql_query(query, conn, params=(fecha_inicio, fecha_fin))
                conn.commit()

            if df.empty:
                return df

            # Rellenar gaps con NaN
            all_dates = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
            df['fecha'] = pd.to_datetime(df['fecha'])
            df = df.set_index('fecha').reindex(all_dates).rename_axis('fecha').reset_index()

            return df

        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo histórico CU: {e}")
            return pd.DataFrame()

    def get_cu_forecast(self, horizon: int = 30) -> pd.DataFrame:
        """
        Retorna pronóstico del CU para los próximos *horizon* días.

        Estrategia:
        1. Busca en la tabla ``predictions`` (fuente='CU_DIARIO') predicciones
           con fecha_prediccion >= hoy.
        2. Si no hay suficientes datos ML, genera un pronóstico naive basado
           en tendencia lineal de los últimos 30 registros de cu_daily.

        Returns:
            DataFrame con columnas:
                fecha, cu_predicho, limite_inferior, limite_superior,
                confianza, modelo
        """
        horizon = min(max(horizon, 1), 90)
        hoy = date.today()

        # ── 1. Intentar predicciones ML ─────────────────────
        try:
            with self._conn_mgr.get_connection() as conn:
                df_ml = pd.read_sql_query(
                    """
                    SELECT fecha_prediccion AS fecha,
                           valor_gwh_predicho AS cu_predicho,
                           intervalo_inferior AS limite_inferior,
                           intervalo_superior AS limite_superior,
                           confianza,
                           modelo
                    FROM predictions
                    WHERE fuente = 'CU_DIARIO'
                      AND fecha_prediccion >= %s
                    ORDER BY fecha_prediccion
                    LIMIT %s
                    """,
                    conn,
                    params=(hoy, horizon),
                )
                conn.commit()

            if len(df_ml) >= horizon:
                df_ml['fecha'] = pd.to_datetime(df_ml['fecha'])
                for col in ['cu_predicho', 'limite_inferior', 'limite_superior', 'confianza']:
                    df_ml[col] = pd.to_numeric(df_ml[col], errors='coerce')
                return df_ml.head(horizon)
        except Exception as exc:
            logger.warning("%s Error leyendo predictions ML: %s", _LOG, exc)

        # ── 2. Fallback: tendencia lineal naive ─────────────
        logger.info("%s Generando forecast naive (horizon=%d)", _LOG, horizon)
        try:
            with self._conn_mgr.get_connection() as conn:
                df_hist = pd.read_sql_query(
                    """
                    SELECT fecha, cu_total
                    FROM cu_daily
                    ORDER BY fecha DESC
                    LIMIT 30
                    """,
                    conn,
                )
                conn.commit()

            if df_hist.empty:
                return pd.DataFrame(columns=[
                    'fecha', 'cu_predicho', 'limite_inferior',
                    'limite_superior', 'confianza', 'modelo',
                ])

            df_hist = df_hist.sort_values('fecha')
            df_hist['cu_total'] = pd.to_numeric(df_hist['cu_total'], errors='coerce')
            df_hist = df_hist.dropna(subset=['cu_total'])

            import numpy as np
            y = df_hist['cu_total'].values
            x = np.arange(len(y), dtype=float)
            if len(y) >= 2:
                coefs = np.polyfit(x, y, 1)
                slope, intercept = coefs
            else:
                slope, intercept = 0.0, y[-1] if len(y) else 0.0

            last_val = y[-1] if len(y) else 0.0
            std_dev = float(np.std(y)) if len(y) > 1 else last_val * 0.05

            rows = []
            for i in range(1, horizon + 1):
                pred = intercept + slope * (len(y) - 1 + i)
                rows.append({
                    'fecha': pd.Timestamp(hoy + timedelta(days=i)),
                    'cu_predicho': round(float(pred), 4),
                    'limite_inferior': round(float(pred - 1.96 * std_dev), 4),
                    'limite_superior': round(float(pred + 1.96 * std_dev), 4),
                    'confianza': round(max(0.3, 0.85 - 0.01 * i), 2),
                    'modelo': 'naive_trend_30d',
                })

            return pd.DataFrame(rows)

        except Exception as exc:
            logger.error("%s Error generando forecast naive: %s", _LOG, exc)
            return pd.DataFrame(columns=[
                'fecha', 'cu_predicho', 'limite_inferior',
                'limite_superior', 'confianza', 'modelo',
            ])

    def get_cu_components_breakdown(self, fecha: date) -> Optional[dict]:
        """
        Desglose porcentual de cada componente del CU para una fecha.
        Útil para gráfico de torta del dashboard.
        """
        fecha = _ensure_date(fecha)

        # Intentar desde cu_daily primero
        query = """
            SELECT componente_g, componente_t, componente_d,
                   componente_c, componente_p, componente_r, cu_total
            FROM cu_daily
            WHERE fecha = %s
        """

        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, (fecha,))
                row = cur.fetchone()
                cur.close()
                conn.commit()

            if row:
                return self._build_breakdown(
                    comp_g=row[0], comp_t=row[1], comp_d=row[2],
                    comp_c=row[3], comp_p=row[4], comp_r=row[5],
                    cu_total=row[6], fecha=fecha
                )

            # Fallback: calcular on-the-fly
            cu = self.calculate_cu_for_date(fecha)
            if cu is None:
                return None
            return self._build_breakdown(
                comp_g=cu['componente_g'], comp_t=cu['componente_t'],
                comp_d=cu['componente_d'], comp_c=cu['componente_c'],
                comp_p=cu['componente_p'], comp_r=cu['componente_r'],
                cu_total=cu['cu_total'], fecha=fecha
            )

        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo breakdown para {fecha}: {e}")
            return None

    # ════════════════════════════════════════════════════════════
    # MÉTODOS INTERNOS — Helpers
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        """Convierte una fila de cu_daily a dict."""
        keys = [
            'fecha', 'componente_g', 'componente_t', 'componente_d',
            'componente_c', 'componente_p', 'componente_r', 'cu_total',
            'demanda_gwh', 'generacion_gwh', 'perdidas_gwh', 'perdidas_pct',
            'fuentes_ok', 'confianza', 'notas'
        ]
        d = dict(zip(keys, row))
        # Serializar fecha
        if d.get('fecha'):
            d['fecha'] = d['fecha'].isoformat() if hasattr(d['fecha'], 'isoformat') else str(d['fecha'])
        # Convertir Decimal a float
        for k in ['componente_g', 'componente_t', 'componente_d', 'componente_c',
                   'componente_p', 'componente_r', 'cu_total', 'demanda_gwh',
                   'generacion_gwh', 'perdidas_gwh', 'perdidas_pct']:
            if d.get(k) is not None:
                d[k] = float(d[k])
        return d

    @staticmethod
    def _build_breakdown(comp_g, comp_t, comp_d, comp_c, comp_p, comp_r,
                         cu_total, fecha) -> dict:
        """Construye desglose porcentual de componentes."""
        total = float(cu_total) if cu_total else 0
        if total <= 0:
            return {'fecha': str(fecha), 'componentes': [], 'cu_total': 0}

        def pct(val):
            return round(float(val) / total * 100, 2) if val is not None else 0

        componentes = [
            {'nombre': 'Generación', 'codigo': 'G',
             'valor_cop_kwh': float(comp_g) if comp_g else 0,
             'porcentaje': pct(comp_g)},
            {'nombre': 'Transmisión', 'codigo': 'T',
             'valor_cop_kwh': float(comp_t) if comp_t else 0,
             'porcentaje': pct(comp_t)},
            {'nombre': 'Distribución', 'codigo': 'D',
             'valor_cop_kwh': float(comp_d) if comp_d else 0,
             'porcentaje': pct(comp_d)},
            {'nombre': 'Comercialización', 'codigo': 'C',
             'valor_cop_kwh': float(comp_c) if comp_c else 0,
             'porcentaje': pct(comp_c)},
            {'nombre': 'Pérdidas', 'codigo': 'P',
             'valor_cop_kwh': float(comp_p) if comp_p else 0,
             'porcentaje': pct(comp_p)},
            {'nombre': 'Restricciones', 'codigo': 'R',
             'valor_cop_kwh': float(comp_r) if comp_r else 0,
             'porcentaje': pct(comp_r)},
        ]

        return {
            'fecha': fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha),
            'cu_total': round(total, 4),
            'componentes': componentes,
        }
