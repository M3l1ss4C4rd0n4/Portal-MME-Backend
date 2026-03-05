-- ═══════════════════════════════════════════════════════════════════════════
-- Schema: Subsidios DDE (Base_Subsidios_DDE.xlsx)
-- Base de datos: portal_energetico
-- Fecha creación: 2026-03-03
-- ═══════════════════════════════════════════════════════════════════════════

-- Tabla principal: pagos de subsidios
CREATE TABLE IF NOT EXISTS subsidios_pagos (
    id                          SERIAL PRIMARY KEY,
    fecha_actualizacion         TIMESTAMP,
    persona_actualiza           VARCHAR(100),
    fondo                       VARCHAR(10),
    area                        VARCHAR(5),
    anio                        INTEGER,
    trimestre                   INTEGER,
    concepto_trimestre          VARCHAR(20),
    codigo_sui                  VARCHAR(30),
    nombre_prestador            VARCHAR(250),
    estado_resolucion           VARCHAR(50),
    no_resolucion               BIGINT,
    fecha_resolucion            DATE,
    valor_resolucion            NUMERIC(18,2) DEFAULT 0,
    link_resolucion             TEXT,
    tipo_giro                   VARCHAR(150),
    distribuidor_mayorista      VARCHAR(250),
    estado_pago                 VARCHAR(20),
    tipo_pago                   VARCHAR(50),
    valor_pagado                NUMERIC(18,2) NOT NULL DEFAULT 0,
    pct_pagado                  NUMERIC(8,4),
    saldo_pendiente             NUMERIC(18,2) NOT NULL DEFAULT 0,
    observacion                 TEXT,
    cod_general                 VARCHAR(50),
    anio_trimestre_resolucion   VARCHAR(20),
    valor_disponible            NUMERIC(18,2),
    valor_disponible_2          NUMERIC(18,2),
    -- Metadatos
    fecha_importacion           TIMESTAMP DEFAULT NOW(),
    hash_fila                   VARCHAR(64) NOT NULL
);

-- Índices para las 9 preguntas del chatbot
CREATE INDEX IF NOT EXISTS idx_sp_fondo ON subsidios_pagos(fondo);
CREATE INDEX IF NOT EXISTS idx_sp_area ON subsidios_pagos(area);
CREATE INDEX IF NOT EXISTS idx_sp_nombre ON subsidios_pagos(nombre_prestador);
CREATE INDEX IF NOT EXISTS idx_sp_estado_pago ON subsidios_pagos(estado_pago);
CREATE INDEX IF NOT EXISTS idx_sp_concepto_trim ON subsidios_pagos(concepto_trimestre);
CREATE INDEX IF NOT EXISTS idx_sp_no_resol ON subsidios_pagos(no_resolucion);
CREATE INDEX IF NOT EXISTS idx_sp_anio_trim_resol ON subsidios_pagos(anio_trimestre_resolucion);
CREATE INDEX IF NOT EXISTS idx_sp_empresa_fondo ON subsidios_pagos(nombre_prestador, fondo);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sp_hash ON subsidios_pagos(hash_fila);

-- Catálogo de empresas prestadoras (hoja Inicio)
CREATE TABLE IF NOT EXISTS subsidios_empresas (
    id                  SERIAL PRIMARY KEY,
    fondo               VARCHAR(10),
    subclase            VARCHAR(10),
    codigo_sui          VARCHAR(20) NOT NULL,
    nit                 VARCHAR(20),
    nombre_prestador    VARCHAR(250) NOT NULL,
    sigla               VARCHAR(100),
    estado              VARCHAR(50),
    tipo_empresa        VARCHAR(50),
    fuente_generacion   VARCHAR(100),
    departamento        VARCHAR(200),
    municipio           VARCHAR(200),
    profesional         VARCHAR(100),
    fecha_importacion   TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_se_codigo ON subsidios_empresas(codigo_sui);

-- Mapa de cobertura geográfica (hoja Mapa)
CREATE TABLE IF NOT EXISTS subsidios_mapa (
    id                  SERIAL PRIMARY KEY,
    departamento        VARCHAR(100) NOT NULL,
    municipio           VARCHAR(100) NOT NULL,
    area                VARCHAR(5),
    nombre_prestador    VARCHAR(250),
    localidades         BIGINT,
    usuarios            BIGINT,
    fecha_importacion   TIMESTAMP DEFAULT NOW()
);

-- Log de importaciones
CREATE TABLE IF NOT EXISTS subsidios_import_log (
    id                  SERIAL PRIMARY KEY,
    fecha               TIMESTAMP DEFAULT NOW(),
    archivo             VARCHAR(500),
    hoja                VARCHAR(50),
    filas_leidas        INTEGER,
    filas_importadas    INTEGER,
    filas_duplicadas    INTEGER,
    filas_error         INTEGER,
    duracion_seg        NUMERIC(8,2),
    observaciones       TEXT
);

-- Usuarios autorizados para consultas de subsidios vía Telegram
CREATE TABLE IF NOT EXISTS subsidios_usuarios_autorizados (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT NOT NULL UNIQUE,
    nombre          VARCHAR(200),
    rol             VARCHAR(50) DEFAULT 'consulta',
    activo          BOOLEAN DEFAULT TRUE,
    fecha_alta      TIMESTAMP DEFAULT NOW()
);

-- Log de auditoría de consultas de subsidios
CREATE TABLE IF NOT EXISTS subsidios_audit_log (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT,
    nombre_usuario  VARCHAR(200),
    comando         VARCHAR(100),
    parametros      TEXT,
    timestamp       TIMESTAMP DEFAULT NOW()
);
