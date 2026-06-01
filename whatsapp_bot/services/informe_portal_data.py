"""
Capa de datos compartida para el informe PDF multi-capítulo.
Réplica las mismas fuentes SQL que los tableros del portal.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SERVER_DIR = str(Path(__file__).resolve().parent.parent.parent)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from infrastructure.database.connection import connection_manager

logger = logging.getLogger(__name__)

DATE_COL_RE = re.compile(r"^col_(\d{1,2})_(\d{1,2})_(\d{4})$")

CURVA_S_CATS = [
    ("obras", "proyectado_obras_civiles", "reportado_obras_civiles", "Obras Civiles"),
    ("usuarios", "proyectado_usuarios", "reportado_usuarios", "Usuarios"),
    ("potencia", "proyectado_potencia", "reportado_potencia", "Potencia"),
    ("internas", "proyectado_internas", "reportado_internas", "Internas"),
]


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


def _col_to_iso(col: str) -> str:
    m = DATE_COL_RE.match(col)
    if not m:
        return col
    d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
    return f"{y}-{mo}-{d}"


def _get_date_columns(cur, table: str) -> List[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'colombia_solar' AND table_name = %s
          AND column_name ~ '^col_[0-9]'
        ORDER BY column_name
        """,
        (table,),
    )
    return [r["column_name"] for r in cur.fetchall() if DATE_COL_RE.match(r["column_name"])]


def _aggregate_curva_table(cur, table: str, date_cols: List[str]) -> Dict[str, float]:
    if not date_cols:
        return {}
    cols_sql = ", ".join(f'COALESCE("{c}"::numeric, 0) AS "{c}"' for c in date_cols)
    cur.execute(f'SELECT {cols_sql} FROM colombia_solar."{table}" WHERE proyecto IS NOT NULL')
    totals = {c: 0.0 for c in date_cols}
    for row in cur.fetchall():
        for c in date_cols:
            totals[c] += float(row.get(c) or 0)
    return totals


def _series_from_totals(totals: Dict[str, float], grand_total: float) -> List[Dict[str, Any]]:
    if grand_total <= 0:
        grand_total = max(totals.values()) or 1.0
    running = 0.0
    out: List[Dict[str, Any]] = []
    for col in sorted(totals.keys(), key=_col_to_iso):
        running = max(running, totals[col])
        out.append({
            "fecha": _col_to_iso(col),
            "pct": round(running / grand_total * 100, 2),
        })
    return out


def fetch_curva_s() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            for cat_id, tbl_p, tbl_r, label in CURVA_S_CATS:
                try:
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='colombia_solar' AND table_name=%s",
                        (tbl_p,),
                    )
                    if not cur.fetchone():
                        continue
                    p_cols = _get_date_columns(cur, tbl_p)
                    prog_tot = _aggregate_curva_table(cur, tbl_p, p_cols)
                    denom = max(prog_tot.values()) if prog_tot else 1.0
                    if denom <= 0:
                        denom = 1.0

                    real_tot: Dict[str, float] = {}
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='colombia_solar' AND table_name=%s",
                        (tbl_r,),
                    )
                    if cur.fetchone():
                        r_cols = _get_date_columns(cur, tbl_r)
                        real_tot = _aggregate_curva_table(cur, tbl_r, r_cols)
                        if not real_tot and tbl_r != "reportado_usuarios":
                            real_tot = _aggregate_curva_table(cur, "reportado_usuarios", _get_date_columns(cur, "reportado_usuarios"))

                    all_cols = sorted(set(prog_tot) | set(real_tot), key=_col_to_iso)
                    merged_prog = {c: prog_tot.get(c, 0) for c in all_cols}
                    merged_real = {c: real_tot.get(c, 0) for c in all_cols}
                    result.append({
                        "id": cat_id,
                        "label": label,
                        "programado": _series_from_totals(merged_prog, denom),
                        "real": _series_from_totals(merged_real, denom),
                    })
                except Exception as exc:
                    logger.warning("[curva_s] %s: %s", cat_id, exc)
    return result


