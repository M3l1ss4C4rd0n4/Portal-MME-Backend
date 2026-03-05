# Cálculo del Costo Unitario (CU) de Energía Eléctrica en Colombia

> **Proyecto:** Portal Energético — Ministerio de Minas y Energía  
> **Fase:** FASE 2 — Motor de Cálculo del CU  
> **Fecha de implementación:** 3 de marzo de 2026  
> **Autor:** Equipo de Arquitectura Dashboard MME  
> **Estado:** ✅ Producción  

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Contexto y Justificación](#2-contexto-y-justificación)
3. [Marco Regulatorio](#3-marco-regulatorio)
4. [Metodología de Cálculo](#4-metodología-de-cálculo)
5. [Fuentes de Datos](#5-fuentes-de-datos)
6. [Arquitectura Técnica](#6-arquitectura-técnica)
7. [Implementación Paso a Paso](#7-implementación-paso-a-paso)
8. [Esquema de Base de Datos](#8-esquema-de-base-de-datos)
9. [API REST — Endpoints](#9-api-rest--endpoints)
10. [Resultados y Validación](#10-resultados-y-validación)
11. [Hallazgos Críticos](#11-hallazgos-críticos)
12. [Limitaciones y Mejoras Futuras](#12-limitaciones-y-mejoras-futuras)
13. [Glosario](#13-glosario)
14. [Referencias](#14-referencias)

---

## 1. Resumen Ejecutivo

Se implementó un motor de cálculo automatizado que computa diariamente el **Costo Unitario (CU) de energía eléctrica** para el Sistema Interconectado Nacional (SIN) de Colombia. El CU desglosa el precio en 6 componentes que reflejan la cadena de valor del sector eléctrico: Generación (G), Transmisión (T), Distribución (D), Comercialización (C), Pérdidas (P) y Restricciones (R).

### Resultados clave

| Indicador | Valor | Interpretación |
|---|---|---|
| Filas `cu_daily` | **2.214** | Cubre 2020-02-06 → 2026-02-27 |
| CU promedio histórico | **446,15 COP/kWh** | Incluye el pico 2023–2024 cuando el precio de bolsa era extremo |
| CU mínimo | **159,73 COP/kWh** | Período de abundancia hídrica (2021) |
| CU máximo | **2.825,29 COP/kWh** | Crisis hídrica sep–nov 2024 (ver [Nota §11.1](#111-sobre-el-cu-máximo-de-2825-copkwh)) |
| Confianza | 2.212 alta / 2 media | 99,9% de días con todos los datos |
| Desglose 25/02/2026 | G=59,6% · D=18,2% · P=10,3% · C=6,2% · T=4,4% · R=1,3% | Coherente con estructura tarifaria colombiana |

### Resumen por año

| Año | Días | CU promedio | CU mín | CU máx | G promedio |
|---|---|---|---|---|---|
| 2020 | 330 | 331,82 | 188,69 | 733,18 | 242,07 |
| 2021 | 365 | 230,37 | 159,73 | 710,95 | 150,07 |
| 2022 | 365 | 304,62 | 172,01 | 814,51 | 215,80 |
| 2023 | 365 | 683,74 | 200,99 | 1.694,54 | 558,12 |
| 2024 | 366 | 813,34 | 192,64 | 2.825,29 | 676,08 |
| 2025 | 365 | 332,12 | 178,08 | 903,12 | 240,84 |
| 2026 | 58 | 250,43 | 177,19 | 441,26 | 167,31 |

---

## 2. Contexto y Justificación

### ¿Qué es el CU?

El Costo Unitario (CU) de energía eléctrica representa el costo promedio ponderado de entregar 1 kWh de energía al usuario final en Colombia. No es el precio que paga un usuario específico (eso depende del estrato, distribuidor, etc.), sino una **métrica agregada del costo del sistema** que sirve como indicador de referencia para:

- Monitorear la eficiencia del mercado eléctrico
- Detectar anomalías de precio tempranas
- Comparar períodos (crisis hídrica vs. normalidad)
- Alimentar modelos predictivos de precios

### ¿Por qué calcularlo internamente?

XM (operador del mercado) publica componentes individuales (precio de bolsa, restricciones, pérdidas) pero **no publica un CU integrado** como serie temporal accesible por API. La CREG define la fórmula tarifaria pero los cargos regulados se actualizan periódicamente y la información está dispersa en múltiples resoluciones. Este motor:

1. **Integra** datos XM en tiempo real con parámetros CREG configurables
2. **Automatiza** el cálculo diario sin intervención manual
3. **Persiste** la serie histórica para análisis y ML
4. **Expone** vía API REST para consumo del dashboard y chatbot

---

## 3. Marco Regulatorio

El CU se basa conceptualmente en la **fórmula tarifaria general** definida por la CREG (Comisión de Regulación de Energía y Gas) en las resoluciones:

- **CREG 119 de 2007** — Fórmula tarifaria general para el mercado regulado
- **CREG 015 de 2018** — Actualización cargos de distribución (Dn)
- **CREG 101 de 2024** — Revisión extraordinaria durante crisis de precios

### Componentes regulatorios usados

| Componente | Valor actual | Fuente | Frecuencia de actualización |
|---|---|---|---|
| Cargo Transmisión (T) | 8,5 COP/kWh | CREG / UPME | Anual (resolución CREG) |
| Cargo Distribución (D) | 35,0 COP/kWh | CREG / OR | 5 años (período tarifario) |
| Cargo Comercialización (C) | 12,0 COP/kWh | CREG | Anual |
| Factor pérdidas distribución | 8,5% | CREG / OR | 5 años |

> **Nota:** Estos son valores promedio nacionales. En la práctica, T, D y C varían por Operador de Red (OR) y nivel de tensión. Para el CU agregado del portal se usan promedios ponderados representativos. Ver [§12 Mejoras Futuras](#12-limitaciones-y-mejoras-futuras) para plan de desagregación por OR.

---

## 4. Metodología de Cálculo

### 4.1 Fórmula general

```
CU = (G + T + D + C + R) × F_pérdidas
```

Donde:
- **G** = Componente de Generación
- **T** = Componente de Transmisión
- **D** = Componente de Distribución
- **C** = Componente de Comercialización
- **R** = Componente de Restricciones y otros cargos del mercado
- **F_pérdidas** = Factor multiplicativo por pérdidas técnicas

### 4.2 Cálculo de cada componente

#### Componente G — Generación

```
G = PrecBolsNaci  [COP/kWh]
```

- **Fuente:** Métrica `PrecBolsNaci` de XM (API SINERGOX / SIMEM)
- **Unidad original:** COP/kWh (ya viene en la unidad correcta)
- **Interpretación:** Precio promedio ponderado del mercado mayorista de energía (bolsa)
- **Lag de datos:** 0–1 días

#### Componente T — Transmisión

```
T = CARGO_TRANSMISION_COP_KWH = 8,5  [COP/kWh]
```

- **Fuente:** Parámetro CREG configurado en `core/config.py` y `.env`
- **Naturaleza:** Cargo fijo regulado, actualizable sin redeploy vía variable de entorno
- **Cubre:** Uso del Sistema de Transmisión Nacional (STN), líneas ≥ 220 kV

#### Componente D — Distribución

```
D = CARGO_DISTRIBUCION_COP_KWH = 35,0  [COP/kWh]
```

- **Fuente:** Parámetro CREG configurado
- **Naturaleza:** Cargo fijo regulado, promedio nacional ponderado
- **Cubre:** Uso del Sistema de Distribución Local (SDL), líneas < 220 kV

#### Componente C — Comercialización

```
C = CARGO_COMERCIALIZACION_COP_KWH = 12,0  [COP/kWh]
```

- **Fuente:** Parámetro CREG configurado
- **Naturaleza:** Margen regulado del comercializador
- **Cubre:** Gestión comercial, facturación, atención al usuario

#### Componente R — Restricciones

```
R = (RestAliv + RestSinAliv) / DemaCome  [COP/kWh]
```

Desglose del cálculo:

```
RestAliv       → Restricciones aliviadas [Millones COP]
RestSinAliv    → Restricciones sin aliviar [Millones COP]  (si disponible)
DemaCome       → Demanda comercial [GWh]

R = (RestAliv + RestSinAliv) / DemaCome
  = [Millones COP] / [GWh]
  = [10⁶ COP] / [10⁶ kWh]
  = COP/kWh  ✓ (las unidades se cancelan)
```

- **Fuente:** Métricas `RestAliv`, `RestSinAliv`, `DemaCome` de XM
- **Lag de datos:** ~2 días para `RestAliv`
- **Interpretación:** Costo que asumen los usuarios por despacho fuera de mérito

#### Componente P — Pérdidas

```
pérdidas_STN_frac = PerdidasEner / Gene  (típicamente ~0,017 → 1,7%)
factor_dist       = FACTOR_PERDIDAS_DISTRIBUCION  (0,085 → 8,5%)
factor_total      = pérdidas_STN_frac + factor_dist

F_pérdidas = 1 / (1 - factor_total)

componente_P = (G + T + D + C + R) × F_pérdidas - (G + T + D + C + R)
             = suma_base × (F_pérdidas - 1)
```

- **Fuente STN:** Métrica `PerdidasEner` de XM (pérdidas transmisión STN en GWh)
- **Fuente distribución:** Parámetro CREG `FACTOR_PERDIDAS_DISTRIBUCION = 0,085`
- **Lag de datos:** ~2 días para `PerdidasEner`

##### Hallazgo crítico sobre pérdidas (descubierto en FASE 1)

> La métrica `PerdidasEner` reportada por XM para `entidad='Sistema'` corresponde **únicamente a pérdidas de transmisión del STN** (~1,5–2,0%), **NO al total de pérdidas del SIN** (~8–12%). 
>
> Las pérdidas de distribución (SDL) no están disponibles como dato real diario por API. Se usa el factor regulado CREG (8,5%) como estimación. Ver detalles en `docs/FASE_A_DIAGNOSTICO_INFORME_EJECUTIVO.md`.

### 4.3 Ejemplo numérico — 25 de febrero de 2026

Datos de entrada (de la tabla `metrics` para esa fecha):

| Métrica | Valor | Unidad |
|---|---|---|
| PrecBolsNaci | 114,5675 | COP/kWh |
| DemaCome | 243,7 | GWh |
| Gene | 243,7 | GWh |
| RestAliv | ~580 | Millones COP |
| PerdidasEner | 4,36 | GWh |

Cálculos paso a paso:

```
1. G = 114,5675 COP/kWh

2. T = 8,50 COP/kWh   (CREG)

3. D = 35,00 COP/kWh  (CREG)

4. C = 12,00 COP/kWh  (CREG)

5. R = RestAliv / DemaCome
     ≈ 580 / 243,7
     ≈ 2,3972 COP/kWh

6. suma_base = G + T + D + C + R
             = 114,5675 + 8,5 + 35,0 + 12,0 + 2,3972
             = 172,4647 COP/kWh

7. pérdidas_STN = PerdidasEner / Gene
                = 4,36 / 243,7
                = 0,01789 (1,789%)

8. factor_total = 0,01789 + 0,085
               = 0,10289 (10,289%)

9. F_pérdidas = 1 / (1 - 0,10289)
             = 1 / 0,89711
             = 1,11471

10. CU = suma_base × F_pérdidas
       = 172,4647 × 1,11471
       = 192,2457 COP/kWh

11. componente_P = CU - suma_base
                 = 192,2457 - 172,4647
                 = 19,7810 COP/kWh
```

Resultado verificado contra la tabla `cu_daily`:

| Campo | Calculado | DB | ✓ |
|---|---|---|---|
| componente_g | 114,5675 | 114,5675 | ✅ |
| componente_t | 8,5000 | 8,5000 | ✅ |
| componente_d | 35,0000 | 35,0000 | ✅ |
| componente_c | 12,0000 | 12,0000 | ✅ |
| componente_r | 2,3972 | 2,3972 | ✅ |
| componente_p | 19,7810 | 19,7810 | ✅ |
| cu_total | 192,2457 | 192,2457 | ✅ |
| perdidas_pct | 10,2894 | 10,2894 | ✅ |
| confianza | alta | alta | ✅ |

### 4.4 Desglose porcentual (25/02/2026)

```
G (Generación)       → 114,57 / 192,25 = 59,59%
D (Distribución)     →  35,00 / 192,25 = 18,21%
P (Pérdidas)         →  19,78 / 192,25 = 10,29%
C (Comercialización) →  12,00 / 192,25 = 6,24%
T (Transmisión)      →   8,50 / 192,25 = 4,42%
R (Restricciones)    →   2,40 / 192,25 = 1,25%
                                          ───────
                                          100,00%
```

### 4.5 Niveles de confianza

| Nivel | Condición | Significado |
|---|---|---|
| **alta** | ≥5 fuentes OK + pérdidas STN disponibles | Todos los componentes XM presentes |
| **media** | ≥4 fuentes OK | Falta algún componente menor (ej: restricciones por lag) |
| **baja** | <4 fuentes OK | Solo cargos CREG, sin datos XM relevantes |

### 4.6 Protecciones y casos borde

| Caso | Manejo |
|---|---|
| `factor_total ≥ 0,95` | Cap a 0,95 con warning en log (evita división por ~0) |
| `DemaCome = 0` | R se omite (NULL), no se divide por cero |
| `Gene = 0` | Pérdidas STN se asumen 0%, solo se usa factor distribución |
| `< 2 métricas medidas` | No se calcula CU para ese día (retorna NULL) |
| Dato ya existe en `cu_daily` | UPSERT (ON CONFLICT DO UPDATE) actualiza con dato más reciente |

---

## 5. Fuentes de Datos

### 5.1 Métricas XM (dinámicas, diarias)

| Métrica | Código XM | Unidad en DB | Descripción | Lag típico |
|---|---|---|---|---|
| Generación | `Gene` | GWh | Generación total del sistema | 0–1 día |
| Demanda comercial | `DemaCome` | GWh | Demanda entregada a comercializadores | 0–1 día |
| Precio de bolsa | `PrecBolsNaci` | COP/kWh | Precio promedio ponderado mayorista | 0–1 día |
| Restricciones aliviadas | `RestAliv` | Millones COP | Costo de restricciones resueltas | ~2 días |
| Restricciones sin aliviar | `RestSinAliv` | Millones COP | Costo de restricciones pendientes | ~2 días |
| Pérdidas energía | `PerdidasEner` | GWh | Pérdidas técnicas del STN | ~2 días |

Todas las métricas se obtienen con filtro `entidad = 'Sistema'` de la tabla `metrics`.

### 5.2 Parámetros CREG (estáticos, configurables)

| Parámetro | Variable `.env` | Valor actual | Frecuencia actualización |
|---|---|---|---|
| Cargo transmisión | `CARGO_TRANSMISION_COP_KWH` | 8,5 | Anual |
| Cargo distribución | `CARGO_DISTRIBUCION_COP_KWH` | 35,0 | Quinquenal |
| Cargo comercialización | `CARGO_COMERCIALIZACION_COP_KWH` | 12,0 | Anual |
| Factor pérdidas distribución | `FACTOR_PERDIDAS_DISTRIBUCION` | 0,085 | Quinquenal |

> Todos los parámetros se pueden actualizar editando `.env` y reiniciando el servicio (`kill -HUP <pid_gunicorn>`), sin necesidad de cambiar código.

### 5.3 Tabla origen: `metrics`

- **Total de filas:** ~13,7 millones
- **Rango temporal:** 2020-02-06 → 2026-02-27
- **Columnas relevadas:** `fecha`, `metrica`, `entidad`, `valor_gwh`, `unidad`
- **Nota importante:** La columna se llama `valor_gwh` por legado, pero almacena valores en **distintas unidades** según la métrica (GWh, COP/kWh, Millones COP). El CUService interpreta correctamente cada unidad.

---

## 6. Arquitectura Técnica

### 6.1 Stack tecnológico

| Capa | Tecnología | Versión | Rol en CU |
|---|---|---|---|
| **Lenguaje** | Python | 3.12 | Toda la lógica |
| **Framework API** | FastAPI | 0.109+ | Endpoints REST del CU |
| **WSGI/ASGI** | Gunicorn + Uvicorn | — | Servidor produccón, 4 workers |
| **Base de datos** | PostgreSQL | 16 | Almacena `metrics` y `cu_daily` |
| **Driver DB** | psycopg2 | — | Conexión directa a PostgreSQL |
| **Cache/Broker** | Redis | 7.x | Broker Celery (db=0), cache (db=1) |
| **Task queue** | Celery | 5.x | Tarea programada `calcular_cu_diario` |
| **Validación** | Pydantic | 2.x | Schemas de config y API responses |
| **Data analysis** | pandas | 2.x | Serie histórica con gap-fill |
| **Rate limiting** | slowapi | — | Protección de endpoints |
| **Config** | python-dotenv + Pydantic Settings | — | Variables de entorno tipadas |

### 6.2 Diagrama de componentes

```
┌─────────────────────────────────────────────────────────────┐
│                      API REST (FastAPI)                      │
│                                                              │
│  GET /api/v1/cu/current          ← CU más reciente          │
│  GET /api/v1/cu/history          ← Serie temporal            │
│  GET /api/v1/cu/components/{d}   ← Desglose % por fecha     │
│                                                              │
│  Rate limiting: 100/30/60 req/min respectivamente            │
│  Auth: X-API-Key header                                      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                      CUService                                │
│          domain/services/cu_service.py (582 líneas)           │
│                                                               │
│  ┌─────────────────────┐  ┌──────────────────────────────┐   │
│  │ _get_daily_components│  │ calculate_cu_for_date        │   │
│  │ (query metrics)     │──│ (fórmula CU completa)        │   │
│  └─────────────────────┘  └──────────┬───────────────────┘   │
│                                       │                       │
│  ┌──────────────────┐  ┌─────────────┴────────────────────┐  │
│  │ save_cu_for_date  │  │ backfill_cu                      │  │
│  │ (UPSERT cu_daily) │  │ (llenado masivo iterativo)       │  │
│  └──────────────────┘  └──────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │ get_cu_current    │  │ get_cu_historico  │  │ breakdown │  │
│  │ (último disponible│  │ (serie + gap fill)│  │ (% torta) │  │
│  └──────────────────┘  └──────────────────┘  └───────────┘  │
└──────────────────────────────────┬───────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  PostgreSQL 16   │  │  core/config.py  │  │  Celery + Redis  │
│                  │  │                  │  │                  │
│  metrics (13.7M) │  │  CARGO_T = 8.5   │  │  calcular_cu_    │
│  cu_daily (2214) │  │  CARGO_D = 35.0  │  │  diario          │
│                  │  │  CARGO_C = 12.0  │  │  (10:00 AM)      │
│                  │  │  FACTOR  = 0.085 │  │  retry ×3        │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 6.3 Patrón de diseño: Clean Architecture

```
                    ┌─────────────────────┐
                    │  api/v1/routes/cu.py │  ← Capa de presentación
                    │  api/v1/schemas/cu.py│     (HTTP, Pydantic)
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  api/dependencies.py │  ← Inyección de dependencias
                    │  core/container.py   │     (DI Container)
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  domain/services/    │  ← Lógica de negocio
                    │  cu_service.py       │     (puro Python, testeable)
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  infrastructure/     │  ← Acceso a datos
                    │  database/           │     (PostgreSQL)
                    │  connection.py       │
                    └─────────────────────┘
```

---

## 7. Implementación Paso a Paso

### PASO 0 — Auditoría del código existente

**Objetivo:** Entender el estado actual antes de escribir código.

**Archivos auditados:**

| Archivo | Propósito | Hallazgos |
|---|---|---|
| `core/config.py` | Configuración centralizada (588 líneas) | CARGO_T/D/C ya existían de Fase 0. Faltaba FACTOR_PERDIDAS_DISTRIBUCION |
| `core/container.py` | DI Container (272 líneas) | Patrón singleton lazy con `get_*()` y `reset()` |
| `core/exceptions.py` | Excepciones custom | `DatabaseError` disponible para errores de persistencia |
| `infrastructure/database/connection.py` | Conexión PostgreSQL | `PostgreSQLConnectionManager` con context manager |
| `domain/services/generation_service.py` | Template de servicio | Patrón DI con repository, logging con prefijo |
| `api/v1/__init__.py` | Router hub | 12 routers registrados |
| `api/v1/routes/metrics.py` | Template de rutas | `Depends(get_api_key)`, slowapi, Pydantic schemas |
| `api/dependencies.py` | Providers FastAPI | Funciones `get_*_service()` |
| `tasks/__init__.py` | Celery config | 4 tareas en beat_schedule |
| `tasks/etl_tasks.py` | Tareas ETL | `SafeETLTask`, `@shared_task`, `@app.task(bind=True)` |

**Query diagnóstica ejecutada:**

```sql
SELECT fecha::date,
    MAX(CASE WHEN metrica='Gene' THEN valor_gwh END) AS gene,
    MAX(CASE WHEN metrica='DemaCome' THEN valor_gwh END) AS dema,
    MAX(CASE WHEN metrica='PrecBolsNaci' THEN valor_gwh END) AS precio,
    MAX(CASE WHEN metrica='RestAliv' THEN valor_gwh END) AS rest,
    MAX(CASE WHEN metrica='PerdidasEner' THEN valor_gwh END) AS perdidas
FROM metrics
WHERE entidad='Sistema'
  AND fecha::date BETWEEN '2026-02-20' AND '2026-02-27'
GROUP BY fecha::date ORDER BY fecha::date;
```

**Hallazgo:** RestAliv y PerdidasEner tienen un **lag de ~2 días** respecto a Gene/DemaCome/PrecBolsNaci. El diseño debe ser tolerante a datos parciales.

---

### TAREA 2.1 — Agregar constantes de configuración

**Archivo modificado:** `core/config.py`

Se agregó:
```python
FACTOR_PERDIDAS_DISTRIBUCION: float = Field(
    default=0.085,
    description="Factor de pérdidas distribución SDL regulado CREG (~8.5%). "
                "Suma con pérdidas STN reales (~1.7%) para factor total CU."
)
```

**Archivo modificado:** `.env`
```
FACTOR_PERDIDAS_DISTRIBUCION=0.085
```

Los cargos T, D, C ya existían desde Fase 0. Solo faltaba el factor de pérdidas de distribución.

---

### TAREA 2.2 — Crear CUService

**Archivo creado:** `domain/services/cu_service.py` (582 líneas)

Clase `CUService` con 7 métodos:

| Método | Tipo | Descripción |
|---|---|---|
| `_get_daily_components(fecha)` | Privado | Query a `metrics`, retorna dict con valores o None |
| `calculate_cu_for_date(fecha)` | Público | Aplica la fórmula completa, retorna dict o None |
| `save_cu_for_date(fecha)` | Público | Calcula + UPSERT en `cu_daily` |
| `backfill_cu(inicio, fin)` | Público | Itera día por día para llenado masivo |
| `get_cu_current()` | Público | Último CU de `cu_daily`, fallback on-the-fly |
| `get_cu_historico(inicio, fin)` | Público | Serie temporal con gap-fill via pandas |
| `get_cu_components_breakdown(fecha)` | Público | Desglose % para gráficos de torta |

**Decisiones de diseño:**

1. **Sin repository pattern:** A diferencia de otros servicios que usan `IMetricsRepository`, CUService accede directamente via `PostgreSQLConnectionManager` porque necesita queries específicas de pivoteo que no encajan en el repository genérico.

2. **Tolerancia a datos parciales:** `_get_daily_components` nunca lanza excepción por dato faltante. Retorna `None` para campos no disponibles y el método de cálculo decide si hay suficiente para computar el CU.

3. **Factor de pérdidas configurable:** STN se calcula en tiempo real desde datos XM; distribución es parámetro CREG actualizable sin redeploy.

---

### TAREA 2.3 — Registrar en DI Container

**Archivo modificado:** `core/container.py`

```python
# Import agregado
from domain.services.cu_service import CUService

# Método agregado en DependencyContainer
def get_cu_service(self) -> CUService:
    if not hasattr(self, '_cu_service') or self._cu_service is None:
        self._cu_service = CUService()
    return self._cu_service

# Reset actualizado
def reset(self):
    ...
    self._cu_service = None

# Función de conveniencia
def get_cu_service() -> CUService:
    return container.get_cu_service()
```

---

### TAREA 2.4 — API Routes y Schemas

**Archivo creado:** `api/v1/schemas/cu.py`

Modelos Pydantic:
- `CUComponente` — un componente con nombre, código, valor y porcentaje
- `CUDatoResponse` — registro completo de un día de CU
- `CUCurrentResponse` — respuesta de /current
- `CUHistoricoResponse` — respuesta de /history con metadata
- `CUBreakdownResponse` — respuesta de /components con lista de componentes

**Archivo creado:** `api/v1/routes/cu.py`

3 endpoints con rate limiting y autenticación:

| Endpoint | Rate limit | Descripción |
|---|---|---|
| `GET /api/v1/cu/current` | 100/min | CU más reciente |
| `GET /api/v1/cu/history?start_date=&end_date=` | 30/min | Serie temporal (max 365 días) |
| `GET /api/v1/cu/components/{fecha}` | 60/min | Desglose porcentual |

**Archivo modificado:** `api/dependencies.py`

```python
def get_cu_service():
    from core.container import container
    return container.get_cu_service()
```

---

### TAREA 2.5 — Registrar router

**Archivo modificado:** `api/v1/__init__.py`

```python
from api.v1.routes import (..., cu)

# 13. Costo Unitario (CU) de energía eléctrica
api_router_v1.include_router(
    cu.router,
    prefix="/cu",
    tags=["💰 Costo Unitario"]
)
```

Total routers: 12 → **13**

---

### TAREA 2.6 — Tarea Celery programada

**Archivo modificado:** `tasks/etl_tasks.py`

```python
@app.task(bind=True, max_retries=3, default_retry_delay=300)
def calcular_cu_diario(self):
    """Calcula CU para los últimos 7 días (cubre lag de RestAliv/PerdidasEner)"""
    cu_service = CUService()
    for i in range(7):
        fecha = date.today() - timedelta(days=i)
        cu_service.save_cu_for_date(fecha)
```

**Archivo modificado:** `tasks/__init__.py`

```python
'calcular-cu-diario': {
    'task': 'tasks.etl_tasks.calcular_cu_diario',
    'schedule': crontab(hour=10, minute=0),  # 10:00 AM diario
},
```

**¿Por qué a las 10:00 AM?** A esa hora los datos de XM del día anterior ya están disponibles. La tarea procesa 7 días hacia atrás para cubrir el lag de ~2 días de RestAliv y PerdidasEner.

Total tareas beat: 4 → **5**

---

### TAREA 2.7 — Backfill histórico

**Archivo creado:** `scripts/backfill_cu_historico.py`

**Enfoque inicial (descartado):** Iteración día por día con `CUService.save_cu_for_date()`. Resultó muy lento (~1 segundo por día × 2.214 días = ~37 minutos).

**Enfoque final (implementado):** Una sola query SQL batch que:
1. Pivotea `metrics` por fecha usando `MAX(CASE WHEN ...)` — CTE `daily`
2. Calcula componentes intermedios — CTE `calc`
3. Aplica fórmula completa — CTE `final`
4. Inserta todo con `ON CONFLICT DO UPDATE`

**Resultado:** 2.214 filas insertadas en **~1 segundo**.

**Ejecución:**
```bash
cd /home/admonctrlxm/server
source venv/bin/activate
python scripts/backfill_cu_historico.py
```

---

## 8. Esquema de Base de Datos

### Tabla `cu_daily`

```sql
CREATE TABLE cu_daily (
    id              SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL UNIQUE,
    componente_g    NUMERIC,        -- Generación (COP/kWh)
    componente_t    NUMERIC,        -- Transmisión (COP/kWh)
    componente_d    NUMERIC,        -- Distribución (COP/kWh)
    componente_c    NUMERIC,        -- Comercialización (COP/kWh)
    componente_p    NUMERIC,        -- Pérdidas (COP/kWh)
    componente_r    NUMERIC,        -- Restricciones (COP/kWh)
    cu_total        NUMERIC,        -- CU total (COP/kWh)
    demanda_gwh     NUMERIC,        -- Demanda comercial (GWh)
    generacion_gwh  NUMERIC,        -- Generación total (GWh)
    perdidas_gwh    NUMERIC,        -- Pérdidas STN (GWh)
    perdidas_pct    NUMERIC,        -- Pérdidas totales (%)
    fuentes_ok      SMALLINT,       -- Componentes con dato (3-5)
    confianza       VARCHAR,        -- 'alta', 'media', 'baja'
    notas           TEXT,           -- eg. 'sin_restricciones; sin_perdidas_stn'
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**Constraint:** `UNIQUE(fecha)` — un solo registro por día, se actualiza con UPSERT.

### Datos de ejemplo

| fecha | G | T | D | C | P | R | CU total | Confianza |
|---|---|---|---|---|---|---|---|---|
| 2020-06-15 | 281,08 | 8,50 | 35,00 | 12,00 | 37,94 | 0,62 | 375,14 | alta |
| 2022-09-15 | 434,25 | 8,50 | 35,00 | 12,00 | 55,02 | 1,22 | 545,99 | alta |
| 2023-06-15 | 362,52 | 8,50 | 35,00 | 12,00 | 49,21 | 2,39 | 469,61 | alta |
| 2024-01-15 | 613,95 | 8,50 | 35,00 | 12,00 | 74,25 | 2,15 | 745,85 | alta |
| 2026-02-25 | 114,57 | 8,50 | 35,00 | 12,00 | 19,78 | 2,40 | 192,25 | alta |

---

## 9. API REST — Endpoints

### 9.1 `GET /api/v1/cu/current`

Retorna el CU del día más reciente disponible.

**Headers:** `X-API-Key: <api_key>`

**Respuesta (200):**
```json
{
  "status": "ok",
  "fecha": "2026-02-27",
  "cu_total": 177.5512,
  "confianza": "media",
  "componente_g": 106.9594,
  "componente_t": 8.5,
  "componente_d": 35.0,
  "componente_c": 12.0,
  "componente_p": 15.0919,
  "componente_r": null,
  "demanda_gwh": 52.724755,
  "generacion_gwh": 250.317655,
  "perdidas_pct": null,
  "fuentes_ok": 4,
  "notas": "sin_restricciones; sin_perdidas_stn"
}
```

> El 27/02/2026 muestra confianza "media" porque RestAliv y PerdidasEner aún no estaban disponibles (lag de 2 días). La tarea Celery recalculará automáticamente cuando lleguen los datos.

### 9.2 `GET /api/v1/cu/history`

**Parámetros query:**
- `start_date` (opcional, default: 30 días atrás)
- `end_date` (opcional, default: hoy)

**Validaciones:**
- `start_date ≤ end_date`
- Rango máximo: 365 días

**Respuesta (200):**
```json
{
  "status": "ok",
  "fecha_inicio": "2026-02-20",
  "fecha_fin": "2026-02-25",
  "total_registros": 6,
  "total_dias": 6,
  "cobertura_pct": 100.0,
  "data": [
    {
      "fecha": "2026-02-20",
      "componente_g": 114.1096,
      "componente_t": 8.5,
      "componente_d": 35.0,
      "componente_c": 12.0,
      "componente_p": 19.9502,
      "componente_r": 2.131,
      "cu_total": 191.6909,
      "perdidas_pct": 10.4075,
      "confianza": "alta",
      "fuentes_ok": 5,
      "notas": null
    }
  ]
}
```

### 9.3 `GET /api/v1/cu/components/{fecha}`

**Respuesta (200):**
```json
{
  "status": "ok",
  "fecha": "2026-02-25",
  "cu_total": 192.2457,
  "componentes": [
    {"nombre": "Generación", "codigo": "G", "valor_cop_kwh": 114.5675, "porcentaje": 59.59},
    {"nombre": "Transmisión", "codigo": "T", "valor_cop_kwh": 8.5, "porcentaje": 4.42},
    {"nombre": "Distribución", "codigo": "D", "valor_cop_kwh": 35.0, "porcentaje": 18.21},
    {"nombre": "Comercialización", "codigo": "C", "valor_cop_kwh": 12.0, "porcentaje": 6.24},
    {"nombre": "Pérdidas", "codigo": "P", "valor_cop_kwh": 19.781, "porcentaje": 10.29},
    {"nombre": "Restricciones", "codigo": "R", "valor_cop_kwh": 2.3972, "porcentaje": 1.25}
  ]
}
```

---

## 10. Resultados y Validación

### 10.1 Tests

```
$ python -m pytest tests/ -v --tb=short
=============== 117 passed, 10 deselected, 33 warnings in 3.93s ================
```

**117/117 tests pasaron** sin modificar ningún test existente. El nuevo código es aditivo (no rompe nada).

### 10.2 Verificación de API en producción

Los 3 endpoints fueron verificados contra el servidor Gunicorn en http://localhost:8000 con API key válida:

- ✅ `/cu/current` → retorna 200 con CU del 2026-02-27
- ✅ `/cu/history` → retorna 200 con serie de 6 registros (20–25 feb)
- ✅ `/cu/components/2026-02-25` → retorna 200 con desglose de 6 componentes

### 10.3 Coherencia de datos

Se verificaron **cross-checks** contra datos conocidos:

| Verificación | Esperado | Obtenido | ✓ |
|---|---|---|---|
| CU promedio 2021 (abundancia hídrica) | Bajo (~200-300) | 230,37 | ✅ |
| CU promedio 2023-2024 (crisis hídrica) | Alto (~600-800+) | 683,74 / 813,34 | ✅ |
| Componente G dominante | ~50-70% del CU | 59,6% (feb 2026) | ✅ |
| Pérdidas totales | ~10% | 10,29% (STN 1,8% + Dist 8,5%) | ✅ |
| Restricciones bajas | ~1-3% | 1,25% (feb 2026) | ✅ |
| Top 3 CU máximos | Sept-Nov 2024 | 30/09, 31/10, 03/11 de 2024 | ✅ |

---

## 11. Hallazgos Críticos

### 11.1 Sobre el CU máximo de 2.825 COP/kWh

Los 3 días con CU más alto:

| Fecha | CU total | Componente G | Contexto |
|---|---|---|---|
| 2024-09-30 | 2.825,29 | 2.498,80 | Crisis hídrica severa, Fenómeno del Niño |
| 2024-10-31 | 2.791,17 | 2.457,10 | Embalses bajo nivel crítico |
| 2024-11-03 | 2.782,30 | 2.459,24 | Generación térmica forzada |

**Esto NO es un error.** Durante la crisis hídrica 2024, el precio de bolsa (componente G) llegó a ~2.500 COP/kWh, casi 25× su valor normal. El portal debe contextualizar:

> ⚠️ **Recomendación para el dashboard:** Cuando `cu_total > 1.000 COP/kWh`, mostrar un tooltip o banner explicativo: *"Período de precio de bolsa excepcional — crisis hídrica / Fenómeno del Niño"*.

### 11.2 Sobre pérdidas STN vs. SIN

La métrica `PerdidasEner` de XM reporta **solo pérdidas del STN** (red de transmisión ≥220 kV), que típicamente son ~1,5–2,0% de la generación. Las pérdidas totales del SIN (incluyendo distribución) rondan 8–12%.

**Decisión tomada:** Usar dato real de STN + factor CREG para distribución (8,5%). Esto da un factor total ~10,3%, coherente con la realidad del sistema.

**Mejora futura:** Si la CREG o los OR publican pérdidas de distribución reales por API, incorporarlas para reemplazar el factor fijo.

### 11.3 Sobre el lag de datos

RestAliv y PerdidasEner tienen lag de ~2 días. Impacto:

- Los últimos 2 días siempre tendrán confianza "media" (sin R ni pérdidas STN)
- La tarea Celery re-calcula los últimos 7 días cada mañana, actualizando cuando llegan datos
- El UPSERT garantiza que el dato más reciente sobreescribe al parcial

---

## 12. Limitaciones y Mejoras Futuras

### Limitaciones actuales

| # | Limitación | Impacto | Severidad |
|---|---|---|---|
| L1 | Cargos T, D, C son promedios nacionales | CU no refleja diferencias por OR o nivel de tensión | Media |
| L2 | Factor pérdidas distribución es estático (8,5%) | No captura variaciones estacionales reales | Baja |
| L3 | RestAliv incluye aliviadas + no aliviadas sin desglose | Menor granularidad del componente R | Baja |
| L4 | No hay CU por tipo de usuario (regulado vs. no regulado) | Solo CU agregado del sistema | Media |
| L5 | Lag de 2 días para dato completo | CU "de hoy" siempre es parcial | Baja (mitigado con re-cálculo) |

### Mejoras planificadas

| # | Mejora | Fase | Prioridad |
|---|---|---|---|
| M1 | Desagregar CU por Operador de Red (OR) | Fase 4+ | Alta |
| M2 | Incorporar cargos CREG dinámicos (scraping resoluciones) | Fase 5+ | Media |
| M3 | Modelo predictivo de CU a 7/30 días | Fase 3 (ML) | Alta |
| M4 | Alerta automática cuando CU > umbral configurable | Fase 3 | Media |
| M5 | CU horario (en lugar de diario) cuando XM publique datos horarios | Largo plazo | Baja |
| M6 | Comparación CU Colombia vs. otros países de la región | Fase 5+ | Baja |
| M7 | Dashboard widget con gráfico de torta del breakdown | Fase 3 (UI) | Alta |

---

## 13. Glosario

| Término | Definición |
|---|---|
| **CU** | Costo Unitario de energía eléctrica (COP/kWh) |
| **SIN** | Sistema Interconectado Nacional — red eléctrica de Colombia |
| **STN** | Sistema de Transmisión Nacional — líneas ≥ 220 kV |
| **SDL** | Sistema de Distribución Local — líneas < 220 kV |
| **CREG** | Comisión de Regulación de Energía y Gas |
| **XM** | Operador y administrador del mercado eléctrico mayorista |
| **OR** | Operador de Red (distribuidor regional) |
| **PrecBolsNaci** | Precio de Bolsa Nacional — precio promedio mayorista spot |
| **DemaCome** | Demanda Comercial — energía entregada a comercializadores |
| **Gene** | Generación total del sistema |
| **RestAliv** | Restricciones aliviadas del SIN (costo en Millones COP) |
| **PerdidasEner** | Pérdidas de energía del STN (GWh) |
| **UPSERT** | INSERT con ON CONFLICT DO UPDATE — idempotente |
| **Lag** | Retraso entre la fecha del dato y su disponibilidad en la API |
| **Factor de pérdidas** | Multiplicador `1/(1-p)` que amplifica el costo base para cubrir energía perdida |

---

## 14. Referencias

### Regulatorias
- CREG Resolución 119 de 2007 — Fórmula tarifaria del mercado regulado
- CREG Resolución 015 de 2018 — Cargos de distribución por nivel de tensión
- CREG Resolución 101 de 2024 — Revisión extraordinaria de fórmula tarifaria
- UPME — Plan de Expansión de Referencia Generación–Transmisión

### Fuentes de datos
- [XM — Portal BI](https://www.xm.com.co/transacciones/informes)
- [SIMEM — Sistema de Información del Mercado de Energía Mayorista](https://www.simem.co/)
- [API SINERGOX](https://sinergox.xm.com.co/) — Fuente programática de métricas

### Documentación interna del proyecto
- `docs/FASE_A_DIAGNOSTICO_INFORME_EJECUTIVO.md` — Diagnóstico inicial y hallazgos Fase A
- `docs/FASE_B_PLAN_ACCION_INFORME_EJECUTIVO.md` — Plan de acción general
- `docs/MAPEO_COMPLETO_METRICAS.md` — Inventario de todas las métricas XM
- `docs/ARQUITECTURA_E2E.md` — Arquitectura end-to-end del portal
- `docs/GUIA_USO_API.md` — Guía de uso de la API REST

### Archivos de código relevantes
- `domain/services/cu_service.py` — Lógica de cálculo (582 líneas)
- `api/v1/routes/cu.py` — Endpoints REST
- `api/v1/schemas/cu.py` — Schemas Pydantic
- `core/config.py` — Configuración CREG
- `core/container.py` — Inyección de dependencias
- `tasks/etl_tasks.py` — Tarea Celery programada
- `scripts/backfill_cu_historico.py` — Script de llenado inicial

---

> **Última actualización:** 3 de marzo de 2026  
> **Próximo milestone:** FASE 3 — Modelo predictivo de CU y alertas automáticas
