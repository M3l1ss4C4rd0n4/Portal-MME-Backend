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

from decimal import Decimal
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

                # KPIs por año — fuente oficial: hoja 'KPI'S Subsidios' del Excel
                cur.execute("""
                    SELECT anio, n_resoluciones, valor_asignado, valor_pendiente
                    FROM subsidios.kpis_resumen
                    WHERE anio IN (2025, 2026)
                    ORDER BY anio
                """)
                kpis_rows = {r[0]: r for r in cur.fetchall()}

                def _kpi_row(anio):
                    r = kpis_rows.get(anio)
                    if r:
                        asig = float(r[2] or 0)
                        pend = float(r[3] or 0)
                        return (int(r[1] or 0), asig, pend, asig - pend)
                    return (0, None, None, None)

                row25 = _kpi_row(2025)
                row26 = _kpi_row(2026)

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

                cur.execute("SELECT MAX(fecha) FROM subsidios.subsidios_import_log")
                ts_sub = cur.fetchone()[0]

        def _f(v):
            return float(v) if v is not None else None

        return JSONResponse({
            "ultima_actualizacion": ts_sub.strftime("%d/%m/%Y, %H:%M") if ts_sub else None,
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
    fechaActualizacion: str = None,
):
    # CASE SQL igual al route Next.js: mapea estado_validacion cuando organizado es NULL
    _ESTADO_SQL = """
        CASE
          WHEN estado_validacion_organizado IS NOT NULL THEN estado_validacion_organizado
          WHEN estado_validacion = 'VF'    THEN 'e. VF'
          WHEN estado_validacion = 'VP'    THEN 'd. VP'
          WHEN estado_validacion = 'VI'    THEN 'b. VI'
          WHEN estado_validacion = 'VI SP' THEN 'c. VI SP'
          ELSE 'a. Otros'
        END
    """

    # Parsear fechaActualizacion "YYYY-MM" en year/month para EXTRACT
    fa_year: int | None = None
    fa_month: int | None = None
    if fechaActualizacion:
        parts = fechaActualizacion.split("-")
        if len(parts) == 2:
            try:
                fa_year, fa_month = int(parts[0]), int(parts[1])
            except ValueError:
                pass

    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # Filtros base: condición de estado (ambas columnas) — sin restricción de área
                filtros = [
                    "(estado_validacion IS NOT NULL OR estado_validacion_organizado IS NOT NULL)",
                ]
                params = []

                # Fecha de actualización (EXTRACT, igual que Next.js)
                if fa_year and fa_month:
                    filtros.append("EXTRACT(YEAR FROM fecha_actualizacion) = %s")
                    params.append(fa_year)
                    filtros.append("EXTRACT(MONTH FROM fecha_actualizacion) = %s")
                    params.append(fa_month)

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

                # Serie: usa el mismo CASE expression que Next.js
                cur.execute(f"""
                    SELECT
                        area,
                        anio,
                        trimestre,
                        {_ESTADO_SQL} AS estado,
                        COUNT(*) AS conteo
                    FROM subsidios.subsidios_validaciones
                    WHERE {where}
                      AND trimestre IS NOT NULL
                    GROUP BY 1, 2, 3, 4
                    ORDER BY 1, 2, 3, 4
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

                # Resumen KPIs — mismos filtros + CASE expression (igual que Next.js)
                cur.execute(f"""
                    SELECT {_ESTADO_SQL} AS estado, COUNT(*) AS total
                    FROM subsidios.subsidios_validaciones
                    WHERE {where}
                    GROUP BY 1
                    ORDER BY 1
                """, params)
                resumen = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(f"""
                    SELECT COUNT(DISTINCT nombre_prestador)
                    FROM subsidios.subsidios_validaciones
                    WHERE {where}
                """, params)
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
                    SELECT anio, subsidios, contribuciones,
                           deficit_anual, deficit_acumulado,
                           apropiacion_pgn, recursos_faltantes
                    FROM subsidios.deficit_historico
                    ORDER BY anio
                """)
                cols = [d[0] for d in cur.description]
                rows = []
                for r in cur.fetchall():
                    row = {}
                    for k, v in zip(cols, r):
                        if isinstance(v, Decimal):
                            row[k] = float(v) if v is not None else None
                        elif hasattr(v, 'isoformat'):
                            row[k] = v.isoformat()
                        else:
                            row[k] = v
                    rows.append(row)

                cur.execute("SELECT MAX(fecha_carga) FROM subsidios.deficit_historico")
                ts_def = cur.fetchone()[0]

        return JSONResponse({
            "ultima_actualizacion": ts_def.strftime("%d/%m/%Y, %H:%M") if ts_def else None,
            "data": rows,
        })
    except Exception as e:
        logger.error("[subsidios/deficit] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener déficit histórico")
