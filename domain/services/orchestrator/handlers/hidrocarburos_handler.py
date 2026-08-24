"""
Mixin: Hidrocarburos — presupuesto y producción/mercado.
Porta a Python las mismas queries SQL que ya usan portal-direccion-mme/src/app/api/
hidrocarburos/{presupuesto,produccion}/route.ts (getPool() directo) — no reimplementa
lógica nueva, solo expone esos mismos datos al orquestador/Asistente IA.
"""
import asyncio
from infrastructure.logging.logger import get_logger
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.database.connection import connection_manager

logger = get_logger(__name__)


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


def _fmt_pct(val) -> str:
    """pct_compromisos/pct_obligaciones vienen como fracción (0.586), no como
    porcentaje ya escalado — confirmado contra hidrocarburos/presupuesto/page.tsx,
    que multiplica por 100 en cada uso (líneas 88-89, 102, 278-279)."""
    if val is None:
        return "N/D"
    return f"{float(val) * 100:.1f}%"


def _fmt_fecha(val) -> str:
    if val is None:
        return "N/D"
    return val.strftime("%d/%m/%Y")


def _fmt_es(val, decimales: int = 0) -> str:
    """Formatea con convención es-CO (miles con punto, decimales con coma) sin
    ambigüedad — swap seguro vía placeholder, no un .replace(",", ".") directo
    (que rompe si el número también tiene parte decimal, ej. "1,083.0" -> "1.083.0")."""
    if val is None:
        return "N/D"
    s = f"{float(val):,.{decimales}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ── Queries ────────────────────────────────────────────────────────────────────

