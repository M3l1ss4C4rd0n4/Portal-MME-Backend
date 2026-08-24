"""
Repositorio para la dimensión de geografía DANE (esquema ontologia).
Implementa IGeografiaRepository (Arquitectura Limpia - Inversión de Dependencias)

Todas las queries usan nombres completamente calificados (ontologia.*) en vez de
depender del search_path global del pool, que no incluye el esquema ontologia
(ver infrastructure/database/connection.py).
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IGeografiaRepository


class GeografiaRepository(BaseRepository, IGeografiaRepository):
    """Repositorio para ontologia.dim_geografia / geografia_alias / mv_resumen_departamento."""

    def listar_departamentos(self) -> List[Dict[str, Any]]:
        query = """
            SELECT codigo_dane_departamento, nombre_departamento,
                   count(*) AS n_municipios
            FROM ontologia.dim_geografia
            WHERE activo
            GROUP BY codigo_dane_departamento, nombre_departamento
            ORDER BY nombre_departamento
        """
        return self.execute_query(query)

    def resumen_departamento(self, codigo_dane_departamento: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT * FROM ontologia.mv_resumen_departamento
            WHERE codigo_dane_departamento = %s
        """
        return self.execute_query_one(query, (codigo_dane_departamento,))

    def listar_municipios(self, codigo_dane_departamento: Optional[str] = None) -> List[Dict[str, Any]]:
        if codigo_dane_departamento:
            query = """
                SELECT codigo_dane_departamento, codigo_dane_municipio,
                       nombre_departamento, nombre_municipio
                FROM ontologia.dim_geografia
                WHERE activo AND codigo_dane_departamento = %s
                ORDER BY nombre_municipio
            """
            return self.execute_query(query, (codigo_dane_departamento,))
        query = """
            SELECT codigo_dane_departamento, codigo_dane_municipio,
                   nombre_departamento, nombre_municipio
            FROM ontologia.dim_geografia
            WHERE activo
            ORDER BY nombre_departamento, nombre_municipio
        """
        return self.execute_query(query)

    def resumen_municipio(self, codigo_dane_municipio: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT * FROM ontologia.mv_resumen_municipio
            WHERE codigo_dane_municipio = %s
        """
        return self.execute_query_one(query, (codigo_dane_municipio,))

    def resolver_alias(
        self, esquema: str, tabla: str, columna: str, valor: str
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT ga.geografia_id, ga.es_compuesto, ga.metodo,
                   g.codigo_dane_departamento, g.codigo_dane_municipio,
                   g.nombre_departamento, g.nombre_municipio
            FROM ontologia.geografia_alias ga
            JOIN ontologia.dim_geografia g ON g.geografia_id = ga.geografia_id
            WHERE ga.esquema_origen = %s AND ga.tabla_origen = %s
              AND ga.columna_origen = %s AND ga.valor_original = %s
        """
        return self.execute_query(query, (esquema, tabla, columna, valor))

    def alias_pendientes(self, limit: int = 200) -> List[Dict[str, Any]]:
        query = """
            SELECT esquema_origen, tabla_origen, columna_origen, valor_original, creado_en
            FROM ontologia.geografia_alias
            WHERE metodo = 'sin_resolver'
            ORDER BY esquema_origen, tabla_origen, columna_origen
            LIMIT %s
        """
        return self.execute_query(query, (limit,))

    def contar_alias_pendientes(self) -> int:
        row = self.execute_query_one(
            "SELECT count(*) AS total FROM ontologia.geografia_alias WHERE metodo = 'sin_resolver'"
        )
        return int(row["total"]) if row else 0

    def historial_lineage(self, limit: int = 30) -> List[Dict[str, Any]]:
        query = """
            SELECT pipeline, paso, estado, filas_afectadas, detalle, iniciado_en, finalizado_en
            FROM ontologia.etl_lineage
            ORDER BY iniciado_en DESC
            LIMIT %s
        """
        return self.execute_query(query, (limit,))
