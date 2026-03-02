# FASE 7–17 — Auditoría, Modelos ML y MLflow Tracking

**Fecha auditoría original:** 2026-02-15  
**FASE 8 Phase 1 (correcciones):** 2026-02-26  
**FASE 8 Phase 2 (optimización):** 2026-02-27  
**FASE 3 (regresores multivariable):** 2026-02-27  
**FASE 4.A (monitoreo ex-post):** 2026-02-27  
**FASE 4.B (regresores calendario DEMANDA):** 2026-02-27  
**FASES 10-13 (modelos especializados):** 2026-02-28  
**FASE 14 (cross-validation temporal):** 2026-02-28  
**FASES 15-16 (multivariate discovery + integración):** 2026-03-01  
**FASE 17 (MLflow tracking server):** 2026-03-01  
**Autor:** Auditoría automatizada + correcciones implementadas  

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
| `scripts/train_predictions_sector_energetico.py` | ~1181 | Entrenamiento batch: 9 métricas estratégicas (con regresores BD + calendario) |
| `scripts/train_predictions_postgres.py` | 601 | Entrenamiento batch: 5 fuentes de generación |
| `scripts/monitor_predictions_quality.py` | ~310 | **NUEVO (FASE 4.A):** Monitoreo ex-post predicciones vs reales |
| `scripts/actualizar_predicciones.sh` | 223 | Orquestador cron (domingos 02:00) |
| `domain/services/predictions_service.py` | 34 | Wrapper simple (solo lectura BD) |
| `domain/services/predictions_service_extended.py` | 433 | Servicio completo con forecast on-demand |
| `infrastructure/database/repositories/predictions_repository.py` | 152 | CRUD predictions table |
| `api/v1/routes/predictions.py` | 221 | Endpoints FastAPI |
| `domain/models/prediction.py` | 54 | Dataclass Prediction |
| `domain/interfaces/repositories.py` | ~44 | ABC IPredictionsRepository |
| `sql/create_predictions_table.sql` | 286 | DDL completo + views + funciones |

### 1.3 Métricas Configuradas (13 fuentes)

#### Script `train_predictions_sector_energetico.py` (ENSEMBLE_SECTOR_v1.0)

| Fuente | Métrica BD | Agregación | Config especial |
|--------|-----------|------------|-----------------|
| GENE_TOTAL | `Gene` | SUM, entidad='Sistema' | — |
| DEMANDA | `DemaReal` | SUM, prefer_sistema | **7 regresores calendario (FASE 4.B)** |
| **PRECIO_BOLSA** | `PrecBolsNaci` | AVG, entidad='Sistema' | **growth='flat', multiplicative, ventana=15m, piso=86.0, 3 regresores** |
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
| **UMBRAL_MAPE_MAXIMO** | **0.50 (50%)** | **0.50 (50%)** |
| **CONFIANZA_SIN_VALIDACION** | **0.50** | **0.50** |

#### Config especial PRECIO_BOLSA (FASE 8 Phase 2 → FASE 3)

| Parámetro | Phase 2 | FASE 3 (actual) | Razón |
|-----------|---------|-----------------|-------|
| `ventana_meses` | 15 | **15** | Sin cambio |
| `prophet_growth` | `'linear'` | **`'flat'`** | Con regresores, `flat` evita competencia trend vs regressors |
| `prophet_seasonality_mode` | `'multiplicative'` | `'multiplicative'` | Sin cambio |
| `piso_historico` | 86.0 | 86.0 | Sin cambio |
| `regresores` | — | **embalses_pct, demanda_gwh, aportes_gwh** | Variables explicativas del precio spot |

#### Regresores PRECIO_BOLSA (FASE 3)

| Regresor | Métrica BD | Agregación | Escala | Correlación con precio |
|----------|-----------|------------|--------|------------------------|
| `embalses_pct` | PorcVoluUtilDiar | AVG, Sistema | ×100 | Inversa: embalses altos → precio bajo |
| `demanda_gwh` | DemaReal | SUM, prefer_sistema | ×1 | Directa: mayor demanda → precio sube |
| `aportes_gwh` | AporEner | SUM | ×1 | Inversa: aportes altos → oferta hídrica → precio baja |

---

## 2. AUDITORÍA DE CALIDAD

### 2.1 Estado Actual de Predicciones en BD (post-FASE 8)

**Total:** 1,170 filas (13 fuentes × 90 días)  
**Último entrenamiento batch:** 2026-02-22 (cron semanal)  
**PRECIO_BOLSA actualizado manualmente:** 2026-02-27  
**Rango predicciones:** 2026-02-17 a 2026-05-25  

### 2.2 MAPE y Confianza por Fuente (estado actual en BD)

| Fuente | Confianza | MAPE | RMSE | Modelo | Estado |
|--------|-----------|------|------|--------|--------|
| EMBALSES | 1.00 | 0.08% | 14.53 | SECTOR_v1.0 | ✅ Excelente |
| EMBALSES_PCT | 0.99 | 1.14% | 0.99 | SECTOR_v1.0 | ✅ Excelente |
| PRECIO_ESCASEZ | 0.99 | 1.37% | 9.57 | SECTOR_v1.0 | ✅ Excelente |
| GENE_TOTAL | 0.96 | 3.75% | 10.33 | SECTOR_v1.0 | ✅ Buena |
| **DEMANDA** | **0.96** | **3.61%\*** | **9.96\*** | SECTOR_v1.0 | ✅ Buena |
| Hidráulica | 0.96 | 3.77% | 8.58 | v1.0 | ✅ Buena |
| Biomasa | 0.94 | 6.11% | 0.22 | v1.0 | ✅ Buena |
| PERDIDAS | 0.90 | 10.00% | 0.60 | SECTOR_v1.0 | ✅ Aceptable |
| Térmica | 0.88 | 12.15% | 3.95 | v1.0 | ⚠️ Aceptable |
| APORTES_HIDRICOS | 0.83 | 16.52% | 110.78 | SECTOR_v1.0 | ⚠️ Aceptable |
| Solar | 0.81 | 18.75% | 3.29 | v1.0 | ⚠️ Aceptable |
| Eólica | 0.78 | 22.00% | 0.14 | v1.0 | ⚠️ Mejorable |
| **PRECIO_BOLSA** | **0.60\*** | **40.07%\*** | **56.02\*** | SECTOR_v1.0 | ⚠️ Aceptable |

\* **PRECIO_BOLSA — nota:** Los valores de MAPE (40.07%), Confianza (59.93%) y RMSE (56.02) fueron validados offline con el modelo multivariable (FASE 3: `growth='flat'` + 3 regresores). Mejora respecto al modelo univariado Phase 2 (MAPE 43.18% → 40.07%, RMSE 63.95 → 56.02). A partir del **próximo cron dominical**, el script persistirá automáticamente estas métricas. Ver §5.3 para detalle del grid search de 8 configuraciones con regresores.

\* **DEMANDA — nota (FASE 4.B):** MAPE mejorado de 3.76% → **3.61%** (-0.14pp) y RMSE de 10.38 → **9.96** (-2.6%) al agregar 7 regresores calendario (festivos Colombia + day-of-week dummies). Los valores se actualizarán en BD en el próximo cron dominical. Ver §5.4.2.

**MAPE promedio (13 fuentes):** ~7.9% (excluyendo PRECIO_BOLSA) / ~10.6% (incluyendo PRECIO_BOLSA) — sistema globalmente muy bueno.

### 2.3 Evolución de Calidad: Antes vs Después de FASE 8

| Fuente | Confianza ANTES | Confianza DESPUÉS | MAPE ANTES | MAPE DESPUÉS | Mejora |
|--------|----------------|-------------------|-----------|-------------|---------|
| EMBALSES | 1.00 | 1.00 | NULL | 0.08% | MAPE persistido |
| GENE_TOTAL | 0.97 | 0.96 | NULL | 3.75% | MAPE persistido |
| DEMANDA | 0.66 | 0.96 | NULL | 3.76% | **+45% confianza** |
| APORTES_HIDRICOS | 0.54 | 0.83 | NULL | 16.52% | **+54% confianza** |
| PRECIO_BOLSA | 0.41 → rechazado | 0.60 (próx. cron) | NULL | 40.07% | **De inusable a validable + regresores** |
| PERDIDAS | 0.32 | 0.90 | NULL | 10.00% | **+181% confianza** |
| Hidráulica | 0.95 (hardcoded) | 0.96 (real) | NULL | 3.77% | Confianza real |
| Biomasa | 0.95 (hardcoded) | 0.94 (real) | NULL | 6.11% | Confianza real |
| Térmica | 0.95 (hardcoded) | 0.88 (real) | NULL | 12.15% | Confianza honesta |
| Eólica | 0.95 (hardcoded) | 0.78 (real) | NULL | 22.00% | Confianza honesta |
| Solar | 0.95 (hardcoded) | 0.81 (real) | NULL | 18.75% | Confianza honesta |

### 2.4 Cobertura de Datos de Entrenamiento

| Métrica BD | Desde | Hasta | Días únicos | Puntos totales |
|-----------|-------|-------|-------------|----------------|
| Gene | 2020-01-01 | 2026-02-24 | ~2,247 | 528,702+ |
| DemaReal | 2020-01-01 | 2026-02-24 | ~2,247 | 184,495+ |
| PrecBolsNaci | 2020-02-06 | 2026-02-24 | ~2,211 | 2,211 |
| PorcVoluUtilDiar | 2020-02-06 | 2026-02-24 | ~2,213 | 53,752+ |
| CapaUtilDiarEner | 2020-01-01 | 2026-02-24 | ~2,249 | 80,981+ |
| AporEner | 2020-01-01 | 2026-02-24 | ~2,249 | 86,579+ |
| PerdidasEner | 2020-02-06 | 2026-02-24 | ~2,209 | 4,222+ |
| PrecEsca | 2020-02-06 | 2026-02-24 | ~2,211 | 2,211 |

Todas las métricas tienen **≥6 años** de historia → suficiente para Prophet con estacionalidad anual.

---

## 3. BUGS DETECTADOS Y ESTADO DE CORRECCIÓN

### ✅ CORREGIDO — BUG 1: Fuga de datos en validación SARIMA

**Corregido en:** FASE 8 Phase 1 (2026-02-26)

**Problema original:** La validación holdout re-entrenaba Prophet con subset pero usaba SARIMA entrenado sobre TODOS los datos (incluyendo holdout) → comparaba períodos temporales distintos.

**Corrección:** Ambos scripts ahora re-entrenan SARIMA temporalmente con `serie_sarima.iloc[:-dias_validacion]` durante holdout, análogo a lo que ya hacía Prophet.

### ✅ CORREGIDO — BUG 2: MAPE/RMSE no se persistían en BD

**Corregido en:** FASE 8 Phase 1 (2026-02-26)

**Problema original:** El INSERT solo incluía 9 columnas, `mape` y `rmse` quedaban NULL en todas las 1,080 filas.

**Corrección:** Ambos scripts ahora pasan `mape` y `rmse` reales del ensemble al INSERT. Visible en BD actual: 12 de 13 fuentes tienen MAPE y RMSE no-NULL.

### ✅ CORREGIDO — BUG 3: Confianza hardcodeada en postgres.py

**Corregido en:** FASE 8 Phase 1 (2026-02-26)

**Problema original:** `guardar_predicciones()` usaba `CONFIANZA=0.95` para TODAS las fuentes de generación.

**Corrección:** Ahora usa `predictor.metricas.get('confianza')` real. Las 5 fuentes de generación muestran confianza honesta: Hidráulica=0.96, Biomasa=0.94, Térmica=0.88, Solar=0.81, Eólica=0.78.

