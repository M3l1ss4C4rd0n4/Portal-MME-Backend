"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          GENERATION SERVICE - PostgreSQL                      ║
║                                                                               ║
║  Servicio de dominio para gestionar datos de generación eléctrica            ║
║  Migrado completamente a PostgreSQL (tabla: metrics)                         ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import pandas as pd
from datetime import date, timedelta
import logging
from typing import Optional, Tuple

from infrastructure.database.repositories.metrics_repository import MetricsRepository

logger = logging.getLogger(__name__)


class GenerationService:
    """
    Servicio de dominio para gestionar datos de generación eléctrica.
    Actúa como fachada sobre PostgreSQL a través de MetricsRepository.
    """

    def __init__(self):
        self.repo = MetricsRepository()

    def get_daily_generation_system(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Obtiene la generación diaria total del sistema (Gene/Sistema).
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
        
        Returns:
            DataFrame con columnas: fecha, valor_gwh
        """
        try:
            df = self.repo.get_metric_data_by_entity(
                metric_id='Gene',
                entity='Sistema',
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if df is None or df.empty:
                logger.warning(f"⚠️ Sin datos de Gene/Sistema para {start_date} - {end_date}")
                return pd.DataFrame()

            return df[['fecha', 'valor_gwh']]
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo generación diaria sistema: {e}")
            return pd.DataFrame()

    def get_resources_by_type(self, source_type: str = 'EOLICA') -> pd.DataFrame:
        """
        Obtiene listado de recursos (plantas) filtrados por tipo de fuente.
        
        Args:
            source_type: 'HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA', 'TODAS'
        
        Returns:
            DataFrame con columnas: recurso, tipo_clasificado
        """
        try:
            # Obtener recursos únicos de Gene/Recurso
            query = """
                SELECT DISTINCT recurso
                FROM metrics
                WHERE metrica = 'Gene' 
                AND entidad = 'Recurso'
                AND recurso IS NOT NULL
                ORDER BY recurso
            """
            
            df_recursos = self.repo.execute_dataframe(query)
            
            if df_recursos is None or df_recursos.empty:
                logger.warning("⚠️ No se encontraron recursos en PostgreSQL")
                return pd.DataFrame()
            
            # Clasificar recursos por tipo basándose en su código
            df_recursos['tipo_clasificado'] = df_recursos['recurso'].apply(self._classify_resource_type)
            
            # Filtrar por tipo solicitado
            if source_type.upper() == 'TODAS':
                filtered = df_recursos
            else:
                filtered = df_recursos[df_recursos['tipo_clasificado'] == source_type.upper()]
            
            logger.info(f"📋 {len(filtered)} recursos de tipo {source_type} (de {len(df_recursos)} totales)")
            return filtered
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo recursos por tipo: {e}")
            return pd.DataFrame()

    def _classify_resource_type(self, codigo: str) -> str:
        """
        Clasifica un recurso en su tipo de fuente basándose en su código.
        
        Args:
            codigo: Código del recurso (ej: 'GUAVIO1', 'JEPIRACHI', 'TERMOCARTAGENA')
        
        Returns:
            Tipo de fuente: 'HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA'
        """
        codigo_str = str(codigo).upper()
        
        # Patrones de hidráulicas
        hidro_patterns = ['H', 'PCH', 'HIDRA', 'ALTO', 'BETANIA', 'CALIMA', 'GUAVIO', 
                         'PLAYAS', 'JAGUAS', 'URRÁ', 'SAN_CARLOS', 'MIEL', 'PORCE', 
                         'CHIVOR', 'GUATAPE', 'SAN CARLOS', 'RIO GRANDE', 'SALVAJINA']
        if any(p in codigo_str for p in hidro_patterns):
            return 'HIDRAULICA'
        
        # Patrones de eólicas
        eolica_patterns = ['EOL', 'JEPIR', 'GUAJI', 'VECT', 'BETA', 'ALPHA', 'WINDP']
        if any(p in codigo_str for p in eolica_patterns):
            return 'EOLICA'
        
        # Patrones de solares
        solar_patterns = ['SOL', 'FV', 'CELSIA', 'FOTOV', 'SOLAR']
        if any(p in codigo_str for p in solar_patterns):
            return 'SOLAR'
        
        # Patrones de biomasa
        biomasa_patterns = ['BIO', 'COG', 'BIOGAS', 'BAGAZO']
        if any(p in codigo_str for p in biomasa_patterns):
            return 'BIOMASA'
        
        # Por defecto: térmica
        return 'TERMICA'

    def get_aggregated_generation_by_type(self, start_date: date, end_date: date, source_type: str = 'HIDRAULICA') -> pd.DataFrame:
        """
        Obtiene generación agregada para un tipo de fuente específico.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            source_type: Tipo de fuente ('HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA')
        
        Returns:
            DataFrame con columnas: fecha, recurso, valor_gwh, tipo_clasificado, planta
        """
        try:
            # 1. Obtener listado de recursos del tipo
            resources_df = self.get_resources_by_type(source_type)
            if resources_df.empty:
                logger.warning(f"⚠️ No se encontraron recursos de tipo {source_type}")
                return pd.DataFrame()
            
            target_codes = resources_df['recurso'].unique().tolist()
            logger.info(f"📋 {len(target_codes)} recursos de {source_type} para consulta")

            # 2. Obtener datos de generación (Gene/Recurso) para esos recursos
            query = """
                SELECT fecha, recurso, valor_gwh
                FROM metrics
                WHERE metrica = 'Gene'
                AND entidad = 'Recurso'
                AND fecha BETWEEN %s AND %s
                AND recurso IN ({})
                ORDER BY fecha, recurso
            """.format(','.join(['%s'] * len(target_codes)))
            
            params = [start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')] + target_codes
            df_gene = self.repo.execute_dataframe(query, tuple(params))
            
            if df_gene is None or df_gene.empty:
                logger.warning(f"⚠️ Sin datos de generación para {source_type} en {start_date} - {end_date}")
                return pd.DataFrame()

            # 3. Agregar columnas Tipo y Planta
            df_gene['tipo_clasificado'] = df_gene['recurso'].apply(self._classify_resource_type)
            df_gene['planta'] = df_gene['recurso']  # Usar código como nombre por ahora
            
            # Renombrar columnas para compatibilidad
            df_gene = df_gene.rename(columns={
                'fecha': 'Fecha',
                'valor_gwh': 'Generacion_GWh',
                'tipo_clasificado': 'Tipo',
                'planta': 'Planta',
                'recurso': 'Codigo'
            })
            
            logger.info(f"✅ {len(df_gene)} registros de generación para {source_type}")
            return df_gene

        except Exception as e:
            logger.error(f"❌ Error en agregación de generación por tipo: {e}")
            return pd.DataFrame()

    def get_generation_by_resource(self, start_date: date, end_date: date, resource_code: str) -> pd.DataFrame:
        """
        Obtiene la generación de un recurso específico.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            resource_code: Código del recurso
        
        Returns:
            DataFrame con la serie temporal de generación
        """
        try:
            query = """
                SELECT fecha, valor_gwh, recurso
                FROM metrics
                WHERE metrica = 'Gene'
                AND entidad = 'Recurso'
                AND recurso = %s
                AND fecha BETWEEN %s AND %s
                ORDER BY fecha
            """
            
            df = self.repo.execute_dataframe(query, (resource_code, 
                                                      start_date.strftime('%Y-%m-%d'),
                                                      end_date.strftime('%Y-%m-%d')))
            
            if df is None or df.empty:
                logger.warning(f"⚠️ Sin datos para recurso {resource_code}")
                return pd.DataFrame()
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo generación por recurso: {e}")
            return pd.DataFrame()

    def get_latest_valid_date(self) -> date:
        """
        Obtiene la última fecha con datos válidos de generación.
        
        Returns:
            Última fecha disponible en PostgreSQL
        """
        try:
            query = """
                SELECT MAX(fecha) as max_fecha
                FROM metrics
                WHERE metrica = 'Gene'
                AND entidad = 'Sistema'
            """
            
            row = self.repo.execute_query_one(query)
            
            if row and row.get('max_fecha'):
                max_fecha = row['max_fecha']
                if isinstance(max_fecha, str):
                    from datetime import datetime
                    max_fecha = datetime.strptime(max_fecha, '%Y-%m-%d').date()
                return max_fecha
            
            # Fallback: ayer
            return date.today() - timedelta(days=1)
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo última fecha válida: {e}")
            return date.today() - timedelta(days=1)

    def get_generation_summary(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Obtiene resumen de generación por tipo de fuente.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
        
        Returns:
            DataFrame con totales por tipo de fuente
        """
        try:
            # Obtener todos los recursos con su generación
            query = """
                SELECT recurso, SUM(valor_gwh) as total_gwh
                FROM metrics
                WHERE metrica = 'Gene'
                AND entidad = 'Recurso'
                AND fecha BETWEEN %s AND %s
                GROUP BY recurso
            """
            
            df = self.repo.execute_dataframe(query, (start_date.strftime('%Y-%m-%d'),
                                                      end_date.strftime('%Y-%m-%d')))
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            # Clasificar por tipo
            df['tipo'] = df['recurso'].apply(self._classify_resource_type)
            
            # Agrupar por tipo
            summary = df.groupby('tipo')['total_gwh'].sum().reset_index()
            summary = summary.sort_values('total_gwh', ascending=False)
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo resumen de generación: {e}")
            return pd.DataFrame()
