# 📊 Análisis Hidrológico y Sistema de Semáforo de Riesgos

## 🎯 Resumen Ejecutivo

Este documento explica el sistema de análisis hidrológico implementado en el Dashboard del Ministerio de Minas y Energía, incluyendo el **Sistema de Semáforo de Riesgos** para la evaluación automática del estado operativo de los embalses del Sistema Interconectado Nacional (SIN).

---

## 📋 1. FUENTES DE DATOS Y MÉTRICAS

### 🔌 **API XM - Fuente Principal**
El sistema consulta la API del XM (eXperto en Mercados) para obtener datos en tiempo real:

| **Métrica API** | **Código** | **Descripción** | **Unidad** |
|-----------------|------------|-----------------|------------|
| Capacidad Útil Diaria | `CapaUtilDiarEner` | Energía máxima que puede generar cada embalse diariamente | GWh |
| Volumen Útil Diario | `PorcVoluUtilDiar` | Porcentaje del volumen almacenado por encima del Nivel Mínimo Técnico | % |
| Aportes Energéticos | `PorcApor` | Porcentaje de aportes de caudal por río | % |
| Listado de Embalses | `ListadoEmbalses` | Información de regiones y características técnicas | N/A |

### 🏞️ **Regiones Hidroeléctricas**
- **Centro**: AGREGADO BOGOTA, EL QUIMBO, MUÑA, SAN CARLOS, TOMINÉ
- **Antioquia**: RIOGRANDE2, PLAYAS, MIRAFLORES, LA FE, PORCE3, PORCE2
- **Oriente**: CHIVOR, GUAVIO
- **Valle**: SALVAJINA, CALIMA1
- **Caldas**: MIEL1
- **Caribe**: URRA1

---

## 📊 2. ESTRUCTURA DE LAS TABLAS

### � **Interpretación del Semáforo de Colores**

**Antes de revisar las tablas, es importante entender qué significa cada color:**

#### 🔴 **ROJO - RIESGO ALTO**
```
"¡Atención! Este embalse es importante para el país y se está quedando sin agua"

• Situación: Embalses críticos con poca agua disponible
• Impacto: Riesgo inmediato de déficit energético nacional
• Acciones: Activar plantas térmicas, restricciones de consumo, monitoreo cada 6 horas
```

#### 🟡 **AMARILLO - RIESGO MEDIO**  
```
"Precaución. Este embalse necesita vigilancia especial"

• Situación: Embalses en estado de alerta temprana
• Impacto: Presión en reservas energéticas del sistema
• Acciones: Monitoreo intensivo, preparar medidas preventivas, optimizar despacho
```

#### 🟢 **VERDE - RIESGO BAJO**
```
"Todo bien. Este embalse está en condiciones normales"

• Situación: Estado operativo óptimo o embalses pequeños
• Impacto: Contribución estable al sistema energético
• Acciones: Monitoreo rutinario, aprovechar para mantenimientos
```

### �🔄 **Tabla Izquierda: "Participación Porcentual (%)"**

**Objetivo**: Mostrar la importancia relativa de cada embalse en el sistema energético nacional.

#### 📐 **Fórmula de Cálculo:**
```
Participación_Embalse = (Capacidad_Embalse_GWh / Total_Sistema_GWh) × 100

Donde:
- Capacidad_Embalse_GWh = Valor de CapaUtilDiarEner para el embalse
- Total_Sistema_GWh = Suma de todos los embalses del sistema
- Restricción: Σ Participación = 100.00% (exacto)
```

#### 🔧 **Proceso Técnico:**
1. **Obtención**: Consulta `CapaUtilDiarEner` para todos los embalses
2. **Agrupación**: Suma por nombre de embalse (múltiples registros → valor único)
3. **Cálculo**: Aplicación de fórmula de participación porcentual
4. **Ajuste**: Corrección de redondeo para garantizar suma exacta de 100%
5. **Ordenamiento**: De mayor a menor participación

#### 📈 **Interpretación:**
- **>20%**: Embalses críticos para el sistema
- **10-20%**: Embalses importantes
- **5-10%**: Embalses relevantes
- **<5%**: Embalses complementarios

### 🌊 **Tabla Derecha: "Volumen Útil (%)"**

