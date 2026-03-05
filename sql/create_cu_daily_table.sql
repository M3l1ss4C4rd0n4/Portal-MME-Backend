-- ============================================================================
-- Tabla: cu_daily
-- Portal Energético MME
-- ============================================================================
-- Almacena el Costo Unitario (CU) diario calculado por componente.
-- Componentes: Generación (G), Transmisión (T), Distribución (D),
--              Comercialización (C), Pérdidas (P), Restricciones (R)
--
-- Ejecución:
--   psql -U postgres -d portal_energetico -f sql/create_cu_daily_table.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS cu_daily (
    id              SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,

    -- Componentes del CU (COP/kWh)
    componente_g    NUMERIC(12,4),       -- Generación: PrecBolsNaci
    componente_t    NUMERIC(12,4),       -- Transmisión: cargo fijo config
    componente_d    NUMERIC(12,4),       -- Distribución: cargo fijo config
    componente_c    NUMERIC(12,4),       -- Comercialización: cargo fijo config
    componente_p    NUMERIC(12,4),       -- Pérdidas: PerdidasEner/Gene * PrecBolsNaci
    componente_r    NUMERIC(12,4),       -- Restricciones: (RestAliv+RestSinAliv) / DemaCome

    -- CU Total (suma de componentes)
    cu_total        NUMERIC(12,4),       -- G + T + D + C + P + R

    -- Metadatos
    demanda_gwh     NUMERIC(12,6),       -- DemaCome del día (GWh)
    generacion_gwh  NUMERIC(12,6),       -- Gene del día (GWh)
    perdidas_gwh    NUMERIC(12,6),       -- PerdidasEner del día (GWh)
    perdidas_pct    NUMERIC(8,4),        -- PerdidasEner/Gene * 100

    -- Calidad y auditoría
    fuentes_ok      SMALLINT DEFAULT 0,  -- Número de métricas fuente disponibles (0-6)
    confianza       VARCHAR(20) DEFAULT 'pendiente',  -- alta/media/baja/pendiente
    notas           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT cu_daily_fecha_unique UNIQUE (fecha)
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_cu_daily_fecha ON cu_daily (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_cu_daily_confianza ON cu_daily (confianza);

COMMENT ON TABLE cu_daily IS 'Costo Unitario diario de energía eléctrica en Colombia, calculado por componente';
COMMENT ON COLUMN cu_daily.componente_g IS 'Componente Generación: PrecBolsNaci ($/kWh)';
COMMENT ON COLUMN cu_daily.componente_t IS 'Componente Transmisión: cargo regulatorio fijo ($/kWh)';
COMMENT ON COLUMN cu_daily.componente_d IS 'Componente Distribución: cargo regulatorio fijo ($/kWh)';
COMMENT ON COLUMN cu_daily.componente_c IS 'Componente Comercialización: cargo regulatorio fijo ($/kWh)';
COMMENT ON COLUMN cu_daily.componente_p IS 'Componente Pérdidas: (PerdidasEner/Gene) * PrecBolsNaci ($/kWh)';
COMMENT ON COLUMN cu_daily.componente_r IS 'Componente Restricciones: (RestAliv+RestSinAliv)/DemaCome ($/kWh)';
COMMENT ON COLUMN cu_daily.cu_total IS 'CU Total = G + T + D + C + P + R ($/kWh)';
