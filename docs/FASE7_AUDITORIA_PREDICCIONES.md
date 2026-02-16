# FASE 7 — Auditoría Técnica del Pipeline de Predicciones

**Fecha:** 2026-02-15  
**Tipo:** Solo lectura / análisis (sin modificaciones de código)  
**Autor:** Auditoría automatizada  

---

## 1. MAPEO TÉCNICO COMPLETO

### 1.1 Arquitectura del Pipeline

```
actualizar_predicciones.sh  (cron: domingos 02:00 AM)
 ├── train_predictions_postgres.py        → 5 fuentes de generación
 │   └── PredictorEnsemble                  Prophet + SARIMA → ENSEMBLE_v1.0
 │         └── PostgreSQLConnectionManager → INSERT INTO predictions
 │
 └── train_predictions_sector_energetico.py → 9 métricas estratégicas
       └── PredictorMetricaSectorial          Prophet + SARIMA → ENSEMBLE_SECTOR_v1.0
             └── PostgreSQLConnectionManager → INSERT INTO predictions

API (on-demand, ruta separada):
 └── api/v1/routes/predictions.py
       └── PredictionsService (predictions_service_extended.py)
             ├── PredictionsRepository → lee predictions ya almacenadas
             └── forecast_metric()     → genera predicciones LIVE (Prophet/ARIMA)
                                         con parámetros DISTINTOS a los batch
```

### 1.2 Archivos Involucrados

| Archivo | Líneas | Rol |
|---------|--------|-----|
| `scripts/train_predictions_sector_energetico.py` | 652 | Entrenamiento batch: 9 métricas estratégicas |
| `scripts/train_predictions_postgres.py` | 484 | Entrenamiento batch: 5 fuentes de generación |
| `scripts/actualizar_predicciones.sh` | 223 | Orquestador cron (domingos 02:00) |
| `domain/services/predictions_service.py` | 34 | Wrapper simple (solo lectura BD) |
| `domain/services/predictions_service_extended.py` | 433 | Servicio completo con forecast on-demand |
| `infrastructure/database/repositories/predictions_repository.py` | 152 | CRUD predictions table |
| `api/v1/routes/predictions.py` | 221 | Endpoints FastAPI |
| `domain/models/prediction.py` | 54 | Dataclass Prediction |
| `domain/interfaces/repositories.py` | ~44 | ABC IPredictionsRepository |
| `sql/create_predictions_table.sql` | 286 | DDL completo + views + funciones |

### 1.3 Métricas Configuradas (12 fuentes)

#### Script `train_predictions_sector_energetico.py` (ENSEMBLE_SECTOR_v1.0)

| Fuente | Métrica BD | Agregación | Config especial |
|--------|-----------|------------|-----------------|
| GENE_TOTAL | `Gene` | SUM, entidad='Sistema' | — |
| DEMANDA | `DemaReal` | SUM, prefer_sistema | Solo usa metricas[0] |
| PRECIO_BOLSA | `PrecBolsNaci` | AVG, entidad='Sistema' | solo_prophet, growth='flat', ventana=8m, piso=86.0 |
| PRECIO_ESCASEZ | `PrecEsca` | AVG | — |
| APORTES_HIDRICOS | `AporEner` | SUM | — |
| EMBALSES | `CapaUtilDiarEner` | SUM, entidad='Sistema' | — |
| EMBALSES_PCT | `PorcVoluUtilDiar` | AVG, entidad='Sistema' | escala_factor=100 |
| PERDIDAS | `PerdidasEner` | SUM, prefer_sistema | — |

#### Script `train_predictions_postgres.py` (ENSEMBLE_v1.0)

| Fuente | Filtro | Agregación |
|--------|--------|------------|
| Hidráulica | catalogos.tipo='HIDRAULICA' | SUM(Gene) por día |
| Térmica | catalogos.tipo='TERMICA' | SUM(Gene) por día |
| Eólica | catalogos.tipo='EOLICA' | SUM(Gene) por día |
| Solar | catalogos.tipo='SOLAR' | SUM(Gene) por día |
| Biomasa | catalogos.tipo='BIOMASA' | SUM(Gene) por día |

### 1.4 Hiperparámetros de los Modelos

