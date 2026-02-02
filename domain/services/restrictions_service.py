from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.external import xm_service
from infrastructure.logging.logger import get_logger
# Importar MetricsService para reusar normalización
from domain.services.metrics_service import MetricsService

logger = get_logger(__name__)

class RestrictionsService:
    """
    Servicio de dominio para Restricciones
    Maneja la lógica de negocio relacionada con restricciones operativas
    """
    
    def __init__(self, repo: Optional[MetricsRepository] = None):
        self.repo = repo or MetricsRepository()
        # Instancia de MetricsService para acceder a utilidades
        self._metrics_service = MetricsService(self.repo)
        
    def get_restrictions_analysis(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        Obtiene los datos consolidados para el análisis de restricciones.
        
        CORRECCIÓN CRÍTICA: Las restricciones vienen en COP (pesos) Y GWh.
        Debemos filtrar por unidad='COP' para valores monetarios.
        
        Returns:
            Diccionario con DataFrames para:
            - RestAliv: Restricciones Aliviadas
            - RestSinAliv: Restricciones No Aliviadas
            - RespComerAGC: Reconciliación AGC
        """
        # Definir métricas clave
        metrics = {
            'RestAliv': 'Restricciones Aliviadas',
            'RestSinAliv': 'Restricciones No Aliviadas',
            'RespComerAGC': 'Reconciliación AGC'
        }
        
        result = {}
        
        for metric_id, name in metrics.items():
            try:
                # ✅ FIX APLICADO: Filtrar unidad='COP' con fallback robusto
                df = self.repo.get_metric_data(
                    metric_id, 
                    start_date, 
                    end_date, 
                    unit='COP'  # Intentar primero con filtro COP
                )
                
                if df is None or df.empty:
                    logger.warning(f"⚠️ {metric_id}: Sin datos con unit='COP', probando sin filtro...")
                    # Fallback 1: Consultar sin filtro de unidad
                    df = self.repo.get_metric_data(metric_id, start_date, end_date)
                    
                    if df is not None and not df.empty:
                        # Filtrar manualmente si existe columna unidad
                        if 'unidad' in df.columns:
                            df = df[df['unidad'].str.upper() == 'COP']
                            logger.info(f"✅ {metric_id}: Filtrado manual, {len(df)} registros COP")
                        else:
                            logger.warning(f"⚠️ {metric_id}: Sin columna 'unidad', asumiendo COP")
                    else:
                        # Fallback 2: Buscar en API XM si no hay datos locales
                        logger.info(f"🔍 {metric_id}: Consultando API XM...")
                        df = xm_service.fetch_metric_data(metric_id, 'Sistema', start_date, end_date)
                        # Normalizar
                        df = self._metrics_service._normalize_time_series(df)
                
                # Validar que no sean todos ceros
                if df is not None and not df.empty:
                    # Si todos los valores son 0, intentar días anteriores
                    if df['valor_gwh'].sum() == 0:
                        logger.warning(f"{metric_id}: Todos los valores son 0, buscando días anteriores")
                        # Intentar 7 días atrás
                        from datetime import datetime, timedelta
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                        new_end = (end_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                        new_start = (end_dt - timedelta(days=7)).strftime('%Y-%m-%d')
                        
                        df = self.repo.get_metric_data(metric_id, new_start, new_end, unit='COP')
                    
                    # ✅ FIX: valor_gwh YA contiene Millones COP (no dividir)
                    # La columna se llama valor_gwh por legacy pero almacena Millones COP
                    if 'valor_gwh' in df.columns:
                        df['valor_cop_millones'] = df['valor_gwh']  # Ya está en Millones
                        # Compatibilidad con callback: renombrar a 'Value' y 'Date'
                        df = df.rename(columns={'valor_gwh': 'Value', 'fecha': 'Date'})
                    
                    df['tipo'] = name
                    
                result[metric_id] = df if df is not None else pd.DataFrame(columns=['fecha', 'valor_gwh'])
                
            except Exception as e:
                logger.error(f"Error fetching {metric_id}: {e}")
                result[metric_id] = pd.DataFrame(columns=['fecha', 'valor_gwh'])
                
        return result

    def get_restrictions_summary(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Calcula el total diario de todas las restricciones"""
        data = self.get_restrictions_analysis(start_date, end_date)
        
        frames = []
        for key, df in data.items():
            if not df.empty:
                frames.append(df)
        
        if not frames:
            return pd.DataFrame()
            
        combined = pd.concat(frames)
        # Usar columna normalizada 'Date' y 'Value'
        if 'Date' in combined.columns and 'Value' in combined.columns:
            return combined.groupby('Date')['Value'].sum().reset_index()
        return pd.DataFrame()
