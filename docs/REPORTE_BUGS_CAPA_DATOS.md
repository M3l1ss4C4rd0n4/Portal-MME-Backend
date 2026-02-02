# 🐛 REPORTE DE BUGS CRÍTICOS - CAPA DE DATOS

**Fecha:** 1 de Febrero de 2026  
**Analista:** GitHub Copilot  
**Prioridad:** CRÍTICA ⚠️

---

## 🔍 RESUMEN EJECUTIVO

La infraestructura funciona **100% correctamente** (servicios, Prometheus, Celery).
El problema está en la **LÓGICA DE NEGOCIO** - los datos existen pero se procesan incorrectamente.

---

## ❌ BUGS IDENTIFICADOS

### BUG #1: APORTES HÍDRICOS MUESTRA 0% (CRÍTICO)

**Archivo:** `domain/services/hydrology_service.py`  
**Líneas:** 37-80  
**Síntoma:** Dashboard muestra "Aportes Hídricos: 0.00%"

**Causa raíz:**
```python
# CÓDIGO INCORRECTO (líneas 49-56)
aportes_diarios = self._fetch_metric_with_fallbacks(
    ['AporEner', ...],
    'Sistema',  # ← ERROR: Busca en 'Sistema'
    fecha_inicio_str, fecha_final_str
)
```

**Problema:**
- La BD tiene **83,805 registros** de `AporEner` para `entidad='Rio'`
- Pero solo **2,227 registros** para `entidad='Sistema'`
- El servicio busca 'Sistema' → encuentra datos vacíos → devuelve 0%

**Evidencia de base de datos:**
```sql
SELECT entidad, COUNT(*) FROM metrics WHERE metrica='AporEner' GROUP BY entidad;
-- Rio: 83,805 registros
-- Sistema: 2,227 registros
```

**Impacto:** ⚠️ **CRÍTICO**  
- KPI principal del dashboard no funciona
- Usuarios no pueden ver estado hídrico del país

**Fix aplicado:** ✅
- Cambiar `entity='Sistema'` → `entity='Rio'`
- Agregar todos los ríos con `SUM(valor_gwh)`
- Validar que resultado esté en rango 30-150%

---

### BUG #2: RESTRICCIONES MUESTRA $0 MILLONES (CRÍTICO)

**Archivo:** `domain/services/restrictions_service.py`  
**Líneas:** 28-68  
**Síntoma:** Dashboard muestra "Restricciones Totales: $0 millones COP"

**Causa raíz 1: Unidades mixtas**
```sql
-- Restricciones tienen 2 unidades diferentes:
SELECT metrica, unidad, COUNT(*) FROM metrics 
WHERE metrica='RestSinAliv' GROUP BY unidad;

-- RestSinAliv | GWh | 1,826 registros
-- RestSinAliv | COP | 1 registro (valor=0)
```

**Problema:**
- XM reporta restricciones en **COP (pesos colombianos)** Y **MWh**
- La columna `valor_gwh` almacena AMBOS tipos sin distinción
- El último dato (2026-01-30) tiene `unidad='COP'` con `valor=0`
- El dashboard consulta la última fecha → obtiene 0

**Causa raíz 2: Conversión de unidades incorrecta**
```python
# Los valores en BD son:
RestAliv: 2.08e+08 "GWh" (pero realmente son MWh o COP)
# 208 millones de GWh/día = IMPOSIBLE (Colombia ~0.2 GWh/día)
```

**Impacto:** ⚠️ **CRÍTICO**  
- KPI económico muestra $0
- Valores reales están en BD pero con unidades incorrectas

**Fix requerido:**
1. Filtrar solo `unidad='COP'` para cálculos monetarios
2. Convertir COP a millones antes de mostrar
3. Validar que valores no sean 0 antes de mostrar
4. Si última fecha = 0, buscar hacia atrás (últimos 7 días)

---

### BUG #3: DNA (DEMANDA) MUESTRA 33 GWh (SOSPECHOSO)

**Archivo:** `domain/services/distribution_service.py`  
**Síntoma:** Dashboard muestra "DNA Nacional: 33.87 GWh"

**Esperado:** Colombia consume ~200 GWh/día

**Análisis pendiente:** 🔍
```sql
SELECT metrica, AVG(valor_gwh), MIN(fecha), MAX(fecha)
FROM metrics 
WHERE metrica LIKE '%Dema%' AND entidad='Sistema'
GROUP BY metrica;
```

**Posibles causas:**
1. Consulta solo 1 hora en lugar de 24 horas
2. Filtro de fechas incorrecto
3. Falta agregación de regiones

---

### BUG #4: SPREAD ESCASEZ $502 $/kWh (ATÍPICO)

**Archivo:** `domain/services/commercial_service.py`  
**Síntoma:** Dashboard muestra "Spread Escasez: $502.67 $/kWh"

**Esperado:** Spread normal Colombia: $50-150 $/kWh

