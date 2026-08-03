"""
Repositorio para la dimensión de empresas/prestadores/ejecutores (esquema ontologia).
Implementa IEmpresaRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IEmpresaRepository


class EmpresaRepository(BaseRepository, IEmpresaRepository):
    """Repositorio para ontologia.dim_empresa / empresa_alias."""

    def buscar_empresas(
        self, nit: Optional[str] = None, nombre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if nit:
            query = """
                SELECT empresa_id, nit, codigo_sui, nombre_oficial, sigla, tipo_empresa
                FROM ontologia.dim_empresa
                WHERE nit_normalizado = regexp_replace(split_part(%s, '.', 1), '[^0-9]', '', 'g')
            """
            return self.execute_query(query, (nit,))
        if nombre:
            # Busca también por sigla (ej. "GENSA") — no solo nombre_oficial (ej.
            # "GESTION ENERGETICA S.A. ESP"), que es como la gente realmente busca.
            # Prioriza filas con NIT verificado (las que sí tienen contratos conectados
            # en el grafo) sobre las que solo tienen coincidencia de texto.
            query = """
                SELECT empresa_id, nit, codigo_sui, nombre_oficial, sigla, tipo_empresa,
                       GREATEST(
                           similarity(nombre_oficial, %s),
                           similarity(coalesce(sigla, ''), %s)
                       ) AS score,
                       (nit_normalizado <> '') AS tiene_nit
                FROM ontologia.dim_empresa
                WHERE nombre_oficial ILIKE %s OR sigla ILIKE %s
                   OR similarity(nombre_oficial, %s) > 0.3
                   OR similarity(coalesce(sigla, ''), %s) > 0.3
                ORDER BY tiene_nit DESC, score DESC
                LIMIT 25
            """
            like = f"%{nombre}%"
            return self.execute_query(query, (nombre, nombre, like, like, nombre, nombre))
        return []

    def obtener_por_id(self, empresa_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT empresa_id, nit, nit_normalizado, codigo_sui, nombre_oficial, sigla, tipo_empresa
            FROM ontologia.dim_empresa
            WHERE empresa_id = %s
        """
        return self.execute_query_one(query, (empresa_id,))

    def alias_pendientes(self, limit: int = 200) -> List[Dict[str, Any]]:
        query = """
            SELECT esquema_origen, tabla_origen, columna_origen, valor_original,
                   metodo, confianza, creado_en
            FROM ontologia.empresa_alias
            WHERE metodo IN ('sin_resolver', 'match_nombre_fuzzy')
            ORDER BY esquema_origen, tabla_origen, columna_origen
            LIMIT %s
        """
        return self.execute_query(query, (limit,))

    def contar_alias_pendientes(self) -> int:
        row = self.execute_query_one(
            "SELECT count(*) AS total FROM ontologia.empresa_alias "
            "WHERE metodo IN ('sin_resolver', 'match_nombre_fuzzy')"
        )
        return int(row["total"]) if row else 0

    def contar_contratos_supervision_por_nit(self, nit_normalizado: str) -> int:
        query = """
            SELECT count(*) AS total FROM supervision.contratos
            WHERE regexp_replace(split_part(ROUND(nit_ejecutor)::text, '.', 1), '[^0-9]', '', 'g') = %s
        """
        row = self.execute_query_one(query, (nit_normalizado,))
        return int(row["total"]) if row else 0

    def contratos_supervision_por_nit(
        self, nit_normalizado: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT id, codcontrato, ejecutor, departamento, municipio,
                   codigo_dane_departamento, codigo_dane_municipio,
                   fondo, numero_bpin, estado_del_contrato, avance_contrato, link_secop
            FROM supervision.contratos
            WHERE regexp_replace(split_part(ROUND(nit_ejecutor)::text, '.', 1), '[^0-9]', '', 'g') = %s
            ORDER BY departamento, municipio
            LIMIT %s
        """
        return self.execute_query(query, (nit_normalizado, limit))

    def alias_resueltos_de_empresa(self, empresa_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT esquema_origen, tabla_origen, columna_origen, valor_original, metodo, confianza
            FROM ontologia.empresa_alias
            WHERE empresa_id = %s AND metodo != 'sin_resolver'
            ORDER BY esquema_origen, tabla_origen
        """
        return self.execute_query(query, (empresa_id,))

    def proyectos_de_empresa(self, empresa_id: int) -> List[Dict[str, Any]]:
        """
        2do salto del grafo: proyectos de contratos_or donde esta empresa aparece
        como ejecutor (vía empresa_alias, normalmente match_nombre_fuzzy — sin NIT
        en contratos_or, ver empresa_alias.metodo/confianza en la respuesta).
        """
        query = """
            SELECT DISTINCT saf.nombre_proyecto_id, saf.departamento, saf.municipio,
                   saf.avance, pa.proyecto_id, ea.metodo AS metodo_empresa,
                   ea.confianza AS confianza_empresa
            FROM ontologia.empresa_alias ea
            JOIN contratos_or.seguimiento_avance_fisico saf
                ON saf.ejecutor = ea.valor_original
            LEFT JOIN ontologia.proyecto_alias pa
                ON pa.esquema_origen = 'contratos_or' AND pa.tabla_origen = 'seguimiento_avance_fisico'
               AND pa.columna_origen = 'nombre_proyecto_id' AND pa.valor_original = saf.nombre_proyecto_id
            WHERE ea.empresa_id = %s
              AND ea.esquema_origen = 'contratos_or' AND ea.tabla_origen = 'seguimiento_avance_fisico'
              AND ea.columna_origen = 'ejecutor'
            ORDER BY saf.departamento, saf.municipio
        """
        return self.execute_query(query, (empresa_id,))

    def empresas_relacionadas_por_geografia(
        self, codigos_dane_departamento: List[str], excluir_empresa_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Patrón de "concentración de contratistas" (2 saltos: empresa -> geografía ->
        otras empresas): dado un conjunto de departamentos donde una empresa ya
        opera (vía NIT verificado), qué otras empresas tienen contratos ahí.
        """
        if not codigos_dane_departamento:
            return []
        query = """
            SELECT de.empresa_id, de.nombre_oficial, de.sigla, de.nit,
                   count(DISTINCT c.id) AS n_contratos_en_zona
            FROM supervision.contratos c
            JOIN ontologia.dim_empresa de
                ON de.nit_normalizado = regexp_replace(
                    split_part(ROUND(c.nit_ejecutor)::text, '.', 1), '[^0-9]', '', 'g'
                )
            WHERE c.codigo_dane_departamento = ANY(%(codigos)s)
              AND de.empresa_id != %(excluir)s
              AND de.nit_normalizado <> ''
            GROUP BY de.empresa_id, de.nombre_oficial, de.sigla, de.nit
            ORDER BY n_contratos_en_zona DESC
            LIMIT %(limit)s
        """
        return self.execute_query(query, {
            "codigos": codigos_dane_departamento,
            "excluir": excluir_empresa_id,
            "limit": limit,
        })
