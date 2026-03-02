# Arquitectura E2E — Portal Energético MME

> Generado: Marzo 2026 | Auditoría FASE 2

---

## 1. Diagrama de Arquitectura General

```
┌────────────────────────────────────────────────────────────────┐
│                         INTERNET                                │
│  Usuarios / ArcGIS Enterprise / XM API / IDEAM / Telegram      │
└───────┬───────────────────────┬────────────────────┬───────────┘
        │ :80/:443              │ :8001               │
┌───────▼───────────────────────▼────────────────────▼───────────┐
│                        NGINX (reverse proxy)                    │
│  /api/*  → 127.0.0.1:8000    (FastAPI via Gunicorn)            │
│  /*      → 127.0.0.1:8050    (Dash via Gunicorn 17 workers)   │
│  :8001   → pass-through      (WhatsApp/Telegram Bot)           │
│  Gzip, static cache 1h, WebSocket support, security headers    │
└───────┬───────────────────────┬────────────────────────────────┘
        │                       │
┌───────▼──────────┐   ┌───────▼──────────────────────┐
│   FastAPI :8000   │   │    Dash/Plotly :8050          │
│   (api-mme)       │   │    (dashboard-mme)            │
│                   │   │                               │
│  12 routers       │   │  14 páginas + 8 sub-hidrología│
│  Rate limiting    │   │  Callbacks interactivos       │
│  API Key auth     │   │  Gráficos Plotly              │
│  Redis cache      │   │  Chat widget integrado        │
│  Depends() DI     │   │  Header corporativo fijo      │
└───────┬──────────┘   └───────┬──────────────────────┘
        │                       │
        └───────────┬───────────┘
                    │
       ┌────────────▼────────────┐
       │    DOMAIN SERVICES      │
       │    (24 servicios)       │
       │                         │
       │  Orchestrator (4,197 L) │
       │  Notification (1,173 L) │
       │  Generation / Metrics   │
       │  Predictions / Reports  │
       │  AI / Analysis / News   │
       └────────────┬────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
┌───▼───┐   ┌──────▼──────┐   ┌───▼────────┐
│ Repos  │   │   DB Mgr    │   │  External   │
│(Clean) │   │  (Legacy)   │   │  Adapters   │
│ 5+base │   │  singleton  │   │             │
│Connection│  │  manager.py │   │ XM API      │
│Manager │   │             │   │ IDEAM       │
│        │   │             │   │ ArcGIS      │
└───┬────┘   └──────┬──────┘   │ OpenAI      │
    │               │          │ Telegram    │
    └───────┬───────┘          │ SMTP/Gmail  │
            │                  └─────────────┘
    ┌───────▼───────┐
    │  PostgreSQL    │
    │  16-main       │
    │  13 tablas     │
    │  63.8M filas   │
    │  14.8 GB       │
    └───────┬────────┘
            │
    ┌───────▼───────┐     ┌──────────────┐
    │    Redis       │     │   MLflow      │
    │  :6379         │     │  :5000        │
    │  DB0: broker   │     │  Model        │
    │  DB1: results  │     │  Registry     │
    │  Cache API     │     │  13 métricas  │
    │  Dedup locks   │     │  Prophet+ARIMA│
    └────────────────┘     └──────────────┘
```

---

## 2. Flujos E2E Principales

### 2.1 Flujo: Usuario → Dashboard → Gráfico

```
1. Browser GET /generacion
2. NGINX → Gunicorn :8050
3. Dash page_container → interface/pages/generacion.py
4. dash.register_page() auto-discovery
5. Layout rendered → callbacks registrados
6. Callback triggered → domain/services/generation_service.py
7. Service → infrastructure/database/repositories/metrics_repository.py
8. Repository → PostgreSQL (metrics_hourly / metrics)
9. DataFrame → Plotly figure → JSON response → Browser render
```

### 2.2 Flujo: API Request → JSON Response

```
1. Client GET /api/v1/generation/summary?metric=Generacion_Total
2. NGINX → Gunicorn :8000 → FastAPI
3. api/v1/routes/generation.py → @router.get()
4. Depends(get_api_key) → validación API key
5. Redis cache check (TTL hit?) → return cached
6. Service instantiation → GenerationService()
7. Service → MetricsRepository → PostgreSQL
8. DataFrame → schema validation → JSON response
9. Redis cache set (TTL) → return to client
```

### 2.3 Flujo: ETL XM → PostgreSQL

