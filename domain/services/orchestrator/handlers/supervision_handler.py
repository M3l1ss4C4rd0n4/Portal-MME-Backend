"""
Mixin: Supervisión — KPIs del dashboard de contratos MinMinas.
Replica métricas de supervision.contratos (sin filtros).
"""
import asyncio
from infrastructure.logging.logger import get_logger
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from domain.services.supervision_parsing import (
    ETAPA_BUCKETS,
    kpi_filter_where,
    sql_parse_cop_guarded,
    sql_parse_int,
    sql_parse_pct,
)
from infrastructure.database.connection import connection_manager

logger = get_logger(__name__)

_ANO_MIN = 2003
_ANO_MAX = 2026

# Corregido 2026-09-08: antes era una copia local del CASE de % desembolsos,
# sin el cast a ::text ni el guardrail de valores anómalos (>100%) que
# api/v1/routes/supervision_portal.py ya tenía desde 2026-06-20 — la corrección
# de datos nunca había llegado a este handler. Ahora es la misma fuente
# (domain/services/supervision_parsing.py::sql_parse_pct), una sola vez.
_PARSE_FIN = sql_parse_pct("porcentaje_de_desembolsos")

# Estados/etapas reales de estado_actividad_fase_administracion_de_la_construccion_y_puest
# — describe la ACTIVIDAD de AOM (Administración, Operación y Mantenimiento) de
# cada contrato, NO el estado global del contrato (estado_del_contrato). Es el
# único lugar donde existe el literal "Suspendida" — nunca debe presentarse como
# si fuera un "estado del contrato".
_COL_ACTIVIDAD_AOM = "estado_actividad_fase_administracion_de_la_construccion_y_puest"

# Corregido 2026-09-08: antes usaban sql_parse_cop() sin el guardrail de escala
# anómala (>1e11 → NULL) que supervision_portal.py sí tenía desde 2026-06-20 —
# producían cifras como "$1,112,017.72 billones" para por_desembolsar.
_PARSE_AR = sql_parse_cop_guarded("valor_por_proyecto_informacion_apoyos_tecnicos")
_PARSE_AU = sql_parse_cop_guarded("valor_desembolsado_informacion_apoyos_financieros")
_PARSE_AV = sql_parse_cop_guarded("valor_por_desembolsar")
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
                    (SELECT COUNT(DISTINCT contratos) FROM supervision.contratos
                      WHERE contratos IS NOT NULL AND TRIM(contratos) != ''
                        AND FLOOR(ano)::integer BETWEEN {_ANO_MIN} AND {_ANO_MAX}) AS n_contratos,
                    COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                        THEN contratos END) AS en_ejecucion,
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
                SELECT fondo, COUNT(DISTINCT contratos) AS contratos
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


