"""
Repositorio para datos de comercialización eléctrica.
Implementa ICommercialRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

import pandas as pd
from datetime import date
from typing import Optional, List, Dict
import logging

from infrastructure.database.manager import db_manager
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
        query = "SELECT MIN(fecha), MAX(fecha) FROM commercial_metrics WHERE metrica = %s"
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
        La tabla usa columna 'metrica' (no 'metric_code').
        """
        query = """
        SELECT
            fecha,
            valor,
            unidad
        FROM commercial_metrics
        WHERE metrica = %s
          AND fecha BETWEEN %s AND %s
        ORDER BY fecha ASC
        """

        params = [metric_code, start_date, end_date]

        try:
            df = self.db_manager.query_df(query, params=params)
            if not df.empty:
                df['fecha'] = pd.to_datetime(df['fecha']).dt.date
                # Columnas extra que el servicio puede esperar
                for col in ['agente_comprador', 'agente_vendedor', 'tipo_contrato', 'extra_data']:
                    if col not in df.columns:
                        df[col] = None
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
        (fecha, metrica, valor, unidad)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fecha, metrica) 
        DO UPDATE SET valor = EXCLUDED.valor, unidad = EXCLUDED.unidad
        """

        try:
            records = []
            for _, row in df.iterrows():
                records.append((
                    row['fecha'],
                    metric_code,
                    row['valor'],
                    row.get('unidad', ''),
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
        query = "SELECT DISTINCT metrica as codigo FROM commercial_metrics ORDER BY metrica"
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
        query = "SELECT DISTINCT metrica FROM commercial_metrics ORDER BY metrica"
        try:
            df = self.db_manager.query_df(query)
            return df['metrica'].tolist() if not df.empty else []
        except Exception as e:
            logger.error(f"Error obteniendo métricas disponibles: {e}")
            return []
