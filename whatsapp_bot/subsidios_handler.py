#!/usr/bin/env python3
"""
Módulo de Subsidios para el Telegram Bot.
Responde las 9 preguntas de Diana con consultas directas a PostgreSQL.
SIN IA — solo datos de la base de datos.

Comandos:
  /subsidios       → Menú de subsidios
  /deuda           → ¿Cuánto se debe a hoy?
  /deuda_empresa   → ¿Cuánto se le debe a empresa X?
  /trimestre_pagado→ ¿Hasta qué trimestre está pagado?
  /resoluciones    → ¿Cuántas resoluciones en un año?
  /estado_resoluciones → Resoluciones pagadas vs pendientes
  /porcentaje_pagado   → % pagado de resoluciones asignadas
  /deuda_fondo     → Deuda por FSSRI y FOES por empresa
  /pagado_anio     → Valor pagado en un año
"""
import logging

import psycopg2
import psycopg2.extras

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ─── DB ───────────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(
        dbname='portal_energetico',
        user='postgres',
        host='localhost',
        port=5432,
    )


def _query(sql: str, params=None):
    """Ejecuta SQL y retorna lista de dicts."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def _scalar(sql: str, params=None):
    """Retorna un solo valor."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


# ─── Authorization ────────────────────────────────────────────────────────────

def _is_authorized(telegram_id: int) -> bool:
    """Verifica si el usuario está autorizado en subsidios_usuarios_autorizados."""
    count = _scalar(
        "SELECT COUNT(*) FROM subsidios_usuarios_autorizados WHERE telegram_id = %s AND activo = TRUE",
        (telegram_id,)
    )
    return count is not None and count > 0


def _audit(telegram_id: int, nombre: str, comando: str, parametros: str = None):
    """Registra auditoría de consulta."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subsidios_audit_log (telegram_id, nombre_usuario, comando, parametros) VALUES (%s, %s, %s, %s)",
                (telegram_id, nombre, comando, parametros)
            )
        conn.commit()
    except Exception as e:
        logger.error(f"Error audit: {e}")
    finally:
        conn.close()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_money(val) -> str:
    """Formatea valor en pesos colombianos resumido."""
    if val is None or val == 0:
        return "$0"
    v = float(val)
    if abs(v) >= 1e12:
        return f"${v/1e12:,.2f} billones"
    if abs(v) >= 1e9:
        return f"${v/1e9:,.2f} mil millones"
    if abs(v) >= 1e6:
        return f"${v/1e6:,.2f} millones"
    return f"${v:,.0f}"


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{float(val):.1f}%"


def _user_name(user) -> str:
    """Nombre del usuario para audit."""
    parts = []
    if user.first_name:
        parts.append(user.first_name)
    if user.last_name:
        parts.append(user.last_name)
    return ' '.join(parts) or (user.username or str(user.id))


def _menu_kb():
    """Teclado del menú de subsidios."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Deuda total", callback_data="sub:deuda"),
         InlineKeyboardButton("🏢 Deuda empresa", callback_data="sub:deuda_empresa")],
        [InlineKeyboardButton("📅 Trimestre pagado", callback_data="sub:trimestre"),
         InlineKeyboardButton("📊 Resoluciones/año", callback_data="sub:resoluciones")],
        [InlineKeyboardButton("✅ Pagadas vs Pend.", callback_data="sub:estado_res"),
         InlineKeyboardButton("📈 % Pagado", callback_data="sub:pct_pagado")],
        [InlineKeyboardButton("🏦 Deuda FSSRI/FOES", callback_data="sub:deuda_fondo"),
         InlineKeyboardButton("💵 Pagado por año", callback_data="sub:pagado_anio")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")],
    ])


def _back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Menú subsidios", callback_data="sub:menu"),
         InlineKeyboardButton("🏠 Menú principal", callback_data="intent:menu")],
    ])


NOT_AUTH_MSG = (
    "🔒 *Acceso restringido*\n\n"
    "No tienes autorización para consultar información de subsidios.\n"
    "Contacta al administrador para solicitar acceso."
)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 1: ¿Cuánto se debe a hoy? (total, SIN, ZNI, FOES)
# ═══════════════════════════════════════════════════════════════════════════════

def q_deuda_total() -> str:
    # Obtener todos los fondos y áreas que existen en la base de datos
    all_combos = _query("""
        SELECT DISTINCT
            fondo,
            CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area
        FROM subsidios_pagos
        WHERE fondo IS NOT NULL
        ORDER BY fondo, area
    """)

    # Obtener deuda pendiente por fondo/area
    rows = _query("""
        SELECT
            fondo,
            CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
            SUM(saldo_pendiente) as deuda,
            COUNT(DISTINCT no_resolucion) as resoluciones
        FROM subsidios_pagos
        WHERE estado_pago = 'Pendiente'
        GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
        ORDER BY fondo, area
    """)

    # Indexar resultados de deuda
    deuda_map = {}
    for r in rows:
        key = (r['fondo'], r['area'])
        deuda_map[key] = {'deuda': r['deuda'], 'resoluciones': r['resoluciones']}

    total = sum(r['deuda'] for r in rows)
    total_res = sum(r['resoluciones'] for r in rows)
    fecha = _scalar("SELECT MAX(fecha_actualizacion) FROM subsidios_pagos")
    fecha_str = fecha.strftime('%d/%m/%Y') if fecha else 'N/A'

    lines = [
        f"💰 *DEUDA TOTAL DE SUBSIDIOS*",
        f"📅 Corte: {fecha_str}",
        f"",
        f"*Total pendiente: {_fmt_money(total)}*",
        f"({total_res} resoluciones pendientes)",
        f"",
        f"*Desglose por fondo y área:*",
    ]

    # Agrupar todos los combos por fondo (incluyendo los con deuda $0)
    by_fondo = {}
    for combo in all_combos:
        f = combo['fondo']
        a = combo['area']
        if f not in by_fondo:
            by_fondo[f] = {}
        data = deuda_map.get((f, a), {'deuda': 0, 'resoluciones': 0})
        by_fondo[f][a] = data

    for fondo in sorted(by_fondo.keys()):
        areas = by_fondo[fondo]
        total_fondo = sum(v['deuda'] for v in areas.values())
        res_fondo = sum(v['resoluciones'] for v in areas.values())
        lines.append(f"\n🏦 *{fondo}*: {_fmt_money(total_fondo)} ({res_fondo} res.)")
        for area in sorted(areas.keys()):
            val = areas[area]['deuda']
            res = areas[area]['resoluciones']
            emoji = "🔌" if area == "SIN" else "🏝️" if area == "ZNI" else "📌"
            lines.append(f"   {emoji} {area}: {_fmt_money(val)} ({res} res.)")

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 2: ¿Cuánto se le debe a empresa X?
# ═══════════════════════════════════════════════════════════════════════════════

