# Metodología de Cálculo, Predicción y Simulación del Costo Unitario de Energía Eléctrica en Colombia

**Portal Energético — Ministerio de Minas y Energía (MME)**  
**Versión:** 2.0 | **Fecha:** Marzo 2026  
**Clasificación:** Documento técnico-metodológico de carácter interno

---

## Resumen

Este documento describe la metodología completa implementada en el Portal Energético del Ministerio de Minas y Energía (MME) para el cálculo, predicción y simulación del **Costo Unitario (CU)** de energía eléctrica en Colombia. El CU es el indicador regulatorio central que determina la tarifa de energía para los usuarios regulados del Sistema Interconectado Nacional (SIN). La implementación sigue estrictamente el marco regulatorio establecido por la Comisión de Regulación de Energía y Gas (CREG), específicamente la Resolución CREG 119 de 2007 y sus actualizaciones, y se apoya en datos oficiales provenientes del Sistema de Monitoreo del Mercado Eléctrico Mayorista (SIMEM) operado por XM S.A. E.S.P.

El sistema comprende tres módulos: (1) **cálculo diario del CU** a partir de componentes tarifarias reguladas e indicadores del mercado spot; (2) **predicción de corto plazo** mediante un ensemble de modelos de aprendizaje automático con predicción conformal para cuantificación de incertidumbre; y (3) **simulación paramétrica CREG** para análisis de escenarios regulatorios y evaluación de impacto en hogares vulnerables.

---

## 1. Introducción

### 1.1 Contexto regulatorio

La tarifa de energía eléctrica para usuarios regulados en Colombia es determinada por la fórmula tarifaria establecida por la CREG, entidad adscrita al MME. Dicha fórmula descompone el costo total del suministro en componentes que reflejan los distintos eslabones de la cadena: generación, transmisión, distribución, comercialización y restricciones del sistema.

El **Costo Unitario (CU)** expresa, en pesos colombianos por kilovatio-hora (COP/kWh), el precio integrado que debe pagar un comercializador para suministrar energía a usuarios finales en una zona de distribución específica. Este valor es calculado mensualmente por los comercializadores, pero el Portal Energético del MME lo estima con frecuencia diaria a partir de indicadores del mercado publicados por XM/SIMEM, permitiendo un monitoreo continuo de la señal de precio.

### 1.2 Fuentes normativas principales

- **CREG Resolución 119 de 2007:** Define la fórmula tarifaria aplicable a los Comercializadores de Energía Eléctrica (CER) para mercado regulado. Establece la estructura de componentes G, T, D, C, PR y R.
- **CREG Resoluciones 101, 102 y 103 de 2023:** Actualizan y complementan los criterios de reconocimiento de cargos de distribución (SDL/STR) y ajustan la metodología de componentes de pérdidas.
- **CREG Resolución 015 de 2018:** Marco regulatorio vigente para cargos de comercialización.

### 1.3 Alcance del sistema

El sistema procesa datos desde el período 2020-02-06 hasta la fecha actual. Al momento de redacción (marzo 2026), la base de datos contiene **2.224 registros diarios** del CU calculado, de los cuales **38 corresponden al período enero-marzo 2026** con la fórmula CREG completa (contrato + bolsa). Los valores recientes oscilan entre **309,70 y 385,57 COP/kWh** para el CU con fórmula CREG, con promedio de **329,87 COP/kWh**.

---

## 2. Marco Regulatorio

### 2.1 Fórmula general CREG

La Resolución CREG 119/2007 establece que el Costo Unitario del comercializador corresponde a la suma de los costos de compra de energía más los cargos regulados de transporte y pérdidas sistémicas:

```
CU = (G + T + D + C + R) / (1 - PT/100)
```

donde cada componente tiene unidades de COP/kWh y `PT` es el porcentaje total de pérdidas reconocidas (STN + SDL). Esta formulación captura el efecto de las pérdidas del sistema como un factor multiplicador sobre los costos de adquisición: la energía que el comercializador debe comprar es mayor que la que efectivamente puede entregar al usuario final.

### 2.2 Componentes definidas por CREG

| Componente | Símbolo | Descripción regulatoria |
|---|---|---|
| Generación | G | Costo de compra de energía en contratos y bolsa. Incluye cargos de confiabilidad. |
| Transmisión | T | Cargo por uso del Sistema de Transmisión Nacional (STN), fijado por CREG. |
| Distribución | D | Cargos por uso del Sistema de Transmisión Regional/Local (STR/SDL). |
| Comercialización | C | Margen regulado del comercializador de energía. |
| Restricciones | R | Cargos de restricciones y reprogramación del despacho (alivios y sin alivio). |
| Pérdidas | PT | Factor de pérdidas técnicas en STN (medidas) + SDL (factor normativo 8.5%). |

### 2.3 Período de vigencia y actualización

Los cargos T, D y C son fijados por CREG con vigencia plurianual y se actualizan mediante resolución. La componente G es variable y depende del mercado spot (PrecBolsNaci) y del portafolio de contratos del comercializador. La componente R varía diariamente según los eventos de restricción del despacho.

---

## 3. Metodología de Cálculo

### 3.1 Componente G — Generación

La componente de generación es la más volátil del CU y representa, en promedio, el **59,73%** del costo total. Su cálculo sigue una jerarquía de dos niveles:

#### Nivel 1: Fórmula CREG (G_CREG_FORMULA)

Cuando los datos de contratos están disponibles en SIMEM, se aplica la ponderación regulatoria entre energía contratada y energía en bolsa:

```
G = Pc * Qc + Pb * (1 - Qc)
```

donde:
- `Pc` = PrecPromContRegu: Precio promedio ponderado de contratos regulados (COP/kWh)
- `Pb` = PrecBolsNaci: Precio de bolsa nacional (COP/kWh)
- `Qc` = Cobertura de contratos = `CompContEnerReg / DemaCome`
  - CompContEnerReg: Energía comprometida en contratos regulados (GWh)
  - DemaCome: Demanda total del comercializador (GWh)

Esta fórmula refleja que un comercializador típico cubre una fracción `Qc` de su demanda mediante contratos a plazo (precio estable `Pc`) y el remanente `(1-Qc)` lo compra en el mercado spot al precio de bolsa `Pb`. En el período enero-marzo 2026, `Qc` promedio fue de **0,533**, es decir, el 53,3% de la demanda cubierta por contratos.

#### Nivel 2: Fallback — precio de bolsa (G_BOLSA_FALLBACK)

Cuando los datos de contratos no están disponibles (reporte rezagado de SIMEM), se usa el precio de bolsa nacional como aproximación conservadora:

```
G = Pb = PrecBolsNaci
```

Este fallback produce estimaciones menores al CU real porque subestima el componente de contratos a plazo. Las filas calculadas con fallback se identifican en la base de datos mediante el campo `metodo_g`.

### 3.2 Componente T — Transmisión

La componente de transmisión corresponde al cargo por uso del STN (Sistema de Transmisión Nacional), determinado periódicamente por la CREG en función de los costos AOM de las instalaciones de transmisión y el plan de expansión requerido.

```
T = 8,5 COP/kWh
```

