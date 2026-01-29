# 🏗️ PLAN DE REFACTORIZACIÓN ARQUITECTÓNICA
## Portal Energético MME - Transformación a Arquitectura Empresarial

**Fecha:** 28 de enero de 2026  
**Ingeniero:** Sistema de Refactorización Automatizada  
**Objetivo:** Transformar proyecto monolítico a arquitectura modular, escalable y lista para APIs

---

## 📋 TABLA DE CONTENIDOS

1. [Análisis de Estructura Actual](#análisis-estructura-actual)
2. [Problemas Identificados](#problemas-identificados)
3. [Estructura Propuesta (Target)](#estructura-propuesta-target)
4. [Plan de Migración por Fases](#plan-de-migración-por-fases)
5. [Refactorización de Código](#refactorización-de-código)
6. [Limpieza de Archivos](#limpieza-de-archivos)
7. [Mejoras de Infraestructura](#mejoras-de-infraestructura)
8. [Sistema ETL y ML](#sistema-etl-y-ml)
9. [Criterios de Calidad](#criterios-de-calidad)
10. [Plan de Pruebas](#plan-de-pruebas)

---

## 📊 ANÁLISIS DE ESTRUCTURA ACTUAL

### Estructura Existente (Simplificada)

```
server/
├── app.py                          # 206 líneas - Punto de entrada monolítico
├── gunicorn_config.py             # Configuración Gunicorn
├── dashboard-mme.service          # Systemd service
├── nginx-dashboard.conf           # Nginx config
├── requirements.txt               # Dependencias
│
├── pages/                         # 21 módulos Dash (páginas del dashboard)
│   ├── __init__.py
│   ├── index_simple_working.py   # Portada
│   ├── generacion.py             # Generación general
│   ├── generacion_fuentes_unificado.py
│   ├── generacion_hidraulica_hidrologia.py
│   ├── transmision.py
│   ├── distribucion.py
│   ├── distribucion_demanda_unificado.py
│   ├── comercializacion.py
│   ├── perdidas.py
│   ├── restricciones.py
│   ├── metricas.py
│   ├── components.py             # ⚠️ Componentes mezclados con páginas
│   ├── config.py                 # ⚠️ Config mezclada con páginas
│   ├── data_loader.py            # ⚠️ Lógica de negocio en carpeta UI
│   └── utils_xm.py               # ⚠️ Duplicación con utils/_xm.py
│
├── componentes/                   # 1 componente (chat IA)
│   ├── chat_ia.py                # 525 líneas - UI + lógica mezcladas
│   └── __pycache__/
│
├── utils/                         # 8 utilidades mezcladas
│   ├── __init__.py
│   ├── db_manager.py             # 679 líneas - Conexión SQLite
│   ├── health_check.py           # 195 líneas - Health endpoint
│   ├── logger.py                 # Configuración logging
│   ├── ai_agent.py               # 451 líneas - Agente IA con GROQ
│   ├── _xm.py                    # Cliente API XM
│   ├── ml_predictor.py           # Predicciones ML
│   └── data_utils.py             # Helpers generales
│
├── etl/                          # Sistema ETL
│   ├── etl_xm_to_sqlite.py      # 660 líneas - ETL principal
│   ├── config_metricas.py       # 93 métricas configuradas
│   ├── validaciones.py          # Validaciones post-ETL
│   └── __pycache__/
│
├── assets/                       # Frontend assets
│   ├── animations.css
│   ├── chat-ia.css
│   ├── mme-corporate.css
│   ├── professional-style.css
│   ├── *.js                     # Scripts JS sueltos
│   └── images/                  # Imágenes corporativas
│
├── docs/                        # Documentación (ya organizada en Fase 1)
│   ├── analisis_historicos/
│   ├── informes_mensuales/
│   ├── tecnicos/
│   └── referencias/
│
├── logs/                        # Logs (limpiados en Fase 1)
│   ├── gunicorn_*.log
│   ├── etl/
│   └── validaciones/
│
├── scripts/                     # Scripts diversos (organizado en Fase 1)
│   ├── utilidades/
│   └── analisis_historico/
│
├── tests/                       # Tests mínimos
│   └── verificaciones/
│
├── backups/                     # Backups BD (organizado en Fase 1)
│   └── database/
│
├── config/                      # Configs (creado en Fase 3)
│   └── logrotate.conf
│
├── notebooks/                   # Notebooks Jupyter (legacy)
│   ├── fuente_*.ipynb
│   └── metricas_repl.ipynb
│
├── legacy/                      # Código legacy archivado
│   └── README.md
│
├── backup_originales/           # ⚠️ Archivos legacy sueltos
├── siea/                        # ⚠️ Sistema SIEA (sin usar?)
├── sql/                         # Schemas SQL
└── api-energia/                 # ⚠️ API Node.js separada (desacoplada?)
```

---

## ⚠️ PROBLEMAS IDENTIFICADOS

### 🔴 Críticos (Arquitectura)

1. **Monolito en app.py**
   - 206 líneas mezclando configuración, inicialización, health check, routes
   - Imports de todas las páginas hardcodeados
   - No hay separación entre config, app factory, y server

2. **Mezcla de responsabilidades en `/pages`**
   - `components.py` y `config.py` NO deberían estar en pages/
   - `data_loader.py` es lógica de negocio, no UI
   - `utils_xm.py` duplica funcionalidad de `utils/_xm.py`

3. **Componentes sin separación UI/Lógica**
   - `componentes/chat_ia.py` (525 líneas) mezcla HTML/Dash + callbacks + lógica
   - `utils/ai_agent.py` tiene lógica de IA pero está en "utils"

4. **ETL sin capa de servicios**
   - `etl/etl_xm_to_sqlite.py` (660 líneas) hace todo directamente
   - No hay abstracción entre ETL y DB
   - Validaciones separadas pero no integradas

5. **Utils como cajón de sastre**
   - `utils/` tiene desde DB hasta ML hasta logging
   - No hay organización clara por dominio

6. **Sin preparación para APIs**
   - No hay capa de servicios reutilizable
   - Lógica acoplada a Dash (callbacks)
   - Imposible reutilizar para REST API

### 🟡 Importantes (Código)

7. **Falta tipado estático**
   - Pocas type hints en funciones críticas
   - Dificulta mantenimiento y refactoring

8. **Logging inconsistente**
   - Algunos módulos usan logging, otros print()
   - No hay estructura de logs unificada

9. **Configuración dispersa**
   - .env en raíz, config.py en pages/, constantes hardcodeadas
   - Falta un config/ centralizado

10. **Tests mínimos**
    - Solo tests/verificaciones/ con scripts básicos
    - Sin unit tests, sin integration tests

### 🟢 Menores (Limpieza)

11. **Archivos legacy**
    - `backup_originales/` con generadores antiguos
    - `notebooks/` con experimentos no documentados
    - `siea/` sin uso claro
    - `api-energia/` desacoplada (Node.js)

12. **Duplicación de assets**
    - Varios CSS/JS que podrían consolidarse
    - Imágenes sin optimizar

13. **Cache Python residual**
    - Aún 66 archivos .pyc (de 11,850 iniciales)
    - __pycache__ en varios lugares

---

## 🎯 ESTRUCTURA PROPUESTA (TARGET)

### Arquitectura Clean/Hexagonal Adaptada

```
server/
│
├── 📄 app.py                      # 30 líneas - Solo inicialización
├── 📄 wsgi.py                     # Entry point para Gunicorn
├── 📄 requirements.txt
├── 📄 .env                        # Variables de entorno
├── 📄 .env.example                # Template para .env
├── 📄 README.md                   # Documentación principal
│
├── 🏗️ core/                       # ⭐ NUEVO - Núcleo de la aplicación
│   ├── __init__.py
│   ├── app_factory.py            # Factory de Dash app
│   ├── config.py                 # Configuración centralizada
│   ├── constants.py              # Constantes del sistema
│   ├── exceptions.py             # Excepciones personalizadas
│   └── middleware.py             # Middlewares (logging, auth futuro)
│
├── 🎨 presentation/               # ⭐ NUEVO - Capa de presentación (UI)
│   ├── __init__.py
│   ├── pages/                    # Páginas Dash (solo UI + callbacks)
│   │   ├── __init__.py
│   │   ├── index.py             # Portada
│   │   ├── generacion/          # Módulo generación
│   │   │   ├── __init__.py
│   │   │   ├── general.py
│   │   │   ├── fuentes.py
│   │   │   └── hidrologia.py
│   │   ├── transmision/
│   │   │   ├── __init__.py
│   │   │   └── transmision.py
│   │   ├── distribucion/
│   │   │   ├── __init__.py
│   │   │   ├── distribucion.py
│   │   │   └── demanda.py
│   │   ├── comercializacion/
│   │   │   ├── __init__.py
│   │   │   └── comercializacion.py
│   │   ├── perdidas/
│   │   │   ├── __init__.py
│   │   │   └── perdidas.py
│   │   ├── restricciones/
│   │   │   ├── __init__.py
│   │   │   └── restricciones.py
│   │   └── metricas/
│   │       ├── __init__.py
│   │       └── metricas.py
│   │
│   ├── components/               # Componentes reutilizables
│   │   ├── __init__.py
│   │   ├── navbar.py            # Navbar común
│   │   ├── footer.py            # Footer
│   │   ├── charts.py            # Gráficos reutilizables
│   │   ├── tables.py            # Tablas reutilizables
│   │   ├── cards.py             # Cards/KPIs
│   │   ├── filters.py           # Filtros de fecha/entidad
│   │   └── chat/                # Chat IA modularizado
│   │       ├── __init__.py
│   │       ├── ui.py            # UI del chat
│   │       └── callbacks.py     # Callbacks del chat
│   │
│   └── layouts/                  # Layouts base
│       ├── __init__.py
│       ├── main_layout.py       # Layout principal con navbar
│       └── page_layout.py       # Layout base para páginas
│
├── 🧠 domain/                     # ⭐ NUEVO - Lógica de negocio (Domain)
│   ├── __init__.py
│   ├── models/                   # Modelos de dominio (dataclasses/Pydantic)
│   │   ├── __init__.py
│   │   ├── metric.py            # Modelo Metrica
│   │   ├── prediction.py        # Modelo Predicción
│   │   ├── catalog.py           # Modelo Catálogo
│   │   └── health.py            # Modelo Health Check
│   │
│   └── services/                 # Servicios de dominio (lógica de negocio)
│       ├── __init__.py
│       ├── metrics_service.py   # Operaciones sobre métricas
│       ├── predictions_service.py  # Operaciones ML
│       ├── catalog_service.py   # Gestión catálogos
│       ├── ai_service.py        # Servicio de IA (chat, análisis)
│       └── health_service.py    # Health checks
│
├── 🔌 infrastructure/             # ⭐ NUEVO - Infraestructura (adaptadores)
│   ├── __init__.py
│   ├── database/                 # Capa de persistencia
│   │   ├── __init__.py
│   │   ├── connection.py        # Conexión DB (pool, context managers)
│   │   ├── repositories/        # Repositorios (patrón Repository)
│   │   │   ├── __init__.py
│   │   │   ├── base_repository.py
│   │   │   ├── metrics_repository.py
│   │   │   ├── predictions_repository.py
│   │   │   └── catalog_repository.py
│   │   ├── migrations/          # Migraciones (Alembic futuro)
│   │   │   └── schema.sql
│   │   └── models.py            # SQLAlchemy models (ORM)
│   │
│   ├── external/                 # Integraciones externas
│   │   ├── __init__.py
│   │   ├── xm_client.py         # Cliente API XM (pydataxm)
│   │   ├── groq_client.py       # Cliente GROQ API
│   │   └── openrouter_client.py # Cliente OpenRouter
│   │
│   ├── ml/                       # Machine Learning
│   │   ├── __init__.py
│   │   ├── models/              # Modelos ML
│   │   │   ├── __init__.py
│   │   │   ├── prophet_model.py
│   │   │   ├── sarima_model.py
│   │   │   └── ensemble_model.py
│   │   ├── training/            # Entrenamiento
│   │   │   ├── __init__.py
│   │   │   ├── trainer.py
│   │   │   └── evaluator.py
│   │   └── inference/           # Inferencia
│   │       ├── __init__.py
│   │       └── predictor.py
│   │
│   └── etl/                      # ETL pipeline
│       ├── __init__.py
│       ├── pipeline.py          # Orquestador ETL
│       ├── extractors/          # Extractores
│       │   ├── __init__.py
│       │   └── xm_extractor.py
│       ├── transformers/        # Transformadores
│       │   ├── __init__.py
│       │   ├── unit_converter.py
│       │   └── data_cleaner.py
│       ├── loaders/             # Cargadores
│       │   ├── __init__.py
│       │   └── db_loader.py
│       ├── validators/          # Validadores
│       │   ├── __init__.py
│       │   └── data_validator.py
│       └── config/              # Config ETL
│           ├── __init__.py
│           └── metrics_config.py
│
├── 🛠️ shared/                     # ⭐ NUEVO - Código compartido
│   ├── __init__.py
│   ├── logging/                  # Logging unificado
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── formatters.py
│   ├── utils/                    # Utilidades generales
│   │   ├── __init__.py
│   │   ├── date_utils.py
│   │   ├── text_utils.py
│   │   └── number_utils.py
│   └── decorators/               # Decoradores útiles
│       ├── __init__.py
│       ├── retry.py
│       └── cache.py
│
├── 🌐 api/                        # ⭐ NUEVO - API REST (futuro)
│   ├── __init__.py
│   ├── main.py                   # FastAPI app
│   ├── routes/                   # Endpoints
│   │   ├── __init__.py
│   │   ├── metrics.py
│   │   ├── predictions.py
│   │   └── health.py
│   ├── schemas/                  # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── metric_schema.py
│   │   └── prediction_schema.py
│   └── dependencies.py           # FastAPI dependencies
│
├── 🧪 tests/                      # Tests organizados
│   ├── __init__.py
│   ├── unit/                     # Tests unitarios
│   │   ├── __init__.py
│   │   ├── test_services/
│   │   ├── test_repositories/
│   │   └── test_utils/
│   ├── integration/              # Tests de integración
│   │   ├── __init__.py
│   │   ├── test_etl/
│   │   └── test_api/
│   ├── e2e/                      # Tests end-to-end
│   │   └── __init__.py
│   ├── fixtures/                 # Fixtures de prueba
│   │   └── sample_data.py
│   └── conftest.py               # Configuración pytest
│
├── 📁 deployment/                 # ⭐ NUEVO - Deployment configs
│   ├── gunicorn_config.py
│   ├── nginx.conf
│   ├── systemd/
│   │   └── dashboard-mme.service
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   └── scripts/
│       ├── deploy.sh
│       ├── backup.sh
│       └── restore.sh
│
├── 📁 assets/                     # Assets frontend (limpiados)
│   ├── css/
│   │   ├── main.css             # CSS principal consolidado
│   │   ├── components.css       # CSS componentes
│   │   └── themes.css           # Temas/variables
│   ├── js/
│   │   ├── main.js              # JS principal
│   │   └── animations.js        # Animaciones
│   └── images/
│       ├── logos/
│       └── icons/
│
├── 📁 docs/                       # Documentación (ya organizada)
│   ├── architecture/             # ⭐ NUEVO
│   │   ├── README.md
│   │   ├── architecture_decision_records/
│   │   └── diagrams/
│   ├── api/                      # ⭐ NUEVO
│   │   └── openapi.yaml
│   ├── deployment/               # Despliegue
│   ├── user_guides/              # Guías de usuario
│   └── developer_guides/         # Guías de desarrollo
│
├── 📁 scripts/                    # Scripts de mantenimiento
│   ├── maintenance/
│   │   ├── cleanup_logs.py
│   │   ├── backup_db.py
│   │   └── vacuum_db.py
│   ├── migration/                # Scripts de migración
│   │   └── migrate_to_new_structure.py
│   └── monitoring/
│       └── health_monitor.py
│
├── 📁 logs/                       # Logs (con logrotate)
│   ├── app/
│   ├── etl/
│   ├── ml/
│   └── api/
│
├── 📁 data/                       # Datos auxiliares
│   ├── cache/                    # Cache de datos
│   └── exports/                  # Exportaciones
│
├── 📁 backups/                    # Backups
│   └── database/
│
└── 📄 portal_energetico.db        # Base de datos SQLite (root por ahora)
```

---

## 🚀 PLAN DE MIGRACIÓN POR FASES

### FASE 4: Reestructuración de Carpetas (2 horas)

**Objetivo:** Crear nueva estructura sin romper funcionalidad actual

#### 4.1 Crear estructura nueva (sin mover archivos aún)

```bash
# Crear directorios principales
mkdir -p core presentation domain infrastructure shared api tests/unit tests/integration deployment

# Crear subdirectorios presentation
mkdir -p presentation/pages presentation/components presentation/layouts

# Crear subdirectorios domain
mkdir -p domain/models domain/services

# Crear subdirectorios infrastructure
mkdir -p infrastructure/database/repositories infrastructure/external infrastructure/ml/{models,training,inference} infrastructure/etl/{extractors,transformers,loaders,validators,config}

# Crear subdirectorios shared
mkdir -p shared/logging shared/utils shared/decorators

# Crear subdirectorios api
mkdir -p api/routes api/schemas

# Crear subdirectorios deployment
mkdir -p deployment/systemd deployment/docker deployment/scripts

# Crear subdirectorios docs nuevos
mkdir -p docs/architecture/architecture_decision_records docs/architecture/diagrams docs/api

# Limpiar assets
mkdir -p assets/css assets/js assets/images/{logos,icons}
```

#### 4.2 Archivos a mantener en su ubicación actual (temporalmente)

- ✅ `app.py` - Se refactorizará, pero sigue siendo entry point
- ✅ `portal_energetico.db` - En raíz hasta migración
- ✅ `requirements.txt` - En raíz
- ✅ `.env` - En raíz (agregar .env.example)
- ✅ `logs/` - Estructura ya limpia
- ✅ `backups/` - Ya organizado

#### 4.3 Archivos a mover en Fase 4

**De `pages/` a `presentation/pages/`:**
- ✅ Todos los `*_page.py` (renombrados después)
- ❌ `components.py` → mover a `presentation/components/`
- ❌ `config.py` → mover a `core/config.py`
- ❌ `data_loader.py` → refactorizar a `domain/services/`
- ❌ `utils_xm.py` → eliminar (duplicado)

**De `componentes/` a `presentation/components/`:**
- ✅ `chat_ia.py` → refactorizar a `chat/` modularizado

**De `utils/` a nuevas ubicaciones:**
- `db_manager.py` → `infrastructure/database/connection.py`
- `health_check.py` → `domain/services/health_service.py`
- `logger.py` → `shared/logging/logger.py`
- `ai_agent.py` → `domain/services/ai_service.py`
- `_xm.py` → `infrastructure/external/xm_client.py`
- `ml_predictor.py` → `infrastructure/ml/inference/predictor.py`
- `data_utils.py` → `shared/utils/` (dividir por tipo)

**De `etl/` a `infrastructure/etl/`:**
- `etl_xm_to_sqlite.py` → refactorizar en `pipeline.py` + extractors/transformers/loaders
- `config_metricas.py` → `infrastructure/etl/config/metrics_config.py`
- `validaciones.py` → `infrastructure/etl/validators/data_validator.py`

**Deployment:**
- `gunicorn_config.py` → `deployment/gunicorn_config.py`
- `dashboard-mme.service` → `deployment/systemd/dashboard-mme.service`
- `nginx-dashboard.conf` → `deployment/nginx.conf`
- Scripts de `scripts/utilidades/` → `deployment/scripts/`

#### 4.4 Archivos a archivar o eliminar

**Archivar a `legacy/`:**
- ✅ `backup_originales/` → `legacy/backup_originales/`
- ✅ `notebooks/` (después de revisión) → `legacy/notebooks/`
- ⚠️ `siea/` (revisar uso primero) → `legacy/siea/` si no se usa
- ⚠️ `api-energia/` (revisar relación) → puede quedar separada

**Eliminar completamente:**
- ❌ `pages/utils_xm.py` (duplicado de utils/_xm.py)
- ❌ `__pycache__/` residuales (66 archivos)
- ❌ Assets CSS/JS no usados (consolidar)

---

### FASE 5: Refactorización de Código (8 horas)

**Objetivo:** Migrar código a nueva arquitectura con separación de concerns

#### 5.1 Core - Configuración y App Factory (1 hora)

**Crear `core/config.py`:**
```python
"""Configuración centralizada del sistema"""
from pydantic import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Portal Energético MME"
    DEBUG: bool = False
    PORT: int = 8050
    HOST: str = "0.0.0.0"
    
    # Database
    DATABASE_PATH: str = "portal_energetico.db"
    DATABASE_TIMEOUT: float = 10.0
    
    # API XM
    XM_API_TIMEOUT: int = 30
    XM_API_RETRIES: int = 3
    
    # AI
    GROQ_API_KEY: str
    OPENROUTER_API_KEY: str
    AI_MODEL: str = "llama-3.3-70b-versatile"
    
    # ML
    ML_FORECAST_DAYS: int = 90
    ML_RETRAIN_HOURS: int = 168  # Semanal
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

**Crear `core/app_factory.py`:**
```python
"""Factory de aplicación Dash"""
import dash
import dash_bootstrap_components as dbc
from dash import Dash

from core.config import get_settings
from shared.logging import get_logger
from presentation.layouts.main_layout import create_main_layout

logger = get_logger(__name__)
settings = get_settings()

def create_app() -> Dash:
    """
    Factory de aplicación Dash
    
    Returns:
        Aplicación Dash configurada
    """
    logger.info("="*70)
    logger.info(f"Inicializando {settings.APP_NAME}")
    logger.info("="*70)
    
    # Crear app Dash
    app = Dash(
        __name__,
        use_pages=True,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
            "/assets/css/main.css",
        ],
        suppress_callback_exceptions=True
    )
    
    # Configurar layout
    app.layout = create_main_layout()
    
    # Registrar health check
    _register_health_check(app.server)
    
    logger.info(f"✅ App creada - Puerto: {settings.PORT}")
    
    return app

def _register_health_check(server):
    """Registra endpoint de health check"""
    from flask import jsonify
    from domain.services.health_service import check_system_health
    
    @server.route('/health')
    def health():
        health_status = check_system_health()
        status_code = 200 if health_status['status'] in ['healthy', 'degraded'] else 503
        return jsonify(health_status), status_code
```

**Refactorizar `app.py` (de 206 → 30 líneas):**
```python
"""
Portal Energético MME
Entry point de la aplicación
"""
from core.app_factory import create_app
from core.config import get_settings

settings = get_settings()
app = create_app()
server = app.server

if __name__ == "__main__":
    app.run(
        debug=settings.DEBUG,
        host=settings.HOST,
        port=settings.PORT
    )
```

**Crear `wsgi.py` (para Gunicorn):**
```python
"""WSGI entry point para Gunicorn"""
from app import server as application

# Gunicorn usará: gunicorn wsgi:application -c deployment/gunicorn_config.py
```

#### 5.2 Domain - Modelos y Servicios (2 horas)

**Crear `domain/models/metric.py`:**
```python
"""Modelo de dominio: Métrica energética"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class Metric:
    """Métrica energética"""
    fecha: date
    metrica: str
    entidad: str
    recurso: Optional[str]
    valor_gwh: float
    unidad: str
    fecha_actualizacion: date
    
    def to_dict(self) -> dict:
        """Convertir a diccionario"""
        return {
            'fecha': self.fecha.isoformat(),
            'metrica': self.metrica,
            'entidad': self.entidad,
            'recurso': self.recurso,
            'valor_gwh': self.valor_gwh,
            'unidad': self.unidad,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat()
        }
```

**Crear `domain/services/metrics_service.py`:**
```python
"""Servicio de dominio: Métricas energéticas"""
from datetime import date
from typing import List, Optional
import pandas as pd

from domain.models.metric import Metric
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from shared.logging import get_logger

logger = get_logger(__name__)

class MetricsService:
    """Servicio para operaciones con métricas"""
    
    def __init__(self, repository: MetricsRepository):
        self.repository = repository
    
    def get_metrics(
        self,
        metrica: str,
        entidad: str,
        fecha_inicio: date,
        fecha_fin: Optional[date] = None,
        recurso: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Obtener métricas del sistema
        
        Args:
            metrica: Código de métrica ('Gene', 'DemaCome', etc.)
            entidad: Entidad ('Sistema', 'Recurso', etc.)
            fecha_inicio: Fecha inicial
            fecha_fin: Fecha final (opcional)
            recurso: Filtro por recurso (opcional)
            
        Returns:
            DataFrame con métricas
        """
        logger.info(f"Obteniendo métricas: {metrica}, {entidad}, {fecha_inicio}-{fecha_fin}")
        
        metrics = self.repository.find_by_criteria(
            metrica=metrica,
            entidad=entidad,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin or fecha_inicio,
            recurso=recurso
        )
        
        logger.info(f"✅ {len(metrics)} registros encontrados")
        return metrics
    
    def get_latest_data_date(self, metrica: str) -> Optional[date]:
        """Obtener fecha más reciente de datos para una métrica"""
        return self.repository.get_latest_date(metrica)
    
    def calculate_totals_by_resource(
        self,
        metrica: str,
        fecha_inicio: date,
        fecha_fin: date
    ) -> pd.DataFrame:
        """
        Calcular totales agrupados por recurso
        
        Returns:
            DataFrame con columnas: recurso, total_gwh
        """
        df = self.get_metrics(
            metrica=metrica,
            entidad='Recurso',
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        if df.empty:
            return pd.DataFrame(columns=['recurso', 'total_gwh'])
        
        totals = df.groupby('recurso')['valor_gwh'].sum().reset_index()
        totals.columns = ['recurso', 'total_gwh']
        
        return totals.sort_values('total_gwh', ascending=False)
```

#### 5.3 Infrastructure - Repositorios (2 horas)

**Crear `infrastructure/database/connection.py`:**
```python
"""Gestión de conexiones a base de datos"""
import sqlite3
from contextlib import contextmanager
from typing import Generator
from pathlib import Path

from core.config import get_settings
from shared.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

DB_PATH = Path(settings.DATABASE_PATH)

@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager para conexión SQLite
    
    Uso:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metrics")
    
    Yields:
        Conexión SQLite
    """
    conn = None
    try:
        conn = sqlite3.connect(
            str(DB_PATH),
            timeout=settings.DATABASE_TIMEOUT,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Error de conexión SQLite: {e}")
        raise
    finally:
        if conn:
            conn.close()

class ConnectionPool:
    """Pool de conexiones SQLite (singleton)"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Obtener conexión del pool"""
        with get_connection() as conn:
            yield conn
```

**Crear `infrastructure/database/repositories/base_repository.py`:**
```python
"""Repositorio base con operaciones comunes"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional
import pandas as pd

from infrastructure.database.connection import get_connection
from shared.logging import get_logger

T = TypeVar('T')
logger = get_logger(__name__)

class BaseRepository(ABC, Generic[T]):
    """Repositorio base con patrón Repository"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
    
    def find_all(self) -> pd.DataFrame:
        """Obtener todos los registros"""
        query = f"SELECT * FROM {self.table_name}"
        return self._execute_query(query)
    
    def find_by_id(self, id_value: int) -> Optional[T]:
        """Buscar por ID"""
        query = f"SELECT * FROM {self.table_name} WHERE id = ?"
        df = self._execute_query(query, (id_value,))
        return df.iloc[0].to_dict() if not df.empty else None
    
    def count(self) -> int:
        """Contar registros"""
        query = f"SELECT COUNT(*) as count FROM {self.table_name}"
        with get_connection() as conn:
            cursor = conn.cursor()
            result = cursor.execute(query).fetchone()
            return result['count']
    
    def _execute_query(self, query: str, params: tuple = ()) -> pd.DataFrame:
        """Ejecutar query y retornar DataFrame"""
        try:
            with get_connection() as conn:
                df = pd.read_sql_query(query, conn, params=params)
                return df
        except Exception as e:
            logger.error(f"Error ejecutando query: {e}")
            logger.debug(f"Query: {query}, Params: {params}")
            raise
    
    @abstractmethod
    def create(self, entity: T) -> int:
        """Crear nuevo registro"""
        pass
    
    @abstractmethod
    def update(self, entity: T) -> bool:
        """Actualizar registro"""
        pass
    
    @abstractmethod
    def delete(self, id_value: int) -> bool:
        """Eliminar registro"""
        pass
```

**Crear `infrastructure/database/repositories/metrics_repository.py`:**
```python
"""Repositorio de métricas energéticas"""
from datetime import date
from typing import Optional, List
import pandas as pd

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.models.metric import Metric
from shared.logging import get_logger

logger = get_logger(__name__)

class MetricsRepository(BaseRepository[Metric]):
    """Repositorio para tabla metrics"""
    
    def __init__(self):
        super().__init__('metrics')
    
    def find_by_criteria(
        self,
        metrica: str,
        entidad: str,
        fecha_inicio: date,
        fecha_fin: date,
        recurso: Optional[str] = None,
        recurso_filter: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Buscar métricas por criterios
        
        Args:
            metrica: Código métrica
            entidad: Entidad
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin
            recurso: Filtro recurso único
            recurso_filter: Lista de recursos
            
        Returns:
            DataFrame con métricas
        """
        query = """
            SELECT fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion
            FROM metrics
            WHERE metrica = ? AND entidad = ? AND fecha BETWEEN ? AND ?
        """
        params = [metrica, entidad, fecha_inicio.isoformat(), fecha_fin.isoformat()]
        
        # Filtro por recurso único
        if recurso:
            query += " AND recurso = ?"
            params.append(recurso)
        
        # Filtro por lista de recursos
        if recurso_filter:
            placeholders = ','.join('?' * len(recurso_filter))
            query += f" AND recurso IN ({placeholders})"
            params.extend(recurso_filter)
        
        query += " ORDER BY fecha, recurso"
        
        return self._execute_query(query, tuple(params))
    
    def get_latest_date(self, metrica: str) -> Optional[date]:
        """Obtener fecha más reciente para una métrica"""
        query = "SELECT MAX(fecha) as max_fecha FROM metrics WHERE metrica = ?"
        df = self._execute_query(query, (metrica,))
        
        if not df.empty and df['max_fecha'].iloc[0]:
            return pd.to_datetime(df['max_fecha'].iloc[0]).date()
        return None
    
    def get_unique_resources(self, metrica: str) -> List[str]:
        """Obtener lista de recursos únicos para una métrica"""
        query = """
            SELECT DISTINCT recurso 
            FROM metrics 
            WHERE metrica = ? AND recurso IS NOT NULL
            ORDER BY recurso
        """
        df = self._execute_query(query, (metrica,))
        return df['recurso'].tolist()
    
    def create(self, entity: Metric) -> int:
        """Insertar nueva métrica"""
        # Implementar si es necesario
        raise NotImplementedError()
    
    def update(self, entity: Metric) -> bool:
        """Actualizar métrica"""
        # Implementar si es necesario
        raise NotImplementedError()
    
    def delete(self, id_value: int) -> bool:
        """Eliminar métrica"""
        # Implementar si es necesario
        raise NotImplementedError()
```

#### 5.4 Presentation - Páginas y Componentes (2 horas)

**Refactorizar páginas** (ejemplo: `presentation/pages/generacion/general.py`):

```python
"""
Página: Generación - Vista General
Muestra métricas generales de generación energética
"""
import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
from datetime import date, timedelta

from presentation.components.filters import create_date_filter
from presentation.components.charts import create_line_chart, create_bar_chart
from presentation.components.cards import create_kpi_card
from domain.services.metrics_service import MetricsService
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from shared.logging import get_logger

dash.register_page(__name__, path='/generacion/general', name='Generación General')

logger = get_logger(__name__)

# Inyección de dependencias
metrics_repo = MetricsRepository()
metrics_service = MetricsService(metrics_repo)

def layout():
    """Layout de la página"""
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H1("📊 Generación Energética - Vista General"),
                html.P("Análisis de generación total del sistema eléctrico colombiano")
            ])
        ], className="mb-4"),
        
        # Filtros
        dbc.Row([
            dbc.Col([
                create_date_filter(
                    id_prefix='gen-general',
                    default_days=30
                )
            ])
        ], className="mb-4"),
        
        # KPIs
        dbc.Row([
            dbc.Col(html.Div(id='gen-general-kpis'), md=12)
        ], className="mb-4"),
        
        # Gráficos
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='gen-general-chart-time')
            ], md=12)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='gen-general-chart-resources')
            ], md=6),
            dbc.Col([
                dcc.Graph(id='gen-general-chart-pie')
            ], md=6)
        ])
    ], fluid=True)

@callback(
    [Output('gen-general-kpis', 'children'),
     Output('gen-general-chart-time', 'figure'),
     Output('gen-general-chart-resources', 'figure'),
     Output('gen-general-chart-pie', 'figure')],
    [Input('gen-general-date-start', 'date'),
     Input('gen-general-date-end', 'date')]
)
def update_content(fecha_inicio_str: str, fecha_fin_str: str):
    """
    Actualizar contenido de la página
    
    Args:
        fecha_inicio_str: Fecha inicio (ISO format)
        fecha_fin_str: Fecha fin (ISO format)
        
    Returns:
        Tuple con (kpis, chart_time, chart_resources, chart_pie)
    """
    try:
        # Parsear fechas
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
        
        logger.info(f"Actualizando generación general: {fecha_inicio} - {fecha_fin}")
        
        # Obtener datos
        df_sistema = metrics_service.get_metrics(
            metrica='Gene',
            entidad='Sistema',
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        df_recursos = metrics_service.get_metrics(
            metrica='Gene',
            entidad='Recurso',
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        # Calcular KPIs
        total_gwh = df_sistema['valor_gwh'].sum()
        promedio_diario = df_sistema['valor_gwh'].mean()
        dias = (fecha_fin - fecha_inicio).days + 1
        
        kpis = dbc.Row([
            dbc.Col(create_kpi_card("Total Generado", f"{total_gwh:,.0f} GWh", "⚡"), md=4),
            dbc.Col(create_kpi_card("Promedio Diario", f"{promedio_diario:,.0f} GWh", "📊"), md=4),
            dbc.Col(create_kpi_card("Período", f"{dias} días", "📅"), md=4)
        ])
        
        # Gráfico temporal
        chart_time = create_line_chart(
            df_sistema,
            x='fecha',
            y='valor_gwh',
            title='Generación Total del Sistema',
            xlabel='Fecha',
            ylabel='Generación (GWh)'
        )
        
        # Gráfico por recursos
        df_totales = metrics_service.calculate_totals_by_resource(
            metrica='Gene',
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        chart_resources = create_bar_chart(
            df_totales.head(10),
            x='recurso',
            y='total_gwh',
            title='Top 10 Recursos por Generación',
            xlabel='Recurso',
            ylabel='Generación Total (GWh)'
        )
        
        # Gráfico pie
        chart_pie = create_pie_chart(
            df_totales.head(5),
            values='total_gwh',
            names='recurso',
            title='Distribución Top 5 Recursos'
        )
        
        return kpis, chart_time, chart_resources, chart_pie
        
    except Exception as e:
        logger.error(f"Error actualizando página: {e}", exc_info=True)
        # Retornar componentes vacíos con mensaje de error
        error_msg = html.Div("⚠️ Error cargando datos", className="alert alert-danger")
        return error_msg, {}, {}, {}
```

**Componentes reutilizables** (`presentation/components/charts.py`):

```python
"""Componentes de gráficos reutilizables"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional

def create_line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    xlabel: str = "",
    ylabel: str = "",
    color: Optional[str] = None
) -> go.Figure:
    """
    Crear gráfico de líneas
    
    Args:
        df: DataFrame con datos
        x: Columna para eje X
        y: Columna para eje Y
        title: Título del gráfico
        xlabel: Etiqueta eje X
        ylabel: Etiqueta eje Y
        color: Columna para agrupar por color (opcional)
        
    Returns:
        Figura Plotly
    """
    fig = px.line(
        df,
        x=x,
        y=y,
        color=color,
        title=title,
        labels={x: xlabel, y: ylabel}
    )
    
    fig.update_layout(
        hovermode='x unified',
        template='plotly_white',
        title_font_size=18,
        title_font_color='#003366'
    )
    
    return fig

def create_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    xlabel: str = "",
    ylabel: str = "",
    color: Optional[str] = None
) -> go.Figure:
    """Crear gráfico de barras"""
    fig = px.bar(
        df,
        x=x,
        y=y,
        color=color,
        title=title,
        labels={x: xlabel, y: ylabel}
    )
    
    fig.update_layout(
        template='plotly_white',
        title_font_size=18,
        title_font_color='#003366'
    )
    
    return fig

def create_pie_chart(
    df: pd.DataFrame,
    values: str,
    names: str,
    title: str
) -> go.Figure:
    """Crear gráfico pie"""
    fig = px.pie(
        df,
        values=values,
        names=names,
        title=title
    )
    
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(
        template='plotly_white',
        title_font_size=18,
        title_font_color='#003366'
    )
    
    return fig
```

#### 5.5 Infrastructure/ETL - Refactorizar Pipeline (1 hora)

**Crear `infrastructure/etl/pipeline.py`:**

```python
"""
Pipeline ETL principal
Orquesta extracción, transformación y carga de datos desde API XM
"""
from datetime import date, timedelta
from typing import List

from infrastructure.etl.extractors.xm_extractor import XMExtractor
from infrastructure.etl.transformers.unit_converter import UnitConverter
from infrastructure.etl.loaders.db_loader import DBLoader
from infrastructure.etl.validators.data_validator import DataValidator
from infrastructure.etl.config.metrics_config import METRICAS_CONFIG
from shared.logging import get_logger

logger = get_logger(__name__)

class ETLPipeline:
    """Pipeline ETL para métricas energéticas"""
    
    def __init__(self):
        self.extractor = XMExtractor()
        self.converter = UnitConverter()
        self.loader = DBLoader()
        self.validator = DataValidator()
    
    def run(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        metricas: List[str] = None
    ) -> dict:
        """
        Ejecutar pipeline ETL completo
        
        Args:
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin
            metricas: Lista de métricas (None = todas)
            
        Returns:
            Diccionario con resultados: {
                'success': bool,
                'metrics_processed': int,
                'records_inserted': int,
                'errors': list
            }
        """
        logger.info("="*70)
        logger.info("INICIANDO PIPELINE ETL")
        logger.info(f"Período: {fecha_inicio} - {fecha_fin}")
        logger.info("="*70)
        
        # Seleccionar métricas a procesar
        if metricas is None:
            metricas_to_process = METRICAS_CONFIG.keys()
        else:
            metricas_to_process = metricas
        
        results = {
            'success': True,
            'metrics_processed': 0,
            'records_inserted': 0,
            'errors': []
        }
        
        for metrica in metricas_to_process:
            try:
                logger.info(f"\n📊 Procesando: {metrica}")
                
                # 1. EXTRACT
                df_raw = self.extractor.extract(metrica, fecha_inicio, fecha_fin)
                
                if df_raw.empty:
                    logger.warning(f"  ⚠️ Sin datos para {metrica}")
                    continue
                
                # 2. TRANSFORM
                df_transformed = self.converter.convert(df_raw, metrica)
                
                # 3. VALIDATE
                is_valid, validation_errors = self.validator.validate(df_transformed, metrica)
                
                if not is_valid:
                    logger.error(f"  ❌ Validación falló: {validation_errors}")
                    results['errors'].append({
                        'metrica': metrica,
                        'errors': validation_errors
                    })
                    results['success'] = False
                    continue
                
                # 4. LOAD
                records_inserted = self.loader.load(df_transformed, metrica)
                
                results['metrics_processed'] += 1
                results['records_inserted'] += records_inserted
                
                logger.info(f"  ✅ {metrica}: {records_inserted} registros insertados")
                
            except Exception as e:
                logger.error(f"  ❌ Error procesando {metrica}: {e}", exc_info=True)
                results['errors'].append({
                    'metrica': metrica,
                    'error': str(e)
                })
                results['success'] = False
        
        logger.info("="*70)
        logger.info(f"ETL COMPLETADO - Métricas: {results['metrics_processed']}, Registros: {results['records_inserted']}")
        logger.info("="*70)
        
        return results
    
    def run_incremental(self, days_back: int = 7) -> dict:
        """
        Ejecutar ETL incremental (últimos N días)
        
        Args:
            days_back: Días hacia atrás desde hoy
            
        Returns:
            Resultados del pipeline
        """
        fecha_fin = date.today()
        fecha_inicio = fecha_fin - timedelta(days=days_back)
        
        return self.run(fecha_inicio, fecha_fin)
```

---

### FASE 6: Tests y Calidad (2 horas)

**Crear estructura de tests:**

```python
# tests/conftest.py
"""Fixtures de pytest"""
import pytest
from pathlib import Path
import sqlite3

@pytest.fixture
def test_db_path(tmp_path):
    """Crear BD de prueba temporal"""
    db_path = tmp_path / "test_portal.db"
    # Crear esquema
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            metrica TEXT NOT NULL,
            entidad TEXT NOT NULL,
            recurso TEXT,
            valor_gwh REAL NOT NULL,
            unidad TEXT,
            fecha_actualizacion DATE DEFAULT CURRENT_DATE
        );
    """)
    conn.close()
    return db_path

@pytest.fixture
def metrics_repository(test_db_path, monkeypatch):
    """Repository con BD de prueba"""
    from infrastructure.database.repositories.metrics_repository import MetricsRepository
    monkeypatch.setattr('infrastructure.database.connection.DB_PATH', test_db_path)
    return MetricsRepository()
```

```python
# tests/unit/test_services/test_metrics_service.py
"""Tests unitarios para MetricsService"""
import pytest
from datetime import date
from domain.services.metrics_service import MetricsService

def test_get_metrics_success(metrics_repository):
    """Test: obtener métricas exitosamente"""
    service = MetricsService(metrics_repository)
    
    fecha = date(2026, 1, 1)
    df = service.get_metrics(
        metrica='Gene',
        entidad='Sistema',
        fecha_inicio=fecha,
        fecha_fin=fecha
    )
    
    assert not df.empty  # Debería tener datos de fixture
    assert 'valor_gwh' in df.columns

def test_calculate_totals_by_resource(metrics_repository):
    """Test: calcular totales por recurso"""
    service = MetricsService(metrics_repository)
    
    df = service.calculate_totals_by_resource(
        metrica='Gene',
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 1, 31)
    )
    
    assert not df.empty
    assert list(df.columns) == ['recurso', 'total_gwh']
    assert df['total_gwh'].sum() > 0
```

---

### FASE 7: Deployment y Documentación (1 hora)

**Actualizar deployment configs:**

```yaml
# deployment/docker/docker-compose.yml
version: '3.8'

services:
  dashboard:
    build:
      context: ../..
      dockerfile: deployment/docker/Dockerfile
    ports:
      - "8050:8050"
    environment:
      - DATABASE_PATH=/app/data/portal_energetico.db
      - GROQ_API_KEY=${GROQ_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    volumes:
      - ../../portal_energetico.db:/app/data/portal_energetico.db
      - ../../logs:/app/logs
    restart: unless-stopped
    command: gunicorn wsgi:application -c deployment/gunicorn_config.py
```

**Documentar arquitectura:**

```markdown
# docs/architecture/README.md

# Arquitectura del Sistema

## Principios de Diseño

1. **Separación de Concerns (SoC)**
   - Presentation: UI y callbacks Dash
   - Domain: Lógica de negocio
   - Infrastructure: Adaptadores (DB, APIs externas, ML)

2. **Dependency Inversion**
   - Domain no depende de Infrastructure
   - Infrastructure implementa interfaces de Domain
   - Inyección de dependencias

3. **Single Responsibility**
   - Cada módulo/clase tiene una responsabilidad clara
   - Services para lógica de negocio
   - Repositories para acceso a datos
   - Components para UI reutilizable

## Flujo de Datos

```
External APIs → Infrastructure/ETL → Infrastructure/Database
                                              ↓
UI (Dash) ← Presentation/Pages ← Domain/Services ← Infrastructure/Repositories
```

## Capas

### Core
Configuración y factory de aplicación. Sin lógica de negocio.

### Presentation
UI y callbacks Dash. Solo maneja interacción con usuario.
Llama a Services para obtener datos.

### Domain
Lógica de negocio pura. Independiente de frameworks.
Models (dataclasses) y Services (operaciones de negocio).

### Infrastructure
Adaptadores a tecnologías externas:
- Database: SQLite con patrón Repository
- External: APIs (XM, GROQ, OpenRouter)
- ML: Modelos Prophet/SARIMA
- ETL: Pipeline de datos

### Shared
Código compartido entre capas: logging, utils, decorators.

## Patrones Utilizados

- **Repository Pattern**: Abstracción de acceso a datos
- **Factory Pattern**: Creación de app Dash
- **Service Pattern**: Lógica de negocio encapsulada
- **Dependency Injection**: Inyección manual en callbacks
```

---

## 🗑️ LIMPIEZA DE ARCHIVOS

### Archivos a Archivar

**Mover a `legacy/`:**

```bash
# Archivos legacy comprobados
mv backup_originales/ legacy/
mv notebooks/ legacy/  # Después de revisar
mv siea/ legacy/  # Si no se usa

# Crear README en legacy
cat > legacy/README.md << 'EOF'
# Archivos Legacy

Este directorio contiene código antiguo que ya no se usa en producción.

## Contenido

- `backup_originales/`: Generadores antiguos (pre-refactorización)
- `notebooks/`: Notebooks Jupyter de exploración
- `siea/`: Sistema SIEA (sin uso confirmado)

⚠️ **NO USAR ESTOS ARCHIVOS EN PRODUCCIÓN**
EOF
```

### Archivos a Eliminar

```bash
# Cache Python residual
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete

# Duplicados confirmados
rm -f pages/utils_xm.py  # Duplicado de utils/_xm.py
```

### Assets a Consolidar

```bash
# Consolidar CSS
cat assets/*.css > assets/css/main.css
# Revisar y eliminar CSS individuales si no se usan

# Consolidar JS
cat assets/*.js > assets/js/main.js
# Revisar y eliminar JS individuales
```

---

## ⚙️ MEJORAS DE INFRAESTRUCTURA

### Preparación para PostgreSQL

**Crear abstracción con SQLAlchemy:**

```python
# infrastructure/database/models.py
"""Modelos SQLAlchemy (preparación PostgreSQL)"""
from sqlalchemy import Column, Integer, String, Float, Date, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class MetricModel(Base):
    """Modelo ORM para métricas"""
    __tablename__ = 'metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False, index=True)
    metrica = Column(String, nullable=False, index=True)
    entidad = Column(String, nullable=False)
    recurso = Column(String, nullable=True)
    valor_gwh = Column(Float, nullable=False)
    unidad = Column(String)
    fecha_actualizacion = Column(Date)
    
    __table_args__ = (
        Index('idx_metrica_fecha', 'metrica', 'fecha'),
        Index('idx_metrica_entidad_recurso', 'metrica', 'entidad', 'recurso'),
    )
```

### Systemd Service Mejorado

```ini
# deployment/systemd/dashboard-mme.service
[Unit]
Description=Dashboard Portal Energético MME
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=notify
User=admonctrlxm
Group=admonctrlxm
WorkingDirectory=/home/admonctrlxm/server
Environment="PATH=/home/admonctrlxm/server/venv/bin:/usr/bin"
Environment="PYTHONPATH=/home/admonctrlxm/server"
EnvironmentFile=/home/admonctrlxm/server/.env
ExecStart=/home/admonctrlxm/server/venv/bin/gunicorn wsgi:application -c deployment/gunicorn_config.py
ExecReload=/bin/kill -s HUP $MAINPID
ExecStop=/bin/kill -s TERM $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

# Recursos
LimitNOFILE=65536
LimitNPROC=4096

# Security (sin cambios)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/admonctrlxm/server/logs
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db-shm
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db-wal
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
```

---

## 📏 CRITERIOS DE CALIDAD

### Code Style

```python
# .flake8
[flake8]
max-line-length = 100
exclude = .git,__pycache__,legacy,venv
ignore = E203,W503

# .pylintrc
[MASTER]
ignore=legacy,venv
max-line-length=100

[MESSAGES CONTROL]
disable=missing-docstring,too-few-public-methods
```

### Type Checking

```ini
# mypy.ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
ignore_missing_imports = True

[mypy-legacy.*]
ignore_errors = True
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black
        language_version: python3.10
  
  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.1
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

---

## ✅ CHECKLIST DE MIGRACIÓN

### Fase 4: Estructura
- [ ] Crear directorios nuevos (core, presentation, domain, infrastructure, shared, api)
- [ ] Mover archivos deployment a deployment/
- [ ] Mover assets y consolidar CSS/JS
- [ ] Archivar legacy (backup_originales/, notebooks/, siea/)
- [ ] Eliminar duplicados (pages/utils_xm.py, cache residual)

### Fase 5: Refactorización
- [ ] Crear core/config.py y core/app_factory.py
- [ ] Refactorizar app.py (206 → 30 líneas)
- [ ] Crear domain/models/ (Metric, Prediction, Health)
- [ ] Crear domain/services/ (MetricsService, PredictionsService, AIService, HealthService)
- [ ] Crear infrastructure/database/repositories/ (BaseRepository, MetricsRepository)
- [ ] Refactorizar infrastructure/etl/ (pipeline, extractors, transformers, loaders)
- [ ] Refactorizar presentation/pages/ (separar UI de lógica)
- [ ] Crear presentation/components/ (charts, tables, cards, filters)
- [ ] Crear shared/logging/ y shared/utils/

### Fase 6: Tests
- [ ] Crear tests/conftest.py con fixtures
- [ ] Tests unitarios de services
- [ ] Tests unitarios de repositories
- [ ] Tests de integración ETL
- [ ] Configurar pytest.ini

### Fase 7: Deployment
- [ ] Actualizar deployment/gunicorn_config.py
- [ ] Actualizar deployment/systemd/dashboard-mme.service
- [ ] Crear deployment/docker/Dockerfile
- [ ] Crear deployment/docker/docker-compose.yml
- [ ] Documentar arquitectura en docs/architecture/

### Calidad
- [ ] Configurar .flake8, .pylintrc, mypy.ini
- [ ] Configurar .pre-commit-config.yaml
- [ ] Añadir type hints en funciones críticas
- [ ] Actualizar docstrings
- [ ] Verificar logging consistente

---

## 📊 MÉTRICAS DE ÉXITO

### Antes de Refactorización
- app.py: 206 líneas (monolito)
- Estructura: 8 carpetas raíz
- Duplicación: 2 archivos (_xm.py)
- Tests: 0 tests automatizados
- Type hints: <10% funciones
- Acoplamiento: Alto (páginas → DB directo)
- Reutilización: Baja (lógica en callbacks)

### Después de Refactorización (Target)
- app.py: 30 líneas (factory pattern)
- Estructura: 15 carpetas organizadas por capa
- Duplicación: 0 (eliminada)
- Tests: >50 tests automatizados
- Type hints: >80% funciones públicas
- Acoplamiento: Bajo (capas desacopladas)
- Reutilización: Alta (services, components)
- Preparación API: Lista (services reutilizables)

---

## 🔄 ESTRATEGIA DE MIGRACIÓN GRADUAL

### Enfoque Estrangulation Pattern

1. **Crear nueva estructura en paralelo** (no romper existente)
2. **Migrar módulo por módulo** (empezar con menos críticos)
3. **Mantener compatibilidad** (imports antiguos siguen funcionando)
4. **Tests de regresión** (verificar funcionalidad intacta)
5. **Eliminar código antiguo** (cuando nueva versión esté estable)

### Orden de Migración Sugerido

1. ✅ **shared/** (logging, utils) - Sin dependencias
2. ✅ **core/** (config, app_factory) - Dependencias mínimas
3. ✅ **infrastructure/database/** (connection, repositories) - Base para todo
4. ✅ **domain/models/** - Solo dataclasses
5. ✅ **domain/services/** - Lógica de negocio
6. ✅ **infrastructure/etl/** - Pipeline independiente
7. ✅ **presentation/components/** - UI reutilizable
8. ✅ **presentation/pages/** - Última capa (depende de todo)

---

## 📞 SOPORTE Y PRÓXIMOS PASOS

### Después de Refactorización

1. **Monitoreo post-migración**
   - Verificar performance (tiempos de respuesta)
   - Revisar logs de errores
   - Validar funcionalidad crítica

2. **Documentación adicional**
   - ADRs (Architecture Decision Records)
   - Diagramas UML
   - API documentation (cuando se cree)

3. **Mejoras futuras**
   - Migración a PostgreSQL
   - API REST con FastAPI
   - Autenticación/Autorización
   - Cache distribuido (Redis)
   - Monitoreo con Grafana/Prometheus

---

**Generado:** 28 de enero de 2026  
**Versión:** 1.0  
**Estado:** Plan aprobado, listo para ejecución
