-- Migración 025: fallback de resolución geográfica por municipio nacionalmente
-- único + corrección de una regresión real encontrada en producción — Fase 14/15
-- (profundizar cobertura de ontología).
--
-- CONTEXTO — dos problemas encontrados investigando el backlog de
-- ontologia.geografia_alias (850 sin_resolver, 508 en subsidios.subsidios_mapa):
--
-- 1. geografia_alias es una tabla de auditoría, NO lo que realmente resuelve
--    los datos: las 6 vistas materializadas _geo (comunidades, contratos_or
--    físico/documental, fenoge, colombia_solar, subsidios_mapa) reimplementan
--    su propio JOIN exacto por (departamento, municipio) normalizados
--    directamente contra dim_geografia, sin pasar por geografia_alias. Cuando
--    el departamento no coincide exactamente (grafía distinta, valor vacío,
--    etc.) la fila queda con geografia_id NULL aunque el municipio, por sí
--    solo, sea inequívoco en toda Colombia (ej. "AGUADAS" solo existe en
--    Caldas). Se cuantificó que ~473-556 de los 850 sin_resolver son
--    municipios nacionalmente únicos — resolubles con un fallback seguro.
--
-- 2. Al verificar el estado real de mv_comunidades_geo para diseñar el punto
--    anterior, se encontró que la vista EN VIVO había perdido el fix de la
--    migración 015 (guion_bajo -> espacio en departamento/municipio antes del
--    join) — mismo patrón de regresión silenciosa ya visto en
--    mv_resumen_departamento (migración 024). Confirmado en vivo: 200 de 589
--    filas de comunidades.base con geografia_id NULL (La Guajira, Norte de
--    Santander, San Andrés y Valle del Cauca invisibles otra vez en Vista
--    Departamental). Causa raíz probable: el sanador de vistas
--    (_recrear_vistas_faltantes) solo se agregó/perfeccionó en fases
--    posteriores a cuando esta vista se recreó por última vez tras un DROP
--    CASCADE externo, dejándola en el estado de la migración 008 (sin el fix).
--
-- DISEÑO DEL FALLBACK — nunca reemplaza el match exacto, solo cubre lo que
-- éste deja sin resolver:
--   1º intento: (departamento, municipio) normalizados, exacto — igual que hoy.
--   2º intento (solo si el 1º no encontró nada): municipio normalizado, SOLO
--      si ese nombre de municipio es único a nivel nacional (no hay dos
--      municipios en Colombia con el mismo nombre normalizado) — evita
--      cualquier ambigüedad (ej. "San José" existe en varios departamentos,
--      nunca cae en el fallback).
--
-- Encapsulado en una función SQL reutilizada por las 6 vistas (en vez de
-- repetir el JOIN LATERAL 6 veces) para que el criterio de resolución viva en
-- un solo lugar.

CREATE OR REPLACE VIEW ontologia.v_municipio_nombre_unico AS
SELECT nombre_municipio_normalizado AS municipio_normalizado,
       min(geografia_id) AS geografia_id
FROM ontologia.dim_geografia
GROUP BY nombre_municipio_normalizado
HAVING count(*) = 1;

COMMENT ON VIEW ontologia.v_municipio_nombre_unico IS
    'Municipios cuyo nombre normalizado no se repite en ningún otro departamento '
    'de Colombia (970/1.122) — base del fallback de f_resolver_geografia().';

CREATE OR REPLACE FUNCTION ontologia.f_resolver_geografia(p_departamento text, p_municipio text)
RETURNS TABLE (
    geografia_id             integer,
    codigo_dane_departamento char(2),
    codigo_dane_municipio    char(5),
    nombre_departamento      text,
    nombre_municipio         text,
    region                   text
)
LANGUAGE sql STABLE AS $$
    SELECT g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
           g.nombre_departamento, g.nombre_municipio, g.region
    FROM ontologia.dim_geografia g
    WHERE upper(ontologia.f_unaccent(replace(p_departamento, '_', ' '))) = g.nombre_departamento_normalizado
      AND upper(ontologia.f_unaccent(replace(p_municipio, '_', ' ')))    = g.nombre_municipio_normalizado
    UNION ALL
    SELECT g2.geografia_id, g2.codigo_dane_departamento, g2.codigo_dane_municipio,
           g2.nombre_departamento, g2.nombre_municipio, g2.region
    FROM ontologia.v_municipio_nombre_unico u
    JOIN ontologia.dim_geografia g2 ON g2.geografia_id = u.geografia_id
    WHERE u.municipio_normalizado = upper(ontologia.f_unaccent(replace(p_municipio, '_', ' ')))
      AND NOT EXISTS (
          SELECT 1 FROM ontologia.dim_geografia g3
          WHERE upper(ontologia.f_unaccent(replace(p_departamento, '_', ' '))) = g3.nombre_departamento_normalizado
            AND upper(ontologia.f_unaccent(replace(p_municipio, '_', ' ')))    = g3.nombre_municipio_normalizado
      )
    LIMIT 1;
$$;

