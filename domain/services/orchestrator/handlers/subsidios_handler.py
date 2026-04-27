"""
Mixin: Subsidios energéticos — 8 módulos.
Replica el módulo del bot de Telegram en el orquestador del portal.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.database.connection import connection_manager

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_cop(val) -> str:
    if val is None:
        return "N/D"
    v = float(val)
    if v == 0:
        return "$0"
    if abs(v) >= 1e12:
        return f"${v / 1e12:,.2f} billones"
    if abs(v) >= 1e9:
        return f"${v / 1e9:,.2f} mil millones"
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.2f} millones"
    return f"${v:,.0f}"


def _fix_area(val) -> str:
    if val is None or str(val) == "None":
        return "General"
    return str(val)


def _area_emoji(area: str) -> str:
    if area == "SIN":
        return "🔌"
    if area == "ZNI":
        return "🏝️"
    return "📌"


# ── Módulo 1 — Deuda total ────────────────────────────────────────────────────

def _q1_deuda_total() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area
                FROM subsidios.subsidios_pagos
                WHERE fondo IS NOT NULL
                ORDER BY fondo, area
            """)
            all_combos = cur.fetchall()

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    SUM(saldo_pendiente) AS deuda,
                    COUNT(DISTINCT no_resolucion) AS resoluciones
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY fondo, area
            """)
            rows = cur.fetchall()

            cur.execute(
                "SELECT MAX(fecha_actualizacion) AS fecha FROM subsidios.subsidios_pagos"
            )
            fecha = (cur.fetchone() or {}).get("fecha")

    deuda_map = {(r["fondo"], r["area"]): r for r in rows}
    total = sum(float(r["deuda"] or 0) for r in rows)
    total_res = sum(int(r["resoluciones"] or 0) for r in rows)
    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/A"

    lines = [
        "💰 **DEUDA TOTAL DE SUBSIDIOS**",
        f"📅 Corte: {fecha_str}",
        "",
        f"**Total pendiente: {_fmt_cop(total)}**",
        f"({total_res} resoluciones pendientes)",
        "",
        "**Desglose por fondo y área:**",
    ]

    by_fondo: dict = defaultdict(dict)
    for combo in all_combos:
        f, a = combo["fondo"], combo["area"]
        by_fondo[f][a] = deuda_map.get((f, a), {"deuda": 0, "resoluciones": 0})

    for fondo in sorted(by_fondo):
        areas = by_fondo[fondo]
        t_f = sum(float(v["deuda"] or 0) for v in areas.values())
        r_f = sum(int(v["resoluciones"] or 0) for v in areas.values())
        lines += ["", f"🏦 **{fondo}**: {_fmt_cop(t_f)} ({r_f} res.)"]
        for area in sorted(areas):
            v = float(areas[area]["deuda"] or 0)
            r = int(areas[area]["resoluciones"] or 0)
            lines.append(f"  {_area_emoji(area)} {area}: {_fmt_cop(v)} ({r} res.)")

    return "\n".join(lines)


# ── Módulo 2 — Deuda por empresa ─────────────────────────────────────────────

def _q2_deuda_empresa() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT nombre_prestador) AS empresas,
                       SUM(saldo_pendiente) AS total_deuda
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
            """)
            res = cur.fetchone() or {}

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    COUNT(DISTINCT nombre_prestador) AS empresas,
                    SUM(saldo_pendiente) AS deuda
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY deuda DESC
            """)
            desglose = cur.fetchall()

            cur.execute("""
                SELECT nombre_prestador, fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    SUM(saldo_pendiente) AS deuda,
                    COUNT(DISTINCT no_resolucion) AS resoluciones,
                    MIN(concepto_trimestre) AS trim_desde,
                    MAX(concepto_trimestre) AS trim_hasta
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
                GROUP BY nombre_prestador, fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY deuda DESC
                LIMIT 5
            """)
            top5 = cur.fetchall()

    n_emp = int(res.get("empresas") or 0)
    total = float(res.get("total_deuda") or 0)

    if n_emp == 0:
        return "✅ No hay deuda pendiente con ninguna empresa."

    lines = [
        "🏢 **DEUDA PENDIENTE POR EMPRESA**",
        "",
        f"📊 Se le debe a **{n_emp} empresas**",
        f"💰 Total adeudado: {_fmt_cop(total)}",
        "",
        "**Distribución por fondo/área:**",
    ]
    for r in desglose:
        a = _fix_area(r["area"])
        lines.append(
            f"  🏦 {r['fondo']} / {_area_emoji(a)} {a}: "
            f"{int(r['empresas'] or 0)} empresas — {_fmt_cop(r['deuda'])}"
        )

    lines += ["", "**Top 5 mayores deudas:**"]
    for i, r in enumerate(top5, 1):
        a = _fix_area(r["area"])
        desde, hasta = r.get("trim_desde", ""), r.get("trim_hasta", "")
        periodo = str(desde) if desde == hasta else f"{desde} → {hasta}"
        lines += [
            "",
            f"{i}. **{r['nombre_prestador']}**",
            f"   {_fmt_cop(r['deuda'])} ({r['resoluciones']} res.)",
            f"   🏦 {r['fondo']} / {_area_emoji(a)} {a} | {periodo}",
        ]

    return "\n".join(lines)


# ── Módulo 3 — Trimestre pagado ───────────────────────────────────────────────

def _q3_trimestre_pagado() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    concepto_trimestre,
                    COUNT(DISTINCT CASE WHEN estado_pago = 'Pagado'    THEN no_resolucion END) AS pagadas,
                    COUNT(DISTINCT CASE WHEN estado_pago = 'Pendiente' THEN no_resolucion END) AS pendientes
                FROM subsidios.subsidios_pagos
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END,
                         concepto_trimestre
                ORDER BY fondo, area, concepto_trimestre DESC
            """)
            rows = cur.fetchall()

    fa: dict = defaultdict(list)
    for r in rows:
        fa[(r["fondo"], _fix_area(r["area"]))].append(r)

    lines = ["📅 **ESTADO DE PAGO POR TRIMESTRE**", ""]
    for (fondo, area), trims in sorted(fa.items()):
        ultimo = next(
            (t["concepto_trimestre"] for t in trims
             if int(t["pendientes"] or 0) == 0 and int(t["pagadas"] or 0) > 0),
            None,
        )
        lines.append(f"🏦 **{fondo}** / {_area_emoji(area)} **{area}**")
        if ultimo:
            lines.append(f"  ✅ Último 100% pagado: **{ultimo}**")
        for t in trims[:6]:
            pen = int(t["pendientes"] or 0)
            pag = int(t["pagadas"] or 0)
            st = "✅" if pen == 0 and pag > 0 else "⏳"
            lines.append(
                f"  {st} {t['concepto_trimestre']}: {pag} pagadas, {pen} pendientes"
            )
        lines.append("")

    return "\n".join(lines)


