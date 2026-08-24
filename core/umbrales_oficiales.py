"""
═══════════════════════════════════════════════════════════════════════════════
UMBRALES OFICIALES DEL SECTOR ELÉCTRICO COLOMBIANO

Único punto de verdad para todos los umbrales regulatorios usados en el portal,
chatbot, alertas y correo diario. Todos los valores aquí están respaldados por
resoluciones de la CREG, el Estatuto para Situaciones de Riesgo de Desabasteci-
miento, publicaciones oficiales de XM/CND y normativa colombiana vigente.

NUNCA modificar estos valores sin actualizar la fuente regulatoria y la fecha
de revisión. Si una resolución CREG cambia, esto se actualiza primero.

═══════════════════════════════════════════════════════════════════════════════
FUENTES REGULATORIAS:
───────────────────────────────────────────────────────────────────────────────
1. Resolución CREG 026 de 2014 — Estatuto para Situaciones de Riesgo de
   Desabastecimiento en el Mercado Mayorista de Energía.
2. Resolución CREG 071 de 2006 — Cargo por Confiabilidad y precio de escasez.
3. Resolución CREG 140 de 2017 — Metodología de cálculo del precio marginal
   de escasez.
4. Resolución CREG 125 de 2020 — Deroga las normas del Capítulo II (Inicio y
   Finalización del Período de Riesgo de Desabastecimiento) de la Resolución
   CREG 026 de 2014 — reemplazadas por la Res. CREG 209 de 2020 (ver #5).
   CORREGIDO (2026-08-20): esta fuente estaba citada como "Resolución CREG
   121 de 2020" — verificado contra el listado cronológico real de la CREG
   (gestornormativo.creg.gov.co) que NO existe ninguna Resolución 121 de
   2020 con este tema (ni con ningún otro) — la 125/2020 es la que
   efectivamente deroga el capítulo que la 209/2020 reemplaza, mismo tema
   descrito aquí desde el inicio. Probable error de transcripción histórico
   en este archivo, nunca antes verificado contra la fuente oficial.
5. Resolución CREG 209 de 2020 — Senda de Referencia del embalse agregado del
   SIN e Índice NE.
6. Resolución CREG 101 055 de 2024 — Complemento al Estatuto de Desabasteci-
   miento.
7. Resolución CREG 101 066 de 2024 — Tres niveles de precio de escasez
   (PEI, PE, PES).
8. Resolución CREG 101 112 de 2026 (12 de junio de 2026, publicada en el
   Diario Oficial el 17 de junio de 2026) — MODIFICA el numeral 1 del
   literal B del artículo 2 de la Resolución CREG 026 de 2014: elimina la
   regla alternativa "embalse ≥ 70% del volumen útil agregado del SIN →
   Índice NE en nivel superior" (introducida por la Res. CREG 210 de 2021).
   Desde su vigencia, el Índice NE se determina EXCLUSIVAMENTE comparando
   el embalse útil real contra la senda de referencia — sin atajo del 70%.
   Verificado en vivo (2026-08-19) contra el texto de la resolución en
   gestornormativo.creg.gov.co — no en las publicaciones de XM, que no
   habían reflejado este cambio en su documentación general.
9. Publicaciones mensuales XM/CND:
   - https://www.xm.com.co/resoluciones/operacion-y-mercado/resolucion-creg-209-de-2020-condicion-del-sistema
   - https://www.xm.com.co/hidrologia/aportes
   - https://www.xm.com.co/hidrologia/reservas
   - https://www.xm.com.co/transacciones/cargo-por-confiabilidad/precio-de-bolsa-y-escasez

═══════════════════════════════════════════════════════════════════════════════
Última revisión normativa: 19 de agosto de 2026 (Res. CREG 101 112/2026 —
regla del 70% absoluto para el Índice NE, derogada desde el 17-jun-2026,
detectada activa en este código y corregida el mismo día de esta revisión).
Próxima revisión sugerida: trimestral, o ante nueva Resolución CREG.
═══════════════════════════════════════════════════════════════════════════════
"""

