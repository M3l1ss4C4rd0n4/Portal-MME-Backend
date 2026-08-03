"""
Linaje de datos — Fase 6 (gobierno de datos, Palantir-IA).

Context manager liviano para registrar en ontologia.etl_lineage qué corrida de un
pipeline (ej. scripts/ontologia/*.py) tocó qué, cuándo, y con qué resultado.

Uso:
    from infrastructure.observability.lineage import registrar_paso

    with registrar_paso("geografia_alias", "seed_dim_geografia") as paso:
        n = seed_dim_geografia()
        paso.filas(n)

No lanza excepciones propias: si el registro de linaje falla (ej. tabla no
disponible), solo deja un warning en el log — nunca debe tumbar el pipeline real
que está observando.
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from infrastructure.database.manager import db_manager

logger = logging.getLogger(__name__)


class _RegistroPaso:
    def __init__(self):
        self._filas: Optional[int] = None

    def filas(self, n: int) -> None:
        self._filas = n


def _marcar_exito(pipeline: str, paso: str, filas: Optional[int]) -> None:
    try:
        db_manager.execute_non_query(
            """
            UPDATE ontologia.etl_lineage
            SET estado = 'exito', finalizado_en = NOW(), filas_afectadas = %s
            WHERE id = (
                SELECT id FROM ontologia.etl_lineage
                WHERE pipeline = %s AND paso = %s AND estado = 'en_progreso'
                ORDER BY iniciado_en DESC LIMIT 1
            )
            """,
            (filas, pipeline, paso),
        )
    except Exception as e:
        logger.warning(f"[LINEAGE] No se pudo registrar éxito de {pipeline}.{paso}: {e}")


def _marcar_error(pipeline: str, paso: str, detalle: str) -> None:
    try:
        db_manager.execute_non_query(
            """
            UPDATE ontologia.etl_lineage
            SET estado = 'error', finalizado_en = NOW(), detalle = %s
            WHERE id = (
                SELECT id FROM ontologia.etl_lineage
                WHERE pipeline = %s AND paso = %s AND estado = 'en_progreso'
                ORDER BY iniciado_en DESC LIMIT 1
            )
            """,
            (detalle[:500], pipeline, paso),
        )
    except Exception as e:
        logger.warning(f"[LINEAGE] No se pudo registrar error de {pipeline}.{paso}: {e}")


@contextmanager
def registrar_paso(pipeline: str, paso: str) -> Generator[_RegistroPaso, None, None]:
    registro = _RegistroPaso()
    try:
        db_manager.execute_non_query(
            "INSERT INTO ontologia.etl_lineage (pipeline, paso, estado) VALUES (%s, %s, 'en_progreso')",
            (pipeline, paso),
        )
    except Exception as e:
        logger.warning(f"[LINEAGE] No se pudo registrar inicio de {pipeline}.{paso}: {e}")

    try:
        yield registro
        _marcar_exito(pipeline, paso, registro._filas)
    except Exception as exc:
        _marcar_error(pipeline, paso, str(exc))
        raise
