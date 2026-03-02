# Inventario Completo del Servidor — Portal Energético MME

> Generado: Marzo 2026 | Auditoría FASE 1

---

## 1. Infraestructura

| Componente | Detalle |
|---|---|
| **SO** | Ubuntu Linux (Azure VM) |
| **Python** | 3.12 |
| **Disco (proyecto)** | 759 MB (excl. venv) |
| **RAM / vCPU** | Azure VM estándar |

### 1.1 Servicios Activos (systemd)

| Servicio | Puerto | Descripción |
|---|---|---|
| `nginx` | 80/443 | Reverse proxy → 8050 (Dash) & 8000 (API) |
| `dashboard-mme` | 8050 (loopback) | Dash/Plotly via Gunicorn (17 workers) |
| `api-mme` | 8000 (loopback) | FastAPI via Gunicorn (4 workers) |
| `celery-worker@1` | — | Worker pool 1 (ETL + anomalías) |
| `celery-worker@2` | — | Worker pool 2 (ETL + anomalías) |
| `celery-beat` | — | Scheduler (4 tareas programadas) |
| `celery-flower` | 5555 | Celery monitoring UI |
| `postgresql@16-main` | 5432 (loopback) | PostgreSQL 16 |
| `redis-server` | 6379 (loopback) | Broker Celery + caché API |
| MLflow (manual) | 5000 | Model Registry & tracking |

### 1.2 Puertos Expuestos

| Puerto | Protocolo | Acceso |
|---|---|---|
| 80 | HTTP | Público (NGINX) |
| 443 | HTTPS | Público (NGINX) |
| 8001 | HTTP | Público (Uvicorn - WhatsApp Bot) |
| 5000 | HTTP | Público (MLflow) |

### 1.3 Cron Jobs (10 activos)

| Horario | Tarea | Script |
|---|---|---|
| `30 6 * * *` | ETL Transmisión (7 días) | `etl/etl_transmision.py` |
| `@reboot` | Auto-start API | `api/start_api_daemon.sh` |
| `*/5 * * * *` | Monitor/auto-recovery API | `scripts/monitor_api.sh` |
| `0 * * * *` | ArcGIS XM dual (horario) | `scripts/arcgis/ejecutar_dual.sh xm` |
| `30 * * * *` | ArcGIS OneDrive dual (horario) | `scripts/arcgis/ejecutar_dual.sh onedrive` |
| `0 */6 * * *` | ETL métricas XM PostgreSQL | `etl/etl_todas_metricas_xm.py` |
| `0 2 * * 0` | Predicciones semanales | `scripts/actualizar_predicciones.sh` |
| `0 3 * * 0` | Backup metrics (retención 4 sem) | `pg_dump -t metrics` |
| `0 4 1 * *` | Backfill Sistema mensual | `scripts/backfill_sistema_metricas.py` |
| `0 8 * * *` | Monitor calidad predicciones | `scripts/monitor_predictions_quality.py` |

### 1.4 Celery Beat Schedule (4 tareas)

| Tarea | Schedule | Módulo |
|---|---|---|
| `etl_incremental_all_metrics` | Cada 6h (0:00, 6:00…) | `tasks.etl_tasks` |
| `clean_old_logs` | 3:00 AM diario | `tasks.etl_tasks` |
| `check_anomalies` | Cada 30 min | `tasks.anomaly_tasks` |
| `send_daily_summary` | 8:00 AM diario | `tasks.anomaly_tasks` |

---

## 2. Base de Datos PostgreSQL

**Base de datos:** `portal_energetico` | **Total filas:** ~63.8 M

