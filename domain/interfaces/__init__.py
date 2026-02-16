"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                        DOMAIN INTERFACES (PORTS)                              ║
║                                                                               ║
║  Arquitectura Hexagonal - Puertos para invertir dependencias                 ║
║  Domain NO depende de Infrastructure, sino de estas abstracciones            ║
║                                                                               ║
║  Referencias:                                                                 ║
║  - Clean Architecture (Robert C. Martin)                                      ║
║  - Hexagonal Architecture (Alistair Cockburn)                                ║
║  - Dependency Inversion Principle (SOLID)                                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

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
