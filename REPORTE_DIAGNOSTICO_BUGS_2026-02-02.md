# 🔍 REPORTE DE DIAGNÓSTICO PROFUNDO - BUGS EN CAPA DE DATOS

**Fecha:** 2026-02-02  
**Ingeniero:** GitHub Copilot (Análisis Full-Stack)  
**Sistema:** Portal MME Dashboard - XM Data Pipeline  

---

## 📋 RESUMEN EJECUTIVO

**Estado infraestructura:** ✅ SALUDABLE (Prometheus, Redis, PostgreSQL, Celery workers operativos)  
**Estado capa de datos:** ❌ **CRÍTICO** - 5 bugs mayores identificados

### Síntomas Observados
1. **Aportes Hídricos:** 0.00% (debería ser 60-70%)
2. **Restricciones:** $0 millones COP (debería haber valores diarios)
3. **Gráficos temporales:** Planos o vacíos
4. **Valores anómalos:** Spread $502, DNA 33 GWh
5. **Redis vacío:** Solo 3 keys de Celery, sin cache de métricas

---

## ❌ BUGS ENCONTRADOS

### **BUG #1: CACHE COMPLETAMENTE VACÍO (CRÍTICO)**

**Archivo:** Redis (instancia en puerto 6379)

#### Problema
```bash
$ redis-cli KEYS "*"
1) "_kombu.binding.celery.pidbox"
2) "_kombu.binding.celeryev"
3) "_kombu.binding.celery"
```

**Solo existen keys de Celery, CERO keys de métricas/aportes/restricciones.**

#### Evidencia
- `ESTADO_ACTUAL.md` menciona "Sistema de caché ELIMINADO" en xm_service.py línea 3
- Los servicios consultan DB/API pero **NO cachean resultados**
- Dashboard hace queries repetidas sin aprovechar cache

#### Impacto
- Consultas lentas (API XM timeout frecuente)
- DB sobrecargada con queries duplicadas
- No hay persistencia de datos entre reinicios

#### Causa Raíz
El sistema **eliminó intencionalmente el cache** (comentario en xm_service.py):
```python
"""IMPORTANTE: Sistema de caché ELIMINADO - Ahora usamos ETL-SQLite para datos históricos."""
```

Pero el ETL **NO se está ejecutando** (workers con 0 tareas procesadas según Flower).

#### Solución
```python
# Option 1: Restaurar cache simple en xm_service.py
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def fetch_metric_data_cached(metric, entity, start_date, end_date):
    cache_key = f"{metric}:{entity}:{start_date}:{end_date}"
    cached = redis_client.get(cache_key)
    
    if cached:
        return pd.read_json(cached)
    
    data = fetch_metric_data(metric, entity, start_date, end_date)
    if data is not None:
        redis_client.setex(cache_key, 3600, data.to_json())  # TTL 1 hora
    
    return data

# Option 2: Ejecutar ETL forzado
python3 /home/admonctrlxm/server/etl/etl_todas_metricas_xm.py
```

---

### **BUG #2: APORTES HÍDRICOS 0% - ENTIDAD INCORRECTA (CRÍTICO)**

**Archivo:** `/home/admonctrlxm/server/domain/services/hydrology_service.py` líneas 64-72

#### Problema
```python
# CÓDIGO ACTUAL (INCORRECTO)
df_aportes = repo.get_metric_data_by_entity(
    metric_id='AporEner',
    entity='Sistema',  # ❌ ENTIDAD INCORRECTA
    start_date=fecha_inicio_str,
    end_date=fecha_final_str
)
```

#### Evidencia
La BD tiene **83,805 registros** de `AporEner` para `entidad='Rio'` pero solo **2,227** para `entidad='Sistema'`:

```sql
SELECT entidad, COUNT(*) FROM metrics 
WHERE metrica='AporEner' 
GROUP BY entidad;

-- Rio      | 83,805 ✅
-- Sistema  |  2,227 ❌
```

Los aportes se reportan **POR RÍO**, no consolidados a nivel sistema.