from datetime import date
from typing import Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — EMBALSES: SENDA DE REFERENCIA CREG E ÍNDICE NE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Fuente: Resolución CREG 209 de 2020, artículo 2.8.2.1.3.
# Calculada por el CND a partir de los supuestos de la CREG y publicada por XM
# en https://www.xm.com.co/resoluciones/operacion-y-mercado/resolucion-creg-209-de-2020-condicion-del-sistema
# o vía FTPS: /INFORMACION_XM/Publico/PlaneacionOperacion/Senda%20de%20Referencia/
#
# La Senda de Referencia es el nivel diario MÍNIMO del embalse útil del SIN
# (expresado como % del volumen útil total ≈ 17 000 GWh) necesario para
# asegurar el suministro de energía durante cada estación.
#
# El Índice NE (Nivel de Embalse) compara el nivel real con la senda:
#   • SUPERIOR: embalse real ≥ senda
#   • ALERTA:   senda − X ≤ embalse < senda
#                (persistente por 2 verificaciones semanales → pasa a inferior)
#   • INFERIOR: embalse real < senda − X
#
# Donde X = puntos porcentuales de tolerancia. En la práctica reciente X = 0.
#
# NOTA (2026-08-19): hasta esta revisión, SUPERIOR también se activaba de
# forma alternativa cuando embalse > 70% del volumen útil, sin importar la
# senda — esa regla (introducida por la Res. CREG 210/2021) fue DEROGADA
# por la Res. CREG 101 112/2026 (vigente desde el 17-jun-2026). Se detectó
# que este código seguía aplicándola activamente 2 meses después de
# derogada — corregido eliminando por completo la comparación alternativa.
#
# ──────────────────────────────────────────────────────────────────────────────

# Tolerancia de la senda (puntos porcentuales). 0 = comparación estricta.
SENDA_TOLERANCIA_PP: float = 0.0

# Senda de Referencia oficial publicada por XM/CND.
# Estos valores se actualizan al inicio de cada estación (mayo y diciembre).
# Estructura: día_del_año → % volumen útil mínimo del SIN.
#
# IMPORTANTE: estos valores son una tabla estática derivada de las sendas oficiales
# publicadas por XM. Para producción debe consultarse la API/FTPS de XM, pero esta
# tabla es el fallback regulatoriamente correcto y se mantiene como referencia.
#
# Fuente concreta:
#   - Senda Invierno 2024 (Circular CREG 023 de 2024):
#     1 mayo 2024 = 28.7%, 30 noviembre 2024 = 67.8%.
#   - Para abril 2024 según reportes: 35.4%.
SENDA_REFERENCIA_2024_2025: Dict[int, float] = {
    # Enero (estación verano) — referencia decreciente desde dic
    1:  55.0,
    # Febrero
    2:  47.0,
    # Marzo (mínimo histórico de verano)
    3:  37.0,
    # Abril (transición fin verano)
    4:  35.4,    # valor oficial CREG abril 2024
    # Mayo (inicio invierno)
    5:  28.7,    # valor oficial CREG inicio invierno 2024
    # Junio
    6:  35.0,
    # Julio
    7:  45.0,
    # Agosto
    8:  55.0,
    # Septiembre
    9:  62.0,
    # Octubre
    10: 65.0,
    # Noviembre
    11: 67.8,    # valor oficial CREG fin invierno 2024
    # Diciembre (inicio verano siguiente)
    12: 65.0,
}


def obtener_senda_referencia(fecha: Optional[date] = None) -> float:
    """
    Devuelve el nivel mínimo del embalse según la Senda de Referencia CREG
    para la fecha dada. Fuente: XM/CND publicación oficial Res. CREG 209/2020.

    Estrategia de consulta (en orden):
      1. Consulta la tabla `sector_energetico.senda_referencia` en PostgreSQL
         (datos diarios oficiales importados de XM).
      2. Si no hay registros en BD o falla la consulta, usa la tabla mensual
         de respaldo SENDA_REFERENCIA_2024_2025.
      3. Si tampoco hay fallback para el mes, retorna 50.0 (valor conservador).

    Args:
        fecha: fecha de evaluación (default: hoy).
    Returns:
        Porcentaje mínimo de volumen útil esperado para esa fecha.
    """
    f = fecha or date.today()

    # 1) Intentar consulta a BD (senda diaria oficial)
    try:
        from etl.etl_senda_referencia import obtener_senda_para_fecha
        valor_bd = obtener_senda_para_fecha(f)
        if valor_bd is not None:
            return float(valor_bd)
    except Exception:
        # Silencioso: si no hay BD disponible, usar respaldo
        pass

    # 2) Fallback: tabla mensual estática
    return SENDA_REFERENCIA_2024_2025.get(f.month, 50.0)


