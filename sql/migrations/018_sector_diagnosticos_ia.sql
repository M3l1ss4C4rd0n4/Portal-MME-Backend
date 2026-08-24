-- Migración 018: sector_energetico.diagnosticos_ia — Fase 11
-- (Diagnósticos de HomeSlider generados por IA, 1 vez al día, cacheados)
--
-- Cachea el texto generado por Gemini para cada uno de los 3 slides ya
-- corregidos de HomeSlider (Reservas Hídricas, Precio y Generación, Térmica),
-- para que la tarea diaria de Celery escriba una sola vez por día y todos los
-- visitantes del portal lean el mismo texto cacheado — nunca se genera más de
-- una vez por día ni por carga de página.

CREATE TABLE IF NOT EXISTS sector_energetico.diagnosticos_ia (
    fecha         DATE NOT NULL,
    slide_id      TEXT NOT NULL,   -- 'reservas' | 'precio_generacion' | 'termica'
    texto         TEXT NOT NULL,
    generado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    modelo        TEXT,
    PRIMARY KEY (fecha, slide_id)
);

GRANT SELECT, INSERT, UPDATE ON sector_energetico.diagnosticos_ia TO mme_user;
