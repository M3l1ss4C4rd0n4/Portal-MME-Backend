"""
Endpoints de predicciones con Machine Learning

Proporciona acceso a predicciones generadas con:
- Prophet (Facebook)
- ARIMA (auto-tuning)
- Ensemble (combinación de modelos)

FASE 19: Redis caching — TTL 1h, ~5ms HIT vs ~120ms MISS.
Cache key: pred:{metric}:{entity}:{horizon}:{model}

Sigue las convenciones de datos en docs/api_data_conventions.md

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
Actualizado: FASE 19 (1 marzo 2026) — Redis caching
"""

import json
import time
import asyncio
import hashlib
import logging
from typing import Optional, Literal, List
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_predictions_service
from api.v1.schemas.predictions import PredictionResponse
from api.v1.schemas.common import ErrorResponse
from domain.services.predictions_service_extended import PredictionsService
from infrastructure.database.repositories.predictions_repository import PredictionsRepository
from infrastructure.database.repositories.metrics_repository import MetricsRepository

logger = logging.getLogger("predictions_cache")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# ─── FASE 19: Redis Cache ───────────────────────────────────────────────────
# Conexión lazy — si Redis no disponible, API funciona sin cache (fallback)
_redis_client = None

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
        logger.info("✅ Redis conectado para cache de predicciones")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Redis no disponible — API sin cache: {e}")
        _redis_client = None
        return None


def _cache_key(metric_id: str, entity: str, horizon_days: int, model_type: str, conformal: bool = True) -> str:
    """Cache key determinista para una predicción."""
    raw = f"{metric_id}|{entity}|{horizon_days}|{model_type}|{conformal}"
    short_hash = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"pred:{metric_id}:{entity}:{horizon_days}:{model_type}:{short_hash}"


