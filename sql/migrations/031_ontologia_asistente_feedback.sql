-- Migración 031: ontologia.asistente_feedback — Fase 23 Bloque 2
--
-- Feedback de usuario (👍/👎) sobre respuestas del Asistente IA — no existía
-- ningún mecanismo de esto en el portal (ni en /asistente ni en ningún otro
-- dashboard). Sin esto, nadie tiene ninguna señal cuantitativa de si el
-- Asistente responde bien en producción real, más allá de leer manualmente
-- las preguntas reales en los logs.

CREATE TABLE IF NOT EXISTS ontologia.asistente_feedback (
    feedback_id   SERIAL PRIMARY KEY,
    turno_id      TEXT,
    pregunta      TEXT NOT NULL,
    respuesta     TEXT NOT NULL,
    util          BOOLEAN NOT NULL,
    tools_usadas  TEXT[],
    ip            TEXT,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_asistente_feedback_util ON ontologia.asistente_feedback (util, creado_en);

GRANT SELECT, INSERT ON ontologia.asistente_feedback TO mme_user;
GRANT USAGE ON SEQUENCE ontologia.asistente_feedback_feedback_id_seq TO mme_user;

COMMENT ON TABLE ontologia.asistente_feedback IS
    'Feedback explícito del usuario (👍/👎) sobre una respuesta del Asistente IA, '
    'con la pregunta/respuesta/tools usadas para poder auditar respuestas marcadas malas.';