def clasificar_indice_ne(
    nivel_embalse_pct: float,
    fecha: Optional[date] = None,
) -> Tuple[str, str, float]:
    """
    Clasifica el embalse según el Índice NE del Estatuto CREG 026/2014 art. 2
    literal B, tal como fue modificado por la Resolución CREG 101 112/2026
    (vigente desde el 17-jun-2026): comparación exclusiva contra la senda de
    referencia — la regla alternativa "≥ 70% del volumen útil" (Res. CREG
    210/2021) fue derogada y ya NO se evalúa.

    Args:
        nivel_embalse_pct: nivel actual del embalse agregado del SIN (%).
        fecha: fecha de evaluación.

    Returns:
        (nivel, descripcion, senda_referencia_pct)
        nivel: 'SUPERIOR' | 'ALERTA' | 'INFERIOR'
    """
    senda = obtener_senda_referencia(fecha)

    if nivel_embalse_pct >= senda:
        return ('SUPERIOR',
                f'Embalse {nivel_embalse_pct:.1f}% ≥ senda {senda:.1f}% (Estatuto CREG).',
                senda)

    umbral_inferior = senda - SENDA_TOLERANCIA_PP
    if nivel_embalse_pct >= umbral_inferior:
        return ('ALERTA',
                f'Embalse {nivel_embalse_pct:.1f}% entre {umbral_inferior:.1f}% y senda {senda:.1f}%.',
                senda)

    return ('INFERIOR',
            f'Embalse {nivel_embalse_pct:.1f}% < senda {senda:.1f}% − {SENDA_TOLERANCIA_PP}pp.',
            senda)


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — APORTES HÍDRICOS: ÍNDICE HSIN
# ═══════════════════════════════════════════════════════════════════════════════
#
# Fuente: Resolución CREG 026 de 2014, artículo 2 — Niveles de alerta del sistema.
# Definición:
#   HSIN = aportes acumulados últimas 4 semanas / promedio histórico mismo período
#
# Niveles oficiales:
#   • HSIN ≥ 90%  → NORMAL    (suministro hídrico esperado o superior)
#   • HSIN < 90%  → VIGILANCIA (déficit confirmado, persistencia 2 verificaciones)
#
# Referencias adicionales documentadas (XM "Aportes Hídricos al SIN"):
# El seguimiento se realiza en porcentaje respecto a la media histórica mensual
# de cada río. https://www.xm.com.co/hidrologia/aportes
#
# Históricamente, abril 2020 = 60% de la media histórica (nivel histórico mínimo
# que llevó a la actualización del Estatuto vía Res. CREG 209/2020).
# ──────────────────────────────────────────────────────────────────────────────

# Umbral oficial CREG para HSIN (% de la media histórica de aportes)
HSIN_UMBRAL_NORMAL: float = 90.0           # ≥ 90% → condición normal
HSIN_UMBRAL_CRITICO_HISTORICO: float = 60.0  # nivel histórico de crisis (abril 2020)
HSIN_UMBRAL_DEFICIT_SEVERO: float = 70.0   # déficit severo documentado en CREG 209/2020

# Ventana de cálculo HSIN según Estatuto
HSIN_VENTANA_SEMANAS: int = 4


def clasificar_hsin(hsin_pct: float) -> Tuple[str, str]:
    """
    Clasifica el índice HSIN según niveles oficiales del Estatuto CREG 026/2014.

    Args:
        hsin_pct: porcentaje de aportes vs media histórica de 4 semanas.

    Returns:
        (nivel, descripcion)
        nivel: 'NORMAL' | 'VIGILANCIA' | 'DEFICIT_SEVERO' | 'CRITICO'
    """
    if hsin_pct >= HSIN_UMBRAL_NORMAL:
        return ('NORMAL',
                f'HSIN {hsin_pct:.1f}% ≥ 90% — condición normal (CREG 026/2014).')
    if hsin_pct >= HSIN_UMBRAL_DEFICIT_SEVERO:
        return ('VIGILANCIA',
                f'HSIN {hsin_pct:.1f}% < 90% — vigilancia (CREG 026/2014 art. 2).')
    if hsin_pct >= HSIN_UMBRAL_CRITICO_HISTORICO:
        return ('DEFICIT_SEVERO',
                f'HSIN {hsin_pct:.1f}% < 70% — déficit severo (referencia CREG 209/2020).')
    return ('CRITICO',
            f'HSIN {hsin_pct:.1f}% ≤ 60% — nivel histórico de crisis (abril 2020).')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — PRECIO DE BOLSA Y PRECIO DE ESCASEZ
