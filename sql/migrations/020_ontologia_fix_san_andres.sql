-- Migración 020: fix nombre_departamento duplicado para San Andrés (código DANE 88)
-- Fase 13 Bloque B — mismo patrón de bug ya corregido en 014/015 (La Guajira,
-- Norte de Santander, Valle del Cauca): dos siembras distintas (Fase 1 desde
-- supervision.contratos, Fase 7 desde DIVIPOLA) dejaron dos filas con el mismo
-- codigo_dane_departamento='88' pero nombre_departamento distinto:
--   - geografia_id=513  (municipio San Andrés,  88001): "Archipielago De San Andres"
--   - geografia_id=5305 (municipio Providencia, 88564): "Archipiélago De San Andrés, Providencia Y Santa Catalina"
-- Esto impedía que el resolver de alias (match exacto normalizado) encontrara
-- un único nombre de departamento consistente para variantes como "San Andrés
-- y Providencia" — quedaban en sin_resolver pese a ser un departamento real y
-- ya sembrado.

UPDATE ontologia.dim_geografia
SET nombre_departamento = 'Archipiélago De San Andrés, Providencia Y Santa Catalina'
WHERE codigo_dane_departamento = '88'
  AND nombre_departamento <> 'Archipiélago De San Andrés, Providencia Y Santa Catalina';
