# Informe Integral de Arquitectura del Servidor Portal Energético
**Fecha:** 2026-01-31  
**Autor:** GitHub Copilot (Agente de Ingeniería de Sistemas)  
**Alcance:** Inspección completa del repositorio `/home/admonctrlxm/server`

---

## 1. Arquitectura General

El sistema ha evolucionado hacia una **Arquitectura Limpia (Clean Architecture)** o hexagonal, separando claramente la interfaz de usuario, la lógica de negocio y el acceso a datos.

### 1.1 Diagrama de Capas

```mermaid
graph TD
    User((Usuario Web)) <--> UI[Interface Layer\n(Dash Pages)]
    
    subgraph "Application Core"
        UI --> Services[Domain Layer\n(Services)]
        Services --> BizLogic[Business Logic\n(Calculations)]
    end
    
    subgraph "Infrastructure Layer"
        Services --> Repos[Repositories\n(SQLite)]
        Services --> ExtAPI[External Adapters\n(XM / SIMEM API)]
        ETL[ETL Scripts\n(Python/Cron)] --> Repos
    end
```

### 1.2 Punto de Entrada y Ciclo de Vida
1.  **Entrada:** `app.py` es el punto de entrada. Inicializa la aplicación llamando a `core/app_factory.py`.
2.  **Web Server:** `wsgi.py` expone `app.server` para Gunicorn (configurado en `gunicorn_config.py`).
3.  **Ruteo:** Se utiliza **Dash Pages** (plugin nativo). Las páginas se registran automáticamente desde `interface/pages/*.py` usando `register_page`.
4.  **Inicialización:** `core/app_factory.py`:
    *   Carga variables de entorno (`.env`).
    *   Configura Logging (`infrastructure/logging`).
    *   Registra layouts globales (Navbar, Chatbot).
    *   No registra páginas manualmente (usa auto-discovery), pero controla callbacks globales.

---

## 2. Estructura de Carpetas y Archivos

### 2.1 `core/` (Núcleo de Configuración)
Configuraciones transversales que no dependen del dominio.
*   `app_factory.py`: **Vital**. Fábrica que crea la instancia `dash.Dash` y conecta componentes globales.
*   `config.py` / `config_simem.py`: Constantes de configuración y mapeos de códigos SIMEM.
*   `validators.py` / `exceptions.py`: Manejo estandarizado de errores y validación de tipos básicos.

### 2.2 `domain/` (Capa de Negocio - **El Corazón**)
Contiene la lógica pura del negocio, agnóstica de la base de datos o la interfaz web.
*   `services/`:
    *   `metrics_service.py`: Normaliza series de tiempo, decide si leer de BD o API. **Esencial**.
    *   `transmission_service.py`: Lógica para líneas de transmisión. **Esencial**.
    *   `generation_service.py`: Gestión de datos de generación.
    *   `system_service.py`: Chequeos de salud del sistema.

### 2.3 `infrastructure/` (Implementación Técnica)
Detalles de implementación técnica (BD, Archivos, APIs).
*   `database/`:
    *   `repositories/metrics_repository.py`: SQL para leer/escribir métricas.
    *   `repositories/transmission_repository.py`: SQL para líneas de transmisión.
    *   `manager.py`: Singleton para gestión de conexiones SQLite.
    *   `simem_metrics.db` / `connection.py`: Controladores de bajo nivel.
*   `external/`:
    *   `xm_service.py`: Adaptador para la librería `pydataxm`.
*   `logging/`: Configuración centralizada de trazas.

### 2.4 `interface/` (Capa de Presentación)
Código específico de Dash (UI).
*   `pages/`: Cada archivo es una URL del portal.
    *   `metricas.py`: Tablero de Métricas (Moderno, usa `MetricsService`).
    *   `transmision.py`: Tablero de Transmisión (Moderno, usa `TransmissionService`).
    *   `generacion.py`: Tablero de Generación (Moderno, usa `MetricsService`).
    *   `distribucion.py` / `comercializacion.py`: **Estado Mixto**. Aún importan directamente `infrastructure.external`.
*   `components/`: Widgets reusables (Navbar, Filtros, Chatbot).

### 2.5 `etl/` (Procesos de Extracción y Carga)
Scripts que corren en segundo plano (backend).
*   `etl_xm_to_sqlite.py`: Script MAESTRO. Descarga métricas diarias de XM y las guarda en SQLite.
*   `etl_transmision.py`: Descarga topología de red de SIMEM.
*   `config_metricas.py`: Define qué variables se descargan.

---

## 3. Flujo de Datos y Automatización

### 3.1 Flujo "End-to-End"
El sistema opera bajo un modelo **Híbrido con Caché Persistente (DB First)**.

1.  **Ingesta (ETL):** `cron` ejecuta scripts en `etl/` $\rightarrow$ `API XM/SIMEM` $\rightarrow$ `SQLite (metrics, transmission tables)`.
2.  **Lectura (App):**
    *   Usuario carga página $\rightarrow$ `interface/pages/X.py`.
    *   Página llama a `domain/services/X_service.py`.
    *   Servicio consulta `infrastructure/database/repositories/X_repository.py`.
    *   **Fallback:** Si la DB está vacía o desactualizada, el repositorio/servicio devuelve vacío o intenta llamar a la API externa en tiempo real (lento).

### 3.2 Automatización Detectada
Se confirmó la existencia de automatización mediante CRON (evidencia en `scripts/setup_etl_cron.sh`).