COMMENT ON FUNCTION ontologia.f_resolver_geografia(text, text) IS
    'Resuelve (departamento, municipio) de texto libre a dim_geografia: match '
    'exacto normalizado primero, y si no hay match, fallback por nombre de '
    'municipio nacionalmente único. Usado por las 6 vistas _geo con join por nombre.';

-- Las 6 vistas se recrean con f_resolver_geografia() en vez del JOIN directo.
-- DROP ... CASCADE en la primera arrastra mv_resumen_departamento y
-- mv_resumen_municipio (dependen de las 6); se recrean al final, igual que en
-- la migración 024.

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_comunidades_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_comunidades_geo AS
SELECT c.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM comunidades.base c
LEFT JOIN LATERAL ontologia.f_resolver_geografia(c.departamento, c.municipio) g ON true;
CREATE UNIQUE INDEX uq_mv_comunidades_geo_id ON ontologia.mv_comunidades_geo (id);
GRANT SELECT ON ontologia.mv_comunidades_geo TO mme_user;

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_contratos_or_fisico_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_contratos_or_fisico_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_fisico t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX uq_mv_contratos_or_fisico_geo_id ON ontologia.mv_contratos_or_fisico_geo (id);
GRANT SELECT ON ontologia.mv_contratos_or_fisico_geo TO mme_user;

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_contratos_or_documental_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_contratos_or_documental_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_documental t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX uq_mv_contratos_or_documental_geo_id ON ontologia.mv_contratos_or_documental_geo (id);
GRANT SELECT ON ontologia.mv_contratos_or_documental_geo TO mme_user;

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_fenoge_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_fenoge_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM fenoge.comunidades t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX uq_mv_fenoge_geo_id ON ontologia.mv_fenoge_geo (id);
GRANT SELECT ON ontologia.mv_fenoge_geo TO mme_user;

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_colombia_solar_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_colombia_solar_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM colombia_solar.base t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX uq_mv_colombia_solar_geo_id ON ontologia.mv_colombia_solar_geo (id);
GRANT SELECT ON ontologia.mv_colombia_solar_geo TO mme_user;

DROP MATERIALIZED VIEW IF EXISTS ontologia.mv_subsidios_mapa_geo CASCADE;
CREATE MATERIALIZED VIEW ontologia.mv_subsidios_mapa_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM subsidios.subsidios_mapa t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento::text, t.municipio::text) g ON true;
CREATE UNIQUE INDEX uq_mv_subsidios_mapa_geo_id ON ontologia.mv_subsidios_mapa_geo (id);
GRANT SELECT ON ontologia.mv_subsidios_mapa_geo TO mme_user;

-- Recrear los 2 resúmenes (dependían de las 6 vistas anteriores, se cayeron
-- por CASCADE) — misma definición que migraciones 024/023, sin cambios.

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

CREATE MATERIALIZED VIEW ontologia.mv_resumen_municipio AS
SELECT
    mun.codigo_dane_departamento,
    mun.codigo_dane_municipio,
    mun.nombre_departamento,
    mun.nombre_municipio,
    count(DISTINCT com.id)  AS n_comunidades,
    count(DISTINCT cf.id)   AS n_contratos_or_fisico,
    count(DISTINCT fen.id)  AS n_proyectos_fenoge,
    count(DISTINCT cs.id)   AS n_proyectos_colombia_solar,
    count(DISTINCT sub.id)  AS n_registros_subsidios_mapa,
    count(DISTINCT sup.id)  AS n_contratos_supervision
FROM (
    SELECT DISTINCT ON (codigo_dane_municipio)
           codigo_dane_departamento, codigo_dane_municipio,
           nombre_departamento, nombre_municipio
    FROM ontologia.dim_geografia
    ORDER BY codigo_dane_municipio, (fuente = 'DANE-DIVIPOLA') DESC, nombre_municipio
) mun
LEFT JOIN ontologia.mv_comunidades_geo com ON com.codigo_dane_municipio = mun.codigo_dane_municipio
LEFT JOIN ontologia.mv_contratos_or_fisico_geo cf ON cf.codigo_dane_municipio = mun.codigo_dane_municipio
LEFT JOIN ontologia.mv_fenoge_geo fen ON fen.codigo_dane_municipio = mun.codigo_dane_municipio
LEFT JOIN ontologia.mv_colombia_solar_geo cs ON cs.codigo_dane_municipio = mun.codigo_dane_municipio
LEFT JOIN ontologia.mv_subsidios_mapa_geo sub ON sub.codigo_dane_municipio = mun.codigo_dane_municipio
LEFT JOIN ontologia.mv_supervision_geo sup
    ON LPAD(TRUNC(sup.codigo_dane_municipio)::text, 5, '0') = mun.codigo_dane_municipio
GROUP BY 1, 2, 3, 4;

CREATE UNIQUE INDEX uq_mv_resumen_municipio_cod
    ON ontologia.mv_resumen_municipio (codigo_dane_municipio);
GRANT SELECT ON ontologia.mv_resumen_municipio TO mme_user;
COMMENT ON MATERIALIZED VIEW ontologia.mv_resumen_municipio IS
    'Vista 360 por municipio (Fase 13) — mismo patrón que mv_resumen_departamento '
    'pero al grano de municipio DANE, reutilizando las mismas vistas _geo.';