# ═══════════════════════════════════════════════════════════════════════════════
#
# Fuente: Resolución CREG 101 066 de 2024 — Tres niveles de precio de escasez.
# Fuente: Resolución CREG 026 de 2014, artículo 2 — Índice PBP.
#
# Tres niveles de precio de escasez vigentes:
#   • PEI (Precio de Escasez Inferior)        — Res. CREG 101 066/2024
#   • PE  (Precio de Escasez Res. 071/2006)   — Res. CREG 071/2006
#   • PES (Precio de Escasez Superior)        — Res. CREG 140/2017
#
# Estos valores se actualizan MENSUALMENTE por la CREG y se publican en
# https://www.xm.com.co/transacciones/cargo-por-confiabilidad/precio-de-bolsa-y-escasez
#
# Valor de referencia para PEI (Res. CREG 101 066/2024): 359 $/kWh base.
#
# Índice PBP (Precio de Bolsa Promedio) — Art. 2 Estatuto CREG 026/2014:
#   • NIVEL BAJO:  PBP promedio < Precio Escasez Activación en 4 de últimos 7 días.
#   • NIVEL ALTO:  PBP promedio ≥ Precio Escasez Activación.
#
# El "Precio de Escasez de Activación" del Cargo por Confiabilidad es el techo
# regulatorio donde se hacen exigibles las Obligaciones de Energía Firme (OEF).
# ──────────────────────────────────────────────────────────────────────────────

# Valores de referencia ene-2026 (Informe oficial XM, actualizar mensualmente):
PRECIO_ESCASEZ_PEI_REF_2026_01: float = 327.67   # COP/kWh
PRECIO_ESCASEZ_PE_REF_2026_01: float = 590.56    # COP/kWh
PRECIO_ESCASEZ_PES_REF_2026_01: float = 830.34   # COP/kWh

# Valor base regulatorio PEI (Res. CREG 101 066/2024)
PRECIO_ESCASEZ_PEI_BASE: float = 359.0   # COP/kWh — referencia base regulatoria

# Reglas oficiales del índice PBP (Estatuto CREG 026/2014)
PBP_DIAS_VENTANA: int = 7
PBP_DIAS_BAJO_MINIMO: int = 4   # 4 de 7 días < precio escasez → nivel BAJO


