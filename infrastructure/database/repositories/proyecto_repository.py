"""
Repositorio para la dimensión de proyectos (esquema ontologia) — Fase 7.
Implementa IProyectoRepository.
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IProyectoRepository


class ProyectoRepository(BaseRepository, IProyectoRepository):
    """Repositorio para ontologia.dim_proyecto / proyecto_alias."""

    def listar_proyectos(self, programa: Optional[str] = None) -> List[Dict[str, Any]]:
        if programa:
            query = """
                SELECT proyecto_id, nombre_canonico, programa, creado_en
                FROM ontologia.dim_proyecto
                WHERE programa = %s
                ORDER BY nombre_canonico
            """
            return self.execute_query(query, (programa,))
        query = """
            SELECT proyecto_id, nombre_canonico, programa, creado_en
            FROM ontologia.dim_proyecto
            ORDER BY programa, nombre_canonico
        """
        return self.execute_query(query)

    def obtener_por_id(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT proyecto_id, nombre_canonico, programa, creado_en
            FROM ontologia.dim_proyecto
            WHERE proyecto_id = %s
        """
        return self.execute_query_one(query, (proyecto_id,))

    def alias_de_proyecto(self, proyecto_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT esquema_origen, tabla_origen, columna_origen, valor_original, metodo
            FROM ontologia.proyecto_alias
            WHERE proyecto_id = %s
            ORDER BY esquema_origen, tabla_origen
        """
        return self.execute_query(query, (proyecto_id,))
