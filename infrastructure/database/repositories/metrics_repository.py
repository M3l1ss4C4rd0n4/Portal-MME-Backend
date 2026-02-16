"""
Repositorio para métricas energéticas.
Implementa IMetricsRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

from typing import List, Optional, Dict, Any
import pandas as pd
from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IMetricsRepository


class MetricsRepository(BaseRepository, IMetricsRepository):
    """
    Repositorio para tabla metrics y métricas relacionadas.
    Implementa IMetricsRepository para cumplir con arquitectura limpia.
    """
    
    def get_total_records(self) -> int:
        query = "SELECT COUNT(*) as count FROM metrics"
        row = self.execute_query_one(query)
        return int(row["count"]) if row else 0
    
    def get_latest_date(self) -> Optional[str]:
        query = "SELECT MAX(fecha) as max_date FROM metrics"
        row = self.execute_query_one(query)
        return row["max_date"] if row and row.get("max_date") else None
    
    def get_metric_data(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        unit: Optional[str] = None,
        entity: Optional[str] = None
    ):
        """
        Obtiene serie temporal de una métrica
        """
        query_parts = ["SELECT fecha, valor_gwh FROM metrics WHERE metrica = %s"]
        params = [metric_id]

        # Filtro de unidad opcional
        if unit:
            query_parts.append("AND unidad = %s")
            params.append(unit)
            
        # Filtro de entidad opcional
        if entity:
            query_parts.append("AND entidad = %s")
            params.append(entity)

        # Filtros de fecha
        if end_date:
            query_parts.append("AND fecha BETWEEN %s AND %s")
            params.extend([start_date, end_date])
        else:
            query_parts.append("AND fecha >= %s")
            params.append(start_date)
        
        # Ordenamiento
        query_parts.append("ORDER BY fecha ASC")

        # Limite
        if limit:
            query_parts.append("LIMIT %s")
            params.append(limit)
        
        query = " ".join(query_parts)
        
        return self.execute_dataframe(query, tuple(params))
    
    def get_metrics_history_by_list(
        self,
        metrics_list: List[str],
        start_date: str,
        end_date: str
    ):
        """
        Obtiene histórico para una lista de métricas
        """
        if not metrics_list:
            return None
            
        placeholders = ','.join(['%s'] * len(metrics_list))
        query = f"""
            SELECT fecha, metrica, AVG(valor_gwh) as valor
            FROM metrics
            WHERE metrica IN ({placeholders})
            AND fecha BETWEEN %s AND %s
            GROUP BY fecha, metrica
            ORDER BY fecha
        """
        params = tuple(metrics_list) + (start_date, end_date)
        return self.execute_dataframe(query, params)
    
    def list_metrics(self) -> List[Dict[str, Any]]:
        query = "SELECT DISTINCT metrica FROM metrics ORDER BY metrica"
        return self.execute_query(query)
    
    def get_metrics_summary(self, start_date: str, end_date: str):
        query = """
             SELECT metrica, COUNT(*) as records,
                 MIN(fecha) as min_date, MAX(fecha) as max_date
            FROM metrics
             WHERE fecha BETWEEN %s AND %s
             GROUP BY metrica
            ORDER BY records DESC
        """
        return self.execute_dataframe(query, (start_date, end_date))

    def get_metric_data_by_entity(self, metric_id: str, entity: str, start_date: str, end_date: str, resource: Optional[str] = None):
        """Obtiene datos filtrando por métrica, entidad y opcionalmente recurso"""
        if resource:
            query = """
                SELECT fecha, valor_gwh, recurso, entidad
                FROM metrics
                WHERE metrica = %s AND entidad = %s AND recurso = %s AND fecha BETWEEN %s AND %s
                ORDER BY fecha ASC
            """
            return self.execute_dataframe(query, (metric_id, entity, resource, start_date, end_date))
        else:
            query = """
                SELECT fecha, valor_gwh, recurso, entidad
                FROM metrics
                WHERE metrica = %s AND entidad = %s AND fecha BETWEEN %s AND %s
                ORDER BY fecha ASC
            """
            return self.execute_dataframe(query, (metric_id, entity, start_date, end_date))

    def get_agent_statistics(self) -> pd.DataFrame:
        """Obtiene estadísticas de agentes en el sistema"""
        query = """
        SELECT 
            recurso as code,
            COUNT(*) as total_registros,
            COUNT(DISTINCT fecha) as dias_unicos,
            COUNT(DISTINCT metrica) as metricas_distintas,
            MIN(fecha) as fecha_min,
            MAX(fecha) as fecha_max
        FROM metrics
        WHERE entidad = 'Agente' 
        AND metrica IN ('DemaCome', 'DemaReal', 'DemaRealReg', 'DemaRealNoReg')
        AND recurso IS NOT NULL
        GROUP BY recurso
        ORDER BY total_registros DESC, dias_unicos DESC
        """
        return self.execute_dataframe(query)

    def get_hourly_data(self, metric_id: str, entity_type: str, date_str: str) -> pd.DataFrame:
        """Obtiene datos horarios de la tabla metrics_hourly"""
        # Fix: use correct column names (metrica, entidad, fecha)
        query = "SELECT * FROM metrics_hourly WHERE metrica = %s AND entidad = %s AND fecha = %s"
        return self.execute_dataframe(query, (metric_id, entity_type, date_str))

    def get_catalogue_mapping(self, catalogue_name: str) -> Dict[str, str]:
        """Obtiene diccionario {codigo: nombre} de un catálogo"""
        query = "SELECT codigo, nombre FROM catalogos WHERE catalogo = %s"
        df = self.execute_dataframe(query, (catalogue_name,))
        if df is not None and not df.empty:
            return dict(zip(df['codigo'], df['nombre']))
        return {}
