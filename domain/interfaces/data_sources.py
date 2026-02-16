"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                   DATA SOURCE INTERFACES (PORTS)                              ║
║                                                                               ║
║  Interfaces para acceso a fuentes de datos externas                          ║
║  Permite intercambiar implementaciones sin afectar el dominio                ║
║                                                                               ║
║  Implementaciones concretas: infrastructure/external/                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import date, datetime
import pandas as pd


class IXMDataSource(ABC):
    """
    Interface para acceso a datos de XM (operador del mercado eléctrico).
    Abstrae la implementación específica de pydataxm o cualquier otra librería.
    """
    
    @abstractmethod
    def fetch_metric_data(
        self,
        metric: str,
        entity: str,
        start_date: date,
        end_date: date
    ) -> Optional[pd.DataFrame]:
        """
        Consulta datos de una métrica específica.
        
        Args:
            metric: Código de métrica (ej: 'Gene', 'PrecBolsNaci')
            entity: Entidad (ej: 'Sistema', 'Recurso', 'Embalse')
            start_date: Fecha inicial
            end_date: Fecha final
            
        Returns:
            DataFrame con los datos o None si no hay datos
        """
        pass
    
    @abstractmethod
    def get_api_object(self) -> Optional[Any]:
        """
        Obtiene el objeto API subyacente para operaciones avanzadas.
        Útil para casos especiales donde se necesita acceso directo.
        
        Returns:
            Objeto API (ej: ReadDB de pydataxm) o None si no está disponible
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Verifica si la fuente de datos está disponible.
        
        Returns:
            True si la API está disponible y funcional
        """
        pass
    
    @abstractmethod
    def fetch_catalog(self, catalog_name: str) -> Optional[pd.DataFrame]:
        """
        Obtiene un catálogo de XM (ListadoRecursos, ListadoEmbalses, etc.).
        
        Args:
            catalog_name: Nombre del catálogo
            
        Returns:
            DataFrame con el catálogo o None si no está disponible
        """
        pass


class ISIMEMDataSource(ABC):
    """
    Interface para acceso a datos del SIMEM (Sistema de Información del Mercado).
    Abstrae la implementación específica de pydatasimem.
    """
    
    @abstractmethod
    def fetch_transmission_lines(self, days_back: int = 7) -> Optional[pd.DataFrame]:
        """
        Consulta líneas de transmisión del SIMEM.
        
        Args:
            days_back: Días hacia atrás a consultar
            
        Returns:
            DataFrame con líneas de transmisión
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Verifica si el servicio SIMEM está disponible"""
        pass
