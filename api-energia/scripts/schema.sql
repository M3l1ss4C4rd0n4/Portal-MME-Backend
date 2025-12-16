-- ========================================
-- BASE DE DATOS: ENERGIA.DB
-- Sistema de Información Energética Colombia
-- ========================================

-- ========================================
-- TABLA: DEMANDA
-- ========================================
CREATE TABLE IF NOT EXISTS demanda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    demanda_mw REAL NOT NULL,
    demanda_comercial_mw REAL,
    demanda_regulada_mw REAL,
    demanda_no_regulada_mw REAL,
    region VARCHAR(50),
    tipo_dia VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha_hora, region)
);

CREATE INDEX idx_demanda_fecha ON demanda(fecha_hora);
CREATE INDEX idx_demanda_region ON demanda(region);

-- ========================================
-- TABLA: GENERACION
-- ========================================
CREATE TABLE IF NOT EXISTS generacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    tipo_fuente VARCHAR(50) NOT NULL,
    recurso VARCHAR(100),
    generacion_mw REAL NOT NULL,
    capacidad_efectiva_mw REAL,
    disponibilidad_pct REAL,
    empresa VARCHAR(100),
    region VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha_hora, tipo_fuente, recurso)
);

CREATE INDEX idx_generacion_fecha ON generacion(fecha_hora);
CREATE INDEX idx_generacion_tipo ON generacion(tipo_fuente);
CREATE INDEX idx_generacion_recurso ON generacion(recurso);

-- ========================================
-- TABLA: TRANSMISION
-- ========================================
CREATE TABLE IF NOT EXISTS transmision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    elemento VARCHAR(100) NOT NULL,
    tipo_elemento VARCHAR(50),
    voltaje_kv REAL,
    carga_mw REAL,
    capacidad_mw REAL,
    utilizacion_pct REAL,
    estado VARCHAR(50),
    contingencias TEXT,
    empresa VARCHAR(100),
    region VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha_hora, elemento)
);

CREATE INDEX idx_transmision_fecha ON transmision(fecha_hora);
CREATE INDEX idx_transmision_elemento ON transmision(elemento);

-- ========================================
-- TABLA: DISTRIBUCION
-- ========================================
CREATE TABLE IF NOT EXISTS distribucion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    empresa VARCHAR(100) NOT NULL,
    region VARCHAR(50),
    energia_distribuida_mwh REAL,
    usuarios_atendidos INTEGER,
    saidi REAL,
    saifi REAL,
    fmik REAL,
    energia_no_servida_mwh REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha, empresa)
);

CREATE INDEX idx_distribucion_fecha ON distribucion(fecha);
CREATE INDEX idx_distribucion_empresa ON distribucion(empresa);

-- ========================================
-- TABLA: COMERCIALIZACION
-- ========================================
CREATE TABLE IF NOT EXISTS comercializacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    tipo_mercado VARCHAR(50) NOT NULL,
    precio_bolsa_cop_kwh REAL,
    precio_escasez_cop_kwh REAL,
    volumen_transado_mwh REAL,
    oferta_total_mw REAL,
    demanda_total_mw REAL,
    margen_reserva_mw REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha_hora, tipo_mercado)
);

CREATE INDEX idx_comercializacion_fecha ON comercializacion(fecha_hora);

-- ========================================
-- TABLA: PERDIDAS
-- ========================================
CREATE TABLE IF NOT EXISTS perdidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    tipo_perdida VARCHAR(50) NOT NULL,
    perdidas_tecnicas_mwh REAL,
    perdidas_no_tecnicas_mwh REAL,
    perdidas_totales_mwh REAL,
    porcentaje_perdidas REAL,
    empresa VARCHAR(100),
    region VARCHAR(50),
    nivel_tension VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha, tipo_perdida, empresa)
);

CREATE INDEX idx_perdidas_fecha ON perdidas(fecha);
CREATE INDEX idx_perdidas_empresa ON perdidas(empresa);

-- ========================================
-- TABLA: RESTRICCIONES
-- ========================================
CREATE TABLE IF NOT EXISTS restricciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    tipo_restriccion VARCHAR(100) NOT NULL,
    elemento_afectado VARCHAR(100),
    causa VARCHAR(200),
    costo_restriccion_cop REAL,
    energia_restringida_mwh REAL,
    duracion_horas REAL,
    region VARCHAR(50),
    estado VARCHAR(50),
    observaciones TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_restricciones_fecha ON restricciones(fecha_hora);
CREATE INDEX idx_restricciones_tipo ON restricciones(tipo_restriccion);

-- ========================================
-- TABLA: PRECIOS_BOLSA
-- ========================================
CREATE TABLE IF NOT EXISTS precios_bolsa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME NOT NULL,
    precio_bolsa_cop_kwh REAL NOT NULL,
    precio_contrato_cop_kwh REAL,
    precio_escasez_cop_kwh REAL,
    precio_reconciliacion_cop_kwh REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha_hora)
);

CREATE INDEX idx_precios_fecha ON precios_bolsa(fecha_hora);

-- ========================================
-- TABLA: COSTO_UNITARIO (CU)
-- ========================================
CREATE TABLE IF NOT EXISTS costo_unitario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    cu_total_cop_kwh REAL NOT NULL,
    cu_generacion_cop_kwh REAL,
    cu_transmision_cop_kwh REAL,
    cu_distribucion_cop_kwh REAL,
    cu_comercializacion_cop_kwh REAL,
    cu_perdidas_cop_kwh REAL,
    cu_restricciones_cop_kwh REAL,
    nivel_tension VARCHAR(50),
    region VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fecha, nivel_tension, region)
);

CREATE INDEX idx_cu_fecha ON costo_unitario(fecha);

-- ========================================
-- TABLA: ANALISIS_IA (Histórico de análisis)
-- ========================================
CREATE TABLE IF NOT EXISTS analisis_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_analisis DATETIME DEFAULT CURRENT_TIMESTAMP,
    tipo_analisis VARCHAR(100),
    pregunta TEXT,
    respuesta TEXT NOT NULL,
    contexto_datos TEXT,
    modelo_ia VARCHAR(100),
    tokens_usados INTEGER,
    tiempo_respuesta_ms INTEGER
);

CREATE INDEX idx_analisis_fecha ON analisis_ia(fecha_analisis);
CREATE INDEX idx_analisis_tipo ON analisis_ia(tipo_analisis);

-- ========================================
-- TABLA: ALERTAS (Anomalías detectadas)
-- ========================================
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    tipo_alerta VARCHAR(100) NOT NULL,
    severidad VARCHAR(20) NOT NULL,
    componente VARCHAR(50),
    descripcion TEXT NOT NULL,
    valor_actual REAL,
    valor_esperado REAL,
    desviacion_pct REAL,
    recomendacion TEXT,
    estado VARCHAR(20) DEFAULT 'activa',
    fecha_resolucion DATETIME
);

CREATE INDEX idx_alertas_fecha ON alertas(fecha_hora);
CREATE INDEX idx_alertas_severidad ON alertas(severidad);
CREATE INDEX idx_alertas_estado ON alertas(estado);