def q_deuda_empresa(nombre: str = None) -> str:
    if nombre:
        # Buscar empresa específica con detalle (ignora guiones/puntos)
        clean_name = nombre.lower().replace('-', '').replace('.', '')
        rows = _query("""
            SELECT nombre_prestador, fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(saldo_pendiente) as deuda,
                   COUNT(DISTINCT no_resolucion) as resoluciones,
                   MIN(concepto_trimestre) as trim_desde,
                   MAX(concepto_trimestre) as trim_hasta
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
              AND (LOWER(nombre_prestador) LIKE %s
                   OR LOWER(REPLACE(REPLACE(nombre_prestador, '-', ''), '.', '')) LIKE %s)
            GROUP BY nombre_prestador, fondo,
                     CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY deuda DESC
        """, (f'%{nombre.lower()}%', f'%{clean_name}%'))

        if not rows:
            return f"ℹ️ No se encontró deuda pendiente para *'{nombre}'*.\n\nIntenta con parte del nombre."

        lines = [f"🏢 *DEUDA POR EMPRESA*\n"]
        current = None
        for r in rows:
            if r['nombre_prestador'] != current:
                current = r['nombre_prestador']
                total_empresa = sum(x['deuda'] for x in rows if x['nombre_prestador'] == current)
                total_res = sum(x['resoluciones'] for x in rows if x['nombre_prestador'] == current)
                lines.append(f"*{current}*")
                lines.append(f"  💰 Total pendiente: {_fmt_money(total_empresa)} ({total_res} res.)")
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            periodo = f"{r['trim_desde']}" if r['trim_desde'] == r['trim_hasta'] else f"{r['trim_desde']} → {r['trim_hasta']}"
            lines.append(f"  • 🏦 {r['fondo']} / {emoji} {r['area']}")
            lines.append(f"    {_fmt_money(r['deuda'])} ({r['resoluciones']} res.) | Periodo: {periodo}")
        return '\n'.join(lines)
    else:
        # Resumen general: total empresas, desglose, top 3
        total_empresas = _scalar("""
            SELECT COUNT(DISTINCT nombre_prestador)
            FROM subsidios_pagos WHERE estado_pago = 'Pendiente'
        """) or 0

        if total_empresas == 0:
            return "✅ No hay deuda pendiente con ninguna empresa."

        total_deuda = _scalar("""
            SELECT SUM(saldo_pendiente) FROM subsidios_pagos WHERE estado_pago = 'Pendiente'
        """) or 0

        # Desglose por fondo/área
        desglose = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   COUNT(DISTINCT nombre_prestador) as empresas,
                   SUM(saldo_pendiente) as deuda
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY deuda DESC
        """)

        # Top 3 empresas con detalle
        top3 = _query("""
            SELECT nombre_prestador, fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(saldo_pendiente) as deuda,
                   COUNT(DISTINCT no_resolucion) as resoluciones,
                   MIN(concepto_trimestre) as trim_desde,
                   MAX(concepto_trimestre) as trim_hasta
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
            GROUP BY nombre_prestador, fondo,
                     CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY deuda DESC
            LIMIT 3
        """)

        lines = [
            f"🏢 *DEUDA PENDIENTE POR EMPRESA*\n",
            f"📊 Se le debe a *{total_empresas} empresas*",
            f"💰 Total adeudado: {_fmt_money(total_deuda)}\n",
            f"*Distribución por fondo/área:*",
        ]
        for r in desglose:
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            lines.append(f"  🏦 {r['fondo']} / {emoji} {r['area']}: {r['empresas']} empresas — {_fmt_money(r['deuda'])}")

        lines.append(f"\n*Top 3 mayores deudas:*")
        for i, r in enumerate(top3, 1):
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            periodo = f"{r['trim_desde']}" if r['trim_desde'] == r['trim_hasta'] else f"{r['trim_desde']} → {r['trim_hasta']}"
            lines.append(f"\n{i}. *{r['nombre_prestador']}*")
            lines.append(f"   {_fmt_money(r['deuda'])} ({r['resoluciones']} res.)")
            lines.append(f"   🏦 {r['fondo']} / {emoji} {r['area']} | Periodo: {periodo}")

        lines.append(f"\n✏️ *Escribe el nombre de la empresa* para ver su deuda detallada.")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 3: ¿Hasta qué trimestre está pagado?
# ═══════════════════════════════════════════════════════════════════════════════

def q_trimestre_pagado(nombre: str = None) -> str:
    from collections import defaultdict
    if nombre:
        clean_name = nombre.lower().replace('-', '').replace('.', '')
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   concepto_trimestre, estado_pago,
                   COUNT(DISTINCT no_resolucion) as n
            FROM subsidios_pagos
            WHERE LOWER(nombre_prestador) LIKE %s
               OR LOWER(REPLACE(REPLACE(nombre_prestador, '-', ''), '.', '')) LIKE %s
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END,
                     concepto_trimestre, estado_pago
            ORDER BY concepto_trimestre DESC
        """, (f'%{nombre.lower()}%', f'%{clean_name}%'))

        if not rows:
            return f"ℹ️ No se encontraron datos para *'{nombre}'*."

        # Agrupar por fondo/area → trimestre → estado
        fa_trims = defaultdict(lambda: defaultdict(lambda: {'Pagado': 0, 'Pendiente': 0}))
        for r in rows:
            key = (r['fondo'], r['area'])
            fa_trims[key][r['concepto_trimestre']][r['estado_pago']] += r['n']

        lines = [f"📅 *TRIMESTRES PAGADOS*\nEmpresa: *{nombre}*\n"]
        for (fondo, area), trims in sorted(fa_trims.items()):
            emoji = "🔌" if area == "SIN" else "🏝️" if area == "ZNI" else "📌"
            lines.append(f"🏦 *{fondo}* / {emoji} *{area}*")
            for trim in sorted(trims.keys(), reverse=True)[:8]:
                pag = trims[trim].get('Pagado', 0)
                pen = trims[trim].get('Pendiente', 0)
                status = "✅" if pen == 0 and pag > 0 else "⏳" if pen > 0 else "❔"
                lines.append(f"  {status} {trim}: {pag} pagadas, {pen} pendientes")
            lines.append("")
        return '\n'.join(lines)

    else:
        # Vista general por fondo/área
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   concepto_trimestre,
                   COUNT(DISTINCT CASE WHEN estado_pago = 'Pagado' THEN no_resolucion END) as pagadas,
                   COUNT(DISTINCT CASE WHEN estado_pago = 'Pendiente' THEN no_resolucion END) as pendientes,
                   COUNT(DISTINCT no_resolucion) as total
            FROM subsidios_pagos
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END,
                     concepto_trimestre
            ORDER BY fondo, area, concepto_trimestre DESC
        """)

        # Agrupar por fondo/area
        fa_data = defaultdict(list)
        for r in rows:
            fa_data[(r['fondo'], r['area'])].append(r)

        lines = [f"📅 *ESTADO DE PAGO POR TRIMESTRE*\n"]
        for (fondo, area), trims in sorted(fa_data.items()):
            emoji = "🔌" if area == "SIN" else "🏝️" if area == "ZNI" else "📌"
            ultimo_completo = None
            for t in trims:
                if t['pendientes'] == 0 and t['pagadas'] > 0 and ultimo_completo is None:
                    ultimo_completo = t['concepto_trimestre']
            lines.append(f"🏦 *{fondo}* / {emoji} *{area}*")
            if ultimo_completo:
                lines.append(f"  ✅ Último 100% pagado: *{ultimo_completo}*")
            for t in trims[:6]:  # últimos 6 trimestres
                status = "✅" if t['pendientes'] == 0 and t['pagadas'] > 0 else "⏳"
                lines.append(f"  {status} {t['concepto_trimestre']}: {t['pagadas']} pagadas, {t['pendientes']} pendientes")
            lines.append("")

        lines.append(f"💡 Para una empresa específica:")
        lines.append(f"`/trimestre_pagado nombre`")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 4: ¿Cuántas resoluciones en un año?
# ═══════════════════════════════════════════════════════════════════════════════

def q_resoluciones_anio(anio: int = None) -> str:
    if anio:
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   COUNT(DISTINCT no_resolucion) as n,
                   SUM(valor_resolucion) as valor
            FROM subsidios_pagos
            WHERE anio = %s
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY fondo, area
        """, (anio,))

        total_res = sum(r['n'] for r in rows)
        total_val = sum(r['valor'] for r in rows)
        lines = [
            f"📊 *RESOLUCIONES AÑO {anio}*\n",
            f"Total: *{total_res}* resoluciones",
            f"Valor total: {_fmt_money(total_val)}\n",
        ]
        for r in rows:
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            lines.append(f"• 🏦 {r['fondo']} / {emoji} {r['area']}: {r['n']} res. ({_fmt_money(r['valor'])})")
        return '\n'.join(lines)
    else:
        rows = _query("""
            SELECT anio, COUNT(DISTINCT no_resolucion) as n,
                   SUM(valor_resolucion) as valor
            FROM subsidios_pagos
            GROUP BY anio
            ORDER BY anio DESC
        """)

        lines = [f"📊 *RESOLUCIONES POR AÑO*\n"]
        for r in rows:
            lines.append(f"*{r['anio']}*: {r['n']} resoluciones ({_fmt_money(r['valor'])})")

        lines.append(f"\n💡 Para un año específico:")
        lines.append(f"`/resoluciones 2024`")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 5: ¿Cuántas resoluciones pagadas vs pendientes?
