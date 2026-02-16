"""
Dependencias compartidas de FastAPI

Proporciona inyección de dependencias para:
- Validación de API Key
- Servicios de dominio (MetricsService, PredictionsService, AIService)
- Rate limiting
- Autenticación y autorización

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from functools import lru_cache

from core.config import settings
from domain.services.metrics_service import MetricsService
from domain.services.predictions_service_extended import PredictionsService
from domain.services.ai_service import AgentIA
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.database.repositories.predictions_repository import PredictionsRepository


# ═══════════════════════════════════════════════════════════
# VALIDACIÓN DE API KEY
# ═══════════════════════════════════════════════════════════

async def get_api_key(x_api_key: Optional[str] = Header(None, description="API Key de autenticación")) -> str:
    """
    Valida la API Key proporcionada en el header X-API-Key
    
    Args:
        x_api_key: API Key del header HTTP
        
    Returns:
        API Key validada
        
    Raises:
        HTTPException: Si la API Key es inválida o falta
        
    Example:
        ```python
        @app.get("/protected")
        async def protected_route(api_key: str = Depends(get_api_key)):
            return {"message": "Acceso autorizado"}
        ```
    """
    # Si la validación está deshabilitada en desarrollo
    if not settings.API_KEY_ENABLED:
        return "development-mode"
    
    # Validar que se proporcionó el header
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key requerida. Proporcione X-API-Key en los headers",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    # Validar que la API Key es correcta
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key inválida",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return x_api_key


# ═══════════════════════════════════════════════════════════
# INYECCIÓN DE SERVICIOS DE DOMINIO
# ═══════════════════════════════════════════════════════════

@lru_cache()
def get_metrics_repository() -> MetricsRepository:
    """
    Singleton del repositorio de métricas
    
    Returns:
        Instancia compartida de MetricsRepository
    """
    return MetricsRepository()


@lru_cache()
def get_predictions_repository() -> PredictionsRepository:
    """
    Singleton del repositorio de predicciones
    
    Returns:
        Instancia compartida de PredictionsRepository
    """
    return PredictionsRepository()


def get_metrics_service(
    metrics_repo: MetricsRepository = Depends(get_metrics_repository)
) -> MetricsService:
    """
    Proveedor del servicio de métricas
    
    Args:
        metrics_repo: Repositorio de métricas inyectado
        
    Returns:
        Instancia de MetricsService
        
    Example:
        ```python
        @app.get("/metrics")
        async def get_metrics(
            service: MetricsService = Depends(get_metrics_service)
        ):
            return service.list_metrics()
        ```
    """
    return MetricsService(repo=metrics_repo)


def get_predictions_service(
    predictions_repo: PredictionsRepository = Depends(get_predictions_repository),
    metrics_repo: MetricsRepository = Depends(get_metrics_repository)
) -> PredictionsService:
    """
    Proveedor del servicio de predicciones ML
    
    Args:
        predictions_repo: Repositorio de predicciones inyectado
        metrics_repo: Repositorio de métricas inyectado
        
    Returns:
        Instancia de PredictionsService
        
    Example:
        ```python
        @app.get("/predictions")
        async def get_predictions(
            service: PredictionsService = Depends(get_predictions_service)
        ):
            return service.get_latest_prediction_date()
        ```
    """
    return PredictionsService(
        repo=predictions_repo,
        metrics_repo=metrics_repo
    )


@lru_cache()
def get_ai_service() -> AgentIA:
    """
    Singleton del servicio de IA
    
    Returns:
        Instancia compartida de AgentIA
        
    Example:
        ```python
        @app.post("/analyze")
        async def analyze(
            ai_service: AgentIA = Depends(get_ai_service)
        ):
            return ai_service.analizar_metrica("Gene")
        ```
    """
    return AgentIA()


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE PAGINACIÓN
# ═══════════════════════════════════════════════════════════

def get_pagination_params(
    limit: int = 1000,
    offset: int = 0
) -> dict:
    """
    Parámetros de paginación con validación
    
    Args:
        limit: Número máximo de registros (default: 1000, máx: 10000)
        offset: Offset para paginación (default: 0)
        
    Returns:
        Dict con limit y offset validados
        
    Raises:
        HTTPException: Si los parámetros son inválidos
    """
    if limit < 1 or limit > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro 'limit' debe estar entre 1 y 10000"
        )
    
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro 'offset' debe ser mayor o igual a 0"
        )
    
    return {"limit": limit, "offset": offset}
