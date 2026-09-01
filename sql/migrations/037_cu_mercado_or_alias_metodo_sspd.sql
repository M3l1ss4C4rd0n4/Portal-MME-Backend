-- Migración 037 — Fase 40 (Costo Unitario): actualiza metodo permitido en
-- cu_mercado_or_alias tras reconstruir el mapeo con la Tabla 26 del
-- Boletín Tarifario SSPD 4T-2025 (fuente oficial operador↔mercado),
-- reemplazando la curación por coincidencia de departamento (035) por una
-- basada en la asignación explícita de la SSPD.

ALTER TABLE cu_mercado_or_alias
    DROP CONSTRAINT IF EXISTS cu_mercado_or_alias_metodo_check;

ALTER TABLE cu_mercado_or_alias
    ADD CONSTRAINT cu_mercado_or_alias_metodo_check
    CHECK (metodo IN (
        'sspd_tabla26',
        'sspd_tabla26_variante_nombre',
        'sin_resolver'
    ));
