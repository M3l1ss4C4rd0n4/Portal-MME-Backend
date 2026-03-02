# INFORME DE ARQUITECTURA COMPLETA — Portal Energético MME

**Fecha:** 2026-03-01  
**Versión:** 1.0  
**Autor:** Auditoría Automatizada de Arquitectura  
**Alcance:** Inspección recursiva completa del servidor `/home/admonctrlxm/server`

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura General](#2-arquitectura-general)
3. [Inventario Completo de Directorios](#3-inventario-completo-de-directorios)
4. [Capa Core — Fundación de la Aplicación](#4-capa-core)
5. [Capa Domain — Lógica de Negocio](#5-capa-domain)
6. [Capa Infrastructure — Adaptadores y Repositorios](#6-capa-infrastructure)
7. [Capa Interface — Dashboard Dash](#7-capa-interface)
8. [API RESTful — FastAPI](#8-api-restful)
9. [ETL — Pipelines de Datos](#9-etl-pipelines)
10. [Scripts — Operaciones y Diagnósticos](#10-scripts-operaciones)
11. [Tasks — Celery y Automatización](#11-tasks-celery)
12. [WhatsApp/Telegram Bot](#12-whatsapp-telegram-bot)
13. [ML/Experiments — Modelos de Predicción](#13-ml-experiments)
14. [Tests — Cobertura de Pruebas](#14-tests-cobertura)
15. [Assets, Data y Archivos Estáticos](#15-assets-data)
16. [Configuración de Infraestructura](#16-configuracion-infraestructura)
17. [Limpieza Realizada](#17-limpieza-realizada)
18. [Hallazgos Críticos y Recomendaciones](#18-hallazgos-criticos)
19. [Métricas del Proyecto](#19-metricas-del-proyecto)

---

## 1. Resumen Ejecutivo

El Portal Energético del Ministerio de Minas y Energía (MME) de Colombia es una plataforma web integral que centraliza datos del sector energético nacional. Desplegado en `portalenergetico.minenergia.gov.co` (IP 172.17.0.46), el sistema comprende:

- **Dashboard interactivo** (Dash/Plotly) con 12 tableros sectoriales
- **API RESTful** (FastAPI) con 25 endpoints y autenticación por API Key
- **Pipeline ETL** automatizado (9 cron jobs) alimentado por XM Colombia, SIMEM e IDEAM
- **Motor de predicciones ML** (Prophet, ARIMA, XGBoost, LightGBM, modelos SOTA)
- **Bot multicanal** (WhatsApp + Telegram) con IA conversacional
- **Base de datos** PostgreSQL (~63.7M filas)
- **Publicación geoespacial** en ArcGIS Enterprise/Online
- **Sistema de notificaciones** (Telegram + Email) con detección de anomalías

### Arquitectura de Alto Nivel

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NGINX (puerto 80/443)                       │
│  portalenergetico.minenergia.gov.co                                 │
├───────────────────────┬─────────────────────────────────────────────┤
│   /api/* → :8000      │   /* → :8050                                │
│   FastAPI (Gunicorn)  │   Dash (Gunicorn)                           │
│   4 workers UvicornW  │   cpu*2+1 workers gthread                   │
├───────────────────────┴─────────────────────────────────────────────┤
│                     Capa de Dominio (domain/)                       │
│  orchestrator · generation · hydrology · commercial · distribution  │
│  transmission · losses · restrictions · predictions · notifications │
│  ai_service · news_service · report_service · intelligent_analysis  │
├─────────────────────────────────────────────────────────────────────┤
│                   Capa de Infraestructura                           │
│  PostgreSQL │ Redis │ XM API │ SIMEM │ IDEAM │ Groq/OpenRouter     │
│  ArcGIS Enterprise │ Telegram API │ Twilio │ Microsoft Graph        │
├─────────────────────────────────────────────────────────────────────┤
│                     Automatización                                  │
│  Celery Beat │ 9 Cron Jobs │ systemd services │ logrotate           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Arquitectura General

### 2.1 Patrón Arquitectónico

El proyecto sigue una **Arquitectura Hexagonal (Ports & Adapters)** parcial con inyección de dependencias manual:

| Capa | Directorio | Responsabilidad |
|------|-----------|-----------------|
| **Core** | `core/` | Configuración, constantes, DI container, factory |
| **Domain** | `domain/` | Interfaces (puertos), modelos, servicios de negocio |
| **Infrastructure** | `infrastructure/` | Repositorios, adaptadores externos, logging |
| **Interface** | `interface/` | Páginas Dash, componentes UI, callbacks |
| **API** | `api/` | Endpoints REST, esquemas Pydantic, DI per-request |
| **ETL** | `etl/` | Pipelines de extracción, validación, carga |

### 2.2 Stack Tecnológico

| Componente | Tecnología | Versión |
|-----------|-----------|---------|
| Dashboard | Dash + Plotly + Bootstrap | 2.17.1 / 5.17.0 |
| API REST | FastAPI + Uvicorn + slowapi | 0.109.0 |
| Base de datos | PostgreSQL + psycopg2 | Latest / 2.9.9 |
| Caché | Redis | 5.0.8 |
| ML | Prophet + ARIMA + XGBoost + LightGBM + NeuralForecast | Múltiples |
| IA | Groq (llama-3.3-70b) + OpenRouter | via openai SDK |
| Bot | python-telegram-bot + Twilio + whatsapp-web.js | Múltiples |
| Servidor | Gunicorn + Nginx + systemd | 21.2.0 |
| Datos externos | pydataxm + pydatasimem + ArcGIS Python API | 2.1.1 |
| PDF | WeasyPrint | ≥60.0 |
| Monitoreo | Prometheus + psutil | 0.20.0 |

### 2.3 Puertos de Red

| Puerto | Servicio | Binding |
|--------|---------|---------|
| 80/443 | Nginx (proxy) | 0.0.0.0 |
| 8050 | Dashboard Dash (Gunicorn) | 127.0.0.1 |
| 8000 | API FastAPI (Gunicorn+Uvicorn) | 127.0.0.1 |
| 8001 | WhatsApp Bot (FastAPI) | 127.0.0.1 |
| 5000 | MLflow Tracking Server | 127.0.0.1 |

### 2.4 Servicios systemd

| Servicio | Archivo | Descripción |
|---------|---------|-------------|
| `dashboard-mme.service` | `dashboard-mme.service` | Dashboard Dash vía Gunicorn |
| `api-mme.service` | `api-mme.service` | API FastAPI vía Gunicorn+Uvicorn |
| `mlflow-server.service` | `config/mlflow-server.service` | MLflow tracking |
| `celery-worker@.service` | `config/celery-worker@.service` | Workers Celery |

---

## 3. Inventario Completo de Directorios

### 3.1 Estructura y Tamaños

| Directorio | Tamaño | Archivos Python | Propósito |
|-----------|--------|----------------|-----------|
| `core/` | 140K | 8 | Configuración, constantes, DI, factory |
| `domain/` | 1.4M | 31 | Interfaces, modelos, 24 servicios de negocio |
| `infrastructure/` | 368K | 17 | Repositorios, adaptadores, logging, news |
| `interface/` | 1.7M | 17 | 12 páginas Dash + 5 componentes |
| `api/` | 484K | 27 | 12 rutas + 12 schemas + main + dependencies |
| `etl/` | 228K | 8 | 5 ETL pipelines + 2 validadores + config |
| `scripts/` | 804K | 32 | Operaciones, diagnósticos, utilidades |
| `tasks/` | 112K | 3 | Celery tasks (ETL, predicciones, reportes) |
| `tests/` | 668K | 20 | Unit tests + integration + scripts ARGIS |
| `whatsapp_bot/` | 55M* | 19 | Bot WhatsApp/Telegram + Node.js service |
| `experiments/` | 46M | 5 | ML experiments FASE 5B/6/7/15 |
| `assets/` | 5.7M | 2 JS | CSS, imágenes, GeoJSON |
| `data/` | 2.0M | — | OneDrive sync + charts generados |
| `docs/` | 3.4M | — | Documentación técnica (13 archivos) |
| `config/` | 16K | — | systemd services, logrotate |
| `sql/` | 24K | — | 4 scripts SQL |
| `ejemplos/` | 40K | 2 | Ejemplos de consumo de API |
| `backups/` | 854M | — | DB dumps semanales (automatizados) |
| `mlruns/` | 276K | — | MLflow experiment tracking |
| `notebooks/` | 8K | — | Solo README.md |

*\*excluyendo venv (3.2G) y node_modules (82M)*

### 3.2 Archivos Raíz

| Archivo | Propósito |
|---------|-----------|
| `app.py` | Entry point del Dashboard Dash |
| `wsgi.py` | Entry point WSGI para Gunicorn |
| `gunicorn_config.py` | Configuración Gunicorn (workers, threads, logging) |
| `requirements.txt` | 35 dependencias Python |
| `pytest.ini` | Configuración pytest (markers, paths) |
| `api-mme.service` | Unidad systemd para API FastAPI |
| `dashboard-mme.service` | Unidad systemd para Dashboard |
| `nginx-api-config.conf` | Nginx con HTTP/HTTPS, SSL, proxy a :8000 y :8050 |
| `nginx-dashboard.conf` | Nginx alternativo con caché de assets |
| `LICENSE` | Licencia del proyecto |
| `.env` / `.env.example` | Variables de entorno |
| `.gitignore` | 152 líneas de exclusiones |
| `celerybeat-schedule` | Archivo binario de Celery Beat (gitignored) |

---

## 4. Capa Core — Fundación de la Aplicación {#4-capa-core}

**Directorio:** `core/` — 1,621 líneas, 8 archivos

### 4.1 Archivos

| Archivo | Líneas | Rol |
|---------|--------|-----|
| `config.py` | 528 | Pydantic Settings — 40+ campos (DB, AI, ML, API, Gunicorn) |
| `constants.py` | 502 | IDs de métricas XM, colores UI, umbrales, configuraciones |
| `container.py` | 258 | Contenedor DI manual — singleton repos + factory services |
| `app_factory.py` | 254 | Factory de la aplicación Dash (layout, callbacks, Prometheus) |
| `validators.py` | 35 | Validación de rangos de fechas y strings |
| `exceptions.py` | 23 | Jerarquía: `PortalError` → Date/Parameter/DataNotFound/ExternalAPI/Database |
| `config_simem.py` | 21 | Stub de compatibilidad SIMEM |
| `__init__.py` | 0 | Marcador de paquete |

### 4.2 Patrones Clave

- **Pydantic Settings** — Configuración tipada con binding a `.env`, propiedades computadas
- **Dependency Injection** — `DependencyContainer` con 5 repos singleton + factory services + `override_*()` para testing
- **Factory** — `create_app()` construye Dash con páginas, layout, callbacks, Flask health endpoints, Prometheus
- **Singleton** — `settings`, `container`, registros Prometheus como singletons module-level

### 4.3 Problemas Detectados

| Severidad | Problema |
|-----------|---------|
| **Media** | `SmartDict`/`UIColors` definidos 3 veces en `constants.py` — las 2 primeras son código muerto |
| **Baja** | `_register_pages()` en `app_factory.py` es una función vacía (`pass`) |
| **Baja** | `redis_cache_operations` Prometheus counter definido pero nunca incrementado |
| **Baja** | `config_simem.py` es un stub documentado — migración incompleta |
| **Baja** | `validators.py` usa `except:` bare que silencia todas las excepciones |

---

## 5. Capa Domain — Lógica de Negocio {#5-capa-domain}

**Directorio:** `domain/` — 15,110 líneas, 31 archivos Python

### 5.1 Interfaces (Puertos)

| Interfaz | Métodos | Propósito |
|----------|---------|-----------|
| `IMetricsRepository` | 6 | CRUD de métricas energéticas (series temporales) |
| `ICommercialRepository` | 4 | Datos de mercado comercial |
| `IDistributionRepository` | 4 | Datos de distribución |
| `ITransmissionRepository` | 5 | Datos de transmisión |
| `IPredictionsRepository` | 5 | CRUD de predicciones ML |
| `IXMDataSource` | 4 | Abstracción API XM |
| `ISIMEMDataSource` | 2 | Abstracción datos SIMEM |
| `IIDEAMDataSource` | 2 | Abstracción datos meteorológicos (declarada, sin implementación) |
| `IDatabaseManager` | 6 | Gestión de conexiones DB |
| `IConnectionManager` | 3 | Pool de conexiones |

### 5.2 Modelos de Dominio

| Modelo | Campos | Estado |
|--------|--------|--------|
| `Metric` | fecha, metrica, entidad, valor_gwh, unidad, recurso | ⚠️ Definido pero NO usado — servicios usan DataFrames crudos |
| `Prediction` | fecha_prediccion, fuente, valor_gwh_predicho, modelo, confianza | ⚠️ Definido pero NO usado |

### 5.3 Servicios de Negocio (24 archivos)

| Servicio | Líneas | Función Principal |
|---------|--------|-------------------|
| `orchestrator_service.py` | **4,197** | Orquestador chatbot — mapea 20+ intents a servicios |
| `report_service.py` | 1,715 | Generación de reportes PDF (WeasyPrint, Markdown→HTML) |
| `executive_report_service.py` | 1,474 | Reporte ejecutivo async con análisis estadístico |
| `notification_service.py` | 1,175 | Broadcast Telegram + Email SMTP |
| `intelligent_analysis_service.py` | 832 | Detección de anomalías, análisis sectorial |
| `news_service.py` | 506 | Agregación multi-fuente de noticias (GNews, Mediastack, Google RSS) |
| `generation_service.py` | 446 | Generación: diaria, por recurso, por fuente |
| `predictions_service_extended.py` | 432 | Predicciones ML (Prophet, ARIMA, ensemble) |
| `ai_service.py` | 420 | Análisis LLM (Groq/OpenRouter), chat interactivo |
| `distribution_service.py` | 401 | Distribución: demanda real/comercial |
| `hydrology_service.py` | 348 | Niveles de embalse, aportes, volúmenes |
| `commercial_service.py` | 280 | Precios de bolsa, escasez |
| `validators.py` | 247 | Validación de rangos para métricas colombianas |
| `transmission_service.py` | 207 | Líneas de transmisión, intercambios internacionales |
| `metrics_service.py` | 200 | Servicio genérico de métricas |
| `metrics_calculator.py` | 197 | Cálculo de variaciones (fórmula XM) |
| `restrictions_service.py` | 198 | Restricciones (aliviadas, AGC, costo) |
| `system_service.py` | 193 | Health check: conectividad, frescura de datos |
| `indicators_service.py` | 173 | Indicadores comparativos con flecha |
| `losses_service.py` | 152 | Pérdidas de energía (STN/STR/SDL) |
| `confianza_politica.py` | 122 | Política de confianza de predicciones |
| `geo_service.py` | 32 | Coordenadas estáticas de departamentos |
| `predictions_service.py` | 32 | Wrapper legacy sobre PredictionsRepository |
| `data_loader.py` | 13 | Single `to_excel()` utility |

### 5.4 Esquemas del Orquestador

```
domain/schemas/orchestrator.py (495 líneas)
├── OrchestratorRequest    → sessionId + intent + parameters
├── OrchestratorResponse   → status + data + errors
├── ErrorDetail           → code + message + field
├── GeneracionElectricaParams → parámetros de consulta generación
├── HidrologiaParams      → parámetros de consulta hidrología
├── DemandaSistemaParams  → parámetros de consulta demanda
├── PreciosBolsaParams    → parámetros de consulta precios
├── PrediccionesParams    → parámetros de consulta predicciones
├── AnomaliaSchema        → detección de anomalías
├── SectorStatusSchema    → estado de salud sectorial
├── EstadoActualResponse  → estado completo del sistema
└── AnomaliasResponse     → reporte de anomalías
```

---

## 6. Capa Infrastructure — Adaptadores y Repositorios {#6-capa-infrastructure}

**Directorio:** `infrastructure/` — 17 archivos fuente

### 6.1 Base de Datos

```
infrastructure/database/
├── connection.py         → PostgreSQLConnectionManager (context manager)
├── manager.py            → DatabaseManager (IDatabaseManager) — query_df, upsert_bulk
└── repositories/
    ├── base_repository.py          → execute_query/dataframe (usa connection.py)
    ├── metrics_repository.py       → IMetricsRepository (extends BaseRepository)
    ├── predictions_repository.py   → IPredictionsRepository (extends BaseRepository)
    ├── transmission_repository.py  → ITransmissionRepository (extends BaseRepository)
    ├── commercial_repository.py    → ICommercialRepository (usa manager.py directo)
    └── distribution_repository.py  → IDistributionRepository (usa manager.py directo)
```

**⚠️ Doble ruta de conexión:** `connection.py` y `manager.py` crean conexiones PostgreSQL independientemente. `BaseRepository` usa `connection.py`; `CommercialRepository` y `DistributionRepository` usan `manager.py`. Esto genera inconsistencia en manejo de errores.

### 6.2 Adaptadores Externos

| Adaptador | Fuente | Protocolo |
|-----------|--------|-----------|
| `xm_service.py` + `xm_adapter.py` | XM Colombia | pydataxm + PostgreSQL fallback |
| `ideam_service.py` | IDEAM (datos.gov.co) | Socrata SODA API con retry |
| `google_news_rss.py` | Google News | RSS feed async (httpx) |
| `mediastack_client.py` | Mediastack | REST API (500 req/mes) |
| `news_client.py` | GNews | REST API (100 req/día) |

### 6.3 Logging

`infrastructure/logging/logger.py` — Sistema centralizado con:
- Rotating file handler (10MB max por archivo)
- Log separado de errores (`errors.log`)
- Console handler solo en modo desarrollo
- `get_logger()` para loggers per-module

---

## 7. Capa Interface — Dashboard Dash {#7-capa-interface}

**Directorio:** `interface/` — 19,354 líneas, 17 archivos Python

### 7.1 Componentes Reutilizables

| Componente | Archivo | Función |
|-----------|---------|---------|
| `crear_chart_card()` | `components/chart_card.py` | Card wrapper Tabler para gráficos |
| `crear_kpi()` / `crear_kpi_row()` | `components/kpi_card.py` | Tarjeta KPI con icono, valor, variación |
| `crear_page_header()` | `components/chart_card.py` | Encabezado de página |
| `crear_chat_widget()` | `components/chat_widget.py` | Widget flotante de chat IA (Groq/OpenRouter) |
| `crear_header_restaurado()` | `components/header.py` | Navbar global (8 links) |
| `crear_navbar_horizontal()` | `components/layout.py` | Navbar legacy (9 links) — **duplicada** |

### 7.2 Páginas del Dashboard (12 tableros)

| # | Ruta | Archivo | Líneas | Métricas Clave |
|---|------|---------|--------|----------------|
| 1 | `/` | `home.py` | 520 | Navegación — SVG interactivo del sistema energético |
| 2 | `/generacion` | `generacion.py` | 471 | Reservas Hídricas %, Aportes GWh, Generación SIN GWh |
| 3 | `/generacion/fuentes` | `generacion_fuentes_unificado.py` | 3,457 | Mix por fuente: hidráulica, térmica, solar, eólica + predicciones ML |
| 4 | `/generacion/hidraulica/hidrologia` | `generacion_hidraulica_hidrologia.py` | **7,319** | Embalses, aportes por río, semáforo de riesgo, mapa Colombia |
| 5 | `/transmision` | `transmision.py` | 689 | Capacidad STN MW, líneas, interrupciones, disponibilidad % |
| 6 | `/distribucion` | `distribucion.py` | 1,211 | Demanda comercial/regulada/no regulada GWh (con modal 24h) |
| 7 | `/comercializacion` | `comercializacion.py` | 736 | Precio Bolsa $/kWh, Escasez, Oferta, Máximo Cargo |
| 8 | `/perdidas` | `perdidas.py` | 342 | Pérdidas STN/STR/SDL/Totales % |
| 9 | `/restricciones` | `restricciones.py` | 382 | Restricciones generación GWh, voltaje, AGC, costo $ |
| 10 | `/metricas` | `metricas.py` | 2,521 | Navegador universal de 120+ métricas XM/SIMEM con export |
| 11 | `/metricas-piloto` | `metricas_piloto.py` | 93 | KPIs piloto con comparación predicciones |
| 12 | `/seguimiento-predicciones` | `seguimiento_predicciones.py` | 988 | Monitoreo MAPE/RMSE/MAE/R² por modelo ML |

**Total callbacks registrados:** ~59 (56 server-side + 3 clientside)

### 7.3 Flujo de Datos por Tablero

```
Páginas modernas (gen, dist, com, pérd, restr, trans):
  interface/pages/*.py → domain/services/*_service.py → infrastructure/

Páginas legadas (métricas, seguimiento):
  interface/pages/*.py → pydataxm/pydatasimem directo  (métricas)
  interface/pages/*.py → psycopg2 directo               (seguimiento)

Páginas híbridas (gen_fuentes, hidro):
  interface/pages/*.py → domain/services/ + xm_service directo + db_manager
```

---

## 8. API RESTful — FastAPI {#8-api-restful}

**Directorio:** `api/` — 25 endpoints, 12 rutas, 27 archivos

### 8.1 Endpoints

| Prefijo | Endpoints | Rate Limit | Autenticación |
|---------|----------|------------|---------------|
| `/v1/generation` | 4 GET (system, by-source, resources, mix) | 100/min | API Key |
| `/v1/hydrology` | 3 GET (aportes, reservoirs, energy) | 100/min | API Key |
| `/v1/system` | 2 GET (demand, prices) | 100/min | API Key |
| `/v1/transmission` | 3 GET (lines, flows*, international) | 100/min | API Key |
| `/v1/distribution` | 2 GET (data, operators) | 100/min | API Key |
| `/v1/commercial` | 2 GET (prices, contracts*) | 100/min | API Key |
| `/v1/losses` | 1 GET (data) | 100/min | API Key |
| `/v1/restrictions` | 1 GET (data) | 100/min | API Key |
| `/v1/metrics` | 2 GET (by id, list) | 60-100/min | API Key |
| `/v1/predictions` | 3 GET + 1 POST + 1 DELETE | 5-20/min | API Key |
| `/v1/chatbot` | 1 POST + 1 GET (orchestrator, health) | 100/min | API Key |
| `/v1/whatsapp` | 1 POST + 1 GET (send-alert, bot-status) | — | ⚠️ Sin auth |

*\*Endpoints stub (flows, contracts) — retornan datos vacíos*

### 8.2 Funcionalidades Clave

- **OpenAPI 3.0.3** con Swagger UI y ReDoc personalizados
- **Rate limiting** con `slowapi` (Redis-backed)
- **Caché de predicciones** en Redis (FASE 19): TTL 1h individual, 30min batch
- **DI** para métricas y predicciones vía `Depends()` — pero 10 de 12 rutas instancian servicios directamente

### 8.3 Problemas de Seguridad

| Severidad | Problema |
|-----------|---------|
| **Crítica** | Endpoints WhatsApp (`send-alert`, `bot-status`) sin autenticación API Key |
| **Alta** | `requests.post()` síncrono en handler async — bloquea event loop |
| **Alta** | SQL injection en `ai_service.py` (`f"SELECT * FROM {tabla}"`) |
| **Alta** | SQL injection en `generation_service.py` (`f"AND tipo = '{tipo_consulta}'"`) |

---

## 9. ETL — Pipelines de Datos {#9-etl-pipelines}

**Directorio:** `etl/` — 8 archivos

### 9.1 Pipelines

| Pipeline | Frecuencia | Fuente → Destino |
|---------|-----------|-------------------|
| `etl_todas_metricas_xm.py` | Cada 6h (cron) | XM API → PostgreSQL (106 métricas) |
| `etl_transmision.py` | Diario 6:30 AM | SIMEN → ⚠️ SQLite (no migrado a PostgreSQL) |
| `etl_xm_to_postgres.py` | Bajo demanda | XM API → PostgreSQL (archivo) |
| `etl_ideam.py` | — | IDEAM (datos.gov.co) → PostgreSQL |
| `etl_rules.py` | — | Motor de reglas para validación post-ETL |
| `validaciones.py` | — | Validación de datos: rangos, fechas, duplicados |
| `validaciones_rangos.py` | — | Rangos específicos por tipo de métrica colombiana |
| `config_metricas.py` | — | Catálogo de 106 métricas XM + configuración |

### 9.2 Cron Jobs Activos

```
30 6 * * *     ETL Transmisión (diario)
0 */6 * * *    ETL métricas XM (cada 6h)
0 * * * *      ArcGIS Enterprise (horario, dual account)
30 * * * *     ArcGIS Online (cada 30min)
0 2 * * 0      Predicciones ML (semanal, domingos)
0 3 * * 0      Backup PostgreSQL (semanal, domingos)
0 4 1 * *      Backfill métricas (mensual)
*/5 * * * *    Monitor API (cada 5min)
@reboot        Auto-start API al reiniciar
```

### 9.3 Problemas Detectados

| Severidad | Problema |
|-----------|---------|
| **Alta** | `etl_transmision.py` usa SQLite mientras todo lo demás usa PostgreSQL |
| **Alta** | `convertir_unidades()` definida en 3 archivos con lógica potencialmente inconsistente |
| **Media** | Clave duplicada en `config_metricas.py` (`metricas_restricciones` sobrescrita silenciosamente) |
| **Media** | Scripts ops (`monitorear_etl.sh`, `verificar_sistema.sh`) aún referencian SQLite |
| **Media** | Conflicto de validación de rangos entre `validaciones_rangos.py` y `etl_rules.py` |

---

## 10. Scripts — Operaciones y Diagnósticos {#10-scripts-operaciones}

**Directorio:** `scripts/` — 32 archivos (804K)

### 10.1 Categorías

| Categoría | Archivos | Ejemplos |
|-----------|---------|----------|
| **Operaciones** | 8 | `monitor_api.sh`, `actualizar_predicciones.sh`, `manage-server.sh` |
| **Diagnóstico** | 6 | `diagnostico_metricas_etl.py`, `diagnostico_conversores_unidades.py` |
| **Training ML** | 2 | `train_predictions_postgres.py`, `train_predictions_sector_energetico.py` |
| **Alertas** | 2 | `alertas_energeticas.py`, `sistema_notificaciones.py` |
| **Utilidades** | 5 | `run_logrotate.sh`, `restart_dashboard.sh`, `monitor_dashboard.sh` |
| **Tests manuales** | 9 | `test_predictions_integration.py`, `test_alertas_e2e.py`, etc. |

### 10.2 Train Predictions

`scripts/train_predictions_sector_energetico.py` (4,019 líneas) — Script principal de entrenamiento:
- 6 métricas élite: DemaCome, Gene, PrecBolsNaci, AporEner, Gene_Eolica, Gene_Solar
- 3 modelos: Prophet, ARIMA, Ensemble
- 11 regresores multivariable (embalses, aportes, precio_bolsa, etc.)
- Festivos colombianos 2020-2027
- Horizonte: 30 días
- Validación MAPE/RMSE/MAE/R²
- Se ejecuta semanalmente vía cron

---

## 11. Tasks — Celery y Automatización {#11-tasks-celery}

**Directorio:** `tasks/` — 3 archivos

| Archivo | Funcionalidad |
|---------|--------------|
| `celery_app.py` | Configuración Celery con Redis broker (DB 0), result backend (DB 1) |
| `etl_tasks.py` | Tasks: `run_etl_metrics`, `run_etl_transmission`, `run_etl_ideam`, `run_backfill`, `generate_arcgis_csv` + Beat schedule |
| `prediction_tasks.py` | Tasks: `train_all_predictions`, `train_single_prediction`, `generate_report`, `generate_system_status` |

**Beat Schedule:**
- ETL métricas XM: cada 6 horas
- ETL transmisión: diario 6:30 AM
- Predicciones: semanal domingos 2:00 AM
- CSV ArcGIS: cada hora
- Reporte ejecutivo: diario 7:00 AM
- Estado del sistema: cada 3 horas

---

## 12. WhatsApp/Telegram Bot {#12-whatsapp-telegram-bot}

**Directorio:** `whatsapp_bot/` — 19 archivos Python + Node.js service

### 12.1 Arquitectura del Bot

```
Telegram (python-telegram-bot polling)  ──┐
                                          ├──→ BotOrchestrator (intent classification)
WhatsApp (Twilio/Meta/whatsapp-web.js) ──┘         │
                                                    ├── DataService (PostgreSQL)
                                                    ├── AIIntegration (Groq/AgentIA)
                                                    └── ChartService (Plotly→PNG)
```

### 12.2 Componentes

| Componente | Archivo | Líneas |
|-----------|---------|--------|
| API Entry Point | `app/main.py` | 413 |
| Telegram Bot (prod) | `telegram_polling.py` | 1,745 |
| Bot Orchestrator | `orchestrator/bot.py` | 306 |
| WhatsApp Webhook | `app/webhook.py` | 185 |
| Message Sender | `app/sender.py` | 253 |
| AI Integration | `services/ai_integration.py` | 155 |
| Data Service | `services/data_service.py` | 210 |
| Chart Generator | `services/chart_service.py` | 351 |
| Executive Charts | `services/informe_charts.py` | 599 |
| Context Manager | `orchestrator/context.py` | 200 |
| Rate Limiting | `app/rate_limiting.py` | 130 |
| Celery Tasks | `app/tasks.py` | 300 |
| Node.js Service | `whatsapp-web-service/server.js` | 299 |

### 12.3 Problemas

| Severidad | Problema |
|-----------|---------|
| **Media** | `orchestrator/context.py` (ContextManager) definido pero **nunca importado/usado** — código muerto |
| **Media** | `app/telegram_handler.py` duplica funcionalidad de `telegram_polling.py` — deprecado |
| **Media** | `services/data_service.py` usa 'PrecioBolsa' pero la BD usa 'PrecBolsNaci' |
| **Baja** | `telegram_polling.py` (1,745 líneas) — debería descomponerse en módulos |

---

## 13. ML/Experiments — Modelos de Predicción {#13-ml-experiments}

**Directorio:** `experiments/` — 5 scripts Python + resultados

### 13.1 Evolución de Fases ML

| FASE | Archivo | Modelos | Métricas |
|------|---------|---------|----------|
| 5.B | `xgboost_precio_bolsa.py` | XGBoost vs Ensemble | PRECIO_BOLSA |
| 6 | `model_selection.py` | XGBoost, LightGBM, RF, LSTM, Ensemble, Hybrid | PRECIO_BOLSA, DEMANDA, APORTES |
| 7 | `sota_models.py` | PatchTST, N-BEATS, TCN, N-HiTS, Chronos + baselines | PRECIO_BOLSA, DEMANDA |
| 15 | `XM_Multivariate_Discovery.py` | Análisis estadístico (Granger, PCA, VIF, redes) | 6 métricas élite |

### 13.2 Resultados en experiments/results/

- CSVs de comparación por métrica (3 métricas × 5 outputs = 15 archivos)
- Gráficos HTML interactivos (barras comparativas + líneas holdout)
- Resultados SOTA separados para DEMANDA y PRECIO_BOLSA

---

## 14. Tests — Cobertura de Pruebas {#14-tests-cobertura}

### 14.1 Tests Reales por Categoría

| Tipo | Archivos | Framework | Cobertura |
|------|---------|-----------|-----------|
| **Unit (pytest)** | 5 | pytest + mocks | MetricsRepo, PredictionsRepo, GenerationService, HydrologyService, TransmissionService |
| **ETL (pytest)** | 1 | unittest | Validaciones, umbrales, duplicados |
| **Bot (pytest)** | 1 | pytest + TestClient | Endpoints, intent classification |
| **Scripts diagnóstico** | 5 | Script manual | Orquestador, API, informes ejecutivos — ⚠️ NO son pytest |
| **ARGIS** | 3 | Script manual | ArcGIS Enterprise/Online — ⚠️ Mal ubicados en tests/ |

### 14.2 Cobertura Real Estimada

| Capa | Tests | Estado |
|------|-------|--------|
| `domain/services/` | 3 de 24 servicios con unit tests | 🔴 12.5% |
| `infrastructure/database/repositories/` | 2 de 6 repos con unit tests | 🟡 33% |
| `etl/` | 1 validador de 8 total | 🔴 12.5% |
| `api/` | 0 endpoints con TestClient | 🔴 0% |
| `interface/` | 0 páginas | 🔴 0% |
| `whatsapp_bot/` | 1 módulo de 13 | 🔴 8% |

### 14.3 Archivos en tests/ARGIS/ (Mal Ubicados)

Estos son scripts operacionales de producción, no tests:
- `actualizar_capa_hospedada.py` (709 líneas) — Publica CSVs a ArcGIS Enterprise
- `actualizar_datos_xm_online.py` (801 líneas) — Extrae datos XM → ArcGIS Online
- `actualizar_desde_onedrive.py` (1,203 líneas) — Microsoft Graph → SharePoint → ArcGIS

**Recomendación:** Mover a `scripts/arcgis/` o `infrastructure/arcgis/`.

---

## 15. Assets, Data y Archivos Estáticos {#15-assets-data}

### 15.1 Assets (5.7M)

| Tipo | Archivos | Propósito |
|------|---------|-----------|
| CSS | 10 archivos | Estilos Tabler-MME, KPI, navbar, tabla, portada, chat-IA |
| JavaScript | 2 archivos | `navbar-active.js`, `portada-interactive.js` + `sidebar.js` |
| GeoJSON | 1 archivo | `departamentos_colombia.geojson` (1.5M) |
| JSON | 1 archivo | `regiones_naturales_colombia.json` |
| Imágenes | `images/` | Logo MME, favicons, íconos de fuentes energéticas |

### 15.2 Data Activa (2.0M)

| Directorio | Contenido | Actualización |
|-----------|-----------|---------------|
| `data/metricas_xm_arcgis.csv` | CSV para publicación ArcGIS | Horaria (cron) |
| `data/onedrive/` | 13 archivos xlsx/csv sincronizados desde SharePoint | Diaria |
| `data/charts/` | PNGs generados para bot (embalses, precios, generación) | Bajo demanda |

### 15.3 SQL Scripts

| Archivo | Propósito |
|---------|-----------|
| `sql/alertas_historial.sql` | Esquema tabla de historial de alertas |
| `sql/actualizar_alertas_historial.sql` | Migración de columnas alertas |
| `sql/predictions_simple.sql` | Vista simplificada de predicciones |
| `sql/telegram_users_and_recipients.sql` | Tablas de usuarios Telegram |

---

## 16. Configuración de Infraestructura {#16-configuracion-infraestructura}

### 16.1 Nginx

Dos archivos de configuración:
- `nginx-api-config.conf` — **Producción activa**: HTTP + HTTPS con SSL, proxy a :8000 (API) y :8050 (Dashboard), security headers, WebSocket support
- `nginx-dashboard.conf` — **Alternativo**: Con proxy_cache de assets, upstream, gzip

### 16.2 systemd

| Servicio | Puerto | Workers | Modo |
|---------|--------|---------|------|
| `api-mme.service` | :8000 | 4 Uvicorn | `Type=notify`, `Restart=always` |
| `dashboard-mme.service` | :8050 | cpu×2+1 gthread | `Type=notify`, `Restart=always` |
| `mlflow-server.service` | :5000 | — | MLflow tracking |
| `celery-worker@.service` | — | — | Template para workers Celery |

### 16.3 Logrotate

```
config/logrotate.conf
 → /home/admonctrlxm/server/logs/*.log
 → daily, rotate 14, compress, 50M size
```

---

## 17. Limpieza Realizada {#17-limpieza-realizada}

### 17.1 Archivos/Directorios Eliminados

| Elemento | Tamaño | Razón |
|---------|--------|-------|
| `control/` | 0 | Directorio vacío |
| `lightning_logs/` | 2.7M | Artefactos TensorBoard obsoletos (~50 event files) |
| `infrastructure/ml/models/` | 0 | Directorio vacío |
| `infrastructure/etl/` | 0 | Módulo placeholder vacío |
| `logs/mlflow_artifacts/` | 0 | Directorio vacío |
| `domain/services/report_service.py.bak` | ~56K | Archivo backup en código fuente |
| `backups/deprecated_css_js/` | 40K | CSS/JS obsoleto ya respaldado |
| `backups/lineas_transmision_simen.csv.bak` | 58M | CSV backup antiguo |
| `logs/debug_callback.log` | Variable | Log de debug temporal |
| `__pycache__/` (15 directorios) | Variable | Caché de bytecode Python |

**Espacio total liberado: ~61M** (excluyendo caché)

### 17.2 Actualizaciones a .gitignore

Nuevas entradas agregadas:
```
lightning_logs/
mlruns/
data/charts/*.png
celerybeat-schedule
celerybeat.pid
experiments/results/
experiments/*.csv
*.bak
```

### 17.3 Archivos Des-rastreados de Git

- `data/charts/*.png` (6 archivos) — Ahora gitignored
- `domain/services/report_service.py.bak` — Eliminado

---

## 18. Hallazgos Críticos y Recomendaciones {#18-hallazgos-criticos}

### 18.1 Seguridad — PRIORIDAD INMEDIATA

| # | Hallazgo | Ubicación | Riesgo |
|---|---------|----------|--------|
| 1 | **Endpoints sin autenticación** — `send-alert` y `whatsapp-bot-status` no requieren API Key | `api/v1/routes/whatsapp_alerts.py` | Alto |
| 2 | **SQL Injection** — interpolación de strings en queries SQL | `ai_service.py`, `generation_service.py` | Alto |
| 3 | **Credenciales hardcodeadas** — password de BD en 3 archivos | `tests/`, `experiments/` | Medio |
| 4 | **Credenciales ArcGIS hardcodeadas** — "Survey123+" como default | `tests/ARGIS/actualizar_datos_xm_online.py` | Medio |

### 18.2 Arquitectura — DEUDA TÉCNICA

| # | Hallazgo | Impacto | Esfuerzo |
|---|---------|---------|----------|
| 5 | **Monolito de 7,319 líneas** (`generacion_hidraulica_hidrologia.py`) — plan de refactoring existe en `hidrologia/__init__.py` pero nunca se ejecutó | Mantenibilidad | Alto |
| 6 | **Orquestador de 4,197 líneas** (`orchestrator_service.py`) | Mantenibilidad | Alto |
| 7 | **Doble ruta de conexión DB** — `connection.py` vs `manager.py` usados por diferentes repos | Inconsistencia | Medio |
| 8 | **DI inconsistente** — solo 2 de 12 rutas API usan `Depends()` para servicios | Testabilidad | Medio |
| 9 | **`etl_transmision.py` aún usa SQLite** — no migrado a PostgreSQL | Fragmentación de datos | Medio |
| 10 | **Modelos de dominio no usados** — `Metric` y `Prediction` definidos pero ignorados | DDD parcial | Bajo |

### 18.3 Código — CALIDAD

| # | Hallazgo | Ubicación |
|---|---------|----------|
| 11 | **`SmartDict`/`UIColors` definidos 3 veces** — 60 líneas de código muerto | `core/constants.py` |
| 12 | **Funciones duplicadas** — `clasificar_riesgo_embalse()` × 2, `categorizar_fuente_xm()` × 4, `get_plotly_modules()` × 2 | `interface/pages/` |
| 13 | **ContextManager nunca utilizado** — 200 líneas de código muerto | `whatsapp_bot/orchestrator/context.py` |
| 14 | **`telegram_handler.py` superado** por `telegram_polling.py` | `whatsapp_bot/app/` |
| 15 | **Scripts ARGIS en tests/** — 2,713 líneas de scripts operacionales mal ubicados | `tests/ARGIS/` |
| 16 | **Tests falsos en tests/** — 5 scripts diagnóstico nombrados test_* pero no son pytest | `tests/` |
| 17 | **Dos navbars compitiendo** — `header.py` vs `layout.py` | `interface/components/` |
| 18 | **Debug writes en producción** — `open('debug_...')` | `generacion_fuentes_unificado.py` |
| 19 | **Bare `except:` clauses** — en 5+ archivos | Multiple |
| 20 | **Logs con referencia a SQLite** cuando el sistema usa PostgreSQL | `xm_service.py` |

### 18.4 Recomendaciones Priorizadas

**Fase 1 — Inmediato (Seguridad)**
1. Agregar `Depends(get_api_key)` a endpoints WhatsApp
2. Reemplazar string interpolation SQL con queries parametrizadas
3. Mover credenciales hardcodeadas a variables de entorno

**Fase 2 — Corto Plazo (Deuda Técnica)**
4. Descomponer `generacion_hidraulica_hidrologia.py` usando el plan en `hidrologia/`
5. Unificar `connection.py` y `manager.py` en una sola ruta de conexión
6. Migrar `etl_transmision.py` a PostgreSQL
7. Mover `tests/ARGIS/` a `scripts/arcgis/`
8. Estandarizar DI en todas las rutas API

**Fase 3 — Medio Plazo (Calidad)**
9. Limpiar duplicaciones en `constants.py`, páginas interface
10. Integrar `ContextManager` al bot o eliminarlo
11. Deprecar `telegram_handler.py`
12. Aumentar cobertura de tests (objetivo: 50%+ en servicios)
13. Unificar navbar: elegir `header.py` o `layout.py`

---

## 19. Métricas del Proyecto {#19-metricas-del-proyecto}

### 19.1 Tamaño de Código

| Métrica | Valor |
|---------|------|
| Archivos Python (excluyendo venv) | ~190 |
| Líneas de código Python estimadas | ~65,000 |
| Archivos CSS/JS | 12 |
| Archivos SQL | 4 |
| Archivos de configuración | 10 |
| Documentación Markdown | 13 archivos, 3.4M |

### 19.2 Complejidad por Capa

| Capa | Archivos | Líneas | Archivo más grande |
|------|---------|--------|-------------------|
| Domain Services | 24 | 13,963 | `orchestrator_service.py` (4,197) |
| Interface Pages | 12 | 19,354 | `generacion_hidraulica_hidrologia.py` (7,319) |
| API Routes | 12 | ~2,600 | `predictions.py` (~380) |
| ETL | 8 | ~2,800 | `etl_todas_metricas_xm.py` |
| Scripts | 32 | ~8,000 | `train_predictions_sector_energetico.py` (4,019) |
| WhatsApp Bot | 19 | ~5,400 | `telegram_polling.py` (1,745) |
| Infrastructure | 17 | ~2,500 | `ideam_service.py` (348) |
| Core | 8 | 1,621 | `config.py` (528) |
| Tests | 20 | ~2,800 | `test_auditoria_datos_orquestador.py` (348) |

### 19.3 Salud del Sistema

| Indicador | Estado | Detalles |
|-----------|--------|---------|
| **Servicios activos** | ✅ | dashboard-mme, api-mme, mlflow |
| **Base de datos** | ✅ | PostgreSQL ~63.7M filas |
| **ETL automatizado** | ✅ | 9 cron jobs + Celery Beat |
| **API disponibilidad** | ✅ | Monitor cada 5min + auto-restart |
| **Backups** | ✅ | Semanales automáticos |
| **Cobertura tests** | 🔴 | <15% estimada |
| **Deuda técnica** | 🟡 | 20 hallazgos documentados |
| **Seguridad** | 🟡 | 4 vulnerabilidades identificadas |

---

*Informe generado mediante inspección recursiva de todos los archivos del proyecto. Fecha de generación: 2026-03-01.*
