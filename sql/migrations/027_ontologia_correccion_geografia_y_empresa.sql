-- Migración 027: Fase 17 — correcciones no ambiguas para "terminar completamente
-- la ontología": índice único de empresa (Gap 3) + corrección de corrupción real
-- en dim_geografia + tabla de alias geográficos curados + tier 3 de
-- f_resolver_geografia() (Gap 4). Todo lo de esta migración es objetivamente
-- correcto (verificado contra datos en vivo / DIVIPOLA), a diferencia de la
-- migración 028 (cambio de nombre visible, separada a propósito).

-- ─── Gap 3: NO se crea un índice único sobre nit_normalizado — se verificó en
-- vivo (a diferencia de lo asumido inicialmente) que 8 NITs ya tienen
-- legítimamente 2 filas en dim_empresa (mismo NIT, distinto codigo_sui: la
-- misma empresa registrada en más de una localidad/punto de servicio ante la
-- SUI, ej. NIT 846000021 con codigo_sui '1759' y '1759 - 520'). Un UNIQUE
-- rompería esa realidad de los datos. La idempotencia de
-- seed_dim_empresa_desde_supervision() (Python) se logra con
-- INSERT ... WHERE NOT EXISTS en vez de ON CONFLICT.

-- ─── Gap 4a: corrección de corrupción real en dim_geografia.nombre_municipio.
-- Causa raíz: seed_dim_geografia() (Fase 1, sembrado desde supervision.contratos
-- en texto libre) no tenía tiebreaker por limpieza de nombre en su
-- DISTINCT ON (muni_cod) — lo que haya ordenado primero para ese código DANE
-- quedó fijo. seed_dim_geografia_desde_divipola() (Fase 7) nunca pudo corregirlo
-- porque usa ON CONFLICT (codigo_dane_municipio) DO NOTHING. Verificado cada
-- caso contra data/referencia/divipola_dane.csv antes de corregir.
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Nátaga'
    WHERE codigo_dane_municipio = '41483' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Albania'
    WHERE codigo_dane_municipio = '44035' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Uribe'
    WHERE codigo_dane_municipio = '50370' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Policarpa'
    WHERE codigo_dane_municipio = '52540' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Bochalema'
    WHERE codigo_dane_municipio = '54099' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'El Carmen'
    WHERE codigo_dane_municipio = '54245' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Chima'
    WHERE codigo_dane_municipio = '68176' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Tona'
    WHERE codigo_dane_municipio = '68820' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Alpujarra'
    WHERE codigo_dane_municipio = '73024' AND fuente = 'DANE';

COMMENT ON TABLE ontologia.dim_geografia IS
    'Catálogo geográfico DANE (1.122 municipios). 8 filas fuente=DANE corregidas '
    'en migración 027 (nombres corruptos heredados de la siembra Fase 1 desde '
    'texto libre, nunca sincronizados por el ON CONFLICT DO NOTHING del overlay '
    'DIVIPOLA de Fase 7) — ver migración 027 para el detalle caso por caso.';

-- ─── Gap 4b: tabla de alias geográficos curados a mano — pares (departamento,
-- municipio) de texto libre verificados contra DIVIPOLA que NUNCA deben
-- resolverse por similitud automática (pg_trgm falla en varios casos reales,
-- ej. "SANTIAGO DE CALI" no acerca "Cali" a su top-3 de candidatos).
CREATE TABLE IF NOT EXISTS ontologia.geografia_alias_curado (
    curado_id           SERIAL PRIMARY KEY,
    patron_departamento TEXT,             -- NULL = resolver solo por nombre de municipio (inequívoco)
    patron_municipio    TEXT NOT NULL,    -- normalizado: upper + unaccent + trim
    geografia_id        INTEGER NOT NULL REFERENCES ontologia.dim_geografia(geografia_id),
    nota                TEXT,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patron_departamento, patron_municipio)
);