def _fetch_supervision_por_estado(
    estado: str = None,
    etapa: str = None,
    fondo: str = None,
    departamento: str = None,
    municipio: str = None,
    ano_min: int = _ANO_MIN,
    ano_max: int = _ANO_MAX,
) -> Dict[str, Any]:
    """Desglose de supervision.contratos por estado/etapa, con filtros opcionales.

    Reusa la misma lógica de filtros/buckets ya construida y probada en
    producción por api/v1/routes/supervision_portal.py (dashboard real del
    portal), vía domain/services/supervision_parsing.py.

    Siempre incluye, además, el bloque `actividad_aom` (estado de la actividad
    de AOM de cada contrato) — un concepto DISTINTO del estado del contrato,
    donde vive el único literal "Suspendida" que existe en el esquema. Nunca
    debe confundirse con "contratos suspendidos" (ese estado NO existe a nivel
    de contrato — estado_del_contrato solo tiene FINALIZADO/VIGENTE/POR INICIAR).
    """
    etapa_bucket = etapa if etapa in ETAPA_BUCKETS else None
    etapa_exacta = None if etapa_bucket else etapa

    where_total, params_total = kpi_filter_where(
        ano_min, ano_max, fondo, estado, etapa_exacta, departamento, municipio
    )
    bucket_sql = f" AND ({ETAPA_BUCKETS[etapa_bucket]})" if etapa_bucket else ""

    # WHEREs "sin X" — para desglosar por X, los demás filtros siguen aplicando
    # pero el propio eje que se está desglosando no se preseleciona.
    where_sin_estado, params_sin_estado = kpi_filter_where(
        ano_min, ano_max, fondo, None, etapa_exacta, departamento, municipio
    )
    where_sin_etapa, params_sin_etapa = kpi_filter_where(
        ano_min, ano_max, fondo, estado, None, departamento, municipio
    )
    # La actividad de AOM es un eje distinto de estado/etapa — nunca se filtra por ellos.
    where_aom, params_aom = kpi_filter_where(
        ano_min, ano_max, fondo, None, None, departamento, municipio
    )

    bucket_selects = ", ".join(
        f"COUNT(DISTINCT CASE WHEN {cond} THEN contratos END) AS bucket_{name}"
        for name, cond in ETAPA_BUCKETS.items()
    )

    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT contratos) AS total
                FROM supervision.contratos
                WHERE {where_total} {bucket_sql}
                """,
                params_total,
            )
            total = int((cur.fetchone() or {}).get("total") or 0)

            cur.execute(
                """
                SELECT DISTINCT estado_del_contrato AS valor
                FROM supervision.contratos
                WHERE estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) != ''
                """
            )
            estados_reales = sorted(r["valor"] for r in cur.fetchall())

            cur.execute(
                """
                SELECT DISTINCT etapa_del_contrato AS valor
                FROM supervision.contratos
                WHERE etapa_del_contrato IS NOT NULL AND TRIM(etapa_del_contrato) != ''
                """
            )
            etapas_reales = sorted(r["valor"] for r in cur.fetchall())

            cur.execute(
                f"""
                SELECT estado_del_contrato AS valor, COUNT(DISTINCT contratos) AS n
                FROM supervision.contratos
                WHERE {where_sin_estado} {bucket_sql}
                GROUP BY estado_del_contrato ORDER BY n DESC
                """,
                params_sin_estado,
            )
            por_estado = cur.fetchall()

            cur.execute(
                f"""
                SELECT etapa_del_contrato AS valor, COUNT(DISTINCT contratos) AS n
                FROM supervision.contratos
                WHERE {where_sin_etapa}
                  AND etapa_del_contrato IS NOT NULL AND TRIM(etapa_del_contrato) != ''
                GROUP BY etapa_del_contrato ORDER BY n DESC LIMIT 15
                """,
                params_sin_etapa,
            )
            por_etapa = cur.fetchall()

            cur.execute(
                f"""
                SELECT {bucket_selects}
                FROM supervision.contratos
                WHERE {where_sin_etapa}
                """,
                params_sin_etapa,
            )
            buckets_row = cur.fetchone() or {}
            por_etapa_agrupada = {
                name: int(buckets_row.get(f"bucket_{name}") or 0) for name in ETAPA_BUCKETS
            }

            cur.execute(
                f"""
                SELECT {_COL_ACTIVIDAD_AOM} AS valor, COUNT(DISTINCT contratos) AS n
                FROM supervision.contratos
                WHERE {where_aom}
                  AND {_COL_ACTIVIDAD_AOM} IS NOT NULL AND TRIM({_COL_ACTIVIDAD_AOM}) != ''
                GROUP BY {_COL_ACTIVIDAD_AOM} ORDER BY n DESC
                """,
                params_aom,
            )
            actividad_aom_rows = cur.fetchall()

    resultado: Dict[str, Any] = {
        "titulo": "Contratos de Supervisión — desglose por estado/etapa",
        "filtros_aplicados": {
            k: v
            for k, v in {
                "estado": estado,
                "etapa": etapa,
                "fondo": fondo,
                "departamento": departamento,
                "municipio": municipio,
            }.items()
            if v is not None
        },
        "total_contratos": total,
        "por_estado": [
            {"estado": r["valor"], "contratos": int(r["n"])} for r in por_estado
        ],
        "por_etapa": [
            {"etapa": r["valor"], "contratos": int(r["n"])} for r in por_etapa
        ],
        "por_etapa_agrupada": por_etapa_agrupada,
        "actividad_aom": {
            "nota": (
                "Estado de la ACTIVIDAD de AOM (Administración, Operación y "
                "Mantenimiento) de cada contrato — un concepto DISTINTO del "
                "estado global del contrato (estado_del_contrato). Un contrato "
                "con actividad AOM 'Suspendida' puede seguir estando VIGENTE "
                "o FINALIZADO a nivel de contrato. NUNCA presentes este dato "
                "como si fuera 'contratos suspendidos'."
            ),
            "valores": [
                {"actividad": r["valor"], "contratos": int(r["n"])}
                for r in actividad_aom_rows
            ],
        },
        "estados_reales_existentes": estados_reales,
    }

    if estado is not None and estado not in estados_reales:
        resultado["advertencia_estado"] = (
            f"El valor de 'estado' recibido ('{estado}') no coincide con ningún "
            f"estado real registrado. Los únicos valores reales de "
            f"estado_del_contrato son: {', '.join(estados_reales)}. Si la "
            "pregunta era sobre contratos 'suspendidos', ese estado no existe "
            "a nivel de contrato — revisa el bloque 'actividad_aom' de esta "
            "misma respuesta (es un dato real, pero de un concepto distinto)."
        )

    if etapa is not None and etapa_bucket is None and etapa not in etapas_reales:
        resultado["advertencia_etapa"] = (
            f"El valor de 'etapa' recibido ('{etapa}') no coincide con ninguna "
            f"etapa real ni con una categoría agrupada válida "
            f"({', '.join(ETAPA_BUCKETS)}). Etapas reales registradas: "
            f"{', '.join(etapas_reales)}."
        )

    return resultado


class SupervisionHandlerMixin:
    """Resumen del tablero de supervisión de contratos."""

    @handle_service_error
    async def _handle_supervision_menu(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data = await asyncio.to_thread(_fetch_supervision_resumen)
        return data, []

    @handle_service_error
    async def _handle_supervision_contratos_por_estado(
        self,
        parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        data = await asyncio.to_thread(
            _fetch_supervision_por_estado,
            estado=parameters.get("estado"),
            etapa=parameters.get("etapa"),
            fondo=parameters.get("fondo"),
            departamento=parameters.get("departamento"),
            municipio=parameters.get("municipio"),
            ano_min=int(parameters.get("ano_min") or _ANO_MIN),
            ano_max=int(parameters.get("ano_max") or _ANO_MAX),
        )
        return data, []