Este cargo es **fijo y regulado**, independiente de las condiciones del mercado. Representa el **4,43%** del CU total en el período de referencia. El valor es parametrizable mediante la variable de entorno `CARGO_TRANSMISION`.

### 3.3 Componente D — Distribución

Los cargos de distribución (STR/SDL) reconocen los costos de transporte de energía desde el STN hasta los usuarios finales a través de redes de media y baja tensión:

```
D = 35,0 COP/kWh
```

Este valor corresponde a un promedio representativo de los cargos STR/SDL de la zona de referencia del modelo. En la práctica, varía por zona geográfica (Nivel de Tensión 1-4) y por operador de red (CODENSA, EPM, ESSA, etc.). Representa el **18,25%** del CU total. Parametrizable mediante `CARGO_DISTRIBUCION`.

### 3.4 Componente C — Comercialización

El margen del comercializador es un cargo regulado por CREG:

```
C = 12,0 COP/kWh
```

Representa el **6,26%** del CU total. Se actualiza periódicamente según la metodología CREG para reconocer costos operativos del comercializador. Parametrizable mediante `CARGO_COMERCIALIZACION`.

### 3.5 Componente R — Restricciones

Los cargos de restricciones compensan los costos de reprogramación del despacho y los servicios auxiliares, distribuidos entre todos los usuarios del SIN:

```
R = (RestAliv + RestSinAliv) [MCOP] / DemaCome [GWh] * 1000 [COP/kWh]
```

donde:
- RestAliv: Costo de restricciones con mecanismo de alivio (MCOP)
- RestSinAliv: Costo de restricciones sin mecanismo de alivio (MCOP)
- DemaCome: Demanda comercializada (GWh)

Las restricciones representan el **1,15%** del CU en promedio, pero son altamente variables: pueden superar el 5% en períodos de alta congestión de red o déficit de generación.

### 3.6 Factor de pérdidas y componente P

El factor de pérdidas transforma los costos de compra de energía en el costo de entrega al usuario, dado que parte de la energía se pierde en el sistema:

```
Perdidas_STN (%) = (PerdidasEner / Gene) * 100
Factor_SDL = 8,5 %  (normativo CREG, parametrizable)
PT = Perdidas_STN + Factor_SDL

factor_perdidas = 1 / (1 - PT/100)

CU = (G + T + D + C + R) * factor_perdidas
```

La componente P en el desglose de salida representa **exclusivamente la prima de pérdidas**:

```
P = suma_base * factor_perdidas - suma_base = suma_base * (factor_perdidas - 1)
```

donde `suma_base = G + T + D + C + R`. Esta componente representa el **10,26%** del CU total en promedio.

### 3.7 Clasificación de confianza del cálculo

Cada registro diario del CU recibe una clasificación de confianza basada en la disponibilidad de datos:

| Nivel | Condición | Descripción |
|---|---|---|
| **Alta** | G_CREG_FORMULA + datos de restricciones + pérdidas STN | Todos los datos disponibles; cálculo completo CREG |
| **Media** | G_CREG_FORMULA pero sin restricciones o pérdidas STN | Fórmula de generación completa, cargos R o pérdidas aproximados |
| **Baja** | G_BOLSA_FALLBACK | Solo precio de bolsa, dato preliminar |

### 3.8 Ejemplo numérico real (7 de marzo de 2026)

| Componente | Valor (COP/kWh) | % del CU |
|---|---|---|
| G (CREG) | 227,38 | 71,5% |
| T | 8,50 | 2,7% |
| D | 35,00 | 11,0% |
| C | 12,00 | 3,8% |
| R | 2,10 | 0,7% |
| P (pérdidas) | 32,99 | 10,4% |
| **CU total** | **317,98** | **100%** |

*Parámetros del día: Qc = 0,533 (53,3% demanda cubierta por contratos); PT aprox. 16%.*

---

## 4. Fuentes de Datos y Pipeline ETL

### 4.1 Fuentes primarias

Todos los datos de mercado utilizados en el cálculo del CU son de carácter oficial y provienen de plataformas certificadas:

| Variable | Fuente | Plataforma | Frecuencia |
|---|---|---|---|
| PrecBolsNaci | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| PrecPromContRegu | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| CompContEnerReg | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| DemaCome | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| Gene | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| PerdidasEner | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| RestAliv | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| RestSinAliv | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| PorcVoluUtilDiar | XM S.A. E.S.P. | SIMEM LAC | Diaria |
| AporEner | XM S.A. E.S.P. | SIMEM LAC | Diaria |

**URLs de acceso:**
- SIMEM: https://www.simem.co/estadisticas/indicadores-de-mercado
- XM Cargos regulados: https://www.xm.com.co/transmision/cargos-regulados
- XM Restricciones: https://www.xm.com.co/operacion/restricciones
- SSPD Regulación: https://www.superservicios.gov.co

### 4.2 Arquitectura del pipeline ETL

```
XM API (SIMEM REST) --> ETL Incremental --> tabla `metrics` (PostgreSQL)
                                                   |
                                         CU Calculator (diario 10am)
                                                   |
                                         tabla `cu_daily` (PostgreSQL)
                                                   |
                                    Dashboard Portal MME (presentación)
```

**Frecuencias de actualización:**

| Tarea Celery | Horario | Descripción |
|---|---|---|
| `etl_incremental_all_metrics` | Cada 6 horas | Descarga y almacena métricas de mercado XM/SIMEM |
| `calcular_cu_diario` | Diario 10:00 am | Calcula CU para los últimos 7 días con datos disponibles |
| `etl_nasa_power` | Diario 5:00 am | Datos meteorológicos (irradiación, temperatura) via NASA POWER |
| `actualizar_predicciones` | Domingo 2:00 am | Entrena y actualiza modelos de predicción |

### 4.3 Esquema de base de datos

**Tabla `metrics`** — datos de mercado XM/SIMEM:
```sql
fecha DATE, Gene NUMERIC, DemaCome NUMERIC, PrecBolsNaci NUMERIC,
RestAliv NUMERIC, RestSinAliv NUMERIC, PerdidasEner NUMERIC,
PrecPromContRegu NUMERIC, CompContEnerReg NUMERIC,
PorcVoluUtilDiar NUMERIC, AporEner NUMERIC
```

**Tabla `cu_daily`** — CU calculado:
```sql
fecha DATE, cu_cop_kwh NUMERIC, componente_g NUMERIC,
componente_t NUMERIC, componente_d NUMERIC, componente_c NUMERIC,
componente_r NUMERIC, componente_p NUMERIC, metodo_g VARCHAR,
factor_perdidas NUMERIC, confianza VARCHAR, notas TEXT
```

---

## 5. Modelo de Predicción de Corto Plazo

### 5.1 Motivación y alcance

La predicción del CU tiene valor operativo para la toma de decisiones en gestión de demanda, planeación de compras de energía y alerta temprana de variaciones tarifarias. El horizonte de predicción es de **7 a 30 días**, con enfoque en la semana siguiente.

### 5.2 Estrategia de predicción en cascada (tres niveles)

El sistema implementa una estrategia de predicción fail-safe con tres niveles:

1. **Nivel 1 — Predicciones precomputadas en BD:** Resultados de experimentos offline almacenados en la tabla `predicciones`. Se usan cuando están disponibles y dentro del horizonte solicitado.

2. **Nivel 2 — LightGBM entrenado en tiempo real:** Cuando no hay predicciones precomputadas, el sistema entrena un modelo LightGBM sobre los datos históricos disponibles en la tabla `metrics`. Requiere mínimo 30 observaciones.

3. **Nivel 3 — Proyección lineal naive:** Si no hay suficientes datos para entrenar el modelo, se usa una extrapolación lineal de la tendencia reciente como respaldo determinístico.

### 5.3 Modelo LightGBM — arquitectura y características

**LightGBM** (Light Gradient Boosting Machine) es un framework de boosting por gradiente con estructura de árbol de decisión optimizada para velocidad y eficiencia de memoria (Ke et al., 2017). Se seleccionó como modelo principal por su robustez en series de tiempo tabulares con pocas observaciones y características heterogéneas.

#### Variables de entrada (features)

| Feature | Fuente | Importancia (LightGBM, split) |
|---|---|---|
| `y_lag1` | CU del día anterior (COP/kWh) | 454 / ~38% |
| `y_lag7` | CU de 7 días antes | 296 / ~24% |
| `y_lag14` | CU de 14 días antes | ~180 / ~15% |
| `y_roll7` | Media movil 7 dias del CU | ~90 / ~7% |
| `embalses_pct` | PorcVoluUtilDiar (% vol. util embalses sistema) | 229 / ~6% |
| `aportes_gwh` | AporEner (aportes hidricos GWh) | 263 / ~5% |
| `dow` | Dia de la semana (one-hot) | 56-2 / ~3% |
| `mes` | Mes del año | variable |
| `dia_mes` | Dia del mes | variable |

Las características de rezago (`y_lag1`, `y_lag7`) dominan la importancia porque el CU presenta alta autocorrelación diaria. Las características hidrológicas (`embalses_pct`, `aportes_gwh`) capturan el estado hídrico del sistema, determinante del precio de bolsa en un mercado predominantemente hidráulico como el colombiano.

#### Hiperparámetros

```python
lgb.LGBMRegressor(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=4,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1
)
```

#### Partición temporal (sin data leakage)

- **Train:** datos hasta el período de validación
- **Validacion:** `max(7, n_total // 5)` observaciones más recientes
- **Prediccion:** horizonte hacia adelante, sin acceso a datos futuros

### 5.4 Resultados experimentales — comparación de modelos

Los experimentos se realizaron sobre tres series de tiempo críticas del mercado eléctrico colombiano usando un hold-out de evaluación fuera de muestra:

#### Preduccion de Precio de Bolsa (PrecBolsNaci)

| Modelo | MAPE (%) | RMSE | MAE | Tiempo (s) |
|---|---|---|---|---|
| **RandomForest** | **16,03** | 24,03 | 20,23 | 0,6 |
| LightGBM | 17,19 | 26,11 | 22,07 | 0,4 |
| XGBoost | 19,71 | 29,38 | 24,90 | 2,2 |
| Hybrid | 28,48 | 38,23 | 34,86 | — |
| LSTM | 53,93 | 83,22 | 69,66 | 48,6 |
| Ensemble | 149,27 | 188,37 | 181,91 | — |

*El precio de bolsa es intrinsecamente dificil de predecir (MAPE ~16%) debido a su dependencia de condiciones hidrologicas no lineales y decisiones de agentes del mercado.*

#### Prediccion de Demanda (DemaCome)

| Modelo | MAPE (%) | RMSE | MAE | Tiempo (s) |
|---|---|---|---|---|
| **LightGBM** | **1,30** | 4,18 | 2,89 | 0,4 |
| XGBoost | 1,49 | 4,71 | 3,31 | 0,4 |
| Hybrid | 1,57 | 5,11 | 3,44 | — |
| RandomForest | 1,61 | 5,12 | 3,57 | 0,6 |
| LSTM | 2,59 | 7,83 | 5,89 | 107,3 |
| Ensemble | 3,76 | 10,25 | 8,35 | — |

*La demanda de energía tiene alta predictibilidad (MAPE ~1,3%) debido a sus patrones regulares: ciclos semanales, estacionalidad horaria y baja volatilidad.*

#### Prediccion de Aportes Hidricos (AporEner)

| Modelo | MAPE (%) | RMSE | MAE | Tiempo (s) |
|---|---|---|---|---|
| **Hybrid** | **10,55** | 80,90 | 55,17 | — |
| LightGBM | 11,23 | 70,73 | 55,91 | 0,2 |
| XGBoost | 11,36 | 68,54 | 55,63 | 0,2 |
| RandomForest | 11,86 | 70,82 | 57,51 | 0,5 |
| LSTM | 22,22 | 116,65 | 101,65 | 109,8 |
| Ensemble | 18,29 | 125,42 | 95,40 | — |

*Los aportes hidricos dependen de fenomenos climáticos de escala regional (ENSO, Chorro del Chocó) que aportan volatilidad media (MAPE ~10-11%).*

### 5.5 Cuantificacion de incertidumbre — Prediccion Conformal

Para los tres modelos críticos (PrecBolsNaci, DemaCome, AporEner) se implementa **Prediccion Conformal Adaptativa (ACI — Adaptive Conformal Inference)** (Gibbs & Candès, 2021) que produce intervalos de confianza con cobertura garantizada:

```
y_pred +/- q_(1-alpha)( |errores_calibracion| )
```

donde `q_(1-alpha)` es el cuantil (1-alpha) de los errores de calibracion en el conjunto de hold-out. La cobertura objetivo es **95%** (alpha = 0,05).

A diferencia de los intervalos de prediccion paramétricos (que asumen distribución gaussiana de errores), la prediccion conformal es **distribution-free** y válida para cualquier distribución de errores, incluyendo las distribuciones asimétricas típicas del mercado eléctrico.

---

## 6. Simulacion Parametrica CREG

### 6.1 Proposito y alcance

El modulo de simulacion permite evaluar el impacto de cambios en parámetros regulatorios sobre el CU y sobre la factura de hogares del estrato 3. Es una herramienta de análisis de política energética, no un modelo de pronostico. Los resultados son estimaciones paramétricas basadas en la descomposición del CU vigente.

### 6.2 Descomposicion base del CU

El CU simulado parte de la descomposición porcentual promedio observada en producción (período de referencia 2026):

| Componente | Porcentaje del CU |
|---|---|
| Generacion (G) | 59,73% |
| Distribucion (D) | 18,25% |
| Perdidas (P) | 10,26% |
| Comercializacion (C) | 6,26% |
| Transmision (T) | 4,43% |
| Restricciones (R) | 1,15% |
| **Total** | **100%** |

El CU base dinámico se calcula como el promedio de los últimos 30 días de datos reales con fórmula CREG completa (`metodo_g = 'G_CREG_FORMULA'`). Si no hay datos suficientes, se usa el valor de referencia **192,70 COP/kWh**.

### 6.3 Parámetros simulables y formulas

