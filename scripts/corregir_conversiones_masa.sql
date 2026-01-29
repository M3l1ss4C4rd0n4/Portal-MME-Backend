-- ============================================================================
-- CORRECCIÓN DE CONVERSIONES DE UNIDADES - MÉTRICAS "MASA"
-- ============================================================================
-- Portal Energético MME
-- Fecha: Diciembre 17, 2025
-- Propósito: Corregir valores de métricas con sufijo "Masa" que están en 
--            unidades incorrectas (kg, m³ sin convertir a millones)
-- ============================================================================

-- IMPORTANTE: Hacer BACKUP antes de ejecutar
-- sqlite3 portal_energetico.db ".backup backup_antes_correccion_masa.db"

BEGIN TRANSACTION;

-- ============================================================================
-- 1. VOLUMEN TURBINADO (VolTurbMasa)
-- ============================================================================
-- PROBLEMA: Valores en m³ sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener Millones de m³ (Hm³)
-- Registros afectados: 204 valores > 1M | Max actual = 380,063,660

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VolTurbMasa'
  AND valor_gwh > 1000000;

SELECT 
    '✅ VolTurbMasa corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'VolTurbMasa';

-- ============================================================================
-- 2. VOLUMEN ÚTIL DIARIO (VoluUtilDiarMasa)
-- ============================================================================
-- PROBLEMA: Valores en m³ sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener Hm³
-- Registros afectados: 102 valores > 1M | Max actual = 1,191,820,000

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VoluUtilDiarMasa'
  AND valor_gwh > 1000000;

SELECT 
    '✅ VoluUtilDiarMasa corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'VoluUtilDiarMasa';

-- ============================================================================
-- 3. CAPACIDAD ÚTIL DIARIA (CapaUtilDiarMasa)
-- ============================================================================
-- PROBLEMA: Valores en m³ sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener Hm³
-- Registros afectados: 102 valores > 1M | Max actual = 1,213,370,000

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'CapaUtilDiarMasa'
  AND valor_gwh > 1000000;

SELECT 
    '✅ CapaUtilDiarMasa corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'CapaUtilDiarMasa';

-- ============================================================================
-- 4. VERTIMIENTO (VertMasa)
-- ============================================================================
-- PROBLEMA: Valores en m³ sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener Hm³
-- Registros afectados: 84 valores > 1M | Max actual = 57,633,190

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Hm³'
WHERE metrica = 'VertMasa'
  AND valor_gwh > 1000000;

SELECT 
    '✅ VertMasa corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'VertMasa';

-- ============================================================================
-- 5. ENERGÍA NO FIRME ICC (ENFICC)
-- ============================================================================
-- PROBLEMA: Valores probablemente en kWh sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener GWh
-- Registros afectados: 100 valores > 1M | Max actual = 244,790,198

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'GWh'
WHERE metrica = 'ENFICC'
  AND valor_gwh > 1000000;

SELECT 
    '✅ ENFICC corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'ENFICC';

-- ============================================================================
-- 6. COMPENSACIÓN CONTRATOS RESPALDO ENERGÍA (ComContRespEner)
-- ============================================================================
-- PROBLEMA: Valores probablemente en kWh sin convertir
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener GWh
-- Registros afectados: 155 valores > 1M | Max actual = 25,746,560

UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'GWh'
WHERE metrica = 'ComContRespEner'
  AND valor_gwh > 1000000;

SELECT 
    '✅ ComContRespEner corregido' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max,
    ROUND(AVG(valor_gwh), 2) AS nuevo_promedio
FROM metrics
WHERE metrica = 'ComContRespEner';

-- ============================================================================
-- 7. PROYECCIONES DEMANDA UPME (EscDemUPME*)
-- ============================================================================
-- PROBLEMA: Valores en kWh sin convertir a GWh
-- SOLUCIÓN: Dividir entre 1,000,000 para obtener GWh

-- Escenario Alto
UPDATE metrics
SET valor_gwh = valor_gwh / 1000000.0
WHERE metrica = 'EscDemUPMEAlto'
  AND valor_gwh > 1000000;