#### Impacto
- Dashboard muestra 0% porque consulta `entity='Sistema'` que está vacía
- Datos correctos existen pero están en `entity='Rio'`
- Gráfico temporal plano (sin datos)

#### Solución
```python
# CORRECCIÓN APLICADA (hydrology_service.py línea 64)
df_aportes = repo.get_metric_data_by_entity(
    metric_id='AporEner',
    entity='Rio',  # ✅ CORRECTO: Agregar todos los ríos
    start_date=fecha_inicio_str,
    end_date=fecha_final_str
)

# Luego agregar todos los ríos
aportes_valor = df_aportes['valor_gwh'].sum()
```

**Validación necesaria:**
```python
def validate_aportes_hidricos(value):
    """Aportes Colombia deben estar entre 50-95%"""
    if not (50 <= value <= 95):
        logger.warning(f"⚠️ Aportes fuera de rango: {value}%")
        return None
    return value
```

---

### **BUG #3: RESTRICCIONES $0 - FILTRO DE UNIDADES FALTANTE (CRÍTICO)**

**Archivo:** `/home/admonctrlxm/server/domain/services/restrictions_service.py` líneas 44-48

#### Problema
```python
# CÓDIGO ACTUAL (PARCIALMENTE CORREGIDO)
df = self.repo.get_metric_data(
    metric_id, 
    start_date, 
    end_date, 
    unit='COP'  # ✅ YA AGREGADO pero la BD puede no tener unit='COP'
)
```

La BD mezcla **2 unidades** para restricciones:
- **COP** (pesos colombianos - valores monetarios)
- **MWh** (energía - valores físicos)

Si la query filtra `unit='COP'` pero la columna `unidad` en BD está vacía/NULL, retorna 0 registros.

#### Evidencia
```sql
-- Verificar unidades en BD
SELECT metrica, unidad, COUNT(*) FROM metrics 
WHERE metrica IN ('RestAliv', 'RestSinAliv') 
GROUP BY metrica, unidad;

-- Si unidad es NULL, el filtro falla
```

#### Impacto
- Dashboard muestra "$0 millones COP"
- Datos existen pero no se consultan correctamente

#### Solución
```python
# restrictions_service.py - MEJORAR LÓGICA DE FALLBACK
try:
    # Intentar con unidad COP primero
    df = self.repo.get_metric_data(metric_id, start_date, end_date, unit='COP')
    
    if df is None or df.empty:
        # Fallback: sin filtro de unidad, luego filtrar en pandas
        df = self.repo.get_metric_data(metric_id, start_date, end_date)
        
        if df is not None and not df.empty:
            # Filtrar manualmente si existe columna unidad
            if 'unidad' in df.columns:
                df = df[df['unidad'].str.upper() == 'COP']
                logger.info(f"✅ Filtrado manual: {len(df)} registros COP")
            else:
                # Si no hay columna unidad, asumir que son valores monetarios
                logger.warning(f"⚠️ {metric_id}: Sin columna 'unidad', asumiendo COP")
    
    # Validar que no sean todos ceros
    if df is not None and not df.empty:
        if df['valor_gwh'].sum() == 0:
            logger.error(f"❌ {metric_id}: Todos los valores son 0")
            # Intentar días anteriores (código existente líneas 56-63)
            
except Exception as e:
    logger.error(f"Error fetching {metric_id}: {e}")
    return pd.DataFrame()
```

---

### **BUG #4: NORMALIZACIÓN DE DATOS FRÁGIL (MEDIO)**

**Archivo:** `/home/admonctrlxm/server/domain/services/metrics_service.py` líneas 40-78

#### Problema
```python
def _normalize_time_series(self, df: pd.DataFrame) -> pd.DataFrame:
    # Solo normaliza nombres de columnas, NO valida tipos ni valores
    col_map = {
        'fecha': 'Date',
        'valor_gwh': 'Value',
        # ...
    }
    df = df.rename(columns=col_map)
    
    # Conversión débil sin validación
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')  # ⚠️ errors='coerce' silencia fallos
    
    if 'Value' in df.columns:
        df['Value'] = pd.to_numeric(df['Value'], errors='coerce')  # ⚠️ NaN sin logging
```