-- El UNIQUE de arriba no deduplica filas con patron_departamento NULL (NULL <>
-- NULL en Postgres, no dispara el conflicto) — la mayoría de las filas curadas
-- son justo de ese tipo (nombre de municipio inequívoco, sin necesitar depto).
-- Índice único parcial adicional para ese caso.
CREATE UNIQUE INDEX IF NOT EXISTS uq_geografia_alias_curado_muni_solo
    ON ontologia.geografia_alias_curado (patron_municipio)
    WHERE patron_departamento IS NULL;

COMMENT ON TABLE ontologia.geografia_alias_curado IS
    'Pares (departamento, municipio) de texto libre verificados a mano contra '
    'DIVIPOLA, para variantes que nunca deben resolverse por similitud automática '
    '(pg_trgm falla en casos reales, ej. "SAN ANDRÉS DE TUMACO" prioriza "San '
    'Andrés" — departamento equivocado). patron_departamento NULL = nombre de '
    'municipio inequívoco por sí solo; NOT NULL = requiere el par exacto porque '
    'el nombre existe en más de un departamento (ej. Rionegro en Antioquia Y '
    'Santander). Usada como 3er nivel de ontologia.f_resolver_geografia() y por '
    'los resolvers Python (build_geografia_alias.py), en ese orden de prioridad.';

GRANT SELECT ON ontologia.geografia_alias_curado TO mme_user;

INSERT INTO ontologia.geografia_alias_curado (patron_departamento, patron_municipio, geografia_id, nota)
SELECT 'ANTIOQUIA', 'RIO NEGRO', geografia_id, 'Rionegro existe en Antioquia Y Santander — requiere el par exacto'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '05615'
UNION ALL
SELECT NULL, 'CARTAGENA DE INDIAS', geografia_id, 'Nombre oficial DIVIPOLA de Cartagena (Bolívar)'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '13001'
UNION ALL
SELECT NULL, 'SANTIAGO DE CALI', geografia_id, 'Nombre oficial DIVIPOLA de Cali (Valle del Cauca)'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '76001'
UNION ALL
SELECT NULL, 'SAN ANDRES DE TUMACO', geografia_id, 'Nombre oficial DIVIPOLA de Tumaco (Nariño)'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '52835'
UNION ALL
SELECT NULL, 'MARIQUITA', geografia_id, 'Nombre corto de San Sebastián de Mariquita (Tolima)'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '73443'
UNION ALL
SELECT NULL, 'DOS QUEBRADAS', geografia_id, 'Variante con espacio de Dosquebradas (Risaralda)'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '66170'
UNION ALL
SELECT NULL, 'VILLA GARZON', geografia_id, 'Variante con espacio de Villagarzón (Putumayo)'
    FROM ontologia.dim_geografia
    WHERE nombre_departamento_normalizado = 'PUTUMAYO' AND nombre_municipio ILIKE 'Villagarz%'
UNION ALL
SELECT NULL, 'VALLE DEL GUAMEZ', geografia_id, 'Variante de ortografía de Valle Del Guamuez (Putumayo)'
    FROM ontologia.dim_geografia
    WHERE nombre_departamento_normalizado = 'PUTUMAYO' AND nombre_municipio_normalizado = 'VALLE DEL GUAMUEZ'
UNION ALL
SELECT NULL, 'BOGOTA D.C.', geografia_id, 'Variante sin coma de Bogotá, D.C.'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '11001'
UNION ALL
SELECT NULL, 'BOGOTA D.C', geografia_id, 'Variante sin coma ni punto final de Bogotá, D.C.'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '11001'
UNION ALL
SELECT NULL, 'BOGOTA. D.C.', geografia_id, 'Variante con punto en vez de coma de Bogotá, D.C.'
    FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '11001'