```
1. Cron: 0 */6 → etl/etl_todas_metricas_xm.py
   OR Celery Beat → tasks.etl_tasks.etl_incremental_all_metrics
2. config_metricas.py → lista de métricas + URLs SIMEM
3. Por cada métrica:
   a. infrastructure/external/xm_adapter.py → API XM/SIMEM
   b. etl_rules.py → normalización + validaciones
   c. validaciones.py → rangos, nulos, duplicados
   d. INSERT/UPSERT → metrics + metrics_hourly
4. Log → logs/etl_postgresql_cron.log
```

### 2.4 Flujo: Predicciones ML (Semanal)

```
1. Cron: 0 2 * * 0 → scripts/actualizar_predicciones.sh
2. → scripts/train_predictions_sector_energetico.py (4,680 LOC)
3. Por cada métrica (13):
   a. Query PostgreSQL → datos históricos
   b. Prophet model → train + forecast
   c. ARIMA model → train + forecast
   d. Ensemble (weighted) → predicción final
   e. MLflow → log model + metrics (MAPE, RMSE, etc.)
   f. INSERT → predictions table
4. → scripts/monitor_predictions_quality.py (diario 8 AM)
   a. Compara predicción vs dato real
   b. MAPE < 5% → OK, ≥ 15% → alerta Telegram
```

### 2.5 Flujo: Detección de Anomalías (cada 30 min)

```
1. Celery Beat → tasks.anomaly_tasks.check_anomalies
2. Redis lock check (dedup) → si lock activo, skip
3. Por cada métrica:
   a. Query últimas 24h → metrics_hourly
   b. Cálculo z-score, percentiles, tendencia
   c. Si anomalía detectada:
      i.  INSERT → alertas_historial (ON CONFLICT DO NOTHING)
      ii. domain/services/notification_service.py
      iii. Telegram Bot → alert_recipients
      iv. Email SMTP → destinatarios configurados
4. Redis lock release
```

### 2.6 Flujo: Chatbot IA (API + Dashboard Widget)

```
1. POST /api/v1/chatbot/ask   {question: "..."}
2. api/v1/routes/chatbot.py
3. → domain/services/orchestrator_service.py (4,197 LOC)
4. Intent detection → mapeo a servicios
5. Parallel service calls (with timeouts):
   - GenerationService, MetricsService, HydrologyService...
6. → domain/services/ai_service.py → OpenAI GPT
7. Context enrichment + response generation
8. → JSON response → chat widget renders
```

### 2.7 Flujo: ArcGIS Enterprise Sync (Horario)

```
1. Cron: 0 * * * * → scripts/arcgis/ejecutar_dual.sh xm
2. → scripts/arcgis/actualizar_datos_xm_online.py
3. Query PostgreSQL → últimos datos métricas
4. ArcGIS REST API → Feature Service update
5. Dual: Vice_Energia portal + Adminportal portal
6. Cron: 30 * * * * → ejecutar_dual.sh onedrive
7. → scripts/arcgis/actualizar_desde_onedrive.py
8. OneDrive/SharePoint → download → parse → ArcGIS update
```

---

## 3. Capas de la Arquitectura (Clean Architecture)

```
┌─────────────────────────────────────────────┐
│              INTERFACE LAYER                  │
│  Dashboard (Dash/Plotly) + API (FastAPI)     │
│  14 pages + 12 routes + components          │
├─────────────────────────────────────────────┤
│              DOMAIN LAYER                    │
│  24 services + models + schemas + interfaces │
│  Business logic, no I/O directo             │
├─────────────────────────────────────────────┤
│           INFRASTRUCTURE LAYER               │
│  database/ (manager, connection, 5 repos)    │
│  external/ (XM adapter, SIMEM)               │
│  logging/ (structured logger)                │
│  etl/ (8 scripts)                            │
│  news/ (scraper)                             │
├─────────────────────────────────────────────┤
│              CORE LAYER                      │
│  config.py (Pydantic Settings)               │
│  container.py (DI Container)                 │
│  constants.py (UI colors, maps)              │
│  exceptions.py (custom exceptions)           │
│  validators.py (data validation)             │
└─────────────────────────────────────────────┘
```

### 3.1 Dependency Injection

**Container:** `core/container.py` — singleton `container`

| Componente | Patrón | Notas |
|---|---|---|
| Repositories (5) | Lazy singleton via container | MetricsRepo, CommercialRepo, etc. |
| Services (5) | Factory via container | GenerationService, MetricsService, etc. |
| DatabaseManager | Global singleton `db_manager` | Ruta legada |
| XMDataSourceAdapter | Lazy singleton via container | API XM |
| Override methods | Mock injection for tests | `override_metrics_repository()` |

