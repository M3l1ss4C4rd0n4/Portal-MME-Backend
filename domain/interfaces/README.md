# Domain Interfaces (Ports) - Arquitectura Hexagonal

## 📌 Propósito

Este directorio contiene las **interfaces (ports)** que definen los contratos entre la capa de **Domain** y la capa de **Infrastructure**, siguiendo los principios de **Arquitectura Limpia** y **Hexagonal**.

## 🎯 Principio de Inversión de Dependencias (DIP)

### ❌ ANTES (Violación del DIP)
```python
# domain/services/generation_service.py
from infrastructure.database.repositories.metrics_repository import MetricsRepository

class GenerationService:
    def __init__(self):
        self.repo = MetricsRepository()  # ❌ Depende de implementación concreta
```

**Problema:** Domain depende de Infrastructure (viola la Regla de Dependencia)

### ✅ DESPUÉS (Cumple DIP)
```python
# domain/services/generation_service.py
from domain.interfaces.repositories import IMetricsRepository

class GenerationService:
    def __init__(self, repository: IMetricsRepository):  # ✅ Depende de abstracción
        self.repo = repository
```

**Beneficio:** Domain solo conoce la interfaz, no la implementación

## 📁 Estructura

```
domain/interfaces/
├── __init__.py              # Exporta todas las interfaces
├── repositories.py          # Interfaces de repositorios (BD)
├── data_sources.py          # Interfaces de fuentes externas (APIs)
├── database.py              # Interfaces de gestión de BD
└── README.md               # Este archivo
```

## 🔌 Interfaces Disponibles

> Corregido 2026-09-01: esta sección documentaba 9 interfaces; el código real (`grep "^class I" domain/interfaces/*.py`) tiene **17**. Las 8 faltantes son las agregadas durante la construcción de la ontología de datos (Fases 1-28 del plan de "Portal MME → Plataforma de Inteligencia Analítica").

### Repositorios (Acceso a Datos)

| Interface | Implementación | Propósito |
|-----------|----------------|-----------|
| `IMetricsRepository` | `MetricsRepository` | Métricas energéticas |
| `ICommercialRepository` | `CommercialRepository` | Datos de comercialización |
| `IDistributionRepository` | `DistributionRepository` | Datos de distribución |
| `ITransmissionRepository` | `TransmissionRepository` | Líneas de transmisión |
| `IPredictionsRepository` | `PredictionsRepository` | Predicciones ML |
| `IGeografiaRepository` | `GeografiaRepository` | Ontología — geografía DANE (departamento/municipio) |
| `IEmpresaRepository` | `EmpresaRepository` | Ontología — empresa/NIT, alias, interventorías |
| `IProyectoRepository` | `ProyectoRepository` | Ontología — proyecto (contratos OR, Colombia Solar, FENOGE) |
| `IMetricaRepository` | `MetricaRepository` | Ontología — catálogo de métricas (`dim_metrica`) |
| `IRecursoRepository` | `RecursoRepository` | Ontología — planta/recurso (`dim_recurso`) |
| `IContratoRepository` | `ContratoRepository` | Ontología — detalle de contrato de supervisión por id |
| `ISemanticSearchRepository` | `SemanticSearchRepository` | RAG — búsqueda vectorial + full-text sobre informes/contratos indexados |

### Fuentes de Datos Externas

| Interface | Implementación | Propósito |
|-----------|----------------|-----------|
| `IXMDataSource` | `XMService` | API de XM (pydataxm) |
| `ISIMEMDataSource` | `SIMEMService` | API SIMEM (transmisión) |
| `IIDEAMDataSource` | (implementación en `infrastructure/`) | Datos climatológicos IDEAM |

### Gestión de Base de Datos

| Interface | Implementación | Propósito |
|-----------|----------------|-----------|
| `IDatabaseManager` | `DatabaseManager` | Gestión de conexiones |
| `IConnectionManager` | `PostgreSQLConnectionManager` | Pool de conexiones |

## 🚀 Cómo Usar

### 1. Implementar la Interface (Infrastructure)