-- Escenario Medio
UPDATE metrics
SET valor_gwh = valor_gwh / 1000000.0
WHERE metrica = 'EscDemUPMEMedio'
  AND valor_gwh > 1000000;

-- Escenario Bajo
UPDATE metrics
SET valor_gwh = valor_gwh / 1000000.0
WHERE metrica = 'EscDemUPMEBajo'
  AND valor_gwh > 1000000;

SELECT 
    '✅ Proyecciones UPME corregidas' AS resultado,
    COUNT(*) AS registros_actualizados
FROM metrics
WHERE metrica IN ('EscDemUPMEAlto', 'EscDemUPMEMedio', 'EscDemUPMEBajo');

-- ============================================================================
-- 8. CARGOS FINANCIEROS (Normalizar a Millones de COP)
-- ============================================================================
-- NOTA: Estos son valores monetarios en pesos colombianos
-- Dividir entre 1,000,000 para mostrar en Millones de COP

-- Cargo Uso STN
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'CargoUsoSTN'
  AND valor_gwh > 1000000;

-- Cargo Uso STR
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'CargoUsoSTR'
  AND valor_gwh > 1000000;

-- FAER
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'FAER'
  AND valor_gwh > 1000000;

-- PRONE
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'PRONE'
  AND valor_gwh > 1000000;

-- Remuneración Real Individual
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'RemuRealIndiv'
  AND valor_gwh > 1000000;

-- Descargos Masa
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'DescMasa'
  AND valor_gwh > 1000000;

SELECT 
    '✅ Cargos financieros normalizados' AS resultado,
    COUNT(*) AS registros_actualizados
FROM metrics
WHERE metrica IN ('CargoUsoSTN', 'CargoUsoSTR', 'FAER', 'PRONE', 'RemuRealIndiv', 'DescMasa')
  AND unidad = 'Millones COP';

-- ============================================================================
-- 9. FAZNI (Fondo Apoyo Zonas No Interconectadas)
-- ============================================================================
UPDATE metrics
SET 
    valor_gwh = valor_gwh / 1000000.0,
    unidad = 'Millones COP'
WHERE metrica = 'FAZNI'
  AND valor_gwh > 1000000;

SELECT 
    '✅ FAZNI normalizado' AS resultado,
    COUNT(*) AS registros_actualizados,
    ROUND(MIN(valor_gwh), 2) AS nuevo_min,
    ROUND(MAX(valor_gwh), 2) AS nuevo_max
FROM metrics
WHERE metrica = 'FAZNI';

-- ============================================================================
-- VERIFICACIÓN FINAL
-- ============================================================================

SELECT 
    '========================================' AS separador,
    '📊 RESUMEN DE CORRECCIONES' AS titulo,
    '========================================' AS separador2;

-- Contar métricas con valores > 1M (deberían ser 0 después de la corrección)
SELECT 
    '⚠️ Métricas con valores > 1M restantes' AS verificacion,
    COUNT(DISTINCT metrica) AS metricas_problematicas,
    COUNT(*) AS registros_problematicos
FROM metrics
WHERE valor_gwh > 1000000
  AND unidad NOT IN ('Millones COP', '$/kWh'); -- Excluir monetarios que son esperados

-- Mostrar las 10 métricas más grandes (para verificar)
SELECT 
    '📈 Top 10 valores más grandes después de corrección' AS verificacion,
    metrica,
    MAX(valor_gwh) AS valor_maximo,
    unidad
FROM metrics
GROUP BY metrica, unidad
ORDER BY MAX(valor_gwh) DESC
LIMIT 10;

-- Verificar que las unidades se actualizaron
SELECT 
    '✅ Unidades actualizadas' AS verificacion,
    unidad,
    COUNT(DISTINCT metrica) AS num_metricas,
    COUNT(*) AS num_registros
FROM metrics
GROUP BY unidad
ORDER BY num_registros DESC;

-- ============================================================================
-- COMMIT O ROLLBACK
-- ============================================================================

-- REVISAR resultados antes de hacer COMMIT
-- Si todo está bien: COMMIT;
-- Si hay problemas: ROLLBACK;

COMMIT;

SELECT '✅✅✅ CORRECCIONES APLICADAS EXITOSAMENTE ✅✅✅' AS resultado_final;
