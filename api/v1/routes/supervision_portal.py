"""
Endpoint supervision dashboard — Portal Dirección EE
GET /v1/supervision/dashboard → supervision.contratos (Sankey + KPIs)
GET /v1/supervision/detalle   → filas para exportación Excel

CORRECCIONES DE DATOS (2026-06-20):
- _PARSE_FIN: filtra valores > 1 (100%) como anómalos → NULL
- _PARSE_AR/AU/AV: filtra valores con escala incorrecta (> 1e15) como anómalos → NULL
- Esto corrige el problema de valores como 4626.0 en % desembolsos y
  valores por desembolsar de ~49 cuatrillones por errores de entrada en Excel.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from domain.services.supervision_parsing import (
    FOTOVOLTAICO_TIPOS_SQL,
    sql_parse_cop,
    sql_parse_int,
)
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_cm = PostgreSQLConnectionManager()

# ─── Parsers con validación de rango ────────────────────────────────────────
# _PARSE_FIN: parsea % desembolsos y descarta valores > 1 (100%) como anómalos
_PARSE_FIN = """
    CASE
      WHEN (porcentaje_de_desembolsos)::text ~ '[0-9]' AND (porcentaje_de_desembolsos)::text ~ '%%'
        THEN CASE
          WHEN CAST(REPLACE(REPLACE(TRIM((porcentaje_de_desembolsos)::text),'%%',''),',','.') AS numeric) / 100 <= 1
            THEN CAST(REPLACE(REPLACE(TRIM((porcentaje_de_desembolsos)::text),'%%',''),',','.') AS numeric) / 100
          ELSE NULL
        END
      WHEN (porcentaje_de_desembolsos)::text ~ '^[0-9.]'
           AND TRIM((porcentaje_de_desembolsos)::text) ~ '^[0-9. ]+$'
        THEN CASE
          WHEN CAST(TRIM((porcentaje_de_desembolsos)::text) AS numeric) <= 1
            THEN CAST(TRIM((porcentaje_de_desembolsos)::text) AS numeric)
          ELSE NULL
        END
    END
"""

# _PARSE_AR: valor por proyecto — descarta valores con escala incorrecta (> 1e11)
_PARSE_AR = f"""
    CASE
      WHEN ({sql_parse_cop("valor_por_proyecto_informacion_apoyos_tecnicos")}) > 1e11
        THEN NULL
      ELSE ({sql_parse_cop("valor_por_proyecto_informacion_apoyos_tecnicos")})
    END
"""

# _PARSE_AU: valor desembolsado — descarta valores con escala incorrecta (> 1e11)
_PARSE_AU = f"""
    CASE
      WHEN ({sql_parse_cop("valor_desembolsado_informacion_apoyos_financieros")}) > 1e11
        THEN NULL
      ELSE ({sql_parse_cop("valor_desembolsado_informacion_apoyos_financieros")})
    END
"""

# _PARSE_AV: valor por desembolsar — descarta valores con escala incorrecta (> 1e11)
_PARSE_AV = f"""
    CASE
      WHEN ({sql_parse_cop("valor_por_desembolsar")}) > 1e11
        THEN NULL
      ELSE ({sql_parse_cop("valor_por_desembolsar")})
    END
