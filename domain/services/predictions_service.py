"""
Servicio de dominio para predicciones
"""

from typing import Optional
import pandas as pd

from infrastructure.database.repositories.predictions_repository import PredictionsRepository


class PredictionsService:
    """Servicio de predicciones"""
    
    def __init__(self, repo: Optional[PredictionsRepository] = None):
        self.repo = repo or PredictionsRepository()
    
    def get_latest_prediction_date(self) -> Optional[str]:
        """Fecha más reciente de predicciones"""
        return self.repo.get_latest_prediction_date()
    
    def count_predictions(self) -> int:
        """Total de predicciones"""
        return self.repo.count_predictions()
    
    def get_predictions(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """Obtiene predicciones para una fuente"""
        return self.repo.get_predictions(metric_id, start_date, end_date)