-- Sin target explícito (a diferencia de otras migraciones del proyecto): hay 2
-- índices únicos aplicables (el UNIQUE de la tabla y el parcial de solo-municipio)
-- y esta única sentencia inserta filas de ambos tipos — un target explícito solo
-- puede apuntar a uno de los dos constraints.
ON CONFLICT DO NOTHING;

-- ─── Gap 4c: tier 3 en f_resolver_geografia() (curado, solo si tiers 1-2 no
-- resolvieron) + btrim() en los 2 tiers existentes (bug real: "MONTERIA " con
-- espacio final, valor real en subsidios.subsidios_mapa, nunca matcheaba
-- "MONTERIA" pese a ortografía idéntica).
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
    -- tier 1: match exacto (departamento, municipio) normalizados
    SELECT g.geografia_id, g.codigo_dane_departamento, g.codigo_dane_municipio,
           g.nombre_departamento, g.nombre_municipio, g.region
    FROM ontologia.dim_geografia g
    WHERE upper(ontologia.f_unaccent(btrim(replace(p_departamento, '_', ' ')))) = g.nombre_departamento_normalizado
      AND upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))    = g.nombre_municipio_normalizado
    UNION ALL
    -- tier 2: municipio nacionalmente único (solo si tier 1 no encontró nada)
    SELECT g2.geografia_id, g2.codigo_dane_departamento, g2.codigo_dane_municipio,
           g2.nombre_departamento, g2.nombre_municipio, g2.region
    FROM ontologia.v_municipio_nombre_unico u
    JOIN ontologia.dim_geografia g2 ON g2.geografia_id = u.geografia_id
    WHERE u.municipio_normalizado = upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))
      AND NOT EXISTS (
          SELECT 1 FROM ontologia.dim_geografia g3
          WHERE upper(ontologia.f_unaccent(btrim(replace(p_departamento, '_', ' ')))) = g3.nombre_departamento_normalizado
            AND upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))    = g3.nombre_municipio_normalizado
      )
    UNION ALL
    -- tier 3: alias curado a mano (solo si tiers 1-2 no encontraron nada)
    SELECT g4.geografia_id, g4.codigo_dane_departamento, g4.codigo_dane_municipio,
           g4.nombre_departamento, g4.nombre_municipio, g4.region
    FROM ontologia.geografia_alias_curado c
    JOIN ontologia.dim_geografia g4 ON g4.geografia_id = c.geografia_id
    WHERE (c.patron_departamento IS NULL
           OR c.patron_departamento = upper(ontologia.f_unaccent(btrim(replace(p_departamento, '_', ' ')))))
      AND c.patron_municipio = upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))
      AND NOT EXISTS (
          SELECT 1 FROM ontologia.dim_geografia g5
          WHERE upper(ontologia.f_unaccent(btrim(replace(p_departamento, '_', ' ')))) = g5.nombre_departamento_normalizado
            AND upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))    = g5.nombre_municipio_normalizado
      )
      AND NOT EXISTS (
          SELECT 1 FROM ontologia.v_municipio_nombre_unico u2
          WHERE u2.municipio_normalizado = upper(ontologia.f_unaccent(btrim(replace(p_municipio, '_', ' '))))
      )
    LIMIT 1;
$$;

COMMENT ON FUNCTION ontologia.f_resolver_geografia(text, text) IS
    'Resuelve (departamento, municipio) de texto libre a dim_geografia en 3 '
    'niveles de prioridad: 1) match exacto normalizado, 2) municipio '
    'nacionalmente único, 3) alias curado a mano (geografia_alias_curado). '
    'btrim() agregado en migración 027 (bug: valores con espacio final nunca '
    'matcheaban). Usada por las 6 vistas _geo con join por nombre.';

-- Refrescar las vistas para reflejar la corrección de nombres + el nuevo tier 3.
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_comunidades_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_fisico_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_documental_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_fenoge_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_colombia_solar_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_subsidios_mapa_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_departamento;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_municipio;