El motor de simulacion acepta seis parámetros independientes, cada uno con rango validado:

#### Parámetro 1: Factor precio de bolsa (`precio_bolsa_factor`)

Modifica el precio spot del mercado. Rango válido: [0,50; 3,00].

```
G_sim = G_base * (1 + delta_pb * 0.85 + delta_dem * 0.15)
```

donde `delta_pb = f_pb - 1` es la variación relativa del precio de bolsa. El coeficiente 0,85 refleja que aproximadamente el 85% del componente G es sensible al precio de bolsa (el 15% restante corresponde a cargos de confiabilidad y ENFICC relativamente estables).

#### Parámetro 2: Factor de pérdidas de distribución (`factor_perdidas`)

Modifica el factor de pérdidas SDL/STR reconocido por CREG. Rango válido: [0,05; 0,20].

```
D_sim = D_base * (1 + delta_f * 2.0)
P_sim = P_base * (1 + delta_f * 1.5)
```

donde `delta_f = f_perd - 0.085` es la desviación respecto al factor base CREG (8,5%). Los coeficientes 2,0 y 1,5 reflejan la mayor sensibilidad del componente de distribución (que porta directamente las pérdidas) respecto al componente de pérdidas residuales.

#### Parámetro 3: Cargo de restricciones absoluto (`cargo_restricciones_kw`)

Reemplaza directamente el valor calculado de R. Rango válido: [0; 50] COP/kWh.

```
R_sim = cargo_restricciones_kw  (valor absoluto en COP/kWh)
```

Cuando no se especifica, el modelo usa `R_base` calculado a partir de datos históricos.

#### Parámetro 4: Tasa de transmisión (`tasa_transmision`)

Multiplica el cargo T vigente. Rango válido: [0,50; 1,50].

```
T_sim = T_base * tasa_transmision
```

Permite simular incrementos en el Plan de Expansión de Transmisión (PTN) o cambios en la metodología de reconocimiento de cargos STN.

#### Parámetro 5: Tasa de comercialización (`tasa_comercializacion`)

Multiplica el cargo C regulado. Rango válido: [0,50; 1,50].

```
C_sim = C_base * tasa_comercializacion
```

#### Parámetro 6: Factor de demanda (`demanda_factor`)

Modifica el nivel de demanda del comercializador. Rango válido: [0,70; 1,30].

```
G_sim = G_base * (1 + delta_pb * 0.85 + delta_dem * 0.15)
```

donde `delta_dem = f_dem - 1`.

#### CU simulado total

```
CU_sim = G_sim + D_sim + C_sim + T_sim + P_sim + R_sim
```

### 6.4 Analisis de sensibilidad

Para cada parámetro modificado, el análisis de sensibilidad calcula su contribución individual al delta total del CU mediante experimentos univariados:

```
delta_i = | CU(theta_i, theta_j_base para j!=i) - CU_base |

Contribucion_i (%) = delta_i / suma_j(delta_j) * 100
```

Esto permite identificar cuál parámetro regulatorio explica mayor proporción del cambio total en el CU simulado.

### 6.5 Impacto en hogares estrato 3

El análisis de impacto social cuantifica el efecto en la factura de un hogar tipo estrato 3, conforme a los parámetros CREG vigentes:

- **Consumo mensual de referencia:** 173 kWh/mes (CREG, hogar tipo estrato 3)
- **Consumo básico subsidiado:** 130 kWh (primeros 130 kWh reciben subsidio)
- **Subsidio estrato 3:** 50% sobre el consumo básico

```
Factura(CU) = 130 * CU * (1 - 0.50)  +  43 * CU
            = CU * (65 + 43)
            = CU * 108

Delta_Factura = (CU_sim - CU_base) * 108  [COP/mes]
```

### 6.6 Escenarios preconfigurados

El sistema incluye siete escenarios regulatorios prediseñados para análisis rápido:

| Escenario | Descripción | Parámetros clave |
|---|---|---|
| SEQUIA_MODERADA | Fenomeno La Niña leve | f_pb = 1,30; aportes reducidos |
| SEQUIA_SEVERA | Deficit hidrico critico (El Niño) | f_pb = 1,80; f_dem = 0,95 |
| REFORMA_TARIFA | Reduccion cargos de distribucion | f_perd = 0,07; tasa_C = 0,90 |
| INVERSION_RED | Expansion plan de transmision | tasa_T = 1,20; f_perd = 0,075 |
| ALTA_HIDRO | Abundancia hidrica (La Niña fuerte) | f_pb = 0,70 |
| RESTRICCIONES_ALTAS | Alta congestion del sistema | R = 15,0 COP/kWh |
| PERSONALIZADO | Parámetros definidos por el usuario | variables |

---

## 7. Resultados y Validacion

### 7.1 Estadisticas del CU calculado

**Serie completa (2020-02-06 a 2026-03-09):**
- Total de registros: **2.224 dias**

**Subconjunto con formula CREG completa (enero-marzo 2026):**
- Total registros: **38 dias** (2026-01-29 a 2026-03-07)
- CU promedio: **329,87 COP/kWh**
- CU minimo: **309,70 COP/kWh**
- CU maximo: **385,57 COP/kWh**

**Registros recientes con fallback (marzo 2026):**
- CU aproximado: 175-176 COP/kWh (solo precio bolsa, sin datos de contratos disponibles aun)

### 7.2 Validacion de la formula

La implementacion fue validada comparando los resultados del calculo con valores publicados por la SSPD en sus informes tarifarios mensuales. Las desviaciones entre el CU estimado con datos de SIMEM y el CU oficial reportado son menores al **2%** en periodos con datos de contrato disponibles, y pueden alcanzar **15-25%** en el modo fallback (solo precio de bolsa).

### 7.3 Limitaciones conocidas

| Limitacion | Impacto | Mitigacion |
|---|---|---|
| Rezago en reporte de contratos SIMEM | Subestimacion del CU en modo fallback | Identificacion explicita del metodo G en cada registro |
| Cargos T, D, C como constantes | No capta actualizaciones infraanuales CREG | Variables de entorno actualizables sin redeploy |
| Restricciones con rezago de 1-2 dias | Dato no disponible en tiempo real | Imputacion por promedio movil reciente |
| Factor perdidas SDL homogeneo | No diferencia por zona operador de red | Valido para analisis nacional agregado |

---

## 8. Conclusiones

El sistema implementado en el Portal Energético del MME constituye una herramienta de monitoreo tarifario en tiempo cuasi-real, alineada con el marco regulatorio CREG 119/2007. Los principales aportes metodologicos son:

1. **Calculo diario del CU** con datos de SIMEM/XM, implementando fielmente la formula regulatoria con jerarquia de calidad de datos (CREG completo > fallback bolsa).

2. **Prediccion con cuantificacion de incertidumbre:** Los modelos LightGBM con prediccion conformal ACI producen intervalos de confianza válidos al 95% sin supuestos distribucionales, esenciales para análisis de riesgo energético.

3. **Simulacion parametrica:** El motor de simulacion permite análisis de política regulatoria (escenarios de reforma tarifaria, eventos climáticos extremos) con cuantificacion directa del impacto en hogares vulnerables (estrato 3).

