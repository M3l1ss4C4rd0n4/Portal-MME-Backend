-- Migración 016: RAG sobre informes de SharePoint (PDF/PPTX) — Fase 8.
--
-- Hasta ahora ontologia.contratos_texto_embeddings (migración 009) solo indexa
-- texto libre de filas de supervision.contratos (objeto/observaciones). Esta
-- migración añade un segundo corpus: documentos completos (PDF/PPTX) descargados
-- de carpetas de SharePoint que YA se relacionan con dominios que el portal
-- muestra hoy (ej. informes de seguimiento de Comunidades Energéticas, guías del
-- sistema de alertas de riesgo de contratos OR) — enriquecen con contexto
-- narrativo lo que los dashboards ya muestran como KPIs numéricos.
--
-- Diseño: tabla de documentos (metadata + hash para detectar cambios, evita
-- re-descargar/re-embeber si el archivo en SharePoint no cambió) + tabla de
-- chunks con embedding. Chunking natural: 1 chunk = 1 página (PDF) o 1
-- diapositiva (PPTX) — evita la complejidad de un splitter genérico para un
-- volumen bajo de documentos (~10 iniciales).
--
-- 100% lectura/indexación — nunca se escribe de vuelta a SharePoint.

CREATE TABLE IF NOT EXISTS ontologia.informes_documentos (
    documento_id              SERIAL PRIMARY KEY,
    carpeta_origen             TEXT NOT NULL,
    nombre_archivo             TEXT NOT NULL,
    tipo_archivo               TEXT NOT NULL CHECK (tipo_archivo IN ('pdf', 'pptx', 'docx')),
    hash_contenido             TEXT NOT NULL,
    sharepoint_item_id         TEXT,
    tamano_bytes               INTEGER,
    modificado_en_sharepoint   TIMESTAMPTZ,
    indexado_en                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (carpeta_origen, nombre_archivo)
);

CREATE TABLE IF NOT EXISTS ontologia.informes_texto_embeddings (
    id             SERIAL PRIMARY KEY,
    documento_id   INTEGER NOT NULL REFERENCES ontologia.informes_documentos(documento_id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL,
    contenido      TEXT NOT NULL,
    embedding      vector(384) NOT NULL,
    modelo         TEXT NOT NULL DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2',
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (documento_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_informes_texto_embeddings_hnsw
    ON ontologia.informes_texto_embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_informes_texto_embeddings_documento
    ON ontologia.informes_texto_embeddings (documento_id);

GRANT SELECT ON ontologia.informes_documentos TO mme_user;
GRANT SELECT ON ontologia.informes_texto_embeddings TO mme_user;

COMMENT ON TABLE ontologia.informes_documentos IS
    'Metadata de informes PDF/PPTX de SharePoint indexados para RAG. Poblada por '
    'scripts/ontologia/build_informes_embeddings.py. hash_contenido evita '
    're-procesar archivos sin cambios entre corridas.';
COMMENT ON TABLE ontologia.informes_texto_embeddings IS
    'Embeddings por chunk (1 página PDF o 1 diapositiva PPTX) de ontologia.informes_documentos. '
    'Capa de solo lectura/análisis — nunca se escribe de vuelta a SharePoint.';
