"""
Mixin: Comunidades energéticas — 4 subsecciones del portal.
Implementadas, Contratos OR, Fenoge 1.0/1.1 y Colombia Solar.
"""
import asyncio
import logging
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.database.connection import connection_manager

logger = logging.getLogger(__name__)

_REGRESAR_COMUNIDADES = {
    "id": "comunidades_menu",
    "titulo": "🔙 Comunidades energéticas",
}
_REGRESAR_MENU = {
    "id": "menu",
    "titulo": "🔙 Menú principal",
}


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


def _fetch_comunidades_menu() -> Dict[str, Any]:
    return {
        "titulo": "Comunidades Energéticas",
        "mensaje": (
            "Capítulo 2 del portal: cuatro tableros integrados — "
            "implementadas, Contratos OR, Fenoge y Colombia Solar."
        ),
        "secciones": [
            {"id": "comunidades_implementadas", "titulo": "Implementadas", "emoji": "🏘️"},
            {"id": "contratos_or_menu", "titulo": "Contratos OR", "emoji": "📄"},
            {"id": "fenoge_menu", "titulo": "Fenoge 1.0 / 1.1", "emoji": "☀️"},
            {"id": "colombia_solar_menu", "titulo": "Colombia Solar", "emoji": "🌞"},
        ],
        "opcion_regresar": _REGRESAR_MENU,
    }


def _fetch_comunidades_implementadas() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS implementadas,
                    SUM(capacidad_de_generacion_kwp) AS capacidad_kwp,
                    SUM(usuarios_equivalentes) AS usuarios_equiv,
                    SUM(CASE WHEN inversion_estimada IS NOT NULL
                              AND inversion_estimada ~ '^[0-9]'
                         THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                         ELSE 0 END) AS inversion_estimada
                FROM comunidades.base
                WHERE implementado = 'Si'
            """)
            k = cur.fetchone() or {}

            cur.execute("""
                SELECT departamento, COUNT(*) AS count,
                       SUM(capacidad_de_generacion_kwp) AS capacidad
                FROM comunidades.base
                WHERE implementado = 'Si' AND departamento IS NOT NULL
                GROUP BY departamento
                ORDER BY count DESC
                LIMIT 5
            """)
            top_deptos = cur.fetchall()

            cur.execute("SELECT MAX(fecha_carga) FROM comunidades.base")
            fecha = (cur.fetchone() or {}).get("max")

    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"
    return {
        "titulo": "Comunidades implementadas",
        "subtitulo": "Resumen de CE en operación (comunidades.base)",
        "fecha_corte": fecha_str,
        "kpis": [
            {"label": "Comunidades", "valor": int(k.get("implementadas") or 0), "unidad": "CEs", "emoji": "🏘️"},
            {"label": "Capacidad", "valor": round(float(k.get("capacidad_kwp") or 0), 1), "unidad": "kWp", "emoji": "⚡"},
            {"label": "Usuarios equiv.", "valor": int(k.get("usuarios_equiv") or 0), "unidad": "", "emoji": "👥"},
            {"label": "Inversión est.", "valor": _fmt_cop(k.get("inversion_estimada")), "unidad": "", "emoji": "💰"},
        ],
        "top_departamentos": [
            {
                "departamento": r["departamento"],
                "count": int(r["count"] or 0),
                "capacidad_kwp": round(float(r["capacidad"] or 0), 1),
            }
            for r in top_deptos
        ],
        "opcion_regresar": _REGRESAR_COMUNIDADES,
    }


def _fetch_contratos_or() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH pagados AS (
                    SELECT nombre_proyecto_id, nro_desembolso
                    FROM contratos_or.seguimiento
                    WHERE necesaria_para_desembolso = 'Sí'
                    GROUP BY nombre_proyecto_id, nro_desembolso
                    HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                )
                SELECT
                    COUNT(DISTINCT s.nombre_proyecto_id) AS n_contratos,
                    ROUND(AVG(s.avance) * 100, 1) AS avance_general,
                    ROUND(COALESCE(SUM(
                        CASE WHEN p.nro_desembolso IS NOT NULL AND s.desembolso IS NOT NULL
                             THEN s.desembolso ELSE 0 END
                    ), 0) / NULLIF(COUNT(DISTINCT s.nombre_proyecto_id), 0) * 100, 1) AS avance_financiero,
                    COUNT(DISTINCT CASE WHEN p.nro_desembolso IS NOT NULL
                          THEN s.nombre_proyecto_id || '-' || s.nro_desembolso::text END) AS pagos_realizados,
                    COUNT(DISTINCT s.nombre_proyecto_id) *
                        COUNT(DISTINCT CASE WHEN s.nro_desembolso IS NOT NULL
                              THEN s.nro_desembolso END) AS pagos_posibles
                FROM contratos_or.seguimiento s
                LEFT JOIN pagados p
                    ON s.nombre_proyecto_id = p.nombre_proyecto_id
                   AND s.nro_desembolso = p.nro_desembolso
                   AND s.necesaria_para_desembolso = 'Sí'
            """)
            g = cur.fetchone() or {}

            cur.execute("""
                WITH pagados AS (
                    SELECT nombre_proyecto_id, nro_desembolso
                    FROM contratos_or.seguimiento
                    WHERE necesaria_para_desembolso = 'Sí'
                    GROUP BY nombre_proyecto_id, nro_desembolso
                    HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                )
                SELECT s.nombre_proyecto_id AS nombre,
                       ROUND(AVG(s.avance) * 100, 1) AS avance
                FROM contratos_or.seguimiento s
                LEFT JOIN pagados p ON s.nombre_proyecto_id = p.nombre_proyecto_id
                GROUP BY s.nombre_proyecto_id
                ORDER BY avance DESC
                LIMIT 5
            """)
            top = cur.fetchall()

            cur.execute("SELECT MAX(fecha_carga) FROM contratos_or.seguimiento")
            fecha = (cur.fetchone() or {}).get("max")

    pag_real = int(g.get("pagos_realizados") or 0)
    pag_pos = int(g.get("pagos_posibles") or 0)
    pct_pagos = round(pag_real / pag_pos * 100, 1) if pag_pos else 0.0
    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"

    return {
        "titulo": "Contratos OR",
        "subtitulo": "Seguimiento desembolsos comunidades energéticas",
        "fecha_corte": fecha_str,
        "kpis": [
            {"label": "Contratos", "valor": int(g.get("n_contratos") or 0), "unidad": "", "emoji": "📄"},
            {"label": "Avance general", "valor": float(g.get("avance_general") or 0), "unidad": "%", "emoji": "🏗️"},
            {"label": "Avance financiero", "valor": float(g.get("avance_financiero") or 0), "unidad": "%", "emoji": "💳"},
            {"label": "Pagos realizados", "valor": pct_pagos, "unidad": "%", "emoji": "✅"},
        ],
        "top_proyectos": [{"nombre": r["nombre"], "avance": float(r["avance"] or 0)} for r in top],
        "opcion_regresar": _REGRESAR_COMUNIDADES,
    }