def fetch_comunidades_full() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT departamento,
                       COUNT(*) AS count,
                       SUM(capacidad_de_generacion_kwp) AS capacidad,
                       SUM(COALESCE(CASE WHEN inversion_estimada IS NULL THEN NULL
                            WHEN inversion_estimada::text ~ '^[0-9.-]+'
                            THEN REPLACE(REPLACE(inversion_estimada::text, '$', ''), ',', '')::numeric
                            ELSE NULL END, 0)) AS inversion
                FROM comunidades.base
                WHERE implementado = 'Si' AND departamento IS NOT NULL
                GROUP BY departamento
                ORDER BY count DESC
            """)
            por_depto = [
                {
                    "departamento": r["departamento"],
                    "departamento_geo": r["departamento"].upper().replace("_", " "),
                    "count": int(r["count"] or 0),
                    "capacidad_kwp": float(r["capacidad"] or 0),
                    "inversion": float(r["inversion"] or 0),
                }
                for r in cur.fetchall()
            ]
            cur.execute("""
                SELECT COUNT(*) AS n, SUM(capacidad_de_generacion_kwp) AS kwp,
                       SUM(usuarios_equivalentes) AS usuarios
                FROM comunidades.base WHERE implementado = 'Si'
            """)
            k = cur.fetchone() or {}
            cur.execute("SELECT MAX(fecha_carga) FROM comunidades.base")
            fecha = (cur.fetchone() or {}).get("max")

    return {
        "por_departamento": por_depto,
        "kpis": [
            {"label": "Comunidades", "valor": int(k.get("n") or 0), "unidad": "CEs"},
            {"label": "Capacidad", "valor": round(float(k.get("kwp") or 0), 1), "unidad": "kWp"},
            {"label": "Usuarios equiv.", "valor": int(k.get("usuarios") or 0), "unidad": ""},
        ],
        "fecha_corte": fecha.strftime("%d/%m/%Y") if fecha else "N/D",
    }


def fetch_contratos_or_full() -> Dict[str, Any]:
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
                    ), 0) / NULLIF(COUNT(DISTINCT s.nombre_proyecto_id), 0) * 100, 1) AS avance_financiero
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
                       ROUND(AVG(s.avance) * 100, 1) AS avance_general,
                       ROUND(COALESCE(SUM(
                           CASE WHEN p.nro_desembolso IS NOT NULL AND s.desembolso IS NOT NULL
                                THEN s.desembolso ELSE 0 END
                       ), 0) * 100, 1) AS avance_financiero
                FROM contratos_or.seguimiento s
                LEFT JOIN pagados p ON s.nombre_proyecto_id = p.nombre_proyecto_id
                GROUP BY s.nombre_proyecto_id
                ORDER BY avance_general DESC
            """)
            proyectos = cur.fetchall()

            cur.execute("""
                WITH pagados AS (
                    SELECT nombre_proyecto_id, nro_desembolso
                    FROM contratos_or.seguimiento WHERE necesaria_para_desembolso = 'Sí'
                    GROUP BY nombre_proyecto_id, nro_desembolso
                    HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                )
                SELECT ROUND(
                    COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' AND s.estado = 'Completo' THEN 1 END)::numeric /
                    NULLIF(COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' THEN 1 END), 0) * 100, 1
                ) AS avance_fisico
                FROM contratos_or.seguimiento s
            """)
            avance_fisico = float((cur.fetchone() or {}).get("avance_fisico") or 0)

            cur.execute("SELECT MAX(fecha_carga) FROM contratos_or.seguimiento")
            fecha = (cur.fetchone() or {}).get("max")

    return {
        "avance_general": float(g.get("avance_general") or 0),
        "avance_financiero": float(g.get("avance_financiero") or 0),
        "avance_fisico": avance_fisico,
        "n_contratos": int(g.get("n_contratos") or 0),
        "proyectos": [
            {
                "nombre": r["nombre"],
                "avance_general": float(r["avance_general"] or 0),
                "avance_financiero": float(r["avance_financiero"] or 0),
            }
            for r in proyectos
        ],
        "fecha_corte": fecha.strftime("%d/%m/%Y") if fecha else "N/D",
    }


