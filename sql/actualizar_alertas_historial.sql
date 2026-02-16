-- ============================================================================
-- ACTUALIZACIÓN: alertas_historial
-- Descripción: Agrega columnas faltantes para integración completa
-- Autor: Portal Energético MME
-- Fecha: February 2026
-- ============================================================================

-- Agregar columna titulo si no existe
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'alertas_historial' AND column_name = 'titulo'
    ) THEN
        ALTER TABLE alertas_historial ADD COLUMN titulo VARCHAR(255);
    END IF;
END $$;

-- Agregar columna dias_afectados si no existe
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'alertas_historial' AND column_name = 'dias_afectados'
    ) THEN
        ALTER TABLE alertas_historial ADD COLUMN dias_afectados INTEGER DEFAULT 0;
    END IF;
END $$;

-- Agregar columna fecha_notificacion si no existe (consolidada)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'alertas_historial' AND column_name = 'fecha_notificacion'
    ) THEN
        ALTER TABLE alertas_historial ADD COLUMN fecha_notificacion TIMESTAMP;
    END IF;
END $$;

-- Crear índice para titulo si no existe
CREATE INDEX IF NOT EXISTS idx_alertas_titulo ON alertas_historial(titulo);

-- Optimizar índice para búsquedas por fecha y severidad combinadas
CREATE INDEX IF NOT EXISTS idx_alertas_fecha_severidad ON alertas_historial(fecha_evaluacion DESC, severidad);

-- Comentarios descriptivos
COMMENT ON COLUMN alertas_historial.titulo IS 'Título descriptivo de la alerta';
COMMENT ON COLUMN alertas_historial.dias_afectados IS 'Número de días proyectados afectados por la condición';
COMMENT ON COLUMN alertas_historial.fecha_notificacion IS 'Timestamp de última notificación enviada (email o WhatsApp)';

-- Verificación
DO $$ 
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'alertas_historial'
    AND column_name IN ('titulo', 'dias_afectados', 'fecha_notificacion');
    
    RAISE NOTICE '✅ Columnas actualizadas: % de 3 columnas presentes', col_count;
END $$;
