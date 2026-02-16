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
