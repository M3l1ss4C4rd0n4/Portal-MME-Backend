# 📡 Endpoint Orquestador - Documentación para Integración Externa

## Información para Oscar (Servidor Java)

**Fecha:** 9 de febrero de 2026  
**Destinatario:** Oscar (Equipo Chatbot Java)  
**Propósito:** Consumir orquestador de alertas desde servidor externo

---

## 🌐 Endpoint Público

### URL Base
```
https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator
```

**Método:** `POST`  
**Disponibilidad:** 24/7 (Servicio systemd con auto-restart)  
**Timeout:** 30 segundos máximo por request  
**Rate Limit:** 100 requests/minuto

---

## 🔐 Autenticación

### API Key (Header requerido)
```
X-API-Key: MME2026_SECURE_KEY
```

**⚠️ IMPORTANTE:** Esta API Key debe enviarse en **cada request** como HTTP header.

---

## 📋 Contrato del Endpoint

### Request Body
```json
{
  "sessionId": "string (requerido, max 100 chars)",
  "intent": "string (requerido, enum)",
  "parameters": {
    "key": "value (opcional, depende del intent)"
  }
}
```

#### Intents Disponibles

| Intent | Descripción | Parámetros Opcionales |
|--------|-------------|-----------------------|
| `generacion_electrica` | Consulta generación eléctrica actual/histórica | `fecha_consulta` (YYYY-MM-DD) |
| `hidrologia` | Datos hidrológicos (embalses, aportes) | `embalse`, `fecha_inicio`, `fecha_fin` |
| `demanda_sistema` | Demanda energética del sistema | `fecha`, `tipo_demanda` |
| `precio_bolsa` | Precios en bolsa energética | `fecha`, `tipo_precio` |
| `predicciones` | Predicciones ML (7 días) | `tipo_prediccion`, `recurso` |
| `informe_ejecutivo` | Informe completo del sistema | N/A |
| `metricas_generales` | Métricas generales del sector | N/A |

### Response Body
```json
{
  "status": "SUCCESS | PARTIAL_SUCCESS | ERROR",
  "message": "string (descripción estado)",
  "data": {
    "resultados": [...],
    "metadata": {}
  },
  "errors": [
    {
      "service": "string (nombre del servicio)",
      "error": "string (descripción del error)"
    }
  ],
  "timestamp": "2026-02-09T17:30:00.000Z",
  "sessionId": "string (mismo del request)",
  "intent": "string (mismo del request)"
}
```

#### Estados de Respuesta

- **SUCCESS** (200): Operación completada exitosamente
- **PARTIAL_SUCCESS** (200): Operación parcial (algunos servicios fallaron)
- **ERROR** (500/400/401/422): Fallo total

---

## ☕ Ejemplo de Consumo desde Java

### Usando Java 11+ HttpClient

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

public class OrchestratorClient {
    private static final String BASE_URL = "https://portalenergetico.minenergia.gov.co";
    private static final String API_KEY = "MME2026_SECURE_KEY";
    private static final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();
    
    private static final Gson gson = new Gson();
    
