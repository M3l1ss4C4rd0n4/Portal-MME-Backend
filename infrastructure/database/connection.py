"""
Gestión de conexiones a base de datos
Capa Infrastructure - Database
Soporte para SQLite y PostgreSQL
"""

import sqlite3
import psycopg2
import psycopg2.extras
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional, Union

# Importar settings si están disponibles
try:
    from core.config import settings
    DB_PATH = settings.DATABASE_PATH
    USE_POSTGRES = getattr(settings, 'USE_POSTGRES', False)
except Exception:
    DB_PATH = Path(__file__).parent.parent.parent / "portal_energetico.db"
    USE_POSTGRES = False


class PostgreSQLConnectionManager:
    """Gestor de conexiones PostgreSQL"""
    
    def __init__(self):
        try:
            from core.config import settings
            self.host = settings.POSTGRES_HOST
            self.port = settings.POSTGRES_PORT
            self.database = settings.POSTGRES_DB
            self.user = settings.POSTGRES_USER
            self.password = settings.POSTGRES_PASSWORD
        except Exception:
            self.host = "localhost"
            self.port = 5432
            self.database = "portal_energetico"
            self.user = "postgres"
            self.password = ""
    
    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Context manager para conexión PostgreSQL
        
        Yields:
            psycopg2.connection: Conexión activa
        """
        conn = None
        try:
            # Construir parámetros de conexión
            conn_params = {
                'host': self.host,
                'port': self.port,
                'database': self.database,
                'user': self.user,
                'cursor_factory': psycopg2.extras.RealDictCursor
            }
            # Solo agregar password si no está vacío
            if self.password:
                conn_params['password'] = self.password
            
            conn = psycopg2.connect(**conn_params)
            conn.autocommit = False
            yield conn
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Error de conexión PostgreSQL: {e}")
        finally:
            if conn:
                conn.close()


class SQLiteConnectionManager:
    """Gestor de conexiones SQLite"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else Path(DB_PATH)
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager para conexión SQLite
        
        Yields:
            sqlite3.Connection: Conexión activa
        """
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # Configuración básica
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Si hay settings, configurar cache y WAL
            try:
                if hasattr(settings, "DB_WAL_MODE") and settings.DB_WAL_MODE:
                    conn.execute("PRAGMA journal_mode = WAL")
                if hasattr(settings, "DB_CACHE_SIZE_MB"):
                    cache_size = settings.DB_CACHE_SIZE_MB * 1024  # KB
                    conn.execute(f"PRAGMA cache_size = {cache_size}")
            except Exception:
                pass
            
            yield conn
        except sqlite3.Error as e:
            raise RuntimeError(f"Error de conexión SQLite: {e}")
        finally:
            if conn:
                conn.close()


# Instancia global basada en configuración
if USE_POSTGRES:
    connection_manager = PostgreSQLConnectionManager()
else:
    connection_manager = SQLiteConnectionManager()


def get_connection() -> Generator[Union[psycopg2.extensions.connection, sqlite3.Connection], None, None]:
    """Acceso rápido al context manager"""
    return connection_manager.get_connection()
