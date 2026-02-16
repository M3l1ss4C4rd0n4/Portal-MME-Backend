from typing import Optional, List, Dict, Any
import pandas as pd
from infrastructure.database.repositories.metrics_repository import MetricsRepository
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
                # Obtener datos SOLO desde PostgreSQL (arquitectura robusta)
                # Para pérdidas, la unidad estándar es GWh
                # Filtramos por 'Sistema' para evitar datos desgregados por planta
                df = self.repo.get_metric_data(metric_id, start_date, end_date, unit='GWh', entity='Sistema')
                
                # Normalización Consistente (Date, Value)
                if df is not None and not df.empty:
                    df = self._metrics_service._normalize_time_series(df)
                else:
                    df = pd.DataFrame(columns=['Date', 'Value'])
                
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

    def get_losses_data(self, start_date, end_date, loss_type: str = 'total') -> pd.DataFrame:
        """
        Obtiene datos de pérdidas de energía.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            loss_type: Tipo de pérdida ('technical', 'non_technical', 'total')
        
        Returns:
            DataFrame con columnas: fecha, perdidas (GWh), porcentaje
        """
        try:
            from datetime import date as date_type
            import logging
            
            logger = logging.getLogger(__name__)
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_str = start_date.strftime('%Y-%m-%d')
            else:
                start_str = str(start_date)
            
            if isinstance(end_date, date_type):
                end_str = end_date.strftime('%Y-%m-%d')
            else:
                end_str = str(end_date)
            
            # Mapear tipo de pérdida a métrica
            metric_map = {
                'total': 'PerdidasEner',
                'technical': 'PerdidasEnerReg',  # Aproximación
                'non_technical': 'PerdidasEnerNoReg'  # Aproximación
            }
            
            metric_id = metric_map.get(loss_type, 'PerdidasEner')
            
            # Obtener datos de pérdidas
            df = self.repo.get_metric_data(metric_id, start_str, end_str, unit='GWh', entity='Sistema')
            
            if df is None or df.empty:
                logger.warning(f"⚠️ No hay datos de pérdidas tipo {loss_type}")
                return pd.DataFrame()
            
            # Normalizar columnas
            df = self._metrics_service._normalize_time_series(df)
            
            # Renombrar para API
            resultado = pd.DataFrame()
            resultado['fecha'] = df['Date']
            resultado['perdidas'] = df['Value']
            
            # Calcular porcentaje si hay datos de generación
            try:
                df_gen = self.repo.get_metric_data('Gene', start_str, end_str, unit='GWh', entity='Sistema')
                if df_gen is not None and not df_gen.empty:
                    df_gen = self._metrics_service._normalize_time_series(df_gen)
                    merged = pd.merge(resultado, df_gen[['Date', 'Value']], 
                                     left_on='fecha', right_on='Date', how='left')
                    merged['porcentaje'] = (merged['perdidas'] / merged['Value']) * 100
                    resultado['porcentaje'] = merged['porcentaje']
                else:
                    resultado['porcentaje'] = None
            except:
                resultado['porcentaje'] = None
            
            logger.info(f"✅ {len(resultado)} registros de pérdidas obtenidos")
            return resultado
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Error obteniendo pérdidas: {e}")
            return pd.DataFrame()
