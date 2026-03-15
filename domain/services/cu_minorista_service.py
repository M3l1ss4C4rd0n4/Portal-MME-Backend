"""
CU Minorista Service — Costo Unitario Tarifa Usuario Final
==========================================================

Calcula el CU que paga el usuario final (tarifa minorista regulada)
por Operador de Red (OR) / Distribuidora en Colombia.

La fórmula se basa en la Resolución CREG 119 de 2007 y el Boletín
Tarifario de la SSPD:

  CU_minorista = (G + T_STN + T_STR + D + C + R + Cargos_Sociales)
                 / (1 - Pérdidas_reconocidas_pct / 100)

donde:
  G             = G mayorista del día (de cu_daily, fórmula CREG con contratos)
  T_STN         = cargo uso STN MINORISTA (~50.87 COP/kWh, distinto del mayorista ~8.5)
                  Derivado de Boletín Tarifario SSPD / Enel Colombia Ene-2026.
                  Se lee primero de cu_tarifas_or.t_stn_cop_kwh, luego de settings.
  T_STR         = cargo uso STR local del OR (COP/kWh, de cu_tarifas_or)
  D             = DTUN distribución del OR (COP/kWh, de cu_tarifas_or)
  C             = cargo comercialización minorista del OR (COP/kWh)
  R             = cargo restricciones del despacho (de cu_tarifas_or, publ. por XM)
  PR            = cargos sociales (FAZNI + FAER + PRONE) del OR
  Pérdidas_pct  = pérdidas reconocidas del OR (de cu_tarifas_or)

NOTA: Los valores de T_STN, T_STR, D, C, R y pérdidas provienen de la tabla
cu_tarifas_or. T_STN se actualiza con Boletín SSPD (valor nacional = mismo para
todos los OR). D, C y pérdidas son específicos por OR. R varía mensualmente.
  - CODENSA: fuente ENEL_OFICIAL_2026_01 (datos Ene 2026 verificados)
  - Demás ORs: fuente SSPD_2024_Q4 (DESACTUALIZADOS — cargar con etl_tarifas_or_mensual.py)
El G se toma dinámicamente de cu_daily para reflejar cambios diarios del mercado.

Los valores NO incluyen IVA (19%) ni descuentos/contribuciones por estrato.
Para un cálculo de factura final al usuario, se deben aplicar:
- Estrato 1-3: descuento de solidaridad (~% del cargo G+T+D+C)
- Estrato 5-6, industrial/comercial: contribución solidaria (+20% sobre G+T+D+C)
- Estrato 4: sin subsidio ni contribución
- IVA: 19% sobre excedentes (estratos 5-6, comercial, industrial)

Fuentes:
  - SSPD Boletín Tarifario Q4 2024
  - CREG Resolución 119 de 2007 (fórmula tarifaria)
  - XM — Boletín LAC (componente G mayorista)
"""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from core.config import get_settings
from infrastructure.database.connection import PostgreSQLConnectionManager

# ─────────────────────────────────────────────────────────────────────────────
# Factores de subsidio / contribución solidaria por estrato (CREG Res. 131/1998
# y actualizaciones CREG 015/2018, CREG 101/2023).
#
# Factor = 1 + delta, donde delta:
#   Estrato 1: -0.60  → usuario paga 40% de la tarifa base
#   Estrato 2: -0.50  → 50%
#   Estrato 3: -0.15  → 85%
#   Estrato 4:  0.00  → 100% (tarifa plena, sin subsidio ni contribución)
#   Estrato 5: +0.20  → 120% (contribución solidaria)
#   Estrato 6: +0.20  → 120%
#   Industrial: +0.20 → 120%
#   Comercial:  +0.20 → 120%
#
# NOTA: Los porcentajes de subsidio aplican al consumo hasta el límite de
# subsistencia (~130 kWh/mes).  Para el dashboard se aplican como factor
# uniforme sobre el CU unitario, lo cual es una aproximación que refleja
# el impacto promedio en la factura mensual de un usuario residencial.
#
# IVA: 19% para estratos 5, 6, industrial y comercial sobre la tarifa base
# (el cargo de energía de uso doméstico está exento para estratos 1-4).
# ─────────────────────────────────────────────────────────────────────────────
FACTOR_ESTRATO: dict[str, float] = {
    'E1':          0.40,
    'E2':          0.50,
    'E3':          0.85,
    'E4':          1.00,
    'E5':          1.20,
    'E6':          1.20,
    'Industrial':  1.20,
    'Comercial':   1.20,
    'Oficial':     1.00,   # entidades gubernamentales, tarifa plena sin IVA
}

