# API RESTful - Portal Energético MME

API RESTful construida con FastAPI para proporcionar acceso programático a los datos del sector energético colombiano, comunidades energéticas, FENOGE, Colombia Solar, contratos OR, supervisión, subsidios, presupuesto, hidrocarburos, ontología (geografía/empresa/proyecto/métrica/recurso), RAG documental y el Asistente IA.

> Corregido 2026-09-01: este README documentaba solo 2 de los ~30 archivos de rutas reales (`metrics.py`/`predictions.py`). Ver la lista completa abajo, generada a partir del código real en `api/v1/routes/`.

## 📋 Características

- ✅ **110 endpoints reales** distribuidos en ~30 archivos de rutas (`api/v1/routes/`)
- ✅ **Métricas energéticas**: Generación, demanda, disponibilidad, precios, pérdidas técnicas y no técnicas
- ✅ **Predicciones ML**: Prophet + SARIMAX (ensemble), con validación rigurosa (ver `docs/tecnicos/PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md`)
- ✅ **Ontología de datos**: geografía (DANE), empresa, proyecto, métrica, recurso — cruces entre 9+ esquemas antes aislados
- ✅ **RAG documental**: búsqueda semántica sobre informes de XM, CREG, UPME, MME, SharePoint del ministerio
- ✅ **Asistente IA**: chat con tool-calling (`/v1/chatbot/asistente`), streaming, voz en tiempo real (`/v1/voz`)
- ✅ **Seguridad**: API Key authentication (`X-API-Key`)
- ✅ **Rate limiting**: `slowapi`, límites por endpoint
- ✅ **CORS**: configuración por variable de entorno
- ✅ **Documentación**: Swagger UI y ReDoc automáticos
- ✅ **Validación**: esquemas Pydantic

## 🚀 Inicio Rápido

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Editar `.env` (ver `server/.env.example` si existe, o las claves reales usadas en producción):

```env
API_ENABLED=true
API_PORT=8000
API_KEY_ENABLED=true
API_KEY=tu-api-key-secreta-aqui
API_CORS_ORIGINS=*
API_RATE_LIMIT=100/minute
```

### 3. Ejecutar servidor de desarrollo

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**En producción** (este servidor) NO se usa Gunicorn ni Docker — corre `uvicorn` plano detrás de `systemd` (`portal-api.service`), con `nginx` como proxy inverso hacia el frontend Next.js. Ver `RUNBOOK_PRODUCCION.md` para el detalle operativo real.

### 4. Acceder a la documentación

- **Swagger UI**: `/api/docs` (deshabilitado automáticamente si `DASH_ENV=production`)
- **ReDoc**: `/api/redoc`
- **OpenAPI JSON**: `/api/openapi.json`

## 📡 Dominios de endpoints reales (`api/v1/routes/`)

La API cubre bastante más que métricas/predicciones. Conteo real de endpoints por archivo (verificado por grep sobre el código, no estimado):

| Archivo | Endpoints | Dominio |
|---|---|---|
| `ontologia.py` | 17 | Geografía DANE, empresa, proyecto, métrica, recurso, grafo, salud de datos |
| `reports.py` | 12 | Informes ejecutivos, informes diarios XM, boletines, descargas |
| `observability.py` | 9 | Health checks, métricas de sistema, logs |
| `predictions.py` | 7 | Predicciones Prophet+SARIMAX (embalses, generación, precio, demanda) |
| `simulation.py` | 5 | Simulación de escenarios CREG |
| `energia_app.py` | 5 | App móvil EnergIA (incluye `/audio/consulta`, voz) |
| `cu.py` | 5 | Costo Unitario (mayorista LAC + minorista Res. CREG 119/2007) |
| `generation.py` | 4 | Generación eléctrica por fuente |
| `chatbot.py` | 4 | Asistente IA (`/v1/chatbot/asistente`), orquestador, feedback |
| `transmission.py` | 3 | Transmisión |
| `subsidios.py` | 3 | Déficit y pagos de subsidios |
| `losses.py` | 3 | Pérdidas técnicas y no técnicas (PNT) |
| `hydrology.py` | 3 | Hidrología, embalses |
| `contratos_or.py` | 3 | Contratos de Obligación de Resultado (electrificación rural) |
| `whatsapp_alerts.py`, `system.py`, `supervision_portal.py`, `sector_snapshot.py`, `metrics.py`, `internal.py`, `informes_tableros.py`, `fenoge.py`, `distribution.py`, `commercial.py` | 2 c/u | Alertas WhatsApp, sistema, supervisión de contratos, snapshot del sector, métricas genéricas, uso interno, tableros de informes, FENOGE, distribución, comercial |
| `voz.py`, `sector_despacho.py`, `riesgo.py`, `restrictions.py`, `presupuesto.py`, `energia_dashboard.py`, `comunidades.py` | 1 c/u | Voz en tiempo real (Gemini Live), despacho, riesgo de atraso de contratos, restricciones, presupuesto, dashboard, comunidades energéticas |

