import psycopg2
import psycopg2.extras
import pandas as pd
from typing import Optional, Generator, Any, List, Dict
from contextlib import contextmanager
from core.config import settings
from infrastructure.logging.logger import get_logger
from domain.interfaces.database import IDatabaseManager

logger = get_logger(__name__)

class DatabaseManager(IDatabaseManager):
    """
    Singleton para manejo de conexiones a base de datos PostgreSQL.
    Implementa IDatabaseManager para cumplir con arquitectura limpia.
    """
    
    def __init__(self):
        pass  # No se necesita configuración especial

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Context manager para obtener conexión segura a PostgreSQL."""
        conn = None
        try:
            conn = psycopg2.connect(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD
            )
            conn.autocommit = False
            yield conn
        except Exception as e:
            logger.error(f"Error de conexión a PostgreSQL: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def query_df(self, query: str, params: Optional[dict] = None) -> pd.DataFrame:
        """Ejecuta query y retorna Pandas DataFrame."""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"Error ejecutando query DF: {e} | Query: {query[:50]}...")
            return pd.DataFrame()

    def execute_non_query(self, query: str, params: Optional[tuple] = None) -> None:
        """Ejecuta una sentencia que no retorna datos (INSERT, UPDATE, DELETE)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                conn.commit()
        except Exception as e:
            logger.error(f"Error ejecutando non-query: {e}")
            raise

    def get_hourly_data_aggregated(self, metric_id: str, entity_type: str, date_str: str) -> pd.DataFrame:
        """
        Obtiene datos horarios agregados desde PostgreSQL.
        """
        query = "SELECT * FROM metrics_hourly WHERE metrica = %s AND entidad = %s AND fecha = %s"
        return self.query_df(query, params=(metric_id, entity_type, date_str))

    def upsert_metrics_bulk(self, data: list) -> int:
        """
        Inserta datos masivamente en metrics.
        data: Lista de tuplas (fecha, metrica, entidad, recurso, valor, unidad)
        """
        query = """
        INSERT INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(fecha, metrica, entidad, recurso) 
        DO UPDATE SET valor_gwh = EXCLUDED.valor_gwh, unidad = EXCLUDED.unidad, fecha_actualizacion = CURRENT_TIMESTAMP
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
        query = "SELECT * FROM catalogos WHERE catalogo = %s"
        return self.query_df(query, params=(nombre_catalogo,))
    
    def upsert_catalogo_bulk(self, nombre_catalogo: str, registros: list) -> int:
        """
        Inserta catálogo masivamente en PostgreSQL.
        registros: Lista de diccionarios con keys: codigo, nombre, tipo, region, capacidad, metadata
        """
        query = """
        INSERT INTO catalogos (catalogo, codigo, nombre, tipo, region, capacidad, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(catalogo, codigo) 
        DO UPDATE SET 
            nombre = EXCLUDED.nombre,
            tipo = EXCLUDED.tipo,
            region = EXCLUDED.region,
            capacidad = EXCLUDED.capacidad,
            metadata = EXCLUDED.metadata,
            fecha_actualizacion = CURRENT_TIMESTAMP
        """
        
        if not registros:
            return 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                data = [
                    (
                        nombre_catalogo,
                        reg.get('codigo'),
                        reg.get('nombre'),
                        reg.get('tipo'),
                        reg.get('region'),
                        reg.get('capacidad'),
                        reg.get('metadata')
                    )
                    for reg in registros
                ]
                cursor.executemany(query, data)
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error en upsert_catalogo_bulk: {e}")
            raise
    
    def upsert_hourly_metrics_bulk(self, data: list) -> int:
        """
        Inserta datos horarios masivamente en metrics_hourly.
        data: Lista de tuplas (fecha, metrica, entidad, recurso, hora, valor_mwh)
        """
        query = """
        INSERT INTO metrics_hourly (fecha, metrica, entidad, recurso, hora, valor_mwh)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(fecha, metrica, entidad, recurso, hora) 
        DO UPDATE SET 
            valor_mwh = EXCLUDED.valor_mwh,
            fecha_actualizacion = CURRENT_TIMESTAMP
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
            logger.error(f"Error en upsert_hourly_metrics_bulk: {e}")
            raise
    
    # Métodos adicionales para cumplir con IDatabaseManager
    
    def execute_many(self, query: str, data: List[tuple]) -> int:
        """
        Ejecuta insert/update masivo.
        Implementa método requerido por IDatabaseManager.
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
            logger.error(f"Error en execute_many: {e}")
            raise
    
    def table_exists(self, table_name: str) -> bool:
        """
        Verifica si una tabla existe.
        Implementa método requerido por IDatabaseManager.
        """
        query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        )
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (table_name,))
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Error verificando tabla: {e}")
            return False
    
    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de una tabla (columnas, tipos, etc.).
        Implementa método requerido por IDatabaseManager.
        """
        query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' 
        AND table_name = %s
        ORDER BY ordinal_position
        """
        try:
            df = self.query_df(query, params=(table_name,))
            if df.empty:
                return None
            
            return {
                'table_name': table_name,
                'columns': df.to_dict('records')
            }
        except Exception as e:
            logger.error(f"Error obteniendo info de tabla: {e}")
            return None

# Instancia global
db_manager = DatabaseManager()
