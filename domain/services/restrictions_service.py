from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
from infrastructure.database.repositories.metrics_repository import MetricsRepository
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
        
        CORRECCIÓN: Las restricciones se almacenan en Millones COP.
        Filtramos por unidad='Millones COP' para valores monetarios.
        
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
                # Obtener datos SOLO desde PostgreSQL (arquitectura robusta)
                # Para restricciones, filtrar unidad='Millones COP'
                df = self.repo.get_metric_data(
                    metric_id, 
                    start_date, 
                    end_date, 
                    unit='Millones COP'
                )
                
                if df is None or df.empty:
                    logger.warning(f"⚠️ {metric_id}: Sin datos con unit='Millones COP', probando sin filtro...")
                    # Consultar sin filtro de unidad
                    df = self.repo.get_metric_data(metric_id, start_date, end_date)
                    
                    if df is not None and not df.empty:
                        # Filtrar manualmente si existe columna unidad
                        if 'unidad' in df.columns:
                            df = df[df['unidad'].isin(['Millones COP', 'COP'])]
                            logger.info(f"✅ {metric_id}: Filtrado manual, {len(df)} registros")
                        else:
                            logger.warning(f"⚠️ {metric_id}: Sin columna 'unidad', asumiendo Millones COP")
                
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
                        
                        df = self.repo.get_metric_data(metric_id, new_start, new_end, unit='Millones COP')
                    
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

    def get_restrictions_data(self, start_date, end_date, restriction_type: Optional[str] = None) -> pd.DataFrame:
        """
        Obtiene datos de restricciones operativas.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            restriction_type: Tipo de restricción (opcional: 'generation', 'network', 'security')
        
        Returns:
            DataFrame con columnas: fecha, tipo, restricciones (GWh), costo_mcop
        """
        try:
            from datetime import date as date_type
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_str = start_date.strftime('%Y-%m-%d')
            else:
                start_str = str(start_date)
            
            if isinstance(end_date, date_type):
                end_str = end_date.strftime('%Y-%m-%d')
            else:
                end_str = str(end_date)
            
            # Obtener análisis de restricciones
            data = self.get_restrictions_analysis(start_str, end_str)
            
            # Consolidar diferentes tipos de restricciones
            resultados = []
            
            for metric_id, df in data.items():
                if df is not None and not df.empty:
                    # Normalizar si es necesario
                    if 'Date' in df.columns and 'Value' in df.columns:
                        temp_df = pd.DataFrame()
                        temp_df['fecha'] = df['Date']
                        temp_df['restricciones'] = df['Value']
                        temp_df['tipo'] = metric_id
                        
                        # Intentar obtener costos si están disponibles (en Millones COP)
                        try:
                            df_costo = self.repo.get_metric_data(
                                metric_id, start_str, end_str, 
                                unit='Millones COP', entity='Sistema'
                            )
                            if df_costo is not None and not df_costo.empty:
                                df_costo = self._metrics_service._normalize_time_series(df_costo)
                                merged = pd.merge(temp_df, df_costo[['Date', 'Value']], 
                                                left_on='fecha', right_on='Date', how='left')
                                temp_df['costo_mcop'] = merged['Value']  # Ya en Millones COP
                            else:
                                temp_df['costo_mcop'] = None
                        except:
                            temp_df['costo_mcop'] = None
                        
                        resultados.append(temp_df)
            
            if not resultados:
                logger.warning("⚠️ No hay datos de restricciones")
                return pd.DataFrame()
            
            # Concatenar todos los resultados
            resultado_final = pd.concat(resultados, ignore_index=True)
            
            # Filtrar por tipo si se especifica
            if restriction_type:
                # Mapeo simple de tipos
                tipo_map = {
                    'generation': 'RestAliv',
                    'network': 'RestSinAliv',
                    'security': 'RespComerAGC'
                }
                tipo_filtro = tipo_map.get(restriction_type)
                if tipo_filtro:
                    resultado_final = resultado_final[resultado_final['tipo'] == tipo_filtro]
            
            logger.info(f"✅ {len(resultado_final)} registros de restricciones obtenidos")
            return resultado_final
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo restricciones: {e}")
            return pd.DataFrame()
