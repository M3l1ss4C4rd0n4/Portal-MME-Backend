"""
Lógica compartida de KPIs de contratos_or.

Extraída de api/v1/routes/contratos_or.py (el endpoint REST real que
alimenta el tablero /contratos-or del portal) el 2026-09-09, para que
domain/services/orchestrator/handlers/comunidades_handler.py (el Asistente
IA) use la MISMA fuente de verdad, en vez de una copia divergente.

Antes de esta extracción, el handler del Asistente (`_fetch_contratos_or`)
referenciaba `contratos_or.seguimiento` — una tabla que ya no existe (fue
reemplazada por `seguimiento_avance_fisico`/`seguimiento_avance_documental`/
`resumen` cuando el ETL se reestructuró, ver etl/etl_nuevos_dashboards.py::
etl_contratos_or(), que sigue cargando a la tabla vieja pero es un ETL sin
consumidores activos hoy). El handler fallaba en el 100% de sus invocaciones
con `relation "contratos_or.seguimiento" does not exist`, capturado en
silencio por handle_service_error — mismo patrón de bug que Supervisión.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List


def _normalizar_texto(s: str | None) -> str:
    """Mayúsculas, sin acentos, sin espacios sobrantes — para cruzar nombres
    de departamento/municipio entre hojas de Excel distintas que no
    mantienen el mismo formato (ej. 'Chocó' vs 'CHOCO')."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split()).upper()