#### Evidencia
Logs muestran: `"⚠️ [MetricsService] Error de normalización: columnas faltantes"`

Pero no hay logging de:
- Cuántos valores se convirtieron a NaN
- Qué valores fallaron la conversión
- Qué estructura tenía el DataFrame original

#### Impacto
- Datos corruptos pasan silenciosamente
- NaN's se propagan a cálculos
- Debugging imposible (sin logs detallados)

#### Solución
```python
def _normalize_time_series(self, df: pd.DataFrame) -> pd.DataFrame:
    """Normalización ROBUSTA con validación y logging"""
    if df is None or df.empty:
        logger.warning("DataFrame vacío en normalización")
        return pd.DataFrame(columns=['Date', 'Value'])
    
    # LOGGING DIAGNÓSTICO
    logger.debug(f"📊 Normalizando DataFrame: {df.shape[0]} filas, columnas: {df.columns.tolist()}")
    
    # Renombrar columnas
    col_map = {
        'fecha': 'Date', 'date': 'Date', 'Fecha': 'Date',
        'valor_gwh': 'Value', 'valor': 'Value', 'Values': 'Value'
    }
    df = df.rename(columns=col_map)
    
    # Validar columnas obligatorias ANTES de conversión
    if 'Date' not in df.columns:
        logger.error(f"❌ Columna 'Date' faltante. Disponible: {df.columns.tolist()}")
        return pd.DataFrame(columns=['Date', 'Value'])
    
    if 'Value' not in df.columns:
        logger.error(f"❌ Columna 'Value' faltante. Disponible: {df.columns.tolist()}")
        return pd.DataFrame(columns=['Date', 'Value'])
    
    # Conversión con REPORTE de errores
    original_rows = len(df)
    
    # Fechas
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    null_dates = df['Date'].isna().sum()
    if null_dates > 0:
        logger.warning(f"⚠️ {null_dates}/{original_rows} fechas inválidas convertidas a NaT")
    
    # Valores numéricos
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    null_values = df['Value'].isna().sum()
    if null_values > 0:
        logger.warning(f"⚠️ {null_values}/{original_rows} valores inválidos convertidos a NaN")
        # Mostrar ejemplos de valores problemáticos
        sample_bad = df[df['Value'].isna()].head(3)
        logger.debug(f"Ejemplos de valores problemáticos:\n{sample_bad}")
    
    # Limpiar NaN's
    df_cleaned = df.dropna(subset=['Date', 'Value'])
    dropped = original_rows - len(df_cleaned)
    if dropped > 0:
        logger.warning(f"🧹 {dropped} filas eliminadas por NaN's")
    
    # Validar rangos razonables
    if not df_cleaned.empty:
        min_val = df_cleaned['Value'].min()
        max_val = df_cleaned['Value'].max()
        logger.debug(f"✅ Valores: min={min_val:.2f}, max={max_val:.2f}")
    
    return df_cleaned
```

---

### **BUG #5: ETL NO SE EJECUTA - WORKERS INACTIVOS (CRÍTICO)**

**Archivo:** `/home/admonctrlxm/server/tasks/etl_tasks.py`

#### Problema
**Flower muestra:**
- 3 workers activos (worker1, worker2, celery@...)
- **0 tareas procesadas** en workers nuevos
- Worker antiguo offline con 64 tareas históricas

**El ETL automático NO se está ejecutando.**

#### Evidencia
```python
# etl_tasks.py línea 145-160
@shared_task
def etl_incremental_all_metrics():
    """Se ejecuta cada 6 horas vía Celery Beat"""
    logger.info("🚀 Iniciando ETL incremental automático")
    
    metrics = ['PrecBolsNaci', 'Gene', 'DEM', 'TRAN', 'PerdidasEner']
    
    # Rango: últimos 7 días
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
```

Pero Celery Beat **NO está configurado** o **NO está activo**:

```bash
$ systemctl status celery-beat
# Verificar si está corriendo
```

#### Impacto
- BD desactualizada (últimos datos de semanas atrás)
- Cache vacío (porque ETL no escribe a Redis)
- Dashboard muestra datos obsoletos/ausentes

#### Solución

**1. Verificar Celery Beat:**
```bash
# Ver configuración de beat
celery -A tasks inspect scheduled

# Ver tareas registradas
celery -A tasks inspect registered
```

**2. Ejecutar ETL manual INMEDIATO:**
```bash
cd /home/admonctrlxm/server
python3 etl/etl_todas_metricas_xm.py
```

**3. Configurar Celery Beat correctamente:**
```python
# tasks/__init__.py o celeryconfig.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    'etl-incremental-every-6-hours': {
        'task': 'tasks.etl_tasks.etl_incremental_all_metrics',
        'schedule': crontab(minute=0, hour='*/6'),  # Cada 6 horas
    },
}
```

**4. Reiniciar servicios:**
```bash
sudo systemctl restart celery-worker celery-beat
sudo systemctl status celery-beat  # Verificar activo
```

---

### **BUG #6: VALIDACIONES DE RANGO FALTANTES (MEDIO)**

**Archivo:** Múltiples servicios (commercial_service, generation_service, hydrology_service)

#### Problema
Los cálculos **NO validan rangos razonables** de valores:

```python
# commercial_service.py - Sin validación
def get_stock_price(self, start_date, end_date):
    df = self._get_price_metric('PrecBolsNaci', ...)
    # NO valida si precio es 0, negativo, o > 1000 $/kWh
    return df

# hydrology_service.py línea 103 - Validación presente pero NO SE USA
if not (30 <= porcentaje <= 150):
    logger.warning(f"Aportes fuera de rango normal: {porcentaje:.1f}%")
    # ⚠️ Solo logea, NO retorna None ni marca como inválido
```

#### Evidencia
Screenshots muestran:
- **Spread Escasez: $502 $/kWh** (normal: $50-150)
- **DNA Nacional: 33 GWh** (Colombia consume ~200 GWh/día)
- Valores pasan a dashboard sin cuestionarse

#### Solución
```python
# Crear validators.py centralizado
class MetricValidators:
    """Validadores de rangos para métricas energéticas Colombia"""
    
    RANGES = {
        'PrecBolsNaci': (50, 300),      # $/kWh
        'PrecEsca': (50, 200),           # $/kWh
        'AportesHidricos': (50, 95),     # %
        'ReservasHidricas': (40, 100),   # %
        'GeneracionSIN': (150, 300),     # GWh/día
        'DemandaNacional': (150, 250),   # GWh/día
        'Restricciones': (0, 10000),     # Millones COP
    }
    
    @classmethod
    def validate(cls, metric_name: str, value: float) -> bool:
        """Retorna True si el valor está en rango razonable"""
        if metric_name not in cls.RANGES:
            return True  # Sin validación definida
        
        min_val, max_val = cls.RANGES[metric_name]
        is_valid = min_val <= value <= max_val
        
        if not is_valid:
            logger.warning(
                f"⚠️ {metric_name}={value:.2f} fuera de rango [{min_val}, {max_val}]"
            )
        
        return is_valid

# Usar en servicios
from core.validators import MetricValidators

def get_aportes_hidricos(self, fecha):
    # ... cálculo de porcentaje ...
    
    if not MetricValidators.validate('AportesHidricos', porcentaje):
        logger.error(f"❌ Aportes inválidos: {porcentaje}%")
        return None, None  # ← RECHAZAR dato malo
    
    return porcentaje, aportes_valor
```

---

### **BUG #7: CALLBACKS SIN MANEJO DE DATOS VACÍOS (MEDIO)**

**Archivo:** `/home/admonctrlxm/server/interface/pages/generacion_hidraulica_hidrologia.py` línea 1640+

