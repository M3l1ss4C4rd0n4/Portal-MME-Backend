"""
Endpoint supervision dashboard — Portal Dirección EE
GET /v1/supervision/dashboard → supervision.contratos (Sankey + KPIs)

Replica exacta de la lógica del portal-direccion-mme con filtros opcionales
de fondo, estado, etapa, ejecutor y rango de años.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_cm = PostgreSQLConnectionManager()

# Parseo de porcentaje_de_desembolsos: texto con formatos mixtos → decimal [0,1].
# Valores en BD: "1"=100%, "0.5"=50%; solo 3 filas usan formato "44,93%".
# %% → % literal en psycopg2 (execute usa % como placeholder de parámetros).
_PARSE_FIN = """
    CASE
      WHEN porcentaje_de_desembolsos ~ '[0-9]' AND porcentaje_de_desembolsos ~ '%%'
        THEN CAST(REPLACE(REPLACE(TRIM(porcentaje_de_desembolsos),'%%',''),',','.') AS numeric) / 100
      WHEN porcentaje_de_desembolsos ~ '^[0-9.]'
           AND TRIM(porcentaje_de_desembolsos) ~ '^[0-9. ]+$'
        THEN CAST(TRIM(porcentaje_de_desembolsos) AS numeric)
    END
"""


def _build_filter(filters: list[tuple[str, Optional[str]]]) -> tuple[str, list]:
    """Construye WHERE dinámico con placeholders %s para psycopg2."""
    params: list[str] = []
    clauses: list[str] = []
    for col, val in filters:
        if val is not None:
            params.append(val)
            clauses.append(f"{col} = %s")
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


@router.get("/dashboard", summary="Dashboard supervición contratos MinMinas")
@limiter.limit("60/minute")
async def get_supervision_dashboard(
    request: Request,
    fondo:    Optional[str] = Query(default=None),
    estado:   Optional[str] = Query(default=None),
    etapa:    Optional[str] = Query(default=None),
    ejecutor: Optional[str] = Query(default=None),
    ano_min:  int = Query(default=2003, ge=2000, le=2030, alias="anoMin"),
    ano_max:  int = Query(default=2026, ge=2000, le=2030, alias="anoMax"),
    api_key: str = Depends(get_api_key),
):
    # Año validado como entero — seguro como literal en SQL
    base_where = f"""
        FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}
        AND estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) != ''
    """

    # WHERE con filtros opcionales para KPIs
    kpi_params: list[str] = []
    kpi_clauses: list[str] = [base_where]
    for col, val in [
        ("fondo", fondo),
        ("estado_del_contrato", estado),
        ("etapa_del_contrato", etapa),
        ("ejecutor", ejecutor),
    ]:
        if val is not None:
            kpi_params.append(val)
            kpi_clauses.append(f"{col} = %s")
    filter_where = " AND ".join(kpi_clauses)

    # WHERE cascade para cada nivel Sankey
    sf2_where, sf2_params = _build_filter([("fondo", fondo)])
    sf3_where, sf3_params = _build_filter([("fondo", fondo), ("estado_del_contrato", estado)])
    sf4_where, sf4_params = _build_filter([("fondo", fondo), ("estado_del_contrato", estado), ("etapa_del_contrato", etapa)])

    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # ── KPIs ──
                # Contadores por grupo de ciclo de vida del contrato:
                #   En Ejecución → AOM → En Liquidación → Liquidado → Perdida Competencia
                # Todos usan COUNT(DISTINCT contrato) = por número de contratos.
                # Avances: AVG simple sobre TODOS los estados (metodología PBI) + AVG
                # solo contratos activos (EJECUCI%) para mostrar el avance real en obra.
                cur.execute(f"""
                    SELECT
                        (SELECT COUNT(DISTINCT contrato) FROM supervision.contratos
                          WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                            AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}) AS n_contratos,
                        (SELECT COUNT(*) FROM supervision.contratos
                          WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                            AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}) AS n_proyectos,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                            THEN contrato END)                        AS en_ejecucion,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato IN ('AOM','ATBF - AOM','ATEI - AOM')
                                            THEN contrato END)                        AS en_aom,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'LIQUIDACI%%'
                                            THEN contrato END)                        AS en_liquidacion,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato IN ('LIQUIDADO','LIQUIDADO - AOM')
                                            THEN contrato END)                        AS liquidados,
                        COUNT(DISTINCT CASE WHEN etapa_del_contrato LIKE 'PERDIDA%%'
                                            THEN contrato END)                        AS perdida_competencia,
                        ROUND(AVG(avance_de_obra) * 100, 2)                          AS avg_avance_fisico,
                        ROUND(AVG({_PARSE_FIN}) * 100, 2)                            AS avg_avance_financiero,
                        ROUND(AVG(CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                       THEN avance_de_obra END) * 100, 2)            AS avg_fisico_activos,
                        ROUND(AVG(CASE WHEN etapa_del_contrato LIKE 'EJECUCI%%'
                                       THEN ({_PARSE_FIN}) END) * 100, 2)            AS avg_financiero_activos
                    FROM supervision.contratos
                    WHERE {filter_where}
                """, kpi_params)
                k = cur.fetchone()

                # ── Donut fondos ──
                cur.execute(f"""
                    SELECT fondo, COUNT(DISTINCT contrato) AS contratos
                    FROM supervision.contratos
                    WHERE {filter_where}
                      AND fondo IS NOT NULL AND TRIM(fondo) != ''
                    GROUP BY fondo ORDER BY contratos DESC
                """, kpi_params)
                fondos = cur.fetchall()

                # ── Línea avance por año (AVG simple, metodología PBI) ──
                cur.execute(f"""
                    SELECT
                        FLOOR(ano)::integer                 AS anio,
                        ROUND(AVG(avance_de_obra)*100, 2)   AS avg_avance_obra
                    FROM supervision.contratos
                    WHERE {filter_where}
                      AND ano IS NOT NULL AND avance_de_obra IS NOT NULL
                    GROUP BY FLOOR(ano)::integer ORDER BY anio
                """, kpi_params)
                avance_anio = cur.fetchall()

                # ── Sankey nivel 1 — FONDO ──
                cur.execute(f"""
                    SELECT fondo AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where}
                      AND fondo IS NOT NULL AND TRIM(fondo) != ''
                    GROUP BY fondo ORDER BY n DESC
                """)
                s_fondo = cur.fetchall()

                # ── Sankey nivel 2 — ESTADO ──
                cur.execute(f"""
                    SELECT estado_del_contrato AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf2_where}
                    GROUP BY estado_del_contrato ORDER BY n DESC
                """, sf2_params)
                s_estado = cur.fetchall()

                # ── Sankey nivel 3 — ETAPA ──
                cur.execute(f"""
                    SELECT etapa_del_contrato AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf3_where}
                      AND etapa_del_contrato IS NOT NULL AND TRIM(etapa_del_contrato) != ''
                    GROUP BY etapa_del_contrato ORDER BY n DESC LIMIT 12
                """, sf3_params)
                s_etapa = cur.fetchall()

                # ── Sankey nivel 4 — EJECUTOR ──
                cur.execute(f"""
                    SELECT ejecutor AS valor, COUNT(DISTINCT contrato) AS n
                    FROM supervision.contratos
                    WHERE {base_where} {sf4_where}
                      AND ejecutor IS NOT NULL AND TRIM(ejecutor) != ''
                    GROUP BY ejecutor ORDER BY n DESC LIMIT 10
                """, sf4_params)
                s_ejecutor = cur.fetchall()

                # ── Total para nodo raíz Sankey ──
                cur.execute(f"""
                    SELECT COUNT(DISTINCT contrato) AS total
                    FROM supervision.contratos
                    WHERE contrato IS NOT NULL AND TRIM(contrato) != ''
                      AND FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}
                """)
                total = int((cur.fetchone() or [0])[0])

        def _f(v):
            return float(v) if v is not None else None

        return JSONResponse({
            "nContratos":              int(k[0] or 0),
            "nProyectos":              int(k[1] or 0),
            "enEjecucion":             int(k[2] or 0),
            "enAOM":                   int(k[3] or 0),
            "enLiquidacion":           int(k[4] or 0),
            "liquidados":              int(k[5] or 0),
            "perdidaCompetencia":      int(k[6] or 0),
            "avanceFisico":            _f(k[7])  or 0.0,
            "avanceFinanciero":        _f(k[8])  or 0.0,
            "avanceFisicoActivos":     _f(k[9])  or 0.0,
            "avanceFinancieroActivos": _f(k[10]) or 0.0,
            "porFondo": [{"fondo": r[0], "contratos": int(r[1])} for r in fondos],
            "avancePorAnio": [{"anio": int(r[0]), "avg_avance_obra": _f(r[1]) or 0.0} for r in avance_anio],
            "sankey": {
                "fondo":    [{"valor": r[0], "n": int(r[1])} for r in s_fondo],
                "estado":   [{"valor": r[0], "n": int(r[1])} for r in s_estado],
                "etapa":    [{"valor": r[0], "n": int(r[1])} for r in s_etapa],
                "ejecutor": [{"valor": r[0], "n": int(r[1])} for r in s_ejecutor],
            },
            "totalContratos": total,
        })
    except Exception as e:
        logger.error("[supervision/dashboard] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener supervision dashboard")