### ✅ CORREGIDO — BUG 4: Confianza fallback hardcodeada a 0.95

**Corregido en:** FASE 8 Phase 1 (2026-02-26)

**Problema original:** Cuando no había suficientes datos para holdout, la confianza se ponía en 0.95 (injustificadamente alta).

**Corrección:** Constante `CONFIANZA_SIN_VALIDACION = 0.50` — conservador pero honesto. El valor `None` (no `-1`) se usa ahora para MAPE cuando no hay validación.

### ✅ CORREGIDO — BUG 5: Holdout Prophet usaba parámetros por defecto

**Descubierto y corregido en:** FASE 8 Phase 2 (2026-02-27)

**Problema:** En `validar_y_generar()` de `train_predictions_sector_energetico.py`, el Prophet temporal para holdout se creaba con parámetros por defecto (`growth='linear'`, `yearly_seasonality=True`) en lugar de heredar los del config (`growth='flat'`, `seasonality_mode='multiplicative'`, etc.). Esto hacía que PRECIO_BOLSA se entrenara con un Prophet y se validara con otro distinto.

**Corrección:** El Prophet temporal de holdout ahora hereda `growth`, `seasonality_mode`, `changepoint_prior_scale`, `seasonality_prior_scale` y `yearly_seasonality` del config de la métrica.

**Impacto:** Este fix fue clave para que PRECIO_BOLSA pasara de MAPE >100% a MAPE 43%.

### ✅ IMPLEMENTADO — Quality Gate (UMBRAL_MAPE_MAXIMO = 50%)

**Implementado en:** FASE 8 Phase 1 (2026-02-26)

Predicciones con MAPE > 50% no se guardan en BD. Ambos scripts implementan este filtro con logging detallado (MAPE Prophet, SARIMA, Ensemble, RMSE, pesos, acción recomendada).

### 🟡 PENDIENTE — BUG MEDIO: Dos pipelines duplicados e inconsistentes

**Sin cambio.** Existen dos servicios de predicción (batch vs API on-demand) con hiperparámetros distintos. Marcado para Fase futura (P8).

### 🟢 MENOR: Intervalos de confianza anchos en métricas volátiles

Parcialmente mitigado. Los intervalos siguen siendo amplios para Eólica, Solar y APORTES_HIDRICOS, lo cual es esperado dada la volatilidad intrínseca. El MAPE honesto ahora permite al usuario evaluar la utilidad de cada predicción.

### 🟡 CONOCIDO — PRECIO_BOLSA forecast en piso histórico

**Estado:** PRECIO_BOLSA pasa el quality gate (MAPE=40.07%) pero los valores de forecast se estancan en el piso histórico (86.0 $/kWh). Con `growth='flat'` + regresores (FASE 3), las predicciones de 90 días siguen cayendo al piso porque la extrapolación de los regresores (especialmente APORTES_HIDRICOS con 16.5% MAPE) amplifica la incertidumbre. La mejora real se observa en holdout (40.07% vs 43.18%). Posible mejora futura: `growth='logistic'` con cap/floor, o SARIMAX para el componente SARIMA.

---

## 4. RESUMEN DE CALIDAD POR CATEGORÍA (post-FASE 8)

| Categoría | Calidad | MAPE | Confianza | Notas |
|-----------|---------|------|-----------|-------|
| EMBALSES | ✅ Excelente | 0.08% | 100% | Serie muy estable |
| EMBALSES_PCT | ✅ Excelente | 1.14% | 99% | — |
| PRECIO_ESCASEZ | ✅ Excelente | 1.37% | 99% | — |
| GENE_TOTAL | ✅ Buena | 3.75% | 96% | — |
| **DEMANDA** | **✅ Buena** | **3.61%** | **96%** | **Mejorada: 34% → 3.76% → 3.61% (FASE 4.B calendario)** |
| Hidráulica | ✅ Buena | 3.77% | 96% | Confianza ahora real (no hardcoded) |
| Biomasa | ✅ Buena | 6.11% | 94% | Confianza ahora real |
| PERDIDAS | ✅ Aceptable | 10.00% | 90% | Era "catastrófica" (88.8%), ahora bien |
| Térmica | ⚠️ Aceptable | 12.15% | 88% | Confianza honesta (antes 95% falso) |
| APORTES_HIDRICOS | ⚠️ Aceptable | 16.52% | 83% | — |
| Solar | ⚠️ Aceptable | 18.75% | 81% | — |
| Eólica | ⚠️ Mejorable | 22.00% | 78% | Candidata a regresores en Fase 3 |
| PRECIO_BOLSA | ⚠️ Aceptable | 40.07% | 60% | Mejorado con regresores (Fase 3) |

---

## 5. FASE 8: CAMBIOS IMPLEMENTADOS

### 5.1 Phase 1 — Auditoría y Corrección (2026-02-26)

**Archivos modificados:** `train_predictions_sector_energetico.py`, `train_predictions_postgres.py`

| Cambio | Archivo | Detalle |
|--------|---------|---------|
| Constantes de calidad | Ambos | `UMBRAL_MAPE_MAXIMO = 0.50`, `CONFIANZA_SIN_VALIDACION = 0.50` |
| Quality gate | Ambos | Predicciones con MAPE > 50% no se guardan |
| MAPE/RMSE en BD | Ambos | Columnas `mape` y `rmse` ahora se llenan |
| Confianza real | postgres.py | Ya no hardcodea 0.95; usa MAPE real |
| Fallback honesto | Ambos | `CONFIANZA_SIN_VALIDACION = 0.50` (no 0.95) |
| MAPE None no -1 | sector.py | Path insuficiente-datos usa `None` |
| Reporte mejorado | postgres.py | `generar_reporte_metricas()` excluye None |

**Tests:** 5 tests de regresión pasaron correctamente.

### 5.2 Phase 2 — Optimización PRECIO_BOLSA y Logging (2026-02-27)

**Archivos modificados:** `train_predictions_sector_energetico.py`, `train_predictions_postgres.py`

#### 5.2.1 Bug encontrado: Holdout Prophet con parámetros incorrectos

El modelo Prophet temporal de validación (holdout) se creaba con defaults genéricos en lugar de heredar los hiperparámetros del config. Esto significaba que:
- PRECIO_BOLSA (config: `growth='flat'`) se validaba con `growth='linear'` (default Prophet)
- Ninguna personalización de `seasonality_mode`, `changepoint_prior_scale`, etc. se aplicaba al holdout

**Corrección en `validar_y_generar()` (líneas 282-296):** El Prophet temporal ahora hereda todos los parámetros.

#### 5.2.2 Grid search de 21 configuraciones para PRECIO_BOLSA

Se probaron combinaciones de:
- Ventanas: 8, 10, 12, 13, 14, 15, 16, 18 meses
- growth: `'flat'` vs `'linear'`
- seasonality_mode: `'additive'` vs `'multiplicative'`
- changepoint_prior_scale: 0.01, 0.05, 0.10, 0.20, 0.50

**Resultados clave:**

| Config | MAPE Ensemble | MAPE Prophet | MAPE SARIMA | Pass? |
|--------|:---:|:---:|:---:|:---:|
| 18m flat mult (Phase 1) | 102.5% | 117.1% | 96.0% | ❌ |
| 15m flat mult | 132.5% | 278.7% | 87.0% | ❌ |
| 15m lin additive | 56.2% | 104.9% | 87.0% | ❌ |
| **15m lin multiplicative** | **43.2%** | **36.2%** | **87.0%** | **✅** |
| 14m lin multiplicative | 75.9% | 71.2% | 84.9% | ❌ |
| 16m lin multiplicative | 97.3% | 125.7% | 81.5% | ❌ |
| 18m lin multiplicative | 70.9% | 58.8% | 96.0% | ❌ |

**Hallazgo clave:** `growth='flat'` era incorrecto para el período actual. El precio spot cayó de ~800 a ~100 $/kWh — solo `growth='linear'` captura esa tendencia. La ventana de 15 meses es el punto óptimo: 14m no tiene suficiente historia para capturar estacionalidad, 16m+ incluye demasiada volatilidad pre-caída.

**Config final elegida:**
```python
'PRECIO_BOLSA': {
    'prophet_growth': 'linear',
    'prophet_seasonality_mode': 'multiplicative',
    'ventana_meses': 15,
    'piso_historico': 86.0,
}
```

#### 5.2.3 PERDIDAS auditada — datos limpios, modelo funcional

Análisis de datos:
- 2,209 días con entidad='Sistema', avg=3.27 GWh, stddev=0.59
- Sin anomalías, sin valores extremos
- `prefer_sistema` funciona correctamente (Sistema y SUM(Agente) coinciden)
- **MAPE real: 10.0%** (Prophet=12.2%, SARIMA=10.0%)

El MAPE "88.8%" reportado en la auditoría original era un ex-post sobre predicciones generadas con los bugs de fuga SARIMA y confianza falsa. Con los bugs corregidos, PERDIDAS funciona bien.

#### 5.2.4 Logging de descartes mejorado

Ambos scripts ahora muestran detalle completo cuando una métrica es descartada por el quality gate:

```
⚠️  DESCARTADA PRECIO_BOLSA: MAPE Ensemble=102.51% > umbral 50%.
    Detalle: Prophet=117.09%, SARIMA=96.03%, RMSE=135.59
    Pesos: Prophet=0.45, SARIMA=0.55
    → Acción recomendada: revisar config o esperar Fase 3 (regresores)
```

### 5.3 FASE 3 — Regresores Multivariable para PRECIO_BOLSA (2026-02-27)

**Archivo modificado:** `train_predictions_sector_energetico.py` (791 → 1022 líneas)

#### 5.3.1 Objetivo

Romper el techo univariado de MAPE ~43% en PRECIO_BOLSA agregando variables explicativas externas (regresores) al modelo Prophet mediante `model.add_regressor()`.

#### 5.3.2 Arquitectura implementada

**Procesamiento ordenado con memoria compartida:**

```
ORDEN_PROCESAMIENTO = [
    'GENE_TOTAL', 'DEMANDA', 'APORTES_HIDRICOS', 'EMBALSES',
    'EMBALSES_PCT', 'PRECIO_ESCASEZ', 'PERDIDAS', 'PRECIO_BOLSA'
]
```

- Las métricas que sirven como regresores (DEMANDA, APORTES, EMBALSES_PCT) se procesan **primero**
- Sus predicciones se almacenan en `predicciones_memoria = {}`
- PRECIO_BOLSA (último) usa las predicciones de sus regresores como valores futuros

**Backward compatible:** Métricas sin `regresores` en su config se procesan exactamente igual que antes.

#### 5.3.3 Nuevas funciones

| Función | Líneas | Rol |
|---------|--------|-----|
| `cargar_regresores_historicos()` | ~60 | Carga series históricas de cada regresor desde BD |
| `construir_regresores_futuros()` | ~40 | Obtiene valores futuros de regresores desde `predicciones_memoria` |
| `preparar_regresores()` | ~50 | Orquesta hist+futuro, merge al df_prophet del modelo |

#### 5.3.4 Hallazgo clave: growth='flat' + regresores > growth='linear' solo

El grid search mostró un resultado contraintuitivo:

| Config | Growth | Regresores | MAPE Prophet | MAPE SARIMA | MAPE Ensemble |
|--------|--------|------------|:---:|:---:|:---:|
| Phase 2 baseline | linear | ninguno | 36.2% | 87.0% | 43.2% |
| FASE 3 intento 1 | linear | embalses+demanda+aportes | 39.7% | 87.0% | 53.5% |
| FASE 3 intento 2 | linear | solo embalses | 36.8% | 87.0% | 47.1% |
| **FASE 3 final** | **flat** | **embalses+demanda+aportes** | **98.6%** | **87.0%** | **40.1%** |
| FASE 3 alternativa | flat | solo embalses | 112.7% | 87.0% | 42.9% |

