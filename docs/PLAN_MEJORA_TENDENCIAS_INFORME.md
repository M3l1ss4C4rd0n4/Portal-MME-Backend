# Plan de Mejora: Análisis de Tendencias e Informe Ejecutivo

## 1. Análisis de Tendencias Actual vs Propuesto

### 1.1 Limitaciones Actuales

```python
# ACTUAL: Comparación simple 30 días
cambio_pct = ((valor_actual - promedio_30d) / promedio_30d) * 100

# PROBLEMAS:
# ❌ Ignora estacionalidad anual (demanda de enero vs julio)
# ❌ No detecta tendencias de largo plazo
# ❌ Sin descomposición (trend vs seasonal vs residual)
# ❌ No compara contra año anterior (YoY)
```

### 1.2 Sistema de Tendencias "Multi-Horizonte"

```
┌────────────────────────────────────────────────────────────────┐
│           ANÁLISIS DE TENDENCIAS MULTI-HORIZONTE               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  MICRO (1-7 días)        MESO (1-12 meses)      MACRO (1-5a)   │
│  ─────────────────       ────────────────      ────────────    │
│  • Desviación diaria     • Tendencia mensual   • Cambio        │
│  • Patrones semanales    • Estacionalidad        estructural   │
│  • Horas pico/valle      • YoY (año-a-año)     • Ciclo        │
│                                                      hidrológico│
└────────────────────────────────────────────────────────────────┘
```

## 2. Implementación: Sistema de Tendencias Avanzado

### 2.1 Descomposición STL (Trend + Seasonal + Residual)

```python
from statsmodels.tsa.seasonal import STL
import pandas as pd
import numpy as np

def analyze_trends_stl(series, period=7):
    """
    Descompone serie temporal en componentes.
    
    Args:
        series: Serie temporal con datetime index
        period: Período estacional (7=días, 30=meses, 365=años)
    
    Returns:
        Dict con tendencia, estacionalidad y análisis
    """
    # STL robusto (resistente a outliers)
    stl = STL(series, period=period, robust=True)
    result = stl.fit()
    
    # Extraer componentes
    trend = result.trend
    seasonal = result.seasonal
    residual = result.resid
    
    # Análisis de tendencia
    trend_slope = np.polyfit(range(len(trend)), trend, 1)[0]
    
    # Detectar aceleración (cambio en la pendiente)
    mid = len(trend) // 2
    slope_recent = np.polyfit(range(mid), trend[-mid:], 1)[0]
    slope_old = np.polyfit(range(mid), trend[:mid], 1)[0]
    acceleration = slope_recent - slope_old
    
    # Fuerza de estacionalidad
    seasonal_strength = 1 - np.var(residual) / np.var(seasonal + residual)
    
    # Varianza residual (ruido)
    residual_var = np.var(residual)
    
    return {
        'trend': trend,
        'seasonal': seasonal,
        'residual': residual,
        'trend_slope': trend_slope,
        'trend_acceleration': acceleration,
        'seasonal_strength': seasonal_strength,
        'residual_variance': residual_var,
        'trend_direction': 'CRECIENTE' if trend_slope > 0 else 'DECRECIENTE',
        'trend_strength': abs(trend_slope) / residual_var if residual_var > 0 else 0
    }

# Ejemplo de uso
trend_analysis = analyze_trends_stl(df['generacion'], period=7)
```

### 2.2 Comparación Year-over-Year (YoY)

```python
def calculate_yoy_comparison(series, current_date):
    """
    Compara valor actual contra mismo período del año anterior.
    
    Ejemplo: Demanda de 15 abril 2026 vs 15 abril 2025
    """
    current_value = series.loc[current_date]
    
    # Buscar fecha similar año pasado (mismo día de semana preferible)
    last_year_date = current_date - pd.DateOffset(years=1)
    
    # Ajustar si no existe fecha exacta
    if last_year_date not in series.index:
        last_year_date = series.index[series.index <= last_year_date][-1]
    
    last_year_value = series.loc[last_year_date]
    
    # Calcular YoY
    yoy_change = ((current_value - last_year_value) / last_year_value) * 100
    
    # Calcular CAGR (Compound Annual Growth Rate) si hay 2+ años de datos
    two_years_ago = current_date - pd.DateOffset(years=2)
    if two_years_ago in series.index:
        value_2y = series.loc[two_years_ago]
        cagr = ((current_value / value_2y) ** (1/2) - 1) * 100
    else:
        cagr = None
    
    return {
        'current_value': current_value,
        'last_year_value': last_year_value,
        'yoy_change_pct': yoy_change,
        'cagr_2y': cagr,
        'date_last_year': last_year_date,
        'interpretation': interpret_yoy(yoy_change)
    }

def interpret_yoy(yoy_pct):
    """
    Interpreta el cambio YoY según magnitud y dirección.
    """
    if abs(yoy_pct) < 2:
        return ('ESTABLE', 'Cambio dentro de rango normal de variabilidad')
    elif yoy_pct > 10:
        return ('CRECIMIENTO_FUERTE', 'Incremento significativo, revisar drivers')
    elif yoy_pct > 2:
        return ('CRECIMIENTO_MODERADO', 'Crecimiento saludable')
    elif yoy_pct < -10:
        return ('CAÍDA_FUERTE', 'Contracción importante, investigar causas')
    else:
        return ('CAÍDA_MODERADA', 'Contracción leve, monitorear')
```

