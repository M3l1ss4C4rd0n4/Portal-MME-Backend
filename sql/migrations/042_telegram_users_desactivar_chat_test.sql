-- Migración 042: desactivar fila de prueba en sector_energetico.telegram_users — Fase 44
--
-- Hallazgo operativo real (2026-09): sector_energetico.telegram_users tiene
-- una fila de prueba (id=304, chat_id=12345, username='test', creada
-- 2026-04-11) que broadcast_telegram() intenta notificar en CADA alerta
-- (incluidas las de vigilancia normativa CREG), ya que la función manda a
-- "todos los usuarios activos sin filtro adicional" — causando un
-- `400 Bad Request: chat not found` real y repetido en los logs por cada
-- broadcast, desde que se creó esa fila.
--
-- Se desactiva (activo=FALSE), no se borra — mismo patrón ya usado para
-- Edgar Pérez/Sara Arévalo en sector_energetico.alert_recipients:
-- reversible, y `activo` ya es la columna diseñada exactamente para esto.

UPDATE sector_energetico.telegram_users
SET activo = FALSE
WHERE id = 304 AND chat_id = 12345 AND username = 'test';
