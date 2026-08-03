-- Migración 008: vistas materializadas de solo lectura que cruzan cada esquema de
-- negocio con ontologia.dim_geografia.
--
-- Diseño: join directo normalizado (upper(f_unaccent(...))) contra dim_geografia, NO a
-- través de geografia_alias — para tablas con departamento+municipio en la misma fila,
-- el join por la pareja normalizada es unívoco por definición (no hay ambigüedad),
-- mientras que unir por geografia_alias.columna_origen='departamento' sí sería ambiguo
-- (un mismo valor de departamento resuelve a muchos geografia_id, uno por municipio).
-- geografia_alias queda como mecanismo de auditoría/backlog (endpoint
-- /v1/ontologia/alias/pendientes), no como mecanismo de join de las MVs.
--
-- LEFT JOIN siempre: una fila sin match en dim_geografia (cobertura DANE aún parcial,
-- solo 527/1122 municipios sembrados desde supervision.contratos) se mantiene con
-- geografia_id NULL, nunca se pierde silenciosamente — permite auditar cobertura con
-- `count(*) FILTER (WHERE geografia_id IS NULL)`.
--
-- Cada MV requiere un índice único sobre su PK de origen para soportar
-- REFRESH MATERIALIZED VIEW CONCURRENTLY (no bloquea lecturas durante el refresh).

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_comunidades_geo AS
SELECT c.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM comunidades.base c
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(c.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(c.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_comunidades_geo_id ON ontologia.mv_comunidades_geo (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_contratos_or_fisico_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_fisico t
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(t.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(t.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_contratos_or_fisico_geo_id ON ontologia.mv_contratos_or_fisico_geo (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_contratos_or_documental_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM contratos_or.seguimiento_avance_documental t
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(t.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(t.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_contratos_or_documental_geo_id ON ontologia.mv_contratos_or_documental_geo (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_fenoge_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM fenoge.comunidades t
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(t.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(t.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_fenoge_geo_id ON ontologia.mv_fenoge_geo (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_colombia_solar_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM colombia_solar.base t
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(t.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(t.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_colombia_solar_geo_id ON ontologia.mv_colombia_solar_geo (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_subsidios_mapa_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM subsidios.subsidios_mapa t
LEFT JOIN ontologia.dim_geografia g
    ON upper(ontologia.f_unaccent(t.departamento)) = g.nombre_departamento_normalizado
   AND upper(ontologia.f_unaccent(t.municipio))    = g.nombre_municipio_normalizado;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_subsidios_mapa_geo_id ON ontologia.mv_subsidios_mapa_geo (id);

-- supervision.contratos ya trae codigo_dane_departamento/codigo_dane_municipio propios
-- (es la semilla de dim_geografia) — join directo por código, sin pasar por texto.
-- t.* ya trae codigo_dane_departamento/municipio propios (source de la semilla) — el de
-- dim_geografia se alias distinto para evitar colisión de nombre de columna.
CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_supervision_geo AS
SELECT t.*,
       g.geografia_id, g.codigo_dane_departamento AS geo_codigo_dane_departamento,
       g.nombre_departamento AS geo_departamento, g.nombre_municipio AS geo_municipio, g.region
FROM supervision.contratos t
LEFT JOIN ontologia.dim_geografia g
    ON LPAD(ROUND(t.codigo_dane_municipio)::text, 5, '0') = g.codigo_dane_municipio;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_supervision_geo_id ON ontologia.mv_supervision_geo (id);

-- Vista de cruce multi-dominio: el caso de uso central del proyecto — "qué existe en
-- este departamento" across comunidades, contratos OR, fenoge, colombia solar,
-- subsidios y supervisión, en una sola fila por departamento.
CREATE MATERIALIZED VIEW IF NOT EXISTS ontologia.mv_resumen_departamento AS
SELECT
    d.codigo_dane_departamento,
    d.nombre_departamento,
    count(DISTINCT com.id)  AS n_comunidades,
    count(DISTINCT cf.id)   AS n_contratos_or_fisico,
    count(DISTINCT fen.id)  AS n_proyectos_fenoge,
    count(DISTINCT cs.id)   AS n_proyectos_colombia_solar,
    count(DISTINCT sub.id)  AS n_registros_subsidios_mapa,
    count(DISTINCT sup.id)  AS n_contratos_supervision
FROM (SELECT DISTINCT codigo_dane_departamento, nombre_departamento
      FROM ontologia.dim_geografia) d
LEFT JOIN ontologia.mv_comunidades_geo com ON com.codigo_dane_departamento = d.codigo_dane_departamento
LEFT JOIN ontologia.mv_contratos_or_fisico_geo cf ON cf.codigo_dane_departamento = d.codigo_dane_departamento
LEFT JOIN ontologia.mv_fenoge_geo fen ON fen.codigo_dane_departamento = d.codigo_dane_departamento
LEFT JOIN ontologia.mv_colombia_solar_geo cs ON cs.codigo_dane_departamento = d.codigo_dane_departamento
LEFT JOIN ontologia.mv_subsidios_mapa_geo sub ON sub.codigo_dane_departamento = d.codigo_dane_departamento
LEFT JOIN ontologia.mv_supervision_geo sup ON sup.geo_codigo_dane_departamento = d.codigo_dane_departamento
GROUP BY 1, 2;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_resumen_departamento_cod
    ON ontologia.mv_resumen_departamento (codigo_dane_departamento);

COMMENT ON MATERIALIZED VIEW ontologia.mv_resumen_departamento IS
    'Vista 360 por departamento: cruza comunidades, contratos OR, FENOGE, Colombia '
    'Solar, subsidios y supervisión. Fuente para GET /v1/ontologia/geografia/{codigo}/resumen.';
