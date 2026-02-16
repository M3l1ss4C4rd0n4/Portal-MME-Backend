"""
Servicio de dominio para métricas.
Lógica de negocio que usa repositorios.
Implementa Inyección de Dependencias (Arquitectura Limpia - Fase 3)
"""

from typing import Optional, List, Dict, Any
import pandas as pd
from datetime import date, datetime

from domain.interfaces.repositories import IMetricsRepository
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MetricsService:
    """
    Servicio de métricas con inyección de dependencias.
    Depende de IMetricsRepository (interfaz), no de implementación concreta.
    """
    
    def __init__(self, repository: Optional[IMetricsRepository] = None):
        """
        Inicializa el servicio con inyección de dependencias opcional.
        
        Args:
            repository: Implementación de IMetricsRepository. 
                       Si es None, usa MetricsRepository() por defecto.
        """
        self.repo = repository if repository is not None else MetricsRepository()
    
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
        
        # 2. Caso especial: Datos horarios de API XM (Values_Hour01, Values_Hour02, etc)
        if 'Date' in df.columns and 'Value' not in df.columns:
            hour_cols = [col for col in df.columns if col.startswith('Values_Hour')]
            if hour_cols:
                # Calcular promedio de todas las horas como 'Value'
                df['Value'] = df[hour_cols].mean(axis=1)
        
        # 3. Validar existencia de columnas obligatorias
        if 'Date' not in df.columns or 'Value' not in df.columns:
            print(f"⚠️ [MetricsService] Error de normalización: columnas faltantes. Disponible: {df.columns.tolist()}")
            return pd.DataFrame(columns=['Date', 'Value'])
            
        # 4. Asegurar tipos de datos
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        if 'Value' in df.columns:
            df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
            
        return df

    def get_metrics_metadata(self) -> pd.DataFrame:
        """
        Obtiene metadatos de todas las métricas disponibles desde PostgreSQL.
        Retorna DataFrame con columnas compatibles: MetricId, MetricName, Entity
        """
        # Consultar métricas únicas en la base de datos
        query = """
            SELECT DISTINCT 
                metrica as "MetricId",
                metrica as "MetricName",
                entidad as "Entity",
                COUNT(*) as "RecordCount"
            FROM metrics
            GROUP BY metrica, entidad
            ORDER BY metrica, entidad;
        """
        try:
            df = self.repo.execute_dataframe(query)
            return df
        except Exception as e:
            logger.error(f"Error obteniendo metadata de métricas: {e}")
            return pd.DataFrame()

    def get_metric_series_hybrid(
        self,
        metric_id: str,
        entity: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Obtiene serie temporal SOLO desde PostgreSQL (arquitectura robusta).
        Eliminado fallback a API - todos los datos deben estar en BD.
        """
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
            
            # Si no hay datos, retornar DataFrame vacío
            logger.warning(f"⚠️ No hay datos en PostgreSQL para {metric_id}/{entity} ({start_date} a {end_date})")
            return pd.DataFrame(columns=['Date', 'Value'])
            
        except Exception as e:
            logger.error(f"❌ [MetricsService] Error consultando PostgreSQL: {e}")
            return pd.DataFrame(columns=['Date', 'Value'])
    
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