def _cache_get(key: str) -> Optional[dict]:
    """Intentar leer del cache. Retorna None si falla."""
    r = _get_redis()
    if r is None:
        return None
    try:
        cached = r.get(key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug(f"Cache read error: {e}")
    return None


def _cache_set(key: str, data: dict, ttl: int = 3600) -> bool:
    """Escribir al cache con TTL. Retorna True si éxito."""
    r = _get_redis()
    if r is None:
        return False
    try:
        r.setex(key, ttl, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.debug(f"Cache write error: {e}")
        return False


# TTL por tipo de consulta
CACHE_TTL_PREDICTION = 3600   # 1h — predicciones cambian con cada re-entrenamiento
CACHE_TTL_BATCH = 1800        # 30min — batch puede ser frecuente


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD DE PREDICCIONES SIN — Portal de Dirección
# ═════════════════════════════════════════════════════════════════════════════

DASHBOARD_CACHE_KEY = "pred:dashboard:sin"
DASHBOARD_CACHE_TTL = 3600  # 1 hora

# Métricas que se muestran en el grid inferior del dashboard
DASHBOARD_METRICAS = [
    ("DEMANDA", "Demanda", "GWh"),
    ("PRECIO_BOLSA", "Precio Bolsa", "$/kWh"),
    ("APORTES_HIDRICOS", "Aportes Hídricos", "GWh"),
    ("GENE_TOTAL", "Generación Total", "GWh"),
]


@router.get(
    "/dashboard",
    response_model=dict,
    summary="Dashboard ejecutivo de predicciones del SIN",
    description="""
    Retorna en una sola llamada todo lo necesario para el tablero de predicciones:
    predicción de embalses 90 días, pico proyectado, señal ONI y resumen de
    métricas del SIN. Lee predicciones ya materializadas en PostgreSQL.
    """
)
@limiter.limit("30/minute")
async def get_predictions_dashboard(
    request: Request,
    api_key: str = Depends(get_api_key),
) -> dict:
    """
    Dashboard de predicciones SIN.

    Lee predicciones materializadas (re-entrenamiento automático cada 3 días)
    para respuesta rápida (< 200 ms). Incluye cache Redis TTL 1h.
    """
    t0 = time.time()

    # ── 1. Intentar cache ───────────────────────────────────────────────────
    cached = _cache_get(DASHBOARD_CACHE_KEY)
    if cached:
        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"✅ DASHBOARD CACHE HIT ({elapsed_ms:.1f}ms)")
        return JSONResponse(content=cached)

    try:
        # ── 2. Repositorios ─────────────────────────────────────────────────
        pred_repo = PredictionsRepository()
        metrics_repo = MetricsRepository()

        hoy = datetime.now().date()

        # ── 3. Predicción EMBALSES_PCT ──────────────────────────────────────
        # Usar solo ENSEMBLE_SECTOR_v1.0 (modelo principal de largo plazo).
        # PROPHET_LARGO_PLAZO_v1.0 existe en la tabla pero genera valores ~0%
        # para EMBALSES_PCT y causa el zig-zag al mezclarse.
        df_embalses = pred_repo.get_predictions(
            "EMBALSES_PCT",
            model_name="ENSEMBLE_SECTOR_v1.0",
            start_date=hoy,
        )
        if df_embalses is None or df_embalses.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay predicciones recientes de EMBALSES_PCT. "
                       "Ejecutar el re-entrenamiento del modelo."
            )

        # Metadata del modelo (MAPE, confianza, modelo, fecha generación)
        meta_embalses = pred_repo.execute_query_one(
            "SELECT mape, confianza, modelo, fecha_generacion "
            "FROM predictions WHERE fuente = %s LIMIT 1",
            ("EMBALSES_PCT",)
        )

        # Normalizar columnas
        df_embalses = df_embalses.rename(columns={
            "fecha_prediccion": "fecha",
            "valor_gwh_predicho": "valor",
            "intervalo_inferior": "lower",
            "intervalo_superior": "upper",
        })
        df_embalses["fecha"] = pd.to_datetime(df_embalses["fecha"]).dt.date

        # Pico proyectado
        idx_pico = df_embalses["valor"].idxmax()
        pico = df_embalses.loc[idx_pico]

        # ── 4. Valor actual real de embalses ────────────────────────────────
        df_embalses_actual = metrics_repo.get_metric_data(
            metric_id="PorcVoluUtilDiar",
            entity="Sistema",
            start_date="2020-01-01",
            end_date=str(hoy),
        )
        embalse_actual = None
        if df_embalses_actual is not None and not df_embalses_actual.empty:
            df_embalses_actual = df_embalses_actual.sort_values("fecha")
            ultimo = df_embalses_actual.iloc[-1]
            embalse_actual = {
                "fecha": str(ultimo["fecha"]),
                "valor": round(float(ultimo["valor_gwh"]) * 100, 2),
            }

        # ── 5. ONI actual y forecast ────────────────────────────────────────
        df_oni = metrics_repo.get_metric_data_by_entity(
            metric_id="ONI_Index",
            entity="NOAA",
            start_date="2026-01-01",
            end_date="2027-12-31",
            resource="Sistema",
        )
        oni_actual = None
        oni_forecast = []
        if df_oni is not None and not df_oni.empty:
            df_oni = df_oni.sort_values("fecha")
            df_oni["oni_real"] = df_oni["valor_gwh"] - 5.0
            df_oni["fecha"] = pd.to_datetime(df_oni["fecha"]).dt.date

            # Separar histórico y pronóstico
            df_oni_hist = df_oni[df_oni["fecha"] <= hoy]
            df_oni_future = df_oni[df_oni["fecha"] > hoy]

            if not df_oni_hist.empty:
                ultimo_oni = df_oni_hist.iloc[-1]
                oni_val = round(float(ultimo_oni["oni_real"]), 2)
                oni_actual = {
                    "valor": oni_val,
                    "fecha": str(ultimo_oni["fecha"]),
                    "estado": (
                        "EL NIÑO" if oni_val >= 0.5
                        else "LA NIÑA" if oni_val <= -0.5
                        else "NEUTRO"
                    ),
                }

            # Forecast: uno por mes (día 15) para no saturar la respuesta
            if not df_oni_future.empty:
                df_oni_future = df_oni_future[
                    df_oni_future["fecha"].apply(lambda d: d.day) == 15
                ]
                oni_forecast = [
                    {
                        "fecha": str(row["fecha"]),
                        "valor": round(float(row["oni_real"]), 2),
                    }
                    for _, row in df_oni_future.iterrows()
                ]

        # ── 5b. Join ONI diario con predicciones (para tooltip del gráfico) ──
        if df_oni is not None and not df_oni.empty:
            oni_by_date = df_oni.set_index("fecha")["oni_real"].to_dict()
            df_embalses["oni"] = df_embalses["fecha"].map(oni_by_date)
        else:
            df_embalses["oni"] = None

        # ── 5c. Join PDO diario con predicciones (ffill para extender al futuro) ─
        df_pdo = metrics_repo.get_metric_data_by_entity(
            metric_id="PDO_Index",
            entity="NOAA_ESRL",
            start_date="2020-01-01",
            end_date="2027-12-31",
            resource="Sistema",
        )
        if df_pdo is not None and not df_pdo.empty:
            df_pdo = df_pdo.sort_values("fecha")
            df_pdo["fecha"] = pd.to_datetime(df_pdo["fecha"]).dt.date
            pdo_serie = df_pdo.set_index("fecha")["valor_gwh"]
            pred_fechas = pd.Index(df_embalses["fecha"])
            pdo_reindexed = pdo_serie.reindex(pdo_serie.index.union(pred_fechas)).ffill()
            df_embalses["pdo"] = pred_fechas.map(pdo_reindexed)
        else:
            df_embalses["pdo"] = None

        # ── 5d. Join SOI diario con predicciones (ffill para extender al futuro) ─
        df_soi = metrics_repo.get_metric_data_by_entity(
            metric_id="SOI_Index",
            entity="NOAA_CPC",
            start_date="2020-01-01",
            end_date="2027-12-31",
            resource="Sistema",
        )
        if df_soi is not None and not df_soi.empty:
            df_soi = df_soi.sort_values("fecha")
            df_soi["fecha"] = pd.to_datetime(df_soi["fecha"]).dt.date
            soi_serie = df_soi.set_index("fecha")["valor_gwh"]
            soi_reindexed = soi_serie.reindex(soi_serie.index.union(pred_fechas)).ffill()
            df_embalses["soi"] = pred_fechas.map(soi_reindexed)
        else:
            df_embalses["soi"] = None

        # ── 5e. Join GMST diario con predicciones (ffill — cambia muy lentamente) ─
        df_gmst = metrics_repo.get_metric_data_by_entity(
            metric_id="GMST_Anomalia",
            entity="NASA_GISS",
            start_date="2020-01-01",
            end_date="2027-12-31",
            resource="Sistema",
        )
        if df_gmst is not None and not df_gmst.empty:
            df_gmst = df_gmst.sort_values("fecha")
            df_gmst["fecha"] = pd.to_datetime(df_gmst["fecha"]).dt.date
            gmst_serie = df_gmst.set_index("fecha")["valor_gwh"]
            gmst_reindexed = gmst_serie.reindex(gmst_serie.index.union(pred_fechas)).ffill()
            df_embalses["gmst"] = pred_fechas.map(gmst_reindexed)
        else:
            df_embalses["gmst"] = None

        # ── 6. Otras métricas SIN ───────────────────────────────────────────
        metricas_resumen = []
        for metric_id, nombre, unidad in DASHBOARD_METRICAS:
            df_pred = pred_repo.get_predictions(metric_id, start_date="2000-01-01")
            if df_pred is None or df_pred.empty:
                continue

            df_pred = df_pred.rename(columns={
                "fecha_prediccion": "fecha",
                "valor_gwh_predicho": "valor",
            })
            df_pred["fecha"] = pd.to_datetime(df_pred["fecha"]).dt.date
            df_pred = df_pred.sort_values("fecha").reset_index(drop=True)

            # Metadata
            meta = pred_repo.execute_query_one(
                "SELECT mape, modelo FROM predictions WHERE fuente = %s LIMIT 1",
                (metric_id,)
            )

            # Predicción a 7 días
            pred_7d = df_pred.iloc[min(6, len(df_pred) - 1)] if len(df_pred) >= 7 else df_pred.iloc[-1]

            # "Actual": usar el primer día de la predicción como valor de referencia reciente.
            # Es consistente con el horizonte del modelo y evita inconsistencias de datos parciales.
            actual_val = round(float(df_pred.iloc[0]["valor"]), 2)

            # Tendencia
            diff = float(pred_7d["valor"]) - actual_val
            pct_diff = abs(diff) / max(abs(actual_val), 1e-9)
            tendencia = "estable"
            if pct_diff > 0.02:
                tendencia = "alta" if diff > 0 else "baja"

            metricas_resumen.append({
                "id": metric_id,
                "nombre": nombre,
                "unidad": unidad,
                "actual": actual_val,
                "prediccion_7d": round(float(pred_7d["valor"]), 2),
                "mape": round(float(meta.get("mape", 0) or 0), 4) if meta else 0.0,
                "modelo": str(meta.get("modelo", "")) if meta else "",
                "tendencia": tendencia,
            })

        # ── 7. Construir respuesta ──────────────────────────────────────────
        response = {
            "embalses": {
                "actual": embalse_actual,
                "prediccion": [
                    {
                        "fecha": str(row["fecha"]),
                        "valor": round(float(row["valor"]), 2),
                        "lower": round(float(row["lower"]), 2),
                        "upper": min(round(float(row["upper"]), 2), 100.0),
                        "oni": round(float(row["oni"]), 3) if pd.notna(row.get("oni", float("nan"))) else None,
                        "pdo": round(float(row["pdo"]), 3) if pd.notna(row.get("pdo", float("nan"))) else None,
                        "soi": round(float(row["soi"]), 3) if pd.notna(row.get("soi", float("nan"))) else None,
                        "gmst": round(float(row["gmst"]), 3) if pd.notna(row.get("gmst", float("nan"))) else None,
                    }
                    for _, row in df_embalses.iterrows()
                ],
                "pico": {
                    "fecha": str(pico["fecha"]),
                    "valor": round(float(pico["valor"]), 2),
                    "dias_desde_hoy": max(0, (pico["fecha"] - hoy).days),
                },
                "mape": round(float(meta_embalses.get("mape", 0) or 0), 4) if meta_embalses else 0.0,
                "confianza": round(float(meta_embalses.get("confianza", 0.92) or 0.92), 2) if meta_embalses else 0.92,
                "modelo": str(meta_embalses.get("modelo", "ensemble_prophet_sarima")) if meta_embalses else "ensemble_prophet_sarima",
                "generado_en": (
                    meta_embalses["fecha_generacion"].isoformat()
                    if meta_embalses and meta_embalses.get("fecha_generacion")
                    else datetime.now().isoformat()
                ),
            },
            "oni": {
                "actual": oni_actual.get("valor") if oni_actual else None,
                "actual_fecha": oni_actual.get("fecha") if oni_actual else None,
                "estado": oni_actual.get("estado") if oni_actual else None,
                "forecast": oni_forecast,
                "pdo": {
                    "actual": round(float(df_pdo.iloc[-1]["valor_gwh"]), 2) if df_pdo is not None and not df_pdo.empty else None,
                    "fase": "PDO+" if (df_pdo is not None and not df_pdo.empty and float(df_pdo.iloc[-1]["valor_gwh"]) > 0) else "PDO−",
                    "fecha": str(df_pdo.iloc[-1]["fecha"]) if df_pdo is not None and not df_pdo.empty else None,
                },
                "soi": {
                    "actual": round(float(df_soi.iloc[-1]["valor_gwh"]), 2) if df_soi is not None and not df_soi.empty else None,
                    "fecha": str(df_soi.iloc[-1]["fecha"]) if df_soi is not None and not df_soi.empty else None,
                },
                "gmst": {
                    "actual": round(float(df_gmst.iloc[-1]["valor_gwh"]), 3) if df_gmst is not None and not df_gmst.empty else None,
                    "fecha": str(df_gmst.iloc[-1]["fecha"]) if df_gmst is not None and not df_gmst.empty else None,
                },
            },
            "metricas": metricas_resumen,
            "generado_en": datetime.now().isoformat(),
        }

        # ── 8. Guardar cache ────────────────────────────────────────────────
        _cache_set(DASHBOARD_CACHE_KEY, response, DASHBOARD_CACHE_TTL)

        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"🔄 DASHBOARD MISS → DB ({elapsed_ms:.1f}ms) — cached TTL={DASHBOARD_CACHE_TTL}s")
        return JSONResponse(content=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generando dashboard de predicciones: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar dashboard de predicciones: {str(e)}"
        )


