-- Migración 007: ontologia.dim_empresa + ontologia.empresa_alias
--
-- subsidios.subsidios_empresas es la única tabla con NIT/código SUI reales. Fuera de
-- subsidios y supervision.contratos.nit_ejecutor, columnas como contratos_or.ejecutor,
-- fenoge.contratista, colombia_solar.or_generador/contratista_entidad son texto libre
-- SIN NIT — no hay match determinístico posible ahí, solo fuzzy matching de nombre
-- (pg_trgm), que nunca se auto-acepta en vistas de producción sin revisión humana.

CREATE TABLE IF NOT EXISTS ontologia.dim_empresa (
    empresa_id      SERIAL PRIMARY KEY,
    nit             VARCHAR(20),
    -- split_part(...,'.',1) descarta el ".0" de columnas fuente que llegaron como
    -- numeric/float (ej. "901415587.0"); regexp_replace limpia cualquier otro símbolo.
    nit_normalizado VARCHAR(20) GENERATED ALWAYS AS
        (regexp_replace(split_part(coalesce(nit, ''), '.', 1), '[^0-9]', '', 'g')) STORED,
    codigo_sui      VARCHAR(20),
    nombre_oficial  TEXT NOT NULL,
    sigla           TEXT,
    tipo_empresa    TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- codigo_sui es la llave de negocio real (grano = "prestador registrado"); un mismo NIT
-- puede tener >1 codigo_sui (misma empresa legal con varios registros de prestador), así
-- que nit_normalizado se indexa pero NO se fuerza UNIQUE.
CREATE INDEX IF NOT EXISTS idx_dim_empresa_nit_normalizado
    ON ontologia.dim_empresa (nit_normalizado) WHERE nit_normalizado <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_empresa_codigo_sui
    ON ontologia.dim_empresa (codigo_sui) WHERE codigo_sui IS NOT NULL AND codigo_sui <> '';
CREATE INDEX IF NOT EXISTS idx_dim_empresa_nombre_trgm
    ON ontologia.dim_empresa USING gin (nombre_oficial gin_trgm_ops);

COMMENT ON TABLE ontologia.dim_empresa IS
    'Dimensión maestra de empresas/prestadores/ejecutores. Semilla desde '
    'subsidios.subsidios_empresas (NIT, código SUI reales).';

CREATE TABLE IF NOT EXISTS ontologia.empresa_alias (
    alias_id       SERIAL PRIMARY KEY,
    esquema_origen TEXT NOT NULL,
    tabla_origen   TEXT NOT NULL,
    columna_origen TEXT NOT NULL,
    valor_original TEXT NOT NULL,
    empresa_id     INTEGER REFERENCES ontologia.dim_empresa(empresa_id),
    metodo         TEXT NOT NULL
        CHECK (metodo IN ('match_nit', 'match_nombre_fuzzy', 'curado_manual', 'sin_resolver')),
    confianza      NUMERIC(3,2),
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (esquema_origen, tabla_origen, columna_origen, valor_original)
);

CREATE INDEX IF NOT EXISTS idx_empresa_alias_lookup
    ON ontologia.empresa_alias (esquema_origen, tabla_origen, columna_origen, valor_original);
CREATE INDEX IF NOT EXISTS idx_empresa_alias_pendientes
    ON ontologia.empresa_alias (metodo) WHERE metodo IN ('sin_resolver', 'match_nombre_fuzzy');

COMMENT ON TABLE ontologia.empresa_alias IS
    'Mapeo de texto libre (ejecutor/contratista/or_generador) hacia dim_empresa. '
    'metodo=match_nombre_fuzzy NUNCA se usa en vistas de producción sin revisión '
    'humana previa (falso positivo = atribuir un contrato a la empresa equivocada).';
