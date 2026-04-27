"""
Endpoint energia dashboard — Portal Dirección EE
GET /v1/energia/dashboard → 25+ métricas XM consolidadas (sector_energetico.metrics + cu_daily)
"""

import logging
from datetime import date, timedelta
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

_COLORES_TIPO: dict[str, str] = {
    "HIDRAULICA": "#3B82F6",
    "TERMICA":    "#EF4444",
    "SOLAR":      "#F59E0B",
    "EOLICA":     "#10B981",
    "COGENERADOR":"#8B5CF6",
}

# Factor CU usuario final hasta integrar cu_tarifas_or
_FACTOR_UF = 1.42


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _round(v, n=2) -> float | None:
    return round(float(v), n) if v is not None else None


@router.get("/dashboard", summary="Dashboard energía — métricas XM consolidadas")
@limiter.limit("60/minute")
async def get_energia_dashboard(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # ── 1. Valores Sistema — CTE para últimas fechas por métrica (sin subquery correlacionada) ──
                cur.execute("""
                    WITH lf AS (
                        SELECT metrica, MAX(fecha) AS fecha
                        FROM sector_energetico.metrics
                        WHERE entidad='Sistema' AND recurso='Sistema'
                          AND metrica IN (
                            'Gene','DemaSIN','DemaReal','DemaCome',
                            'PPPrecBolsNaci','PorcVoluUtilDiar','CapaUtilDiarEner','VoluUtilDiarEner',
                            'AporEner','AporEnerMediHist','ExpoEner','ImpoEner',
                            'PrecEsca','VertEner','PerdidasEner','PerdidasEnerReg','PerdidasEnerNoReg'
                          )
                        GROUP BY metrica
                    )
                    SELECT m.metrica,
                           CASE WHEN m.metrica IN ('Gene','DemaSIN','DemaReal','DemaCome',
                                'ExpoEner','ImpoEner','VertEner','PerdidasEner',
                                'PerdidasEnerReg','PerdidasEnerNoReg','AporEner','AporEnerMediHist')
                                THEN SUM(m.valor_gwh)
                                ELSE AVG(m.valor_gwh) END AS valor,
                           lf.fecha
                    FROM sector_energetico.metrics m
                    JOIN lf ON m.metrica = lf.metrica AND m.fecha = lf.fecha
                    WHERE m.entidad='Sistema' AND m.recurso='Sistema'
                    GROUP BY m.metrica, lf.fecha
                """)
                vals: dict[str, float | None] = {}
                fecha_ref: date | None = None
                for row in cur.fetchall():
                    vals[row[0]] = _f(row[1])
                    if row[0] == "Gene":
                        fecha_ref = row[2]

                # Fix Gene si valor es < 100 GWh (dato parcial XM) — buscar día anterior
                if vals.get("Gene") is not None and vals["Gene"] < 100:
                    cur.execute("""
                        SELECT fecha, valor_gwh FROM sector_energetico.metrics
                        WHERE metrica='Gene' AND entidad='Sistema' AND recurso='Sistema'
                          AND fecha < %s
                        ORDER BY fecha DESC LIMIT 5
                    """, [fecha_ref])
                    for back_row in cur.fetchall():
                        if back_row[1] and float(back_row[1]) >= 100:
                            vals["Gene"] = float(back_row[1])
                            fecha_ref = back_row[0]
                            break

                # ── 2. Capacidad instalada y emisiones — CTE para últimas fechas por (metrica, entidad) ──
                cur.execute("""
                    WITH lf2 AS (
                        SELECT metrica, entidad, MAX(fecha) AS fecha
                        FROM sector_energetico.metrics
                        WHERE (metrica='CapEfecNeta'   AND entidad='Recurso')
                           OR (metrica IN ('EmisionesCO2','EmisionesCH4','EmisionesN2O') AND entidad='RecursoComb')
                           OR (metrica='EmisionesCO2Eq' AND entidad='Recurso')
                        GROUP BY metrica, entidad
                    )
                    SELECT m.metrica, SUM(m.valor_gwh) AS valor
                    FROM sector_energetico.metrics m
                    JOIN lf2 ON m.metrica = lf2.metrica AND m.entidad = lf2.entidad AND m.fecha = lf2.fecha
                    GROUP BY m.metrica
                """)
                for row in cur.fetchall():
                    vals[row[0]] = _f(row[1])

                # CapEfecNeta viene en kW → dividir por 1000 para MW
                if vals.get("CapEfecNeta") is not None:
                    vals["CapEfecNeta"] = vals["CapEfecNeta"] / 1000

                # ── 4. Generación por tipo (últimos 7 días desde fecha_ref) ──
                cur.execute("""
                    WITH generacion_recursos AS (
                        SELECT c.tipo, SUM(m.valor_gwh) AS total_gwh
                        FROM sector_energetico.metrics m
                        JOIN sector_energetico.catalogos c
                          ON m.recurso = c.codigo AND c.catalogo = 'ListadoRecursos'
                        WHERE m.metrica = 'Gene'
                          AND m.fecha BETWEEN %s::date - INTERVAL '7 days' AND %s::date
                          AND c.tipo IS NOT NULL
                        GROUP BY c.tipo
                    ),
                    total AS (SELECT SUM(total_gwh) AS suma FROM generacion_recursos)
                    SELECT tipo,
                           ROUND(total_gwh::numeric, 2) AS generacion_gwh,
                           ROUND((total_gwh / NULLIF((SELECT suma FROM total), 0) * 100)::numeric, 1) AS porcentaje
                    FROM generacion_recursos ORDER BY total_gwh DESC
                """, [fecha_ref, fecha_ref])
                gen_por_tipo = cur.fetchall()

                # ── 5. Histórico precios de bolsa (desde inicio de mes) ──
                cur.execute("""
                    SELECT fecha, ROUND(valor_gwh::numeric, 2) AS precio
                    FROM sector_energetico.metrics
                    WHERE metrica='PPPrecBolsNaci' AND entidad='Sistema' AND recurso='Sistema'
                      AND fecha >= DATE_TRUNC('month', CURRENT_DATE) AND fecha <= CURRENT_DATE
                    ORDER BY fecha ASC
                """)
                precio_historico = cur.fetchall()

                # ── 6. Embalses individuales ──
                cur.execute("""
                    SELECT MAX(fecha) AS fecha FROM sector_energetico.metrics
                    WHERE metrica='PorcVoluUtilDiar' AND entidad='Embalse'
                """)
                fecha_embalses_ind = (cur.fetchone() or [None])[0]

                cur.execute("""
                    SELECT m.recurso AS codigo,
                           COALESCE(c.nombre, m.recurso) AS nombre,
                           ROUND((m.valor_gwh * 100)::numeric, 1) AS porcentaje,
                           ROUND(COALESCE(cap.valor_gwh, 0)::numeric, 2) AS "capacidadGwh"
                    FROM sector_energetico.metrics m
                    LEFT JOIN sector_energetico.catalogos c
                      ON m.recurso = c.codigo AND c.catalogo = 'ListadoEmbalses'
                    LEFT JOIN sector_energetico.metrics cap
                      ON cap.recurso = m.recurso
                     AND cap.metrica = 'CapaUtilDiarEner' AND cap.entidad = 'Embalse'
                     AND cap.fecha = (
                         SELECT MAX(f3.fecha) FROM sector_energetico.metrics f3
                         WHERE f3.metrica='CapaUtilDiarEner' AND f3.entidad='Embalse'
                     )
                    WHERE m.metrica='PorcVoluUtilDiar' AND m.entidad='Embalse'
                      AND m.fecha = %s
                    ORDER BY m.valor_gwh DESC
                """, [fecha_embalses_ind])
                embalses_det = cur.fetchall()

                # ── 7. Demanda histórica (últimos 30 días) ──
                fecha_dema_hist = vals.get("DemaSIN") and fecha_ref
                cur.execute("""
                    SELECT fecha, metrica, valor_gwh AS valor
                    FROM sector_energetico.metrics
                    WHERE entidad='Sistema' AND recurso='Sistema'
                      AND metrica IN ('DemaSIN','DemaReal','DemaCome')
                      AND fecha >= %s::date - INTERVAL '30 days' AND fecha <= %s
                    ORDER BY fecha ASC, metrica
                """, [fecha_ref, fecha_ref])
                dema_hist = cur.fetchall()

                # ── 8. Aportes por río (Top 15) ──
                cur.execute("""
                    SELECT MAX(fecha) AS fecha FROM sector_energetico.metrics
                    WHERE metrica='AporEner' AND entidad='Rio'
                """)
                fecha_rio = (cur.fetchone() or [None])[0]

                cur.execute("""
                    WITH actual AS (
                        SELECT recurso, valor_gwh FROM sector_energetico.metrics
                        WHERE metrica='AporEner' AND entidad='Rio' AND fecha=%s
                    ),
                    historico AS (
                        SELECT recurso, valor_gwh FROM sector_energetico.metrics
                        WHERE metrica='AporEnerMediHist' AND entidad='Rio' AND fecha=%s
                    ),
                    porc AS (
                        SELECT recurso, valor_gwh FROM sector_energetico.metrics
                        WHERE metrica='PorcApor' AND entidad='Rio' AND fecha=%s
                    )
                    SELECT a.recurso AS codigo,
                           COALESCE(c.nombre, a.recurso) AS nombre,
                           ROUND(a.valor_gwh::numeric, 2) AS "actualGwh",
                           ROUND(COALESCE(h.valor_gwh, 0)::numeric, 2) AS "historicoGwh",
                           ROUND(COALESCE(p.valor_gwh * 100, 0)::numeric, 1) AS porcentaje
                    FROM actual a
                    LEFT JOIN historico h ON a.recurso = h.recurso
                    LEFT JOIN porc p ON a.recurso = p.recurso
                    LEFT JOIN sector_energetico.catalogos c
                      ON a.recurso = c.codigo AND c.catalogo = 'ListadoRios'
                    ORDER BY a.valor_gwh DESC LIMIT 15
                """, [fecha_rio, fecha_rio, fecha_rio])
                rios = cur.fetchall()

                # ── 9. CU más reciente ──
                cur.execute("""
                    SELECT fecha, cu_total,
                           componente_g, componente_t, componente_d,
                           componente_c, componente_p, componente_r
                    FROM sector_energetico.cu_daily
                    ORDER BY fecha DESC LIMIT 1
                """)
                cu_row = cur.fetchone()

        # ── Construir series de demanda ──
        fechas_set = sorted(set(r[0] for r in dema_hist))
        dema_series: dict[str, list] = {"sin": [], "real": [], "comercial": []}
        for i, f in enumerate(fechas_set):
            for r in dema_hist:
                if r[0] == f:
                    point = {"x": str(i + 1), "y": round(float(r[2]), 2), "fecha": str(f)}
                    if r[1] == "DemaSIN":
                        dema_series["sin"].append(point)
                    elif r[1] == "DemaReal":
                        dema_series["real"].append(point)
                    elif r[1] == "DemaCome":
                        dema_series["comercial"].append(point)

        pct_emb_raw = vals.get("PorcVoluUtilDiar")
        pct_emb = round(float(pct_emb_raw) * 100, 1) if pct_emb_raw else None

        cu_data = None
        if cu_row:
            cu_data = {
                "fecha": str(cu_row[0]),
                "mayoristaLac": _round(cu_row[1], 2),
                "usuarioFinal": _round(float(cu_row[1]) * _FACTOR_UF, 2) if cu_row[1] else None,
                "componentes": {
                    "g": _round(cu_row[2], 4),
                    "t": _round(cu_row[3], 4),
                    "d": _round(cu_row[4], 4),
                    "c": _round(cu_row[5], 4),
                    "p": _round(cu_row[6], 4),
                    "r": _round(cu_row[7], 4) if cu_row[7] is not None else None,
                },
            }

        return JSONResponse({
            "fecha": str(fecha_ref) if fecha_ref else None,
            "generacion": {
                "gwh": _round(vals.get("Gene"), 2),
                "porFuente": [
                    {
                        "id":            r[0],
                        "label":         r[0][0] + r[0][1:].lower(),
                        "value":         float(r[2]),
                        "color":         _COLORES_TIPO.get(r[0], "#6B7280"),
                        "generacionGwh": float(r[1]),
                    }
                    for r in gen_por_tipo
                ],
            },
            "demanda": {
                "sin":       _round(vals.get("DemaSIN"), 2),
                "real":      _round(vals.get("DemaReal"), 2),
                "comercial": _round(vals.get("DemaCome"), 2),
            },
            "precioBolsa": {
                "actual": _round(vals.get("PPPrecBolsNaci"), 2),
                "historico": [{
                    "id": "COP/kWh",
                    "color": "#F59E0B",
                    "data": [
                        {"x": str(i + 1), "y": float(r[1]), "fecha": str(r[0])}
                        for i, r in enumerate(precio_historico)
                    ],
                }],
            },
            "embalses": {
                "promedioNacional":      pct_emb,
                "capacidadUtilTotalGwh": _round(vals.get("CapaUtilDiarEner"), 2),
                "volumenUtilTotalGwh":   _round(vals.get("VoluUtilDiarEner"), 2),
                "detalle": [
                    {
                        "codigo":       r[0],
                        "nombre":       r[1],
                        "porcentaje":   float(r[2]),
                        "capacidadGwh": float(r[3]),
                    }
                    for r in embalses_det
                ],
            },
            "aportes": {
                "actualGwh":    _round(vals.get("AporEner"), 2),
                "historicoGwh": _round(vals.get("AporEnerMediHist"), 2),
            },
            "aportesRios": [
                {
                    "codigo":      r[0],
                    "nombre":      r[1],
                    "actualGwh":   float(r[2]),
                    "historicoGwh": float(r[3]),
                    "porcentaje":  float(r[4]),
                }
                for r in rios
            ],
            "capacidadInstaladaMw": _round(vals.get("CapEfecNeta"), 2),
            "emisiones": {
                "co2Ton":   _round(vals.get("EmisionesCO2"), 2),
                "co2EqTon": _round(vals.get("EmisionesCO2Eq"), 2),
                "ch4Ton":   _round(vals.get("EmisionesCH4"), 2),
                "n2oTon":   _round(vals.get("EmisionesN2O"), 2),
            },
            "comercio": {
                "exportacionesGwh": _round(vals.get("ExpoEner"), 2),
                "importacionesGwh": _round(vals.get("ImpoEner"), 2),
                "vertimientoGwh":   _round(vals.get("VertEner"), 2),
                "precioEscasez":    _round(vals.get("PrecEsca"), 2),
            },
            "perdidas": {
                "energiaGwh":      _round(vals.get("PerdidasEner"), 2),
                "reguladasGwh":    _round(vals.get("PerdidasEnerReg"), 2),
                "noReguladasGwh":  _round(vals.get("PerdidasEnerNoReg"), 2),
            },
            "demandaHistorica": [
                {"id": "Dema SIN",       "color": "#3B82F6", "data": dema_series["sin"]},
                {"id": "Dema Real",      "color": "#10B981", "data": dema_series["real"]},
                {"id": "Dema Comercial", "color": "#F59E0B", "data": dema_series["comercial"]},
            ],
            "cu": cu_data,
        })
    except Exception as e:
        logger.error("[energia/dashboard] %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al obtener dashboard energía")