**FastAPI DI:** `api/dependencies.py` → `Depends()` 
- ✅ `get_api_key` — ALL 12 routes
- ✅ Service DI — metrics.py, predictions.py  
- ⚠️ Direct instantiation — 10 other routes

---

## 4. Tecnologías

| Categoría | Tecnología |
|---|---|
| Web Framework | Dash 2.x (Plotly) + FastAPI |
| WSGI Server | Gunicorn (gthread, 17+4 workers) |
| Reverse Proxy | NGINX |
| Database | PostgreSQL 16 |
| Cache/Broker | Redis 7.x |
| Task Queue | Celery 5.x (Beat + 2 Workers) |
| ML | Prophet + ARIMA + Ensemble |
| ML Tracking | MLflow |
| AI | OpenAI GPT (chatbot) |
| Mapping | ArcGIS Enterprise REST API |
| Notifications | Telegram Bot API + SMTP/Gmail |
| Config | Pydantic Settings + .env |
| Testing | pytest (117 tests) |
| Monitoring | Prometheus metrics + Celery Flower + health check |

---

## 5. Pipeline ETL — Datos y Transformación

### 5.1 Archivos ETL (3,046 líneas totales)

| Archivo | Líneas | Función |
|---|---|---|
| `etl_xm_to_postgres.py` | 697 | Ingestión genérica XM → PostgreSQL |
| `etl_todas_metricas_xm.py` | 592 | Orquestador: ejecuta todas las métricas XM |
| `config_metricas.py` | 421 | Configuración de 122 métricas (nombre, tipo, API) |
| `etl_rules.py` | 400 | Reglas de validación y transformación |
| `etl_ideam.py` | 324 | ETL datos IDEAM (meteorología/hidrología) |
| `validaciones.py` | 273 | Validaciones de datos post-ETL |
| `validaciones_rangos.py` | 202 | Validación de rangos físicos por métrica |
| `etl_transmision.py` | 137 | ETL líneas de transmisión SIMEN |

### 5.2 Crontab — 10 Jobs Programados

| Schedule | Job | Log |
|---|---|---|
| `*/5 * * * *` | Monitor API + auto-recuperación | stdout |
| `0 * * * *` | ArcGIS XM (dual: Vice_Energia + Adminportal) | `logs/arcgis_dual.log` |
| `30 * * * *` | ArcGIS OneDrive/SharePoint (dual) | `logs/arcgis_dual.log` |
| `30 6 * * *` | ETL Transmisión (últimos 7 días) | `logs/etl/transmision.log` |
| `0 */6 * * *` | ETL PostgreSQL — todas las métricas XM | `logs/etl_postgresql_cron.log` |
| `0 8 * * *` | Verificación predicciones vs datos reales | `logs/etl/quality_monitor.log` |
| `0 2 * * 0` | Actualización semanal predicciones ML | vía script |
| `0 3 * * 0` | Backup semanal tabla metrics (pg_dump) | `logs/backup_metrics.log` |
| `0 4 1 * *` | Backfill mensual métricas Sistema (90 días) | `logs/backfill_mensual.log` |
| `@reboot` | Auto-arranque API (sleep 30 + daemon) | `logs/api-startup.log` |

### 5.3 Pipeline ArcGIS Enterprise (2,797 líneas)

| Script | Líneas | Función |
|---|---|---|
| `actualizar_desde_onedrive.py` | 1,202 | Sincroniza archivos OneDrive/SharePoint → ArcGIS |
| `actualizar_datos_xm_online.py` | 800 | Publica datos XM en capas ArcGIS Online |
| `actualizar_capa_hospedada.py` | 708 | Actualiza capas hospedadas en ArcGIS Enterprise |
| `ejecutar_dual.sh` | 87 | Orquestador dual: ejecuta para Vice_Energia + Adminportal |

**Flujo**: Crontab → `ejecutar_dual.sh {xm|onedrive}` → script Python → ArcGIS REST API → Capas publicadas.

---

## 6. Base de Datos PostgreSQL

### 6.1 Esquema (13 tablas)

| Tabla | Filas | Descripción |
|---|---|---|
| `metrics` | 13,700,913 | Datos diarios XM (122 métricas distintas) |
| `metrics_hourly` | 50,127,023 | Datos horarios XM (24h × recursos) |
| `lineas_transmision` | 53,208 | Datos red de transmisión SIMEN |
| `predictions` | 1,170 | Predicciones ML activas (13 fuentes × 90 días) |
| `predictions_quality_history` | 24 | Historial auditoría ex-post predicciones |
| `telegram_users` | 5 | Usuarios registrados Telegram bot |
| `alert_recipients` | 5 | Destinatarios alertas energéticas |
| `configuracion_notificaciones` | — | Config notificaciones por tipo |
| `alertas_historial` | — | Registro histórico de alertas enviadas |
| `catalogos` | — | Catálogos de referencia |
| `loss_metrics` | 0 | Métricas de pérdidas (pendiente ETL) |
| `restriction_metrics` | 0 | Métricas restricciones (pendiente ETL) |
| `commercial_metrics` | 0 | Métricas comercialización (pendiente ETL) |

