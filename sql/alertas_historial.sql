-- ============================================================================
-- TABLA: alertas_historial
-- Descripción: Almacena historial de alertas energéticas generadas por el sistema
-- Autor: Portal Energético MME
-- Fecha: 9 de Febrero de 2026
-- ============================================================================

CREATE TABLE IF NOT EXISTS alertas_historial (
    id SERIAL PRIMARY KEY,
    fecha_generacion TIMESTAMP DEFAULT NOW() NOT NULL,
    fecha_evaluacion DATE NOT NULL,
    
    -- Métricas evaluadas
    metrica VARCHAR(50) NOT NULL,  -- DEMANDA, APORTES_HIDRICOS, EMBALSES, PRECIO_BOLSA, PERDIDAS, BALANCE
    valor_actual DECIMAL(10, 2),
    valor_minimo DECIMAL(10, 2),
    valor_maximo DECIMAL(10, 2),
    valor_promedio DECIMAL(10, 2),
    
    -- Clasificación de severidad
    severidad VARCHAR(20) NOT NULL,  -- NORMAL, ALERTA, CRÍTICO
    estado_general VARCHAR(20),  -- Estado general del sistema completo
    
    -- Detalles
    descripcion TEXT,
    recomendacion TEXT,
    umbral_alerta DECIMAL(10, 2),
    umbral_critico DECIMAL(10, 2),
    
    -- Notificaciones
    notificacion_email_enviada BOOLEAN DEFAULT FALSE,
    notificacion_whatsapp_enviada BOOLEAN DEFAULT FALSE,
    fecha_notificacion_email TIMESTAMP,
    fecha_notificacion_whatsapp TIMESTAMP,
    destinatarios_email TEXT[],  -- Array de emails notificados
    destinatarios_whatsapp TEXT[],  -- Array de números WhatsApp notificados
    
    -- Metadata
    total_alertas_generadas INTEGER DEFAULT 0,
    alertas_criticas_count INTEGER DEFAULT 0,
    alertas_importantes_count INTEGER DEFAULT 0,
    json_completo JSONB,  -- Almacenar el JSON completo de la alerta
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_alerta_fecha_metrica UNIQUE(fecha_evaluacion, metrica, severidad)
);

-- ============================================================================
-- ÍNDICES para optimizar consultas
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_alertas_fecha_generacion ON alertas_historial(fecha_generacion DESC);
CREATE INDEX IF NOT EXISTS idx_alertas_fecha_evaluacion ON alertas_historial(fecha_evaluacion DESC);
CREATE INDEX IF NOT EXISTS idx_alertas_metrica ON alertas_historial(metrica);
CREATE INDEX IF NOT EXISTS idx_alertas_severidad ON alertas_historial(severidad);
CREATE INDEX IF NOT EXISTS idx_alertas_estado_general ON alertas_historial(estado_general);
CREATE INDEX IF NOT EXISTS idx_alertas_notificaciones ON alertas_historial(notificacion_email_enviada, notificacion_whatsapp_enviada);
CREATE INDEX IF NOT EXISTS idx_alertas_json ON alertas_historial USING gin(json_completo);

-- ============================================================================
-- TABLA: configuracion_notificaciones
-- Descripción: Configuración de destinatarios para notificaciones
-- ============================================================================

CREATE TABLE IF NOT EXISTS configuracion_notificaciones (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,  -- EMAIL, WHATSAPP, SMS, TEAMS
    destinatario VARCHAR(255) NOT NULL,
    nombre VARCHAR(255),
    cargo VARCHAR(255),
    
    -- Configuración de alertas
    recibir_alertas_normales BOOLEAN DEFAULT FALSE,
    recibir_alertas_importantes BOOLEAN DEFAULT TRUE,
    recibir_alertas_criticas BOOLEAN DEFAULT TRUE,
    
    -- Horarios de notificación
    horario_inicio TIME DEFAULT '06:00:00',
    horario_fin TIME DEFAULT '22:00:00',
    dias_semana INTEGER[] DEFAULT ARRAY[1,2,3,4,5,6,7],  -- 1=Lunes, 7=Domingo
    
    -- Estado
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_tipo_destinatario UNIQUE(tipo, destinatario)
);

