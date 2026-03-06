"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    DEPENDENCY INJECTION CONTAINER                             ║
║                                                                               ║
║  Contenedor simple para inyección de dependencias                            ║
║  Centraliza la creación de servicios y repositorios                          ║
║  Facilita testing con mocks y configuraciones alternativas                   ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from typing import Optional
import logging

# Domain Interfaces
from domain.interfaces.repositories import (
    IMetricsRepository,
    ICommercialRepository,
    IDistributionRepository,
    ITransmissionRepository,
    IPredictionsRepository,
)
from domain.interfaces.data_sources import IXMDataSource
from domain.interfaces.database import IDatabaseManager

# Infrastructure Implementations
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.database.repositories.commercial_repository import CommercialRepository
from infrastructure.database.repositories.distribution_repository import DistributionRepository
from infrastructure.database.repositories.transmission_repository import TransmissionRepository
from infrastructure.database.repositories.predictions_repository import PredictionsRepository
from infrastructure.database.manager import DatabaseManager, db_manager
from infrastructure.external.xm_adapter import XMDataSourceAdapter

# Domain Services
from domain.services.generation_service import GenerationService
from domain.services.metrics_service import MetricsService
from domain.services.commercial_service import CommercialService
from domain.services.distribution_service import DistributionService
from domain.services.transmission_service import TransmissionService
from domain.services.cu_service import CUService

logger = logging.getLogger(__name__)