### 6.2 Top 10 Métricas por Volumen

| Métrica | Registros |
|---|---|
| DDVContratada | 2,968,022 |
| ENFICC | 2,964,339 |
| ObligEnerFirme | 2,964,310 |
| CapEfecNeta | 1,056,031 |
| DispoDeclarada | 576,527 |
| DispoCome | 569,349 |
| Gene | 534,554 |
| DemaCome | 188,828 |
| DemaReal | 186,419 |
| DispoReal | 149,319 |

### 6.3 Métricas con Mayor Rezago (stale data)

| Métrica | Último dato | Rezago (días) | Causa |
|---|---|---|---|
| ExcedenteAGPE | 2021-11-30 | 1,552 | XM dejó de publicar esta métrica |
| DesvGenVariableRedesp | 2024-08-20 | 558 | Datos suspendidos por XM |
| DesvGenVariableDesp | 2024-08-20 | 558 | Datos suspendidos por XM |
| PrecEscaAct | 2025-02-28 | 366 | Publicación anual |
| IrrPanel / IrrGlobal / TempPanel / TempAmbSolar | 2025-12-16 | 75 | IDEAM — estaciones solares con retraso |
| CERE | 2026-01-01 | 59 | Publicación mensual, pendiente actualización |
| IndRecMargina | 2026-01-31 | 29 | Publicación mensual |

> **Nota**: Los rezagos > 30 días son causados por la fuente externa (XM/IDEAM), no por fallas ETL.

---

## 7. Dashboard — 14 Páginas Dash

### 7.1 Inventario de Páginas

| Página | Líneas | Callbacks | Área |
|---|---|---|---|
| generacion_fuentes_unificado.py | 3,406 | 11 | Generación por fuente (principal) |
| metricas.py | 2,517 | 14 | Explorer métricas genérico |
| distribucion.py | 1,210 | 3 | Distribución y demanda |
| seguimiento_predicciones.py | 996 | 3 | Seguimiento ML predicciones |
| comercializacion.py | 735 | 4 | Comercialización / precios |
| transmision.py | 688 | 3 | Red de transmisión |
| home.py | 519 | 1 | Portada interactiva |
| generacion.py | 470 | 1 | Generación general |
| restricciones.py | 381 | 2 | Restricciones SIN |
| perdidas.py | 341 | 2 | Pérdidas de energía |
| metricas_piloto.py | 92 | 1 | Piloto métrica individual |
| config.py | 73 | 0 | Config Dash pages |
| generacion_hidraulica_hidrologia.py | 27 | 0 | Stub (redirige a fuentes) |
| __init__.py | 1 | 0 | Package init |

**Total**: ~10,456 líneas de código, 45 callbacks activos.

---

## 8. Sistema de Predicciones ML

### 8.1 Modelos Activos

- **Algoritmos**: Prophet + ARIMA + Ensemble (promedio ponderado)
- **Horizonte**: 90 días a futuro
- **Actualización**: Semanal (domingo 2:00 AM)
- **Tracking**: MLflow (métricas MAPE, RMSE por fuente)

### 8.2 13 Fuentes de Predicción

| Fuente | Predicciones | Rango |
|---|---|---|
| Hidráulica | 90 | feb 2026 → may 2026 |
| Térmica | 90 | feb 2026 → may 2026 |
| Solar | 90 | feb 2026 → may 2026 |
| Eólica | 90 | feb 2026 → may 2026 |
| Biomasa | 90 | feb 2026 → may 2026 |
| GENE_TOTAL | 90 | feb 2026 → may 2026 |
| DEMANDA | 90 | feb 2026 → may 2026 |
| APORTES_HIDRICOS | 90 | feb 2026 → may 2026 |
| EMBALSES | 90 | feb 2026 → may 2026 |
| EMBALSES_PCT | 90 | feb 2026 → may 2026 |
| PRECIO_BOLSA | 90 | feb 2026 → may 2026 |
| PRECIO_ESCASEZ | 90 | feb 2026 → may 2026 |
| PERDIDAS | 90 | feb 2026 → may 2026 |

### 8.3 Auditoría Ex-Post (Quality History)

