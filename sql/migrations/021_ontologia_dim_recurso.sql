-- Migración 021: ontologia.dim_recurso — Fase 13 Bloque B
-- (Planta/Recurso de generación como objeto de primera clase)
--
-- Hoy "planta" es solo un código XM (sector_energetico.metrics.recurso) o un
-- nombre libre mencionado en texto (ej. "CARTAGENA 1" en los informes de
-- SeguimientoDespacho indexados por RAG) — sin un objeto de dominio que las
-- una. sector_energetico.catalogos (catalogo='ListadoRecursos', sincronizado
-- desde la propia API de XM) ya tiene el catálogo completo (código, nombre,
-- tipo) pero mezclado con ListadoRios/ListadoAgentes en una tabla genérica de
-- otro esquema. Esta migración le da a "Recurso" el mismo tratamiento de
-- objeto de dominio que ya tienen geografía, empresa, proyecto y métrica —
-- confirmado que el nombre coincide exactamente con las menciones de texto
-- libre en los informes de despacho (ej. "CARTAGENA 1" → código CTG1, TERMICA).

CREATE TABLE IF NOT EXISTS ontologia.dim_recurso (
    recurso_id      SERIAL PRIMARY KEY,
    codigo_xm       TEXT NOT NULL UNIQUE,   -- código XM del recurso (ej. 'CTG1')
    nombre          TEXT NOT NULL,          -- nombre público (ej. 'CARTAGENA 1') — coincide con menciones en informes
    tipo            TEXT,                   -- HIDRAULICA | TERMICA | SOLAR | EOLICA | COGENERADOR
    region          TEXT,
    capacidad       DOUBLE PRECISION,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado_en  TIMESTAMPTZ,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dim_recurso_nombre ON ontologia.dim_recurso (nombre);
CREATE INDEX IF NOT EXISTS idx_dim_recurso_tipo ON ontologia.dim_recurso (tipo);

GRANT SELECT ON ontologia.dim_recurso TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia GRANT SELECT ON TABLES TO mme_user;

COMMENT ON TABLE ontologia.dim_recurso IS
    'Catálogo de plantas/recursos de generación (Recurso como objeto de '
    'primera clase). Sembrado 1:1 desde sector_energetico.catalogos '
    '(catalogo=''ListadoRecursos''), con codigo_xm como llave para unir con '
    'sector_energetico.metrics.recurso y con menciones de texto libre en '
    'informes de despacho indexados por RAG (mismo nombre).';
