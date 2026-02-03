# 🚦 Sistema de Semáforo de Riesgos - Guía de Implementación

## 📋 Resumen

Este README describe la implementación técnica del **Sistema de Semáforo de Riesgos** para el análisis hidrológico del Dashboard del MME. El sistema clasifica automáticamente los embalses según su nivel de riesgo operativo usando colores tipo semáforo.

## 🎯 Objetivos

- **Identificación Visual Inmediata**: Los ingenieros pueden ver de un vistazo qué embalses requieren atención
- **Priorización Automática**: Sistema objetivo para toma de decisiones operativas
- **Reducción de Riesgos**: Detección temprana de situaciones críticas
- **Comunicación Efectiva**: Lenguaje visual universal para equipos técnicos

## 🔧 Implementación Técnica

### 📊 Algoritmo de Clasificación

```python
def clasificar_riesgo_embalse(participacion, volumen_util):
    """
    Matriz de riesgo basada en:
    - Participación: Importancia del embalse en el sistema (%)
    - Volumen Útil: Disponibilidad actual de agua (%)
    """
    # Regla prioritaria: >70% volumen = siempre verde
    if volumen_util >= 70:
        return 'low'
    
    # Matriz de riesgo por importancia
    if participacion >= 15:        # Embalses críticos
        if volumen_util < 30: return 'high'
        elif volumen_util < 50: return 'medium'
    elif participacion >= 10:      # Embalses importantes  
        if volumen_util < 20: return 'high'
        elif volumen_util < 40: return 'medium'
    elif participacion >= 5:       # Embalses relevantes
        if volumen_util < 15: return 'high'
        elif volumen_util < 35: return 'medium'
    else:                          # Embalses complementarios
        if volumen_util < 25: return 'medium'
    
    return 'low'
```

### 🎨 Código de Colores

| **Nivel** | **Color** | **Fondo** | **Texto** | **Criterio** |
|-----------|-----------|-----------|-----------|--------------|
| 🔴 Alto | `#fee2e2` | Rojo claro | `#991b1b` | Embalses importantes + bajo volumen |
| 🟡 Medio | `#fef3c7` | Amarillo claro | `#92400e` | Situación de precaución |
| 🟢 Bajo | `#d1fae5` | Verde claro | `#065f46` | Estado óptimo |

### 📈 Matriz de Riesgo Completa

| **Participación** | **Vol < 15%** | **Vol 15-25%** | **Vol 25-35%** | **Vol 35-50%** | **Vol 50-70%** | **Vol ≥ 70%** |
|-------------------|---------------|----------------|----------------|----------------|----------------|----------------|
| **≥ 20%** | 🔴 CRÍTICO | 🔴 ALTO | 🟡 MEDIO | 🟡 MEDIO | 🟡 PRECAUCIÓN | 🟢 ÓPTIMO |
| **15-20%** | 🔴 ALTO | 🔴 ALTO | 🟡 MEDIO | 🟡 MEDIO | 🟡 PRECAUCIÓN | 🟢 ÓPTIMO |
| **10-15%** | 🔴 ALTO | 🟡 MEDIO | 🟡 MEDIO | 🟡 MEDIO | 🟢 BAJO | 🟢 ÓPTIMO |
| **5-10%** | 🔴 ALTO | 🟡 MEDIO | 🟡 MEDIO | 🟢 BAJO | 🟢 BAJO | 🟢 ÓPTIMO |
| **< 5%** | 🟡 MEDIO | 🟡 MEDIO | 🟢 BAJO | 🟢 BAJO | 🟢 BAJO | 🟢 ÓPTIMO |

## 💻 Integración en Dash DataTable

### 🔄 Proceso de Aplicación

1. **Cálculo por Embalse**: Para cada embalse se obtiene participación y volumen útil
2. **Clasificación**: Se aplica el algoritmo de riesgo
3. **Estilo Dinámico**: Se genera estilo CSS específico por fila
4. **Aplicación Visual**: Se agrega a `style_data_conditional` de DataTable

### 📝 Código de Integración

