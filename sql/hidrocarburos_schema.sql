-- Schema: hidrocarburos
-- Fuente: Direccion_Hidrocarburos.xlsx (OneDrive, hojas "Ejecución Presupuestal" y
-- "Producción petroleo_gas") + snapshot diario de WTI/BRENT (larepublica.co).

CREATE SCHEMA IF NOT EXISTS hidrocarburos;

-- Hoja "Ejecución Presupuestal" — bloque resumen. Histórico acumulado por
-- fecha_actualizacion (upsert), no se trunca — permite graficar tendencia
-- de ejecución presupuestal a través del tiempo.
CREATE TABLE IF NOT EXISTS hidrocarburos.presupuesto_resumen (
    id                  SERIAL PRIMARY KEY,
    fecha_actualizacion DATE,
    apropiacion_vigente NUMERIC,
    compromisos         NUMERIC,
    obligaciones        NUMERIC,
    por_comprometer     NUMERIC,
    pct_compromisos     NUMERIC,
    pct_obligaciones    NUMERIC,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);

-- Migración: instalaciones existentes tenían fecha_actualizacion nullable
-- sin UNIQUE (modelo TRUNCATE). La fila ya cargada trae una fecha válida,
-- así que basta con endurecer la columna — no hace falta truncar.
ALTER TABLE hidrocarburos.presupuesto_resumen ALTER COLUMN fecha_actualizacion SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'presupuesto_resumen_fecha_actualizacion_key'
    ) THEN
        ALTER TABLE hidrocarburos.presupuesto_resumen
            ADD CONSTRAINT presupuesto_resumen_fecha_actualizacion_key UNIQUE (fecha_actualizacion);
    END IF;
END $$;

-- Hoja "Ejecución Presupuestal" — tabla "Ejecución por proyectos". Histórico
-- acumulado por (fecha_actualizacion, proyecto) — mismo criterio que arriba.
CREATE TABLE IF NOT EXISTS hidrocarburos.presupuesto_proyectos (
    id                  SERIAL PRIMARY KEY,
    proyecto            TEXT,
    apropiacion_vigente NUMERIC,
    compromisos         NUMERIC,
    obligaciones        NUMERIC,
    por_comprometer     NUMERIC,
    pct_compromisos     NUMERIC,
    pct_obligacion      NUMERIC,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);

-- Migración única (modelo TRUNCATE -> histórico por fecha_actualizacion):
-- las filas existentes no tienen fecha_actualizacion; se descartan (el
-- próximo ETL las recarga con la columna correcta) en vez de intentar
-- adivinar backfill.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hidrocarburos' AND table_name = 'presupuesto_proyectos'
              AND column_name = 'fecha_actualizacion'
    ) THEN
        ALTER TABLE hidrocarburos.presupuesto_proyectos ADD COLUMN fecha_actualizacion DATE;
        TRUNCATE TABLE hidrocarburos.presupuesto_proyectos;
    END IF;
END $$;

ALTER TABLE hidrocarburos.presupuesto_proyectos ALTER COLUMN fecha_actualizacion SET NOT NULL;
ALTER TABLE hidrocarburos.presupuesto_proyectos ALTER COLUMN proyecto SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'presupuesto_proyectos_fecha_proyecto_key'
    ) THEN
        ALTER TABLE hidrocarburos.presupuesto_proyectos
            ADD CONSTRAINT presupuesto_proyectos_fecha_proyecto_key UNIQUE (fecha_actualizacion, proyecto);
    END IF;
END $$;

-- Hoja "Producción petroleo_gas" — serie diaria (columnas A-D). No se trunca:
-- upsert por fecha, acumula histórico mes a mes.
CREATE TABLE IF NOT EXISTS hidrocarburos.produccion_diaria (
    fecha                     DATE PRIMARY KEY,
    petroleo_bbl              NUMERIC,
    gas_fiscalizado_mpc       NUMERIC,
    gas_comercializado_mpc    NUMERIC,
    fecha_carga               TIMESTAMP DEFAULT NOW()
);

-- Hoja "Producción petroleo_gas" — mini-tablas "Top 5" (columnas F-G).
-- `periodo` es "YYYY-MM" derivado del mes de los datos (no el texto crudo
-- "Junio" del Excel, que colisionaría entre años con el mismo nombre de mes).
CREATE TABLE IF NOT EXISTS hidrocarburos.produccion_top5 (
    id          SERIAL PRIMARY KEY,
    mes         TEXT,  -- etiqueta original del Excel, ej. "Junio" (solo display)
    categoria   TEXT,  -- campos_petroleo | contratos_petroleo | campos_gas | contratos_gas
    nombre      TEXT,
    valor       NUMERIC,
    unidad      TEXT,  -- BLS | MPC
    fecha_carga TIMESTAMP DEFAULT NOW()
);

-- Migración única (modelo TRUNCATE -> histórico por periodo "YYYY-MM"):
-- las filas existentes solo tienen "mes" (texto libre, ej. "Junio", sin año
-- — colisionaría entre años); se descartan y el próximo ETL las recarga
-- con `periodo` correcto.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hidrocarburos' AND table_name = 'produccion_top5' AND column_name = 'periodo'
    ) THEN
        ALTER TABLE hidrocarburos.produccion_top5 ADD COLUMN periodo TEXT;
        TRUNCATE TABLE hidrocarburos.produccion_top5;
    END IF;
END $$;

ALTER TABLE hidrocarburos.produccion_top5 ALTER COLUMN periodo SET NOT NULL;
ALTER TABLE hidrocarburos.produccion_top5 ALTER COLUMN categoria SET NOT NULL;
ALTER TABLE hidrocarburos.produccion_top5 ALTER COLUMN nombre SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'produccion_top5_periodo_categoria_nombre_key'
    ) THEN
        ALTER TABLE hidrocarburos.produccion_top5
            ADD CONSTRAINT produccion_top5_periodo_categoria_nombre_key UNIQUE (periodo, categoria, nombre);
    END IF;
END $$;

-- Snapshot diario de commodities (WTI/BRENT) desde larepublica.co /api/master.
-- No se trunca: acumula histórico día a día para poder graficar tendencia.
CREATE TABLE IF NOT EXISTS hidrocarburos.commodities_historico (
    fecha          DATE,
    commodity      TEXT,  -- WTI | BRENT
    valor_usd      NUMERIC,
    variacion_abs  NUMERIC,
    variacion_pct  NUMERIC,
    fecha_carga    TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fecha, commodity)
);

-- El BFF de Next.js lee como mme_user (no como postgres) — mismo patrón de
-- privilegios que el resto de schemas (ver pg_default_acl de "subsidios").
GRANT USAGE ON SCHEMA hidrocarburos TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hidrocarburos TO mme_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA hidrocarburos GRANT SELECT ON TABLES TO mme_user;
