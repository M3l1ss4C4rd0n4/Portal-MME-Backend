# POLÍTICA DE CONFIANZA POR FUENTE DE PREDICCIÓN

> **Portal Energético MME — Ministerio de Minas y Energía de Colombia**  
> Generado: 2026-02-16  
> Resultado de FASE 5 del Plan de Limpieza de Datos y Mejora de Predicciones

---

## 1. Resumen Ejecutivo

Se reentrenaron **13 fuentes de predicción** (8 sectoriales + 5 por tipo de generación) con modelos
ENSEMBLE (Prophet + SARIMA), horizonte de 90 días y validación holdout de 30 días. Todas las predicciones
tienen **cero valores negativos** y rangos coherentes con el histórico.

| Clasificación | Criterio | Fuentes |
|---|---|---|
| **MUY CONFIABLE** | MAPE ≤ 15%, confianza ≥ 85% | 8 fuentes |
| **CONFIABLE** | MAPE 15-20%, confianza 75-85% | 3 fuentes |
| **ACEPTABLE** | MAPE 20-30%, confianza 60-80% | 1 fuente |
| **EXPERIMENTAL** | Sin holdout (datos insuficientes) | 1 fuente |

---

## 2. Matriz de Confianza Detallada

### 2.1 Métricas Sectoriales (train_predictions_sector_energetico.py)

| Fuente | MAPE | RMSE | Confianza BD | Clasificación | Nota |
|---|---|---|---|---|---|
| GENE_TOTAL | 2.26% | 6.76 GWh | 98% | ✅ MUY CONFIABLE | Generación total del sistema |
| DEMANDA | 2.78% | 7.57 GWh | 97% | ✅ MUY CONFIABLE | Demanda real del SIN |
| PRECIO_ESCASEZ | 1.02% | 8.10 $/kWh | 99% | ✅ MUY CONFIABLE | Precio regulado, baja volatilidad |
| EMBALSES | 0.06% | 11.37 GWh | 100% | ✅ MUY CONFIABLE | Volumen útil diario, serie suave |
| EMBALSES_PCT | 3.35% | 2.70 pp | 97% | ✅ MUY CONFIABLE | % volumen útil (escala 0-100%) |
| PERDIDAS | 10.67% | 0.65 GWh | 89% | ✅ MUY CONFIABLE | Pérdidas de energía |
| APORTES_HIDRICOS | 19.52% | 100.03 GWh | 80% | 🟡 CONFIABLE | Alta variabilidad hidrológica |
| PRECIO_BOLSA | NULL | NULL | 50% | 🔵 EXPERIMENTAL | Ventana de 8 meses, sin holdout posible |

### 2.2 Generación por Tipo de Recurso (train_predictions_postgres.py)

| Fuente | MAPE | RMSE | Confianza BD | Clasificación | Nota |
|---|---|---|---|---|---|
| Hidráulica | 3.51% | 8.22 GWh | 96% | ✅ MUY CONFIABLE | Principal fuente de generación |
| Biomasa | 5.85% | 0.21 GWh | 94% | ✅ MUY CONFIABLE | Volumen bajo pero estable |
| Térmica | 16.64% | 5.09 GWh | 83% | 🟡 CONFIABLE | Despacho variable según hidrología |
| Solar | 19.94% | 3.44 GWh | 80% | 🟡 CONFIABLE | Expansión reciente, patrón cambiante |
| Eólica | 25.10% | 0.15 GWh | 75% | 🟠 ACEPTABLE | Capacidad instalada mínima, alta volatilidad relativa |

---

## 3. Reglas de Confianza para el Orquestador

El orquestador (cuando se integre) debe seguir estas reglas para interpretar predicciones:

```python
# Política de confianza — FASE 5 (2026-02-16)
POLITICA_CONFIANZA = {
    # MUY CONFIABLE (MAPE ≤ 15%)
    'GENE_TOTAL':      {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'DEMANDA':         {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'PRECIO_ESCASEZ':  {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.02, 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES':        {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.01, 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES_PCT':    {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'PERDIDAS':        {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.15, 'usar_intervalos': True,  'disclaimer': False},
    'Hidráulica':      {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'Biomasa':         {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.10, 'usar_intervalos': True,  'disclaimer': False},

    # CONFIABLE (MAPE 15-20%)
    'APORTES_HIDRICOS':{'nivel': 'CONFIABLE',      'mape_max': 0.25, 'usar_intervalos': True,  'disclaimer': True},
    'Térmica':         {'nivel': 'CONFIABLE',      'mape_max': 0.20, 'usar_intervalos': True,  'disclaimer': True},
    'Solar':           {'nivel': 'CONFIABLE',      'mape_max': 0.25, 'usar_intervalos': True,  'disclaimer': True},

    # ACEPTABLE (MAPE 20-30%)
    'Eólica':          {'nivel': 'ACEPTABLE',      'mape_max': 0.30, 'usar_intervalos': True,  'disclaimer': True},

    # EXPERIMENTAL (sin holdout)
    'PRECIO_BOLSA':    {'nivel': 'EXPERIMENTAL',   'mape_max': None, 'usar_intervalos': False, 'disclaimer': True},
}

def obtener_disclaimer(fuente: str) -> str:
    """Genera disclaimer según nivel de confianza de la fuente."""
    politica = POLITICA_CONFIANZA.get(fuente, {})
    nivel = politica.get('nivel', 'DESCONOCIDO')
    
    if nivel == 'MUY_CONFIABLE':
        return ""
    elif nivel == 'CONFIABLE':
        return "⚠️ Predicción con precisión moderada. Usar como referencia direccional."
    elif nivel == 'ACEPTABLE':
        return "⚠️ Predicción con alta incertidumbre. Considerar el rango (intervalo) como guía principal."
    elif nivel == 'EXPERIMENTAL':
        return "🔬 Predicción experimental: pocos datos históricos, sin validación holdout. NO usar para toma de decisiones."
    else:
        return "❌ Fuente no reconocida en política de confianza."
```

