-- ================================================================
-- ESQUEMA POSTGRESQL PARA PROYECTO "EnergiA"
-- Asistente IA para Detección de Pérdidas No Técnicas
-- ================================================================

-- Crear database
CREATE DATABASE energia_colombia;
\c energia_colombia;

-- ================================================================
-- SCHEMA 1: XM (Operador del Sistema)
-- ================================================================
CREATE SCHEMA IF NOT EXISTS xm;

-- Demanda horaria del sistema
CREATE TABLE xm.demanda_horaria (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    hora SMALLINT NOT NULL CHECK (hora BETWEEN 0 AND 23),
    agente VARCHAR(100),
    recurso VARCHAR(100),
    valor_mwh DECIMAL(12,2) NOT NULL,
    tipo_demanda VARCHAR(50), -- Comercial, Regulada, No regulada
    region VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_demanda_horaria UNIQUE (fecha, hora, agente, recurso)
);

-- Generación por fuente
CREATE TABLE xm.generacion (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    recurso VARCHAR(100) NOT NULL,
    tipo_recurso VARCHAR(50), -- Hidráulica, Térmica, Solar, Eólica
    valor_gwh DECIMAL(12,3) NOT NULL,
    capacidad_instalada_mw DECIMAL(10,2),
    factor_planta DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pérdidas técnicas reconocidas
CREATE TABLE xm.perdidas_tecnicas (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    operador_red VARCHAR(200) NOT NULL,
    nivel_tension VARCHAR(50), -- STR, STN, SDL
    perdidas_mwh DECIMAL(12,2) NOT NULL,
    perdidas_porcentaje DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- SCHEMA 2: SUI (Superservicios)
-- ================================================================
CREATE SCHEMA IF NOT EXISTS sui;

-- Pérdidas no técnicas reportadas (CRÍTICO PARA FRAUDE)
CREATE TABLE sui.perdidas_no_tecnicas (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    operador_red VARCHAR(200) NOT NULL,
    nit VARCHAR(20),
    municipio VARCHAR(100),
    departamento VARCHAR(100),
    energia_comprada_kwh DECIMAL(15,2) NOT NULL,
    energia_facturada_kwh DECIMAL(15,2) NOT NULL,
    perdidas_tecnicas_kwh DECIMAL(15,2),
    perdidas_no_tecnicas_kwh DECIMAL(15,2),
    perdidas_no_tecnicas_pct DECIMAL(5,2),
    usuarios_totales INTEGER,
    usuarios_fraude_detectado INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_pnt_sui UNIQUE (fecha, operador_red, municipio)
);

-- Comercialización
CREATE TABLE sui.comercializacion (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    comercializador VARCHAR(200) NOT NULL,
    mercado VARCHAR(50), -- Regulado, No Regulado
    estrato SMALLINT CHECK (estrato BETWEEN 1 AND 6),
    usuarios INTEGER,
    consumo_kwh DECIMAL(15,2),
    facturacion_cop DECIMAL(18,2),
    recaudo_cop DECIMAL(18,2),
    cartera_vencida_cop DECIMAL(18,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inventario de medidores
CREATE TABLE sui.medidores (
    id BIGSERIAL PRIMARY KEY,
    operador_red VARCHAR(200),
    municipio VARCHAR(100),
    tipo_medidor VARCHAR(100), -- Electromecánico, Digital, Smart
    cantidad INTEGER,
    fecha_reporte DATE,
    estado VARCHAR(50), -- Activo, Dañado, Manipulado
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- SCHEMA 3: CREG (Regulación)
-- ================================================================
CREATE SCHEMA IF NOT EXISTS creg;

-- Metas reguladas de pérdidas
CREATE TABLE creg.metas_perdidas (
    id SERIAL PRIMARY KEY,
    operador_red VARCHAR(200) NOT NULL,
    anio SMALLINT NOT NULL,
    meta_perdidas_tecnicas_pct DECIMAL(5,2),
    meta_perdidas_no_tecnicas_pct DECIMAL(5,2),
    resolucion VARCHAR(50),
    fecha_vigencia DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_metas UNIQUE (operador_red, anio)
);

-- Resoluciones CREG
CREATE TABLE creg.resoluciones (
    id SERIAL PRIMARY KEY,
    numero_resolucion VARCHAR(50) UNIQUE NOT NULL,
    fecha_expedicion DATE NOT NULL,
    titulo TEXT,
    contenido TEXT,
    tipo VARCHAR(100), -- Tarifa, Pérdidas, Calidad, etc.
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- SCHEMA 4: DANE (Socioeconómico)
-- ================================================================
CREATE SCHEMA IF NOT EXISTS dane;

-- Estratificación
CREATE TABLE dane.estratificacion (
    id SERIAL PRIMARY KEY,
    codigo_dane VARCHAR(20) UNIQUE NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    departamento VARCHAR(100) NOT NULL,
    estrato_1_pct DECIMAL(5,2),
    estrato_2_pct DECIMAL(5,2),
    estrato_3_pct DECIMAL(5,2),
    estrato_4_pct DECIMAL(5,2),
    estrato_5_pct DECIMAL(5,2),
    estrato_6_pct DECIMAL(5,2),
    anio SMALLINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Población
CREATE TABLE dane.poblacion (
    id SERIAL PRIMARY KEY,
    codigo_dane VARCHAR(20) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    departamento VARCHAR(100) NOT NULL,
    anio SMALLINT NOT NULL,
    poblacion_total INTEGER,
    poblacion_urbana INTEGER,
    poblacion_rural INTEGER,
    densidad_hab_km2 DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_poblacion UNIQUE (codigo_dane, anio)
);

-- Variables socioeconómicas
CREATE TABLE dane.socioeconomico (
    id SERIAL PRIMARY KEY,
    codigo_dane VARCHAR(20) NOT NULL,
    municipio VARCHAR(100),
    anio SMALLINT,
    desempleo_pct DECIMAL(5,2),
    pobreza_pct DECIMAL(5,2),
    ingreso_promedio_cop DECIMAL(15,2),
    indice_desarrollo DECIMAL(5,3),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- SCHEMA 5: ANALYTICS (Datos Procesados y ML)
-- ================================================================
CREATE SCHEMA IF NOT EXISTS analytics;

-- Vista materializada: Pérdidas integradas
CREATE MATERIALIZED VIEW analytics.perdidas_integradas AS
SELECT 
    pnt.fecha,
    pnt.operador_red,
    pnt.municipio,
    pnt.departamento,
    pnt.perdidas_no_tecnicas_kwh,
    pnt.perdidas_no_tecnicas_pct,
    pnt.usuarios_fraude_detectado,
    pt.perdidas_tecnicas AS perdidas_tecnicas_kwh_xm,
    meta.meta_perdidas_no_tecnicas_pct AS meta_creg,
    pob.poblacion_total,
    pob.densidad_hab_km2,
    soc.pobreza_pct,
    soc.desempleo_pct,
    est.estrato_1_pct + est.estrato_2_pct AS estratos_bajos_pct,
    -- Score de riesgo calculado
    CASE 
        WHEN pnt.perdidas_no_tecnicas_pct > meta.meta_perdidas_no_tecnicas_pct * 1.5 
        THEN 'ALTO'
        WHEN pnt.perdidas_no_tecnicas_pct > meta.meta_perdidas_no_tecnicas_pct * 1.2 
        THEN 'MEDIO'
        ELSE 'BAJO'
    END AS nivel_riesgo
FROM sui.perdidas_no_tecnicas pnt
LEFT JOIN xm.perdidas_tecnicas pt 
    ON pt.fecha = pnt.fecha AND pt.operador_red = pnt.operador_red
LEFT JOIN creg.metas_perdidas meta
    ON meta.operador_red = pnt.operador_red 
    AND meta.anio = EXTRACT(YEAR FROM pnt.fecha)
LEFT JOIN dane.poblacion pob
    ON pob.municipio = pnt.municipio 
    AND pob.anio = EXTRACT(YEAR FROM pnt.fecha)
LEFT JOIN dane.socioeconomico soc
    ON soc.municipio = pnt.municipio 
    AND soc.anio = EXTRACT(YEAR FROM pnt.fecha)
LEFT JOIN dane.estratificacion est
    ON est.municipio = pnt.municipio 
    AND est.anio = EXTRACT(YEAR FROM pnt.fecha);

-- Índices para la vista materializada
CREATE INDEX idx_perdidas_fecha ON analytics.perdidas_integradas(fecha);
CREATE INDEX idx_perdidas_municipio ON analytics.perdidas_integradas(municipio);
CREATE INDEX idx_perdidas_riesgo ON analytics.perdidas_integradas(nivel_riesgo);

-- Tabla de predicciones ML
CREATE TABLE analytics.predicciones_fraude (
    id BIGSERIAL PRIMARY KEY,
    fecha_prediccion DATE NOT NULL,
    municipio VARCHAR(100),
    operador_red VARCHAR(200),
    probabilidad_fraude DECIMAL(5,4), -- 0.0000 a 1.0000
    score_riesgo INTEGER CHECK (score_riesgo BETWEEN 0 AND 100),
    factores_riesgo JSONB, -- {"densidad_alta": true, "pobreza": 45.2, ...}
    modelo_usado VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de alertas
CREATE TABLE analytics.alertas (
    id BIGSERIAL PRIMARY KEY,
    fecha_alerta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_alerta VARCHAR(100), -- Anomalía, Umbral excedido, Patrón sospechoso
    severidad VARCHAR(20) CHECK (severidad IN ('BAJA', 'MEDIA', 'ALTA', 'CRÍTICA')),
    municipio VARCHAR(100),
    operador_red VARCHAR(200),
    descripcion TEXT,
    valor_actual DECIMAL(15,2),
    valor_esperado DECIMAL(15,2),
    desviacion_pct DECIMAL(5,2),
    estado VARCHAR(20) DEFAULT 'NUEVA', -- NUEVA, EN_REVISION, CERRADA
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- ÍNDICES PARA OPTIMIZACIÓN
-- ================================================================

-- XM
CREATE INDEX idx_xm_demanda_fecha ON xm.demanda_horaria(fecha);
CREATE INDEX idx_xm_generacion_fecha ON xm.generacion(fecha);
CREATE INDEX idx_xm_perdidas_fecha ON xm.perdidas_tecnicas(fecha);

-- SUI
CREATE INDEX idx_sui_pnt_fecha ON sui.perdidas_no_tecnicas(fecha);
CREATE INDEX idx_sui_pnt_municipio ON sui.perdidas_no_tecnicas(municipio);
CREATE INDEX idx_sui_pnt_operador ON sui.perdidas_no_tecnicas(operador_red);
CREATE INDEX idx_sui_pnt_pct ON sui.perdidas_no_tecnicas(perdidas_no_tecnicas_pct);

-- CREG
CREATE INDEX idx_creg_metas_operador ON creg.metas_perdidas(operador_red);

-- DANE
CREATE INDEX idx_dane_pob_municipio ON dane.poblacion(municipio);
CREATE INDEX idx_dane_socio_municipio ON dane.socioeconomico(municipio);

-- ANALYTICS
CREATE INDEX idx_alertas_fecha ON analytics.alertas(fecha_alerta);
CREATE INDEX idx_alertas_severidad ON analytics.alertas(severidad);
CREATE INDEX idx_predicciones_fecha ON analytics.predicciones_fraude(fecha_prediccion);
CREATE INDEX idx_predicciones_municipio ON analytics.predicciones_fraude(municipio);

-- ================================================================
-- FUNCIONES ÚTILES PARA EL AGENTE IA
-- ================================================================

-- Función: Obtener top circuitos con más pérdidas
CREATE OR REPLACE FUNCTION analytics.get_top_circuitos_perdidas(
    p_fecha_inicio DATE,
    p_fecha_fin DATE,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    municipio VARCHAR,
    operador_red VARCHAR,
    perdidas_promedio_pct DECIMAL,
    total_perdidas_kwh DECIMAL,
    nivel_riesgo TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pi.municipio,
        pi.operador_red,
        AVG(pi.perdidas_no_tecnicas_pct)::DECIMAL(5,2) AS perdidas_promedio_pct,
        SUM(pi.perdidas_no_tecnicas_kwh)::DECIMAL(15,2) AS total_perdidas_kwh,
        pi.nivel_riesgo
    FROM analytics.perdidas_integradas pi
    WHERE pi.fecha BETWEEN p_fecha_inicio AND p_fecha_fin
    GROUP BY pi.municipio, pi.operador_red, pi.nivel_riesgo
    ORDER BY perdidas_promedio_pct DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Función: Comparar pérdidas real vs meta CREG
CREATE OR REPLACE FUNCTION analytics.comparar_vs_meta_creg(
    p_operador_red VARCHAR,
    p_anio INTEGER
)
RETURNS TABLE (
    mes INTEGER,
    perdidas_reales_pct DECIMAL,
    meta_creg_pct DECIMAL,
    desviacion_pct DECIMAL,
    cumple_meta BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        EXTRACT(MONTH FROM pnt.fecha)::INTEGER AS mes,
        AVG(pnt.perdidas_no_tecnicas_pct)::DECIMAL(5,2) AS perdidas_reales_pct,
        meta.meta_perdidas_no_tecnicas_pct,
        (AVG(pnt.perdidas_no_tecnicas_pct) - meta.meta_perdidas_no_tecnicas_pct)::DECIMAL(5,2) AS desviacion_pct,
        AVG(pnt.perdidas_no_tecnicas_pct) <= meta.meta_perdidas_no_tecnicas_pct AS cumple_meta
    FROM sui.perdidas_no_tecnicas pnt
    JOIN creg.metas_perdidas meta 
        ON meta.operador_red = pnt.operador_red 
        AND meta.anio = p_anio
    WHERE pnt.operador_red = p_operador_red
        AND EXTRACT(YEAR FROM pnt.fecha) = p_anio
    GROUP BY EXTRACT(MONTH FROM pnt.fecha), meta.meta_perdidas_no_tecnicas_pct
    ORDER BY mes;
END;
$$ LANGUAGE plpgsql;

-- ================================================================
-- COMENTARIOS PARA DOCUMENTACIÓN
-- ================================================================

COMMENT ON SCHEMA xm IS 'Datos del operador XM - Sistema Interconectado Nacional';
COMMENT ON SCHEMA sui IS 'Datos del SUI - Superservicios';
COMMENT ON SCHEMA creg IS 'Datos regulatorios de CREG';
COMMENT ON SCHEMA dane IS 'Datos socioeconómicos de DANE';
COMMENT ON SCHEMA analytics IS 'Datos procesados, ML y vistas analíticas';

COMMENT ON TABLE sui.perdidas_no_tecnicas IS 'Tabla crítica para detección de fraude - pérdidas no técnicas reportadas';
COMMENT ON TABLE analytics.predicciones_fraude IS 'Predicciones de modelos ML para fraude eléctrico';
COMMENT ON TABLE analytics.alertas IS 'Sistema de alertas automáticas para anomalías';

-- ================================================================
-- FIN DEL ESQUEMA
-- ================================================================
