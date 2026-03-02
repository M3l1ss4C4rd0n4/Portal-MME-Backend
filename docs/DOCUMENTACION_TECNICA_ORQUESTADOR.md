# 🤖 Documentación Técnica — Orquestador para Chatbot

**Fecha de inspección:** 1 de marzo de 2026  
**Versión del documento:** 2.0 (actualización basada en inspección del código fuente)  
**Estado:** ✅ En producción — API respondiendo correctamente  
**Archivo principal:** `domain/services/orchestrator_service.py` (4.198 líneas)

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura Actual](#2-arquitectura-actual)
3. [Endpoint y Contrato](#3-endpoint-y-contrato)
4. [Mapeo Completo de Intents](#4-mapeo-completo-de-intents)
5. [Handlers — Descripción Detallada](#5-handlers--descripción-detallada)
6. [Servicios Backend Integrados](#6-servicios-backend-integrados)
7. [Política de Confianza de Predicciones](#7-política-de-confianza-de-predicciones)
8. [Schemas Pydantic](#8-schemas-pydantic)
9. [Seguridad y Validación](#9-seguridad-y-validación)
10. [Generación de Informes con IA](#10-generación-de-informes-con-ia)
11. [Detección de Anomalías](#11-detección-de-anomalías)
12. [Despliegue y Operación](#12-despliegue-y-operación)
13. [Monitoreo y Debugging](#13-monitoreo-y-debugging)
14. [Inventario de Métodos](#14-inventario-de-métodos)
15. [Estado Actual — Hallazgos de la Inspección](#15-estado-actual--hallazgos-de-la-inspección)

---

## 1. Resumen Ejecutivo

El **Orquestador para Chatbot** es el endpoint central del Portal Energético MME que sirve como punto único de integración con el chatbot de WhatsApp (desarrollado por Oscar Parra). Recibe intents del chatbot y los distribuye a los servicios backend apropiados del sistema.

### Estado del sistema al 1 de marzo de 2026

| Componente | Estado | Detalle |
|---|---|---|
| API (FastAPI/Gunicorn) | ✅ Operativo | Health check OK: `chatbot-orchestrator` |
| Endpoint POST | ✅ Activo | `/api/v1/chatbot/orchestrator` |
| Health check GET | ✅ Activo | `/api/v1/chatbot/health` |
| Autenticación API Key | ✅ Activa | Header `X-API-Key` obligatorio |
| Rate Limiting | ✅ Activo | 100 req/min por IP (SlowAPI) |
| Servicios backend | ✅ Operativos | Generation, Hydrology, Metrics, Predictions, AI, News |
| Base de datos PostgreSQL | ✅ Operativo | Métricas de XM, predicciones, alertas |
| Servicio IA (Groq/OpenRouter) | ✅ Operativo | Para informes ejecutivos y resúmenes |
| Servicio de noticias | ✅ Configurado | GNews + MediaStack |

### Líneas de código del orquestador

| Archivo | Líneas | Rol |
|---|---|---|
| `domain/services/orchestrator_service.py` | 4.198 | Lógica de orquestación, 14 handlers, helpers |
| `domain/schemas/orchestrator.py` | 496 | Schemas request/response Pydantic |
| `api/v1/routes/chatbot.py` | 386 | Endpoint FastAPI, docs Swagger, rate limiting |
| **Total** | **5.080** | |

---

## 2. Arquitectura Actual

### 2.1 Diagrama de Componentes

```
┌──────────────────────┐
│   Chatbot WhatsApp   │
│   (Oscar Parra)      │
└──────────┬───────────┘
           │ POST /api/v1/chatbot/orchestrator
           │ Header: X-API-Key
           │ Body: {sessionId, intent, parameters}
           ▼
┌──────────────────────────────────────────────────────────┐
│               API Gateway (FastAPI + Gunicorn)           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  SlowAPI Rate Limiter (100/min)                    │  │
│  │  API Key Validation (api/dependencies.py)          │  │
│  │  Request Validation (Pydantic v2)                  │  │
│  └────────────────────────────────────────────────────┘  │
│  Archivo: api/v1/routes/chatbot.py                       │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│          ChatbotOrchestratorService                       │
│          domain/services/orchestrator_service.py          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  _get_intent_handler() → Mapeo de 38 intents       │  │
│  │  orchestrate() → Despacho con timeout 60s           │  │
│  │  _sanitize_numpy_types() → Serialización segura     │  │
│  │  handle_service_error → Decorador de errores        │  │
│  └────────────────────────────────────────────────────┘  │
└──────────┬───────────────────────────────────────────────┘
           │
     ┌─────┴──────┬──────────┬───────────┬──────────┬──────────┐
     ▼            ▼          ▼           ▼          ▼          ▼
┌──────────┐┌─────────┐┌──────────┐┌─────────┐┌────────┐┌────────┐
│Generation││Hydrology││ Metrics  ││Predict- ││AgentIA ││ News   │
│ Service  ││ Service ││ Service  ││ ions    ││(Groq/  ││Service │
│ (446 ln) ││(348 ln) ││(200 ln)  ││Service  ││OpenR.) ││(506 ln)│
└────┬─────┘└────┬────┘└────┬─────┘└────┬────┘└────┬───┘└────┬───┘
     │           │          │           │          │         │
     ▼           ▼          ▼           ▼          ▼         ▼
┌──────────────────────────────────────────────────────────────────┐
│  PostgreSQL (metrics, predictions, alertas_historial)            │
│  APIs externas: XM/SIMEM, Groq, OpenRouter, GNews, MediaStack   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Servicios Auxiliares (dentro del orquestador)

| Servicio | Líneas | Función |
|---|---|---|
| `IntelligentAnalysisService` | 832 | Detección avanzada de anomalías |
| `ExecutiveReportService` | 1.474 | Generación de informes PDF/HTML |
| `confianza_politica` | 123 | Política de confianza de predicciones |

### 2.3 Estructura de Archivos Actual

```
server/
├── api/
│   ├── dependencies.py                    # API Key validation, DI
│   ├── main.py                            # FastAPI app, mounts /v1
│   └── v1/
│       ├── __init__.py                    # Registra router chatbot en /chatbot
│       ├── routes/
│       │   ├── chatbot.py                 # POST /orchestrator, GET /health
│       │   └── whatsapp_alerts.py         # POST /send-alert
│       └── schemas/
│           └── orchestrator.py            # Schemas Pydantic (duplicado)
│
├── domain/
│   ├── schemas/
│   │   └── orchestrator.py                # Schemas canónicos (496 ln)
│   └── services/
│       ├── orchestrator_service.py        # Orquestador central (4.198 ln)
│       ├── generation_service.py          # Generación eléctrica
│       ├── hydrology_service.py           # Embalses e hidrología
│       ├── metrics_service.py             # Métricas XM genéricas
│       ├── predictions_service.py         # Predicciones ML (32 ln, básico)
│       ├── intelligent_analysis_service.py # Análisis de anomalías
│       ├── executive_report_service.py    # Informes ejecutivos
│       ├── ai_service.py                  # AgentIA (Groq/OpenRouter)
│       ├── news_service.py               # Noticias del sector
│       └── confianza_politica.py          # Política de confianza
│
├── infrastructure/
│   └── database/
│       ├── manager.py                     # db_manager (conexión PostgreSQL)
│       └── repositories/
│           ├── metrics_repository.py
│           └── predictions_repository.py
│
├── core/
│   └── config.py                          # Settings (API_KEY, API_KEY_ENABLED)
│
└── tasks/
    └── anomaly_tasks.py                   # Tareas Celery que llaman al orquestador
```

---

## 3. Endpoint y Contrato

### 3.1 Endpoint Principal

| Método | URL | Auth |
|---|---|---|
| `POST` | `/api/v1/chatbot/orchestrator` | `X-API-Key` (header) |
| `GET` | `/api/v1/chatbot/health` | Ninguna |

### 3.2 Request (OrchestratorRequest)

```json
{
  "sessionId": "string (1-100 chars, sin <>&\"'\\/ ni null bytes)",
  "intent": "string (1-100 chars, alphanumeric + guiones)",
  "parameters": { }
}
```

**Validaciones Pydantic:**
- `sessionId`: No vacío, sin caracteres peligrosos (`< > & " ' \ / \x00`), se aplica `strip()`
- `intent`: Solo alfanuméricos + `_` + `-`, normalizado a lowercase
- `parameters`: Dict libre, validación según el intent

### 3.3 Response (OrchestratorResponse)

```json
{
  "status": "SUCCESS | PARTIAL_SUCCESS | ERROR",
  "message": "string",
  "data": { },
  "errors": [
    {
      "code": "string",
      "message": "string",
      "field": "string | null"
    }
  ],
  "timestamp": "ISO 8601 UTC",
  "sessionId": "echo del request",
  "intent": "echo del intent procesado"
}
```

### 3.4 Timeouts

| Nivel | Valor | Nota |
|---|---|---|
| Por servicio individual | 10 s | `SERVICE_TIMEOUT = 10` |
| Total de la request | 60 s | `TOTAL_TIMEOUT = 60` (ampliado de 30 a 60 para IA) |
| Llamada a IA (informe) | 60 s | Timeout específico para `_generar_informe_con_ia` |
| Llamada a IA (noticias) | 15 s | Timeout para resumen de noticias |
| Llamada a IA (pregunta libre) | 20 s | Timeout para análisis IA de pregunta |

### 3.5 Códigos de Error

| Código | Cuándo |
|---|---|
| `UNKNOWN_INTENT` | Intent no encontrado en el mapa |
| `VALIDATION_ERROR` | Falla de validación Pydantic |
| `SERVICE_ERROR` | Excepción en servicio backend |
| `TIMEOUT` | Timeout de servicio individual |
| `TOTAL_TIMEOUT` | Timeout global de la request |
| `NO_DATA` | Sin datos para el periodo/fecha |
| `PARTIAL_DATA` | Datos incompletos (un indicador de 3) |
| `INTERNAL_ERROR` | Error no manejado |
| `INVALID_DATE` | Fecha personalizada inválida |
| `INVALID_DATE_FORMAT` | Formato de fecha no reconocido |
| `SERVICE_UNAVAILABLE` | Servicio no inicializado |
| `MISSING_QUESTION` | Intent `pregunta_libre` sin parámetro `pregunta` |
| `PREDICTION_UNAVAILABLE` | Predicción no disponible para un indicador |
| `NEWS_UNAVAILABLE` | Servicio de noticias no configurado |
| `NEWS_TIMEOUT` | Timeout consultando noticias |
| `NEWS_ERROR` | Error en servicio de noticias |
| `ANALYSIS_ERROR` | Error en detección de anomalías |
| `REPORT_ERROR` | Error generando informe ejecutivo |
| `QUERY_ERROR` | Error en pregunta libre |
| `NOT_IMPLEMENTED` | Funcionalidad no implementada |

---

## 4. Mapeo Completo de Intents

El método `_get_intent_handler()` define **38 intents** organizados en 5 grupos:

### 4.1 Menú Principal (4 opciones del Viceministro)

| Intent(s) | Handler | Descripción |
|---|---|---|
| `estado_actual`, `como_esta_sistema`, `status_sistema` | `_handle_estado_actual` | 3 fichas KPI: Generación, Precio, Embalses |
| `predicciones_sector`, `predicciones_indicadores` | `_handle_predicciones_sector` | Predicciones con horizonte configurable |
| `anomalias_sector`, `anomalias_detectadas`, `problemas_sistema`, `detectar_anomalias`, `alertas` | `_handle_anomalias_detectadas` | Anomalías real vs hist/pred |
| `mas_informacion` | `_handle_menu` | Muestra sub-menú |

### 4.2 Sub-opciones de "Más Información"

| Intent(s) | Handler | Descripción |
|---|---|---|
| `informe_ejecutivo`, `generar_informe`, `informe_completo`, `reporte_ejecutivo` | `_handle_informe_ejecutivo` | Informe IA de 5 secciones |
| `noticias_sector`, `noticias`, `news` | `_handle_noticias_sector` | Noticias del sector (GNews/MediaStack) |
| `pregunta_libre`, `pregunta`, `consulta_libre` | `_handle_pregunta_libre` | Pregunta en lenguaje natural |

### 4.3 Intents Específicos por Sector

| Intent(s) | Handler | Descripción |
|---|---|---|
| `generacion_electrica`, `consultar_generacion`, `generacion` | `_handle_generacion_electrica` | Generación por fecha/rango/recurso |
| `hidrologia`, `consultar_embalses`, `embalses`, `nivel_embalses` | `_handle_hidrologia` | Nivel de embalses y energía |
| `demanda_sistema`, `consultar_demanda`, `demanda` | `_handle_demanda_sistema` | Demanda eléctrica (DemaCome) |
| `precio_bolsa`, `precios_bolsa`, `consultar_precios` | `_handle_precio_bolsa` | Precio de bolsa nacional |
| `predicciones`, `pronostico`, `forecast` | `_handle_predicciones` | Predicciones por fuente detallada |
| `metricas_generales`, `resumen_sistema`, `estado_sistema`, `resumen_completo` | `_handle_metricas_generales` | Resumen de métricas del sistema |

### 4.4 Menú / Ayuda

| Intent(s) | Handler | Descripción |
|---|---|---|
| `menu`, `ayuda`, `help`, `opciones`, `inicio`, `start` | `_handle_menu` | Menú con 5 opciones y sub-menús |

---

## 5. Handlers — Descripción Detallada

### 5.1 `_handle_estado_actual` (Handler principal 1️⃣)

**Líneas:** 343–678  
**Función:** Retorna 3 fichas KPI con datos actuales.

**Lógica por ficha:**

1. **⚡ Generación Total del Sistema (GWh)**
   - Consulta `generation_service.get_daily_generation_system()` últimos 7 días
   - Extrae último día disponible + promedio semanal
   - Calcula variación porcentual y tendencia (↗️/↘️/➡️)

2. **💰 Precio de Bolsa Nacional (COP/kWh)**
   - Consulta `metrics_service.get_metric_series('PrecBolsNaci')` últimos 7 días
   - Incluye promedio, máximo, mínimo de la semana
   - Umbral de tendencia: ±5%

3. **💧 Porcentaje de Embalses (%)**
   - Recorre ventana de 7 días buscando dato más reciente con completitud ≥80%
   - Calcula `VoluUtilDiarEner / CapaUtilDiarEner × 100`
   - Evalúa con percentiles históricos del mismo mes (2020–presente)
   - Incluye promedio 30d, media histórica 2020-2025, desviación
   - Semáforo: 🟢 Nivel alto (>P75), 🟡 Medio (P25–P75), 🟠 Bajo (<P25), 🔴 Crítico (<30% fijo)

**Campos adicionales:** `opcion_regresar`, `fecha_consulta`

### 5.2 `_handle_anomalias_detectadas` (Handler 2️⃣: ¿Qué problemas hay?)

**Líneas:** 680–1015  
**Función:** Detecta anomalías comparando valor real vs histórico 30d vs predicción.

**Algoritmo:**
1. Para cada indicador (Generación, Precio, Embalses):
   - Obtiene `valor_actual` (último dato real en BD)
   - Obtiene `avg_hist_30d` (promedio 30 días reales)
   - Busca `valor_predicho` para la fecha del dato real (±2 días)
2. Calcula `delta_hist_pct = |actual - avg_hist| / avg_hist × 100`
3. Si la predicción es CONFIABLE o MUY_CONFIABLE (según política):
   - Calcula `delta_pred_pct = |actual - predicho| / predicho × 100`
   - Si no (ACEPTABLE/EXPERIMENTAL): predicción solo como contexto
4. `desviacion_pct = max(delta_hist, delta_pred)` 

**Umbrales de severidad (calibrados empíricamente):**

| Indicador | Alerta | Crítico | Razón |
|---|---|---|---|
| Generación Total | >10% | >25% | Estable históricamente |
| Embalses | >10% | >25% | Estable históricamente |
| Precio de Bolsa | >20% | >40% | Volátil por naturaleza |

**Salida:** Lista de anomalías con `indicador`, `severidad`, `valor_actual`, `promedio_hist_30d`, `delta_hist_pct`, `comentario`, `disclaimer_confianza`.

### 5.3 `_handle_predicciones_sector` (Handler 3️⃣)

**Líneas:** 1746–1998  
**Función:** Predicciones de los 3 indicadores con horizonte configurable.

**Horizontes soportados:**

| Horizonte | Días | Título |
|---|---|---|
| `1_semana` | 7 | Próxima semana |
| `1_mes` | 30 | Próximo mes |
| `6_meses` | 180 | Próximos 6 meses |
| `1_ano` | 365 | Próximo año |
| `personalizado` | Variable | Fecha DD-MM-AAAA o YYYY-MM-DD |

**Por cada indicador:**
- Consulta `predictions_service.get_predictions(metric_id, start, end)`
- Fallbacks: `GENE_TOTAL` → suma de 5 fuentes; `EMBALSES_PCT` → `EMBALSES` (GWh)
- Construye ficha con `_build_prediction_ficha()`:
  - promedio/min/max del periodo
  - comparación vs histórico real 30d
  - cambio_pct y tendencia derivada (>5% Creciente, <-5% Decreciente, else Estable)
  - verificación de confianza mínima (60%)
- Enriquece con política de confianza (`enriquecer_ficha_con_confianza`)

### 5.4 `_handle_pregunta_libre`

**Líneas:** 1999–2242  
**Función:** Respuesta a preguntas en lenguaje natural.

**Algoritmo:**
1. Analiza keywords en la pregunta para detectar temas:
   - Generación (energía, solar, hídrica...)
   - Precios (precio, bolsa, COP...)
   - Embalses (agua, nivel, reserva...)
   - Demanda (consumo, carga...)
   - Predicciones (pronóstico, futuro...)
2. Consulta servicios relevantes y compone `datos_consultados`
3. Si no detecta tema: retorna los 3 KPIs generales
4. **Opcional**: si `con_analisis_ia=true` en parameters:
   - Llama a AgentIA con contexto para generar respuesta en lenguaje natural
   - System prompt: asesor energético, máximo 200 palabras, solo datos reales

### 5.5 `_handle_informe_ejecutivo`

**Líneas:** 2827–3847  
**Función:** Informe ejecutivo completo con IA de 5 secciones.

**Pipeline detallado:**
1. **Recopilación en paralelo** (`asyncio.gather`):
   - Estado actual (3 fichas)
   - Predicciones: 1 semana, 1 mes, 6 meses, 1 año
   - Anomalías detectadas
2. **Noticias** (best-effort, timeout 15s):
   - `NewsService.get_enriched_news()`: top 3 + extras
   - Resumen IA de titulares
3. **Construcción de contexto** enriquecido:
   - Fichas KPI + generación por fuente (`_build_generacion_por_fuente`)
   - Embalses detalle (`_build_embalses_detalle`)
   - Predicciones mes resumen (`_build_predicciones_mes_resumen`)
   - Tabla indicadores clave con semáforo (`_build_tabla_indicadores_clave`)
   - Anomalías de BD (`alertas_historial`) fusionadas y deduplicadas
   - Notas de negocio (umbrales, suposiciones)
   - Confianza de modelos (`POLITICA_CONFIANZA`)
4. **Cache diario**: Si ya se generó informe hoy, usa cache
5. **Llamada a IA** (`_generar_informe_con_ia`):
   - Provider: Groq o OpenRouter (configurable vía AgentIA)
   - System prompt estructurado con 6 reglas obligatorias (R1-R6)
   - Temperatura: 0.3, max_tokens: 4000
   - Inyección explícita de anomalías en user prompt
6. **Post-procesamiento** (`_postprocess_informe_ia`):
   - Elimina nombres de campos JSON
   - Limpia backticks y espacios
   - Valida: mínimo 3 secciones `##`, mínimo 400 chars
   - Trunca a 3.200 chars (1 página PDF), preservando sección 5
7. **Fallback sin IA** (`_generar_informe_fallback`):
   - Genera informe markdown con tablas de datos numéricos
   - 5 secciones: Contexto, Señales, Riesgos, Recomendaciones, Cierre

**Estructura del informe IA (5 secciones obligatorias):**

```
## 1. Contexto general del sistema
## 2. Señales clave y evolución
  ### 2.1 Proyecciones del próximo mes
  ### 2.2 Análisis cualitativo
## 3. Riesgos y oportunidades
  ### 3.1 Riesgos operativos (corto plazo)
  ### 3.2 Riesgos estructurales (mediano plazo)
  ### 3.3 Oportunidades
## 4. Recomendaciones para el Viceministro
  ### 4.1 Corto plazo
  ### 4.2 Mediano plazo
## 5. Calificación del sistema (ESTABLE / EN VIGILANCIA / PREOCUPANTE)
```

### 5.6 `_handle_noticias_sector`

**Líneas:** 3848–4029  
**Función:** Top 3 noticias + lista extendida + resumen IA.

- Usa `NewsService.get_enriched_news(max_top=3, max_extra=7)`
- Resumen IA vía modelo ligero `llama-3.1-8b-instant` (máx 120 palabras)
- Campos: `noticias[]`, `otras_noticias[]`, `resumen_general`

### 5.7 `_handle_menu`

**Líneas:** 4030–4136  
**Función:** Retorna menú estructurado del chatbot WhatsApp.

**Menú principal (5 opciones):**
1. 📊 Estado actual del sector → `estado_actual`
2. 🔮 Predicciones del sector → `predicciones_sector` (con sub-menú de horizonte)
3. 🚨 Anomalías detectadas → `anomalias_sector`
4. 📰 Noticias del sector → `noticias_sector`
5. 📋 Más información → sub-menú:
   - Informe ejecutivo completo → `informe_ejecutivo`
   - Pregunta libre → `pregunta_libre`

### 5.8 Handlers específicos por sector

| Handler | Líneas | Métricas consultadas | Defaults |
|---|---|---|---|
| `_handle_generacion_electrica` | 2243–2341 | `get_daily_generation_system`, `get_generation_by_source` | Últimos 7 días |
| `_handle_hidrologia` | 2342–2401 | `get_reservas_hidricas` | Hoy |
| `_handle_demanda_sistema` | 2402–2472 | `get_metric_series('DemaCome')` | Últimos 7 días |
| `_handle_precio_bolsa` | 2473–2543 | `get_metric_series('PrecBolsNaci')` | Últimos 7 días |
| `_handle_predicciones` | 2544–2744 | `get_predictions(metric_id)` | Hidráulica, 7 días |
| `_handle_metricas_generales` | 2745–2826 | Combinación de los anteriores | Últimos 7 días |

---

## 6. Servicios Backend Integrados

### 6.1 Servicios instanciados en `__init__`

```python
class ChatbotOrchestratorService:
    def __init__(self):
        self.generation_service = GenerationService()       # Siempre
        self.hydrology_service = HydrologyService()         # Siempre
        self.metrics_service = MetricsService()             # Siempre
        self.intelligent_analysis = IntelligentAnalysisService()  # Siempre
        self.executive_report_service = ExecutiveReportService()  # Siempre
        self.predictions_service = PredictionsService()     # try/except
        self.news_service = NewsService()                   # try/except
        self._informe_ia_cache = {}                         # Cache diario
```

### 6.2 Tabla de Servicios

| Servicio | Archivo | Líneas | Función | Degradación si falla |
|---|---|---|---|---|
| `GenerationService` | `generation_service.py` | 446 | Generación eléctrica por sistema/fuente/mix | Error parcial |
| `HydrologyService` | `hydrology_service.py` | 348 | Embalses, reservas hídricas | Error parcial |
| `MetricsService` | `metrics_service.py` | 200 | Métricas genéricas XM (PrecBolsNaci, DemaCome) | Error parcial |
| `PredictionsService` | `predictions_service.py` | 32 | Predicciones ML de BD | Handler retorna UNAVAILABLE |
| `IntelligentAnalysisService` | `intelligent_analysis_service.py` | 832 | Anomalías, severidad | No usado directamente ahora |
| `ExecutiveReportService` | `executive_report_service.py` | 1.474 | Informes PDF/HTML | No usado directamente por orquestador |
| `AgentIA` | `ai_service.py` | 420 | Groq/OpenRouter (LLM) | Fallback a informe sin IA |
| `NewsService` | `news_service.py` | 506 | GNews + MediaStack | Handler retorna UNAVAILABLE |
| `confianza_politica` | `confianza_politica.py` | 123 | Política de confianza | Se usa default DESCONOCIDO |

### 6.3 Acceso a Base de Datos

El orquestador accede directamente a PostgreSQL vía `db_manager.query_df()` para:
- **Embalses** (cálculo `VoluUtilDiarEner / CapaUtilDiarEner`): queries SQL directas con filtrado de completitud (≥80%)
- **Predicciones** (lookup ±2 días): tabla `predictions`
- **Alertas historial**: tabla `alertas_historial` (anomalías recientes de BD)
- **Percentiles históricos**: cálculo de P25/P75 del mismo mes del año (2020-presente)

---

## 7. Política de Confianza de Predicciones

Archivo: `domain/services/confianza_politica.py`

| Fuente | Nivel | MAPE máx | Usar intervalos | Disclaimer |
|---|---|---|---|---|
| `GENE_TOTAL` | MUY_CONFIABLE | 5% | Sí | No |
| `DEMANDA` | MUY_CONFIABLE | 5% | Sí | No |
| `EMBALSES` | MUY_CONFIABLE | 1% | Sí | No |
| `EMBALSES_PCT` | MUY_CONFIABLE | 5% | Sí | No |
| `PERDIDAS` | MUY_CONFIABLE | 15% | Sí | No |
| `Hidráulica` | MUY_CONFIABLE | 5% | Sí | No |
| `Biomasa` | MUY_CONFIABLE | 10% | Sí | No |
| `PRECIO_ESCASEZ` | MUY_CONFIABLE | 2% | Sí | No |
| `APORTES_HIDRICOS` | CONFIABLE | 25% | Sí | Sí |
| `Térmica` | CONFIABLE | 20% | Sí | Sí |
| `Solar` | CONFIABLE | 25% | Sí | Sí |
| `Eólica` | ACEPTABLE | 30% | Sí | Sí |
| `PRECIO_BOLSA` | EXPERIMENTAL | N/A | No | Sí |

**Integración con anomalías (FASE 7):**
- `MUY_CONFIABLE` / `CONFIABLE` → predicción influye en severidad
- `ACEPTABLE` / `EXPERIMENTAL` / `DESCONOCIDO` → predicción solo como contexto, severidad basada exclusivamente en histórico 30d

---

## 8. Schemas Pydantic

Archivo: `domain/schemas/orchestrator.py` (496 líneas)

### Schemas principales

| Schema | Tipo | Uso |
|---|---|---|
| `OrchestratorRequest` | Request | sessionId, intent, parameters |
| `OrchestratorResponse` | Response | status, message, data, errors, timestamp |
| `ErrorDetail` | Nested | code, message, field |

### Schemas de parámetros por intent

| Schema | Intent(s) |
|---|---|
| `GeneracionElectricaParams` | generacion_electrica |
| `HidrologiaParams` | hidrologia, consultar_embalses |
| `DemandaSistemaParams` | demanda_sistema |
| `PreciosBolsaParams` | precio_bolsa |
| `PrediccionesParams` | predicciones |
| `EstadoActualParams` | estado_actual |
| `AnomaliasParams` | anomalias_detectadas |

### Schemas de respuesta compleja

| Schema | Contenido |
|---|---|
| `AnomaliaSchema` | Anomalía individual con sector, severidad, valores, umbrales |
| `SectorStatusSchema` | Estado de sector: KPIs, tendencias, anomalías |
| `EstadoActualResponse` | Estado general + sectores + resumen anomalías |
| `AnomaliasResponse` | Lista agrupada por sector y severidad |

---

## 9. Seguridad y Validación

### 9.1 Autenticación

| Aspecto | Valor |
|---|---|
| Método | API Key en header `X-API-Key` |
| Validación | `api/dependencies.py` → `get_api_key()` |
| Config | `core/config.py` → `settings.API_KEY` |
| Toggle | `API_KEY_ENABLED` en `.env` (puede desactivarse en dev) |

### 9.2 Rate Limiting

| Aspecto | Valor |
|---|---|
| Framework | SlowAPI |
| Límite | 100 requests/minuto por IP |
| Response al exceder | HTTP 429 |

### 9.3 Sanitización de Entrada

- **sessionId**: Eliminación de `< > & " ' \ / \x00`, strip de espacios
- **intent**: Solo alfanuméricos + `_` + `-`, normalizado a lowercase
- **parameters**: Validación de tipos según intent, timeout por servicio

### 9.4 Sanitización de Salida

- `_sanitize_numpy_types()`: Convierte recursivamente `np.int64`, `np.float64`, `pd.Timestamp`, `np.ndarray` → tipos nativos Python
- Errores genéricos al usuario sin exposición de stack traces
- Logging detallado interno para debugging

---

## 10. Generación de Informes con IA

### 10.1 Proveedores de IA

| Provider | Uso | Modelo |
|---|---|---|
| Groq | Informes ejecutivos | Configurable vía `AgentIA` |
| OpenRouter | Fallback | Configurable vía `AgentIA` |
| Groq (ligero) | Resumen de noticias | `llama-3.1-8b-instant` |

### 10.2 Cache de Informes

```python
self._informe_ia_cache = {
    "2026-03-01": {
        "texto": "## 1. Contexto general...",
        "hora": "14:30"
    }
}
```

- Cache por fecha (string YYYY-MM-DD)
- Se regenera si la fecha cambia
- Invalidación manual: reiniciar la API

### 10.3 Post-procesamiento del Informe

1. Eliminación de nombres de campos JSON (`desviacion_pct_media_historica`, etc.)
2. Eliminación de backticks residuales
3. Limpieza de espacios múltiples
4. Eliminación de frases vacías/genéricas
5. Validación: mínimo 3 secciones `##`, mínimo 400 chars
6. Truncamiento a 3.200 chars preservando sección 5 (Calificación)

### 10.4 Reglas del System Prompt (R1-R6)

- **R1**: NO repetir números (tabla semáforo ya los muestra); usar lenguaje cualitativo
- **R2**: Máximo 600 palabras / ≤3.000 chars
- **R3**: Exactamente 5 secciones numeradas
- **R4**: NUNCA usar nombres de campos JSON ni backticks
- **R5**: NUNCA inventar datos; siempre integrar noticias y anomalías
- **R6**: PRECIO_BOLSA es experimental (solo referencia direccional)

---

## 11. Detección de Anomalías

### 11.1 Flujo de Detección

```
_handle_anomalias_detectadas()
  └─ _detect_anomalias_clave()
       └─ _evaluar_indicador_anomalia()  × 3 indicadores
            ├─ _get_real_e_historico()           # Generación, Precio
            ├─ _get_embalses_real_e_historico()   # Embalses (fórmula especial)
            ├─ predictions.query (±2 días)        # Predicción si existe
            └─ get_confianza_politica()           # FASE 7: decidir si usar pred
```

### 11.2 Helpers para Datos Históricos

| Método | Función | Línea |
|---|---|---|
| `_get_real_e_historico` | Valor actual + avg 30d para métrica genérica | 1017 |
| `_get_embalses_real_e_historico` | % embalses actual + avg 30d (fórmula Vol/Cap) | 1059 |
| `_get_historical_avg_30d` | Promedio 30d para una métrica/entidad | 1246 |
| `_get_embalses_avg_30d` | Promedio 30d de embalses en % | 1276 |
| `_get_media_historica_embalses_2020_2025` | Media 2020–2025 para referencia largo plazo | 1312 |
| `_evaluar_nivel_embalses_historico` | Percentiles P25/P75 del mismo mes | 586 |

### 11.3 Filtrado de Completitud en Embalses

Todas las queries de embalses aplican:
```sql
WHERE n_cap > 0 AND n_vol::float / n_cap >= 0.80
```
Razón: XM publica parcialmente; si un día tiene <80% de los embalses con VoluUtil vs CapaUtil, el dato se descarta como incompleto.

---

## 12. Despliegue y Operación

### 12.1 Stack de Producción

| Componente | Tecnología |
|---|---|
| HTTP Server | Gunicorn + Uvicorn workers |
| Framework | FastAPI |
| Proxy reverso | Nginx (`nginx-api-config.conf`) |
| Systemd | `api-mme.service` |
| BD | PostgreSQL (local, puerto 5432) |
| ML Tracking | MLflow (puerto 5000) |
| Tareas async | Celery |

### 12.2 Archivos de Configuración

| Archivo | Función |
|---|---|
| `api-mme.service` | Servicio systemd del API |
| `gunicorn_config.py` | Workers, bind, timeout |
| `nginx-api-config.conf` | Proxy Nginx para API |
| `.env` | Variables: GROQ_API_KEY, OPENROUTER_API_KEY, etc. |
| `core/config.py` | Settings Pydantic (API_KEY, API_KEY_ENABLED) |

### 12.3 Verificación

```bash
# Health check
curl http://localhost:8000/api/v1/chatbot/health

# Respuesta esperada:
# {"status":"healthy","service":"chatbot-orchestrator","timestamp":"..."}

# Documentación Swagger
# http://[dominio]/api/docs → Sección "🤖 Chatbot"
```

### 12.4 Reinicio

```bash
sudo systemctl restart api-mme.service
# O directamente:
cd /home/admonctrlxm/server && ./api/run_prod.sh
```

---

## 13. Monitoreo y Debugging

### 13.1 Prefijos de Log

| Prefijo | Handler/Módulo |
|---|---|
| `[CHATBOT_ENDPOINT]` | Recepción y respuesta en route |
| `[ORCHESTRATOR]` | Método `orchestrate()` principal |
| `[ESTADO_ACTUAL]` | Handler estado_actual |
| `[EMBALSES]` | Consultas de embalses, percentiles |
| `[ANOMALIAS]` | Detección de anomalías |
| `[PREDICCIONES_SECTOR]` | Predicciones con horizonte |
| `[PREGUNTA_LIBRE]` | Pregunta en lenguaje natural |
| `[INFORME_EJECUTIVO_IA]` | Recopilación de contexto para informe |
| `[INFORME_IA]` | Llamada a IA y generación |
| `[INFORME_IA_POST]` | Post-procesamiento del texto IA |
| `[INFORME]` | Helpers de enriquecimiento (Building blocks) |
| `[NOTICIAS]` | Handler de noticias |
| `[NOTICIAS_RESUMEN]` | Resumen IA de titulares |

### 13.2 Búsqueda por sessionId

```bash
grep "sessionId: chat_123456789" /home/admonctrlxm/server/logs/api.log
```

### 13.3 Métricas Operativas

- Requests por minuto por intent
- Tasa de éxito: SUCCESS vs PARTIAL_SUCCESS vs ERROR
- Tiempos de respuesta (logged en `[ORCHESTRATOR] Elapsed:`)
- Tasa de cache hit en informes IA
- Disponibilidad de servicios (PredictionsService, NewsService)
- Ratio de anomalías detectadas vs evaluadas

---

## 14. Inventario de Métodos

### 14.1 Clase `ChatbotOrchestratorService`

| Método | Línea | Tipo | Función |
|---|---|---|---|
| `__init__` | 93 | Init | Instancia servicios, cache |
| `orchestrate` | 126 | async | Despacho principal |
| `_get_intent_handler` | 231 | Sync | Mapea intent → handler (38 intents) |
| **Handlers principales** | | | |
| `_handle_estado_actual` | 343 | async | 3 fichas KPI |
| `_handle_anomalias_detectadas` | 680 | async | Anomalías real vs hist/pred |
| `_handle_predicciones_sector` | 1746 | async | Predicciones con horizonte |
| `_handle_pregunta_libre` | 1999 | async | Respuesta a pregunta libre |
| `_handle_informe_ejecutivo` | 2827 | async | Informe IA de 5 secciones |
| `_handle_noticias_sector` | 3848 | async | Noticias del sector |
| `_handle_menu` | 4030 | async | Menú de 5 opciones |
| **Handlers específicos** | | | |
| `_handle_generacion_electrica` | 2243 | async | Generación por fecha/fuente |
| `_handle_hidrologia` | 2342 | async | Embalses |
| `_handle_demanda_sistema` | 2402 | async | Demanda (DemaCome) |
| `_handle_precio_bolsa` | 2473 | async | Precio de bolsa |
| `_handle_predicciones` | 2544 | async | Predicciones por fuente |
| `_handle_metricas_generales` | 2745 | async | Resumen general |
| **Helpers de datos** | | | |
| `_evaluar_nivel_embalses_historico` | 586 | Sync | Percentiles P25/P75 embalses |
| `_detect_anomalias_clave` | 762 | async | Evalúa 3 indicadores |
| `_evaluar_indicador_anomalia` | 826 | async | Evalúa 1 indicador completo |
| `_get_real_e_historico` | 1017 | Sync | Valor actual + avg 30d |
| `_get_embalses_real_e_historico` | 1059 | Sync | Embalses actual + avg 30d |
| `_get_historical_avg_30d` | 1246 | Sync | Promedio 30d por métrica |
| `_get_embalses_avg_30d` | 1276 | Sync | Promedio 30d embalses % |
| `_get_media_historica_embalses_2020_2025` | 1312 | Sync | Media largo plazo |
| **Helpers de informe** | | | |
| `_build_generacion_por_fuente` | 1367 | async | Mix energético |
| `_build_embalses_detalle` | 1436 | Sync | Consolidación embalses |
| `_build_predicciones_mes_resumen` | 1486 | Sync | Bloque compacto 3 métricas |
| `_build_prediction_ficha` | 1116 | Sync | Ficha de predicción enriquecida |
| `_build_tabla_indicadores_clave` | 1581 | Sync | KPIs con semáforo |
| `_deduplicar_anomalias` | 1710 | Static | Elimina anomalías duplicadas |
| `_generar_informe_con_ia` | 3356 | async | Llamada a LLM |
| `_postprocess_informe_ia` | 3218 | Sync | Limpieza de texto IA |
| `_generar_informe_fallback` | 3645 | Sync | Informe sin IA |
| `_generar_resumen_noticias` | 3952 | async | Resumen IA de titulares |
| **Utilidades** | | | |
| `_sanitize_numpy_types` | 4137 | Static | Conversión tipos numpy |
| `_serialize_anomalia` | 4157 | Sync | Anomalia → dict |
| `_create_error_response` | 4182 | Sync | Response de error estándar |

### 14.2 Decorador `handle_service_error`

**Línea:** 59  
Captura `TimeoutError` → código `TIMEOUT`; cualquier otra excepción → código `SERVICE_ERROR`. Se aplica a todos los handlers con `@handle_service_error`.

---

## 15. Estado Actual — Hallazgos de la Inspección

### 15.1 Lo que funciona correctamente

| Aspecto | Estado | Evidencia |
|---|---|---|
| API respondiendo | ✅ | Health check OK |
| Autenticación activa | ✅ | `API Key inválida` al enviar key incorrecta |
| 38 intents mapeados | ✅ | Cobertura completa del menú y sub-menús |
| 3 indicadores clave | ✅ | Generación, Precio, Embalses con contexto histórico |
| Detección de anomalías | ✅ | Con umbrales calibrados por indicador |
| Predicciones multi-horizonte | ✅ | 1 semana, 1 mes, 6 meses, 1 año, personalizado |
| Informe ejecutivo con IA | ✅ | 5 secciones, cache diario, post-procesamiento |
| Fallback sin IA | ✅ | Informe degradado con datos numéricos |
| Noticias multi-fuente | ✅ | GNews + MediaStack + resumen IA |
| Pregunta libre | ✅ | NLP básico con keyword matching + IA opcional |
| Política de confianza | ✅ | FASE 6/7 integrada, 13 fuentes clasificadas |
| Serialización segura | ✅ | Sanitización de tipos numpy/pandas |

### 15.2 Observaciones técnicas

1. **Tamaño del archivo**: `orchestrator_service.py` tiene 4.198 líneas — es el archivo más grande del proyecto (~195 KB). Considerar refactorizar separando handlers en módulos.

2. **Instanciación por request**: El `ChatbotOrchestratorService()` se instancia cada vez que llega un request (`chatbot.py` línea 322). Esto crea nuevas instancias de todos los servicios por request, incluyendo el cache de informe IA que vive en la instancia (se pierde entre requests). Se recomienda usar singleton o `Depends()` de FastAPI.

3. **Cache de informe IA**: El cache `_informe_ia_cache` está en la instancia, no compartido entre requests. En producción con Gunicorn workers, cada worker tiene su propia instancia y no comparten cache.

4. **Timeout total ampliado**: Se cambió de 30s a 60s para acomodar IA con más tokens. Documentación original decía 30s.

5. **Queries SQL directas**: El orquestador ejecuta queries SQL directamente con `db_manager.query_df()` en varios helpers (embalses, predicciones, alertas). Esto mezcla capas de dominio e infraestructura.

6. **PredictionsService básico**: Solo 32 líneas — es un wrapper muy básico. El service extendido (`predictions_service_extended.py`) se usa en el DI de FastAPI pero no en el orquestador.

7. **Schemas duplicados**: Existen schemas en `domain/schemas/orchestrator.py` Y en `api/v1/schemas/orchestrator.py`. Los del dominio son los canónicos (el route importa de `domain`).

8. **Pruebas**: No se encontró `tests/test_orchestrator.py` (referenciado en doc v1.0). La suite de pruebas puede haberse movido o no estar implementada.

### 15.3 Última modificación de archivos clave

| Archivo | Última modificación |
|---|---|
| `orchestrator_service.py` | 1 mar 2026, 11:47 |
| `notification_service.py` | 1 mar 2026, 11:47 |
| `report_service.py` | 28 feb 2026, 02:54 |
| `news_service.py` | 17 feb 2026, 12:32 |
| `hydrology_service.py` | 17 feb 2026, 11:31 |
| `confianza_politica.py` | 16 feb 2026, 11:43 |
| `executive_report_service.py` | 16 feb 2026, 07:14 |

### 15.4 Integración con otros componentes

| Componente | Integración | Archivo |
|---|---|---|
| Tareas Celery (anomalías) | Llama al orquestador vía HTTP | `tasks/anomaly_tasks.py` |
| WhatsApp bot | Consume endpoint orquestador | `whatsapp_bot/` |
| Scripts de test | Llama al orquestador | `scripts/test_informe_solo_mjcardona.py` |
| Ejemplo de uso | Llama al orquestador | `ejemplos/ejemplo_informe_ejecutivo.py` |

---

## Apéndice A — Ejemplo de Request/Response

### Estado Actual

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/orchestrator \
  -H "Content-Type: application/json" \
  -H "X-API-Key: [API_KEY]" \
  -d '{
    "sessionId": "chat_12345",
    "intent": "estado_actual",
    "parameters": {}
  }'
```

### Predicciones (1 mes)

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/orchestrator \
  -H "Content-Type: application/json" \
  -H "X-API-Key: [API_KEY]" \
  -d '{
    "sessionId": "chat_12345",
    "intent": "predicciones_sector",
    "parameters": {"horizonte": "1_mes"}
  }'
```

### Pregunta Libre con IA

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/orchestrator \
  -H "Content-Type: application/json" \
  -H "X-API-Key: [API_KEY]" \
  -d '{
    "sessionId": "chat_12345",
    "intent": "pregunta_libre",
    "parameters": {
      "pregunta": "¿Cómo están los embalses hoy?",
      "con_analisis_ia": true
    }
  }'
```

---

**Documento generado por inspección automática del código fuente el 1 de marzo de 2026.**  
**Versión:** 2.0 — Refleja el estado real del sistema en producción.
