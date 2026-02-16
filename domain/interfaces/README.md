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

### Repositorios (Acceso a Datos)

| Interface | Implementación | Propósito |
|-----------|----------------|-----------|
| `IMetricsRepository` | `MetricsRepository` | Métricas energéticas |
| `ICommercialRepository` | `CommercialRepository` | Datos de comercialización |
| `IDistributionRepository` | `DistributionRepository` | Datos de distribución |
| `ITransmissionRepository` | `TransmissionRepository` | Líneas de transmisión |
| `IPredictionsRepository` | `PredictionsRepository` | Predicciones ML |

### Fuentes de Datos Externas

| Interface | Implementación | Propósito |
|-----------|----------------|-----------|
| `IXMDataSource` | `XMService` | API de XM (pydataxm) |
| `ISIMEMDataSource` | `SIMEMService` | API SIMEM (transmisión) |

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

### Fase Actual: ✅ COMPLETADA
- [x] Crear interfaces en `domain/interfaces/`
- [x] Documentar contratos y propósitos

### Siguiente Fase: Implementar Interfaces
1. Hacer que repositorios implementen interfaces
2. NO modificar servicios aún (compatible hacia atrás)
3. Probar que todo sigue funcionando

### Fase Final: Refactorizar Servicios
1. Modificar servicios para recibir interfaces
2. Implementar inyección de dependencias
3. Eliminar imports directos de infrastructure

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