def _q_hidrocarburos_presupuesto() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fecha_actualizacion, apropiacion_vigente, compromisos, obligaciones,
                       por_comprometer, pct_compromisos, pct_obligaciones
                FROM hidrocarburos.presupuesto_resumen
                ORDER BY fecha_actualizacion DESC LIMIT 1
            """)
            resumen = cur.fetchone()

            if resumen is None:
                return "No hay datos de ejecución presupuestal de hidrocarburos cargados todavía."

            cur.execute("""
                SELECT proyecto, apropiacion_vigente, compromisos, obligaciones,
                       por_comprometer, pct_compromisos, pct_obligacion
                FROM hidrocarburos.presupuesto_proyectos
                WHERE fecha_actualizacion = %s
                ORDER BY pct_obligacion ASC NULLS LAST
            """, (resumen["fecha_actualizacion"],))
            proyectos = cur.fetchall()

    fecha_str = _fmt_fecha(resumen["fecha_actualizacion"])
    lines = [
        "💰 **EJECUCIÓN PRESUPUESTAL — DIRECCIÓN DE HIDROCARBUROS**",
        f"📅 Corte: {fecha_str} (dato de carga manual, no diario — puede tener varias semanas)",
        "",
        f"**Apropiación vigente:** {_fmt_cop(resumen['apropiacion_vigente'])}",
        f"**Compromisos:** {_fmt_cop(resumen['compromisos'])} ({_fmt_pct(resumen['pct_compromisos'])})",
        f"**Obligaciones:** {_fmt_cop(resumen['obligaciones'])} ({_fmt_pct(resumen['pct_obligaciones'])})",
        f"**Por comprometer:** {_fmt_cop(resumen['por_comprometer'])}",
    ]
    if proyectos:
        lines += ["", "**Proyectos con menor % de obligación (peor desempeño primero):**"]
        for p in proyectos[:5]:
            lines.append(
                f"• {p['proyecto']}: {_fmt_pct(p['pct_obligacion'])} obligado "
                f"({_fmt_cop(p['obligaciones'])} de {_fmt_cop(p['apropiacion_vigente'])})"
            )
    return "\n".join(lines)


def _q_hidrocarburos_produccion() -> str:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fecha, petroleo_bbl, gas_fiscalizado_mpc, gas_comercializado_mpc
                FROM hidrocarburos.produccion_diaria
                ORDER BY fecha DESC LIMIT 1
            """)
            produccion = cur.fetchone()

            cur.execute("""
                SELECT DISTINCT ON (commodity) commodity, fecha, valor_usd, variacion_abs, variacion_pct
                FROM hidrocarburos.commodities_historico
                ORDER BY commodity, fecha DESC
            """)
            commodities = cur.fetchall()

            cur.execute("""
                SELECT mes, categoria, nombre, valor, unidad
                FROM hidrocarburos.produccion_top5
                WHERE periodo = (SELECT MAX(periodo) FROM hidrocarburos.produccion_top5)
                ORDER BY categoria, valor DESC
            """)
            top5 = cur.fetchall()

    lines = ["🛢️ **PRODUCCIÓN Y MERCADO — HIDROCARBUROS**"]

    if produccion:
        fiscalizado = produccion["gas_fiscalizado_mpc"]
        comercializado = produccion["gas_comercializado_mpc"]
        brecha = (float(fiscalizado) - float(comercializado)) if fiscalizado is not None and comercializado is not None else None
        lines += [
            f"📅 Producción — corte: {_fmt_fecha(produccion['fecha'])} (dato de carga manual, no diario)",
            f"**Petróleo:** {_fmt_es(produccion['petroleo_bbl'])} bbl/día",
            f"**Gas fiscalizado:** {_fmt_es(fiscalizado, 1)} Mpcd",
            f"**Gas comercializado:** {_fmt_es(comercializado, 1)} Mpcd",
        ]
        if brecha is not None:
            pct_brecha = (brecha / float(fiscalizado) * 100) if fiscalizado else 0
            lines.append(f"**Brecha fiscalización-comercialización:** {_fmt_es(brecha, 1)} Mpcd ({pct_brecha:.1f}% sin comercializar)")
    else:
        lines.append("Sin datos de producción diaria cargados.")

    if commodities:
        lines += ["", "**Precios de referencia (actualización diaria):**"]
        for c in commodities:
            signo = "+" if (c["variacion_abs"] or 0) >= 0 else ""
            lines.append(
                f"• {c['commodity']} ({_fmt_fecha(c['fecha'])}): USD {c['valor_usd']:.2f} "
                f"({signo}{c['variacion_abs']:.2f} / {signo}{c['variacion_pct']:.2f}%)"
            )

    if top5:
        lines += ["", "**Top campos del mes más reciente:**"]
        por_categoria: Dict[str, List[Any]] = {}
        for t in top5:
            por_categoria.setdefault(t["categoria"], []).append(t)
        for categoria, items in por_categoria.items():
            lines.append(f"_{categoria}_")
            for it in items[:5]:
                lines.append(f"  • {it['nombre']}: {_fmt_es(it['valor'], 1)} {it['unidad']}")

    return "\n".join(lines)


def _make_handler(titulo: str, fn):
    """Factoría: crea un método async de handler para una consulta de hidrocarburos."""

    @handle_service_error
    async def _handler(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []
        try:
            texto = await asyncio.to_thread(fn)
            data.update({"tipo": "hidrocarburos_texto", "titulo": titulo, "texto": texto})
        except Exception as exc:
            logger.error("[%s] %s", titulo, exc, exc_info=True)
            errors.append(ErrorDetail(code="DB_ERROR", message=str(exc)))
        return data, errors

    _handler.__name__ = f"_handle_{titulo.lower().replace(' ', '_')}"
    return _handler


class HidrocarburosHandlerMixin:
    """
    Mixin que expone datos duros de hidrocarburos (presupuesto, producción,
    precios WTI/Brent) al orquestador del portal — distinto del intent
    "hidrocarburos" ya existente (libre_noticias_handler.py), que solo filtra
    noticias por keyword y no trae ninguno de estos datos.
    """

    _handle_hidrocarburos_presupuesto = _make_handler("💰 Presupuesto hidrocarburos", _q_hidrocarburos_presupuesto)
    _handle_hidrocarburos_produccion = _make_handler("🛢️ Producción hidrocarburos", _q_hidrocarburos_produccion)
