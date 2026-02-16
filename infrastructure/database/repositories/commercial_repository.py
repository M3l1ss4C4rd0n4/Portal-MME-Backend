"""
Repositorio para datos de comercialización eléctrica.
Implementa ICommercialRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

import pandas as pd
from datetime import date
from typing import Optional, List, Dict
import logging

from infrastructure.database.manager import db_manager
from core.exceptions import DatabaseError
from domain.interfaces.repositories import ICommercialRepository

logger = logging.getLogger(__name__)


class CommercialRepository(ICommercialRepository):
    """
    Repositorio para datos de comercialización eléctrica.
    Acceso a tabla 'commercial_metrics' en PostgreSQL.
    Implementa ICommercialRepository para cumplir con arquitectura limpia.
    """
    
    def __init__(self):
        self.db_manager = db_manager

    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible"""
        query = "SELECT MIN(fecha), MAX(fecha) FROM commercial_metrics WHERE metric_code = %s"
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (metric_code,))
                return cursor.fetchone()
        except Exception:
            return None

    def fetch_commercial_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente_comprador: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Consulta métricas de comercialización desde PostgreSQL.
        """
        query = """
        SELECT 
            fecha,
            valor,
            unidad,
            agente_comprador,
            agente_vendedor,
            tipo_contrato,
            extra_data
        FROM commercial_metrics
        WHERE metric_code = %s
          AND fecha BETWEEN %s AND %s
        """
        
        params = [metric_code, start_date, end_date]
        
        if agente_comprador:
            query += " AND agente_comprador = %s"
            params.append(agente_comprador)
        
        query += " ORDER BY fecha ASC"
        
        try:
            df = self.db_manager.query_df(query, params=params)
            
            if not df.empty:
                df['fecha'] = pd.to_datetime(df['fecha']).dt.date
            
            logger.info(f"📊 Query retornó {len(df)} registros para {metric_code}")
            return df
        
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {str(e)}")
            return pd.DataFrame(columns=['fecha', 'valor', 'unidad', 'agente_comprador'])

    def save_metrics(self, df: pd.DataFrame, metric_code: str) -> int:
        """
        Inserta o actualiza métricas en PostgreSQL.
        """
        if df.empty:
            return 0
        
        insert_sql = """
        INSERT INTO commercial_metrics 
        (metric_code, fecha, valor, unidad, agente_comprador, agente_vendedor, tipo_contrato, extra_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (metric_code, fecha, agente_comprador, agente_vendedor) 
        DO UPDATE SET valor = EXCLUDED.valor, unidad = EXCLUDED.unidad
        """
        
        try:
            records = []
            for _, row in df.iterrows():
                agente_comp = row.get('agente_comprador', None)
                agente_vend = row.get('agente_vendedor', None)
                tipo_contr = row.get('tipo_contrato', None)
                extra = row.get('extra_data', None)
                records.append((
                    metric_code, 
                    row['fecha'], 
                    row['valor'], 
                    row['unidad'], 
                    agente_comp, 
                    agente_vend, 
                    tipo_contr,
                    extra
                ))
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(insert_sql, records)
                conn.commit()
                return cursor.rowcount
        
        except Exception as e:
            logger.error(f"❌ Error guardando datos: {str(e)}")
            return 0

    def get_available_buyers(self) -> List[Dict[str, str]]:
        """Obtiene lista de compradores disponibles"""
        query = "SELECT DISTINCT agente_comprador as codigo FROM commercial_metrics WHERE agente_comprador IS NOT NULL ORDER BY agente_comprador"
        try:
            df = self.db_manager.query_df(query)
            return [{'codigo': row['codigo'], 'nombre': row['codigo']} for _, row in df.iterrows()]
        except Exception as e:
            logger.error(f"Error obteniendo compradores: {e}")
            return []
    
    def get_agents(self) -> List[str]:
        """
        Obtiene lista de agentes comerciales (compradores y vendedores).
        Implementa método requerido por ICommercialRepository.
        """
        query = """
        SELECT DISTINCT agente FROM (
            SELECT agente_comprador as agente FROM commercial_metrics WHERE agente_comprador IS NOT NULL
            UNION
            SELECT agente_vendedor as agente FROM commercial_metrics WHERE agente_vendedor IS NOT NULL
        ) agents ORDER BY agente
        """
        try:
            df = self.db_manager.query_df(query)
            return df['agente'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Error obteniendo agentes: {e}")
            return []
    
    def get_available_metrics(self) -> List[str]:
        """
        Obtiene lista de métricas de comercialización disponibles.
        Implementa método requerido por ICommercialRepository.
        """
        query = "SELECT DISTINCT metric_code FROM commercial_metrics ORDER BY metric_code"
        try:
            df = self.db_manager.query_df(query)
            return df['metric_code'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Error obteniendo métricas disponibles: {e}")
            return []
