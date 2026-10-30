-- 050 — Separa los avisos técnicos de las alertas del SIN.
--
-- Motivo (2026-10-29): los destinatarios se quejaron de dos cosas distintas.
--
--   1. Les llegan avisos que no pueden atender. Los latidos del sistema
--      ("celery-worker corre código viejo", "la Senda CREG se agota en 29
--      días") salen 3 veces al día a los 5 destinatarios con el MISMO asunto
--      que una alerta real del sector: "⚠️ Alerta Energética [CRITICO]".
--      Solo quien desarrolla puede actuar sobre ellos.
--
--   2. Camilo Tautiva (Director) solo quiere los informes, no las alertas.
--
-- `recibir_alertas` no servía para separar (1): es un sí/no a todo. Esta
-- migración añade `recibir_tecnicas`, que por defecto es FALSE — nadie
-- recibe avisos técnicos salvo quien se marque explícitamente.

BEGIN;

ALTER TABLE sector_energetico.alert_recipients
    ADD COLUMN IF NOT EXISTS recibir_tecnicas BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN sector_energetico.alert_recipients.recibir_tecnicas IS
    'Avisos de salud de la plataforma (latidos, ETL caído, datos congelados, '
    'discrepancias de configuración). FALSE por defecto: solo desarrollo.';

COMMENT ON COLUMN sector_energetico.alert_recipients.recibir_alertas IS
    'Alertas del estado del SIN (embalses, demanda, precio, estrés térmico). '
    'No incluye los avisos técnicos: para eso está recibir_tecnicas.';

ALTER TABLE sector_energetico.telegram_users
    ADD COLUMN IF NOT EXISTS recibir_tecnicas BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN sector_energetico.telegram_users.recibir_tecnicas IS
    'Mismo criterio que alert_recipients.recibir_tecnicas, para Telegram.';

-- Melissa Cardona es hoy la única persona que desarrolla y mantiene el portal.
UPDATE sector_energetico.alert_recipients
   SET recibir_tecnicas = TRUE
 WHERE correo = 'mjcardona@minenergia.gov.co';

UPDATE sector_energetico.telegram_users
   SET recibir_tecnicas = TRUE
 WHERE chat_id = 5084190952;  -- Melissa

-- Camilo Tautiva: solo informes (diario de gestión y semanal de Dirección de
-- Energía). `recibir_diario` se deja en TRUE a propósito: es la marca que usan
-- los dos informes.
UPDATE sector_energetico.alert_recipients
   SET recibir_alertas = FALSE,
       recibir_tecnicas = FALSE
 WHERE correo = 'ctautiva@minenergia.gov.co';

COMMIT;
