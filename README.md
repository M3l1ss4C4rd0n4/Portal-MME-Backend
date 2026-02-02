# 🔌 Portal Energético Colombia - Dashboard MME

> **Sistema Avanzado de Monitoreo y Análisis del Sector Energético Colombiano**
> **Versión 3.0 (Arquitectura Clean Architecture / DDD)**

Dashboard interactivo con **Inteligencia Artificial**, **Machine Learning** y **Sistema ETL Automático** para análisis en tiempo real del Sistema Interconectado Nacional (SIN).

[![Estado](https://img.shields.io/badge/Estado-Producción-success)]() 
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()
[![Factored](https://img.shields.io/badge/Architecture-DDD-purple)]()

---

## 🏗️ Nueva Arquitectura (2026)

Este proyecto ha sido refactorizado siguiendo principios de **Domain-Driven Design (DDD)** y **Clean Architecture** para asegurar escalabilidad y mantenibilidad.

### Estructura del Proyecto

```
server/
├── core/               # Configuración central, constantes, logs y fábrica de la app
├── domain/             # Lógica de negocio pura (Servicios, Modelos, Interfaces)
│   ├── services/       # Servicios de dominio (AIService, MetricsService, etc.)
│   └── models/         # Modelos de datos
├── infrastructure/     # Implementación técnica (Base de datos, APIs externas)
│   ├── database/       # Repositorios y Singleton DatabaseManager
│   └── external/       # Clientes API (XM, OpenRouter/Groq)
├── interface/          # Capa de presentación (UI/UX)
│   ├── components/     # Componentes visuales reutilizables (Chat, Navbar, Tablas)
│   └── pages/          # Páginas del Dashboard (Dash)
└── assets/             # Archivos estáticos (CSS, JS, Imágenes)
```

## 🚀 Instalación y Ejecución

### Requisitos Previos
- Python 3.12+
- SQLite3
- Acceso a Internet (para API XM y Servicios de IA)

### 1. Configuración de Entorno
Crea un archivo `.env` en la raíz (ver `.env.example` o usar el existente):
```bash
GROQ_API_KEY=tu_api_key
OPENROUTER_API_KEY=tu_api_key_backup
```

### 2. Ejecución

**Modo Producción (Recomendado)**
```bash
./manage-server.sh
# O manualmente:
gunicorn -c gunicorn_config.py app:server
```

**Modo Desarrollo**
```bash
python3 app.py
```

## 🛠️ Tecnologías

- **Backend Framework**: Dash (Plotly) + Flask
- **Base de Datos**: SQLite (Modo WAL habilitado para concurrencia)
- **Servidor Web**: Gunicorn (Threaded Workers)
- **AI/ML**: Llama 3.3 (vía Groq/OpenRouter)

## 📁 Gestión de Datos (ETL)

El sistema cuenta con un pipeline ETL robusto ubicado en `etl/`:
- `etl_todas_metricas_xm.py`: Script maestro de extracción.
- `etl_xm_to_sqlite.py`: Carga y transformación hacia SQLite.

Para actualizar datos manualmente:
```bash
python3 etl/etl_todas_metricas_xm.py --seccion "Generación" --dias 10
```

---
**Ministerio de Minas y Energía - 2026**
