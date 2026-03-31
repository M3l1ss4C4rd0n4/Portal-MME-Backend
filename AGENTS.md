# AGENTS.md - Server Backend MME

## Guía para Agentes de Desarrollo

Información crítica para agentes de IA y desarrolladores del backend del Portal Dirección MME.

---

## 🚨 REGLAS CRÍTICAS

### 1. NUNCA modificar sin:
- Backup verificable
- Confirmación explícita del usuario
- `python -m py_compile archivo.py` sin errores

### 2. SIEMPRE verificar dependencias:
```bash
grep -r "nombre_funcion" --include="*.py" .
```

### 3. NUNCA tocar código en producción sin coordinar

### 4. SIEMPRE ejecutar tests después de cambios:
```bash
pytest tests/ -v --tb=short
```

---

## 📁 Estructura del Proyecto

### Convenciones Python

```
server/
├── api/                      # FastAPI routes
│   ├── main.py              # Entry point
│   └── v1/routes/           # Endpoints
│
├── core/                    # Core infrastructure
│   ├── container.py         # Dependency injection
│   ├── config.py            # Configuration
│   └── app_factory.py       # Dash app factory
│
├── domain/                  # Business logic
│   ├── services/            # Domain services
│   │   ├── __init__.py
│   │   └── nombre_service.py
│   ├── models/              # Pydantic models
│   ├── schemas/             # DTOs
│   └── interfaces/          # Abstract base classes
│
├── infrastructure/          # External adapters
│   ├── database/           # PostgreSQL repositories
│   ├── cache/              # Redis
│   ├── external/           # XM, OneDrive, IDEAM clients
│   └── logging/            # Logging setup
│
├── etl/                     # ETL scripts
│   └── etl_nombre.py
│
└── tests/                   # Tests
    ├── unit/
    └── integration/
```

### Nomenclatura

- **Archivos:** `snake_case.py`
- **Clases:** `PascalCase`
- **Funciones/variables:** `snake_case`
- **Constantes:** `UPPER_CASE`
- **Privados:** `_leading_underscore`

---

## 🔧 Dependency Injection (Container)

### Patrón Correcto

```python
# core/container.py
class DependencyContainer:
    def get_nombre_service(self) -> NombreService:
        repo = self.get_repository()
        return NombreService(repo)

# Uso correcto
from core.container import container
service = container.get_nombre_service()

# ❌ INCORRECTO - No usar container.resolve()
result = container.resolve(INombreService)  # No existe este método
```

### Reglas del Container

1. Cada servicio tiene su propio getter: `get_nombre_service()`
2. Repositorios se inyectan en constructores de servicios
3. NO usar `container.resolve()` - no existe
4. Los getters crean instancias lazy (singleton por request)

---

## 🗄️ Base de Datos

### Connection Pool

```python
# ✅ CORRECTO
from core.database.pool import get_pool

pool = get_pool()
async with pool.acquire() as conn:
    result = await conn.fetch("SELECT * FROM tabla")

# ❌ INCORRECTO - Nunca crear pool nuevo
from psycopg2 import pool
my_pool = pool.SimpleConnectionPool(...)  # NO hacer esto
```

### Variables de Entorno (.env)

```bash
PGHOST=localhost
PGPORT=5432
PGDATABASE=portal_energetico
PGUSER=mme_user
PGPASSWORD=<password>

REDIS_URL=redis://localhost:6379/0
```

---

## 📝 Logging

### Configuración

```python
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# ✅ CORRECTO - Usar estructurado
logger.info("Proceso completado", registros=len(data), tiempo_ms=elapsed)
logger.error("Error conectando BD", error=str(e), reintentos=retries)

# ❌ INCORRECTO - Usar print
print(f"Proceso completado: {len(data)} registros")  # NO hacer esto
```

### Niveles de Log

- `DEBUG`: Información detallada para desarrollo
- `INFO`: Eventos normales del sistema
- `WARNING`: Advertencias, no críticas
- `ERROR`: Errores que afectan operación
- `CRITICAL`: Errores que detienen el sistema

---

## ⚠️ Manejo de Excepciones

### Patrón Correcto

```python
# ✅ CORRECTO - Específico primero, genérico al final
try:
    result = await operation()
except DatabaseConnectionError as e:
    logger.error("Error conexión BD", error=str(e))
    raise ServiceUnavailableException()
except ValidationError as e:
    logger.warning("Datos inválidos", errors=e.errors())
    raise BadRequestException()
except Exception as e:
    logger.exception("Error inesperado")
    raise InternalServerError()

# ❌ INCORRECTO - Solo genérico
try:
    result = await operation()
except Exception as e:  # Captura todo, difícil debuggear
    logger.exception("Error")
```

### Excepciones Personalizadas

```python
# domain/exceptions.py
class DomainException(Exception):
    """Base para excepciones del dominio"""
    pass

class ServiceUnavailableException(DomainException):
    pass

class BadRequestException(DomainException):
    pass
```

---

## 🔌 API FastAPI

### Estructura de Endpoint

```python
# api/v1/routes/ejemplo.py
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_ejemplo_service
from domain.services.ejemplo_service import EjemploService

router = APIRouter(prefix="/ejemplo", tags=["ejemplo"])

@router.get("/")
async def list_ejemplos(
    service: EjemploService = Depends(get_ejemplo_service)
):
    try:
        result = await service.get_all()
        return {"data": result, "status": "success"}
    except Exception as e:
        logger.exception("Error listando ejemplos")
        raise HTTPException(status_code=500, detail=str(e))
```

