-- Migración 030: recurso_mencion.documento_id → ON DELETE CASCADE
--
-- Bug de producción real, activo desde que existen menciones resueltas
-- (Fase 13/2026-08-03): la migración 022 creó recurso_mencion.documento_id
-- como FK a informes_documentos SIN 'ON DELETE CASCADE' — a diferencia de
-- informes_texto_embeddings (migración 016), que sí lo tiene para la misma
-- relación. La poda diaria de informes_diarios_xm fuera de la ventana móvil
-- de 14 días (build_informes_embeddings.py::_indexar_informes_diarios_xm)
-- intenta DELETE sobre informes_documentos, y como los informes diarios son
-- justo el tema que resolver_recurso_mencion.py escanea, la poda choca con
-- esta FK de forma sistemática, no ocasional — el corpus RAG crece sin
-- límite pese a que el diseño explícito de la ventana móvil buscaba evitarlo.

ALTER TABLE ontologia.recurso_mencion
    DROP CONSTRAINT recurso_mencion_documento_id_fkey;

ALTER TABLE ontologia.recurso_mencion
    ADD CONSTRAINT recurso_mencion_documento_id_fkey
    FOREIGN KEY (documento_id) REFERENCES ontologia.informes_documentos(documento_id)
    ON DELETE CASCADE;
