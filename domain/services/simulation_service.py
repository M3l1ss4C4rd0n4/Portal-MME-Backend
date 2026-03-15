"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║               SIMULATION SERVICE — Motor de Simulación CREG                   ║
║                                                                               ║
║  Permite simular escenarios regulatorios modificando parámetros CREG         ║
║  y evaluar su impacto en el CU y en la factura de hogares estrato 3.         ║
║                                                                               ║
║  Parámetros simulables:                                                       ║
║  - precio_bolsa_factor:    multiplicador sobre PrecBolsNaci                   ║
║  - factor_perdidas:        factor distribución (SDL, CREG default 8.5%)       ║
║  - cargo_restricciones_kw: COP/kWh absoluto (None = usar valor actual)        ║
║  - tasa_transmision:       multiplicador sobre componente T                   ║
║  - tasa_comercializacion:  multiplicador sobre componente C                   ║
║  - demanda_factor:         multiplicador sobre demanda                        ║
║                                                                               ║
║  FASE 6 — Motor de Simulación CREG                                           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
from typing import Optional

from core.exceptions import DatabaseError
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)

_LOG = "[SIMULATION_SERVICE]"

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTES — Valores reales de producción (2026-03-03)
# ═══════════════════════════════════════════════════════════════════════

CONSUMO_ESTRATO3_KWH = 173          # kWh/mes hogar típico
SUBSIDIO_BASICO_KWH = 130           # kWh subsidiados estrato 3
SUBSIDIO_PCT = 0.50                  # 50% sobre consumo básico
CU_BASE_DEFAULT = 192.6981           # COP/kWh — producción
PRECIO_BOLSA_BASE = 115.1896         # COP/kWh — producción

DESGLOSE_BASE = {
    'g': 0.5965,   # generación  (ajustado para que sum=1.0000)
    'd': 0.1825,   # distribución
    'c': 0.0626,   # comercialización
    't': 0.0443,   # transmisión
    'p': 0.1026,   # pérdidas
    'r': 0.0115,   # restricciones
}  # sum = 1.0000

# Rangos válidos para parámetros simulables
PARAM_RANGES = {
    'precio_bolsa_factor':    (0.5, 3.0),
    'factor_perdidas':        (0.05, 0.20),
    'cargo_restricciones_kw': (0.0, 50.0),
    'tasa_transmision':       (0.5, 1.5),
    'tasa_comercializacion':  (0.5, 1.5),
    'demanda_factor':         (0.7, 1.3),
}