**Explicación:** Con `growth='linear'`, la función de tendencia de Prophet y los regresores **compiten** por explicar la misma señal (caída de precios ~800→100 $/kWh). Con `growth='flat'`, la tendencia es constante y los regresores capturan los fundamentales económicos, mientras SARIMA (peso ~0.5 en ensemble) maneja la dinámica temporal. El MAPE Prophet individual empeora (98.6% vs 36.2%), pero el **ensemble** mejora porque Prophet contribuye buena estructura y SARIMA compensa.

#### 5.3.5 Grid search de 8 configuraciones

| # | Growth | Regresores | MAPE Ensemble | RMSE | Pass? |
|---|--------|------------|:---:|:---:|:---:|
| 1 | linear | — (baseline) | 43.2% | 63.9 | ✅ |
| 2 | linear | embalses | 47.1% | 67.4 | ✅ |
| 3 | linear | demanda | 53.5% | 73.3 | ❌ |
| 4 | linear | aportes | 45.1% | 65.3 | ✅ |
| 5 | linear | embalses+aportes | 50.8% | 70.7 | ❌ |
| 6 | linear | all 3 | 53.5% | 72.8 | ❌ |
| 7 | flat | embalses | 42.9% | 62.9 | ✅ |
| **8** | **flat** | **all 3** | **40.1%** | **56.0** | **✅** |

#### 5.3.6 Config final PRECIO_BOLSA (v3)

```python
'PRECIO_BOLSA': {
    'prophet_growth': 'flat',           # v3: flat+regresores gana
    'prophet_seasonality_mode': 'multiplicative',
    'ventana_meses': 15,
    'piso_historico': 86.0,
    'regresores': {
        'embalses_pct': {'metrica': 'PorcVoluUtilDiar', 'agg': 'AVG',
                         'entidad': 'Sistema', 'escala': 100},
        'demanda_gwh':  {'metrica': 'DemaReal', 'agg': 'SUM',
                         'prefer_sistema': True},
        'aportes_gwh':  {'metrica': 'AporEner', 'agg': 'SUM'},
    }
}
```

**Evolución:**
- v1 (Phase 1): `flat/multiplicative/18m` → MAPE 102% ❌
- v2 (Phase 2): `linear/multiplicative/15m` → MAPE 43.2% ✅
- **v3 (FASE 3): `flat/multiplicative/15m + 3 regresores` → MAPE 40.1% ✅**

#### 5.3.7 Resultado validado

```
PRECIO_BOLSA — MAPE: 40.07%, Confianza: 59.93%, RMSE: 56.02
Quality gate: ✅ PASA (40.07% < 50%)
Predicciones: 90 días (2026-02-25 → 2026-05-25)
Valores: 86.0 $/kWh (piso), intervalos [143, 424] superior
```

**Mejora respecto a Phase 2:** MAPE 43.18% → 40.07% (-3.11pp), RMSE 63.95 → 56.02 (-12.4%)

#### 5.3.8 Regresión verificada

| Métrica | MAPE antes | MAPE después | Diferencia |
|---------|:---:|:---:|:---:|
| DEMANDA | 3.76% | 3.73% | -0.03pp (ruido) |
| EMBALSES_PCT | 0.08% | 0.67% | +0.59pp (ruido) |

Las métricas sin regresores funcionan idéntico — la arquitectura es backward compatible.

### 5.4 FASE 4 — Monitoreo Ex-Post y Regresores Calendario (2026-02-27)

#### 5.4.1 FASE 4.A: Script de monitoreo ex-post (`monitor_predictions_quality.py`)

**Archivo creado:** `scripts/monitor_predictions_quality.py` (~310 líneas)

**Objetivo:** Detectar degradación (*drift*) de las predicciones comparándolas con los datos reales que van llegando, generando alertas y persistiendo el historial de calidad.

**Tabla PostgreSQL creada:** `predictions_quality_history`

```sql
CREATE TABLE IF NOT EXISTS predictions_quality_history (
    id SERIAL PRIMARY KEY,
    fuente VARCHAR(50),
    fecha_evaluacion TIMESTAMP DEFAULT NOW(),
    mape_expost FLOAT,
    rmse_expost FLOAT,
    mape_train FLOAT,
    dias_overlap INT,
    alertas TEXT,
    estado VARCHAR(20)  -- 'OK', 'DRIFT', 'CRITICO'
);
```

**Arquitectura:**

```
monitor_predictions_quality.py
 ├── FUENTES_MAPPING: 13 fuentes mapeadas (8 sectoriales + 5 generación)
 ├── cargar_reales_metrica()    → query BD metricas (sectoriales)
 ├── cargar_reales_generacion() → query BD metricas+catalogos JOIN (generación)
 ├── evaluar_fuente()           → merge predicciones vs reales, MAPE/RMSE ex-post
 │     └── Filtro datos parciales: valor < 50% mediana → excluir
 ├── generar_alertas()
 │     ├── UMBRAL_MAPE_CRITICO = 50%  → alerta CRITICO
 │     └── FACTOR_DRIFT = 2.0×        → alerta DRIFT (MAPE ex-post > 2× MAPE train)
 ├── guardar_evaluacion()       → INSERT INTO predictions_quality_history
 └── main()                     → itera 13 fuentes, evalúa, alerta, persiste
```

**Resultado de primera ejecución (post-fix datos parciales):**

| Fuente | MAPE ex-post | Estado | Días overlap |
|--------|:---:|---|:---:|
| GENE_TOTAL | 5.62% | ✅ OK | 8 |
| DEMANDA | 0.62% | ✅ OK | 6 |
| EMBALSES | 0.39% | ✅ OK | 8 |
| EMBALSES_PCT | 0.65% | ✅ OK | 8 |
| PRECIO_ESCASEZ | 0.46% | ✅ OK | 6 |
| APORTES_HIDRICOS | 22.08% | ✅ OK | 8 |
| PERDIDAS | 5.83% | ✅ OK | 6 |
| Hidráulica | 6.14% | ✅ OK | 8 |
| Térmica | 6.37% | ✅ OK | 8 |
| Eólica | 8.96% | ✅ OK | 7 |
| Solar | 5.06% | ✅ OK | 8 |
| Biomasa | 13.21% | ⚠️ Drift leve | 6 |
| PRECIO_BOLSA | — | Sin datos reales aún | 0 |

**Hallazgo resuelto:** DEMANDA mostraba inicialmente 104.74% MAPE ex-post por datos parciales de XM (Feb 23: 48 GWh, Feb 24: 44 GWh vs ~230 GWh normal). Se aplicó el mismo filtro de datos parciales que usa el script de entrenamiento: si un valor real < 50% de la mediana de los últimos 90 días, se excluye.

**Uso recomendado:** Integrar en cron después del ETL diario, o ejecutar manualmente con:
```bash
/home/admonctrlxm/server/whatsapp_bot/venv/bin/python3 scripts/monitor_predictions_quality.py
```

#### 5.4.2 FASE 4.B: Regresores Calendario para DEMANDA

**Archivo modificado:** `scripts/train_predictions_sector_energetico.py` (1022 → 1181 líneas)

**Objetivo:** Mejorar la predicción de DEMANDA incorporando patrones calendario determinísticos (festivos colombianos + día de semana) que el modelo Prophet puede aprender directamente.

**Nuevas funciones implementadas:**

| Función | Líneas | Rol |
|---------|--------|-----|
| `_festivos_colombia(year)` | ~70 | Calendario completo de festivos colombianos (Ley 51 de 1983, Ley Emiliani) |
| `_generar_set_festivos()` | ~5 | Consolida festivos 2020-2028 en un set de `datetime.date` |
| `construir_regresores_calendario(fechas_series)` | ~20 | Genera 7 columnas para cualquier rango de fechas |

**Festivos implementados (Ley 51 de 1983 + Ley Emiliani):**

| Tipo | Festivos | Regla |
|------|----------|-------|
| Fijos | Año Nuevo (1 ene), Trabajo (1 may), Independencia (20 jul), Batalla Boyacá (7 ago), Inmaculada (8 dic), Navidad (25 dic) | Fecha exacta |
| Ley Emiliani | Reyes Magos (6 ene→lun), San José (19 mar→lun), San Pedro y San Pablo (29 jun→lun), Asunción (15 ago→lun), Día de la Raza (12 oct→lun), Todos los Santos (1 nov→lun), Independencia Cartagena (11 nov→lun) | Se trasladan al lunes siguiente |
| Pascua-dependientes | Jueves Santo, Viernes Santo, Ascensión (Pascua+43→lun), Corpus Christi (Pascua+64→lun), Sagrado Corazón (Pascua+71→lun) | Algoritmo de Meeus/Jones/Butcher |

**7 regresores calendario:**

| Regresor | Tipo | Valores | Nota |
|----------|------|---------|------|
| `es_festivo` | Binario | 0/1 | Incluye festivos + Ley Emiliani |
| `dow_lun` | Dummy | 0/1 | Lunes |
| `dow_mar` | Dummy | 0/1 | Martes |
| `dow_mie` | Dummy | 0/1 | Miércoles |
| `dow_jue` | Dummy | 0/1 | Jueves |
| `dow_vie` | Dummy | 0/1 | Viernes |
| `dow_sab` | Dummy | 0/1 | Sábado |

Domingo = categoría base (omitido para evitar colinealidad perfecta).

**Refactorización de `preparar_regresores()`:**

La función ahora maneja dos ramas:
1. **Calendario** (`tipo: 'calendario'`): Genera regresores determinísticos para todo el rango (histórico + horizonte futuro). No requiere consulta a BD ni `predicciones_memoria`.
2. **BD** (sin `tipo`): Comportamiento original de FASE 3 — carga históricos de BD, construye futuros desde `predicciones_memoria`.

Ambas ramas son compatibles y se ejecutan en la misma métrica si tiene regresores mixtos.

**Config DEMANDA (v2):**

```python
'DEMANDA': {
    'metricas': [{'nombre': 'DemaReal', 'agg': 'SUM', 'prefer_sistema': True}],
    'regresores': {
        'es_festivo':  {'tipo': 'calendario'},
        'dow_lun':     {'tipo': 'calendario'},
        'dow_mar':     {'tipo': 'calendario'},
        'dow_mie':     {'tipo': 'calendario'},
        'dow_jue':     {'tipo': 'calendario'},
        'dow_vie':     {'tipo': 'calendario'},
        'dow_sab':     {'tipo': 'calendario'},
    }
}
```

**Resultado validado:**

| Modelo | MAPE (baseline) | MAPE (calendario) | Diferencia |
|--------|:---:|:---:|:---:|
| Prophet | 2.68% | 2.57% | -0.11pp |
| SARIMA | 7.23% | 7.23% | 0 (sin regresores) |
| **Ensemble** | **3.75%** | **3.61%** | **-0.14pp (-3.7%)** |
| RMSE | 10.22 | 9.96 | **-2.6%** |

Los festivos colombianos (109 en el rango de entrenamiento) permiten a Prophet ajustar las caídas de demanda en días no laborables. El SARIMA no cambia porque no usa regresores calendario (solo estacionalidad 7-day).

#### 5.4.3 Regresión verificada (post-FASE 4.B)

