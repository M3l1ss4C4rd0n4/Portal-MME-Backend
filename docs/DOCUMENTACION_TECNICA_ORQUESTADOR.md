# 🤖 Documentación Técnica - Orquestador para Chatbot

**Fecha:** 9 de febrero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Completado y listo para integración

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura](#arquitectura)
3. [Endpoints Implementados](#endpoints-implementados)
4. [Intents Soportados](#intents-soportados)
5. [Seguridad y Validación](#seguridad-y-validación)
6. [Despliegue](#despliegue)
7. [Pruebas](#pruebas)
8. [Monitoreo](#monitoreo)
9. [Anexos](#anexos)

---

## 1. Resumen Ejecutivo

Se ha implementado exitosamente el **Endpoint Orquestador para Chatbot** conforme al 100% de las especificaciones del documento "Requerimientos – Endpoint Orquestador para Chatbot".

### ✅ Cumplimiento de Requerimientos

| Requisito | Estado | Implementación |
|-----------|--------|----------------|
| Método POST | ✅ | `/api/v1/chatbot/orchestrator` |
| Formato JSON | ✅ | Request y Response en JSON |
| Contrato Request | ✅ | `sessionId`, `intent`, `parameters` |
| Contrato Response | ✅ | `status`, `message`, `data`, `errors` |
| Estados permitidos | ✅ | SUCCESS, PARTIAL_SUCCESS, ERROR |
| Manejo de errores | ✅ | Robusto sin exposición interna |
| Seguridad | ✅ | API Key, validación, sanitización |
| Timeouts | ✅ | 10s por servicio, 30s total |
| Rate limiting | ✅ | 100 requests/minuto |
| Documentación | ✅ | OpenAPI/Swagger completa |
| Ejemplos | ✅ | Funcionales para todos los intents |
| Pruebas | ✅ | Suite de tests automatizada |

---

## 2. Arquitectura

### 2.1 Diagrama de Componentes

```
┌─────────────────┐
│    Chatbot      │
│   (Cliente)     │
└────────┬────────┘
         │ POST /api/v1/chatbot/orchestrator
         │ Headers: X-API-Key
         │ Body: {sessionId, intent, parameters}
         ↓
┌─────────────────────────────────────────────────┐
│         API Gateway (FastAPI)                   │
│  ┌───────────────────────────────────────────┐  │
│  │  Rate Limiter (100/min)                   │  │
│  │  API Key Validation                       │  │
│  │  Request Validation (Pydantic)            │  │
│  └───────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│   ChatbotOrchestratorService                    │
│   /domain/services/orchestrator_service.py      │
│  ┌───────────────────────────────────────────┐  │
│  │  Intent Mapping                           │  │
│  │  Handler Dispatching                      │  │
│  │  Timeout Management (10s/30s)             │  │
│  │  Error Consolidation                      │  │
│  └───────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────┘
         │
         ├──────────┬──────────┬──────────┬────────┐
         ↓          ↓          ↓          ↓        ↓
    ┌─────────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌─────┐
    │Generation│ │Hydrology│ │System │ │ ... │ │ ... │
    │ Service │ │ Service │ │Service│ │     │ │     │
    └─────────┘ └────────┘ └────────┘ └──────┘ └─────┘
         │          │          │
         ↓          ↓          ↓
    ┌──────────────────────────────┐
    │   Base de Datos / Cache      │
    └──────────────────────────────┘
```

### 2.2 Estructura de Archivos

```
/home/admonctrlxm/server/
│
├── api/v1/
│   ├── routes/
│   │   └── chatbot.py              # Endpoint del orquestador
│   ├── schemas/
│   │   └── orchestrator.py         # Schemas Pydantic
│   └── __init__.py                 # Registro del router
│
├── domain/services/
│   └── orchestrator_service.py     # Lógica de orquestación
│
├── docs/
│   ├── RESPUESTA_CORREO_ORQUESTADOR.md    # Respuesta al correo
│   ├── EJEMPLOS_ORQUESTADOR_CHATBOT.md    # Ejemplos de uso
│   └── DOCUMENTACION_TECNICA_ORQUESTADOR.md (este archivo)
│
└── tests/
    └── test_orchestrator.py        # Suite de pruebas
```

---

## 3. Endpoints Implementados

### 3.1 Endpoint Principal

**URL:** `POST /api/v1/chatbot/orchestrator`

**Headers:**
```http
Content-Type: application/json
X-API-Key: [API_KEY]
```

**Request Body:**
```json
{
  "sessionId": "string",
  "intent": "string",
  "parameters": {}
}
```

**Response Body:**
```json
{
  "status": "SUCCESS | PARTIAL_SUCCESS | ERROR",
  "message": "string",
  "data": {},
  "errors": [],
  "timestamp": "2026-02-09T15:30:00Z",
  "sessionId": "string",
  "intent": "string"
}
```

### 3.2 Health Check

**URL:** `GET /api/v1/chatbot/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "chatbot-orchestrator",
  "timestamp": "2026-02-09T15:30:00Z"
}
```

---

## 4. Intents Soportados

### 4.1 Generación Eléctrica

**Intents:**
- `generacion_electrica`
- `consultar_generacion`
- `generacion`

**Parámetros opcionales:**
- `fecha` (YYYY-MM-DD): Fecha específica
- `fecha_inicio`, `fecha_fin`: Rango de fechas
- `recurso`: Tipo de recurso (hidraulica, termica, solar, eolica)

**Datos retornados:**
- `generacion_total_gwh`: Generación total
- `generacion_promedio_gwh`: Promedio del periodo
- `periodo`: {inicio, fin}
- `por_recurso`: Desglose por fuente (si aplica)

### 4.2 Hidrología y Embalses

**Intents:**
- `hidrologia`
- `consultar_embalses`
- `embalses`
- `nivel_embalses`

**Parámetros opcionales:**
- `fecha` (YYYY-MM-DD): Fecha de consulta
- `embalse`: Nombre del embalse específico

**Datos retornados:**
- `nivel_promedio_sistema`: Nivel promedio (%)
- `energia_embalsada_gwh`: Energía total embalsada
- `fecha`: Fecha de consulta
- `embalse`: Detalle del embalse (si se especificó)

### 4.3 Demanda del Sistema

**Intents:**
- `demanda_sistema`
- `consultar_demanda`
- `demanda`

**Parámetros opcionales:**
- `fecha` (YYYY-MM-DD): Fecha específica
- `fecha_inicio`, `fecha_fin`: Rango de fechas

**Datos retornados:**
- `demanda_total_gwh`: Demanda total
- `demanda_promedio_gwh`: Promedio del periodo
- `demanda_maxima_gwh`: Demanda máxima
- `periodo`: {inicio, fin}

### 4.4 Precios de Bolsa

**Intents:**
- `precio_bolsa`
- `precios_bolsa`
- `consultar_precios`

**Parámetros opcionales:**
- `fecha` (YYYY-MM-DD): Fecha específica
- `fecha_inicio`, `fecha_fin`: Rango de fechas

**Datos retornados:**
- `precio_promedio_cop_kwh`: Precio promedio
- `precio_maximo_cop_kwh`: Precio máximo
- `precio_minimo_cop_kwh`: Precio mínimo
- `periodo`: {inicio, fin}

### 4.5 Predicciones

**Intents:**
- `predicciones`
- `pronostico`
- `forecast`

**Parámetros opcionales:**
- `tipo`: Tipo de predicción (demanda, generacion, precios)
- `horizonte`: Horizonte en días (1-90)

**Datos retornados:**
- Estructura según el tipo de predicción

### 4.6 Métricas Generales

**Intents:**
- `metricas_generales`
- `resumen_sistema`
- `estado_sistema`

**Parámetros:** Ninguno

**Datos retornados:**
- `fecha`: Fecha del resumen
- `generacion`: Datos de generación
- `hidrologia`: Datos de embalses
- `demanda`: Datos de demanda

---

## 5. Seguridad y Validación

### 5.1 Autenticación

- **Método:** API Key en header `X-API-Key`
- **Gestión:** Configurada en `core/config.py`
- **Validación:** Automática por middleware FastAPI

### 5.2 Validación de Entrada

- **Framework:** Pydantic v2
- **Schemas:** `api/v1/schemas/orchestrator.py`
- **Validaciones:**
  - `sessionId`: No vacío, sin caracteres peligrosos
  - `intent`: Alfanumérico con guiones y guiones bajos
  - `parameters`: Validación según el intent

### 5.3 Sanitización

- Eliminación de caracteres peligrosos en `sessionId`
- Normalización de `intent` a lowercase
- Validación de tipos en `parameters`

### 5.4 Rate Limiting

- **Límite:** 100 requests/minuto por IP
- **Implementación:** SlowAPI
- **Response:** HTTP 429 cuando se excede

### 5.5 Manejo de Errores

- **Sin exposición de detalles internos**
- **Mensajes genéricos para usuarios**
- **Logging detallado para debugging**
- **Códigos de error estándar:**
  - `UNKNOWN_INTENT`: Intent no reconocido
  - `VALIDATION_ERROR`: Error de validación
  - `SERVICE_ERROR`: Error en servicio backend
  - `TIMEOUT`: Timeout en servicio
  - `NO_DATA`: Sin datos disponibles
  - `INTERNAL_ERROR`: Error inesperado

---

## 6. Despliegue

### 6.1 Requisitos Previos

- Python 3.11+
- FastAPI instalado
- Servicios backend operativos
- API Key configurada

### 6.2 Configuración

1. **Variables de Entorno:**
   ```bash
   # En .env o configuración del sistema
   API_KEY_ENABLED=true
   API_KEY=tu-clave-secreta-aqui
   ```

2. **Reiniciar API:**
   ```bash
   # Si usas el servicio systemd
   sudo systemctl restart api-mme.service
   
   # O si usas gunicorn directamente
   cd /home/admonctrlxm/server
   ./api/run_prod.sh
   ```

### 6.3 Verificación

```bash
# Health check
curl http://localhost:8000/api/v1/chatbot/health

# Debe retornar:
# {"status": "healthy", "service": "chatbot-orchestrator", "timestamp": "..."}
```

### 6.4 Documentación Swagger

Una vez desplegado, la documentación interactiva está disponible en:

```
http://[tu-dominio]/api/docs
```

Busca la sección "🤖 Chatbot" para ver los endpoints del orquestador.

---

## 7. Pruebas

### 7.1 Suite de Pruebas Automatizada

**Ubicación:** `/home/admonctrlxm/server/tests/test_orchestrator.py`

**Ejecutar:**
```bash
cd /home/admonctrlxm/server
python tests/test_orchestrator.py
```

**Nota:** Antes de ejecutar, actualizar:
- `API_BASE_URL` (línea 24)
- `API_KEY` (línea 25)

### 7.2 Tests Incluidos

1. ✅ Health check
2. ✅ Generación eléctrica
3. ✅ Hidrología
4. ✅ Demanda del sistema
5. ✅ Precios de bolsa
6. ✅ Métricas generales
7. ✅ Intent desconocido (manejo de error)
8. ✅ Validación de sessionId

### 7.3 Pruebas Manuales

Ver ejemplos completos en:
- `docs/EJEMPLOS_ORQUESTADOR_CHATBOT.md`

Incluye ejemplos en:
- cURL
- Python
- JavaScript/TypeScript

---

## 8. Monitoreo

### 8.1 Logs

**Ubicación:** `/home/admonctrlxm/server/logs/`

**Formato:**
```
[ORCHESTRATOR] SessionId: {sessionId} | Intent: {intent} | Parameters: {params}
[ORCHESTRATOR] SessionId: {sessionId} | Status: {status} | Elapsed: {time}s
```

**Niveles:**
- `INFO`: Requests y responses exitosos
- `WARNING`: Servicios parcialmente disponibles
- `ERROR`: Errores de procesamiento

### 8.2 Métricas Recomendadas

- Requests por minuto
- Tasa de éxito por intent
- Tiempos de respuesta promedio
- Rate de errores (SUCCESS vs PARTIAL_SUCCESS vs ERROR)
- Intents más utilizados

### 8.3 Debugging

Para debugging, buscar logs por `sessionId`:

```bash
grep "sessionId: chat_123456789" /home/admonctrlxm/server/logs/api.log
```

---

## 9. Anexos

### 9.1 Códigos de Error

| Código | Descripción | Acción |
|--------|-------------|--------|
| `UNKNOWN_INTENT` | Intent no reconocido | Verificar intent válido |
| `VALIDATION_ERROR` | Error en validación | Corregir formato de parámetros |
| `SERVICE_ERROR` | Error en servicio backend | Reportar para investigación |
| `TIMEOUT` | Timeout en servicio | Reintentar o verificar backend |
| `NO_DATA` | Sin datos disponibles | Verificar fechas o parámetros |
| `PARTIAL_DATA` | Datos parciales | Algunos servicios fallaron |
| `INTERNAL_ERROR` | Error inesperado | Contactar soporte |

### 9.2 Mejores Prácticas para el Chatbot

1. **SessionId único:** Generar un ID único por conversación
2. **Retry logic:** Implementar backoff exponencial para errores temporales
3. **Cache:** Considerar cachear responses frecuentes
4. **Timeout cliente:** Configurar timeout de 35 segundos mínimo
5. **Validación:** Validar fechas antes de enviar
6. **Logging:** Loguear sessionId para correlación
7. **Fallback:** Tener respuestas por defecto para PARTIAL_SUCCESS

### 9.3 Contactos

- **Desarrollador Backend:** [Tu nombre]
- **Email:** [Tu email]
- **Chatbot Developer:** Oscar Parra

### 9.4 Próximos Pasos de Integración

1. ✅ Implementación del orquestador completada
2. 📋 Entrega de credenciales (API Key) a Oscar Parra
3. 🧪 Pruebas de integración conjuntas
4. 🔄 Ajustes según feedback del chatbot
5. 🚀 Despliegue a producción  
6. 📊 Monitoreo inicial y optimización

---

## ✅ Entregables Completados

- [x] Endpoint desplegado y operativo
- [x] Documentación técnica completa
- [x] Documentación OpenAPI/Swagger
- [x] Ejemplos funcionales para todos los intents
- [x] Suite de pruebas automatizada
- [x] Respuesta formal al correo
- [x] Logs estructurados implementados
- [x] Manejo robusto de errores
- [x] Seguridad implementada (API Key, validación, rate limiting)
- [x] Timeouts configurados (10s/servicio, 30s/total)

---

**Documento generado:** 9 de febrero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Producción Ready
