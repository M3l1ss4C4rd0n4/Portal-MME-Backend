-- 045 — Registro de entrega por canal en alertas_historial
--
-- Problema: el tracking por canal estaba invertido. La única columna que se
-- escribía era `notificacion_whatsapp_enviada`, para un canal que NO envía
-- nada (el bot de WhatsApp está instalado pero sin proveedor activo, y
-- _broadcast_alert_via_bot() no tiene ningún caller). El canal que sí
-- funciona, el correo, quedaba en FALSE: 1 de 848 filas con el flag en TRUE.
-- Y Telegram, que es el único canal con tráfico real (7 usuarios activos),
-- no tenía ninguna columna donde registrarse.
--
-- Esta migración agrega las columnas de Telegram. El código de
-- tasks/anomaly_tasks.py::_registrar_alerta_bd pasa a escribir los tres
-- canales con su resultado real.

ALTER TABLE sector_energetico.alertas_historial
    ADD COLUMN IF NOT EXISTS notificacion_telegram_enviada boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS fecha_notificacion_telegram   timestamp,
    ADD COLUMN IF NOT EXISTS destinatarios_telegram        text[];

COMMENT ON COLUMN sector_energetico.alertas_historial.notificacion_telegram_enviada
    IS 'TRUE si el broadcast de Telegram reportó al menos un envío exitoso.';
COMMENT ON COLUMN sector_energetico.alertas_historial.notificacion_whatsapp_enviada
    IS 'TRUE solo si WhatsApp envió de verdad. Hasta 2026-10-08 se escribía '
       'TRUE para cualquier envío de cualquier canal, incluso con 0 enviados.';
