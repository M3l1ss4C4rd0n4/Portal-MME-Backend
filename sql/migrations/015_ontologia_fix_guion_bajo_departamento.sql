-- Migración 015: corrige ontologia.mv_comunidades_geo — guion bajo en departamento.
--
-- Bug real encontrado en producción: comunidades.base.departamento guarda 4
-- valores con guion bajo en vez de espacio ("La_Guajira", "Norte_de_Santander",
-- "San_Andrés_y_Providencia", "Valle_del_Cauca" — 168 filas en total), probable
-- artefacto del Excel/ETL de origen. upper(f_unaccent('La_Guajira')) = 'LA_GUAJIRA',
-- que nunca matchea 'LA GUAJIRA' en dim_geografia.nombre_departamento_normalizado
-- — el LEFT JOIN de mv_comunidades_geo dejaba esas 168 filas con geografia_id NULL,
-- y por lo tanto invisibles en mv_resumen_departamento (ej. La Guajira mostraba
-- 0 comunidades energéticas en Vista Departamental pese a tener 115 reales).
--
-- Fix: normalizar guion bajo -> espacio también en la condición del JOIN, antes
-- de f_unaccent(). No afecta ninguna otra tabla (verificado: es el único caso en
-- todo el proyecto) ni cambia c.* (el valor original de comunidades.base sigue
-- intacto en la fila resultante).
--
-- mv_resumen_departamento depende de mv_comunidades_geo (pg_depend) — DROP
-- CASCADE se la lleva también, así que se recrea aquí con la misma definición
-- ya corregida por la migración 014 (DISTINCT ON + preferencia por DIVIPOLA),
-- para no reintroducir ese bug ya resuelto.

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_comunidades_geo CASCADE;

CREATE MATERIALIZED VIEW ontologia.mv_comunidades_geo AS
SELECT c.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM comunidades.base c
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(replace(c.departamento, '_', ' '))) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(replace(c.municipio, '_', ' ')))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX uq_mv_comunidades_geo_id ON ontologia.mv_comunidades_geo (id);

GRANT SELECT ON ontologia.mv_comunidades_geo TO mme_user;

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