| Tabla | Filas | Tamaño | Columnas | Descripción |
|---|---|---|---|---|
| `metrics_hourly` | 50,127,023 | 12 GB | 9 | Métricas horarias (granularidad hora) |
| `metrics` | 13,700,913 | 2,818 MB | 8 | Métricas diarias agregadas |
| `lineas_transmision` | 53,208 | 15 MB | 23 | Líneas de transmisión SIMEN |
| `predictions` | 1,170 | 928 KB | 15 | Predicciones ML |
| `catalogos` | — | 352 KB | 9 | Catálogos de referencia |
| `alertas_historial` | 23 | 296 KB | 29 | Historial de alertas |
| `telegram_users` | — | 104 KB | 7 | Usuarios Telegram registrados |
| `alert_recipients` | — | 64 KB | 10 | Destinatarios de alertas |
| `predictions_quality_history` | — | 64 KB | 12 | Historial calidad predicciones |
| `configuracion_notificaciones` | — | 48 KB | 14 | Config notificaciones |
| `loss_metrics` | — | 48 KB | 8 | Métricas de pérdidas |
| `restriction_metrics` | — | 48 KB | 9 | Métricas de restricciones |
| `commercial_metrics` | — | 32 KB | 6 | Métricas comercialización |

### 2.1 Doble Ruta de Conexión DB

| Ruta | Clase | Usado por |
|---|---|---|
| **Legada** | `DatabaseManager` (manager.py) — singleton `db_manager` | Repositories (CommercialRepo, etc.), servicios directos |
| **Nueva** | `PostgreSQLConnectionManager` (connection.py) → `BaseRepository` | Nuevos repositorios vía herencia |

Ambas apuntan al mismo servidor con las mismas credenciales.

---

## 3. Código Fuente — Inventario Cuantitativo

**Total Python:** 75,674 líneas (excl. venv/backups)
**Total archivos Python:** ~180

### 3.1 Top 15 Archivos por Tamaño

| # | Archivo | Líneas |
|---|---|---|
| 1 | `scripts/train_predictions_sector_energetico.py` | 4,680 |
| 2 | `domain/services/orchestrator_service.py` | 4,197 |
| 3 | `interface/pages/generacion_fuentes_unificado.py` | 3,456 |
| 4 | `interface/pages/metricas.py` | 2,731 |
| 5 | `interface/pages/hidrologia/callbacks.py` | 2,667 |
| 6 | `tasks/anomaly_tasks.py` | 832 |
| 7 | `interface/pages/hidrologia/tables.py` | 1,700+ |
| 8 | `domain/services/executive_report_service.py` | 1,600+ |
| 9 | `domain/services/notification_service.py` | 1,173 |
| 10 | `domain/services/intelligent_analysis_service.py` | 900+ |
| 11 | `interface/pages/hidrologia/data_services.py` | 1,100+ |
| 12 | `interface/pages/distribucion.py` | 1,200+ |
| 13 | `domain/services/report_service.py` | 1,300+ |
| 14 | `whatsapp_bot/telegram_polling.py` | 1,744 |
| 15 | `scripts/train_predictions_postgres.py` | 600+ |

### 3.2 Componentes por Capa

| Capa | Cantidad | Archivos |
|---|---|---|
| **API Routes** | 12 routers | `api/v1/routes/` — generation, metrics, predictions, hydrology, transmission, distribution, commercial, losses, restrictions, system, chatbot, whatsapp_alerts |
| **Dashboard Pages** | 14 páginas | `interface/pages/` — home, generacion, generacion_fuentes_unificado, generacion_hidraulica_hidrologia, transmision, distribucion, perdidas, restricciones, comercializacion, metricas, metricas_piloto, seguimiento_predicciones, config + hidrologia (8 submodules) |
| **Domain Services** | 24 servicios | `domain/services/` — orchestrator, notification, generation, metrics, commercial, distribution, transmission, hydrology, losses, restrictions, predictions, predictions_extended, ai_service, intelligent_analysis, executive_report, report, news, system, validators, confianza_politica, indicators, metrics_calculator, geo, data_loader |
| **Repositories** | 6 repos | `infrastructure/database/repositories/` — base, metrics, commercial, distribution, transmission, predictions |
| **ETL** | 8 scripts | `etl/` — etl_todas_metricas_xm, etl_transmision, etl_xm_to_postgres, etl_ideam, etl_rules, config_metricas, validaciones, validaciones_rangos |
| **Celery Tasks** | 2 módulos | `tasks/` — etl_tasks, anomaly_tasks |
| **WhatsApp Bot** | 16 archivos | `whatsapp_bot/` — 5,815 líneas total |
| **Scripts** | 20+ archivos | `scripts/` — predicciones, ArcGIS, diagnósticos, backfill, monitoreo |
| **ML/Predictions** | 3 scripts | train_predictions_sector_energetico (4,680 LOC), train_predictions_postgres (600+), monitor_predictions_quality |
| **ArcGIS** | 4 archivos | actualizar_capa_hospedada, actualizar_datos_xm_online, actualizar_desde_onedrive, ejecutar_dual.sh |