**Objetivo**: Mostrar el estado operativo actual y la disponibilidad energética real.

#### 📊 **Columnas:**

**1. Capacidad Útil Diaria (GWh):**
- **Fuente**: `CapaUtilDiarEner` (mismo que tabla izquierda)
- **Procesamiento**: Formateo con separadores de miles
- **Interpretación**: Potencial energético máximo diario

**2. Volumen Útil (%):**
- **Fuente**: `PorcVoluUtilDiar`
- **Procesamiento**: `Valor_API × 100` (conversión decimal a porcentaje)
- **Interpretación**: Disponibilidad real de agua para generación

#### 🎯 **Significado del Volumen Útil:**
```
Volumen Útil = ((Nivel_Actual - Nivel_Mínimo_Técnico) / (Nivel_Máximo - Nivel_Mínimo_Técnico)) × 100

Interpretación:
- 100%: Embalse al máximo nivel útil
- 50%: Embalse a la mitad de su capacidad útil
- 0%: Embalse en nivel mínimo técnico (crítico)
```

---

## 🚨 3. SISTEMA DE SEMÁFORO DE RIESGOS

### 🧠 **¿Cómo Funciona la Lógica del Semáforo?**

El semáforo de riesgos es un **sistema inteligente de alerta temprana** que evalúa automáticamente el estado operativo de cada embalse del Sistema Interconectado Nacional (SIN). 

#### 🔑 **Principio Fundamental:**
```
RIESGO = f(IMPORTANCIA_DEL_EMBALSE, DISPONIBILIDAD_DE_AGUA)

Donde:
- IMPORTANCIA = Participación porcentual en el sistema (%)
- DISPONIBILIDAD = Volumen útil disponible (%)
```

#### 🎯 **Filosofía del Sistema:**
- **Embalse importante + Poca agua** = 🔴 **RIESGO ALTO**
- **Embalse mediano + Agua moderada** = 🟡 **RIESGO MEDIO** 
- **Embalse con suficiente agua** = 🟢 **RIESGO BAJO**

### 🔄 **Tabla Izquierda: "Participación Porcentual (%)"**

**Objetivo**: Mostrar la importancia relativa de cada embalse en el sistema energético nacional.

### 🔬 **Análisis Paso a Paso:**

#### **Paso 1: Evaluar la Importancia del Embalse**
```
• Participación ≥ 15% → Embalse CRÍTICO para el sistema
• Participación 10-15% → Embalse IMPORTANTE 
• Participación 5-10% → Embalse RELEVANTE
• Participación < 5% → Embalse COMPLEMENTARIO
```

#### **Paso 2: Evaluar la Disponibilidad de Agua**
```
• Volumen ≥ 70% → ABUNDANTE agua disponible
• Volumen 50-70% → ADECUADA cantidad de agua
• Volumen 30-50% → MODERADA cantidad de agua
• Volumen < 30% → ESCASA agua disponible
```

#### **Paso 3: Aplicar la Matriz de Riesgo**
El algoritmo combina ambas variables usando la siguiente lógica:

```python
if volumen_util >= 70:
    return VERDE  # Siempre verde si hay abundante agua
elif participacion >= 15 and volumen_util < 30:
    return ROJO   # Embalse crítico con poca agua
elif participacion >= 10 and volumen_util < 20:
    return ROJO   # Embalse importante con muy poca agua
# ... más condiciones según la matriz
```

### 🎨 **Metodología de Clasificación**

El sistema evalúa el riesgo combinando **participación en el sistema** y **volumen útil disponible**, aplicando una matriz de riesgo:

#### 🔴 **RIESGO ALTO (ROJO)**
```
Condiciones (se evalúan en orden, primera que aplique):
1. Participación ≥ 15% AND Volumen < 30%
2. Participación ≥ 10% AND Volumen < 20%
3. Participación ≥ 5% AND Volumen < 15%

Interpretación:
- Embalses importantes con muy poca agua disponible
- Riesgo inmediato de afectación al suministro energético
- Requiere acción correctiva inmediata
```

