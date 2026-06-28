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

# Centroides de departamentos (calculados del GeoJSON)
# Usados cuando una CE no tiene coordenadas geográficas
_DEPT_CENTROID: dict[str, tuple[float, float]] = {
    "AMAZONAS":                                               (-1.4426, -71.7341),
    "ANTIOQUIA":                                              (6.9998, -75.8351),
    "ARAUCA":                                                 (6.4797, -71.1813),
    "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA": (12.5493, -81.7191),
    "ATLANTICO":                                              (10.6765, -74.9739),
    "BOLIVAR":                                                (9.1230, -74.7633),
    "BOYACA":                                                 (5.8476, -73.2957),
    "CALDAS":                                                 (5.3503, -75.3816),
    "CAQUETA":                                                (0.6652, -73.8092),
    "CASANARE":                                               (5.4443, -71.7390),
    "CAUCA":                                                  (2.3141, -76.8181),
    "CESAR":                                                  (9.2880, -73.5241),
    "CHOCO":                                                  (6.0140, -77.0042),
    "CORDOBA":                                                (8.5294, -75.6963),
    "CUNDINAMARCA":                                           (4.7540, -74.1737),
    "GUAINIA":                                                (2.8304, -68.8610),
    "GUAVIARE":                                               (1.9134, -71.8686),
    "HUILA":                                                  (2.6641, -75.6033),
    "LA GUAJIRA":                                             (11.4495, -72.4951),
    "MAGDALENA":                                              (10.1873, -74.2653),
    "META":                                                   (3.2160, -73.1139),
    "NARIÑO":                                                 (1.5721, -77.8219),
    "NORTE DE SANTANDER":                                     (7.8691, -72.9493),
    "PUTUMAYO":                                               (0.3368, -75.6166),
    "QUINDIO":                                                (4.4965, -75.7020),
    "RISARALDA":                                              (5.0596, -75.8931),
    "SANTAFE DE BOGOTA D.C":                                  (4.2840, -74.2118),
    "SANTANDER":                                              (6.6089, -73.4278),
    "SUCRE":                                                  (9.1335, -75.2053),
    "TOLIMA":                                                 (4.0742, -75.2126),
    "VALLE DEL CAUCA":                                        (3.9789, -76.5671),
    "VAUPES":                                                 (0.3193, -70.5730),
    "VICHADA":                                                (4.2500, -69.2627),
}

FASE_LABELS = {"1_0": "Fenoge 1.0", "1_1": "Fenoge 1.1", "CE": "CE"}


def _to_geo_id(dept: str) -> str:
    key = dept.lower().replace(" ", "_")
    return _DEPT_MAP.get(key, dept.upper().replace("_", " "))


def _f(v):
    return float(v) if v is not None else None


def _coord(v) -> float | None:
    try:
        f = float(v) if v and str(v).strip() not in ("", "-", "N/A") else None
    except (ValueError, TypeError):
        return None
    if f is None:
        return None
    # Los datos pueden venir con la coma decimal del formato español
    # eliminada:  "6,70418" → 670418 .  Detectamos valores fuera del
    # rango colombiano y corregimos:
    #   lat  → 1 dígito entero (ej. 670418  → 6.70418)
    #   lng  → 2 dígitos enteros (ej. 71047444 → 71.047444)
    if f > 15:
        # Mangled latitud (Colombia siempre lat > 0 y < ~13)
        s = str(abs(int(f)))
        if len(s) >= 2:
            f = float(f"{s[:1]}.{s[1:]}")
    elif f < -66:
        # Mangled longitud (Colombia siempre lng < 0 y entre -82 y -66)
        s = str(abs(int(f)))
        if len(s) >= 3:
            f = -float(f"{s[:2]}.{s[2:]}")
    return f


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

                # Puntos individuales — todos los CEs, con coordenadas si existen,
                # o centroide del departamento como fallback
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

                cur.execute("SELECT MAX(fecha_carga) FROM fenoge.comunidades")
                ts_fen = cur.fetchone()[0]

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

        # puntos — con fallback a centroide del departamento si falta coordenada
        puntos = []
        for r in puntos_rows:
            lat = _coord(r[3])
            lng = _coord(r[4])
            dept_geo = _to_geo_id(r[2])
            # Si no tiene coordenadas válidas, usar centroide del departamento
            if lat is None or lng is None:
                centroide = _DEPT_CENTROID.get(dept_geo)
                if centroide:
                    lat, lng = centroide
            if lat is not None and lng is not None:
                puntos.append({
                    "nombre":          r[0] or "",
                    "municipio":       r[1] or "",
                    "departamentoGeo": dept_geo,
                    "fase":            r[5],
                    "lat":             lat,
                    "lng":             lng,
                    "capacidad":       _coord(r[6]),
                })

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
            "ultima_actualizacion": ts_fen.strftime("%d/%m/%Y, %H:%M") if ts_fen else None,
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


