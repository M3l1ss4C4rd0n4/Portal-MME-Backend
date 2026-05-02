"""
Endpoint sector snapshot — Portal Dirección EE
GET /v1/sector/snapshot → métricas clave del SIN (sector_energetico.metrics)
"""

import logging
from datetime import datetime
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

_LOCALE_MESES = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]


def _fmt_fecha(d) -> str | None:
    if d is None:
        return None
    if not isinstance(d, datetime):
        d = datetime.combine(d, datetime.min.time())
    return f"{d.day} {_LOCALE_MESES[d.month - 1]} {d.year}"


def _fmt_fecha_hora(d) -> str | None:
    if d is None:
        return None
    if not isinstance(d, datetime):
        d = datetime.combine(d, datetime.min.time())
    return f"{d.day} {_LOCALE_MESES[d.month - 1]} {d.year}, {d.hour:02d}:{d.minute:02d}"


@router.get("/snapshot", summary="Snapshot de métricas clave del SIN")
@limiter.limit("120/minute")
async def get_sector_snapshot(request: Request, api_key: str = Depends(get_api_key)):
    try:
        with _cm.get_connection() as conn:
            with conn.cursor() as cur:
                # Últimas fechas de cada métrica
                cur.execute("""
                    SELECT
                        MAX(CASE WHEN metrica='Gene'             AND entidad='Sistema' AND recurso='Sistema' THEN fecha END) AS fecha_gene,
                        MAX(CASE WHEN metrica='PPPrecBolsNaci'   AND entidad='Sistema' AND recurso='Sistema' THEN fecha END) AS fecha_precio,
                        MAX(CASE WHEN metrica='PorcVoluUtilDiar' AND entidad='Sistema' AND recurso='Sistema' THEN fecha END) AS fecha_embalse,
                        MAX(CASE WHEN metrica='AporEner'         AND entidad='Sistema' AND recurso='Sistema' THEN fecha END) AS fecha_aportes,
                        MAX(fecha) AS ultima_actualizacion,
                        MAX(fecha_actualizacion) AS ultima_ejecucion_etl
                    FROM sector_energetico.metrics
                    WHERE metrica IN ('Gene','PPPrecBolsNaci','PorcVoluUtilDiar','AporEner')
                      AND entidad = 'Sistema' AND recurso = 'Sistema'
                """)
                r = cur.fetchone()
                fecha_gene, fecha_precio, fecha_embalse, fecha_aportes, ultima, ultima_etl = r

                # Valores de cada métrica en su última fecha
                cur.execute("""
                    SELECT
                        SUM(CASE WHEN metrica='Gene'             AND fecha=%s THEN valor_gwh END) AS generacion,
                        AVG(CASE WHEN metrica='PPPrecBolsNaci'   AND fecha=%s THEN valor_gwh END) AS precio_bolsa,
                        AVG(CASE WHEN metrica='PorcVoluUtilDiar' AND fecha=%s THEN valor_gwh END) AS pct_embalse,
                        AVG(CASE WHEN metrica='AporEner'         AND fecha=%s THEN valor_gwh END) AS aportes,
                        AVG(CASE WHEN metrica='AporEnerMediHist' AND fecha=%s THEN valor_gwh END) AS aportes_hist
                    FROM sector_energetico.metrics
                    WHERE entidad='Sistema' AND recurso='Sistema'
                      AND metrica IN ('Gene','PPPrecBolsNaci','PorcVoluUtilDiar','AporEner','AporEnerMediHist')
                      AND fecha IN (%s, %s, %s, %s)
                """, [
                    fecha_gene, fecha_precio, fecha_embalse, fecha_aportes, fecha_aportes,
                    fecha_gene, fecha_precio, fecha_embalse, fecha_aportes,
                ])
                v = cur.fetchone()

                generacion  = float(v[0] or 0)
                precio      = float(v[1] or 0)
                pct_emb_raw = float(v[2] or 0)
                aportes     = float(v[3] or 0)
                aportes_h   = float(v[4] or 0)

                # ── Validación anti-datos-parciales ──────────────────────────
                # XM publica datos de forma incremental durante el día.
                # Si el ETL corre de madrugada, los valores del día corriente
                # pueden ser preliminares/incompletos (unas pocas horas).
                # Regla: si PorcVoluUtilDiar cae > 80% respecto al día anterior,
                # o si AporEner es < 15% de la media histórica → usar día anterior.

                # Fallback PorcVoluUtilDiar
                if pct_emb_raw < 0.20:  # < 20% → sospechoso
                    cur.execute("""
                        SELECT valor_gwh, fecha FROM sector_energetico.metrics
                        WHERE metrica='PorcVoluUtilDiar'
                          AND entidad='Sistema' AND recurso='Sistema'
                          AND fecha < %s AND valor_gwh >= 0.40
                        ORDER BY fecha DESC LIMIT 1
                    """, [fecha_embalse])
                    fb = cur.fetchone()
                    if fb:
                        logger.warning(
                            "PorcVoluUtilDiar parcial detectado (%.4f → %.4f, fecha %s). "
                            "Usando fallback: %.4f del %s",
                            pct_emb_raw, fb[0], fecha_embalse, fb[0], fb[1]
                        )
                        pct_emb_raw  = float(fb[0])
                        fecha_embalse = fb[1]

                # Fallback AporEner (< 15% de la media histórica diaria = dato de pocas horas)
                if aportes_h > 0 and aportes < aportes_h * 0.15:
                    cur.execute("""
                        SELECT m.valor_gwh, m.fecha FROM sector_energetico.metrics m
                        WHERE m.metrica='AporEner'
                          AND m.entidad='Sistema' AND m.recurso='Sistema'
                          AND m.fecha < %s AND m.valor_gwh >= %s * 0.30
                        ORDER BY m.fecha DESC LIMIT 1
                    """, [fecha_aportes, aportes_h])
                    fb = cur.fetchone()
                    if fb:
                        logger.warning(
                            "AporEner parcial detectado (%.2f GWh, fecha %s). "
                            "Usando fallback: %.2f GWh del %s",
                            aportes, fecha_aportes, fb[0], fb[1]
                        )
                        aportes      = float(fb[0])
                        fecha_aportes = fb[1]

                # Acumulado mensual (metodología oficial XM): suma desde el 1° del mes
                # hasta fecha_aportes — igual que Portal Energético y XM
                cur.execute("""
                    SELECT
                        SUM(CASE WHEN metrica='AporEner'         THEN valor_gwh END) AS aportes_mtd,
                        SUM(CASE WHEN metrica='AporEnerMediHist' THEN valor_gwh END) AS hist_mtd
                    FROM sector_energetico.metrics
                    WHERE entidad='Sistema' AND recurso='Sistema'
                      AND metrica IN ('AporEner','AporEnerMediHist')
                      AND fecha >= date_trunc('month', %s::date)
                      AND fecha <= %s
                """, [fecha_aportes, fecha_aportes])
                row_mtd = cur.fetchone()
                aportes_mtd = float(row_mtd[0]) if row_mtd and row_mtd[0] else None
                hist_mtd    = float(row_mtd[1]) if row_mtd and row_mtd[1] else None

                # Volumen útil total en GWh (suma de todos los embalses)
                cur.execute("""
                    SELECT SUM(valor_gwh)
                    FROM sector_energetico.metrics
                    WHERE metrica='VoluUtilDiarEner'
                      AND entidad='Embalse'
                      AND recurso != '_SISTEMA_'
                      AND fecha = %s
                """, [fecha_embalse])
                row_vol = cur.fetchone()
                embalse_gwh = float(row_vol[0]) if row_vol and row_vol[0] else None

                # ── Tendencias 7 días (momentum) ──────────────────────────
                # Compara valor actual vs promedio de los 7 días anteriores.
                # Umbrales aprobados: embalses ±1pp, precio/generación/aportes ±5%
                cur.execute("""
                    SELECT
                        AVG(CASE WHEN metrica='Gene'             THEN valor_gwh END) AS gene_7d,
                        AVG(CASE WHEN metrica='PPPrecBolsNaci'   THEN valor_gwh END) AS precio_7d,
                        AVG(CASE WHEN metrica='PorcVoluUtilDiar' THEN valor_gwh END) AS emb_7d,
                        AVG(CASE WHEN metrica='AporEner'         THEN valor_gwh END) AS apor_7d,
                        AVG(CASE WHEN metrica='AporEnerMediHist' THEN valor_gwh END) AS apor_hist_7d
                    FROM sector_energetico.metrics
                    WHERE entidad='Sistema' AND recurso='Sistema'
                      AND metrica IN ('Gene','PPPrecBolsNaci','PorcVoluUtilDiar','AporEner','AporEnerMediHist')
                      AND fecha >= %s::date - INTERVAL '7 days'
                      AND fecha < %s::date
                """, [fecha_gene, fecha_gene])
                t7 = cur.fetchone()
                gene_7d     = float(t7[0]) if t7 and t7[0] else None
                precio_7d   = float(t7[1]) if t7 and t7[1] else None
                emb_7d_raw  = float(t7[2]) if t7 and t7[2] else None
                apor_7d     = float(t7[3]) if t7 and t7[3] else None
                apor_h_7d   = float(t7[4]) if t7 and t7[4] else None

        # % embalse viene como fracción (0-1) desde la BD
        pct_embalses = round(pct_emb_raw * 100, 2)

        # ── Cálculo de tendencias ─────────────────────────────────────────
        def _tendencia_pct(actual, ref_7d, umbral):
            """Retorna dirección y cambio porcentual relativo vs media 7d."""
            if actual is None or ref_7d is None or ref_7d == 0:
                return {"direccion": "desconocida", "cambio7d": None, "label": "S/D"}
            cambio = ((actual - ref_7d) / abs(ref_7d)) * 100
            if cambio > umbral:
                label = "ALTA"
            elif cambio < -umbral:
                label = "BAJA"
            else:
                label = "ESTABLE"
            return {"direccion": label.lower(), "cambio7d": round(cambio, 1), "label": label}

        def _tendencia_pp(actual_pct, ref_pct_7d, umbral_pp):
            """Tendencia en puntos porcentuales (para embalses y aportes%)."""
            if actual_pct is None or ref_pct_7d is None:
                return {"direccion": "desconocida", "cambio7d": None, "label": "S/D"}
            cambio = actual_pct - ref_pct_7d
            if cambio > umbral_pp:
                label = "ALTA"
            elif cambio < -umbral_pp:
                label = "BAJA"
            else:
                label = "ESTABLE"
            return {"direccion": label.lower(), "cambio7d": round(cambio, 2), "label": label}

        if pct_embalses < 50:
            estado_sin, color_sin = "CRÍTICO", "#EF4444"
        elif pct_embalses < 60:
            estado_sin, color_sin = "ALERTA ALTA", "#F97316"
        elif pct_embalses < 70:
            estado_sin, color_sin = "ALERTA TEMPRANA", "#F59E0B"
        elif pct_embalses < 80:
            estado_sin, color_sin = "ESTABLE", "#06B6D4"
        else:
            estado_sin, color_sin = "NORMAL", "#22C55E"

        # pct mensual (metodología XM): acumulado mes / acumulado histórico
        aportes_pct = round((aportes_mtd / hist_mtd) * 100, 2) \
            if aportes_mtd and hist_mtd and hist_mtd > 0 else None

        # ── Tendencias: variables auxiliares ─────────────────────────────
        emb_7d_pct  = round(emb_7d_raw * 100, 2) if emb_7d_raw else None
        apor_pct_7d = round((apor_7d / apor_h_7d) * 100, 2) \
                      if apor_7d and apor_h_7d and apor_h_7d > 0 else None

        tendencias = {
            "embalses":   _tendencia_pp(pct_embalses,  emb_7d_pct,   1.0),
            "precio":     _tendencia_pct(precio,        precio_7d,    5.0),
            "generacion": _tendencia_pct(generacion,    gene_7d,      5.0),
            "aportes":    _tendencia_pp(aportes_pct,    apor_pct_7d,  5.0),
        }

        # Capacidad útil total del sistema (GWh)
        capacidad_gwh = round(embalse_gwh / pct_emb_raw, 2) \
            if embalse_gwh and pct_emb_raw > 0 else None

        return JSONResponse({
            "generacionGwh":    round(generacion, 2),
            "precioBolsa":      round(precio, 2),
            "pctEmbalses":      pct_embalses,
            "embalseGwh":       round(embalse_gwh, 2) if embalse_gwh else None,
            "capacidadEmbalseGwh": capacidad_gwh,
            "estadoSin":        estado_sin,
            "colorSin":         color_sin,
            "aportesHidricos": {
                "actualGwh":      round(aportes_mtd, 2) if aportes_mtd else round(aportes, 2),
                "historicoGwh":   round(hist_mtd, 2) if hist_mtd else round(aportes_h, 2),
                "pct":            aportes_pct,
                "dailyActualGwh": round(aportes, 2),
                "dailyHistGwh":   round(aportes_h, 2),
            },
            "tendencias":          tendencias,
            "ultimaActualizacion": _fmt_fecha(ultima),
            "ultimaEjecucionETL":  _fmt_fecha_hora(ultima_etl),
            "fechaGeneracion":     _fmt_fecha(fecha_gene),
            "fechaPrecio":         _fmt_fecha(fecha_precio),
            "fechaEmbalse":        _fmt_fecha(fecha_embalse),
            "fechaAportes":        _fmt_fecha(fecha_aportes),
        })
    except Exception as e:
        logger.error("[sector/snapshot] %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener snapshot del sector")