# ── Módulo 4 — Resoluciones por año ──────────────────────────────────────────

def _q4_resoluciones() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT LEFT(anio_trimestre_resolucion, 4)::int AS anio_res,
                       COUNT(DISTINCT no_resolucion) AS n,
                       SUM(valor_resolucion) AS valor
                FROM subsidios.subsidios_pagos
                WHERE anio_trimestre_resolucion IS NOT NULL
                GROUP BY 1
                ORDER BY 1 DESC
            """)
            rows = cur.fetchall()

    lines = ["📊 **RESOLUCIONES POR AÑO (expedición)**", ""]
    for r in rows:
        lines.append(f"**{r['anio_res']}**: {int(r['n'])} resoluciones ({_fmt_cop(r['valor'])})")
    return "\n".join(lines)


# ── Módulo 5 — Estado de resoluciones ────────────────────────────────────────

def _q5_estado_resoluciones() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(concepto_trimestre) AS periodo_min,
                       MAX(concepto_trimestre) AS periodo_max,
                       MAX(fecha_actualizacion) AS fecha_corte
                FROM subsidios.subsidios_pagos
            """)
            meta = cur.fetchone() or {}

            cur.execute("""
                SELECT estado_pago,
                       COUNT(DISTINCT no_resolucion) AS resoluciones,
                       SUM(valor_pagado) AS valor_pag,
                       SUM(saldo_pendiente) AS saldo
                FROM subsidios.subsidios_pagos
                GROUP BY estado_pago
                ORDER BY estado_pago
            """)
            resumen = cur.fetchall()

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    estado_pago,
                    SUM(saldo_pendiente) AS deuda,
                    SUM(valor_pagado) AS pagado,
                    COUNT(DISTINCT no_resolucion) AS n,
                    MIN(concepto_trimestre) AS desde,
                    MAX(concepto_trimestre) AS hasta
                FROM subsidios.subsidios_pagos
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END,
                         estado_pago
                ORDER BY fondo, area, estado_pago
            """)
            desglose = cur.fetchall()

    fecha_corte = meta.get("fecha_corte")
    fecha_str = fecha_corte.strftime("%d/%m/%Y") if fecha_corte else "N/A"
    periodo_min = meta.get("periodo_min", "")
    periodo_max = meta.get("periodo_max", "")
    total_res = sum(int(r["resoluciones"] or 0) for r in resumen)

    pag = next((r for r in resumen if r["estado_pago"] == "Pagado"), None)
    pen = next((r for r in resumen if r["estado_pago"] == "Pendiente"), None)
    n_pag = int(pag["resoluciones"] or 0) if pag else 0
    v_pag = float(pag["valor_pag"] or 0) if pag else 0
    n_pen = int(pen["resoluciones"] or 0) if pen else 0
    v_pen = float(pen["saldo"] or 0) if pen else 0
    pct_pag = (n_pag / total_res * 100) if total_res else 0
    pct_pen = (n_pen / total_res * 100) if total_res else 0

    lines = [
        "📊 **ESTADO DE RESOLUCIONES**",
        f"📅 Corte: {fecha_str} | Periodo: {periodo_min} → {periodo_max}",
        "",
        f"De {total_res:,} resoluciones únicas registradas:",
        "",
        f"✅ **Pagadas:** {n_pag:,} ({pct_pag:.1f}%)",
        f"   Total pagado: {_fmt_cop(v_pag)}",
        "",
        f"⏳ **Pendientes:** {n_pen:,} ({pct_pen:.1f}%)",
        f"   Total adeudado: {_fmt_cop(v_pen)}",
        "",
        "**Detalle por fondo/área:**",
    ]

    fa_map: dict = defaultdict(dict)
    for r in desglose:
        a = _fix_area(r["area"])
        fa_map[(r["fondo"], a)][r["estado_pago"]] = r

    for (fondo, area), estados in sorted(fa_map.items()):
        lines += ["", f"🏦 **{fondo}** / {_area_emoji(area)} **{area}**"]
        for estado in ("Pagado", "Pendiente"):
            if estado in estados:
                r = estados[estado]
                icon = "✅" if estado == "Pagado" else "⏳"
                val = _fmt_cop(r["pagado"]) if estado == "Pagado" else _fmt_cop(r["deuda"])
                desde, hasta = r.get("desde", ""), r.get("hasta", "")
                periodo = str(desde) if desde == hasta else f"{desde} → {hasta}"
                lines.append(f"  {icon} {estado}: {int(r['n'] or 0)} res. — {val}")
                lines.append(f"     Periodo: {periodo}")

    return "\n".join(lines)


# ── Módulo 6 — % Pagado ───────────────────────────────────────────────────────

def _q6_pct_pagado() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT SUM(valor_resolucion) AS total_res,
                       SUM(valor_pagado) AS total_pag
                FROM subsidios.subsidios_pagos
            """)
            row = cur.fetchone() or {}

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    SUM(valor_resolucion) AS total_res,
                    SUM(valor_pagado) AS total_pag,
                    MIN(concepto_trimestre) AS desde,
                    MAX(concepto_trimestre) AS hasta
                FROM subsidios.subsidios_pagos
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY fondo, area
            """)
            fa_rows = cur.fetchall()

            cur.execute("""
                SELECT nombre_prestador,
                       SUM(valor_resolucion) AS total_res,
                       SUM(valor_pagado) AS total_pag
                FROM subsidios.subsidios_pagos
                GROUP BY nombre_prestador
                HAVING SUM(valor_resolucion) > 0
                ORDER BY (SUM(valor_pagado)::float / NULLIF(SUM(valor_resolucion)::float, 0)) ASC
                LIMIT 10
            """)
            empresas = cur.fetchall()

    tr = float(row.get("total_res") or 0)
    tp = float(row.get("total_pag") or 0)
    pct = (tp / tr * 100) if tr else 0
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)

    lines = [
        "📈 **% PAGADO GLOBAL**",
        "",
        f"{bar} **{pct:.1f}%**",
        f"Asignado: {_fmt_cop(tr)}",
        f"Pagado: {_fmt_cop(tp)}",
        "",
        "**Detalle por fondo/área:**",
    ]
    for r in fa_rows:
        a = _fix_area(r["area"])
        tr2 = float(r["total_res"] or 0)
        tp2 = float(r["total_pag"] or 0)
        p = (tp2 / tr2 * 100) if tr2 else 0
        desde, hasta = r.get("desde", ""), r.get("hasta", "")
        periodo = str(desde) if desde == hasta else f"{desde} → {hasta}"
        lines.append(f"  🏦 {r['fondo']} / {_area_emoji(a)} {a}: {p:.1f}%")
        lines.append(f"     Asignado: {_fmt_cop(tr2)} | Pagado: {_fmt_cop(tp2)}")
        lines.append(f"     Periodo: {periodo}")

    lines += ["", "**Top 10 empresas con menor % pagado:**", ""]
    for i, r in enumerate(empresas, 1):
        tr2 = float(r["total_res"] or 0)
        tp2 = float(r["total_pag"] or 0)
        p = (tp2 / tr2 * 100) if tr2 else 0
        lines.append(f"{i}. {r['nombre_prestador']}: {p:.1f}%")

    return "\n".join(lines)


# ── Módulo 7 — Deuda FSSRI/FOES ──────────────────────────────────────────────

def _q7_deuda_fondo() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area
                FROM subsidios.subsidios_pagos
                WHERE fondo IS NOT NULL
                ORDER BY fondo, area
            """)
            all_combos = cur.fetchall()

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    SUM(saldo_pendiente) AS deuda,
                    COUNT(DISTINCT nombre_prestador) AS empresas,
                    COUNT(DISTINCT no_resolucion) AS resoluciones
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY deuda DESC
            """)
            rows = cur.fetchall()

            cur.execute("""
                SELECT nombre_prestador, fondo,
                       SUM(saldo_pendiente) AS deuda
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente'
                GROUP BY nombre_prestador, fondo
                ORDER BY deuda DESC
                LIMIT 5
            """)
            top5 = cur.fetchall()

    deuda_map = {(r["fondo"], _fix_area(r["area"])): r for r in rows}
    total = sum(float(r["deuda"] or 0) for r in rows)

    lines = [
        "🏦 **DEUDA POR FONDO Y ÁREA (FSSRI / FOES)**",
        f"**Total pendiente: {_fmt_cop(total)}**",
        "",
    ]
    for combo in all_combos:
        f, a = combo["fondo"], _fix_area(combo["area"])
        d = deuda_map.get((f, a), {"deuda": 0, "empresas": 0, "resoluciones": 0})
        lines += [
            f"🏦 **{f}** / {_area_emoji(a)} **{a}**",
            f"  Deuda: {_fmt_cop(d['deuda'])}",
            f"  Empresas: {int(d['empresas'] or 0)} | Resoluciones: {int(d['resoluciones'] or 0)}",
        ]

    if top5:
        lines += ["", "**Top 5 deudas empresa×fondo:**"]
        for i, r in enumerate(top5, 1):
            lines.append(f"{i}. {r['nombre_prestador']} ({r['fondo']}): {_fmt_cop(r['deuda'])}")

    return "\n".join(lines)


# ── Módulo 8 — Pagado por año ─────────────────────────────────────────────────

def _q8_pagado_anio() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT anio,
                       SUM(valor_pagado) AS pagado,
                       COUNT(DISTINCT no_resolucion) AS n,
                       COUNT(DISTINCT fondo) AS fondos
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pagado'
                GROUP BY anio
                ORDER BY anio DESC
            """)
            rows = cur.fetchall()

            cur.execute("""
                SELECT fondo,
                    CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END AS area,
                    SUM(valor_pagado) AS pagado,
                    COUNT(DISTINCT no_resolucion) AS n
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pagado'
                GROUP BY fondo,
                         CASE WHEN area IS NULL OR area = 'None' THEN 'General' ELSE area END
                ORDER BY pagado DESC
            """)
            fa = cur.fetchall()

    lines = ["💵 **VALOR PAGADO POR AÑO**", ""]
    for r in rows:
        lines.append(
            f"**{r['anio']}**: {_fmt_cop(r['pagado'])} "
            f"({int(r['n'])} res. en {int(r['fondos'])} fondos)"
        )

    lines += ["", "**Acumulado por fondo/área:**"]
    for r in fa:
        a = _fix_area(r["area"])
        lines.append(
            f"  🏦 {r['fondo']} / {_area_emoji(a)} {a}: "
            f"{_fmt_cop(r['pagado'])} ({int(r['n'])} res.)"
        )

    return "\n".join(lines)