#### 🟡 **RIESGO MEDIO (AMARILLO)**
```
Condiciones (se evalúan en orden, primera que aplique):
1. Participación ≥ 15% AND Volumen 30-49.99%
2. Participación ≥ 10% AND Volumen 20-39.99%
3. Participación ≥ 5% AND Volumen 15-34.99%
4. Participación < 5% AND Volumen < 25%

Interpretación:
- Embalses en estado de precaución
- Monitoreo intensivo requerido
- Preparación de medidas preventivas
```

#### 🟢 **RIESGO BAJO (VERDE)**
```
Condiciones (se evalúan en orden, primera que aplique):
1. Volumen ≥ 70% (independiente de participación)
2. Participación ≥ 15% AND Volumen 50-69.99%
3. Participación ≥ 10% AND Volumen 40-69.99%
4. Participación ≥ 5% AND Volumen 35-69.99%
5. Participación < 5% AND Volumen ≥ 25%

Interpretación:
- Estado operativo óptimo
- Contribución estable al sistema
- Monitoreo rutinario
```

### 📊 **Matriz de Riesgo Detallada**

| **Participación (%)** | **Volumen < 15%** | **Volumen 15-19.99%** | **Volumen 20-24.99%** | **Volumen 25-29.99%** | **Volumen 30-34.99%** | **Volumen 35-39.99%** | **Volumen 40-49.99%** | **Volumen 50-69.99%** | **Volumen ≥ 70%** |
|-----------------------|-------------------|------------------------|------------------------|------------------------|------------------------|------------------------|------------------------|------------------------|-------------------|
| **≥ 15%** | 🔴 **ALTO** | 🔴 **ALTO** | � **ALTO** | 🔴 **ALTO** | �🟡 **MEDIO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟢 **BAJO** | 🟢 **BAJO** |
| **10-14.99%** | 🔴 **ALTO** | 🔴 **ALTO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟡 **MEDIO** | � **MEDIO** | �🟢 **BAJO** | 🟢 **BAJO** | 🟢 **BAJO** |
| **5-9.99%** | 🔴 **ALTO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟢 **BAJO** | 🟢 **BAJO** | 🟢 **BAJO** | 🟢 **BAJO** |
| **< 5%** | � **MEDIO** | 🟡 **MEDIO** | 🟡 **MEDIO** | 🟢 **BAJO** | 🟢 **BAJO** | 🟢 **BAJO** | � **BAJO** | � **BAJO** | 🟢 **BAJO** |

- **🔴 ALTO**: Riesgo inmediato, requiere acción correctiva
- **🟡 MEDIO**: Estado de precaución, monitoreo intensivo
- **🟢 BAJO**: Estado operativo óptimo, monitoreo rutinario

### 💡 **Ejemplos Prácticos con Datos Reales**

#### 📊 **Caso 1: AGREGADO BOGOTA**
```
Datos actuales:
• Participación: 38.02% (embalse CRÍTICO)
• Volumen útil: 63.4% (agua ADECUADA)

Aplicación del algoritmo:
1. ¿Volumen ≥ 70%? NO (63.4% < 70%)
2. ¿Participación ≥ 15%? SÍ (38.02% ≥ 15%)
3. ¿Volumen < 30%? NO (63.4% ≥ 30%)
4. ¿Volumen < 50%? NO (63.4% ≥ 50%)

Resultado: 🟢 RIESGO BAJO
Razón: Embalse crítico pero con agua adecuada (50-69.99%)
```

#### 📊 **Caso 2: MUÑA**
```
Datos actuales:
• Participación: 0.52% (embalse COMPLEMENTARIO)
• Volumen útil: 77.5% (agua ABUNDANTE)

Aplicación del algoritmo:
1. ¿Volumen ≥ 70%? SÍ (77.5% ≥ 70%)

Resultado: 🟢 RIESGO BAJO
Razón: Abundante agua (regla prioritaria)
```

#### 📊 **Caso 3: Escenario Hipotético - EL QUIMBO en Crisis**
```
Datos hipotéticos:
• Participación: 10.22% (embalse IMPORTANTE)
• Volumen útil: 15% (agua ESCASA)

Aplicación del algoritmo:
1. ¿Volumen ≥ 70%? NO (15% < 70%)
2. ¿Participación ≥ 15%? NO (10.22% < 15%)
3. ¿Participación ≥ 10%? SÍ (10.22% ≥ 10%)
4. ¿Volumen < 20%? SÍ (15% < 20%)

Resultado: 🔴 RIESGO ALTO
Razón: Embalse importante con muy poca agua
```

