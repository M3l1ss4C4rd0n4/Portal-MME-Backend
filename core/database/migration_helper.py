"""
Helper para facilitar la migración de conexiones DB a pool.

Este módulo proporciona funciones de compatibilidad para migrar
código que usa psycopg2.connect() directamente a usar el pool
de conexiones PostgreSQLConnectionManager.
"""

from contextlib import contextmanager
from typing import Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def get_db_connection(service_name: str = "unknown"):
    """
    Context manager que proporciona una conexión del pool.
    
    Args:
        service_name: Nombre del servicio para logging
        
    Yields:
        Conexión de PostgreSQL del pool
        
    Example:
        with get_db_connection("my_service") as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM metrics")
            rows = cur.fetchall()
    """
    from infrastructure.database.connection import connection_manager
    
    conn = None
    try:
        conn = connection_manager.get_connection()
        yield conn
    except Exception as e:
        logger.error(f"[{service_name}] Error en conexión DB: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if conn:
            try:
                connection_manager.release_connection(conn)
            except Exception as e:
                logger.warning(f"[{service_name}] Error liberando conexión: {e}")


@contextmanager
def get_db_cursor(service_name: str = "unknown", cursor_factory=None):
    """
    Context manager que proporciona un cursor del pool.
    
    Args:
        service_name: Nombre del servicio para logging
        cursor_factory: Factory opcional para cursores especiales (ej: RealDictCursor)
        
    Yields:
        Cursor de PostgreSQL
        
    Example:
        with get_db_cursor("my_service") as cur:
            cur.execute("SELECT * FROM metrics")
            rows = cur.fetchall()
    """
    from infrastructure.database.connection import connection_manager
    
    conn = None
    cur = None
    try:
        conn = connection_manager.get_connection()
        if cursor_factory:
            cur = conn.cursor(cursor_factory=cursor_factory)
        else:
            cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception as e:
        logger.error(f"[{service_name}] Error en operación DB: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            try:
                connection_manager.release_connection(conn)
            except Exception as e:
                logger.warning(f"[{service_name}] Error liberando conexión: {e}")


def migrate_direct_connection(func):
    """
    Decorador para migrar funciones que crean conexiones directas.
    
    Reemplaza el uso de psycopg2.connect() por el pool de conexiones.
    
    Args:
        func: Función a decorar
        
    Example:
        @migrate_direct_connection
        def get_data(conn=None):
            if conn is None:
                conn = psycopg2.connect(**DB_CONFIG)  # Será reemplazado
            # ...
    """
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Si ya se pasó una conexión, usarla
        if 'conn' in kwargs and kwargs['conn'] is not None:
            return func(*args, **kwargs)
        
        # Si no, crear una del pool
        with get_db_connection(func.__name__) as conn:
            kwargs['conn'] = conn
            return func(*args, **kwargs)
    
    return wrapper