# ═══════════════════════════════════════════════════════════════════════════════

def q_estado_resoluciones() -> str:
    # Rango de periodos
    periodo_min = _scalar("SELECT MIN(concepto_trimestre) FROM subsidios_pagos")
    periodo_max = _scalar("SELECT MAX(concepto_trimestre) FROM subsidios_pagos")
    fecha = _scalar("SELECT MAX(fecha_actualizacion) FROM subsidios_pagos")
    fecha_str = fecha.strftime('%d/%m/%Y') if fecha else 'N/A'

    # Resumen general
    resumen = _query("""
        SELECT estado_pago,
               COUNT(DISTINCT no_resolucion) as resoluciones,
               SUM(valor_resolucion) as valor_res,
               SUM(valor_pagado) as valor_pag,
               SUM(saldo_pendiente) as saldo
        FROM subsidios_pagos
        GROUP BY estado_pago
        ORDER BY estado_pago
    """)

    total_res = sum(r['resoluciones'] for r in resumen)
    pagado_data = next((r for r in resumen if r['estado_pago'] == 'Pagado'), None)
    pendiente_data = next((r for r in resumen if r['estado_pago'] == 'Pendiente'), None)

    n_pagado = pagado_data['resoluciones'] if pagado_data else 0
    v_pagado = pagado_data['valor_pag'] if pagado_data else 0
    n_pendiente = pendiente_data['resoluciones'] if pendiente_data else 0
    v_pendiente = pendiente_data['saldo'] if pendiente_data else 0

    pct_pagado = (n_pagado / total_res * 100) if total_res else 0
    pct_pendiente = (n_pendiente / total_res * 100) if total_res else 0

    lines = [
        f"📊 *ESTADO DE RESOLUCIONES*",
        f"📅 Corte: {fecha_str} | Periodo: {periodo_min} → {periodo_max}\n",
        f"De {total_res:,} resoluciones únicas registradas:\n",
        f"✅ *Pagadas:* {n_pagado:,} ({pct_pagado:.1f}%)",
        f"   Total pagado: {_fmt_money(v_pagado)}\n",
        f"⏳ *Pendientes:* {n_pendiente:,} ({pct_pendiente:.1f}%)",
        f"   Total adeudado: {_fmt_money(v_pendiente)}\n",
    ]

    # Desglose por fondo/área con periodo
    desglose = _query("""
        SELECT
            fondo,
            CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
            estado_pago,
            SUM(saldo_pendiente) as deuda,
            SUM(valor_pagado) as pagado,
            COUNT(DISTINCT no_resolucion) as n,
            MIN(concepto_trimestre) as desde,
            MAX(concepto_trimestre) as hasta
        FROM subsidios_pagos
        GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END, estado_pago
        ORDER BY fondo, area, estado_pago
    """)

    from collections import defaultdict
    fa_map = defaultdict(dict)
    for r in desglose:
        fa_map[(r['fondo'], r['area'])][r['estado_pago']] = r

    lines.append(f"*Detalle por fondo/área:*")
    for (fondo, area), estados in sorted(fa_map.items()):
        emoji = "🔌" if area == "SIN" else "🏝️" if area == "ZNI" else "📌"
        lines.append(f"\n🏦 *{fondo}* / {emoji} *{area}*")
        for estado in ['Pagado', 'Pendiente']:
            if estado in estados:
                r = estados[estado]
                icon = "✅" if estado == 'Pagado' else "⏳"
                val = _fmt_money(r['pagado']) if estado == 'Pagado' else _fmt_money(r['deuda'])
                periodo = f"{r['desde']}" if r['desde'] == r['hasta'] else f"{r['desde']} → {r['hasta']}"
                lines.append(f"  {icon} {estado}: {r['n']} res. — {val}")
                lines.append(f"     Periodo: {periodo}")

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 7: ¿% pagado de resoluciones asignadas?
# ═══════════════════════════════════════════════════════════════════════════════

