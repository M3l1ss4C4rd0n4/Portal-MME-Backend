"""
Gestión de conexiones a base de datos PostgreSQL
Capa Infrastructure - Database

Pool de conexiones centralizado (ThreadedConnectionPool).
Tanto PostgreSQLConnectionManager como DatabaseManager (legacy)
comparten este pool para evitar abrir/cerrar conexiones por operación.
"""

import atexit
import threading
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager
from typing import Generator

# Importar settings
from core.config import settings
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────
# Pool centralizado (singleton thread-safe)
# ──────────────────────────────────────────────────────────
_pool_lock = threading.Lock()
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Obtiene o crea el pool de conexiones (lazy, thread-safe)."""
    global _pool
    if _pool is None or _pool.closed:
        with _pool_lock:
            if _pool is None or _pool.closed:
                conn_params = {
                    'host': settings.POSTGRES_HOST,
                    'port': settings.POSTGRES_PORT,
                    'database': settings.POSTGRES_DB,
                    'user': settings.POSTGRES_USER,
                    'connect_timeout': 10,
                    'options': (
                        '-c statement_timeout=30000'
                        ' -c search_path=sector_energetico,subsidios,supervision,'
                        'comunidades,presupuesto,contratos_or,public'
                    ),
                }
                if settings.POSTGRES_PASSWORD:
                    conn_params['password'] = settings.POSTGRES_PASSWORD

                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20,
                    **conn_params,
                )
                logger.info(
                    "Pool PostgreSQL creado (min=2, max=20)"
                )
    return _pool


def close_pool() -> None:
    """Cierra el pool de conexiones (llamado al apagar)."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        logger.info("Pool PostgreSQL cerrado")
        _pool = None


atexit.register(close_pool)


class PostgreSQLConnectionManager:
    """Gestor de conexiones PostgreSQL basado en pool."""

    @contextmanager
    def get_connection(self, use_dict_cursor: bool = False) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Context manager para conexión PostgreSQL desde el pool.

        Args:
            use_dict_cursor: Si True, usa RealDictCursor.

        Yields:
            psycopg2.connection: Conexión activa (devuelta al pool al salir).
        """
        pool = _get_pool()
        conn = pool.getconn()
        try:
            if use_dict_cursor:
                conn.cursor_factory = psycopg2.extras.RealDictCursor
            else:
                conn.cursor_factory = psycopg2.extensions.cursor

            conn.autocommit = False
            yield conn
        except psycopg2.Error as e:
            if conn and not conn.closed:
                conn.rollback()
            raise RuntimeError(f"Error de conexión PostgreSQL: {e}")
        finally:
            if conn is None:
                return
            if conn.closed:
                # Conexión muerta — descartar del pool en vez de reciclar
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                return
            try:
                conn.reset()  # rollback si hay transacción abierta
                with conn.cursor() as _cur:
                    # Restaurar search_path al valor configurado.
                    # RESET search_path volvería al default de Postgres ("$user",public),
                    # deshaciendo la opción de startup del pool.
                    _cur.execute(
                        "SET search_path TO "
                        "sector_energetico, subsidios, supervision, "
                        "comunidades, presupuesto, contratos_or, public"
                    )
                conn.commit()
                pool.putconn(conn)
            except Exception:
                # Estado desconocido — descartar en vez de reciclar conexión rota
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass


# Instancia global
connection_manager = PostgreSQLConnectionManager()


def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Acceso rápido al context manager"""
    return connection_manager.get_connection()