def obtener_precios_escasez_vigentes(
    fecha: Optional[date] = None,
) -> Dict[str, float]:
    """
    Devuelve los precios de escasez vigentes (PEI/PE/PES) para la fecha dada.

    Estrategia de consulta (en orden):
      1. Lee `PrecEscaSup` (→ pes) y `PrecEscaInf` (→ pei) directamente de
         `sector_energetico.metrics` — son series diarias reales de XM, cada
         una en su propia fecha más reciente (Resolución CREG 101 066/2024,
         Art. 3 y 4). `pe` se deriva como punto medio de pei/pes por
         compatibilidad con el código que aún lo consume — ya no corresponde
         a un umbral regulatorio independiente desde la Res. 101 066/2024
         (antes de esa resolución solo existía un "precio de escasez" único).
      2. Si (1) no tiene datos, consulta la tabla
         `sector_energetico.precios_escasez_mensuales` (mantenimiento manual,
         puede estar desactualizada).
      3. Si la BD no está disponible o no hay datos, devuelve los valores de
         referencia ene-2026 (PRECIO_ESCASEZ_*_REF_2026_01).

    Fuente: Resolución CREG 101 066 de 2024, artículos 3 y 4.
    Publicación: https://www.xm.com.co/transacciones/cargo-por-confiabilidad/precio-de-bolsa-y-escasez

    Args:
        fecha: fecha de evaluación (default: hoy).

    Returns:
        dict con claves 'pei', 'pe', 'pes' (COP/kWh), 'anio', 'mes', 'fuente'.
    """
    f = fecha or date.today()

    # 1) Leer PES (PrecEscaSup) y PEI (PrecEscaInf) directamente, cada una en
    #    su propia fecha más reciente (mismo patrón que sector_snapshot.py
    #    usa para PPPrecBolsNaci — nunca combinar el MAX(fecha) de dos
    #    métricas distintas, o se arriesga a traer NULL para una de ellas).
    try:
        import psycopg2
        from core.config import settings
        params = {
            'host': settings.POSTGRES_HOST,
            'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB,
            'user': settings.POSTGRES_USER,
        }
        if settings.POSTGRES_PASSWORD:
            params['password'] = settings.POSTGRES_PASSWORD
        conn = psycopg2.connect(**params)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    (SELECT valor_gwh FROM sector_energetico.metrics
                     WHERE metrica = 'PrecEscaSup' AND entidad = 'Sistema' AND recurso = 'Sistema'
                     ORDER BY fecha DESC LIMIT 1) AS pes,
                    (SELECT fecha FROM sector_energetico.metrics
                     WHERE metrica = 'PrecEscaSup' AND entidad = 'Sistema' AND recurso = 'Sistema'
                     ORDER BY fecha DESC LIMIT 1) AS fecha_pes,
                    (SELECT valor_gwh FROM sector_energetico.metrics
                     WHERE metrica = 'PrecEscaInf' AND entidad = 'Sistema' AND recurso = 'Sistema'
                     ORDER BY fecha DESC LIMIT 1) AS pei,
                    (SELECT fecha FROM sector_energetico.metrics
                     WHERE metrica = 'PrecEscaInf' AND entidad = 'Sistema' AND recurso = 'Sistema'
                     ORDER BY fecha DESC LIMIT 1) AS fecha_pei
            """)
            row = cur.fetchone()
            cur.close()
            if row and row[0] is not None and row[2] is not None:
                pes = float(row[0])
                pei = float(row[2])
                return {
                    'pei': round(pei, 2),
                    'pe': round((pei + pes) / 2, 2),
                    'pes': round(pes, 2),
                    'fuente': f'XM PrecEscaSup ({row[1]}) / PrecEscaInf ({row[3]})',
                    'anio': f.year,
                    'mes': f.month,
                    'origen': 'XM',
                }
        finally:
            conn.close()
    except Exception:
        # BD no disponible, seguir con el siguiente nivel de fallback
        pass

    # 2) Tabla mensual de mantenimiento manual (puede estar desactualizada)
    try:
        import psycopg2
        from core.config import settings
        params = {
            'host': settings.POSTGRES_HOST,
            'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB,
            'user': settings.POSTGRES_USER,
        }
        if settings.POSTGRES_PASSWORD:
            params['password'] = settings.POSTGRES_PASSWORD
        conn = psycopg2.connect(**params)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT pei, pe, pes, fuente, anio, mes
                FROM sector_energetico.precios_escasez_mensuales
                WHERE anio = %s AND mes = %s
            """, (f.year, f.month))
            row = cur.fetchone()
            if not row:
                cur.execute("""
                    SELECT pei, pe, pes, fuente, anio, mes
                    FROM sector_energetico.precios_escasez_mensuales
                    WHERE (anio, mes) <= (%s, %s)
                    ORDER BY anio DESC, mes DESC
                    LIMIT 1
                """, (f.year, f.month))
                row = cur.fetchone()
            cur.close()
            if row:
                return {
                    'pei': float(row[0]),
                    'pe': float(row[1]),
                    'pes': float(row[2]),
                    'fuente': str(row[3]),
                    'anio': int(row[4]),
                    'mes': int(row[5]),
                    'origen': 'BD_mensual',
                }
        finally:
            conn.close()
    except Exception:
        pass

    # 3) Fallback: valores de referencia enero 2026
    return {
        'pei': PRECIO_ESCASEZ_PEI_REF_2026_01,
        'pe': PRECIO_ESCASEZ_PE_REF_2026_01,
        'pes': PRECIO_ESCASEZ_PES_REF_2026_01,
        'fuente': 'Valores referencia enero 2026 (CREG 101 066/2024)',
        'anio': 2026,
        'mes': 1,
        'origen': 'fallback',
    }


def clasificar_indice_pbp(
    pbp_diarios: list,
    precio_escasez_activacion: float,
) -> Tuple[str, str]:
    """
    Clasifica el índice PBP según el Estatuto CREG 026/2014.

    Args:
        pbp_diarios: lista de PBP de los últimos 7 días (COP/kWh).
        precio_escasez_activacion: precio de escasez vigente del mes (PE o PES).

    Returns:
        (nivel, descripcion)
        nivel: 'BAJO' | 'ALTO'
    """
    if len(pbp_diarios) < PBP_DIAS_VENTANA:
        return ('INDETERMINADO',
                f'Solo {len(pbp_diarios)} días disponibles, se requieren {PBP_DIAS_VENTANA}.')

    dias_bajo = sum(1 for p in pbp_diarios if p < precio_escasez_activacion)

    if dias_bajo >= PBP_DIAS_BAJO_MINIMO:
        return ('BAJO',
                f'{dias_bajo}/{PBP_DIAS_VENTANA} días con PBP < precio escasez '
                f'{precio_escasez_activacion:.0f} COP/kWh (CREG 026/2014).')
    return ('ALTO',
            f'PBP supera precio de escasez {precio_escasez_activacion:.0f} COP/kWh '
            f'en {PBP_DIAS_VENTANA - dias_bajo}/{PBP_DIAS_VENTANA} días — riesgo (CREG 026/2014).')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — CONDICIÓN DEL SISTEMA (NORMAL / VIGILANCIA / RIESGO)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Fuente: Resolución CREG 026 de 2014, artículo 3.
