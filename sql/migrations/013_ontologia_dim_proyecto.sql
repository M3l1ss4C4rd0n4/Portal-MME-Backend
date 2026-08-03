-- Migración 013: ontologia.dim_proyecto + ontologia.proyecto_alias — Fase 7 Parte B
-- (Proyecto como objeto de primera clase, Palantir-IA)
--
-- Hoy "proyecto" es solo un campo de texto disperso en varios esquemas:
-- contratos_or.seguimiento_avance_fisico.nombre_proyecto_id (21 valores, formato
-- limpio "01 - Nuquí"), colombia_solar.base.proyecto (texto libre, incluye
-- proyectos multi-municipio como "San Miguel, Valle del Guamuez,Villa Garzon,
-- Puerto Guzman" — mismo patrón de valores compuestos ya resuelto para
-- departamentos en Fase 1). Esta migración le da a "Proyecto" el mismo tratamiento
-- de objeto de dominio que ya tienen geografía y empresa.

CREATE TABLE IF NOT EXISTS ontologia.dim_proyecto (
    proyecto_id     SERIAL PRIMARY KEY,
    nombre_canonico TEXT NOT NULL,
    programa        TEXT NOT NULL,   -- 'contratos_or' | 'colombia_solar' | 'fenoge'
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (nombre_canonico, programa)
);

CREATE TABLE IF NOT EXISTS ontologia.proyecto_alias (
    alias_id        SERIAL PRIMARY KEY,
    esquema_origen  TEXT NOT NULL,
    tabla_origen    TEXT NOT NULL,
    columna_origen  TEXT NOT NULL,
    valor_original  TEXT NOT NULL,
    proyecto_id     INTEGER REFERENCES ontologia.dim_proyecto(proyecto_id),
    es_compuesto    BOOLEAN NOT NULL DEFAULT FALSE,
    metodo          TEXT NOT NULL
        CHECK (metodo IN ('exacto_normalizado', 'curado_manual', 'sin_resolver')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (esquema_origen, tabla_origen, columna_origen, valor_original, proyecto_id)
);

-- Mismo fix aplicado en la migración 012 a geografia_alias: índice único parcial
-- para 'sin_resolver' (proyecto_id siempre NULL ahí), porque NULL <> NULL rompería
-- el ON CONFLICT sobre el constraint que incluye proyecto_id.
CREATE UNIQUE INDEX IF NOT EXISTS uq_proyecto_alias_sin_resolver
    ON ontologia.proyecto_alias (esquema_origen, tabla_origen, columna_origen, valor_original)
    WHERE metodo = 'sin_resolver';

CREATE INDEX IF NOT EXISTS idx_proyecto_alias_lookup
    ON ontologia.proyecto_alias (esquema_origen, tabla_origen, columna_origen, valor_original);

GRANT SELECT ON ontologia.dim_proyecto, ontologia.proyecto_alias TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia GRANT SELECT ON TABLES TO mme_user;

COMMENT ON TABLE ontologia.dim_proyecto IS
    'Dimensión maestra de proyectos (Proyecto como objeto de primera clase). '
    'Semilla desde contratos_or.seguimiento_avance_fisico.nombre_proyecto_id.';