def q_porcentaje_pagado(nombre: str = None) -> str:
    if nombre:
        clean_name = nombre.lower().replace('-', '').replace('.', '')
        rows = _query("""
            SELECT nombre_prestador, fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(valor_resolucion) as total_res,
                   SUM(valor_pagado) as total_pag,
                   MIN(concepto_trimestre) as desde,
                   MAX(concepto_trimestre) as hasta
            FROM subsidios_pagos
            WHERE LOWER(nombre_prestador) LIKE %s
               OR LOWER(REPLACE(REPLACE(nombre_prestador, '-', ''), '.', '')) LIKE %s
            GROUP BY nombre_prestador, fondo,
                     CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY nombre_prestador, fondo
        """, (f'%{nombre.lower()}%', f'%{clean_name}%'))

        if not rows:
            return f"ℹ️ No se encontró empresa *'{nombre}'*."

        lines = [f"📈 *% PAGADO POR EMPRESA*\n"]
        current = None
        for r in rows:
            if r['nombre_prestador'] != current:
                current = r['nombre_prestador']
                # Total global de la empresa
                total_res_emp = sum(x['total_res'] for x in rows if x['nombre_prestador'] == current)
                total_pag_emp = sum(x['total_pag'] for x in rows if x['nombre_prestador'] == current)
                pct_global = (float(total_pag_emp) / float(total_res_emp) * 100) if total_res_emp else 0
                bar = "█" * int(pct_global / 5) + "░" * (20 - int(pct_global / 5))
                lines.append(f"*{current}*")
                lines.append(f"  {bar} *{pct_global:.1f}%*")
                lines.append(f"  Asignado: {_fmt_money(total_res_emp)} | Pagado: {_fmt_money(total_pag_emp)}\n")
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            pct = (float(r['total_pag']) / float(r['total_res']) * 100) if r['total_res'] else 0
            periodo = f"{r['desde']}" if r['desde'] == r['hasta'] else f"{r['desde']} → {r['hasta']}"
            lines.append(f"  🏦 {r['fondo']} / {emoji} {r['area']}: {pct:.1f}%")
            lines.append(f"     Asignado: {_fmt_money(r['total_res'])} | Pagado: {_fmt_money(r['total_pag'])}")
            lines.append(f"     Periodo: {periodo}")
        return '\n'.join(lines)
    else:
        # Global con desglose por fondo/área
        row = _query("""
            SELECT SUM(valor_resolucion) as total_res,
                   SUM(valor_pagado) as total_pag
            FROM subsidios_pagos
        """)[0]

        pct = (float(row['total_pag']) / float(row['total_res']) * 100) if row['total_res'] else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

        # Desglose por fondo/área
        fa_rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(valor_resolucion) as total_res,
                   SUM(valor_pagado) as total_pag,
                   MIN(concepto_trimestre) as desde,
                   MAX(concepto_trimestre) as hasta
            FROM subsidios_pagos
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY fondo, area
        """)

        # Top 10 con menor %
        empresas = _query("""
            SELECT nombre_prestador,
                   SUM(valor_resolucion) as total_res,
                   SUM(valor_pagado) as total_pag
            FROM subsidios_pagos
            GROUP BY nombre_prestador
            HAVING SUM(valor_resolucion) > 0
            ORDER BY (SUM(valor_pagado)::float / NULLIF(SUM(valor_resolucion)::float, 0)) ASC
            LIMIT 10
        """)

        lines = [
            f"📈 *% PAGADO GLOBAL*\n",
            f"{bar} *{pct:.1f}%*",
            f"Asignado: {_fmt_money(row['total_res'])}",
            f"Pagado: {_fmt_money(row['total_pag'])}\n",
            f"*Detalle por fondo/área:*",
        ]
        for r in fa_rows:
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            p = (float(r['total_pag']) / float(r['total_res']) * 100) if r['total_res'] else 0
            periodo = f"{r['desde']}" if r['desde'] == r['hasta'] else f"{r['desde']} → {r['hasta']}"
            lines.append(f"  🏦 {r['fondo']} / {emoji} {r['area']}: {p:.1f}%")
            lines.append(f"     Asignado: {_fmt_money(r['total_res'])} | Pagado: {_fmt_money(r['total_pag'])}")
            lines.append(f"     Periodo: {periodo}")

        lines.append(f"\n*Top 10 empresas con menor % pagado:*\n")
        for i, r in enumerate(empresas, 1):
            p = (float(r['total_pag']) / float(r['total_res']) * 100) if r['total_res'] else 0
            lines.append(f"{i}. {r['nombre_prestador']}: {p:.1f}%")

        lines.append(f"\n💡 Para una empresa:")
        lines.append(f"`/porcentaje_pagado nombre`")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 8: Deuda por FSSRI y FOES por empresa
# ═══════════════════════════════════════════════════════════════════════════════

def q_deuda_fondo(nombre: str = None) -> str:
    if nombre:
        # Obtener todos los fondos/áreas donde la empresa tiene registros
        all_combos = _query("""
            SELECT DISTINCT
                fondo,
                CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area
            FROM subsidios_pagos
            WHERE LOWER(nombre_prestador) LIKE %s
            ORDER BY fondo, area
        """, (f'%{nombre.lower()}%',))

        if not all_combos:
            return f"ℹ️ No se encontró empresa *'{nombre}'*."

        # Deuda pendiente por fondo/area
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(saldo_pendiente) as deuda,
                   COUNT(DISTINCT no_resolucion) as n
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
              AND LOWER(nombre_prestador) LIKE %s
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY deuda DESC
        """, (f'%{nombre.lower()}%',))

        deuda_map = {}
        for r in rows:
            deuda_map[(r['fondo'], r['area'])] = {'deuda': r['deuda'], 'n': r['n']}

        total = sum(r['deuda'] for r in rows)
        lines = [
            f"🏦 *DEUDA POR FONDO*",
            f"Empresa: *{nombre}*",
            f"Total pendiente: {_fmt_money(total)}\n",
        ]
        for combo in all_combos:
            f, a = combo['fondo'], combo['area']
            data = deuda_map.get((f, a), {'deuda': 0, 'n': 0})
            emoji = "🔌" if a == "SIN" else "🏝️" if a == "ZNI" else "📌"
            lines.append(f"• 🏦 *{f}* / {emoji} {a}")
            lines.append(f"  {_fmt_money(data['deuda'])} ({data['n']} res. pendientes)")
        return '\n'.join(lines)
    else:
        # Todos los fondos/áreas existentes
        all_combos = _query("""
            SELECT DISTINCT
                fondo,
                CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area
            FROM subsidios_pagos
            WHERE fondo IS NOT NULL
            ORDER BY fondo, area
        """)

        # Deuda pendiente
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(saldo_pendiente) as deuda,
                   COUNT(DISTINCT nombre_prestador) as empresas,
                   COUNT(DISTINCT no_resolucion) as resoluciones
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY deuda DESC
        """)

        deuda_map = {}
        for r in rows:
            deuda_map[(r['fondo'], r['area'])] = r

        total = sum(r['deuda'] for r in rows)
        lines = [
            f"🏦 *DEUDA POR FONDO Y ÁREA*",
            f"Total pendiente: {_fmt_money(total)}\n",
        ]
        for combo in all_combos:
            f, a = combo['fondo'], combo['area']
            data = deuda_map.get((f, a), {'deuda': 0, 'empresas': 0, 'resoluciones': 0})
            emoji = "🔌" if a == "SIN" else "🏝️" if a == "ZNI" else "📌"
            lines.append(f"🏦 *{f}* / {emoji} *{a}*")
            lines.append(f"  Deuda: {_fmt_money(data['deuda'])}")
            lines.append(f"  Empresas: {data['empresas']} | Resoluciones: {data['resoluciones']}")

        # Top 5 empresas con más deuda por fondo
        top = _query("""
            SELECT nombre_prestador, fondo,
                   SUM(saldo_pendiente) as deuda
            FROM subsidios_pagos
            WHERE estado_pago = 'Pendiente'
            GROUP BY nombre_prestador, fondo
            ORDER BY deuda DESC
            LIMIT 5
        """)
        if top:
            lines.append(f"\n*Top 5 deudas empresa×fondo:*")
            for i, r in enumerate(top, 1):
                lines.append(f"{i}. {r['nombre_prestador']} ({r['fondo']}): {_fmt_money(r['deuda'])}")

        lines.append(f"\n💡 Para una empresa:")
        lines.append(f"`/deuda_fondo nombre`")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION 9: Valor pagado en un año
# ═══════════════════════════════════════════════════════════════════════════════

def q_pagado_anio(anio: int = None) -> str:
    if anio:
        rows = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(valor_pagado) as pagado,
                   COUNT(DISTINCT no_resolucion) as n,
                   MIN(concepto_trimestre) as desde,
                   MAX(concepto_trimestre) as hasta
            FROM subsidios_pagos
            WHERE anio = %s AND estado_pago = 'Pagado'
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY pagado DESC
        """, (anio,))

        total = sum(r['pagado'] for r in rows)
        lines = [
            f"💵 *VALOR PAGADO EN {anio}*",
            f"Total: {_fmt_money(total)}\n",
            f"*Detalle por fondo/área:*",
        ]
        for r in rows:
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            periodo = f"{r['desde']}" if r['desde'] == r['hasta'] else f"{r['desde']} → {r['hasta']}"
            lines.append(f"  🏦 *{r['fondo']}* / {emoji} *{r['area']}*")
            lines.append(f"     {_fmt_money(r['pagado'])} ({r['n']} res.) | Periodo: {periodo}")

        # Top empresas con fondo
        top = _query("""
            SELECT nombre_prestador, fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(valor_pagado) as pagado
            FROM subsidios_pagos
            WHERE anio = %s AND estado_pago = 'Pagado'
            GROUP BY nombre_prestador, fondo,
                     CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY pagado DESC
            LIMIT 10
        """, (anio,))

        if top:
            lines.append(f"\n*Top 10 pagos empresa×fondo:*")
            for i, r in enumerate(top, 1):
                emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
                lines.append(f"{i}. {r['nombre_prestador']}")
                lines.append(f"   🏦 {r['fondo']}/{emoji}{r['area']}: {_fmt_money(r['pagado'])}")
        return '\n'.join(lines)
    else:
        rows = _query("""
            SELECT anio,
                   SUM(valor_pagado) as pagado,
                   COUNT(DISTINCT no_resolucion) as n,
                   COUNT(DISTINCT fondo) as fondos
            FROM subsidios_pagos
            WHERE estado_pago = 'Pagado'
            GROUP BY anio
            ORDER BY anio DESC
        """)

        lines = [f"💵 *VALOR PAGADO POR AÑO*\n"]
        for r in rows:
            lines.append(f"*{r['anio']}*: {_fmt_money(r['pagado'])} ({r['n']} res. en {r['fondos']} fondos)")

        # Desglose global por fondo/área
        fa = _query("""
            SELECT fondo,
                   CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
                   SUM(valor_pagado) as pagado,
                   COUNT(DISTINCT no_resolucion) as n
            FROM subsidios_pagos
            WHERE estado_pago = 'Pagado'
            GROUP BY fondo, CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
            ORDER BY pagado DESC
        """)
        lines.append(f"\n*Acumulado por fondo/área:*")
        for r in fa:
            emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
            lines.append(f"  🏦 {r['fondo']} / {emoji} {r['area']}: {_fmt_money(r['pagado'])} ({r['n']} res.)")

        lines.append(f"\n💡 Para un año específico:")
        lines.append(f"`/pagado_anio 2024`")
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH: Buscar empresa por nombre (fuzzy)
# ═══════════════════════════════════════════════════════════════════════════════

