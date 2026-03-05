"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║            LOSSES NT SERVICE — Pérdidas No Técnicas del SIN                  ║
║                                                                               ║
║  Estima pérdidas técnicas (STN + SDL) y NO técnicas del Sistema              ║
║  Interconectado Nacional de Colombia.                                         ║
║                                                                               ║
║  Método RESIDUO_HIBRIDO_CREG (v2 — HOTFIX 4.0):                             ║
║                                                                               ║
║  Métricas de entrada:                                                         ║
║  • Gene     = Generación total inyectada al SIN (GWh/día, tabla metrics)     ║
║  • DemaReal = Demanda real medida en frontera STN/SDL (GWh/día, metrics)     ║
║  • DemaReal mide energía que SALE del STN hacia distribución (SDL).          ║
║    NO mide consumo final: pérdidas de distribución y NT ocurren después.     ║
║                                                                               ║
║  Fórmulas:                                                                    ║
║  P_STN = (Gene - DemaReal) / Gene × 100  [medido, ≈1.4%]                    ║
║  P_dist = FACTOR_PERDIDAS_DISTRIBUCION × 100  [CREG, 8.5%]                  ║
║  P_tec = P_STN + P_dist  [total técnicas, ≈9.9%]                            ║
║                                                                               ║
║  DemaUsuario_est = DemaReal × (1 - FACTOR_PERDIDAS_SDL_TOTAL)                ║
║  P_total = (Gene - DemaUsuario_est) / Gene × 100  [estimado, ≈13%]          ║
║  P_NT = P_total - P_tec  [residuo, ≈3%]                                     ║
║                                                                               ║
║  FACTOR_PERDIDAS_SDL_TOTAL (12%) = pérdidas totales en SDL (tech + NT)       ║
║  según promedio nacional CREG/UPME. Incluye P_dist(8.5%) + P_NT_SDL(3.5%).  ║
║                                                                               ║
║  Nota: XM solo reporta datos a nivel STN. Las pérdidas de distribución       ║
║  y no técnicas ocurren en el SDL (operadores regionales: Enel-Codensa,       ║
║  EPM, Electricaribe, etc.) y no son medidas directamente por XM.             ║
║  El factor 12% es una estimación regulatoria CREG promedio nacional.         ║
║                                                                               ║
║  Anomalías: P_STN < -1% o > 5%, o P_NT < 0% o > 10%                        ║
║                                                                               ║
║  Confianza:                                                                   ║
║  - Alta  (0.85): todos los datos OK, P_NT entre 0-8%                        ║
║  - Media (0.60): P_NT en rango amplio o fuente faltante menor               ║
║  - Baja  (0.40): dato faltante o anomalía detectada                         ║
║                                                                               ║
║  Autor: Arquitectura Dashboard MME                                            ║
║  Fecha: 4 de marzo de 2026                                                   ║
║  Fase:  FASE 4 — HOTFIX 4.0 (DemaCome→DemaReal + método híbrido CREG)       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any

import pandas as pd

from core.config import get_settings
from core.exceptions import DatabaseError
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Constantes internas
# ─────────────────────────────────────────────────────────────
_PREFIX = "[LOSSES_NT_SERVICE]"

# Umbrales de anomalía
_NT_MIN_THRESHOLD = 0.0    # P_NT < 0% → anomalía (fórmula incoherente)
_NT_MAX_THRESHOLD = 10.0   # P_NT > 10% → anomalía (excesivo para promedio nacional)
_STN_MIN_THRESHOLD = -1.0  # P_STN < -1% → anomalía (DemaReal >> Gene)
_STN_MAX_THRESHOLD = 5.0   # P_STN > 5% → anomalía (pérdidas STN excesivas)

# Umbrales de confianza
_CONF_ALTA = "alta"
_CONF_MEDIA = "media"
_CONF_BAJA = "baja"


