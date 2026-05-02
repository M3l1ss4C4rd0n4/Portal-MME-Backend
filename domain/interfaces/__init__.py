# Importar todas las interfaces para facilitar su uso
from domain.interfaces.repositories import (
    IMetricsRepository,
    ICommercialRepository,
    IDistributionRepository,
    ITransmissionRepository,
    IPredictionsRepository,
)

from domain.interfaces.data_sources import (
    IXMDataSource,
    ISIMEMDataSource,
)

from domain.interfaces.database import (
    IDatabaseManager,
    IConnectionManager,
)

# Exportar todo
__all__ = [
    # Repositories
    "IMetricsRepository",
    "ICommercialRepository",
    "IDistributionRepository",
    "ITransmissionRepository",
    "IPredictionsRepository",
    # Data Sources
    "IXMDataSource",
    "ISIMEMDataSource",
    # Database
    "IDatabaseManager",
    "IConnectionManager",
]
