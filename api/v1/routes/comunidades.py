"""
Endpoint comunidades energéticas — Portal Dirección EE
GET /v1/comunidades/mapa → comunidades.base (KPIs, mapa, por departamento)
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


def _to_geo_id(dept: str) -> str:
    key = dept.lower().replace(" ", "_")
    return _DEPT_MAP.get(key, dept.upper().replace("_", " "))


@router.get("/mapa", summary="Mapa y KPIs de comunidades energéticas implementadas")
@limiter.limit("60/minute")
async def get_comunidades_mapa(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # KPIs globales
                cur.execute("""
                    SELECT
                        COUNT(*)                                                           AS implementadas,
                        SUM(CASE WHEN inversion_estimada IS NOT NULL
                                  AND inversion_estimada ~ '^[0-9]'
                             THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                             ELSE 0 END)                                                   AS inversion_estimada,
                        AVG(CASE WHEN inversion_estimada IS NOT NULL
                                  AND inversion_estimada ~ '^[0-9]'
                             THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                             END)                                                          AS avg_inversion,
                        SUM(capacidad_de_generacion_kwp)                                  AS capacidad_kwp,
                        AVG(capacidad_de_generacion_kwp)                                  AS avg_capacidad,
                        SUM(usuarios_equivalentes)                                        AS usuarios_equiv,
                        AVG(usuarios_equivalentes)                                        AS avg_usuarios,
                        SUM(beneficiarios_equivalentes)                                   AS beneficiarios_equiv,
                        AVG(beneficiarios_equivalentes)                                   AS avg_beneficiarios
                    FROM comunidades.base
                    WHERE implementado = 'Si'
                """)
                k = cur.fetchone()

                # Desglose por departamento × zona
                cur.execute("""
                    SELECT
                        departamento,
                        COALESCE(NULLIF(TRIM(zona_sin_zni_mixto),''),'Sin clasificar') AS zona,
                        COUNT(*)                                                        AS count,
                        SUM(capacidad_de_generacion_kwp)                               AS capacidad,
                        SUM(CASE WHEN inversion_estimada IS NOT NULL
                                  AND inversion_estimada ~ '^[0-9]'
                             THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                             ELSE 0 END)                                               AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND departamento IS NOT NULL
                    GROUP BY departamento, zona_sin_zni_mixto
                    ORDER BY departamento, zona
                """)
                zona_rows = cur.fetchall()

                # Puntos individuales con coordenadas
                cur.execute("""
                    SELECT
                        nombre_de_la_organizacion AS nombre,
                        municipio,
                        departamento              AS dept,
                        latitud                   AS lat,
                        longitud                  AS lng,
                        COALESCE(NULLIF(TRIM(zona_sin_zni_mixto),''),'Sin clasificar') AS zona,
                        CAST(capacidad_de_generacion_kwp AS text)                     AS capacidad
                    FROM comunidades.base
                    WHERE implementado = 'Si'
                      AND latitud  IS NOT NULL AND TRIM(latitud)  NOT IN ('', '-', 'N/A')
                      AND longitud IS NOT NULL AND TRIM(longitud) NOT IN ('', '-', 'N/A')
                    ORDER BY departamento, municipio
                """)
                puntos_rows = cur.fetchall()

                # Municipios por departamento
                cur.execute("""
                    SELECT
                        departamento,
                        municipio,
                        COUNT(*)                                                        AS count,
                        SUM(capacidad_de_generacion_kwp)                               AS capacidad,
                        SUM(CASE WHEN inversion_estimada IS NOT NULL
                                  AND inversion_estimada ~ '^[0-9]'
                             THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                             ELSE 0 END)                                               AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND municipio IS NOT NULL
                    GROUP BY departamento, municipio
                    ORDER BY departamento, count DESC
                """)
                muni_rows = cur.fetchall()

                # Promedios por departamento
                cur.execute("""
                    SELECT
                        departamento,
                        AVG(capacidad_de_generacion_kwp)  AS avg_capacidad,
                        AVG(usuarios_equivalentes)         AS avg_usuarios,
                        AVG(beneficiarios_equivalentes)    AS avg_beneficiarios,
                        AVG(CASE WHEN inversion_estimada IS NOT NULL
                                  AND inversion_estimada ~ '^[0-9]'
                             THEN CAST(REPLACE(REPLACE(inversion_estimada,'$',''),',','') AS numeric)
                             END)                          AS avg_inversion,
                        SUM(usuarios_equivalentes)         AS sum_usuarios,
                        SUM(beneficiarios_equivalentes)    AS sum_beneficiarios
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND departamento IS NOT NULL
                    GROUP BY departamento
                """)
                dept_avg_rows = cur.fetchall()

        def _f(v):
            return float(v) if v is not None else None

        # detalle_zona con geo key
        detalle_zona = [
            {
                "departamento":    r[0],
                "departamentoGeo": _to_geo_id(r[0]),
                "zona":            r[1],
                "count":           int(r[2]),
                "capacidad":       _f(r[3]) or 0.0,
                "inversion":       _f(r[4]) or 0.0,
            }
            for r in zona_rows
        ]

        # por_departamento — suma por depto (agrupa zonas)
        dept_map: dict[str, dict] = {}
        for d in detalle_zona:
            gk = d["departamentoGeo"]
            if gk not in dept_map:
                dept_map[gk] = {"departamento": d["departamento"], "departamentoGeo": gk,
                                 "count": 0, "capacidad": 0.0, "inversion": 0.0}
            dept_map[gk]["count"]     += d["count"]
            dept_map[gk]["capacidad"] += d["capacidad"]
            dept_map[gk]["inversion"] += d["inversion"]
        por_departamento = sorted(dept_map.values(), key=lambda x: -x["count"])

        def _coord(v) -> float | None:
            try:
                return float(v) if v and str(v).strip() not in ('', '-', 'N/A') else None
            except (ValueError, TypeError):
                return None

        # puntos
        puntos = [
            {
                "nombre":          r[0] or "",
                "municipio":       r[1] or "",
                "departamentoGeo": _to_geo_id(r[2]),
                "zona":            r[5],
                "lat":             _coord(r[3]),
                "lng":             _coord(r[4]),
                "capacidad":       _coord(r[6]),
            }
            for r in puntos_rows
            if _coord(r[3]) is not None and _coord(r[4]) is not None
        ]

        # por_municipio — dict clave=departamentoGeo
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

        # dept_avgs — dict clave=departamentoGeo
        dept_avgs: dict[str, dict] = {}
        for r in dept_avg_rows:
            dept_avgs[_to_geo_id(r[0])] = {
                "avgCap":   _f(r[1]),
                "avgUsu":   _f(r[2]),
                "avgBenef": _f(r[3]),
                "avgInv":   _f(r[4]),
                "sumUsu":   _f(r[5]) or 0.0,
                "sumBenef": _f(r[6]) or 0.0,
            }

        return JSONResponse({
            "implementadas":      int(k[0]),
            "inversionEstimada":  _f(k[1]) or 0.0,
            "capacidadKwp":       _f(k[3]) or 0.0,
            "usuariosEquiv":      _f(k[5]) or 0.0,
            "beneficiariosEquiv": _f(k[7]) or 0.0,
            "avgCapacidad":       _f(k[4]),
            "avgUsuarios":        _f(k[6]),
            "avgBeneficiarios":   _f(k[8]),
            "avgInversion":       _f(k[2]),
            "porDepartamento":    por_departamento,
            "detalleZona":        detalle_zona,
            "puntos":             puntos,
            "porMunicipio":       por_municipio,
            "deptAvgs":           dept_avgs,
        })
    except Exception as e:
        logger.error("[comunidades/mapa] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener comunidades")