def fetch_fenoge_full() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT departamento, COUNT(*) AS count, SUM(kwp) AS kwp,
                       SUM(valor_proyecto) AS inversion
                FROM fenoge.comunidades
                WHERE departamento IS NOT NULL
                GROUP BY departamento ORDER BY count DESC
            """)
            por_depto = [
                {
                    "departamento": r["departamento"],
                    "count": int(r["count"] or 0),
                    "kwp": float(r["kwp"] or 0),
                    "inversion": float(r["inversion"] or 0),
                }
                for r in cur.fetchall()
            ]
            cur.execute("""
                SELECT dia_actualizacion::date AS fecha,
                       AVG(avance_real_acumulado_pct) * 100 AS real_pct,
                       AVG(avance_programado_acumulado_pct) * 100 AS prog_pct
                FROM fenoge.seguimiento
                WHERE dia_actualizacion IS NOT NULL
                GROUP BY 1 ORDER BY 1
            """)
            seguimiento = [
                {
                    "fecha": r["fecha"].isoformat(),
                    "real": round(float(r["real_pct"] or 0), 2),
                    "programado": round(float(r["prog_pct"] or 0), 2),
                }
                for r in cur.fetchall()
            ]
            cur.execute("SELECT COUNT(*) AS n, SUM(kwp) AS kwp FROM fenoge.comunidades")
            k = cur.fetchone() or {}
            cur.execute("SELECT MAX(fecha_carga) FROM fenoge.comunidades")
            fecha = (cur.fetchone() or {}).get("max")

    return {
        "por_departamento": por_depto,
        "seguimiento": seguimiento,
        "kpis": [
            {"label": "Comunidades", "valor": int(k.get("n") or 0), "unidad": "CEs"},
            {"label": "Capacidad", "valor": round(float(k.get("kwp") or 0), 1), "unidad": "kWp"},
        ],
        "fecha_corte": fecha.strftime("%d/%m/%Y") if fecha else "N/D",
    }


def fetch_subsidios_full() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT anio, subsidios, contribuciones, deficit_anual,
                       deficit_acumulado, apropiacion_pgn, recursos_faltantes
                FROM subsidios.deficit_historico ORDER BY anio
            """)
            deficit = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT SUM(valor_pagado) AS pagado, SUM(valor_resolucion) AS asignado,
                       SUM(saldo_pendiente) AS pendiente
                FROM subsidios.subsidios_pagos
            """)
            pagos_k = cur.fetchone() or {}

            cur.execute("""
                SELECT concepto_trimestre,
                       SUM(CASE WHEN estado_pago='Pagado' THEN valor_pagado ELSE 0 END) AS pagado,
                       SUM(saldo_pendiente) AS pendiente
                FROM subsidios.subsidios_pagos
                WHERE concepto_trimestre IS NOT NULL
                GROUP BY concepto_trimestre ORDER BY concepto_trimestre
            """)
            trimestres = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT nombre_prestador, SUM(saldo_pendiente) AS deuda
                FROM subsidios.subsidios_pagos
                WHERE estado_pago = 'Pendiente' AND saldo_pendiente > 0
                GROUP BY nombre_prestador ORDER BY deuda DESC LIMIT 12
            """)
            prestadores = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT area, anio, trimestre, estado_validacion_organizado AS estado,
                       COUNT(*) AS conteo
                FROM subsidios.subsidios_validaciones
                WHERE area IN ('SIN','ZNI') AND trimestre IS NOT NULL
                  AND estado_validacion_organizado IS NOT NULL
                GROUP BY area, anio, trimestre, estado_validacion_organizado
                ORDER BY area, anio, trimestre
            """)
            validaciones_serie = [dict(r) for r in cur.fetchall()]

            cur.execute("SELECT MAX(fecha_actualizacion) FROM subsidios.subsidios_pagos")
            fecha_p = (cur.fetchone() or {}).get("max")
            cur.execute("SELECT MAX(fecha_actualizacion) FROM subsidios.subsidios_validaciones")
            fecha_v = (cur.fetchone() or {}).get("max")

    asignado = float(pagos_k.get("asignado") or 0)
    pagado = float(pagos_k.get("pagado") or 0)
    return {
        "deficit_historico": [
            {
                k: (int(v) if k == "anio" else float(v or 0))
                for k, v in row.items()
                if k != "fecha_carga"
            }
            for row in deficit
        ],
        "pagos": {
            "pct_pagado": round(pagado / asignado * 100, 1) if asignado else 0,
            "pagado": pagado,
            "pendiente": float(pagos_k.get("pendiente") or 0),
            "trimestres": trimestres,
            "prestadores": prestadores,
            "fecha_corte": fecha_p.strftime("%d/%m/%Y") if fecha_p else "N/D",
        },
        "validaciones": {
            "serie": validaciones_serie,
            "fecha_corte": fecha_v.strftime("%d/%m/%Y") if fecha_v else "N/D",
        },
    }


def fetch_supervision_full() -> Dict[str, Any]:
    """Réplica KPIs del tablero supervisión + series para gráficas."""
    from domain.services.orchestrator.handlers.supervision_handler import _fetch_supervision_resumen

    base = (
        "FLOOR(ano)::integer BETWEEN 2003 AND 2026 "
        "AND estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) <> ''"
    )
    resumen = _fetch_supervision_resumen()
    kpis = {k["label"]: k["valor"] for k in resumen.get("kpis", [])}

    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT fondo, COUNT(DISTINCT contrato) AS n
                FROM supervision.contratos WHERE {base}
                  AND fondo IS NOT NULL AND TRIM(fondo) <> ''
                GROUP BY fondo ORDER BY n DESC
            """)
            por_fondo = [{"fondo": r["fondo"], "contratos": int(r["n"])} for r in cur.fetchall()]

            cur.execute(f"""
                SELECT FLOOR(ano)::integer AS anio,
                       ROUND(AVG(avance_de_obra) * 100, 2) AS avance
                FROM supervision.contratos
                WHERE {base} AND avance_de_obra IS NOT NULL
                GROUP BY 1 ORDER BY 1
            """)
            evolucion = [
                {"anio": int(r["anio"]), "avance": float(r["avance"] or 0)}
                for r in cur.fetchall()
            ]

            cur.execute(f"""
                SELECT fondo, estado_del_contrato, COUNT(DISTINCT contrato) AS n
                FROM supervision.contratos
                WHERE {base} AND fondo IS NOT NULL AND estado_del_contrato IS NOT NULL
                GROUP BY fondo, estado_del_contrato ORDER BY n DESC LIMIT 20
            """)
            sankey = [dict(r) for r in cur.fetchall()]

    return {
        "gauges_portafolio": {
            "fisico": float(kpis.get("Avance físico promedio", 0)),
            "financiero": float(kpis.get("Avance financiero promedio", 0)),
        },
        "gauges_ejecucion": {
            "fisico": float(kpis.get("Avance físico promedio", 0)),
            "financiero": float(kpis.get("Avance financiero promedio", 0)),
        },
        "por_fondo": por_fondo or resumen.get("top_fondos", []),
        "evolucion": evolucion,
        "sankey": sankey,
        "n_contratos": int(kpis.get("Contratos", 0)),
        "usuarios": int(kpis.get("Usuarios contratados", 0)),
        "fecha_corte": resumen.get("fecha_corte", "N/D"),
    }


