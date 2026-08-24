-- Migración 033: búsqueda full-text (BM25-like) sobre los 2 corpus RAG
--
-- Fase 25 — búsqueda híbrida (denso + disperso), estándar de facto en RAG de
-- producción: la similitud de embeddings (búsqueda densa) pierde términos
-- exactos, códigos y nombres poco frecuentes (evidencia propia, 2026-08-06:
-- la consulta "plantas fuera de servicio por mantenimiento" con tema='despacho'
-- no trae en absoluto, ni ampliando el pool a 20 candidatos, el chunk real que
-- lista "Indisponible por mantenimiento: CARTAGENA 1..." — solo trae páginas
-- de encabezado genéricas con similitud de embeddings más alta). Postgres
-- full-text search (tsvector/ts_rank_cd) resuelve justo ese caso por
-- coincidencia léxica directa, sin ninguna dependencia nueva.
--
-- Índices GIN sobre to_tsvector('spanish', contenido) — 'spanish' es una
-- configuración de búsqueda de texto instalada por defecto en Postgres.

CREATE INDEX IF NOT EXISTS idx_informes_texto_embeddings_fts
    ON ontologia.informes_texto_embeddings
    USING GIN (to_tsvector('spanish', contenido));

CREATE INDEX IF NOT EXISTS idx_contratos_texto_embeddings_fts
    ON ontologia.contratos_texto_embeddings
    USING GIN (to_tsvector('spanish', contenido));