    /**
     * Consulta generación eléctrica
     */
    public static JsonObject consultarGeneracion(String sessionId) throws Exception {
        // Crear request body
        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("sessionId", sessionId);
        requestBody.addProperty("intent", "generacion_electrica");
        requestBody.add("parameters", new JsonObject());
        
        // Crear HTTP request
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/v1/chatbot/orchestrator"))
            .header("Content-Type", "application/json")
            .header("X-API-Key", API_KEY)
            .timeout(Duration.ofSeconds(30))
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(requestBody)))
            .build();
        
        // Enviar request
        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
        
        // Validar respuesta
        if (response.statusCode() != 200) {
            throw new RuntimeException("Error HTTP: " + response.statusCode());
        }
        
        // Parsear JSON
        return gson.fromJson(response.body(), JsonObject.class);
    }
    
    /**
     * Obtener informe ejecutivo completo
     */
    public static JsonObject obtenerInformeEjecutivo(String sessionId) throws Exception {
        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("sessionId", sessionId);
        requestBody.addProperty("intent", "informe_ejecutivo");
        requestBody.add("parameters", new JsonObject());
        
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/v1/chatbot/orchestrator"))
            .header("Content-Type", "application/json")
            .header("X-API-Key", API_KEY)
            .timeout(Duration.ofSeconds(30))
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(requestBody)))
            .build();
        
        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
            
        return gson.fromJson(response.body(), JsonObject.class);
    }
    
    /**
     * Consultar predicciones ML
     */
    public static JsonObject obtenerPredicciones(String sessionId, String tipoPrediccion) 
        throws Exception {
        
        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("sessionId", sessionId);
        requestBody.addProperty("intent", "predicciones");
        
        // Parámetros opcionales
        JsonObject params = new JsonObject();
        if (tipoPrediccion != null) {
            params.addProperty("tipo_prediccion", tipoPrediccion);
        }
        requestBody.add("parameters", params);
        
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/v1/chatbot/orchestrator"))
            .header("Content-Type", "application/json")
            .header("X-API-Key", API_KEY)
            .timeout(Duration.ofSeconds(30))
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(requestBody)))
            .build();
        
        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
            
        return gson.fromJson(response.body(), JsonObject.class);
    }
    
    /**
     * Ejemplo de uso principal
     */
    public static void main(String[] args) {
        try {
            // Generar session ID único
            String sessionId = "chatbot-java-" + System.currentTimeMillis();
            
            // 1. Consultar generación
            System.out.println("📊 Consultando generación eléctrica...");
            JsonObject generacion = consultarGeneracion(sessionId);
            System.out.println("Status: " + generacion.get("status").getAsString());
            System.out.println("Message: " + generacion.get("message").getAsString());
            
            // 2. Obtener informe ejecutivo
            System.out.println("\n📋 Obteniendo informe ejecutivo...");
            JsonObject informe = obtenerInformeEjecutivo(sessionId);
            System.out.println("Status: " + informe.get("status").getAsString());
            
            // 3. Predicciones
            System.out.println("\n🔮 Consultando predicciones...");
            JsonObject predicciones = obtenerPredicciones(sessionId, "generacion");
            System.out.println("Status: " + predicciones.get("status").getAsString());
            
            System.out.println("\n✅ Todas las consultas exitosas");
            
        } catch (Exception e) {
            System.err.println("❌ Error: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
```

### Dependencias Maven (pom.xml)
```xml
<dependencies>
    <!-- Gson para JSON -->
    <dependency>
        <groupId>com.google.code.gson</groupId>
        <artifactId>gson</artifactId>
        <version>2.10.1</version>
    </dependency>
</dependencies>
```

### Usando Spring RestTemplate (Alternativa)

```java
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import java.util.HashMap;
import java.util.Map;

@Service
public class OrchestratorService {
    
    private final RestTemplate restTemplate;
    private static final String BASE_URL = "https://portalenergetico.minenergia.gov.co/api/v1/chatbot";
    private static final String API_KEY = "MME2026_SECURE_KEY";
    
    public OrchestratorService() {
        this.restTemplate = new RestTemplate();
    }
    
    /**
     * Llamar al orquestador
     */
    public ResponseEntity<Map> llamarOrquestador(String sessionId, String intent, Map<String, Object> parameters) {
        // Preparar headers
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-API-Key", API_KEY);
        
        // Preparar body
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("sessionId", sessionId);
        requestBody.put("intent", intent);
        requestBody.put("parameters", parameters != null ? parameters : new HashMap<>());
        
        // Crear entity
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(requestBody, headers);
        
        // Llamar endpoint
        return restTemplate.exchange(
            BASE_URL + "/orchestrator",
            HttpMethod.POST,
            entity,
            Map.class
        );
    }
    
    /**
     * Ejemplo: Consultar generación
     */
    public Map consultarGeneracion(String sessionId) {
        ResponseEntity<Map> response = llamarOrquestador(
            sessionId,
            "generacion_electrica",
            null
        );
        
        if (response.getStatusCode() == HttpStatus.OK) {
            return response.getBody();
        } else {
            throw new RuntimeException("Error al consultar generación: " + response.getStatusCode());
        }
    }
}
```

---

## 🔥 Ejemplos de Request/Response Reales

### Ejemplo 1: Generación Eléctrica

**Request:**
```bash
curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: MME2026_SECURE_KEY" \
  -d '{
    "sessionId": "java-bot-12345",
    "intent": "generacion_electrica",
    "parameters": {
      "fecha_consulta": "2026-02-09"
    }
  }'
```

**Response (200 OK):**
```json
{
  "status": "SUCCESS",
  "message": "Datos de generación eléctrica obtenidos exitosamente",
  "data": {
    "generacion_total_gwh": 18.5,
    "generacion_por_recurso": {
      "hidraulica": 12.3,
      "termica": 4.2,
      "solar": 1.5,
      "eolica": 0.5
    },
    "porcentaje_hidraulica": 66.5,
    "fecha": "2026-02-09",
    "hora_actualizacion": "16:00:00"
  },
  "errors": [],
  "timestamp": "2026-02-09T16:05:23.456Z",
  "sessionId": "java-bot-12345",
  "intent": "generacion_electrica"
}
```

### Ejemplo 2: Informe Ejecutivo

**Request:**
```bash
curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: MME2026_SECURE_KEY" \
  -d '{
    "sessionId": "java-bot-informe-001",
    "intent": "informe_ejecutivo",
    "parameters": {}
  }'
```

**Response (200 OK):**
```json
{
  "status": "SUCCESS",
  "message": "Informe ejecutivo generado exitosamente",
  "data": {
    "resumen_ejecutivo": {
      "generacion_total": 18.5,
      "demanda_total": 17.2,
      "reserva_porcentaje": 7.6,
      "precio_promedio_bolsa": 245.8
    },
    "alertas_activas": [
      {
        "tipo": "HIDROLOGICA",
        "nivel": "MEDIA",
        "descripcion": "Nivel de embalses en 65%"
      }
    ],
    "predicciones_7dias": {
      "generacion_promedio": 18.2,
      "tendencia": "ESTABLE"
    }
  },
  "errors": [],
  "timestamp": "2026-02-09T16:10:45.789Z",
  "sessionId": "java-bot-informe-001",
  "intent": "informe_ejecutivo"
}
```

### Ejemplo 3: Error - API Key Inválida

**Request:**
```bash
curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: WRONG_KEY" \
  -d '{
    "sessionId": "test",
    "intent": "generacion_electrica",
    "parameters": {}
  }'