# ── Mixin ──────────────────────────────────────────────────────────────────────

_MODULE_MAP = {
    "subsidios_deuda_total":   ("💰 Deuda total",          _q1_deuda_total),
    "subsidios_deuda_empresa": ("🏢 Deuda por empresa",     _q2_deuda_empresa),
    "subsidios_trimestre":     ("📅 Trimestre pagado",       _q3_trimestre_pagado),
    "subsidios_resoluciones":  ("📊 Resoluciones por año",   _q4_resoluciones),
    "subsidios_estado":        ("✅ Estado resoluciones",    _q5_estado_resoluciones),
    "subsidios_pct_pagado":    ("📈 % Pagado",               _q6_pct_pagado),
    "subsidios_deuda_fondo":   ("🏦 Deuda FSSRI/FOES",       _q7_deuda_fondo),
    "subsidios_pagado_anio":   ("💵 Pagado por año",          _q8_pagado_anio),
}


def _make_handler(titulo: str, fn):
    """Factoria: crea un método async de handler para una consulta de subsidios."""

    @handle_service_error
    async def _handler(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        try:
            texto = await asyncio.to_thread(fn)
            data.update({"tipo": "subsidios_texto", "titulo": titulo, "texto": texto})
        except Exception as exc:
            logger.error("[%s] %s", titulo, exc, exc_info=True)
            errors.append(ErrorDetail(code="DB_ERROR", message=str(exc)))
        return data, errors

    _handler.__name__ = f"_handle_{titulo.lower().replace(' ', '_')}"
    return _handler


class SubsidiosHandlerMixin:
    """
    Mixin que expone los 8 módulos del sistema de subsidios (FSSRI/FOES)
    a través del orquestador del portal de dirección.
    """

    _handle_subsidios_deuda_total   = _make_handler("💰 Deuda total",        _q1_deuda_total)
    _handle_subsidios_deuda_empresa = _make_handler("🏢 Deuda por empresa",   _q2_deuda_empresa)
    _handle_subsidios_trimestre     = _make_handler("📅 Trimestre pagado",     _q3_trimestre_pagado)
    _handle_subsidios_resoluciones  = _make_handler("📊 Resoluciones por año", _q4_resoluciones)
    _handle_subsidios_estado        = _make_handler("✅ Estado resoluciones",  _q5_estado_resoluciones)
    _handle_subsidios_pct_pagado    = _make_handler("📈 % Pagado",             _q6_pct_pagado)
    _handle_subsidios_deuda_fondo   = _make_handler("🏦 Deuda FSSRI/FOES",     _q7_deuda_fondo)
    _handle_subsidios_pagado_anio   = _make_handler("💵 Pagado por año",        _q8_pagado_anio)
