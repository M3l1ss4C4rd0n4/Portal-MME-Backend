# 🚀 Guía de Uso - API REST Portal Energético MME

**Fecha:** 6 de febrero de 2026
**Reescrita:** 2026-09-30 — esta versión cubre los 115 endpoints reales en 32 archivos de rutas
(antes solo documentaba ~25 de ejemplo, metrics/predictions). Fuente de verdad del conteo:
[`api/README.md`](../api/README.md), que tiene la tabla completa por archivo con descripción de
cada dominio.

---

## ✅ **ESTADO ACTUAL**

El servidor FastAPI está **funcionando correctamente** en:
- **URL Base:** `http://localhost:8000` (local, atado a loopback desde el 29-sep — no alcanzable
  directamente desde fuera del servidor) / `https://portaldireccionee.minenergia.gov.co` (público,
  vía `nginx`; `portalenergetico.minenergia.gov.co` es el Portal Energético, un dominio distinto)
- **Documentación Swagger:** `http://localhost:8000/api/docs`
- **Documentación ReDoc:** `http://localhost:8000/api/redoc`
- **Modo:** Producción (autenticación API Key activa)

---

## 🎯 **INICIO RÁPIDO**

### **Producción real (systemd — la única forma en que corre hoy)**

```bash
# Verificar estado
sudo systemctl status portal-api.service

# Reiniciar si es necesario (necesario también tras rotar la API key)
sudo systemctl restart portal-api.service
```

El proceso real es `uvicorn` plano (sin Gunicorn ni múltiples workers) vía systemd — ver el
`ExecStart` real de `portal-api.service` en `RUNBOOK_PRODUCCION.md`. No existe ningún script de
arranque alternativo con Gunicorn en este repo: si alguna vez lo hay, no es la ruta de producción
real y binding a `0.0.0.0` revertiría el cierre de seguridad del 29-sep.

**Características:**
- ✅ Autenticación API Key activa (`X-API-Key` requerido), validada contra una lista blanca que
  admite varias claves a la vez para rotar sin downtime
- ✅ Límite de uso por minuto (`slowapi`) en los endpoints más costosos
- ✅ Auto-restart si falla (`Restart=on-failure` en systemd)
- ✅ Monitoreo cada 5 minutos (`scripts/monitor_api.sh`, cron)
- ✅ Disponible 24/7

### **Inicio manual (solo desarrollo local)**

```bash
cd /home/admonctrlxm/server
source venv/bin/activate

export DASH_ENV=development
export API_KEY_ENABLED=false

python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📚 **DOCUMENTACIÓN INTERACTIVA**

### **Swagger UI (Recomendado para pruebas)**
```
http://localhost:8000/api/docs
```
Deshabilitado automáticamente si `DASH_ENV=production`.

### **ReDoc (Recomendado para consulta)**
```
http://localhost:8000/api/redoc
```

---

## 📡 Dominios de endpoints reales — los 115, por archivo

Ver la tabla completa, verificada por grep sobre el código (no estimada), en
[`api/README.md`](../api/README.md) § "Dominios de endpoints reales". Resumen por grupo:

| Grupo | Archivos | Ejemplos de ruta |
|---|---|---|
| Métricas del sector (XM) | `metrics.py`, `system.py`, `generation.py`, `hydrology.py`, `commercial.py`, `distribution.py`, `transmission.py`, `restrictions.py`, `losses.py` | `/api/v1/generation/system`, `/api/v1/hydrology/aportes`, `/api/v1/system/prices` |
| Predicciones | `predictions.py` | `/api/v1/predictions/dashboard` |
| Balance oferta-demanda (nuevo, 29-sep) | `balance_oferta_demanda.py` | `/v1/balance-oferta-demanda/historico`, `/demanda-no-atendida-regional`, `/proyectos-upme`, `/correlacion-retraso`, `POST /simular-contrafactual` |
| Costo Unitario | `cu.py` | `/api/v1/cu/minorista/promedio-nacional` |
| Ontología + RAG | `ontologia.py` (17 endpoints) | `/v1/ontologia/geografia/{id}/resumen` |
| Asistente IA + voz | `chatbot.py`, `voz.py` | `/v1/chatbot/asistente` (streaming SSE), `/v1/voz/token`, `/v1/voz/ws` |
| Informes/reportes | `reports.py`, `informes_tableros.py` | Generación e histórico de informes ejecutivos/PDF |
| Simulación | `simulation.py`, `riesgo.py` | Escenarios CREG, riesgo de atraso de contratos OR |
| Dominios sectoriales | `comunidades.py`, `contratos_or.py`, `fenoge.py`, `subsidios.py`, `presupuesto.py`, `supervision_portal.py` | Comunidades energéticas, contratos OR, FENOGE, subsidios, presupuesto, supervisión |
| App móvil / alertas | `energia_app.py`, `energia_dashboard.py`, `whatsapp_alerts.py` | App EnergIA, alertas de WhatsApp |
| Observabilidad | `observability.py`, `internal.py` | Health checks internos, métricas de sistema |
| `/health` | — | Health check general (JSON con clave `services`) |

**Ejemplo — métrica cruda:**
```bash
curl -H "X-API-Key: <tu-api-key>" \
  "http://localhost:8000/api/v1/metrics/Gene?entity=Sistema&start_date=2026-01-01"
```

**Ejemplo — balance oferta-demanda:**
```bash
curl -H "X-API-Key: <tu-api-key>" \
  "http://localhost:8000/v1/balance-oferta-demanda/historico?start_date=2026-01-01"