| Parámetro | Sector (v1.0) | Postgres (v1.0) |
|-----------|---------------|-----------------|
| Prophet `changepoint_prior_scale` | 0.05 | 0.05 |
| Prophet `seasonality_prior_scale` | 10.0 | 10.0 |
| Prophet yearly_seasonality | auto (≥365 pts) | True |
| Prophet weekly_seasonality | True | False |
| Prophet daily_seasonality | False | False |
| SARIMA `m` (estacionalidad) | 7 | 7 |
| SARIMA `max_order` | 5 | max_p=2,max_q=2 |
| SARIMA `D` | auto | 1 |
| Horizonte | 90 días | 90 días |
| Holdout validación | 30 días | 30 días |
| Pesos iniciales | prophet=0.6, sarima=0.4 | prophet=0.5, sarima=0.5 |
| Confianza (intervalo) | 0.95 | 0.95 |

---

## 2. AUDITORÍA DE CALIDAD

### 2.1 Estado Actual de Predicciones en BD

**Total:** 1,080 filas (12 fuentes × 90 días)  
**Generadas:** 2026-02-15 (todas el mismo día)  
**Rango predicciones:** 2026-02-05 a 2026-05-15  
**Entrenamiento cron:** Domingos 02:00 AM  

### 2.2 MAPE y Confianza por Fuente

La columna `mape` y `rmse` están **NULL en todas las 1,080 filas**. Solo se almacena `confianza`.

| Fuente | Confianza | MAPE implícito* | Avg predicho | Avg real reciente | Δ% |
|--------|-----------|-----------------|-------------|-------------------|-----|
| EMBALSES | 1.00 | ~0% | 16,902 GWh | — | — |
| EMBALSES_PCT | 0.98 | ~2% | 70.94% | 75.69% | -6.3% |
| GENE_TOTAL | 0.97 | ~3% | 238.41 GWh | 235.02 GWh | +1.4% |
| Biomasa | 0.95 | default** | 2.52 GWh | — | — |
| Eólica | 0.95 | default** | 0.61 GWh | — | — |
| Hidráulica | 0.95 | default** | 200.26 GWh | — | — |
| Solar | 0.95 | default** | 15.27 GWh | — | — |
| Térmica | 0.95 | default** | 14.61 GWh | — | — |
| DEMANDA | 0.66 | ~34% | 148.56 GWh | 176.07 GWh | **-15.6%** |
| APORTES_HIDRICOS | 0.54 | ~46% | 324.92 GWh | — | — |
| PRECIO_BOLSA | 0.41 | ~59% | 204.53 $/kWh | 111.76 $/kWh | **+83.0%** |
| PERDIDAS | 0.32 | ~68% | 0.41 GWh | 6.01 GWh† | **-93.2%** |

\* MAPE implícito = `1 - confianza` (solo aplica para métricas SECTOR_v1.0).  
\** Las 5 fuentes de generación usan `guardar_predicciones()` que hardcodea `CONFIANZA=0.95`, NO el MAPE real calculado.  
† PERDIDAS: los valores reales observados (Feb 5-10) promedian 6.01 GWh vs predicción ~0.41 GWh → **APE 86-93%**.

### 2.3 Validación Ex-Post (Overlap predicciones vs reales)

Solo **PERDIDAS** tiene overlap verificable:

| Fecha | Predicho | Real | APE |
|-------|----------|------|-----|
| 2026-02-05 | 0.66 | 4.78 | 86.2% |
| 2026-02-06 | 0.65 | 4.80 | 86.5% |
| 2026-02-07 | 0.64 | 3.98 | 83.9% |
| 2026-02-08 | 0.61 | 7.75 | 92.1% |
| 2026-02-09 | 0.60 | 8.24 | 92.7% |
| 2026-02-10 | 0.57 | 6.83 | 91.7% |

**MAPE ex-post PERDIDAS = 88.8%** — predicción completamente inútil.

Para las restantes 11 fuentes **NO hay overlap** (predicciones comienzan después de la última fecha de datos reales).

### 2.4 Cobertura de Datos de Entrenamiento

| Métrica BD | Desde | Hasta | Días únicos | Puntos totales |
|-----------|-------|-------|-------------|----------------|
| Gene | 2020-01-01 | 2026-02-12 | 2,235 | 528,702 |
| DemaReal | 2020-01-01 | 2026-02-12 | 2,235 | 184,495 |
| PrecBolsNaci | 2020-02-06 | 2026-02-12 | 2,199 | 2,199 |
| PorcVoluUtilDiar | 2020-02-06 | 2026-02-14 | 2,201 | 53,752 |
| CapaUtilDiarEner | 2020-01-01 | 2026-02-14 | 2,237 | 80,981 |
| AporEner | 2020-01-01 | 2026-02-14 | 2,237 | 86,579 |
| PerdidasEner | 2020-02-06 | 2026-02-10 | 2,197 | 4,222 |
| PrecEsca | 2020-02-06 | 2026-02-12 | 2,199 | 2,199 |
| DemaCome | 2020-01-01 | 2026-02-12 | 2,235 | 186,498 |