El sistema verifica automáticamente (8:00 AM diario via `monitor_predictions_quality.py`):

| Campo | Descripción |
|---|---|
| `mape_expost` | Error porcentual absoluto medio contra datos reales |
| `rmse_expost` | Error cuadrático medio contra datos reales |
| `mape_train` / `rmse_train` | Métricas de entrenamiento para comparar drift |
| `notas` | Alertas automáticas: `OK` o `🟡 DRIFT: MAPE ex-post > 2× MAPE train` |

**Último ciclo** (2026-02-28, 24 evaluaciones):
- Biomasa: `🟡 DRIFT` — MAPE ex-post 13.1% > 2× MAPE train 6.1%
- Solar: OK — MAPE ex-post 14.0% (vs train 18.8%, mejorando)
- Eólica: OK — MAPE ex-post 9.1% (excelente)

---

## 9. Deuda Técnica — Estado y Recomendaciones

### 9.1 Resuelto en esta auditoría

| Issue | Acción | Impacto |
|---|---|---|
| Debug file writes en producción | Eliminado de `generacion_fuentes_unificado.py` | -6 LOC, no más escritura a `debug_callback.log` |
| `_register_pages()` función muerta | Eliminada de `app_factory.py` | -18 LOC, código limpio |
| `categorizar_fuente_xm` ×5 duplicados | Consolidado en una función top-level | -64 LOC, un solo punto de mantenimiento |
| `UIColors` ×3 definiciones redundantes | Unificado: SmartDict + colors_data | -50 LOC, una sola fuente de verdad |
| `httpx` 0.28.1 → 0.27.2 | Pin de versión en requirements.txt | 14 errores de test API corregidos |
| 37 tests fallando (sesión anterior) | Mocks actualizados a APIs reales | 117/117 passing |
| Celery deprecation warning ×88/día | `broker_connection_retry_on_startup=True` | 0 warnings |
| `sistema_notificaciones.py` muerto | Movido a `backups/deprecated/` | Sin imports rotos |
| Git post-commit hook roto | Deshabilitado (referenciaba archivo inexistente) | Commits limpios |

### 9.2 Deuda técnica pendiente

| Prioridad | Issue | Ubicación | Recomendación |
|---|---|---|---|
| 🟡 Media | `generacion_fuentes_unificado.py` (3,406L) | `interface/pages/` | Separar en módulos: layout, callbacks, data_utils |
| 🟡 Media | `train_predictions_sector_energetico.py` (4,680L) | `scripts/` | Extraer a clases por tipo de modelo |
| 🟡 Media | `orchestrator_service.py` (4,197L) | `domain/services/` | Separar intents en handlers individuales |
| 🟢 Baja | 3 tablas vacías (loss/restriction/commercial_metrics) | DB | Implementar ETL cuando haya datos disponibles |
| 🟢 Baja | `get_plotly_modules()` ×9 copias | Dashboard pages | Patrón de lazy-import aceptable, no crítico |
| 🟢 Baja | `telegram_handler.py` (14.8 KB) | `whatsapp_bot/app/` | Importado activamente — revisar si Telegram sigue en uso |
| 🟢 Baja | TODOs en API routes | `api/v1/routes/` | 3 TODOs: contratos, flujos, activo/inactivo |

### 9.3 Estadísticas del codebase

| Métrica | Valor |
|---|---|
| Archivos Python (sin venv/backups) | ~120 |
| Líneas de código Python | ~74,500 |
| Tests automatizados | 117 (100% passing) |
| Cobertura estimada | Servicios de dominio: ~85%, UI: ~5% |
| Dashboard callbacks | 45 activos |
| Métricas ETL | 122 distintas |
| Predicciones ML activas | 1,170 (13 fuentes × 90 días) |
| Base de datos | 63.9M filas (metrics + hourly + transmision) |

---

## 10. Historial de Cambios — Auditoría Marzo 2026

| Fecha | FASE | Descripción |
|---|---|---|
| 2026-03-01 | FASE 1 | Inventario completo del servidor |
| 2026-03-01 | FASE 2 | Documentación arquitectura E2E |
| 2026-03-01 | FASE 3 | Documentación ETL/DB/ArcGIS |
| 2026-03-01 | FASE 4 | Documentación Dashboard/ML |
| 2026-03-01 | FASE 5 | Limpieza código muerto (-138 LOC) |
| 2026-03-01 | FASE 6 | Evaluación deuda técnica + fix httpx |
| 2026-03-01 | FASE 7 | Documentación final |
| 2026-03-01 | FASE 8 | Restart servicios + commit |
