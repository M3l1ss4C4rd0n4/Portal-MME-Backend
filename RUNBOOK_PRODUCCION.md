# Portal Energético MME — RunBook de Producción

> **Versión:** 1.0.0  
> **Fecha:** 2026-03-03  
> **Audiencia:** Equipo de operaciones  
> **Servidor:** Srvwebprdctrlxm (Azure VM, Ubuntu)

---

## 1. Servicios y puertos

| Servicio | Puerto | Proceso | Servicio systemd |
|---|---|---|---|
| Dashboard Dash | 127.0.0.1:8050 | gunicorn + sync workers | `dashboard-mme` |
| API FastAPI | 127.0.0.1:8000 | gunicorn + uvicorn workers | `api-mme` |
| PostgreSQL 16 | 127.0.0.1:5432 | postgresql | `postgresql` |
| Redis | 127.0.0.1:6379 | redis-server | `redis-server` |
| Celery Worker | background | celery worker | `celery-worker@1` |
| Celery Beat | background | celery beat | `celery-beat` (o cron) |
| Nginx (reverse proxy) | 80/443 | nginx | `nginx` |
| Telegram Bot | 127.0.0.1:8001 | uvicorn | (proceso propio) |
| MLflow | 127.0.0.1:5000 | uvicorn | (proceso propio) |

---

## 2. Tareas programadas (Celery Beat)

| Hora (COT) | Tarea | Descripción |
|---|---|---|
| Cada 6h (0, 6, 12, 18) | `etl_incremental_all_metrics` | ETL incremental datos XM → PostgreSQL |
| 03:00 | `clean_old_logs` | Limpieza de logs antiguos |
| Cada 30 min | `check_anomalies` | Detección de anomalías (gene, precio, embalses, CU, PNT) |
| 08:00 | `send_daily_summary` | Informe ejecutivo diario → Telegram + PDF |
| 10:00 | `calcular_cu_diario` | Cálculo Costo Unitario + Pérdidas NT |

---

## 3. Procedimientos de operación

### 3.1 Verificar estado de todos los servicios

```bash
systemctl is-active api-mme dashboard-mme postgresql redis-server nginx
# Debe mostrar "active" para cada uno

# Health check completo de la API:
curl -s http://localhost:8000/health | python3 -m json.tool

# Health check el dashboard:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8050/
# Debe retornar 200
```

### 3.2 Reiniciar el dashboard

```bash
sudo systemctl restart dashboard-mme
# o bien hot-reload sin downtime:
kill -HUP $(pgrep -f 'gunicorn_config.py' | head -1)

# Verificar:
sleep 10
curl -s -o /dev/null -w "%{http_code}" http://localhost:8050/
```

### 3.3 Reiniciar la API

```bash
sudo systemctl restart api-mme
# o bien hot-reload sin downtime:
kill -HUP $(pgrep -f 'gunicorn.*api.main' | head -1)

# Verificar:
sleep 5
curl -s http://localhost:8000/health | python3 -m json.tool
```

### 3.4 Ejecutar ETL manualmente

```bash
cd /home/admonctrlxm/server
source venv/bin/activate

# ETL incremental (todas las métricas):
python3 -c "
from tasks.etl_tasks import etl_incremental_all_metrics
etl_incremental_all_metrics()
"

# Recalcular CU para una fecha específica:
python3 -c "
from core.container import container
cu_svc = container.get_cu_service()
resultado = cu_svc.calculate_cu_for_date('2026-03-02')
print(resultado)
"
```

### 3.5 Verificar datos frescos

```bash
# Desde psql:
psql -d portal_energetico -c "
SELECT MAX(fecha) as ultima_fecha, COUNT(*) as total_filas
FROM cu_daily;
"
# → ultima_fecha debe ser >= ayer

# Desde Python:
cd /home/admonctrlxm/server && source venv/bin/activate
python3 -c "
from core.container import container
cu = container.get_cu_service().get_cu_current()
print('CU total:', cu.get('cu_total') if cu else 'N/D')
print('Fecha:', cu.get('fecha') if cu else 'N/D')
# Si None → ETL no corrió hoy
# Si > 1000 → crisis de precio de bolsa
# Si < 100 → verificar datos de entrada
"
```

### 3.6 CU o P_NT muestran valores extraños

1. Verificar fecha del último dato:
   ```bash
   python3 -c "
   from core.container import container
   cu = container.get_cu_service().get_cu_current()
   pnt = container.losses_nt_service.get_losses_statistics()
   print('CU:', cu.get('cu_total'), 'fecha:', cu.get('fecha'))
   print('PNT_30d:', pnt.get('pct_promedio_nt_30d'))
   "
   ```

2. Si el CU es None o la fecha es vieja (> 3 días):
   - La ETL probablemente falló → verificar logs celery
   - Relanzar ETL manualmente (ver sección 3.4)

3. Si el CU es > 400 COP/kWh:
   - Verificar precio de bolsa en XM: `curl -s 'https://www.simem.co/...'`
   - Si el precio de bolsa realmente subió → es correcto
   - Si no → verificar datos de entrada en tabla `metrics`

### 3.7 Circuit Breaker XM activado

Si en `/health` aparece `xm_api.circuit_state: "OPEN"`:

1. La API de XM está caída o respondiendo con errores
2. El ETL **no** ejecutará llamadas a XM mientras esté abierto
3. Esperar 5 minutos → pasará a `HALF_OPEN` automáticamente
4. Si persiste por > 1 hora → verificar https://www.simem.co manualmente
5. Si XM funciona pero el circuit sigue abierto:
   ```bash
   # Forzar reset (reiniciar workers API):
   sudo systemctl restart api-mme
   ```

### 3.8 Enviar informe diario manualmente

