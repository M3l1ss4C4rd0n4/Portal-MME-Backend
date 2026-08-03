# API RESTful - Portal Energético MME

API RESTful construida con FastAPI para proporcionar acceso programático a los datos del sector energético colombiano.

## 📋 Características

- ✅ **Métricas energéticas**: Generación, demanda, disponibilidad, precios
- ✅ **Predicciones ML**: Prophet, ARIMA, Ensemble
- ✅ **Seguridad**: API Key authentication
- ✅ **Rate limiting**: Control de tasa de requests
- ✅ **CORS**: Configuración flexible de orígenes
- ✅ **Documentación**: Swagger UI y ReDoc automáticos
- ✅ **Validación**: Esquemas Pydantic robustos
- ✅ **Formato estándar**: Sigue convenciones en `docs/api_data_conventions.md`

## 🚀 Inicio Rápido

### 1. Instalar dependencias

```bash
pip install fastapi uvicorn slowapi pydantic-settings
```

### 2. Configurar variables de entorno

Editar `.env`:

```env
# API REST
API_ENABLED=true
API_PORT=8000
API_KEY_ENABLED=true
API_KEY=tu-api-key-secreta-aqui
API_CORS_ORIGINS=*
API_RATE_LIMIT=100/minute
```

### 3. Ejecutar servidor de desarrollo

```bash
# Opción 1: Directamente con Python
python api/main.py

# Opción 2: Con Uvicorn
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Opción 3: Con Gunicorn (producción)
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 4. Acceder a la documentación

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

## 📡 Endpoints Disponibles

### Root

```http
GET /
GET /health
```

### Métricas (v1)

```http
GET /api/v1/metrics/{metric_id}?entity=Sistema&start_date=2026-01-01&end_date=2026-02-03
GET /api/v1/metrics/
```

**Ejemplo:**
```bash
curl -H "X-API-Key: tu-api-key" \
  "http://localhost:8000/api/v1/metrics/Gene?entity=Sistema&start_date=2026-01-01"
```

**Respuesta:**
```json
{
  "metric_id": "Gene",
  "entity": "Sistema",
  "unit": "GWh",
  "count": 34,
  "data": [
    {
      "date": "2026-01-01",
      "value": 234.56,
      "metadata": {
        "source": "hybrid",
        "quality": "validated"
      }
    }
  ]
}
```

### Predicciones (v1)

```http
GET /api/v1/predictions/{metric_id}?entity=Sistema&horizon_days=30&model_type=prophet
POST /api/v1/predictions/{metric_id}/train?model_type=prophet&save_model=true
```

**Ejemplo:**
```bash
curl -H "X-API-Key: tu-api-key" \
  "http://localhost:8000/api/v1/predictions/Gene?horizon_days=30&model_type=prophet"
```

**Respuesta:**
```json
{
  "metric_id": "Gene",
  "entity": "Sistema",
  "unit": "GWh",
  "model": "prophet",
  "horizon_days": 30,
  "generated_at": "2026-02-03T14:30:00Z",
  "data": [
    {
      "date": "2026-03-01",
      "value": 245.78,
      "lower": 230.12,
      "upper": 261.44,
      "confidence": 0.95
    }
  ]
}
```

## 🔐 Autenticación

Todas las peticiones requieren el header `X-API-Key`:

```bash
curl -H "X-API-Key: tu-api-key-secreta" http://localhost:8000/api/v1/metrics/Gene
```

Para deshabilitar autenticación en desarrollo, configurar en `.env`:

```env
API_KEY_ENABLED=false
```

## ⚡ Rate Limiting

Por defecto, la API aplica los siguientes límites:

- **Endpoints generales**: 100 requests/minuto
- **Listados**: 60 requests/minuto
- **Predicciones**: 20 requests/minuto
- **Entrenamiento de modelos**: 5 requests/hora

Configurar en `.env`:

```env
API_RATE_LIMIT=100/minute
```

Headers de respuesta:
- `X-RateLimit-Limit`: Límite total
- `X-RateLimit-Remaining`: Requests restantes
- `X-RateLimit-Reset`: Timestamp de reset

## 📐 Arquitectura

```
api/
├── __init__.py              # Módulo API
├── main.py                  # Aplicación FastAPI principal
├── dependencies.py          # Dependencias compartidas
└── v1/
    ├── __init__.py          # Router v1
    ├── routes/
    │   ├── metrics.py       # Endpoints de métricas
    │   └── predictions.py   # Endpoints de predicciones
    └── schemas/
        ├── common.py        # Esquemas comunes
        ├── metrics.py       # Esquemas de métricas
        └── predictions.py   # Esquemas de predicciones