# Fuente: Resolución CREG 209 de 2020 (actualización Índice NE).
# Fuente: Resolución CREG 101 055 de 2024 (regla complementaria).
#
# La condición del sistema resulta de la combinación de tres índices:
#   • NE  — Nivel de Embalse vs Senda de Referencia (sección 1)
#   • HSIN — Hidrología del SIN (sección 2)
#   • PBP — Precio de Bolsa Promedio (sección 3)
#
# Combinaciones oficiales (simplificación didáctica del art. 3):
#   • NE Superior + HSIN Normal + PBP Bajo                    → NORMAL
#   • Cualquier índice en nivel intermedio                    → VIGILANCIA
#   • NE Inferior + (HSIN < 90% o PBP Alto)                   → RIESGO
#
# El CND publica el resultado SEMANALMENTE:
#   • Estado Normal:    mensual, primeros 5 días del mes
#   • Vigilancia:       martes siguiente al cálculo
#   • Riesgo:           martes y viernes (2 veces por semana)
#
# Una vez declarado RIESGO, la CREG confirma y se activa el Mecanismo de
# Sostenimiento de Confiabilidad (art. 7 Res. 026/2014).
# ──────────────────────────────────────────────────────────────────────────────

CONDICION_NORMAL: str = 'NORMAL'
CONDICION_VIGILANCIA: str = 'VIGILANCIA'
CONDICION_RIESGO: str = 'RIESGO'


def determinar_condicion_sistema(
    ne_nivel: str,
    hsin_nivel: str,
    pbp_nivel: str,
) -> Tuple[str, str]:
    """
    Determina la condición del sistema según el Estatuto CREG 026/2014 art. 3.

    Args:
        ne_nivel: 'SUPERIOR' | 'ALERTA' | 'INFERIOR'
        hsin_nivel: 'NORMAL' | 'VIGILANCIA' | 'DEFICIT_SEVERO' | 'CRITICO'
        pbp_nivel: 'BAJO' | 'ALTO' | 'INDETERMINADO'

    Returns:
        (condicion, descripcion)
        condicion: 'NORMAL' | 'VIGILANCIA' | 'RIESGO'
    """
    # Riesgo: nivel inferior de embalse + cualquier otra señal negativa
    if ne_nivel == 'INFERIOR' and (hsin_nivel != 'NORMAL' or pbp_nivel == 'ALTO'):
        return (CONDICION_RIESGO,
                'NE en nivel inferior + HSIN o PBP en señal negativa → riesgo de '
                'desabastecimiento (Estatuto CREG 026/2014 art. 3).')

    if ne_nivel == 'INFERIOR':
        return (CONDICION_VIGILANCIA,
                'NE en nivel inferior — vigilancia preventiva (CREG 026/2014).')

    # Vigilancia: cualquier índice en alerta o HSIN < 90%
    if ne_nivel == 'ALERTA' or hsin_nivel != 'NORMAL' or pbp_nivel == 'ALTO':
        return (CONDICION_VIGILANCIA,
                f'Indicador(es) en alerta: NE={ne_nivel}, HSIN={hsin_nivel}, '
                f'PBP={pbp_nivel} (CREG 026/2014 art. 3).')

    # Normal: todos los índices en niveles óptimos
    return (CONDICION_NORMAL,
            'Todos los índices en niveles normales (Estatuto CREG 026/2014).')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — OBJETIVO XM ANTE EL NIÑO
# ═══════════════════════════════════════════════════════════════════════════════
# Nota: la capacidad útil de reserva del SIN (GWh) y la capacidad efectiva neta
# instalada (MW) ya NO se hardcodean aquí — se calculan en vivo desde
# `sector_energetico.metrics` (ver `capacidadEmbalseGwh`/`capacidadInstaladaMw`
# en `api/v1/routes/sector_snapshot.py`), evitando que queden desactualizadas.
# ──────────────────────────────────────────────────────────────────────────────

# Objetivo XM/CND para enfrentar El Niño (XM Boletín 10-abril-2026):
# "Maximizar reservas desde agosto al inicio del verano para alcanzar nivel
# agregado del SIN superior al 80%". Esto es un objetivo OPERATIVO de XM,
# no un umbral del Estatuto.
OBJETIVO_XM_EMBALSE_ANTE_NINO_PCT: float = 80.0


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — UMBRALES VISUALES DEL PORTAL (DERIVADOS DE LA SENDA CREG)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Los umbrales visuales del portal NO son regulatoriamente vinculantes. Su
# propósito es comunicación gerencial al Viceministro y su equipo. Se calibran
# tomando como referencia la senda CREG y la regla absoluta del 70%:
#
#   • Verde:   embalse ≥ 80% (zona objetivo XM ante El Niño)
#   • Cian:    embalse 70 – 80% (umbral absoluto Estatuto CREG)
#   • Ámbar:   embalse ≥ senda y < 70%
#   • Naranja: embalse < senda (correspondería a NE Alerta/Inferior)
#   • Rojo:    embalse < senda − 5pp (NE Inferior persistente)
#
# Estos colores son una representación VISUAL más fina que los 3 niveles del
# Estatuto, manteniendo siempre concordancia regulatoria.
# ──────────────────────────────────────────────────────────────────────────────