*   **06:00 AM**: `etl/etl_xm_to_sqlite.py` (Métricas diarias).
*   **06:30 AM**: `etl/etl_transmision.py`.

La base de datos **se actualiza sola** siempre que el servicio cron y el servidor estén encendidos.

---

## 4. Análisis Tablero por Tablero

| Tablero | Estado Arquitectónico | Fuente de Datos Principal | Observaciones |
| :--- | :--- | :--- | :--- |
| **Inicio** (`home.py`) | ✅ Moderno | N/A | Landing page, navegación. |
| **Métricas** (`metricas.py`) | ✅ Excelente | `MetricsService` | Completamente migrado a Hexagonal. Maneja errores de datos vacíos. |
| **Transmisión** (`transmision.py`) | ✅ Excelente | `TransmissionService` | **Arquitectura Pura ETL-Driven**. El servicio NO conecta a APIs externas; lee exclusivamente de una BD local (`lineas_transmision`) poblada asíncronamente por `etl/etl_transmision.py`. Esto garantiza carga instantánea (0 latencia de red) y estabilidad. |
| **Generación** (`generacion.py`) | ✅ Bueno | `MetricsService` | Utiliza el servicio de métricas genérico correctamente. |
| **Distribución** (`distribucion.py`) | ⚠️ Deuda Técnica | `infrastructure.external` | **No usa Servicio de Dominio**. Llama directo a `get_objetoAPI`. Funciona pero viola capas. |
| **Comercialización** (`comercializacion.py`) | ⚠️ Deuda Técnica | `infrastructure.external` | **No usa Servicio de Dominio**. Llama funciones raw de infraestructura. |
| **Restricciones** (`restricciones.py`) | ⚠️ Revisar | Mixto | Pendiente de migración completa a repositorios. |

**Causas de posibles fallos en tableros rotos:**
1.  **Distribución/Comercialización:** Al depender de llamadas directas a API en tiempo real (sin cache DB intermedio), si la API XM falla o es lenta (timeout), el tablero se rompe (Spinners infinitos).
2.  **Datos:** Si el ETL de las 6 AM falla, los servicios bien construidos (Transmisión) muestran datos de ayer. Los mal construidos (Distribución) intentan buscar datos HOY en tiempo real y fallan.

---

## 5. Clasificación de Archivos (Esenciales vs. Prescindibles)

### 🚨 ESENCIALES (No Tocar / Tocar con Cuidado)
*   `app.py`, `wsgi.py`, `gunicorn_config.py`: Arranque del servidor.
*   `core/app_factory.py`: Configuración vital.
*   `domain/services/*.py`: Lógica de negocio.
*   `infrastructure/database/repositories/*.py`: Acceso a datos.
*   `etl/*.py`: Scripts de llenado de datos.
*   `requirements.txt`: Dependencias.
*   `portal_energetico.db`: Base de datos (asegurar backups).

### 🗑️ CANDIDATOS A BORRAR / LEGACY
*   `legacy_archive/`: **TODA** esta carpeta contiene código muerto (`src_backup`, `pages_old`). Se puede archivar en otro medio y eliminar del repo de producción para reducir ruido.
*   `test_transmission_debug.py`: Parece un script de prueba manual temporal. Mover a `tests/manual/` o borrar.
*   Scripts sueltos en raíz que no sean de arranque.

---

## 6. Evaluación para API Pública

### 6.1 ¿Estamos listos?
**Parcialmente.**
*   **Backend (Data & Logic):** `MetricsService` y `TransmissionService` están listos. Exponen métodos claros (`get_metric_series`, `get_transmission_lines`) que devuelven DataFrames limpios.
*   **Database:** SQLite es robusto para lectura, pero si se abre una API pública con alta concurrencia, SQLite podría bloquearse por escrituras concurrentes (ETL). Un paso a PostgreSQL sería recomendado para una API real.

### 6.2 Estrategia de API Recomendada
No exponer directamente los métodos de Dash.
*   **Propuesta:** Crear un módulo `api/` usando **FastAPI** (u otro Blueprint de Flask dentro de la misma app) que monte endpoints REST.
*   **Endpoints:**
    *   `GET /api/v1/metrics/{metric_id}` -> Llama a `MetricsService.get_metric_series_hybrid`.
    *   `GET /api/v1/transmission/lines` -> Llama a `TransmissionService.get_transmission_lines`.

### 6.3 Tareas Imprescindibles antes de la API
1.  **Migrar Distribución y Comercialización:** Deben usar Servicios (`DistributionService`, `CommercialService`) y Repositorios. No se puede exponer una API basada en llamadas directas inestables.
2.  **Estandarizar Nombres:** Asegurar que todos los servicios devuelvan JSON/Dicts con claves consistentes (actualmente devuelven DataFrames, la capa API deberá serializarlos a JSON).

## 7. Recomendaciones Finales

1.  **Completar la Refactorización:** Prioridad alta a migrar `distribucion.py` y `comercializacion.py` a la arquitectura de Servicios + Repositorios.
2.  **Limpieza:** Eliminar `legacy_archive` del servidor de producción.
3.  **Monitoreo ETL:** Implementar un log más visible o alertas si el cron de las 06:00 AM falla, ya que es el corazón de los datos.
4.  **API:** Iniciar con un piloto de API solo para **Transmisión** y **Métricas Generales**, que son los módulos más estables.

---
*Fin del Informe Técnico*
