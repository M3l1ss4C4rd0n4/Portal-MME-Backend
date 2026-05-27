"""
Mixin: Supervisión — KPIs del dashboard de contratos MinMinas.
Replica métricas de supervision.contratos (sin filtros).
"""
import asyncio
import logging
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from domain.services.supervision_parsing import sql_parse_cop, sql_parse_int
from infrastructure.database.connection import connection_manager

logger = logging.getLogger(__name__)

_ANO_MIN = 2003
_ANO_MAX = 2026

_PARSE_FIN = """
    CASE
      WHEN porcentaje_de_desembolsos ~ '[0-9]' AND porcentaje_de_desembolsos ~ '%%'
        THEN CAST(REPLACE(REPLACE(TRIM(porcentaje_de_desembolsos),'%%',''),',','.') AS numeric) / 100
      WHEN porcentaje_de_desembolsos ~ '^[0-9.]'
           AND TRIM(porcentaje_de_desembolsos) ~ '^[0-9. ]+$'
        THEN CAST(TRIM(porcentaje_de_desembolsos) AS numeric)
    END
"""

_PARSE_AR = sql_parse_cop("valor_por_proyecto_informacion_apoyos_tecnicos")
_PARSE_AU = sql_parse_cop("valor_desembolsado_informacion_apoyos_financieros")
_PARSE_AV = sql_parse_cop("valor_por_desembolsar")
_PARSE_UC = sql_parse_int("numero_de_usuarios_totales_contratados")
_PARSE_UF = sql_parse_int("numero_de_usuarios_totales_finales")


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


def _fetch_supervision_resumen() -> Dict[str, Any]:
    base_where = f"""
        FLOOR(ano)::integer BETWEEN {_ANO_MIN} AND {_ANO_MAX}
        AND estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) != ''
    """

    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    (SELECT COUNT(DISTINCT contrato) FROM supervision.contratos
                      WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                        AND FLOOR(ano)::integer BETWEEN {_ANO_MIN} AND {_ANO_MAX}) AS n_contratos,
                    COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                        THEN contrato END) AS en_ejecucion,
                    ROUND(AVG(avance_de_obra) * 100, 2) AS avg_avance_fisico,
                    ROUND(AVG({_PARSE_FIN}) * 100, 2) AS avg_avance_financiero,
                    COALESCE(SUM({_PARSE_AR}), 0) AS sum_ar,
                    COALESCE(SUM({_PARSE_AU}), 0) AS sum_au,
                    COALESCE(SUM({_PARSE_AV}), 0) AS sum_av,
                    COALESCE(SUM({_PARSE_UC}), 0) AS sum_usuarios_contratados,
                    COALESCE(SUM({_PARSE_UF}), 0) AS sum_usuarios_finales
                FROM supervision.contratos
                WHERE {base_where}
                """
            )
            k = cur.fetchone() or {}

            cur.execute(
                f"""
                SELECT fondo, COUNT(DISTINCT contrato) AS contratos
                FROM supervision.contratos
                WHERE {base_where}
                  AND fondo IS NOT NULL AND TRIM(fondo) != ''
                GROUP BY fondo
                ORDER BY contratos DESC
                LIMIT 5
                """
            )
            fondos = cur.fetchall()

            cur.execute("SELECT MAX(fecha_carga) FROM supervision.contratos")
            fecha_row = cur.fetchone() or {}
            fecha = fecha_row.get("max")

    sum_au = float(k.get("sum_au") or 0)
    sum_av = float(k.get("sum_av") or 0)
    ejecutado = sum_au + sum_av
    pct_desembolsado = round(sum_au / ejecutado * 100, 1) if ejecutado > 0 else 0.0
    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"

    kpis = [
        {
            "label": "Contratos",
            "valor": int(k.get("n_contratos") or 0),
            "unidad": "",
            "emoji": "📄",
        },
        {
            "label": "En ejecución",
            "valor": int(k.get("en_ejecucion") or 0),
            "unidad": "contratos",
            "emoji": "🔧",
        },
        {
            "label": "Avance físico promedio",
            "valor": round(float(k.get("avg_avance_fisico") or 0), 1),
            "unidad": "%",
            "emoji": "🏗️",
        },
        {
            "label": "Avance financiero promedio",
            "valor": round(float(k.get("avg_avance_financiero") or 0), 1),
            "unidad": "%",
            "emoji": "💳",
        },
        {
            "label": "Usuarios contratados",
            "valor": int(k.get("sum_usuarios_contratados") or 0),
            "unidad": "",
            "emoji": "👥",
        },
        {
            "label": "% desembolsado",
            "valor": pct_desembolsado,
            "unidad": "%",
            "emoji": "💰",
        },
    ]

    top_fondos = [
        {"fondo": r["fondo"], "contratos": int(r["contratos"] or 0)}
        for r in fondos
    ]

    return {
        "titulo": "Supervisión de Contratos",
        "fecha_corte": fecha_str,
        "kpis": kpis,
        "top_fondos": top_fondos,
        "financiero": {
            "valor_proyecto": _fmt_cop(k.get("sum_ar")),
            "desembolsado": _fmt_cop(sum_au),
            "por_desembolsar": _fmt_cop(sum_av),
        },
        "opcion_regresar": {
            "id": "menu",
            "titulo": "🔙 Regresar al menú principal",
        },
    }


class SupervisionHandlerMixin:
    """Resumen del tablero de supervisión de contratos."""

    @handle_service_error
    async def _handle_supervision_menu(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data = await asyncio.to_thread(_fetch_supervision_resumen)
        return data, []