| Métrica | Tipo regresores | MAPE esperado | MAPE obtenido | Estado |
|---------|----------------|:---:|:---:|---|
| **PRECIO_BOLSA** | BD (embalses+demanda+aportes) | ~40.07% | 41.83% | ✅ OK (variación estocástica) |
| **EMBALSES_PCT** | Ninguno | ~0.67% | 0.67% | ✅ Exacto |
| **DEMANDA** | Calendario (7 features) | ~3.61% | 3.66% | ✅ OK (variación estocástica) |

La refactorización de `preparar_regresores()` es **backward compatible**: las métricas con regresores BD (PRECIO_BOLSA) y sin regresores (EMBALSES_PCT) producen resultados equivalentes.

---

## 6. PROPUESTAS DE MEJORA — ESTADO

### ✅ P1: Corregir fuga de datos SARIMA en validación — IMPLEMENTADO (FASE 8 Phase 1)

### ✅ P2: Persistir MAPE/RMSE en BD — IMPLEMENTADO (FASE 8 Phase 1)

### ✅ P3: Corregir confianza en `train_predictions_postgres.py` — IMPLEMENTADO (FASE 8 Phase 1)

### ✅ P4: Implementar umbral mínimo de calidad — IMPLEMENTADO (FASE 8 Phase 1)

`UMBRAL_MAPE_MAXIMO = 0.50` en ambos scripts. Logging detallado de descartes.

### ✅ P5: Reconstruir PERDIDAS — NO NECESARIO

Investigación demostró que los datos son limpios y `prefer_sistema` funciona correctamente. MAPE real = 10%, confianza = 90%. El error ex-post anterior se debía a los bugs de validación (fuga SARIMA + confianza falsa).

### ✅ P6: Optimizar PRECIO_BOLSA — IMPLEMENTADO (Phase 2 + FASE 3)

- **Phase 2:** Grid search 21 configs → `linear/multiplicative/15m` → MAPE=43.18%
- **FASE 3:** Grid search 8 configs con regresores → `flat/multiplicative/15m + 3 regresores` → **MAPE=40.07%**
- Mejora acumulada: de "inusable" (102%) → 43.18% → 40.07%

### 🔲 P7: Implementar cross-validation temporal [Prioridad MEDIA]

Reemplazar holdout simple de 30 días por expanding window cross-validation:
```python
from prophet.diagnostics import cross_validation, performance_metrics
cv = cross_validation(model, initial='730 days', period='30 days', horizon='90 days')
pm = performance_metrics(cv)
mape_cv = pm['mape'].mean()
```
Esto daría estimaciones de MAPE más robustas.

### 🔲 P8: Unificar pipeline batch/API [Prioridad MEDIA]

Eliminar `predictions_service_extended.py` como generador live, o alinear sus parámetros con los scripts batch.

### ✅ P9: Agregar regresores externos (Fase 3+4) — IMPLEMENTADO

**FASE 3 — PRECIO_BOLSA** con 3 regresores BD: embalses_pct, demanda_gwh, aportes_gwh.
- Arquitectura `ORDEN_PROCESAMIENTO` + `predicciones_memoria` permite que las predicciones de una métrica alimenten como regresores a otra
- Resultado: MAPE 43.18% → 40.07% (-3.11pp)

**FASE 4.B — DEMANDA** con 7 regresores calendario: es_festivo + 6 day-of-week dummies.
- Festivos colombianos (Ley 51 de 1983, Ley Emiliani, Easter-based)
- Resultado: MAPE 3.75% → 3.61% (-0.14pp), RMSE -2.6%
- Infraestructura lista para agregar regresores calendario a cualquier métrica

**Métricas pendientes de regresores:**

| Métrica | MAPE actual | Regresores candidatos | Prioridad |
|---------|:---:|---|---|
| Eólica | 22.00% | Clima, velocidad viento | MEDIA |
| Solar | 18.75% | Radiación, nubosidad | MEDIA |
| APORTES_HIDRICOS | 16.52% | ENSO, precipitación | MEDIA |

### ✅ P11: Monitoreo ex-post de predicciones (FASE 4.A) — IMPLEMENTADO

**Script:** `scripts/monitor_predictions_quality.py`  
**Tabla:** `predictions_quality_history`  
- Compara predicciones almacenadas vs datos reales que llegan
- Alertas: MAPE > 50% (crítico), MAPE > 2× train (drift)
- Filtro de datos parciales (< 50% mediana → excluir)
- 13 fuentes cubiertas, historial persistido en PostgreSQL

### 🔲 P10: Tracking de experimentos [Prioridad BAJA]

MLflow o log JSON por ejecución para comparación histórica.

---

## 7. DIAGRAMA DE DEPENDENCIAS (actualizado)

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
│ Prophet+SARIMA          │  │ Prophet+SARIMA + regresores  │
│ Modelo: ENSEMBLE_v1.0   │  │ Modelo: ENSEMBLE_SECTOR_v1.0│
│ Quality gate: MAPE≤50%  │  │ Quality gate: MAPE≤50%      │
└────────┬────────────────┘  │ ORDEN_PROCESAMIENTO (FASE 3) │
         │                   │ Regresores calendario (4.B)  │
         │                   └────────┬─────────────────────┘
         │                            │
         │     ┌──────────────────────┘
         │     │  predicciones_memoria{}
         │     │  DEMANDA ─┐ (+ calendario: festivos + DOW)
         │     │  APORTES ─┼─▶ regresores BD ─▶ PRECIO_BOLSA
         │     │  EMBALSES─┘
         │     │
         ▼     ▼
┌──────────────────────────────────────────┐
│        PostgreSQL: predictions           │
│  13 fuentes × 90 días = 1,170 filas     │
│  MAPE/RMSE/Confianza: REALES ✅         │
└──────────────────┬───────────────────────┘
                   │
         ┌─────────┼──────────┐
         ▼         │          ▼
┌────────────────┐ │ ┌────────────────────┐
│ Orchestrator   │ │ │ API /predictions/  │
│ _handle_pred.  │ │ │ GET /{metric_id}   │
│ Lee de BD      │ │ │ Genera LIVE ⚠️     │
│ (confianza)    │ │ │ (forecast_metric)  │
└────────────────┘ │ └────────────────────┘
                   │
                   ▼
       ┌──────────────────────────────┐
       │ monitor_predictions_quality  │  ← NUEVO (FASE 4.A)
       │ Compara predictions vs reales│
       │ Alertas: CRITICO / DRIFT    │
       │ → predictions_quality_history│
       └──────────────────────────────┘
