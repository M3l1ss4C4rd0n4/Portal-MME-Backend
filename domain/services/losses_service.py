from typing import Optional, List, Dict, Any
import pandas as pd
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.external import xm_service
from domain.services.metrics_service import MetricsService

class LossesService:
    """
    Servicio de dominio para Pérdidas
    Maneja la lógica de negocio relacionada con pérdidas de energía
    """
    
    def __init__(self, repo: Optional[MetricsRepository] = None):
        self.repo = repo or MetricsRepository()
        self._metrics_service = MetricsService(self.repo)
        
    def get_losses_analysis(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        Obtiene los datos para análisis de pérdidas.
        Retorna diccionario con DataFrames de:
        - Totales
        - Reguladas
        - No Reguladas
        - Generación referencia
        """
        metrics = [
            'PerdidasEner', 
            'PerdidasEnerReg',
            'PerdidasEnerNoReg',
            'Gene' # Referencia para calcular porcentajes
        ]
        
        result = {}
        
        for metric_id in metrics:
            try:
                # 1. DB Check - Use unit='GWh' to avoid duplicates if specific unit known
                # Para pérdidas, la unidad estándar es GWh. Si hay COP mezclado, esto lo filtrará.
                # Además filtramos por 'Sistema' para evitar datos desgregados por planta
                df = self.repo.get_metric_data(metric_id, start_date, end_date, unit='GWh', entity='Sistema')
                
                # 2. API Fallback
                if df is None or df.empty:
                    df = xm_service.fetch_metric_data(metric_id, 'Sistema', start_date, end_date)
                
                # 3. Normalización Consistente (Date, Value)
                df = self._metrics_service._normalize_time_series(df)
                
                result[metric_id] = df
                
            except Exception as e:
                print(f"Error fetching losses metric {metric_id}: {e}")
                result[metric_id] = pd.DataFrame(columns=['Date', 'Value'])
                
        return result

    def get_losses_indicators(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Calcula indicadores clave (ej: % de pérdidas vs generación)
        """
        data = self.get_losses_analysis(start_date, end_date)
        
        perdidas = data.get('PerdidasEner')
        generacion = data.get('Gene')
        
        if perdidas is None or perdidas.empty or generacion is None or generacion.empty:
            return pd.DataFrame()
            
        # Merge por fecha (usando columnas normalizadas 'Date')
        merged = pd.merge(
            perdidas, 
            generacion, 
            on='Date', 
            suffixes=('_loss', '_gen')
        )
        
        # Calcular porcentaje (Value_loss / Value_gen)
        merged['percentage'] = (merged['Value_loss'] / merged['Value_gen']) * 100
        return merged
