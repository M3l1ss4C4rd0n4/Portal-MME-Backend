# Server Backend - Portal Dirección MME

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688)
![Dash](https://img.shields.io/badge/Dash-2.17.1-19A7CE)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Architecture](https://img.shields.io/badge/Architecture-Hexagonal-purple)

**Backend del Portal de Dirección de Energía Eléctrica**  
API REST + Dashboard Analítico + ETL Pipeline

</div>

---

## 📋 Índice

1. [Visión General](#visión-general)
2. [Arquitectura](#arquitectura)
3. [Estructura del Proyecto](#estructura-del-proyecto)
4. [Servicios de Dominio](#servicios-de-dominio)
5. [API Endpoints](#api-endpoints)
6. [ETL Pipeline](#etl-pipeline)
7. [Instalación](#instalación)
8. [Despliegue](#despliegue)
9. [Monitoreo y Logs](#monitoreo-y-logs)

---

## Visión General

Servidor backend multi-propósito para el Portal de Dirección MME. Proporciona:

- **API REST** (FastAPI): **115 endpoints** en 32 archivos de rutas (`api/v1/routes/`) para consumo del frontend Next.js y de la app móvil EnergIA, incluyendo el tablero de balance oferta-demanda del SIN (5 endpoints, 29-sep)
- **Dashboard Analítico** (Dash): tableros interactivos legacy
- **ETL Pipeline**: Extracción automática de datos de XM, IDEAM, OneDrive/SharePoint, despacho diario XM en PDF, hidrocarburos (Excel + scraping de precios WTI/Brent), y normativa CREG/UPME/MME (scraping de gestores normativos oficiales)
- **Sistema de Alertas**: Notificaciones Telegram/email basadas en anomalías, con marco regulatorio explícito (Índice NE/HSIN/PBP citando resoluciones CREG) y vigilancia automática de cambios normativos
- **Capa de Ontología** (esquema Postgres `ontologia`): dimensiones de geografía/empresa/proyecto/métrica/recurso, grafo de relaciones multi-hop, y un corpus RAG (búsqueda semántica híbrida vector+full-text) sobre informes de XM/CREG/UPME/MME/SharePoint — ver `docs/FUENTES_RAG.md`
- **Asistente IA** (`api/v1/routes/chatbot.py` + `domain/services/asistente_ia_service.py`, ~1.440 líneas): agente conversacional con ~45 herramientas (tool-calling), failover automático entre proveedores (Gemini → Groq → OpenRouter), y **voz en tiempo real** (`api/v1/routes/voz.py`, Gemini Live API)
- **Sistema de predicciones con validación rigurosa**: ensemble Prophet+SARIMAX con backtest out-of-sample real (no solo holdout de entrenamiento) — ver `docs/tecnicos/PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md`
- **CU (Costo Unitario)**: cálculo mayorista y minorista (tarifa usuario final por operador de red), ponderado por demanda real — ver `docs/METODOLOGIA_CU.md`

### Estadísticas (verificadas 2026-09-30)

- **464 archivos Python** (excluyendo entornos virtuales)
- **43 servicios de dominio** (`domain/services/*.py`, nivel raíz — sin contar subcarpetas `orchestrator/`, `report_chapters/`)
- **115 endpoints REST** en 32 archivos de rutas (incluye el tablero de balance oferta-demanda, agregado el 29-sep)
- **44 migraciones SQL** (`sql/migrations/`)
- **438 tests pasando, 0 fallando** (10 deseleccionados; `pytest tests/ -q`)
- **17 interfaces de dominio** (`domain/interfaces/`) con inyección de dependencias activa

### Seguridad (revisión del 10-sep, controles aplicados el 29-sep)

Auditoría de seguridad del servidor y de los dos repositorios: se eliminó una clave de API con
valor por defecto en el código, se añadieron límites de uso por minuto a los endpoints más costosos
(generación de PDF, audio del Asistente IA, difusión de alertas), y se cerró la política de CORS
del bot de WhatsApp a una lista explícita de dominios del Ministerio. Ver `api/dependencies.py` y
el commit `291df26`.

---

## Arquitectura

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENTES                            │
│     (Portal Next.js / Dashboard Dash / Telegram Bot)       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/HTTPS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      ENTRY POINTS                           │
├─────────────────────────────────────────────────────────────┤
│  api/main.py (FastAPI)              app.py (Dash)          │
│  ├── Puerto: 8000                   ├── Puerto: 8050       │
│  ├── 115 endpoints REST             └── 17 tableros        │
│  └── Autenticación X-API-Key                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│   Domain Layer  │ │   Core      │ │  Infrastructure │
│   (Servicios)   │ │   (DI/Config)│ │   (BD/Cache)   │
└────────┬────────┘ └──────┬──────┘ └────────┬────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES                             │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL 16    Redis 7    XM API    OneDrive    IDEAM   │
│  (15GB, 64M filas)  (Cache)   (Datos)   (Excel)   (Hydro)  │
└─────────────────────────────────────────────────────────────┘
```

### Arquitectura Hexagonal (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────────┐
│                      ADAPTERS                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  REST API   │  │   Dash UI   │  │   Telegram Bot      │ │
│  │  (FastAPI)  │  │  (Legacy)   │  │   (Async)           │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼────────────────────┼────────────┘
          │                │                    │
          └────────────────┴────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │         APPLICATION             │
          │         (Domain Layer)          │
          │  ┌─────────────────────────┐    │
          │  │    43 Services          │    │
          │  │  - cu_service            │    │
          │  │  - report_service        │    │
          │  │  - metrics_service       │    │
          │  │  - ...                   │    │
          │  └─────────────────────────┘    │
          └────────────────┬────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │      INFRASTRUCTURE (Ports)     │
          │  ┌─────────────┐ ┌────────────┐ │
          │  │  Database   │ │   Cache    │ │
          │  │  (PostgreSQL)│ │  (Redis)   │ │
          │  └─────────────┘ └────────────┘ │
          │  ┌─────────────┐ ┌────────────┐ │
          │  │   XM API    │ │  OneDrive  │ │
          │  │   Client    │ │   Client   │ │
          │  └─────────────┘ └────────────┘ │
          └─────────────────────────────────┘
```

---

## Estructura del Proyecto

```
server/
├── api/                          (52 archivos)
│   ├── main.py                   → Entry point FastAPI
│   ├── v1/routes/                → 115 endpoints REST
│   │   ├── restrictions.py
│   │   ├── distribution.py
│   │   ├── system.py
│   │   ├── cu.py
│   │   ├── commercial.py
│   │   ├── generation.py
│   │   └── ...
│   └── dependencies.py           → Inyección FastAPI
│
├── core/                         (24 archivos)
│   ├── app_factory.py            → Factory Dash app
│   ├── container.py              → DependencyContainer (DI)
│   ├── config.py                 → Configuración centralizada
│   ├── database/
│   │   ├── pool.py               → Connection pool PostgreSQL
│   │   └── migration_helper.py   → Helpers migraciones
│   ├── security/
│   │   ├── vault.py              → Gestión de secretos
│   │   └── sql_validator.py      → Validación SQL
│   └── utils/
│       └── date_utils.py         → Utilidades de fechas
│
├── domain/                       (81 archivos)
│   ├── services/                 → 43 servicios (nivel raíz)
│   ├── models/                   → Modelos Pydantic
│   ├── schemas/                  → DTOs y validaciones
│   ├── interfaces/               → 17 interfaces abstractas
│   ├── orchestrator/             → Orquestador del Asistente IA (handlers)
│   └── report_chapters/          → Capítulos del informe ejecutivo
│
├── infrastructure/               (69 archivos)
│   ├── database/                 → Repositorios PostgreSQL
│   ├── cache/                    → Redis cache manager
│   ├── external/                 → Clientes APIs externas
│   │   ├── xm_client.py
│   │   ├── onedrive_client.py
│   │   └── ideam_client.py
│   ├── logging/                  → Sistema de logging
│   └── observability/            → Métricas y health checks
│
├── interface/                    (46 archivos) [LEGACY]
│   └── pages/                    → Páginas Dash (17 páginas registradas)
│
├── etl/                          (30 archivos)
│   ├── etl_todas_metricas_xm.py  → Principal (cada 6h)
│   ├── etl_xm_to_postgres.py     → Backfill manual
│   ├── etl_nuevos_dashboards.py  → Datos dashboard (presupuesto, comunidades, subsidios)
│   └── validaciones_rangos.py    → Validaciones
│
├── tasks/                        → Celery tasks
│   ├── anomaly_tasks.py
│   └── etl_tasks.py
│
├── tests/                        (57 archivos)
│   ├── unit/                     (44 archivos)
│   ├── integration/              (0 archivos) ⚠️
│   └── e2e/                      (0 archivos) ⚠️
│
├── config/
│   └── logrotate-mme.conf        → Config rotación logs
│
├── data/                         → Datos locales
│   ├── base_de_datos_comunidades_energeticas/
│   ├── base_de_datos_contratos_or/
│   ├── base_de_datos_supervision/
│   └── ejecucion_presupuestal/
│
├── logs/                         → Logs de aplicación
│   ├── gunicorn_error.log
│   ├── gunicorn_access.log
│   └── celery/
│
├── docs/                         (21 archivos MD)
├── backups/                      → Backups BD
├── experiments/                  → Experimentos ML
├── scripts/                      (47 archivos)
└── app.py                        → Entry point Dash
```

---

## Servicios de Dominio

### Servicios Principales (por tamaño, verificado 2026-09-01)

| Servicio | Líneas | Función | Estado |
|----------|--------|---------|--------|
| `report_service.py` | 3,584 | Generación de informes (creció ~94% desde la última auditoría) | ✅ Activo — candidato prioritario a refactor, ver `docs/refactoring/ARCHIVOS_GRANDES_PLAN.md` |
| `portal_report_service.py` | 2,819 | Generador del PDF del dashboard de predicciones/portal | ✅ Activo (no listado en versiones anteriores de este README) |
| `executive_report_service.py` | 1,618 | Informes ejecutivos | ✅ Activo |
| `asistente_ia_service.py` | 1,443 | Asistente IA — loop de tool-calling (~45 herramientas), streaming, voz | ✅ Activo (no listado en versiones anteriores de este README) |
| `notification_service.py` | 1,347 | Notificaciones Telegram/email | ✅ Activo |
| `losses_nt_service.py` | 1,208 | Pérdidas no técnicas | ✅ Activo |
| `cu_service.py` | 1,122 | Comercialización mayorista (CU) | ✅ Activo |
| `news_service.py` | 901 | Noticias del sector (multi-fuente, scraping de texto completo) | ✅ Activo (no listado en versiones anteriores de este README) |
| `intelligent_analysis_service.py` | 892 | Análisis con IA | ✅ Activo |
| `predictions_service_extended.py` | 887 | Predicciones ML | ✅ Activo |
| `simulation_service.py` | 748 | Simulaciones CREG | ✅ Activo |
| `cu_minorista_service.py` | 676 | Comercialización minorista (tarifa usuario final) | ✅ Activo |
| `ai_service.py` | 574 | `AgentIA` — integración LLM compartida (informes, WhatsApp) | ✅ Activo — 388 aristas en el grafo, uno de los 10 "god nodes" del sistema |
| `investment_service.py` | 523 | Inversiones | ✅ Activo |
| `distribution_service.py` | 480 | Distribución | ✅ Activo |
| `generation_service.py` | 448 | Generación | ✅ Activo |
| `hydrology_service.py` | 460 | Datos hidrológicos | ✅ Activo |
| `graph_service.py` | — | Grafo de relaciones ontología (empresa/proyecto/geografía) | ✅ Activo (no listado en versiones anteriores) |
| `ontologia_service.py` | — | Capa de ontología semántica + RAG | ✅ Activo (no listado en versiones anteriores) |
| `voz_ia_service.py` | — | Asistente de voz en tiempo real (Gemini Live API) | ✅ Activo (no listado en versiones anteriores) |
| `geo_service.py` | 32 | Georreferenciación | ⚠️ DEPRECATED |
| `orchestrator_service.py` | 4 | Orquestación | ⚠️ DEPRECATED |
| `predictions_service.py` | 10 | Predicciones (stub) | ⚠️ DEPRECATED |

> Tabla no exhaustiva (43 servicios en total en `domain/services/`; ver § "Notas de Arquitectura"
> abajo para las cifras vigentes del grafo de código, regenerado el 2026-09-30).

### Servicios deprecated — con shim de compatibilidad activo (NO eliminar sin migrar antes)

Estos tres archivos están marcados `⚠️ DEPRECATED` en su docstring porque la lógica real ya vive en
otro módulo, pero **hoy siguen siendo importados por código en producción** — verificado el
2026-09-30 con grep de importadores. Borrarlos sin antes migrar cada llamador rompería el portal:

- `geo_service.py` → importado por `interface/pages/hidrologia/callbacks.py` y
  `interface/pages/hidrologia/maps.py` (usa `REGIONES_COORDENADAS`).
- `orchestrator_service.py` → re-exporta desde `domain/services/orchestrator/orchestrator_service.py`;
  importado por `api/v1/routes/chatbot.py`, `api/v1/routes/energia_app.py`, `core/container.py`,
  `scripts/auditoria_datos_orquestador.py` y 2 archivos de test.
- `predictions_service.py` → re-exporta desde `predictions_service_extended.py`; importado por
  `interface/pages/metricas_piloto.py`, `domain/services/executive_report_service.py`,
  `domain/services/orchestrator/orchestrator_service.py` y su test unitario.

---

## API Endpoints

**115 endpoints en total**, distribuidos en 32 archivos de rutas (`api/v1/routes/`). Grupos principales:

| Grupo de rutas | Archivo | Descripción |
|---|---|---|
| Métricas del sector | `metrics.py`, `system.py`, `generation.py`, `hydrology.py`, `commercial.py`, `distribution.py`, `transmission.py`, `restrictions.py`, `losses.py` | Datos operativos del SIN (XM) |
| Predicciones | `predictions.py` | Pronósticos ML + validación rigurosa (backtest out-of-sample) |
| Costo Unitario | `cu.py` | CU mayorista y minorista (tarifa usuario final) |
| **Ontología** | `ontologia.py` (17 endpoints) | Geografía/empresa/proyecto/métrica/recurso, grafo de relaciones, búsqueda RAG |
| **Asistente IA** | `chatbot.py` | Orquestador de intents (~100 mapeados) + Asistente IA con tool-calling |
| **Voz en tiempo real** | `voz.py` | `/v1/voz/token`, `/v1/voz/ws` (Gemini Live API) |
| Informes/reportes | `reports.py`, `informes_tableros.py` | Generación e histórico de informes ejecutivos/PDF |
| Simulación | `simulation.py`, `riesgo.py` | Escenarios CREG, riesgo de atraso de contratos OR |
| Dominios sectoriales | `comunidades.py`, `contratos_or.py`, `fenoge.py`, `subsidios.py`, `presupuesto.py`, `supervision_portal.py` | Comunidades energéticas, contratos OR, FENOGE, subsidios, presupuesto, supervisión |
| **Balance oferta-demanda** (29-sep) | `balance_oferta_demanda.py` (5 endpoints) | Histórico oferta/demanda/margen de reserva del SIN, demanda no atendida por área, proyectos UPME con retraso, correlación MW retrasados vs. margen, simulador contrafactual |
| App móvil / alertas | `energia_app.py`, `energia_dashboard.py`, `whatsapp_alerts.py` | Endpoints para la app EnergIA y alertas de WhatsApp |
| Observabilidad | `observability.py`, `internal.py` | Health checks internos, métricas de sistema |
| `/health` | — | Health check general (JSON con clave `services`, no `checks`) |

Documentación completa: [`docs/GUIA_USO_API.md`](./docs/GUIA_USO_API.md) (reescrita 2026-09-30, cubre los 115 endpoints reales).

### Autenticación

```bash
# Header requerido
X-API-Key: <api_key>

# Ejemplo
curl -H "X-API-Key: tu_api_key" http://localhost:8000/api/v1/restrictions
```

---

## ETL Pipeline

### Scripts Principales

| Script | Frecuencia | Fuente | Descripción |
|--------|------------|--------|-------------|
| `etl_todas_metricas_xm.py` | Cada 6h | XM API | Métricas en tiempo real |
| `etl_xm_to_postgres.py` | Manual | XM API | Backfill histórico |
| `etl_nuevos_dashboards.py` | On-demand | OneDrive | Presupuesto, comunidades |
| `etl_losses_detailed.py` | Diario | XM API | Pérdidas detalladas |
| `etl_transmision.py` | Cada 6h | XM API | Datos de transmisión |

### Scheduling (Celery Beat)

```python
# Configuración en core/config.py o celery_config.py
beat_schedule = {
    'etl-metricas-xm': {
        'task': 'tasks.etl_tasks.run_etl_xm',
        'schedule': crontab(hour='*/6', minute=0),  # Cada 6 horas
    },
    'check-anomalies': {
        'task': 'tasks.anomaly_tasks.detect_anomalies',
        'schedule': crontab(minute='*/30'),  # Cada 30 minutos
    },
}
```

---

## Instalación

### Requisitos

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- 4GB RAM mínimo
- 20GB espacio en disco

### Pasos

```bash
# 1. Clonar repositorio
git clone <url-repositorio> server
cd server

# 2. Crear entorno virtual
python3.12 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
nano .env  # Editar con credenciales reales

# 5. Inicializar base de datos
python scripts/init_db.py

# 6. Ejecutar tests
pytest tests/ -v

# 7. Iniciar servicios
# Terminal 1: API
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Dashboard
python app.py

# Terminal 3: Celery Worker
celery -A tasks worker --loglevel=info

# Terminal 4: Celery Beat
celery -A tasks beat --loglevel=info
```

---

## Despliegue

### Producción (systemd)

```bash
# API FastAPI
sudo systemctl status portal-api.service
sudo systemctl restart portal-api.service

# Dashboard Dash
sudo systemctl status dashboard-mme
sudo systemctl restart dashboard-mme

# Celery
sudo systemctl status celery-worker
sudo systemctl restart celery-worker

sudo systemctl status celery-beat
sudo systemctl restart celery-beat
```

### Configuración Gunicorn

```python
# gunicorn_config.py
bind = "127.0.0.1:8050"
workers = 5
worker_class = "gthread"
threads = 2
timeout = 120
max_requests = 1000
```

---

## Monitoreo y Logs

### Rotación de Logs

Configuraciones activas en `/etc/logrotate.d/`:

| Archivo | Contenido | Rotación |
|---|---|---|
| `server-mme` | Logs generales + celery | Diaria, 14 días, comprimido (copytruncate) |
| `telegram-polling` | Logs del bot Telegram | Diaria, 7 días, comprimido (copytruncate) |

```bash
# Verificar configuración activa
sudo logrotate -d /etc/logrotate.d/server-mme

# Forzar rotación manual
sudo logrotate -f /etc/logrotate.d/server-mme
```

> ⚠️ La configuración activa está en `/etc/logrotate.d/`. El archivo `config/logrotate-mme.conf` es una referencia local.

### Métricas Clave

| Métrica | Valor Esperado | Alerta si |
|---------|----------------|-----------|
| Uptime API | >99% | <95% |
| Tiempo respuesta API | <200ms | >500ms |
| Errores 5xx | <1% | >5% |
| Conexiones BD | <80% pool | >95% pool |
| Uso RAM | <70% | >90% |

### Logs Importantes

```bash
# API
 tail -f logs/gunicorn_error.log
 tail -f logs/gunicorn_access.log

# Celery
 tail -f logs/celery/worker-1.log
 tail -f logs/celery/worker-2.log

# ETL
 tail -f logs/etl_postgresql_cron.log
```

---

## Documentación Adicional

> **Nota (2026-09-01):** los 2 enlaces que aparecían aquí antes (`ARQUITECTURA_E2E.md`, `INDICE.md`) apuntaban a archivos que no existen — corregido. Una auditoría completa de ~25 documentos del proyecto encontró varios más en el mismo estado (ver "Deuda documental" abajo).

**Vigentes y verificados:**
- [Fuentes del corpus RAG](./docs/FUENTES_RAG.md) — el mejor mantenido del set, verificado línea por línea
- [Metodología de Costo Unitario](./docs/METODOLOGIA_CU.md) — incluye §9.14, ponderación por demanda real (2026-08)
- [Predicciones de embalses — validación rigurosa](./docs/tecnicos/PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md) (2026-08)
- [Análisis Hidrológico y Semáforo de Riesgos](./docs/tecnicos/ANALISIS_HIDROLOGIA_SEMAFORO.md) — incluye §10, distinción Índice NE (CREG) vs. IDEAM/UNGRD (2026-08)
- [Guía de Troubleshooting](./docs/GUIA_TROUBLESHOOTING.md) (corregida 2026-09-30, ver nota abajo)
- [Contenido del Informe Ejecutivo](./docs/INFORME_EJECUTIVO_CONTENIDO.md)
- [Nota — fila de totales en Excel](./docs/tecnicos/NOTA_FILA_TOTALES_EXCEL.md)
- [Uso de API](./docs/GUIA_USO_API.md) — reescrita 2026-09-30, cubre los 115 endpoints reales en 32 archivos
- [Runbook de Producción](./RUNBOOK_PRODUCCION.md) — sincronizado 2026-09-30 (servicios systemd completos, sin contradicción entre secciones, balance oferta-demanda y seguridad agregados)
- [Guía de Onboarding](./docs/GUIA_ONBOARDING.md) — enlaces corregidos 2026-09-30

**Necesitan actualización** (ver auditoría completa en `docs/AUDITORIA_DOCUMENTACION_2026-09.md`):
- Ninguno pendiente de los señalados por esa auditoría al 2026-09-30 — ver "Deuda documental" abajo
  para el detalle de lo que se corrigió en cada ronda.

---

## Deuda documental (auditoría 2026-09-01)

Una auditoría completa de ~25 documentos `.md` del proyecto (contra el código real, no solo lectura visual) encontró que varios habían quedado desactualizados tras meses de crecimiento del sistema — ver detalle completo en `docs/AUDITORIA_DOCUMENTACION_2026-09.md`. Resumen:

- **2 documentos obsoletos, recomendados para borrar** (superados por otros ya vigentes): `docs/tecnicos/DOCUMENTACION_TECNICA_IA_ML.md` (arquitectura SQLite/Dash pre-PostgreSQL, dic-2025), `docs/tecnicos/README_SEMAFORO.md` (matriz de riesgo ya desautorizada por `ANALISIS_HIDROLOGIA_SEMAFORO.md`).
- **Hallazgo operativo crítico**: `RUNBOOK_PRODUCCION.md` documentaba rutas de logs de la API (`logs/api-error.log`) que no existen — la ruta real es `/var/log/portal-api.log` (systemd `StandardOutput`/`StandardError`). `AGENTS.md` documentaba un pool de conexiones async (`asyncpg`/`get_pool()`) que tampoco existe — la conexión real es `psycopg2.ThreadedConnectionPool` vía `infrastructure/database/connection.py`.
- **Hallazgo operativo crítico #2**: `whatsapp_bot/GUIA_TELEGRAM_BOT_PASO_A_PASO.md` instruye configurar un webhook de Telegram — si se sigue, **rompería el bot real en producción**, que usa `long polling` (`telegram_polling.py`/`telegram-polling.service`) y no puede coexistir con un webhook activo.
- **Patrón sistémico**: 5+ enlaces rotos repetidos en varios documentos (`ARQUITECTURA_E2E.md`, `INDICE.md`, `DOCUMENTACION_TECNICA_ORQUESTADOR.md`, `MAPEO_COMPLETO_METRICAS.md`, `INVENTARIO_SERVIDOR.md` — ninguno existe).
- **`api/README.md`** documentaba ~2 de los 30 archivos de rutas reales y no mencionaba Ontología, Asistente IA, Voz ni CU — corregido el mismo día (ver nota al pie del propio archivo); hoy cubre los 115 endpoints en 32 archivos, incluido balance oferta-demanda (29-sep).

### Deuda Técnica de Código (última verificación 2026-09-30)

- **Archivos con print():** 66 (verificado 2026-09-30)
- **Archivos con except Exception:** por verificar de nuevo
- **Tests de integración:** 0 (`tests/integration/` vacío)
- **Tests unitarios:** 438 pasando, 0 fallando (verificado 2026-09-30)

---

## Notas de Arquitectura (Validadas por Grafo — regenerado 2026-09-30)

> Estas notas complementan la documentación anterior con datos validados mediante Graphify (análisis estático del grafo de código). Grafo regenerado el 2026-09-30 (`graphify update .`), ya incluye el trabajo de septiembre (balance oferta-demanda, seguridad, etc.) y los archivos eliminados en la limpieza de la misma fecha.

### Métricas reales del codebase

| Métrica | Valor |
|---|---|
| Archivos analizados | 517 (~1.458.091 palabras) |
| Nodos en grafo | 8.984 |
| Aristas (conexiones) | 25.622 |
| Comunidades detectadas | 1.155 |
| Aristas EXTRACTED | 36% |
| Aristas INFERRED | 64% (confianza promedio 0.53) |

### God Nodes (por aristas totales, análisis de 2026-08-30 — no recalculado nodo por nodo en la corrida del 30-sep; usar `graphify explain "<nombre>" --graph graphify-out/graph.json` para el valor vigente de un nodo puntual)

| # | Nodo | Aristas |
|---|---|---|
| 1 | `MetricsService` | 473 |
| 2 | `GenerationService` | 451 |
| 3 | `HydrologyService` | 425 |
| 4 | `MetricsRepository` | 419 |
| 5 | `PostgreSQLConnectionManager` | 414 |
| 6 | `AgentIA` | 388 — el hub de IA compartido (informes, WhatsApp), no listado en auditorías previas |
| 7 | `CommercialService` | 378 |
| 8 | `DistributionService` | 375 |
| 9 | `TransmissionService` | 369 |
| 10 | `LossesService` | 354 |

### Subproyectos embebidos detectados

Además de la API REST y el Dashboard, el monolito contiene:

- **`whatsapp_bot/`** — 607 nodos en el grafo (26 archivos, 9.702 líneas), cifra corregida el 2026-09-01 (antes se citaba 522, ya desactualizado). Comparación aclarada: es ~94% del tamaño de `api/` sola (644 nodos/12.881 líneas), pero solo ~12% del backend completo (`api`+`domain`+`infrastructure`+`core`+`interface` = 4.865 nodos/91.740 líneas) — la comparación anterior ("casi tan grande como la API principal") dependía de qué se comparaba exactamente. Nota operativa importante: el canal de producción real hoy es **Telegram** (`telegram_polling.py`, long polling); el canal WhatsApp/Twilio está activo pero sin tráfico real desde hace días, y la integración `whatsapp-web.js` nunca se desplegó (sin `node_modules` ni Chrome instalados) — ver `docs/AUDITORIA_DOCUMENTACION_2026-09.md`.
- **`energia_app/`** — App móvil React Native (Android/iOS).
- **`experiments/`** — Experimentos ML (XGBoost, SARIMA, LightGBM).
- **`scripts/`** — scripts de utilidad ETL/ontología/CU/predicciones.

### Deuda técnica validada por el grafo

- **`core/container.py`** — 575 nodos, cohesión 0.01. God file de inyección de dependencias. Requiere división en módulos temáticos.
- **ETL duplicado** — `scripts/completar_tablas_incompletas.py` repite la misma lógica para `commercial_metrics`, `loss_metrics` y `restriction_metrics`.
- **Servicios deprecated** — Confirmados: `geo_service.py`, `orchestrator_service.py`, `predictions_service.py`.

### Documentación técnica

- **`PROPUESTA_MAESTRA.md`** (repo portal) — Roadmap completo, deuda técnica, ADRs
- **`AGENTS.md`** — Reglas y convenciones para agentes de desarrollo
- **`SKILL_PACK_COMPACTO.md`** — Operativo diario: jerarquía de verdad, comandos, ejemplos
- **`RUNBOOK_PRODUCCION.md`** — Procedimientos operativos críticos
- **Grafo de dependencias:** `graphify-out/graph-global.json` (6.184 nodos, 14.012 aristas)

---

## Contacto

- **Infraestructura:** Equipo TI MinMinas
- **Repositorio:** `git@github.com:M3l1ss4C4rd0n4/Portal-MME-Backend.git`
- **Desarrollador Principal:** *(sin completar — no se encontró un dato real verificable para rellenar este campo; se deja marcado en vez de inventar un nombre)*

---

© 2026 Ministerio de Minas y Energía - República de Colombia
