-- 049 — Fotos diarias de los indicadores del Informe Diario de Dirección de Energía
--
-- El informe es diario, así que su valor está en mostrar QUÉ CAMBIÓ. Los tableros
-- de origen solo exponen el estado vigente: no guardan el valor de ayer. Esta tabla
-- es la única memoria que permite calcular la variación.
--
-- Una fila por (fecha, sección, kpi). La tarea de Celery escribe la foto del día;
-- el constructor del informe lee la foto anterior más reciente para el delta.

CREATE TABLE IF NOT EXISTS public.informe_de_snapshot (
    fecha         DATE        NOT NULL,
    seccion       TEXT        NOT NULL,
    kpi           TEXT        NOT NULL,
    valor         NUMERIC,
    unidad        TEXT        NOT NULL DEFAULT '',
    etiqueta      TEXT        NOT NULL DEFAULT '',
    capturado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT informe_de_snapshot_pk PRIMARY KEY (fecha, seccion, kpi)
);

-- El acceso real es "dame la foto anterior a hoy", siempre ordenando por fecha
-- descendente y cortando en la primera. Sin este índice es un seq scan completo.
CREATE INDEX IF NOT EXISTS informe_de_snapshot_fecha_desc_idx
    ON public.informe_de_snapshot (fecha DESC);

COMMENT ON TABLE  public.informe_de_snapshot IS
    'Foto diaria de los KPI del Informe Diario de Dirección de Energía. Permite calcular la variación día a día; los tableros de origen solo exponen el estado vigente.';
COMMENT ON COLUMN public.informe_de_snapshot.valor IS
    'Valor numérico crudo, SIN formatear. El formato (COP, %, unidades) se aplica al render.';
COMMENT ON COLUMN public.informe_de_snapshot.unidad IS
    'Unidad cruda del valor: COP, pct, kWp, MWp o cadena vacía para conteos.';

GRANT SELECT, INSERT, UPDATE ON public.informe_de_snapshot TO mme_user;
