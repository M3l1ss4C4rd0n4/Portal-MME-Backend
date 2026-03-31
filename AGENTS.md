# Guía para Agentes - Server Backend

## Estructura del Proyecto

Arquitectura Limpia (Clean Architecture) con capas bien definidas:

```
server/
├── api/                    # API REST (FastAPI)
│   ├── main.py            # Entry point
│   └── v1/routes/         # Endpoints
├── core/                   # Framework y configuración
│   ├── config.py          # Pydantic Settings
│   ├── container.py       # Dependency Injection
│   └── app_factory.py     # Factory Dash
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

### Manejo de Errores
❌ **NUNCA** usar `except Exception as e:` sin especificar primero:

```python
# ❌ INCORRECTO
except Exception as e:
    logger.exception(f"Error: {e}")
    return None

# ✅ CORRECTO
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

### Logging
❌ **NUNCA** usar `print()`:

```python
# ❌ INCORRECTO
print(f"DEBUG: Variable = {value}")

# ✅ CORRECTO
import logging
logger = logging.getLogger(__name__)
logger.debug("Variable = %s", value)
```

### Git
- **Rama:** `master` para backend
- **Commits:** Atómicos, mensajes descriptivos
  ```
  feat(api): agregar endpoint de predicciones
  fix(etl): corregir timeout en conexión XM
  refactor(service): consolidar predictions_service
  ```
- **Probar antes de push:**
  ```bash
  python -m py_compile archivo.py
  pytest tests/ -x
  ```

## Dependencias Principales

```
FastAPI==0.128.2
Pydantic==2.12.5
psycopg2-binary==2.9.11
Redis==5.0.8
Celery==5.6.2
Prophet==1.1.5
Dash==2.17.1
Plotly==5.17.0
```

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
sudo systemctl restart dashboard-mme api-mme

# Logs
tail -f logs/gunicorn_error.log
tail -f logs/api-error.log

# Verificar puertos
ss -tlnp | grep -E '8000|8050|8001|5000'
```

## Archivos Críticos (NO modificar sin revisión)

- `core/config.py` - Configuración centralizada
- `domain/services/*_service.py` - Lógica de negocio
- `api/v1/routes/*.py` - Endpoints públicos
- `etl/etl_xm_to_postgres.py` - Pipeline ETL principal

## Deuda Técnica Conocida

- [ ] 930+ bloques `except Exception` por migrar a excepciones específicas
- [ ] 2250+ prints por migrar a logging estructurado
- [ ] `predictions_service.py` vs `predictions_service_extended.py` - pendiente consolidar
- [ ] `core/config.py` (767 líneas) - considerar dividir en módulos

## Seguridad

- Variables de entorno en `.env` (no commitear)
- API Key en header `X-API-Key`
- Rate limiting por IP (extensible a por API key)
- Secrets cifrados con Fernet AES-128

## Frontend Relacionado

- Repositorio: https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git
- Rama: `main` para frontend (`portal-direccion-mme/`)
- Rama: `master` para backend (`server/`)

## Notas Importantes

1. **Excepciones:** Siempre capturar específicas primero
2. **Logging:** Usar `logger.*` NO `print()`
3. **Git:** Un commit por cambio lógico
4. **Tests:** Ejecutar antes de push
5. **ETL:** Verificar conexión XM antes de ejecutar manual

## Documentación

- [README.md](./README.md) - Guía completa
- [docs/](./docs/) - Documentación técnica extensa
- [docs/GUIA_ONBOARDING.md](./docs/GUIA_ONBOARDING.md) - Onboarding nuevos devs