```

### Flujo de Datos

1. **Request** → FastAPI recibe petición
2. **Authentication** → Valida API Key (si está habilitado)
3. **Rate Limiting** → Verifica límites de tasa
4. **Validation** → Pydantic valida parámetros
5. **Service Layer** → Llama a servicios de dominio
6. **Repository** → Accede a base de datos
7. **Response** → Serializa respuesta según esquemas

## 🧪 Testing

### Probar health check

```bash
curl http://localhost:8000/health
```

### Probar autenticación

```bash
# Sin API Key (debe fallar)
curl http://localhost:8000/api/v1/metrics/Gene

# Con API Key válida
curl -H "X-API-Key: tu-api-key" http://localhost:8000/api/v1/metrics/Gene
```

### Probar rate limiting

```bash
# Ejecutar múltiples veces rápidamente
for i in {1..150}; do
  curl -H "X-API-Key: tu-api-key" http://localhost:8000/api/v1/metrics/Gene
done
```

## 🐳 Docker (Opcional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t portal-energetico-api .
docker run -p 8000:8000 --env-file .env portal-energetico-api
```

## 📊 Métricas Disponibles

| Código | Descripción | Unidad |
|--------|-------------|--------|
| `Gene` | Generación de energía | GWh |
| `DemaReal` | Demanda real de energía | GWh |
| `Dispo` | Disponibilidad efectiva neta | MW |
| `PrecBols` | Precio de bolsa | $/kWh |
| `Aportes` | Aportes hídricos | m³/s |

## 🤖 Modelos ML

| Modelo | Descripción | Uso recomendado |
|--------|-------------|-----------------|
| `prophet` | Facebook Prophet | Series con estacionalidad fuerte |
| `arima` | ARIMA auto-tuning | Series estacionarias |
| `ensemble` | Combinación de modelos | Mayor precisión |

## 🔧 Configuración Avanzada

### CORS personalizado

```env
API_CORS_ORIGINS=https://dashboard.mme.gov.co,https://admin.mme.gov.co
```

### Múltiples API Keys

```env
API_KEY=key-principal
API_KEYS_WHITELIST=key-secundaria,key-desarrollo,key-testing
```

### Deshabilitar documentación en producción

```env
DASH_ENV=production  # Deshabilita /api/docs automáticamente
```

## 📝 Convenciones de Datos

La API sigue las convenciones definidas en [docs/api_data_conventions.md](../docs/api_data_conventions.md):

- ✅ Formato ISO 8601 para fechas (`YYYY-MM-DD`)
- ✅ Timestamps en UTC con zona horaria (`2026-02-03T14:30:00Z`)
- ✅ Valores numéricos como `float`
- ✅ Metadatos opcionales en campo `metadata`
- ✅ Intervalos de confianza para predicciones

## 🚨 Manejo de Errores

La API retorna códigos HTTP estándar:

- `200 OK`: Petición exitosa
- `400 Bad Request`: Parámetros inválidos
- `401 Unauthorized`: API Key faltante
- `403 Forbidden`: API Key inválida
- `404 Not Found`: Recurso no encontrado
- `429 Too Many Requests`: Rate limit excedido
- `500 Internal Server Error`: Error del servidor

Formato de respuestas de error:

```json
{
  "error": "Not Found",
  "message": "No se encontraron datos para la métrica 'Gene'",
  "details": null
}
```

## 🎯 Roadmap

- [ ] Endpoints de análisis con IA
- [ ] Endpoints de hidrología
- [ ] WebSockets para datos en tiempo real
- [ ] GraphQL API
- [ ] Autenticación OAuth2
- [ ] Versionado semántico de API

## 📞 Soporte

Para reportar problemas o sugerencias, revisar la documentación del proyecto principal.

---

**Autor:** Arquitectura Dashboard MME  
**Fecha:** 6 de julio de 2026 *(actualizado)*  
**Versión:** 1.1.0