class LossesNTService:
    """
    Estima pérdidas técnicas y NO técnicas del SIN colombiano.

    Método RESIDUO_HIBRIDO_CREG (v2):
        P_STN = (Gene - DemaReal) / Gene × 100              [medido]
        P_dist = FACTOR_PERDIDAS_DISTRIBUCION × 100          [CREG 8.5%]
        P_tec = P_STN + P_dist                               [~9.9%]

        DemaUsuario_est = DemaReal × (1 − SDL_TOTAL_FACTOR)
        P_total = (Gene − DemaUsuario_est) / Gene × 100     [~13%]
        P_NT = P_total − P_tec                               [~3%]

    SDL_TOTAL_FACTOR (12%) = pérdidas totales en SDL (tech + NT)
    por CREG promedio nacional.

    Anomalías:
    - P_STN < −1% o P_STN > 5%  → anomalía transmisión
    - P_NT  < 0%  o P_NT  > 10% → anomalía fórmula

    Confianza:
    - Alta  (0.85): datos completos, P_NT entre 0-8%
    - Media (0.60): P_NT en rango amplio o fuente menor faltante
    - Baja  (0.40): dato faltante o anomalía detectada
    """

    def __init__(self):
        self._db = PostgreSQLConnectionManager()
        self._settings = get_settings()
        self._factor_dist = self._settings.FACTOR_PERDIDAS_DISTRIBUCION
        self._factor_sdl_total = self._settings.FACTOR_PERDIDAS_SDL_TOTAL
        logger.info(
            "%s Inicializado (factor_dist=%.3f, factor_sdl_total=%.3f)",
            _PREFIX,
            self._factor_dist,
            self._factor_sdl_total,
        )

    # ================================================================
    # PRIVATE: Obtener datos diarios
    # ================================================================

    def _get_daily_data(self, fecha: date) -> Optional[Dict[str, Any]]:
        """
        Obtiene Gene, DemaReal y P_STN para una fecha.

        Fuentes:
        - Gene, DemaReal, PrecBolsNaci: tabla metrics (entidad='Sistema')
        - PerdidasEnerReg: tabla loss_metrics (metric_code='PerdidasEnerReg')

        Returns:
            dict con claves: gene_gwh, dema_real_gwh, precio_bolsa, p_stn_gwh
            None si Gene o DemaReal no disponibles.
        """
        fecha_str = fecha.isoformat()
        try:
            with self._db.get_connection() as conn:
                cur = conn.cursor()

                # ── Metrics: Gene, DemaReal, PrecBolsNaci ────────────
                cur.execute(
                    """
                    SELECT
                        MAX(CASE WHEN metrica = 'Gene'         THEN valor_gwh END),
                        MAX(CASE WHEN metrica = 'DemaReal'     THEN valor_gwh END),
                        MAX(CASE WHEN metrica = 'PrecBolsNaci' THEN valor_gwh END)
                    FROM metrics
                    WHERE fecha::date = %s
                      AND entidad = 'Sistema'
                      AND metrica IN ('Gene', 'DemaReal', 'PrecBolsNaci')
                    """,
                    (fecha_str,),
                )
                row = cur.fetchone()
                if not row or row[0] is None or row[1] is None:
                    return None

                gene_gwh = float(row[0])
                dema_real_gwh = float(row[1])
                precio_bolsa = float(row[2]) if row[2] is not None else None

                if gene_gwh <= 0:
                    return None

                # ── loss_metrics: PerdidasEnerReg (STN) ──────────────
                cur.execute(
                    """
                    SELECT valor
                    FROM loss_metrics
                    WHERE metric_code = 'PerdidasEnerReg'
                      AND fecha = %s
                    LIMIT 1
                    """,
                    (fecha_str,),
                )
                lm_row = cur.fetchone()
                p_stn_gwh = float(lm_row[0]) if lm_row and lm_row[0] is not None else None

                conn.commit()

            return {
                "gene_gwh": gene_gwh,
                "dema_real_gwh": dema_real_gwh,
                "precio_bolsa": precio_bolsa,
                "p_stn_gwh": p_stn_gwh,
            }

        except Exception as exc:
            logger.error("%s Error obteniendo datos para %s: %s", _PREFIX, fecha, exc)
            return None

    # ================================================================
    # PUBLIC: Calcular pérdidas para una fecha
    # ================================================================

    def calculate_losses_for_date(self, fecha: date) -> Optional[Dict[str, Any]]:
        """
        Calcula el desglose completo de pérdidas para 1 fecha.
        Método RESIDUO_HIBRIDO_CREG: usa DemaReal + factor SDL total.

        Retorna dict con todos los campos de losses_detailed o None.
        """
        data = self._get_daily_data(fecha)
        if data is None:
            return None

        gene = data["gene_gwh"]
        dema_real = data["dema_real_gwh"]
        precio = data["precio_bolsa"]
        p_stn_gwh = data["p_stn_gwh"]

        fuentes_ok = 2  # Gene + DemaReal siempre presentes aquí
        notas_parts = ["metodo=RESIDUO_HIBRIDO_CREG", "demanda=DemaReal"]

        # ── P_STN medido (%) ────────────────────────────────────
        # Pérdidas STN = (Gene - DemaReal) / Gene
        p_stn_measured_pct = (gene - dema_real) / gene * 100.0

        # P_STN desde loss_metrics (para cross-validation)
        if p_stn_gwh is not None and gene > 0:
            p_stn_xm_pct = (p_stn_gwh / gene) * 100.0
            fuentes_ok += 1
            # Usar el medido (Gene-DemaReal), el XM es solo referencia
            p_stn_pct = p_stn_measured_pct
        else:
            p_stn_pct = p_stn_measured_pct
            notas_parts.append("sin_perdidas_stn_xm")

        if precio is not None:
            fuentes_ok += 1
        else:
            notas_parts.append("sin_precio_bolsa")

        # ── Cálculos RESIDUO_HIBRIDO_CREG ───────────────────────
        # Technical losses = STN measured + Distribution CREG factor
        factor_dist_pct = self._factor_dist * 100.0  # 0.085 → 8.5%
        p_tec_pct = p_stn_pct + factor_dist_pct

        # Technical losses in GWh
        perdidas_tec_gwh = gene * p_tec_pct / 100.0

        # Estimated user-level demand (after ALL SDL losses: tech + NT)
        # DemaReal measures at STN/SDL boundary; distribution + NT losses
        # happen downstream. SDL_total = 12% is CREG national average.
        dema_usuario_est = dema_real * (1.0 - self._factor_sdl_total)

        # Total losses = Generation - estimated end-user demand
        perdidas_total_gwh = gene - dema_usuario_est
        p_total_pct = (perdidas_total_gwh / gene) * 100.0

        # Non-technical = total - technical (residual)
        p_nt_pct = p_total_pct - p_tec_pct
        perdidas_nt_gwh = perdidas_total_gwh - perdidas_tec_gwh
        factor_dist_pct = self._factor_dist * 100.0  # 0.085 → 8.5%
        p_tec_pct = p_stn_pct + factor_dist_pct

        # Technical losses in GWh
        perdidas_tec_gwh = gene * p_tec_pct / 100.0

        # Non-technical = residual
        p_nt_pct = p_total_pct - p_tec_pct
        perdidas_nt_gwh = perdidas_total_gwh - perdidas_tec_gwh

        # ── Anomalía ────────────────────────────────────────────
        anomalia = False
        # STN anomaly: unusual transmission loss level
        if p_stn_pct < _STN_MIN_THRESHOLD:
            anomalia = True
            notas_parts.append(f"stn_negativo={p_stn_pct:.2f}%")
        if p_stn_pct > _STN_MAX_THRESHOLD:
            anomalia = True
            notas_parts.append(f"stn_excesivo={p_stn_pct:.2f}%")
        # NT anomaly: formula-level issue
        if p_nt_pct < _NT_MIN_THRESHOLD:
            anomalia = True
            notas_parts.append(f"pnt_negativo={p_nt_pct:.2f}%")
        if p_nt_pct > _NT_MAX_THRESHOLD:
            anomalia = True
            notas_parts.append(f"pnt_excesivo={p_nt_pct:.2f}%")

        # ── Confianza ───────────────────────────────────────────
        if fuentes_ok >= 3 and 0.0 <= p_nt_pct <= 8.0 and not anomalia:
            confianza = _CONF_ALTA
        elif fuentes_ok >= 3 and not anomalia:
            confianza = _CONF_MEDIA
        else:
            confianza = _CONF_BAJA

        # ── Costos (millones COP) ───────────────────────────────
        # GWh × COP/kWh × 10⁶ kWh/GWh / 10⁶ = GWh × COP/kWh
        # Resultado en Millones COP: GWh * precio * 1000 / 1e6 = GWh * precio / 1000
        # Más preciso: GWh × 1e6 kWh × COP/kWh / 1e6 = GWh × COP/kWh
        if precio is not None:
            costo_total_mcop = abs(perdidas_total_gwh) * precio  # Millones COP
            costo_tec_mcop = perdidas_tec_gwh * precio
            costo_nt_mcop = abs(perdidas_nt_gwh) * precio if p_nt_pct > 0 else 0.0
        else:
            costo_total_mcop = None
            costo_tec_mcop = None
            costo_nt_mcop = None

        return {
            "fecha": fecha,
            "generacion_gwh": round(gene, 6),
            "demanda_gwh": round(dema_real, 6),
            "perdidas_total_gwh": round(perdidas_total_gwh, 6),
            "perdidas_tecnicas_gwh": round(perdidas_tec_gwh, 6),
            "perdidas_no_tecnicas_gwh": round(perdidas_nt_gwh, 6),
            "perdidas_total_pct": round(p_total_pct, 4),
            "perdidas_tecnicas_pct": round(p_tec_pct, 4),
            "perdidas_no_tecnicas_pct": round(p_nt_pct, 4),
            "perdidas_stn_pct": round(p_stn_pct, 4),
            "precio_bolsa_cop_kwh": round(precio, 4) if precio else None,
            "costo_perdidas_total_mcop": round(costo_total_mcop, 4) if costo_total_mcop is not None else None,
            "costo_perdidas_tecnicas_mcop": round(costo_tec_mcop, 4) if costo_tec_mcop is not None else None,
            "costo_no_tecnicas_mcop": round(costo_nt_mcop, 4) if costo_nt_mcop is not None else None,
            "fuentes_ok": fuentes_ok,
            "confianza": confianza,
            "anomalia_detectada": anomalia,
            "metodo_estimacion": "RESIDUO_HIBRIDO_CREG",
            "notas": "; ".join(notas_parts) if notas_parts else None,
        }

    # ================================================================
    # PUBLIC: Guardar en losses_detailed
    # ================================================================

    def save_losses_for_date(self, fecha: date) -> bool:
        """
        Calcula y persiste en losses_detailed.
        ON CONFLICT DO NOTHING (no sobreescribe existentes).

        Returns:
            True si se insertó o ya existía, False si error.
        """
        result = self.calculate_losses_for_date(fecha)
        if result is None:
            return False

        try:
            with self._db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO losses_detailed (
                        fecha, generacion_gwh, demanda_gwh,
                        perdidas_total_gwh, perdidas_tecnicas_gwh, perdidas_no_tecnicas_gwh,
                        perdidas_total_pct, perdidas_tecnicas_pct, perdidas_no_tecnicas_pct,
                        perdidas_stn_pct,
                        precio_bolsa_cop_kwh,
                        costo_perdidas_total_mcop, costo_perdidas_tecnicas_mcop, costo_no_tecnicas_mcop,
                        fuentes_ok, confianza, anomalia_detectada, metodo_estimacion, notas
                    ) VALUES (
                        %(fecha)s, %(generacion_gwh)s, %(demanda_gwh)s,
                        %(perdidas_total_gwh)s, %(perdidas_tecnicas_gwh)s, %(perdidas_no_tecnicas_gwh)s,
                        %(perdidas_total_pct)s, %(perdidas_tecnicas_pct)s, %(perdidas_no_tecnicas_pct)s,
                        %(perdidas_stn_pct)s,
                        %(precio_bolsa_cop_kwh)s,
                        %(costo_perdidas_total_mcop)s, %(costo_perdidas_tecnicas_mcop)s, %(costo_no_tecnicas_mcop)s,
                        %(fuentes_ok)s, %(confianza)s, %(anomalia_detectada)s, %(metodo_estimacion)s, %(notas)s
                    )
                    ON CONFLICT (fecha) DO NOTHING
                    """,
                    result,
                )
                conn.commit()
            return True

        except Exception as exc:
            logger.error("%s Error guardando %s: %s", _PREFIX, fecha, exc)
            return False

    # ================================================================
    # PUBLIC: Backfill masivo
    # ================================================================

    def backfill_losses(
        self, fecha_inicio: date, fecha_fin: date
    ) -> Dict[str, Any]:
        """
        Cálculo por lotes para rango de fechas.

        Returns:
            dict con: insertados, errores, anomalias, total_dias
        """
        logger.info(
            "%s Backfill %s → %s", _PREFIX, fecha_inicio, fecha_fin
        )
        insertados = 0
        errores = 0
        anomalias = 0
        total = 0

        current = fecha_inicio
        while current <= fecha_fin:
            total += 1
            try:
                result = self.calculate_losses_for_date(current)
                if result is None:
                    errores += 1
                    current += timedelta(days=1)
                    continue

                if result["anomalia_detectada"]:
                    anomalias += 1

                if self._save_result(result):
                    insertados += 1
                else:
                    errores += 1

            except Exception as exc:
                logger.error("%s Error en %s: %s", _PREFIX, current, exc)
                errores += 1

            if total % 200 == 0:
                logger.info(
                    "%s Progreso: %d/%d insertados (anomalias=%d, errores=%d)",
                    _PREFIX, insertados, total, anomalias, errores,
                )

            current += timedelta(days=1)

        resumen = {
            "total_dias": total,
            "insertados": insertados,
            "errores": errores,
            "anomalias": anomalias,
        }
        logger.info("%s Backfill completado: %s", _PREFIX, resumen)
        return resumen

    def _save_result(self, result: Dict[str, Any]) -> bool:
        """Guarda un resultado pre-calculado. Interno para backfill."""
        try:
            with self._db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO losses_detailed (
                        fecha, generacion_gwh, demanda_gwh,
                        perdidas_total_gwh, perdidas_tecnicas_gwh, perdidas_no_tecnicas_gwh,
                        perdidas_total_pct, perdidas_tecnicas_pct, perdidas_no_tecnicas_pct,
                        perdidas_stn_pct,
                        precio_bolsa_cop_kwh,
                        costo_perdidas_total_mcop, costo_perdidas_tecnicas_mcop, costo_no_tecnicas_mcop,
                        fuentes_ok, confianza, anomalia_detectada, metodo_estimacion, notas
                    ) VALUES (
                        %(fecha)s, %(generacion_gwh)s, %(demanda_gwh)s,
                        %(perdidas_total_gwh)s, %(perdidas_tecnicas_gwh)s, %(perdidas_no_tecnicas_gwh)s,
                        %(perdidas_total_pct)s, %(perdidas_tecnicas_pct)s, %(perdidas_no_tecnicas_pct)s,
                        %(perdidas_stn_pct)s,
                        %(precio_bolsa_cop_kwh)s,
                        %(costo_perdidas_total_mcop)s, %(costo_perdidas_tecnicas_mcop)s, %(costo_no_tecnicas_mcop)s,
                        %(fuentes_ok)s, %(confianza)s, %(anomalia_detectada)s, %(metodo_estimacion)s, %(notas)s
                    )
                    ON CONFLICT (fecha) DO NOTHING
                    """,
                    result,
                )
                inserted = cur.rowcount > 0
                conn.commit()
            return inserted
        except Exception as exc:
            logger.error("%s Error _save_result: %s", _PREFIX, exc)
            return False

    # ================================================================
    # PUBLIC: Lectura — Último registro
    # ================================================================

    def get_losses_current(self) -> Optional[Dict[str, Any]]:
        """
        Retorna el desglose más reciente de losses_detailed.
        Fallback: calcula on-the-fly si tabla vacía.
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT fecha, generacion_gwh, demanda_gwh,
                           perdidas_total_gwh, perdidas_tecnicas_gwh, perdidas_no_tecnicas_gwh,
                           perdidas_total_pct, perdidas_tecnicas_pct, perdidas_no_tecnicas_pct,
                           perdidas_stn_pct,
                           precio_bolsa_cop_kwh,
                           costo_perdidas_total_mcop, costo_perdidas_tecnicas_mcop, costo_no_tecnicas_mcop,
                           fuentes_ok, confianza, anomalia_detectada, metodo_estimacion, notas
                    FROM losses_detailed
                    ORDER BY fecha DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                conn.commit()

            if row:
                return self._row_to_dict(row)

            # Fallback: calcular on-the-fly
            logger.warning("%s Tabla vacía, calculando on-the-fly", _PREFIX)
            return self.calculate_losses_for_date(date.today() - timedelta(days=2))

        except Exception as exc:
            logger.error("%s Error get_losses_current: %s", _PREFIX, exc)
            return None

    # ================================================================
    # PUBLIC: Serie histórica
    # ================================================================

    def get_losses_historico(
        self, fecha_inicio: date, fecha_fin: date
    ) -> pd.DataFrame:
        """
        Serie histórica desde losses_detailed.

        Returns:
            DataFrame con columnas: fecha, perdidas_totales_pct,
            perdidas_tecnicas_pct, perdidas_nt_pct, confianza, etc.
        """
        try:
            with self._db.get_connection() as conn:
                query = """
                    SELECT fecha,
                           perdidas_total_pct,
                           perdidas_tecnicas_pct,
                           perdidas_no_tecnicas_pct as perdidas_nt_pct,
                           perdidas_stn_pct,
                           generacion_gwh,
                           demanda_gwh,
                           perdidas_total_gwh,
                           perdidas_tecnicas_gwh,
                           perdidas_no_tecnicas_gwh as perdidas_nt_gwh,
                           costo_no_tecnicas_mcop as costo_nt_mcop,
                           precio_bolsa_cop_kwh,
                           confianza,
                           anomalia_detectada,
                           fuentes_ok
                    FROM losses_detailed
                    WHERE fecha BETWEEN %s AND %s
                    ORDER BY fecha
                """
                df = pd.read_sql(query, conn, params=[fecha_inicio, fecha_fin])
                conn.commit()

            if df.empty:
                logger.warning(
                    "%s Sin datos en losses_detailed para %s → %s",
                    _PREFIX, fecha_inicio, fecha_fin,
                )
            return df

        except Exception as exc:
            logger.error("%s Error get_losses_historico: %s", _PREFIX, exc)
            return pd.DataFrame()

    # ================================================================
    # PUBLIC: Estadísticas agregadas para dashboard
    # ================================================================

    def get_losses_statistics(self) -> Dict[str, Any]:
        """
        Estadísticas agregadas para el tablero:
        - pct_promedio_total, pct_promedio_tecnicas, pct_promedio_nt
        - tendencia_nt: 'MEJORANDO', 'ESTABLE', 'EMPEORANDO'
        - dias_anomalia: cantidad de días con P_NT fuera de rango
        - costo_nt_cop_historico: suma COP estimada PNT toda la serie
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.cursor()

                # ── Promedios globales ───────────────────────────
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_dias,
                        ROUND(AVG(perdidas_total_pct)::numeric, 4) as avg_total,
                        ROUND(AVG(perdidas_tecnicas_pct)::numeric, 4) as avg_tec,
                        ROUND(AVG(perdidas_no_tecnicas_pct)::numeric, 4) as avg_nt,
                        SUM(CASE WHEN anomalia_detectada THEN 1 ELSE 0 END) as dias_anomalia,
                        ROUND(SUM(COALESCE(costo_no_tecnicas_mcop, 0))::numeric, 2) as costo_nt_total_mcop
                    FROM losses_detailed
                    """
                )
                row = cur.fetchone()
                if not row or row[0] == 0:
                    conn.commit()
                    return {"error": "Sin datos en losses_detailed"}

                total_dias = int(row[0])
                avg_total = float(row[1]) if row[1] else 0.0
                avg_tec = float(row[2]) if row[2] else 0.0
                avg_nt = float(row[3]) if row[3] else 0.0
                dias_anomalia = int(row[4])
                costo_nt_total = float(row[5]) if row[5] else 0.0

                # ── Promedios últimos 365 días ───────────────────
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as dias,
                        ROUND(AVG(perdidas_no_tecnicas_pct)::numeric, 4) as avg_nt_12m,
                        ROUND(SUM(COALESCE(costo_no_tecnicas_mcop, 0))::numeric, 2) as costo_nt_12m
                    FROM losses_detailed
                    WHERE fecha >= CURRENT_DATE - INTERVAL '365 days'
                    """
                )
                row12 = cur.fetchone()
                avg_nt_12m = float(row12[1]) if row12 and row12[1] else avg_nt
                costo_nt_12m = float(row12[2]) if row12 and row12[2] else 0.0

                # ── Tendencia: comparar promedio NT últimos 6 meses
                #    vs 6 meses anteriores ────────────────────────
                cur.execute(
                    """
                    SELECT
                        ROUND(AVG(CASE WHEN fecha >= CURRENT_DATE - INTERVAL '180 days'
                              THEN perdidas_no_tecnicas_pct END)::numeric, 4) as avg_nt_6m,
                        ROUND(AVG(CASE WHEN fecha BETWEEN CURRENT_DATE - INTERVAL '360 days'
                                                     AND CURRENT_DATE - INTERVAL '181 days'
                              THEN perdidas_no_tecnicas_pct END)::numeric, 4) as avg_nt_6m_prev
                    FROM losses_detailed
                    """
                )
                tend_row = cur.fetchone()
                if tend_row and tend_row[0] is not None and tend_row[1] is not None:
                    diff = float(tend_row[0]) - float(tend_row[1])
                    if diff < -0.5:
                        tendencia = "MEJORANDO"
                    elif diff > 0.5:
                        tendencia = "EMPEORANDO"
                    else:
                        tendencia = "ESTABLE"
                else:
                    tendencia = "ESTABLE"

                # ── Promedios últimos 30 días ────────────────────
                cur.execute(
                    """
                    SELECT
                        ROUND(AVG(perdidas_no_tecnicas_pct)::numeric, 4) as avg_nt_30d,
                        ROUND(AVG(perdidas_total_pct)::numeric, 4) as avg_total_30d,
                        SUM(CASE WHEN anomalia_detectada THEN 1 ELSE 0 END) as anomalias_30d
                    FROM losses_detailed
                    WHERE fecha >= CURRENT_DATE - INTERVAL '30 days'
                    """
                )
                row30 = cur.fetchone()
                avg_nt_30d = float(row30[0]) if row30 and row30[0] else avg_nt
                avg_total_30d = float(row30[1]) if row30 and row30[1] else avg_total
                anomalias_30d = int(row30[2]) if row30 and row30[2] else 0

                conn.commit()

            return {
                "total_dias": total_dias,
                "pct_promedio_total": avg_total,
                "pct_promedio_tecnicas": avg_tec,
                "pct_promedio_nt": avg_nt,
                "pct_promedio_nt_30d": avg_nt_30d,
                "pct_promedio_total_30d": avg_total_30d,
                "anomalias_30d": anomalias_30d,
                "pct_promedio_nt_12m": avg_nt_12m,
                "tendencia_nt": tendencia,
                "dias_anomalia": dias_anomalia,
                "costo_nt_historico_mcop": costo_nt_total,
                "costo_nt_12m_mcop": costo_nt_12m,
            }

        except Exception as exc:
            logger.error("%s Error get_losses_statistics: %s", _PREFIX, exc)
            return {"error": str(exc)}

    # ================================================================
    # HELPERS
    # ================================================================

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        """Convierte una fila de cursor a dict."""
        keys = [
            "fecha", "generacion_gwh", "demanda_gwh",
            "perdidas_total_gwh", "perdidas_tecnicas_gwh", "perdidas_no_tecnicas_gwh",
            "perdidas_total_pct", "perdidas_tecnicas_pct", "perdidas_no_tecnicas_pct",
            "perdidas_stn_pct",
            "precio_bolsa_cop_kwh",
            "costo_perdidas_total_mcop", "costo_perdidas_tecnicas_mcop", "costo_no_tecnicas_mcop",
            "fuentes_ok", "confianza", "anomalia_detectada", "metodo_estimacion", "notas",
        ]
        d = {}
        for i, k in enumerate(keys):
            val = row[i]
            if hasattr(val, "__float__"):
                d[k] = float(val)
            else:
                d[k] = val
        return d
