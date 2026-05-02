"""
Endpoint subsidios — Portal Dirección EE
GET /v1/subsidios/kpis             → KPIs generales
GET /v1/subsidios/validaciones     → Tablero de validaciones (replica Power BI)
GET /v1/subsidios/deficit-historico → Déficit histórico
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


@router.get("/validaciones", summary="Tablero de validaciones de cuentas subsidios")
@limiter.limit("60/minute")
async def get_validaciones(
    request: Request,
    api_key: str = Depends(get_api_key),
    fondo: str = None,
    area: str = None,
    anio_desde: int = None,
    anio_hasta: int = None,
    prestador: str = None,
):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # Filtros dinámicos
                filtros = ["estado_validacion_organizado IS NOT NULL", "area IN ('SIN', 'ZNI')"]
                params = []
                if fondo:
                    filtros.append("fondo = %s")
                    params.append(fondo)
                if area:
                    filtros.append("area = %s")
                    params.append(area)
                if anio_desde:
                    filtros.append("anio >= %s")
                    params.append(anio_desde)
                if anio_hasta:
                    filtros.append("anio <= %s")
                    params.append(anio_hasta)
                if prestador:
                    filtros.append("nombre_prestador ILIKE %s")
                    params.append(f"%{prestador}%")

                where = " AND ".join(filtros)

                # Serie principal: conteo por area / anio / trimestre / estado_organizado
                cur.execute(f"""
                    SELECT
                        area,
                        anio,
                        trimestre,
                        estado_validacion_organizado AS estado,
                        COUNT(*) AS conteo
                    FROM subsidios.subsidios_validaciones
                    WHERE {where}
                      AND trimestre IS NOT NULL
                    GROUP BY area, anio, trimestre, estado_validacion_organizado
                    ORDER BY area, anio, trimestre, estado_validacion_organizado
                """, params)
                serie = [
                    {"area": r[0], "anio": r[1], "trimestre": r[2], "estado": r[3], "conteo": r[4]}
                    for r in cur.fetchall()
                ]

                # Filtros disponibles para el front
                cur.execute("SELECT DISTINCT fondo FROM subsidios.subsidios_validaciones WHERE fondo IS NOT NULL ORDER BY 1")
                fondos = [r[0] for r in cur.fetchall()]

                cur.execute("SELECT DISTINCT anio FROM subsidios.subsidios_validaciones WHERE anio IS NOT NULL ORDER BY 1")
                anios = [r[0] for r in cur.fetchall()]

                cur.execute("SELECT DISTINCT nombre_prestador FROM subsidios.subsidios_validaciones WHERE nombre_prestador IS NOT NULL AND area IN ('SIN','ZNI') ORDER BY 1")
                prestadores = [r[0] for r in cur.fetchall()]

                cur.execute("SELECT DISTINCT departamento FROM subsidios.subsidios_empresas WHERE departamento IS NOT NULL ORDER BY 1")
                departamentos = [r[0] for r in cur.fetchall()]

                # Resumen general (KPIs del tablero)
                cur.execute("""
                    SELECT
                        estado_validacion_organizado,
                        COUNT(*) AS total
                    FROM subsidios.subsidios_validaciones
                    WHERE area IN ('SIN','ZNI')
                      AND estado_validacion_organizado IS NOT NULL
                    GROUP BY estado_validacion_organizado
                    ORDER BY estado_validacion_organizado
                """)
                resumen = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute("""
                    SELECT COUNT(DISTINCT nombre_prestador)
                    FROM subsidios.subsidios_validaciones
                    WHERE area IN ('SIN','ZNI')
                """)
                total_prestadores = cur.fetchone()[0]

                cur.execute("SELECT MAX(fecha_actualizacion) FROM subsidios.subsidios_validaciones")
                ultima_act = cur.fetchone()[0]

        return JSONResponse({
            "serie": serie,
            "resumen": resumen,
            "totalPrestadores": total_prestadores,
            "ultimaActualizacion": ultima_act.isoformat() if ultima_act else None,
            "filtros": {
                "fondos": fondos,
                "anios": anios,
                "prestadores": prestadores,
                "departamentos": departamentos,
            },
        })
    except Exception as e:
        logger.error("[subsidios/validaciones] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener validaciones")


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
