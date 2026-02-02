# 🔌 Portal Energético Colombia - Dashboard MME

> **Sistema Avanzado de Monitoreo y Análisis del Sector Energético Colombiano**  
> **Versión 4.0 - PostgreSQL + Arquitectura DDD (Febrero 2026)**

Dashboard interactivo de producción con **Inteligencia Artificial**, **Machine Learning** y **ETL Automatizado** para análisis en tiempo real del Sistema Interconectado Nacional (SIN).

[![Estado](https://img.shields.io/badge/Estado-Producción-success)]() 
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192)]()
[![Architecture](https://img.shields.io/badge/Architecture-DDD-purple)]()
[![AI](https://img.shields.io/badge/AI-Llama%203.3%2070B-orange)]()

---

## 📊 Estado Actual del Sistema (Febrero 2026)

### Base de Datos
- **Motor:** PostgreSQL 16+ (migrado desde SQLite)
- **Registros:** 12,378,969 datos históricos
- **Cobertura temporal:** 2020-01-01 → 2026-01-30 (6+ años)
- **Tablas:** 7 especializadas (metrics, metrics_hourly, commercial_metrics, distribution_metrics, lineas_transmision, catalogos, predictions)
- **Top métricas:** DDVContratada (2.9M), ENFICC (2.9M), ObligEnerFirme (2.9M), Gene (523K), DemaReal (183K)

### Arquitectura
- **Servicios de dominio:** 16 servicios especializados
- **Tableros activos:** 13 páginas (10 funcionales, 2 en corrección, 1 en desarrollo)
- **ETL automatizado:** 9 cron jobs (14 ejecuciones/día)
- **Chatbot IA:** Groq + Llama 3.3 70B operativo

---

## 🏗️ Arquitectura DDD (Domain-Driven Design)

El proyecto implementa una arquitectura limpia de 3 capas separando responsabilidades:

```
server/
├── core/                      # ⚙️ Configuración central
│   ├── config.py             # Settings (PostgreSQL, Groq, XM API)
│   ├── constants.py          # Constantes de negocio
│   ├── app_factory.py        # Fábrica de aplicación Dash
│   ├── exceptions.py         # Excepciones personalizadas
│   └── validators.py         # Validadores globales
│
├── domain/                    # 🧠 Lógica de negocio (16 servicios)
│   └── services/
│       ├── ai_service.py              # Agente IA (Groq/OpenRouter)
│       ├── generation_service.py      # Generación eléctrica
│       ├── metrics_calculator.py      # Cálculos métricas XM
│       ├── indicators_service.py      # Indicadores con variaciones
│       ├── hydrology_service.py       # Embalses, aportes, caudales
│       ├── restrictions_service.py    # Restricciones eléctricas
│       ├── transmission_service.py    # Líneas transmisión UPME
│       ├── distribution_service.py    # Distribución
│       ├── commercial_service.py      # Comercialización
│       ├── losses_service.py          # Pérdidas energéticas
│       ├── predictions_service.py     # Predicciones ML
│       ├── metrics_service.py         # Métricas genéricas
│       ├── system_service.py          # Health checks
│       ├── data_loader.py             # Carga de datos
│       ├── geo_service.py             # Servicios geográficos
│       └── validators.py              # Validadores de dominio
│
├── infrastructure/            # 🔧 Implementación técnica
│   ├── database/
│   │   ├── connection.py            # Gestión conexiones PostgreSQL/SQLite
│   │   ├── manager.py               # DatabaseManager (singleton dual-engine)
│   │   └── repositories/            # Repositorios especializados
│   │       ├── base_repository.py        # Repositorio base (auto-detección BD)
│   │       ├── metrics_repository.py     # Métricas XM
│   │       ├── commercial_repository.py  # Datos comerciales
│   │       ├── distribution_repository.py # Datos distribución
│   │       └── transmission_repository.py # Líneas transmisión
│   │
│   ├── external/              # APIs externas
│   │   ├── xm_service.py           # Cliente API XM (pydataxm)
│   │   └── simem_service.py        # Cliente API SIMEM
│   │
│   ├── logging/               # Sistema de logs
│   └── ml/                    # Modelos machine learning
│
├── interface/                 # 🎨 Capa de presentación
│   ├── components/
│   │   ├── chat_widget.py          # Widget chatbot IA flotante
│   │   ├── header.py               # Navbar corporativo MME
│   │   └── layout.py               # Layouts comunes
│   │
│   └── pages/                 # 13 tableros
│       ├── home.py                      # Dashboard principal
│       ├── generacion.py                # Generación general
│       ├── generacion_fuentes_unificado.py # Generación por fuentes
│       ├── generacion_hidraulica_hidrologia.py # Hidrología
│       ├── restricciones.py             # Restricciones eléctricas
│       ├── transmision.py               # Transmisión
│       ├── distribucion.py              # Distribución
│       ├── comercializacion.py          # Comercialización
│       ├── perdidas.py                  # Pérdidas
│       ├── metricas.py                  # Base de datos métricas
│       ├── metricas_piloto.py           # Prototipo nuevas métricas
│       └── config.py                    # Configuración páginas
│
├── etl/                       # 📥 Scripts ETL (10 archivos)
│   ├── etl_todas_metricas_xm.py     # ETL principal (193 métricas)
│   ├── etl_xm_to_postgres.py        # Pipeline XM → PostgreSQL
│   ├── etl_transmision.py           # ETL transmisión UPME
│   ├── etl_distribucion.py          # ETL distribución
│   ├── etl_comercializacion.py      # ETL comercialización
│   ├── validaciones.py              # Validaciones ETL
│   ├── validaciones_rangos.py       # Rangos XM (193 métricas)
│   └── config_*.py                  # Configuraciones ETL
│
├── scripts/                   # 🛠️ Scripts mantenimiento
│   ├── actualizar_incremental.py     # Actualización incremental datos
│   ├── train_predictions.py          # Entrenamiento ML (Prophet/SARIMA)
│   ├── migrate_sqlite_to_postgresql.py # Script migración BD
│   ├── limpiar_datos_corruptos.py    # Limpieza datos
│   └── ops/                          # Scripts operativos
│
├── tasks/                     # 📋 Tareas Celery
│   └── etl_tasks.py
│
├── tests/                     # ✅ Tests automatizados
│   ├── smoke_test_dashboard.py
│   ├── test_integracion_indicadores.py
│   └── verificaciones/
│
├── docs/                      # 📚 Documentación técnica
│   ├── informes_mensuales/         # Informes SECOP II
│   ├── tecnicos/                   # Documentación técnica
│   └── referencias/                # Referencias API XM, SIMEM
│
└── assets/                    # 🎨 Archivos estáticos
    ├── styles.css
    ├── mme-corporate.css
    ├── chat-ia.css
    ├── departamentos_colombia.geojson
    └── images/
```

---

## 🚀 Instalación y Ejecución

### Requisitos Previos
- **Python:** 3.12+
- **PostgreSQL:** 16+ (o SQLite como respaldo)
- **Sistema Operativo:** Linux Ubuntu 20.04+ (recomendado)
- **Acceso a Internet:** Para APIs XM y servicios IA

### 1. Instalación de Dependencias

```bash
# Clonar repositorio
git clone https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git
cd Dashboard_Multipage_MME

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configuración de Variables de Entorno

Crear archivo `.env` en la raíz del proyecto:

```bash
# Base de Datos PostgreSQL
USE_POSTGRES=True
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=portal_energetico
POSTGRES_USER=tu_usuario
POSTGRES_PASSWORD=tu_password

# APIs de IA
GROQ_API_KEY=tu_api_key_groq
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile

# Backup OpenRouter
OPENROUTER_API_KEY=tu_api_key_openrouter

# Configuración Servidor
DEBUG=False
HOST=0.0.0.0
PORT=8050
```

### 3. Inicialización de Base de Datos

**PostgreSQL (Recomendado):**
```bash
# Crear base de datos
sudo -u postgres createdb portal_energetico

# Ejecutar migración (si existe backup)
sudo -u postgres psql -d portal_energetico -f backups/portal_backup.sql

# O ejecutar ETL inicial
python3 etl/etl_todas_metricas_xm.py
```

**SQLite (Desarrollo):**
```bash
# Configurar .env
USE_POSTGRES=False

# Ejecutar ETL
python3 etl/etl_todas_metricas_xm.py
```

### 4. Ejecución del Dashboard

**Modo Producción (Recomendado):**
```bash
# Con systemd service
sudo systemctl start dashboard-mme
sudo systemctl enable dashboard-mme

# O manualmente con Gunicorn
gunicorn -c gunicorn_config.py app:server
```

**Modo Desarrollo:**
```bash
python3 app.py
```

Acceder a: http://localhost:8050

---

## 🤖 Inteligencia Artificial

### Chatbot IA (Groq + Llama 3.3 70B)

El sistema incluye un asistente de IA conversacional para análisis energético:

- **Modelo:** Llama 3.3 70B Versatile
- **Proveedor:** Groq (primario), OpenRouter (respaldo)
- **Capacidades:**
  - Consultas SQL conversacionales en lenguaje natural
  - Análisis de tendencias y patrones
  - Resúmenes ejecutivos automáticos
  - Respuestas contextualizadas con datos históricos
- **Acceso:** Widget flotante integrado en todas las páginas

### Machine Learning (Prophet/SARIMA)

Predicciones automáticas de métricas energéticas:

- **Modelos:** Prophet (Facebook) y SARIMA
- **Actualización:** Entrenamiento semanal automático (lunes 3:00 AM)
- **Métricas predichas:** Generación, demanda, precios
- **Tabla:** `predictions` en PostgreSQL

---

## 📥 Sistema ETL Automatizado

### Procesos Programados (9 Cron Jobs)

| Tarea | Frecuencia | Script | Descripción |
|-------|------------|--------|-------------|
| Actualización incremental | Cada 6 horas | `actualizar_incremental.py` | Datos XM actualizados |
| ETL principal | Diario 2:00 AM | `etl_todas_metricas_xm.py` | 193 métricas XM |
| ETL transmisión | Diario 6:30 AM | `etl_transmision.py` | Líneas transmisión UPME |
| ETL distribución | Diario 7:00 AM | `etl_distribucion.py` | Datos distribución |
| ETL comercialización | Diario 7:30 AM | `etl_comercializacion.py` | Datos comercialización |
| Validación post-ETL | Cada 6 horas | `validar_post_etl.sh` | Verificación calidad datos |
| Entrenamiento ML | Semanal (lunes 3:00 AM) | `train_predictions.py` | Re-entrenamiento modelos |
| Documentación | Diario 23:00 | `actualizar_documentacion.py` | Auto-documentación |
| Limpieza logs | Mensual | `find logs/ -mtime +60 -delete` | Retención 60 días |

### Ejecución Manual ETL

```bash
# ETL completo (193 métricas XM)
python3 etl/etl_todas_metricas_xm.py

# ETL específico
python3 etl/etl_transmision.py --days 7 --clean
python3 etl/etl_distribucion.py
python3 etl/etl_comercializacion.py

# Validación post-ETL
bash scripts/ops/verificar_post_etl.sh
```

---

## 🛠️ Tecnologías

### Backend
- **Framework:** Dash (Plotly) + Flask
- **Base de Datos:** PostgreSQL 16+ (SQLite como respaldo)
- **Servidor Web:** Gunicorn (18-19 workers threaded)
- **ORM/Queries:** psycopg2 + pandas
- **ETL:** pydataxm (API XM oficial)

### Frontend
- **Framework:** Dash Bootstrap Components
- **Gráficas:** Plotly.js
- **Estilos:** CSS personalizado (MME corporativo)
- **Componentes:** Chat widget IA, navbar activo, filtros dinámicos

### Inteligencia Artificial
- **Modelos:** Llama 3.3 70B (Groq), Prophet, SARIMA
- **Proveedores:** Groq API, OpenRouter (respaldo)
- **Librerías:** openai, prophet, statsmodels

### DevOps
- **Proceso Manager:** systemd
- **Tareas Asíncronas:** Celery + Redis
- **Monitoreo:** Logs + health checks
- **Backup:** Automático diario (PostgreSQL dump)

---

## 📚 Documentación

### Informes Mensuales (SECOP II)
- [Informe Comparativo Diciembre 2025 vs Febrero 2026](docs/informes_mensuales/INSPECCION_COMPARATIVA_DIC2025_FEB2026.md)
- [Resumen Ejecutivo Enero 2026](docs/informes_mensuales/RESUMEN_EJECUTIVO_ENERO_2026_SECOP_II.md)

### Documentación Técnica
- [Arquitectura Completa](docs/INFORME_ARQUITECTURA_COMPLETA_2026-01-31.md)
- [Plan Refactorización Hidrología](docs/PLAN_REFACTORIZACION_HIDROLOGIA_2026.md)
- [Mejoras Monitoreo](docs/MEJORAS_MONITOREO_2026-02-01.md)
- [Reporte Bugs Capa Datos](docs/REPORTE_BUGS_CAPA_DATOS.md)
- [Resultados Inspección Tableros](docs/RESULTADOS_INSPECCION_TABLEROS.md)

### Migración PostgreSQL
- [Plan Migración PostgreSQL](PLAN_MIGRACION_POSTGRESQL_2026-02-02.md)
- [Resumen Migración Completada](RESUMEN_MIGRACION_COMPLETADA_2026-02-02.md)
- [Cambios Técnicos PostgreSQL](CAMBIOS_POSTGRESQL_2026-02-02.md)

---

## 🔧 Administración del Sistema

### Servicios Systemd

```bash
# Dashboard principal
sudo systemctl status dashboard-mme
sudo systemctl restart dashboard-mme
sudo systemctl logs -f -u dashboard-mme

# Celery workers
sudo systemctl status celery-worker
sudo systemctl restart celery-worker
```

### Monitoreo

```bash
# Estado general del sistema
bash scripts/ops/verificar_sistema.sh

# Monitoreo ETL
bash scripts/ops/monitorear_etl.sh

# Gestión servidor
bash scripts/ops/manage-server.sh
```

### Backup y Recuperación

```bash
# Backup manual PostgreSQL
sudo -u postgres pg_dump portal_energetico > backups/portal_backup_$(date +%Y%m%d).sql

# Restaurar backup
sudo -u postgres psql -d portal_energetico -f backups/portal_backup_20260202.sql
```

---

## 🎯 Roadmap

### Completado ✅
- [x] Migración PostgreSQL (12.4M registros)
- [x] Arquitectura DDD (16 servicios)
- [x] Chatbot IA operativo (Llama 3.3 70B)
- [x] 13 tableros implementados
- [x] ETL automatizado (9 cron jobs)
- [x] Documentación técnica completa

### En Progreso ⏳
- [ ] Fix tablero Generación/Fuentes (datos vacíos)
- [ ] Verificación modelos ML (archivos .pkl)
- [ ] Tablero Pérdidas (estructura creada)

### Planificado 📋
- [ ] API REST con FastAPI (endpoints públicos)
- [ ] Tests automatizados (cobertura 80%+)
- [ ] Optimización índices PostgreSQL
- [ ] Dashboard de monitoreo Grafana

---

## 📞 Soporte

**Desarrollador:** Melissa de Jesús Cardona Navarro  
**Contrato:** GGC-0316-2026  
**Repositorio:** https://github.com/MelissaCardona2003/Dashboard_Multipage_MME  
**Última actualización:** 2 de febrero de 2026

---

## 📄 Licencia

Este proyecto es propiedad del **Ministerio de Minas y Energía de Colombia**.

---

**Ministerio de Minas y Energía - Colombia 2026**
