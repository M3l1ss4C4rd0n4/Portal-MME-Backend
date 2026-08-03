-- Migración 010: linaje de datos — Fase 6 (gobierno de datos, Palantir-IA)
--
-- Registra cada corrida del pipeline de ontología (scripts/ontologia/*.py):
-- cuándo corrió, cuántas filas tocó, si falló y por qué. Antes de esto, la
-- única forma de saber si el refresh diario (cron 4:30am) realmente corrió
-- era revisar logs de texto plano — esto lo hace consultable.

CREATE TABLE IF NOT EXISTS ontologia.etl_lineage (
    id            SERIAL PRIMARY KEY,
    pipeline      TEXT NOT NULL,        -- 'geografia_alias' | 'empresa_alias' | 'texto_embeddings' | 'refresh_vistas'
    paso          TEXT NOT NULL,        -- función/tabla específica dentro del pipeline
    iniciado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_en TIMESTAMPTZ,
    filas_afectadas INTEGER,
    estado        TEXT NOT NULL DEFAULT 'en_progreso'
        CHECK (estado IN ('en_progreso', 'exito', 'error')),
    detalle       TEXT
);

CREATE INDEX IF NOT EXISTS idx_etl_lineage_pipeline_fecha
    ON ontologia.etl_lineage (pipeline, iniciado_en DESC);

GRANT SELECT ON ontologia.etl_lineage TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia GRANT SELECT ON TABLES TO mme_user;

COMMENT ON TABLE ontologia.etl_lineage IS
    'Linaje del pipeline de ontología: qué corrió, cuándo, cuántas filas, con qué '
    'resultado. Poblada por scripts/ontologia/*.py vía infrastructure.lineage.registrar_paso().';