---

## 4. Lineamientos Operativos

### 4.1 Para el Bot / Orquestador

| Nivel | Acción en respuesta al usuario |
|---|---|
| MUY CONFIABLE | Mostrar valor predicho + intervalo. Sin disclaimer. |
| CONFIABLE | Mostrar valor predicho + intervalo + disclaimer de precisión moderada. |
| ACEPTABLE | Mostrar intervalo como guía principal + disclaimer de alta incertidumbre. |
| EXPERIMENTAL | Mostrar solo como referencia + disclaimer fuerte. Nunca afirmar como dato seguro. |

### 4.2 Para Reentrenamiento Periódico

| Frecuencia | Acción |
|---|---|
| **Diaria** | El ETL carga datos nuevos de XM a `metrics`. |
| **Semanal** | Reentrenar fuentes MUY CONFIABLE y CONFIABLE (cron job). |
| **Quincenal** | Reentrenar ACEPTABLE y EXPERIMENTAL con datos acumulados. |
| **Mensual** | Revisión de esta política: si MAPE mejora → promover nivel; si empeora → degradar. |

### 4.3 Criterios de Alertas Automáticas

- Si MAPE en siguiente reentrenamiento **sube más de 5pp** respecto al valor actual → Alerta #data-quality
- Si aparecen **predicciones negativas** → Alerta crítica (no debería ocurrir con el clamp actual)
- Si datos de XM no se actualizan en **3 días** → Alerta #etl-delay

---

## 5. Notas Técnicas

### 5.1 PRECIO_BOLSA (Caso Especial)
- **Problema**: Solo dispone de ~8 meses de datos históricos (ventana configurada `ventana_meses: 8`)
- **Efecto**: 243 registros, insuficientes para holdout de 30 días con modelo estable
- **Decisión**: Se entrena solo con Prophet (sin SARIMA), confianza fija 0.50
- **Acción futura**: Cuando acumule ≥ 18 meses de datos, cambiar a ENSEMBLE con holdout completo

### 5.2 Eólica (MAPE Alto)
- **Causa**: Capacidad instalada mínima (~0.60 GWh/día), alta volatilidad relativa
- **Efecto**: MAPE 25.10%, pero RMSE solo 0.15 GWh (error absoluto muy bajo)
- **Decisión**: Clasificación ACEPTABLE por MAPE, pero el impacto real es mínimo en la matriz energética

### 5.3 Aportes Hídricos (MAPE Borderline)
- **Causa**: Variabilidad natural de caudales (clima, estacionalidad)
- **MAPE**: 19.52% — justo por debajo del umbral 20%
- **Decisión**: Clasificación CONFIABLE con disclaimer. Monitorear en próximo reentrenamiento.

### 5.4 Filtro de Datos Parciales (FASE 2/4)
- Se agregó un filtro defensivo en `train_predictions_sector_energetico.py` que excluye datos
  de los últimos 5 días cuando el valor es < 50% de la mediana de 90 días
- **Solo aplica** a métricas de tipo `suma_diaria`, `suma_embalses`, `agregado_por_recurso`
- **NO aplica** a precios (PRECIO_BOLSA, PRECIO_ESCASEZ) para evitar filtrar valores legítimos

---

## 6. Verificaciones Finales

| Verificación | Resultado |
|---|---|
| Predicciones negativas | **0** en todas las 13 fuentes |
| Horizonte de predicción | 90 días (hasta mayo 2026) |
| Fecha de última generación | 2026-02-16 |
| Total predicciones en BD | 1,170 (13 fuentes × 90 días) |
| Coherencia de rangos | ✅ Todos los valores dentro de rangos históricos |
| Intervalos de confianza | ✅ Presentes en 12/13 fuentes (excepto PRECIO_BOLSA) |

---

## 7. Decisión FASE 5

### ✅ GO — La política de confianza está definida y documentada.

**Justificación:**
1. **12 de 13 fuentes** tienen MAPE validado (la excepción PRECIO_BOLSA está documentada)
2. **8 fuentes** son Muy Confiables (MAPE ≤ 15%)
3. **3 fuentes** son Confiables (MAPE 15-20%)
4. **1 fuente** es Aceptable (Eólica, pero impacto bajo por escala)
5. **1 fuente** es Experimental (PRECIO_BOLSA, se mejoró respecto a su estado anterior)
6. **Cero predicciones negativas** en todo el sistema
7. Todos los rangos son coherentes con el histórico

**Siguiente paso:** Integrar `POLITICA_CONFIANZA` en el orquestador del bot (en sesión separada, según lo indicado en el Prompt Maestro).
