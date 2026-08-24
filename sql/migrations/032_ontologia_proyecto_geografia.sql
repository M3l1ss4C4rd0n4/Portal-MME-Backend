-- Migración 032: ontologia.proyecto_geografia — Fase 23 Bloque 2
--
-- dim_proyecto no tenía ningún vínculo geográfico estructurado — no se podía
-- responder "¿qué proyectos hay en La Guajira?" con un join limpio. Tabla
-- puente muchos-a-muchos (no una sola columna geografia_id en dim_proyecto)
-- porque un proyecto puede abarcar más de un municipio (ej. varios registros
-- de colombia_solar.base.proyecto con texto multi-municipio, marcados
-- es_compuesto=TRUE en proyecto_alias — esos NO se resuelven aquí a
-- propósito, mismo principio de "nunca partir un valor compuesto
-- automáticamente" ya aplicado en geografia_alias/empresa_alias).

CREATE TABLE IF NOT EXISTS ontologia.proyecto_geografia (
    proyecto_id   INTEGER NOT NULL REFERENCES ontologia.dim_proyecto(proyecto_id),
    geografia_id  INTEGER NOT NULL REFERENCES ontologia.dim_geografia(geografia_id),
    PRIMARY KEY (proyecto_id, geografia_id)
);

GRANT SELECT ON ontologia.proyecto_geografia TO mme_user;

COMMENT ON TABLE ontologia.proyecto_geografia IS
    'Vínculo muchos-a-muchos proyecto↔geografía, resuelto vía '
    'ontologia.f_resolver_geografia() sobre departamento/municipio de la fila '
    'fuente de cada proyecto — nunca sobre valores compuestos multi-municipio.';