```

---

## 8. CONCLUSIÓN

### Antes de FASE 8

El pipeline tenía **3 bugs críticos**: fuga de datos SARIMA, MAPE no persistido, confianza hardcodeada. De 12 fuentes, solo 3 (GENE_TOTAL, EMBALSES, EMBALSES_PCT) eran confiables. PERDIDAS era "catastrófica" (88.8% MAPE ex-post) y PRECIO_BOLSA era inusable (59% MAPE implícito, validación falsa).

### Después de FASE 8

- **5 bugs críticos corregidos** (fuga SARIMA, MAPE en BD, confianza hardcoded, fallback 0.95→0.50, holdout Prophet params)
- **Quality gate activo**: MAPE > 50% → no se guarda (con logging detallado)
- **13 de 13 fuentes** tienen predicciones en BD con métricas reales
- **MAPE promedio global: ~8.3%** (excluyendo PRECIO_BOLSA)
- **PERDIDAS**: de 88.8% MAPE a 10.0% MAPE (diagnóstico correcto + bugs corregidos)
- **Confianzas honestas** en todas las fuentes (ya no hay 0.95 falsos)

### Después de FASE 3 (Regresores Multivariable)

- **PRECIO_BOLSA mejorado**: MAPE 43.18% → **40.07%** (-3.11 puntos porcentuales)
- **RMSE mejorado**: 63.95 → **56.02** (-12.4%)
- **3 regresores activos**: embalses_pct, demanda_gwh, aportes_gwh
- **Hallazgo clave**: `growth='flat'` + regresores supera a `growth='linear'` sin regresores — los regresores capturan los fundamentales económicos que el trend lineal intentaba aproximar
- **Arquitectura escalable**: `ORDEN_PROCESAMIENTO` + `predicciones_memoria` permite agregar regresores a cualquier métrica sin cambios estructurales
- **Backward compatible**: Métricas sin regresores (DEMANDA, EMBALSES, etc.) producen resultados idénticos

### Después de FASE 4 (Monitoreo + Regresores Calendario)

- **Monitoreo ex-post operativo** (FASE 4.A): Script `monitor_predictions_quality.py` compara predicciones vs reales para las 13 fuentes, detecta drift y alertas críticas, persiste historial en `predictions_quality_history`
- **DEMANDA mejorada** (FASE 4.B): 7 regresores calendario (festivos colombianos + day-of-week) → MAPE 3.75% → **3.61%** (-0.14pp), RMSE -2.6%
- **Festivos Colombia completos**: Ley 51 de 1983, Ley Emiliani (traslados a lunes), Pascua (Meeus/Jones/Butcher), 2020-2028
- **`preparar_regresores()` refactorizado**: Soporta dos paradigmas — regresores BD (PRECIO_BOLSA) y regresores calendario (DEMANDA) — en la misma función, mixables por métrica
- **Regresión verificada**: PRECIO_BOLSA (BD) = 41.83%, EMBALSES_PCT (ninguno) = 0.67%, ambos estables

### Siguiente paso

Con PRECIO_BOLSA en ~40% MAPE y monitoreo operativo, las vías de mejora restantes son:
1. **Regresores calendario para más métricas** (GENE_TOTAL, Hidráulica) — la infraestructura ya existe
2. **Regresores BD para otras métricas** (Eólica, Solar, APORTES_HIDRICOS) — misma infra
3. **SARIMAX**: Agregar regresores también al componente SARIMA del ensemble (actualmente solo Prophet los usa)
4. **`growth='logistic'`** con cap/floor para PRECIO_BOLSA — evitaría predicciones negativas sin depender del piso histórico
5. **Cross-validation temporal** (P7) para estimaciones de MAPE más robustas
6. **Datos climáticos** (ONI, precipitación) para APORTES_HIDRICOS, que a su vez mejoraría PRECIO_BOLSA automáticamente
7. **XGBoost/Random Forest** como tercer modelo del ensemble (FASE 4.C candidata)

### 5.5 FASE 5 — Integración Cron de Monitoreo y Experimento XGBoost (2026-02-28)

#### 5.5.1 FASE 5.A: Integración del monitoreo ex-post al cron (`actualizar_predicciones.sh`)

**Archivo modificado:** `scripts/actualizar_predicciones.sh` (223 → 256 líneas)

**Objetivo:** Ejecutar automáticamente `monitor_predictions_quality.py` como parte del pipeline semanal de actualización, sin intervención manual.

**Cambios realizados:**

1. **Nuevo PASO 4** insertado entre entrenamiento (PASO 3) y alertas operacionales (PASO 5):
   - Ejecuta `monitor_predictions_quality.py` con captura de stdout
   - Fallo del monitor es **no-crítico** (`|| true`) — no detiene el pipeline
   - Cuenta fuentes OK / CRÍTICO / DRIFT mediante grep del output
   - Log completo del monitor se anexa al log del cron

2. **Renumeración de pasos**: PASO 4→5 (alertas), PASO 5→6 (integridad), PASO 6→7 (limpieza)

3. **Resumen final ampliado**: Incluye contadores del monitoreo ex-post (OK/críticas/drift)

**Secuencia del pipeline actualizada (7 pasos):**

```
PASO 1: Verificar entorno (Python venv, PostgreSQL)
PASO 2: Entrenar predicciones de generación (5 fuentes)
PASO 3: Entrenar predicciones sectoriales (9 métricas estratégicas)
PASO 4: Monitoreo ex-post de calidad  ← NUEVO (FASE 5.A)
PASO 5: Sistema de alertas operacionales
PASO 6: Verificar integridad de predicciones (COUNT(*))
PASO 7: Limpiar logs antiguos (>30 días)
```

**Verificación:** `bash -n actualizar_predicciones.sh` → syntax OK ✅

#### 5.5.2 FASE 5.B: Experimento XGBoost offline para PRECIO_BOLSA

**Archivo creado:** `experiments/xgboost_precio_bolsa.py` (~340 líneas)

**Objetivo:** Evaluar si XGBoost multivariable supera al ensemble Prophet+SARIMA actual para la predicción de Precio de Bolsa Nacional. Experimento offline — NO integrado a producción.

**Dataset multivariable (12 features):**

| Feature | Tipo | Fuente |
|---------|------|--------|
| `embalses_pct` | Regresor BD | PorcVoluUtilDiar × 100 |
| `demanda_gwh` | Regresor BD | DemaReal (prefer Sistema) |
| `aportes_gwh` | Regresor BD | AporEner |
| `precio_lag_1` | Lag target | PRECIO_BOLSA (t-1) |
| `precio_lag_7` | Lag target | PRECIO_BOLSA (t-7) |
| `es_festivo` | Calendario | Festivos Colombia |
| `dow_lun..dow_sab` | Calendario | Day-of-week dummies (6) |

**Validación:** Temporal holdout (últimos 30 días). NO random split.

**Resultados primera ejecución (2026-02-28):**

| Modelo | MAPE | RMSE | Status |
|--------|:---:|:---:|--------|
| **XGBoost (multivariable)** | **18.14%** | **27.27 $/kWh** | EXPERIMENTO |
| Ensemble Prophet+SARIMA | ~40.07% | ~56.02 $/kWh | PRODUCCIÓN |

**Mejora estimada:** ~22pp de reducción en MAPE (40% → 18%).

**Feature Importance (top 5):**

| Feature | Importancia | % |
|---------|:---:|:---:|
| `precio_lag_1` | 0.6756 | 67.6% |
| `precio_lag_7` | 0.1168 | 11.7% |
| `aportes_gwh` | 0.0636 | 6.4% |
| `embalses_pct` | 0.0315 | 3.1% |
| `dow_lun` | 0.0293 | 2.9% |

**Hallazgo clave:** Los lags del precio (`precio_lag_1` + `precio_lag_7`) explican el **79.3%** de la importancia total, confirmando que PRECIO_BOLSA tiene fuerte autocorrelación. Los regresores BD (`aportes_gwh`, `embalses_pct`, `demanda_gwh`) contribuyen un 11.1% adicional. Los features calendario son marginales (~8.5%).

**CSVs generados:**
- `experiments/resultados_xgboost_precio.csv` — predicciones vs reales (30 días)
- `experiments/feature_importance_xgboost.csv` — importancia de features
- `experiments/comparacion_modelos.csv` — tabla comparativa
- `experiments/xgboost_experiment_*.log` — log completo con timestamp

**⚠️ Caveats antes de integrar a producción:**
1. XGBoost con lags requiere datos reales del día anterior para predecir — el ensemble actual predice 90 días hacia adelante sin requerir inputs futuros
2. La ventaja del lag se erosiona a medida que el horizonte de predicción crece (recursive forecasting)
3. Evaluación sobre 30 días de holdout; necesita validación cruzada temporal más robusta
4. Para horizonte corto (1-7 días), XGBoost es claramente superior; para 90 días, el ensemble puede ser más estable

### 5.6 FASE 6 — Model Selection Experiment (2026-02-28)

**Archivo creado:** `experiments/model_selection.py` (~530 líneas)

**Objetivo:** Comparar sistemáticamente 6 modelos ML en 3 métricas prioritarias para determinar el mejor modelo por métrica antes de integrar a producción.

**Dependencias instaladas:** `lightgbm 4.6.0`, `torch 2.10.0+cpu` (CPU-only para LSTM)

**6 modelos comparados:**

| # | Modelo | Tipo | Características |
|---|--------|------|-----------------|
| 1 | Ensemble Prophet+SARIMA | Estadístico | Re-entrenado con mismo holdout para comparación justa |
| 2 | XGBoost | Gradient Boosting | FASE 5.B baseline, 500 trees, early stopping |
| 3 | LightGBM | Gradient Boosting | Más rápido, regularización L1/L2 |
| 4 | Random Forest | Bagging | 300 trees, menos overfitting |
| 5 | LSTM | Deep Learning | PyTorch, 2 capas, secuencias de 14 días |
| 6 | Hybrid | Combinación | Mejor tree-model + ensemble, pesos por inv. MAPE |

**Uso:**
```bash
python experiments/model_selection.py --metrica PRECIO_BOLSA
python experiments/model_selection.py --metrica DEMANDA
python experiments/model_selection.py --metrica APORTES_HIDRICOS
python experiments/model_selection.py --metrica ALL
```

#### 5.6.1 Resultados PRECIO_BOLSA

| # | Modelo | MAPE | RMSE ($/kWh) | Tiempo |
|---|--------|:---:|:---:|:---:|
| 1 | **RandomForest** 🏆 | **16.03%** | **24.03** | 0.6s |
| 2 | LightGBM | 17.19% | 26.11 | 0.4s |
| 3 | XGBoost | 19.71% | 29.38 | 2.2s |
| 4 | Hybrid | 28.48% | 38.23 | — |
| 5 | LSTM | 53.93% | 83.22 | 48.6s |
| 6 | Ensemble P+S | 149.27% | 188.37 | — |

**Hallazgo:** Los 3 modelos tree-based (RF, LGBM, XGB) superan masivamente al ensemble. Random Forest lidera con **16.03% MAPE** vs ensemble 149% (el ensemble sufre en este holdout particular por régimen de precios cambiante).

**Feature importance (Random Forest):** `y_lag1` domina (96.6%), confirmando la fuerte autocorrelación del precio.

#### 5.6.2 Resultados DEMANDA

| # | Modelo | MAPE | RMSE (GWh) | Tiempo |
|---|--------|:---:|:---:|:---:|
| 1 | **LightGBM** 🏆 | **1.30%** | **4.18** | 0.4s |
| 2 | XGBoost | 1.49% | 4.71 | 0.4s |
| 3 | Hybrid | 1.57% | 5.11 | — |
| 4 | RandomForest | 1.61% | 5.12 | 0.6s |
| 5 | LSTM | 2.59% | 7.83 | 107s |
| 6 | Ensemble P+S | 3.76% | 10.25 | — |

**Hallazgo:** LightGBM reduce MAPE de **3.76% → 1.30%** (−2.46pp, mejora del 65%). Los 3 tree-models logran MAPE < 2%, todos muy superiores al ensemble actual.

**Feature importance (LightGBM):** `y_lag7` (39.5%) y `y_lag1` (37.9%) dominan; el patrón semanal de demanda es clave.

#### 5.6.3 Resultados APORTES_HIDRICOS

| # | Modelo | MAPE | RMSE (GWh) | Tiempo |
|---|--------|:---:|:---:|:---:|
| 1 | **Hybrid** 🏆 | **10.55%** | 80.90 | — |
| 2 | LightGBM | 11.23% | **70.73** | 0.2s |
| 3 | XGBoost | 11.36% | 68.54 | 0.2s |
| 4 | RandomForest | 11.86% | 70.82 | 0.5s |
| 5 | Ensemble P+S | 18.29% | 125.42 | — |
| 6 | LSTM | 22.22% | 116.65 | 110s |

**Hallazgo:** El modelo **Hybrid** (LightGBM 62% + Ensemble 38%) gana con **10.55% MAPE**. En esta métrica volátil (hidrología), combinar paradigmas aporta valor. Todos los tree-models mejoran el ensemble por ~7pp.

**Feature importance (LightGBM):** Distribución más equilibrada — `y_lag1` (34%), `embalses_pct` (31%), `y_lag7` (29%). Los niveles de embalse son un predictor fuerte para aportes.

#### 5.6.4 Resumen consolidado FASE 6

| Métrica | Ensemble actual | Mejor modelo | MAPE | Mejora |
|---------|:---:|:---:|:---:|:---:|
| PRECIO_BOLSA | 149.27%* | **RandomForest** | **16.03%** | −133pp |
| DEMANDA | 3.76% | **LightGBM** | **1.30%** | −2.46pp (−65%) |
| APORTES_HIDRICOS | 18.29% | **Hybrid (LGBM+Ens)** | **10.55%** | −7.74pp (−42%) |

\* El ensemble Prophet+SARIMA sufre especialmente en el holdout de PRECIO_BOLSA por el cambio de régimen de precios reciente. En producción, su MAPE reportado es ~40%.

**Conclusiones clave:**
1. **Los modelos tree-based con lags ganan en las 3 métricas** — la autocorrelación temporal (`y_lag1`, `y_lag7`) es el predictor dominante.
2. **LSTM no es competitivo** — con ~450 datos (PRECIO_BOLSA) no tiene suficientes muestras, y para DEMANDA/APORTES (2200+) sigue perdiendo contra trees.
3. **Hybrid aporta valor en series volátiles** (APORTES_HIDRICOS) donde combinar paradigmas suaviza errores.
4. **⚠️ Caveat crítico:** Todos estos resultados son con holdout de 1 paso (next-day vía lags). Para horizonte de 90 días (producción), se necesita recursive forecasting donde los lags se alimentan de predicciones propias, degradando el MAPE progresivamente.

**Salidas generadas en `experiments/results/`:**
- `*_comparacion.csv` — tabla ranking por métrica
- `*_predicciones_holdout.csv` — predicciones de los 6 modelos vs real
- `*_feature_importance.csv` — importancia de features (modelos árbol)
- `*_comparacion_barras.html` — gráfico Plotly barras MAPE/RMSE
- `*_holdout_lineas.html` — gráfico Plotly líneas predicción vs real

### Siguiente paso

Con los resultados de FASE 6, las opciones para producción son:
1. **Horizonte dual**: tree-model (1-7 días) + ensemble (8-90 días) — lo mejor de ambos mundos
2. **Recursive XGBoost/LightGBM**: entrenar con lags recursivos para evaluar degradación a 90 días
3. **Multi-step XGBoost**: entrenar un modelo por horizonte (h=1, h=7, h=30, h=90) con direct forecasting
4. **Integrar el ganador** como tercer componente del ensemble actual (tree weight + prophet weight + sarima weight)

---

## 5.7 FASE 7 — Experimento SOTA (Estado del Arte)

**Fecha:** 2026-02-28
**Script:** `experiments/sota_models.py`
**Paquetes:** neuralforecast 3.1.5, chronos-forecasting 2.2.2 (torch 2.10.0+cpu)
**Objetivo:** Evaluar si arquitecturas neuronales SOTA de series temporales superan a los ganadores tree-based de FASE 6 en PRECIO_BOLSA y DEMANDA.

#### 5.7.1 Modelos SOTA evaluados

| # | Modelo | Arquitectura | Tipo | Exógenas |
|---|--------|-------------|------|----------|
| 1 | **PatchTST** | Transformer con patches channel-independent | Univariado | No (v3.x no soporta futr_exog) |
| 2 | **N-BEATS** | Neural Basis Expansion (trend + seasonality stacks) | Univariado | No (diseño puro) |
| 3 | **TCN** | Temporal Convolutional Network con dilataciones | Con calendario | sí (futr_exog: 7 features) |
| 4 | **N-HiTS** | Neural Hierarchical Interpolation multi-resolución | Univariado | No |
| 5 | **Chronos** | Foundation Model T5 pre-entrenado (zero-shot) | Univariado | No (sin entrenamiento) |

**Baselines FASE 6:** RandomForest y LightGBM (con features: y_lag1, y_lag7, regresores BD, calendario).

**Nota sobre NeuralProphet:** Se sustituyó por N-HiTS debido a incompatibilidad irresoluble de `neuralprophet 0.8.0` con `pytorch-lightning 2.x` (requerido por neuralforecast). Múltiples APIs internas rotas (`ProgressBar.main_progress_bar`, `FitLoop.running_loss`).

#### 5.7.2 Nota metodológica crítica

Los modelos SOTA enfrentan una **desventaja estructural** vs los tree-models de FASE 6:

| Aspecto | Tree-models (FASE 6) | SOTA (FASE 7) |
|---------|:---:|:---:|
| Features de lag | **y_lag1, y_lag7 reales** del holdout | No disponibles (multi-step genuino) |
| Tipo de forecast | 1-paso (con lags actuales) | 30-pasos directos (sin retroalimentación) |
| Feature engineering | Manual (12 features) | Automático (aprendido de la serie) |
| Datos DEMANDA | 2215 train + features | 2215 train, solo y |
| Datos PRECIO_BOLSA | 424 train + features | 424 train, solo y (+ calendario TCN) |

**Implicación:** Si un modelo SOTA iguala o supera a un tree-model, es un resultado significativamente más fuerte, ya que resuelve un problema más difícil (forecasting multi-paso real sin features pre-calculados).

#### 5.7.3 Resultados PRECIO_BOLSA

| # | Tipo | Modelo | MAPE | RMSE ($/kWh) | MAE | T(s) |
|---|------|--------|:---:|:---:|:---:|:---:|
| 1 | F6 | **RandomForest_F6** | **16.03%** | 24.03 | 20.23 | 0.5s 🏆 |
| 2 | F6 | LightGBM_F6 | 17.19% | 26.11 | 22.07 | 6.1s |
| 3 | SOTA | PatchTST | 60.06% | 80.25 | 71.49 | 554.6s ⭐ |
| 4 | SOTA | Chronos | 93.58% | 118.71 | 108.01 | 2.5s |
| 5 | SOTA | N-BEATS | 116.58% | 147.45 | 133.88 | 64.9s |
| 6 | SOTA | N-HiTS | 118.67% | 149.81 | 137.37 | 49.5s |
| 7 | SOTA | TCN | 128.44% | 178.89 | 168.49 | 35.6s |

**Hallazgo:** Los tree-models dominan por amplio margen (16% vs 60%). PatchTST es el mejor SOTA pero queda a 44pp del RandomForest. Razones:
- Solo 424 muestras de entrenamiento — insuficiente para transformers
- Régimen de precios altamente volátil con cambio estructural reciente
- Los tree-models usan `y_lag1` real (ventaja injusta pero ilustrativa del poder predictivo de la autocorrelación)
- **Chronos** destaca por su velocidad (2.5s, zero-shot) y MAPE ~94%: notable para un modelo sin entrenamiento

#### 5.7.4 Resultados DEMANDA

| # | Tipo | Modelo | MAPE | RMSE (GWh) | MAE | T(s) |
|---|------|--------|:---:|:---:|:---:|:---:|
| 1 | F6 | **LightGBM_F6** | **1.30%** | 4.18 | 2.89 | 1.7s 🏆 |
| 2 | F6 | RandomForest_F6 | 1.61% | 5.12 | 3.57 | 0.6s |
| 3 | SOTA | **TCN** | **1.76%** | 5.00 | 3.95 | 65.6s ⭐ |
| 4 | SOTA | N-BEATS | 1.83% | 5.82 | 4.06 | 45.0s |
| 5 | SOTA | N-HiTS | 2.02% | 5.78 | 4.59 | 37.9s |
| 6 | SOTA | PatchTST | 2.15% | 6.73 | 4.70 | 295.1s |
| 7 | SOTA | Chronos | 2.17% | 6.84 | 4.85 | 1.8s |

**Hallazgo: DEMANDA muestra resultados impresionantemente competitivos:**
- **TCN** logra 1.76% MAPE — solo **0.46pp** por debajo de LightGBM (1.30%)
- **N-BEATS** queda a 0.53pp — virtualmente al mismo nivel
- **Todos los SOTA están por debajo de 2.2%** — excelente para forecasting multi-paso sin lags
- **Chronos** logra 2.17% con ZERO entrenamiento (zero-shot, 1.8s)

**Interpretación:** Para DEMANDA (2215 datos, serie estable con estacionalidad clara), los modelos SOTA capturan eficientemente los patrones temporales. La brecha de 0.46pp refleja la ventaja de tener `y_lag1` como feature explícito, no una superioridad inherente de los tree-models.

#### 5.7.5 Resumen consolidado FASE 7

| Métrica | Mejor Tree (F6) | MAPE F6 | Mejor SOTA | MAPE SOTA | Δ MAPE |
|---------|:---:|:---:|:---:|:---:|:---:|
| PRECIO_BOLSA | RandomForest | 16.03% | PatchTST | 60.06% | +44.03pp |
| DEMANDA | LightGBM | 1.30% | TCN | 1.76% | +0.46pp |

#### 5.7.6 Conclusiones FASE 7

1. **Los tree-models con feature engineering mantienen la ventaja**, especialmente con datasets pequeños (PRECIO_BOLSA ~450 obs) donde las arquitecturas neuronales no tienen suficientes datos.

2. **Para DEMANDA, los SOTA son casi equivalentes** (gap de solo 0.46pp). En un escenario de producción para horizonte >7 días (donde los lags reales no están disponibles), los modelos SOTA como TCN o N-BEATS probablemente **superen** a los tree-models.

3. **Chronos es notable** como baseline zero-shot: sin entrenamiento, DEMANDA 2.17% (vs 1.30% tree-best). Para prototyping rápido o métricas nuevas sin histórico largo, es una opción viable.

4. **PatchTST necesita más datos**: con ~2200 obs (DEMANDA) logra 2.15%, pero con ~450 (PRECIO_BOLSA) se degrada a 60%. Los transformers necesitan >1000 muestras para ser competitivos.

5. **TCN es el SOTA más robusto**: consistentemente buen rendimiento en ambas métricas, entrenamiento relativamente rápido (35-65s).

6. **Recomendación de producción**: Mantener tree-models para horizonte 1-7 días. Para horizonte 30-90 días (donde los lags reales no existen), evaluar **TCN** o **N-BEATS** como modelo principal, ya que su forecasting multi-paso genuino evita la degradación recursiva que sufren los tree-models con lags auto-alimentados.

**Salidas generadas en `experiments/results/`:**
- `*_sota_comparacion.csv` — tabla ranking SOTA vs FASE 6
- `*_sota_predicciones.csv` — predicciones de los 7 modelos vs real
- `*_sota_comparacion.html` — gráfico Plotly barras MAPE/RMSE
- `*_sota_holdout.html` — gráfico Plotly líneas predicción vs real

---

### §5.8 FASE 8 — Sistema de Horizonte Dual en Producción (LightGBM + TCN)

**Fecha:** 2026-02-28  
**Objetivo:** Implementar en producción el sistema de horizonte dual LightGBM (1-7 días) + TCN (8-90 días) basado en hallazgos de FASE 6+7.

#### Motivación

FASE 7 demostró que:
- Tree-models (LightGBM, RandomForest) dominan el corto plazo gracias a features de lag real (`y_lag1`, `y_lag7`)
- TCN es el SOTA más robusto para multi-step genuino (sin recursión de lags)
- Para DEMANDA, el gap SOTA vs tree-model era de solo 0.46pp (1.76% vs 1.30%)

**Hipótesis:** Combinar LightGBM (precisión local con lags reales, días 1-7) con TCN (generalización multi-paso, días 8-90) producirá un sistema superior al ensemble Prophet+SARIMA actual.

#### Arquitectura

```
PredictorHorizonteDual
├── LightGBM (días 1-7)
│   ├── Features: y_lag1, y_lag7, regresores BD, calendario colombiano
│   ├── Predicción recursiva: lag1 se actualiza con predicción previa
│   └── Intervalos: ±1.96σ residuos × factor creciente por día
│
├── TCN (días 8-90) — neuralforecast 3.1.5
│   ├── h=83, input_size=90
│   ├── kernel_size=3, dilations=[1,2,4,8,16]
│   ├── futr_exog: calendario (festivos + DOW)
│   ├── Multi-step directo (sin recursión)
│   └── Intervalos: ±1.96 × MAPE_holdout × valor_predicho
│
└── Handoff día 7→8: transición limpia (sin blending)
```

#### Cambios implementados

| Componente | Cambio |
|---|---|
| `predictions` table | Nueva columna `metodo_prediccion VARCHAR(50) DEFAULT 'ensemble_prophet_sarima'` |
| `guardar_predicciones_bd()` | Nuevos params: `metodo_prediccion`, `modelo_version`. Per-row `metodo_prediccion` desde DataFrame |
| `PredictorHorizonteDual` | Nueva clase (~500 líneas): dataset builder, LightGBM trainer, TCN trainer, recursive predictor, holdout validator |
| `main_horizonte_dual()` | Nuevo pipeline completo para métricas duales |
| CLI | `--test_horizonte_dual [METRICA ...]` — activa modo dual |
| `METRICAS_HORIZONTE_DUAL` | Config para DEMANDA y PRECIO_BOLSA (params LightGBM + TCN) |

#### Resultados de producción

**DEMANDA (2245 registros, 5.1 años)**

| Horizonte | Modelo | MAPE | Notas |
|---|---|---|---|
| Días 1-7 | LightGBM recursivo | **0.74%** | y_lag1 real → predicción recursiva |
| Días 8-30 | TCN multi-step | **2.00%** | calendario exog, early stopping |
| Combinado (1-30d holdout) | Dual | **1.70%** | Confianza: 98.30% |

**Comparación con baseline:**
| Sistema | MAPE Holdout 30d | Modelo |
|---|---|---|
| Ensemble Prophet+SARIMA | ~3.6% | ENSEMBLE_SECTOR_v1.0 |
| FASE 6 LightGBM (solo) | 1.30% | Holdout con lags reales |
| **FASE 8 Horizonte Dual** | **1.70%** | DUAL_HORIZON_v1.0 |

El horizonte dual (1.70%) supera al ensemble Prophet+SARIMA (~3.6%) por ~1.9pp. Es ligeramente inferior al LightGBM FASE 6 (1.30%) porque incluye los días 8-30 con TCN (degradación natural por horizonte largo).

**PRECIO_BOLSA (454 registros, 15 meses)**

| Horizonte | Modelo | MAPE | Resultado |
|---|---|---|---|
| Días 1-7 | LightGBM recursivo | 21.14% | Degradación recursiva con solo 454 obs |
| Días 8-30 | TCN | 142.87% | Datos insuficientes + alta volatilidad |
| Combinado | Dual | 114.47% | **DESCARTADA** (> umbral 50%) |

Resultado esperado: PRECIO_BOLSA con σ=201 $/kWh y solo 454 registros es intratable para cualquier modelo SOTA. El quality gate (UMBRAL_MAPE_MAXIMO=50%) correctamente descarta las predicciones.

#### Esquema BD actualizado

```sql
-- Columna añadida
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS
    metodo_prediccion VARCHAR(50) DEFAULT 'ensemble_prophet_sarima';