```

**Response (401 Unauthorized):**
```json
{
  "detail": "API Key inválida o ausente"
}
```

### Ejemplo 4: Error - Validación

**Request:**
```bash
curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: MME2026_SECURE_KEY" \
  -d '{
    "sessionId": "",
    "intent": "INTENT_INVALIDO",
    "parameters": {}
  }'
```

**Response (422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "loc": ["body", "sessionId"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    },
    {
      "loc": ["body", "intent"],
      "msg": "value is not a valid enumeration member",
      "type": "type_error.enum"
    }
  ]
}
```

---

## ⚡ Características Técnicas

### Arquitectura
- **Framework:** FastAPI (Python)
- **Server:** Gunicorn + Uvicorn Workers (4 workers)
- **Proxy:** Nginx (puertos 80/443)
- **Protocolo:** HTTP/1.1, HTTPS disponible
- **Formato:** JSON exclusivamente

### Seguridad
✅ API Key validation  
✅ Rate limiting (100 req/min)  
✅ Input sanitization  
✅ Pydantic validation  
✅ Error handling robusto  
✅ No exposición de errores internos  

### Timeouts
- **Por servicio interno:** 10 segundos
- **Total request:** 30 segundos máximo
- **Connection timeout:** 10 segundos

### Disponibilidad 24/7
- **Servicio:** systemd (api-mme.service)
- **Auto-restart:** Habilitado
- **Logs:** `/home/admonctrlxm/server/logs/`
  - `api-access.log` - Logs de acceso
  - `api-error.log` - Logs de errores
- **Monitoreo:** Health check en `/api/v1/chatbot/health`

---

## 🔍 Health Check Endpoint

### Verificar Estado del Servicio

**URL:**
```
GET https://portalenergetico.minenergia.gov.co/api/v1/chatbot/health
```

