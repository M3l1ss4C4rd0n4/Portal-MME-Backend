"""
Repositorio para el catálogo de plantas/recursos de generación (esquema
ontologia) — Fase 13 Bloque B. Implementa IRecursoRepository.
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IRecursoRepository


class RecursoRepository(BaseRepository, IRecursoRepository):
    """Repositorio para ontologia.dim_recurso."""

    def listar_recursos(
        self, tipo: Optional[str] = None, nombre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        condiciones = []
        params: Dict[str, Any] = {}
        if tipo:
            condiciones.append("tipo = %(tipo)s")
            params["tipo"] = tipo
        if nombre:
            condiciones.append("nombre ILIKE %(nombre)s")
            params["nombre"] = f"%{nombre}%"
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        query = f"""
            SELECT recurso_id, codigo_xm, nombre, tipo, region, capacidad, activo, actualizado_en
            FROM ontologia.dim_recurso
            {where}
            ORDER BY tipo, nombre
        """
        return self.execute_query(query, params if params else None)

    def obtener_por_codigo(self, codigo_xm: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT recurso_id, codigo_xm, nombre, tipo, region, capacidad, activo, actualizado_en
            FROM ontologia.dim_recurso
            WHERE codigo_xm = %(codigo)s
        """
        return self.execute_query_one(query, {"codigo": codigo_xm})

    def menciones_recientes(self, recurso_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
            SELECT d.nombre_archivo, m.chunk_index, m.creado_en
            FROM ontologia.recurso_mencion m
            JOIN ontologia.informes_documentos d ON d.documento_id = m.documento_id
            WHERE m.recurso_id = %(id)s
            ORDER BY d.nombre_archivo DESC
            LIMIT %(limit)s
        """
        return self.execute_query(query, {"id": recurso_id, "limit": limit})
