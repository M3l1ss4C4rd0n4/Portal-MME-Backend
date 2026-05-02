"""
Endpoints Fenoge — Portal Dirección EE

GET /v1/fenoge/mapa      → KPIs, mapa de CEs, por departamento, por municipio
GET /v1/fenoge/seguimiento → datos de avance de obra para gráfica de líneas
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

_DEPT_MAP: dict[str, str] = {
    "bogota_d.c.": "SANTAFE DE BOGOTA D.C",
    "narino": "NARIÑO",
    "san_andres_y_providencia": "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA",
}

FASE_LABELS = {"1_0": "Fenoge 1.0", "1_1": "Fenoge 1.1", "CE": "CE"}


def _to_geo_id(dept: str) -> str:
    key = dept.lower().replace(" ", "_")
    return _DEPT_MAP.get(key, dept.upper().replace("_", " "))


def _f(v):
    return float(v) if v is not None else None


def _coord(v) -> float | None:
    try:
        return float(v) if v and str(v).strip() not in ("", "-", "N/A") else None
    except (ValueError, TypeError):
        return None


# ─── /mapa ────────────────────────────────────────────────────────────────────
@router.get("/mapa", summary="Mapa y KPIs de comunidades energéticas Fenoge")
@limiter.limit("60/minute")
async def get_fenoge_mapa(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:

                # KPIs globales
                cur.execute("""
                    SELECT
                        COUNT(*)             AS total_ces,
                        SUM(kwp)             AS total_kwp,
                        AVG(kwp)             AS avg_kwp,
                        SUM(beneficiarios)   AS total_beneficiarios,
                        AVG(beneficiarios)   AS avg_beneficiarios,
                        SUM(valor_proyecto)  AS total_inversion,
                        AVG(valor_proyecto)  AS avg_inversion
                    FROM fenoge.comunidades
                """)
                k = cur.fetchone()

                # Desglose por departamento × fase
                cur.execute("""
                    SELECT
                        departamento,
                        COALESCE(NULLIF(TRIM(fase), ''), 'Sin clasificar') AS fase,
                        COUNT(*)            AS count,
                        SUM(kwp)            AS kwp,
                        SUM(valor_proyecto) AS inversion
                    FROM fenoge.comunidades
                    WHERE departamento IS NOT NULL
                    GROUP BY departamento, fase
                    ORDER BY departamento, fase
                """)
                fase_rows = cur.fetchall()

                # Puntos individuales con coordenadas
                cur.execute("""
                    SELECT
                        comunidad        AS nombre,
                        municipio,
                        departamento     AS dept,
                        latitud          AS lat,
                        longitud         AS lng,
                        COALESCE(NULLIF(TRIM(fase), ''), 'Sin clasificar') AS fase,
                        kwp              AS capacidad
                    FROM fenoge.comunidades
                    WHERE latitud  IS NOT NULL
                      AND longitud IS NOT NULL
                    ORDER BY departamento, municipio
                """)
                puntos_rows = cur.fetchall()

                # Municipios por departamento
                cur.execute("""
                    SELECT
                        departamento,
                        municipio,
                        COUNT(*)            AS count,
                        SUM(kwp)            AS kwp,
                        SUM(valor_proyecto) AS inversion
                    FROM fenoge.comunidades
                    WHERE municipio IS NOT NULL
                    GROUP BY departamento, municipio
                    ORDER BY departamento, count DESC
                """)
                muni_rows = cur.fetchall()

                # Promedios por departamento
                cur.execute("""
                    SELECT
                        departamento,
                        AVG(kwp)            AS avg_kwp,
                        AVG(beneficiarios)  AS avg_beneficiarios,
                        AVG(valor_proyecto) AS avg_inversion,
                        SUM(beneficiarios)  AS sum_beneficiarios
                    FROM fenoge.comunidades
                    WHERE departamento IS NOT NULL
                    GROUP BY departamento
                """)
                dept_avg_rows = cur.fetchall()

        # --- Construir detalle_fase (equivalente a detalleZona) ---
        detalle_fase = [
            {
                "departamento":    r[0],
                "departamentoGeo": _to_geo_id(r[0]),
                "fase":            r[1],
                "faseLabel":       FASE_LABELS.get(r[1], r[1]),
                "count":           int(r[2]),
                "capacidad":       _f(r[3]) or 0.0,
                "inversion":       _f(r[4]) or 0.0,
            }
            for r in fase_rows
        ]

        # por_departamento
        dept_map: dict[str, dict] = {}
        for d in detalle_fase:
            gk = d["departamentoGeo"]
            if gk not in dept_map:
                dept_map[gk] = {
                    "departamento": d["departamento"],
                    "departamentoGeo": gk,
                    "count": 0, "capacidad": 0.0, "inversion": 0.0,
                }
            dept_map[gk]["count"]     += d["count"]
            dept_map[gk]["capacidad"] += d["capacidad"]
            dept_map[gk]["inversion"] += d["inversion"]
        por_departamento = sorted(dept_map.values(), key=lambda x: -x["count"])

        # puntos
        puntos = [
            {
                "nombre":          r[0] or "",
                "municipio":       r[1] or "",
                "departamentoGeo": _to_geo_id(r[2]),
                "fase":            r[5],
                "lat":             _coord(r[3]),
                "lng":             _coord(r[4]),
                "capacidad":       _coord(r[6]),
            }
            for r in puntos_rows
            if _coord(r[3]) is not None and _coord(r[4]) is not None
        ]

        # por_municipio
        por_municipio: dict[str, list] = {}
        for r in muni_rows:
            gk = _to_geo_id(r[0])
            if gk not in por_municipio:
                por_municipio[gk] = []
            por_municipio[gk].append({
                "municipio": r[1],
                "count":     int(r[2]),
                "capacidad": _f(r[3]) or 0.0,
                "inversion": _f(r[4]) or 0.0,
            })

        # dept_avgs
        dept_avgs: dict[str, dict] = {}
        for r in dept_avg_rows:
            dept_avgs[_to_geo_id(r[0])] = {
                "avgKwp":     _f(r[1]),
                "avgBenef":   _f(r[2]),
                "avgInv":     _f(r[3]),
                "sumBenef":   _f(r[4]) or 0.0,
            }

        return JSONResponse({
            "totalCes":       int(k[0]),
            "totalKwp":       _f(k[1]) or 0.0,
            "avgKwp":         _f(k[2]),
            "totalBenef":     _f(k[3]) or 0.0,
            "avgBenef":       _f(k[4]),
            "totalInversion": _f(k[5]) or 0.0,
            "avgInversion":   _f(k[6]),
            "porDepartamento": por_departamento,
            "detalleFase":     detalle_fase,
            "puntos":          puntos,
            "porMunicipio":    por_municipio,
            "deptAvgs":        dept_avgs,
        })

    except Exception as e:
        logger.error("[fenoge/mapa] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener datos Fenoge")


# ─── /seguimiento ─────────────────────────────────────────────────────────────
@router.get("/seguimiento", summary="Avance de obra Fenoge para gráfica de líneas")
@limiter.limit("60/minute")
async def get_fenoge_seguimiento(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:

                # Catálogos para filtros
                cur.execute("""
                    SELECT DISTINCT region FROM fenoge.seguimiento
                    WHERE region IS NOT NULL ORDER BY region
                """)
                regiones = [r[0] for r in cur.fetchall()]

                cur.execute("""
                    SELECT DISTINCT numero_contrato FROM fenoge.seguimiento
                    WHERE numero_contrato IS NOT NULL ORDER BY numero_contrato
                """)
                contratos = [r[0] for r in cur.fetchall()]

                # Datos completos ordenados por fecha y contrato
                cur.execute("""
                    SELECT
                        region,
                        numero_contrato,
                        dia_actualizacion,
                        avance_real_acumulado_pct,
                        avance_programado_acumulado_pct
                    FROM fenoge.seguimiento
                    WHERE dia_actualizacion IS NOT NULL
                    ORDER BY region, numero_contrato, dia_actualizacion
                """)
                rows = cur.fetchall()

        # Agrupar por contrato para generar series de líneas
        # Retornamos los datos planos + catálogos; el frontend agrupa
        data = [
            {
                "region":         r[0],
                "contrato":       r[1],
                "fecha":          r[2].isoformat() if r[2] else None,
                "realAcum":       float(r[3]) * 100 if r[3] is not None else None,
                "programadoAcum": float(r[4]) * 100 if r[4] is not None else None,
            }
            for r in rows
        ]

        return JSONResponse({
            "regiones":  regiones,
            "contratos": contratos,
            "data":      data,
        })

    except Exception as e:
        logger.error("[fenoge/seguimiento] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener seguimiento Fenoge")
