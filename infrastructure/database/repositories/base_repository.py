"""
Repositorio base para acceso a SQLite
Proporciona métodos comunes para consultas
"""

from typing import Any, Dict, List, Optional
import pandas as pd

from infrastructure.database.connection import SQLiteConnectionManager


class BaseRepository:
    """Repositorio base con utilidades comunes"""
    
    def __init__(self, connection_manager: Optional[SQLiteConnectionManager] = None):
        self.connection_manager = connection_manager or SQLiteConnectionManager()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Ejecuta una consulta y retorna lista de diccionarios
        """
        with self.connection_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def execute_query_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        Ejecuta una consulta y retorna un solo registro
        """
        with self.connection_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def execute_dataframe(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Ejecuta una consulta y retorna DataFrame
        """
        with self.connection_manager.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params or ())
    
    def execute_non_query(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Ejecuta INSERT/UPDATE/DELETE y retorna filas afectadas
        """
        with self.connection_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return cursor.rowcount