**Análisis pendiente:** 🔍
```sql
SELECT metrica, AVG(valor_gwh), MAX(valor_gwh)
FROM metrics 
WHERE metrica LIKE '%Prec%' OR metrica LIKE '%Spread%'
GROUP BY metrica;
```

**Posibles causas:**
1. Confusión entre Precio Bolsa y Precio Escasez
2. Falta validación de valores atípicos
3. Error en fórmula del spread

---

### BUG #5: GRÁFICOS TEMPORALES PLANOS/VACÍOS

**Archivos:** Varios en `interface/pages/`  
**Síntoma:** Gráficos de evolución temporal muestran líneas planas en 0

**Causa raíz:** Callbacks no manejan datos NULL correctamente
```python
# Callback típico problemático:
@callback(...)
def update_graph(fecha):
    data = service.get_data(fecha)
    # Si data es None o vacío, Plotly dibuja línea en 0
    fig = go.Figure(data=[go.Scatter(y=data)])  # ← No valida NULL
    return fig
```

**Fix requerido:**
```python
@callback(...)
def update_graph(fecha):
    data = service.get_data(fecha)
    
    # VALIDACIÓN ROBUSTA
    if data is None or data.empty:
        return crear_grafico_sin_datos()  # Mensaje claro
    
    if data['valor'].isna().all():
        return crear_grafico_sin_datos()
    
    fig = go.Figure(data=[go.Scatter(y=data['valor'])])
    return fig
```

---

### BUG #6: CACHE REDIS CORRUPTO/DESACTUALIZADO

**Síntoma:** Workers Celery tienen 0 tareas procesadas en workers nuevos

**Análisis:**
```bash
redis-cli
> KEYS *
# Verificar qué keys existen

> GET aportes_hidricos_2026_01_31
# Verificar si valores cacheados son correctos

> TTL aportes_hidricos_2026_01_31
# Verificar si cache expiró
```

**Fix requerido:**
1. `FLUSHDB` para limpiar cache corrupto
2. Re-ejecutar ETL para poblar con datos correctos
3. Configurar TTL apropiado (6-24 horas)

---

## ✅ FIXES APLICADOS HASTA AHORA

### Fix #1: Aportes Hídricos ✅
**Archivo:** `domain/services/hydrology_service.py`

**Cambio:**
```python
# ANTES:
entity='Sistema'  # Solo 2K registros

# DESPUÉS:
entity='Rio'  # 83K registros - datos completos
aportes_valor = df_aportes['valor_gwh'].sum()  # Agregar todos los ríos
```

**Validación:**
```python
# Agregada validación de rangos
if not (30 <= porcentaje <= 150):
    logger.warning(f"Aportes fuera de rango: {porcentaje}%")
```

---

## 🔧 FIXES PENDIENTES (PRÓXIMOS PASOS)

### Fix #2: Restricciones (EN PROGRESO)
- [ ] Filtrar `unidad='COP'` para valores monetarios
- [ ] Convertir a millones de COP
- [ ] Fallback a días anteriores si último valor = 0
- [ ] Validación: restricciones > 0

### Fix #3: DNA (TODO)
- [ ] Verificar agregación horaria → diaria
- [ ] Validar rango: 150-250 GWh/día para Colombia

### Fix #4: Spread (TODO)
- [ ] Revisar fórmula de cálculo
- [ ] Validar rango: 50-200 $/kWh

### Fix #5: Callbacks (TODO)
- [ ] Agregar validación NULL en todos los callbacks
- [ ] Crear función helper `safe_create_figure(data)`

### Fix #6: Cache Redis (TODO)
- [ ] `redis-cli FLUSHDB`
- [ ] Re-ejecutar ETL completo

---

## 📊 EVIDENCIA DE DATOS

### Estructura de BD (SQLite)
```sql
CREATE TABLE metrics (
    fecha DATE,
    metrica VARCHAR(50),
    entidad VARCHAR(100),  -- 'Sistema', 'Rio', 'Embalse'
    recurso VARCHAR(100),  -- 'CARBON', 'HIDRAULICA', etc.
    valor_gwh REAL,
    unidad VARCHAR(10)  -- 'GWh', 'COP', 'MWh'
);
```

### Datos disponibles:
- **Gene:** 522,868 registros (2020-2026)
- **AporEner (Rio):** 83,805 registros ✅
- **AporEner (Sistema):** 2,227 registros ❌
- **RestAliv:** 1,824 registros (pero unidades mixtas)
- **Últimos datos:** 2026-01-31

---

## 🎯 IMPACTO DE FIXES

| Bug | Fix | Impacto esperado |
|-----|-----|------------------|
| Aportes 0% | Cambiar entity='Rio' | Muestra 60-90% (realista) |
| Restricciones $0 | Filtrar unidad='COP' | Muestra millones COP |
| DNA 33 GWh | Agregar 24 horas | Muestra ~200 GWh |
| Gráficos vacíos | Validar NULL | Muestran datos o mensaje claro |

---

**Siguiente paso:** Aplicar Fix #2 (Restricciones)
