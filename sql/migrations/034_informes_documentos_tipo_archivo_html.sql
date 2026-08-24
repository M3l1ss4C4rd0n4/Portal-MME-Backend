-- Migración 034: permitir tipo_archivo = 'html' en informes_documentos
--
-- Fase 37 — normativa CREG indexada desde gestornormativo.creg.gov.co: el
-- texto se extrae de páginas HTML (Gestor Normativo Alejandría 2.0), no de
-- un PDF/PPTX/DOCX descargado como binario — los 3 únicos valores permitidos
-- hasta ahora por informes_documentos_tipo_archivo_check. Reproducido en vivo
-- (2026-08-20): el primer intento de indexar una resolución CREG falló con
-- CheckViolation al insertar tipo_archivo='txt', que tampoco estaba permitido.

ALTER TABLE ontologia.informes_documentos
    DROP CONSTRAINT informes_documentos_tipo_archivo_check;

ALTER TABLE ontologia.informes_documentos
    ADD CONSTRAINT informes_documentos_tipo_archivo_check
    CHECK (tipo_archivo = ANY (ARRAY['pdf'::text, 'pptx'::text, 'docx'::text, 'html'::text]));