### 🔍 **¿Por Qué Esta Lógica?**

#### **Fundamento Técnico:**
1. **Prioridad al Volumen Alto (≥70%)**: Un embalse lleno no representa riesgo, sin importar su tamaño.

2. **Penalización por Importancia**: Mientras más importante sea el embalse (mayor participación), menos agua necesita perder para ser considerado riesgoso.

3. **Tolerancia para Embalses Pequeños**: Los embalses con baja participación (<5%) pueden tener menos agua sin afectar significativamente el sistema.

#### **Lógica Operativa:**
```
AGREGADO BOGOTA (38% del sistema) con 25% de agua = CRISIS NACIONAL
MUÑA (0.5% del sistema) con 25% de agua = SITUACIÓN MANEJABLE
```

### 🎯 **Umbrales Críticos por Importancia**

| **Importancia del Embalse** | **Umbral de Riesgo Alto** | **Umbral de Riesgo Medio** |
|----------------------------|---------------------------|----------------------------|
| **≥ 15% (CRÍTICOS)** | Volumen < 30% | Volumen 30-49.99% |
| **10-15% (IMPORTANTES)** | Volumen < 20% | Volumen 20-39.99% |
| **5-10% (RELEVANTES)** | Volumen < 15% | Volumen 15-34.99% |
| **< 5% (COMPLEMENTARIOS)** | No aplica* | Volumen < 25% |

*Los embalses complementarios no pueden generar riesgo alto por sí solos.

**📋 Leyenda de la Matriz:**

### ⚡ **Indicadores de Riesgo Sistémico**

#### 🚩 **Alertas Automáticas:**
1. **ALERTA ROJA**: >30% de la capacidad del sistema en riesgo alto
2. **ALERTA NARANJA**: >50% de la capacidad del sistema en riesgo medio o alto
3. **ALERTA AMARILLA**: Embalses críticos (>15% participación) en riesgo medio

#### 📈 **Métricas de Sistema:**
- **Índice de Riesgo Ponderado**: `Σ (Participación × Factor_Riesgo)`
- **Capacidad en Riesgo**: Suma de GWh de embalses en rojo y amarillo
- **Diversificación**: Número de embalses que concentran el 80% del sistema

### 🚀 **Interpretación Intuitiva del Semáforo**

#### 🔴 **Cuando veas ROJO:**
```
"¡Atención! Este embalse es importante para el país y se está quedando sin agua"

Acciones típicas:
• Activar plantas térmicas de respaldo
• Implementar restricciones de consumo
• Monitoreo cada 6 horas
• Comunicar a autoridades
```

#### 🟡 **Cuando veas AMARILLO:**
```
"Precaución. Este embalse necesita vigilancia especial"

Acciones típicas:
• Monitoreo diario intensivo
• Preparar medidas preventivas
• Revisar pronósticos climáticos
• Optimizar despacho energético
```

#### 🟢 **Cuando veas VERDE:**
```
"Todo bien. Este embalse está en condiciones normales"

Acciones típicas:
• Monitoreo rutinario
• Aprovechar para mantenimientos
• Posible exportación de energía
• Operación estándar
```

### 🧪 **Validación de la Lógica con Casos Extremos**

#### **Caso Extremo 1: Embalse Grande Vacío**
```
Embalse: 50% participación, 5% volumen
Resultado: 🔴 RIESGO ALTO
Interpretación: ¡EMERGENCIA NACIONAL!
```

#### **Caso Extremo 2: Embalse Pequeño Vacío**
```
Embalse: 1% participación, 5% volumen
Resultado: 🟡 RIESGO MEDIO
Interpretación: Vigilar, pero no es crítico
```

#### **Caso Extremo 3: Cualquier Embalse Lleno**
```
Embalse: X% participación, 80% volumen
Resultado: 🟢 RIESGO BAJO
Interpretación: Sin problemas, agua suficiente
```

---

## 🛠️ 4. IMPLEMENTACIÓN TÉCNICA

