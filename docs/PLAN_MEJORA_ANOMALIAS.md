# Plan de Mejora: Sistema Avanzado de Detección de Anomalías

## 1. Limitaciones del Sistema Actual

### 1.1 Problemas Identificados

```python
# ACTUAL (Simplificado)
desviacion = abs(valor_actual - promedio_30d) / promedio_30d
if desviacion > umbral:
    es_anomalia = True

# LIMITACIONES:
# ❌ No considera estacionalidad (ej: demanda en diciembre siempre es alta)
# ❌ Umbral fijo para todas las métricas (precio es más volátil que generación)
# ❌ Solo compara contra 30 días (no contra histórico multi-anual)
# ❌ No diferencia entre anomalía puntual vs cambio de régimen
# ❌ Sin contexto multivariado (ej: si generación sube pero embalses bajan)
```

### 1.2 Falsos Positivos y Negativos

| Tipo | Ejemplo | Impacto |
|------|---------|---------|
| **Falso Positivo** | Demanda de diciembre marcada como "crítica" por ser 30% mayor que noviembre | Alerta innecesaria, fatiga de alertas |
| **Falso Negativo** | Precio de bolsa sube 50% pero coincide con pico de demanda (no se detecta como anomalía) | No se alerta sobre estrés de mercado real |

## 2. Arquitectura Propuesta: "Anomaly Detection Contextual"

### 2.1 Componentes Principales

```
┌────────────────────────────────────────────────────────────────────┐
│              CAPA 1: DETECCIÓN UNIVARIADA (por métrica)             │
├────────────────────────────────────────────────────────────────────┤
│  Método A: Seasonal Hybrid ESD (S-H-ESD)                           │
│  - Detecta outliers robustos considerando estacionalidad           │
│  - Usa descomposición STL (Seasonal-Trend-Residual)                │
│  - Aplica Generalized ESD en residuales                            │
│                                                                    │
│  Método B: Isolation Forest con features temporales               │
│  - Entrenado en histórico 3 años                                   │
│  - Features: día_semana, mes, lag_1, lag_7, ma_7                   │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│           CAPA 2: DETECCIÓN MULTIVARIADA (sistema)                  │
├────────────────────────────────────────────────────────────────────┤
│  Método C: Autoencoder + Mahalanobis Distance                      │
│  - Input: [generacion, demanda, precio, embalses, temp]           │
│  - Reconstrucción error → anomalía multivariada                    │
│  - Captura correlaciones rotas (ej: gen↑ + precio↑ = anómalo)      │
│                                                                    │
│  Método D: CUSUM Multivariado (cambios de régimen)                │
│  - Detecta cambios persistentes (no outliers puntuales)            │
│  - Útil para detectar inicio de fenómeno El Niño, etc.             │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│              CAPA 3: CLASIFICACIÓN Y PRIORIZACIÓN                   │
├────────────────────────────────────────────────────────────────────┤
│  • Tipo de anomalía:                                               │
│    - Puntual (1 día): Revisar dato/operación                       │
│    - Persistente (>3 días): Cambio estructural                     │
│    - Cambio de régimen (>7 días): Revisar política                 │
│                                                                    │
│  • Severidad ajustada por contexto:                                │
│    - Crítico: Impacta seguridad energética                         │
│    - Alto: Impacta precio significativamente                       │
│    - Medio: Desviación operativa normal                            │
│    - Informativo: Tendencia a monitorear                           │
└────────────────────────────────────────────────────────────────────┘
```

## 3. Implementación Técnica

### 3.1 Método A: S-H-ESD (Seasonal Hybrid ESD)

```python
from statsmodels.tsa.seasonal import STL
from scipy import stats

def detect_anomalies_shesd(series, period=7, alpha=0.05, max_outliers=10):
    """
    Seasonal Hybrid ESD Test
    
    1. Descompone serie en trend + seasonal + residual
    2. Aplica ESD test en residuales
    3. Retorna índices de anomalías
    """
    # Descomposición STL (robusta a outliers)
    stl = STL(series, period=period, robust=True)
    result = stl.fit()
    
    # Trabajar con residuales
    residuals = result.resid
    
    # Generalized ESD test
    outliers = []
    n = len(residuals)
    
    for i in range(1, max_outliers + 1):
        # Calcular estadístico de Grubbs
        mean_r = residuals.mean()
        std_r = residuals.std()
        
        if std_r == 0:
            break
            
        # Encontrar máximo residual estandarizado
        max_idx = np.argmax(np.abs(residuals - mean_r))
        max_val = residuals.iloc[max_idx]
        g_stat = np.abs(max_val - mean_r) / std_r
        
        # Valor crítico
        p = 1 - alpha / (2 * (n - i + 1))
        t_val = stats.t.ppf(p, n - i - 1)
        critical_val = ((n - i) * t_val) / np.sqrt((n - i - 1 + t_val**2) * (n - i + 1))
        
        if g_stat > critical_val:
            outliers.append(max_idx)
            # Remover outlier para siguiente iteración
            residuals.iloc[max_idx] = np.nan
        else:
            break
    
    return outliers
```

