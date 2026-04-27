"""
Endpoint contratos OR — Portal Dirección EE
GET /v1/contratos-or/dashboard → contratos_or.seguimiento (Power BI logic)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_cm = PostgreSQLConnectionManager()


@router.get("/dashboard", summary="Dashboard seguimiento contratos OR")
@limiter.limit("60/minute")
async def get_contratos_or_dashboard(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # KPIs por proyecto
                cur.execute("""
                    WITH pagados AS (
                        SELECT nombre_proyecto_id, nro_desembolso
                        FROM contratos_or.seguimiento
                        WHERE necesaria_para_desembolso = 'Sí'
                        GROUP BY nombre_proyecto_id, nro_desembolso
                        HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                    )
                    SELECT
                        s.nombre_proyecto_id,
                        s.ejecutor,
                        s.departamento,
                        s.municipio,
                        ROUND(AVG(s.avance) * 100, 1)                                 AS avance_general,
                        ROUND(COALESCE(SUM(
                            CASE WHEN p.nro_desembolso IS NOT NULL AND s.desembolso IS NOT NULL
                                 THEN s.desembolso ELSE 0 END
                        ), 0) * 100, 1)                                               AS avance_financiero,
                        COUNT(DISTINCT CASE WHEN s.nro_desembolso IS NOT NULL
                              THEN s.nro_desembolso END)                               AS total_desembolsos,
                        COUNT(DISTINCT p.nro_desembolso)                               AS pagos_realizados
                    FROM contratos_or.seguimiento s
                    LEFT JOIN pagados p
                        ON s.nombre_proyecto_id = p.nombre_proyecto_id
                       AND s.nro_desembolso     = p.nro_desembolso
                       AND s.necesaria_para_desembolso = 'Sí'
                    GROUP BY s.nombre_proyecto_id, s.ejecutor, s.departamento, s.municipio
                    ORDER BY s.nombre_proyecto_id
                """)
                cols_p = [d[0] for d in cur.description]
                proyectos_rows = [dict(zip(cols_p, r)) for r in cur.fetchall()]

                # KPIs globales
                cur.execute("""
                    WITH pagados AS (
                        SELECT nombre_proyecto_id, nro_desembolso
                        FROM contratos_or.seguimiento
                        WHERE necesaria_para_desembolso = 'Sí'
                        GROUP BY nombre_proyecto_id, nro_desembolso
                        HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                    )
                    SELECT
                        COUNT(DISTINCT s.nombre_proyecto_id)                           AS n_contratos,
                        ROUND(AVG(s.avance) * 100, 1)                                 AS avance_general,
                        ROUND(COALESCE(SUM(
                            CASE WHEN p.nro_desembolso IS NOT NULL AND s.desembolso IS NOT NULL
                                 THEN s.desembolso ELSE 0 END
                        ), 0) / NULLIF(COUNT(DISTINCT s.nombre_proyecto_id), 0) * 100, 1) AS avance_financiero,
                        COUNT(DISTINCT
                            CASE WHEN p.nro_desembolso IS NOT NULL
                                 THEN s.nombre_proyecto_id || '-' || s.nro_desembolso::text
                            END)                                                        AS pagos_realizados_total,
                        COUNT(DISTINCT s.nombre_proyecto_id) *
                            COUNT(DISTINCT CASE WHEN s.nro_desembolso IS NOT NULL
                                  THEN s.nro_desembolso END)                           AS pagos_posibles_total
                    FROM contratos_or.seguimiento s
                    LEFT JOIN pagados p
                        ON s.nombre_proyecto_id = p.nombre_proyecto_id
                       AND s.nro_desembolso     = p.nro_desembolso
                       AND s.necesaria_para_desembolso = 'Sí'
                """)
                g = cur.fetchone()

                # Progreso por desembolso
                cur.execute("""
                    WITH pagados AS (
                        SELECT nombre_proyecto_id, nro_desembolso
                        FROM contratos_or.seguimiento
                        WHERE necesaria_para_desembolso = 'Sí'
                        GROUP BY nombre_proyecto_id, nro_desembolso
                        HAVING COUNT(*) = COUNT(CASE WHEN estado = 'Completo' THEN 1 END)
                    )
                    SELECT
                        s.nro_desembolso::int                                          AS numero,
                        COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' THEN 1 END) AS act_necesarias,
                        COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí'
                                    AND s.estado = 'Completo' THEN 1 END)              AS act_completas,
                        ROUND(
                            COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí'
                                        AND s.estado = 'Completo' THEN 1 END)::numeric /
                            NULLIF(COUNT(CASE WHEN s.necesaria_para_desembolso = 'Sí' THEN 1 END), 0) * 100
                        , 1)                                                           AS pct_completado,
                        COUNT(DISTINCT p.nombre_proyecto_id)                          AS proyectos_pagados
                    FROM contratos_or.seguimiento s
                    LEFT JOIN pagados p
                        ON s.nombre_proyecto_id = p.nombre_proyecto_id
                       AND s.nro_desembolso     = p.nro_desembolso
                    WHERE s.nro_desembolso IS NOT NULL
                    GROUP BY s.nro_desembolso
                    ORDER BY s.nro_desembolso
                """)
                cols_d = [d[0] for d in cur.description]
                desembolsos_rows = [dict(zip(cols_d, r)) for r in cur.fetchall()]

        def _f(v):
            return float(v) if v is not None else None

        n_contratos       = int(g[0] or 0)
        avance_general    = _f(g[1])
        avance_financiero = _f(g[2])
        pagos_real        = int(g[3] or 0)
        pagos_pos         = int(g[4] or 0)

        return JSONResponse({
            "nContratos":        n_contratos,
            "avanceGeneral":     avance_general,
            "avanceFinanciero":  avance_financiero,
            "pagosRealizados":   pagos_real,
            "pagosPosibles":     pagos_pos,
            "pctPagosRealizados": round(pagos_real / pagos_pos * 100, 1) if pagos_pos else 0.0,
            "desembolsos": [
                {
                    "numero":            int(d["numero"]),
                    "actNecesarias":     int(d["act_necesarias"]),
                    "actCompletas":      int(d["act_completas"]),
                    "pctCompletado":     _f(d["pct_completado"]),
                    "proyectosPagados":  int(d["proyectos_pagados"]),
                }
                for d in desembolsos_rows
            ],
            "proyectos": [
                {
                    "nombre":           p["nombre_proyecto_id"],
                    "ejecutor":         p["ejecutor"],
                    "departamento":     p["departamento"],
                    "municipio":        p["municipio"],
                    "avanceGeneral":    _f(p["avance_general"]),
                    "avanceFinanciero": _f(p["avance_financiero"]),
                    "totalDesembolsos": int(p["total_desembolsos"]),
                    "pagosRealizados":  int(p["pagos_realizados"]),
                }
                for p in proyectos_rows
            ],
        })
    except Exception as e:
        logger.error("[contratos-or] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener contratos OR")