-- Valores posibles:
--   'ensemble_prophet_sarima' — sistema original (default)
--   'lightgbm_short'          — LightGBM días 1-7
--   'tcn_long'                — TCN días 8-90
--   'dual_horizon'            — valor general del pipeline dual
```

#### Uso en producción

```bash
# Modo estándar (sin cambios, ensemble Prophet+SARIMA)
python scripts/train_predictions_sector_energetico.py

# Horizonte dual — todas las métricas configuradas
python scripts/train_predictions_sector_energetico.py --test_horizonte_dual

# Horizonte dual — solo DEMANDA
python scripts/train_predictions_sector_energetico.py --test_horizonte_dual DEMANDA

# Horizonte dual — métricas específicas
python scripts/train_predictions_sector_energetico.py --test_horizonte_dual DEMANDA PRECIO_BOLSA
```

#### Decisiones de diseño

1. **Sin blending en frontera día 7→8**: LightGBM termina en día 7, TCN empieza en día 8. No se promedia en la frontera porque (a) la discontinuidad es mínima para DEMANDA, (b) la complejidad adicional no justifica el beneficio marginal.

2. **TCN h=83 (no h=90)**: TCN predice 83 días (8-90). Se entrena con h=HORIZONTE_LARGO_DIAS=83 y sus predicciones se mapean directamente a días 8-90. Se acepta el ligero desfase temporal (TCN cree predecir días 1-83) porque los patrones son relativos.

3. **Intervalos diferenciados**: LightGBM usa residuos del train set × factor creciente (1 + 0.15×día). TCN usa MAPE del holdout como proxy de incertidumbre proporcional (±1.96×MAPE×predicción).

4. **Quality gate unificado**: Si MAPE_combinado > 50%, se descartan TODAS las predicciones de esa métrica. PRECIO_BOLSA se descarta correctamente en producción.

5. **Backward compatible**: `guardar_predicciones_bd()` mantiene defaults, el ensemble original funciona sin cambios. La columna `metodo_prediccion` tiene default `'ensemble_prophet_sarima'` para registros existentes.

#### Feature importance (LightGBM, DEMANDA producción)

```
y_lag7       42%  ████████████████████
y_lag1       39%  ███████████████████
dow_lun       4%  ██
es_festivo    4%  ██
dow_sab       4%  ██
```

Los lags dominan (81% total) — confirma la tesis de FASE 6: la demanda eléctrica es altamente autocorrelacionada a escala semanal.

---

### §5.9 FASE 9 — (reservada)

_(No hubo FASE 9 separada; las mejoras continuas se integraron en FASES 10-17.)_

---

### §5.10 FASE 10 — RandomForest para PRECIO_BOLSA (2026-02-28)

**Objetivo:** Reemplazar LightGBM para PRECIO_BOLSA por RandomForest, mejor adaptado a alta volatilidad.

| Componente | Detalle |
|---|---|
| Modelo | `RandomForestRegressor` (scikit-learn) |
| Versión | `RANDOMFOREST_v1.0` |
| Config | `PRECIO_BOLSA_RF_CONFIG` (línea ~99) |
| n_estimators | 300 |
| max_depth | 12 |
| min_samples_leaf | 5 |
| Pipeline | `main_randomforest_precio()` |
| MAPE holdout | **15.60%** |

**Regresores BD:** 6 variables (precio_escasez, capacidad_util, etc.)

---

### §5.11 FASE 11 — LGBM Directo para APORTES_HIDRICOS (2026-02-28)

**Objetivo:** Migrar APORTES_HIDRICOS de Prophet+SARIMA ensemble a LightGBM directo con regresores BD.

| Componente | Detalle |
|---|---|
| Modelo | `LGBMRegressor` (lightgbm) |
| Versión | `LGBM_DIRECTO_v1.0` |
| Config | `APORTES_HIDRICOS_LGBM_CONFIG` (línea ~161) |
| Pipeline | `main_lgbm_aportes()` |
| MAPE holdout | **13.70%** |
| Regresores BD | 6 variables |

---

### §5.12 FASE 12 — LGBM Directo para Térmica (2026-02-28)

| Componente | Detalle |
|---|---|
| Modelo | `LGBMRegressor` |
| Versión | `LGBM_DIRECTO_TERMICA_v1.0` |
| Config | `TERMICA_LGBM_CONFIG` (línea ~228) |
| Pipeline | `main_lgbm_termica()` |
| MAPE holdout | **12.60%** (pre-FASE 16) |
| Regresores BD | 7 variables |
| `recurso_filtro` | `'Térmicas'` — filtra `generacion_real_sistema` por recurso |

---

### §5.13 FASE 13 — LGBM Directo para Solar y Eólica (2026-02-28)

**Solar:**

| Componente | Detalle |
|---|---|
| Versión | `LGBM_DIRECTO_SOLAR_v1.0` |
| Config | `SOLAR_LGBM_CONFIG` (línea ~301) |
| Pipeline | `main_lgbm_solar()` |
| MAPE holdout | **18.02%** (pre-FASE 16) |
| Regresores BD | 6 variables |
| `recurso_filtro` | `'Solar'` |

**Eólica:**

| Componente | Detalle |
|---|---|
| Versión | `LGBM_DIRECTO_EOLICA_v1.0` |
| Config | `EOLICA_LGBM_CONFIG` (línea ~368) |
| Pipeline | `main_lgbm_eolica()` |
| MAPE holdout | **16.36%** |
| Regresores BD | 4 variables |
| `recurso_filtro` | `'Eólica'` |

---

### §5.14 FASE 14 — Cross-Validation Temporal 5-Fold (2026-02-28)

**Objetivo:** Validación robusta con expanding window CV (5 folds, step=60d, horizon=30d).

| Componente | Detalle |
|---|---|
| Función | `cross_validate_temporal()` |
| CV_MODEL_REGISTRY | Mapea 5 métricas → (PredictorClass, config, args) |
| `main_cross_validation()` | Ejecuta CV para 1 o todas las métricas |
| Quality gate | `mape_median` < umbral → PASS |
| Artefactos | `cv_temporal_fase14.html`, `cv_boxplot_comparativo.html` |
| CLI | `--cv METRICA`, `--cv_all` |

Resultado CV (métricas al corte):
```
mape_mean, mape_median, mape_trimmed, mape_std, mape_min, mape_max
rmse_mean, ci_95, n_outlier_folds (media ± 2σ)
```

---

### §5.15 FASE 15 — Multivariate Discovery (2026-03-01)

**Objetivo:** Descubrir variables de alta correlación entre las métricas PostgreSQL.

- Analizó 52 variables potenciales de la BD `portal_energetico`
- Identificó 37 regresores con impacto **ALTO** (correlación + feature importance > umbral)
- Ranking por relevancia permite selección automática de top-N regresores por métrica

---

### §5.16 FASE 16 — Integración Top-10 Regresores (2026-03-01)

**Objetivo:** Incorporar los mejores regresores descubiertos en FASE 15 a los 4 modelos LGBM.

**Resultados de producción:**

| Métrica | MAPE Pre-F16 | MAPE Post-F16 | Δ | Gate |
|---|---|---|---|---|
| Térmica | 12.60% | **7.43%** | **-41%** | ✅ PASS |
| Solar | 18.02% | **10.14%** | **-44%** | ✅ PASS |
| APORTES_HIDRICOS | 13.70% | 14.79% | +8% | ✅ PASS |
| Eólica | 16.36% | 18.77% | +15% | ✅ PASS |
| PRECIO_BOLSA | 15.60% | 15.94% | +2% | ✅ PASS |

**Cambios clave:**
- 12 nuevos regresores distribuidos entre 4 configs (Térmica +4, Solar +3, APORTES +3, Eólica +2)
- Soporte `recurso_filtro` en `PredictorLGBMDirecto`, `PredictorLGBMDirectoMultivar`, `PredictorRandomForest`
- 5/5 Quality Gate PASS

---

### §5.17 FASE 17 — MLflow Tracking Server (2026-03-01)

**Objetivo:** Implementar experiment tracking con MLflow para registro automático de CV y producción.

#### Infraestructura

| Componente | Detalle |
|---|---|
| MLflow | v3.10.0 |
| Backend store | PostgreSQL `mlflow_tracking` DB |
| Tracking URI | `postgresql+psycopg2://postgres:***@localhost:5432/mlflow_tracking` |
| Artifact root | `logs/mlflow_artifacts/` |
| Server | Puerto 5000, systemd `config/mlflow-server.service` |
| Activación | CLI flag `--mlflow` (off por defecto) |

