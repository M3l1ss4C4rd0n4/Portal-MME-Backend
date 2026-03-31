-- ═══════════════════════════════════════════════════════════════
-- OPTIMIZACIÓN DE ÍNDICES - FASE 4 PERFORMANCE
-- ═══════════════════════════════════════════════════════════════
-- Ejecutar con: psql -d portal_energetico -f sql/optimizacion_indices_fase4.sql

-- ═══════════════════════════════════════════════════════════════
-- 1. ÍNDICES PARA TABLA metrics
-- ═══════════════════════════════════════════════════════════════

-- Índice compuesto principal (usado en 90% de queries)
CREATE INDEX IF NOT EXISTS idx_metrics_metrica_fecha_entidad 
    ON metrics (metrica, fecha DESC, entidad);

-- Índice para búsquedas por fecha
CREATE INDEX IF NOT EXISTS idx_metrics_fecha_desc 
    ON metrics (fecha DESC);

-- Índice para búsquedas por entidad
CREATE INDEX IF NOT EXISTS idx_metrics_entidad_metrica 
    ON metrics (entidad, metrica, fecha DESC);

-- Índice para queries de recurso
CREATE INDEX IF NOT EXISTS idx_metrics_recurso 
    ON metrics (recurso) WHERE recurso IS NOT NULL;

-- Índice parcial para métricas recientes (últimos 30 días)
-- Útil para dashboards en tiempo real
CREATE INDEX IF NOT EXISTS idx_metrics_recientes 
    ON metrics (metrica, fecha DESC, entidad) 
    WHERE fecha >= CURRENT_DATE - INTERVAL '30 days';

-- ═══════════════════════════════════════════════════════════════
-- 2. ÍNDICES PARA TABLA metrics_hourly
-- ═══════════════════════════════════════════════════════════════

-- Índice compuesto principal
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_metrica_fecha_hora 
    ON metrics_hourly (metrica, fecha DESC, hora, entidad);

-- Índice para queries por hora
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_fecha_hora 
    ON metrics_hourly (fecha DESC, hora);

-- Índice para métricas horarias recientes
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_recientes 
    ON metrics_hourly (metrica, fecha DESC, hora) 
    WHERE fecha >= CURRENT_DATE - INTERVAL '7 days';

-- ═══════════════════════════════════════════════════════════════
-- 3. ÍNDICES PARA TABLA predictions
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_predictions_metrica_fecha 
    ON predictions (metrica, fecha_prediccion DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_modelo 
    ON predictions (modelo, fecha_entrenamiento DESC);

-- ═══════════════════════════════════════════════════════════════
-- 4. ÍNDICES PARA TABLA alertas_historial
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_alertas_fecha_severidad 
    ON alertas_historial (fecha_generacion DESC, severidad);

CREATE INDEX IF NOT EXISTS idx_alertas_metrica 
    ON alertas_historial (metrica, fecha_generacion DESC);

-- ═══════════════════════════════════════════════════════════════
-- 5. ÍNDICES PARA TABLA cu_daily
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_cu_daily_fecha 
    ON cu_daily (fecha DESC);

-- ═══════════════════════════════════════════════════════════════
-- 6. TABLAS DE ESTADÍSTICAS PARA OPTIMIZACIÓN
-- ═══════════════════════════════════════════════════════════════

-- Tabla de estadísticas de tablas (para monitoreo)
CREATE TABLE IF NOT EXISTS table_statistics (
    table_name VARCHAR(100) PRIMARY KEY,
    row_count BIGINT,
    size_bytes BIGINT,
    last_analyzed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    index_count INTEGER
);

-- Función para actualizar estadísticas
CREATE OR REPLACE FUNCTION update_table_statistics()
RETURNS void AS $$
BEGIN
    INSERT INTO table_statistics (table_name, row_count, size_bytes, index_count)
    SELECT 
        schemaname || '.' || tablename as table_name,
        (xpath('/row/cnt/text()', xmlforest(query_to_xml(
            format('SELECT COUNT(*) as cnt FROM %I.%I', schemaname, tablename), 
            true, false, ''))))[1]::text::bigint as row_count,
        pg_total_relation_size(schemaname || '.' || tablename) as size_bytes,
        (SELECT COUNT(*) FROM pg_indexes WHERE tablename = t.tablename)
    FROM pg_tables t
    WHERE schemaname = 'public'
    ON CONFLICT (table_name) 
    DO UPDATE SET 
        row_count = EXCLUDED.row_count,
        size_bytes = EXCLUDED.size_bytes,
        last_analyzed = CURRENT_TIMESTAMP,
        index_count = EXCLUDED.index_count;
END;
$$ LANGUAGE plpgsql;

-- Ejecutar actualización de estadísticas
SELECT update_table_statistics();

-- ═══════════════════════════════════════════════════════════════
-- 7. CONFIGURACIÓN DE POSTGRESQL PARA PERFORMANCE
-- ═══════════════════════════════════════════════════════════════

-- Estas configuraciones deben hacerse en postgresql.conf
-- shared_buffers = 256MB                    # Aumentar según RAM disponible
-- effective_cache_size = 1GB                # 50% de RAM disponible
-- work_mem = 16MB                           # Para queries complejos
-- maintenance_work_mem = 128MB              # Para VACUUM, CREATE INDEX
-- random_page_cost = 1.1                    # Para SSD
-- effective_io_concurrency = 200            # Para SSD
-- max_connections = 100                     # Según necesidad
-- checkpoint_completion_target = 0.9        # Suavizar checkpoints
-- wal_buffers = 16MB                        # Buffer de WAL
-- default_statistics_target = 100           # Estadísticas más precisas

-- ═══════════════════════════════════════════════════════════════
-- 8. ANALYZE PARA ACTUALIZAR ESTADÍSTICAS
-- ═══════════════════════════════════════════════════════════════

ANALYZE metrics;
ANALYZE metrics_hourly;
ANALYZE predictions;
ANALYZE alertas_historial;

-- ═══════════════════════════════════════════════════════════════
-- 9. VERIFICACIÓN DE ÍNDICES CREADOS
-- ═══════════════════════════════════════════════════════════════

SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