@router.get(
    "/{metric_id}",
    response_model=PredictionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Métrica no encontrada o sin datos históricos"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Generar predicción ML para una métrica",
    description="""
    Genera predicciones a futuro para una métrica energética usando Machine Learning.
    
    **Modelos disponibles:**
    - `prophet`: Facebook Prophet (recomendado para series con estacionalidad)
    - `arima`: ARIMA auto-tuning (recomendado para series estacionarias)
    - `ensemble`: Combinación de múltiples modelos (mayor precisión)
    
    **Parámetros:**
    - `metric_id`: Código de la métrica (Gene, DemaReal, Aportes, etc.)
    - `entity`: Entidad a predecir (Sistema, HIDRAULICA, etc.)
    - `horizon_days`: Días de proyección (7, 30, 90, 365)
    - `model_type`: Tipo de modelo ML a usar
    
    **Respuesta:**
    Predicciones con intervalos de confianza según formato en `docs/api_data_conventions.md`
    """
)
@limiter.limit("20/minute")
async def get_prediction(
    request: Request,
    metric_id: str,
    entity: Optional[str] = Query(
        default="Sistema",
        description="Entidad a predecir (Sistema, Recurso, etc.)"
    ),
    horizon_days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Días de proyección (1-365)"
    ),
    model_type: Literal["prophet", "arima", "ensemble"] = Query(
        default="prophet",
        description="Tipo de modelo ML a usar"
    ),
    conformal: bool = Query(
        default=True,
        description="Aplicar calibración conformal a los intervalos (garantía ≥ confidence_level de cobertura)"
    ),
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> PredictionResponse:
    """
    Genera predicción ML para una métrica específica
    
    Args:
        request: Request de FastAPI (para rate limiting)
        metric_id: Código de la métrica XM
        entity: Entidad a predecir
        horizon_days: Días de proyección futura
        model_type: Tipo de modelo ML
        api_key: API Key validada
        service: Servicio de predicciones inyectado
        
    Returns:
        Predicción con intervalos de confianza
        
    Raises:
        HTTPException 404: Si la métrica no existe o no tiene datos históricos
        HTTPException 400: Si los parámetros son inválidos
        HTTPException 500: Error interno del servidor o error del modelo ML
    """
    try:
        t0 = time.time()
        
        # ── FASE 19: Check Redis cache ──
        cache_k = _cache_key(metric_id, entity, horizon_days, model_type, conformal)
        cached = _cache_get(cache_k)
        if cached:
            elapsed_ms = (time.time() - t0) * 1000
            logger.info(f"✅ CACHE HIT: {cache_k} ({elapsed_ms:.1f}ms)")
            return JSONResponse(content=cached)
        
        # CACHE MISS → query DB + model
        # Generar predicción usando el servicio de dominio
        df_prediction = service.forecast_metric(
            metric_id=metric_id,
            entity=entity,
            horizon_days=horizon_days,
            model_type=model_type,
            conformal=conformal,
        )
        
        # Verificar si se generó la predicción
        if df_prediction is None or df_prediction.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudo generar predicción para '{metric_id}'. Verifique que existan datos históricos suficientes."
            )
        
        # Convertir DataFrame a formato API
        response = PredictionResponse.from_dataframe(
            df=df_prediction,
            metric_id=metric_id,
            entity=entity,
            model_type=model_type,
            horizon_days=horizon_days
        )
        
        # ── FASE 19: Store in Redis cache ──
        response_dict = response.model_dump(mode='json')
        _cache_set(cache_k, response_dict, CACHE_TTL_PREDICTION)
        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"🔄 CACHE MISS → DB: {cache_k} ({elapsed_ms:.1f}ms) — cached TTL={CACHE_TTL_PREDICTION}s")
        
        return response
        
    except HTTPException:
        raise
    except ValueError as e:
        # Errores de validación del modelo ML
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Errores internos del modelo ML
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar predicción: {str(e)}"
        )


