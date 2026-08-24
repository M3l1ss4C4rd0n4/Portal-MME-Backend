"""
Repositorio para la dimensión de proyectos (esquema ontologia) — Fase 7.
Implementa IProyectoRepository.
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IProyectoRepository


class ProyectoRepository(BaseRepository, IProyectoRepository):
    """Repositorio para ontologia.dim_proyecto / proyecto_alias."""

    def listar_proyectos(
        self, programa: Optional[str] = None, departamento: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        condiciones, params = [], {}
        if programa:
            condiciones.append("p.programa = %(programa)s")
            params["programa"] = programa
        if departamento:
            # Fase 23 Bloque 2 — filtra por proyecto_geografia (vínculo real,
            # nunca por texto crudo de la tabla origen del proyecto).
            condiciones.append("""
                p.proyecto_id IN (
                    SELECT pg.proyecto_id FROM ontologia.proyecto_geografia pg
                    JOIN ontologia.dim_geografia g ON g.geografia_id = pg.geografia_id
                    WHERE g.nombre_departamento_normalizado = upper(ontologia.f_unaccent(%(depto)s))
                )
            """)
            params["depto"] = departamento
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        query = f"""
            SELECT p.proyecto_id, p.nombre_canonico, p.programa, p.creado_en
            FROM ontologia.dim_proyecto p
            {where}
            ORDER BY p.programa, p.nombre_canonico
        """
        return self.execute_query(query, params if params else None)

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

    def geografias_de_proyecto(self, proyecto_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT g.codigo_dane_departamento, g.nombre_departamento,
                   g.codigo_dane_municipio, g.nombre_municipio
            FROM ontologia.proyecto_geografia pg
            JOIN ontologia.dim_geografia g ON g.geografia_id = pg.geografia_id
            WHERE pg.proyecto_id = %s
            ORDER BY g.nombre_departamento, g.nombre_municipio
        """
        return self.execute_query(query, (proyecto_id,))
