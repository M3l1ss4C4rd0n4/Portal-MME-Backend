"""
Módulo de conexión a PostgreSQL
Reemplaza las conexiones SQLite por PostgreSQL
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
env_path = Path(__file__).parent.parent / '.env.postgres'
if env_path.exists():
    load_dotenv(env_path)

# Configuración de conexión
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'energia_colombia'),
    'user': os.getenv('POSTGRES_USER', 'energia_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'energia_2025_secure')
}


class PostgresConnection:
    """Manejador de conexiones PostgreSQL con pool"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Inicializa la conexión a PostgreSQL
        
        Args:
            config: Diccionario con configuración de conexión
        """
        self.config = config or DB_CONFIG
        self._connection = None
    
    def connect(self):
        """Establece conexión a PostgreSQL"""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.config)
        return self._connection
    
    def close(self):
        """Cierra la conexión"""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    def execute_query(self, query: str, params: tuple = None) -> list:
        """
        Ejecuta una query y retorna resultados como lista de diccionarios
        
        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (opcional)
            
        Returns:
            Lista de diccionarios con los resultados
        """
        conn = self.connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if cursor.description:  # Si hay resultados
                    return [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return []
        except Exception as e:
            conn.rollback()
            raise e
    
    def query_to_df(self, query: str, params: tuple = None) -> pd.DataFrame:
        """
        Ejecuta query y retorna DataFrame de pandas
        
        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (opcional)
            
        Returns:
            DataFrame con los resultados
        """
        conn = self.connect()
        try:
            df = pd.read_sql_query(query, conn, params=params)
            return df
        except Exception as e:
            raise e
    
    def execute_many(self, query: str, data: list):
        """
        Ejecuta múltiples inserts/updates de forma eficiente
        
        Args:
            query: Query SQL con placeholders
            data: Lista de tuplas con los datos
        """
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.executemany(query, data)
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def __enter__(self):
        """Soporte para context manager"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cierra conexión al salir del context manager"""
        self.close()


# Instancia global para uso directo
db = PostgresConnection()


def query_to_df(query: str, params: tuple = None) -> pd.DataFrame:
    """
    Función helper para compatibilidad con código existente
    Ejecuta query y retorna DataFrame
    
    Args:
        query: Query SQL a ejecutar
        params: Parámetros para la query (opcional)
        
    Returns:
        DataFrame con los resultados
    """
    return db.query_to_df(query, params)


def execute_query(query: str, params: tuple = None) -> list:
    """
    Función helper para ejecutar queries que retornan resultados
    
    Args:
        query: Query SQL a ejecutar
        params: Parámetros para la query (opcional)
        
    Returns:
        Lista de diccionarios con los resultados
    """
    return db.execute_query(query, params)


def test_connection() -> bool:
    """
    Prueba la conexión a PostgreSQL
    
    Returns:
        True si la conexión es exitosa, False en caso contrario
    """
    try:
        with db:
            result = db.execute_query("SELECT version();")
            print(f"✅ Conexión exitosa a PostgreSQL")
            print(f"   Versión: {result[0]['version']}")
            return True
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        return False


if __name__ == "__main__":
    # Test de conexión
    print("🧪 Probando conexión a PostgreSQL...")
    test_connection()
