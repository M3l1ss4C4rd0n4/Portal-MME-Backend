# 🚀 Guía de Uso - API REST Portal Energético MME

**Fecha:** 6 de febrero de 2026  
**Estado:** ✅ API Completamente Funcional

---

## ✅ **ESTADO ACTUAL**

El servidor FastAPI está **funcionando correctamente** en:
- **URL Base:** `http://localhost:8000`
- **Documentación Swagger:** `http://localhost:8000/api/docs`
- **Documentación ReDoc:** `http://localhost:8000/api/redoc`
- **Modo:** Desarrollo (autenticación deshabilitada)

---

## 🎯 **INICIO RÁPIDO**

### **Opción 1: Script de Desarrollo (Recomendado)**

```bash
# Ejecutar desde ~/server
./api/start_dev.sh
```

**Características:**
- ✅ Entorno desarrollo
- ✅ Documentación Swagger habilitada
- ✅ Autenticación API Key deshabilitada
- ✅ Auto-reload activado
- ✅ Debug habilitado

### **Opción 2: Inicio Manual**

```bash
cd /home/admonctrlxm/server
source venv/bin/activate

# Configurar variables de entorno
export DASH_ENV=development
export API_KEY_ENABLED=false

# Iniciar servidor
python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📚 **DOCUMENTACIÓN INTERACTIVA**

### **Swagger UI (Recomendado para pruebas)**
```
http://localhost:8000/api/docs
```

**Características:**
- ✅ Interfaz interactiva
- ✅ Probar endpoints directamente
- ✅ Ver esquemas de datos
- ✅ Generar ejemplos automáticos
- ✅ Ver respuestas en tiempo real

### **ReDoc (Recomendado para consulta)**
```
http://localhost:8000/api/redoc
```

**Características:**
- ✅ Documentación ordenada
- ✅ Búsqueda integrada
- ✅ Exportar a PDF
- ✅ Navegación jerárquica

---

## 🧪 **PROBAR ENDPOINTS**

### **1. Verificar Estado del Servicio**

```bash
curl http://localhost:8000/
```

**Respuesta esperada:**
```json
{
    "service": "Portal Energético MME - API",
    "version": "1.0.0",
    "status": "operational",
    "documentation": "/api/docs",
    "endpoints": {
        "health": "/health",
        "v1": "/api/v1"
    }
}
```

### **2. Probar Endpoint de Salud**

```bash
curl http://localhost:8000/health
```

### **3. Obtener Generación del Sistema**

```bash
# Últimos 30 días (default)
curl "http://localhost:8000/api/v1/generation/system"

# Rango de fechas específico
curl "http://localhost:8000/api/v1/generation/system?start_date=2026-01-01&end_date=2026-01-31"
```

**Respuesta esperada:**
```json
{
    "total_points": 31,
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
    "data": [
        {
            "date": "2026-01-01",
            "value": 234.56,
            "resource": null,
            "agent": null,
            "region": null,
            "metadata": null
        }
    ]
}
```

### **4. Obtener Mix Energético**

```bash
# Mix de ayer
curl "http://localhost:8000/api/v1/generation/mix"

# Mix de fecha específica
curl "http://localhost:8000/api/v1/generation/mix?date=2026-02-01"
```

### **5. Obtener Aportes Hídricos**

```bash
curl "http://localhost:8000/api/v1/hydrology/aportes?start_date=2026-01-01"
```

### **6. Obtener Precios de Bolsa**

```bash
curl "http://localhost:8000/api/v1/system/prices?start_date=2026-02-01"
```

---

## 📋 **CATEGORÍA DE ENDPOINTS DISPONIBLES**

### **1️⃣ Generación (4 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/generation/system` | GET | Generación total del sistema |
| `/api/v1/generation/by-source` | GET | Generación por tipo de fuente |
| `/api/v1/generation/resources` | GET | Catálogo de recursos generadores |
| `/api/v1/generation/mix` | GET | Mix energético diario |

### **2️⃣ Hidrología (3 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/hydrology/aportes` | GET | Aportes hídricos diarios |
| `/api/v1/hydrology/reservoirs` | GET | Catálogo de embalses |
| `/api/v1/hydrology/energy` | GET | Energía embalsada del sistema |

### **3️⃣ Sistema (2 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/system/demand` | GET | Demanda eléctrica nacional |
| `/api/v1/system/prices` | GET | Precios de bolsa |

### **4️⃣ Transmisión (3 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/transmission/lines` | GET | Catálogo de líneas de transmisión |
| `/api/v1/transmission/flows` | GET | Flujos de potencia en líneas |
| `/api/v1/transmission/international` | GET | Intercambios internacionales |

### **5️⃣ Distribución (2 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/distribution/data` | GET | Datos de distribución por operador |
| `/api/v1/distribution/operators` | GET | Catálogo de operadores |

### **6️⃣ Comercial (2 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/commercial/prices` | GET | Precios comerciales de energía |
| `/api/v1/commercial/contracts` | GET | Contratos de energía |

### **7️⃣ Pérdidas (1 endpoint)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/losses/data` | GET | Pérdidas de energía (total/técnicas/no técnicas) |

### **8️⃣ Restricciones (1 endpoint)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/restrictions/data` | GET | Restricciones operativas del sistema |

### **9️⃣ Métricas (2 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/metrics/` | GET | Listar métricas disponibles |
| `/api/v1/metrics/{metric_id}` | GET | Obtener datos de métrica específica |