class SimulationService:
    """
    Motor de Simulación paramétrica CREG.

    Calcula el impacto de cambios en parámetros regulatorios sobre:
    - Costo Unitario (CU) de energía eléctrica
    - Factura de un hogar estrato 3
    - Sensibilidad por parámetro individual

    Usa PostgreSQLConnectionManager para lectura de cu_daily actual
    y para persistir resultados en simulation_results.
    """

    def __init__(self):
        self._conn_mgr = PostgreSQLConnectionManager()
        logger.info(f"{_LOG} Inicializado — CU_base={CU_BASE_DEFAULT}, "
                     f"PrecBolsa_base={PRECIO_BOLSA_BASE}")

    # ════════════════════════════════════════════════════════════
    # MÉTODO PRINCIPAL
    # ════════════════════════════════════════════════════════════

    def simular_escenario(
        self,
        parametros: dict,
        horizonte_dias: int = 30,
        nombre: str = "Escenario personalizado",
        tipo: str = "PERSONALIZADO",
    ) -> dict:
        """
        Ejecuta una simulación paramétrica CREG completa.

        Args:
            parametros: Dict con los factores a modificar
            horizonte_dias: Días para la serie simulada (default 30)
            nombre: Nombre descriptivo del escenario
            tipo: Tipo de escenario (SEQUIA, REFORMA_TARIFA, INVERSION, PERSONALIZADO)

        Returns:
            Dict con cu_simulado, delta, impacto_estrato3, sensibilidad,
            serie_simulada, componentes y advertencias
        """
        try:
            # Obtener CU base dinámico (últimos 30 días reales)
            cu_base = self._get_cu_base_dinamico()
            if cu_base is None:
                cu_base = CU_BASE_DEFAULT
                logger.warning(f"{_LOG} Usando CU base hardcodeado: {cu_base}")

            # Calcular simulación
            resultado_componentes = self._calcular_cu_simulado(parametros, cu_base)
            cu_sim = resultado_componentes['cu_simulado']

            # Análisis complementario
            delta_cop = cu_sim - cu_base
            delta_pct = (delta_cop / cu_base * 100) if cu_base > 0 else 0.0
            impacto = self.calcular_impacto_estrato3(cu_sim, cu_base)
            sensibilidad = self._calcular_sensibilidad(parametros, cu_base)
            advertencias = self._generar_advertencias(parametros)

            # Serie de N días simulados
            serie = self._generar_serie_simulada(parametros, horizonte_dias)

            logger.info(
                f"{_LOG} Simulación '{nombre}' — CU base={cu_base:.2f}, "
                f"CU sim={cu_sim:.2f}, delta={delta_pct:+.1f}%"
            )

            return {
                'cu_simulado': cu_sim,
                'cu_baseline': cu_base,
                'delta_cop_kwh': round(delta_cop, 4),
                'delta_pct': round(delta_pct, 2),
                'componentes_simulados': resultado_componentes['componentes'],
                'componentes_baseline': {
                    k: round(cu_base * v, 4)
                    for k, v in DESGLOSE_BASE.items()
                },
                'impacto_estrato3': impacto,
                'serie_simulada': serie,
                'sensibilidad': sensibilidad,
                'parametros_usados': parametros,
                'tipo_escenario': tipo,
                'advertencias': advertencias,
                'nota_legal': (
                    'Simulación paramétrica. No representa datos '
                    'reales ni proyecciones oficiales del MME.'
                ),
            }
        except Exception as e:
            logger.error(f"{_LOG} Error en simulación: {e}")
            raise

    # ════════════════════════════════════════════════════════════
    # CÁLCULO CORE
    # ════════════════════════════════════════════════════════════

    def _calcular_cu_simulado(self, params: dict, cu_base: float) -> dict:
        """
        Aplica factores sobre el CU base descompuesto.

        El componente G se afecta ~85% por precio bolsa (el 15% restante
        son cargos fijos: ENFICC, cargo por confiabilidad).
        El factor pérdidas CREG afecta los componentes D y P.

        Returns:
            dict con cu_simulado y componentes simulados
        """
        # Componentes base en COP/kWh
        base = {k: cu_base * v for k, v in DESGLOSE_BASE.items()}

        # Generación: precio bolsa afecta ~85% del componente G
        delta_pb = params.get('precio_bolsa_factor', 1.0) - 1.0
        delta_dem = params.get('demanda_factor', 1.0) - 1.0
        comp_g_sim = base['g'] * (1 + delta_pb * 0.85 + delta_dem * 0.15)

        # Pérdidas: el factor CREG afecta el componente D y P
        delta_f = params.get('factor_perdidas', 0.085) - 0.085
        comp_d_sim = base['d'] * (1 + delta_f * 2.0)
        comp_p_sim = base['p'] * (1 + delta_f * 1.5)

        # Transmisión y Comercialización
        comp_t_sim = base['t'] * params.get('tasa_transmision', 1.0)
        comp_c_sim = base['c'] * params.get('tasa_comercializacion', 1.0)

        # Restricciones: reemplazar si se especifica valor absoluto
        if params.get('cargo_restricciones_kw') is not None:
            comp_r_sim = float(params['cargo_restricciones_kw'])
        else:
            comp_r_sim = base['r']

        cu_sim = (comp_g_sim + comp_d_sim + comp_c_sim +
                  comp_t_sim + comp_p_sim + comp_r_sim)

        return {
            'cu_simulado': round(cu_sim, 4),
            'componentes': {
                'g': round(comp_g_sim, 4),
                'd': round(comp_d_sim, 4),
                'c': round(comp_c_sim, 4),
                't': round(comp_t_sim, 4),
                'p': round(comp_p_sim, 4),
                'r': round(comp_r_sim, 4),
            },
        }

    # ════════════════════════════════════════════════════════════
    # IMPACTO ESTRATO 3
    # ════════════════════════════════════════════════════════════

    def calcular_impacto_estrato3(self, cu_sim: float, cu_base: float) -> dict:
        """
        Consumo: 173 kWh/mes hogar estrato 3 (CREG).
        Subsidio: 50% sobre primeros 130 kWh.
        """
        kwh_basico = SUBSIDIO_BASICO_KWH
        kwh_exceso = CONSUMO_ESTRATO3_KWH - kwh_basico  # 43 kWh

        factura_base = (
            kwh_basico * cu_base * (1 - SUBSIDIO_PCT)
            + kwh_exceso * cu_base
        )

        factura_sim = (
            kwh_basico * cu_sim * (1 - SUBSIDIO_PCT)
            + kwh_exceso * cu_sim
        )

        diff = factura_sim - factura_base
        diff_pct = (diff / factura_base * 100) if factura_base > 0 else 0.0

        return {
            'consumo_kwh': CONSUMO_ESTRATO3_KWH,
            'factura_base_cop': round(factura_base, 0),
            'factura_sim_cop': round(factura_sim, 0),
            'diferencia_cop_mes': round(diff, 0),
            'diferencia_pct': round(diff_pct, 2),
            'nota': (
                'Subsidio 50% aplicado sobre 130 kWh básicos. '
                'Estrato 3 no paga contribución.'
            ),
        }

    # ════════════════════════════════════════════════════════════
    # SENSIBILIDAD
    # ════════════════════════════════════════════════════════════

    # Valores de referencia (baseline) para cada parámetro simulable
    _PARAM_DEFAULTS = {
        'precio_bolsa_factor': 1.0,
        'factor_perdidas': 0.085,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
        'cargo_restricciones_kw': 0.0,
        'demanda_factor': 1.0,
    }

    def _calcular_sensibilidad(self, params: dict, cu_base: float) -> dict:
        """
        Para cada parámetro REALMENTE modificado (distinto de su baseline),
        calcula su contribución individual al delta total del CU.
        Retorna ranking ordenado de mayor a menor impacto.
        """
        delta_total = abs(
            self._calcular_cu_simulado(params, cu_base)['cu_simulado'] - cu_base
        )
        if delta_total < 0.01:
            return {}

        sensibilidad = {}
        for param in [
            'precio_bolsa_factor', 'factor_perdidas',
            'tasa_transmision', 'tasa_comercializacion',
            'cargo_restricciones_kw', 'demanda_factor',
        ]:
            if param not in params:
                continue
            # Omitir parámetros en su valor baseline (no modificados)
            default_val = self._PARAM_DEFAULTS.get(param, 0.0)
            if abs((params[param] or 0.0) - default_val) < 1e-6:
                continue
            # Simular solo este parámetro, el resto en baseline
            params_solo = {param: params[param]}
            cu_solo = self._calcular_cu_simulado(params_solo, cu_base)['cu_simulado']
            delta_solo = abs(cu_solo - cu_base)
            sensibilidad[param] = {
                'delta_cop_kwh': round(cu_solo - cu_base, 4),
                'contribucion_pct': round(
                    delta_solo / delta_total * 100, 1
                ),
            }

        # Ordenar por contribución descendente
        return dict(sorted(
            sensibilidad.items(),
            key=lambda x: abs(x[1]['contribucion_pct']),
            reverse=True,
        ))

    # ════════════════════════════════════════════════════════════
    # ADVERTENCIAS
    # ════════════════════════════════════════════════════════════

    def _generar_advertencias(self, params: dict) -> list:
        """Genera advertencias contextuales según los parámetros."""
        advertencias = []
        pb = params.get('precio_bolsa_factor', 1.0)
        if pb > 2.0:
            advertencias.append(
                f'⚠️ Precio de bolsa {pb:.1f}× el actual '
                f'({pb * PRECIO_BOLSA_BASE:.0f} COP/kWh) — escenario de '
                f'crisis extrema comparable a 2022-23'
            )
        if pb > 1.5:
            advertencias.append(
                '📊 A este precio de bolsa, la generación '
                'térmica se activa como respaldo crítico'
            )
        fp = params.get('factor_perdidas', 0.085)
        if fp < 0.06:
            advertencias.append(
                '⚠️ Factor pérdidas < 6%: por debajo de los '
                'mínimos técnicos reconocidos por CREG'
            )
        if fp > 0.15:
            advertencias.append(
                '⚠️ Factor pérdidas > 15%: supera el doble '
                'del factor actual — implicaría reforma '
                'regulatoria mayor'
            )
        cr = params.get('cargo_restricciones_kw')
        if cr is not None and cr > 30:
            advertencias.append(
                f'⚠️ Cargo restricciones {cr:.1f} COP/kWh — '
                f'nivel de crisis operativa grave del SIN'
            )
        return advertencias

    # ════════════════════════════════════════════════════════════
    # ESCENARIOS PREDEFINIDOS
    # ════════════════════════════════════════════════════════════

    def get_escenarios_predefinidos(self) -> list:
        """Retorna escenarios predefinidos con contexto histórico colombiano."""
        return [
            {
                'id': 'sequia_moderada',
                'nombre': 'Sequía moderada (El Niño típico)',
                'descripcion': (
                    'Precio bolsa +40%, restricciones elevadas. '
                    'Similar al período jun-sep 2015.'
                ),
                'tipo': 'SEQUIA',
                'parametros': {
                    'precio_bolsa_factor': 1.40,
                    'demanda_factor': 0.97,
                    'cargo_restricciones_kw': 3.5,
                },
                'contexto_historico': (
                    'Embalses al 40%. CU histórico en ese '
                    'período: ~220-250 COP/kWh.'
                ),
            },
            {
                'id': 'sequia_severa',
                'nombre': 'Sequía severa (crisis hídrica 2022-23)',
                'descripcion': (
                    'Precio bolsa +120%, restricciones críticas. '
                    'Replica condiciones dic 2022 - mar 2023.'
                ),
                'tipo': 'SEQUIA',
                'parametros': {
                    'precio_bolsa_factor': 2.20,
                    'demanda_factor': 0.90,
                    'cargo_restricciones_kw': 15.0,
                },
                'contexto_historico': (
                    'CU real en ese período llegó a 800+ '
                    'COP/kWh. Embalses < 25%.'
                ),
            },
            {
                'id': 'reforma_perdidas_reduccion',
                'nombre': 'Reforma CREG: reducir pérdidas reconocidas',
                'descripcion': (
                    'Bajar factor de 8.5% a 7.0% — ahorro '
                    'por eficiencia distribuidoras.'
                ),
                'tipo': 'REFORMA_TARIFA',
                'parametros': {
                    'factor_perdidas': 0.070,
                },
                'contexto_historico': (
                    'CREG Concepto 2921/2025 analiza este '
                    'ajuste actualmente.'
                ),
            },
            {
                'id': 'expansion_renovables',
                'nombre': 'Expansión renovables 2GW',
                'descripcion': (
                    'Precio bolsa -20% por mayor oferta '
                    'solar/eólica. Proyección 2027-2028.'
                ),
                'tipo': 'INVERSION',
                'parametros': {
                    'precio_bolsa_factor': 0.80,
                    'factor_perdidas': 0.082,
                },
                'contexto_historico': (
                    'Plan de expansión UPME incluye 4.5 GW '
                    'renovables no convencionales a 2027.'
                ),
            },
            {
                'id': 'antifraude_agresivo',
                'nombre': 'Programa Antifraude Agresivo (AMI)',
                'descripcion': (
                    'Implementación de medidores inteligentes AMI en zonas de '
                    'alta incidencia + operativos de normalización SSPD. '
                    'Reducción pérdidas reconocidas: 8.5% → 7.2% (−15% PNT).'
                ),
                'tipo': 'REFORMA_TARIFA',
                'parametros': {
                    'factor_perdidas': 0.072,
                },
                'contexto_historico': (
                    'Colombia pierde ~COP 2.8B/año por pérdidas NT '
                    '(CREG Concepto 2921/2025). Reducción del 15% viable '
                    'en 18 meses según experiencias EPM/ENEL.'
                ),
            },
            {
                'id': 'combinado',
                'nombre': 'Renovables + Antifraude (Escenario Óptimo)',
                'descripcion': (
                    'Combinación de expansión renovable (500 MW solar Costa '
                    'Atlántica + 300 MW eólica La Guajira) con programa '
                    'antifraude que reduce pérdidas en 10%. Política pública '
                    'más probable 2026-2030 (UPME/SSPD-MME).'
                ),
                'tipo': 'INVERSION',
                'parametros': {
                    'precio_bolsa_factor': 0.88,
                    'factor_perdidas': 0.077,
                    'demanda_factor': 1.02,
                },
                'contexto_historico': (
                    'Meta UPME: 4.5 GW renovables a 2027. CREG ha priorizado '
                    'reducción de pérdidas como mecanismo de reducción '
                    'tarifaria para estratos 1-3.'
                ),
            },
            {
                'id': 'apagon_regional',
                'nombre': 'Apagón Regional (Escenario Extremo)',
                'descripcion': (
                    'Crisis hídrica severa (embalses < 20% útil) combinada '
                    'con pico de pérdidas y restricciones de transmisión en '
                    'zona Caribe. Escenario de riesgo sistémico.'
                ),
                'tipo': 'SEQUIA',
                'parametros': {
                    'precio_bolsa_factor': 2.80,
                    'demanda_factor': 0.92,
                    'cargo_restricciones_kw': 45.0,
                    'factor_perdidas': 0.092,
                },
                'contexto_historico': (
                    'Crisis hídrica 2015-2016: embalses al 19%, precio bolsa '
                    'superó $1,200 COP/kWh. UPME clasifica este riesgo como '
                    '"alto" si no se diversifica la matriz antes de 2028.'
                ),
            },
        ]

    # ════════════════════════════════════════════════════════════
    # PERSISTENCIA
    # ════════════════════════════════════════════════════════════

    def guardar_simulacion(
        self,
        nombre: str,
        parametros: dict,
        resultado: dict,
        tipo: str = "PERSONALIZADO",
        descripcion: str = "",
    ) -> int:
        """
        Persiste una simulación en simulation_results.

        Returns:
            ID del registro creado
        """
        try:
            baseline = {
                'cu_baseline': resultado.get('cu_baseline', CU_BASE_DEFAULT),
                'componentes_baseline': resultado.get('componentes_baseline', {}),
            }
            impacto_pct = resultado.get('delta_pct', 0.0)

            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO simulation_results
                        (nombre, descripcion, parametros_json, resultado_json,
                         baseline_json, tipo_escenario, impacto_pct)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        nombre,
                        descripcion,
                        json.dumps(parametros),
                        json.dumps(resultado, default=str),
                        json.dumps(baseline, default=str),
                        tipo,
                        impacto_pct,
                    ),
                )
                row_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"{_LOG} Simulación guardada — id={row_id}, nombre='{nombre}'")
                return row_id
        except Exception as e:
            logger.error(f"{_LOG} Error guardando simulación: {e}")
            raise DatabaseError(f"Error guardando simulación: {e}")

    def limpiar_historial(self) -> int:
        """Elimina todos los registros de simulation_results. Retorna filas borradas."""
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM simulation_results")
                deleted = cur.rowcount
                conn.commit()
                logger.info(f"{_LOG} Historial eliminado — {deleted} registros borrados")
                return deleted
        except Exception as e:
            logger.error(f"{_LOG} Error limpiando historial: {e}")
            raise DatabaseError(f"Error limpiando historial: {e}")

    def get_historial(self, limite: int = 20) -> list:
        """Retorna las últimas N simulaciones guardadas."""
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, nombre, tipo_escenario, impacto_pct,
                           fecha_creacion, parametros_json, resultado_json
                    FROM simulation_results
                    WHERE vigente = TRUE
                    ORDER BY fecha_creacion DESC
                    LIMIT %s
                    """,
                    (limite,),
                )
                rows = cur.fetchall()
                conn.commit()

            historial = []
            for r in rows:
                resultado_json = r[6] if isinstance(r[6], dict) else json.loads(r[6])
                historial.append({
                    'id': r[0],
                    'nombre': r[1],
                    'tipo': r[2],
                    'impacto_pct': float(r[3]) if r[3] else 0.0,
                    'fecha': str(r[4]),
                    'parametros': r[5] if isinstance(r[5], dict) else json.loads(r[5]),
                    'cu_simulado': resultado_json.get('cu_simulado'),
                    'cu_baseline': resultado_json.get('cu_baseline'),
                })
            return historial
        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo historial: {e}")
            return []

    # ════════════════════════════════════════════════════════════
    # MÉTODOS AUXILIARES PRIVADOS
    # ════════════════════════════════════════════════════════════

    def _get_cu_base_dinamico(self) -> Optional[float]:
        """
        Lee AVG(cu_total) de cu_daily de los últimos 30 días.
        Retorna float o None si falla.
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT ROUND(AVG(cu_total)::numeric, 4)
                    FROM cu_daily
                    WHERE fecha >= CURRENT_DATE - INTERVAL '30 days'
                      AND cu_total > 0
                      AND notas LIKE 'G_CREG_FORMULA%%'
                    """
                )
                row = cur.fetchone()
                conn.commit()
                if row and row[0]:
                    val = float(row[0])
                    logger.debug(f"{_LOG} CU base dinámico (30d): {val}")
                    return val
                return None
        except Exception as e:
            logger.warning(f"{_LOG} Error obteniendo CU base dinámico: {e}")
            return None

    def _generar_serie_simulada(
        self, params: dict, horizonte_dias: int = 30
    ) -> list:
        """
        Lee los últimos horizonte_dias de cu_daily, aplica
        _calcular_cu_simulado() a cada fila.

        Returns:
            list[dict] con fecha, cu_real, cu_simulado
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT fecha, cu_total
                    FROM cu_daily
                    WHERE cu_total > 0
                    ORDER BY fecha DESC
                    LIMIT %s
                    """,
                    (horizonte_dias,),
                )
                rows = cur.fetchall()
                conn.commit()

            serie = []
            for fecha, cu_real in reversed(rows):
                sim = self._calcular_cu_simulado(params, float(cu_real))
                serie.append({
                    'fecha': str(fecha),
                    'cu_real': round(float(cu_real), 4),
                    'cu_simulado': sim['cu_simulado'],
                })
            return serie
        except Exception as e:
            logger.warning(f"{_LOG} Error generando serie simulada: {e}")
            return []

    # ════════════════════════════════════════════════════════════
    # MONTE CARLO
    # ════════════════════════════════════════════════════════════

    def run_monte_carlo(
        self,
        escenario: str,
        n_simulations: int = 500,
        seed: int = 42,
    ) -> dict:
        """
        Ejecuta N simulaciones Monte Carlo variando los factores del escenario
        con distribución triangular (±15%).

        Retorna:
          escenario, n_simulations, cu_base,
          cu_p10, cu_p50, cu_p90, cu_mean, cu_std,
          reduccion_cu_p50 (% vs base), histogram_data
        """
        import numpy as np

        rng = np.random.default_rng(seed)

        # Factores base del escenario
        presets = {e["id"]: e for e in self.get_escenarios_predefinidos()}
        if escenario in presets:
            base_params = presets[escenario]["parametros"].copy()
        else:
            base_params = {
                "precio_bolsa_factor": 1.0,
                "factor_perdidas": 0.085,
            }

        cu_base = self._get_cu_base_dinamico()
        if cu_base is None:
            cu_base = CU_BASE_DEFAULT

        resultados_cu = []
        for _ in range(n_simulations):
            params_sim = {}
            for nombre, valor_central in base_params.items():
                if valor_central == 0.0:
                    # Escalar con epsilon para evitar degenerate triangular
                    params_sim[nombre] = 0.0
                else:
                    lo = valor_central * 0.85
                    hi = valor_central * 1.15
                    # Asegurar orden correcto (p.ej. factores negativos)
                    if lo > hi:
                        lo, hi = hi, lo
                    params_sim[nombre] = float(
                        rng.triangular(lo, valor_central, hi)
                    )
            cu_sim = self._calcular_cu_simulado(params_sim, cu_base)["cu_simulado"]
            resultados_cu.append(cu_sim)

        arr = np.array(resultados_cu)
        cu_p50 = float(np.percentile(arr, 50))

        return {
            "escenario": escenario,
            "n_simulations": n_simulations,
            "cu_base": round(cu_base, 4),
            "cu_p10": round(float(np.percentile(arr, 10)), 4),
            "cu_p50": round(cu_p50, 4),
            "cu_p90": round(float(np.percentile(arr, 90)), 4),
            "cu_mean": round(float(arr.mean()), 4),
            "cu_std": round(float(arr.std()), 4),
            "reduccion_cu_p50": round((cu_base - cu_p50) / cu_base * 100, 2),
            "histogram_data": arr.tolist(),
        }

    def get_baseline_info(self) -> dict:
        """
        Retorna información del baseline actual para el endpoint /baseline.
        """
        cu_base = self._get_cu_base_dinamico() or CU_BASE_DEFAULT

        return {
            'cu_base': cu_base,
            'precio_bolsa_base': PRECIO_BOLSA_BASE,
            'desglose_componentes': {
                k: round(cu_base * v, 4)
                for k, v in DESGLOSE_BASE.items()
            },
            'desglose_porcentual': {k: v for k, v in DESGLOSE_BASE.items()},
            'p_nt_validado': 3.328,
            'parametros_creg_actuales': {
                'factor_perdidas_distribucion': 0.085,
                'factor_perdidas_sdl_total': 0.12,
                'consumo_estrato3_kwh': CONSUMO_ESTRATO3_KWH,
                'subsidio_basico_kwh': SUBSIDIO_BASICO_KWH,
                'subsidio_pct': SUBSIDIO_PCT,
            },
        }
