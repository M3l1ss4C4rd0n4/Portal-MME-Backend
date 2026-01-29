"""
Gestión de conexiones a base de datos
Capa Infrastructure - Database
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional

# Importar settings si están disponibles
try:
    from core.config import settings
    DB_PATH = settings.DATABASE_PATH
except Exception:
    DB_PATH = Path(__file__).parent.parent.parent / "portal_energetico.db"


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


# Instancia global
connection_manager = SQLiteConnectionManager()


def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Acceso rápido al context manager"""
    return connection_manager.get_connection()
