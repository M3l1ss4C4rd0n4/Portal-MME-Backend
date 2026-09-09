"""
Mixin: Comunidades energéticas — 4 subsecciones del portal.
Implementadas, Contratos OR, Fenoge 1.0/1.1 y Colombia Solar.
"""
import asyncio
from infrastructure.logging.logger import get_logger
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.contratos_or_parsing import fetch_contratos_or_kpis
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.database.connection import connection_manager

logger = get_logger(__name__)

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
                    SUM(COALESCE(CASE WHEN inversion_estimada IS NULL THEN NULL
                         WHEN inversion_estimada::text ~ '^[0-9.-]+'
                         THEN REPLACE(REPLACE(inversion_estimada::text, '$', ''), ',', '')::numeric
                         ELSE NULL END, 0)) AS inversion_estimada
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
    """Corregido 2026-09-09: antes referenciaba contratos_or.seguimiento, una
    tabla que ya no existe (fue reemplazada por seguimiento_avance_fisico/
    seguimiento_avance_documental/resumen cuando el ETL se reestructuró) —
    fallaba en el 100% de las invocaciones, capturado en silencio por
    handle_service_error. Ahora reusa fetch_contratos_or_kpis(), la misma
    lógica ya probada en producción por api/v1/routes/contratos_or.py
    (el tablero real /contratos-or)."""
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            r = fetch_contratos_or_kpis(cur)

    top = sorted(
        r["proyectos"], key=lambda p: p["avance_general"] or 0, reverse=True
    )[:5]

    return {
        "titulo": "Contratos OR",
        "subtitulo": "Seguimiento desembolsos comunidades energéticas",
        "fecha_corte": r["fecha_corte"] or "N/D",
        "kpis": [
            {"label": "Contratos", "valor": r["n_contratos"], "unidad": "", "emoji": "📄"},
            {"label": "Avance documental", "valor": r["avance_general"], "unidad": "%", "emoji": "🏗️"},
            {"label": "Avance financiero", "valor": r["avance_financiero"], "unidad": "%", "emoji": "💳"},
            {"label": "Avance físico", "valor": r["avance_fisico"], "unidad": "%", "emoji": "🔧"},
            {"label": "Pagos realizados", "valor": r["pct_pagos_realizados"], "unidad": "%", "emoji": "✅"},
        ],
        "top_proyectos": [
            {"nombre": p["nombre"], "avance": p["avance_general"] or 0.0} for p in top
        ],
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
            # Curva S — MISMA fuente que el tablero real /colombia-solar
            # (portal-direccion-mme/src/lib/colombia-solar-curva-s.ts).
            cur.execute("SELECT COUNT(DISTINCT proyecto) AS n FROM colombia_solar.proyectado_usuarios")
            n_proy = int((cur.fetchone() or {}).get("n") or 0)

            cur.execute("SELECT MAX(fecha_carga) FROM colombia_solar.proyectado_usuarios")
            fecha_curva = (cur.fetchone() or {}).get("max")

            # colombia_solar.base — fuente DISTINTA (registro planeado vs.
            # ejecutado por proyecto), que el tablero de curva S NO usa.
            # Corregido 2026-09-09: antes se mezclaba bajo un solo resumen sin
            # aclarar que viene de otra tabla — separado y etiquetado explícito.
            cur.execute("""
                SELECT
                    COUNT(DISTINCT departamento) FILTER (WHERE departamento IS NOT NULL AND TRIM(departamento) != '') AS n_deptos,
                    SUM(planeado_usuarios) AS planeado_usuarios,
                    SUM(ejecutado_usuarios) AS ejecutado_usuarios,
                    SUM(capacidad_kwp_planeada) AS kwp_planeada,
                    SUM(capacidad_kwp_ejecutada) AS kwp_ejecutada,
                    SUM(inversion) AS inversion
                FROM colombia_solar.base
            """)
            b = cur.fetchone() or {}

            cur.execute("SELECT MAX(fecha_carga) FROM colombia_solar.base")
            fecha_base = (cur.fetchone() or {}).get("max")

    planeado = float(b.get("planeado_usuarios") or 0)
    ejecutado = float(b.get("ejecutado_usuarios") or 0)
    pct_avance = round(ejecutado / planeado * 100, 1) if planeado else 0.0
    fecha_str = fecha_curva.strftime("%d/%m/%Y") if fecha_curva else "N/D"
    return {
        "titulo": "Colombia Solar",
        "subtitulo": "Curva S — programación vs avance reportado (OR)",
        "fecha_corte": fecha_str,
        "kpis": [
            {"label": "Proyectos OR (curva S)", "valor": n_proy, "unidad": "", "emoji": "🌞"},
        ],
        "registro_planeado_vs_ejecutado": {
            "nota": (
                "Fuente DISTINTA a la curva S de arriba — colombia_solar.base, "
                "un registro de avance planeado vs. ejecutado por proyecto, "
                "sin cruce directo con los 'Proyectos OR' de la curva S. "
                "No mezclar ambas cifras como si fueran la misma fuente."
            ),
            "fecha_corte": fecha_base.strftime("%d/%m/%Y") if fecha_base else "N/D",
            "departamentos": int(b.get("n_deptos") or 0),
            "usuarios_planeados": int(planeado),
            "usuarios_ejecutados": int(ejecutado),
            "pct_avance_usuarios": pct_avance,
            "capacidad_kwp_planeada": round(float(b.get("kwp_planeada") or 0), 1),
            "capacidad_kwp_ejecutada": round(float(b.get("kwp_ejecutada") or 0), 1),
            "inversion": _fmt_cop(b.get("inversion")),
        },
        "nota": (
            "Incluye curvas S de obras civiles, usuarios, potencia e internas "
            "según el tablero Colombia Solar del portal."
        ),
        "opcion_regresar": _REGRESAR_COMUNIDADES,
    }


def _fetch_fenoge_seguimiento() -> Dict[str, Any]:
    """Nuevo 2026-09-09: avance real vs. programado de FENOGE, dato descrito
    por el propio catálogo de tableros ('seguimiento financiero de proyectos
    real vs. programado') pero que ninguna tool cubría — fenoge_menu solo da
    totales estáticos. Reusa fenoge.seguimiento, la misma tabla que alimenta
    GET /v1/fenoge/seguimiento (api/v1/routes/fenoge.py) — toma el dato más
    reciente por contrato (las fechas de corte varían entre contratos)."""
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (numero_contrato)
                    numero_contrato, region, nombre_comunidad, dia_actualizacion,
                    avance_real_acumulado_pct, avance_programado_acumulado_pct
                FROM fenoge.seguimiento
                WHERE numero_contrato IS NOT NULL
                  AND dia_actualizacion IS NOT NULL
                  AND (avance_real_acumulado_pct IS NOT NULL
                       OR avance_programado_acumulado_pct IS NOT NULL)
                ORDER BY numero_contrato, dia_actualizacion DESC
            """)
            rows = cur.fetchall()

    contratos: List[Dict[str, Any]] = []
    for r in rows:
        real = float(r["avance_real_acumulado_pct"]) * 100 if r["avance_real_acumulado_pct"] is not None else None
        prog = float(r["avance_programado_acumulado_pct"]) * 100 if r["avance_programado_acumulado_pct"] is not None else None
        contratos.append({
            "contrato": r["numero_contrato"],
            "region": r["region"] or "Sin región",
            "comunidad": r["nombre_comunidad"],
            "fecha_ultimo_dato": r["dia_actualizacion"].strftime("%d/%m/%Y") if r["dia_actualizacion"] else None,
            "avance_real_pct": round(real, 1) if real is not None else None,
            "avance_programado_pct": round(prog, 1) if prog is not None else None,
            "brecha_pct": round(real - prog, 1) if real is not None and prog is not None else None,
        })

    reales = [c["avance_real_pct"] for c in contratos if c["avance_real_pct"] is not None]
    progs = [c["avance_programado_pct"] for c in contratos if c["avance_programado_pct"] is not None]
    avg_real = round(sum(reales) / len(reales), 1) if reales else 0.0
    avg_prog = round(sum(progs) / len(progs), 1) if progs else 0.0

    por_region: Dict[str, Dict[str, Any]] = {}
    for c in contratos:
        d = por_region.setdefault(c["region"], {"n_contratos": 0, "reales": [], "progs": []})
        d["n_contratos"] += 1
        if c["avance_real_pct"] is not None:
            d["reales"].append(c["avance_real_pct"])
        if c["avance_programado_pct"] is not None:
            d["progs"].append(c["avance_programado_pct"])

    resumen_por_region = [
        {
            "region": region,
            "n_contratos": d["n_contratos"],
            "avance_real_promedio_pct": round(sum(d["reales"]) / len(d["reales"]), 1) if d["reales"] else None,
            "avance_programado_promedio_pct": round(sum(d["progs"]) / len(d["progs"]), 1) if d["progs"] else None,
        }
        for region, d in sorted(por_region.items())
    ]

    con_brecha = sorted(
        (c for c in contratos if c["brecha_pct"] is not None),
        key=lambda c: c["brecha_pct"],
    )

    return {
        "titulo": "FENOGE — Avance real vs. programado",
        "subtitulo": "Seguimiento financiero de proyectos (curva de avance acumulado)",
        "n_contratos": len(contratos),
        "avance_real_promedio_pct": avg_real,
        "avance_programado_promedio_pct": avg_prog,
        "brecha_promedio_pct": round(avg_real - avg_prog, 1),
        "por_region": resumen_por_region,
        "contratos_mas_rezagados": [
            {
                "contrato": c["contrato"], "comunidad": c["comunidad"], "region": c["region"],
                "avance_real_pct": c["avance_real_pct"], "avance_programado_pct": c["avance_programado_pct"],
                "brecha_pct": c["brecha_pct"],
            }
            for c in con_brecha[:5]
        ],
        "nota": (
            "El 'avance real' de cada contrato usa su dato más reciente "
            "disponible — las fechas de corte varían por contrato, no todos "
            "comparten la misma fecha de actualización."
        ),
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
    async def _handle_fenoge_seguimiento(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_fenoge_seguimiento), []

    @handle_service_error
    async def _handle_colombia_solar_menu(
        self, parameters: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        return await asyncio.to_thread(_fetch_colombia_solar), []
