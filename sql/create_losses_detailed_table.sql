-- ============================================================================
-- Tabla: losses_detailed
-- Portal Energético MME
-- ============================================================================
-- Almacena pérdidas de energía desglosadas por tipo (técnicas / no técnicas)
-- con porcentaje respecto a generación total.
--
-- Ejecución:
--   psql -U postgres -d portal_energetico -f sql/create_losses_detailed_table.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS losses_detailed (
    id                  SERIAL PRIMARY KEY,
    fecha               DATE NOT NULL,

    -- Pérdidas absolutas (GWh)
    perdidas_total_gwh  NUMERIC(12,6),       -- PerdidasEner
    perdidas_tecnicas_gwh   NUMERIC(12,6),   -- PerdidasEnerReg
    perdidas_no_tecnicas_gwh NUMERIC(12,6),  -- PerdidasEnerNoReg

    -- Referencia generación (GWh)
    generacion_gwh      NUMERIC(12,6),       -- Gene (Sistema)

    -- Porcentajes sobre generación
    perdidas_total_pct      NUMERIC(8,4),    -- PerdidasEner / Gene * 100
    perdidas_tecnicas_pct   NUMERIC(8,4),    -- PerdidasEnerReg / Gene * 100
    perdidas_no_tecnicas_pct NUMERIC(8,4),   -- PerdidasEnerNoReg / Gene * 100

    -- Costo económico de las pérdidas (Millones COP)
    costo_perdidas_total_mcop    NUMERIC(14,4),  -- PerdidasEner * PrecBolsNaci * 1000 / 1e6
    costo_perdidas_tecnicas_mcop NUMERIC(14,4),
    costo_no_tecnicas_mcop       NUMERIC(14,4),

    -- Auditoría
    precio_bolsa_cop_kwh    NUMERIC(12,4),   -- PrecBolsNaci del día
    fuentes_ok              SMALLINT DEFAULT 0,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT losses_detailed_fecha_unique UNIQUE (fecha)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_losses_detailed_fecha ON losses_detailed (fecha DESC);

COMMENT ON TABLE losses_detailed IS 'Pérdidas de energía desglosadas por tipo con porcentaje y costo económico';
COMMENT ON COLUMN losses_detailed.perdidas_tecnicas_gwh IS 'Pérdidas reguladas (técnicas) — PerdidasEnerReg';
COMMENT ON COLUMN losses_detailed.perdidas_no_tecnicas_gwh IS 'Pérdidas no reguladas (no técnicas) — PerdidasEnerNoReg';
COMMENT ON COLUMN losses_detailed.costo_perdidas_total_mcop IS 'Costo económico: PerdidasEner(GWh) * PrecBolsNaci($/kWh) * 1e6 / 1e6 = Millones COP';