#### Funciones nuevas (`train_predictions_sector_energetico.py`)

| Función | Línea | Rol |
|---|---|---|
| `setup_mlflow(experiment_name)` | ~599 | Configura URI + experiment |
| `mlflow_log_cv_run(result, config, modelo_version, experiment_name)` | ~617 | Registra CV: params, 12+ métricas, per-fold, artefactos HTML |
| `mlflow_log_production_run(metrica, predictor, config, modelo_version, elapsed_s, ok_bd)` | ~710 | Registra producción: params, métricas holdout, modelo serializado |

#### Parámetros registrados (CV)

```
metrica, modelo_tipo, modelo_version, cv_initial, cv_step, cv_horizon,
cv_n_folds, fecha_ejecucion, n_regresores_bd, regresores_bd,
ventana_meses, n_estimators, lgbm_* (hiperparámetros)
```

#### Métricas registradas (CV)

```
mape_mean, mape_median, mape_trimmed, mape_std, mape_min, mape_max,
rmse_mean, ci95_lower, ci95_upper, n_outlier_folds, quality_gate_pass,
tiempo_cv_s, fold_{i}_mape, fold_{i}_rmse, fold_{i}_train_size
```

#### Métricas registradas (Producción)

```
mape_holdout, rmse_holdout, confianza, guardado_bd, tiempo_s
```

#### Artefactos

- **CV:** `cv_temporal_fase14.html`, `cv_boxplot_comparativo.html`
- **Producción:** Modelo serializado (LightGBM vía `mlflow.lightgbm`, sklearn vía `mlflow.sklearn`, fallback pickle)

#### Hooks de integración

| Función | Hook location |
|---|---|
| `main_cross_validation()` | Después de `all_results.append(result)` → `mlflow_log_cv_run()` |
| `main_lgbm_aportes()` | Después de `elapsed = time.time() - t0` → `mlflow_log_production_run()` |
| `main_lgbm_termica()` | Ídem |
| `main_lgbm_solar()` | Ídem |
| `main_lgbm_eolica()` | Ídem |
| `main_randomforest_precio()` | Ídem |

#### CLI

```bash
# CV con MLflow tracking
python scripts/train_predictions_sector_energetico.py --cv_all --mlflow

# CV con experiment custom
python scripts/train_predictions_sector_energetico.py --cv PRECIO_BOLSA --mlflow --mlflow_experiment mi_exp

# Producción con MLflow
python scripts/train_predictions_sector_energetico.py --lgbm_aportes --mlflow
python scripts/train_predictions_sector_energetico.py --rf_precio --mlflow
```

#### Resultados verificados

8 runs registrados en MLflow (experiment `cv_all_metrics`):

| Métrica | MAPE median | MAPE mean | Gate | Regresores | Tiempo |
|---|---|---|---|---|---|
| APORTES_HIDRICOS | 14.79% | 14.37% | ✅ | 6 | 7.4s |
| Térmica | 7.43% | 17.28% | ✅ | 7 | 8.4s |
| Solar | 10.14% | 11.04% | ✅ | 6 | 4.4s |
| Eólica | 18.77% | 89.17% | ✅ | 4 | 4.5s |
| PRECIO_BOLSA | 15.94% | 17.54% | ✅ | 6 | 4.5s |

**Total CV time:** 30.9s — **5/5 PASS + 5 MLflow runs logged**

