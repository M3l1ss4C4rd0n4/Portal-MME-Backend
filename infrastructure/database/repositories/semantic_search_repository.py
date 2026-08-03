"""
Repositorio de búsqueda semántica (RAG) sobre ontologia.contratos_texto_embeddings.
Implementa ISemanticSearchRepository.
"""

from typing import Any, Dict, List

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import ISemanticSearchRepository


def _vector_literal(embedding: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


class SemanticSearchRepository(BaseRepository, ISemanticSearchRepository):
    """Repositorio para búsqueda por similitud coseno vía pgvector (operador <=>)."""

    def buscar_similar(
        self, embedding: List[float], top_k: int = 5, umbral_similitud: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Top-k por similitud coseno sobre DOS corpus (`fuente` distingue cuál):
          - 'contrato': observaciones/objeto de supervision.contratos, deduplicado
            por contenido exacto (muchas filas comparten texto copiado — sin
            dedupe el top-5 mostraba la misma oración 5 veces; `repeticiones`
            indica en cuántas filas aparece).
          - 'informe': chunks (página PDF o diapositiva PPTX) de informes de
            SharePoint (ontologia.informes_texto_embeddings) — sin dedupe, cada
            chunk es contenido único de un documento real, no texto repetido
            entre filas de una tabla.
        """
        vector_lit = _vector_literal(embedding)
        query = """
            SELECT 'contrato' AS fuente, esquema_origen, tabla_origen, fila_id,
                   campo, contenido, similitud, repeticiones,
                   NULL::text AS nombre_archivo, NULL::int AS chunk_index
            FROM (
                SELECT DISTINCT ON (contenido)
                       esquema_origen, tabla_origen, fila_id, campo, contenido,
                       1 - (embedding <=> %(v)s::vector) AS similitud,
                       count(*) OVER (PARTITION BY contenido) AS repeticiones
                FROM ontologia.contratos_texto_embeddings
                WHERE 1 - (embedding <=> %(v)s::vector) >= %(umbral)s
                ORDER BY contenido, embedding <=> %(v)s::vector
            ) dedup_contratos

            UNION ALL

            SELECT 'informe' AS fuente, NULL, NULL, NULL, NULL, e.contenido,
                   1 - (e.embedding <=> %(v)s::vector) AS similitud,
                   1 AS repeticiones, d.nombre_archivo, e.chunk_index
            FROM ontologia.informes_texto_embeddings e
            JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
            WHERE 1 - (e.embedding <=> %(v)s::vector) >= %(umbral)s

            ORDER BY similitud DESC
            LIMIT %(top_k)s
        """
        return self.execute_query(
            query, {"v": vector_lit, "umbral": umbral_similitud, "top_k": top_k}
        )
