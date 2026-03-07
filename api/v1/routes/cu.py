"""
Endpoints del Costo Unitario (CU) de energía eléctrica

Proporciona acceso a:
- CU actual (último día calculado)
- CU histórico (serie temporal)
- Desglose de componentes (para gráficos)
- CU forecast — predicción ML con cache Redis (FASE 4)

Autor: Arquitectura Dashboard MME — FASE 2
Actualizado: FASE 4 (forecast endpoint con Redis cache)
"""

import json
import hashlib
import logging
from typing import Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_cu_service
from api.v1.schemas.cu import (
    CUCurrentResponse,
    CUHistoricoResponse,
    CUBreakdownResponse,
    CUDatoResponse,
    CUForecastResponse,
    CUForecastPoint,
)
from api.v1.schemas.common import ErrorResponse
from domain.services.cu_service import CUService

logger = logging.getLogger("cu_forecast")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ─── FASE 4: Redis Cache para /forecast ─────────────────────────────────────
_redis_client = None
CACHE_TTL_FORECAST = 3600  # 1h — predicciones cambian con re-entrenamiento


def _get_redis():
    """Obtener cliente Redis con conexión lazy y fallback graceful."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.Redis(
            host='localhost', port=6379, db=0,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        logger.info("✅ Redis conectado para cache CU forecast")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Redis no disponible — forecast sin cache: {e}")
        _redis_client = None
        return None


def _cache_key_forecast(horizon: int) -> str:
    """Cache key para forecast CU."""
    raw = f"cu_forecast|{horizon}"
    short_hash = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"cu:forecast:{horizon}:{short_hash}"


def _cache_get(key: str) -> Optional[dict]:
    r = _get_redis()
    if r is None:
        return None
    try:
        cached = r.get(key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug("Cache get error: %s", e)
    return None


def _cache_set(key: str, data: dict, ttl: int = CACHE_TTL_FORECAST) -> bool:
    r = _get_redis()
    if r is None:
        return False
    try:
        r.setex(key, ttl, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.debug("Cache set error: %s", e)
        return False


@router.get(
    "/current",
    response_model=CUCurrentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No hay datos de CU disponibles"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"},
    },
    summary="CU actual",
    description="""
    Retorna el Costo Unitario más reciente calculado.
    
    El CU se calcula diariamente a las 10:00 AM UTC-5 
    cuando todos los componentes están disponibles.
    
    **Componentes:**
    - **G**: Generación — precio de bolsa nacional (XM)
    - **T**: Transmisión — cargo CREG fijo
    - **D**: Distribución — cargo CREG fijo
    - **C**: Comercialización — cargo CREG fijo
    - **P**: Pérdidas — STN + distribución
    - **R**: Restricciones — aliviadas + no aliviadas
    
    **Confianza:**
    - `alta`: Todos los componentes XM disponibles
    - `media`: 4+ componentes disponibles
    - `baja`: Solo cargos CREG (sin datos XM)
    """,
)
@limiter.limit("100/minute")
async def get_cu_current(
    request: Request,
    api_key: str = Depends(get_api_key),
    service: CUService = Depends(get_cu_service),
):
    """Obtiene el CU del día más reciente."""
    try:
        cu = service.get_cu_current()
        if cu is None:
            raise HTTPException(
                status_code=404,
                detail="No hay datos de CU disponibles. El backfill puede estar pendiente.",
            )

        return CUCurrentResponse(
            status="ok",
            fecha=cu.get("fecha"),
            cu_total=cu.get("cu_total", 0),
            confianza=cu.get("confianza", "baja"),
            componente_g=cu.get("componente_g"),
            componente_t=cu.get("componente_t", 0),
            componente_d=cu.get("componente_d", 0),
            componente_c=cu.get("componente_c", 0),
            componente_p=cu.get("componente_p"),
            componente_r=cu.get("componente_r"),
            demanda_gwh=cu.get("demanda_gwh"),
            generacion_gwh=cu.get("generacion_gwh"),
            perdidas_pct=cu.get("perdidas_pct"),
            fuentes_ok=cu.get("fuentes_ok", 0),
            notas=cu.get("notas"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo CU actual: {e}")


@router.get(
    "/history",
    response_model=CUHistoricoResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"},
    },
    summary="CU histórico",
    description="""
    Retorna la serie temporal del Costo Unitario en un rango de fechas.
    
    Si no se proporciona rango, retorna los últimos 30 días.
    Rango máximo: 365 días.
    """,
)
@limiter.limit("30/minute")
async def get_cu_history(
    request: Request,
    start_date: Optional[date] = Query(
        default=None,
        description="Fecha inicio (YYYY-MM-DD). Default: 30 días atrás",
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Fecha fin (YYYY-MM-DD). Default: hoy",
    ),
    api_key: str = Depends(get_api_key),
    service: CUService = Depends(get_cu_service),
):
    """Obtiene serie temporal del CU."""
    try:
        # Defaults
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        # Validaciones
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date debe ser anterior o igual a end_date",
            )
        if (end_date - start_date).days > 365:
            raise HTTPException(
                status_code=400,
                detail="Rango máximo permitido: 365 días",
            )

        df = service.get_cu_historico(start_date, end_date)

        # Convertir DataFrame a lista de dicts para respuesta
        registros = []
        for _, row in df.iterrows():
            if row.get("cu_total") is not None and not (
                hasattr(row["cu_total"], "__float__") and str(row["cu_total"]) == "nan"
            ):
                try:
                    registros.append(
                        CUDatoResponse(
                            fecha=row["fecha"].date() if hasattr(row["fecha"], "date") else row["fecha"],
                            componente_g=_safe_float(row.get("componente_g")),
                            componente_t=_safe_float(row.get("componente_t"), 0),
                            componente_d=_safe_float(row.get("componente_d"), 0),
                            componente_c=_safe_float(row.get("componente_c"), 0),
                            componente_p=_safe_float(row.get("componente_p")),
                            componente_r=_safe_float(row.get("componente_r")),
                            cu_total=float(row["cu_total"]),
                            demanda_gwh=_safe_float(row.get("demanda_gwh")),
                            generacion_gwh=_safe_float(row.get("generacion_gwh")),
                            perdidas_gwh=_safe_float(row.get("perdidas_gwh")),
                            perdidas_pct=_safe_float(row.get("perdidas_pct")),
                            fuentes_ok=int(row.get("fuentes_ok", 0)) if row.get("fuentes_ok") is not None else 0,
                            confianza=str(row.get("confianza", "baja")) if row.get("confianza") is not None else "baja",
                            notas=str(row.get("notas")) if row.get("notas") is not None and str(row.get("notas")) != "nan" else None,
                        )
                    )
                except (ValueError, TypeError):
                    continue

        total_dias = (end_date - start_date).days + 1

        return CUHistoricoResponse(
            status="ok",
            fecha_inicio=start_date,
            fecha_fin=end_date,
            total_registros=len(registros),
            total_dias=total_dias,
            cobertura_pct=round(len(registros) / total_dias * 100, 2) if total_dias > 0 else 0,
            data=registros,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo histórico CU: {e}")


@router.get(
    "/components/{fecha}",
    response_model=CUBreakdownResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No hay datos para esa fecha"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"},
    },
    summary="Desglose de componentes del CU",
    description="""
    Retorna el desglose porcentual de cada componente del CU
    para una fecha específica. Ideal para gráficos de torta.
    """,
)
@limiter.limit("60/minute")
async def get_cu_components(
    request: Request,
    fecha: date,
    api_key: str = Depends(get_api_key),
    service: CUService = Depends(get_cu_service),
):
    """Obtiene desglose de componentes del CU para una fecha."""
    try:
        breakdown = service.get_cu_components_breakdown(fecha)
        if breakdown is None:
            raise HTTPException(
                status_code=404,
                detail=f"No hay datos de CU para {fecha}",
            )

        return CUBreakdownResponse(
            status="ok",
            fecha=breakdown["fecha"],
            cu_total=breakdown["cu_total"],
            componentes=breakdown["componentes"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo desglose CU: {e}",
        )


# ═══════════════════════════════════════════════════════════
# FASE 4: CU FORECAST — Predicción ML con Redis cache
# ═══════════════════════════════════════════════════════════

@router.get(
    "/forecast",
    response_model=CUForecastResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Sin predicciones disponibles"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"},
    },
    summary="Predicción ML del CU",
    description="""
    Retorna la predicción del Costo Unitario generada por el modelo ML
    (Prophet+SARIMA ensemble) con intervalos de confianza.

    **Cache:** Redis con TTL=3600s (1 hora).
    **Fallback:** Si no hay predicciones ML, genera forecast naive
    basado en la tendencia de los últimos 30 días.

    **Parámetros:**
    - `horizon`: Número de días a predecir (default: 30, máx: 90)
    """,
)
@limiter.limit("20/minute")
async def get_cu_forecast(
    request: Request,
    horizon: int = Query(
        default=30,
        ge=1,
        le=90,
        description="Horizonte de predicción en días (1-90)",
    ),
    api_key: str = Depends(get_api_key),
    service: CUService = Depends(get_cu_service),
):
    """Obtiene predicción ML del CU con cache Redis."""
    import time
    t0 = time.time()

    # 1. Intentar cache Redis
    cache_key = _cache_key_forecast(horizon)
    cached = _cache_get(cache_key)
    if cached:
        cached["cache_hit"] = True
        latency_ms = round((time.time() - t0) * 1000, 1)
        logger.info(f"CU forecast HIT — {latency_ms}ms")
        return CUForecastResponse(**cached)

    try:
        # 2. CU actual para contexto
        cu_actual = service.get_cu_current()
        cu_val = cu_actual.get("cu_total") if cu_actual else None
        cu_fecha = cu_actual.get("fecha") if cu_actual else None

        # 3. Intentar cargar predicciones ML desde BD
        forecast_data = _load_ml_predictions(horizon)

        if forecast_data is not None:
            # ML predictions OK
            response_data = {
                "status": "ok",
                "fuente": "CU_DIARIO",
                "modelo": forecast_data["modelo"],
                "cu_actual": cu_val,
                "fecha_actual": cu_fecha,
                "horizonte_dias": horizon,
                "total_puntos": len(forecast_data["puntos"]),
                "mape_entrenamiento": forecast_data.get("mape"),
                "confianza": forecast_data.get("confianza"),
                "fecha_generacion": forecast_data.get("fecha_generacion"),
                "metodo_fallback": False,
                "forecast": forecast_data["puntos"],
                "cache_hit": False,
            }
        else:
            # 4. Fallback: tendencia naive (últimos 30 días)
            naive_data = _naive_forecast(service, horizon)
            if naive_data is None:
                raise HTTPException(
                    status_code=404,
                    detail="Sin predicciones ML ni datos históricos suficientes para forecast naive.",
                )
            response_data = {
                "status": "ok",
                "fuente": "CU_DIARIO",
                "modelo": "naive_trend_30d",
                "cu_actual": cu_val,
                "fecha_actual": cu_fecha,
                "horizonte_dias": horizon,
                "total_puntos": len(naive_data),
                "mape_entrenamiento": None,
                "confianza": "baja",
                "fecha_generacion": datetime.now().isoformat(),
                "metodo_fallback": True,
                "forecast": naive_data,
                "cache_hit": False,
            }

        # 5. Guardar en cache
        _cache_set(cache_key, response_data, CACHE_TTL_FORECAST)

        latency_ms = round((time.time() - t0) * 1000, 1)
        logger.info(f"CU forecast MISS — {latency_ms}ms, puntos={response_data['total_puntos']}")

        return CUForecastResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando forecast CU: {e}")


def _load_ml_predictions(horizon: int) -> Optional[dict]:
    """
    Carga predicciones ML desde la tabla predictions (fuente='CU_DIARIO').
    Retorna dict con modelo, puntos, mape, confianza; o None si no hay datos.
    """
    try:
        import psycopg2
        from core.config import Settings
        settings = Settings()
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT fecha_prediccion, valor_gwh_predicho, intervalo_inferior,
                   intervalo_superior, modelo, confianza, mape, fecha_generacion
            FROM predictions
            WHERE fuente = 'CU_DIARIO'
              AND fecha_prediccion >= CURRENT_DATE
            ORDER BY fecha_prediccion
            LIMIT %s
        """, (horizon,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        puntos = []
        for row in rows:
            puntos.append(CUForecastPoint(
                fecha=row[0],
                valor_predicho=round(float(row[1]), 2),
                intervalo_inferior=round(float(row[2]), 2) if row[2] else round(float(row[1]) * 0.9, 2),
                intervalo_superior=round(float(row[3]), 2) if row[3] else round(float(row[1]) * 1.1, 2),
            ))

        return {
            "modelo": rows[0][4] or "Prophet+SARIMA",
            "confianza": rows[0][5] or "media",
            "mape": round(float(rows[0][6]) * 100, 2) if rows[0][6] else None,
            "fecha_generacion": str(rows[0][7]) if rows[0][7] else None,
            "puntos": puntos,
        }

    except Exception as e:
        logger.warning(f"Error cargando predicciones ML CU: {e}")
        return None


def _naive_forecast(service: CUService, horizon: int) -> Optional[list]:
    """
    Forecast naive: tendencia lineal de los últimos 30 días de CU.
    Retorna lista de CUForecastPoint dicts, o None si datos insuficientes.
    """
    try:
        end = date.today()
        start = end - timedelta(days=30)
        df = service.get_cu_historico(start, end)

        if df is None or len(df) < 7:
            return None

        # Calcular tendencia lineal
        import numpy as np
        vals = df['cu_total'].dropna().values
        if len(vals) < 7:
            return None

        x = np.arange(len(vals), dtype=float)
        slope, intercept = np.polyfit(x, vals, 1)
        std_residual = np.std(vals - (slope * x + intercept))

        # Generar predicciones
        puntos = []
        base_idx = len(vals)
        for i in range(horizon):
            fecha_pred = end + timedelta(days=i + 1)
            val_pred = intercept + slope * (base_idx + i)
            # Intervalo: ±2σ expandido con horizonte
            spread = std_residual * 2.0 * (1 + i * 0.02)
            puntos.append(
                CUForecastPoint(
                    fecha=fecha_pred,
                    valor_predicho=round(max(val_pred, 0), 2),
                    intervalo_inferior=round(max(val_pred - spread, 0), 2),
                    intervalo_superior=round(val_pred + spread, 2),
                ).model_dump()
            )

        return puntos

    except Exception as e:
        logger.warning(f"Error generando forecast naive CU: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _safe_float(val, default=None):
    """Convierte a float de forma segura, retornando default si es NaN/None."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN check
            return default
        return f
    except (ValueError, TypeError):
        return default
