# 📊 MAPEO COMPLETO DE MÉTRICAS - Portal Energético MME

**Fecha de análisis:** 9 de febrero de 2026  
**Propósito:** Documentar TODAS las métricas disponibles por tablero para orquestador inteligente

---

## 🎯 OBJETIVO DEL ORQUESTADOR

El chatbot debe poder responder:
1. **Estado actual del sector** (¿Cómo está el sistema ahora?)
2. **Anomalías detectadas** (¿Hay problemas o valores atípicos?)

Para lograrlo, necesita acceso a:
- ✅ Todas las fichas KPI
- ✅ Todas las gráficas y sus datos
- ✅ Comparaciones anuales
- ✅ Predicciones SARIMA
- ✅ Inventarios completos
- ✅ Datos geográficos
- ✅ Análisis de tendencias

---

## 📁 TABLEROS Y SUS MÉTRICAS

### 1. 🔌 GENERACIÓN ELÉCTRICA

**Página:** `interface/pages/generacion.py`

#### Fichas KPI (3):
1. **Reservas Hídricas**
   - Porcentaje de llenado de embalses
   - Volumen útil en GWh
   - Fórmula: `(VoluUtilDiarEner / CapaUtilDiarEner) * 100`
   - Validación: Rechazar si < 10,000 GWh

2. **Aportes Hídricos**
   - Porcentaje vs media histórica
   - Aportes reales vs histórico
   - Fórmula: `(AporEner / AporEnerMediHist) * 100`

3. **Generación SIN**
   - Generación diaria total en GWh
   - Métrica: `Gene/Sistema`

#### Servicios disponibles:
- `get_daily_generation_system()` - Generación total diaria
- `get_generation_by_source()` - Por fuente (hidráulica, térmica, eólica, solar, biomasa)
- `get_resources_by_type()` - Listado de plantas
- `get_generation_mix()` - Mix energético (% por fuente)
- `get_generation_summary()` - Resumen con estadísticas
- `get_aggregated_generation_by_type()` - Agregación por tipo

#### Endpoints API:
- `GET /generation/system` - Generación total
- `GET /generation/by-source` - Por fuente
- `GET /generation/resources` - Catálogo de plantas
- `GET /generation/mix` - Mix energético

#### Datos disponibles:
- Generación diaria por planta
- Clasificación por tipo de fuente
- Serie temporal completa
- Capacidad instalada
- Estado de plantas (activo/inactivo)

---

### 2. 💧 HIDROLOGÍA Y EMBALSES

**Página:** `interface/pages/generacion_hidraulica_hidrologia.py`

#### Fichas KPI (3+):
1. **Reservas Hídricas Sistema**
   - Nivel promedio nacional
   - Energía embalsada total

2. **Aportes Hídricos Sistema**
   - % vs media histórica
   - Aportes en GWh

3. **Humedad/Nivel Actual**
   - Indicador de estado hídrico
   - Comparación temporal

#### Componentes importantes:
- **Mapa de embalses** (geo-data)
  - Ubicación de cada embalse
  - Estado visual por nivel
  - Datos por región

- **Tabla de embalses**
  - Listado completo
  - Nivel individual
  - Capacidad útil
  - Río asociado
  - Región hidrológica

- **Gráfica línea temporal**
  - Evolución de niveles
  - Serie histórica
  - Tendencias

- **Comparación anual**
  - Año actual vs año anterior
  - Diferencias porcentuales

#### Servicios disponibles:
- `get_reservas_hidricas()` - Reservas sistema
- `get_aportes_hidricos()` - Aportes sistema
- `calcular_volumen_util_unificado()` - Volumen por región/embalse
- `get_aportes_diarios()` - Serie temporal aportes
- `get_embalses()` - Catálogo de embalses
- `get_energia_embalsada()` - Energía total embalsada
- `get_reservoir_levels()` - Niveles individuales

#### Endpoints API:
- `GET /hydrology/aportes` - Aportes diarios
- `GET /hydrology/reservoirs` - Listado embalses
- `GET /hydrology/energy` - Energía embalsada

#### Datos disponibles:
- Nivel por embalse (%)
- Volumen útil (GWh)
- Capacidad útil (GWh)
- Aportes diarios
- Media histórica
- Región hidrológica
- Coordenadas geográficas
- Río asociado

---

### 3. ⚡ SISTEMA (Demanda y Precios)

**Servicios:** `system_service.py`

#### Métricas principales:
1. **Demanda Eléctrica**
   - Demanda comercial diaria
   - Métrica: `DemaCome/Sistema`
   - Demanda horaria
   - Picos de demanda

2. **Precios de Bolsa**
   - Precio en bolsa ($/kWh)
   - Serie temporal
   - Estadísticas (min, max, promedio)

#### Servicios disponibles:
- `get_daily_demand()` - Demanda diaria
- `get_daily_spot_prices()` - Precios bolsa
- `get_demand_statistics()` - Estadísticas demanda

#### Endpoints disponibles:
- `GET /system/demand` - Demanda comercial
- `GET /system/prices` - Precios bolsa

---

### 4. 🔌 TRANSMISIÓN

**Página:** `interface/pages/transmision.py`  
**Servicios:** `transmission_service.py`

#### Componentes importantes:
- **Inventario de líneas**
  - Listado completo de líneas de transmisión
  - Tensión (kV)
  - Longitud
  - Propietario
  - Estado

- **Mapa de red**
  - Ubicación geográfica
  - Conexiones entre subestaciones

- **Intercambios internacionales**
  - Exportaciones/importaciones
  - Energía intercambiada

#### Servicios disponibles:
- `get_transmission_lines()` - Inventario líneas
- `get_summary_stats()` - Estadísticas red
- `get_intercambios_internacionales()` - Intercambios