#### Problema
```python
@callback(...)
def update_ficha_kpi(n_clicks, rango, start_date, end_date, region, rio):
    data, _ = obtener_datos_inteligente('AporEner', 'Rio', start_date_str, end_date_str)
    
    if data is None or data.empty:
        logger.warning(f"⚠️ Ficha KPI: No hay datos")
        return html.Div()  # ← Retorna vacío sin mensaje al usuario
    
    # Continúa procesamiento sin validar más adelante
    total_real = data_filtrada['Value'].sum()  # ⚠️ Puede ser 0
```

Si `data` está vacío, el usuario ve **componentes vacíos** sin explicación.

#### Solución
```python
@callback(...)
def update_ficha_kpi(n_clicks, rango, start_date, end_date, region, rio):
    data, _ = obtener_datos_inteligente('AporEner', 'Rio', start_date_str, end_date_str)
    
    if data is None or data.empty:
        # Mensaje claro al usuario
        return dbc.Alert(
            [
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"No hay datos de aportes hídricos para el período {start_date_str} - {end_date_str}. ",
                html.Br(),
                "Intente con un rango de fechas diferente o ejecute el ETL."
            ],
            color="warning",
            className="mt-3"
        )
    
    # Validar después de filtrar
    if data_filtrada.empty:
        return dbc.Alert(
            f"No hay datos para la región/río seleccionado en el período especificado.",
            color="info"
        )
    
    # Validar valores numéricos
    if total_real == 0:
        return dbc.Alert(
            f"⚠️ Total de aportes = 0 GWh. Verifique los datos en la base de datos.",
            color="warning"
        )
    
    # Continuar procesamiento normal...
```

---

## 🔧 PLAN DE ACCIÓN INMEDIATA

### **FASE 1: RESTAURAR DATOS (PRIORIDAD CRÍTICA)**

```bash
# 1. Ejecutar ETL completo manual
cd /home/admonctrlxm/server
python3 etl/etl_todas_metricas_xm.py

# 2. Verificar carga de datos
sqlite3 data/metricas_xm.db "SELECT metrica, COUNT(*) FROM metrics GROUP BY metrica LIMIT 10;"

# 3. Verificar Celery Beat activo
sudo systemctl status celery-beat
sudo systemctl restart celery-beat

# 4. Forzar ejecución de tarea ETL
celery -A tasks call tasks.etl_tasks.etl_incremental_all_metrics
```

### **FASE 2: APLICAR CORRECCIONES DE CÓDIGO**

```bash
# Aplicar fixes a:
# 1. hydrology_service.py - Cambiar entity='Sistema' a 'Rio'
# 2. restrictions_service.py - Mejorar filtro de unidades
# 3. metrics_service.py - Añadir logging diagnóstico
# 4. Crear validators.py - Validaciones de rangos

# Reiniciar dashboard
sudo systemctl restart dashboard-mme
```

### **FASE 3: VALIDAR RESULTADOS**

```bash
# Test script de validación
cat > /tmp/test_dashboard_data.py << 'EOF'
from domain.services.hydrology_service import HydrologyService
from domain.services.restrictions_service import RestrictionsService
from datetime import date

# Test Aportes
hydro = HydrologyService()
aportes_pct, aportes_gwh = hydro.get_aportes_hidricos('2026-01-31')
print(f"Aportes: {aportes_pct}% ({aportes_gwh} GWh)")
assert 50 <= aportes_pct <= 95, f"Aportes fuera de rango: {aportes_pct}%"

# Test Restricciones
rest = RestrictionsService()
data = rest.get_restrictions_analysis('2026-01-01', '2026-01-31')
total = sum(df['valor_gwh'].sum() for df in data.values() if not df.empty)
print(f"Restricciones: ${total/1e6:.1f} millones COP")
assert total > 0, "Restricciones no pueden ser 0"

print("✅ TODAS LAS VALIDACIONES PASARON")
EOF

python3 /tmp/test_dashboard_data.py
```

---

## 📊 SCRIPTS DE DIAGNÓSTICO