```

**Ejemplo — Asistente IA (streaming SSE):**
```bash
curl -N -H "X-API-Key: <tu-api-key>" -H "Content-Type: application/json" \
  -d '{"mensaje": "¿Cómo está la generación eléctrica hoy?", "historial": []}' \
  http://localhost:8000/v1/chatbot/asistente
```

**Ejemplo — búsqueda RAG (ontología):**
```bash
curl -H "X-API-Key: <tu-api-key>" \
  "http://localhost:8000/v1/ontologia/geografia/27/resumen"
```

---

## 🤖 **ENDPOINT ORQUESTADOR (Chatbot, para integraciones externas)**

```
POST /api/v1/chatbot/orchestrator
Header: X-API-Key: <tu-api-key>
Header: Content-Type: application/json
```

A diferencia de `/v1/chatbot/asistente` (lenguaje natural libre), este endpoint requiere un
**intent preseleccionado**. Son muchos más de los 13 originales — cada categoría acepta varios
sinónimos (ej. generación: `generacion_electrica`, `consultar_generacion`, `generacion`), y el
total mapeado ronda el centenar entre intents y sinónimos (ver `api/README.md`, "~100
herramientas" del Asistente IA, construido sobre el mismo mapeo). La lista completa y vigente vive
en el docstring de la ruta (`api/v1/routes/chatbot.py::chatbot_orchestrator`) — consultarla ahí
directamente en vez de copiarla aquí, porque crece seguido y una copia estática vuelve a quedar
obsoleta.

### Ejemplo rápido

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/orchestrator \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <tu-api-key>" \
  -d '{"sessionId": "test-001", "intent": "generacion_electrica", "parameters": {}}'
```

> Integración Java: `docs/ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md` (el "13 intents" que menciona es el
> contrato estable original, no el total real de hoy).

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
cd /home/admonctrlxm/server
source venv/bin/activate
pip install -r requirements.txt
```

### **Error: "Port 8000 already in use"**

```bash
sudo lsof -t -i:8000 | xargs kill -9
# En producción real, el puerto lo ocupa portal-api.service — reiniciarlo en vez de matar el PID:
sudo systemctl restart portal-api.service
```

### **Error: "401 Unauthorized" / "403 Forbidden"**

```bash
# 401: falta el header X-API-Key.
# 403: la clave enviada no está en la lista blanca (API_KEYS_WHITELIST).
curl -H "X-API-Key: <tu-api-key>" http://localhost:8000/api/v1/generation/system

# Para desarrollo local sin auth:
export API_KEY_ENABLED=false
```

### **Documentación no disponible (404)**

```bash
# Swagger está disponible solo en modo desarrollo
export DASH_ENV=development
```

---

## 🎯 **CASOS DE USO**

### **Caso 1: Dashboard Externo**

```javascript
fetch('http://localhost:8000/api/v1/generation/system')
  .then(res => res.json())
  .then(data => {
    console.log(`Total de puntos: ${data.total_points}`);
  });
```

### **Caso 2: Análisis de Datos**

```python
import requests
import pandas as pd

response = requests.get(
    'http://localhost:8000/api/v1/generation/system',
    params={'start_date': '2026-01-01', 'end_date': '2026-01-31'},
    headers={'X-API-Key': 'tu-api-key'},
)

df = pd.json_normalize(response.json()['data'])
print(df.describe())
```

---

## 🔐 **MODO PRODUCCIÓN (real, systemd — no Gunicorn)**

```bash
# La API en producción corre así, sin alternativa (ver RUNBOOK_PRODUCCION.md §1 y §11):
sudo systemctl status portal-api.service
sudo systemctl restart portal-api.service
```

**Características reales en producción:**
- ✅ Documentación Swagger/ReDoc deshabilitada (`DASH_ENV=production`)
- ✅ Autenticación API Key requerida, contra lista blanca rotable
- ✅ Rate limiting por endpoint (`slowapi`)
- ✅ Solo accesible vía `nginx` (loopback, HTTPS en el borde)
- ✅ Logs de auditoría

---

## 📈 **MONITOREO**

```bash
# Health check
curl http://localhost:8000/health

# Logs reales (systemd, no logs/api.log)
sudo journalctl -u portal-api.service -f
```

---

## 🎉 **RESUMEN**

```
╔════════════════════════════════════════════════════════╗
║  ✅ API REST 100% FUNCIONAL                             ║
║                                                          ║
║  🚀 115 endpoints REST en 32 archivos de rutas           ║
║  📚 Documentación Swagger completa                       ║
║  🔐 API Key rotable sin downtime (lista blanca)          ║
║  🤖 Asistente IA (streaming) + orquestador de intents     ║
║  📊 Formato JSON estandarizado                           ║
║  🎯 Rate limiting por endpoint                            ║
║  🔍 Validación Pydantic automática                        ║
║  📈 Disponible 24/7 con systemd (sin Gunicorn)            ║
║                                                          ║
║  🌐 Público: https://portaldireccionee.minenergia.gov.co ║
║  📖 Docs: http://localhost:8000/api/docs                 ║
╚════════════════════════════════════════════════════════╝
```

---

**Última actualización:** 2026-09-30 — reescrita por completo contra el código real (antes
documentaba 25 de 115 endpoints reales, y citaba `run_prod.sh`/Gunicorn, un script que no se usa
en producción y que se eliminó del repo en esta misma revisión).