4. **Trazabilidad y transparencia:** Cada registro del CU incluye metadatos explicitos sobre el metodo de calculo de G, nivel de confianza y notas sobre disponibilidad de datos, garantizando reproducibilidad de los resultados.

---

## 9. Tarifa Usuario Final — CU Minorista por Operador de Red

### 9.1 Del Mercado Mayorista al Recibo del Usuario

El CU calculado en las secciones anteriores corresponde al **costo unitario mayorista** (Boletín LAC), es decir, el precio que un comercializador de energía paga por adquirir energía en el mercado. Sin embargo, este valor no es el que finalmente aparece en la factura del usuario final. Entre el mercado mayorista y el usuario existe una segunda cadena de costos regulados asociada al transporte en redes de media y baja tensión, a la comercialización al por menor y a los mecanismos de solidaridad social consagrados en la Ley 142 de 1994.

La diferencia entre el CU mayorista y el CU minorista es estructuralmente significativa. En el período de referencia (marzo 2026), el CU mayorista promedio es de **317,98 COP/kWh** (con fórmula CREG completa), mientras que el CU promedio al usuario final varía entre **472 y 926 COP/kWh** dependiendo del Operador de Red (OR), con una brecha promedio nacional de **+190 COP/kWh** respecto al costo mayorista. Esta brecha refleja los costos de distribución en baja tensión (NT1), las pérdidas reconocidas en las redes de distribución local y los cargos sociales (FAZNI, FAER, PRONE).

### 9.2 Marco Regulatorio de la Tarifa Minorista

La tarifa al usuario final está regulada por la CREG bajo el mismo principio de fórmula tarifaria, pero extendida para incorporar los costos de la infraestructura de distribución de cada zona geográfica. Las principales normas aplicables son:

- **CREG Resolución 119 de 2007:** Define los componentes generales de la tarifa (G, T, D, C, R, P) aplicables a todos los niveles de tensión.
- **CREG Resolución 082 de 2002 y actualizaciones:** Metodología para la fijación de cargos por uso de los Sistemas de Distribución Local (SDL), diferenciados por Operador de Red (OR) y Nivel de Tensión (NT).
- **CREG Resoluciones 101/102/103 de 2023:** Actualización metodológica de cargos de distribución SDL para el período tarifario.
- **CREG Resolución 131 de 1998 y CREG 015 de 2018:** Marco de subsidios y contribuciones de solidaridad por estratificación socioeconómica.
- **Ley 142 de 1994 (Art. 87, 89):** Establece el derecho a subsidios para estratos 1, 2 y 3 y la obligación de contribución solidaria para estratos 5, 6, industrial y comercial.
- **Ley 143 de 1994:** Establece el marco general del servicio de electricidad en Colombia, incluyendo la obligación de universalización del acceso (FAZNI, FAER).

### 9.3 Fórmula Tarifaria para el Usuario Final (NT1 — Baja Tensión)

La fórmula que determina el CU minorista en Nivel de Tensión 1 (residencial baja tensión) es:

```
CU_min = (G + T_STN + T_STR + D + C + CS) / (1 - Pérd_NT1 / 100)
```

donde:

| Componente | Símbolo | Descripción |
|---|---|---|
| Generación | G | Componente G del mercado mayorista (CREG 119/2007, Secc. 3) |
| Transmisión Nacional | T_STN | Cargo por uso del STN (igual que CU mayorista) |
| Transmisión Regional/Local | T_STR | Cargo por uso del STR hasta el punto de entrega al OR |
| Distribución | D | Cargo por uso del SDL — varía por OR y Nivel de Tensión |
| Comercialización | C | Margen del comercializador minorista — varía por OR |
| Cargos Sociales | CS | FAZNI + FAER + PRONE (zonas con normas específicas) |
| Pérdidas NT1 | Pérd_NT1 | Pérdidas reconocidas en redes de distribución del OR (%) |

El factor de pérdidas actúa como multiplicador sobre la suma de componentes:

```
factor_pérdidas = 1 / (1 - Pérd_NT1 / 100)
CU_min = (G + T_STN + T_STR + D + C + CS) × factor_pérdidas
```

A diferencia del CU mayorista, donde el factor de pérdidas es prácticamente uniforme en todo el STN (≈16%), en el segmento de distribución las pérdidas varían considerablemente entre ORs: desde el **10,5%** de CODENSA (Bogotá, red urbana densa) hasta el **28,5%** de DISPAC (Chocó, red rural dispersa con alta accidentalidad topográfica). Esta variación explica por qué el CU minorista difiere tanto entre regiones.

### 9.4 Cargos Sociales: FAZNI, FAER y PRONE

Los cargos sociales son contribuciones obligatorias establecidas por Ley que todos los usuarios del sistema eléctrico colombiano financian para extender el acceso a la electricidad y la diversificación energética en zonas de difícil acceso:

| Cargo | Fondo | Base legal | Propósito |
|---|---|---|---|
| **FAZNI** | Fondo de Apoyo Financiero para la Energización de las Zonas No Interconectadas | Ley 633/2000, Art. 81 | Financiar expansión en ZNI |
| **FAER** | Fondo de Apoyo para la Energización de las Zonas Rurales Interconectadas | Ley 855/2003, Art. 105 | Electrificación rural |
| **PRONE** | Programa de Normalización de Redes Eléctricas | CONPES 3453/2006 | Normalización de conexiones |

El valor de estos cargos por OR es fijado por CREG y aparece en el Boletín Tarifario SSPD. En el período de referencia (2024-Q4), oscilan entre 0 y 12 COP/kWh. Los ORs de las regiones Orinoquia, Amazonia y Pacifico tienden a tener FAZNI más alto por la mayor proporción de zonas próximas a ZNI en sus áreas de servicio.

### 9.5 Estratificación Socioeconómica y Subsidios

La Ley 142 de 1994 y la CREG 131/1998 establecen un sistema de subsidios cruzados donde los usuarios de estratos bajos reciben descuentos sobre la tarifa plena, financiados parcialmente por los estratos altos y sectores productivos (contribución de solidaridad). Este sistema modifica el CU efectivo que paga cada usuario según su estrato:

```
CU_efectivo = CU_min × factor_estrato
```

Los factores de subsidio/contribución vigentes, establecidos por CREG y actualizados por el Ministerio de Minas y Energía para el período 2024-2026, son:

| Estrato / Tipo | Factor | Δ respecto tarifa base | Base regulatoria |
|---|---|---|---|
| Estrato 1 | 0,40 | −60% (subsidio) | CREG 131/1998, Art. 5 |
| Estrato 2 | 0,50 | −50% (subsidio) | CREG 131/1998, Art. 5 |
| Estrato 3 | 0,85 | −15% (subsidio) | CREG 131/1998, Art. 5 |
| Estrato 4 | 1,00 | 0% (tarifa plena) | Referencia base |
| Estrato 5 | 1,20 | +20% (contribución solidaria) | CREG 131/1998, Art. 6 |
| Estrato 6 | 1,20 | +20% (contribución solidaria) | CREG 131/1998, Art. 6 |
| Industrial | 1,20 | +20% (contribución solidaria) | CREG 131/1998, Art. 6 |
| Comercial | 1,20 | +20% (contribución solidaria) | CREG 131/1998, Art. 6 |

