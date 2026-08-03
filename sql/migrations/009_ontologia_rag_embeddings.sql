-- Migración 009: RAG real — ontologia.contratos_texto_embeddings (pgvector)
--
-- Fase 2 (profundización): SQL determinístico sobre ontologia.* ya resuelve preguntas
-- de KPIs/cruces (mv_resumen_departamento). Lo que NO se puede resolver con SQL exacto
-- es texto libre: objeto del contrato, observaciones jurídicas/técnicas de
-- supervision.contratos — 2,370 objetos de contrato + ~480 observaciones reales,
-- verificado en vivo. Ahí es donde aplica RAG (búsqueda semántica), no en los números.
--
-- Embeddings LOCALES (sentence-transformers, modelo paraphrase-multilingual-MiniLM-L12-v2,
-- 384 dims) — no LightRAG (más pesado, requiere extracción de entidades vía LLM por
-- chunk) ni API externa de embeddings (Groq no ofrece endpoint de embeddings; no hay
-- OPENAI_API_KEY configurada). Corre en CPU, sin costo por llamada, sin dependencia de
-- disponibilidad de un proveedor externo — apropiado para un portal gubernamental.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ontologia.contratos_texto_embeddings (
    id             SERIAL PRIMARY KEY,
    esquema_origen TEXT NOT NULL,
    tabla_origen   TEXT NOT NULL,
    fila_id        INTEGER NOT NULL,
    campo          TEXT NOT NULL,
    contenido      TEXT NOT NULL,
    embedding      vector(384) NOT NULL,
    modelo         TEXT NOT NULL DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2',
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (esquema_origen, tabla_origen, fila_id, campo)
);

-- HNSW: mejor recall/latencia que ivfflat para este volumen (miles de filas, no millones).
CREATE INDEX IF NOT EXISTS idx_contratos_texto_embeddings_hnsw
    ON ontologia.contratos_texto_embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_contratos_texto_embeddings_origen
    ON ontologia.contratos_texto_embeddings (esquema_origen, tabla_origen);

GRANT SELECT ON ontologia.contratos_texto_embeddings TO mme_user;

COMMENT ON TABLE ontologia.contratos_texto_embeddings IS
    'Embeddings de texto libre (objeto de contrato, observaciones jurídicas/técnicas) '
    'para búsqueda semántica. Poblada por scripts/ontologia/build_texto_embeddings.py. '
    'Capa de solo lectura/análisis — no se deriva de aquí ninguna acción sobre contratos.';