Todas las métricas tienen **≥6 años** de historia → suficiente para Prophet con estacionalidad anual.

---

## 3. BUGS Y PROBLEMAS DETECTADOS

### 🔴 BUG CRÍTICO 1: Fuga de datos en validación SARIMA

**Ambos scripts** (`train_predictions_sector_energetico.py` y `train_predictions_postgres.py`).

**Problema:** La validación holdout re-entrena Prophet correctamente con `df_train_p = df_prophet.iloc[:-30]`, pero usa **el SARIMA ya entrenado sobre TODOS los datos** (incluyendo el holdout). Al llamar `self.modelo_sarima.predict(n_periods=30)`, SARIMA predice 30 días **más allá del final de los datos completos** (T+1 a T+30), pero se compara con `y_real` que son los **últimos 30 días de datos observados** (T-29 a T).

**Consecuencia:**
- El MAPE de SARIMA es **espurio** (compara períodos temporales distintos)
- Los pesos Prophet/SARIMA derivados de esos MAPE son **arbitrarios**
- El MAPE del ensemble heredado es **poco fiable**
- La `confianza` almacenada es **engañosa**

**Corrección necesaria:** Re-entrenar SARIMA temporalmente con `serie_sarima.iloc[:-30]` y luego predecir 30 períodos ahead, o usar la misma ventana temporal que Prophet.

### 🔴 BUG CRÍTICO 2: MAPE/RMSE no se persisten en BD

**Archivo:** `guardar_predicciones_bd()` en `train_predictions_sector_energetico.py` (líneas 479-520)

**Problema:** El INSERT solo incluye 9 columnas: `fecha_prediccion, fecha_generacion, fuente, valor_gwh_predicho, intervalo_inferior, intervalo_superior, horizonte_dias, modelo, confianza`. Las columnas `mape` y `rmse` (que existen en la tabla) **nunca se llenan** → todas NULL.

El MAPE calculado durante validación se guarda en `self.metricas` (dict en memoria) y en `confianza_real`, pero `mape` y `rmse` como columnas no se pasan al INSERT.

**Consecuencia:** Imposible auditar calidad histórica de predicciones desde la BD.

### 🔴 BUG CRÍTICO 3: Confianza hardcodeada en `train_predictions_postgres.py`

**Archivo:** `guardar_predicciones()` línea 341

**Problema:** Usa `CONFIANZA` (constante = 0.95) para TODAS las fuentes de generación, ignorando el MAPE real calculado en `validar_modelos()`. El script sector sí pasa `config['confianza_real']`, pero el de postgres NO.

**Consecuencia:** Las 5 fuentes de generación (Hidráulica, Térmica, Eólica, Solar, Biomasa) siempre muestran confianza=0.95 sin importar la calidad real del modelo.

### 🟡 BUG MEDIO 4: DEMANDA usa solo primera métrica

**Archivo:** `train_predictions_sector_energetico.py`, config DEMANDA

**Problema:** La config declara `'metricas': ['DemaReal', 'DemaCome', 'DemaRealReg', 'DemaRealNoReg']` pero `cargar_datos_metrica()` (línea 413) solo usa `config['metricas'][0]` = `DemaReal`. Las demás métricas se ignoran.

**Consecuencia:** No es un error funcional (DemaReal es la correcta para demanda total), pero la config es engañosa. Las métricas adicionales son informativas/documentales, no funcionales.

### 🟡 BUG MEDIO 5: PERDIDAS — modelo catastrófico

**Problema:** PERDIDAS predice ~0.41 GWh/día vs ~6 GWh/día reales → error del 93%. La confianza de 0.32 (MAPE ~68% en holdout) ya señalaba problemas pero las predicciones pasaron igual.

**Causa probable:** El filtro `prefer_sistema` puede estar generando agregación incorrecta. Si hay pocos días con entidad='Sistema' para PERDIDAS, la serie terminada tiene muchos vacíos o valores muy bajos.

### 🟡 BUG MEDIO 6: Dos pipelines duplicados e inconsistentes

**Problema:** Existen dos servicios de predicción:
1. **Batch** (`train_predictions_*.py`): entrenamiento semanal, guarda en BD
2. **API on-demand** (`predictions_service_extended.py`): genera predicciones live con Prophet/ARIMA

Los hiperparámetros son **distintos** entre ambos:
- API: `daily_seasonality=True`, `weekly_seasonality=True` (Prophet), `max_p=5, max_q=5` (ARIMA)
- Batch: `daily_seasonality=False`, parámetros SARIMA más conservadores