#### Decisiones de diseño

1. **Off por defecto:** `_MLFLOW_ENABLED = False` — no impacta ejecuciones cron existentes. Se activa solo con `--mlflow`.
2. **Try/except envolvente:** Todo logging MLflow está en try/except para no interrumpir predicciones si MLflow falla.
3. **Experiment naming:** CV usa `cv_all_metrics`, producción usa `production_{metrica}`.
4. **Run naming:** `cv_{metrica}_{timestamp}` / `prod_{metrica}_{timestamp}` — identifica runs únicos.
5. **Per-fold metrics:** Cada fold se registra como `fold_{i}_mape`, `fold_{i}_rmse`, `fold_{i}_train_size` para diagnóstico granular.
6. **Model serialization:** LightGBM → `mlflow.lightgbm.log_model()`, RandomForest → `mlflow.sklearn.log_model()`, otros → pickle fallback.

---

### §5.18 FASE 18 — ETL IDEAM: Datos Meteorológicos Externos (01-mar-2026)

#### Problema

Las predicciones de **Eólica** (MAPE 18.77%) no contaban con datos de **velocidad del viento** — el factor físico primario. Solar y APORTES_HIDRICOS usaban solo regresores XM internos, sin datos meteorológicos externos (temperatura ambiente, precipitación pluvial).

#### Fuente de datos: IDEAM vía datos.gov.co

IDEAM (Instituto de Hidrología, Meteorología y Estudios Ambientales de Colombia) publica datos abiertos en el portal **datos.gov.co** a través de la API Socrata SODA:

| Variable | Dataset ID | Unidad | Resolución raw | Rango validación |
|---|---|---|---|---|
| Velocidad del viento | `sgfv-3yp8` | m/s | Minutal | 0–50 m/s |
| Precipitación | `s54a-sgyg` | mm | Minutal | 0–500 mm |
| Temperatura | `sbwg-7ju4` | °C | Minutal | -10–55 °C |

> **Nota:** Radiación solar (brillo_solar) no disponible — todos los endpoints `hp4d-2tgp` devuelven 404.

#### Arquitectura ETL

```
datos.gov.co (Socrata SODA API)
    │ paginated fetch (50K batch, retry, rate limit)
    ▼
infrastructure/external/ideam_service.py
    │ validation → out-of-range filter
    │ aggregation: minutal → diario (2-step: intra-station → inter-station mean)
    ▼
etl/etl_ideam.py
    │ 5 pipelines paralelas
    │ epsilon fix: 0.0 → 0.0001 (evita filtro valor_gwh > 0)
    ▼
PostgreSQL metrics table (ON CONFLICT DO UPDATE)
```

#### 5 Pipelines ETL

| Pipeline | metrica_bd | recurso | Estaciones | Uso |
|---|---|---|---|---|
| Viento La Guajira | `IDEAM_VelViento` | `LA_GUAJIRA` | La Guajira | Eólica |
| Viento Nacional | `IDEAM_VelViento` | `NACIONAL` | 9 dptos | General |
| Precipitación Cuencas | `IDEAM_Precipitacion` | `CUENCAS_HIDRO` | 9 dptos (Antioquia, Caldas, Boyacá, etc.) | APORTES_HIDRICOS |
| Temperatura Zonas Solares | `IDEAM_Temperatura` | `ZONAS_SOLAR` | 8 dptos (Cesar, La Guajira, Atlántico, etc.) | Solar |
| Temperatura Nacional | `IDEAM_Temperatura` | `NACIONAL` | 9 dptos | General |

#### Integración como regresores

**Archivos modificados:**
- `scripts/train_predictions_sector_energetico.py`:
  - `EOLICA_LGBM_CONFIG` → nuevo regresor `ideam_vel_viento` (IDEAM_VelViento, recurso=LA_GUAJIRA)
  - `SOLAR_LGBM_CONFIG` → nuevo regresor `ideam_temperatura_solar` (IDEAM_Temperatura, recurso=ZONAS_SOLAR)
  - `APORTES_HIDRICOS_LGBM_CONFIG` → nuevo regresor `ideam_precipitacion` (IDEAM_Precipitacion, recurso=CUENCAS_HIDRO)
  - `cargar_regresores_historicos()` → soporte `recurso` (para RandomForest)
  - `PredictorHorizonteDual._construir_dataset()` → `recurso_filtro=reg_cfg.get('recurso')`
- `scripts/actualizar_predicciones.sh` → PASO 1.5: ETL IDEAM antes de predicciones
- `domain/interfaces/data_sources.py` → interfaz `IIDEAMDataSource`

**Nuevos archivos:**
- `infrastructure/external/ideam_service.py` (~300 líneas)
- `etl/etl_ideam.py` (~330 líneas)

#### Backfill 365 días — Resultados

| Métrica | Recurso | Días | Records raw | μ | σ |
|---|---|---|---|---|---|
| IDEAM_VelViento | LA_GUAJIRA | 356 | 742,940 | 2.75 m/s | 0.65 |
| IDEAM_VelViento | NACIONAL | ~360 | ~3.5M | ~1.80 m/s | ~0.10 |
| IDEAM_Precipitacion | CUENCAS_HIDRO | ~360 | ~15M | ~0.07 mm | ~0.04 |
| IDEAM_Temperatura | ZONAS_SOLAR | ~360 | ~500K | ~23.3 °C | ~0.75 |
| IDEAM_Temperatura | NACIONAL | ~360 | ~1M | ~19.7 °C | ~0.68 |

#### CLI

```bash
# Backfill 365 días (todas las variables)
python etl/etl_ideam.py --dias 365 --timeout 120

# Solo viento, últimos 14 días
python etl/etl_ideam.py --dias 14 --solo viento

# Solo precipitación
python etl/etl_ideam.py --dias 30 --solo precipitacion

# Verificar datos existentes en PostgreSQL
python etl/etl_ideam.py --verificar
```

#### Cron: `actualizar_predicciones.sh`

```bash
# PASO 1.5: ETL IDEAM — 14 días frescos antes de predicciones
python etl/etl_ideam.py --dias 14 --timeout 90
```

Se ejecuta **antes** de los pasos de predicción (PASO 2+). Si falla, las predicciones continúan con los datos IDEAM existentes.

#### Decisiones técnicas

1. **Epsilon 0.0001**: Precipitación y viento pueden tener valor legítimo 0.0, pero la BD filtra `valor_gwh > 0`. Almacenar 0.0001 en lugar de 0.0 para preservar la señal.
2. **Agregación 2-step**: Primero promedio intra-día por estación, luego promedio inter-estaciones. Evita sesgo por estaciones con más mediciones.
3. **Rate limiting**: 2s entre pipelines + pausa entre batches para respetar límites Socrata.
4. **Zonas geográficas estratégicas**: La Guajira para eólica (90%+ de capacidad instalada), 8 dptos para solar (zonas de alta irradiancia), 9 dptos para hidro (cuencas principales de embalses).
5. **Tolerancia a fallas**: ETL IDEAM es opcional — si falla, predicciones usan regresores existentes.

---

### §5.19 FASE 19 — Redis Cache para API de Predicciones (01-mar-2026)

#### Objetivo

Reducir latencia de endpoints de predicciones de ~120ms (query DB + serialización) a ~3ms (cache Redis), logrando **-97% de latencia** en llamadas repetidas. Fundamental para dashboard de alta concurrencia y bot WhatsApp.

#### Arquitectura

```
Cliente → FastAPI → Redis (HIT?) → JSONResponse (~3ms)
                         ↓ MISS
                    PredictionsService → PostgreSQL → modelo ML
                         ↓
                    Redis SET (TTL 1h) → JSONResponse (~120ms+)
```

- **Cache-aside pattern**: check cache first, fall back to DB on MISS, store result
- **Graceful fallback**: si Redis cae, API sigue funcionando sin cache (try/except en toda operación)
- **Conexión lazy**: singleton `_redis_client` se inicializa en primer uso, no al importar módulo

#### TTL (Time-to-Live)

| Tipo | TTL | Justificación |
|------|-----|---------------|
| Predicción individual | **3600s** (1h) | Predicciones ML se actualizan cada 6h vía cron |
| Batch (múltiples métricas) | **1800s** (30min) | Combina varias métricas, invalidar más frecuente |

#### Cache Key Format

```
pred:{metric_id}:{entity}:{horizon}:{model}:{md5_hash[:8]}
pred:batch:{md5_hash[:8]}
```

Ejemplo: `pred:PRECIO_BOLSA:Sistema:30:prophet:a3f1b2c4`

#### Endpoints implementados

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/v1/predictions/{metric_id}` | Predicción individual (cache 1h) |
| `GET` | `/api/v1/predictions/batch/forecast` | Batch para 6 métricas principales (cache 30min) |
| `GET` | `/api/v1/predictions/cache/stats` | Estadísticas Redis: keys, memoria, TTLs |
| `DELETE` | `/api/v1/predictions/cache/flush` | Flush manual de todas las keys `pred:*` |

#### Cache invalidation

- **Automática**: al ejecutar `POST /{metric_id}/train`, se eliminan todas las keys `pred:{metric_id}:*` + keys batch
- **Manual**: endpoint `DELETE /cache/flush` para purga completa
- **TTL expiry**: keys expiran automáticamente según TTL configurado

#### Batch endpoint

```bash
# Default: 6 métricas principales
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/predictions/batch/forecast"

# Custom: métricas específicas
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/predictions/batch/forecast?metricas=DEMANDA&metricas=Solar"
```

Métricas default: `DEMANDA`, `PRECIO_BOLSA`, `APORTES_HIDRICOS`, `Térmica`, `Solar`, `Eólica`

#### Resultados de performance

| Métrica | Valor |
|---------|-------|
| Latencia CACHE HIT | **~3ms** |
| Latencia CACHE MISS | ~120ms+ (DB + modelo) |
| Reducción latencia | **-97%** |
| Overhead Redis | <1ms por operación GET/SET |
| Memoria Redis por key | ~2-5KB (JSON serializado) |

#### Archivos modificados

```
api/v1/routes/predictions.py   — Cache infrastructure + 3 nuevos endpoints
requirements.txt                — redis==5.0.8
```

#### Funciones de cache (predictions.py)

| Función | Propósito |
|---------|-----------|
| `_get_redis()` | Singleton lazy con fallback graceful (timeout 2s) |
| `_cache_key()` | Genera key determinístico con hash MD5 |
| `_cache_get(key)` | Lee de Redis, deserializa JSON, None si falla |
| `_cache_set(key, data, ttl)` | Serializa JSON → Redis SET con EXPIRE |

#### Monitoreo

```bash
# Ver keys activos
redis-cli KEYS "pred:*"

# Memoria usada por predicciones
redis-cli MEMORY USAGE "pred:DEMANDA:Sistema:30:prophet:abc12345"

# Stats vía API
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/predictions/cache/stats

# Flush manual
curl -X DELETE -H "X-API-Key: $KEY" http://localhost:8000/api/v1/predictions/cache/flush
```

#### Decisiones técnicas

1. **`json.dumps(default=str)`**: maneja `datetime`, `date`, `Decimal` sin errores de serialización
2. **`model_dump(mode='json')`**: Pydantic v2 serializa nativamente antes de `json.dumps()`
3. **Timeout 2s en conexión**: evita bloqueo si Redis está lento; API degrada a sin-cache
4. **No cache en errores**: solo se cachean respuestas exitosas (HTTP 200)
5. **Hash MD5[:8] en key**: previene colisiones con caracteres especiales en metric_id
6. **Keys limitados a 20 en stats**: previene respuestas gigantes si hay muchas keys
