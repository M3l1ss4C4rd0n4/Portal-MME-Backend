import sqlite3
import psycopg2
import psycopg2.extras
import pandas as pd
from pathlib import Path
from typing import Optional, Generator, Any
from contextlib import contextmanager
from core.config import settings
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """Singleton para manejo de conexiones a base de datos (PostgreSQL o SQLite)."""
    
    def __init__(self):
        self.use_postgres = getattr(settings, 'USE_POSTGRES', False)
        if not self.use_postgres:
            self.db_path = settings.DATABASE_PATH

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Context manager para obtener conexión segura."""
        conn = None
        try:
            if self.use_postgres:
                # Conexión PostgreSQL
                conn = psycopg2.connect(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    database=settings.POSTGRES_DB,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD
                )
                conn.autocommit = False
            else:
                # Conexión SQLite
                conn = sqlite3.connect(
                    self.db_path, 
                    timeout=30.0, 
                    check_same_thread=False
                )
                if settings.DB_WAL_MODE:
                    conn.execute("PRAGMA journal_mode=WAL;")
                conn.row_factory = sqlite3.Row
            
            yield conn
        except Exception as e:
            logger.error(f"Error de conexión a BD: {e}")
            if conn and self.use_postgres:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def query_df(self, query: str, params: Optional[dict] = None) -> pd.DataFrame:
        """Ejecuta query y retorna Pandas DataFrame."""
        try:
            with self.get_connection() as conn:
                if self.use_postgres:
                    # PostgreSQL usa %s para placeholders
                    return pd.read_sql_query(query, conn, params=params)
                else:
                    # SQLite usa ?
                    return pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"Error ejecutando query DF: {e} | Query: {query[:50]}...")
            return pd.DataFrame()

    def execute_non_query(self, query: str, params: Optional[tuple] = None) -> None:
        """Ejecuta una sentencia que no retorna datos (INSERT, UPDATE, DELETE)."""
        try:
            with self.get_connection() as conn:
                if self.use_postgres:
                    cursor = conn.cursor()
                    cursor.execute(query, params or ())
                    conn.commit()
                else:
                    if params:
                        conn.execute(query, params)
                    else:
                        conn.execute(query)
                    conn.commit()
        except Exception as e:
            logger.error(f"Error ejecutando non-query: {e}")
            raise

    def get_hourly_data_aggregated(self, metric_id: str, entity_type: str, date_str: str) -> pd.DataFrame:
        """
        Obtiene datos horarios agregados (compatibilidad legacy).
        """
        # CORRECCIÓN: La tabla se llama metrics_hourly y tiene columnas metrica, entidad, fecha
        # NO tiene: metric_id, entity_type, date
        query = "SELECT * FROM metrics_hourly WHERE metrica = ? AND entidad = ? AND fecha = ?"
        return self.query_df(query, params=(metric_id, entity_type, date_str))

    def upsert_metrics_bulk(self, data: list) -> int:
        """
        Inserta datos masivamente en metrics.
        data: Lista de tuplas (fecha, metrica, entidad, recurso, valor, unidad)
        """
        query = """
        INSERT INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(fecha, metrica, entidad, recurso) 
        DO UPDATE SET valor_gwh = excluded.valor_gwh, unidad = excluded.unidad, fecha_actualizacion = CURRENT_TIMESTAMP
        """
        if not data:
            return 0
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, data)
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error en bulk upsert: {e}")
            raise

    def get_catalogo(self, nombre_catalogo: str) -> pd.DataFrame:
        """Obtiene un catálogo completo."""
        query = "SELECT * FROM catalogos WHERE catalogo = ?"
        return self.query_df(query, params=(nombre_catalogo,))

# Instancia global
db_manager = DatabaseManager()