**Consecuencia:** Un usuario que compara predicciones de la API vs las del chatbot (que lee de BD) podría obtener resultados diferentes para la misma métrica.

### 🟢 MENOR 7: Intervalos de confianza extremadamente anchos

| Fuente | Intervalo típico | Ancho relativo |
|--------|-----------------|----------------|
| APORTES_HIDRICOS | 144 – 553 GWh | ±63% del promedio |
| GENE_TOTAL | 146 – 327 GWh | ±38% del promedio |
| DEMANDA | 33 – 228 GWh | ±66% del promedio |

Intervalos así son informativamente vacíos para toma de decisiones.

### 🟢 MENOR 8: No hay versionado de modelos

Los modelos se entrenan y descartan. No hay persistencia de artefactos `.pkl`/`.json`, ni tracking de hiperparámetros, ni comparación entre versiones.

---

## 4. RESUMEN DE CALIDAD POR CATEGORÍA

| Categoría | Calidad | Notas |
|-----------|---------|-------|
| GENE_TOTAL | ✅ Buena | MAPE ~3%, valor coherente con recientes |
| EMBALSES | ✅ Buena | MAPE ~0% (serie muy estable) |
| EMBALSES_PCT | ✅ Buena | MAPE ~2%, ligera subestimación |
| Hidráulica/Solar | ⚠️ Incierta | Confianza hardcodeada, MAPE real desconocido |
| Térmica/Eólica/Biomasa | ⚠️ Incierta | Confianza hardcodeada, MAPE real desconocido |
| DEMANDA | ⚠️ Pobre | MAPE ~34%, subestima 15-16% |
| PRECIO_BOLSA | ❌ Mala | MAPE ~59%, sobreestima 83% vs recientes |
| APORTES_HIDRICOS | ❌ Mala | MAPE ~46% |
| PERDIDAS | ❌ Muy mala | MAPE 88.8% ex-post verificado |
| PRECIO_ESCASEZ | ⚠️ Sin datos overlap | No verificable |

---

## 5. PROPUESTAS DE MEJORA (sin implementar)

### P1: Corregir fuga de datos SARIMA en validación [Prioridad CRÍTICA]

En `validar_y_generar()` y `validar_modelos()`, re-entrenar SARIMA temporalmente:
```python
# En lugar de usar self.modelo_sarima (entrenado con TODOS los datos):
serie_train_s = serie_sarima.iloc[:-dias_validacion]
modelo_sarima_temp = auto_arima(serie_train_s.dropna(), seasonal=True, m=7, ...)
pred_sarima_val = modelo_sarima_temp.predict(n_periods=dias_validacion)
```
Esto asegura que SARIMA predice las mismas fechas que Prophet durante validación.

### P2: Persistir MAPE/RMSE en BD [Prioridad ALTA]

Modificar ambas funciones `guardar_predicciones*()` para pasar `mape` y `rmse`:
```python
cursor.execute("""
    INSERT INTO predictions (..., mape, rmse)
    VALUES (%s, ..., %s, %s)
""", (..., predictor.metricas.get('mape_ensemble'), predictor.metricas.get('rmse')))
```
Y calcular RMSE que actualmente no se computa.

### P3: Corregir confianza en `train_predictions_postgres.py` [Prioridad ALTA]

Reemplazar el hardcoded `CONFIANZA` por el MAPE real:
```python
confianza_real = max(0.0, 1.0 - predictor.metricas.get('mape_ensemble', 0))
```

### P4: Implementar umbral mínimo de calidad [Prioridad ALTA]

No guardar predicciones con MAPE > 50%. Ejemplo:
```python
if mape_ensemble > 0.50:
    print(f"⚠️ {categoria}: MAPE={mape_ensemble:.0%} > 50%. Predicciones NO guardadas.")
    continue
```
Esto evitaría que PERDIDAS y PRECIO_BOLSA contaminen el chatbot con datos inútiles.

### P5: Reconstruir PERDIDAS con datos correctos [Prioridad ALTA]

Investigar la query de `cargar_datos_metrica()` con `prefer_sistema=True` para PERDIDAS:
- Verificar cuántos días tienen entidad='Sistema' vs solo-Agentes
- Posiblemente usar SUM(valor_gwh) directo sin la lógica prefer_sistema
- Considerar excluir PERDIDAS de predicciones hasta validar la serie temporal base

### P6: Reducir ventana PRECIO_BOLSA [Prioridad MEDIA]

Actualmente usa `ventana_meses=8` (≈240 datos). Considerar:
- Reducir a 4-6 meses si hay alta volatilidad reciente
- Agregar cambio de régimen explícito (changepoint detection)
- Probar `seasonality_mode='additive'` vs `'multiplicative'` con cross-validation