-- ============================================================================
-- INSERTAR CONFIGURACIÓN INICIAL: Viceministro de Energía
-- ============================================================================

INSERT INTO configuracion_notificaciones 
(tipo, destinatario, nombre, cargo, recibir_alertas_normales, recibir_alertas_importantes, recibir_alertas_criticas, activo)
VALUES 
('EMAIL', 'vjpaternina@minenergia.gov.co', 'Viceministro de Energía', 'Viceministro', FALSE, TRUE, TRUE, TRUE),
('WHATSAPP', '+57_whatsapp_viceministro', 'Viceministro de Energía', 'Viceministro', FALSE, TRUE, TRUE, TRUE)
ON CONFLICT (tipo, destinatario) DO NOTHING;

-- Directores técnicos (ejemplo)
INSERT INTO configuracion_notificaciones 
(tipo, destinatario, nombre, cargo, recibir_alertas_normales, recibir_alertas_importantes, recibir_alertas_criticas, activo)
VALUES 
('EMAIL', 'direccion.energia@minenergia.gov.co', 'Dirección de Energía', 'Director', FALSE, TRUE, TRUE, TRUE)
ON CONFLICT (tipo, destinatario) DO NOTHING;

-- ============================================================================
-- COMENTARIOS
-- ============================================================================

COMMENT ON TABLE alertas_historial IS 'Historial completo de alertas energéticas generadas por el sistema de predicciones ML';
COMMENT ON COLUMN alertas_historial.metrica IS 'Métrica evaluada: DEMANDA, APORTES_HIDRICOS, EMBALSES, PRECIO_BOLSA, PERDIDAS, BALANCE';
COMMENT ON COLUMN alertas_historial.severidad IS 'NORMAL: Operación rutinaria | ALERTA: Monitoreo cercano | CRÍTICO: Acción inmediata';
COMMENT ON COLUMN alertas_historial.json_completo IS 'JSON completo de la alerta para auditoría y análisis histórico';

COMMENT ON TABLE configuracion_notificaciones IS 'Configuración de destinatarios para notificaciones de alertas';
COMMENT ON COLUMN configuracion_notificaciones.tipo IS 'Tipo de notificación: EMAIL, WHATSAPP, SMS, TEAMS';
COMMENT ON COLUMN configuracion_notificaciones.horario_inicio IS 'No enviar notificaciones antes de esta hora (solo aplica a ALERTA, CRÍTICO siempre se envía)';

-- ============================================================================
-- VISTA: alertas_recientes
-- Descripción: Vista para consultar alertas de los últimos 30 días
-- ============================================================================

CREATE OR REPLACE VIEW alertas_recientes AS
SELECT 
    id,
    fecha_generacion,
    fecha_evaluacion,
    metrica,
    severidad,
    estado_general,
    valor_promedio,
    descripcion,
    notificacion_email_enviada,
    notificacion_whatsapp_enviada,
    total_alertas_generadas,
    alertas_criticas_count
FROM alertas_historial
WHERE fecha_evaluacion >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY fecha_generacion DESC;

-- ============================================================================
-- VISTA: metricas_criticas_activas
-- Descripción: Vista para métricas con alertas críticas en las últimas 24 horas
-- ============================================================================

CREATE OR REPLACE VIEW metricas_criticas_activas AS
SELECT 
    metrica,
    MAX(fecha_generacion) as ultima_alerta,
    COUNT(*) as veces_critco_24h,
    AVG(valor_promedio) as valor_promedio_periodo,
    STRING_AGG(DISTINCT descripcion, ' | ') as descripciones
FROM alertas_historial
WHERE severidad = 'CRÍTICO'
  AND fecha_generacion >= NOW() - INTERVAL '24 hours'
GROUP BY metrica
ORDER BY ultima_alerta DESC;

-- ============================================================================
-- FIN DEL SCRIPT
-- ============================================================================

-- Verificar creación exitosa
SELECT 
    'alertas_historial' as tabla,
    COUNT(*) as registros
FROM alertas_historial
UNION ALL
SELECT 
    'configuracion_notificaciones' as tabla,
    COUNT(*) as registros
FROM configuracion_notificaciones;
