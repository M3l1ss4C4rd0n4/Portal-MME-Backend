-- Migración 019: ontologia.informes_documentos.tema — Fase 11 Ronda 5
--
-- La búsqueda RAG (Fase 8) depende solo de similitud vectorial para encontrar
-- el documento correcto. Se verificó en la práctica que esto no es confiable:
-- contenido real y valioso (qué plantas están indisponibles en
-- InformeDiario_*_SeguimientoDespacho.pdf, el pronóstico de El Niño en
-- Boletines_energeticos_2026.pdf) no aparecía de forma consistente en los
-- resultados de la Fase 11 pese a estar indexado. El patrón de nombres de
-- archivo/carpeta es limpio y 100% consistente (verificado contra las filas
-- reales de la tabla) — permite una clasificación determinística por patrón,
-- sin depender de heurística de IA ni de similitud semántica.

ALTER TABLE ontologia.informes_documentos ADD COLUMN IF NOT EXISTS tema TEXT;

CREATE INDEX IF NOT EXISTS idx_informes_documentos_tema ON ontologia.informes_documentos (tema);

COMMENT ON COLUMN ontologia.informes_documentos.tema IS
    'Clasificación temática determinística por patrón de nombre/carpeta (ver '
    'scripts/ontologia/clasificar_tema_informes.py) — permite que la búsqueda '
    'RAG filtre por tipo de documento en vez de depender solo de similitud '
    'vectorial. NULL = fuera del dominio sector_energetico, no reclasificado.';