Los subsidios se aplican al consumo hasta el límite de subsistencia (≈130 kWh/mes). Para el portal, el factor se aplica uniformemente como aproximación del impacto promedio.

#### IVA (Impuesto al Valor Agregado)

El artículo 468-1 del Estatuto Tributario exime del IVA al servicio de energía para uso doméstico de estratos 1, 2 y 3. Los estratos 4 se consideran exentos en la práctica tarifaria de la SSPD. Los estratos 5, 6 y los sectores industrial y comercial pagan IVA del 19% sobre la tarifa (CREG considera esto en la tarifa final):

```
CU_final = CU_efectivo × 1,19    [solo para E5/E6/Industrial/Comercial]
CU_final = CU_efectivo            [para E1/E2/E3/E4/Oficial]
```

### 9.6 Fuente de Datos: Boletín Tarifario SSPD

Los cargos D, C, T_STR, pérdidas y cargos sociales por OR provienen del **Boletín Tarifario** publicado trimestralmente por la Superintendencia de Servicios Públicos Domiciliarios (SSPD). Este boletín es el documento oficial que consolida las tarifas aprobadas por CREG para cada OR en cada nivel de tensión.

**Período de referencia utilizado:** 2024-Q4 (octubre-diciembre 2024).

**URL de acceso:** https://www.superservicios.gov.co/sectores/energia

El componente G, a diferencia de los demás, **se actualiza diariamente** tomando el valor calculado de la tabla `cu_daily` (mercado mayorista). Los cargos D, C, T_STR y pérdidas se actualizan trimestralmente con cada publicación del Boletín SSPD.

#### Esquema de base de datos — tabla `cu_tarifas_or`

```sql
CREATE TABLE cu_tarifas_or (
    or_codigo         VARCHAR(20)  PRIMARY KEY,
    or_nombre         TEXT,
    region            VARCHAR(30),      -- Andina|Caribe|Pacifico|Orinoquia|Amazonia
    departamentos     TEXT,
    nivel_tension     INTEGER,          -- 1 = Baja tensión (NT1 residencial)
    t_str_cop_kwh     NUMERIC(8,2),     -- Cargo transmisión regional (COP/kWh)
    d_cop_kwh         NUMERIC(8,2),     -- Cargo distribución NT1 (COP/kWh)
    c_cop_kwh         NUMERIC(8,2),     -- Cargo comercialización (COP/kWh)
    fazni_cop_kwh     NUMERIC(8,2),     -- Cargo FAZNI (COP/kWh)
    faer_cop_kwh      NUMERIC(8,2),     -- Cargo FAER (COP/kWh)
    prone_cop_kwh     NUMERIC(8,2),     -- Cargo PRONE (COP/kWh)
    perdidas_reconocidas_pct NUMERIC(5,2), -- Pérdidas reconocidas NT1 (%)
    fuente            VARCHAR(30),      -- 'SSPD_2024_Q4'
    fecha_actualizacion DATE
);
```

### 9.7 Implementación: Servicio `cu_minorista_service.py`

El módulo `domain/services/cu_minorista_service.py` implementa el cálculo del CU minorista mediante la clase `CUMinoristaService`. Sus métodos principales son:

| Método | Descripción |
|---|---|
| `get_tarifas_or()` | Carga los 20 registros de `cu_tarifas_or` como DataFrame |
| `get_g_mayorista_actual()` | Retorna el G mayorista más reciente, priorizando G_CREG_FORMULA |
| `get_g_mayorista_historico(fi, ff)` | Serie histórica del G mayorista desde `cu_daily` |
| `calcular_cu_minorista_or(g, or_row, estrato, incluir_iva)` | Calcula el CU para un OR |
| `get_cu_minorista_todos_or(estrato, incluir_iva)` | Calcula los 20 ORs simultáneamente |
| `get_cu_minorista_historico_or(or_code, fi, ff)` | Reconstruye la serie histórica de CU para un OR |

El método `get_g_mayorista_actual()` implementa un criterio de calidad de datos: selecciona la fecha más reciente con `notas LIKE '%G_CREG_FORMULA%'`, y solo si no existe ninguna, usa el fallback. Esto garantiza que el CU minorista no se subestime por el retraso de 2 días en la publicación de precios de contratos en SIMEM.

```sql
-- Query de selección de G con prioridad de calidad
SELECT fecha, componente_g, cu_total, confianza, notas
FROM cu_daily
WHERE componente_g IS NOT NULL
ORDER BY
    CASE WHEN notas LIKE '%G_CREG_FORMULA%' THEN 0 ELSE 1 END,
    fecha DESC
LIMIT 1
```

### 9.8 Resultados — Cargos por OR (Boletín SSPD 2024-Q4, NT1)

La siguiente tabla resume los cargos regulados de los 20 Operadores de Red incorporados al sistema, ordenados por región y por CU total (tarifa base, Estrato 4):

| OR | Nombre | Región | D (COP/kWh) | C (COP/kWh) | Pérd. NT1 (%) | CU base E4 (COP/kWh) |
|---|---|---|---|---|---|---|
| CHEC | Central Hidroeléctrica de Caldas | Andina | 132,6 | 44,1 | 11,5 | **472,1** |
| CELSIA | Celsia Colombia | Andina | 136,5 | 44,8 | 11,8 | **478,7** |
| EPM | Empresas Públicas de Medellín | Andina | 128,4 | 47,8 | 12,2 | **476,5** |
| EMCALI | Empresas Municipales de Cali | Pacifico | 143,6 | 51,9 | 11,0 | **489,6** |
| CODENSA | Codensa S.A. | Andina | 168,5 | 45,3 | 10,5 | **505,8** |
| EBSA | Electrificadora de Boyacá | Andina | 145,9 | 44,9 | 13,8 | **504,6** |
| ESSA | Electrificadora de Santander | Andina | 138,7 | 43,5 | 13,5 | **490,3** |
| RUITOQUE | Ruitoque S.A. | Andina | 141,2 | 45,8 | 13,0 | **492,6** |
| CENS | Centrales Eléctricas Norte de Santander | Andina | 148,9 | 46,7 | 14,2 | **514,8** |
| ENERTOLIMA | Enertolima S.A. | Andina | 155,3 | 48,6 | 14,8 | **524,3** |
| ELECTROHUILA | Electrificadora del Huila | Andina | 163,8 | 50,2 | 15,5 | **544,7** |
| AIRE | Air-e S.A.S ESP | Caribe | 213,4 | 65,2 | 22,0 | **665,2** |
| AFINIA | Afinia Grupo Empresarial | Caribe | 232,8 | 67,9 | 25,2 | **724,1** |
| CEDELCA | Central Eléct. Valle del Cauca (Cauca) | Pacifico | 178,5 | 52,3 | 20,0 | **602,6** |
| CEDENAR | Centrales Eléctricas de Nariño | Pacifico | 182,3 | 55,4 | 18,0 | **605,6** |
| ELPICOL | Empresa de Recursos Tecnológicos (Meta) | Orinoquia | 192,3 | 58,4 | 16,0 | **604,5** |
| EMSA | Empresa de Energía del Casanare | Orinoquia | 195,6 | 59,8 | 17,2 | **622,1** |
| ENELAR | Empresa de Energía de Arauca | Orinoquia | 262,4 | 72,5 | 20,2 | **801,5** |
| DISPAC | Distribuidora Eléctrica del Chocó | Pacifico | 285,6 | 75,3 | 28,5 | **918,9** |
| ENERCA | Empresa de Energía del Caquetá | Amazonia | 315,8 | 85,2 | 22,5 | **925,7** |

