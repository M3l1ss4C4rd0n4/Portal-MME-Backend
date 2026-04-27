"""
Endpoint presupuesto — Portal Dirección EE
GET /v1/presupuesto/resumen → tabla presupuesto.resumen
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


@router.get("/resumen", summary="Presupuesto DEE — resumen por proyecto")
@limiter.limit("60/minute")
async def get_presupuesto_resumen(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        proyecto,
                        apropiacion,
                        compromisos            AS comprometido,
                        comprometido           AS pct_comprometido,
                        obligados,
                        obligado               AS pct_obligado,
                        sin_comprometer_disponible AS disponible
                    FROM presupuesto.resumen
                    WHERE proyecto NOT IN ('Proyecto', 'TOTAL')
                    ORDER BY apropiacion DESC
                """)
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]

                cur.execute("""
                    SELECT
                        SUM(apropiacion)                                           AS apropiacion,
                        SUM(compromisos)                                           AS comprometido,
                        SUM(compromisos) / NULLIF(SUM(apropiacion), 0)            AS pct_comprometido,
                        SUM(obligados)                                             AS obligados,
                        SUM(obligados)::numeric / NULLIF(SUM(apropiacion), 0)     AS pct_obligado,
                        SUM(sin_comprometer_disponible)                            AS disponible
                    FROM presupuesto.resumen
                    WHERE proyecto NOT IN ('Proyecto', 'TOTAL')
                """)
                cols_t = [d[0] for d in cur.description]
                totales = dict(zip(cols_t, cur.fetchone()))

        # Convert Decimal → float for JSON serialization
        def _f(v):
            return float(v) if v is not None else None

        return JSONResponse({
            "proyectos": [
                {k: _f(v) if hasattr(v, "__float__") else v for k, v in row.items()}
                for row in rows
            ],
            "totales": {k: _f(v) for k, v in totales.items()},
        })
    except Exception as e:
        logger.error("[presupuesto] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener presupuesto")
