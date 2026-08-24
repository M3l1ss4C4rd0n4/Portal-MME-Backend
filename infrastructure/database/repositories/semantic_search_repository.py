"""
Repositorio de búsqueda semántica (RAG) sobre ontologia.contratos_texto_embeddings.
Implementa ISemanticSearchRepository.
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import ISemanticSearchRepository


def _vector_literal(embedding: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


class SemanticSearchRepository(BaseRepository, ISemanticSearchRepository):
    """Repositorio para búsqueda por similitud coseno vía pgvector (operador <=>)."""

    def buscar_similar(
        self,
        embedding: List[float],
        top_k: int = 5,
        umbral_similitud: float = 0.3,
        tema: Optional[str] = None,
        campo_contrato: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Top-k por similitud coseno sobre DOS corpus (`fuente` distingue cuál):
          - 'contrato': observaciones/objeto de supervision.contratos, deduplicado
            por contenido exacto (muchas filas comparten texto copiado — sin
            dedupe el top-5 mostraba la misma oración 5 veces; `repeticiones`
            indica en cuántas filas aparece).
          - 'informe': chunks (página PDF o diapositiva PPTX) de informes de
            SharePoint (ontologia.informes_texto_embeddings), también deduplicado
            por contenido exacto — se verificó con datos reales que SÍ hay
            texto repetido entre documentos distintos (ej. la misma página de
            portada/título en varios informes diarios consecutivos); sin
            dedupe, una consulta podía devolver la misma frase de 38
            caracteres 5 veces en el top-5 en vez de contenido real distinto.

        `tema`: filtro determinístico opcional sobre `informes_documentos.tema`
        (Fase 11 Ronda 5, ver scripts/ontologia/clasificar_tema_informes.py) —
        cuando se pasa, solo aplica al corpus 'informe' y garantiza que un tipo
        de documento conocido aparezca en el resultado en vez de depender solo
        de que la similitud semántica lo encuentre por casualidad.

        `campo_contrato`: filtro determinístico opcional sobre
        `contratos_texto_embeddings.campo` (Fase 13, equivalente a `tema` pero
        para el corpus de contratos — ej. 'objeto_del_contrato',
        'observaciones_dificultades_y_gestion_por_parte_del_juridico',
        'observacion_alerta_de_incumplimiento') — solo aplica al corpus
        'contrato'. `tema` y `campo_contrato` son mutuamente excluyentes (cada
        uno filtra un corpus distinto).
        """
        vector_lit = _vector_literal(embedding)
        if tema:
            query = """
                SELECT 'informe' AS fuente, NULL::text, NULL::text, NULL::int,
                       NULL::text, contenido, similitud, repeticiones,
                       nombre_archivo, chunk_index, tema, fecha_documento
                FROM (
                    SELECT DISTINCT ON (e.contenido)
                           e.contenido,
                           1 - (e.embedding <=> %(v)s::vector) AS similitud,
                           count(*) OVER (PARTITION BY e.contenido) AS repeticiones,
                           d.nombre_archivo, e.chunk_index, d.tema,
                           d.modificado_en_sharepoint AS fecha_documento
                    FROM ontologia.informes_texto_embeddings e
                    JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
                    WHERE d.tema = %(tema)s
                      AND 1 - (e.embedding <=> %(v)s::vector) >= %(umbral)s
                    ORDER BY e.contenido, e.embedding <=> %(v)s::vector
                ) dedup_informes
                ORDER BY similitud DESC
                LIMIT %(top_k)s
            """
            return self.execute_query(
                query, {"v": vector_lit, "umbral": umbral_similitud, "top_k": top_k, "tema": tema}
            )

        if campo_contrato:
            query = """
                SELECT 'contrato' AS fuente, esquema_origen, tabla_origen, fila_id,
                       campo, contenido, similitud, repeticiones,
                       NULL::text AS nombre_archivo, NULL::int AS chunk_index, NULL::text AS tema,
                       NULL::timestamptz AS fecha_documento
                FROM (
                    SELECT DISTINCT ON (contenido)
                           esquema_origen, tabla_origen, fila_id, campo, contenido,
                           1 - (embedding <=> %(v)s::vector) AS similitud,
                           count(*) OVER (PARTITION BY contenido) AS repeticiones
                    FROM ontologia.contratos_texto_embeddings
                    WHERE campo = %(campo)s
                      AND 1 - (embedding <=> %(v)s::vector) >= %(umbral)s
                    ORDER BY contenido, embedding <=> %(v)s::vector
                ) dedup_contratos
                ORDER BY similitud DESC
                LIMIT %(top_k)s
            """
            return self.execute_query(
                query, {"v": vector_lit, "umbral": umbral_similitud, "top_k": top_k, "campo": campo_contrato}
            )

        query = """
            SELECT 'contrato' AS fuente, esquema_origen, tabla_origen, fila_id,
                   campo, contenido, similitud, repeticiones,
                   NULL::text AS nombre_archivo, NULL::int AS chunk_index, NULL::text AS tema,
                   NULL::timestamptz AS fecha_documento
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

            SELECT 'informe' AS fuente, NULL, NULL, NULL, NULL, contenido,
                   similitud, repeticiones, nombre_archivo, chunk_index, tema, fecha_documento
            FROM (
                SELECT DISTINCT ON (e.contenido)
                       e.contenido,
                       1 - (e.embedding <=> %(v)s::vector) AS similitud,
                       count(*) OVER (PARTITION BY e.contenido) AS repeticiones,
                       d.nombre_archivo, e.chunk_index, d.tema,
                       d.modificado_en_sharepoint AS fecha_documento
                FROM ontologia.informes_texto_embeddings e
                JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
                WHERE 1 - (e.embedding <=> %(v)s::vector) >= %(umbral)s
                ORDER BY e.contenido, e.embedding <=> %(v)s::vector
            ) dedup_informes

            ORDER BY similitud DESC
            LIMIT %(top_k)s
        """
        return self.execute_query(
            query, {"v": vector_lit, "umbral": umbral_similitud, "top_k": top_k}
        )

    def buscar_texto_completo(
        self,
        consulta: str,
        top_k: int = 15,
        tema: Optional[str] = None,
        campo_contrato: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fase 25 — búsqueda dispersa (full-text nativo de Postgres) sobre los
        mismos 2 corpus de buscar_similar(), usando los índices GIN de la
        migración 033. `ts_rank_cd` para el ranking, `plainto_tsquery` para
        tolerar la consulta en lenguaje natural del usuario (no requiere
        sintaxis de operadores booleanos). Sin umbral de score — a diferencia
        de la similitud coseno (acotada 0-1 con un umbral significativo), el
        rango de `ts_rank_cd` no tiene una escala fija comparable entre
        consultas; se filtra solo por `plainto_tsquery` no vacío (postgres
        ya excluye filas sin coincidencia léxica alguna vía `@@`).
        """
        if tema:
            query = """
                SELECT 'informe' AS fuente, NULL::text, NULL::text, NULL::int,
                       NULL::text, e.contenido,
                       ts_rank_cd(to_tsvector('spanish', e.contenido), q) AS rank_fts,
                       d.nombre_archivo, e.chunk_index, d.tema, d.modificado_en_sharepoint AS fecha_documento
                FROM ontologia.informes_texto_embeddings e
                JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
                CROSS JOIN plainto_tsquery('spanish', %(consulta)s) q
                WHERE d.tema = %(tema)s AND to_tsvector('spanish', e.contenido) @@ q
                ORDER BY rank_fts DESC
                LIMIT %(top_k)s
            """
            return self.execute_query(query, {"consulta": consulta, "tema": tema, "top_k": top_k})

        if campo_contrato:
            query = """
                SELECT 'contrato' AS fuente, esquema_origen, tabla_origen, fila_id,
                       campo, contenido,
                       ts_rank_cd(to_tsvector('spanish', contenido), q) AS rank_fts,
                       NULL::text AS nombre_archivo, NULL::int AS chunk_index, NULL::text AS tema,
                       NULL::timestamptz AS fecha_documento
                FROM ontologia.contratos_texto_embeddings
                CROSS JOIN plainto_tsquery('spanish', %(consulta)s) q
                WHERE campo = %(campo)s AND to_tsvector('spanish', contenido) @@ q
                ORDER BY rank_fts DESC
                LIMIT %(top_k)s
            """
            return self.execute_query(query, {"consulta": consulta, "campo": campo_contrato, "top_k": top_k})

        query = """
            SELECT 'contrato' AS fuente, esquema_origen, tabla_origen, fila_id,
                   campo, contenido,
                   ts_rank_cd(to_tsvector('spanish', contenido), q) AS rank_fts,
                   NULL::text AS nombre_archivo, NULL::int AS chunk_index, NULL::text AS tema,
                   NULL::timestamptz AS fecha_documento
            FROM ontologia.contratos_texto_embeddings
            CROSS JOIN plainto_tsquery('spanish', %(consulta)s) q
            WHERE to_tsvector('spanish', contenido) @@ q

            UNION ALL

            SELECT 'informe' AS fuente, NULL, NULL, NULL, NULL, e.contenido,
                   ts_rank_cd(to_tsvector('spanish', e.contenido), q) AS rank_fts,
                   d.nombre_archivo, e.chunk_index, d.tema, d.modificado_en_sharepoint AS fecha_documento
            FROM ontologia.informes_texto_embeddings e
            JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
            CROSS JOIN plainto_tsquery('spanish', %(consulta)s) q
            WHERE to_tsvector('spanish', e.contenido) @@ q

            ORDER BY rank_fts DESC
            LIMIT %(top_k)s
        """
        return self.execute_query(query, {"consulta": consulta, "top_k": top_k})

    def buscar_recientes(
        self,
        embedding: List[float],
        tema: str,
        top_k: int = 10,
        umbral_similitud: float = 0.15,
    ) -> List[Dict[str, Any]]:
        """Fase 35 — ver docstring de la interfaz. Ordena por fecha de
        modificación (más reciente primero), no por similitud — la similitud
        solo actúa como filtro mínimo de relación temática."""
        vector_lit = _vector_literal(embedding)
        query = """
            SELECT 'informe' AS fuente, NULL::text, NULL::text, NULL::int,
                   NULL::text, contenido, similitud, repeticiones,
                   nombre_archivo, chunk_index, tema, fecha_documento
            FROM (
                SELECT DISTINCT ON (e.contenido)
                       e.contenido,
                       1 - (e.embedding <=> %(v)s::vector) AS similitud,
                       count(*) OVER (PARTITION BY e.contenido) AS repeticiones,
                       d.nombre_archivo, e.chunk_index, d.tema,
                       d.modificado_en_sharepoint AS fecha_documento
                FROM ontologia.informes_texto_embeddings e
                JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
                WHERE d.tema = %(tema)s
                  AND 1 - (e.embedding <=> %(v)s::vector) >= %(umbral)s
                ORDER BY e.contenido, e.embedding <=> %(v)s::vector
            ) dedup_informes
            ORDER BY fecha_documento DESC NULLS LAST
            LIMIT %(top_k)s
        """
        return self.execute_query(
            query, {"v": vector_lit, "umbral": umbral_similitud, "top_k": top_k, "tema": tema}
        )
