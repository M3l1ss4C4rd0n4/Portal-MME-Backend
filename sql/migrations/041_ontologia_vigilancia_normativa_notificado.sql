-- Migración 041: ontologia.vigilancia_normativa_notificado — Fase 44
--
-- Causa raíz del spam diario de vigilancia_normativa_creg.py: el NIVEL 1
-- (notas de vigencia, alta confianza, Fase 37) usa un `vistos = set()` local
-- a cada ejecución del script — sin ninguna tabla que recuerde "esto ya se
-- notificó", el mismo hallazgo (ej. la propia Resolución CREG 101 112/2026
-- que motivó el mecanismo) se reenvía idéntico por Telegram/email todos los
-- días mientras siga dentro de la ventana de retención de
-- ANIOS_RETENCION_CREG años — confirmado en logs, mismo conteo (~25
-- hallazgos) repetido en 10+ corridas consecutivas desde 2026-08-31.
--
-- Esta tabla persiste, por hallazgo individual (mismo `clave` que ya usa
-- _detectar_modificaciones_via_notas_vigencia() para deduplicar en memoria,
-- hasheado con SHA-256), cuándo se vio por primera vez y cuándo se notificó
-- por última vez — permitiendo que el script filtre antes de notificar en
-- vez de reenviar todo lo que encuentra en cada corrida.
--
-- `revisado_en`/`revisado_por` quedan reservados para un futuro flujo humano
-- de "ya apliqué el cambio de código correspondiente" — sin usar todavía
-- (decisión explícita: notificación única, sin recordatorio periódico ni
-- flujo de resolución en esta ronda).

CREATE TABLE IF NOT EXISTS ontologia.vigilancia_normativa_notificado (
    clave_hash              TEXT PRIMARY KEY,
    resolucion_nucleo       TEXT NOT NULL,
    elemento                TEXT NOT NULL,
    accion                  TEXT NOT NULL,
    articulo_modificador    TEXT NOT NULL,
    resolucion_modificadora TEXT NOT NULL,
    primera_deteccion_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultima_notificacion_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    veces_notificado        INTEGER NOT NULL DEFAULT 1,
    revisado_en             TIMESTAMPTZ,
    revisado_por            TEXT
);

CREATE INDEX IF NOT EXISTS idx_vigilancia_normativa_notificado_resolucion
    ON ontologia.vigilancia_normativa_notificado (resolucion_nucleo);

GRANT SELECT, INSERT, UPDATE ON ontologia.vigilancia_normativa_notificado TO mme_user;

COMMENT ON TABLE ontologia.vigilancia_normativa_notificado IS
    'Fase 44 — hallazgos de NIVEL 1 (notas de vigencia) de vigilancia_normativa_creg.py '
    'ya notificados, para dejar de reenviar el mismo hallazgo cada día mientras esté '
    'dentro de la ventana de retención de ANIOS_RETENCION_CREG años.';