**Headers:** NO requiere API Key

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-09T16:15:00.000Z",
  "version": "1.0.0",
  "uptime_seconds": 125436
}
```

**Ejemplo curl:**
```bash
curl -X GET "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/health"
```

---

## 📚 Documentación Interactiva

### Swagger UI
```
https://portalenergetico.minenergia.gov.co/api/docs
```

### ReDoc
```
https://portalenergetico.minenergia.gov.co/api/redoc
```

### OpenAPI Schema (JSON)
```
https://portalenergetico.minenergia.gov.co/api/openapi.json
```

---

## ❓ Manejo de Errores - Guía Completa

### Códigos HTTP

| Código | Significado | Acción Recomendada |
|--------|-------------|-------------------|
| 200 | SUCCESS/PARTIAL_SUCCESS | Procesar respuesta |
| 400 | Bad Request | Revisar formato del request |
| 401 | Unauthorized | Verificar API Key |
| 422 | Validation Error | Revisar campos del request |
| 429 | Rate Limit Exceeded | Reintentar después de 60s |
| 500 | Internal Server Error | Reintentar con backoff exponencial |
| 503 | Service Unavailable | Servicio temporalmente no disponible |

### Estrategia de Reintentos (Java)

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class RetryStrategy {
    private static final int MAX_RETRIES = 3;
    private static final int BASE_DELAY_MS = 1000;
    
    /**
     * Ejecutar con reintentos exponenciales
     */
    public static <T> T executeWithRetry(java.util.function.Supplier<T> operation) 
        throws Exception {
        
        int attempt = 0;
        Exception lastException = null;
        
        while (attempt < MAX_RETRIES) {
            try {
                return operation.get();
            } catch (Exception e) {
                lastException = e;
                attempt++;
                
                if (attempt < MAX_RETRIES) {
                    long delayMs = BASE_DELAY_MS * (long) Math.pow(2, attempt - 1);
                    System.out.println("Intento " + attempt + " falló. Reintentando en " + delayMs + "ms...");
                    TimeUnit.MILLISECONDS.sleep(delayMs);
                } else {
                    System.err.println("Todos los reintentos fallaron");
                }
            }
        }
        
        throw lastException;
    }
    
    /**
     * Ejemplo de uso
     */
    public static void main(String[] args) {
        try {
            JsonObject resultado = executeWithRetry(() -> {
                try {
                    return OrchestratorClient.consultarGeneracion("test-session");
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });
            
            System.out.println("✅ Éxito: " + resultado);
            
        } catch (Exception e) {
            System.err.println("❌ Error final: " + e.getMessage());
        }
    }
}
```

---

## 🧪 Testing desde Servidor Externo

### Comando curl (Terminal Linux/Mac)
```bash
# Test básico
curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: MME2026_SECURE_KEY" \
  -d '{
    "sessionId": "test-external-001",
    "intent": "metricas_generales",
    "parameters": {}
  }' | jq .

# Medir tiempo de respuesta
time curl -X POST "https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: MME2026_SECURE_KEY" \
  -d '{
    "sessionId": "perf-test",
    "intent": "generacion_electrica",
    "parameters": {}
  }'
```

### Test desde Postman
1. **Method:** POST
2. **URL:** `https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator`
3. **Headers:**
   - `Content-Type: application/json`
   - `X-API-Key: MME2026_SECURE_KEY`
4. **Body (raw JSON):**
   ```json
   {
     "sessionId": "postman-test-123",
     "intent": "generacion_electrica",
     "parameters": {}
   }
   ```

---

## 📞 Contacto y Soporte

**Equipo:** Portal Energético MME  
**Servidor:** `portalenergetico.minenergia.gov.co`  
**IP:** `172.17.0.46` (interna)  
**Dominio Público:** `https://portalenergetico.minenergia.gov.co`  

### Para Reportar Problemas
1. Verificar health endpoint primero
2. Revisar código de error HTTP
3. Incluir sessionId para rastreo
4. Proporcionar timestamp del error
5. Compartir request/response completo (sin API Key en logs públicos)

---

## ✅ Checklist de Integración

Antes de integrar en producción, verificar:

- [ ] API Key configurada correctamente (`MME2026_SECURE_KEY`)
- [ ] URL correcta con HTTPS
- [ ] Header `X-API-Key` incluido en todos los requests
- [ ] Header `Content-Type: application/json`
- [ ] Validación de intents permitidos
- [ ] Manejo de errores HTTP (401, 422, 500, 503)
- [ ] Timeouts configurados (30s recomendado)
- [ ] Estrategia de reintentos implementada
- [ ] Logs de requests/responses habilitados
- [ ] Health check endpoint probado
- [ ] Tests desde servidor externo completados
- [ ] Documentación Swagger revisada

---

## 🎯 Resumen para Oscar

**✅ TODO LISTO PARA CONSUMO DESDE JAVA**

1. **Endpoint público accesible:** `https://portalenergetico.minenergia.gov.co/api/v1/chatbot/orchestrator`
2. **Disponibilidad:** 24/7 con systemd y auto-restart
3. **Seguridad:** API Key validation activada
4. **Documentación:** Swagger UI disponible
5. **Ejemplos Java:** Incluidos en este documento (HttpClient + Spring)
6. **7 Intents soportados:** Todos operacionales
7. **Contrato estable:** Request/Response definidos con Pydantic
8. **Error handling robusto:** Estados SUCCESS/PARTIAL/ERROR
9. **Rate limiting:** 100 req/min
10. **Logs y monitoreo:** Activos

**🚀 Puedes comenzar la integración inmediatamente**

---

**Documento generado:** 9 de febrero de 2026  
**Versión:** 1.0  
**Estado:** ✅ PRODUCCION - LISTO PARA USO EXTERNO