### **🔟 Predicciones (2 endpoints)**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/predictions/` | GET | Listar predicciones existentes |
| `/api/v1/predictions/generate` | POST | Generar nueva predicción |

**TOTAL: 25 endpoints disponibles**

---

## 🔧 **PARÁMETROS COMUNES**

### **Fechas (Formato ISO 8601)**

```
?start_date=2026-02-01
?end_date=2026-02-05
?date=2026-02-03
```

**Defaults:**
- Si no se especifica `start_date`: últimos 30 días
- Si no se especifica `end_date`: hoy
- Si no se especifica `date`: ayer

### **Filtros Opcionales**

```
?resource=HIDRAULICA
?agent=EMGESA
?operator=CODENSA
?loss_type=total
?restriction_type=generation
```

---

## 📊 **FORMATO DE RESPUESTAS**

### **Respuesta Exitosa (200 OK)**

```json
{
    "total_points": 100,
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
    "data": [
        {
            "date": "2026-01-01",
            "value": 234.56,
            "resource": "HIDRAULICA",
            "agent": null,
            "region": null,
            "metadata": {
                "source": "xm_api",
                "quality": "validated"
            }
        }
    ]
}
```

### **Respuesta de Error (4xx/5xx)**

```json
{
    "error": "Bad Request",
    "message": "Fecha inicial debe ser anterior a fecha final",
    "details": {
        "start_date": "2026-02-01",
        "end_date": "2026-01-01"
    }
}
```

---

## 🛠️ **SOLUCIÓN DE PROBLEMAS**

### **Error: "No module named uvicorn"**

```bash
# Instalar dependencias
cd /home/admonctrlxm/server
source venv/bin/activate
pip install fastapi uvicorn[standard] python-multipart slowapi httpx pydantic
```

### **Error: "No module named pandas"**

```bash
# Instalar dependencias adicionales
pip install pandas numpy sqlalchemy psycopg2-binary python-dotenv requests openai
```

### **Error: "Port 8000 already in use"**

```bash
# Matar proceso en puerto 8000
sudo lsof -t -i:8000 | xargs kill -9

# O usar otro puerto
python3 -m uvicorn api.main:app --reload --port 8001
```

### **Error: "401 Unauthorized"**

```bash
# Asegurar que autenticación esté deshabilitada
export API_KEY_ENABLED=false

# O iniciar con script de desarrollo
./api/start_dev.sh
```

### **Documentación no disponible (404)**

```bash
# Verificar que esté en modo desarrollo
export DASH_ENV=development

# Reiniciar servidor
./api/start_dev.sh
```

---

## 🎯 **CASOS DE USO**

### **Caso 1: Dashboard Externo**

```javascript
// Obtener generación del último mes
fetch('http://localhost:8000/api/v1/generation/system')
  .then(res => res.json())
  .then(data => {
    console.log(`Total de puntos: ${data.total_points}`);
    // Renderizar en gráfico
  });
```

### **Caso 2: Análisis de Datos**

```python
import requests
import pandas as pd

# Obtener datos
response = requests.get(
    'http://localhost:8000/api/v1/generation/system',
    params={'start_date': '2026-01-01', 'end_date': '2026-01-31'}
)

# Convertir a DataFrame
df = pd.json_normalize(response.json()['data'])
print(df.describe())
```

### **Caso 3: Integración con BI**

```bash
# Power BI / Tableau
# Usar como origen de datos Web API
# URL: http://localhost:8000/api/v1/generation/system
# Método: GET
# Formato: JSON
```

---

## 🔐 **MODO PRODUCCIÓN**

Para usar la API en producción:

```bash
# 1. Configurar variables de entorno
export DASH_ENV=production
export API_KEY_ENABLED=true
export API_KEY=tu_clave_secreta_aqui

# 2. Usar script de producción
./api/run_prod.sh

# O usar gunicorn
gunicorn -c gunicorn_config.py api.main:app
```

**Cambios en producción:**
- ✅ Documentación deshabilitada
- ✅ Autenticación API Key requerida
- ✅ Rate limiting estricto
- ✅ HTTPS recomendado
- ✅ Logs de auditoría

---

## 📈 **MONITOREO**

### **Verificar Estado**

```bash
# Health check
curl http://localhost:8000/health

# Logs en tiempo real
tail -f logs/api.log
```

### **Métricas Prometheus**

```bash
# Endpoint de métricas (si está configurado)
curl http://localhost:8000/metrics
```

---

## 🎉 **RESUMEN**

```
╔════════════════════════════════════════════════════════╗
║  ✅ API REST 100% FUNCIONAL                            ║
║                                                        ║
║  🚀 25 endpoints operacionales                         ║
║  📚 Documentación Swagger completa                     ║
║  🔓 Sin autenticación en desarrollo                    ║
║  ⚡ Auto-reload habilitado                             ║
║  📊 Formato JSON estandarizado                         ║
║  🎯 Rate limiting configurado                          ║
║  🔍 Validación Pydantic automática                     ║
║  📈 Listo para integración externa                     ║
║                                                        ║
║  🌐 URL: http://localhost:8000                         ║
║  📖 Docs: http://localhost:8000/api/docs               ║
╚════════════════════════════════════════════════════════╝
```

---

**Desarrollado por:** GitHub Copilot (Claude Sonnet 4.5)  
**Proyecto:** Portal Energético MME  
**Última actualización:** 6 de febrero de 2026
