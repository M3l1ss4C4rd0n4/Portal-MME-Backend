"""
Repositorio para métricas energéticas
"""

from typing import List, Optional, Dict, Any
from infrastructure.database.repositories.base_repository import BaseRepository


class MetricsRepository(BaseRepository):
    """Repositorio para tabla metrics y métricas relacionadas"""
    
    def get_total_records(self) -> int:
        query = "SELECT COUNT(*) as count FROM metrics"
        row = self.execute_query_one(query)
        return int(row["count"]) if row else 0
    
    def get_latest_date(self) -> Optional[str]:
        query = "SELECT MAX(fecha) as max_date FROM metrics"
        row = self.execute_query_one(query)
        return row["max_date"] if row and row.get("max_date") else None
    
    def get_metric_data(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ):
        """
        Obtiene serie temporal de una métrica
        """
        if end_date:
            query = """
                SELECT fecha, valor_gwh
                FROM metrics
                WHERE metrica = ? AND fecha BETWEEN ? AND ?
                ORDER BY fecha ASC
            """
            params = (metric_id, start_date, end_date)
        else:
            query = """
                SELECT fecha, valor_gwh
                FROM metrics
                WHERE metrica = ? AND fecha >= ?
                ORDER BY fecha ASC
            """
            params = (metric_id, start_date)
        
        if limit:
            query += " LIMIT ?"
            params = params + (limit,)
        
        return self.execute_dataframe(query, params)
    
    def list_metrics(self) -> List[Dict[str, Any]]:
        query = "SELECT DISTINCT metrica FROM metrics ORDER BY metrica"
        return self.execute_query(query)
    
    def get_metrics_summary(self, start_date: str, end_date: str):
        query = """
             SELECT metrica, COUNT(*) as records,
                 MIN(fecha) as min_date, MAX(fecha) as max_date
            FROM metrics
             WHERE fecha BETWEEN ? AND ?
             GROUP BY metrica
            ORDER BY records DESC
        """
        return self.execute_dataframe(query, (start_date, end_date))