#### Datos disponibles:
- Líneas de transmisión
- Nivel de tensión
- Longitud de líneas
- Subestaciones
- Intercambios internacionales
- Flujos de energía

---

### 5. 🏘️ DISTRIBUCIÓN

**Página:** `interface/pages/distribucion.py`  
**Servicios:** `distribution_service.py`

#### Métricas principales:
- Energía distribuida por OR (Operador de Red)
- Usuarios por OR
- Cobertura geográfica
- Indicadores de calidad

#### Servicios disponibles:
- `get_distribution_analysis()` - Análisis distribución
- `get_operators()` - Listado de ORs

---

### 6. 💰 COMERCIALIZACIÓN

**Página:** `interface/pages/comercializacion.py`  
**Servicios:** `commercial_service.py`

#### Métricas principales:
- Precios contratos
- Energía comercializada
- Agentes del mercado
- Transacciones

#### Servicios disponibles:
- `get_commercial_analysis()` - Análisis comercial
- `get_contract_prices()` - Precios contratos

---

### 7. 📉 PÉRDIDAS

**Página:** `interface/pages/perdidas.py`  
**Servicios:** `losses_service.py`

#### Métricas principales:
- Pérdidas de transmisión (%)
- Pérdidas de distribución (%)
- Pérdidas totales sistema
- Energía perdida (GWh)

#### Servicios disponibles:
- `get_losses_analysis()` - Análisis pérdidas
- `get_losses_indicators()` - Indicadores
- `get_losses_data()` - Datos pérdidas

#### Datos disponibles:
- Pérdidas por tipo
- Tendencias temporales
- Comparación con umbrales

---

### 8. ⚠️ RESTRICCIONES

**Página:** `interface/pages/restricciones.py`  
**Servicios:** `restrictions_service.py`

#### Métricas principales:
- Restricciones operativas activas
- Energía restringida
- Costos de restricciones
- Causas de restricciones

#### Servicios disponibles:
- `get_restrictions_analysis()` - Análisis restricciones
- `get_restrictions_summary()` - Resumen
- `get_restrictions_data()` - Datos detallados

#### Datos disponibles:
- Número de restricciones
- Energía afectada
- Duraci ón
- Tipo de restricción
- Recursos afectados

---

### 9. 🤖 PREDICCIONES (SARIMA)

**Servicios:** `predictions_service.py`, `predictions_service_extended.py`

#### Modelos disponibles:
- Prophet
- ARIMA
- SARIMA
- Ensemble

#### Variables predichas:
- Generación hidráulica
- Demanda eléctrica
- Precios de bolsa
- Niveles de embalses

#### Servicios disponibles:
- `predict_generation()` - Predicción generación
- `predict_demand()` - Predicción demanda
- `predict_prices()` - Predicción precios
- `get_prediction_accuracy()` - Precisión modelos

#### Datos disponibles:
- Forecast horizonte 7-90 días
- Intervalos de confianza
- Métricas de precisión (MAPE, RMSE)
- Comparación modelo vs real

---

### 10. 📋 MÉTRICAS GENERALES

**Página:** `interface/pages/metricas.py`  
**Servicios:** `metrics_service.py`, `indicators_service.py`

#### Indicadores consolidados:
- Resumen del sector completo
- KPI agregados
- Estado general del sistema
- Alertas y notificaciones

#### Servicios disponibles:
- `get_metrics_metadata()` - Metadatos métricas
- `get_metric_series_hybrid()` - Series temporales
- `calculate_all_indicators()` - Todos los indicadores

---

## 🚨 VALIDADORES Y RANGOS

**Archivo:** `domain/services/validators.py`

Contiene rangos válidos para cada métrica:
- Reservas Hídricas: 0-100%
- Aportes: 0-300%
- Generación: > 0 GWh
- Demanda: > 0 GWh
- Precios: > 0 $/kWh
- Pérdidas: 0-20%

---

## 🎯 LO QUE EL ORQUESTADOR NECESITA HACER

### 1. **Estado Actual del Sector**

Para cada tablero, consolidar:
- ✅ Últimos valores de todas las fichas KPI
- ✅ Tendencia (subiendo/bajando/estable)
- ✅ Comparación con histórico
- ✅ Clasificación (normal/alerta/crítico)

### 2. **Detección de Anomalías**

Para cada métrica:
- 🔴 **Crítico:** Valor fuera de rango seguro
- 🟡 **Alerta:** Valor cerca de límites
- 🟢 **Normal:** Valor dentro de rango esperado

Ejemplos de anomalías:
- Reservas < 30% → CRÍTICO
- Generación hoy vs ayer -20% → ALERTA
- Precios bolsa > μ + 2σ → ANÓMALO
- Restricciones 3x vs semana pasada → ALERTA
- Pérdidas > 15% → CRÍTICO
- Aportes < 70% → ALERTA

### 3. **Análisis Comparativo**

- Hoy vs ayer
- Semana actual vs semana anterior
- Mes actual vs mes anterior
- Año actual vs año anterior
- Valor actual vs promedio histórico

### 4. **Información Contextual**

Para cada valor anómalo:
- Magnitud de la desviación
- Duración del evento
- Recursos/regiones af ectados
- Posible causa (si se puede inferir)
- Recomendaciones

---

## 📝 SIGUIENTE PASO

Diseñar el **Servicio de Análisis Inteligente** que:

1. **Recopile** todos los datos de todos los servicios
2. **Calcule** indicadores derivados
3. **Compare** con históricos y umbrales
4. **Detecte** anomalías automáticamente
5. **Clasifique** severidad (normal/alerta/crítico)
6. **Genere** resumen textual inteligente
7. **Retorne** estado + anomalías

---

**Documento en progreso** - Se actualizará con más detalles según análisis