### 3.2 Método B: Isolation Forest con Features Temporales

```python
from sklearn.ensemble import IsolationForest

def build_anomaly_detector(historical_data):
    """
    Entrena detector de anomalías basado en Isolation Forest
    con features temporales enriquecidas.
    """
    # Feature engineering
    df = historical_data.copy()
    df['day_of_week'] = df.index.dayofweek
    df['month'] = df.index.month
    df['day_of_year'] = df.index.dayofyear
    df['lag_1'] = df['value'].shift(1)
    df['lag_7'] = df['value'].shift(7)
    df['ma_7'] = df['value'].rolling(7).mean()
    df['std_14'] = df['value'].rolling(14).std()
    
    # Variables cíclicas (mejor que categóricas para ML)
    df['sin_day'] = np.sin(2 * np.pi * df['day_of_year'] / 365.25)
    df['cos_day'] = np.cos(2 * np.pi * df['day_of_year'] / 365.25)
    
    # Limpiar NaN
    df = df.dropna()
    
    features = [
        'day_of_week', 'month', 'sin_day', 'cos_day',
        'lag_1', 'lag_7', 'ma_7', 'std_14'
    ]
    
    # Isolation Forest
    # contamination: proporción esperada de anomalías (1-5% típico)
    model = IsolationForest(
        n_estimators=100,
        contamination=0.02,  # Esperamos ~2% de anomalías
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(df[features])
    
    return model, features

# Uso en producción
def score_anomaly(model, features, current_data):
    """
    Retorna score de anomalía (-1 = anomalía, 1 = normal)
    """
    score = model.decision_function(current_data[features])[0]
    is_anomaly = model.predict(current_data[features])[0] == -1
    
    # Convertir a probabilidad aproximada (0 a 1)
    # score típicamente en [-0.5, 0.5]
    anomaly_prob = 1 - (score + 0.5)  # Normalización aproximada
    
    return {
        'is_anomaly': is_anomaly,
        'anomaly_score': score,
        'anomaly_probability': max(0, min(1, anomaly_prob))
    }
```

### 3.3 Método C: Autoencoder Multivariado

```python
import torch
import torch.nn as nn

class AnomalyAutoencoder(nn.Module):
    """
    Autoencoder para detección de anomalías multivariadas.
    Input: [generacion, demanda, precio, embalses, temp, aportes]
    """
    def __init__(self, input_dim=6, encoding_dim=3):
        super().__init__()
        
        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(8, encoding_dim),
            nn.ReLU()
        )
        
        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(encoding_dim, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim)
        )
    
    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded
    
    def reconstruction_error(self, x):
        """Error de reconstrucción = anomalía"""
        reconstructed = self.forward(x)
        error = torch.mean((x - reconstructed) ** 2, dim=1)
        return error

# Uso
def detect_multivariate_anomaly(model, data_point, threshold_percentile=95):
    """
    Detecta anomalías usando error de reconstrucción.
    """
    with torch.no_grad():
        error = model.reconstruction_error(data_point).item()
    
    # Comparar contra distribución histórica de errores
    # (pre-calculada durante entrenamiento)
    is_anomaly = error > threshold_percentile
    
    return {
        'reconstruction_error': error,
        'is_anomaly': is_anomaly,
        'threshold': threshold_percentile
    }
```

### 3.4 Método D: CUSUM Multivariado (Cambios de Régimen)

```python
def cusum_multivariate(data, k=0.5, h=5):
    """
    CUSUM (Cumulative Sum Control Chart) multivariado.
    Detecta cambios persistentes, no outliers puntuales.
    
    Args:
        k: Allowance parameter (sensibilidad)
        h: Decision interval (umbral de alerta)
    """
    n = len(data)
    s_pos = np.zeros(n)
    s_neg = np.zeros(n)
    
    # Media histórica
    mu = np.mean(data[:30])  # Primeros 30 días como baseline
    sigma = np.std(data[:30])
    
    # Normalizar
    z = (data - mu) / sigma
    
    # CUSUM
    for i in range(1, n):
        s_pos[i] = max(0, s_pos[i-1] + z[i] - k)
        s_neg[i] = max(0, s_neg[i-1] - z[i] - k)
    
    # Detectar cambios
    change_points = []
    for i in range(n):
        if s_pos[i] > h or s_neg[i] > h:
            change_points.append(i)
    
    return {
        'positive_cusum': s_pos,
        'negative_cusum': s_neg,
        'change_points': change_points,
        'regime_shift': len(change_points) > 0
    }
```

## 4. Sistema de Severidad Contextual

### 4.1 Matriz de Severidad Ajustada