### Dependencies

```python
# api/dependencies.py
from core.container import container
from domain.services.ejemplo_service import EjemploService

def get_ejemplo_service() -> EjemploService:
    return container.get_ejemplo_service()
```

---

## 🔄 ETL Pipeline

### Estructura de Script ETL

```python
# etl/etl_ejemplo.py
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

class ETLEjemplo:
    def __init__(self):
        self.db_pool = get_pool()
        self.xm_client = XMClient()
    
    async def extract(self):
        """Extraer datos de fuente"""
        logger.info("Extrayendo datos...")
        # ...
    
    async def transform(self, data):
        """Transformar datos"""
        logger.info(f"Transformando {len(data)} registros...")
        # ...
    
    async def load(self, data):
        """Cargar a BD"""
        logger.info("Cargando a BD...")
        # ...
    
    async def run(self):
        """Ejecutar pipeline completo"""
        try:
            data = await self.extract()
            transformed = await self.transform(data)
            await self.load(transformed)
            logger.info("ETL completado exitosamente")
        except Exception as e:
            logger.exception("ETL falló")
            raise

# Entry point
if __name__ == "__main__":
    etl = ETLEjemplo()
    asyncio.run(etl.run())
```

### Scheduling (Celery)

```python
# tasks/etl_tasks.py
from celery import shared_task
from etl.etl_ejemplo import ETLEjemplo

@shared_task
def run_etl_ejemplo():
    etl = ETLEjemplo()
    asyncio.run(etl.run())

# Configuración en celery_config.py
beat_schedule = {
    'etl-ejemplo': {
        'task': 'tasks.etl_tasks.run_etl_ejemplo',
        'schedule': crontab(hour='*/6', minute=0),
    },
}
```

---

## 🧪 Testing

### Tests Unitarios

```python
# tests/unit/services/test_ejemplo_service.py
import pytest
from unittest.mock import Mock, patch
from domain.services.ejemplo_service import EjemploService

@pytest.fixture
def service():
    repo = Mock()
    return EjemploService(repo)

async def test_get_all(service):
    # Arrange
    service.repo.get_all.return_value = ["item1", "item2"]
    
    # Act
    result = await service.get_all()
    
    # Assert
    assert len(result) == 2
    service.repo.get_all.assert_called_once()
```

### Ejecutar Tests

```bash
# Todos los tests
pytest tests/ -v

# Tests específicos
pytest tests/unit/services/test_cu_service.py -v

# Con cobertura
pytest tests/ --cov=server --cov-report=html
```

---

## 🚀 Despliegue

### Systemd Services

```bash
# Ver estado
sudo systemctl status api-mme
sudo systemctl status dashboard-mme

# Restart
sudo systemctl restart api-mme
sudo systemctl restart dashboard-mme

# Logs
sudo journalctl -u api-mme --no-pager -n 50
sudo journalctl -u dashboard-mme --no-pager -n 50
```

### Celery

```bash
# Worker
celery -A tasks worker --loglevel=info --concurrency=4

# Beat (scheduler)
celery -A tasks beat --loglevel=info

# Monitoreo
flower -A tasks --port=5555
```

---

## 🐛 Debugging

### Python Debugger

```python
import pdb; pdb.set_trace()  # Breakpoint

# Comandos:
# n - next line
# s - step into
# c - continue
# p variable - print variable
# q - quit
```

### Logs en Tiempo Real

```bash
# Todos los logs
tail -f logs/*.log

# Específico
tail -f logs/gunicorn_error.log
tail -f logs/celery/worker-1.log
```

---

## 📦 Dependencias

### requirements.txt

```bash
# Agregar nueva dependencia
echo "nueva-lib==1.2.3" >> requirements.txt
pip install nueva-lib==1.2.3

# Actualizar todas
pip install -r requirements.txt --upgrade
```

### Dependencias Críticas (NO actualizar sin pruebas)

- `fastapi`: Framework API
- `dash`: Dashboard legacy
- `sqlalchemy`: ORM
- `psycopg2-binary`: PostgreSQL driver
- `celery`: Tareas async

---

## 🔒 Seguridad

### Variables de Entorno Sensibles

```python
# ✅ CORRECTO - Usar desde .env
import os
password = os.getenv("PGPASSWORD")

# ❌ INCORRECTO - Nunca hardcodear
password = "admin123"  # ¡PELIGRO!
```

### SQL Injection Prevention

```python
# ✅ CORRECTO - Parametrizado
result = await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)

# ❌ INCORRECTO - Concatenación
result = await conn.fetch(f"SELECT * FROM users WHERE id = {user_id}")  # SQL Injection!
```

---

## ⚠️ Deuda Técnica Conocida

### Servicios Deprecated (serán eliminados en V5)

- `geo_service.py` - Sin implementación
- `orchestrator_service.py` - Vacío
- `predictions_service.py` - Consolidado en extended

### Mejoras Pendientes

- 72 archivos con `print()` → migrar a logger
- 171 archivos con `except Exception` genérico → específicos
- 0 tests de integración → implementar
- 0 tests e2e → implementar

---

## 📚 Recursos

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/)
- [Celery Docs](https://docs.celeryproject.org/)
- [Dash Docs](https://dash.plotly.com/)

---

## 📞 Contacto

- **Desarrollador Principal:** [Tu nombre/email]
- **Infraestructura:** Equipo TI MinMinas

---

*Documento actualizado: 31 de marzo de 2026*