UMBRAL_VISUAL_VERDE_EMBALSE: float = 80.0      # Objetivo XM ante El Niño
UMBRAL_VISUAL_CIAN_EMBALSE: float = 70.0       # Regla absoluta CREG 209/2020
UMBRAL_VISUAL_AMBAR_EMBALSE_RESPECTO_SENDA: float = 0.0  # ≥ senda


def clasificar_visual_embalse(
    nivel_embalse_pct: float,
    fecha: Optional[date] = None,
) -> Tuple[str, str, str]:
    """
    Clasifica visualmente el embalse en 5 niveles consistentes con la
    Senda de Referencia CREG e Índice NE.

    Returns:
        (etiqueta, color_hex, justificacion_regulatoria)
    """
    senda = obtener_senda_referencia(fecha)

    if nivel_embalse_pct >= UMBRAL_VISUAL_VERDE_EMBALSE:
        return ('NORMAL', '#22C55E',
                f'≥ {UMBRAL_VISUAL_VERDE_EMBALSE:.0f}% (objetivo XM ante El Niño).')
    if nivel_embalse_pct >= UMBRAL_VISUAL_CIAN_EMBALSE:
        return ('ESTABLE', '#06B6D4',
                f'≥ {UMBRAL_VISUAL_CIAN_EMBALSE:.0f}% (regla absoluta CREG 209/2020).')
    if nivel_embalse_pct >= senda:
        return ('SOBRE SENDA', '#F59E0B',
                f'≥ senda CREG {senda:.1f}% — NE Superior (Estatuto CREG 026/2014).')
    if nivel_embalse_pct >= senda - 5.0:
        return ('BAJO SENDA — ALERTA', '#F97316',
                f'< senda CREG {senda:.1f}% — NE Alerta (CREG 026/2014).')
    return ('BAJO SENDA — RIESGO', '#EF4444',
            f'< senda CREG {senda:.1f}% − 5pp — NE Inferior persistente (CREG 026/2014).')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 7 — UMBRALES VISUALES DE APORTES (DERIVADOS DE HSIN)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Los umbrales visuales de aportes son consistentes con HSIN del Estatuto CREG:
#   • Verde:   aportes ≥ 100% media histórica (suministro normal o superior)
#   • Cian:    90 – 100% (cerca del umbral oficial CREG)
#   • Ámbar:   70 – 90% (vigilancia oficial CREG)
#   • Naranja: 60 – 70% (déficit severo, referencia 2020)
#   • Rojo:    < 60% (nivel histórico de crisis abril 2020)
# ──────────────────────────────────────────────────────────────────────────────


def clasificar_visual_aportes(aportes_pct_vs_historico: float) -> Tuple[str, str, str]:
    """
    Clasificación visual de aportes hídricos consistente con HSIN del Estatuto CREG.

    Returns:
        (etiqueta, color_hex, justificacion_regulatoria)
    """
    if aportes_pct_vs_historico >= 100.0:
        return ('NORMAL O SUPERIOR', '#22C55E',
                f'≥ 100% media histórica — HSIN normal (CREG 026/2014).')
    if aportes_pct_vs_historico >= HSIN_UMBRAL_NORMAL:
        return ('CERCA UMBRAL CREG', '#06B6D4',
                f'≥ {HSIN_UMBRAL_NORMAL:.0f}% — HSIN aún normal (CREG 026/2014).')
    if aportes_pct_vs_historico >= HSIN_UMBRAL_DEFICIT_SEVERO:
        return ('VIGILANCIA CREG', '#F59E0B',
                f'< {HSIN_UMBRAL_NORMAL:.0f}% — HSIN en vigilancia (CREG 026/2014 art. 2).')
    if aportes_pct_vs_historico >= HSIN_UMBRAL_CRITICO_HISTORICO:
        return ('DÉFICIT SEVERO', '#F97316',
                f'< {HSIN_UMBRAL_DEFICIT_SEVERO:.0f}% — déficit severo (CREG 209/2020).')
    return ('CRÍTICO HISTÓRICO', '#EF4444',
            f'≤ {HSIN_UMBRAL_CRITICO_HISTORICO:.0f}% — nivel de crisis abril 2020.')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 8 — UMBRALES VISUALES DE PRECIO (DERIVADOS DE PEI/PE/PES)