def q_buscar_empresa(nombre: str) -> str:
    clean_name = nombre.lower().replace('-', '').replace('.', '')
    rows = _query("""
        SELECT nombre_prestador, fondo,
               CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END as area,
               COUNT(DISTINCT no_resolucion) as registros,
               SUM(valor_resolucion) as total_res,
               SUM(saldo_pendiente) as deuda,
               MIN(concepto_trimestre) as desde,
               MAX(concepto_trimestre) as hasta
        FROM subsidios_pagos
        WHERE LOWER(nombre_prestador) LIKE %s
           OR LOWER(REPLACE(REPLACE(nombre_prestador, '-', ''), '.', '')) LIKE %s
        GROUP BY nombre_prestador, fondo,
                 CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
        ORDER BY nombre_prestador, fondo
        LIMIT 30
    """, (f'%{nombre.lower()}%', f'%{clean_name}%'))

    if not rows:
        return f"ℹ️ No se encontró empresa que contenga *'{nombre}'*."

    lines = [f"🔍 *Empresas encontradas para '{nombre}':*\n"]
    current = None
    for r in rows:
        if r['nombre_prestador'] != current:
            current = r['nombre_prestador']
            total_reg = sum(x['registros'] for x in rows if x['nombre_prestador'] == current)
            total_val = sum(x['total_res'] for x in rows if x['nombre_prestador'] == current)
            lines.append(f"*{current}*")
            lines.append(f"  {total_reg} resoluciones | Total: {_fmt_money(total_val)}")
        emoji = "🔌" if r['area'] == "SIN" else "🏝️" if r['area'] == "ZNI" else "📌"
        periodo = f"{r['desde']}" if r['desde'] == r['hasta'] else f"{r['desde']} → {r['hasta']}"
        deuda_txt = f" | Deuda: {_fmt_money(r['deuda'])}" if r['deuda'] > 0 else ""
        lines.append(f"  • 🏦 {r['fondo']} / {emoji} {r['area']}: {r['registros']} res.{deuda_txt}")
        lines.append(f"    Periodo: {periodo}")
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SMART TEXT ROUTING — Detecta si texto libre es sobre subsidios
# Usa BD (audit_log) en vez de memoria para sobrevivir reinicios
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re

