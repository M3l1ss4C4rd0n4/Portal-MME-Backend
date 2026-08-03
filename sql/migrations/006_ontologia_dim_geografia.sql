-- Migración 006: ontologia.dim_geografia + ontologia.geografia_alias
--
-- Ningún esquema de negocio tiene hoy un catálogo de departamentos/municipios DANE.
-- departamento no es texto uniforme entre esquemas (mayúsculas/tildes/valores
-- compuestos como "Bolivar/Cesar/Cordoba/Sucre"), así que el cruce necesita una
-- dimensión + una tabla de alias (nunca se escribe geografia_id dentro de las
-- tablas de negocio — así ningún ETL existente cambia una sola línea).
--
-- Semilla real: supervision.contratos es la única tabla con codigo_dane_departamento/
-- codigo_dane_municipio confiables. Se completa con el CSV oficial DANE (divipola) en
-- server/data/referencia/divipola_dane.csv, cargado por
-- server/scripts/ontologia/build_geografia_alias.py (no se carga aquí en SQL puro
-- porque el proceso de resolución de alias requiere Python: unaccent + revisión humana
-- de valores compuestos).

-- unaccent() es STABLE, no IMMUTABLE (depende del diccionario de text search) — Postgres
-- rechaza usarlo directo en una columna GENERATED. Wrapper IMMUTABLE estándar:
CREATE OR REPLACE FUNCTION ontologia.f_unaccent(text)
    RETURNS text AS $$
    SELECT unaccent('unaccent', $1)
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;

CREATE TABLE IF NOT EXISTS ontologia.dim_geografia (
    geografia_id             SERIAL PRIMARY KEY,
    codigo_dane_departamento CHAR(2) NOT NULL,
    codigo_dane_municipio    CHAR(5) NOT NULL,
    nombre_departamento      TEXT NOT NULL,
    nombre_municipio         TEXT NOT NULL,
    nombre_departamento_normalizado TEXT GENERATED ALWAYS AS
        (upper(ontologia.f_unaccent(nombre_departamento))) STORED,
    nombre_municipio_normalizado TEXT GENERATED ALWAYS AS
        (upper(ontologia.f_unaccent(nombre_municipio))) STORED,
    region                    TEXT,
    fuente                    TEXT NOT NULL DEFAULT 'DANE',
    activo                    BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (codigo_dane_municipio)
);

CREATE INDEX IF NOT EXISTS idx_dim_geografia_depto_norm
    ON ontologia.dim_geografia (nombre_departamento_normalizado);
CREATE INDEX IF NOT EXISTS idx_dim_geografia_muni_norm
    ON ontologia.dim_geografia (nombre_municipio_normalizado);
CREATE INDEX IF NOT EXISTS idx_dim_geografia_depto_cod
    ON ontologia.dim_geografia (codigo_dane_departamento);

COMMENT ON TABLE ontologia.dim_geografia IS
    'Dimensión maestra de geografía DANE (departamento+municipio). Semilla desde '
    'supervision.contratos, completada con divipola_dane.csv.';

CREATE TABLE IF NOT EXISTS ontologia.geografia_alias (
    alias_id       SERIAL PRIMARY KEY,
    esquema_origen TEXT NOT NULL,
    tabla_origen   TEXT NOT NULL,
    columna_origen TEXT NOT NULL,
    valor_original TEXT NOT NULL,
    geografia_id   INTEGER REFERENCES ontologia.dim_geografia(geografia_id),
    es_compuesto   BOOLEAN NOT NULL DEFAULT FALSE,
    metodo         TEXT NOT NULL
        CHECK (metodo IN ('exacto_normalizado', 'curado_manual', 'sin_resolver')),
    revisado_por   TEXT,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (esquema_origen, tabla_origen, columna_origen, valor_original, geografia_id)
);

CREATE INDEX IF NOT EXISTS idx_geografia_alias_lookup
    ON ontologia.geografia_alias (esquema_origen, tabla_origen, columna_origen, valor_original);
CREATE INDEX IF NOT EXISTS idx_geografia_alias_pendientes
    ON ontologia.geografia_alias (metodo) WHERE metodo = 'sin_resolver';

COMMENT ON TABLE ontologia.geografia_alias IS
    'Mapeo de valores de texto libre (departamento/municipio) de cada esquema de '
    'negocio hacia dim_geografia. es_compuesto=TRUE cuando un valor_original '
    '(ej. "Bolivar/Cesar/Cordoba/Sucre") produce varias filas, una por geografia_id.';
