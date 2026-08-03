"""
Endpoint comunidades energéticas — Portal Dirección EE
GET /v1/comunidades/mapa → comunidades.base (KPIs, mapa, por departamento)
"""

import logging
import unicodedata
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


def _inv_numeric(col: str = "inversion_estimada") -> str:
    """Expresión SQL compatible con inversion_estimada TEXT o NUMERIC.

    Celdas con errores de fórmula (#REF!, etc.) o basura no numérica se
    ignoran (NULL) en vez de tumbar la consulta con un error de CAST —
    el patrón exige que el string quede COMPLETO en formato numérico,
    no solo que empiece por un dígito.
    """
    return f"""CASE WHEN {col} IS NULL THEN NULL
         WHEN REPLACE(REPLACE({col}::text, '$', ''), ',', '') ~ '^-?[0-9]+(\\.[0-9]+)?$'
         THEN REPLACE(REPLACE({col}::text, '$', ''), ',', '')::numeric
         ELSE NULL END"""


_COORD_WHERE = """
    latitud IS NOT NULL AND longitud IS NOT NULL
    AND NULLIF(TRIM(latitud::text), '') IS NOT NULL
    AND NULLIF(TRIM(longitud::text), '') IS NOT NULL
    AND TRIM(latitud::text) NOT IN ('-', 'N/A', 'nan', 'NaN')
    AND TRIM(longitud::text) NOT IN ('-', 'N/A', 'nan', 'NaN')
"""


def _to_geo_id(dept: str) -> str:
    ascii_dept = unicodedata.normalize('NFKD', dept).encode('ascii', 'ignore').decode('ascii')
    key = ascii_dept.lower().replace(" ", "_")
    return _DEPT_MAP.get(key, ascii_dept.upper().replace("_", " "))


