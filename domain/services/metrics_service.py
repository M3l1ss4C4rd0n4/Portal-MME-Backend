"""
Servicio de dominio para métricas
Lógica de negocio que usa repositorios
"""

from typing import Optional, List, Dict, Any
import pandas as pd
from datetime import date, datetime

from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.external import xm_service


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
        """Lista métricas disponibles en BD"""
        return self.repo.list_metrics()
    
    def _normalize_time_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza las columnas de un DataFrame de series temporales.
        Garantiza que existan 'Date' y 'Value'.
        
        Args:
            df (pd.DataFrame): DataFrame original (puede venir de SQLite o API XM)
            
        Returns:
            pd.DataFrame: DataFrame normalizado con columnas Date y Value
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=['Date', 'Value'])
        
        logger = self.repo.logger if hasattr(self.repo, 'logger') else None
        
        # 1. Normalizar nombres de columnas (mapa de variantes comunes)
        col_map = {
            'fecha': 'Date',
            'date': 'Date',
            'Fecha': 'Date',
            'valor_gwh': 'Value',
            'valor': 'Value',
            'value': 'Value',
            'Valor': 'Value',
            'Values': 'Value'
        }
        
        # Renombrar columnas existentes
        df = df.rename(columns=col_map)
        
        # 2. Validar existencia de columnas obligatorias
        if 'Date' not in df.columns or 'Value' not in df.columns:
            # Caso especial: a veces la API devuelve 'Values_code' o similar, pero si no hay Value claro
            # intentamos inferir o loggear error.
            # Verificamos si solo faltó el rename
            pass
            
        # 3. Asegurar tipos de datos
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        if 'Value' in df.columns:
            df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
            
        # 4. Si después de todo faltan columnas, retornar vacío seguro
        if 'Date' not in df.columns or 'Value' not in df.columns:
            print(f"⚠️ [MetricsService] Error de normalización: columnas faltantes. Disponible: {df.columns.tolist()}")
            return pd.DataFrame(columns=['Date', 'Value'])
            
        return df

    def get_metrics_metadata(self) -> pd.DataFrame:
        """
        Obtiene metadatos de todas las métricas disponibles (desde XM API o caché).
        Retorna DataFrame con columnas: MetricId, MetricName, Entity, etc.
        """
        api = xm_service.get_objetoAPI()
        if api:
            return api.get_collections()
        return pd.DataFrame()

    def get_metric_series_hybrid(
        self,
        metric_id: str,
        entity: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Obtiene serie temporal intentando primero DB y luego API XM si es necesario.
        """
        # 1. Intentar DB primero (rápido)
        try:
            df = self.repo.get_metric_data_by_entity(metric_id, entity, start_date, end_date)
            
            if df is not None and not df.empty:
                # Normalizar usando la función interna
                df_norm = self._normalize_time_series(df)
                if not df_norm.empty:
                    # CRITICO: Marcar que ya está en GWh restaurando la columna 'valor_gwh'
                    # Esto evita que el frontend divida por 1,000,000 nuevamente
                    df_norm['valor_gwh'] = df_norm['Value']
                    return df_norm
        except Exception as e:
            print(f"⚠️ [MetricsService] Error consultando SQLite: {e}")
        
        # 2. Fallback API XM
        # Para mantener consistencia con "fetch_metric_data" que devuelve formato API:
        df = xm_service.fetch_metric_data(metric_id, entity, start_date, end_date)
        return self._normalize_time_series(df)
    
    def get_metric_series_by_entity(
        self,
        metric_id: str,
        entity: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Obtiene datos filtrados por entidad (ej: Gene, Recurso) desde DB"""
        df = self.repo.get_metric_data_by_entity(metric_id, entity, start_date, end_date)
        return self._normalize_time_series(df)

    def get_agent_statistics(self) -> pd.DataFrame:
        """Obtiene estadísticas de agentes"""
        return self.repo.get_agent_statistics()

    def get_hourly_data(self, metric_id: str, entity_type: str, date_str: str) -> pd.DataFrame:
        """Obtiene datos horarios"""
        return self.repo.get_hourly_data(metric_id, entity_type, date_str)

    def get_metric_series(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Serie temporal de una métrica"""
        df = self.repo.get_metric_data(metric_id, start_date, end_date, limit)
        return self._normalize_time_series(df)

    def get_multiple_metrics_history(
        self, 
        metrics_list: List[str], 
        start_date: str, 
        end_date: str
    ) -> pd.DataFrame:
        """
        Obtiene histórico para múltiples métricas (optimizado)
        """
        return self.repo.get_metrics_history_by_list(metrics_list, start_date, end_date)
    
    def get_metrics_summary(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Resumen de métricas en un rango"""
        return self.repo.get_metrics_summary(start_date, end_date)

# Compatibility wrapper
def get_metric_data(metric_id: str, start_date: str, end_date: Optional[str] = None):
    service = MetricsService()
    return service.get_metric_series(metric_id, start_date, end_date)