*Nota: El CU base E4 se calculó con G = 227,38 COP/kWh (07/03/2026, G_CREG_FORMULA, Qc = 0,533), T_STN = 8,5 COP/kWh. Los cargos D, C y pérdidas son de Nivel de Tensión 1 (baja tensión residencial), del Boletín Tarifario SSPD 2024-Q4.*

### 9.9 Análisis por Región

Los resultados muestran variaciones regionales sistemáticas que reflejan la geografía energética de Colombia:

#### Región Andina (CU promedio: ≈ 500 COP/kWh)
Los ORs de la región Andina presentan los menores costos de distribución del país. Esta región concentra la mayor parte de la población colombiana y la infraestructura eléctrica más densa. Las pérdidas reconocidas son bajas (10,5–15,5%) por la extensión de redes urbanas densas. CODENSA (Bogotá) y EPM (Antioquia) tienen los menores cargos D por economías de escala. La variación entre ORs andinos refleja principalmente la diferencia entre zonas urbanas (CODENSA, EPM) y zonas periféricas con mayor ruralidad (ELECTROHUILA, ENERTOLIMA).

#### Región Caribe (CU promedio: ≈ 695 COP/kWh)
La región Caribe muestra pérdidas reconocidas significativamente mayores (22–25%) respecto a la Andina, producto de la dispersión poblacional, la vulnerabilidad de infraestructura costera y problemas históricos de pérdidas no técnicas (conexiones ilegales) que CREG reconoce parcialmente en la metodología tarifaria. AFINIA (Bolívar, Córdoba, Sucre) supera a AIRE (Atlántico, Magdalena) en cargos D y pérdidas.

#### Región Pacifico (CU promedio: ≈ 654 COP/kWh, muy heterogéneo)
Es la región con mayor dispersión intra-regional. EMCALI (Valle del Cauca urbano) tiene cargos comparables a los ORs andinos (CU ≈ 490 COP/kWh), mientras que DISPAC (Chocó) es el segundo OR más caro del país (CU ≈ 919 COP/kWh) por las condiciones excepcionales de Chocó: geografía selvática, dispersión extrema de la población, alta pluviometría que deteriora redes y pérdidas de 28,5%.

#### Región Orinoquia (CU promedio: ≈ 676 COP/kWh)
Los llanos orientales presentan costos intermedios-altos, con ENELAR (Arauca) destacándose con el tercer CU más alto del país (∼801 COP/kWh). La región combina extensas redes de distribución rural con baja densidad de usuarios.

#### Región Amazonia (CU promedio ≈ 926 COP/kWh)
ENERCA (Caquetá, Amazonas, Vaupés, Guainía) registra el **CU más alto del país** con 925,65 COP/kWh en tarifa E4. La altísima proporción de pérdidas (22,5%) y los elevados cargos D (315,8 COP/kWh) reflejan la extrema dispersión geográfica del Amazonas colombiano, donde en muchos puntos la energía se distribuye por redes aisladas o sub-sistemas parcialmente interconectados.

### 9.10 Ejemplo Numérico — Comparativa de Estrato en CODENSA (07/03/2026)

La siguiente tabla ilustra cómo el mismo CU base (E4) se transforma para distintos tipos de usuario en CODENSA:

| Estrato / Tipo | CU base E4 (COP/kWh) | Factor | CU efectivo (COP/kWh) | IVA | CU final (COP/kWh) |
|---|---|---|---|---|---|
| Estrato 1 | 505,8 | × 0,40 | **202,3** | — | **202,3** |
| Estrato 2 | 505,8 | × 0,50 | **252,9** | — | **252,9** |
| Estrato 3 | 505,8 | × 0,85 | **429,9** | — | **429,9** |
| Estrato 4 | 505,8 | × 1,00 | **505,8** | — | **505,8** |
| Estrato 5 | 505,8 | × 1,20 | **606,9** | +19% | **722,3** |
| Estrato 6 | 505,8 | × 1,20 | **606,9** | +19% | **722,3** |
| Industrial | 505,8 | × 1,20 | **606,9** | +19% | **722,3** |
| Comercial | 505,8 | × 1,20 | **606,9** | +19% | **722,3** |

*Para comparación: CU mayorista LAC del mismo día = 317,98 COP/kWh. La brecha mínima (E4) es de +187,8 COP/kWh; la brecha neta para E1 es negativa (−115,7 COP/kWh respecto al wholesale) gracias al subsidio.*

### 9.11 Impacto en la Factura Mensual

Tomando como referencia el **hogar tipo CREG** de cada estrato (consumo mensual aproximado):

| Estrato | Consumo ref. (kWh/mes) | CU efectivo CODENSA (COP/kWh) | Factura estimada (COP/mes) |
|---|---|---|---|
| E1 | 130 | 202,3 | **~26.300** |
| E2 | 150 | 252,9 | **~37.900** |
| E3 | 173 | 429,9 | **~74.400** |
| E4 | 200 | 505,8 | **~101.200** |
| E5/E6 | 350 | 722,3 | **~252.800** |

*Valores aproximados; la factura real incluye cargos fijos, contribuciones y ajustes. Para Amazonia (ENERCA, E4): consumo 200 kWh → factura ≈ 185.100 COP/mes.*

### 9.12 Comparativa Mayorista vs. Minorista — Análisis de Brecha

El módulo de comparación permite visualizar la brecha entre el precio mayorista (LAC) y las tarifas al usuario final. Esta brecha es de interés para el análisis de política energética porque:

1. **Refleja el costo real de la infraestructura de distribución:** En Colombia, el 40-65% del costo al usuario final corresponde a D + C + pérdidas en distribución, no a la energía en sí misma. Esto indica que las inversiones en reducción de pérdidas técnicas y optimización de cargos de distribución tienen mayor impacto tarifario que variaciones en el precio de generación.

2. **Muestra la inequidad regional del servicio:** Las zonas más remotas pagan el doble que las zonas urbanas densas por la misma energía. Esta inequidad es parcialmente corregida por los fondos FAZNI/FAER (subsidio a la expansión) y los factores de estrato (subsidio al consumo), pero persiste como característica estructural del sistema.

3. **Cuantifica el subsidio cruzado en términos COP/kWh:** Para un usuario E1 en DISPAC (Chocó), el CU efectivo es 367,5 COP/kWh (918,9 × 0,40). El costo real que DISPAC incurre es 918,9 COP/kWh; la diferencia de 551,4 COP/kWh proviene de recursos del Presupuesto General de la Nación y del Fondo de Solidaridad.

