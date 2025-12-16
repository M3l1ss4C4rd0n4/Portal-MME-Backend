-- ============================================================================
-- ESQUEMA DE BASE DE DATOS: Portal Energético MME
-- Base de datos: SQLite
-- Propósito: Almacenar métricas energéticas de Colombia (XM API)
-- ============================================================================

-- Eliminar tabla si existe (solo para desarrollo)
DROP TABLE IF EXISTS metrics;

-- ============================================================================
-- TABLA: metrics
-- Descripción: Almacena todas las métricas energéticas (generación, demanda, etc.)
-- ============================================================================
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    metrica VARCHAR(50) NOT NULL,           -- 'Gene', 'DemaCome', 'VoluUtilDiarEner', etc.
    entidad VARCHAR(100) NOT NULL,          -- 'Sistema', 'Recurso', 'Embalse', etc.
    recurso VARCHAR(100),                   -- 'CARBON', 'HIDRAULICA', 'SOLAR', etc. (puede ser NULL)
    valor_gwh REAL NOT NULL,                -- Valor en GWh (ya convertido)
    unidad VARCHAR(10) DEFAULT 'GWh',
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraint único: evita duplicados
    UNIQUE(fecha, metrica, entidad, recurso)
);

-- ============================================================================
-- ÍNDICES: Optimización de consultas
-- ============================================================================

-- Índice por fecha (consultas por rango de fechas)
CREATE INDEX idx_fecha ON metrics(fecha);

-- Índice compuesto: métrica + entidad (consultas más comunes)
CREATE INDEX idx_metrica_entidad ON metrics(metrica, entidad);

-- Índice compuesto: fecha + métrica (dashboards por tipo de métrica)
CREATE INDEX idx_fecha_metrica ON metrics(fecha, metrica);

-- Índice compuesto: fecha + métrica + entidad (consultas específicas)
CREATE INDEX idx_fecha_metrica_entidad ON metrics(fecha, metrica, entidad);

-- Índice por recurso (cuando se filtra por tipo de recurso)
CREATE INDEX idx_recurso ON metrics(recurso) WHERE recurso IS NOT NULL;

-- ============================================================================
-- TABLA: metrics_hourly
-- Descripción: Almacena métricas con desagregación horaria (24 horas)
-- Propósito: Análisis detallado por hora del día
-- ============================================================================
DROP TABLE IF EXISTS metrics_hourly;

CREATE TABLE metrics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    metrica VARCHAR(50) NOT NULL,           -- 'DemaCome', 'DemaReal', 'Gene', etc.
    entidad VARCHAR(100) NOT NULL,          -- 'Sistema', 'Agente', 'Recurso'
    recurso VARCHAR(100),                   -- Código de agente/recurso (puede ser NULL para Sistema)
    hora INTEGER NOT NULL,                  -- 1 a 24
    valor_mwh REAL NOT NULL,                -- Valor en MWh (conversión de kWh)
    unidad VARCHAR(10) DEFAULT 'MWh',
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraint único: evita duplicados
    UNIQUE(fecha, metrica, entidad, recurso, hora),
    
    -- Validación: hora debe estar entre 1 y 24
    CHECK(hora >= 1 AND hora <= 24)
);

-- Índices para consultas rápidas
CREATE INDEX idx_hourly_fecha ON metrics_hourly(fecha);
CREATE INDEX idx_hourly_metrica_entidad ON metrics_hourly(metrica, entidad);
CREATE INDEX idx_hourly_fecha_metrica ON metrics_hourly(fecha, metrica);
CREATE INDEX idx_hourly_fecha_metrica_entidad ON metrics_hourly(fecha, metrica, entidad);

-- ============================================================================
-- TABLA: catalogos
-- Descripción: Almacena catálogos de XM (ListadoRecursos, ListadoEmbalses, etc.)
-- Propósito: Mapear códigos a nombres (ej: "2QBW" → "GUAVIO")
-- ============================================================================
DROP TABLE IF EXISTS catalogos;

CREATE TABLE catalogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalogo VARCHAR(50) NOT NULL,          -- 'ListadoRecursos', 'ListadoEmbalses', etc.
    codigo VARCHAR(100) NOT NULL,            -- Código XM (ej: '2QBW', 'GUAVIO', etc.)
    nombre VARCHAR(200),                     -- Nombre completo
    tipo VARCHAR(100),                       -- Tipo/categoría (ej: 'HIDRAULICA', 'SOLAR')
    region VARCHAR(100),                     -- Región geográfica (opcional)
    capacidad REAL,                          -- Capacidad instalada (MW) - opcional
    metadata TEXT,                           -- JSON con campos adicionales
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraint único: un código por catálogo
    UNIQUE(catalogo, codigo)
);

-- Índices para catálogos
CREATE INDEX idx_catalogo ON catalogos(catalogo);
CREATE INDEX idx_catalogo_codigo ON catalogos(catalogo, codigo);
CREATE INDEX idx_catalogo_tipo ON catalogos(catalogo, tipo) WHERE tipo IS NOT NULL;

-- ============================================================================
-- COMENTARIOS TÉCNICOS
-- ============================================================================
-- 1. UNIQUE constraint previene duplicados automáticamente
-- 2. Índices optimizados para consultas típicas del dashboard:
--    - Rangos de fechas (idx_fecha)
--    - Métricas específicas (idx_metrica_entidad)
--    - Consultas combinadas (idx_fecha_metrica_entidad)
-- 3. SQLite almacena dates como TEXT en formato ISO8601 ('YYYY-MM-DD')
-- 4. REAL para valor_gwh soporta decimales con precisión suficiente
-- 5. AUTOINCREMENT en PRIMARY KEY garantiza IDs únicos incluso tras DELETE
-- 6. Tabla catalogos para mapear códigos XM a nombres legibles
-- ============================================================================
