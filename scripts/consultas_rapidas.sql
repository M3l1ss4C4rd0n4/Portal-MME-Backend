-- ════════════════════════════════════════════════════════════════════════════
-- CONSULTAS RÁPIDAS - PostgreSQL Portal Energético MME
-- ════════════════════════════════════════════════════════════════════════════
-- Uso: sudo -u postgres psql -d portal_energetico -f scripts/consultas_rapidas.sql
-- ════════════════════════════════════════════════════════════════════════════

\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '📊 INFORMACIÓN GENERAL DE LA BASE DE DATOS'
\echo '═══════════════════════════════════════════════════════════════════════════════'

-- Tamaño total de la base de datos
SELECT 
    pg_size_pretty(pg_database_size('portal_energetico')) as "Tamaño Total BD";

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '📋 TABLAS Y TAMAÑOS'
\echo '═══════════════════════════════════════════════════════════════════════════════'

SELECT 
    schemaname as "Schema",
    tablename as "Tabla",
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as "Tamaño"
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '📊 CONTEO DE REGISTROS POR TABLA'
\echo '═══════════════════════════════════════════════════════════════════════════════'

SELECT 'metrics' as "Tabla", COUNT(*) as "Registros" FROM metrics
UNION ALL
SELECT 'metrics_hourly', COUNT(*) FROM metrics_hourly
UNION ALL
SELECT 'lineas_transmision', COUNT(*) FROM lineas_transmision
UNION ALL
SELECT 'distribution_metrics', COUNT(*) FROM distribution_metrics
UNION ALL
SELECT 'catalogos', COUNT(*) FROM catalogos
UNION ALL
SELECT 'commercial_metrics', COUNT(*) FROM commercial_metrics
UNION ALL
SELECT 'predictions', COUNT(*) FROM predictions
ORDER BY "Registros" DESC;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '📅 RANGO DE FECHAS - TABLA METRICS'
\echo '═══════════════════════════════════════════════════════════════════════════════'

SELECT 
    MIN(fecha) as "Fecha Mínima",
    MAX(fecha) as "Fecha Máxima",
    MAX(fecha) - MIN(fecha) as "Días de Datos"
FROM metrics;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '🔝 TOP 10 RECURSOS MÁS RECIENTES'
\echo '═══════════════════════════════════════════════════════════════════════════════'

SELECT 
    fecha,
    metrica,
    entidad,
    recurso,
    ROUND(valor_gwh::numeric, 2) as "Valor GWh"
FROM metrics
ORDER BY fecha DESC
LIMIT 10;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo '⚡ GENERACIÓN TOTAL POR MÉTRICA (ÚLTIMOS 7 DÍAS)'
\echo '═══════════════════════════════════════════════════════════════════════════════'

SELECT 
    metrica,
    COUNT(*) as "Registros",
    ROUND(SUM(valor_gwh)::numeric, 2) as "Total GWh",
    ROUND(AVG(valor_gwh)::numeric, 2) as "Promedio GWh"
FROM metrics
WHERE fecha >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY metrica
ORDER BY "Total GWh" DESC;

\echo ''
\echo '✅ Consultas ejecutadas exitosamente'
\echo ''