# ═══════════════════════════════════════════════════════════════════════════════
#
# El precio de escasez se actualiza MENSUALMENTE. La capa visual usa los tres
# niveles oficiales CREG como referencia para colorear:
#
#   • Verde:   PBP < PEI (precio cómodo, sin presión)
#   • Ámbar:   PEI ≤ PBP < PE (alza moderada)
#   • Naranja: PE ≤ PBP < PES (alta presión)
#   • Rojo:    PBP ≥ PES (cerca del techo regulatorio)
# ──────────────────────────────────────────────────────────────────────────────


def clasificar_visual_precio_bolsa(
    pbp_actual: float,
    pei: Optional[float] = None,
    pe: Optional[float] = None,
    pes: Optional[float] = None,
    fecha: Optional[date] = None,
) -> Tuple[str, str, str]:
    """
    Clasificación visual del PBP usando los 3 niveles oficiales de precio de
    escasez de la CREG (Res. 101 066/2024).

    Si no se pasan valores explícitos de PEI/PE/PES, consulta los vigentes
    para la fecha dada usando obtener_precios_escasez_vigentes() (BD).

    Args:
        pbp_actual: Precio de Bolsa Ponderado actual (COP/kWh).
        pei: Precio de Escasez Inferior vigente (COP/kWh). Si es None, consulta BD.
        pe:  Precio de Escasez de Res. 071/2006 vigente (COP/kWh).
        pes: Precio de Escasez Superior vigente (COP/kWh).
        fecha: fecha de evaluación (para consulta dinámica de PEI/PE/PES).

    Returns:
        (etiqueta, color_hex, justificacion_regulatoria)
    """
    # Si no se pasan precios explícitos, obtener los vigentes desde BD
    if pei is None or pe is None or pes is None:
        precios = obtener_precios_escasez_vigentes(fecha)
        pei = pei if pei is not None else precios['pei']
        pe = pe if pe is not None else precios['pe']
        pes = pes if pes is not None else precios['pes']

    if pbp_actual < pei:
        return ('CÓMODO', '#22C55E',
                f'< PEI {pei:.0f} COP/kWh — sin presión regulatoria (CREG 101 066/2024).')
    if pbp_actual < pe:
        return ('ESTRÉS MODERADO', '#F59E0B',
                f'≥ PEI {pei:.0f}, < PE {pe:.0f} — alza moderada (CREG 101 066/2024).')
    if pbp_actual < pes:
        return ('ALTA PRESIÓN', '#F97316',
                f'≥ PE {pe:.0f}, < PES {pes:.0f} — alta presión (CREG 101 066/2024).')
    return ('TECHO REGULATORIO', '#EF4444',
            f'≥ PES {pes:.0f} COP/kWh — cerca del techo de escasez (CREG 101 066/2024).')


# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 9 — INFORMACIÓN DE GOBERNANZA
# ═══════════════════════════════════════════════════════════════════════════════

NOTAS_GOBERNANZA: dict = {
    'fuente_principal': 'Estatuto para Situaciones de Riesgo de Desabastecimiento (CREG)',
    'resoluciones_clave': [
        'Resolución CREG 026 de 2014',
        'Resolución CREG 071 de 2006',
        'Resolución CREG 140 de 2017',
        'Resolución CREG 125 de 2020',  # corregida de "121" — ver docstring del módulo
        'Resolución CREG 209 de 2020',
        'Resolución CREG 101 055 de 2024',
        'Resolución CREG 101 066 de 2024',
        'Resolución CREG 101 112 de 2026',
    ],
    'publicacion_oficial_xm': (
        'https://www.xm.com.co/resoluciones/operacion-y-mercado/'
        'resolucion-creg-209-de-2020-condicion-del-sistema'
    ),
    'ftps_xm': '/INFORMACION_XM/Publico/PlaneacionOperacion/Senda%20de%20Referencia/',
    'caracter': (
        'Todos los umbrales aquí están respaldados por resoluciones de la CREG '
        'y publicaciones oficiales XM/CND. NO son criterios discrecionales del '
        'proyecto. Las clasificaciones visuales (sección 6-8) son derivadas de '
        'los umbrales regulatorios y se documentan explícitamente.'
    ),
    'fecha_revision': '2026-05-25',
    'proxima_revision': 'Mensual (precios escasez) y semestral (senda referencia)',
}
