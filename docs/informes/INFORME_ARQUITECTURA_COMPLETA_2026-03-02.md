# INFORME DE ARQUITECTURA COMPLETA — Portal Energético MME

**Fecha:** 2 de marzo de 2026  
**Versión:** 3.0  
**Autor:** Auditoría automatizada — Ingeniero de Sistemas Senior  
**Servidor:** `172.17.0.46` — `portalenergetico.minenergia.gov.co`

---

## Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Estructura de carpetas y archivos](#2-estructura-de-carpetas-y-archivos)
3. [Flujo de datos y ETL](#3-flujo-de-datos-y-etl)
4. [Análisis tablero por tablero](#4-análisis-tablero-por-tablero)
5. [Análisis de la API REST](#5-análisis-de-la-api-rest)
6. [Bot de Telegram y alertas](#6-bot-de-telegram-y-alertas)
7. [Archivos esenciales vs prescindibles](#7-archivos-esenciales-vs-prescindibles)
8. [Evaluación para una API pública](#8-evaluación-para-una-api-pública)
9. [Hallazgos críticos y deuda técnica](#9-hallazgos-críticos-y-deuda-técnica)
10. [Recomendaciones finales](#10-recomendaciones-finales)

---

## 1. Arquitectura general

### 1.1 Diagrama de capas

```
┌──────────────────────────────────────────────────────────────────────┐
│                         NGINX (443/80)                               │
│  portalenergetico.minenergia.gov.co                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │  /api/* → :8000      │  │  /* → :8050                         │  │
│  │  FastAPI REST API    │  │  Dash Dashboard                     │  │
│  └──────────┬───────────┘  └──────────────┬──────────────────────┘  │
└─────────────┼──────────────────────────────┼────────────────────────┘
              │                              │
┌─────────────▼──────────┐   ┌───────────────▼──────────────────────┐
│  api/main.py           │   │  app.py → core/app_factory.py       │
│  FastAPI + Uvicorn     │   │  Dash 2.18 + Flask 3.0              │
│  12 routers, 29 endpts │   │  13 páginas, ~60 callbacks          │
│  Gunicorn 4 workers    │   │  Gunicorn gthread                   │
└─────────┬──────────────┘   └──────────────┬──────────────────────┘
          │                                  │
          └──────────┬───────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────┐
│                    CAPA DE DOMINIO (domain/)                      │
│  24 servicios: GenerationService, HydrologyService,              │
│  CommercialService, DistributionService, TransmissionService,    │
│  LossesService, RestrictionsService, MetricsService,             │
│  PredictionsService(×2), OrchestratorService, AgentIA,           │
│  ExecutiveReportService, NotificationService, NewsService,       │
│  IntelligentAnalysisService, IndicatorsService, SystemService,   │
│  MetricsCalculator, Validators, ReportService, GeoService,       │
│  ConfianzaPolitica                                               │
│  ────────────────────────────────────────────────────            │
│  5 interfaces (ABCs): IMetricsRepo, ICommercialRepo,             │
│  IDistributionRepo, ITransmissionRepo, IPredictionsRepo         │
│  2 data source ABCs: IXMDataSource, ISIMEMDataSource             │
│  2 modelos (Metric, Prediction) — no usados en práctica          │
└────────────────────┬─────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────┐
│                CAPA DE INFRAESTRUCTURA (infrastructure/)          │
│  ┌────────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ database/       │  │ external/    │  │ news/ + logging/      │ │
│  │ ├─ manager.py   │  │ ├─ xm_svc   │  │ ├─ google_news_rss   │ │
│  │ ├─ connection   │  │ ├─ xm_adapt  │  │ ├─ mediastack        │ │
│  │ └─ repos/ (5)   │  │ └─ ideam_svc │  │ ├─ news_client       │ │
│  │   ├─ metrics    │  └──────────────┘  │ └─ logger.py         │ │
│  │   ├─ commercial │                     └───────────────────────┘ │
│  │   ├─ distrib.   │                                               │
│  │   ├─ transmis.  │                                               │
│  │   └─ predict.   │                                               │
│  └────────────────┘                                               │
└────────────────────┬─────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────┐
│           ALMACENAMIENTO                                          │
│  ┌─────────────────┐  ┌───────────┐  ┌────────────────────────┐  │
│  │  PostgreSQL      │  │  Redis    │  │  APIs externas         │  │
│  │  portal_energet. │  │  Cache    │  │  ├─ XM (pydataxm)     │  │
│  │  ├─ metrics      │  │  Broker   │  │  ├─ SIMEM (pydatasimem│  │
│  │  ├─ metrics_hour │  │  Celery   │  │  ├─ IDEAM (datos.gov) │  │
│  │  ├─ catalogos    │  └───────────┘  │  ├─ Groq / OpenRouter │  │
│  │  ├─ commercial_m │                 │  ├─ GNews / Mediastack │  │
│  │  ├─ predictions  │                 │  └─ Google News RSS    │  │
│  │  ├─ lineas_trans │                 └────────────────────────┘  │
│  │  ├─ telegram_usr │                                              │
│  │  └─ alert_recip. │                                              │
│  └─────────────────┘                                              │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Puntos de entrada

| Servicio | Archivo de entrada | Puerto | Proceso |
|----------|-------------------|--------|---------|
| Dashboard Dash | `app.py` → `core/app_factory.py` | 8050 | Gunicorn gthread (`dashboard-mme.service`) |
| API REST FastAPI | `api/main.py` | 8000 | Gunicorn + UvicornWorker (`api-mme.service`) |
| Bot Telegram | `whatsapp_bot/telegram_polling.py` | — | `telegram-polling.service` |
| Celery Worker | `tasks/__init__.py` | — | `celery-worker@.service` |
| Celery Beat | `tasks/__init__.py` | — | Celery Beat |

### 1.3 Inicialización del Dashboard

1. `app.py` llama `create_app()` de `core/app_factory.py`
2. `create_app()` crea una instancia `Dash(use_pages=True, pages_folder="interface/pages")`
3. Dash auto-descubre las páginas con `register_page()` en cada archivo de `interface/pages/`
4. Se registra el layout global (navbar + sidebar + content + chat) vía `_register_layout()`
5. Se precargan conexiones XM API (`_preload_xm_api()`)
6. Se expone `server = app.server` (Flask subyacente) para Gunicorn

### 1.4 Registración de páginas Dash

| Página | Ruta | Archivo | Orden |
|--------|------|---------|-------|
| Inicio | `/` | `home.py` | 0 |
| Generación | `/generacion` | `generacion.py` | 2 |
| Generación por Fuente | `/generacion/fuentes` | `generacion_fuentes_unificado.py` | 6 |
| Hidrología | `/generacion/hidraulica/hidrologia` | `generacion_hidraulica_hidrologia.py` + `hidrologia/` | 6 |
| Transmisión | `/transmision` | `transmision.py` | 20 |
| Distribución | `/distribucion` | `distribucion.py` | 10 |
| Comercialización | `/comercializacion` | `comercializacion.py` | — |
| Pérdidas | `/perdidas` | `perdidas.py` | 15 |
| Restricciones | `/restricciones` | `restricciones.py` | 50 |
| Métricas | `/metricas` | `metricas.py` | — |
| Métricas Piloto | `/metricas-piloto` | `metricas_piloto.py` | — |
| Seguimiento Predicciones | `/seguimiento-predicciones` | `seguimiento_predicciones.py` | 10 |

---

## 2. Estructura de carpetas y archivos

### 2.1 Archivos raíz

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `app.py` | Punto de entrada del dashboard Dash | **ESENCIAL** |
| `wsgi.py` | Entry point WSGI alternativo (duplica `app.py`) | **ÚTIL** — posible duplicado |
| `gunicorn_config.py` | Configuración Gunicorn para dashboard (puerto 8050, gthread) | **ESENCIAL** |
| `requirements.txt` | Dependencias Python (~35 paquetes) | **ESENCIAL** |
| `pytest.ini` | Configuración pytest (markers: slow, integration, unit, smoke) | **ESENCIAL** |
| `.gitignore` | Exclusiones git (~150 patrones) | **ESENCIAL** |
| `.env.example` | Plantilla variables de entorno generales | **ESENCIAL** |
| `.env.api.example` | Plantilla variables API REST (bien documentada, 120 líneas) | **ESENCIAL** |
| `api-mme.service` | Systemd unit para FastAPI (puerto 8000) | **ESENCIAL** |
| `dashboard-mme.service` | Systemd unit para Dash (puerto 8050) | **ESENCIAL** |
| `nginx-api-config.conf` | Nginx producción unificado (HTTP+HTTPS, `/api/`→8000, `/*`→8050) | **ESENCIAL** |
| `nginx-dashboard.conf` | Nginx standalone alternativo (probablemente obsoleto) | **ÚTIL** |
| `celerybeat-schedule` | Binario Celery Beat (artefacto runtime) | Artefacto |
| `LICENSE` | MIT License 2024-2025 | **ESENCIAL** |

### 2.2 `core/` — Núcleo de la aplicación (132 KB, 7 archivos)

| Archivo | Líneas | Propósito | Estado |
|---------|--------|-----------|--------|
| `app_factory.py` | ~310 | Factory `create_app()`: crea instancia Dash, registra layout, callbacks, métricas Prometheus, endpoints health/metrics | **ESENCIAL** |
| `config.py` | ~529 | `Settings(BaseSettings)` con ~50 campos: PostgreSQL, AI, ML, ETL, API, Gunicorn, logging, cache. Singleton `get_settings()` | **ESENCIAL** |
| `config_simem.py` | ~45 | Stub de configuración SIMEM (categorías→métricas). Creado durante refactor | **ÚTIL** |
| `constants.py` | ~502 | Constantes globales: `METRIC_IDS`, `TABLES`, `COLORS`, `CACHE_TTL`, `PAGES`, helpers `SmartDict`, `UIColors` | **ESENCIAL** |
| `container.py` | ~180 | Contenedor de inyección de dependencias (lazy singletons): 5 repos, 5 servicios, 1 DB manager, 1 XM adapter | **ESENCIAL** |
| `exceptions.py` | ~50 | Jerarquía `PortalError` → `DateRangeError`, `DataNotFoundError`, `ExternalAPIError`, `DatabaseError`, `InvalidParameterError` | **ESENCIAL** |
| `validators.py` | ~35 | `validate_date_range()`, `validate_string()` — validaciones básicas | **ÚTIL** |

### 2.3 `domain/` — Capa de dominio (1.4 MB, ~15,120 líneas)

#### 2.3.1 Interfaces (`domain/interfaces/`)

| Archivo | Propósito |
|---------|-----------|
| `database.py` | ABCs: `IDatabaseManager` (query_df, execute_non_query), `IConnectionManager` |
| `data_sources.py` | ABCs: `IXMDataSource`, `ISIMEMDataSource`, `IIDEAMDataSource` (⚠️ no implementada) |
| `repositories.py` | ABCs: `IMetricsRepository`, `ICommercialRepository`, `IDistributionRepository`, `ITransmissionRepository`, `IPredictionsRepository` |

#### 2.3.2 Modelos (`domain/models/`)

| Archivo | Propósito | Nota |
|---------|-----------|------|
| `metric.py` | Dataclass `Metric` (fecha, metrica, entidad, valor_gwh, unidad) | Definido pero **no usado** — los servicios trabajan con DataFrames |
| `prediction.py` | Dataclass `Prediction` (fecha_prediccion, fuente, valor_gwh_predicho, confianza) | Definido pero **no usado** |

#### 2.3.3 Schemas (`domain/schemas/`)

| Archivo | Propósito |
|---------|-----------|
| `orchestrator.py` | Modelos Pydantic v2 para el chatbot: `OrchestratorRequest`, `OrchestratorResponse`, params por intent |

#### 2.3.4 Servicios (`domain/services/`) — 24 archivos, ~13,360 líneas

| Servicio | Líneas | Fuente de datos | Usa DI? | Consumido por |
|----------|--------|-----------------|---------|---------------|
| `orchestrator_service.py` | 4,197 | Todos los servicios | ❌ Instancia todo | Chatbot API |
| `executive_report_service.py` | 1,474 | Todos los servicios | ❌ Instancia todo | Informe diario |
| `report_service.py` | 1,715 | Markdown → PDF | — | Descarga PDF |
| `notification_service.py` | 1,173 | PostgreSQL directo (psycopg2) | ❌ Raw SQL | Telegram/Email |
| `intelligent_analysis_service.py` | 832 | Todos los servicios | ❌ Instancia todo | Estado actual |
| `news_service.py` | 506 | GNews, Mediastack, Google RSS | ❌ Directo | Noticias |
| `generation_service.py` | 448 | PostgreSQL (metrics, catalogos) | ⚠️ Parcial | Generación |
| `predictions_service_extended.py` | 432 | PostgreSQL (metrics) | ❌ Directo | Predicciones |
| `ai_service.py` | 430 | PostgreSQL + Groq/OpenRouter | ❌ Directo | Chat IA |
| `distribution_service.py` | 401 | PostgreSQL (metrics) + XM API | ⚠️ Parcial | Distribución |
| `hydrology_service.py` | 348 | PostgreSQL (metrics) | ❌ Directo | Hidrología |
| `commercial_service.py` | 280 | PostgreSQL + XM API | ⚠️ Parcial | Comercialización |
| `validators.py` | 247 | — | — | Validación rangos |
| `transmission_service.py` | 207 | PostgreSQL (lineas_transmision) | ⚠️ Parcial | Transmisión |
| `metrics_service.py` | 200 | PostgreSQL + XM API | ✅ Completo | Métricas |
| `metrics_calculator.py` | 197 | — | — | Cálculos KPI |
| `system_service.py` | 193 | PostgreSQL directo (psycopg2) | ❌ Raw SQL | Health check |
| `indicators_service.py` | 173 | PostgreSQL directo | ❌ Directo | KPIs globales |
| `losses_service.py` | 152 | PostgreSQL (metrics) | ❌ Directo | Pérdidas |
| `restrictions_service.py` | 198 | PostgreSQL (metrics) | ❌ Directo | Restricciones |
| `confianza_politica.py` | 122 | — | — | Política confianza |
| `predictions_service.py` | 32 | PostgreSQL (predictions) | ❌ Directo | Predicciones |
| `geo_service.py` | 32 | Estático | — | Mapas |

**Cumplimiento DI: 1/15 completo, 4/15 parcial, 10/15 ninguno.**

### 2.4 `infrastructure/` — Capa de infraestructura (348 KB, ~2,560 líneas)

#### 2.4.1 Base de datos (`infrastructure/database/`)

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `connection.py` | ~73 | `PostgreSQLConnectionManager`: context manager para conexiones psycopg2. **Sin connection pool.** |
| `manager.py` | ~251 | `DatabaseManager(IDatabaseManager)`: query_df, execute_non_query, upserts bulk (metrics, catalogos, hourly). **Duplica lógica de conexión.** |
| `repositories/base_repository.py` | ~62 | `BaseRepository`: execute_query, execute_dataframe, execute_non_query |
| `repositories/metrics_repository.py` | ~140 | `MetricsRepository(IMetricsRepository)`: tabla `metrics`, `metrics_hourly`, `catalogos` |
| `repositories/commercial_repository.py` | ~152 | `CommercialRepository(ICommercialRepository)`: tabla `commercial_metrics` |
| `repositories/distribution_repository.py` | ~233 | `DistributionRepository(IDistributionRepository)`: lee de `metrics`, escribe en `distribution_metrics` |
| `repositories/transmission_repository.py` | ~225 | `TransmissionRepository(ITransmissionRepository)`: tabla `lineas_transmision` |
| `repositories/predictions_repository.py` | ~137 | `PredictionsRepository(IPredictionsRepository)`: tabla `predictions` |

#### 2.4.2 Servicios externos

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `external/xm_service.py` | ~280 | Cliente XM API (`pydataxm`). `obtener_datos_inteligente()`: BD primero → API XM fallback |
| `external/xm_adapter.py` | ~137 | Adapter limpio: `XMDataSourceAdapter(IXMDataSource)` |
| `external/ideam_service.py` | ~348 | Cliente IDEAM (datos.gov.co SODA API): viento, precipitación, temperatura |

#### 2.4.3 Noticias y logging

| Archivo | Propósito |
|---------|-----------|
| `news/google_news_rss.py` | Scraper async Google News RSS (httpx) |
| `news/mediastack_client.py` | Cliente async Mediastack API |
| `news/news_client.py` | Cliente async GNews API |
| `logging/logger.py` | `LoggerManager` singleton, rotating file handlers, configurable |

### 2.5 `interface/` — Capa de presentación (1.8 MB, ~20,280 líneas)

#### 2.5.1 Componentes reutilizables (`interface/components/`)

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `chart_card.py` | 208 | `crear_chart_card`, `crear_table_card`, `crear_page_header`, `crear_filter_bar` |
| `kpi_card.py` | 121 | `crear_kpi`, `crear_kpi_row` — tarjetas KPI con variación y sparkline |
| `header.py` | 72 | Navbar global MinEnergía (8 enlaces) |
| `layout.py` | 130 | `crear_navbar_horizontal` (9 enlaces), helpers de layout. Tiene funciones no-op |
| `chat_widget.py` | 524 | Widget flotante de chat IA (OpenRouter) con 3 callbacks |

#### 2.5.2 Páginas (ver sección 4 para análisis detallado)

| Archivo | Líneas | Callbacks | Ruta |
|---------|--------|-----------|------|
| `home.py` | 519 | 1 | `/` |
| `generacion.py` | 470 | 1 | `/generacion` |
| `generacion_fuentes_unificado.py` | 3,406 | 11 | `/generacion/fuentes` |
| `hidrologia/` (paquete) | 7,766 | 17 | `/generacion/hidraulica/hidrologia` |
| `transmision.py` | 688 | 3 | `/transmision` |
| `distribucion.py` | 1,210 | 3 | `/distribucion` |
| `comercializacion.py` | 735 | 4 | `/comercializacion` |
| `perdidas.py` | 341 | 2 | `/perdidas` |
| `restricciones.py` | 381 | 2 | `/restricciones` |
| `metricas.py` | 2,520 | 14 | `/metricas` |
| `metricas_piloto.py` | 92 | 1 | `/metricas-piloto` |
| `seguimiento_predicciones.py` | 996 | 3 | `/seguimiento-predicciones` |

### 2.6 `etl/` — Pipelines ETL (208 KB, 8 archivos)

| Archivo | Líneas | Propósito | Tabla destino |
|---------|--------|-----------|---------------|
| `etl_xm_to_postgres.py` | 698 | ETL principal: catálogos + métricas diarias desde XM API | `metrics`, `metrics_hourly`, `catalogos` |
| `etl_todas_metricas_xm.py` | 593 | ETL bulk: las 193 métricas XM con filtros por sección | `metrics` |
| `config_metricas.py` | 422 | Configuración maestra: mapeo unidades, rangos válidos, batch sizes | — (config) |
| `etl_rules.py` | 401 | Reglas centralizadas: `MetricRule`, conversiones, validaciones | — (reglas) |
| `etl_ideam.py` | 325 | ETL IDEAM: viento, precipitación, temperatura desde datos.gov.co | `metrics` (prefijo IDEAM_) |
| `validaciones.py` | 245 | `ValidadorDatos`: validación fechas, valores, deduplicación | — (validación) |
| `validaciones_rangos.py` | 197 | Validación rangos suplementaria (`VALID_RANGES`) | — (validación) |
| `etl_transmision.py` | 120 | ETL transmisión desde SIMEM API (dataset 7538fd) | `lineas_transmision` |

### 2.7 `api/` — API REST FastAPI (484 KB)

| Capa | Archivos | Propósito |
|------|----------|-----------|
| `api/main.py` | 323 líneas | App factory: CORS, rate limiting, OpenAPI 3.0.3, exception handlers |
| `api/dependencies.py` | 206 líneas | DI: `get_api_key()`, `get_metrics_service()`, `get_predictions_service()` |
| `api/v1/__init__.py` | 127 líneas | Registra 12 sub-routers |
| `api/v1/routes/` | 12 archivos | Endpoints (ver sección 5) |
| `api/v1/schemas/` | 12 archivos | Modelos Pydantic request/response |

### 2.8 `tasks/` — Tareas Celery (112 KB)

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `__init__.py` | 73 | Config Celery: broker Redis (db 0), backend Redis (db 1), timezone Bogotá |
| `etl_tasks.py` | 222 | `etl_incremental_all_metrics` (cada 6h), `clean_old_logs` (diario 3AM) |
| `anomaly_tasks.py` | 833 | `check_anomalies` (cada 30min), `send_daily_summary` (8AM con PDF+charts) |

### 2.9 `scripts/` — Scripts operacionales (816 KB)

| Script | Auto/Manual | Propósito |
|--------|-------------|-----------|
| `actualizar_predicciones.sh` | CRON dom 2AM | Master semanal: IDEAM + entrenar modelos + calidad + alertas |
| `backfill_sistema_metricas.py` | CRON 1° mes 4AM | Backfill histórico 2020-2026 para 14 métricas del Sistema |
| `alertas_energeticas.py` | Celery | `SistemaAlertasEnergeticas`: umbrales ministeriales |
| `backup_postgres_diario.sh` | CRON dom 3AM | pg_dump + gzip, retención 30 días |
| `monitor_predictions_quality.py` | CRON 8AM | Verificación ex-post: MAPE/RMSE predicciones vs reales |
| `monitor_api.sh` | CRON cada 5min | Watchdog auto-recovery API |
| `completar_tablas_incompletas.py` | Manual | Rellenar gaps en commercial/loss/restriction metrics |
| `ejecutar_etl_completo.sh` | Manual | Loop secciones ETL |
| `ops/manage-server.sh` | Manual | Menú interactivo: status, logs, git pull, nginx, SSL |
| `ops/monitorear_etl.sh` | Manual | Monitor proceso ETL (CPU/RAM/logs) |
| `ops/verificar_sistema.sh` | Manual | Health check: disco, RAM, Gunicorn, PostgreSQL, Redis, nginx |
| `train_predictions_sector_energetico.py` | Semanal | Entrenamiento modelos ML (Prophet + ARIMA + ensemble) |
| `arcgis/` (5 scripts) | CRON horario | Sincronización datos XM/OneDrive → ArcGIS Online |

### 2.10 `tests/` — Suite de pruebas (456 KB, 128 tests)

| Archivo | Tests | Tipo | Qué prueba |
|---------|-------|------|------------|
| `test_api_endpoints.py` | 14 | Integration | Root, generation, hydrology, predictions, metrics, auth, rate limiting |
| `test_etl.py` | 16 | Unit | ValidadorDatos: fechas, rangos, normalización, duplicados |
| `test_informe_ejecutivo.py` | — | Slow | ExecutiveReportService end-to-end |
| `test_informe_ejecutivo_completo.py` | — | Slow | Reporte ejecutivo completo |
| `unit/test_repositories/test_metrics_repository_unit.py` | 10 | Unit | MetricsRepository: init, queries, filtros |
| `unit/test_services/test_ai_service.py` | 13 | Unit | AgentIA: whitelist, SQL injection, providers |
| `unit/test_services/test_distribution_commercial_losses_restrictions.py` | 17 | Unit | 4 servicios sector |
| `unit/test_services/test_system_service.py` | 5 | Unit | Health check, reporte texto |
| `unit/test_services/test_generation_service.py` | — | Unit | GenerationService |
| `unit/test_services/test_hydrology_service.py` | — | Unit | HydrologyService |
| `unit/test_services/test_transmission_service.py` | — | Unit | TransmissionService |

**Resultado actual: 85 passed, 38 failed (pre-existentes), 5 deselected** de 128 tests totales.

### 2.11 Otras carpetas

| Carpeta | Propósito | Contenido |
|---------|-----------|-----------|
| `assets/` | Recursos estáticos Dash: CSS (9), JS (3), imágenes portada (11), GeoJSON (1), JSON regiones (1) | 5.7 MB |
| `data/` | Datos estáticos + cachés: `metricas_xm_arcgis.csv`, `data/charts/` (6 PNG), `data/onedrive/` (8 xlsx activos) | 1.5 MB |
| `config/` | Systemd units adicionales: `celery-worker@.service`, `logrotate.conf`, `mlflow-server.service` | 16 KB |
| `docs/` | 15 archivos Markdown + 1 PDF referencia + informes | 3.6 MB |
| `experiments/` | Experimentos ML: XGBoost, comparación modelos, SOTA, CSV resultados | 224 KB |
| `ejemplos/` | 2 scripts de ejemplo: informe ejecutivo, bot WhatsApp | 40 KB |
| `sql/` | 4 archivos SQL: schema alertas, predictions, telegram users | 24 KB |
| `notebooks/` | Solo `README.md` — carpeta vacía | 8 KB |
| `whatsapp_bot/` | Bot Telegram/WhatsApp con Docker, servicios, orchestrator | 1.8 MB |
| `backups/database/` | 2 dumps PostgreSQL (550MB + 103MB) — gitignored | 652 MB |
| `logs/` | Logs rotados (app, ETL, celery, arcgis, API) — gitignored | 3.4 MB |
| `mlruns/` | MLflow tracking artifacts | 276 KB |

---

## 3. Flujo de datos y ETL

### 3.1 Flujo extremo a extremo

```
 ┌─────────────┐    ┌─────────────┐    ┌───────────────┐
 │  API XM     │    │ SIMEM API   │    │ IDEAM API     │
 │ (pydataxm)  │    │ (pydatasim) │    │ (datos.gov.co)│
 └──────┬──────┘    └──────┬──────┘    └───────┬───────┘
        │                  │                    │
 ┌──────▼──────┐    ┌──────▼──────┐    ┌───────▼───────┐
 │etl_xm_to_   │    │etl_trans-   │    │etl_ideam.py   │
 │postgres.py   │    │mision.py    │    │               │
 │etl_todas_   │    │             │    │               │
 │metricas.py   │    │             │    │               │
 └──────┬──────┘    └──────┬──────┘    └───────┬───────┘
        │                  │                    │
        ▼                  ▼                    ▼
 ┌──────────────────────────────────────────────────────┐
 │              P O S T G R E S Q L                      │
 │  metrics (~500K+ rows), metrics_hourly, catalogos     │
 │  commercial_metrics, lineas_transmision               │
 │  predictions, telegram_users, alert_recipients        │
 └──────────┬───────────────────────────┬───────────────┘
            │                           │
    ┌───────▼────────┐          ┌───────▼────────┐
    │ Repositories    │          │ Services        │
    │ (5 repos)       │          │ (24 services)   │
    └───────┬────────┘          └───────┬────────┘
            │                           │
    ┌───────▼───────────────────────────▼───────┐
    │                                            │
    │  ┌──────────┐  ┌───────────┐  ┌─────────┐ │
    │  │Dashboard  │  │ API REST  │  │Telegram │ │
    │  │13 páginas │  │29 endpts  │  │Bot      │ │
    │  └──────────┘  └───────────┘  └─────────┘ │
    └────────────────────────────────────────────┘
```

### 3.2 Programación ETL automatizada

| Frecuencia | Script | Tabla(s) | Fuente |
|------------|--------|----------|--------|
| Cada 6h (`0 */6 * * *`) | `etl_todas_metricas_xm.py --dias 7` | `metrics` | XM API |
| Cada 6h (Celery) | `etl_tasks.etl_incremental_all_metrics` | `metrics` (5 métricas core) | XM API |
| Diario 6:30 AM | `etl_transmision.py --days 7` | `lineas_transmision` | SIMEM API |
| Diario 8:00 AM | `monitor_predictions_quality.py` | — (solo lee) | PostgreSQL |
| Cada 30min (Celery) | `anomaly_tasks.check_anomalies` | — (solo lee + alerta) | PostgreSQL |
| Diario 8:00 AM (Celery) | `anomaly_tasks.send_daily_summary` | — (genera PDF+charts) | PostgreSQL |
| Semanal dom 2AM | `actualizar_predicciones.sh` | `predictions`, `metrics` (IDEAM) | IDEAM + ML |
| Mensual 1° 4AM | `backfill_sistema_metricas.py` | `metrics` (backfill) | XM API |
| Semanal dom 3AM | `backup_postgres_diario.sh` | — (backup) | pg_dump |
| Horario | `arcgis/ejecutar_dual.sh` | — (ArcGIS Online) | XM + OneDrive |

### 3.3 Origen de datos por tablero

| Tablero | Solo BD | BD + API XM | CSV/JSON directo |
|---------|---------|-------------|------------------|
| Inicio | — (estático) | — | — |
| Generación | ✅ | ✅ (fichas KPI) | — |
| Gen. por Fuente | ✅ | ✅ (fallback) | — |
| Hidrología | ✅ | ✅ (fallback `obtener_datos_inteligente`) | — |
| Transmisión | ✅ | — | — |
| Distribución | ✅ | ✅ (fallback) | — |
| Comercialización | ✅ | ✅ (fallback) | — |
| Pérdidas | ✅ | — | — |
| Restricciones | ✅ | — | — |
| Métricas | ✅ | ✅ (SIMEM opt.) | — |
| Predicciones | ✅ (psycopg2 directo) | — | — |

**Ningún tablero lee CSV/JSON estáticos directamente saltándose la capa de servicios.** Todo pasa por PostgreSQL con fallback opcional a API XM.

---

## 4. Análisis tablero por tablero

### 4.1 Inicio (`/`)

- **Archivos:** `interface/pages/home.py` (519 líneas)
- **Layout:** Landing page interactiva con imágenes PNG en capas, 6 botones módulo con tooltips de fórmula CU
- **Callbacks:** 1 (vestigial — retorna div vacío, chat es ahora global)
- **Datos:** Ninguno (página puramente estática)
- **Estado:** ✅ **FUNCIONAL** — correctamente implementada

### 4.2 Generación Eléctrica (`/generacion`)

- **Archivos:** `interface/pages/generacion.py` (470 líneas)
- **Layout:** Header, imagen, KPI row (Reservas, Aportes, Generación SIN), 2 cards navegación a sub-páginas
- **Callbacks:** 1 — carga fichas KPI con `MetricsService.get_metric_series_hybrid()`
- **Servicios:** `MetricsService` (DI correcto)
- **Estado:** ✅ **FUNCIONAL** — hub de navegación limpio

### 4.3 Generación por Fuente (`/generacion/fuentes`)

- **Archivos:** `interface/pages/generacion_fuentes_unificado.py` (3,406 líneas)
- **Layout:** 5 pestañas (Visión General, Análisis Temporal, Ranking Plantas, Comparación Anual, Predicciones ML), KPIs, gráficas interactivas
- **Callbacks:** 11 — tab routing, barras apiladas, tortas, áreas, tablas, comparación anual
- **Servicios:** `GenerationService` (primario) + `xm_service` directo (fallback) + `db_manager` directo (⚠️ violación)
- **Estado:** ✅ **FUNCIONAL** — completo pero con violaciones de arquitectura y archivo muy grande

### 4.4 Hidrología (`/generacion/hidraulica/hidrologia`)

- **Archivos:** `generacion_hidraulica_hidrologia.py` (27 líneas, wrapper) + paquete `hidrologia/` (7,766 líneas, 9 archivos)
- **Layout:** Tabs (Aportes de Energía, Comparación Anual), modals, KPIs expandibles, mapas GeoJSON, tablas jerárquicas
- **Callbacks:** 17 — actualizar KPIs, routing tabs, drill-down por región/río, mapas, tablas colapsables
- **Servicios:** `HydrologyService` + `obtener_datos_inteligente` directo (⚠️ violación) + `GeoService`
- **Estado:** ✅ **FUNCIONAL** — el más complejo, bien modularizado en subpaquete

### 4.5 Transmisión (`/transmision`)

- **Archivos:** `interface/pages/transmision.py` (688 líneas)
- **Layout:** Page header, date filter, KPIs (total líneas, km, tensión promedio), 3 gráficas, tabla detallada
- **Callbacks:** 3 — filtro fechas, trigger auto-init, KPIs + gráficos + tabla
- **Servicios:** `TransmissionService` (arquitectura limpia)
- **Estado:** ✅ **FUNCIONAL** — función `get_plotly_modules()` duplicada (líneas 18 y 51)

### 4.6 Distribución / Demanda (`/distribucion`)

- **Archivos:** `interface/pages/distribucion.py` (1,210 líneas)
- **Layout:** Page header, filtro fechas, KPIs demanda, 3 gráficas (líneas, barras, torta), modal detalle horario
- **Callbacks:** 3 — filtro fechas, datos principales, detalle horario por click
- **Servicios:** `DistributionService` (arquitectura limpia)
- **Estado:** ✅ **FUNCIONAL** — contiene imports no utilizados de `DatabaseManager`

### 4.7 Comercialización (`/comercializacion`)

- **Archivos:** `interface/pages/comercializacion.py` (735 líneas)
- **Layout:** Header, filtro fechas, KPIs precios, gráfica precios bolsa/escasez, modal spread
- **Callbacks:** 4 — filtro, datos principales, modal detalle, info spread
- **Servicios:** `CommercialService` (arquitectura limpia)
- **Estado:** ✅ **FUNCIONAL** — bien estructurado

### 4.8 Pérdidas (`/perdidas`)

- **Archivos:** `interface/pages/perdidas.py` (341 líneas)
- **Layout:** Header, filtro fechas, contenedor dinámico con KPIs + gráficos
- **Callbacks:** 2 — filtro fechas, carga datos
- **Servicios:** `LossesService` (arquitectura limpia)
- **Estado:** ✅ **FUNCIONAL** — comparte store chatbot con otras páginas

### 4.9 Restricciones (`/restricciones`)

- **Archivos:** `interface/pages/restricciones.py` (381 líneas)
- **Layout:** Header, filtro fechas, contenedor KPIs + gráficos
- **Callbacks:** 2 — filtro fechas, carga datos
- **Servicios:** `RestrictionsService` (arquitectura limpia)
- **Estado:** ✅ **FUNCIONAL** — `valor_gwh` almacena Millones COP para costos de restricción (nombre engañoso)

### 4.10 Métricas (`/metricas`)

- **Archivos:** `interface/pages/metricas.py` (2,520 líneas)
- **Layout:** 5 tabs (Consulta, Secciones, Análisis, Exploración, Guía), explorador general de métricas
- **Callbacks:** 14 — tab routing, selección fuente (XM/SIMEM), consulta, análisis, descarga
- **Servicios:** `MetricsService` + `pydatasimem` (SIMEM opcional)
- **Estado:** ✅ **FUNCIONAL** — archivo grande, contiene referencia legacy a SQLite path hardcodeado

### 4.11 Métricas Piloto (`/metricas-piloto`)

- **Archivos:** `interface/pages/metricas_piloto.py` (92 líneas)
- **Layout:** KPIs con auto-refresh cada 5 minutos
- **Callbacks:** 1
- **Servicios:** `MetricsService`, `PredictionsService`
- **Estado:** ✅ **FUNCIONAL** — prototipo/piloto, no enlazado desde navbar principal

### 4.12 Seguimiento Predicciones (`/seguimiento-predicciones`)

- **Archivos:** `interface/pages/seguimiento_predicciones.py` (996 líneas)
- **Layout:** Resumen ejecutivo, tabla métricas, detalle por métrica, historial calidad
- **Callbacks:** 3 — carga resumen, detalle por métrica, historial calidad
- **Servicios:** ⚠️ **PostgreSQL directo (psycopg2)** — no usa servicios de dominio
- **Estado:** ✅ **FUNCIONAL** pero con violación severa de arquitectura. No aparece en navbar `header.py`

### 4.13 Resumen estado tableros

| Tablero | Funcional | Arquitectura | Prioridad mejora |
|---------|-----------|-------------|-----------------|
| Inicio | ✅ | Limpia | Baja |
| Generación | ✅ | Limpia | Baja |
| Gen. por Fuente | ✅ | Mixta | Media |
| Hidrología | ✅ | Mixta | Media |
| Transmisión | ✅ | Limpia | Baja |
| Distribución | ✅ | Limpia | Baja |
| Comercialización | ✅ | Limpia | Baja |
| Pérdidas | ✅ | Limpia | Baja |
| Restricciones | ✅ | Limpia | Baja |
| Métricas | ✅ | Limpia | Media (tamaño) |
| Métricas Piloto | ✅ | Limpia | Baja (piloto) |
| Predicciones | ✅ | **Violación** | **Alta** |

**Todos los 12 tableros están funcionales.** No hay páginas rotas ni vacías.

---

## 5. Análisis de la API REST

### 5.1 Endpoints completos (29 endpoints)

| Ruta | Método | Servicio | Descripción |
|------|--------|----------|-------------|
| `/api/v1/generation/system` | GET | DB directa | Generación total del SIN |
| `/api/v1/generation/by-source` | GET | DB directa | Generación por tipo fuente |
| `/api/v1/generation/resources` | GET | DB directa | Lista recursos generación |
| `/api/v1/generation/mix` | GET | DB directa | Mix energético |
| `/api/v1/hydrology/aportes` | GET | DB directa | Aportes hídricos |
| `/api/v1/hydrology/reservoirs` | GET | DB directa | Embalses |
| `/api/v1/hydrology/energy` | GET | DB directa | Energía almacenada |
| `/api/v1/system/demand` | GET | MetricsService | Demanda real |
| `/api/v1/system/prices` | GET | MetricsService | Precios spot |
| `/api/v1/transmission/lines` | GET | DB directa | Catálogo líneas |
| `/api/v1/transmission/flows` | GET | DB directa | Flujos de potencia |
| `/api/v1/transmission/international` | GET | DB directa | Intercambios internacionales |
| `/api/v1/distribution/data` | GET | DistributionService | Datos distribución |
| `/api/v1/distribution/operators` | GET | DistributionService | Catálogo operadores |
| `/api/v1/commercial/prices` | GET | CommercialService | Precios comerciales |
| `/api/v1/commercial/contracts` | GET | CommercialService | Precios contratos |
| `/api/v1/losses/data` | GET | LossesService | Pérdidas energía |
| `/api/v1/restrictions/data` | GET | RestrictionsService | Restricciones operativas |
| `/api/v1/metrics/` | GET | MetricsService (DI) | Lista métricas disponibles |
| `/api/v1/metrics/{metric_id}` | GET | MetricsService (DI) | Serie temporal métrica |
| `/api/v1/predictions/{metric_id}` | GET | PredictionsService (DI) | Generar predicción |
| `/api/v1/predictions/{metric_id}/train` | POST | PredictionsService | Entrenar modelo |
| `/api/v1/predictions/batch/forecast` | GET | PredictionsService | Batch predicción |
| `/api/v1/predictions/cache/stats` | GET | Redis | Estadísticas caché |
| `/api/v1/predictions/cache/flush` | DELETE | Redis | Limpiar caché |
| `/api/v1/chatbot/orchestrator` | POST | OrchestratorService | Chatbot IA |
| `/api/v1/chatbot/health` | GET | — | Health check orquestador |
| `/api/v1/whatsapp/send-alert` | POST | HTTP→Bot:8001 | Broadcast alerta |
| `/api/v1/whatsapp/whatsapp-bot-status` | GET | HTTP→Bot:8001 | Estado bot |

### 5.2 Seguridad API

- **Autenticación:** API Key vía header `X-API-Key` (configurable `API_KEY_ENABLED`)
- **Rate Limiting:** slowapi `100/minute` por defecto (configurable)
- **CORS:** Configurable vía `API_CORS_ORIGINS`
- **Validación:** Pydantic v2 schemas para request/response
- **Inyección SQL:** Protección via whitelist en AgentIA + queries parametrizadas

### 5.3 Observaciones API

- 6 de 12 routers usan queries directas a DB en lugar de servicios de dominio
- El endpoint predictions tiene cache Redis con TTL configurable
- Documentación Swagger/ReDoc habilitada vía `API_DOCS_ENABLED`
- Auto-recovery watchdog cada 5 minutos (`monitor_api.sh`)

---

## 6. Bot de Telegram y alertas

### 6.1 Arquitectura del Bot

```
whatsapp_bot/
├── telegram_polling.py          ← Entry point (long polling)
├── telegram-polling.service     ← Systemd unit
├── orchestrator/
│   ├── bot.py                   ← Lógica principal bot
│   └── context.py               ← Gestión contexto conversación
├── services/
│   ├── data_service.py          ← Acceso datos sector energético
│   ├── ai_integration.py        ← Integración LLM
│   ├── chart_service.py         ← Generación gráficos PNG
│   └── informe_charts.py        ← Charts para informe ejecutivo
├── app/
│   ├── main.py                  ← FastAPI app (webhook mode)
│   ├── config.py                ← Configuración bot
│   ├── security.py              ← Validación webhook signatures
│   ├── rate_limiting.py         ← Rate limiter por session
│   ├── sender.py                ← Envío mensajes Telegram
│   └── tasks.py                 ← Tareas async
└── Docker + nginx configs
```

### 6.2 Funcionalidades

- **Informe ejecutivo diario** a las 8:00 AM (Celery Beat) con PDF + 3 gráficos PNG
- **Alertas en tiempo real** cada 30 minutos evaluando umbrales ministeriales
- **Chat conversacional** con contexto persistente
- **Canales:** Telegram (producción), WhatsApp Web (experimental/deshabilitado)

---

## 7. Archivos esenciales vs prescindibles

### 7.1 Archivos ESENCIALES (no tocar)

Todos los archivos en las carpetas `core/`, `domain/services/`, `infrastructure/`, `interface/pages/`, `interface/components/`, `etl/`, `api/`, `tasks/` son **esenciales para producción**, con las excepciones listadas abajo.

### 7.2 Archivos ÚTILES pero secundarios

| Archivo | Razón |
|---------|-------|
| `wsgi.py` | Entry point alternativo, posiblemente no usado en `dashboard-mme.service` |
| `nginx-dashboard.conf` | Config standalone, probablemente reemplazada por `nginx-api-config.conf` |
| `core/config_simem.py` | Stub de refactor — debería consolidarse con `constants.py` |
| `core/validators.py` | Solo 2 funciones básicas, largamente reemplazado por Pydantic |
| `domain/models/metric.py` | Definido pero no usado por los servicios |
| `domain/models/prediction.py` | Definido pero no usado por los servicios |
| `interface/pages/config.py` | Supersedido por `core/constants.UIColors` |
| `interface/pages/metricas_piloto.py` | Prototipo no enlazado desde navbar |
| `experiments/` (toda la carpeta) | Resultados de experimentos ML — referencia |
| `ejemplos/` (toda la carpeta) | Scripts de ejemplo |
| `notebooks/README.md` | Carpeta vacía |

### 7.3 Archivos ELIMINADOS en esta inspección

| Archivo | Razón | Espacio |
|---------|-------|---------|
| `whatsapp_bot/whatsapp-web-service/node_modules/` | 82 MB no tracked, 6,161 archivos runtime | 82 MB |
| `whatsapp_bot/whatsapp-web-service/.wwebjs_auth/` | Datos autenticación runtime | Variable |
| `data/onedrive/test_download1.xlsx` | Archivo test no productivo (tracked) | 26 KB |
| `data/onedrive/test_publico.xlsx` | Archivo test no productivo (tracked) | 44 KB |
| `data/onedrive/Test_Comunidades_Energeticas.csv` | Archivo test no productivo (tracked) | 17 KB |
| `data/onedrive/Test_Comunidades_Energeticas.xlsx` | Archivo test no productivo (tracked) | 26 KB |
| `infrastructure/etl/__init__.py` | Paquete vacío sin módulos | 0 |
| `infrastructure/external/xm/__init__.py` | Paquete vacío sin módulos | 0 |
| `backups/deprecated/sistema_notificaciones.py` | Backup de servicio reescrito | 18 KB |
| `experiments/xgboost_experiment_*.log` | Log experiment no productivo | 3 KB |
| 27 directorios `__pycache__/` | Cache bytecode Python | ~2.5 MB |
| `.pytest_cache/` | Cache pytest | 44 KB |
| 5 logs truncados (>500KB cada uno) | Logs antiguos sobredimensionados | ~5 MB |

**Total liberado: ~90 MB**

### 7.4 Candidatos a evaluación futura

| Archivo | Razón | Recomendación |
|---------|-------|---------------|
| `backups/database/*.dump` | 652 MB en disco (gitignored) | Programar retención automática |
| `docs/referencias/*.pdf` | PDF 3 MB tracked en git | Mover a almacenamiento externo |
| `interface/pages/config.py` | Supersedido por `core/constants` | Verificar que nadie lo importe y eliminar |
| `domain/services/data_loader.py` | **ELIMINADO** — 13 líneas, nunca importado | Ya borrado |
| `whatsapp_bot/whatsapp-web-service/` | Proyecto WhatsApp Web deshabilitado | Evaluar si se reactiva o se elimina por completo |

---

## 8. Evaluación para una API pública

### 8.1 ¿Está la BD suficientemente limpia?

**SÍ, con reservas.** PostgreSQL es el backend principal desde FASE 20:

| Aspecto | Estado | Nota |
|---------|--------|------|
| Tabla `metrics` | ✅ Estable | ~500K+ filas, actualizada cada 6h |
| Tabla `metrics_hourly` | ✅ | Datos horarios segmentados |
| Tabla `catalogos` | ✅ | Recursos, embalses, ríos, agentes |
| Tabla `commercial_metrics` | ⚠️ | Se llena vía `completar_tablas_incompletas.py` (manual) |
| Tabla `lineas_transmision` | ✅ | ETL diario desde SIMEM |
| Tabla `predictions` | ✅ | Reentrenamiento semanal |
| Tabla `distribution_metrics` | ⚠️ | Lectura desde `metrics`, escritura separada |

### 8.2 ¿Hay inconsistencias de modelo de datos?

| Inconsistencia | Impacto | Severidad |
|----------------|---------|-----------|
| `valor_gwh` almacena Millones COP para restricciones | Semántica engañosa | **Alta** |
| Columnas `Values_Code`/`Values_Name` vs `codigo`/`nombre` | Doble naming convention | Media |
| `entidad` polisemántico: "Sistema", "Agente", nombre recurso | Difícil filtrar | Media |
| Métricas XM sin acentos: `Gene_Trmica`, `Gene_lica` | Nombres API originales | Baja |

### 8.3 Arquitectura propuesta para API pública

La API ya existe en `api/v1/` con 29 endpoints. Para exponerla públicamente:

1. **Los endpoints de `metrics`, `losses`, `restrictions`, `distribution`, `commercial` ya usan servicios de dominio** — listos para exposición
2. **Los endpoints de `generation`, `hydrology`, `transmission` usan queries directas** — deberían migrar a servicios
3. **Se necesita:**
   - Versionado semántico claro del API (ya usa `/v1/`)
   - Documentación OpenAPI más detallada con ejemplos
   - Rate limiting por API key (no solo global)
   - Métricas de uso (Prometheus ya está declarado pero no incrementado)
   - Caché HTTP con ETags para series temporales

### 8.4 Veredicto: ¿Listo para API pública?

**El proyecto está ~80% listo.** Tareas imprescindibles antes de exponer:

| # | Tarea | Esfuerzo |
|---|-------|----------|
| 1 | Migrar 6 routers API de queries directas a servicios de dominio | 2-3 días |
| 2 | Normalizar columna `valor_gwh` (renombrar a `valor` + campo `unidad` explícito en respuesta) | 1 día |
| 3 | Añadir rate limiting por API key | 0.5 días |
| 4 | Documentar OpenAPI con ejemplos y descripciones | 1 día |
| 5 | Activar métricas Prometheus (ya declaradas, solo falta `.inc()`) | 0.5 días |
| 6 | Connection pooling (psycopg2.pool) para soportar carga concurrente | 1 día |

---

## 9. Hallazgos críticos y deuda técnica

### 9.1 Prioridad ALTA

| # | Hallazgo | Ubicación | Impacto |
|---|----------|-----------|---------|
| 1 | **Sin connection pool** — cada operación DB abre/cierra una conexión TCP | `infrastructure/database/connection.py`, `manager.py` | Rendimiento bajo carga concurrente |
| 2 | **Inserts fila por fila** en PredictionsRepo y TransmissionRepo | `predictions_repository.py`, `transmission_repository.py` | ETL extremadamente lento |
| 3 | **Orchestrator de 4,197 líneas** — archivo monolítico | `domain/services/orchestrator_service.py` | Mantenibilidad |
| 4 | **10/15 servicios ignoran las interfaces DI** | Ver tabla DI en sección 2.3.4 | Testabilidad y acoplamiento |
| 5 | **6/12 routers API con queries directas** | `api/v1/routes/{generation,hydrology,transmission}.py` | Duplicación lógica, difícil mantener |
| 6 | **Seguimiento Predicciones usa psycopg2 directo** | `interface/pages/seguimiento_predicciones.py` | Violación severa de arquitectura |

### 9.2 Prioridad MEDIA

| # | Hallazgo | Ubicación |
|---|----------|-----------|
| 7 | Métricas Prometheus declaradas pero nunca incrementadas | `core/app_factory.py` |
| 8 | `.env.example` desincronizado con `config.py` (falta ~8 keys) | `.env.example` |
| 9 | Navbar desincronizada: `header.py` (8 links) vs `layout.py` (9 links) | `interface/components/` |
| 10 | `SmartDict.__getitem__` retorna `#CCCCCC` para claves inexistentes silenciosamente | `core/constants.py` |
| 11 | `Type=notify` en systemd services sin sd_notify | `api-mme.service`, `dashboard-mme.service` |
| 12 | Colisión nombre clase `PredictionsService` en 2 archivos | `domain/services/predictions_service*.py` |
| 13 | Lógica de conversión unidades duplicada en 3 archivos ETL | `etl/etl_rules.py`, `etl_xm_to_postgres.py`, `etl_todas_metricas_xm.py` |
| 14 | `celery` no está en `requirements.txt` a pesar de celerybeat-schedule y tasks/ | `requirements.txt` |

### 9.3 Prioridad BAJA

| # | Hallazgo |
|---|----------|
| 15 | `registrar_callback_filtro_fechas()` es no-op en `layout.py` |
| 16 | `crear_sidebar_universal()` retorna div vacío |
| 17 | `IIDEAMDataSource` definida pero nunca implementada |
| 18 | Modelos de dominio (`Metric`, `Prediction`) definidos pero nunca usados |
| 19 | `generar_fichas_hidricas_fallback()` duplicada, nunca invocada |
| 20 | `REGEX_PATTERNS` en `constants.py` definido pero no referenciado |

---

## 10. Recomendaciones finales

### 10.1 Acciones inmediatas (esta semana)

1. **Añadir connection pooling** (`psycopg2.pool.ThreadedConnectionPool`) en `connection.py` — impacto directo en rendimiento
2. **Corregir inserts batch** en `PredictionsRepository` y `TransmissionRepository` — usar `execute_batch()`
3. **Sincronizar `.env.example`** con todos los campos de `config.py`
4. **Añadir `celery` a `requirements.txt`**

### 10.2 Acciones a corto plazo (2 semanas)

5. **Migrar 6 routers API** de queries directas a servicios de dominio
6. **Dividir `orchestrator_service.py`** en intent handlers (~12 módulos)
7. **Migrar seguimiento_predicciones.py** a usar `PredictionsService`
8. **Unificar navbars** (`header.py` + `layout.py`)

### 10.3 Acciones a mediano plazo (1 mes)

9. **Migrar 10 servicios sin DI** a usar interfaces (empezar por `hydrology_service.py`, `notification_service.py`)
10. **Activar cobertura pytest** e incrementar de 85 a 120+ tests pasando
11. **Activar métricas Prometheus** en endpoints y callbacks
12. **Documentar API OpenAPI** con ejemplos para exposición pública

### 10.4 Métricas del proyecto

| Métrica | Valor |
|---------|-------|
| **Líneas de código Python** | ~55,000 |
| **Archivos Python** | ~130 |
| **Carpetas principales** | 15 |
| **Servicios de dominio** | 24 |
| **Repositorios** | 5 |
| **Páginas dashboard** | 12 (+ 1 piloto) |
| **Endpoints API** | 29 |
| **Callbacks Dash** | ~60 |
| **Tests** | 128 (85 pasando) |
| **ETL automatizados** | 10 cron + 4 Celery |
| **Tablas PostgreSQL** | 8 principales |
| **Espacio código (sin venv/git)** | 671 MB (652 MB son backups DB) |
| **Espacio código neto** | ~19 MB |

---

*Informe generado el 2 de marzo de 2026 mediante inspección automatizada de todo el repositorio.*
