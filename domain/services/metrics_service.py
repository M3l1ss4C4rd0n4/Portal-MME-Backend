"""
Servicio de dominio para métricas
Lógica de negocio que usa repositorios
"""

from typing import Optional, List, Dict, Any
import pandas as pd

from infrastructure.database.repositories.metrics_repository import MetricsRepository


class MetricsService:
    """Servicio de métricas"""
    
    def __init__(self, repo: Optional[MetricsRepository] = None):
        self.repo = repo or MetricsRepository()
    
    def get_latest_date(self) -> Optional[str]:
        """Obtiene la fecha más reciente de datos"""
        return self.repo.get_latest_date()
    
    def get_total_records(self) -> int:
        """Total de registros en metrics"""
        return self.repo.get_total_records()
    
    def list_metrics(self) -> List[Dict[str, Any]]:
        """Lista métricas disponibles"""
        return self.repo.list_metrics()
    
    def get_metric_series(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Serie temporal de una métrica"""
        return self.repo.get_metric_data(metric_id, start_date, end_date, limit)
    
    def get_metrics_summary(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Resumen de métricas en un rango"""
        return self.repo.get_metrics_summary(start_date, end_date)