def _match_valores_base_general(
    proyectos: List[Dict[str, Any]], filas_base: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Empareja cada proyecto de contratos_or (por nombre_proyecto_id) con su
    fila correspondiente de colombia_solar.base_general_or_inicial (hoja
    "Base General OR_Inicial" de Colombia_Solar_OR.xlsx), para traer
    valor/usuarios/potencia_mwp.

    Paso 1 — cruce exacto por (departamento, municipio) normalizado: funciona
    para 17 de los 18 proyectos.

    Paso 2 — por eliminación: el proyecto "14 - Santander" (municipio
    'Municipios Rurales' en contratos_or) no tiene match exacto porque
    'Base General OR_Inicial' guarda ahí la lista real de veredas
    ('Bolivar, Charalá, El Peñón, ...'), no el texto 'Municipios Rurales'.
    Como Santander solo tiene 2 filas en total y la otra ('Guaca') ya
    emparejó en el paso 1, la única fila de Santander que queda sin
    emparejar en ambos lados debe ser la correcta — se asignan entre sí.
    """
    restantes = list(filas_base)
    resultado: Dict[str, Dict[str, Any]] = {}
    sin_match: List[Dict[str, Any]] = []

    for p in proyectos:
        key = (_normalizar_texto(p["departamento"]), _normalizar_texto(p["municipio"]))
        match = next(
            (f for f in restantes
             if (_normalizar_texto(f["departamento"]), _normalizar_texto(f["municipio"])) == key),
            None,
        )
        if match:
            resultado[p["nombre_proyecto_id"]] = match
            restantes.remove(match)
        else:
            sin_match.append(p)

    for p in sin_match:
        depto = _normalizar_texto(p["departamento"])
        candidatos = [f for f in restantes if _normalizar_texto(f["departamento"]) == depto]
        if len(candidatos) == 1:
            resultado[p["nombre_proyecto_id"]] = candidatos[0]
            restantes.remove(candidatos[0])

    return resultado


_PREFIJO_NUMERO_RE = re.compile(r"^\d+\s*-\s*")


def _match_avances_resumen(
    proyectos: List[Dict[str, Any]], filas_gj: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Empareja cada proyecto con la fila correspondiente de la tabla
    Ejecutor/Nombre Proyecto/Avance Financiero/Avance Documental que vive en
    columnas G:J de la propia hoja "Resumen" (contratos_or.resumen,
    unnamed_6..unnamed_9) — el usuario confirmó que esta tabla, no la hoja
    Seguimiento_Avance_Documental, es la fuente correcta de estos dos avances.

    Cruce por (ejecutor, nombre de proyecto sin el prefijo "NN - ")
    normalizado — verificado 18/18 contra la BD real, sin casos especiales
    (a diferencia del cruce con colombia_solar).
    """
    por_key = {
        (_normalizar_texto(f["ejecutor"]), _normalizar_texto(f["nombre_proyecto"])): f
        for f in filas_gj
    }
    resultado: Dict[str, Dict[str, Any]] = {}
    for p in proyectos:
        nombre_sin_prefijo = _PREFIJO_NUMERO_RE.sub("", p["nombre_proyecto_id"] or "").strip()
        key = (_normalizar_texto(p["ejecutor"]), _normalizar_texto(nombre_sin_prefijo))
        match = por_key.get(key)
        if match:
            resultado[p["nombre_proyecto_id"]] = match
    return resultado


def fetch_contratos_or_kpis(cur) -> Dict[str, Any]:
    """Ejecuta las queries reales del tablero de Contratos OR sobre un
    cursor ya abierto (dict cursor) y devuelve los KPIs globales + desglose
    por proyecto + por desembolso.

    Replica exactamente la lógica ya probada en producción por
    api/v1/routes/contratos_or.py::get_contratos_or_dashboard — incluida la
    fórmula de avance físico global, que NO es un promedio simple: promedia
    primero `avance` dentro de cada `ejecutor` en seguimiento_avance_fisico,
    y luego promedia esos subtotales entre sí (así lo calcula el Excel
    origen, ver comentario histórico en la ruta REST).
    """
    # KPIs por proyecto (avance documental/financiero, desde seguimiento_avance_documental)
    cur.execute(
        """
        WITH pagados AS (
            SELECT nombre_proyecto_id, nro_desembolso
            FROM contratos_or.seguimiento_avance_documental
            WHERE necesaria_para_desembolso = 'Sí'
            GROUP BY nombre_proyecto_id, nro_desembolso
            HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
        )
        SELECT
            s.nombre_proyecto_id AS nombre_proyecto_id,
            s.ejecutor AS ejecutor,
            s.departamento AS departamento,
            s.municipio AS municipio,
            ROUND(AVG(s.avance) * 100, 1) AS avance_general,
            ROUND(COALESCE(SUM(DISTINCT
                CASE WHEN p.nro_desembolso IS NOT NULL AND s.desembolso IS NOT NULL
                     THEN s.desembolso ELSE 0 END
            ), 0) * 100, 1) AS avance_financiero,
            COUNT(DISTINCT CASE WHEN s.nro_desembolso IS NOT NULL
                  THEN s.nro_desembolso END) AS total_desembolsos,
            COUNT(DISTINCT p.nro_desembolso) AS pagos_realizados
        FROM contratos_or.seguimiento_avance_documental s
        LEFT JOIN pagados p
            ON s.nombre_proyecto_id = p.nombre_proyecto_id
           AND s.nro_desembolso     = p.nro_desembolso
           AND s.necesaria_para_desembolso = 'Sí'
        GROUP BY s.nombre_proyecto_id, s.ejecutor, s.departamento, s.municipio
        ORDER BY s.nombre_proyecto_id
        """
    )
    proyectos_rows = cur.fetchall()

    # Avance Financiero/Documental por proyecto — tabla Ejecutor/Nombre
    # Proyecto/Avance Financiero/Avance Documental en columnas G:J de la
    # propia hoja Resumen (unnamed_6..unnamed_9), confirmada por el usuario
    # como la fuente correcta (reemplaza el AVG(avance) de
    # seguimiento_avance_documental usado antes). unnamed_8 es fracción 0-1
    # (%×100 directo); unnamed_9 es el valor crudo que el Excel interpreta
    # como puntos porcentuales tal cual — verificado contra la fórmula real
    # de la celda B12 (`=AVERAGE(J3:J20)/100`), no necesita otra escala.
    cur.execute(
        """
        SELECT unnamed_6 AS ejecutor, unnamed_7 AS nombre_proyecto,
               unnamed_8 AS avance_financiero, unnamed_9 AS avance_documental
        FROM contratos_or.resumen
        WHERE unnamed_6 IS NOT NULL
        """
    )
    filas_gj_resumen = cur.fetchall()

    # KPIs globales desde la hoja Resumen del Excel (pivot unnamed_0/unnamed_1)
    cur.execute(
        """
        SELECT
            MAX(CASE WHEN unnamed_0 = 'Numero de Contratos' THEN unnamed_1 END) AS n_contratos,
            MAX(CASE WHEN unnamed_0 = 'Avance Financiero' THEN unnamed_1 END)   AS avance_financiero,
            MAX(CASE WHEN unnamed_0 = 'Avance Documental' THEN unnamed_1 END)   AS avance_general,
            MAX(CASE WHEN unnamed_0 = 'Pagos Realizados' THEN unnamed_1 END)    AS pagos_realizados,
            MAX(CASE WHEN unnamed_0 = 'Total Pagos' THEN unnamed_1 END)        AS total_pagos,
            MAX(CASE WHEN unnamed_0 = '% Pagos' THEN unnamed_1 END)            AS pct_pagos
        FROM contratos_or.resumen
        """
    )
    g = cur.fetchone() or {}

    cur.execute("SELECT MAX(fecha_carga) AS max FROM contratos_or.resumen")
    ts_or = (cur.fetchone() or {}).get("max")

    # Avance Físico global — replica Resumen!B11 del Excel: promedia primero
    # dentro de cada ejecutor, luego promedia esos subtotales entre sí.
    # ejecutor IS NOT NULL excluye la fila "Promedio Avance" que deja el Excel.
    cur.execute(
        """
        SELECT ROUND(AVG(avance_ejecutor) * 100, 1) AS avance_fisico
        FROM (
            SELECT ejecutor, AVG(avance) AS avance_ejecutor
            FROM contratos_or.seguimiento_avance_fisico
            WHERE avance IS NOT NULL AND ejecutor IS NOT NULL
            GROUP BY ejecutor
        ) por_ejecutor
        """
    )
    af = (cur.fetchone() or {}).get("avance_fisico")

    # Avance físico por proyecto, con fallback por (ejecutor, departamento,
    # municipio) para filas del Excel sin "Nombre proyecto + ID" (ej. ENAM).
    cur.execute(
        """
        SELECT nombre_proyecto_id, ejecutor, departamento, municipio,
               ROUND(AVG(avance) * 100, 1) AS avance_fisico
        FROM contratos_or.seguimiento_avance_fisico
        WHERE avance IS NOT NULL
          AND (nombre_proyecto_id IS NULL OR nombre_proyecto_id != 'Promedio Avance')
        GROUP BY nombre_proyecto_id, ejecutor, departamento, municipio
        """
    )
    af_per_project: Dict[str, float] = {}
    af_por_ubicacion: Dict[tuple, float] = {}
    for row in cur.fetchall():
        valor = float(row["avance_fisico"]) if row["avance_fisico"] is not None else 0.0
        pid = row["nombre_proyecto_id"]
        if pid is not None:
            af_per_project[pid] = valor
        if row["ejecutor"] is not None and row["departamento"] is not None and row["municipio"] is not None:
            af_por_ubicacion[(row["ejecutor"], row["departamento"], row["municipio"])] = valor

    # Progreso por desembolso
    cur.execute(
        """
        WITH pagados AS (
            SELECT nombre_proyecto_id, nro_desembolso
            FROM contratos_or.seguimiento_avance_documental
            WHERE necesaria_para_desembolso = 'Sí'
            GROUP BY nombre_proyecto_id, nro_desembolso
            HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
        )
        SELECT
            s.nro_desembolso::int AS numero,
            COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' THEN 1 END) AS act_necesarias,
            COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí'
                        AND s.estado = 'Completo' THEN 1 END) AS act_completas,
            ROUND(
                COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí'
                            AND s.estado = 'Completo' THEN 1 END)::numeric /
                NULLIF(COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' THEN 1 END), 0) * 100
            , 1) AS pct_completado,
            COUNT(DISTINCT p.nombre_proyecto_id) AS proyectos_pagados
        FROM contratos_or.seguimiento_avance_documental s
        LEFT JOIN pagados p
            ON s.nombre_proyecto_id = p.nombre_proyecto_id
           AND s.nro_desembolso     = p.nro_desembolso
        WHERE s.nro_desembolso IS NOT NULL
        GROUP BY s.nro_desembolso
        ORDER BY s.nro_desembolso
        """
    )
    desembolsos_rows = cur.fetchall()

    # Valor/usuarios/potencia — hoja "Base General OR_Inicial" de
    # Colombia_Solar_OR.xlsx (schema colombia_solar, otro Excel fuente).
    # departamento IS NOT NULL excluye la fila de totales que deja el ETL.
    cur.execute(
        """
        SELECT departamento, municipio, valor, usuarios, potencia_mwp
        FROM colombia_solar.base_general_or_inicial
        WHERE departamento IS NOT NULL
        """
    )
    filas_base_general = cur.fetchall()

    cur.execute(
        """
        SELECT valor, usuarios, potencia_mwp
        FROM colombia_solar.base_general_or_inicial
        WHERE departamento IS NULL
        """
    )
    totales_base_general = cur.fetchone() or {}

    def _f(v):
        return float(v) if v is not None else None

    n_contratos = int(g.get("n_contratos") or 0)
    avance_financiero = (_f(g.get("avance_financiero")) or 0.0) * 100
    avance_general = (_f(g.get("avance_general")) or 0.0) * 100
    pagos_real = int(g.get("pagos_realizados") or 0)
    pagos_pos = int(g.get("total_pagos") or 0)
    avance_fisico = _f(af) or 0.0

    valores_por_proyecto = _match_valores_base_general(proyectos_rows, filas_base_general)
    avances_gj_por_proyecto = _match_avances_resumen(proyectos_rows, filas_gj_resumen)

    proyectos: List[Dict[str, Any]] = [
        {
            "nombre": p["nombre_proyecto_id"],
            "ejecutor": p["ejecutor"],
            "departamento": p["departamento"],
            "municipio": p["municipio"],
            "avance_general": _f(
                (avances_gj_por_proyecto.get(p["nombre_proyecto_id"]) or {}).get("avance_documental")
            ) if p["nombre_proyecto_id"] in avances_gj_por_proyecto else _f(p["avance_general"]),
            "avance_fisico": af_per_project.get(
                p["nombre_proyecto_id"],
                af_por_ubicacion.get(
                    (p["ejecutor"], p["departamento"], p["municipio"]), 0.0
                ),
            ),
            "avance_financiero": (
                (_f((avances_gj_por_proyecto.get(p["nombre_proyecto_id"]) or {}).get("avance_financiero")) or 0.0) * 100
            ) if p["nombre_proyecto_id"] in avances_gj_por_proyecto else _f(p["avance_financiero"]),
            "total_desembolsos": int(p["total_desembolsos"]),
            "pagos_realizados": int(p["pagos_realizados"]),
            "valor": _f((valores_por_proyecto.get(p["nombre_proyecto_id"]) or {}).get("valor")) or 0.0,
            "usuarios": int((valores_por_proyecto.get(p["nombre_proyecto_id"]) or {}).get("usuarios") or 0),
            "potencia_mwp": _f((valores_por_proyecto.get(p["nombre_proyecto_id"]) or {}).get("potencia_mwp")) or 0.0,
        }
        for p in proyectos_rows
    ]

    return {
        "valor_total": _f(totales_base_general.get("valor")) or 0.0,
        "usuarios_total": int(totales_base_general.get("usuarios") or 0),
        "potencia_mwp_total": _f(totales_base_general.get("potencia_mwp")) or 0.0,
        "fecha_corte": ts_or.strftime("%d/%m/%Y, %H:%M") if ts_or else None,
        "n_contratos": n_contratos,
        "avance_general": round(avance_general, 1),
        "avance_financiero": round(avance_financiero, 1),
        "avance_fisico": avance_fisico,
        "pagos_realizados": pagos_real,
        "pagos_posibles": pagos_pos,
        "pct_pagos_realizados": round(pagos_real / pagos_pos * 100, 1) if pagos_pos else 0.0,
        "desembolsos": [
            {
                "numero": int(d["numero"]),
                "actividades_necesarias": int(d["act_necesarias"]),
                "actividades_completas": int(d["act_completas"]),
                "pct_completado": _f(d["pct_completado"]),
                "proyectos_pagados": int(d["proyectos_pagados"]),
            }
            for d in desembolsos_rows
        ],
        "proyectos": proyectos,
    }


def fetch_ratios_consolidados(cur) -> Dict[str, Any]:
    """
    Lee contratos_or.ratios_consolidados (hoja Ratios_Consolidados del Excel).
    La fila id=1 es el propio encabezado guardado como datos (el ETL genérico
    no tiene header_overrides para esta hoja) — se excluye con id > 1.
    Columnas unnamed_1..7 mapean 1:1 a Ejecutor/Departamento/Municipio/
    Proyectado/Obras Civiles/Instalaciones Internas/Usuarios Energizados,
    confirmado contra el encabezado real del Excel fuente.
    """
    cur.execute(
        """
        SELECT
            unnamed_1 AS ejecutor,
            unnamed_2 AS departamento,
            unnamed_3 AS municipio,
            unnamed_4 AS proyectado,
            unnamed_5 AS obras_civiles,
            unnamed_6 AS instalaciones_internas,
            unnamed_7 AS usuarios_energizados
        FROM contratos_or.ratios_consolidados
        WHERE id > 1
        ORDER BY unnamed_2, unnamed_3
        """
    )
    filas = cur.fetchall()

    def _n(v):
        return float(v) if v is not None else 0.0

    return {
        "kpis": {
            "departamentos": len({r["departamento"] for r in filas if r["departamento"]}),
            "municipios": len([r for r in filas if r["municipio"]]),
            "proyectado": sum(_n(r["proyectado"]) for r in filas),
            "obrasCiviles": sum(_n(r["obras_civiles"]) for r in filas),
            "instalacionesInternas": sum(_n(r["instalaciones_internas"]) for r in filas),
            "usuariosEnergizados": sum(_n(r["usuarios_energizados"]) for r in filas),
        },
        "filas": [
            {
                "ejecutor": r["ejecutor"],
                "departamento": r["departamento"],
                "municipio": r["municipio"],
                "proyectado": _n(r["proyectado"]),
                "obrasCiviles": _n(r["obras_civiles"]),
                "instalacionesInternas": _n(r["instalaciones_internas"]),
                "usuariosEnergizados": _n(r["usuarios_energizados"]),
            }
            for r in filas
        ],
    }
