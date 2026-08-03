-- Migración 003: Tabla de Senda de Referencia del Embalse Agregado del SIN (CREG 209/2020)
-- Esquema ya asumido por etl/etl_senda_referencia.py (importar_xlsx, cargar_valores_semilla,
-- obtener_senda_para_fecha) — la tabla nunca se había creado en la BD real.

CREATE TABLE IF NOT EXISTS sector_energetico.senda_referencia (
    fecha DATE PRIMARY KEY,
    porcentaje_volumen_util NUMERIC(5,2) NOT NULL,
    estacion TEXT NOT NULL CHECK (estacion IN ('VERANO', 'INVIERNO')),
    fecha_publicacion DATE,
    fuente TEXT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_senda_referencia_fecha
    ON sector_energetico.senda_referencia (fecha DESC);