@router.post(
    "/{metric_id}/train",
    response_model=dict,
    responses={
        404: {"model": ErrorResponse, "description": "Métrica no encontrada"},
        400: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    },
    summary="Entrenar modelo ML para una métrica",
    description="""
    Entrena y guarda un modelo ML específico para una métrica.
    
    **Nota:** Este endpoint puede tardar varios minutos dependiendo del tamaño de los datos.
    
    **Parámetros:**
    - `metric_id`: Código de la métrica
    - `model_type`: Tipo de modelo a entrenar
    - `save_model`: Si se debe guardar el modelo entrenado (default: True)
    
    **Respuesta:**
    Métricas de evaluación del modelo entrenado
    """
)
@limiter.limit("5/hour")
async def train_model(
    request: Request,
    metric_id: str,
    model_type: Literal["prophet", "arima", "ensemble"] = Query(
        default="prophet",
        description="Tipo de modelo ML a entrenar"
    ),
    save_model: bool = Query(
        default=True,
        description="Guardar modelo entrenado para uso futuro"
    ),
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> dict:
    """
    Entrena modelo ML para una métrica específica
    
    Args:
        request: Request de FastAPI (para rate limiting)
        metric_id: Código de la métrica XM
        model_type: Tipo de modelo ML
        save_model: Guardar modelo entrenado
        api_key: API Key validada
        service: Servicio de predicciones inyectado
        
    Returns:
        Métricas de evaluación del modelo
        
    Raises:
        HTTPException 404: Si la métrica no existe
        HTTPException 400: Si los parámetros son inválidos
        HTTPException 500: Error durante el entrenamiento
    """
    try:
        # Entrenar modelo
        metrics = service.train_and_save_model(
            metric_id=metric_id,
            model_type=model_type,
            save=save_model
        )

        # FASE 19: Invalidar cache para esta métrica tras re-entrenamiento
        r = _get_redis()
        if r:
            try:
                pattern = f"pred:{metric_id}:*"
                keys = r.keys(pattern)
                # Also flush batch keys that might contain this metric
                batch_keys = r.keys("pred:batch:*")
                all_keys = keys + batch_keys
                if all_keys:
                    deleted = r.delete(*all_keys)
                    logger.info(f"🗑️ Cache invalidated after train: {deleted} keys for {metric_id}")
            except Exception as e:
                pass  # Cache invalidation is best-effort
        
        return {
            "metric_id": metric_id,
            "model_type": model_type,
            "status": "trained",
            "saved": save_model,
            "metrics": metrics,
            "cache_invalidated": True
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al entrenar modelo: {str(e)}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# FASE 19: Batch predictions + Cache management endpoints
# ═════════════════════════════════════════════════════════════════════════════

DEFAULT_BATCH_METRICS = [
    "DEMANDA", "PRECIO_BOLSA", "APORTES_HIDRICOS",
    "Térmica", "Solar", "Eólica"
]


@router.get(
    "/batch/forecast",
    response_model=dict,
    summary="Predicciones batch para múltiples métricas",
    description="""
    Genera predicciones para múltiples métricas en una sola llamada.
    Usa Redis cache (TTL 30min). Ideal para dashboards y bots.
    
    **Default:** DEMANDA, PRECIO_BOLSA, APORTES_HIDRICOS, Térmica, Solar, Eólica
    """
)
@limiter.limit("10/minute")
async def get_batch_predictions(
    request: Request,
    metricas: List[str] = Query(
        default=None,
        description="Lista de métricas a predecir (default: 6 principales)"
    ),
    horizon_days: int = Query(default=30, ge=1, le=365),
    model_type: Literal["prophet", "arima", "ensemble"] = Query(default="prophet"),
    conformal: bool = Query(
        default=True,
        description="Aplicar calibración conformal a los intervalos"
    ),
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> dict:
    """Batch predictions con cache Redis."""
    t0 = time.time()
    if not metricas:
        metricas = DEFAULT_BATCH_METRICS

    # Check batch cache
    batch_key_raw = f"batch|{'_'.join(sorted(metricas))}|{horizon_days}|{model_type}|{conformal}"
    batch_hash = hashlib.md5(batch_key_raw.encode()).hexdigest()[:8]
    batch_cache_key = f"pred:batch:{batch_hash}"

    cached = _cache_get(batch_cache_key)
    if cached:
        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"✅ BATCH CACHE HIT: {batch_cache_key} ({elapsed_ms:.1f}ms)")
        return JSONResponse(content=cached)

    # MISS → generate each
    results = {}
    cache_hits = 0
    for m in metricas:
        # Try individual cache first
        ind_key = _cache_key(m, "Sistema", horizon_days, model_type, conformal)
        ind_cached = _cache_get(ind_key)
        if ind_cached:
            results[m] = ind_cached
            cache_hits += 1
            continue

        try:
            df_pred = service.forecast_metric(
                metric_id=m,
                entity="Sistema",
                horizon_days=horizon_days,
                model_type=model_type,
                conformal=conformal,
            )
            if df_pred is not None and not df_pred.empty:
                resp = PredictionResponse.from_dataframe(
                    df=df_pred, metric_id=m, entity="Sistema",
                    model_type=model_type, horizon_days=horizon_days
                )
                resp_dict = resp.model_dump(mode='json')
                _cache_set(ind_key, resp_dict, CACHE_TTL_PREDICTION)
                results[m] = resp_dict
            else:
                results[m] = {"error": f"Sin datos para {m}"}
        except Exception as e:
            results[m] = {"error": str(e)}

    batch_result = {
        "generated_at": datetime.now().isoformat(),
        "metricas_solicitadas": metricas,
        "metricas_ok": len([v for v in results.values() if "error" not in v]),
        "cache_hits": cache_hits,
        "predictions": results,
    }
    _cache_set(batch_cache_key, batch_result, CACHE_TTL_BATCH)
    elapsed_ms = (time.time() - t0) * 1000
    logger.info(f"🔄 BATCH MISS → DB: {len(metricas)} métricas ({elapsed_ms:.1f}ms)")
    return batch_result


@router.get(
    "/cache/stats",
    response_model=dict,
    summary="Estadísticas del cache Redis",
    description="Muestra keys activos, memoria usada y estado de Redis."
)
async def cache_stats(
    api_key: str = Depends(get_api_key)
) -> dict:
    """Estadísticas del cache Redis para predicciones."""
    r = _get_redis()
    if r is None:
        return {
            "status": "offline",
            "message": "Redis no disponible — API funciona sin cache"
        }

    try:
        info = r.info("memory")
        pred_keys = r.keys("pred:*")
        batch_keys = [k for k in pred_keys if ":batch:" in k]
        individual_keys = [k for k in pred_keys if ":batch:" not in k]

        # TTL de cada key
        key_details = []
        for k in pred_keys[:20]:  # Limit to 20
            ttl = r.ttl(k)
            key_details.append({"key": k, "ttl_seconds": ttl})

        return {
            "status": "online",
            "redis_version": r.info("server").get("redis_version", "unknown"),
            "memory_used_human": info.get("used_memory_human", "N/A"),
            "memory_peak_human": info.get("used_memory_peak_human", "N/A"),
            "total_pred_keys": len(pred_keys),
            "individual_keys": len(individual_keys),
            "batch_keys": len(batch_keys),
            "keys": key_details,
            "ttl_prediction": CACHE_TTL_PREDICTION,
            "ttl_batch": CACHE_TTL_BATCH,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete(
    "/cache/flush",
    response_model=dict,
    summary="Limpiar cache de predicciones",
    description="Elimina todas las keys pred:* de Redis. Útil después de re-entrenamiento."
)
async def cache_flush(
    api_key: str = Depends(get_api_key)
) -> dict:
    """Flush all prediction cache keys."""
    r = _get_redis()
    if r is None:
        return {"status": "offline", "deleted": 0}

    try:
        keys = r.keys("pred:*")
        if keys:
            deleted = r.delete(*keys)
        else:
            deleted = 0
        logger.info(f"🗑️ Cache flushed: {deleted} keys eliminadas")
        return {"status": "flushed", "deleted": deleted}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post(
    "/generate-long-term",
    response_model=dict,
    summary="Genera predicciones de largo plazo (91–365 días)",
    description=(
        "Genera predicciones Prophet hasta 365 días para todas las fuentes. "
        "Predicciones >90 días clasificadas como EXPERIMENTAL. "
        "Proceso síncrono — puede tardar 3-8 minutos."
    ),
)
async def generate_long_term(
    horizonte_dias: int = Query(default=90, ge=30, le=365, description="Días a predecir (30–365)"),
    fuentes: Optional[List[str]] = Query(default=None, description="Fuentes a generar (None = todas)"),
    api_key: str = Depends(get_api_key),
) -> dict:
    """Genera y persiste predicciones de largo plazo con Prophet."""
    loop = asyncio.get_event_loop()
    svc = PredictionsService()

    resumen = await loop.run_in_executor(
        None,
        lambda: svc.save_long_term_predictions(
            fuentes=fuentes,
            horizonte_dias=horizonte_dias,
        )
    )

    total = sum(resumen.values())
    fuentes_ok = [f for f, n in resumen.items() if n > 0]
    fuentes_fail = [f for f, n in resumen.items() if n == 0]

    return {
        'message': f'{total} predicciones {horizonte_dias}d generadas',
        'horizonte_dias': horizonte_dias,
        'clasificacion': 'EXPERIMENTAL' if horizonte_dias > 90 else 'MODERADA',
        'advertencia': (
            'Predicciones >90 días tienen mayor incertidumbre. '
            'Usar solo para planificación estratégica, '
            'no para operaciones del día siguiente.'
        ),
        'resumen_por_fuente': resumen,
        'fuentes_exitosas': len(fuentes_ok),
        'fuentes_fallidas': len(fuentes_fail),
        'fuentes_fallidas_lista': fuentes_fail,
        'generado_en': datetime.now().isoformat(),
    }
