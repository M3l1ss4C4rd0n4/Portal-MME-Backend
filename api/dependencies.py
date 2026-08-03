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
from domain.services.ontologia_service import OntologiaService
from domain.services.risk_service import RiskService
from domain.services.graph_service import GraphService
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.database.repositories.predictions_repository import PredictionsRepository
from infrastructure.database.repositories.geografia_repository import GeografiaRepository
from infrastructure.database.repositories.empresa_repository import EmpresaRepository
from infrastructure.database.repositories.semantic_search_repository import SemanticSearchRepository
from infrastructure.database.repositories.proyecto_repository import ProyectoRepository


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
    return MetricsService(repository=metrics_repo)


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
def get_geografia_repository() -> GeografiaRepository:
    """Singleton del repositorio de geografía DANE (esquema ontologia)."""
    return GeografiaRepository()


@lru_cache()
def get_empresa_repository() -> EmpresaRepository:
    """Singleton del repositorio de empresas/prestadores (esquema ontologia)."""
    return EmpresaRepository()


@lru_cache()
def get_semantic_search_repository() -> SemanticSearchRepository:
    """Singleton del repositorio de búsqueda semántica / RAG (esquema ontologia)."""
    return SemanticSearchRepository()


@lru_cache()
def get_proyecto_repository() -> ProyectoRepository:
    """Singleton del repositorio de proyectos (esquema ontologia, Fase 7)."""
    return ProyectoRepository()


def get_ontologia_service(
    geografia_repo: GeografiaRepository = Depends(get_geografia_repository),
    empresa_repo: EmpresaRepository = Depends(get_empresa_repository),
    semantic_search_repo: SemanticSearchRepository = Depends(get_semantic_search_repository),
    proyecto_repo: ProyectoRepository = Depends(get_proyecto_repository),
) -> OntologiaService:
    """
    Proveedor del servicio de ontología (geografía DANE + empresas/prestadores + RAG + proyectos).
    Capa 100% de lectura/análisis — sin operaciones de escritura sobre contratos.
    """
    return OntologiaService(
        geografia_repository=geografia_repo,
        empresa_repository=empresa_repo,
        semantic_search_repository=semantic_search_repo,
        proyecto_repository=proyecto_repo,
    )


@lru_cache()
def get_risk_service() -> RiskService:
    """Singleton del servicio de riesgo de atraso (Fase 4 — analítica predictiva)."""
    return RiskService()


def get_graph_service(
    empresa_repo: EmpresaRepository = Depends(get_empresa_repository),
) -> GraphService:
    """Proveedor del servicio de grafo de relaciones (Fase 5 — solo lectura/auditoría)."""
    return GraphService(empresa_repository=empresa_repo)


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
# SERVICIO ORQUESTADOR (singleton via DI Container)
# ═══════════════════════════════════════════════════════════

def get_cu_service():
    """
    Singleton del servicio de Costo Unitario (CU).
    
    Usa el DI Container para reutilizar la misma instancia
    entre requests.
    
    Returns:
        Instancia compartida de CUService
    """
    from core.container import get_cu_service as _get_cu_service
    return _get_cu_service()


def get_losses_nt_service():
    """
    Singleton del servicio de Pérdidas No Técnicas.
    
    Returns:
        Instancia compartida de LossesNTService
    """
    from core.container import get_losses_nt_service as _get_losses_nt_service
    return _get_losses_nt_service()


def get_simulation_service():
    """
    Singleton del servicio de Simulación CREG.
    
    Returns:
        Instancia compartida de SimulationService
    """
    from core.container import get_simulation_service as _get_simulation_service
    return _get_simulation_service()


def get_orchestrator_service():
    """
    Singleton del servicio orquestador de chatbot.
    
    Usa el DI Container para reutilizar la misma instancia
    entre requests (evita re-inicializar 7 sub-servicios).
    
    Returns:
        Instancia compartida de ChatbotOrchestratorService
    """
    from core.container import container
    return container.get_orchestrator_service()


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
