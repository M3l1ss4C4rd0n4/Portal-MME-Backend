-- Migración 024: normaliza nombre_departamento para TODOS los departamentos
-- que aún tuvieran más de una ortografía entre fuentes — Fase 13/14.
--
-- Mismo bug de fondo ya corregido puntualmente para San Andrés (migración 020):
-- la siembra original (Fase 1, desde supervision.contratos, sin tildes) y la
-- siembra DIVIPOLA (Fase 7, oficial, con tildes) dejaron nombre_departamento
-- inconsistente para el mismo codigo_dane_departamento. Se encontraron 3 casos
-- más nunca corregidos: Caquetá (18), Guainía (94), Vaupés (97) — causaban que
-- ontologia.mv_resumen_departamento tuviera filas duplicadas por código,
-- rompiendo silenciosamente su índice único (uq_mv_resumen_departamento_cod)
-- y por lo tanto el REFRESH ... CONCURRENTLY diario (fallando desde al menos
-- esta mañana sin que nada lo hubiera reportado).
--
-- Fix genérico (no solo estos 3 casos puntuales): para cualquier
-- codigo_dane_departamento con más de un nombre_departamento, normaliza todas
-- las filas al nombre de la fuente DANE-DIVIPOLA (oficial, con tildes).

UPDATE ontologia.dim_geografia AS g
SET nombre_departamento = canonico.nombre_departamento
FROM (
    SELECT DISTINCT ON (codigo_dane_departamento)
           codigo_dane_departamento, nombre_departamento
    FROM ontologia.dim_geografia
    ORDER BY codigo_dane_departamento, (fuente = 'DANE-DIVIPOLA') DESC, nombre_departamento
) AS canonico
WHERE g.codigo_dane_departamento = canonico.codigo_dane_departamento
  AND g.nombre_departamento <> canonico.nombre_departamento;

-- La vista mv_resumen_departamento en vivo resultó estar corrida con una
-- definición vieja (SELECT DISTINCT plano en vez de DISTINCT ON con
-- preferencia DIVIPOLA) — pese a que 015_ontologia_fix_guion_bajo_departamento.sql
-- en disco ya tiene la versión correcta. Causa probable: el índice único de esa
-- migración falló por los mismos duplicados que esta migración corrige arriba,
-- y con ON_ERROR_STOP=1 el resto del reintento de vistas quedó en un estado
-- parcial. Se recrea aquí explícitamente con la definición correcta para no
-- depender de reconstruir esa secuencia histórica.
DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_resumen_departamento CASCADE;

CREATE MATERIALIZED VIEW ontologia.mv_resumen_departamento AS
SELECT
    dep.codigo_dane_departamento,
    dep.nombre_departamento,
    count(DISTINCT com.id)  AS n_comunidades,
    count(DISTINCT cf.id)   AS n_contratos_or_fisico,
    count(DISTINCT fen.id)  AS n_proyectos_fenoge,
    count(DISTINCT cs.id)   AS n_proyectos_colombia_solar,
    count(DISTINCT sub.id)  AS n_registros_subsidios_mapa,
    count(DISTINCT sup.id)  AS n_contratos_supervision
FROM (
    SELECT DISTINCT ON (codigo_dane_departamento)
           codigo_dane_departamento, nombre_departamento
    FROM ontologia.dim_geografia
    ORDER BY codigo_dane_departamento, (fuente = 'DANE-DIVIPOLA') DESC, nombre_departamento
) dep
LEFT JOIN ontologia.mv_comunidades_geo com ON com.codigo_dane_departamento = dep.codigo_dane_departamento
LEFT JOIN ontologia.mv_contratos_or_fisico_geo cf ON cf.codigo_dane_departamento = dep.codigo_dane_departamento
LEFT JOIN ontologia.mv_fenoge_geo fen ON fen.codigo_dane_departamento = dep.codigo_dane_departamento
LEFT JOIN ontologia.mv_colombia_solar_geo cs ON cs.codigo_dane_departamento = dep.codigo_dane_departamento
LEFT JOIN ontologia.mv_subsidios_mapa_geo sub ON sub.codigo_dane_departamento = dep.codigo_dane_departamento
LEFT JOIN ontologia.mv_supervision_geo sup ON sup.geo_codigo_dane_departamento = dep.codigo_dane_departamento
GROUP BY 1, 2;

CREATE UNIQUE INDEX uq_mv_resumen_departamento_cod
    ON ontologia.mv_resumen_departamento (codigo_dane_departamento);

GRANT SELECT ON ontologia.mv_resumen_departamento TO mme_user;

COMMENT ON MATERIALIZED VIEW ontologia.mv_resumen_departamento IS
    'Vista 360 por departamento. Nombre canónico: prefiere la fuente DIVIPOLA '
    '(oficial DANE) cuando un mismo código tiene variantes de nombre entre fuentes.';
