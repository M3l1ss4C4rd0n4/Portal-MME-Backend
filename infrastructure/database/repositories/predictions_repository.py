"""
Repositorio para predicciones
"""

from typing import Optional
from infrastructure.database.repositories.base_repository import BaseRepository


class PredictionsRepository(BaseRepository):
    """Repositorio para tabla predictions"""
    
    def get_latest_prediction_date(self) -> Optional[str]:
        query = "SELECT MAX(fecha_prediccion) as max_date FROM predictions"
        row = self.execute_query_one(query)
        return row["max_date"] if row and row.get("max_date") else None
    
    def get_predictions(self, metric_id: str, start_date: str, end_date: Optional[str] = None):
        if end_date:
            query = """
                SELECT fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior
                FROM predictions
                WHERE fuente = ? AND fecha_prediccion BETWEEN ? AND ?
                ORDER BY fecha_prediccion ASC
            """
            params = (metric_id, start_date, end_date)
        else:
            query = """
                SELECT fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior
                FROM predictions
                WHERE fuente = ? AND fecha_prediccion >= ?
                ORDER BY fecha_prediccion ASC
            """
            params = (metric_id, start_date)
        
        return self.execute_dataframe(query, params)
    
    def count_predictions(self) -> int:
        query = "SELECT COUNT(*) as count FROM predictions"
        row = self.execute_query_one(query)
        return int(row["count"]) if row else 0
