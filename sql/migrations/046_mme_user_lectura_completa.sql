-- 046 · Lectura completa para mme_user
--
-- El frontend Next.js se conecta como `mme_user` (ecosystem.config.js, src/lib/db.ts),
-- pero seis objetos creados por los ETL recientes quedaron sin ningún privilegio para
-- ese usuario. No rompía nada todavía porque ninguna ruta de Next los consultaba, pero
-- cualquier route nueva que los tocara habría fallado con "permission denied".
--
-- Detectado en la inspección del 2026-10-22, al contrastar el servidor contra el manual
-- técnico. Aplicado ese mismo día.
--
-- Nota: esto NO resuelve la escritura. `mme_user` sigue sin INSERT/UPDATE/DELETE en 124
-- de 131 tablas y no es dueño de 129 de ellas, así que el backend y los ETL siguen
-- conectándose como `postgres`. Migrar esa propiedad es un trabajo aparte.

GRANT SELECT ON sector_energetico.disponibilidad_plantas   TO mme_user;
GRANT SELECT ON sector_energetico.estado_sin_diario        TO mme_user;
GRANT SELECT ON sector_energetico.precio_predespacho_ideal TO mme_user;
GRANT SELECT ON sector_energetico.senda_referencia         TO mme_user;
GRANT SELECT ON public.alertas_recientes                   TO mme_user;
GRANT SELECT ON public.metricas_criticas_activas           TO mme_user;

-- Para que las tablas que creen los ETL a futuro nazcan legibles por mme_user y no haya
-- que recordar otorgarlo a mano cada vez.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA sector_energetico GRANT SELECT ON TABLES TO mme_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public            GRANT SELECT ON TABLES TO mme_user;