### P7: Implementar cross-validation temporal [Prioridad MEDIA]

Reemplazar holdout simple de 30 días por expanding window cross-validation:
```python
from prophet.diagnostics import cross_validation, performance_metrics
cv = cross_validation(model, initial='730 days', period='30 days', horizon='90 days')
pm = performance_metrics(cv)
mape_cv = pm['mape'].mean()
```
Esto da estadísticos de error más robustos con 6 años de datos.

### P8: Unificar pipeline batch/API [Prioridad MEDIA]

Eliminar `predictions_service_extended.py` como generador live, o alinear sus parámetros con los scripts batch. Idealmente:
- Los scripts batch entrenan y guardan predicciones + modelo serializado
- La API lee SOLO de la tabla `predictions`  
- El endpoint `/train` invoca el mismo código que el batch

### P9: Agregar regresores externos [Prioridad BAJA]

Para mejorar DEMANDA y PRECIO_BOLSA:
- **Calendario:** festivos colombianos, día de la semana
- **Temperatura:** promedio nacional (correlación con demanda aire acondicionado)  
- **ENSO:** índice ONI (El Niño/La Niña → impacto hidrológico → precios)

```python
modelo.add_regressor('festivo')
modelo.add_regressor('dia_semana')
```

### P10: Tracking de experimentos [Prioridad BAJA]

Implementar MLflow o al menos log JSON por ejecución:
```json
{
  "run_date": "2026-02-15T02:00:00",
  "modelo": "ENSEMBLE_SECTOR_v1.0",
  "fuente": "PRECIO_BOLSA",
  "mape_prophet": 0.59,
  "mape_sarima": null,
  "mape_ensemble": 0.59,
  "pesos": {"prophet": 1.0},
  "n_datos_entrenamiento": 240,
  "hiperparametros": {...}
}
```

---

## 6. DIAGRAMA DE DEPENDENCIAS

```
                    ┌─────────────────────────┐
                    │   crontab (dom 02:00)    │
                    │ actualizar_predicciones  │
                    └────────┬────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼                             ▼
┌─────────────────────────┐  ┌──────────────────────────────┐
│ train_predictions_      │  │ train_predictions_sector_    │
│ postgres.py             │  │ energetico.py                │
│ (PredictorEnsemble)     │  │ (PredictorMetricaSectorial)  │
│ 5 fuentes generación    │  │ 9 métricas estratégicas      │
│ Prophet+SARIMA          │  │ Prophet+SARIMA (o solo-P)    │
│ Modelo: ENSEMBLE_v1.0   │  │ Modelo: ENSEMBLE_SECTOR_v1.0│
└────────┬────────────────┘  └────────┬─────────────────────┘
         │                            │
         ▼                            ▼
┌──────────────────────────────────────────┐
│        PostgreSQL: predictions           │
│  12 fuentes × 90 días = 1,080 filas     │
│  mape=NULL, rmse=NULL en todas          │
└──────────────────┬───────────────────────┘
                   │
         ┌─────────┼──────────┐
         ▼                    ▼
┌────────────────┐   ┌────────────────────┐
│ Orchestrator   │   │ API /predictions/  │
│ _handle_pred.  │   │ GET /{metric_id}   │
│ Lee de BD      │   │ Genera LIVE ⚠️     │
│ (confianza)    │   │ (forecast_metric)  │
└────────────────┘   └────────────────────┘
```

---

## 7. CONCLUSIÓN

El pipeline de predicciones tiene una arquitectura sólida (ensemble Prophet+SARIMA, validación holdout, cron automatizado) pero sufre de **3 bugs críticos** que comprometen la fiabilidad:

1. **Fuga de datos SARIMA** → pesos ensemble incorrectos
2. **MAPE no persistido** → imposible auditar calidad histórica  
3. **Confianza hardcodeada** → 5 fuentes siempre muestran 0.95

De las 12 fuentes, **solo 3** (GENE_TOTAL, EMBALSES, EMBALSES_PCT) producen predicciones confiables. **4 fuentes** (DEMANDA, APORTES_HIDRICOS, PRECIO_BOLSA, PERDIDAS) tienen calidad deficiente a muy mala. Las **5 fuentes de generación** tienen calidad indeterminada por el bug de confianza hardcodeada.

**Recomendación:** Implementar P1-P4 antes de la próxima ejecución del cron (próximo domingo), lo cual requiere ~2-3 horas de desarrollo. Luego P5-P7 en una segunda iteración.
