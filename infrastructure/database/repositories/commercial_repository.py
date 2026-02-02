"""
Repositorio para datos de comercialización eléctrica.
"""

import sqlite3
import pandas as pd
from datetime import date
from typing import Optional, List, Dict
import logging

from infrastructure.database.manager import db_manager
from core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class CommercialRepository:
    """
    Repositorio para datos de comercialización eléctrica.
    Acceso directo a tabla 'commercial_metrics' en SQLite.
    """
    
    def __init__(self):
        self.db_manager = db_manager
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """
        Crea tabla commercial_metrics si no existe (solo para SQLite).
        En PostgreSQL las tablas ya deben existir.
        """
        # Si usamos PostgreSQL, asumir que las tablas ya existen
        if self.db_manager.use_postgres:
            logger.info("✅ Usando PostgreSQL - tablas preexistentes")
            return
            
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS commercial_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_code TEXT NOT NULL,
            fecha DATE NOT NULL,
            valor REAL,
            unidad TEXT,
            agente_comprador TEXT,
            agente_vendedor TEXT,
            tipo_contrato TEXT,
            extra_data TEXT,  -- JSON para datos horarios u otros detalles
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(metric_code, fecha, agente_comprador, agente_vendedor)
        );
        
        CREATE INDEX IF NOT EXISTS idx_commercial_date 
        ON commercial_metrics(metric_code, fecha);
        """
        
        try:
            with self.db_manager.get_connection() as conn:
                # SQLite only - try to add column
                try:
                    conn.execute("ALTER TABLE commercial_metrics ADD COLUMN extra_data TEXT")
                except Exception:
                    pass  # Column likely exists
                
                conn.executescript(create_table_sql)
                conn.commit()
                logger.info("✅ Tabla commercial_metrics verificada")
        except sqlite3.Error as e:
            logger.error(f"❌ Error creando tabla: {str(e)}")

    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible"""
        query = "SELECT MIN(fecha), MAX(fecha) FROM commercial_metrics WHERE metric_code = ?"
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
        Consulta métricas de comercialización desde SQLite.
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
        WHERE metric_code = ?
          AND fecha BETWEEN ? AND ?
        """
        
        params = [metric_code, start_date, end_date]
        
        if agente_comprador:
            query += " AND agente_comprador = ?"
            params.append(agente_comprador)
        
        query += " ORDER BY fecha ASC"
        
        try:
            with self.db_manager.get_connection() as conn:
                df = pd.read_sql_query(query, conn, params=params)
                
                if not df.empty:
                    df['fecha'] = pd.to_datetime(df['fecha']).dt.date
                
                logger.info(f"📊 Query retornó {len(df)} registros para {metric_code}")
                return df
        
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {str(e)}")
            return pd.DataFrame(columns=['fecha', 'valor', 'unidad', 'agente_comprador'])

    def save_metrics(self, df: pd.DataFrame, metric_code: str) -> int:
        """
        Inserta o actualiza métricas.
        """
        if df.empty:
            return 0
        
        insert_sql = """
        INSERT OR REPLACE INTO commercial_metrics 
        (metric_code, fecha, valor, unidad, agente_comprador, agente_vendedor, tipo_contrato, extra_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        
        except sqlite3.Error as e:
            logger.error(f"❌ Error guardando datos: {str(e)}")
            return 0

            
    def get_available_buyers(self) -> List[Dict[str, str]]:
        query = "SELECT DISTINCT agente_comprador as codigo FROM commercial_metrics WHERE agente_comprador IS NOT NULL ORDER BY agente_comprador"
        try:
            with self.db_manager.get_connection() as conn:
                df = pd.read_sql_query(query, conn)
                return [{'codigo': row['codigo'], 'nombre': row['codigo']} for _, row in df.iterrows()]
        except Exception as e:
            logger.error(f"Error agents: {e}")
            return []