# Palabras clave que SIEMPRE indican subsidios
_SUBSIDIOS_KEYWORDS = _re.compile(
    r'(?i)(subsidio|deuda|fssri|foes|resoluc|pendiente|pagad|pagó|pago|trimestre|prestador|saldo)',
)


def _is_in_subsidios_context(telegram_id: int, minutes: int = 10) -> bool:
    """Verifica si el usuario interactuó con subsidios recientemente (BD-based, sobrevive reinicios)."""
    result = _scalar("""
        SELECT COUNT(*) FROM subsidios_audit_log
        WHERE telegram_id = %s
          AND timestamp > NOW() - INTERVAL '%s minutes'
    """, (telegram_id, minutes))
    return result is not None and result > 0


def _match_prestador(text: str):
    """Busca si el texto coincide con un nombre_prestador en la BD (fuzzy: ignora guiones)."""
    clean = text.strip().lower()
    # Búsqueda fuzzy: quitar guiones y caracteres especiales para comparar
    rows = _query("""
        SELECT DISTINCT nombre_prestador
        FROM subsidios_pagos
        WHERE LOWER(nombre_prestador) LIKE %s
           OR LOWER(REPLACE(REPLACE(nombre_prestador, '-', ''), '.', '')) LIKE %s
        LIMIT 5
    """, (f'%{clean}%', f'%{clean}%'))
    return [r['nombre_prestador'] for r in rows] if rows else []


