-- Migración 012: corrige duplicación de filas 'sin_resolver' en geografia_alias.
--
-- Bug real encontrado en producción: el UNIQUE constraint original incluye
-- geografia_id, pero en Postgres NULL <> NULL para efectos de unicidad — así que
-- cada corrida del pipeline que encontraba el mismo valor aún sin resolver
-- insertaba una fila NUEVA en vez de respetar ON CONFLICT DO NOTHING. Tras varias
-- corridas manuales esta sesión, "CUNDINAMARCA" llegó a tener 962 filas idénticas
-- de sin_resolver, inflando artificialmente la métrica de "deuda de ontología".
--
-- Fix: un índice único parcial específico para metodo='sin_resolver' (donde
-- geografia_id siempre es NULL) — ahí sí se puede garantizar unicidad real por
-- valor, sin el problema de NULL<>NULL, porque el índice no incluye la columna NULL.

-- 1. Limpiar duplicados existentes: dejar solo la fila más antigua de cada grupo.
DELETE FROM ontologia.geografia_alias ga
WHERE ga.metodo = 'sin_resolver'
  AND ga.alias_id NOT IN (
    SELECT min(alias_id)
    FROM ontologia.geografia_alias
    WHERE metodo = 'sin_resolver'
    GROUP BY esquema_origen, tabla_origen, columna_origen, valor_original
  );

-- 2. Índice único parcial que sí deduplica sin_resolver correctamente.
CREATE UNIQUE INDEX IF NOT EXISTS uq_geografia_alias_sin_resolver
    ON ontologia.geografia_alias (esquema_origen, tabla_origen, columna_origen, valor_original)
    WHERE metodo = 'sin_resolver';
