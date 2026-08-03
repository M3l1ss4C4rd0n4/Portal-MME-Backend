-- Migración 004: Disponibilidad de plantas y precio de predespacho ideal
-- Extraídos del informe diario XM "Seguimiento de Despacho" (texto real del PDF,
-- no imagen) — ver etl/despacho_pdf_parser.py y etl/etl_despacho_diario.py.

CREATE TABLE IF NOT EXISTS sector_energetico.disponibilidad_plantas (
    id SERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    recurso TEXT NOT NULL,
    tipo_indisponibilidad TEXT NOT NULL
        CHECK (tipo_indisponibilidad IN ('MANTENIMIENTO', 'EMERGENCIA', 'SIN_REGISTRAR')),
    total_recursos_disp_menor_100 INT,
    fecha_publicacion DATE,
    fuente TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fecha, recurso)
);

CREATE INDEX IF NOT EXISTS idx_disponibilidad_plantas_fecha
    ON sector_energetico.disponibilidad_plantas (fecha DESC);

CREATE TABLE IF NOT EXISTS sector_energetico.precio_predespacho_ideal (
    fecha DATE PRIMARY KEY,
    precio_cop_kwh NUMERIC(10,3) NOT NULL,
    fecha_publicacion DATE,
    fuente TEXT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_precio_predespacho_fecha
    ON sector_energetico.precio_predespacho_ideal (fecha DESC);