class DependencyContainer:
    """
    Contenedor de Inyección de Dependencias (DI Container).
    
    Propósito:
    - Centralizar la creación de objetos y sus dependencias
    - Facilitar testing con configuraciones alternativas
    - Permitir intercambiar implementaciones sin cambiar código
    
    Uso:
        # Obtener servicio con dependencias inyectadas
        container = DependencyContainer()
        gen_service = container.get_generation_service()
        
        # Testing con mocks
        container = DependencyContainer()
        container.override_metrics_repository(MockMetricsRepository())
        gen_service = container.get_generation_service()  # Usa mock
    """
    
    def __init__(self):
        """Inicializa el contenedor con configuración por defecto."""
        self._metrics_repository: Optional[IMetricsRepository] = None
        self._commercial_repository: Optional[ICommercialRepository] = None
        self._distribution_repository: Optional[IDistributionRepository] = None
        self._transmission_repository: Optional[ITransmissionRepository] = None
        self._predictions_repository: Optional[IPredictionsRepository] = None
        self._database_manager: Optional[IDatabaseManager] = None
        self._xm_datasource: Optional[IXMDataSource] = None
        
        logger.debug("DependencyContainer inicializado")
    
    # ============================================================================
    # REPOSITORIES - Lazy instantiation con singleton pattern
    # ============================================================================
    
    def get_metrics_repository(self) -> IMetricsRepository:
        """Obtiene repositorio de métricas (singleton)."""
        if self._metrics_repository is None:
            self._metrics_repository = MetricsRepository()
            logger.debug("MetricsRepository creado")
        return self._metrics_repository
    
    def get_commercial_repository(self) -> ICommercialRepository:
        """Obtiene repositorio de comercialización (singleton)."""
        if self._commercial_repository is None:
            self._commercial_repository = CommercialRepository()
            logger.debug("CommercialRepository creado")
        return self._commercial_repository
    
    def get_distribution_repository(self) -> IDistributionRepository:
        """Obtiene repositorio de distribución (singleton)."""
        if self._distribution_repository is None:
            self._distribution_repository = DistributionRepository()
            logger.debug("DistributionRepository creado")
        return self._distribution_repository
    
    def get_transmission_repository(self) -> ITransmissionRepository:
        """Obtiene repositorio de transmisión (singleton)."""
        if self._transmission_repository is None:
            self._transmission_repository = TransmissionRepository()
            logger.debug("TransmissionRepository creado")
        return self._transmission_repository
    
    def get_predictions_repository(self) -> IPredictionsRepository:
        """Obtiene repositorio de predicciones (singleton)."""
        if self._predictions_repository is None:
            self._predictions_repository = PredictionsRepository()
            logger.debug("PredictionsRepository creado")
        return self._predictions_repository
    
    def get_database_manager(self) -> IDatabaseManager:
        """Obtiene database manager (usa instancia global)."""
        if self._database_manager is None:
            self._database_manager = db_manager
            logger.debug("DatabaseManager obtenido (instancia global)")
        return self._database_manager
    
    def get_xm_datasource(self) -> IXMDataSource:
        """Obtiene data source de XM (singleton)."""
        if self._xm_datasource is None:
            self._xm_datasource = XMDataSourceAdapter()
            logger.debug("XMDataSourceAdapter creado")
        return self._xm_datasource
    
    # ============================================================================
    # SERVICES - Factory methods con inyección de dependencias
    # ============================================================================
    
    def get_generation_service(self) -> GenerationService:
        """
        Crea GenerationService con dependencias inyectadas.
        
        Returns:
            GenerationService con MetricsRepository inyectado
        """
        return GenerationService(repository=self.get_metrics_repository())
    
    def get_metrics_service(self) -> MetricsService:
        """
        Crea MetricsService con dependencias inyectadas.
        
        Returns:
            MetricsService con MetricsRepository inyectado
        """
        return MetricsService(repository=self.get_metrics_repository())
    
    def get_commercial_service(self) -> CommercialService:
        """
        Crea CommercialService con dependencias inyectadas.
        
        Returns:
            CommercialService con CommercialRepository inyectado
        """
        return CommercialService(repository=self.get_commercial_repository())
    
    def get_distribution_service(self) -> DistributionService:
        """
        Crea DistributionService con dependencias inyectadas.
        
        Returns:
            DistributionService con DistributionRepository inyectado
        """
        return DistributionService(repository=self.get_distribution_repository())
    
    def get_transmission_service(self) -> TransmissionService:
        """
        Crea TransmissionService con dependencias inyectadas.
        
        Returns:
            TransmissionService con TransmissionRepository inyectado
        """
        return TransmissionService(repository=self.get_transmission_repository())
    
    def get_cu_service(self) -> CUService:
        """
        Obtiene CUService como singleton lazy.
        
        Returns:
            CUService para cálculo de Costo Unitario
        """
        if not hasattr(self, '_cu_service') or self._cu_service is None:
            self._cu_service = CUService()
            logger.debug("CUService creado (singleton)")
        return self._cu_service
    
    @property
    def losses_nt_service(self):
        """Obtiene LossesNTService como singleton lazy."""
        if not hasattr(self, '_losses_nt_service') or self._losses_nt_service is None:
            from domain.services.losses_nt_service import LossesNTService
            self._losses_nt_service = LossesNTService()
            logger.debug("LossesNTService creado (singleton)")
        return self._losses_nt_service

    @property
    def simulation_service(self):
        """Obtiene SimulationService como singleton lazy."""
        if not hasattr(self, '_simulation_service') or self._simulation_service is None:
            from domain.services.simulation_service import SimulationService
            self._simulation_service = SimulationService()
            logger.debug("SimulationService creado (singleton)")
        return self._simulation_service

    # ============================================================================
    # SERVICIOS ADICIONALES - Lazy singletons
    # ============================================================================

    @property
    def hydrology_service(self):
        """Obtiene HydrologyService como singleton lazy."""
        if not hasattr(self, '_hydrology_service') or self._hydrology_service is None:
            from domain.services.hydrology_service import HydrologyService
            self._hydrology_service = HydrologyService()
            logger.debug("HydrologyService creado (singleton)")
        return self._hydrology_service

    @property
    def agent_ia(self):
        """Obtiene AgentIA como singleton lazy."""
        if not hasattr(self, '_agent_ia') or self._agent_ia is None:
            from domain.services.ai_service import AgentIA
            self._agent_ia = AgentIA()
            logger.debug("AgentIA creado (singleton)")
        return self._agent_ia

    @property
    def news_service(self):
        """Obtiene NewsService como singleton lazy."""
        if not hasattr(self, '_news_service') or self._news_service is None:
            from domain.services.news_service import NewsService
            from core.config import settings as _s
            self._news_service = NewsService(api_key=_s.GNEWS_API_KEY or None)
            logger.debug("NewsService creado (singleton)")
        return self._news_service

    @property
    def restrictions_service(self):
        """Obtiene RestrictionsService como singleton lazy."""
        if not hasattr(self, '_restrictions_service') or self._restrictions_service is None:
            from domain.services.restrictions_service import RestrictionsService
            self._restrictions_service = RestrictionsService(repo=self.get_metrics_repository())
            logger.debug("RestrictionsService creado (singleton)")
        return self._restrictions_service

    @property
    def losses_service(self):
        """Obtiene LossesService como singleton lazy."""
        if not hasattr(self, '_losses_service') or self._losses_service is None:
            from domain.services.losses_service import LossesService
            self._losses_service = LossesService(repo=self.get_metrics_repository())
            logger.debug("LossesService creado (singleton)")
        return self._losses_service

    @property
    def indicators_service(self):
        """Obtiene IndicatorsService como singleton lazy."""
        if not hasattr(self, '_indicators_service') or self._indicators_service is None:
            from domain.services.indicators_service import IndicatorsService
            self._indicators_service = IndicatorsService()
            logger.debug("IndicatorsService creado (singleton)")
        return self._indicators_service

    @property
    def executive_report_service(self):
        """Obtiene ExecutiveReportService como singleton lazy."""
        if not hasattr(self, '_executive_report_service') or self._executive_report_service is None:
            from domain.services.executive_report_service import ExecutiveReportService
            self._executive_report_service = ExecutiveReportService()
            logger.debug("ExecutiveReportService creado (singleton)")
        return self._executive_report_service

    @property
    def intelligent_analysis_service(self):
        """Obtiene IntelligentAnalysisService como singleton lazy."""
        if not hasattr(self, '_intelligent_analysis_service') or self._intelligent_analysis_service is None:
            from domain.services.intelligent_analysis_service import IntelligentAnalysisService
            self._intelligent_analysis_service = IntelligentAnalysisService()
            logger.debug("IntelligentAnalysisService creado (singleton)")
        return self._intelligent_analysis_service

    @property
    def predictions_extended_service(self):
        """Obtiene PredictionsService (extended/ML) como singleton lazy."""
        if not hasattr(self, '_predictions_extended_service') or self._predictions_extended_service is None:
            from domain.services.predictions_service_extended import PredictionsService
            self._predictions_extended_service = PredictionsService(
                repo=self.get_predictions_repository(),
                metrics_repo=self.get_metrics_repository(),
            )
            logger.debug("PredictionsService (extended) creado (singleton)")
        return self._predictions_extended_service

    # ============================================================================
    # ORCHESTRATOR SERVICE - Singleton pesado (4.197 líneas, 7 sub-servicios)
    # ============================================================================
    
    def get_orchestrator_service(self):
        """Obtiene ChatbotOrchestratorService como singleton lazy."""
        if not hasattr(self, '_orchestrator_service') or self._orchestrator_service is None:
            from domain.services.orchestrator_service import ChatbotOrchestratorService
            self._orchestrator_service = ChatbotOrchestratorService()
            logger.debug("ChatbotOrchestratorService creado (singleton)")
        return self._orchestrator_service
    
    # ============================================================================
    # OVERRIDES - Para testing con mocks
    # ============================================================================
    
    def override_metrics_repository(self, repository: IMetricsRepository) -> None:
        """Override para testing - permite inyectar mock."""
        self._metrics_repository = repository
        logger.debug("MetricsRepository overridden")
    
    def override_commercial_repository(self, repository: ICommercialRepository) -> None:
        """Override para testing - permite inyectar mock."""
        self._commercial_repository = repository
        logger.debug("CommercialRepository overridden")
    
    def override_distribution_repository(self, repository: IDistributionRepository) -> None:
        """Override para testing - permite inyectar mock."""
        self._distribution_repository = repository
        logger.debug("DistributionRepository overridden")
    
    def override_transmission_repository(self, repository: ITransmissionRepository) -> None:
        """Override para testing - permite inyectar mock."""
        self._transmission_repository = repository
        logger.debug("TransmissionRepository overridden")
    
    def override_xm_datasource(self, datasource: IXMDataSource) -> None:
        """Override para testing - permite inyectar mock."""
        self._xm_datasource = datasource
        logger.debug("XMDataSource overridden")
    
    # ============================================================================
    # RESET - Para limpiar estado entre tests
    # ============================================================================
    
    def reset(self) -> None:
        """Resetea todas las dependencias (útil para testing)."""
        self._metrics_repository = None
        self._commercial_repository = None
        self._distribution_repository = None
        self._transmission_repository = None
        self._predictions_repository = None
        self._database_manager = None
        self._xm_datasource = None
        self._orchestrator_service = None
        self._cu_service = None
        self._losses_nt_service = None
        self._simulation_service = None
        self._hydrology_service = None
        self._agent_ia = None
        self._news_service = None
        self._restrictions_service = None
        self._losses_service = None
        self._indicators_service = None
        self._executive_report_service = None
        self._intelligent_analysis_service = None
        self._predictions_extended_service = None
        logger.debug("DependencyContainer reseteado")


