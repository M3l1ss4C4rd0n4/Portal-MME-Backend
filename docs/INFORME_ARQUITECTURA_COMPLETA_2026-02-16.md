# Informe de Arquitectura Completa — Portal Energético MME

**Fecha:** 16 de febrero de 2026  
**Autor:** Inspección automatizada por ingeniero de sistemas senior  
**Versión del proyecto:** 2.0.0  
**Total líneas de código Python:** ~56.400  
**Archivos Python:** ~120  
**Base de datos:** PostgreSQL `portal_energetico` — ~63.7 millones de filas  

---

## Tabla de Contenidos

1. [Arquitectura General](#1-arquitectura-general)  
2. [Estructura de Carpetas y Archivos](#2-estructura-de-carpetas-y-archivos)  
3. [Flujo de Datos y ETL](#3-flujo-de-datos-y-etl)  
4. [Análisis Tablero por Tablero](#4-análisis-tablero-por-tablero)  
5. [Análisis de la API REST](#5-análisis-de-la-api-rest)  
6. [Bot de Telegram / WhatsApp](#6-bot-de-telegram--whatsapp)  
7. [Base de Datos — Estado Actual](#7-base-de-datos--estado-actual)  
8. [Machine Learning y Predicciones](#8-machine-learning-y-predicciones)  
9. [Archivos Esenciales vs. Prescindibles](#9-archivos-esenciales-vs-prescindibles)  
10. [Evaluación para API Pública](#10-evaluación-para-api-pública)  
11. [Recomendaciones Finales](#11-recomendaciones-finales)  

---

## 1. Arquitectura General

### 1.1 Patrón arquitectónico

El proyecto sigue una **Arquitectura Hexagonal (Clean Architecture)** con cuatro capas bien definidas:

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERFAZ (Presentación)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Dashboard    │  │  API REST    │  │  Bot Telegram/WhatsApp │ │
│  │  Dash/Plotly  │  │  FastAPI     │  │  python-telegram-bot   │ │
│  │  :8050        │  │  :8000       │  │  polling + :8001       │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘ │
├─────────┼──────────────────┼────────────────────┼───────────────┤
│         ▼                  ▼                    ▼               │
│                    DOMINIO (Servicios)                          │
│  orchestrator_service · generation_service · hydrology_service  │
│  commercial_service · transmission_service · losses_service     │
│  restrictions_service · distribution_service · ai_service       │
│  predictions_service_extended · news_service · indicators_svc   │
│  executive_report_service · intelligent_analysis_service        │
├─────────────────────────────────────────────────────────────────┤
│                    INFRAESTRUCTURA (Adaptadores)                │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  PostgreSQL      │  │  XM API      │  │  GNews API        │  │
│  │  repositories/   │  │  xm_service  │  │  news_client      │  │
│  │  connection.py   │  │  xm_adapter  │  │  (httpx)          │  │
│  └─────────────────┘  └──────────────┘  └───────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    CORE (Transversal)                           │
│  config.py · constants.py · container.py (DI) · exceptions.py  │
│  app_factory.py · validators.py                                │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Servicios en ejecución

| Servicio | Puerto | Proceso | Estado |
|----------|--------|---------|--------|
| API REST (FastAPI) | 8000 | gunicorn (5 workers) | ✅ Activo (systemd `api-mme.service`) |
| Dashboard (Dash/Plotly) | 8050 | gunicorn (18 workers) | ✅ Activo (systemd `dashboard-mme.service`) |
| Bot WhatsApp (FastAPI) | 8001 | uvicorn (3 workers) | ✅ Activo |
| Bot Telegram | polling | python3 telegram_polling.py | ✅ Activo |
| PostgreSQL | 5432 | postgres | ✅ Activo |
| Nginx (reverse proxy) | 80/443 | nginx | ✅ Activo |

### 1.3 Puntos de entrada

| Archivo | Función |
|---------|---------|
| `app.py` | Entrada para desarrollo (`python app.py`) — crea Dash app |
| `wsgi.py` | Entrada WSGI para gunicorn del Dashboard (puerto 8050) |
| `api/main.py` | Aplicación FastAPI del API REST (puerto 8000) |
| `whatsapp_bot/app/main.py` | Aplicación FastAPI del bot WhatsApp (puerto 8001) |
| `whatsapp_bot/telegram_polling.py` | Bot de Telegram en modo polling (sin puerto) |

---

## 2. Estructura de Carpetas y Archivos

### 2.1 `core/` — Capa Core (7 archivos)

Contiene la configuración central, constantes y contenedor de inyección de dependencias.

| Archivo | Propósito | Clases/Funciones clave |
|---------|-----------|----------------------|
| `app_factory.py` | Factory pattern para crear la app Dash multi-página | `create_app()`, `create_layout()`, callbacks de navbar, health endpoint |
| `config.py` | Configuración centralizada via Pydantic Settings | `Settings` (todas las env vars), `get_settings()` singleton, `validate_configuration()` |
| `config_simem.py` | Stub para categorías de métricas SIMEM | `METRICAS_SIMEM_POR_CATEGORIA`, `obtener_listado_simem()` |
| `constants.py` | Constantes globales: colores, IDs de métricas, umbrales | `METRIC_IDS`, `FUENTES_GENERACION`, `COLORS`, `UIColors`, `MapConfig` |
| `container.py` | Contenedor de DI con singletons lazy | `DependencyContainer`, métodos `get_*_repository()`, `get_*_service()` |
| `exceptions.py` | Jerarquía de excepciones del dominio | `PortalError` → `DateRangeError`, `InvalidParameterError`, `DataNotFoundError`, `ExternalAPIError`, `DatabaseError` |
| `validators.py` | Validadores básicos de fecha y strings | `validate_date_range()`, `validate_string()` |

**Problemas detectados:**  
- `constants.py` define `UIColors` tres veces al final del archivo (SmartDict, dict, SmartDict). Debería consolidarse.

### 2.2 `domain/` — Capa de Dominio

#### `domain/interfaces/` — Puertos (3 archivos)

| Archivo | Propósito |
|---------|-----------|
| `database.py` | ABC `IDatabaseManager` — contrato de acceso a BD (`query_df()`, `execute_non_query()`) |
| `data_sources.py` | ABCs `IXMDataSource`, `ISIMEMDataSource` — contratos para APIs externas |
| `repositories.py` | ABCs `IMetricsRepository`, `ICommercialRepository`, `IDistributionRepository`, `ITransmissionRepository`, `IPredictionsRepository` |

#### `domain/models/` — Modelos de dominio (2 archivos)

| Archivo | Propósito |
|---------|-----------|
| `metric.py` | Dataclass `Metric` (fecha, metrica, entidad, valor_gwh, unidad, recurso) |
| `prediction.py` | Dataclass `Prediction` (fecha_prediccion, fuente, valor_gwh_predicho, intervalos, modelo, confianza) |

#### `domain/schemas/` — Esquemas API (1 archivo)

| Archivo | Propósito |
|---------|-----------|
| `orchestrator.py` | Pydantic schemas: `OrchestratorRequest` (sessionId, intent, parameters), `OrchestratorResponse`, `ErrorDetail` |

#### `domain/services/` — Lógica de Negocio (21 archivos)

| Archivo | Líneas | Propósito | Estado |
|---------|--------|-----------|--------|
| `orchestrator_service.py` | 2941 | Orquestador central del chatbot: mapea intents a servicios, genera menú, maneja 15+ intents | **Esencial** |
| `executive_report_service.py` | 1475 | Genera informe ejecutivo estadístico con 11 secciones en paralelo | **Esencial** |
| `intelligent_analysis_service.py` | 833 | Detección de anomalías y estado del sector (umbrales, severidad) | **Esencial** |
| `generation_service.py` | 447 | Datos de generación (hidráulica, térmica, solar, eólica) | **Esencial** |
| `predictions_service_extended.py` | 433 | Motor ML: Prophet + ARIMA + Ensemble para predicciones | **Esencial** |
| `ai_service.py` | 421 | Agente IA usando LLM (Groq/OpenRouter) | **Esencial** |
| `distribution_service.py` | 402 | Distribución/demanda con deduplicación de agentes | **Esencial** |
| `hydrology_service.py` | 325 | Niveles de embalses, aportes hídricos, volumen útil | **Esencial** |
| `commercial_service.py` | 281 | Precios (bolsa, escasez, activación): BD primero, fallback a API | **Esencial** |
| `validators.py` | 248 | Validadores de rangos por métrica del dominio | **Esencial** |
| `transmission_service.py` | 208 | Líneas de transmisión e intercambios internacionales | **Esencial** |
| `metrics_service.py` | 201 | Fachada de métricas con DI y normalización temporal | **Esencial** |
| `metrics_calculator.py` | 200 | Fórmulas oficiales XM: variación, formato colombiano | **Esencial** |
| `news_service.py` | 200 | Noticias energéticas: scoring, caché 30min, top 3 | **Útil** |
| `restrictions_service.py` | 200 | Restricciones operativas (RestAliv, AGC) en Millones COP | **Esencial** |
| `losses_service.py` | 170 | Análisis de pérdidas de energía | **Esencial** |
| `indicators_service.py` | 170 | KPIs con comparación temporal (valor+variación+flecha) | **Esencial** |
| `system_service.py` | 170 | Verificación de salud del sistema | **Esencial** |
| `confianza_politica.py` | 117 | Política de confianza en predicciones (Fase 6) | **Útil** |
| `geo_service.py` | 40 | Coordenadas geográficas de regiones colombianas | **Útil** |
| `predictions_service.py` | 34 | Wrapper simple de predicciones — delegado al repositorio | **Obsoleto** (supersedido por `_extended`) |
| `data_loader.py` | 13 | Conversión DataFrame → Excel (BytesIO) | **Obsoleto** (sin uso aparente) |

### 2.3 `infrastructure/` — Capa de Infraestructura

#### `infrastructure/database/` — Acceso a datos (8 archivos)

| Archivo | Propósito |
|---------|-----------|
| `connection.py` | `PostgreSQLConnectionManager` — pool de conexiones con psycopg2 context manager |
| `manager.py` | `DatabaseManager` — `query_df()`, `upsert_metrics_bulk()`, `upsert_catalogo_bulk()` con ON CONFLICT |
| `repositories/base_repository.py` | `BaseRepository` — operaciones comunes (`execute_query()`, `execute_dataframe()`) |
| `repositories/metrics_repository.py` | `MetricsRepository` — tabla `metrics` y `metrics_hourly` |
| `repositories/commercial_repository.py` | `CommercialRepository` — tabla `commercial_metrics` |
| `repositories/distribution_repository.py` | `DistributionRepository` — tabla `metrics` filtrada por demanda |
| `repositories/transmission_repository.py` | `TransmissionRepository` — tabla `lineas_transmision` |
| `repositories/predictions_repository.py` | `PredictionsRepository` — tabla `predictions` con ON CONFLICT upsert |

#### `infrastructure/external/` — Adaptadores externos (2 archivos)

| Archivo | Propósito |
|---------|-----------|
| `xm_adapter.py` | Adaptador hexagonal que implementa `IXMDataSource` envolviendo `xm_service` |
| `xm_service.py` | Helper para API XM: singleton de pydataxm, `fetch_metric_data()` (30s timeout), estrategia inteligente BD→API |

#### `infrastructure/news/` — Noticias (1 archivo)

| Archivo | Propósito |
|---------|-----------|
| `news_client.py` | Cliente HTTP async para GNews API (httpx, 10 artículos/request) |

#### `infrastructure/logging/` — Logging (1 archivo)

| Archivo | Propósito |
|---------|-----------|
| `logger.py` | `LoggerManager` singleton con RotatingFileHandler (10MB, 5 backups) |

### 2.4 `interface/` — Dashboard Dash/Plotly

#### `interface/components/` — Componentes UI (3 archivos)

| Archivo | Propósito |
|---------|-----------|
| `layout.py` | Navbar horizontal, sidebar universal, header, filtro de fechas compacto |
| `header.py` | Header restaurado con logos del ministerio |
| `chat_widget.py` | Widget de chat IA integrado en el dashboard, conecta al orquestador |

#### `interface/pages/` — Páginas del tablero (13 archivos)

| Archivo | Ruta | Propósito |
|---------|------|-----------|
| `home.py` | `/` | Página de inicio con portada interactiva y navegación visual |
| `generacion.py` | `/generacion` | Vista general de generación con KPI cards |
| `generacion_fuentes_unificado.py` | `/generacion-fuentes` | Generación desglosada por tipo de fuente |
| `generacion_hidraulica_hidrologia.py` | `/generacion-hidraulica` | Generación hidráulica + hidrología (embalses, aportes) |
| `distribucion.py` | `/distribucion` | Demanda y distribución por agentes |
| `comercializacion.py` | `/comercializacion` | Precios: bolsa, escasez, activación |
| `transmision.py` | `/transmision` | Líneas de transmisión y flujos |
| `restricciones.py` | `/restricciones` | Restricciones operativas y costos |
| `perdidas.py` | `/perdidas` | Pérdidas de energía |
| `metricas.py` | `/metricas` | Explorador general de métricas |
| `metricas_piloto.py` | `/metricas-piloto` | Versión experimental del explorador |
| `config.py` | — | Constantes de configuración de páginas |
| `hidrologia/utils.py` | — | Helpers para la página de hidrología |

### 2.5 `api/` — API REST FastAPI (15+ archivos)

| Grupo | Archivos | Propósito |
|-------|----------|-----------|
| Core API | `main.py`, `dependencies.py` | App FastAPI, CORS, rate limiting, DI, API key validation |
| Routes (12) | `chatbot.py`, `metrics.py`, `generation.py`, `hydrology.py`, `predictions.py`, `commercial.py`, `distribution.py`, `transmission.py`, `losses.py`, `restrictions.py`, `system.py`, `whatsapp_alerts.py` | Endpoints REST por dominio |
| Schemas (12) | `common.py`, `commercial.py`, `distribution.py`, `generation.py`, `hydrology.py`, `losses.py`, `metrics.py`, `orchestrator.py`, `predictions.py`, `restrictions.py`, `system.py`, `transmission.py` | Modelos Pydantic de request/response |

### 2.6 `etl/` — Pipeline de Datos (7 archivos)

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `etl_rules.py` | 401 | **Fuente de verdad canónica** para conversiones de unidades, rangos, y reglas de 60+ métricas |
| `etl_xm_to_postgres.py` | 698 | ETL principal: XM API → PostgreSQL (cron 3x/día). Contiene `convertir_unidades()` propio |
| `etl_todas_metricas_xm.py` | 593 | ETL masivo de 193 métricas XM. Usa `etl_rules` primero con fallback legacy |
| `config_metricas.py` | 422 | Configuración de métricas por sección: períodos, batch sizes, entidades |
| `validaciones.py` | 274 | Validador de calidad de datos post-incidente |
| `validaciones_rangos.py` | 203 | Validación de rangos según estándares XM Sinergox |
| `etl_transmision.py` | 130 | ETL de líneas de transmisión desde SIMEM (dataset 7538fd) |

### 2.7 `scripts/` — Scripts Operacionales (29 archivos)

#### Producción / Cron

| Archivo | Propósito |
|---------|-----------|
| `actualizar_predicciones.sh` | Cron semanal: entrena ML → genera alertas → notifica |
| `ejecutar_etl_completo.sh` | Ejecuta ETL para las 12 secciones |
| `backup_postgres_diario.sh` | Backup diario con pg_dump (30 días retención) |
| `monitor_api.sh` | Watchdog: reinicia API si health falla (cron 5 min) |
| `alertas_energeticas.py` | Motor de alertas por umbrales (583 líneas) |
| `sistema_notificaciones.py` | Servicio de notificación: Email + WhatsApp (486 líneas) |
| `train_predictions_postgres.py` | ML: Prophet+SARIMA para generación (553 líneas) |
| `train_predictions_sector_energetico.py` | ML: predicciones extendidas para todo el sector (735 líneas) |

#### Utilidades / Diagnóstico

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `backfill_sistema_metricas.py` | Backfill de 6 años de datos históricos | Útil (one-time) |
| `completar_tablas_incompletas.py` | Rellena tablas vacías desde XM | Útil (one-time) |
| `db_explorer.py` | Explorador interactivo de BD | Útil |
| `diagnostico_conversores_unidades.py` | Audita conversiones del ETL | Útil |
| `diagnostico_metricas_etl.py` | Health check: gaps, unidades, datos stale | Útil |
| `limpiar_datos_corruptos.py` | Limpiador destructivo (con --dry-run) | Útil |
| `validar_sistema_completo.py` | Validación de caché, conversiones, cron | Útil |
| `inspeccion_senior_endpoint.py` | Validación E2E del orquestador API | Útil |

#### Obsoletos (candidatos a borrar)

| Archivo | Razón |
|---------|-------|
| `demo_bd.sh` | Demo interactivo sin valor operacional |
| `ver_bd.sh` | Wrapper de 2 líneas que solo llama a db_explorer.py |
| `ops/monitorear_etl.sh` | **Roto:** usa comandos SQLite pero la BD es PostgreSQL |
| `ops/verificar_sistema.sh` | **Roto:** usa comandos SQLite pero la BD es PostgreSQL |

### 2.8 `tasks/` — Tareas Celery (3 archivos)

| Archivo | Propósito |
|---------|-----------|
| `__init__.py` | Configuración Celery: broker Redis, schedule (ETL 6h, anomalías 30min, logs 3AM, resumen 7AM) |
| `etl_tasks.py` | `SafeETLTask` con auto-retry + backoff, `etl_incremental_all_metrics`, `clean_old_logs` |
| `anomaly_tasks.py` | `check_anomalies` (30min), `send_daily_summary` (7AM): alertas → BD → API bot |

### 2.9 `whatsapp_bot/` — Bot de Mensajería

| Archivo | Propósito |
|---------|-----------|
| `telegram_polling.py` | Bot Telegram completo (1373 líneas): polling, inline keyboards, 5 intents del menú, renders profesionales |
| `app/config.py` | Settings: Twilio, Meta API, WhatsApp Web, Groq AI, Redis, Telegram |
| `app/main.py` | FastAPI para webhooks WhatsApp (:8001) |
| `app/rate_limiting.py` | Rate limiter con Redis |
| `app/security.py` | Validación de firma Twilio |
| `app/sender.py` | Sender multi-proveedor: Twilio, Meta API, WhatsApp Web |
| `app/tasks.py` | Tareas de broadcasting de alertas |
| `whatsapp-web-service/` | Servicio Node.js/Express con whatsapp-web.js (Puppeteer). Alternativa gratuita a Twilio |

### 2.10 Otros directorios

| Directorio | Propósito |
|------------|-----------|
| `sql/` | Scripts DDL: `alertas_historial.sql`, `predictions_simple.sql`, migraciones |
| `tests/` | Tests unitarios + integración: servicios, repositorios, ETL, API, informe ejecutivo |
| `tests/ARGIS/` | Scripts de integración con ArcGIS Online (capa hospedada) |
| `docs/` | 19 documentos técnicos en Markdown + PDF de referencia CREG |
| `backups/` | Dumps PostgreSQL y backups de datos |
| `data/` | `metricas_xm_arcgis.csv` — datos para capa ArcGIS hospedada |
| `config/` | Archivos de configuración systemd (Celery worker) y logrotate |
| `ejemplos/` | Ejemplos de uso del API: informe ejecutivo y bot WhatsApp |
| `notebooks/` | Solo README.md — carpeta prácticamente vacía |
| `assets/` | CSS (13 archivos), JS (5 archivos), imágenes (12), GeoJSON de Colombia |

### 2.11 Archivos raíz

| Archivo | Propósito |
|---------|-----------|
| `app.py` | Entry point de desarrollo para Dash |
| `wsgi.py` | Entry point de producción para gunicorn del dashboard |
| `gunicorn_config.py` | Config gunicorn: bind 127.0.0.1:8050, workers=CPU×2+1, gthread, timeout 120s |
| `requirements.txt` | 52 dependencias Python |
| `pytest.ini` | Configuración de pytest |
| `api-mme.service` | Archivo systemd para el API REST |
| `dashboard-mme.service` | Archivo systemd para el Dashboard |
| `nginx-api-config.conf` | Config nginx para proxy inverso del API |
| `nginx-dashboard.conf` | Config nginx para proxy inverso del Dashboard |
| `LICENSE` | Licencia del proyecto |
| `README.md` | Documentación principal del proyecto |
| `.env` / `.env.example` / `.env.api.example` | Variables de entorno |
| `.gitignore` | Archivos ignorados por git |

---

## 3. Flujo de Datos y ETL

### 3.1 Diagrama de flujo de datos

```
FUENTES EXTERNAS                    ETL                         BASE DE DATOS                   PRESENTACIÓN
┌──────────────┐     ┌───────────────────────┐     ┌───────────────────────┐     ┌─────────────────────────┐
│  XM API      │────▶│ etl_xm_to_postgres    │────▶│ metrics (13.5M filas) │────▶│ Dashboard Dash (:8050)  │
│  (pydataxm)  │     │ etl_todas_metricas_xm │     │ metrics_hourly (50M)  │     │ API REST (:8000)        │
│              │     │ cron 3x/día           │     │ catalogos (2264)      │     │ Bot Telegram (polling)  │
└──────────────┘     └───────────────────────┘     │ predictions (1170)    │     │ Bot WhatsApp (:8001)    │
                                                    └───────────────────────┘     └─────────────────────────┘
┌──────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
│  SIMEM API   │────▶│ etl_transmision       │────▶│ lineas_transmision    │
│  (ReadSIMEM) │     │ (dataset 7538fd)      │     │ (42.106 filas)        │
└──────────────┘     └───────────────────────┘     └───────────────────────┘

┌──────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
│  GNews API   │────▶│ news_client (httpx)   │────▶│ Cache in-memory 30min │
│  (gnews.io)  │     │ news_service scoring  │     │ (no persiste en BD)   │
└──────────────┘     └───────────────────────┘     └───────────────────────┘

┌──────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
│  Groq /      │────▶│ ai_service (LLM)      │────▶│ Respuestas en tiempo  │
│  OpenRouter  │     │ AgentIA               │     │ real (no persiste)    │
└──────────────┘     └───────────────────────┘     └───────────────────────┘
```

### 3.2 Automatización ETL

| Tarea | Frecuencia | Mecanismo | Script |
|-------|-----------|-----------|--------|
| ETL métricas principales | 3x/día (06:00, 12:00, 18:00) | Cron | `etl_xm_to_postgres.py` |
| ETL todas 193 métricas | Manual / semanal | Cron / manual | `etl_todas_metricas_xm.py` |
| ETL transmisión | Manual | Script | `etl_transmision.py` |
| Predicciones ML | Semanal | Cron | `actualizar_predicciones.sh` → `train_predictions_*.py` |
| Detección anomalías | Cada 30 min | Celery Beat | `tasks/anomaly_tasks.py` |
| ETL incremental | Cada 6 horas | Celery Beat | `tasks/etl_tasks.py` |
| Resumen diario | 7:00 AM | Celery Beat | `tasks/anomaly_tasks.py` |
| Backup BD | Diario | Cron | `backup_postgres_diario.sh` |
| Log rotation | Diario | Logrotate | `config/logrotate.conf` |

### 3.3 Cómo usa cada capa sus datos

| Componente | Accede a BD vía… | Accede a API externa vía… | Lee archivos estáticos |
|------------|------------------|--------------------------|----------------------|
| Dashboard (páginas) | Servicios de dominio → Repositorios | XM API como fallback | GeoJSON de Colombia, imágenes CSS |
| API REST | Servicios de dominio → Repositorios | XM API como fallback | No |
| Bot Telegram | Orquestador → API REST HTTP | GNews vía news_client | No |
| ETL | Directamente con psycopg2/upsert | XM/SIMEM APIs | No |

---

## 4. Análisis Tablero por Tablero

### 4.1 Inicio (`home.py` → `/`)

- **Layout:** Portada interactiva con logos del ministerio, botones visuales a cada sección
- **Callbacks:** Navegación a las demás páginas
- **Datos:** No requiere datos — es la portada visual
- **Estado:** ✅ Funcional

### 4.2 Generación (`generacion.py` → `/generacion`)

- **Layout:** KPI cards de generación total, por recurso (hidráulica, térmica, solar, eólica)
- **Callbacks:** Filtro por rango de fechas, actualización de gráficos y KPIs
- **Datos:** `GenerationService` → `MetricsRepository` → tabla `metrics`
- **Estado:** ✅ Funcional — tiene datos 2020–2026

### 4.3 Generación por Fuentes (`generacion_fuentes_unificado.py` → `/generacion-fuentes`)

- **Layout:** Gráficos de generación por tipo de fuente con mix energético
- **Callbacks:** Filtros por fuente, período, tipo de gráfico
- **Datos:** `GenerationService` → `MetricsRepository`
- **Estado:** ✅ Funcional

### 4.4 Hidrología (`generacion_hidraulica_hidrologia.py` → `/generacion-hidraulica`)

- **Layout:** Niveles de embalses, aportes hídricos, volumen útil
- **Callbacks:** Filtro por fechas, embalse específico
- **Datos:** `HydrologyService` → `MetricsRepository`
- **Estado:** ✅ Funcional

### 4.5 Distribución (`distribucion.py` → `/distribucion`)

- **Layout:** Demanda por operador, distribución regional
- **Callbacks:** Filtro por agente, período
- **Datos:** `DistributionService` → `MetricsRepository`
- **Estado:** ✅ Funcional

### 4.6 Comercialización (`comercializacion.py` → `/comercializacion`)

- **Layout:** Precios de bolsa, escasez, activación
- **Callbacks:** Filtro por fechas, tipo de precio
- **Datos:** `CommercialService` → BD con fallback a XM API
- **Estado:** ⚠️ Parcial — tabla `commercial_metrics` tiene **0 filas**. Funciona vía fallback a API XM pero es más lento.

### 4.7 Transmisión (`transmision.py` → `/transmision`)

- **Layout:** Líneas de transmisión, flujos, intercambios
- **Callbacks:** Filtro por línea, período
- **Datos:** `TransmissionService` → `TransmissionRepository` → tabla `lineas_transmision`
- **Estado:** ✅ Funcional — 42.106 registros de líneas

### 4.8 Restricciones (`restricciones.py` → `/restricciones`)

- **Layout:** Costo de restricciones (RestAliv, AGC), análisis temporal
- **Callbacks:** Filtro por tipo, período
- **Datos:** `RestrictionsService` → `MetricsRepository`
- **Estado:** ⚠️ Parcial — tabla `restriction_metrics` tiene **0 filas**. Depende de datos en `metrics` principal.

### 4.9 Pérdidas (`perdidas.py` → `/perdidas`)

- **Layout:** Pérdidas técnicas y no técnicas
- **Callbacks:** Filtro por tipo, período
- **Datos:** `LossesService` → `MetricsRepository`
- **Estado:** ⚠️ Parcial — tabla `loss_metrics` tiene **0 filas**. Depende de datos en `metrics` principal.

### 4.10 Métricas (`metricas.py` → `/metricas`)

- **Layout:** Explorador general de métricas con selección dinámica
- **Callbacks:** Dropdown de métricas, rango de fechas, gráfico dinámico
- **Datos:** `MetricsService` → `MetricsRepository`
- **Estado:** ✅ Funcional — accede a las 13.5M filas de datos

### 4.11 Métricas Piloto (`metricas_piloto.py` → `/metricas-piloto`)

- **Estado:** Experimental — versión de prueba del explorador de métricas. No enlazado en el menú principal.

---

## 5. Análisis de la API REST

### 5.1 Endpoints disponibles

La API tiene **26+ endpoints** organizados por dominio:

| Grupo | Endpoints | Base |
|-------|-----------|------|
| Chatbot | `POST /chatbot/orchestrator`, `GET /chatbot/health` | `/api/v1/chatbot/` |
| Metrics | `GET /metrics/{metric}`, `GET /metrics` | `/api/v1/metrics/` |
| Generation | `/system`, `/by-source`, `/resources`, `/mix` | `/api/v1/generation/` |
| Hydrology | `/aportes`, `/reservoirs`, `/energy` | `/api/v1/hydrology/` |
| Predictions | `GET /{metric}`, `POST /train` | `/api/v1/predictions/` |
| Commercial | `/prices`, `/contracts` | `/api/v1/commercial/` |
| Distribution | `/data`, `/operators` | `/api/v1/distribution/` |
| Transmission | `/lines`, `/flows`, `/international` | `/api/v1/transmission/` |
| Losses | `GET /` | `/api/v1/losses/` |
| Restrictions | `GET /` | `/api/v1/restrictions/` |
| System | `/demand`, `/prices` | `/api/v1/system/` |
| WhatsApp | `POST /alert`, `GET /status` | `/api/v1/whatsapp/` |

### 5.2 Autenticación

- API Key via header `X-API-Key`
- Validación en `dependencies.py`
- Key actual: `mme-portal-energetico-2026-secret-key`

### 5.3 Documentación interactiva

- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
- OpenAPI 3.0.3

---

## 6. Bot de Telegram / WhatsApp

### 6.1 Bot de Telegram (`telegram_polling.py`)

**Modo:** Polling (no requiere webhook ni puerto público)  
**Tamaño:** 1373 líneas  

**Menú principal (5 opciones):**

| # | Intent | Emoji | Descripción |
|---|--------|-------|-------------|
| 1 | `estado_actual` | 📊 | Estado actual del sector |
| 2 | `predicciones_sector` | 🔮 | Predicciones (submenú horizontes) |
| 3 | `anomalias_sector` | 🚨 | Anomalías detectadas |
| 4 | `noticias_sector` | 📰 | Noticias del sector energético |
| 5 | `mas_informacion` | 📋 | Más información (informe + pregunta libre) |

**Funcionalidades:**
- Inline keyboards con navegación bidireccional
- Renders profesionales por intent
- Submenús: predicciones (5 horizontes), más información (informe + pregunta libre)
- Cache de informes para navegación por secciones (11 secciones)
- Detalle de anomalías expandible inline
- Noticias con botones URL y actualización in-place
- Pregunta libre con toggle datos ↔ análisis IA
- Comandos: `/estado`, `/predicciones`, `/anomalias`, `/noticias`, `/informe`, `/menu`, `/ayuda`

### 6.2 Bot WhatsApp

- **Backend:** FastAPI en puerto 8001 (uvicorn)
- **Proveedores:** Twilio, Meta API, WhatsApp Web (Node.js local)
- **WhatsApp Web Service:** `whatsapp-web-service/` — Express + Puppeteer (82MB node_modules)
- **Funcionalidad:** Recibe webhooks, envía alertas, broadcasting de anomalías diarias

---

## 7. Base de Datos — Estado Actual

### 7.1 Tablas y volumen de datos

| Tabla | Filas | Estado | Propósito |
|-------|-------|--------|-----------|
| `metrics` | 13.545.680 | ✅ Sana | Métricas diarias del SIN (2020–2026) |
| `metrics_hourly` | 50.127.023 | ✅ Sana | Datos horarios del SIN |
| `lineas_transmision` | 42.106 | ✅ Sana | Infraestructura de transmisión |
| `catalogos` | 2.264 | ✅ Sana | Catálogo de métricas XM |
| `predictions` | 1.170 | ✅ Sana | Predicciones ML (Prophet/ARIMA) |
| `alertas_historial` | 3 | ✅ Sana | Historial de alertas enviadas |
| `alertas_recientes` | 3 | ✅ Sana | Alertas recientes activas |
| `configuracion_notificaciones` | 3 | ✅ Sana | Configuración de destinatarios |
| `commercial_metrics` | **0** | ⚠️ Vacía | Precios comerciales — sin datos |
| `loss_metrics` | **0** | ⚠️ Vacía | Pérdidas — sin datos |
| `restriction_metrics` | **0** | ⚠️ Vacía | Restricciones — sin datos |
| `metricas_criticas_activas` | **0** | ⚠️ Vacía | Métricas críticas activas |

**Total:** ~63.7 millones de filas (99.6% en `metrics` + `metrics_hourly`)

### 7.2 Tablas vacías — Causa raíz

Las tablas `commercial_metrics`, `loss_metrics`, y `restriction_metrics` están vacías porque:

1. El ETL principal (`etl_xm_to_postgres.py`) escribe todo a la tabla `metrics` unificada
2. Los scripts de backfill (`completar_tablas_incompletas.py`) existen pero no se han ejecutado
3. Los servicios de dominio de comercialización, pérdidas y restricciones usan **fallback a la tabla `metrics` principal** o a la API XM directa

**Impacto:** Funcional pero subóptimo — los tableros de comercialización, pérdidas y restricciones dependen del fallback y pueden ser más lentos.

---

## 8. Machine Learning y Predicciones

### 8.1 Modelos implementados

| Modelo | Implementación | Uso |
|--------|----------------|-----|
| Prophet | `predictions_service_extended.py` → `_forecast_prophet()` | Series temporales con estacionalidad |
| ARIMA/SARIMA | `predictions_service_extended.py` → `_forecast_arima()` | Series temporales estacionarias |
| Ensemble | `predictions_service_extended.py` → `_forecast_ensemble()` | Promedio ponderado Prophet+ARIMA |

### 8.2 Pipeline de entrenamiento

1. `train_predictions_postgres.py` — Generación por fuente (90 días horizonte)
2. `train_predictions_sector_energetico.py` — Todas las métricas del sector
3. Resultados → tabla `predictions` (1.170 predicciones activas)

### 8.3 Política de confianza (Fase 6)

Definida en `confianza_politica.py`:
- **MUY_CONFIABLE:** MAPE < 5% (generación total, demanda)
- **CONFIABLE:** MAPE 5-15% (hidráulica, térmica, embalses)
- **ACEPTABLE:** MAPE 15-25% (solar, eólica, aportes)
- **EXPERIMENTAL:** MAPE > 25% (precios, pérdidas)
- **DESCONOCIDO:** Sin datos de entrenamiento

---

## 9. Archivos Esenciales vs. Prescindibles

### 9.1 Archivos borrados en esta inspección (basura)

| Archivo | Razón |
|---------|-------|
| `ql -h localhost -U postgres -d portal_energetico --no-align -t -c "` | Archivo accidental creado por comando psql roto |
| `ql -h localhost -U postgres -d portal_energetico -P pager=off -c "` | Ídem |
| `tema'` | Archivo accidental de bash con comillas sin cerrar |
| `celerybeat-schedule` | Runtime de Celery Beat (se regenera automáticamente) |
| `control/celery.exchange` | Runtime de Celery (se regenera) |
| `control/celery.pidbox.exchange` | Runtime de Celery (se regenera) |

### 9.2 Archivos movidos

| Archivo | De → A | Razón |
|---------|--------|-------|
| `test_auditoria_datos_orquestador.py` | raíz → `tests/` | Test fuera de lugar |
| `LINKS_ACCESO.md` | raíz → `docs/` | Documentación. Añadido a `.gitignore` (tiene credenciales) |

### 9.3 Candidatos a borrar (obsoletos)

| Archivo | Razón | Acción recomendada |
|---------|-------|-------------------|
| `domain/services/predictions_service.py` | 34 líneas, supersedido por `predictions_service_extended.py` | Mover a `legacy/` |
| `domain/services/data_loader.py` | 13 líneas (`to_excel`), sin imports en el proyecto | Borrar |
| `scripts/demo_bd.sh` | Demo interactiva sin valor | Borrar |
| `scripts/ver_bd.sh` | Wrapper trivial de 2 líneas | Borrar |
| `scripts/ops/monitorear_etl.sh` | **Roto:** usa SQLite pero la BD es PostgreSQL | Borrar o reescribir |
| `scripts/ops/verificar_sistema.sh` | **Roto:** usa SQLite pero la BD es PostgreSQL | Borrar o reescribir |
| `infrastructure/etl/__init__.py` | Placeholder vacío sin uso | Dejar (inofensivo) |
| `interface/pages/metricas_piloto.py` | Experimental, no enlazado en menú | Mover a `legacy/` |

### 9.4 Archivos esenciales que no deben tocarse

- Todo el directorio `core/`
- Todo el directorio `domain/` (excepto los 2 obsoletos indicados)
- Todo el directorio `infrastructure/` (adaptadores, repositorios, clientes)
- Todo el directorio `api/` (API REST)
- Todo el directorio `etl/` (pipeline de datos)
- Todo el directorio `tasks/` (Celery Beat)
- `whatsapp_bot/telegram_polling.py` y `whatsapp_bot/app/`
- Archivos raíz de producción: `wsgi.py`, `gunicorn_config.py`, `*.service`, `nginx-*.conf`

---

## 10. Evaluación para API Pública

### 10.1 ¿Está listo para una API pública?

**Respuesta: SÍ, con reservas menores.**

La API REST ya existe y está funcionando con 26+ endpoints, autenticación por API key, schemas Pydantic validados, documentación Swagger/ReDoc, y rate limiting.

### 10.2 Fortalezas actuales

| Aspecto | Estado |
|---------|--------|
| Arquitectura hexagonal | ✅ Bien definida — servicios → repositorios → BD |
| Schemas Pydantic | ✅ Tipado fuerte en request/response |
| Autenticación | ✅ API Key funcional |
| Documentación interactiva | ✅ Swagger + ReDoc |
| Rate limiting | ✅ Implementado |
| CORS configurado | ✅ Permitido |
| Health checks | ✅ En API y chatbot |
| Manejo de errores | ✅ Excepciones tipadas |
| Datos históricos | ✅ 63.7M filas desde 2020 |

### 10.3 Debilidades a corregir antes de API pública

| Problema | Impacto | Prioridad |
|----------|---------|-----------|
| Tablas vacías (`commercial_metrics`, `loss_metrics`, `restriction_metrics`) | Endpoints de comercialización, pérdidas y restricciones dependen de fallback | **Alta** |
| Clave `metricas_restricciones` duplicada en `config_metricas.py` | Silenciosamente sobrescribe configuración | **Media** |
| `UIColors` triplicado en `constants.py` | Confusión de mantenimiento | **Baja** |
| ETL aún tiene `convertir_unidades()` legacy en `etl_xm_to_postgres.py` | Inconsistencia con `etl_rules.py` canónico | **Media** |
| API key hardcodeada en docs/ejemplos | Riesgo de seguridad | **Media** |
| Scripts ops con referencia a SQLite | Scripts rotos que no sirven | **Baja** |

### 10.4 Tareas para API pública estable

1. **Ejecutar `completar_tablas_incompletas.py`** para poblar las 3 tablas vacías
2. **Unificar `convertir_unidades()`** en `etl_xm_to_postgres.py` para que use `etl_rules.py`
3. **Corregir clave duplicada** `metricas_restricciones` en `config_metricas.py`
4. **Documentar formato de API key** y añadir mecanismo de rotación
5. **Agregar versionado** semántico a la API (`/api/v1/...` ya existe)
6. **Añadir paginación** a endpoints que retornan series grandes (ya parcialmente implementado)

---

## 11. Recomendaciones Finales

### 11.1 Prioridad Alta — Hacer ahora

1. **Poblar tablas vacías:** Ejecutar `scripts/completar_tablas_incompletas.py` para `commercial_metrics`, `loss_metrics`, `restriction_metrics`
2. **Limpiar archivos obsoletos:** Borrar los 6 archivos marcados como candidatos
3. **Corregir `config_metricas.py`:** Eliminar la clave duplicada `metricas_restricciones`

### 11.2 Prioridad Media — Próximas semanas

4. **Migrar conversiones a `etl_rules.py`:** Reemplazar `convertir_unidades()` en `etl_xm_to_postgres.py` por las reglas canónicas
5. **Consolidar `UIColors`** a una sola definición en `constants.py`
6. **Eliminar `predictions_service.py` simple** — solo usar `predictions_service_extended.py`
7. **Actualizar scripts ops:** Reescribir `monitorear_etl.sh` y `verificar_sistema.sh` para PostgreSQL

### 11.3 Prioridad Baja — Mejora continua

8. **Agregar tests de integración** para endpoints de comercialización, pérdidas y restricciones
9. **Implementar caché Redis** para queries pesadas de la API (actualmente solo cache in-memory para noticias)
10. **Mover `whatsapp-web-service/node_modules/`** (82MB) al `.gitignore` si no está
11. **Documentar política de datos:** qué métricas se actualizan con qué frecuencia y cuáles tienen lag

---

## Apéndice A — Servicios del sistema

```
# Estado de servicios activos (16 febrero 2026)
api-mme.service        → active (gunicorn :8000, 5 workers)
dashboard-mme.service  → active (gunicorn :8050, 18 workers)
whatsapp-bot           → active (uvicorn :8001, 3 workers)
telegram-bot           → active (python3 polling)
postgresql             → active (:5432)
nginx                  → active (:80, :443)
```

## Apéndice B — Cron Jobs activos

```bash
# ETL métricas principales (3x/día)
0 6,12,18 * * * cd /home/admonctrlxm/server && /home/admonctrlxm/server/venv/bin/python etl/etl_xm_to_postgres.py

# Predicciones ML (semanal, lunes 2 AM)
0 2 * * 1 cd /home/admonctrlxm/server && bash scripts/actualizar_predicciones.sh

# Backup diario (3 AM)
0 3 * * * bash /home/admonctrlxm/server/scripts/backup_postgres_diario.sh

# Monitor API (cada 5 min)
*/5 * * * * bash /home/admonctrlxm/server/scripts/monitor_api.sh
```

## Apéndice C — Limpieza realizada en esta inspección

| Acción | Detalle |
|--------|---------|
| ❌ Eliminado | 3 archivos basura en raíz (comandos psql rotos, `tema'`) |
| ❌ Eliminado | 3 archivos runtime de Celery (`celerybeat-schedule`, exchanges) |
| 📁 Movido | `test_auditoria_datos_orquestador.py` → `tests/` |
| 📁 Movido | `LINKS_ACCESO.md` → `docs/` |
| 🔒 Protegido | `docs/LINKS_ACCESO.md` añadido a `.gitignore` (contiene credenciales) |
| 🧹 Limpiado | 25 directorios `__pycache__` eliminados |

---

*Informe generado el 16 de febrero de 2026 — inspección completa del servidor Portal Energético MME v2.0.0*