# IVA (19%) aplica sobre la tarifa post-factor para estos tipos de usuario
CATEGORIAS_CON_IVA = {'E5', 'E6', 'Industrial', 'Comercial'}

LABELS_ESTRATO = {
    'E1':          'Estrato 1 (subsidio 60%)',
    'E2':          'Estrato 2 (subsidio 50%)',
    'E3':          'Estrato 3 (subsidio 15%)',
    'E4':          'Estrato 4 (sin subsidio)',
    'E5':          'Estrato 5 (+20% contribución)',
    'E6':          'Estrato 6 (+20% contribución)',
    'Industrial':  'Industrial (+20% contribución)',
    'Comercial':   'Comercial (+20% contribución)',
    'Oficial':     'Sector Oficial (tarifa plena)',
}

logger = logging.getLogger(__name__)
_LOG = "[CU_MINORISTA]"


class CUMinoristaService:
    """
    Servicio de CU minorista (tarifa usuario final) por OR.

    Combina:
      - G diario de cu_daily (dato vivo del mercado mayorista)
      - Cargos tarifarios por OR de cu_tarifas_or (referencia SSPD)
    """

    def __init__(self):
        self._settings = get_settings()
        self._conn_mgr = PostgreSQLConnectionManager()
        # T_STN MINORISTA: valor real del Boletín Tarifario SSPD (~50.87 COP/kWh en 2026).
        # Es el fallback; se lee primero de cu_tarifas_or.t_stn_cop_kwh por OR.
        # MUY DISTINTO del T_STN mayorista (~8.5 COP/kWh del Boletín LAC XM).
        self._t_stn_minorista = self._settings.CARGO_T_STN_MINORISTA_COP_KWH

    # ─────────────────────────────────────────────────────────────────
    # Cargos tarifarios de referencia
    # ─────────────────────────────────────────────────────────────────

    def get_tarifas_or(self) -> pd.DataFrame:
        """
        Retorna todos los OR con sus cargos de referencia SSPD.
        Columnas: or_codigo, or_nombre, region, departamentos,
                  nivel_tension, t_stn_cop_kwh, t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
                  r_restricciones_cop_kwh, perdidas_reconocidas_pct, fazni_cop_kwh,
                  faer_cop_kwh, prone_cop_kwh, fuente, vigente_desde
        """
        sql = """
            SELECT or_codigo, or_nombre, region, departamentos,
                   nivel_tension,
                   COALESCE(t_stn_cop_kwh, 50.87) AS t_stn_cop_kwh,
                   t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
                   COALESCE(r_restricciones_cop_kwh, 0) AS r_restricciones_cop_kwh,
                   perdidas_reconocidas_pct,
                   fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh,
                   fuente, vigente_desde
            FROM cu_tarifas_or
            ORDER BY region, or_nombre
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                df = pd.read_sql_query(sql, conn)
            return df
        except Exception as e:
            logger.error(f"{_LOG} Error cargando tarifas OR: {e}")
            return pd.DataFrame()

    # ─────────────────────────────────────────────────────────────────
    # G mayorista diario (de cu_daily)
    # ─────────────────────────────────────────────────────────────────

    def get_g_mayorista_actual(self) -> Optional[dict]:
        """
        Retorna el G mayorista más reciente disponible en cu_daily,
        priorizando fechas calculadas con la fórmula CREG (G_CREG_FORMULA)
        sobre el fallback de solo precio de bolsa (G_BOLSA_FALLBACK).

        La API de XM publica PrecPromContRegu con ~2 días de lag;
        los últimos 1-2 días de cu_daily suelen tener G_BOLSA_FALLBACK.
        Usar la última fecha con fórmula CREG da el CU más preciso.

        Returns dict: {fecha, componente_g, cu_total_mayorista, confianza,
                       fuente_g ('G_CREG_FORMULA' | 'G_BOLSA_FALLBACK')}
        """
        sql = """
            SELECT fecha, componente_g, cu_total, confianza, notas
            FROM cu_daily
            WHERE componente_g IS NOT NULL
            ORDER BY
                -- Priorizar G_CREG_FORMULA sobre fallback
                CASE WHEN notas LIKE '%G_CREG_FORMULA%' THEN 0 ELSE 1 END,
                fecha DESC
            LIMIT 1
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql)
                row = cur.fetchone()
                cur.close()
            if row is None:
                return None
            notas = row[4] or ''
            fuente_g = 'G_CREG_FORMULA' if 'G_CREG_FORMULA' in notas else 'G_BOLSA_FALLBACK'
            return {
                'fecha': row[0],
                'componente_g': float(row[1]),
                'cu_total_mayorista': float(row[2]),
                'confianza': row[3],
                'fuente_g': fuente_g,
            }
        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo G mayorista: {e}")
            return None

    def get_g_mayorista_historico(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """
        Retorna la serie histórica de G mayorista y CU mayorista.
        """
        sql = """
            SELECT fecha, componente_g, componente_t, componente_r,
                   perdidas_pct, cu_total, confianza
            FROM cu_daily
            WHERE fecha BETWEEN %s AND %s
              AND componente_g IS NOT NULL
            ORDER BY fecha
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                df = pd.read_sql_query(sql, conn, params=(fecha_inicio, fecha_fin))
            for col in ['componente_g', 'componente_t', 'componente_r', 'perdidas_pct', 'cu_total']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception as e:
            logger.error(f"{_LOG} Error obteniendo G histórico: {e}")
            return pd.DataFrame()

    def get_g_promedio_mensual(self, año: int, mes: int) -> Optional[dict]:
        """
        Calcula el promedio mensual del componente G mayorista para un año/mes dado.

        Replica la lógica de facturación real: los distribuidores liquidan la tarifa
        usando el G promedio del mes de suministro (no el precio spot diario).

        Args:
            año: año calendario (ej. 2026)
            mes: mes calendario 1-12

        Returns:
            dict con:
              - 'componente_g': promedio mensual COP/kWh
              - 'cu_total_mayorista': promedio mensual CU mayorista
              - 'dias': número de días con dato
              - 'g_min', 'g_max': rango del mes
              - 'periodo_ref': string "ene-2026"
              - 'fuente_g': 'G_MENSUAL'
            None si no hay datos para ese mes (< 5 días disponibles).
        """
        from datetime import datetime
        import calendar
        sql = """
            SELECT AVG(componente_g)  AS g_prom,
                   AVG(cu_total)      AS cu_prom,
                   COUNT(*)           AS dias,
                   MIN(componente_g)  AS g_min,
                   MAX(componente_g)  AS g_max
            FROM cu_daily
            WHERE EXTRACT(year  FROM fecha) = %s
              AND EXTRACT(month FROM fecha) = %s
              AND componente_g IS NOT NULL
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql, (año, mes))
                row = cur.fetchone()
                cur.close()
            if row is None or row[0] is None or int(row[2]) < 5:
                return None
            meses_es = ['', 'ene', 'feb', 'mar', 'abr', 'may', 'jun',
                        'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
            return {
                'componente_g':      float(row[0]),
                'cu_total_mayorista': float(row[1]),
                'dias':              int(row[2]),
                'g_min':             float(row[3]),
                'g_max':             float(row[4]),
                'periodo_ref':       f"{meses_es[mes]}-{año}",
                'fuente_g':          'G_MENSUAL',
            }
        except Exception as e:
            logger.error(f"{_LOG} Error calculando G mensual {año}-{mes:02d}: {e}")
            return None

    def get_g_periodo_referencia(self) -> Optional[dict]:
        """
        Retorna el G de referencia óptimo para replicar la tarifa facturada:

          1. Intenta el mes ANTERIOR completo (≥20 días de dato) → 'G_MENSUAL'
          2. Si falla, intenta hace 2 meses → 'G_MENSUAL'
          3. Fallback: G diario más reciente con fórmula CREG → 'G_CREG_FORMULA'
          4. Último recurso: G diario sin importar fuente → 'G_BOLSA_FALLBACK'

        La prioridad de mensual vs diario refleja cómo los ORs liquidan la tarifa:
        el G de un mes facturado usa el promedio del mes, no el precio spot del día.

        Returns:
            dict compatible con el que retorna get_g_mayorista_actual(), más
            las claves 'dias', 'g_min', 'g_max', 'periodo_ref' (si es mensual).
        """
        from datetime import datetime
        hoy = date.today()
        # 1. Mes anterior
        if hoy.month == 1:
            año_ref, mes_ref = hoy.year - 1, 12
        else:
            año_ref, mes_ref = hoy.year, hoy.month - 1

        g_mensual = self.get_g_promedio_mensual(año_ref, mes_ref)
        if g_mensual and g_mensual.get('dias', 0) >= 20:
            return g_mensual

        # 2. Hace 2 meses
        if mes_ref == 1:
            año2, mes2 = año_ref - 1, 12
        else:
            año2, mes2 = año_ref, mes_ref - 1
        g_dos_meses = self.get_g_promedio_mensual(año2, mes2)
        if g_dos_meses and g_dos_meses.get('dias', 0) >= 20:
            logger.warning(f"{_LOG} Usando G de hace 2 meses ({g_dos_meses['periodo_ref']}) — mes anterior insuficiente")
            return g_dos_meses

        # 3 & 4. Fallback a diario
        logger.warning(f"{_LOG} Sin G mensual disponible — usando G diario como fallback")
        return self.get_g_mayorista_actual()

    # ─────────────────────────────────────────────────────────────────
    # Cálculo CU minorista
    # ─────────────────────────────────────────────────────────────────

    def calcular_cu_minorista_or(
        self,
        g_mayorista: float,
        or_row: dict,
        estrato: str = 'E4',
        incluir_iva: bool = False,
    ) -> dict:
        """
        Calcula el CU minorista para un OR dado un G mayorista,
        aplicando el factor de subsidio/contribución solidaria por estrato
        (CREG Res. 131/1998, actualizaciones CREG 015/2018 y CREG 101/2023)
        y opcionalmente el IVA (19%).

        Args:
            g_mayorista:  componente G del mercado mayorista (COP/kWh)
            or_row:       fila de cu_tarifas_or como dict
            estrato:      código de estrato ('E1'...'E6', 'Industrial', 'Comercial', 'Oficial')
            incluir_iva:  si True, añade IVA 19% para E5/E6/Industrial/Comercial

        Returns:
            dict con todos los componentes, CU base, CU con estrato, (CU con IVA)
        """
        # T_STN: leer del OR (columna por OR en BD) o fallback al setting nacional
        t_stn = float(or_row.get('t_stn_cop_kwh') or self._t_stn_minorista)
        t_str = float(or_row.get('t_str_cop_kwh', 0) or 0)
        d     = float(or_row.get('d_cop_kwh', 0) or 0)
        c     = float(or_row.get('c_cop_kwh', 0) or 0)
        r     = float(or_row.get('r_restricciones_cop_kwh', 0) or 0)
        fazni = float(or_row.get('fazni_cop_kwh', 0) or 0)
        faer  = float(or_row.get('faer_cop_kwh', 0) or 0)
        prone = float(or_row.get('prone_cop_kwh', 0) or 0)
        perdidas_pct = float(or_row.get('perdidas_reconocidas_pct', 10.0) or 10.0)

        cargos_sociales = fazni + faer + prone

        # Suma base de componentes (CREG 119/2007: G + T_STN + T_STR + D + C + R + CS)
        suma_base = g_mayorista + t_stn + t_str + d + c + r + cargos_sociales

        # Factor de pérdidas reconocidas del OR
        if perdidas_pct >= 95:
            perdidas_pct = 95.0
        factor_perdidas = 1.0 / (1.0 - perdidas_pct / 100.0)

        # CU base NT1 sin estrato (tarifa de referencia CREG)
        cu_base = suma_base * factor_perdidas

        # Factor de estrato (subsidio / contribución solidaria)
        factor_est = FACTOR_ESTRATO.get(estrato, 1.0)
        cu_con_estrato = cu_base * factor_est

        # IVA (19%) — solo para categorías que aplican y si el usuario lo pide
        aplica_iva = incluir_iva and estrato in CATEGORIAS_CON_IVA
        cu_con_iva = cu_con_estrato * 1.19 if aplica_iva else cu_con_estrato

        # Delta vs tarifa base (efecto subsidio o contribución en COP/kWh)
        delta_estrato = cu_con_estrato - cu_base

        return {
            'or_codigo':  or_row.get('or_codigo'),
            'or_nombre':  or_row.get('or_nombre'),
            'region':     or_row.get('region'),
            'departamentos': or_row.get('departamentos', ''),
            # Componentes base
            'g_mayorista':              round(g_mayorista, 2),
            't_stn':                    round(t_stn, 2),
            't_str':                    round(t_str, 2),
            'd':                        round(d, 2),
            'c':                        round(c, 2),
            'r_restricciones':          round(r, 2),
            'cargos_sociales':          round(cargos_sociales, 2),
            'fazni':                    round(fazni, 2),
            'faer':                     round(faer, 2),
            'prone':                    round(prone, 2),
            'perdidas_reconocidas_pct': round(perdidas_pct, 2),
            'factor_perdidas': round(factor_perdidas, 4),
            # CU a distintos niveles
            'cu_minorista_total':  round(cu_base, 2),        # Tarifa base (E4, sin subsidio)
            'cu_con_estrato':      round(cu_con_estrato, 2), # Tarifa ajustada por estrato
            'cu_con_iva':          round(cu_con_iva, 2),     # Con IVA (si aplica)
            'factor_estrato':      round(factor_est, 2),
            'delta_estrato':       round(delta_estrato, 2),
            'aplica_iva':          aplica_iva,
            'estrato':             estrato,
            'fuente': or_row.get('fuente', 'SSPD_2024_Q4'),
        }

    def get_cu_minorista_todos_or(
        self,
        fecha: Optional[date] = None,
        estrato: str = 'E4',
        incluir_iva: bool = False,
        modo_g: str = 'mensual',
    ) -> pd.DataFrame:
        """
        Calcula el CU minorista para TODOS los OR.

        Args:
            fecha:       fecha específica de G (solo aplica cuando modo_g='diario').
                         None → usa el G más reciente disponible.
            estrato:     código de estrato ('E1'...'E6', 'Industrial', 'Comercial', 'Oficial')
            incluir_iva: si True, multiplica por 1.19 para categorías que aplican IVA
            modo_g:      'mensual' → usa el promedio del mes anterior (réplica tarifa facturada)
                         'diario'  → usa el G del día más reciente (precio actual de mercado)

        Returns DataFrame con columnas:
            or_codigo, or_nombre, region, departamentos,
            g_mayorista, t_stn, t_str, d, c, r_restricciones, cargos_sociales,
            perdidas_reconocidas_pct, cu_minorista_total, cu_con_estrato,
            cu_con_iva, cu_mayorista, diferencia_mayorista, fuente, fecha_g,
            fuente_g, periodo_ref (si modo_g='mensual')
        """
        # ── Resolver G según modo ─────────────────────────────────────
        if modo_g == 'mensual':
            g_info = self.get_g_periodo_referencia()
        elif fecha is not None:
            # Modo diario con fecha explícita
            sql_fecha = """
                SELECT fecha, componente_g, cu_total, confianza, notas
                FROM cu_daily
                WHERE fecha = %s AND componente_g IS NOT NULL
            """
            try:
                with self._conn_mgr.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(sql_fecha, (fecha,))
                    row = cur.fetchone()
                    cur.close()
                if row:
                    notas = row[4] or ''
                    g_info = {
                        'fecha': row[0],
                        'componente_g': float(row[1]),
                        'cu_total_mayorista': float(row[2]),
                        'confianza': row[3],
                        'fuente_g': 'G_CREG_FORMULA' if 'G_CREG_FORMULA' in notas else 'G_BOLSA_FALLBACK',
                    }
                else:
                    g_info = None
            except Exception as e:
                logger.error(f"{_LOG} Error obteniendo G para {fecha}: {e}")
                g_info = None
        else:
            # Modo diario sin fecha → más reciente
            g_info = self.get_g_mayorista_actual()

        if g_info is None:
            logger.warning(f"{_LOG} No hay G mayorista disponible (modo_g={modo_g})")
            return pd.DataFrame()

        g        = g_info['componente_g']
        cu_mayor = g_info['cu_total_mayorista']
        # Para G mensual no hay un único 'fecha'; usamos el primer día del período
        fecha_g  = g_info.get('fecha', None)
        fuente_g = g_info.get('fuente_g', 'G_BOLSA_FALLBACK')
        periodo_ref = g_info.get('periodo_ref', '')  # ej. "feb-2026" o ''

        # Obtener tarifas de todos los OR
        df_tarifas = self.get_tarifas_or()
        if df_tarifas.empty:
            return pd.DataFrame()

        resultados = []
        for _, row in df_tarifas.iterrows():
            calc = self.calcular_cu_minorista_or(g, row.to_dict(), estrato=estrato, incluir_iva=incluir_iva)
            calc['fecha_g']     = fecha_g
            calc['fuente_g']    = fuente_g
            calc['periodo_ref'] = periodo_ref
            calc['cu_mayorista'] = round(cu_mayor, 2)
            calc['diferencia_mayorista'] = round(calc['cu_con_estrato'] - cu_mayor, 2)
            resultados.append(calc)

        return pd.DataFrame(resultados)

    def get_cu_minorista_historico_or(
        self,
        or_codigo: str,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> pd.DataFrame:
        """
        Calcula la serie histórica de CU minorista para un OR específico,
        combinando el G diario de cu_daily con los cargos fijos del OR.

        Returns DataFrame con: fecha, g_mayorista, cu_mayorista, cu_minorista_total
        """
        # Obtener datos del OR
        sql_or = """
            SELECT or_codigo, or_nombre, region, departamentos,
                   COALESCE(t_stn_cop_kwh, 50.87) AS t_stn_cop_kwh,
                   t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
                   COALESCE(r_restricciones_cop_kwh, 0) AS r_restricciones_cop_kwh,
                   perdidas_reconocidas_pct,
                   fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh, fuente
            FROM cu_tarifas_or
            WHERE or_codigo = %s
            LIMIT 1
        """
        try:
            with self._conn_mgr.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql_or, (or_codigo,))
                or_row_raw = cur.fetchone()
                cur.close()
        except Exception as e:
            logger.error(f"{_LOG} Error cargando OR {or_codigo}: {e}")
            return pd.DataFrame()

        if or_row_raw is None:
            logger.warning(f"{_LOG} OR no encontrado: {or_codigo}")
            return pd.DataFrame()

        cols = ['or_codigo', 'or_nombre', 'region', 'departamentos',
                't_str_cop_kwh', 'd_cop_kwh', 'c_cop_kwh', 'perdidas_reconocidas_pct',
                'fazni_cop_kwh', 'faer_cop_kwh', 'prone_cop_kwh', 'fuente']
        or_row = dict(zip(cols, or_row_raw))

        # Obtener G histórico
        df_g = self.get_g_mayorista_historico(fecha_inicio, fecha_fin)
        if df_g.empty:
            return pd.DataFrame()

        resultados = []
        for _, grow in df_g.iterrows():
            g = float(grow['componente_g'])
            calc = self.calcular_cu_minorista_or(g, or_row)
            resultados.append({
                'fecha': grow['fecha'],
                'g_mayorista': g,
                'cu_mayorista': float(grow['cu_total']),
                'cu_minorista_total': calc['cu_minorista_total'],
                't_stn': calc['t_stn'],
                't_str': calc['t_str'],
                'd': calc['d'],
                'c': calc['c'],
                'cargos_sociales': calc['cargos_sociales'],
                'diferencia_mayorista': round(calc['cu_minorista_total'] - float(grow['cu_total']), 2),
            })

        return pd.DataFrame(resultados)

    def get_promedio_nacional_minorista(self, fecha: Optional[date] = None) -> Optional[dict]:
        """
        Calcula el CU minorista promedio nacional (promedio ponderado por
        número de ORs por región, igual peso para simplificar).

        Útil para mostrar en el KPI de home.py.
        """
        df = self.get_cu_minorista_todos_or(fecha)
        if df.empty:
            return None

        cu_prom = df['cu_minorista_total'].mean()
        cu_min  = df['cu_minorista_total'].min()
        cu_max  = df['cu_minorista_total'].max()
        fecha_g = df['fecha_g'].iloc[0] if 'fecha_g' in df.columns else None

        # OR más y menos caro
        or_mas_caro   = df.loc[df['cu_minorista_total'].idxmax()]
        or_menos_caro = df.loc[df['cu_minorista_total'].idxmin()]

        return {
            'fecha': fecha_g,
            'cu_minorista_promedio': round(cu_prom, 2),
            'cu_minorista_min': round(cu_min, 2),
            'cu_minorista_max': round(cu_max, 2),
            'or_mas_caro': or_mas_caro.get('or_codigo', ''),
            'or_menos_caro': or_menos_caro.get('or_codigo', ''),
            'n_operadores': len(df),
        }