### 2.3 Índices Compuestos

```python
def calculate_composite_indices(df):
    """
    Calcula índices compuestos que resumen múltiples métricas.
    """
    # Índice de Estrés del Sistema (0-100)
    # Combina: precio alto, embalses bajos, restricciones altas
    
    # Normalizar cada componente (0-1)
    precio_norm = min(1, max(0, (df['precio_bolsa'] - 100) / 400))
    embalses_norm = min(1, max(0, (70 - df['embalses_pct']) / 70))  # Inverso
    restricciones_norm = min(1, max(0, df['restricciones_gwh'] / 500))
    
    # Pesos según impacto
    stress_index = (
        0.4 * precio_norm +
        0.35 * embalses_norm +
        0.25 * restricciones_norm
    ) * 100
    
    # Índice de Sostenibilidad Hídrica
    # Combina: embalses, aportes, generación hidráulica %
    hidraulica_pct = df['generacion_hidraulica'] / df['generacion_total']
    sustainability = (
        0.4 * (df['embalses_pct'] / 100) +
        0.3 * (df['aportes_pct'] / 150) +  # Normalizado
        0.3 * hidraulica_pct
    ) * 100
    
    # Índice de Diversificación de Generación (Shannon Diversity)
    generacion_fuentes = [
        df['generacion_hidraulica'],
        df['generacion_termica'],
        df['generacion_solar'],
        df['generacion_eolica']
    ]
    total = sum(generacion_fuentes)
    proporciones = [g/total for g in generacion_fuentes if g > 0]
    
    # Shannon Diversity Index (0-1, 1 = máxima diversidad)
    import scipy.stats as stats
    diversity = stats.entropy(proporciones) / np.log(len(proporciones))
    
    return {
        'stress_index': stress_index,
        'sustainability_index': sustainability,
        'diversification_index': diversity * 100,
        'stress_level': 'ALTO' if stress_index > 70 else 'MEDIO' if stress_index > 40 else 'BAJO'
    }
```

## 3. Enriquecimiento del Informe Ejecutivo

### 3.1 Estructura Propuesta del Nuevo Informe

