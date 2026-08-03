-- Migración 014: corrige mv_resumen_departamento — nombre de departamento duplicado.
--
-- Bug real encontrado en producción (visible en /salud-datos como corrida con
-- error): tras cargar el DIVIPOLA oficial (migración/Fase 7 Parte A), el mismo
-- codigo_dane_departamento='88' quedó con DOS nombres distintos en dim_geografia
-- — "Archipielago De San Andres" (semilla original de supervision.contratos) y
-- "Archipiélago De San Andrés, Providencia Y Santa Catalina" (nombre oficial
-- completo de DIVIPOLA). ontologia.mv_resumen_departamento asumía que
-- (codigo_dane_departamento, nombre_departamento) era único por departamento —
-- dejó de serlo al tener dos fuentes con distinta convención de nombres, y el
-- REFRESH empezó a fallar con "duplicate key value violates unique constraint
-- uq_mv_resumen_departamento_cod".
--
-- Fix: DISTINCT ON (codigo_dane_departamento) en vez de DISTINCT sobre la pareja
-- completa, prefiriendo el nombre de DIVIPOLA (fuente oficial) como canónico.

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_resumen_departamento;

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