def _fetch_fenoge() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_ces,
                    SUM(kwp) AS total_kwp,
                    SUM(beneficiarios) AS beneficiarios,
                    SUM(valor_proyecto) AS inversion
                FROM fenoge.comunidades
            """)
            k = cur.fetchone() or {}

            cur.execute("""
                SELECT COALESCE(NULLIF(TRIM(fase), ''), 'Sin clasificar') AS fase,
                       COUNT(*) AS count, SUM(kwp) AS kwp
                FROM fenoge.comunidades
                GROUP BY 1 ORDER BY count DESC
            """)
            por_fase = cur.fetchall()

            cur.execute("SELECT MAX(fecha_carga) FROM fenoge.comunidades")
            fecha = (cur.fetchone() or {}).get("max")

    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"
    return {
        "titulo": "Fenoge 1.0 / 1.1",
        "subtitulo": "Programa Fenoge — comunidades energéticas",
        "fecha_corte": fecha_str,
        "kpis": [
            {"label": "Comunidades", "valor": int(k.get("total_ces") or 0), "unidad": "CEs", "emoji": "☀️"},
            {"label": "Capacidad", "valor": round(float(k.get("total_kwp") or 0), 1), "unidad": "kWp", "emoji": "⚡"},
            {"label": "Beneficiarios", "valor": int(k.get("beneficiarios") or 0), "unidad": "", "emoji": "👥"},
            {"label": "Valor proyectos", "valor": _fmt_cop(k.get("inversion")), "unidad": "", "emoji": "💰"},
        ],
        "por_fase": [
            {"fase": r["fase"], "count": int(r["count"] or 0), "kwp": round(float(r["kwp"] or 0), 1)}
            for r in por_fase
        ],
        "opcion_regresar": _REGRESAR_COMUNIDADES,
    }


def _fetch_colombia_solar() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS filas FROM colombia_solar.base")
            base_n = int((cur.fetchone() or {}).get("filas") or 0)

            cur.execute("SELECT COUNT(DISTINCT proyecto) AS n FROM colombia_solar.proyectado_usuarios")
            n_proy = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute("""
                SELECT COUNT(DISTINCT departamento) AS n
                FROM colombia_solar.base
                WHERE departamento IS NOT NULL AND TRIM(departamento) != ''
            """)
            n_deptos = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute("SELECT MAX(fecha_carga) FROM colombia_solar.base")
            fecha = (cur.fetchone() or {}).get("max")

    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else "N/D"
    return {
        "titulo": "Colombia Solar",
        "subtitulo": "Curva S — programación vs avance reportado (OR)",
        "fecha_corte": fecha_str,
        "kpis": [
            {"label": "Proyectos OR", "valor": n_proy, "unidad": "", "emoji": "🌞"},
            {"label": "Registros base", "valor": base_n, "unidad": "", "emoji": "📊"},
            {"label": "Departamentos", "valor": n_deptos, "unidad": "", "emoji": "🗺️"},
        ],
        "nota": (
            "Incluye curvas S de obras civiles, usuarios, potencia e internas "
            "según el tablero Colombia Solar del portal."
        ),
        "opcion_regresar": _REGRESAR_COMUNIDADES,
    }


class ComunidadesHandlerMixin:
    """Capítulo 2 — Comunidades energéticas (4 subsecciones)."""

    @handle_service_error
    async def _handle_comunidades_menu(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_comunidades_menu), []

    @handle_service_error
    async def _handle_comunidades_implementadas(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_comunidades_implementadas), []

    @handle_service_error
    async def _handle_contratos_or_menu(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_contratos_or), []

    @handle_service_error
    async def _handle_fenoge_menu(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_fenoge), []

    @handle_service_error
    async def _handle_colombia_solar_menu(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_colombia_solar), []
