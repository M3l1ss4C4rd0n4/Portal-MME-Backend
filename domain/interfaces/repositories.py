"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                   REPOSITORY INTERFACES (PORTS)                               ║
║                                                                               ║
║  Interfaces para acceso a datos - Arquitectura Hexagonal                     ║
║  Domain no depende de Infrastructure, sino de estas abstracciones            ║
║                                                                               ║
║  Implementaciones concretas: infrastructure/database/repositories/           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import date
import pandas as pd


class IMetricsRepository(ABC):
    """
    Interface para acceso a métricas energéticas.
    Define el contrato que debe cumplir cualquier implementación.
    """
    
    @abstractmethod
    def get_total_records(self) -> int:
        """Obtiene el total de registros en la tabla de métricas"""
        pass
    
    @abstractmethod
    def get_latest_date(self) -> Optional[str]:
        """Obtiene la fecha más reciente disponible"""
        pass
    
    @abstractmethod
    def get_metric_data(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        unit: Optional[str] = None,
        entity: Optional[str] = None
    ) -> pd.DataFrame:
        """Obtiene serie temporal de una métrica específica"""
        pass
    
    @abstractmethod
    def get_metrics_history_by_list(
        self,
        metrics_list: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Obtiene histórico para una lista de métricas"""
        pass
    
    @abstractmethod
    def list_metrics(self) -> List[Dict[str, Any]]:
        """Lista todas las métricas disponibles"""
        pass
    
    @abstractmethod
    def get_metrics_summary(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Obtiene resumen de métricas en un rango de fechas"""
        pass


class ICommercialRepository(ABC):
    """Interface para acceso a datos de comercialización eléctrica"""
    
    @abstractmethod
    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible para una métrica"""
        pass
    
    @abstractmethod
    def fetch_commercial_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente_comprador: Optional[str] = None
    ) -> pd.DataFrame:
        """Consulta métricas de comercialización"""
        pass
    
    @abstractmethod
    def get_agents(self) -> List[str]:
        """Obtiene lista de agentes comerciales"""
        pass
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Obtiene lista de métricas de comercialización disponibles"""
        pass


class IDistributionRepository(ABC):
    """Interface para acceso a datos de distribución eléctrica"""
    
    @abstractmethod
    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible"""
        pass
    
    @abstractmethod
    def fetch_distribution_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        distribuidor: Optional[str] = None
    ) -> pd.DataFrame:
        """Consulta métricas de distribución"""
        pass
    
    @abstractmethod
    def get_distributors(self) -> List[str]:
        """Obtiene lista de distribuidores"""
        pass
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Obtiene lista de métricas de distribución disponibles"""
        pass


class ITransmissionRepository(ABC):
    """Interface para acceso a datos de líneas de transmisión"""
    
    @abstractmethod
    def get_all_lines(self) -> pd.DataFrame:
        """Obtiene todas las líneas de transmisión"""
        pass
    
    @abstractmethod
    def get_lines_by_region(self, region: str) -> pd.DataFrame:
        """Obtiene líneas de transmisión por región"""
        pass
    
    @abstractmethod
    def get_lines_by_voltage(self, voltage: str) -> pd.DataFrame:
        """Obtiene líneas de transmisión por nivel de tensión"""
        pass
    
    @abstractmethod
    def get_total_count(self) -> int:
        """Obtiene el número total de líneas"""
        pass
    
    @abstractmethod
    def get_latest_update(self) -> Optional[str]:
        """Obtiene la fecha de última actualización"""
        pass


class IPredictionsRepository(ABC):
    """Interface para acceso a predicciones de machine learning"""
    
    @abstractmethod
    def save_predictions(
        self,
        metric: str,
        model_name: str,
        predictions_df: pd.DataFrame
    ) -> int:
        """Guarda predicciones generadas por un modelo"""
        pass
    
    @abstractmethod
    def get_predictions(
        self,
        metric: str,
        model_name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """Obtiene predicciones almacenadas"""
        pass
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Lista métricas con predicciones disponibles"""
        pass
    
    @abstractmethod
    def get_available_models(self, metric: str) -> List[str]:
        """Lista modelos disponibles para una métrica"""
        pass
    
    @abstractmethod
    def delete_predictions(
        self,
        metric: str,
        model_name: Optional[str] = None
    ) -> int:
        """Elimina predicciones (útil para reentrenamiento)"""
        pass