```bash
cd /home/admonctrlxm/server && source venv/bin/activate
python3 -c "
from tasks.anomaly_tasks import send_daily_summary
send_daily_summary()
"
```

---

## 4. Umbrales de alerta configurados

| Indicador | Umbral | Severidad | Acción |
|---|---|---|---|
| CU > 400 COP/kWh | ALERTA | Monitorear | Revisar precio de bolsa |
| CU > 600 COP/kWh | CRÍTICO | Urgente | Posible crisis energética — escalar |
| P_NT > 8% | ALERTA | Monitorear | Revisar metodología o datos fuente |
| Embalses < 30% | CRÍTICO | Urgente | Riesgo de racionamiento |
| Embalses < 40% | ALERTA | Monitorear | Aumentar vigilancia |
| Datos > 24h sin actualizar | ALERTA | Monitorear | Verificar ETL y XM API |

---

## 5. Logs importantes

| Log | Ubicación |
|---|---|
| API acceso | `/home/admonctrlxm/server/logs/api-access.log` |
| API errores | `/home/admonctrlxm/server/logs/api-error.log` |
| Dashboard acceso | `/home/admonctrlxm/server/logs/gunicorn_access.log` |
| Dashboard errores | `/home/admonctrlxm/server/logs/gunicorn_error.log` |
| Celery / ETL | `/home/admonctrlxm/server/logs/celery*.log` |
| Systemd services | `journalctl -u api-mme -f` / `journalctl -u dashboard-mme -f` |

```bash
# Ver errores recientes API:
tail -50 /home/admonctrlxm/server/logs/api-error.log

# Ver errores recientes Dashboard:
tail -50 /home/admonctrlxm/server/logs/gunicorn_error.log

# Ver logs de celery en tiempo real:
journalctl -u celery-worker@1 -f

# Buscar errores CRÍTICOS del último día:
grep -i "CRITICAL\|ERROR" /home/admonctrlxm/server/logs/*.log | tail -20
```

---

## 6. Endpoints clave para monitoreo

| Endpoint | Método | Propósito |
|---|---|---|
| `GET /health` | Dashboard :8050 | Health check completo del dashboard |
| `GET /health` | API :8000 | Health check completo: DB, Redis, XM, freshness |
| `GET /health/live` | API :8000 | Liveness probe (solo "alive") |
| `GET /health/ready` | API :8000 | Readiness probe (DB + Redis) |
| `GET /metrics` | Dashboard :8050 | Métricas Prometheus |

### Interpretar `/health` de la API

```json
{
  "status": "healthy | degraded | unhealthy",
  "checks": {
    "database": { "status": "ok", "latency_ms": 12 },
    "redis": { "status": "ok", "latency_ms": 1 },
    "xm_api": { "circuit_state": "CLOSED" },
    "data_freshness": { "hours_since_update": 6.0 }
  }
}
```

- **healthy**: Todo OK
- **degraded**: DB funciona pero Redis/XM/freshness tiene problemas (HTTP 200)
- **unhealthy**: DB no responde (HTTP 503)

---

## 7. Base de datos

### Tablas principales

| Tabla | Filas aprox. | Descripción |
|---|---|---|
| `metrics` | 13.7M+ | Datos XM: generación, demanda, precios, embalses |
| `cu_daily` | 2,200+ | Costo unitario calculado por día |
| `losses_detailed` | 2,200+ | Pérdidas técnicas y no técnicas por día |
| `predictions` | variable | Predicciones ML por métrica/horizonte |
| `alertas_historial` | variable | Alertas detectadas por el sistema |

### Backup

```bash
# Backup completo:
pg_dump portal_energetico > /home/admonctrlxm/server/backups/database/portal_$(date +%Y%m%d).sql

# Restore:
psql portal_energetico < /path/to/backup.sql
```

---

## 8. Chatbot e intents

El endpoint `POST /api/v1/chatbot/orchestrator` recibe intents del bot de Telegram/WhatsApp.

### Intents energéticos principales

| Intent | Descripción |
|---|---|
| `estado_actual` | 3 fichas KPI: generación, precio, embalses |
| `cu_actual` | Costo unitario actual con desglose |
| `perdidas_nt` | Pérdidas no técnicas 30d/12m |
| `simulacion` | Motor simulación CREG (4 escenarios) |
| `predicciones_sector` | Predicciones ML por horizonte |
| `informe_ejecutivo` | Informe completo con IA |
| `pregunta_libre` | Pregunta en lenguaje natural |

### Probar manualmente

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/orchestrator \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MME_API_KEY" \
  -d '{"sessionId":"test","intent":"cu_actual","parameters":{"pregunta":"CU actual"}}'
```

---

## 9. Contactos de escalamiento

| Rol | Nombre | Contacto |
|---|---|---|
| Administrador servidor | [Rellenar] | [Rellenar] |
| DBA PostgreSQL | [Rellenar] | [Rellenar] |
| Líder técnico portal | [Rellenar] | [Rellenar] |
| Soporte XM (datos) | XM S.A. | https://www.xm.com.co |
| Soporte Azure VM | [Rellenar] | [Rellenar] |

---

## 10. Arquitectura resumida

```
Internet
  │
  ▼
Nginx :80/:443  (reverse proxy + SSL)
  │
  ├─→ Dashboard Dash :8050  (gunicorn, sync)
  │     └─ 15 páginas + chat widget
  │
  ├─→ API FastAPI :8000  (gunicorn + uvicorn, async)
  │     └─ 21 endpoints + chatbot orchestrator
  │
  └─→ Telegram Bot :8001  (uvicorn)

Celery Worker + Beat ──→ PostgreSQL :5432
                     ──→ Redis :6379 (cache + broker)
                     ──→ XM API (SIMEM) [con circuit breaker]
```
