"""
Gestión de conexiones a base de datos PostgreSQL
Capa Infrastructure - Database
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Generator

# Importar settings
from core.config import settings


class PostgreSQLConnectionManager:
    """Gestor de conexiones PostgreSQL"""
    
    def __init__(self):
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.database = settings.POSTGRES_DB
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
    
    @contextmanager
    def get_connection(self, use_dict_cursor: bool = False) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Context manager para conexión PostgreSQL
        
        Args:
            use_dict_cursor: Si True, usa RealDictCursor. Si False (default), usa cursor normal para pandas.
        
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
                'user': self.user
            }
            
            # Agregar cursor_factory solo si se solicita explícitamente
            if use_dict_cursor:
                conn_params['cursor_factory'] = psycopg2.extras.RealDictCursor
            
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


# Instancia global
connection_manager = PostgreSQLConnectionManager()


def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Acceso rápido al context manager"""
    return connection_manager.get_connection()
