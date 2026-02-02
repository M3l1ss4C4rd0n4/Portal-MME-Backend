"""
Servicio de Dominio para Distribución Eléctrica
Gestiona datos de consumo, pérdidas y activos de distribución
"""

import pandas as pd
from datetime import datetime, date
from typing import Optional, List, Dict
import logging

from infrastructure.database.repositories.distribution_repository import DistributionRepository
from infrastructure.external.xm_service import XMService
from core.exceptions import DataNotFoundError, ExternalAPIError

logger = logging.getLogger(__name__)


class DistributionService:
    """
    Servicio de dominio para gestión de datos de distribución.
    Implementa patrón Repository con fallback a API externa.
    """
    
    def __init__(self):
        self.repository = DistributionRepository()
        self.xm_service = XMService()
    
    def get_agents_list(self) -> pd.DataFrame:
        """
        Obtiene listado de agentes con estadisticas y advertencias.
        """
        try:
            # 1. Obtener estadísticas del repositorio
            agentes_estadisticas = self.repository.fetch_agent_statistics()
            
            if agentes_estadisticas.empty:
                logger.warning("⚠️ No se encontraron agentes en DB local")
                # Intento de fallback a API para obtener lista simple si está vacía
                # Por ahora retornamos vacío para que el dashboard maneje la ausencia
                return pd.DataFrame()

            # 2. Calcular advertencias
            fecha_actual = date.today()
            
            def generar_advertencia(row):
                advertencias = []
                if row['dias_unicos'] < 100:
                    advertencias.append(f"⚠️ Solo {row['dias_unicos']} días")
                if row['metricas_distintas'] < 2:
                    advertencias.append("⚠️ Datos incompletos")
                try:
                    fecha_max = pd.to_datetime(row['fecha_max']).date()
                    dias_desde_ultimo = (fecha_actual - fecha_max).days
                    if dias_desde_ultimo > 30:
                        advertencias.append(f"⚠️ Último dato: {dias_desde_ultimo} días atrás")
                except:
                   pass
                return " | ".join(advertencias) if advertencias else ""
            
            agentes_estadisticas['advertencia'] = agentes_estadisticas.apply(generar_advertencia, axis=1)
            
            # 3. Enriquecer con catálogo (Nombres) - Usamos API para esto por ahora
            # Idealmente esto debería venir de un 'AgentRepository'
            # Usamos los códigos como Nombres por defecto
            agentes_estadisticas['Values_Code'] = agentes_estadisticas['code']
            agentes_estadisticas['Values_Name'] = agentes_estadisticas['code']
            
            return agentes_estadisticas

        except Exception as e:
            logger.error(f"Error en get_agents_list: {e}")
            return pd.DataFrame()

    def get_commercial_demand(self, start_date: date, end_date: date, agent_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """Obtiene demanda comercial (DemaCome) procesada en GWh"""
        return self._get_demand_processed('DemaCome', start_date, end_date, agent_codes)

    def get_real_demand(self, start_date: date, end_date: date, agent_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """Obtiene demanda real (DemaReal) procesada en GWh"""
        return self._get_demand_processed('DemaReal', start_date, end_date, agent_codes)

    def _get_demand_processed(self, metric: str, start: date, end: date, agents: Optional[List[str]]) -> pd.DataFrame:
        """Helper para obtener y procesar métricas de demanda"""
        # Si se piden agentes específicos, iterar (optimizacion pendiente: soporte lista en repo)
        # Por ahora obtenemos todo y filtramos en memoria o hacemos loop? 
        # API XM soporta 'Agente' parametro uno por uno.
        # Repositorio soporta filtro por agente uno por uno.
        # Si la lista de agentes es None, obtenemos TODO (si el repo lo soporta).
        # DistributionRepository.fetch_distribution_metrics soporta agente=None (todos).
        
        try:
            # Consultar Agente y Sistema para tener respaldo en caso de falta de datos granulares
            df = self.repository.fetch_distribution_metrics(metric, start, end, agente=None, entities=['Agente', 'Sistema'])
            
            if df.empty:
                logger.info(f"DB vacía para {metric}, consultando API...")
                # Fallback a API
                # La API requiere consultar por sistema o agente? DemaCome es por Agente.
                # Si consultamos sin agente en pydataxm para 'DemaCome', retorna todos?
                # Pydataxm suele retornar todos si entity='Agente'.
                df = self._fetch_from_external_api(metric, start, end, agente=None)

            if df.empty:
                return pd.DataFrame()

            # Normalizar columnas para la UI
            # df tiene: fecha, valor, unidad, agente
            # UI espera: Fecha, Codigo_Agente, Demanda_GWh, Tipo
            
            # Filtrar agentes si se solicitó, pero conservar Sistema/Agente como referencia
            if agents:
                # Asegurar que los totales no se filtren
                safe_agents = agents + ['Sistema', 'Agente', 'SIN']
                df = df[df['agente'].isin(safe_agents)]

            if df.empty:
                return pd.DataFrame()
            
            # Conversión de unidad
            # Asumimos que la data raw (API o DB) viene en kWh (TXR unit map says kWh). 
            # DemaCome viene en kWh de XM.
            df['Demanda_GWh'] = df['valor'] / 1_000_000  # kWh -> GWh

            # LÓGICA DE DEDUPLICACIÓN DE SISTEMA vs AGENTES
            # Si para un día, la suma de los agentes 'reales' es significativa (> 1 GWh),
            # descartamos la fila 'Sistema' (o el agregado 'Agente') para evitar doble conteo.
            # Si la suma de agentes es casi nula (data provisional de XM), usamos la fila 'Sistema'.
            
            clean_dfs = []
            
            for fecha, group in df.groupby('fecha'):
                 # Agentes reales: ni Sistema ni Agente (el agregado) ni SIN
                 # Aunque 'Agente' suele ser el nombre del recurso agregado cuando entidad=Agente
                 real_agents = group[~group['agente'].isin(['Sistema', 'Agente', 'SIN', 'MercadoComercializacion'])]
                 
                 # Calcular suma de demanda de agentes reales
                 # Ya está en GWh en 'Demanda_GWh' pero ojo: df['valor'] es lo que convertimos arriba
                 # La conversión a Demanda_GWh es columna calculada. Usémosla.
                 sum_real = real_agents['Demanda_GWh'].sum()
                 
                 # Si tenemos datos granulares válidos (> 0.5 GWh)
                 if sum_real > 0.5:
                     clean_dfs.append(real_agents)
                 else:
                     # Si no, buscamos el mejor total disponible: Sistema > Agente > Mercado...
                     sistema_row = group[group['agente'] == 'Sistema']
                     if not sistema_row.empty:
                         clean_dfs.append(sistema_row)
                     else:
                         agente_row = group[group['agente'] == 'Agente']
                         if not agente_row.empty:
                             clean_dfs.append(agente_row)
                         else:
                             # Fallback a lo que haya (probablemente vacío o solo Mercado)
                             clean_dfs.append(group)
            
            if not clean_dfs:
                 return pd.DataFrame()
                 
            df_final = pd.concat(clean_dfs)
            
            result = pd.DataFrame({
                'Fecha': pd.to_datetime(df_final['fecha']),
                'Codigo_Agente': df_final['agente'],
                'Demanda_GWh': df_final['Demanda_GWh'],
                'Tipo': metric
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error procesando demanda {metric}: {e}")
            return pd.DataFrame()

    def get_distribution_data(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente: Optional[str] = None,
        entity: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Obtiene datos de distribución con estrategia híbrida (DB First).
        
        Args:
            metric_code: Código métrica
            start_date: Fecha inicio
            end_date: Fecha fin
            agente: Código agente/recurso (opcional)
            entity: Entidad a consultar (opcional, default Agente en repo)
        
        Returns:
            DataFrame con columnas [fecha, valor, unidad, agente]
        
        Raises:
            DataNotFoundError: Si no hay datos en DB ni en API
        """
        logger.info(f"Solicitando {metric_code} ({entity or 'Agente'}) desde {start_date} hasta {end_date}")
        
        try:
            # 1. INTENTO PRIMARIO: Leer de base de datos local
            # Prepara lista de entidades si se especifica
            entities_list = [entity] if entity else None
            
            df = self.repository.fetch_distribution_metrics(
                metric_code=metric_code,
                start_date=start_date,
                end_date=end_date,
                agente=agente,
                entities=entities_list
            )
            
            if not df.empty:
                logger.info(f"✅ Datos encontrados en DB local: {len(df)} registros")
                return df
            
            # 2. FALLBACK: Llamar API externa si DB vacío
            logger.warning(f"⚠️ DB vacío, intentando API externa para {metric_code}")
            # TODO: Add support for entity in _fetch_from_external_api
            df = self._fetch_from_external_api(metric_code, start_date, end_date, agente)
            
            if not df.empty:
                logger.info(f"✅ Datos obtenidos de API: {len(df)} registros")
                # Opcional: Guardar en cache (implementar método en repository si se desea auto-cache)
                # self.repository.save_metrics(df, metric_code)
                return df
            
            # 3. NO HAY DATOS: Lanzar excepción
            raise DataNotFoundError(
                f"No se encontraron datos para {metric_code} "
                f"en el período {start_date} - {end_date}"
            )
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos distribución: {str(e)}")
            raise
    
    def _fetch_from_external_api(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente: Optional[str]
    ) -> pd.DataFrame:
        """
        Llama a API externa de XM/SIMEM.
        
        Returns:
            DataFrame normalizado o vacío si falla
        """
        try:
            # Llamar adaptador XM (infrastructure/external/xm_service.py)
            raw_data = self.xm_service.get_metric_data(
                metric=metric_code,
                start_date=start_date,
                end_date=end_date
            )
            
            # Normalizar estructura
            df = self._normalize_dataframe(raw_data, metric_code)
            
            # Filtrar por agente si aplica
            if agente and 'agente' in df.columns:
                df = df[df['agente'] == agente]
            
            return df
        
        except Exception as e:
            logger.error(f"❌ Error API externa: {str(e)}")
            # NO lanzar excepción, devolver vacío para intentar degradación elegante
            return pd.DataFrame()
    
    def _normalize_dataframe(self, raw_df: pd.DataFrame, metric_code: str) -> pd.DataFrame:
        """
        Normaliza DataFrame a estructura estándar del sistema.
        
        Expected columns: [fecha, valor, unidad, agente]
        """
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=['fecha', 'valor', 'unidad', 'agente'])
        
        # Renombrar columnas según venga de pydataxm
        column_mapping = {
            'Values': 'valor',
            'Date': 'fecha',
            'Agente': 'agente'
        }
        
        # Verificar columnas presentes
        current_cols = raw_df.columns
        for col, new_col in column_mapping.items():
             if col not in current_cols:
                  # Algunas APIs retornan 'Value' en lugar de 'Values'
                  if col == 'Values' and 'Value' in current_cols:
                      column_mapping['Value'] = 'valor'
                      column_mapping.pop('Values')

        df = raw_df.rename(columns=column_mapping)
        
        # Asegurar tipos correctos
        if 'fecha' in df.columns:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
        if 'valor' in df.columns:
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
        
        # Añadir metadatos
        if 'unidad' not in df.columns:
            df['unidad'] = self._get_metric_unit(metric_code)
            
        # Asegurar columnas requeridas aunque esten vacias
        for col in ['fecha', 'valor', 'unidad', 'agente']:
            if col not in df.columns:
                df[col] = None
        
        return df[['fecha', 'valor', 'unidad', 'agente']].dropna(subset=['valor'])
    
    def _get_metric_unit(self, metric_code: str) -> str:
        """
        Devuelve unidad de medida según código métrica.
        """
        units = {
            'TXR': 'kWh',
            'PERCOM': '%',
            'CONSUM': 'GWh',
            'PERD': '%'
        }
        return units.get(metric_code, 'N/A')
    
    def get_available_agents(self) -> List[Dict[str, str]]:
        """
        Retorna lista de agentes distribuidores disponibles.
        
        Returns:
            Lista de dicts con {codigo, nombre}
        """
        return self.repository.fetch_available_agents()
