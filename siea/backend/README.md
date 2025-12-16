# Backend - SIEA

API Backend construida con FastAPI para el Sistema Integral de Inteligencia Energética y Asistencia Ministerial.

## Estructura

```
backend/
├── api/                    # Aplicación FastAPI
│   ├── main.py            # Entry point
│   ├── routers/           # Endpoints organizados
│   │   ├── health.py      # Health checks
│   │   ├── reports.py     # Generación de reportes
│   │   ├── predictions.py # Modelos predictivos
│   │   └── simulations.py # Simuladores
│   └── models/            # Pydantic models
├── etl/                   # Pipelines ETL
│   ├── extractors/        # Conectores a fuentes
│   ├── transformers/      # Limpieza y normalización
│   └── loaders/           # Carga a DB
├── db/                    # Base de datos
│   ├── connection.py      # Pool de conexiones
│   ├── models.py          # SQLAlchemy ORM
│   └── migrations/        # Alembic migrations
├── config.py              # Configuración
├── requirements.txt       # Dependencias
└── tests/                 # Tests unitarios
```

## Instalación

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

## Configuración

Crear archivo `.env`:

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/siea
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
```

## Ejecutar

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
pytest tests/ -v --cov=api
```

## Endpoints

- `GET /health` - Health check
- `GET /api/v1/reports/daily` - Resumen diario
- `POST /api/v1/predict/demanda` - Forecast demanda
- `POST /api/v1/simulate/market` - Simulación mercado