```python
SEVERITY_MATRIX = {
    'Generación Total': {
        'base_thresholds': {'alerta': 10, 'critico': 25},
        'context_adjustments': {
            'embalses_bajos': {'threshold_factor': 0.7, 'reason': 'Sistema vulnerable'},
            'restricciones_altas': {'threshold_factor': 0.8, 'reason': 'Menor flexibilidad'},
        }
    },
    'Precio de Bolsa': {
        'base_thresholds': {'alerta': 20, 'critico': 40},
        'context_adjustments': {
            'disponibilidad_baja': {'threshold_factor': 0.6, 'reason': 'Mercado tenso'},
            'escasez_programada': {'threshold_factor': 0.5, 'reason': 'Evento conocido'},
        }
    },
    'Embalses': {
        'base_thresholds': {'alerta': 10, 'critico': 25},
        'context_adjustments': {
            'temporada_seca': {'threshold_factor': 1.3, 'reason': 'Comportamiento esperado'},
            'fenomeno_nino': {'threshold_factor': 0.6, 'reason': 'Condición extrema'},
        }
    }
}

def calculate_contextual_severity(metric, deviation_pct, context):
    """
    Calcula severidad considerando contexto operativo.
    """
    config = SEVERITY_MATRIX[metric]
    thresholds = config['base_thresholds'].copy()
    reasons = []
    
    # Ajustar umbrales según contexto
    for condition, adjustment in config['context_adjustments'].items():
        if context.get(condition, False):
            factor = adjustment['threshold_factor']
            thresholds['alerta'] *= factor
            thresholds['critico'] *= factor
            reasons.append(adjustment['reason'])
    
    # Determinar severidad
    if deviation_pct > thresholds['critico']:
        severity = 'CRÍTICO'
    elif deviation_pct > thresholds['alerta']:
        severity = 'ALERTA'
    else:
        severity = 'NORMAL'
    
    return {
        'severity': severity,
        'adjusted_thresholds': thresholds,
        'context_reasons': reasons,
        'raw_deviation': deviation_pct
    }
```

### 4.2 Clasificación por Duración

```python
def classify_anomaly_type(anomaly_history):
    """
    Clasifica anomalía según duración y patrón.
    """
    n_days = len(anomaly_history)
    
    if n_days == 1:
        return {
            'type': 'PUNTUAL',
            'action': 'Verificar dato fuente',
            'priority': 'Baja'
        }
    elif n_days <= 3:
        return {
            'type': 'TRANSITORIA',
            'action': 'Monitorear evolución',
            'priority': 'Media'
        }
    elif n_days <= 7:
        return {
            'type': 'PERSISTENTE',
            'action': 'Investigar causa operativa',
            'priority': 'Alta'
        }
    else:
        return {
            'type': 'CAMBIO_DE_RÉGIMEN',
            'action': 'Revisar políticas/planificación',
            'priority': 'Crítica'
        }
```

## 5. Integración con Informe Ejecutivo

### 5.1 Nuevas Secciones del Informe

```markdown
## 3. Análisis de Anomalías Detectadas

### 3.1 Resumen Ejecutivo
- Total anomalías: 5 (2 críticas, 3 alertas)
- Tendencia: ↑ Aumento vs semana anterior (+2)
- Patrón dominante: Anomalías en precio durante horas pico

### 3.2 Detalle por Tipo

🔴 CRÍTICO — Precio de Bolsa (ayer, 16:00)
- Valor: 450 COP/kWh (+80% vs promedio)
- Contexto: Disponibilidad térmica 60%, restricciones en zona Caribe
- Tipo: PUNTUAL (duró 2 horas)
- Acción recomendada: Verificar si fue oferta estratégica o falla real

🟠 ALERTA — Generación Total (últimos 3 días)
- Valor promedio: 280 GWh (+12% vs 30d)
- Contexto: Embalses recuperándose (62%), aprovechando agua
- Tipo: PERSISTENTE
- Acción recomendada: Monitorear uso de reservas hídricas

### 3.3 Correlaciones Detectadas
⚠️ Anomalía multivariada: Generación↑ + Precio↑ (día 2026-04-08)
- Esto es inusual (normalmente son inversas)
- Posible causa: Demanda muy alta por ola de calor

### 3.4 Proyección de Riesgos
Basado en modelo CUSUM: Se detecta cambio de régimen en embalses
- Probabilidad de déficit hídrico: 35% (próximas 4 semanas)
- Recomendación: Acelerar mantenimientos térmicos programados
```

## 6. Cronograma

| Semana | Actividad | Entregable |
|--------|-----------|------------|
| 1-2 | Implementar S-H-ESD | Módulo de detección univariada |
| 3-4 | Implementar Isolation Forest | Detector con features temporales |
| 5-6 | Implementar Autoencoder | Detección multivariada |
| 7-8 | Integración y calibración | Sistema ensemble de anomalías |
| 9 | Pruebas y ajuste | Reducción de falsos positivos >30% |
| 10 | Despliegue | Nuevo sistema en producción |