```markdown
# INFORME EJECUTIVO INTELIGENTE — Sector Eléctrico Colombiano
## Fecha: 11 de abril de 2026

═══════════════════════════════════════════════════════════════════

## 1. PANEL DE INDICADORES CLAVE (KPIs)

┌─────────────────┬──────────┬─────────────┬─────────────┬──────────┐
│ Indicador       │ Valor    │ vs 30d      │ vs Año Ant. │ Estado   │
├─────────────────┼──────────┼─────────────┼─────────────┼──────────┤
│ Generación      │ 253 GWh  │ +7.7% ▲     │ +3.2% ▲     │ 🟢 Normal│
│ Precio Bolsa    │ 301 $/kWh│ +51.2% 🔺   │ +18.5% 🔺   │ 🔴 Crítico│
│ Embalses        │ 62.3%    │ -6.9% ▼     │ +5.1% ▲     │ 🟡 Alerta│
└─────────────────┴──────────┴─────────────┴─────────────┴──────────┘

Índice de Estrés del Sistema: 58/100 (MEDIO)
Índice de Sostenibilidad Hídrica: 65/100 (ADECUADO)

═══════════════════════════════════════════════════════════════════

## 2. ANÁLISIS DE TENDENCIAS

### 2.1 Tendencia de Generación (Últimos 30 días)
```
Gráfico: Descomposición STL
- Tendencia: Ligeramente creciente (+0.5 GWh/día)
- Estacionalidad semanal: Fuerte (viernes 8% mayor)
- Ruido residual: Bajo (variabilidad controlada)
```

**Interpretación:** La generación muestra un crecimiento moderado consistente con 
el aumento de demanda por temporada seca. La estacionalidad semanal es normal, 
con picos los viernes por actividad industrial.

### 2.2 Comparación Year-over-Year

| Métrica | Actual | Abril 2025 | Cambio YoY | Interpretación |
|---------|--------|------------|------------|----------------|
| Demanda Promedio | 245 GWh | 237 GWh | +3.4% | Crecimiento sostenido |
| Precio Promedio | 220 $/kWh | 186 $/kWh | +18.3% | 🔴 Presión alcista |
| Embalses Promedio | 62% | 59% | +5.1% | Mejor situación hídrica |

**Conclusión:** El sistema está en mejor condición hídrica que el año pasado, 
pero los precios muestran presión alcista significativa (+18%). Esto sugiere 
factores no-hídricos: posiblemente costos de combustibles o restricciones.

### 2.3 Proyección de Tendencias (Próximos 30 días)

Basado en modelo de tendencia + estacionalidad:

```
Generación:     253 → 265 GWh (+4.7%, intervalo: 255-275)
Precio Bolsa:   301 → 280 $/kWh (-7%, intervalo: 240-320)
Embalses:       62% → 58% (-6%, intervalo: 55-62%)
```

**Alerta de Tendencia:** Los embalses proyectan caída adicional. Considerar 
planificación de disponibilidad térmica para mitigar riesgo de precios.

═══════════════════════════════════════════════════════════════════

## 3. DETECCIÓN DE ANOMALÍAS

### 3.1 Resumen de Eventos Detectados

🔴 **2 Anomalías Críticas** (requieren acción inmediata)
🟠 **3 Alertas** (monitoreo intensivo)
🟡 **5 Tendencias** (seguimiento regular)

### 3.2 Anomalías Destacadas

#### 🔴 CRÍTICO: Precio de Bolsa Elevado (últimos 3 días)

**Detección:** S-H-ESD detectó outlier en serie de precios
- Valor: 301 $/kWh (z-score: 2.8)
- Desviación vs tendencia: +45%
- Contexto: Disponibilidad térmica reducida (65%)

**Tipo:** Anomalía multivariada (precio↑ + disponibilidad↓)
**Duración:** Persistente (3 días consecutivos)
**Impacto estimado:** +$2.5M en costos de compra diarios

**Acción recomendada:** 
1. Verificar disponibilidad real de plantas térmicas
2. Revisar si hay ofertas estratégicas (manipulación)
3. Considerar importación de energía desde Ecuador

#### 🟠 ALERTA: Patrón de Demanda Inusual

**Detección:** Isolation Forest
- Anomalía en patrón horario (pico anticipado 2 horas)
- Correlación con temperatura: 0.92 (muy alta)

**Interpretación:** Ola de calor anticipada. Demanda por aire acondicionado 
comenzó a las 10am (normalmente 12pm).

**Acción recomendada:** Preparar unidades de respaldo rápido.

### 3.3 Análisis de Correlaciones Rotas

⚠️ **Anomalía de Correlación Detectada:**
```
Normal: Generación Hidráulica ↑ → Precio ↓ (correlación -0.7)
Actual: Generación Hidráulica ↑ → Precio ↑ (correlación +0.3)
```

**Diagnóstico:** Esto es anómalo. Posibles causas:
1. Demanda creció más rápido que oferta hidráulica
2. Restricciones de transmisión aislaron mercados regionales
3. Evento de oferta (precio alto intencional)

═══════════════════════════════════════════════════════════════════

## 4. ANÁLISIS POR FUENTE DE GENERACIÓN

### 4.1 Mix Energético Actual

```
Hidráulica:  78.5% (198 GWh)  ▲ +5% vs mes anterior
Térmica:     13.9% (35 GWh)   ▼ -8% vs mes anterior  
Solar:        6.4% (16 GWh)   ▲ +15% vs mes anterior
Eólica:       0.3% (0.6 GWh)  ▼ -20% vs mes anterior
Biomasa:      1.0% (2.4 GWh)  → Estable
```

**Análisis:** Dependencia hídrica alta (78.5%). Riesgo si llega Fenómeno El Niño.
Crecimiento solar es positivo pero aún marginal.

### 4.2 Eficiencia por Fuente

| Fuente | Factor Plant | Tendencia | Notas |
|--------|--------------|-----------|-------|
| Hidráulica | 0.45 | ↗ Mejorando | Buenos aportes hídricos |
| Térmica | 0.72 | → Estable | Gas/carbón disponibles |
| Solar | 0.18 | ↗ Mejorando | Radiación alta (temporada seca) |

═══════════════════════════════════════════════════════════════════

## 5. ESCENARIOS Y PROYECCIONES

### 5.1 Escenario Base (60% probabilidad)
Condiciones meteorológicas normales, mantenimientos programados.

**Proyección mes próximo:**
- Generación: 7,800 GWh (+4% vs mes actual)
- Precio promedio: 240 $/kWh (-20% vs actual)
- Embalses: 55% al final del mes

### 5.2 Escenario Riesgo (30% probabilidad)
Menores aportes hídricos, retraso en mantenimientos térmicos.

**Proyección mes próximo:**
- Generación: 7,200 GWh (-4% vs mes actual)
- Precio promedio: 350 $/kWh (+16% vs actual) 🔴
- Embalses: 48% al final del mes 🔴

**Acciones preventivas:**
1. Adelantar compras de combustible
2. Negociar contratos bilaterales a precio fijo
3. Preparar campaña de ahorro energético

### 5.3 Escenario Óptimo (10% probabilidad)
Buenos aportes hídricos, sin restricciones.

**Proyección:** Precios < 200 $/kWh, embalses > 60%.

═══════════════════════════════════════════════════════════════════

## 6. RECOMENDACIONES ESTRATÉGICAS

### Corto Plazo (1-7 días)
1. ⚠️ **URGENTE:** Investigar precios elevados de bolsa
2. 📊 Monitorear embalses diariamente (tendencia decreciente)
3. 🔧 Verificar disponibilidad térmica real vs programada

### Mediano Plazo (1-3 meses)
1. 💧 Planificar uso estratégico de reservas hídricas
2. ⚡ Evaluar necesidad de importaciones de energía
3. 📈 Acelerar proyectos solares (crecimiento prometedor)

### Largo Plazo (3-12 meses)
1. 🌊 Preparación para Fenómeno El Niño (probabilidad 70%)
2. 🔄 Diversificar mix: Meta 70% renovables 2030
3. 🤖 Implementar sistema de predicción de precios en tiempo real

═══════════════════════════════════════════════════════════════════

## 7. ANEXOS TÉCNICOS

### A. Metodología de Predicciones
- Modelo: Ensemble (Prophet + LightGBM + SARIMA)
- Validación: Temporal CV (holdout 30 días)
- MAPE promedio: 8.5% (rango: 3-15% por métrica)
- Intervalos: Conformal Prediction (95% cobertura)

### B. Metodología de Anomalías
- Método: S-H-ESD + Isolation Forest + Autoencoder
- Entrenamiento: 3 años históricos
- Falsos positivos: < 5%
- Detección multivariada: Correlaciones hasta 6 variables

### C. Fuentes de Datos
- XM S.A. (generación, precios, restricciones)
- IDEAM (precipitación, temperatura)
- UPME (demanda, proyecciones)
- NASA POWER (radiación solar)

═══════════════════════════════════════════════════════════════════

*Informe generado por Sistema de Análisis Inteligente MME v2.0*
*Fecha de generación: 2026-04-11 08:00:00*
*Próxima actualización: 2026-04-12 08:00:00*
```

