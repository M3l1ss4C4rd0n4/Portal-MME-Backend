-- Migración 026: nuevo método 'municipio_unico_nacional' en geografia_alias.
--
-- Migración 025 agregó un fallback a las 6 vistas _geo (resolver por nombre de
-- municipio nacionalmente único cuando el par departamento+municipio no
-- coincide exacto). Esta migración extiende el CHECK de
-- ontologia.geografia_alias para poder registrar ese mismo criterio en la
-- tabla de auditoría — sin esto, resolver_pares_depto_municipio() (Python) no
-- podría marcar esas filas de forma distinguible de un match exacto, y el
-- backlog de sin_resolver seguiría reportando como pendientes filas que las
-- vistas ya resuelven en la práctica.

ALTER TABLE ontologia.geografia_alias DROP CONSTRAINT geografia_alias_metodo_check;

ALTER TABLE ontologia.geografia_alias
    ADD CONSTRAINT geografia_alias_metodo_check
    CHECK (metodo = ANY (ARRAY['exacto_normalizado', 'municipio_unico_nacional', 'curado_manual', 'sin_resolver']));

COMMENT ON COLUMN ontologia.geografia_alias.metodo IS
    'exacto_normalizado: match departamento+municipio exacto. '
    'municipio_unico_nacional: el par no coincidió, pero el municipio es único '
    'en Colombia (ver ontologia.v_municipio_nombre_unico) — mismo criterio que '
    'usa el fallback de ontologia.f_resolver_geografia() en las vistas _geo. '
    'curado_manual: revisado por un analista. sin_resolver: pendiente.';