---

## 4. Hallazgos de Código Muerto / Duplicado

### 4.1 SmartDict duplicado en `core/constants.py`

- **Línea 417:** Primera definición `class SmartDict(dict)` + `UIColors = SmartDict(...)` (básica)
- **Línea 462:** Segunda definición `class SmartDict(dict)` (robusta, case-insensitive) + `UIColors = SmartDict(...)` con colores de dominio
- **Impacto:** La segunda sobrescribe la primera; la primera es código muerto
- **Acción:** ELIMINAR primera definición (líneas 417-460)

### 4.2 Debug write en producción — `generacion_fuentes_unificado.py`

- **Línea 2017-2020:** `with open(debug_file, "a") as f:` escribe en `logs/debug_callback.log`
- **Impacto:** I/O innecesario en cada callback de la página de generación
- **Acción:** ELIMINAR bloque de escritura debug

### 4.3 Prometheus counter sin uso — `core/app_factory.py`

- **Línea 61-62:** `redis_cache_operations` definido pero nunca `.inc()`
- **Impacto:** Métrica siempre en 0 en Prometheus
- **Acción:** Mantener (futuro uso con Redis cache) — no es código muerto, es métrica preparada

### 4.4 `_register_pages()` comentado — `core/app_factory.py`

- **Línea 96:** Función definida con `pass` (importaciones comentadas)
- **Línea 250:** `# _register_pages()` — comentada porque Dash auto-discovery maneja el registro
- **Impacto:** Nulo (Dash usa `use_pages=True` con auto-discovery)
- **Acción:** ELIMINAR función vacía

### 4.5 Archivos que NO son código muerto (confirmado)

| Archivo | Estado | Evidencia |
|---|---|---|
| `whatsapp_bot/app/telegram_handler.py` | ✅ ACTIVO | Importado por `whatsapp_bot/app/main.py` |
| `interface/components/header.py` | ✅ ACTIVO | Header global, importado por `app_factory.py` |
| `interface/components/layout.py` | ✅ ACTIVO | Componentes per-page, usado por 10+ páginas |
| `whatsapp_bot/orchestrator_context.py` | ❌ NO EXISTE | Archivo ya eliminado o nunca existió |

### 4.6 DI Incompleta en API Routes

- **2/12 rutas** usan `Depends()` para inyección de servicios (metrics, predictions)
- **10/12 rutas** instancian servicios directamente
- **Impacto:** Testabilidad reducida en 10 rutas
- **Acción:** Deuda técnica FASE 6

---

## 5. Tests

| Métrica | Valor |
|---|---|
| Tests pasando | 117/117 |
| Tests deseleccionados | 10 (integración/async) |
| Tests fallando | 0 |
| Cobertura estimada | ~35-40% |

---

## 6. Resumen de Salud del Sistema

| Área | Estado | Nota |
|---|---|---|
| **Servicios** | ✅ Todos activos | 11 servicios systemd running |
| **Base de datos** | ✅ Operativa | 63.8M filas, 14.8 GB |
| **Tests** | ✅ 117/117 | 0 fallos |
| **Código muerto** | ⚠️ Menor | SmartDict dup + debug write (FASE 5) |
| **Deuda técnica** | ⚠️ Moderada | DI 2/12, doble ruta DB |
| **Seguridad** | ✅ API Key | Todas las rutas protegidas |
| **ML/Predicciones** | ✅ 13 métricas | Entrenamiento semanal, MAPE élite |
| **Monitoreo** | ✅ Activo | Prometheus, health check, Flower, Telegram alerts |
