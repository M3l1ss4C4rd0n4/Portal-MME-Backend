"""
Repositorio para predicciones de machine learning.
Implementa IPredictionsRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

from typing import Optional, List
from datetime import date
import pandas as pd
import logging
from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IPredictionsRepository

logger = logging.getLogger(__name__)


class PredictionsRepository(BaseRepository, IPredictionsRepository):
    """
    Repositorio para tabla predictions.
    Implementa IPredictionsRepository para cumplir con arquitectura limpia.
    """
    
    def get_latest_prediction_date(self) -> Optional[str]:
        query = "SELECT MAX(fecha_prediccion) as max_date FROM predictions"
        row = self.execute_query_one(query)
        return row["max_date"] if row and row.get("max_date") else None
    
    def get_predictions(self, metric_id: str, start_date: str, end_date: Optional[str] = None):
        if end_date:
            query = """
                SELECT fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior, confianza
                FROM predictions
                WHERE fuente = %s AND fecha_prediccion BETWEEN %s AND %s
                ORDER BY fecha_prediccion ASC
            """
            params = (metric_id, start_date, end_date)
        else:
            query = """
                SELECT fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior, confianza
                FROM predictions
                WHERE fuente = %s AND fecha_prediccion >= %s
                ORDER BY fecha_prediccion ASC
            """
            params = (metric_id, start_date)
        
        return self.execute_dataframe(query, params)
    
    def count_predictions(self) -> int:
        query = "SELECT COUNT(*) as count FROM predictions"
        row = self.execute_query_one(query)
        return int(row["count"]) if row else 0
    
    # Métodos adicionales para cumplir con IPredictionsRepository
    
    def save_predictions(
        self,
        metric: str,
        model_name: str,
        predictions_df: pd.DataFrame
    ) -> int:
        """
        Guarda predicciones generadas por un modelo.
        Implementa método requerido por IPredictionsRepository.
        """
        if predictions_df.empty:
            return 0
        
        query = """
            INSERT INTO predictions 
            (fuente, modelo, fecha_prediccion, valor_gwh_predicho, intervalo_inferior, intervalo_superior, fecha_actualizacion)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (fuente, modelo, fecha_prediccion) 
            DO UPDATE SET 
                valor_gwh_predicho = EXCLUDED.valor_gwh_predicho,
                intervalo_inferior = EXCLUDED.intervalo_inferior,
                intervalo_superior = EXCLUDED.intervalo_superior,
                fecha_actualizacion = NOW()
        """
        
        try:
            records = []
            for _, row in predictions_df.iterrows():
                records.append((
                    metric,
                    model_name,
                    row.get('fecha_prediccion', row.get('fecha')),
                    row.get('valor_gwh_predicho', row.get('yhat')),
                    row.get('intervalo_inferior', row.get('yhat_lower')),
                    row.get('intervalo_superior', row.get('yhat_upper'))
                ))
            
            inserted = 0
            for record in records:
                self.execute_non_query(query, record)
                inserted += 1
            
            logger.info(f"✅ Guardadas {inserted} predicciones para {metric} ({model_name})")
            return inserted
        
        except Exception as e:
            logger.error(f"❌ Error guardando predicciones: {e}")
            return 0
    
    def get_available_metrics(self) -> List[str]:
        """
        Lista métricas con predicciones disponibles.
        Implementa método requerido por IPredictionsRepository.
        """
        query = "SELECT DISTINCT fuente FROM predictions ORDER BY fuente"
        try:
            df = self.execute_dataframe(query)
            return df['fuente'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Error obteniendo métricas: {e}")
            return []
    
    def get_available_models(self, metric: str) -> List[str]:
        """
        Lista modelos disponibles para una métrica.
        Implementa método requerido por IPredictionsRepository.
        """
        query = "SELECT DISTINCT modelo FROM predictions WHERE fuente = %s ORDER BY modelo"
        try:
            df = self.execute_dataframe(query, (metric,))
            return df['modelo'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Error obteniendo modelos: {e}")
            return []
    
    def delete_predictions(
        self,
        metric: str,
        model_name: Optional[str] = None
    ) -> int:
        """
        Elimina predicciones (útil para reentrenamiento).
        Implementa método requerido por IPredictionsRepository.
        """
        if model_name:
            query = "DELETE FROM predictions WHERE fuente = %s AND modelo = %s"
            params = (metric, model_name)
        else:
            query = "DELETE FROM predictions WHERE fuente = %s"
            params = (metric,)
        
        try:
            result = self.execute_non_query(query, params)
            logger.info(f"🗑️ Eliminadas predicciones para {metric}" + (f" ({model_name})" if model_name else ""))
            return result
        except Exception as e:
            logger.error(f"Error eliminando predicciones: {e}")
            return 0