**Ejemplo — métrica cruda:**
```bash
curl -H "X-API-Key: tu-api-key" \
  "http://localhost:8000/api/v1/metrics/Gene?entity=Sistema&start_date=2026-01-01"
```

**Ejemplo — predicción:**
```bash
curl -H "X-API-Key: tu-api-key" \
  "http://localhost:8000/api/v1/predictions/dashboard"
```

**Ejemplo — Asistente IA (streaming SSE):**
```bash
curl -N -H "X-API-Key: tu-api-key" -H "Content-Type: application/json" \
  -d '{"mensaje": "¿Cómo está la generación eléctrica hoy?", "historial": []}' \
  http://localhost:8000/v1/chatbot/asistente
```

**Ejemplo — búsqueda RAG (ontología):**
```bash
curl -H "X-API-Key: tu-api-key" \
  "http://localhost:8000/v1/ontologia/geografia/27/resumen"
```

## 🔐 Autenticación

Todas las peticiones requieren el header `X-API-Key`:

```bash
curl -H "X-API-Key: tu-api-key-secreta" http://localhost:8000/api/v1/metrics/Gene
```

Deshabilitar solo en desarrollo local:

```env
API_KEY_ENABLED=false
```

## ⚡ Rate Limiting

Límites reales, definidos por endpoint vía `slowapi` (varían según el costo real de cada uno — ej. el Asistente IA, que puede hacer varias llamadas a Gemini/Groq por turno, tiene un límite más bajo que un endpoint de lectura simple). No existe un límite único global — revisar el decorador `@limiter.limit(...)` de cada ruta en `api/v1/routes/` para el valor exacto vigente.

Configurar el límite por defecto en `.env`:

```env
API_RATE_LIMIT=100/minute
```

Headers de respuesta:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## 📐 Arquitectura real

```
api/
├── main.py                  # Aplicación FastAPI principal, montaje de routers
├── dependencies.py          # Dependencias compartidas (get_api_key, etc.)
└── v1/
    ├── routes/               # ~30 archivos de rutas — ver tabla de dominios arriba
    └── schemas/              # Esquemas Pydantic (request/response)
```

La lógica de negocio real NO vive en `api/` — vive en `domain/services/*.py` (~42 servicios) y se accede vía inyección de dependencias desde `core/container.py`. Las rutas son delgadas: reciben la petición, llaman al servicio correspondiente, serializan la respuesta.

### Flujo de datos

1. **Request** → FastAPI recibe la petición
2. **Authentication** → `Depends(get_api_key)` valida `X-API-Key`
3. **Rate Limiting** → `slowapi` verifica el límite del endpoint
4. **Validation** → Pydantic valida los parámetros
5. **Service Layer** → `core/container.py` resuelve el servicio de dominio (lazy singleton)
6. **Repository** → acceso a Postgres vía `psycopg2.ThreadedConnectionPool` (`infrastructure/database/connection.py::_get_pool()`) — **no** `asyncpg`
7. **Response** → serialización según el esquema Pydantic de respuesta

## 🧪 Testing

```bash
# Health check real
curl http://localhost:8000/health

# Sin API Key (debe fallar si API_KEY_ENABLED=true)
curl http://localhost:8000/api/v1/metrics/Gene

# Con API Key válida
curl -H "X-API-Key: tu-api-key" http://localhost:8000/api/v1/metrics/Gene
```

Suite de tests del backend: 373 tests pasando (verificado 2026-09), corre con `pytest` desde `server/`.

## 📝 Convenciones de Datos

La API sigue las convenciones definidas en `docs/api_data_conventions.md`:

- ✅ Formato ISO 8601 para fechas (`YYYY-MM-DD`)
- ✅ Timestamps en UTC con zona horaria
- ✅ Valores numéricos como `float`
- ✅ Metadatos opcionales en campo `metadata`
- ✅ Intervalos de confianza para predicciones (con calibración por horizonte, ver `PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md`)

## 🚨 Manejo de Errores

- `200 OK`
- `400 Bad Request` — parámetros inválidos
- `401 Unauthorized` — API Key faltante
- `403 Forbidden` — API Key inválida
- `404 Not Found`
- `429 Too Many Requests` — rate limit excedido
- `500 Internal Server Error`

## 📞 Referencias

- Manual técnico completo, glosario, guía de código: `docs/` (ver `README.md` del servidor para el índice completo)
- Auditoría de documentación y deuda documental: `docs/AUDITORIA_DOCUMENTACION_2026-09.md`
- Operación en producción (systemd, Celery Beat, logs reales): `RUNBOOK_PRODUCCION.md`

---

**Última revisión de este documento:** 2026-09-01 — reescrito contra el código real (antes documentaba solo 2 de ~30 archivos de rutas).