```python
# En build_hierarchical_table_view()
for embalse in embalses:
    # ... obtener datos del embalse ...
    
    # Clasificar riesgo
    nivel_riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val)
    
    # Agregar fila
    row_index = len(table_data)
    table_data.append({
        "nombre": f"    └─ {embalse_name}",
        "valor": valor_embalse
    })
    
    # Aplicar estilo de semáforo
    estilo = obtener_estilo_riesgo(nivel_riesgo)
    style_data_conditional.append({
        'if': {'row_index': row_index},
        **estilo
    })
```

## 🎯 Casos de Uso por Nivel

### 🔴 **RIESGO ALTO - Acción Inmediata**
```
Ejemplo: AGREGADO BOGOTA (65% participación, 25% volumen)
Acciones:
✅ Activar plantas térmicas de respaldo
✅ Monitoreo horario de niveles
✅ Restricciones de demanda no esencial
✅ Comunicación a autoridades
```

### 🟡 **RIESGO MEDIO - Monitoreo Intensivo**
```
Ejemplo: BETANIA (15% participación, 45% volumen)
Acciones:
🔍 Seguimiento diario detallado
🔍 Preparar medidas preventivas
🔍 Revisar proyecciones de aportes
🔍 Evaluar transferencias entre embalses
```

### 🟢 **RIESGO BAJO - Operación Normal**
```
Ejemplo: AMANI (5% participación, 92% volumen)
Acciones:
📊 Monitoreo rutinario
📊 Aprovechamiento para mantenimientos
📊 Posible soporte a otros embalses
```

## 📊 Métricas del Sistema

### 🔢 **Indicadores Automáticos**

1. **Porcentaje de Capacidad en Riesgo**:
   ```
   % Riesgo Alto = (Σ Capacidad Embalses Rojos / Capacidad Total) × 100
   ```

2. **Índice de Salud del Sistema**:
   ```
   Salud = (% Verde × 1 + % Amarillo × 0.5 + % Rojo × 0) / 100
   ```

3. **Factor de Riesgo Ponderado**:
   ```
   Factor = (% Rojo × 3 + % Amarillo × 2 + % Verde × 1) / 100
   ```

### 🚨 **Alertas Automáticas**

| **Nivel** | **Condición** | **Acción** |
|-----------|---------------|------------|
| 🔴 **CRÍTICO** | >30% capacidad en rojo | Activar protocolo de crisis |
| 🟠 **ALTO** | >50% capacidad en amarillo/rojo | Alerta a operadores |
| 🟡 **MEDIO** | Embalses >15% participación en amarillo | Monitoreo reforzado |

## 🛠️ Personalización y Ajustes

### ⚙️ **Parámetros Configurables**

```python
# Umbrales de volumen útil
UMBRAL_CRITICO = 15    # Porcentaje crítico
UMBRAL_BAJO = 25       # Porcentaje de precaución  
UMBRAL_MEDIO = 50      # Porcentaje aceptable
UMBRAL_OPTIMO = 70     # Porcentaje óptimo

# Umbrales de participación
PARTICIPACION_CRITICA = 15   # Embalses críticos
PARTICIPACION_IMPORTANTE = 10  # Embalses importantes
PARTICIPACION_RELEVANTE = 5    # Embalses relevantes
```

### 🎨 **Personalización Visual**

```python
# Modificar colores en obtener_estilo_riesgo()
COLORES_PERSONALIZADOS = {
    'high': {
        'backgroundColor': '#tu_color_rojo',
        'color': '#tu_texto_rojo'
    },
    # ... otros colores
}
```

## 📚 Documentación Adicional

- **Análisis Completo**: Ver `ANALISIS_HIDROLOGIA_SEMAFORO.md`
- **API XM**: Documentación técnica de métricas
- **Casos de Estudio**: Ejemplos históricos de aplicación

## 👥 Equipo de Desarrollo

**Desarrollado por**: Equipo de Digitalización - MME  
**Fecha**: Septiembre 2025  
**Versión**: 1.0  
**Estado**: Producción

---

*Este sistema representa un avance significativo en la gestión inteligente de recursos hídricos para el sector energético colombiano.*
