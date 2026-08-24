-- Definición canónica y actual de las 9 vistas materializadas de ontologia —
-- Fase 18 (mitigación del sanador de vistas).
--
-- POR QUÉ EXISTE: un ETL externo (etl_sharepoint_watcher.py, cada 5 min) hace
-- DROP TABLE ... CASCADE sobre comunidades.base/supervision.*/fenoge.*/
-- colombia_solar.*/subsidios.subsidios_mapa cuando detecta un cambio real en
-- el Excel de origen (necesario para adaptar columnas, no se puede evitar sin
-- romper esa función) — eso se lleva en cascada las vistas de ontologia
-- construidas encima. Antes de esta fase, el sanador (_recrear_vistas_
-- faltantes en scripts/ontologia/refresh_ontologia.py) reaplicaba la cadena
-- histórica completa de migraciones (008→...→029, creciendo con cada fase),
-- tardando minutos por corrida — insostenible para correr cada 5 min, y se
-- encontró en vivo que una corrida interrumpida a medias (por otro DROP
-- externo llegando en el momento, o por timeout) puede dejar vistas creadas
-- SIN su índice único, rompiendo el propio REFRESH CONCURRENTLY.
--
-- Este archivo es la fuente de verdad para reconstrucción de emergencia: una
-- sola pasada rápida (segundos) que crea solo lo que falte (todo IF NOT
-- EXISTS) envuelta en una transacción — si cualquier vista falla al crearse
-- (ej. porque la tabla origen está en mitad de su propio DROP/CREATE), todo
-- se revierte y el sanador simplemente reintenta en el próximo ciclo (5 min),
-- en vez de dejar un estado a medias (ej. una vista resumen agregando sobre
-- solo algunas de las 6 vistas base).
--
-- MANTENIMIENTO: cualquier migración futura que cambie la definición SQL de
-- una de estas 9 vistas DEBE actualizar este archivo también — es lo que usa
-- el sanador automático (tasks.ontologia_tasks.verificar_vistas_ontologia,
-- cada 5 min) y _recrear_vistas_faltantes(), no las migraciones históricas.

BEGIN;

-- Las 6 vistas "_geo" con resolución de nombre libre vía
-- ontologia.f_resolver_geografia() (match exacto -> municipio único nacional
-- -> alias curado a mano, ver migración 025/027).

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_comunidades_geo AS
SELECT c.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM comunidades.base c
LEFT JOIN LATERAL ontologia.f_resolver_geografia(c.departamento, c.municipio) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_comunidades_geo_id ON ontologia.mv_comunidades_geo (id);
GRANT SELECT ON ontologia.mv_comunidades_geo TO mme_user;

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_contratos_or_fisico_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_fisico t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_contratos_or_fisico_geo_id ON ontologia.mv_contratos_or_fisico_geo (id);
GRANT SELECT ON ontologia.mv_contratos_or_fisico_geo TO mme_user;

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_contratos_or_documental_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_documental t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_contratos_or_documental_geo_id ON ontologia.mv_contratos_or_documental_geo (id);
GRANT SELECT ON ontologia.mv_contratos_or_documental_geo TO mme_user;

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_fenoge_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM fenoge.comunidades t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_fenoge_geo_id ON ontologia.mv_fenoge_geo (id);
GRANT SELECT ON ontologia.mv_fenoge_geo TO mme_user;

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_colombia_solar_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM colombia_solar.base t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_colombia_solar_geo_id ON ontologia.mv_colombia_solar_geo (id);
GRANT SELECT ON ontologia.mv_colombia_solar_geo TO mme_user;

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_subsidios_mapa_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM subsidios.subsidios_mapa t
LEFT JOIN LATERAL ontologia.f_resolver_geografia(t.departamento::text, t.municipio::text) g ON true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_subsidios_mapa_geo_id ON ontologia.mv_subsidios_mapa_geo (id);
GRANT SELECT ON ontologia.mv_subsidios_mapa_geo TO mme_user;

-- supervision.contratos ya trae codigo_dane_departamento/codigo_dane_municipio
-- propios (es la semilla de dim_geografia) — join directo por código, sin
-- pasar por texto libre. Sin cambios desde la migración 008.
CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_supervision_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento AS geo_codigo_dane_departamento,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM supervision.contratos t
LEFT JOIN ontologia.dim_geografia g
    ON LPAD(ROUND(t.codigo_dane_municipio)::text, 5, '0') = g.codigo_dane_municipio;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_supervision_geo_id ON ontologia.mv_supervision_geo (id);
GRANT SELECT ON ontologia.mv_supervision_geo TO mme_user;

-- Vistas de cruce multi-dominio — dependen de las 6 vistas "_geo" de arriba,
-- por eso van al final (deben existir primero dentro de esta misma transacción).

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_resumen_departamento AS
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_resumen_departamento_cod
    ON ontologia.mv_resumen_departamento (codigo_dane_departamento);
GRANT SELECT ON ontologia.mv_resumen_departamento TO mme_user;
COMMENT ON MATERIALIZED VIEW ontologia.mv_resumen_departamento IS
    'Vista 360 por departamento. Nombre canónico: prefiere la fuente DIVIPOLA '
    '(oficial DANE) cuando un mismo código tiene variantes de nombre entre fuentes.';

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_resumen_municipio AS
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_resumen_municipio_cod
    ON ontologia.mv_resumen_municipio (codigo_dane_municipio);
GRANT SELECT ON ontologia.mv_resumen_municipio TO mme_user;
COMMENT ON MATERIALIZED VIEW ontologia.mv_resumen_municipio IS
    'Vista 360 por municipio — mismo patrón que mv_resumen_departamento pero '
    'al grano de municipio DANE, reutilizando las mismas vistas _geo.';

COMMIT;