def fetch_presupuesto_full() -> Dict[str, Any]:
    with connection_manager.get_connection(use_dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT SUM(apropiacion) AS apropiacion, SUM(compromisos) AS comprometido,
                       SUM(obligados) AS obligados, SUM(sin_comprometer_disponible) AS disponible
                FROM presupuesto.resumen WHERE proyecto NOT IN ('Proyecto','TOTAL')
            """)
            tot = cur.fetchone() or {}
            cur.execute("""
                SELECT proyecto, apropiacion, compromisos, obligados
                FROM presupuesto.resumen
                WHERE proyecto NOT IN ('Proyecto','TOTAL')
                ORDER BY apropiacion DESC LIMIT 10
            """)
            proyectos = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT MAX(fecha_carga) FROM presupuesto.resumen")
            fecha = (cur.fetchone() or {}).get("max")

    ap = float(tot.get("apropiacion") or 0)
    comp = float(tot.get("comprometido") or 0)
    obl = float(tot.get("obligados") or 0)
    disp = float(tot.get("disponible") or 0)
    return {
        "totales": {
            "apropiacion": ap,
            "comprometido": comp,
            "obligados": obl,
            "disponible": disp,
            "pct_comprometido": round(comp / ap * 100, 1) if ap else 0,
            "pct_obligado": round(obl / ap * 100, 1) if ap else 0,
            "pct_disponible": round(disp / ap * 100, 1) if ap else 0,
        },
        "proyectos": proyectos,
        "fecha_corte": fecha.strftime("%d/%m/%Y") if fecha else "N/D",
    }


def fetch_all_portal_dashboards() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    fetchers = {
        "comunidades": fetch_comunidades_full,
        "contratos_or": fetch_contratos_or_full,
        "fenoge": fetch_fenoge_full,
        "colombia_solar": fetch_curva_s,
        "subsidios": fetch_subsidios_full,
        "supervision": fetch_supervision_full,
        "presupuesto": fetch_presupuesto_full,
    }
    for key, fn in fetchers.items():
        try:
            result[key] = fn()
            logger.info("[informe_portal_data] %s OK", key)
        except Exception as exc:
            logger.warning("[informe_portal_data] %s: %s", key, exc)
            result[key] = {}
    return result
