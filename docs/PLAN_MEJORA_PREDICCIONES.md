# Plan de Mejora: Sistema Predictivo Multimodal

## 1. Integración de Variables Exógenas

### 1.1 Fuentes de Datos Prioritarias

| Variable | Fuente | Frecuencia | Latencia | Impacto Esperado |
|----------|--------|------------|----------|------------------|
| **Precipitación regional** | IDEAM API | Diaria | 24h | +15% precisión embalses |
| **Temperatura promedio** | NASA POWER | Diaria | 24h | +8% precisión demanda |
| **Disponibilidad térmica** | XM (SCRAP) | Horaria | 1h | +12% precisión precio |
| **Restricciones programadas** | XM | Diaria | 24h | +10% precisión generación |
| **Precio gas natural** | DANE/BBG | Mensual | 30d | +5% precisión precio bolsa |

### 1.2 Feature Engineering Temporal

```python
# Features cíclicas (capturan estacionalidad)
features = {
    'sin_dia_año': np.sin(2 * np.pi * df['dayofyear'] / 365.25),
    'cos_dia_año': np.cos(2 * np.pi * df['dayofyear'] / 365.25),
    'sin_dia_semana': np.sin(2 * np.pi * df['dayofweek'] / 7),
    'es_fin_de_semana': df['dayofweek'].isin([5, 6]).astype(int),
    'trimestre': df['month'] // 4 + 1,
    
    # Comparación año-a-año (YoY)
    'variacion_yoy': (df['valor'] - df['valor'].shift(365)) / df['valor'].shift(365) * 100,
    
    # Rolling windows
    'ma_7d': df['valor'].rolling(7).mean(),
    'ma_30d': df['valor'].rolling(30).mean(),
    'std_14d': df['valor'].rolling(14).std(),
    
    # Lags estratégicos
    'lag_1d': df['valor'].shift(1),   # Ayer
    'lag_7d': df['valor'].shift(7),   # Misma semana pasada
    'lag_365d': df['valor'].shift(365), # Mismo día año pasado
}
```

## 2. Arquitectura de Ensemble Híbrido

### 2.1 Modelos Base (Nivel 0)

1. **LightGBM** (gradient boosting)
   - Ventaja: Maneja bien features categóricas y nulos
   - Hiperparámetros: `num_leaves=31`, `learning_rate=0.05`, `n_estimators=500`
   
2. **Prophet** (descomposición aditiva)
   - Ventaja: Captura estacionalidad multi-nivel
   - Config: `yearly_seasonality=True`, `weekly_seasonality=True`, `daily_seasonality=False`
   - Regressors: Variables exógenas

3. **N-BEATS** (neural basis expansion)
   - Ventaja: Deep learning para series temporales
   - Stacks: Trend + Seasonality blocks
   - Backcast: 365 días, Forecast: 90 días

4. **SARIMA** (baseline estadístico)
   - Ventaja: Interpretable, funciona con pocos datos
   - Auto-tuning: `auto_arima()` con `seasonal=True`, `m=7`

### 2.2 Meta-Learner (Nivel 1)

```python
# XGBoost como meta-learner
meta_features = np.column_stack([
    lgbm_preds,
    prophet_preds,
    nbeats_preds,
    sarima_preds,
    # Features adicionales para el meta-learner
    uncertainty_lgbm,  # Varianza de predicciones del modelo
    uncertainty_prophet,
    day_of_week,       # Para ponderación condicional
    is_holiday,
])

meta_model = xgb.XGBRegressor(
    n_estimators=100,
    max_depth=3,  # Shallow para evitar overfitting
    learning_rate=0.1,
    reg_alpha=1.0,  # L1 regularization
    reg_lambda=1.0,  # L2 regularization
)
```

### 2.3 Intervalos de Confianza Calibrados

En lugar de intervalos nativos de Prophet, usar **Conformal Prediction**:

```python
# Conformal Prediction (ICP)
# Garantía: P(y_real ∈ [y_lower, y_upper]) ≥ 0.95

# 1. Reservar últimos 60 días como calibration set
# 2. Entrenar modelo en training set
# 3. Calcular quantiles de errores en calibration set
# 4. Usar quantiles para construir intervalos

alpha = 0.05  # 95% cobertura
errors = np.abs(y_calib - y_pred_calib)
q_hat = np.quantile(errors, 1 - alpha)

interval_lower = y_pred - q_hat
interval_upper = y_pred + q_hat
```

## 3. Política de Confianza Revisada

| Fuente | MAPE Actual | MAPE Objetivo | Nivel Actual | Nivel Objetivo |
|--------|-------------|---------------|--------------|----------------|
| GENE_TOTAL | ~5% | <3% | MUY_CONFIABLE | MUY_CONFIABLE ✅ |
| DEMANDA | ~3.6% | <2% | MUY_CONFIABLE | MUY_CONFIABLE ✅ |
| EMBALSES_PCT | ~5% | <3% | MUY_CONFIABLE | MUY_CONFIABLE ✅ |
| **PRECIO_BOLSA** | **~40%** | **<15%** | **EXPERIMENTAL** | **CONFIABLE** 🎯 |
| APORTES_HÍDRICOS | ~25% | <15% | CONFIABLE | CONFIABLE ✅ |

### Estrategia específica para PRECIO_BOLSA:

```python
# El precio de bolsa es altamente volátil por:
# 1. Eventos de escasez (shocks de oferta)
# 2. Disponibilidad térmica
# 3. Restricciones de transmisión

# Solución: Modelo híbrido con regime detection

if disponibilidad_hidraulica < 40%:
    # Régimen de escasez - usar modelo especializado
    modelo = ensemble_escasez  # Entrenado solo en periodos de embalses bajos
    usar_features = ['embalses_pct', 'disp_termica', 'restricciones']
else:
    # Régimen normal
    modelo = ensemble_normal
    usar_features = ['demanda', 'apertes', 'precio_gas']
```

## 4. Validación y Monitoreo

### 4.1 Métricas de Evaluación

- **MAPE** (Mean Absolute Percentage Error): Error relativo
- **RMSE** (Root Mean Square Error): Penaliza outliers
- **MASE** (Mean Absolute Scaled Error): Independiente de escala
- **Cobertura**: % de valores reales dentro de intervalo de confianza
- **Sharpness**: Ancho promedio de intervalos (menor es mejor)

### 4.2 Drift Detection

```python
# Detectar cuando el modelo degrada
# PSI (Population Stability Index) entre distribución de features
# y predicciones recientes vs entrenamiento

psi = calculate_psi(features_train, features_recent)
if psi > 0.25:  # Umbral de drift significativo
    trigger_retraining = True
    alertar_equipo_ml("Drift detectado en PRECIO_BOLSA")
```

## 5. Cronograma de Implementación

| Fase | Duración | Tareas |
|------|----------|--------|
| **Fase 1.1** | 2 semanas | Pipeline de datos exógenos (IDEAM/XM) |
| **Fase 1.2** | 2 semanas | Feature engineering y validación |
| **Fase 2.1** | 3 semanas | Entrenamiento ensemble híbrido |
| **Fase 2.2** | 2 semanas | Calibración conformal y tests |
| **Fase 3** | 1 semana | Integración en producción |
| **Fase 4** | Continuo | Monitoreo y re-entrenamiento mensual |

## 6. Recursos Necesarios

- **Computación**: GPU para N-BEATS (puede usar CPU con menor tamaño)
- **Almacenamiento**: +50GB para datos históricos extendidos
- **Tiempo de cálculo**: ~2 horas para re-entrenamiento completo
- **Datos externos**: Contrato API IDEAM (gratuito para gobierno)
