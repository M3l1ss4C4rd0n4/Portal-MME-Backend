"""
Mixin: Ejecución presupuestal DEE — totales + top proyectos.
Replica métricas de presupuesto.resumen.
"""
import asyncio
import logging
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.database.connection import connection_manager

logger = logging.getLogger(__name__)


def _fmt_cop(val) -> str:
    if val is None:
        return "N/D"
    v = float(val)
    if abs(v) >= 1e12:
        return f"${v / 1e12:,.2f} billones"
    if abs(v) >= 1e9:
        return f"${v / 1e9:,.2f} mil millones"
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.2f} millones"
    return f"${v:,.0f}"


def _fmt_pct(val) -> float:
    if val is None:
        return 0.0
    f = float(val)
    return round(f * 100, 1) if f <= 1 else round(f, 1)


def _fetch_presupuesto_resumen() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    SUM(apropiacion) AS apropiacion,
                    SUM(compromisos) AS comprometido,
                    SUM(compromisos) / NULLIF(SUM(apropiacion), 0) * 100 AS pct_comprometido,
                    SUM(obligados) AS obligados,
                    SUM(obligados)::numeric / NULLIF(SUM(apropiacion), 0) * 100 AS pct_obligado,
                    SUM(sin_comprometer_disponible) AS disponible
                FROM presupuesto.resumen
                WHERE proyecto NOT IN ('Proyecto', 'TOTAL')
            """)
            tot = cur.fetchone() or {}

            cur.execute("""
                SELECT
                    proyecto,
                    apropiacion,
                    compromisos AS comprometido,
                    comprometido AS pct_comprometido,
                    obligados,
                    obligado AS pct_obligado
                FROM presupuesto.resumen
                WHERE proyecto NOT IN ('Proyecto', 'TOTAL')
                ORDER BY apropiacion DESC
                LIMIT 5
            """)
            proyectos = cur.fetchall()

            cur.execute("SELECT MAX(fecha_carga) FROM presupuesto.resumen")
            fecha_row = cur.fetchone() or {}
            fecha = fecha_row.get("max")

    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"
    pct_comp = _fmt_pct(tot.get("pct_comprometido"))
    pct_obl = _fmt_pct(tot.get("pct_obligado"))

    totales = {
        "apropiacion": _fmt_cop(tot.get("apropiacion")),
        "comprometido": _fmt_cop(tot.get("comprometido")),
        "pct_comprometido": pct_comp,
        "obligados": _fmt_cop(tot.get("obligados")),
        "pct_obligado": pct_obl,
        "disponible": _fmt_cop(tot.get("disponible")),
    }

    top_proyectos = [
        {
            "proyecto": r["proyecto"],
            "apropiacion": _fmt_cop(r.get("apropiacion")),
            "comprometido": _fmt_cop(r.get("comprometido")),
            "pct_comprometido": _fmt_pct(r.get("pct_comprometido")),
            "obligados": _fmt_cop(r.get("obligados")),
        }
        for r in proyectos
    ]

    return {
        "titulo": "Ejecución Presupuestal DEE",
        "fecha_corte": fecha_str,
        "totales": totales,
        "top_proyectos": top_proyectos,
        "opcion_regresar": {
            "id": "menu",
            "titulo": "🔙 Regresar al menú principal",
        },
    }


class PresupuestoHandlerMixin:
    """Resumen del tablero de ejecución presupuestal."""

    @handle_service_error
    async def _handle_presupuesto_menu(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data = await asyncio.to_thread(_fetch_presupuesto_resumen)
        return data, []
