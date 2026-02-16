# 🔌 Portal Energético Colombia — Dashboard MME

> **Sistema Avanzado de Monitoreo y Análisis del Sector Energético Colombiano**  
> **Versión 5.0 — Arquitectura Hexagonal + IA + Bots + API REST (Febrero 2026)**

Dashboard interactivo de producción con **Inteligencia Artificial**, **Machine Learning**, **Bot de Telegram**, **API REST pública**, **Noticias del sector** y **ETL Automatizado** para análisis en tiempo real del Sistema Interconectado Nacional (SIN).

[![Estado](https://img.shields.io/badge/Estado-Producción-success)]()
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192)]()
[![Architecture](https://img.shields.io/badge/Architecture-Hexagonal-purple)]()
[![AI](https://img.shields.io/badge/AI-Llama%203.3%2070B-orange)]()
[![API](https://img.shields.io/badge/API-FastAPI-009688)]()
[![Telegram](https://img.shields.io/badge/Bot-Telegram-26A5E4)]()

---

## 📊 Estado Actual del Sistema (16 Febrero 2026)

### Base de Datos
- **Motor:** PostgreSQL 16+
- **Registros totales:** ~63.7 millones de filas
- **Cobertura temporal:** 2020-01-01 → 2026-02-16 (6+ años)
- **Tablas principales:** 12 especializadas
  - `metrics` — 13.545.680 filas (métricas diarias del SIN)
  - `metrics_hourly` — 50.127.023 filas (datos horarios)
  - `lineas_transmision` — 42.106 filas (infraestructura)
  - `catalogos` — 2.264 filas (catálogos XM)
  - `predictions` — 1.170 filas (predicciones ML)

### Arquitectura
- **Patrón:** Arquitectura Hexagonal (Clean Architecture) — 4 capas
- **Servicios de dominio:** 21 servicios especializados
- **Tableros activos:** 13 páginas Dash/Plotly
- **API REST:** FastAPI con 26+ endpoints, Swagger/ReDoc, API Key auth
- **Bot Telegram:** Inline keyboards, 5 intents, informes ejecutivos
- **Bot WhatsApp:** FastAPI webhooks + WhatsApp Web (Node.js)
- **Noticias:** GNews API con scoring inteligente y caché
- **Chatbot IA:** Groq + Llama 3.3 70B operativo
- **Líneas de código Python:** ~56.400
- **Archivos Python:** ~120

---

## 🏗️ Arquitectura Hexagonal (Clean Architecture)

El proyecto implementa una arquitectura hexagonal de 4 capas con inyección de dependencias:

```
server/
├── core/                      # ⚙️ Capa Core (transversal)
│   ├── config.py             # Settings centralizados (Pydantic)
│   ├── constants.py          # Constantes: métricas, colores, umbrales
│   ├── container.py          # Contenedor de DI (singletons lazy)
│   ├── app_factory.py        # Factory para app Dash
│   ├── exceptions.py         # Jerarquía de excepciones del dominio
│   └── validators.py         # Validadores globales
│
├── domain/                    # 🧠 Capa de Dominio (21 servicios)
│   ├── interfaces/           # Puertos (ABCs)
│   │   ├── database.py       #   IDatabaseManager
│   │   ├── data_sources.py   #   IXMDataSource, ISIMEMDataSource
│   │   └── repositories.py   #   IMetrics/Commercial/Distribution/Transmission/PredictionsRepository
│   │
│   ├── models/               # Entidades
│   │   ├── metric.py         #   Dataclass Metric
│   │   └── prediction.py     #   Dataclass Prediction
│   │
│   ├── schemas/              # Esquemas API
│   │   └── orchestrator.py   #   OrchestratorRequest/Response (Pydantic)
│   │
│   └── services/             # Lógica de negocio
│       ├── orchestrator_service.py          # Orquestador central (15+ intents)
│       ├── executive_report_service.py      # Informe ejecutivo (11 secciones)
│       ├── intelligent_analysis_service.py  # Anomalías y estado del sector
│       ├── generation_service.py            # Generación eléctrica
│       ├── predictions_service_extended.py  # ML: Prophet + ARIMA + Ensemble
│       ├── ai_service.py                    # Agente IA (Groq/OpenRouter)
│       ├── distribution_service.py          # Demanda por agentes
│       ├── hydrology_service.py             # Embalses, aportes hídricos
│       ├── commercial_service.py            # Precios (bolsa, escasez)
│       ├── transmission_service.py          # Líneas de transmisión
│       ├── restrictions_service.py          # Restricciones operativas
│       ├── losses_service.py                # Pérdidas de energía
│       ├── news_service.py                  # Noticias del sector (GNews)
│       ├── metrics_service.py               # Métricas con DI
│       ├── metrics_calculator.py            # Fórmulas oficiales XM
│       ├── indicators_service.py            # KPIs con variaciones
│       ├── system_service.py                # Health checks
│       ├── confianza_politica.py            # Política de confianza ML
│       ├── geo_service.py                   # Coordenadas geográficas
│       └── validators.py                    # Validadores de dominio
│
├── infrastructure/            # 🔧 Capa de Infraestructura (adaptadores)
│   ├── database/
│   │   ├── connection.py            # Pool de conexiones PostgreSQL
│   │   ├── manager.py              # DatabaseManager (upsert bulk)
│   │   └── repositories/           # Repositorios especializados
│   │       ├── base_repository.py
│   │       ├── metrics_repository.py
│   │       ├── commercial_repository.py
│   │       ├── distribution_repository.py
│   │       ├── transmission_repository.py
│   │       └── predictions_repository.py
│   │
│   ├── external/              # APIs externas
│   │   ├── xm_service.py           # Cliente XM (pydataxm, BD→API fallback)
│   │   └── xm_adapter.py           # Adaptador hexagonal IXMDataSource
│   │
│   ├── news/                  # Noticias
│   │   └── news_client.py          # Cliente GNews API (httpx async)
│   │
│   └── logging/               # Logging
│       └── logger.py               # RotatingFileHandler (10MB, 5 backups)
│
├── interface/                 # 🎨 Capa de Presentación (Dashboard)
│   ├── components/
│   │   ├── layout.py               # Navbar, sidebar, filtros
│   │   ├── header.py               # Header con logos MME
│   │   └── chat_widget.py          # Widget chatbot IA flotante
│   │
│   └── pages/                 # 13 tableros activos
│       ├── home.py                  # Portada interactiva
│       ├── generacion.py            # Generación general + KPIs
│       ├── generacion_fuentes_unificado.py  # Por tipo de fuente
│       ├── generacion_hidraulica_hidrologia.py  # Hidrología
│       ├── distribucion.py          # Demanda
│       ├── comercializacion.py      # Precios
│       ├── transmision.py           # Líneas de transmisión
│       ├── restricciones.py         # Restricciones
│       ├── perdidas.py              # Pérdidas de energía
│       ├── metricas.py              # Explorador de métricas
│       ├── metricas_piloto.py       # Prototipo experimental
│       └── config.py               # Configuración de páginas
│
├── api/                       # 🌐 API REST (FastAPI)
│   ├── main.py               # App FastAPI, CORS, rate limiting
│   ├── dependencies.py       # DI y autenticación API Key
│   └── v1/
│       ├── routes/            # 12 archivos de endpoints
│       │   ├── chatbot.py, metrics.py, generation.py
│       │   ├── hydrology.py, predictions.py, commercial.py
│       │   ├── distribution.py, transmission.py, losses.py
│       │   ├── restrictions.py, system.py, whatsapp_alerts.py
│       │
│       └── schemas/           # 12 archivos Pydantic
│
├── etl/                       # 📥 Pipeline ETL (7 archivos)
│   ├── etl_xm_to_postgres.py        # ETL principal → PostgreSQL (cron 3x/día)
│   ├── etl_todas_metricas_xm.py     # ETL masivo (193 métricas)
│   ├── etl_transmision.py           # ETL transmisión SIMEM
│   ├── etl_rules.py                 # Reglas canónicas (60+ métricas)
│   ├── config_metricas.py           # Configuración por sección
│   ├── validaciones.py              # Validación post-carga
│   └── validaciones_rangos.py       # Rangos XM Sinergox
│
├── whatsapp_bot/              # 💬 Bots de mensajería
│   ├── telegram_polling.py          # Bot Telegram (1373 líneas, polling)
│   ├── app/                         # Bot WhatsApp (FastAPI :8001)
│   │   ├── main.py, config.py, sender.py
│   │   ├── rate_limiting.py, security.py, tasks.py
│   │
│   └── whatsapp-web-service/        # Servicio Node.js alternativo
│
├── tasks/                     # 📋 Tareas Celery Beat
│   ├── __init__.py            # Config: ETL 6h, anomalías 30min
│   ├── etl_tasks.py           # SafeETLTask con auto-retry
│   └── anomaly_tasks.py       # Alertas cada 30min + resumen 7AM
│
├── scripts/                   # 🛠️ Scripts operacionales (29 archivos)
│   ├── alertas_energeticas.py       # Motor de alertas por umbrales
│   ├── sistema_notificaciones.py    # Email + WhatsApp notifications
│   ├── train_predictions_*.py       # Entrenamiento ML (Prophet/SARIMA)
│   ├── backup_postgres_diario.sh    # Backup diario con retención
│   ├── monitor_api.sh               # Watchdog (cron 5min)
│   └── ops/                         # Scripts operativos
│
├── tests/                     # ✅ Tests automatizados
├── sql/                       # 🗄️ Scripts DDL y migraciones
├── docs/                      # 📚 19+ documentos técnicos
├── data/                      # 📊 Datos estáticos (ArcGIS)
├── backups/                   # 💾 Backups PostgreSQL
├── config/                    # ⚙️ Systemd + logrotate
├── ejemplos/                  # 📝 Ejemplos de uso del API
└── assets/                    # 🎨 CSS, JS, imágenes, GeoJSON
```

---

## 🚀 Instalación y Ejecución

### Requisitos Previos
- **Python:** 3.12+
- **PostgreSQL:** 16+
- **Redis:** Para Celery Beat (opcional)
- **Node.js:** 18+ (para WhatsApp Web service, opcional)
- **Sistema Operativo:** Linux Ubuntu 20.04+ (recomendado)

### 1. Instalación de Dependencias

```bash
git clone https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git
cd Dashboard_Multipage_MME

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configuración de Variables de Entorno

Crear archivo `.env` (ver `.env.example`):

```bash
# Base de Datos PostgreSQL
USE_POSTGRES=True
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=portal_energetico
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password

# APIs de IA
GROQ_API_KEY=tu_api_key_groq
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=tu_api_key_openrouter

# API REST
API_KEY=tu_api_key
API_BASE_URL=http://localhost:8000

# Noticias del sector
GNEWS_API_KEY=tu_api_key_gnews

# Bot Telegram
TELEGRAM_BOT_TOKEN=tu_token_telegram

# Configuración Servidor
DEBUG=False
HOST=0.0.0.0
PORT=8050
```

### 3. Base de Datos

```bash
# Crear base de datos
sudo -u postgres createdb portal_energetico

# Ejecutar ETL inicial
python3 etl/etl_xm_to_postgres.py --fecha-inicio 2020-01-01 --sin-timeout
python3 etl/etl_transmision.py --days 2000 --clean
```

### 4. Ejecución

**Dashboard (Producción):**
```bash
sudo systemctl start dashboard-mme    # systemd
# O manualmente:
gunicorn -c gunicorn_config.py wsgi:server
```

**API REST (Producción):**
```bash
sudo systemctl start api-mme          # systemd
# O manualmente:
gunicorn -w 5 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 api.main:app
```

**Bot Telegram:**
```bash
python3 whatsapp_bot/telegram_polling.py &
```

**Bot WhatsApp:**
```bash
uvicorn whatsapp_bot.app.main:app --host 0.0.0.0 --port 8001 --workers 3
```

---

## 🌐 API REST (FastAPI)

### Endpoints (26+)

| Grupo | Base | Endpoints principales |
|-------|------|-----------------------|
| Chatbot | `/api/v1/chatbot/` | `POST /orchestrator`, `GET /health` |
| Métricas | `/api/v1/metrics/` | `GET /{metric}`, `GET /` |
| Generación | `/api/v1/generation/` | `/system`, `/by-source`, `/resources`, `/mix` |
| Hidrología | `/api/v1/hydrology/` | `/aportes`, `/reservoirs`, `/energy` |
| Predicciones | `/api/v1/predictions/` | `GET /{metric}`, `POST /train` |
| Comercialización | `/api/v1/commercial/` | `/prices`, `/contracts` |
| Distribución | `/api/v1/distribution/` | `/data`, `/operators` |
| Transmisión | `/api/v1/transmission/` | `/lines`, `/flows`, `/international` |
| Pérdidas | `/api/v1/losses/` | `GET /` |
| Restricciones | `/api/v1/restrictions/` | `GET /` |
| Sistema | `/api/v1/system/` | `/demand`, `/prices` |
| WhatsApp | `/api/v1/whatsapp/` | `POST /alert`, `GET /status` |

### Autenticación
- Header: `X-API-Key`
- Documentación: `http://localhost:8000/api/docs` (Swagger) / `http://localhost:8000/api/redoc`

---

## 🤖 Inteligencia Artificial

### Chatbot IA (Groq + Llama 3.3 70B)
- **Modelo:** Llama 3.3 70B Versatile (Groq primario, OpenRouter respaldo)
- **Capacidades:** Consultas en lenguaje natural, análisis de tendencias, resúmenes ejecutivos
- **Acceso:** Widget flotante en Dashboard + Bot Telegram + API REST

### Machine Learning (Prophet + ARIMA + Ensemble)
- **Modelos:** Prophet, ARIMA/SARIMA, Ensemble (promedio ponderado)
- **Métricas predichas:** Generación, demanda, precios, embalses
- **Entrenamiento:** Semanal automático (cron, lunes 2 AM)
- **Política de confianza:** MUY_CONFIABLE (<5% MAPE) → EXPERIMENTAL (>25% MAPE)
- **Predicciones activas:** 1.170 registros en tabla `predictions`

---

## 💬 Bot de Telegram

Bot interactivo con **inline keyboards** y navegación bidireccional:

| # | Opción | Descripción |
|---|--------|-------------|
| 1 | 📊 Estado actual | Estado del sector con KPIs |
| 2 | 🔮 Predicciones | Submenú con 5 horizontes temporales |
| 3 | 🚨 Anomalías | Alertas con detalle expandible |
| 4 | 📰 Noticias | Top 3 noticias con scoring + URLs |
| 5 | 📋 Más información | Informe ejecutivo (11 secciones) + Pregunta libre IA |

**Comandos:** `/menu`, `/estado`, `/predicciones`, `/anomalias`, `/noticias`, `/informe`, `/ayuda`

---

## 📥 Sistema ETL Automatizado

### Pipeline de datos

```
API XM (pydataxm) ──► etl_xm_to_postgres.py ──► metrics / metrics_hourly
API SIMEM          ──► etl_transmision.py    ──► lineas_transmision
GNews API          ──► news_client.py        ──► Caché in-memory (30 min)
```

### Automatización

| Tarea | Frecuencia | Mecanismo |
|-------|-----------|-----------|
| ETL métricas principales | 3x/día (06, 12, 18h) | Cron |
| ETL incremental | Cada 6 horas | Celery Beat |
| Detección anomalías | Cada 30 min | Celery Beat |
| Resumen diario | 7:00 AM | Celery Beat |
| Predicciones ML | Semanal (lunes 2 AM) | Cron |
| Backup BD | Diario (3 AM) | Cron |
| Monitor API | Cada 5 min | Cron |

### Estado de Tablas PostgreSQL

| Tabla | Filas | Estado |
|-------|-------|--------|
| `metrics` | 13.545.680 | ✅ Sana |
| `metrics_hourly` | 50.127.023 | ✅ Sana |
| `lineas_transmision` | 42.106 | ✅ Sana |
| `catalogos` | 2.264 | ✅ Sana |
| `predictions` | 1.170 | ✅ Sana |
| `alertas_historial` | 3 | ✅ Sana |
| `commercial_metrics` | 0 | ⚠️ Vacía |
| `loss_metrics` | 0 | ⚠️ Vacía |
| `restriction_metrics` | 0 | ⚠️ Vacía |

---

## 🛠️ Tecnologías

| Capa | Tecnologías |
|------|-------------|
| **Dashboard** | Dash/Plotly, Flask, Dash Bootstrap Components, CSS corporativo MME |
| **API REST** | FastAPI, Pydantic, Uvicorn, Swagger/ReDoc |
| **Base de datos** | PostgreSQL 16+, psycopg2, pandas |
| **ETL** | pydataxm, pydatasimem (ReadSIMEM) |
| **IA** | Groq API, OpenRouter, Llama 3.3 70B |
| **ML** | Prophet, statsmodels (ARIMA/SARIMA) |
| **Bots** | python-telegram-bot, httpx, Twilio, whatsapp-web.js |
| **Noticias** | GNews API, httpx async |
| **DevOps** | gunicorn, uvicorn, systemd, nginx, Celery + Redis |
| **Monitoreo** | Health checks, RotatingFileHandler, cron watchdog |

---

## 📚 Documentación

- [Arquitectura Completa (16 Feb 2026)](docs/INFORME_ARQUITECTURA_COMPLETA_2026-02-16.md) ← **Informe detallado archivo por archivo**
- [Documentación Técnica](docs/DOCUMENTACION_TECNICA_ORQUESTADOR.md)
- [Guía de Uso del API](docs/GUIA_USO_API.md)
- [Setup API 24/7](docs/API_24_7_SETUP.md)
- [Integración WhatsApp Bot](docs/INTEGRACION_WHATSAPP_BOT.md)
- [Auditoría de Predicciones (Fase 7)](docs/FASE7_AUDITORIA_PREDICCIONES.md)
- [Mapeo Completo de Métricas](docs/MAPEO_COMPLETO_METRICAS.md)

---

## 🔧 Administración

### Servicios Systemd

```bash
# Dashboard
sudo systemctl status dashboard-mme
sudo systemctl restart dashboard-mme

# API REST
sudo systemctl status api-mme
sudo systemctl restart api-mme

# Reload API sin downtime
kill -HUP $(pgrep -f "gunicorn.*8000" | head -1)
```

### Monitoreo rápido

```bash
# Puertos activos
ss -tlnp | grep -E '8000|8050|8001|5432'

# Logs en vivo
tail -f logs/api.log
tail -f logs/etl.log
```

---

## 🎯 Roadmap

### Completado ✅
- [x] Migración PostgreSQL (63.7M registros)
- [x] Arquitectura Hexagonal (21 servicios, DI, puertos)
- [x] API REST FastAPI (26+ endpoints, auth, Swagger)
- [x] Bot Telegram con inline keyboards (5 intents)
- [x] Bot WhatsApp (webhooks + WhatsApp Web)
- [x] Chatbot IA (Groq + Llama 3.3 70B)
- [x] ML: Prophet + ARIMA + Ensemble
- [x] Noticias del sector (GNews + scoring)
- [x] 13 tableros Dash/Plotly
- [x] ETL automatizado (cron + Celery Beat)
- [x] Informe ejecutivo estadístico (11 secciones)
- [x] Política de confianza en predicciones

### Pendiente 📋
- [ ] Poblar tablas vacías (commercial, loss, restriction)
- [ ] Tests automatizados (cobertura 80%+)
- [ ] Dashboard de monitoreo Grafana
- [ ] Caché Redis para queries API pesadas
- [ ] Paginación completa en endpoints de series grandes

---

## 📞 Soporte

**Desarrollador:** Melissa de Jesús Cardona Navarro  
**Contrato:** GGC-0316-2026  
**Repositorio:** https://github.com/MelissaCardona2003/Dashboard_Multipage_MME  
**Última actualización:** 16 de febrero de 2026

---

## 📄 Licencia

Este proyecto es propiedad del **Ministerio de Minas y Energía de Colombia**.

---

**Ministerio de Minas y Energía — Colombia 2026**
