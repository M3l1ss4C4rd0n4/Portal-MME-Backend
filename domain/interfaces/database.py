"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                   DATABASE INTERFACES (PORTS)                                 ║
║                                                                               ║
║  Interfaces para gestión de conexiones y operaciones generales de BD         ║
║                                                                               ║
║  Implementaciones concretas: infrastructure/database/                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from abc import ABC, abstractmethod
from typing import Optional, Generator, Any, List, Dict
from contextlib import contextmanager
import pandas as pd


class IDatabaseManager(ABC):
    """
    Interface para gestión de conexiones a base de datos.
    Permite intercambiar entre PostgreSQL, SQLite u otra BD sin afectar dominio.
    """
    
    @abstractmethod
    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """
        Context manager para obtener conexión segura a base de datos.
        
        Yields:
            Objeto de conexión (psycopg2.connection, sqlite3.Connection, etc.)
            
        Example:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
        """
        pass
    
    @abstractmethod
    def query_df(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """
        Ejecuta query y retorna Pandas DataFrame.
        
        Args:
            query: Consulta SQL
            params: Parámetros de la consulta
            
        Returns:
            DataFrame con los resultados
        """
        pass
    
    @abstractmethod
    def execute_non_query(self, query: str, params: Optional[tuple] = None) -> None:
        """
        Ejecuta sentencia que no retorna datos (INSERT, UPDATE, DELETE).
        
        Args:
            query: Sentencia SQL
            params: Parámetros de la sentencia
        """
        pass
    
    @abstractmethod
    def execute_many(self, query: str, data: List[tuple]) -> int:
        """
        Ejecuta insert/update masivo.
        
        Args:
            query: Sentencia SQL con placeholders
            data: Lista de tuplas con datos
            
        Returns:
            Número de filas afectadas
        """
        pass
    
    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """
        Verifica si una tabla existe.
        
        Args:
            table_name: Nombre de la tabla
            
        Returns:
            True si la tabla existe
        """
        pass
    
    @abstractmethod
    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de una tabla (columnas, tipos, etc.).
        
        Args:
            table_name: Nombre de la tabla
            
        Returns:
            Diccionario con información de la tabla o None
        """
        pass


class IConnectionManager(ABC):
    """
    Interface para gestión de pools de conexiones.
    Maneja conexiones de forma eficiente con pooling y retry logic.
    """
    
    @abstractmethod
    @contextmanager
    def get_connection(self, use_dict_cursor: bool = False) -> Generator[Any, None, None]:
        """
        Obtiene conexión del pool.
        
        Args:
            use_dict_cursor: Si True, retorna filas como diccionarios
            
        Yields:
            Conexión a base de datos
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        Prueba la conexión a la base de datos.
        
        Returns:
            True si la conexión es exitosa
        """
        pass
    
    @abstractmethod
    def close_all(self) -> None:
        """Cierra todas las conexiones del pool"""
        pass