### 🎨 **Código de Colores CSS**
```css
/* Riesgo Alto */
.risk-high {
    background-color: #fee2e2 !important;  /* Fondo rojo claro */
    color: #991b1b !important;             /* Texto rojo oscuro */
    font-weight: bold;
}

/* Riesgo Medio */
.risk-medium {
    background-color: #fef3c7 !important;  /* Fondo amarillo claro */
    color: #92400e !important;             /* Texto amarillo oscuro */
    font-weight: bold;
}

/* Riesgo Bajo */
.risk-low {
    background-color: #d1fae5 !important;  /* Fondo verde claro */
    color: #065f46 !important;             /* Texto verde oscuro */
}
```

### 🔄 **Algoritmo de Clasificación**
```python
def clasificar_riesgo_embalse(participacion, volumen_util):
    """
    Clasifica el riesgo de un embalse basado en participación y volumen útil
    
    Args:
        participacion (float): Participación porcentual en el sistema (0-100)
        volumen_util (float): Volumen útil disponible (0-100)
    
    Returns:
        str: 'high', 'medium', 'low'
    
    Lógica paso a paso:
    1. Si hay abundante agua (≥70%) → SIEMPRE verde
    2. Si es embalse crítico (≥15%) → Evaluar umbrales estrictos
    3. Si es embalse importante (≥10%) → Evaluar umbrales moderados  
    4. Si es embalse relevante (≥5%) → Evaluar umbrales básicos
    5. Si es embalse complementario (<5%) → Solo amarillo si muy vacío
    """
    # Regla prioritaria: abundante agua = riesgo bajo
    if volumen_util >= 70:
        return 'low'  # Verde: Sin importar tamaño, agua suficiente
    
    # Evaluación por importancia del embalse
    if participacion >= 15:  # Embalses CRÍTICOS
        if volumen_util < 30:
            return 'high'    # Rojo: Crítico con poca agua
        elif volumen_util < 50:
            return 'medium'  # Amarillo: Crítico con agua moderada
        else:
            return 'low'     # Verde: Crítico con agua adecuada
            
    elif participacion >= 10:  # Embalses IMPORTANTES
        if volumen_util < 20:
            return 'high'    # Rojo: Importante con muy poca agua
        elif volumen_util < 40:
            return 'medium'  # Amarillo: Importante con agua limitada
        else:
            return 'low'     # Verde: Importante con agua suficiente
            
    elif participacion >= 5:   # Embalses RELEVANTES
        if volumen_util < 15:
            return 'high'    # Rojo: Relevante casi vacío
        elif volumen_util < 35:
            return 'medium'  # Amarillo: Relevante con poca agua
        else:
            return 'low'     # Verde: Relevante con agua aceptable
            
    else:  # Embalses COMPLEMENTARIOS (< 5%)
        if volumen_util < 25:
            return 'medium'  # Amarillo: Pequeño pero muy vacío
        else:
            return 'low'     # Verde: Pequeño con agua suficiente
    
    # Caso por defecto (no debería llegar aquí)
    return 'low'
```

### 🎯 **Flujo de Decisión Simplificado**
```
ENTRADA: Participación = X%, Volumen = Y%

┌─ ¿Y ≥ 70%? ──► SÍ ──► 🟢 VERDE (Abundante agua)
│
└─ NO ──► ¿X ≥ 15%? ──► SÍ ──► ¿Y < 30%? ──► SÍ ──► 🔴 ROJO
                        │                  └─ NO ──► ¿Y < 50%? ──► SÍ ──► 🟡 AMARILLO
                        │                                        └─ NO ──► 🟢 VERDE
                        │
                        └─ NO ──► ¿X ≥ 10%? ──► SÍ ──► [Lógica similar]
                                               └─ NO ──► [Continúa...]
```

---

## 📋 5. CASOS DE USO Y APLICACIONES

### 🎯 **Para Operadores del Sistema:**
1. **Monitoreo en Tiempo Real**: Identificación inmediata de embalses en riesgo
2. **Despacho Energético**: Priorización de embalses según estado operativo
3. **Mantenimiento Predictivo**: Programación basada en niveles de riesgo

