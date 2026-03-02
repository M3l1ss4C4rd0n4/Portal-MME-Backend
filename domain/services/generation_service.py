"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          GENERATION SERVICE - PostgreSQL                      ║
║                                                                               ║
║  Servicio de dominio para gestionar datos de generación eléctrica            ║
║  Migrado completamente a PostgreSQL (tabla: metrics)                         ║
║  Implementa Inyección de Dependencias (Arquitectura Limpia - Fase 3)        ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import pandas as pd
from datetime import date, timedelta, datetime
import logging
from typing import Optional, Tuple, Union

from domain.interfaces.repositories import IMetricsRepository
from infrastructure.database.repositories.metrics_repository import MetricsRepository

logger = logging.getLogger(__name__)


def _ensure_date(d: Union[date, str]) -> date:
    """Convierte string a date si es necesario"""
    if isinstance(d, str):
        return datetime.strptime(d, '%Y-%m-%d').date()
    return d


class GenerationService:
    """
    Servicio de dominio para gestionar datos de generación eléctrica.
    Actúa como fachada sobre PostgreSQL a través de MetricsRepository.
    
    Implementa Inyección de Dependencias:
    - Acepta IMetricsRepository como parámetro opcional
    - Si no se provee, usa MetricsRepository() por defecto (backward compatible)
    """

    def __init__(self, repository: Optional[IMetricsRepository] = None):
        """
        Inicializa el servicio con inyección de dependencias opcional.
        
        Args:
            repository: Implementación de IMetricsRepository. 
                       Si es None, usa MetricsRepository() por defecto.
        """
        self.repo = repository if repository is not None else MetricsRepository()

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
            start_date = _ensure_date(start_date)
            end_date = _ensure_date(end_date)
            
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
        Consulta la tabla catalogos para obtener el tipo real de cada recurso.
        
        Args:
            source_type: 'HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA', 'TODAS'
        
        Returns:
            DataFrame con columnas: recurso, tipo_clasificado
        """
        try:
            # Mapear BIOMASA a COGENERADOR (así está en la tabla catalogos)
            tipo_consulta = 'COGENERADOR' if source_type.upper() == 'BIOMASA' else source_type.upper()
            
            # Obtener recursos del catálogo con su tipo
            if source_type.upper() == 'TODAS':
                query = """
                    SELECT codigo as recurso, tipo as tipo_clasificado
                    FROM catalogos
                    WHERE catalogo = 'ListadoRecursos'
                    AND tipo IS NOT NULL
                    ORDER BY codigo
                """
            else:
                query = """
                    SELECT codigo as recurso, tipo as tipo_clasificado
                    FROM catalogos
                    WHERE catalogo = 'ListadoRecursos'
                    AND tipo = %s
                    ORDER BY codigo
                """
            
            df_recursos = self.repo.execute_dataframe(
                query, (tipo_consulta,)
            ) if source_type.upper() != 'TODAS' else self.repo.execute_dataframe(query)
            
            if df_recursos is None or df_recursos.empty:
                logger.warning(f"⚠️ No se encontraron recursos de tipo {source_type} en catalogos")
                return pd.DataFrame()
            
            # Si es BIOMASA, renombrar el tipo a BIOMASA en el resultado
            if source_type.upper() == 'BIOMASA':
                df_recursos['tipo_clasificado'] = 'BIOMASA'
            
            logger.info(f"📋 {len(df_recursos)} recursos de tipo {source_type} encontrados en catalogos")
            return df_recursos
            
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
            
            params = [_ensure_date(start_date).strftime('%Y-%m-%d'), _ensure_date(end_date).strftime('%Y-%m-%d')] + target_codes
            df_gene = self.repo.execute_dataframe(query, tuple(params))
            
            if df_gene is None or df_gene.empty:
                logger.warning(f"⚠️ Sin datos de generación para {source_type} en {start_date} - {end_date}")
                return pd.DataFrame()

            # 3. Hacer merge con el catálogo para obtener el tipo real
            df_gene = df_gene.merge(
                resources_df[['recurso', 'tipo_clasificado']], 
                on='recurso', 
                how='left'
            )
            
            # Usar el tipo que viene del parámetro para los que no hicieron match
            df_gene['tipo_clasificado'] = df_gene['tipo_clasificado'].fillna(source_type.upper())
            
            # Agregar columna Planta
            df_gene['planta'] = df_gene['recurso']  # Usar código como nombre por ahora
            
            # ✅ FIX: Capitalizar el tipo para que coincida con el filtro del tablero
            def capitalizar_tipo(tipo_str):
                """Convierte HIDRAULICA → Hidráulica, TERMICA → Térmica, etc."""
                tipo_upper = str(tipo_str).upper()
                if tipo_upper == 'HIDRAULICA':
                    return 'Hidráulica'
                elif tipo_upper == 'TERMICA':
                    return 'Térmica'
                elif tipo_upper == 'EOLICA':
                    return 'Eólica'
                elif tipo_upper == 'SOLAR':
                    return 'Solar'
                elif tipo_upper == 'BIOMASA':
                    return 'Biomasa'
                else:
                    return tipo_str.capitalize()
            
            df_gene['tipo_clasificado'] = df_gene['tipo_clasificado'].apply(capitalizar_tipo)
            
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

    def get_generation_by_source(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Obtiene generación desagregada por TODOS los tipos de fuente.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
        
        Returns:
            DataFrame con columnas: fecha, tipo, valor_gwh
        """
        try:
            tipos = ['HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'COGENERADOR']
            resultados = []
            
            for tipo in tipos:
                df = self.get_aggregated_generation_by_type(start_date, end_date, tipo)
                if not df.empty:
                    # Agrupar por fecha
                    df_grouped = df.groupby('Fecha').agg({
                        'Generacion_GWh': 'sum'
                    }).reset_index()
                    df_grouped['tipo'] = tipo
                    resultados.append(df_grouped)
            
            if resultados:
                df_final = pd.concat(resultados, ignore_index=True)
                return df_final.rename(columns={
                    'Fecha': 'fecha',
                    'Generacion_GWh': 'valor_gwh'
                })
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo generación por fuente: {e}")
            return pd.DataFrame()

    def get_generation_mix(self, target_date: date) -> pd.DataFrame:
        """
        Calcula el mix energético para una fecha específica.
        Muestra el porcentaje de participación de cada fuente.
        
        Args:
            target_date: Fecha específica
        
        Returns:
            DataFrame con columnas: tipo, generacion_gwh, porcentaje
        """
        try:
            # Obtener generación por tipo para la fecha
            tipos = ['HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'COGENERADOR']
            data = []
            
            for tipo in tipos:
                df = self.get_aggregated_generation_by_type(target_date, target_date, tipo)
                if not df.empty:
                    total = df['Generacion_GWh'].sum()
                    if total > 0:
                        data.append({
                            'tipo': tipo,
                            'generacion_gwh': total
                        })
            
            if not data:
                logger.warning(f"⚠️ No se encontraron datos de mix para {target_date}")
                return pd.DataFrame()
            
            # Crear DataFrame
            df_mix = pd.DataFrame(data)
            
            # Calcular porcentajes
            total_generacion = df_mix['generacion_gwh'].sum()
            df_mix['porcentaje'] = (df_mix['generacion_gwh'] / total_generacion * 100)
            
            logger.info(f"✅ Mix energético calculado para {target_date}: {len(df_mix)} fuentes")
            return df_mix.sort_values('generacion_gwh', ascending=False)
            
        except Exception as e:
            logger.error(f"❌ Error calculando mix energético: {e}")
            return pd.DataFrame()