# ============================================================================
# INSTANCIA GLOBAL (Singleton)
# ============================================================================

# Instancia global del contenedor para uso en la aplicación
container = DependencyContainer()


# ============================================================================
# FUNCIONES DE CONVENIENCIA
# ============================================================================

def get_generation_service() -> GenerationService:
    """Función de conveniencia para obtener GenerationService."""
    return container.get_generation_service()


def get_metrics_service() -> MetricsService:
    """Función de conveniencia para obtener MetricsService."""
    return container.get_metrics_service()


def get_commercial_service() -> CommercialService:
    """Función de conveniencia para obtener CommercialService."""
    return container.get_commercial_service()


def get_distribution_service() -> DistributionService:
    """Función de conveniencia para obtener DistributionService."""
    return container.get_distribution_service()


def get_transmission_service() -> TransmissionService:
    """Función de conveniencia para obtener TransmissionService."""
    return container.get_transmission_service()


def get_cu_service() -> CUService:
    """Función de conveniencia para obtener CUService."""
    return container.get_cu_service()


def get_losses_nt_service():
    """Función de conveniencia para obtener LossesNTService."""
    return container.losses_nt_service


def get_simulation_service():
    """Función de conveniencia para obtener SimulationService."""
    return container.simulation_service


def get_hydrology_service():
    """Función de conveniencia para obtener HydrologyService."""
    return container.hydrology_service


def get_agent_ia():
    """Función de conveniencia para obtener AgentIA."""
    return container.agent_ia


def get_news_service():
    """Función de conveniencia para obtener NewsService."""
    return container.news_service


def get_restrictions_service():
    """Función de conveniencia para obtener RestrictionsService."""
    return container.restrictions_service


def get_losses_service():
    """Función de conveniencia para obtener LossesService."""
    return container.losses_service


def get_indicators_service():
    """Función de conveniencia para obtener IndicatorsService."""
    return container.indicators_service


def get_executive_report_service():
    """Función de conveniencia para obtener ExecutiveReportService."""
    return container.executive_report_service


def get_intelligent_analysis_service():
    """Función de conveniencia para obtener IntelligentAnalysisService."""
    return container.intelligent_analysis_service


def get_predictions_extended_service():
    """Función de conveniencia para obtener PredictionsService (extended/ML)."""
    return container.predictions_extended_service