### 📊 **Para Planificadores Energéticos:**
1. **Análisis de Vulnerabilidad**: Identificación de puntos críticos del sistema
2. **Gestión de Demanda**: Activación de medidas según nivel de riesgo
3. **Inversión en Infraestructura**: Priorización basada en criticidad

### 🏛️ **Para Autoridades Regulatorias:**
1. **Supervisión Regulatoria**: Monitoreo del estado del SIN
2. **Políticas Públicas**: Definición de estrategias basadas en riesgo
3. **Comunicación Pública**: Transparencia en el estado energético

---

## ⚠️ 6. INTERPRETACIÓN DE RESULTADOS

### 🔍 **Escenarios Típicos:**

#### 🔴 **Escenario de Crisis (Múltiples Rojos):**
```
Ejemplo: AGREGADO BOGOTA (65% participación, 25% volumen)
- Impacto: Alto riesgo de déficit energético
- Acción: Activación de plantas térmicas de respaldo
- Monitoreo: Horario de niveles y aportes
```

#### 🟡 **Escenario de Precaución (Amarillos Dominantes):**
```
Ejemplo: Sistema con 60% de capacidad en amarillo
- Impacto: Presión en reservas energéticas
- Acción: Restricciones voluntarias de demanda
- Preparación: Planes de contingencia activados
```

#### 🟢 **Escenario Óptimo (Verdes Mayoritarios):**
```
Ejemplo: >80% del sistema en verde
- Estado: Operación normal del SIN
- Estrategia: Aprovechamiento para mantenimientos
- Oportunidad: Exportación de energía
```

### 📈 **Indicadores de Rendimiento del Sistema:**

1. **Índice de Salud del Sistema**: `% de capacidad en verde / 100`
2. **Factor de Riesgo**: `(% rojos × 3 + % amarillos × 2 + % verdes × 1) / 100`
3. **Capacidad Disponible Efectiva**: `Σ (Capacidad × Factor_Volumen_Útil)`

---

## 🚀 7. BENEFICIOS DEL SISTEMA DE SEMÁFORO

### ✅ **Ventajas Operativas:**
- **Visualización Inmediata**: Estado del sistema de un vistazo
- **Priorización Automática**: Enfoque en embalses críticos
- **Reducción de Riesgos**: Detección temprana de problemas
- **Eficiencia Operativa**: Optimización de recursos humanos

### 📊 **Ventajas Analíticas:**
- **Correlaciones**: Identificación de patrones regionales
- **Tendencias**: Evolución histórica del riesgo
- **Comparaciones**: Benchmarking entre regiones
- **Proyecciones**: Modelado de escenarios futuros

### 🎯 **Ventajas Estratégicas:**
- **Toma de Decisiones**: Información objetiva y oportuna
- **Comunicación**: Lenguaje universal de riesgos
- **Transparencia**: Criterios claros y reproducibles
- **Mejora Continua**: Ajuste de umbrales basado en experiencia

---

## 📚 8. GLOSARIO TÉCNICO

| **Término** | **Definición** |
|-------------|---------------|
| **Capacidad Útil** | Energía máxima que puede generar un embalse en condiciones normales |
| **Volumen Útil** | Porcentaje de agua disponible por encima del nivel mínimo técnico |
| **Nivel Mínimo Técnico** | Cota mínima para operación segura de las turbinas |
| **Participación Porcentual** | Proporción de la capacidad de un embalse respecto al total del sistema |
| **SIN** | Sistema Interconectado Nacional de energía eléctrica |
| **XM** | Compañía experta en mercados que administra el sistema eléctrico |
| **Despacho Energético** | Asignación de generación a las plantas del sistema |
| **Factor de Riesgo** | Métrica cuantitativa del nivel de amenaza operativa |

---

## 📞 9. CONTACTO Y SOPORTE

**Desarrollado por**: Equipo de Digitalización - Ministerio de Minas y Energía  
**Versión**: 1.0  
**Fecha**: Septiembre 2025  
**Actualización**: Tiempo real vía API XM  

---

*Este documento es una guía técnica para la interpretación del Sistema de Semáforo de Riesgos Hidrológicos. Para consultas técnicas o sugerencias de mejora, contacte al equipo de desarrollo.*
