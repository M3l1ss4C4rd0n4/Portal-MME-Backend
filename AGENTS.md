# Guía para Agentes - Server Backend

## Estructura del Proyecto

Arquitectura Limpia (Clean Architecture):

```
server/
├── api/                    # API REST (FastAPI)
│   ├── main.py            # Entry point
│   └── v1/routes/         # Endpoints
├── core/                   # Framework y configuración
│   ├── config.py          # Pydantic Settings
│   ├── container.py       # Dependency Injection
│   ├── app_factory.py     # Factory Dash
│   ├── app_factory_fix.py # FIX: Callbacks Gunicorn
│   ├── security/          # Encriptación, vault
│   └── database/          # Migration helpers
├── domain/                 # Lógica de negocio
│   ├── services/          # 25+ servicios
│   ├── models/            # Modelos de dominio
│   └── interfaces/        # Repository Pattern
├── infrastructure/         # Adaptadores
│   ├── database/          # PostgreSQL
│   ├── external/          # API XM
│   └── cache/             # Redis
├── interface/             # Dashboard Dash
├── etl/                   # Pipelines de datos
└── tasks/                 # Celery tasks
```

## Convenciones Críticas

### 1. Manejo de Errores

```python
# ❌ NUNCA usar except Exception: sin especificar
except Exception as e:
    logger.exception(f"Error: {e}")
    return None

# ✅ CAPTURAR EXCEPCIONES ESPECÍFICAS PRIMERO
except requests.Timeout:
    logger.error("Timeout connecting to XM API")
    return None
except requests.ConnectionError as e:
    logger.error("Connection error: %s", e)
    return None
except Exception as e:  # Fallback
    logger.exception("Unexpected error: %s", e)
    return None
```

### 2. Logging (NO print)

```python
# ❌ INCORRECTO
print(f"DEBUG: Variable = {value}")

# ✅ CORRECTO
import logging
logger = logging.getLogger(__name__)
logger.debug("Variable = %s", value)
```

### 3. Credenciales

```python
# ❌ NUNCA hardcodear
API_KEY = "MME2026_SECURE_KEY"

# ✅ SIEMPRE usar variables de entorno
import os
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY no configurada")
```

### 4. Git

- Rama `master` para backend
- Commits atómicos con mensajes descriptivos
- Probar antes de push: `python -m py_compile archivo.py`

## Comandos Útiles

```bash
# Tests
pytest tests/ -v

# Verificar sintaxis
find . -name "*.py" -not -path "./venv/*" -exec python -m py_compile {} \;

# ETL manual
python etl/etl_xm_to_postgres.py --fecha-inicio 2024-01-01

# Servicios
sudo systemctl status dashboard-mme api-mme
curl http://localhost:8000/api/health

# Logs
tail -f logs/gunicorn_error.log
tail -f logs/api-error.log
```

## Archivos Críticos

- `api/dependencies.py` - DI + API Key auth (¡verificar indentación!)
- `core/config.py` - Configuración centralizada
- `domain/services/*_service.py` - Lógica de negocio
- `etl/etl_xm_to_postgres.py` - Pipeline ETL principal

## Hotfix Reciente (2026-03-30)

### Problemas Corregidos

1. **IndentationError línea 187** - `api/dependencies.py`
2. **Credenciales expuestas** - 3 scripts afectados
3. **Módulos untracked** - `core/security/`, `core/database/` integrados

### Nuevos Módulos

| Módulo | Propósito |
|--------|-----------|
| `core/security/vault.py` | Encriptación Fernet AES-128 |
| `core/security/sql_validator.py` | Validación queries SQL |
| `core/database/migration_helper.py` | Utilidades migración |
| `core/app_factory_fix.py` | Fix callbacks Gunicorn |

## Dependencias Principales

```
fastapi==0.109.2
pydantic==2.12.5
psycopg2-binary==2.9.11
redis==5.0.8
celery==5.6.2
prophet==1.1.5
cryptography>=41.0.7  # Nuevo: requerido por vault.py
```

## Frontend Relacionado

- Repo: https://github.com/M3l1ss4C4rd0n4/Portal-de-Direccion-MME.git
- Rama: `main` para frontend (`portal-direccion-mme/`)
- Rama: `master` para backend (`server/`)

## Notas Importantes

1. **Excepciones:** Siempre capturar específicas primero
2. **Logging:** Usar `logger.*` NO `print()`
3. **Git:** Un commit por cambio lógico
4. **Tests:** Ejecutar antes de push
5. **API:** Verificar que `api/dependencies.py` no tenga errores de indentación
6. **Container:** Usar funciones `get_*_service`, NO `container.resolve()`