def _detect_subsidios_action(text: str):
    """
    Analiza texto libre y detecta qué acción de subsidios ejecutar.
    Retorna (action, param) o (None, None).
    """
    t = text.strip()

    # Detectar año (ej: "2024", "año 2024")
    year_match = _re.search(r'\b(20[0-9]{2})\b', t)

    # Si tiene keywords de subsidios + año → podría ser resoluciones o pagado
    if _SUBSIDIOS_KEYWORDS.search(t) and year_match:
        anio = int(year_match.group(1))
        if _re.search(r'pagad|valor|cuánto.*pagó', t, _re.IGNORECASE):
            return 'pagado_anio', anio
        return 'resoluciones', anio

    # Si tiene keywords de subsidios + nombre → deuda empresa
    if _SUBSIDIOS_KEYWORDS.search(t):
        # Quitar las keywords para extraer posible nombre
        cleaned = _SUBSIDIOS_KEYWORDS.sub('', t).strip()
        if cleaned and len(cleaned) >= 2:
            matches = _match_prestador(cleaned)
            if matches:
                return 'deuda_empresa', cleaned
        # Keyword sola sin nombre → menú general
        return 'menu_subsidios', None

    # Texto corto (1-4 palabras) que coincide con empresa → probablemente busca empresa
    words = t.split()
    if 1 <= len(words) <= 4:
        matches = _match_prestador(t)
        if matches:
            return 'deuda_empresa', t

    return None, None


