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

- **API REST** (FastAPI): 52 endpoints para consumo del frontend Next.js
- **Dashboard Analítico** (Dash): 17 tableros interactivos legacy
- **ETL Pipeline**: Extracción automática de datos de XM, IDEAM, OneDrive
- **Sistema de Alertas**: Notificaciones Telegram basadas en anomalías

### Estadísticas

- **350 archivos Python**
- **30 servicios de dominio**
- **17 scripts ETL**
- **354 tests recopilados (347 pasan, 7 fallando)**
- **~113,000 líneas de código**

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
│  ├── 52 endpoints REST              └── 17 tableros        │
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
          │  │    30 Services          │    │
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
├── api/                          (36 archivos)
│   ├── main.py                   → Entry point FastAPI
│   ├── v1/routes/                → 52 endpoints REST
│   │   ├── restrictions.py
│   │   ├── distribution.py
│   │   ├── system.py
│   │   ├── cu.py
│   │   ├── commercial.py
│   │   ├── generation.py
│   │   └── ...
│   └── dependencies.py           → Inyección FastAPI
│
├── core/                         (21 archivos)
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
├── domain/                       (53 archivos)
│   ├── services/                 → 30 servicios
│   ├── models/                   → Modelos Pydantic
│   ├── schemas/                  → DTOs y validaciones
│   └── interfaces/               → Interfaces abstractas
│
├── infrastructure/               (41 archivos)
│   ├── database/                 → Repositorios PostgreSQL
│   ├── cache/                    → Redis cache manager
│   ├── external/                 → Clientes APIs externas
│   │   ├── xm_client.py
│   │   ├── onedrive_client.py
│   │   └── ideam_client.py
│   ├── logging/                  → Sistema de logging
│   └── observability/            → Métricas y health checks
│
├── interface/                    (17 archivos) [LEGACY]
│   └── pages/                    → Páginas Dash
│
├── etl/                          (17 archivos)
│   ├── etl_todas_metricas_xm.py  → Principal (cada 6h)
│   ├── etl_xm_to_postgres.py     → Backfill manual
│   ├── etl_nuevos_dashboards.py  → Datos dashboard
│   └── validaciones_rangos.py    → Validaciones
│
├── tasks/                        → Celery tasks
│   ├── anomaly_tasks.py
│   └── etl_tasks.py
│
├── tests/                        (42 archivos)
│   ├── unit/                     (35 archivos)
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
├── docs/                         (24+ archivos MD)
├── backups/                      → Backups BD
├── experiments/                  → Experimentos ML
├── scripts/                      (43 archivos)
└── app.py                        → Entry point Dash
```

---

## Servicios de Dominio

### Servicios Principales (por tamaño)

| Servicio | Líneas | Función | Estado |
|----------|--------|---------|--------|
| `report_service.py` | 1,850 | Generación de informes | ✅ Activo |
| `executive_report_service.py` | 1,618 | Informes ejecutivos | ✅ Activo |
| `cu_service.py` | 1,010 | Comercialización mayorista | ✅ Activo |
| `losses_nt_service.py` | 1,199 | Pérdidas no técnicas | ✅ Activo |
| `notification_service.py` | 1,178 | Notificaciones Telegram | ✅ Activo |
| `intelligent_analysis_service.py` | 829 | Análisis con IA | ✅ Activo |
| `simulation_service.py` | 748 | Simulaciones | ✅ Activo |
| `predictions_service_extended.py` | 698 | Predicciones ML | ✅ Activo |
| `cu_minorista_service.py` | 599 | Comercialización minorista | ✅ Activo |
| `ai_service.py` | 504 | Integración LLM | ✅ Activo |
| `commercial_service.py` | 342 | Datos comerciales | ✅ Activo |
| `hydrology_service.py` | 368 | Datos hidrológicos | ✅ Activo |
| `investment_service.py` | 523 | Inversiones | ✅ Activo |
| `distribution_service.py` | 480 | Distribución | ✅ Activo |
| `generation_service.py` | 448 | Generación | ✅ Activo |
| `metrics_service.py` | 222 | Métricas calculadas | ✅ Activo |
| `restrictions_service.py` | 222 | Restricciones | ✅ Activo |
| `transmission_service.py` | 207 | Transmisión | ✅ Activo |
| `indicators_service.py` | 173 | Indicadores | ✅ Activo |
| `system_service.py` | 193 | Sistema | ✅ Activo |
| `validators.py` | 247 | Validaciones | ✅ Activo |
| `confianza_politica.py` | 122 | Análisis político | ⚠️ Sin documentar |
| `geo_service.py` | 32 | Georreferenciación | ⚠️ DEPRECATED |
| `orchestrator_service.py` | 4 | Orquestación | ⚠️ DEPRECATED |
| `predictions_service.py` | 10 | Predicciones (stub) | ⚠️ DEPRECATED |

### Servicios Deprecated

Los siguientes servicios están marcados como deprecated y serán eliminados en V5:

- `geo_service.py` → Funcionalidad no implementada
- `orchestrator_service.py` → Vacío, sin uso
- `predictions_service.py` → Consolidado en `predictions_service_extended.py`

---

## API Endpoints

### Endpoints Principales

| Endpoint | Método | Descripción | Cache |
|----------|--------|-------------|-------|
| `/api/v1/restrictions` | GET | Restricciones del SIN | 5 min |
| `/api/v1/distribution` | GET | Datos de distribución | 5 min |
| `/api/v1/system/metrics` | GET | Métricas del sistema | 1 min |
| `/api/v1/commercial` | GET | Datos comerciales | 5 min |
| `/api/v1/generation` | GET | Generación eléctrica | 5 min |
| `/api/v1/cu` | GET | Comercialización mayorista | 5 min |
| `/api/v1/predictions` | GET | Predicciones ML | 1 hora |
| `/health` | GET | Health check | No |

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
sudo systemctl status api-mme
sudo systemctl restart api-mme

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

Configuración en `config/logrotate-mme.conf`:

```bash
# Aplicar configuración
sudo cp config/logrotate-mme.conf /etc/logrotate.d/mme-server
sudo logrotate -f /etc/logrotate.d/mme-server
```

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
 tail -f logs/actualizacion_onedrive_arcgis.log
```

---

## Documentación Adicional

- [Guía de Onboarding](./docs/GUIA_ONBOARDING.md)
- [Arquitectura E2E](./docs/ARQUITECTURA_E2E.md)
- [Guía Troubleshooting](./docs/GUIA_TROUBLESHOOTING.md)
- [Uso de API](./docs/GUIA_USO_API.md)
- [Índice Completo](./docs/INDICE.md)

---

## Estado de Corrección V4

### Fases Completadas

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Limpieza basura | ✅ 6 archivos eliminados |
| 2 | Documentar deuda técnica | ✅ 3 servicios deprecated |
| 3 | Optimización espacio | ✅ ~1GB liberado |
| 4 | Arquitectura | ⏸️ Diferida a V5 |
| 5 | Documentación | ✅ README actualizado |

### Deuda Técnica Documentada

- **Archivos con print():** 72 (planificado para V5)
- **Archivos con except Exception:** 171 (planificado para V5)
- **Tests de integración:** 0 (planificado para V5)

---

## Contacto

- **Desarrollador Principal:** [Tu nombre/email]
- **Infraestructura:** Equipo TI MinMinas
- **Repositorio:** [URL del repositorio]

---

© 2026 Ministerio de Minas y Energía - República de Colombia