```python
# infrastructure/database/repositories/metrics_repository.py
from domain.interfaces.repositories import IMetricsRepository

class MetricsRepository(IMetricsRepository):  # ✅ Implementa interface
    def get_metric_data(self, metric_id, start_date, end_date):
        # Implementación específica PostgreSQL
        pass
```

### 2. Usar en el Servicio de Dominio

```python
# domain/services/generation_service.py
from domain.interfaces.repositories import IMetricsRepository

class GenerationService:
    def __init__(self, repository: IMetricsRepository):
        self.repo = repository  # ✅ Inyección de dependencia
    
    def get_daily_generation(self, start_date, end_date):
        return self.repo.get_metric_data('Gene', start_date, end_date)
```

### 3. Componer en el Punto de Entrada

```python
# app.py o factory
from domain.services.generation_service import GenerationService
from infrastructure.database.repositories.metrics_repository import MetricsRepository

# Crear dependencias (Infrastructure)
repo = MetricsRepository()

# Inyectar en servicio (Domain)
service = GenerationService(repository=repo)
```

## 🔄 Plan de Migración (Sin Romper Nada)

> Corregido 2026-09-01: esta sección describía la migración como "siguiente fase"/"fase final" pendientes. Ya están hechas — verificado que los repositorios de la ontología (`GeografiaRepository`, `EmpresaRepository`, `ProyectoRepository`, `MetricaRepository`, `RecursoRepository`, `ContratoRepository`) implementan sus interfaces y se inyectan vía `core/container.py` (patrón lazy-singleton, ej. `get_geografia_repository()`), consumidos por `OntologiaService` con DI real, no imports directos de infraestructura.

### Fase 1 — Crear interfaces: ✅ COMPLETADA
- [x] Interfaces creadas en `domain/interfaces/`
- [x] Contratos y propósitos documentados

### Fase 2 — Implementar interfaces: ✅ COMPLETADA
- [x] Los repositorios reales implementan sus interfaces (`class MetricsRepository(IMetricsRepository)`, etc.)
- [x] Compatible hacia atrás durante la transición

### Fase 3 — Refactorizar servicios con DI real: 🟡 PARCIAL
- [x] Los servicios de la ontología (`OntologiaService`) y varios servicios más nuevos reciben repositorios vía `core/container.py`
- [ ] Algunos servicios más antiguos (`MetricsService`, `GenerationService`, etc.) todavía instancian su repositorio directamente en `__init__` en vez de recibirlo inyectado — no se ha hecho una migración exhaustiva de los ~42 servicios de dominio, solo de los construidos en fases recientes

## ✅ Ventajas de Este Enfoque

### 1. **Testabilidad**
```python
# Mock simple para pruebas
class MockMetricsRepository(IMetricsRepository):
    def get_metric_data(self, ...):
        return pd.DataFrame({'fecha': [...], 'valor': [...]})

# Test
repo_mock = MockMetricsRepository()
service = GenerationService(repo_mock)
assert service.get_daily_generation(...) is not None
```

### 2. **Intercambiabilidad**
Cambiar de PostgreSQL a otra BD sin tocar Domain:
```python
# Antes: PostgreSQL
repo = MetricsRepository()  # PostgreSQL

# Después: MongoDB
repo = MongoMetricsRepository()  # ✅ Implementa IMetricsRepository

# Domain NO se modifica
service = GenerationService(repo)  # ✅ Funciona igual
```

### 3. **Claridad de Contratos**
Las interfaces documentan explícitamente qué operaciones están disponibles.

## 📚 Referencias

- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Hexagonal Architecture - Alistair Cockburn](https://alistair.cockburn.us/hexagonal-architecture/)
- [SOLID Principles - Dependency Inversion](https://en.wikipedia.org/wiki/Dependency_inversion_principle)

## ⚠️ Importante

**ESTAS INTERFACES SON OPCIONALMENTE ADOPTABLES**

El código actual sigue funcionando sin modificaciones. La migración es gradual:
1. ✅ Interfaces creadas (NO rompe nada)
2. ⏳ Implementar interfaces (compatible hacia atrás)
3. ⏳ Refactorizar servicios (cuando sea conveniente)

**NO hay prisa**, el sistema funciona perfectamente ahora.
