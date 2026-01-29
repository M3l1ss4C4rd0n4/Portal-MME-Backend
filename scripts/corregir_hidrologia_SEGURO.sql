-- ============================================================================
-- CORRECCIÓN SEGURA DE MÉTRICAS DE HIDROLOGÍA
-- ============================================================================
-- Portal Energético MME
-- Fecha: Diciembre 17, 2025
-- SOLO MÉTRICAS DE HIDROLOGÍA USADAS EN TABLEROS
-- ============================================================================

-- ESTRATEGIA CONSERVADORA:
-- 1. Solo corregir 4 métricas de hidrología confirmadas en uso
-- 2. Solo corregir valores > 1,000,000 (claramente incorrectos)
-- 3. Unidad: m³ → Hm³ (Hectómetros cúbicos = Millones de m³)
-- 4. Conversión: valor / 1,000,000

-- ============================================================================
-- PASO 1: VERIFICACIÓN PRE-CORRECCIÓN
-- ============================================================================

.mode column
.headers on

SELECT '============================================' AS separador;
SELECT '📊 ESTADO ANTES DE LA CORRECCIÓN' AS titulo;
SELECT '============================================' AS separador;

-- Ver estado actual de las 4 métricas
SELECT 
    metrica,
    COUNT(*) as total_registros,
    COUNT(CASE WHEN valor_gwh > 1000000 THEN 1 END) as registros_gt_1m,
    ROUND(MIN(valor_gwh), 2) as minimo,
    ROUND(MAX(valor_gwh), 2) as maximo,
    unidad
FROM metrics
WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa')
GROUP BY metrica, unidad
ORDER BY metrica;

-- Ejemplo de valores que se van a corregir
SELECT '============================================' AS separador;
SELECT '📋 EJEMPLO DE VALORES A CORREGIR (Top 3)' AS titulo;
SELECT '============================================' AS separador;

SELECT 
    fecha,
    metrica,
    entidad,
    recurso,
    ROUND(valor_gwh, 2) as valor_original_m3,
    ROUND(valor_gwh / 1000000.0, 2) as valor_corregido_hm3,
    '→' as flecha,
    'Reducción correcta' as verificacion
FROM metrics
WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa')
  AND valor_gwh > 1000000
ORDER BY valor_gwh DESC
LIMIT 3;

-- ============================================================================
-- PASO 2: CORRECCIONES (DENTRO DE TRANSACCIÓN)
-- ============================================================================

BEGIN TRANSACTION;

-- 1. VOLUMEN TURBINADO (VolTurbMasa)
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VolTurbMasa'
  AND valor_gwh > 1000000;

-- 2. VOLUMEN ÚTIL DIARIO (VoluUtilDiarMasa)
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VoluUtilDiarMasa'
  AND valor_gwh > 1000000;

-- 3. CAPACIDAD ÚTIL DIARIA (CapaUtilDiarMasa)
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'CapaUtilDiarMasa'
  AND valor_gwh > 1000000;

-- 4. VERTIMIENTO (VertMasa)
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VertMasa'
  AND valor_gwh > 1000000;

-- ============================================================================
-- PASO 3: VERIFICACIÓN POST-CORRECCIÓN (ANTES DE COMMIT)
-- ============================================================================

SELECT '============================================' AS separador;
SELECT '✅ ESTADO DESPUÉS DE LA CORRECCIÓN' AS titulo;
SELECT '============================================' AS separador;

-- Verificar que NO hay valores > 1M restantes
SELECT 
    metrica,
    COUNT(*) as total_registros,
    COUNT(CASE WHEN valor_gwh > 1000000 THEN 1 END) as registros_gt_1m_DEBERIA_SER_0,
    ROUND(MIN(valor_gwh), 2) as nuevo_minimo,
    ROUND(MAX(valor_gwh), 2) as nuevo_maximo,
    ROUND(AVG(valor_gwh), 2) as nuevo_promedio,
    unidad
FROM metrics
WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa')
GROUP BY metrica, unidad
ORDER BY metrica;

-- Verificar que las unidades se actualizaron
SELECT '============================================' AS separador;
SELECT '🔍 VERIFICACIÓN DE UNIDADES' AS titulo;
SELECT '============================================' AS separador;

SELECT 
    metrica,
    unidad,
    COUNT(*) as registros,
    CASE 
        WHEN unidad = 'Hm³' THEN '✅ Correcto'
        WHEN unidad = 'GWh' THEN '⚠️ Sin corregir (valores < 1M)'
        ELSE '❌ Error'
    END as estado
FROM metrics
WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa')
GROUP BY metrica, unidad
ORDER BY metrica, unidad;

-- Verificar rangos razonables (valores típicos de embalses colombianos)
SELECT '============================================' AS separador;
SELECT '📊 VERIFICACIÓN DE RANGOS RAZONABLES' AS titulo;
SELECT '============================================' AS separador;

SELECT 
    metrica,
    ROUND(MAX(valor_gwh), 2) as max_hm3,
    CASE 
        WHEN metrica = 'VoluUtilDiarMasa' AND MAX(valor_gwh) BETWEEN 0 AND 2000 THEN '✅ Razonable (0-2000 Hm³)'
        WHEN metrica = 'CapaUtilDiarMasa' AND MAX(valor_gwh) BETWEEN 0 AND 2000 THEN '✅ Razonable (0-2000 Hm³)'
        WHEN metrica = 'VolTurbMasa' AND MAX(valor_gwh) BETWEEN 0 AND 500 THEN '✅ Razonable (0-500 Hm³/día)'
        WHEN metrica = 'VertMasa' AND MAX(valor_gwh) BETWEEN 0 AND 500 THEN '✅ Razonable (0-500 Hm³/día)'
        ELSE '⚠️ Verificar manualmente'
    END as validacion
FROM metrics
WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa')
  AND unidad = 'Hm³'
GROUP BY metrica;

-- Conteo final de registros modificados
SELECT '============================================' AS separador;
SELECT '📈 RESUMEN DE CAMBIOS' AS titulo;
SELECT '============================================' AS separador;

SELECT 
    '✅ Corrección completada' as resultado,
    (SELECT COUNT(*) FROM metrics WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa') AND unidad = 'Hm³') as registros_corregidos,
    (SELECT COUNT(*) FROM metrics WHERE metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa') AND valor_gwh > 1000000) as valores_gt_1m_restantes_DEBE_SER_0;

-- ============================================================================
-- DECISIÓN: COMMIT O ROLLBACK
-- ============================================================================
-- IMPORTANTE: Revisar los resultados arriba
-- Si todo está correcto: las verificaciones muestran valores razonables
-- Entonces: COMMIT (se ejecuta automáticamente al final)
-- Si hay problemas: interrumpir antes del final para hacer ROLLBACK

COMMIT;

SELECT '============================================' AS separador;
SELECT '✅✅✅ CORRECCIÓN APLICADA EXITOSAMENTE ✅✅✅' AS resultado_final;
SELECT '============================================' AS separador;
SELECT 'Métricas corregidas: VolTurbMasa, VoluUtilDiarMasa, CapaUtilDiarMasa, VertMasa' as detalle;
SELECT 'Unidad actualizada: m³ → Hm³ (Hectómetros cúbicos)' as detalle2;
SELECT 'Próximo paso: Reiniciar portal con sudo systemctl restart dashboard-mme' as recomendacion;