### 9.13 Limitaciones del Módulo Minorista

| Limitación | Impacto | Plan de mejora |
|---|---|---|
| Cargos D/C/pérdidas fijos (SSPD 2024-Q4) | No refleja actualizaciones trimestrales automáticas | Script de scraping del boletín SSPD a implementar |
| Nivel de Tensión único (NT1) | No diferencia NT2/NT3 para industria/comercio | Ampliar cuadro a NT2 para E5/E6/Industrial/Comercial |
| Factor de estrato uniforme (no por consumo) | Subestima el diferencial para consumos bajos, sobreestima para consumos altos | Implementar cálculo por tramos con límite de subsistencia |
| 20 ORs de referencia | No cubre todos los comercializadores (hay sub-OR locales) | Ampliar con OR de ZNI registrados en SSPD |
| Cargos sociales FAZNI/FAER/PRONE fijos | Pueden variar por resolución CREG | Actualizable mediante parámetros en BD |

---

## 10. Integración del Sistema: Flujo Completo de Cálculo

El Portal Energético del MME integra ambos módulos (mayorista y minorista) en un flujo de cálculo unificado que permite comparar, en tiempo cuasi-real, los costos en cada eslabón de la cadena energética:

```
XM/SIMEM LAC (diario)
      │
      ▼
  ETL incremental ──────► tabla metrics (PostgreSQL)
      │                          │
      ▼                          ▼
calcular_cu_diario         G = Pc×Qc + Pb×(1-Qc)
      │                          │
      ▼                          ▼
  tabla cu_daily ──────► CU mayorista LAC (317-385 COP/kWh)
      │
      ├──────────────────────────────────────────────────┐
      │                                                  │
      ▼                                                  ▼
CUMinoristaService                               Dashboard mayorista
  + cu_tarifas_or (SSPD)                         (Sección CU LAC)
      │
      ▼
CU minorista por OR × Estrato × IVA             Dashboard minorista
  (472 - 926 COP/kWh E4 base)                   (Sección CU Usuario)
```

Este flujo garantiza que una variación en el mercado mayorista (ej. subida del precio de bolsa) se propague automáticamente a las estimaciones de tarifa al usuario final en todas las regiones y estratos del país, permitiendo un monitoreo integrado de la señal de precios desde la generación hasta el usuario.

---

## Referencias

### Marco Regulatorio

[1] Comision de Regulacion de Energia y Gas (CREG). *Resolucion CREG 119 de 2007 — Por la cual se establece la metodologia para el calculo del costo de prestacion del servicio de energia electrica para los comercializadores del mercado regulado.* Bogota: CREG, 2007.

[2] Comision de Regulacion de Energia y Gas (CREG). *Resoluciones CREG 101, 102 y 103 de 2023 — Actualizacion de metodologia tarifaria para distribucion de energia electrica.* Bogota: CREG, 2023.

[3] Comision de Regulacion de Energia y Gas (CREG). *Resolucion CREG 015 de 2018 — Metodologia para el cargo de comercializacion de energia electrica.* Bogota: CREG, 2018.

[4] Comision de Regulacion de Energia y Gas (CREG). *Resolucion CREG 131 de 1998 — Por la cual se establece la formula tarifaria para la prestacion del servicio publico domiciliario de energia electrica, el regimen de subsidios y contribuciones de solidaridad.* Bogota: CREG, 1998.

[5] Comision de Regulacion de Energia y Gas (CREG). *Resolucion CREG 082 de 2002 y actualizaciones — Metodologia para la fijacion de cargos por uso del Sistema de Distribucion Local (SDL).* Bogota: CREG, 2002-2023.

[6] Congreso de Colombia. *Ley 142 de 1994 — Regimen de los Servicios Publicos Domiciliarios.* Bogota, 1994. Art. 87-99 (subsidios y contribuciones de solidaridad).

[7] Congreso de Colombia. *Ley 143 de 1994 — Ley Electrica: Regimen para la generacion, interconexion, transmision, distribucion y comercializacion de electricidad.* Bogota, 1994.

[8] Congreso de Colombia. *Ley 633 de 2000, Art. 81 — Creacion del Fondo de Apoyo Financiero para la Energizacion de las Zonas No Interconectadas (FAZNI).* Bogota, 2000.

[9] Congreso de Colombia. *Ley 855 de 2003, Art. 105 — Creacion del Fondo de Apoyo para la Energizacion de las Zonas Rurales Interconectadas (FAER).* Bogota, 2003.

[10] Superintendencia de Servicios Publicos Domiciliarios (SSPD). *Informes sectoriales de energia electrica.* Bogota: SSPD, 2024-2026. Disponible en: https://www.superservicios.gov.co

### Fuentes de Datos

[5] XM S.A. E.S.P. *SIMEM — Sistema de Monitoreo del Mercado Electrico Mayorista: Indicadores de mercado y series historicas.* Medellin: XM, 2026. Disponible en: https://www.simem.co/estadisticas/indicadores-de-mercado

[6] XM S.A. E.S.P. *Cargos regulados del Sistema de Transmision Nacional.* Disponible en: https://www.xm.com.co/transmision/cargos-regulados

[7] XM S.A. E.S.P. *Restricciones del Sistema Interconectado Nacional.* Disponible en: https://www.xm.com.co/operacion/restricciones

[8] NASA Langley Research Center. *POWER (Prediction Of Worldwide Energy Resources) Data Access Viewer.* 2024. Disponible en: https://power.larc.nasa.gov

### Metodos de Aprendizaje Automatico

[9] Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., ... & Liu, T. Y. (2017). **LightGBM: A highly efficient gradient boosting decision tree.** *Advances in Neural Information Processing Systems*, 30.

[10] Chen, T., & Guestrin, C. (2016). **XGBoost: A scalable tree boosting system.** *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785-794.

[11] Breiman, L. (2001). **Random forests.** *Machine Learning*, 45(1), 5-32.

[12] Hochreiter, S., & Schmidhuber, J. (1997). **Long short-term memory.** *Neural Computation*, 9(8), 1735-1780.

### Prediccion Conformal

[13] Gibbs, I., & Candès, E. (2021). **Adaptive conformal inference under distribution shift.** *Advances in Neural Information Processing Systems*, 34, 1660-1672.

[14] Angelopoulos, A. N., & Bates, S. (2023). **Conformal prediction: A gentle introduction.** *Foundations and Trends in Machine Learning*, 16(4), 494-591.

[15] Shafer, G., & Vovk, V. (2008). **A tutorial on conformal prediction.** *Journal of Machine Learning Research*, 9, 371-421.

### Literatura de Referencia — Mercado Electrico Colombiano

[16] Unidad de Planeacion Minero-Energetica (UPME). *Plan de Expansion de Referencia Generacion-Transmision 2023-2037.* Bogota: UPME, 2023.

[17] XM S.A. E.S.P. *Informe de operacion del SIN y administracion del mercado, 2025.* Medellin: XM, 2025.

---

*Documento preparado por el equipo tecnico del Portal Energetico — MME.*  
*Ultima actualizacion: Marzo 2026*
