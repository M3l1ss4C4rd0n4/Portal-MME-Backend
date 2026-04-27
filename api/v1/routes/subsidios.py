"""
Endpoint subsidios — Portal Dirección EE
GET /v1/subsidios/kpis → schema subsidios.subsidios_pagos + subsidios.deficit_historico
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


@router.get("/kpis", summary="KPIs de subsidios FSSRI/FOES")
@limiter.limit("60/minute")
async def get_subsidios_kpis(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # Déficit acumulado (estado Pendiente)
                cur.execute("""
                    SELECT SUM(saldo_pendiente) AS deficit_acumulado
                    FROM subsidios.subsidios_pagos
                    WHERE estado_pago = 'Pendiente'
                """)
                deficit = float(cur.fetchone()[0] or 0)

                # KPIs año 2025
                cur.execute("""
                    SELECT
                        COUNT(DISTINCT no_resolucion)  AS resoluciones,
                        SUM(valor_resolucion)          AS valor_asignado,
                        SUM(saldo_pendiente)           AS pendiente,
                        SUM(valor_pagado)              AS pagado
                    FROM subsidios.subsidios_pagos
                    WHERE LEFT(anio_trimestre_resolucion, 4)::int = 2025
                """)
                row25 = cur.fetchone()

                # KPIs año 2026
                cur.execute("""
                    SELECT
                        COUNT(DISTINCT no_resolucion)  AS resoluciones,
                        SUM(valor_resolucion)          AS valor_asignado,
                        SUM(saldo_pendiente)           AS pendiente,
                        SUM(valor_pagado)              AS pagado
                    FROM subsidios.subsidios_pagos
                    WHERE LEFT(anio_trimestre_resolucion, 4)::int = 2026
                """)
                row26 = cur.fetchone()

                # Histórico por año y fondo
                cur.execute("""
                    SELECT
                        anio,
                        fondo,
                        SUM(valor_resolucion) AS valor_asignado,
                        SUM(valor_pagado)     AS pagado,
                        SUM(saldo_pendiente)  AS pendiente
                    FROM subsidios.subsidios_pagos
                    WHERE fondo IN ('FSSRI', 'FOES')
                    GROUP BY anio, fondo
                    ORDER BY anio, fondo
                """)
                cols_h = [d[0] for d in cur.description]
                historico = [dict(zip(cols_h, r)) for r in cur.fetchall()]

        def _f(v):
            return float(v) if v is not None else None

        return JSONResponse({
            "deficitAcumulado": deficit,
            "anio2025": {
                "resoluciones": int(row25[0] or 0),
                "valorAsignado": _f(row25[1]),
                "pendiente": _f(row25[2]),
                "pagado": _f(row25[3]),
            },
            "anio2026": {
                "resoluciones": int(row26[0] or 0),
                "valorAsignado": _f(row26[1]),
                "pendiente": _f(row26[2]),
                "pagado": _f(row26[3]),
            },
            "historico": [
                {k: _f(v) if k != "fondo" and k != "anio" else v for k, v in row.items()}
                for row in historico
            ],
        })
    except Exception as e:
        logger.error("[subsidios] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener subsidios")


@router.get("/deficit-historico", summary="Déficit histórico de subsidios")
@limiter.limit("60/minute")
async def get_deficit_historico(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT anio, fondo, deficit
                    FROM subsidios.deficit_historico
                    ORDER BY anio, fondo
                """)
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        return JSONResponse(rows)
    except Exception as e:
        logger.error("[subsidios/deficit] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener déficit histórico")
