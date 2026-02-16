# Análisis de Causas Raíz de Fallos en el ETL

**Fecha:** 2025-07-09  
**Autor:** Arquitecto ETL  
**Alcance:** Pipeline ETL completo — Fuentes XM/SIMEM → PostgreSQL → Servicios → Dashboard

---

## 1. Diagrama de Flujo General del ETL

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Fuentes    │     │   ETL Scripts    │     │   PostgreSQL     │     │  Servicios   │
│  Externas   │────►│                  │────►│  portal_         │────►│  de Dominio  │
│             │     │                  │     │  energetico      │     │              │
│ • XM API    │     │ etl_todas_       │     │                  │     │ • hydrology  │
│   (pydataxm)│     │   metricas_xm.py │     │ metrics (13.4M)  │     │ • generation │
│ • SIMEM API │     │ etl_transmision  │     │ metrics_hourly   │     │ • demand     │
│   (pydatasim│     │   .py            │     │ catalogos        │     │ • prices     │
│             │     │ config_metricas  │     │ predictions      │     │ • restrict.  │
│             │     │   .py            │     │ lineastransmision│     │ • system     │
└──────┬──────┘     └────────┬─────────┘     └────────┬─────────┘     └──────┬───────┘
       │    FALLO 1          │   FALLO 2-5            │   FALLO 6           │   FALLO 7
       │  (Fuente caída,     │  (Conversión,          │  (Datos corruptos   │  (Filtros
       │   timeout,          │   unidades,            │   ya insertados,    │   incorrectos,
       │   formato           │   duplicados,          │   sin validación    │   cálculos
       │   cambiado)         │   config dup.)         │   previa)           │   sobre datos
       │                     │                        │                     │   malos)
       ▼                     ▼                        ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ Dashboard    │     │     API      │     │   Cron       │     │  Validación      │
│ (Dash :8050) │     │ (FastAPI     │     │  0 */6 * * * │     │  (validar_etl.py │
│              │◄────│  :8000)      │     │              │     │   ← aún SQLite!) │
│ 13 secciones │     │ 28 endpoints │     │ Cada 6 horas │     │                  │
│              │     │              │     │              │     │ FALLO 8          │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────────┘
   FALLO 9              FALLO 10            FALLO 11              (Script obsoleto)
  (Gráficos con         (Swagger 405         (Si falla 1 métrica  
   datos cero o          ya resuelto)         se aborta todo?)    
   unidades mixtas)                                               
```

---

## 2. Catálogo de Fallos Identificados

### FALLO 1 — Fuente externa caída o con formato cambiado

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl_todas_metricas_xm.py:descargar_metrica()` ≈ L290 |
| **Síntoma**     | `pydataxm` arroja excepción, DataFrame vacío, o columnas inesperadas |
| **Causa raíz**  | La API de XM (`servapibi.xm.com.co`) cambia nombres de columnas, tiene timeouts o devuelve 500. No hay retry ni fallback. |
| **Impacto**     | La métrica no se carga; si ocurre al inicio del loop puede abortar métricas posteriores |
| **Estado**      | ⚠️ SIN MITIGACIÓN — el try/except solo loggea y sigue |
| **Mitigación**  | Agregar retry con backoff exponencial (max 3 intentos, espera 5/15/30 s). Validar que el DF tenga columnas esperadas antes de procesarlo. |

---

### FALLO 2 — `detectar_conversion()` clasifica mal la métrica

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl_todas_metricas_xm.py:detectar_conversion()` ≈ L108 |
| **Síntoma**     | Unidad incorrecta en BD (ej: `CapEfecNeta` con GWh en vez de MW, `AporCaudal` con GWh en vez de m³/s) |
| **Causa raíz**  | Usa pattern matching por substring (`'Gene' in metric_id`) que clasifica métricas erróneamente. `CapEfecNeta` contiene implícitamente la rama que matchea antes. Nuevas métricas caen en `sin_conversion` por defecto. |
| **Impacto**     | **CRÍTICO** — 103,298 registros de `CapEfecNeta` con unidad errada, 69,934 de `AporCaudalMediHist` con GWh |
| **Estado**      | 🔧 PARCIALMENTE RESUELTO — se agregaron listas explícitas pero sigue siendo frágil |
| **Mitigación**  | Reemplazar `detectar_conversion()` por lookup en `etl_rules.py:get_conversion_type()`. Cada nueva métrica debe agregarse a `_RULES` con su regla explícita. |

---

### FALLO 3 — Llave duplicada `metricas_restricciones` en config_metricas.py

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl/config_metricas.py` líneas ~270 y ~340 |
| **Síntoma**     | Métricas de restricciones del primer bloque se pierden silenciosamente |
| **Causa raíz**  | Python permite claves duplicadas en dict literals — la segunda sobrescribe la primera sin error ni warning |
| **Impacto**     | Métricas como `RestAliv`, `RestSinAliv` del primer bloque nunca se procesan en ciertos modos batch |
| **Estado**      | ❌ SIN RESOLVER |
| **Mitigación**  | Renombrar la segunda clave a `metricas_restricciones_2` o unificar ambos bloques. Agregar linter `pylint-duplicate-keys`. |

---

### FALLO 4 — `asegurar_columna_valor()` genera `Value` dos veces

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl_todas_metricas_xm.py:asegurar_columna_valor()` ≈ L250 y `convertir_unidades()` ≈ L167 |
| **Síntoma**     | Al pasar un DF con columnas horarias, `asegurar_columna_valor()` crea `Value` sumando/promediando, y luego `convertir_unidades()` vuelve a sumar/promediar y dividir. Doble conversión. |
| **Causa raíz**  | Ambas funciones compiten por crear la columna `Value`, y el orden de llamada importa pero no está documentado. |
| **Impacto**     | Dependiendo del orden en `descargar_metrica()`, el valor puede ser correcto o incorrecto. Si `asegurar_columna_valor()` ya derivó el valor, `convertir_unidades()` lo vuelve a dividir. |
| **Estado**      | ⚠️ PARCIALMENTE MITIGADO — el orden actual parece correcto, pero es frágil |
| **Mitigación**  | Centralizar en `apply_conversion()` de `etl_rules.py` que maneja ambos pasos en una sola función idempotente. |

---

### FALLO 5 — Unidad asignada como `None` en BD

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl_todas_metricas_xm.py:descargar_metrica()` — lógica de asignación de `unidad` ≈ L350 |
| **Síntoma**     | Miles de registros en BD con `unidad = NULL` |
| **Causa raíz**  | La unidad se asigna condicionalmente (`if conversion_type == 'Wh_a_GWh': unit = 'GWh'`) pero las ramas no cubren todos los tipos de conversión. Métricas con `sin_conversion` reciben `None`. |
| **Impacto**     | Dashboards muestran "None" como unidad, servicios no pueden filtrar por unidad, confusión para usuarios |
| **Estado**      | ❌ SIN RESOLVER para muchas métricas |
| **Mitigación**  | Usar `get_expected_unit(metric_id)` de `etl_rules.py` para asignar la unidad SIEMPRE, sin depender del tipo de conversión. |

---

### FALLO 6 — No hay validación antes de insertar en BD

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl_todas_metricas_xm.py:descargar_metrica()` — entre conversión e inserción |
| **Síntoma**     | Datos con valores absurdos, unidades incorrectas o fechas futuras llegan a la BD |
| **Causa raíz**  | No existe un paso de validación entre la conversión de datos y el `INSERT INTO metrics`. Los datos pasan directo: download → convert → insert. |
| **Impacto**     | **CRÍTICO** — una vez insertados, los datos malos contaminan todos los servicios y dashboards. Requiere limpieza manual con DELETE. |
| **Estado**      | ❌ SIN RESOLVER |
| **Mitigación**  | Agregar `validate_metric_df(df, metric_id)` entre la conversión y la inserción. Si hay errores, loggear y NO insertar. Si solo hay warnings, insertar pero loggear. |

---

### FALLO 7 — Servicios de dominio filtran por valores hardcoded

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `infrastructure/external/xm_service.py`, `domain/services/hydrology_service.py`, etc. |
| **Síntoma**     | Servicios filtran por `recurso='_SISTEMA_'` (ya corregido a `'Sistema'`), o asumen unidades específicas |
| **Causa raíz**  | Los servicios asumen que los datos en BD tienen un formato específico sin verificarlo. Cuando el ETL cambia la forma de almacenar (ej: renombrar entidades), los servicios fallan silenciosamente. |
| **Impacto**     | Queries retornan 0 filas, dashboard muestra "Sin datos" |
| **Estado**      | 🔧 RESUELTO PARCIALMENTE en sesiones anteriores (`_SISTEMA_` → `Sistema`) |
| **Mitigación**  | Documentar el contrato de datos en `etl_rules.py` (entidades esperadas). Los servicios deben usar las constantes del módulo de reglas. |

---

### FALLO 8 — `validar_etl.py` usa SQLite (obsoleto)

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `scripts/validar_etl.py` |
| **Síntoma**     | Script de validación no funciona porque busca una BD SQLite que ya no existe |
| **Causa raíz**  | El proyecto migró de SQLite a PostgreSQL pero el script de validación no se actualizó |
| **Impacto**     | No hay validación post-ETL automatizada |
| **Estado**      | ❌ SIN RESOLVER |
| **Mitigación**  | El nuevo `scripts/diagnostico_metricas_etl.py` reemplaza esta funcionalidad con PostgreSQL. |

---

### FALLO 9 — Dashboard muestra datos con unidades mixtas

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | Dash pages (13 secciones) |
| **Síntoma**     | Gráficos suman GWh con m³/s, o muestran "None" como unidad |
| **Causa raíz**  | Cascade desde FALLO 2 y FALLO 5 — datos incorrectos en BD llegan al dashboard |
| **Impacto**     | Valores absurdos en el dashboard visible al público/directivos |
| **Estado**      | ⚠️ MITIGACIÓN INDIRECTA al resolver fallos 2, 5, 6 |
| **Mitigación**  | Resolver causas raíz (fallos 2, 5, 6). El dashboard se auto-corrige cuando los datos subyacentes son correctos. |

---

### FALLO 10 — `validaciones_rangos.py` IDs incorrectos

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | `etl/validaciones_rangos.py` |
| **Síntoma**     | Rangos no se aplican porque los metric IDs no coinciden |
| **Causa raíz**  | `VALID_RANGES` usa IDs como `'GeneReal'` (no existe en XM, debería ser `'Gene'`), `'DemaEner'` (debería ser `'DemaReal'`) |
| **Impacto**     | Validación de rangos no funciona para las métricas más importantes |
| **Estado**      | ❌ SIN RESOLVER (pero `etl_rules.py` tiene los rangos correctos) |
| **Mitigación**  | Deprecated `validaciones_rangos.py`; usar los rangos de `etl_rules.py` que están verificados contra los IDs reales de XM. |

---

### FALLO 11 — Cron no tiene reintentos ni alertas

| Atributo        | Detalle |
|-----------------|---------|
| **Ubicación**   | Crontab: `0 */6 * * *` |
| **Síntoma**     | Si el ETL falla a las 00:00, no se reintenta hasta las 06:00 |
| **Causa raíz**  | No hay mecanismo de retry ni notificación de fallo |
| **Impacto**     | 6 horas sin datos nuevos si falla una ejecución |
| **Estado**      | ⚠️ SIN RESOLVER |
| **Mitigación**  | Agregar validación post-ejecución en cron (`diagnostico_metricas_etl.py --dias 2`). Enviar alerta si el diagnóstico retorna exit code 1. |

---

## 3. Prioridad de Resolución

| Prioridad | Fallo | Impacto | Esfuerzo |
|-----------|-------|---------|----------|
| 🔴 P0    | FALLO 6 — Sin validación pre-insert | Datos corruptos irreversibles | Bajo — agregar 10 líneas |
| 🔴 P0    | FALLO 2 — detectar_conversion() | 170K+ registros con unidad errada | Bajo — reemplazar por lookup |
| 🔴 P0    | FALLO 5 — Unidad = None | Dashboard muestra None | Bajo — usar get_expected_unit() |
| 🟡 P1    | FALLO 3 — Dict key duplicada | Métricas silenciosamente perdidas | Trivial — renombrar clave |
| 🟡 P1    | FALLO 4 — Doble conversión | Valores potencialmente incorrectos | Medio — refactor |
| 🟡 P1    | FALLO 8 — validar_etl.py obsoleto | No hay validación post-ETL | Ya resuelto con nuevo script |
| 🟡 P1    | FALLO 10 — IDs incorrectos en rangos | Rangos no se aplican | Ya resuelto con etl_rules.py |
| 🟢 P2    | FALLO 1 — Fuente caída | 0 registros cargados | Medio — retry + backoff |
| 🟢 P2    | FALLO 7 — Filtros hardcoded | Queries retornan vacío | Ya resuelto parcialmente |
| 🟢 P2    | FALLO 9 — Dashboard unidades mixtas | UX pobre | Se auto-resuelve con P0 |
| 🟢 P2    | FALLO 11 — Cron sin retry | 6h sin datos | Bajo — script wrapper |

---

## 4. Mapa de Archivos Afectados

| Archivo | Fallos que lo afectan | Rol |
|---------|----------------------|-----|
| `etl/etl_todas_metricas_xm.py` | 1, 2, 4, 5, 6 | ETL principal — 80% de los fallos están aquí |
| `etl/config_metricas.py` | 3 | Configuración batch con dict duplicado |
| `etl/validaciones_rangos.py` | 10 | Rangos con IDs incorrectos |
| `scripts/validar_etl.py` | 8 | Validación obsoleta (SQLite) |
| `etl/etl_rules.py` | — | **NUEVO** — solución centralizada para 2, 4, 5, 6, 10 |
| `scripts/diagnostico_metricas_etl.py` | — | **NUEVO** — reemplaza fallo 8 |
| `scripts/diagnostico_conversores_unidades.py` | — | **NUEVO** — detecta fallo 2, 4 |