"""

_PARSE_UC = sql_parse_int("numero_de_usuarios_totales_contratados")
_PARSE_UF = sql_parse_int("numero_de_usuarios_totales_finales")

_FILTER_COLS = [
    ("fondo", "fondo"),
    ("estado_del_contrato", "estado"),
    ("etapa_del_contrato", "etapa"),
    ("departamento", "departamento"),
    ("municipio", "municipio"),
]


def _build_filter(filters: list[tuple[str, Optional[str]]]) -> tuple[str, list]:
    params: list[str] = []
    clauses: list[str] = []
    for col, val in filters:
        if val is not None:
            params.append(val)
            clauses.append(f"{col} = %s")
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _base_year_where(ano_min: int, ano_max: int) -> str:
    return f"""
        FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}
        AND estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) != ''
    """


def _kpi_filter_where(
    ano_min: int,
    ano_max: int,
    fondo: Optional[str],
    estado: Optional[str],
    etapa: Optional[str],
    departamento: Optional[str],
    municipio: Optional[str],
) -> tuple[str, list[str]]:
    kpi_params: list[str] = []
    kpi_clauses: list[str] = [_base_year_where(ano_min, ano_max)]
    for col, val in [
        ("fondo", fondo),
        ("estado_del_contrato", estado),
        ("etapa_del_contrato", etapa),
        ("departamento", departamento),
        ("municipio", municipio),
    ]:
        if val is not None:
            kpi_params.append(val)
            kpi_clauses.append(f"{col} = %s")
    return " AND ".join(kpi_clauses), kpi_params


def _float(v) -> float:
    return float(v) if v is not None else 0.0


@router.get("/dashboard", summary="Dashboard supervisión contratos MinMinas")
@limiter.limit("60/minute")
async def get_supervision_dashboard(
    request: Request,
    fondo: Optional[str] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    etapa: Optional[str] = Query(default=None),
    departamento: Optional[str] = Query(default=None),
    municipio: Optional[str] = Query(default=None),
    ano_min: int = Query(default=2003, ge=2000, le=2030, alias="anoMin"),
    ano_max: int = Query(default=2026, ge=2000, le=2030, alias="anoMax"),
    api_key: str = Depends(get_api_key),
):
    base_where = _base_year_where(ano_min, ano_max)
    filter_where, kpi_params = _kpi_filter_where(
        ano_min, ano_max, fondo, estado, etapa, departamento, municipio
    )

    sf2_where, sf2_params = _build_filter([("fondo", fondo)])
    sf3_where, sf3_params = _build_filter(
        [("fondo", fondo), ("estado_del_contrato", estado)]
    )
    sf4_where, sf4_params = _build_filter(
        [
            ("fondo", fondo),
            ("estado_del_contrato", estado),
            ("etapa_del_contrato", etapa),
        ]
    )
    sf5_where, sf5_params = _build_filter(
        [
            ("fondo", fondo),
            ("estado_del_contrato", estado),
            ("etapa_del_contrato", etapa),
            ("departamento", departamento),
        ]
    )

    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        (SELECT COUNT(DISTINCT contrato) FROM supervision.contratos
                          WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                            AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}) AS n_contratos,
                        (SELECT COUNT(*) FROM supervision.contratos
                          WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                            AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}) AS n_proyectos,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                            THEN contrato END) AS en_ejecucion,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato IN ('AOM','ATBF - AOM','ATEI - AOM')
                                            THEN contrato END) AS en_aom,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'LIQUIDACI%%'
                                            THEN contrato END) AS en_liquidacion,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato IN ('LIQUIDADO','LIQUIDADO - AOM')
                                            THEN contrato END) AS liquidados,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'PERDIDA%%'
                                            THEN contrato END) AS perdida_competencia,
                        ROUND(AVG(avance_de_obra) * 100, 2) AS avg_avance_fisico,
                        ROUND(AVG({_PARSE_FIN}) * 100, 2) AS avg_avance_financiero,
                        ROUND(AVG(avance_contrato) * 100, 2) AS avg_avance_contrato,
                        ROUND(AVG(CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                       THEN avance_de_obra END) * 100, 2) AS avg_fisico_activos,
                        ROUND(AVG(CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                       THEN ({_PARSE_FIN}) END) * 100, 2) AS avg_financiero_activos,
                        COALESCE(SUM({_PARSE_AR}), 0) AS sum_ar,
                        COALESCE(SUM({_PARSE_AU}), 0) AS sum_au,
                        COALESCE(SUM({_PARSE_AV}), 0) AS sum_av,
                        COALESCE(SUM({_PARSE_UC}), 0) AS sum_usuarios_contratados,
                        COALESCE(SUM({_PARSE_UF}), 0) AS sum_usuarios_finales,
                        COUNT(*) FILTER (WHERE {_PARSE_AR} IS NOT NULL) AS filas_ar,
                        COUNT(*) FILTER (WHERE {_PARSE_AU} IS NOT NULL) AS filas_au,
                        COUNT(*) FILTER (WHERE {_PARSE_UC} IS NOT NULL) AS filas_uc,
                        COUNT(*) FILTER (WHERE {_PARSE_UF} IS NOT NULL) AS filas_uf,
                        COUNT(*) FILTER (WHERE {FOTOVOLTAICO_TIPOS_SQL}) AS n_fotovoltaicos
                    FROM supervision.contratos
                    WHERE {filter_where}
                    """,
                    kpi_params,
                )
                k = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT COALESCE(NULLIF(TRIM(tipo_de_solucion), ''), 'Sin clasificar') AS tipo,
                           COUNT(*) AS n
                    FROM supervision.contratos
                    WHERE {filter_where}
                    GROUP BY 1 ORDER BY n DESC
                    """,
                    kpi_params,
                )
                por_tipo = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT fondo, COUNT(DISTINCT contrato) AS contratos
                    FROM supervision.contratos
                    WHERE {filter_where}
                      AND fondo IS NOT NULL AND TRIM(fondo) != ''
                    GROUP BY fondo ORDER BY contratos DESC
                    """,
                    kpi_params,
                )
                fondos = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT FLOOR(ano)::integer AS anio,
                           ROUND(AVG(avance_de_obra)*100, 2) AS avg_avance_obra
                    FROM supervision.contratos
                    WHERE {filter_where}
                      AND ano IS NOT NULL AND avance_de_obra IS NOT NULL
                    GROUP BY FLOOR(ano)::integer ORDER BY anio
                    """,
                    kpi_params,
                )
                avance_anio = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT fondo AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where}
                      AND fondo IS NOT NULL AND TRIM(fondo) != ''
                    GROUP BY fondo ORDER BY n DESC
                    """
                )
                s_fondo = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT estado_del_contrato AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf2_where}
                    GROUP BY estado_del_contrato ORDER BY n DESC
                    """,
                    sf2_params,
                )
                s_estado = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT etapa_del_contrato AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf3_where}
                      AND etapa_del_contrato IS NOT NULL AND TRIM(etapa_del_contrato) != ''
                    GROUP BY etapa_del_contrato ORDER BY n DESC LIMIT 12
                    """,
                    sf3_params,
                )
                s_etapa = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT departamento AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf4_where}
                      AND departamento IS NOT NULL AND TRIM(departamento) != ''
                    GROUP BY departamento ORDER BY n DESC LIMIT 15
                    """,
                    sf4_params,
                )
                s_departamento = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT municipio AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf5_where}
                      AND municipio IS NOT NULL AND TRIM(municipio) != ''
                    GROUP BY municipio ORDER BY n DESC LIMIT 15
                    """,
                    sf5_params,
                )
                s_municipio = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT COUNT(DISTINCT contrato) AS total
                    FROM supervision.contratos
                    WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                      AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}
                    """
                )
                total = int((cur.fetchone() or [0])[0])

                cur.execute("SELECT MAX(fecha_carga) FROM supervision.contratos")
                ts_sup = cur.fetchone()[0]

        sum_ar = _float(k[12])
        sum_au = _float(k[13])
        sum_av = _float(k[14])
        ejecutado_total = sum_au + sum_av
        pct_desembolsado = round(sum_au / ejecutado_total * 100, 1) if ejecutado_total > 0 else 0.0

        return JSONResponse(
            {
                "ultima_actualizacion": ts_sup.strftime("%d/%m/%Y, %H:%M") if ts_sup else None,
                "nContratos": int(k[0] or 0),
                "nProyectos": int(k[1] or 0),
                "enEjecucion": int(k[2] or 0),
                "enAOM": int(k[3] or 0),
                "enLiquidacion": int(k[4] or 0),
                "liquidados": int(k[5] or 0),
                "perdidaCompetencia": int(k[6] or 0),
                "avanceFisico": _float(k[7]),
                "avanceFinanciero": _float(k[8]),
                "avanceContrato": _float(k[9]),
                "avanceFisicoActivos": _float(k[10]),
                "avanceFinancieroActivos": _float(k[11]),
                "financiero": {
                    "valorProyecto": sum_ar,
                    "valorDesembolsado": sum_au,
                    "valorPorDesembolsar": sum_av,
                    "pctDesembolsado": pct_desembolsado,
                    "filasConValor": int(k[17] or 0),
                    "filasConDesembolso": int(k[18] or 0),
                },
                "usuarios": {
                    "contratados": int(k[15] or 0),
                    "finales": int(k[16] or 0),
                    "filasContratados": int(k[19] or 0),
                    "filasFinales": int(k[20] or 0),
                },
                "nFotovoltaicos": int(k[21] or 0),
                "porTipoSolucion": [{"tipo": r[0], "proyectos": int(r[1])} for r in por_tipo],
                "porFondo": [{"fondo": r[0], "contratos": int(r[1])} for r in fondos],
                "avancePorAnio": [
                    {"anio": int(r[0]), "avg_avance_obra": _float(r[1])} for r in avance_anio
                ],
                "sankey": {
                    "fondo": [{"valor": r[0], "n": int(r[1])} for r in s_fondo],
                    "estado": [{"valor": r[0], "n": int(r[1])} for r in s_estado],
                    "etapa": [{"valor": r[0], "n": int(r[1])} for r in s_etapa],
                    "departamento": [{"valor": r[0], "n": int(r[1])} for r in s_departamento],
                    "municipio": [{"valor": r[0], "n": int(r[1])} for r in s_municipio],
                },
                "totalContratos": total,
            }
        )
    except Exception as e:
        logger.error("[supervision/dashboard] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener supervision dashboard")


@router.get("/detalle", summary="Detalle fila a fila — exportación Excel")
@limiter.limit("30/minute")
async def get_supervision_detalle(
    request: Request,
    fondo: Optional[str] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    etapa: Optional[str] = Query(default=None),
    departamento: Optional[str] = Query(default=None),
    municipio: Optional[str] = Query(default=None),
    ano_min: int = Query(default=2003, ge=2000, le=2030, alias="anoMin"),
    ano_max: int = Query(default=2026, ge=2000, le=2030, alias="anoMax"),
    api_key: str = Depends(get_api_key),
):
    filter_where, kpi_params = _kpi_filter_where(
        ano_min, ano_max, fondo, estado, etapa, departamento, municipio
    )

    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        FLOOR(ano)::integer,
                        contrato,
                        nombre_del_proyecto,
                        fondo,
                        tipo_de_solucion,
                        estado_del_contrato,
                        etapa_del_contrato,
                        ejecutor,
                        departamento,
                        municipio,
                        {_PARSE_UC},
                        {_PARSE_UF},
                        {_PARSE_AR},
                        {_PARSE_AU},
                        {_PARSE_AV},
                        ROUND(COALESCE(avance_de_obra, 0) * 100, 2),
                        ROUND(COALESCE(({_PARSE_FIN}), 0) * 100, 2)
                    FROM supervision.contratos
                    WHERE {filter_where}
                      AND contrato IS NOT NULL AND TRIM(contrato) != ''
                    ORDER BY FLOOR(ano)::integer DESC, contrato, nombre_del_proyecto
                    """,
                    kpi_params,
                )
                rows = cur.fetchall()

        proyectos = [
            {
                "anio": int(r[0]) if r[0] is not None else None,
                "contrato": r[1],
                "nombreProyecto": r[2],
                "fondo": r[3],
                "tipoSolucion": r[4],
                "estado": r[5],
                "etapa": r[6],
                "ejecutor": r[7],
                "departamento": r[8],
                "municipio": r[9],
                "usuariosContratados": int(r[10]) if r[10] is not None else None,
                "usuariosFinales": int(r[11]) if r[11] is not None else None,
                "valorProyecto": _float(r[12]) if r[12] is not None else None,
                "valorDesembolsado": _float(r[13]) if r[13] is not None else None,
                "valorPorDesembolsar": _float(r[14]) if r[14] is not None else None,
                "avanceObraPct": _float(r[15]),
                "avanceFinancieroPct": _float(r[16]),
            }
            for r in rows
        ]

        return JSONResponse({"proyectos": proyectos, "total": len(proyectos)})
    except Exception as e:
        logger.error("[supervision/detalle] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener detalle supervision")
