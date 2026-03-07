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
import hashlib
import logging
from typing import Optional, Literal, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_predictions_service
from api.v1.schemas.predictions import PredictionResponse
from api.v1.schemas.common import ErrorResponse
from domain.services.predictions_service_extended import PredictionsService

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


def _cache_key(metric_id: str, entity: str, horizon_days: int, model_type: str) -> str:
    """Cache key determinista para una predicción."""
    raw = f"{metric_id}|{entity}|{horizon_days}|{model_type}"
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
        cache_k = _cache_key(metric_id, entity, horizon_days, model_type)
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
            model_type=model_type
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
    api_key: str = Depends(get_api_key),
    service: PredictionsService = Depends(get_predictions_service)
) -> dict:
    """Batch predictions con cache Redis."""
    t0 = time.time()
    if not metricas:
        metricas = DEFAULT_BATCH_METRICS

    # Check batch cache
    batch_key_raw = f"batch|{'_'.join(sorted(metricas))}|{horizon_days}|{model_type}"
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
        ind_key = _cache_key(m, "Sistema", horizon_days, model_type)
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
                model_type=model_type
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
