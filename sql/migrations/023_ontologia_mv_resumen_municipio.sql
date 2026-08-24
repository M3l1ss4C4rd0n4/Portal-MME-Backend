-- Migración 023: ontologia.mv_resumen_municipio — Fase 13 (profundización)
-- (Municipio como objeto de primera clase, mismo tratamiento que Departamento)
--
-- ontologia.dim_geografia ya es granular por municipio (1.122 municipios
-- DANE, Fase 7), y las vistas _geo (mv_comunidades_geo, mv_fenoge_geo, etc.)
-- ya cargan codigo_dane_municipio (verificado en vivo) — solo faltaba
-- agregarlas a ese grano en vez de solo a nivel de departamento. Mismo patrón
-- exacto que ontologia.mv_resumen_departamento (migración 014/015), cambiando
-- el GROUP BY de departamento a municipio.
--
-- NOTA IMPORTANTE (encontrado al construir esta migración): mv_resumen_departamento
-- y 3 de las 8 vistas _geo habían desaparecido de la base en producción (DROP
-- CASCADE de un ETL externo, mismo bug ya documentado en refresh_ontologia.py)
-- — se restauraron corriendo el sanador antes de esta migración. Esta migración
-- asume que las 8 vistas de la migración 008/014/015 existen.

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
    'Vista 360 por municipio (Fase 13) — mismo patrón que mv_resumen_departamento '
    'pero al grano de municipio DANE, reutilizando las mismas vistas _geo.';