## 4. Implementación Técnica

### 4.1 Clase de Análisis de Tendencias

```python
class TendenciaAnalyzer:
    """
    Sistema completo de análisis de tendencias.
    """
    
    def __init__(self, data):
        self.data = data
        self.results = {}
    
    def analizar_completo(self):
        """
        Ejecuta análisis completo de tendencias.
        """
        self.results = {
            'stl': self._analisis_stl(),
            'yoy': self._comparacion_yoy(),
            'indices': self._calcular_indices(),
            'proyeccion': self._proyectar_30dias(),
            'interpretacion': self._generar_interpretacion()
        }
        return self.results
    
    def _generar_interpretacion(self):
        """
        Genera texto narrativo del análisis (para IA o directo).
        """
        partes = []
        
        # Tendencia principal
        if self.results['stl']['trend_direction'] == 'CRECIENTE':
            if self.results['stl']['trend_acceleration'] > 0:
                partes.append("tendencia fuertemente creciente con aceleración")
            else:
                partes.append("tendencia creciente pero estabilizándose")
        else:
            partes.append("tendencia decreciente")
        
        # Estacionalidad
        if self.results['stl']['seasonal_strength'] > 0.5:
            partes.append("fuerte componente estacional")
        
        # Comparación año anterior
        if self.results['yoy']['yoy_change_pct'] > 5:
            partes.append(f"significativamente mayor que el año pasado (+{self.results['yoy']['yoy_change_pct']:.1f}%)")
        
        return "La serie muestra " + ", ".join(partes) + "."
```

## 5. Cronograma de Implementación

| Fase | Semanas | Entregable |
|------|---------|------------|
| 1. STL + YoY | 2 | Módulo de descomposición temporal |
| 2. Índices compuestos | 1 | Sistema de índices de estrés/sostenibilidad |
| 3. Proyecciones de tendencia | 2 | Proyección 30 días con intervalos |
| 4. Enriquecimiento informe | 2 | Nuevo formato de informe ejecutivo |
| 5. Integración | 1 | Sistema completo en producción |

## 6. Métricas de Éxito

- ✅ Informe generado en < 60 segundos
- ✅ Proyecciones con MAPE < 10%
- ✅ Cobertura de intervalos > 90%
- ✅ Falsos positivos en anomalías < 5%
- ✅ Satisfacción usuario (encuesta) > 4.5/5