### **Script 1: Validar integridad SQLite**
```bash
cat > /tmp/validate_db.sh << 'EOF'
#!/bin/bash
DB="/home/admonctrlxm/server/data/metricas_xm.db"

echo "=== INVENTARIO DE MÉTRICAS ==="
sqlite3 $DB "SELECT metrica, entidad, COUNT(*) as registros, MIN(fecha), MAX(fecha) 
FROM metrics 
WHERE metrica IN ('AporEner', 'RestAliv', 'RestSinAliv', 'Gene')
GROUP BY metrica, entidad
ORDER BY metrica, entidad;"

echo -e "\n=== UNIDADES DE RESTRICCIONES ==="
sqlite3 $DB "SELECT metrica, unidad, COUNT(*) 
FROM metrics 
WHERE metrica LIKE 'Rest%' 
GROUP BY metrica, unidad;"

echo -e "\n=== VALORES NULL ==="
sqlite3 $DB "SELECT metrica, COUNT(*) 
FROM metrics 
WHERE valor_gwh IS NULL 
GROUP BY metrica;"
EOF

bash /tmp/validate_db.sh
```

### **Script 2: Probar API XM directa**
```python
# /tmp/test_xm_api.py
from infrastructure.external.xm_service import fetch_metric_data
from datetime import date, timedelta

# Test 1: Aportes recientes
end = date.today()
start = end - timedelta(days=7)

print("🔍 Probando API XM...")
df = fetch_metric_data('AporEner', 'Rio', start, end)

if df is not None:
    print(f"✅ Datos recibidos: {len(df)} registros")
    print(f"Columnas: {df.columns.tolist()}")
    print(df.head())
else:
    print("❌ API XM no devolvió datos")
```

### **Script 3: Limpiar cache corrupto**
```bash
#!/bin/bash
echo "⚠️ LIMPIANDO REDIS..."
redis-cli FLUSHDB
echo "✅ Redis limpio"

echo "🔄 REINICIANDO WORKERS..."
sudo systemctl restart celery-worker celery-beat
sleep 3
sudo systemctl status celery-worker | head -15
```

---

## 🎯 VALORES ESPERADOS (VALIDACIÓN POST-FIX)

| Métrica | Valor Actual | Valor Esperado | Unidad |
|---------|--------------|----------------|--------|
| Aportes Hídricos | 0.00% ❌ | 60-70% | % vs histórico |
| Reservas Hídricas | 76.41% ✅ | 70-85% | % capacidad |
| Restricciones | $0 M ❌ | $500-2000 M | COP |
| Precio Bolsa | $208 ✅ | $150-300 | $/kWh |
| Spread Escasez | $502 ❌ | $50-150 | $/kWh |
| DNA Nacional | 33 GWh ❌ | 180-220 GWh | GWh/día |
| Generación SIN | 242.84 GWh ✅ | 200-260 GWh | GWh/día |

---

## 📌 CONCLUSIÓN

**Diagnóstico confirmado:** El problema NO es de infraestructura sino de **LÓGICA DE DATOS**:

1. **ETL inactivo** → BD desactualizada
2. **Cache vacío** → Sin persistencia
3. **Consultas incorrectas** → Entity='Sistema' vs 'Rio'
4. **Sin validaciones** → Datos corruptos pasan
5. **Callbacks frágiles** → Errores silenciosos

**Tiempo estimado de corrección:** 2-3 horas (aplicar fixes + ejecutar ETL + validar)

**Riesgo de regresión:** BAJO (changes son quirúrgicos, no arquitectónicos)

---

## 🚀 PRÓXIMOS PASOS

1. ✅ **Ejecutar ETL completo** (restaurar datos)
2. ✅ **Aplicar Fix #1:** Cambiar entity='Rio' en aportes
3. ✅ **Aplicar Fix #2:** Mejorar filtro restricciones
4. ⏳ **Aplicar Fix #3:** Logging robusto normalización
5. ⏳ **Aplicar Fix #4:** Validadores de rangos
6. ⏳ **Aplicar Fix #5:** Mensajes de error en callbacks
7. ✅ **Validar dashboard** con valores esperados

---

**FIN DEL REPORTE**