# Último mes visible en la curva S (evita meses futuros sin datos reales)
SEGUIMIENTO_FECHA_CORTE = "2026-08-01"


# ─── /seguimiento ─────────────────────────────────────────────────────────────
@router.get("/seguimiento", summary="Avance de obra Fenoge para gráfica de líneas")
@limiter.limit("60/minute")
async def get_fenoge_seguimiento(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:

                # Catálogos para filtros — solo entidades con al menos un valor de avance
                cur.execute("""
                    SELECT DISTINCT region FROM fenoge.seguimiento
                    WHERE region IS NOT NULL
                      AND (avance_real_acumulado_pct IS NOT NULL
                           OR avance_programado_acumulado_pct IS NOT NULL)
                    ORDER BY region
                """)
                regiones = [r[0] for r in cur.fetchall()]

                cur.execute("""
                    SELECT DISTINCT numero_contrato FROM fenoge.seguimiento
                    WHERE numero_contrato IS NOT NULL
                      AND (avance_real_acumulado_pct IS NOT NULL
                           OR avance_programado_acumulado_pct IS NOT NULL)
                    ORDER BY numero_contrato
                """)
                contratos = [r[0] for r in cur.fetchall()]

                cur.execute("""
                    SELECT DISTINCT nombre_comunidad FROM fenoge.seguimiento
                    WHERE nombre_comunidad IS NOT NULL AND nombre_comunidad <> ''
                      AND (avance_real_acumulado_pct IS NOT NULL
                           OR avance_programado_acumulado_pct IS NOT NULL)
                    ORDER BY nombre_comunidad
                """)
                comunidades = [r[0] for r in cur.fetchall()]

                # Datos completos ordenados por fecha y contrato (hasta agosto 2026)
                cur.execute("""
                    SELECT MAX(fecha_carga) FROM fenoge.seguimiento
                """)
                ts_seg = cur.fetchone()[0]

                cur.execute("""
                    SELECT
                        s.region,
                        s.numero_contrato,
                        s.nombre_comunidad,
                        s.dia_actualizacion,
                        s.avance_real_acumulado_pct,
                        s.avance_programado_acumulado_pct,
                        c.beneficiarios,
                        c.kwp
                    FROM fenoge.seguimiento s
                    LEFT JOIN fenoge.comunidades c
                      ON c.comunidad = s.nombre_comunidad
                    WHERE s.dia_actualizacion IS NOT NULL
                      AND s.dia_actualizacion <= %s
                    ORDER BY s.region, s.numero_contrato, s.nombre_comunidad, s.dia_actualizacion
                """, (SEGUIMIENTO_FECHA_CORTE,))
                rows = cur.fetchall()

        # Agrupar por contrato para generar series de líneas
        # Retornamos los datos planos + catálogos; el frontend agrupa
        data = [
            {
                "region":         r[0],
                "contrato":       r[1],
                "comunidad":      r[2] or "",
                "fecha":          r[3].isoformat() if r[3] else None,
                "realAcum":       float(r[4]) * 100 if r[4] is not None else None,
                "programadoAcum": float(r[5]) * 100 if r[5] is not None else None,
                "usuarios":       int(r[6]) if r[6] is not None else 0,
                "potencia":       float(r[7]) if r[7] is not None else 0.0,
            }
            for r in rows
        ]

        return JSONResponse({
            "ultima_actualizacion": ts_seg.strftime("%d/%m/%Y, %H:%M") if ts_seg else None,
            "regiones":    regiones,
            "contratos":   contratos,
            "comunidades": comunidades,
            "fechaCorte":  SEGUIMIENTO_FECHA_CORTE,
            "data":        data,
        })

    except Exception as e:
        logger.error("[fenoge/seguimiento] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener seguimiento Fenoge")