@router.get("/mapa", summary="Mapa y KPIs de comunidades energéticas implementadas")
@limiter.limit("60/minute")
async def get_comunidades_mapa(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # KPIs globales
                cur.execute(f"""
                    SELECT
                        COUNT(*)                                                           AS implementadas,
                        SUM(COALESCE({_inv_numeric()}, 0))                                AS inversion_estimada,
                        AVG({_inv_numeric()})                                             AS avg_inversion,
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

                # Agrupaciones categóricas nuevas
                cur.execute(f"""
                    SELECT estado_actual,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND estado_actual IS NOT NULL
                    GROUP BY estado_actual
                    ORDER BY count DESC
                """)
                estado_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT tipo_ce,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND tipo_ce IS NOT NULL
                    GROUP BY tipo_ce
                    ORDER BY count DESC
                """)
                tipo_ce_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT fuentes_energia,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND fuentes_energia IS NOT NULL AND NULLIF(TRIM(fuentes_energia), '') IS NOT NULL
                    GROUP BY fuentes_energia
                    ORDER BY count DESC
                """)
                fuente_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT COALESCE(NULLIF(TRIM(zona_sin_zni_mixto),''),'Sin clasificar') AS zona,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si'
                    GROUP BY zona
                    ORDER BY count DESC
                """)
                zona_flat_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT etnia,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND etnia IS NOT NULL
                    GROUP BY etnia
                    ORDER BY count DESC
                """)
                etnia_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT ejecutor,
                        COUNT(*) AS count,
                        SUM(capacidad_de_generacion_kwp) AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0)) AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND ejecutor IS NOT NULL
                    GROUP BY ejecutor
                    ORDER BY count DESC
                """)
                ejecutor_rows = cur.fetchall()

                cur.execute("""
                    SELECT
                        MIN(fecha_registro) AS min_registro,
                        MAX(fecha_registro) AS max_registro,
                        MIN(fecha_operacion) AS min_operacion,
                        MAX(fecha_operacion) AS max_operacion,
                        COUNT(*) FILTER (WHERE fecha_registro IS NOT NULL) AS con_registro,
                        COUNT(*) FILTER (WHERE fecha_operacion IS NOT NULL) AS con_operacion
                    FROM comunidades.base
                    WHERE implementado = 'Si'
                """)
                fechas_row = cur.fetchone()

                # Desglose por departamento × zona
                cur.execute(f"""
                    SELECT
                        departamento,
                        COALESCE(NULLIF(TRIM(zona_sin_zni_mixto),''),'Sin clasificar') AS zona,
                        COUNT(*)                                                        AS count,
                        SUM(capacidad_de_generacion_kwp)                               AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0))                             AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND departamento IS NOT NULL
                    GROUP BY departamento, zona_sin_zni_mixto
                    ORDER BY departamento, zona
                """)
                zona_rows = cur.fetchall()

                # Puntos individuales con coordenadas (expandido con nuevos campos)
                cur.execute(f"""
                    SELECT
                        nombre_de_la_organizacion AS nombre,
                        municipio,
                        departamento              AS dept,
                        latitud                   AS lat,
                        longitud                  AS lng,
                        COALESCE(NULLIF(TRIM(zona_sin_zni_mixto),''),'Sin clasificar') AS zona,
                        CAST(capacidad_de_generacion_kwp AS text)                     AS capacidad,
                        estado_actual,
                        tipo_ce,
                        fuentes_energia,
                        etnia,
                        ejecutor,
                        {_inv_numeric()}                                               AS inversion_estimada_num
                    FROM comunidades.base
                    WHERE implementado = 'Si'
                      AND {_COORD_WHERE}
                    ORDER BY departamento, municipio
                """)
                puntos_rows = cur.fetchall()

                # Municipios por departamento
                cur.execute(f"""
                    SELECT
                        departamento,
                        municipio,
                        COUNT(*)                                                        AS count,
                        SUM(capacidad_de_generacion_kwp)                               AS capacidad,
                        SUM(COALESCE({_inv_numeric()}, 0))                             AS inversion
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND municipio IS NOT NULL
                    GROUP BY departamento, municipio
                    ORDER BY departamento, count DESC
                """)
                muni_rows = cur.fetchall()

                # Promedios por departamento
                cur.execute(f"""
                    SELECT
                        departamento,
                        AVG(capacidad_de_generacion_kwp)  AS avg_capacidad,
                        AVG(usuarios_equivalentes)         AS avg_usuarios,
                        AVG(beneficiarios_equivalentes)    AS avg_beneficiarios,
                        AVG({_inv_numeric()})              AS avg_inversion,
                        SUM(usuarios_equivalentes)         AS sum_usuarios,
                        SUM(beneficiarios_equivalentes)    AS sum_beneficiarios
                    FROM comunidades.base
                    WHERE implementado = 'Si' AND departamento IS NOT NULL
                    GROUP BY departamento
                """)
                dept_avg_rows = cur.fetchall()

                cur.execute("SELECT MAX(fecha_carga) FROM comunidades.base")
                ts_cem = cur.fetchone()[0]

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

        # puntos (expandido con nuevos campos)
        puntos = [
            {
                "nombre":            r[0] or "",
                "municipio":         r[1] or "",
                "departamentoGeo":   _to_geo_id(r[2]),
                "zona":              r[5],
                "lat":               _coord(r[3]),
                "lng":               _coord(r[4]),
                "capacidad":         _coord(r[6]),
                "estado_actual":     r[7] or "",
                "tipo_ce":           r[8] or "",
                "fuentes_energia":   r[9] or "",
                "etnia":             r[10] or "",
                "ejecutor":          r[11] or "",
                "inversion_estimada": _f(r[12]),
            }
            for r in puntos_rows
            if _coord(r[3]) is not None and _coord(r[4]) is not None
        ]

        # por_estado
        por_estado = [
            {
                "estado":    r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in estado_rows
        ]

        # por_tipo_ce
        por_tipo_ce = [
            {
                "tipo":      r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in tipo_ce_rows
        ]

        # por_fuente_energia
        por_fuente_energia = [
            {
                "fuente":    r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in fuente_rows
        ]

        # por_zona
        por_zona = [
            {
                "zona":      r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in zona_flat_rows
        ]

        # por_etnia
        por_etnia = [
            {
                "etnia":     r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in etnia_rows
        ]

        # por_ejecutor
        por_ejecutor = [
            {
                "ejecutor":  r[0],
                "count":     int(r[1]),
                "capacidad": _f(r[2]) or 0.0,
                "inversion": _f(r[3]) or 0.0,
            }
            for r in ejecutor_rows
        ]

        # stats_fechas
        stats_fechas = {
            "min_registro":  fechas_row[0].strftime("%Y-%m-%d") if fechas_row[0] else None,
            "max_registro":  fechas_row[1].strftime("%Y-%m-%d") if fechas_row[1] else None,
            "min_operacion": fechas_row[2].strftime("%Y-%m-%d") if fechas_row[2] else None,
            "max_operacion": fechas_row[3].strftime("%Y-%m-%d") if fechas_row[3] else None,
            "con_registro":  int(fechas_row[4]),
            "con_operacion": int(fechas_row[5]),
        }

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
            "implementadas":         int(k[0]),
            "inversionEstimada":     _f(k[1]) or 0.0,
            "capacidadKwp":          _f(k[3]) or 0.0,
            "usuariosEquiv":         _f(k[5]) or 0.0,
            "beneficiariosEquiv":    _f(k[7]) or 0.0,
            "avgCapacidad":          _f(k[4]),
            "avgUsuarios":           _f(k[6]),
            "avgBeneficiarios":      _f(k[8]),
            "avgInversion":          _f(k[2]),
            "porDepartamento":       por_departamento,
            "detalleZona":           detalle_zona,
            "porEstado":             por_estado,
            "porTipoCE":             por_tipo_ce,
            "porFuenteEnergia":      por_fuente_energia,
            "porZona":               por_zona,
            "porEtnia":              por_etnia,
            "porEjecutor":           por_ejecutor,
            "statsFechas":           stats_fechas,
            "puntos":                puntos,
            "porMunicipio":          por_municipio,
            "deptAvgs":              dept_avgs,
            "ultima_actualizacion":  ts_cem.strftime("%d/%m/%Y, %H:%M") if ts_cem else None,
        })
    except Exception as e:
        logger.error("[comunidades/mapa] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener comunidades")