async def handle_subsidios_text(update: Update, context, message: str) -> bool:
    """
    Determina si un mensaje de texto libre debe ser manejado por subsidios.
    Usa BD (audit_log) para contexto, no depende de memoria.
    Retorna True si se manejó, False si debe ir al orquestador normal.
    """
    # Guard: NO interceptar comandos — dejar al CommandHandler
    if message.strip().startswith('/'):
        return False

    user = update.effective_user
    chat = update.effective_chat

    # Solo para usuarios autorizados de subsidios
    if not _is_authorized(user.id):
        return False

    message_clean = message.strip()

    # Paso 1: Detectar qué acción corresponde
    action, param = _detect_subsidios_action(message_clean)

    if action:
        # Si detectó keywords de subsidios → ejecutar directamente
        logger.info(f"[SUBSIDIOS-SMART] Detected action={action} param={param} for user {user.id}")
    else:
        # Paso 2: Sin keywords, pero ¿está en contexto de subsidios reciente?
        if _is_in_subsidios_context(user.id, minutes=10):
            # Verificar si el texto coincide con una empresa
            matches = _match_prestador(message_clean)
            if matches:
                action = 'deuda_empresa'
                param = message_clean
                logger.info(f"[SUBSIDIOS-CONTEXT] User {user.id} in subsidios context, matched empresa: {matches}")
            else:
                # En contexto pero no matchea empresa ni keyword → dejar pasar al orquestador
                return False
        else:
            return False

    # Ejecutar la acción detectada
    await chat.send_action("typing")
    _audit(user.id, _user_name(user), f'smart:{action}', str(param))

    if action == 'deuda_empresa':
        text = q_deuda_empresa(param)
    elif action == 'pagado_anio':
        text = q_pagado_anio(param)
    elif action == 'resoluciones':
        text = q_resoluciones_anio(param)
    elif action == 'menu_subsidios':
        text = (
            "📋 *MÓDULO DE SUBSIDIOS*\n"
            "Base de Subsidios DDE — Ministerio de Minas y Energía\n\n"
            "Selecciona la consulta que deseas realizar:"
        )
        await _safe_send(chat, text, _menu_kb())
        return True
    else:
        return False

    await _safe_send(chat, text, _back_kb())
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _safe_send(chat, text: str, keyboard=None):
    """Envía con fallback."""
    if len(text) > 4096:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            kb = keyboard if i == len(chunks) - 1 else None
            try:
                await chat.send_message(chunk, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await chat.send_message(chunk, reply_markup=kb)
    else:
        try:
            await chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception:
            await chat.send_message(text, reply_markup=keyboard)


async def _check_auth(update):
    """Verifica autorización. Si no autorizado, envía mensaje y retorna False."""
    user = update.effective_user
    if not _is_authorized(user.id):
        await _safe_send(update.effective_chat, NOT_AUTH_MSG, _back_kb())
        logger.warning(f"[SUBSIDIOS] Acceso denegado: {user.id} (@{user.username})")
        return False
    return True


async def cmd_subsidios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú principal de subsidios."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    _audit(user.id, _user_name(user), '/subsidios')

    text = (
        "📋 *MÓDULO DE SUBSIDIOS*\n"
        "Base de Subsidios DDE — Ministerio de Minas y Energía\n\n"
        "Selecciona la consulta que deseas realizar:"
    )
    await _safe_send(update.effective_chat, text, _menu_kb())


async def cmd_deuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deuda total."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    _audit(user.id, _user_name(user), '/deuda')
    await update.effective_chat.send_action("typing")
    text = q_deuda_total()
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_deuda_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deuda por empresa."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    nombre = ' '.join(context.args) if context.args else None
    _audit(user.id, _user_name(user), '/deuda_empresa', nombre)
    await update.effective_chat.send_action("typing")
    text = q_deuda_empresa(nombre)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_trimestre_pagado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trimestre pagado."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    nombre = ' '.join(context.args) if context.args else None
    _audit(user.id, _user_name(user), '/trimestre_pagado', nombre)
    await update.effective_chat.send_action("typing")
    text = q_trimestre_pagado(nombre)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_resoluciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resoluciones por año."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    anio = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    _audit(user.id, _user_name(user), '/resoluciones', str(anio))
    await update.effective_chat.send_action("typing")
    text = q_resoluciones_anio(anio)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_estado_resoluciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estado resoluciones pagadas vs pendientes."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    _audit(user.id, _user_name(user), '/estado_resoluciones')
    await update.effective_chat.send_action("typing")
    text = q_estado_resoluciones()
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_porcentaje_pagado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """% pagado."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    nombre = ' '.join(context.args) if context.args else None
    _audit(user.id, _user_name(user), '/porcentaje_pagado', nombre)
    await update.effective_chat.send_action("typing")
    text = q_porcentaje_pagado(nombre)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_deuda_fondo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deuda por fondo."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    nombre = ' '.join(context.args) if context.args else None
    _audit(user.id, _user_name(user), '/deuda_fondo', nombre)
    await update.effective_chat.send_action("typing")
    text = q_deuda_fondo(nombre)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_pagado_anio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valor pagado por año."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    anio = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    _audit(user.id, _user_name(user), '/pagado_anio', str(anio))
    await update.effective_chat.send_action("typing")
    text = q_pagado_anio(anio)
    await _safe_send(update.effective_chat, text, _back_kb())


async def cmd_buscar_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buscar empresa."""
    if not await _check_auth(update):
        return
    user = update.effective_user
    nombre = ' '.join(context.args) if context.args else None
    _audit(user.id, _user_name(user), '/buscar_empresa', nombre)
    if not nombre:
        text = "ℹ️ Uso: `/buscar_empresa nombre`\nEjemplo: `/buscar_empresa electricaribe`"
        await _safe_send(update.effective_chat, text, _back_kb())
        return
    await update.effective_chat.send_action("typing")
    text = q_buscar_empresa(nombre)
    await _safe_send(update.effective_chat, text, _back_kb())


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER (inline buttons)
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_subsidios_callback(query, user, chat, data: str, context):
    """Maneja callbacks de botones inline del módulo subsidios."""
    action = data.split(":", 1)[1] if ":" in data else data

    if not _is_authorized(user.id):
        try:
            await query.edit_message_text(NOT_AUTH_MSG, parse_mode=ParseMode.MARKDOWN, reply_markup=_back_kb())
        except Exception:
            await _safe_send(chat, NOT_AUTH_MSG, _back_kb())
        return

    _audit(user.id, _user_name(user), f'cb:{action}')
    await chat.send_action("typing")

    if action == 'menu':
        text = (
            "📋 *MÓDULO DE SUBSIDIOS*\n"
            "Base de Subsidios DDE — Ministerio de Minas y Energía\n\n"
            "Selecciona la consulta que deseas realizar:"
        )
        kb = _menu_kb()
    elif action == 'deuda':
        text = q_deuda_total()
        kb = _back_kb()
    elif action == 'deuda_empresa':
        text = q_deuda_empresa()
        kb = _back_kb()
    elif action == 'trimestre':
        text = q_trimestre_pagado()
        kb = _back_kb()
    elif action == 'resoluciones':
        text = q_resoluciones_anio()
        kb = _back_kb()
    elif action == 'estado_res':
        text = q_estado_resoluciones()
        kb = _back_kb()
    elif action == 'pct_pagado':
        text = q_porcentaje_pagado()
        kb = _back_kb()
    elif action == 'deuda_fondo':
        text = q_deuda_fondo()
        kb = _back_kb()
    elif action == 'pagado_anio':
        text = q_pagado_anio()
        kb = _back_kb()
    else:
        text = "⚠️ Opción no reconocida."
        kb = _menu_kb()

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception:
        await _safe_send(chat, text, kb)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION FUNCTION (called from telegram_polling.py)
# ═══════════════════════════════════════════════════════════════════════════════

def register_subsidios_handlers(app):
    """Registra todos los handlers de subsidios en la aplicación de Telegram."""
    app.add_handler(CommandHandler("subsidios", cmd_subsidios))
    app.add_handler(CommandHandler("deuda", cmd_deuda))
    app.add_handler(CommandHandler("deuda_empresa", cmd_deuda_empresa))
    app.add_handler(CommandHandler("trimestre_pagado", cmd_trimestre_pagado))
    app.add_handler(CommandHandler("resoluciones", cmd_resoluciones))
    app.add_handler(CommandHandler("estado_resoluciones", cmd_estado_resoluciones))
    app.add_handler(CommandHandler("porcentaje_pagado", cmd_porcentaje_pagado))
    app.add_handler(CommandHandler("deuda_fondo", cmd_deuda_fondo))
    app.add_handler(CommandHandler("pagado_anio", cmd_pagado_anio))
    app.add_handler(CommandHandler("buscar_empresa", cmd_buscar_empresa))
    logger.info("✅ Handlers de subsidios registrados (10 comandos)")


def get_subsidios_bot_commands():
    """Retorna BotCommand list para el menú de Telegram."""
    return [
        BotCommand("subsidios", "📋 Menú de subsidios"),
        BotCommand("deuda", "💰 Deuda total de subsidios"),
        BotCommand("deuda_empresa", "🏢 Deuda por empresa"),
        BotCommand("trimestre_pagado", "📅 Hasta qué trimestre pagado"),
        BotCommand("resoluciones", "📊 Resoluciones por año"),
        BotCommand("estado_resoluciones", "✅ Pagadas vs pendientes"),
        BotCommand("porcentaje_pagado", "📈 % pagado"),
        BotCommand("deuda_fondo", "🏦 Deuda FSSRI/FOES"),
        BotCommand("pagado_anio", "💵 Valor pagado por año"),
    ]
