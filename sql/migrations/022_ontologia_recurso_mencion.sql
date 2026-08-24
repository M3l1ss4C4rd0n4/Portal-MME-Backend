-- Migración 022: ontologia.recurso_mencion — Fase 13 (profundización)
--
-- Vincula menciones de plantas específicas en el corpus RAG (ej. "CARTAGENA 1"
-- en los informes de SeguimientoDespacho) con el catálogo estructurado
-- ontologia.dim_recurso — verificado en la Ronda 5 que el nombre coincide
-- exactamente, pero hasta ahora esa coincidencia nunca se materializaba en
-- una tabla consultable. Método de resolución: coincidencia de palabra
-- completa (no subcadena) contra dim_recurso.nombre, solo para nombres de
-- 6+ caracteres — evita falsos positivos de nombres cortos/genéricos
-- (ej. "SUBA", "ZEUS", "URRA" existen como nombre de recurso real).

CREATE TABLE IF NOT EXISTS ontologia.recurso_mencion (
    mencion_id      SERIAL PRIMARY KEY,
    documento_id    INTEGER NOT NULL REFERENCES ontologia.informes_documentos(documento_id),
    chunk_index     INTEGER NOT NULL,
    recurso_id      INTEGER NOT NULL REFERENCES ontologia.dim_recurso(recurso_id),
    metodo          TEXT NOT NULL DEFAULT 'coincidencia_palabra_completa',
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (documento_id, chunk_index, recurso_id)
);

CREATE INDEX IF NOT EXISTS idx_recurso_mencion_recurso ON ontologia.recurso_mencion (recurso_id);
CREATE INDEX IF NOT EXISTS idx_recurso_mencion_documento ON ontologia.recurso_mencion (documento_id, chunk_index);

GRANT SELECT ON ontologia.recurso_mencion TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia GRANT SELECT ON TABLES TO mme_user;

COMMENT ON TABLE ontologia.recurso_mencion IS
    'Menciones de plantas/recursos específicos detectadas en chunks del corpus '
    'RAG (informes_texto_embeddings), por coincidencia de palabra completa '
    'contra dim_recurso.nombre — permite ir de un informe de despacho a la '
    'planta estructurada mencionada, y viceversa.';
