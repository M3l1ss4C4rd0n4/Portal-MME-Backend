# Portal Energético Colombia — Dashboard MME

> **Sistema Integral de Monitoreo y Análisis del Sector Energético Colombiano**  
> **Versión 1.4.0 — Arquitectura Hexagonal + IA + Bots + API REST + ML (Marzo 2026)**

Dashboard interactivo de producción con **Inteligencia Artificial**, **Machine Learning**, **Bots multicanal (Telegram + WhatsApp)**, **API REST pública**, **Noticias del sector**, **ETL automatizado** y **publicación ArcGIS** para análisis en tiempo real del Sistema Interconectado Nacional (SIN).

[![Estado](https://img.shields.io/badge/Estado-Producción-success)]()
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192)]()
[![Architecture](https://img.shields.io/badge/Architecture-Hexagonal-purple)]()
[![AI](https://img.shields.io/badge/AI-Llama%203.3%2070B-orange)]()
[![API](https://img.shields.io/badge/API-FastAPI%2029%20endpoints-009688)]()
[![Telegram](https://img.shields.io/badge/Bot-Telegram-26A5E4)]()

---

## Estado Actual del Sistema (15 Marzo 2026)

### Plataforma

| Componente | Detalle |
|-----------|--------|
| **Servidor** | Srvwebprdctrlxm (Azure VM, Ubuntu) |
| **Dashboard** | Dash 2.17.1 / Plotly 5.17.0 — 14 tableros activos, port 8050 |
| **API REST** | FastAPI — 29+ endpoints, port 8000, autenticación X-API-Key |
| **Chatbot IA** | Analista Energético flotante (izquierda), con alertas + noticias en tiempo real |
| **Widget Noticias** | Carrusel KPI top-left en inicio, rotación automática cada 7 s |
| **Alertas Inteligentes** | Celery Beat detecta anomalías, cooldown 2h, notifica Telegram |
| **Bot Telegram** | Polling mode, inline keyboards, informes ejecutivos |
| **Bot WhatsApp** | FastAPI + whatsapp-web.js, port 8001 (experimental) |
| **MLflow** | Tracking server, port 5000 |
| **Celery** | 2 workers + Beat |

### Base de Datos PostgreSQL 16

| Tabla | Descripción |
|-------|-------------|
| `metrics_hourly` | Métricas XM horarias (50M+ filas, 2020→presente) |
| `metrics` | Métricas XM diarias (13M+ filas) |
| `cu_daily` | Costo Unitario mayorista diario |
| `predictions` | Predicciones ML (horizonte 365 días) |
| `alertas_historial` | Historial de alertas energéticas con cooldown |
| `losses_detailed` | Pérdidas detalladas por OR |
| `commercial_metrics` | Métricas comerciales por agente |
| `restriction_metrics` | Restricciones operativas |
| `subsidios_pagos` | Subsidios y estratos |
| **Total** | **~15 GB**, ~64M filas, cobertura 2020-01-01 → presente |

### Métricas del Código

| Métrica | Valor |
|---------|-------|
| Archivos Python | 261 (todos con sintaxis válida) |
| Servicios de dominio | 28 |
| Repositorios | 6 |
| Endpoints API | 29+ |
| Páginas Dashboard | 15 |
| Handlers orquestador | 8 |
| Tareas Celery | 2 archivos (anomaly_tasks + etl_tasks) |
| ETL processes | 11 scripts ETL |

---
        ├── database/           ├── XM Colombia
        │   ├── connection      ├── SIMEM
        │   ├── manager         ├── IDEAM
        │   └── repositories    ├── Groq/OpenRouter
        ├── external/           ├── ArcGIS
        ├── logging/            ├── Telegram
        └── news/               └── Twilio/Meta
```

### Estructura del Proyecto

```
server/
├── core/                      # Configuración, DI, factory, constantes
│   ├── config.py             # Pydantic Settings (40+ campos)
│   ├── constants.py          # IDs métricas XM, colores, umbrales
│   ├── container.py          # Contenedor DI (singletons lazy)
│   ├── app_factory.py        # Factory Dash + Prometheus
│   ├── exceptions.py         # PortalError → 5 subtipos
│   └── validators.py         # Validación global
│
├── domain/                    # Lógica de negocio (15,110 líneas)
│   ├── interfaces/           # 10 ABCs (puertos)
│   ├── models/               # Metric, Prediction (frozen dataclass)
│   ├── schemas/              # OrchestratorRequest/Response (Pydantic)
│   └── services/             # 24 servicios especializados
│       ├── orchestrator_service.py          # Orquestador (20+ intents)
│       ├── executive_report_service.py      # Informe ejecutivo (11 secciones)
│       ├── intelligent_analysis_service.py  # Anomalías y estado sectorial
│       ├── report_service.py                # PDFs (WeasyPrint)
│       ├── notification_service.py          # Telegram + Email SMTP
│       ├── generation_service.py            # Generación eléctrica
│       ├── predictions_service_extended.py  # ML: Prophet + ARIMA + Ensemble
│       ├── ai_service.py                    # Agente IA (Groq/OpenRouter)
│       ├── news_service.py                  # Noticias (GNews, Mediastack, RSS)
│       └── ... (15 servicios más)
│
├── infrastructure/            # Adaptadores (repositorios, APIs, logging)
│   ├── database/             # PostgreSQL: connection, manager, 6 repos
│   ├── external/             # XM, IDEAM adapters
│   ├── news/                 # 3 clientes de noticias (async)
│   └── logging/              # RotatingFileHandler
│
├── interface/                 # Dashboard Dash (19,354 líneas)
│   ├── components/           # chart_card, kpi_card, chat_widget, header
│   └── pages/                # 12 tableros + config + hidrologia/utils
│
├── api/                       # API REST FastAPI
│   ├── main.py               # CORS, rate limiting, OpenAPI 3.0.3
│   ├── dependencies.py       # DI + API Key auth
│   └── v1/                   # 12 routers + 12 schemas
│
├── etl/                       # Pipelines de datos (8 archivos)
├── scripts/                   # Operaciones y diagnósticos (32 archivos)
├── tasks/                     # Celery tasks (ETL + predicciones + reportes)
├── whatsapp_bot/              # Bot WhatsApp + Telegram (19 archivos)
├── experiments/               # ML offline: FASE 5B/6/7/15
├── tests/                     # Unit + integration + ARGIS scripts
├── docs/                      # Documentación técnica
├── sql/                       # Scripts DDL
├── assets/                    # CSS, JS, imágenes, GeoJSON
├── data/                      # OneDrive sync + charts generados
├── config/                    # systemd, logrotate
├── ejemplos/                  # Ejemplos de consumo del API
└── backups/                   # DB dumps semanales automáticos
```

---

## Tableros del Dashboard

| # | Ruta | Descripción | Estado |
|---|------|-------------|--------|
| # | Ruta | Descripción | Estado |
|---|------|-------------|--------|
| 1 | `/` | Portada interactiva | ✅ 200 |
| 2 | `/generacion` | Generación SIN | ✅ 200 |
| 3 | `/generacion-fuentes` | Por fuente energética | ✅ 200 |
| 4 | `/hidrologia` | Hidrología | ✅ 200 |
| 5 | `/transmision` | Transmisión | ✅ 200 |
| 6 | `/distribucion` | Distribución | ✅ 200 |
| 7 | `/comercializacion` | Comercialización | ✅ 200 |
| 8 | `/perdidas` | Pérdidas técnicas | ✅ 200 |
| 9 | `/perdidas-nt` | Pérdidas no técnicas | ✅ 200 |
| 10 | `/costo-unitario` | Costo unitario (CU) | ✅ 200 |
| 11 | `/simulacion` | Simulación CREG | ✅ 200 |
| 12 | `/restricciones` | Restricciones | ✅ 200 |
| 13 | `/metricas` | Explorador universal | ✅ 200 |
| 14 | `/seguimiento-predicciones` | Monitoreo ML | ✅ 200 |

---

## API REST (FastAPI)

**Base URL:** `https://portalenergetico.minenergia.gov.co/api`  
**Documentación:** `/api/docs` (Swagger) · `/api/redoc` (ReDoc)  
**Autenticación:** Header `X-API-Key`

### Endpoints

| Grupo | Prefijo | Endpoints | Rate Limit |
|-------|---------|----------|------------|
| Generación | `/v1/generation` | system, by-source, resources, mix | 100/min |
| Hidrología | `/v1/hydrology` | aportes, reservoirs, energy | 100/min |
| Sistema | `/v1/system` | demand, prices | 100/min |
| Transmisión | `/v1/transmission` | lines, flows, international | 100/min |
| Distribución | `/v1/distribution` | data, operators | 100/min |
| Comercial | `/v1/commercial` | prices, contracts | 100/min |
| Pérdidas | `/v1/losses` | data | 100/min |
| Restricciones | `/v1/restrictions` | data | 100/min |
| Métricas | `/v1/metrics` | list, by id | 60-100/min |
| Predicciones | `/v1/predictions` | forecast, train, batch, cache stats, cache flush | 5-20/min |
| Chatbot | `/v1/chatbot` | orchestrator, health | 100/min |
| WhatsApp | `/v1/whatsapp` | send-alert, bot-status | — |

**Total:** 29 endpoints (25 GET, 2 POST, 1 DELETE, 1 batch)

---

## Inteligencia Artificial y Machine Learning

### Chatbot IA
- **Modelo:** Llama 3.3 70B Versatile (Groq primario, OpenRouter fallback)
- **Acceso:** Widget flotante en Dashboard + Bot Telegram + API `POST /v1/chatbot/orchestrator`
- **Intents:** 20+ (estado_actual, generacion, hidrologia, precios, predicciones, anomalias, informe_ejecutivo, noticias, comparacion_anual...)

### Predicciones ML
- **Modelos en producción:** Prophet, ARIMA/SARIMA, Ensemble (promedio ponderado)
- **Modelos experimentados:** XGBoost, LightGBM, Random Forest, LSTM, PatchTST, N-BEATS, TCN, N-HiTS, Chronos
- **Métricas predichas:** DemaCome, Gene, PrecBolsNaci, AporEner, Gene_Eolica, Gene_Solar
- **Regresores:** 11 variables multivariable (embalses, aportes, precios...)
- **Entrenamiento:** Semanal automático (domingos 2:00 AM)
- **Horizonte:** 30 días
- **Política de confianza:** MUY_CONFIABLE (<5% MAPE) → EXPERIMENTAL (>25% MAPE)

---

## ETL y Automatización

### Cron Jobs Activos

| Frecuencia | Tarea | Script |
|-----------|-------|--------|
| Cada 6 horas | ETL métricas XM (106 métricas) | `etl/etl_todas_metricas_xm.py` |
| Diario 6:30 AM | ETL transmisión | `etl/etl_transmision.py` |
| Cada hora | ArcGIS Enterprise (dual account) | `scripts/arcgis/ejecutar_dual.sh` |
| Cada 30 min | ArcGIS Online | `scripts/arcgis/actualizar_datos_xm_online.py` |
| Semanal dom 2 AM | Predicciones ML | `scripts/actualizar_predicciones.sh` |
| Semanal dom 3 AM | Backup PostgreSQL | `scripts/backup_postgres_diario.sh` |
| Mensual día 1 | Backfill métricas | `scripts/backfill_sistema_metricas.py` |
| Cada 5 min | Monitor API | `scripts/monitor_api.sh` |
| @reboot | Auto-start API | `api/start_api_daemon.sh` |

### Celery Beat

| Tarea | Frecuencia |
|-------|-----------|
| ETL métricas core | Cada 6 horas |
| Limpieza logs | Diario 3:00 AM |
| Detección anomalías | Cada 30 minutos |
| Resumen diario (PDF + charts) | Diario 8:00 AM |

---

## Bot Telegram

Bot con inline keyboards y navegación bidireccional:

**Comandos:** `/menu`, `/estado`, `/predicciones`, `/anomalias`, `/noticias`, `/informe`, `/ayuda`, `/precio`, `/generacion`, `/demanda`, `/mix`, `/grafico`, `/resumen`

**Funcionalidades:**
- Estado actual del sector con KPIs
- Predicciones con 5 horizontes temporales
- Detección de anomalías con detalle expandible
- Noticias del sector con scoring y URLs
- Informe ejecutivo completo (11 secciones)
- Gráficos PNG (embalses, precios, generación)
- Chat libre con IA

---

## Instalación

### Requisitos
- Python 3.12+
- PostgreSQL 16+
- Redis (para Celery Beat y caché)
- Node.js 18+ (para WhatsApp Web, opcional)
- Linux Ubuntu 20.04+

### Setup

```bash
git clone https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git
cd Dashboard_Multipage_MME

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con credenciales reales

# Base de datos
sudo -u postgres createdb portal_energetico

# ETL inicial
python3 etl/etl_xm_to_postgres.py --fecha-inicio 2020-01-01 --sin-timeout
```

### Ejecución

```bash
# Dashboard (systemd)
sudo systemctl start dashboard-mme

# API REST (systemd)
sudo systemctl start api-mme

# Bot Telegram
python3 whatsapp_bot/telegram_polling.py &

# Bot WhatsApp
uvicorn whatsapp_bot.app.main:app --host 0.0.0.0 --port 8001
```

---

## Stack Tecnológico

| Capa | Tecnologías |
|------|-------------|
| Dashboard | Dash 2.17.1, Plotly 5.17.0, Flask 3.0.0, DBC 1.5.0 |
| API | FastAPI 0.128.2, Pydantic 2.5, slowapi 0.1.9, Redis 5.0.8 |
| Base de datos | PostgreSQL 16, psycopg2-binary 2.9.11 |
| ML | Prophet 1.1.5, statsmodels, scikit-learn, XGBoost, LightGBM |
| IA | Groq (Llama 3.3 70B), OpenRouter, openai SDK |
| Bots | python-telegram-bot, Twilio, whatsapp-web.js (Node.js) |
| Noticias | GNews, Mediastack, Google News RSS (httpx async) |
| ETL | pydataxm 0.7.1, Celery 5.6.2, ArcGIS Python API |
| Servidor | Gunicorn 23.0.0, Uvicorn 0.34.0, Nginx, systemd |
| PDF | WeasyPrint |
| Monitoreo | Prometheus, psutil, logrotate, MLflow 2.21.3 |

---

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [Informe Arquitectura Completa v4](docs/informes/INFORME_ARQUITECTURA_COMPLETA_2026-03-05.md) | Inspección completa: 12 secciones, inventario BD, deuda técnica, seguridad |
| [Documentación Técnica Orquestador](docs/DOCUMENTACION_TECNICA_ORQUESTADOR.md) | 20+ intents, timeout, flujo completo |
| [Guía de Uso del API](docs/GUIA_USO_API.md) | Endpoints, autenticación, ejemplos |
| [Endpoint Orchestrator](docs/ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md) | Integración para Oscar (WhatsApp) |
| [Auditoría Predicciones](docs/FASE7_AUDITORIA_PREDICCIONES.md) | MAPE/RMSE por modelo y métrica |
| [Mapeo Métricas](docs/MAPEO_COMPLETO_METRICAS.md) | 120+ métricas XM/SIMEM documentadas |
| [Cron Jobs ETL](docs/CRON_JOB_ETL_POSTGRESQL.md) | Configuración de automatización |
| [Disponibilidad 24/7](docs/DISPONIBILIDAD_24_7.md) | systemd, nginx, monitoreo |
| [Política de Confianza](docs/POLITICA_CONFIANZA_PREDICCIONES.md) | Niveles de confianza ML |
| [Plan de Estabilidad ETL](docs/etl_stability_plan.md) | Diagnósticos y mejoras ETL |

---

## Administración

```bash
# Estado de servicios
sudo systemctl status dashboard-mme api-mme

# Logs en vivo
tail -f logs/gunicorn_error.log
tail -f logs/api-error.log

# Puertos activos
ss -tlnp | grep -E '8000|8050|8001|5000'

# Restart sin downtime (API)
kill -HUP $(pgrep -f "gunicorn.*8000" | head -1)
```

---

## Licencia

Propiedad del **Ministerio de Minas y Energía de Colombia**.

**Repositorio:** https://github.com/MelissaCardona2003/Dashboard_Multipage_MME  
**Última actualización:** 15 de marzo de 2026  
**Tag:** v1.4.0

---

## Changelog

### v1.4.0 — 15 Marzo 2026
- **fix(costo_usuario_final):** `TypeError: can only concatenate str (not "Br") to str` al construir la alerta de metodología en la página CU Usuario Final
- **fix(config_simem):** `AttributeError: 'list' object has no attribute 'empty'` — `obtener_listado_simem()` ahora retorna `pd.DataFrame` con columnas `CodigoVariable` y `Nombre` en lugar de lista plana
- **feat(chatbot):** Widget flotante con panel anclado `bottom:20px` que crece hacia arriba; posición `top:70%` para no interferir con navbar
- **feat(home):** Carrusel de noticias del sector energético en esquina superior izquierda, auto-rotante cada 7 s
- **fix(alertas):** Eliminadas 2 alertas `BALANCE_ENERGETICO` falsas de la BD generadas antes del fix
- **chore:** Eliminados 3 archivos basura del directorio raíz (`:`, `ettings`, `tructure.database.manager import db_manager`)
- **chore(gitignore):** Patrones para ignorar salidas de pager/terminal guardadas accidentalmente
- **refactor:** Arquitectura hexagonal completa — 261 archivos Python, 0 errores de sintaxis
