# Portal Energético MME — RunBook de Producción

> **Versión:** 1.2.0  
> **Fecha:** 2026-07-06 (creación) — **corregido 2026-09-01**: Celery Beat, logs reales, `/health` real, umbrales P_NT/Embalses  
> **Audiencia:** Equipo de operaciones  
> **Servidor:** Srvwebprdctrlxm (Azure VM, Ubuntu)

---

## 1. Servicios y puertos

| Servicio | Puerto | Proceso | Servicio systemd |
|---|---|---|---|
| Dashboard Dash | 127.0.0.1:8050 | gunicorn + sync workers | `dashboard-mme` |
| API FastAPI | 127.0.0.1:8000 | uvicorn | `portal-api` |
| PostgreSQL 16 | 127.0.0.1:5432 | postgresql | `postgresql` |
| Redis | 127.0.0.1:6379 | redis-server | `redis-server` |
| Celery Worker | background | celery worker | `celery-worker@1` |
| Celery Beat | background | celery beat | `celery-beat` (o cron) |
| Nginx (reverse proxy) | 80/443 | nginx | `nginx` |
| Telegram Bot | systemd | telegram-polling.service | `telegram-polling` |
| MLflow | 127.0.0.1:5000 | uvicorn | (proceso propio) |

---

## 2. Tareas programadas (Celery Beat)

> **Actualizado 2026-09-01** — la tabla anterior solo tenía 5 de las ~15 tareas reales (`tasks/__init__.py::app.conf.beat_schedule`). Faltaban, entre otras, el sanador de vistas de ontología (cada 5 min) y el backtest riguroso de predicciones (mensual) — ambos subsistemas construidos después de la última versión de este runbook.

| Hora (COT) | Tarea | Descripción |
|---|---|---|
| Cada 6h (0, 6, 12, 18) | `etl_incremental_all_metrics` | ETL incremental datos XM → PostgreSQL |
| 03:00 diario | `clean_old_logs` | Limpieza de logs antiguos |
| Cada 30 min | `check_anomalies` | Detección de anomalías (gene, precio, embalses, CU, PNT) |
| 08:30 | `send_daily_generate` | Informe ejecutivo: genera PDF, Telegram, encola emails en paralelo |
| 08:35 | `enviar_informe_diario_push` | Push FCM del informe a la app móvil EnergIA |
| 10:00 | `calcular_cu_diario` | Cálculo Costo Unitario + Pérdidas NT |
| Lunes 01:15 | `actualizar_pdo_soi` | Refresco semanal de índices climáticos PDO/SOI (NOAA) |
| Lunes 01:30 | `actualizar_oni` | Refresco semanal del índice ONI (NOAA CPC) |
| Dom/Mié/Sáb 02:00 | `regenerar_predicciones` | Reentrenamiento del ensemble Prophet+SARIMAX (embalses/demanda/generación/etc.) |
| 1er domingo del mes 03:30 | `ejecutar_backtests_predicciones` | Backtest riguroso out-of-sample (5 fuentes) — la validación real de precisión, no el holdout optimista. Ver `docs/tecnicos/PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md` |
| 7h, 12h, 19h | `refresh_news_cache` | Refresco de caché de noticias del sector |
| Lunes 02:15 | `refresh_senda_referencia` | Refresco semanal de la Senda de Referencia CREG |
| Día 1 del mes 03:00 | `refresh_precios_escasez` | Refresco mensual de Precios de Escasez (PEI/PE/PES) |
| 08:45 | `generar_diagnosticos_homeslider` | Diagnósticos generados por IA para el slider del home |
| **Cada 5 min** | `verificar_vistas_ontologia` | Sanador automático de las vistas materializadas del esquema `ontologia` — se reparan solas si un ETL externo las tumba con `DROP CASCADE` |

Fuente de verdad real: `tasks/__init__.py::app.conf.beat_schedule` — regenerar esta tabla desde ahí si vuelve a quedar desactualizada, no confiar en esta copia indefinidamente.

---

## 3. Procedimientos de operación

### 3.1 Verificar estado de todos los servicios

```bash
systemctl is-active portal-api dashboard-mme postgresql redis-server nginx
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
sudo systemctl restart portal-api.service
# o bien hot-reload sin downtime:
kill -HUP $(pgrep -f 'uvicorn.*api.main' | head -1)

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
   # Forzar reset (reiniciar API):
   sudo systemctl restart portal-api.service
   ```

### 3.8 Enviar informe diario manualmente

```bash
cd /home/admonctrlxm/server && source venv/bin/activate
python3 -c "
from tasks.anomaly_tasks import send_daily_generate
send_daily_generate()
"
```

La tarea `send_daily_generate` persiste artefactos en `whatsapp_bot/informes/`:
- `Informe_Ejecutivo_MME_YYYY-MM-DD.pdf`
- `Informe_Ejecutivo_MME_YYYY-MM-DD.html`

El envío de email se encola en subtareas Celery (`send_daily_emails_fanout` → `send_single_daily_email`).

**Documentación de contenido:** ver [`docs/INFORME_EJECUTIVO_CONTENIDO.md`](docs/INFORME_EJECUTIVO_CONTENIDO.md) (estructura del PDF, fuentes de datos por página).

**Alcance PDF:** solo sector eléctrico + gestión de riesgos + noticias. Los tableros portal (comunidades, subsidios, etc.) están suspendidos — ver [`docs/INFORME_PORTAL_CAPITULOS_PENDIENTES.md`](docs/INFORME_PORTAL_CAPITULOS_PENDIENTES.md).

### 3.9 Reintentar emails fallidos (sin regenerar PDF)

Si la generación completó pero algunos correos fallaron, reencolar solo el fanout:

```bash
cd /home/admonctrlxm/server && source venv/bin/activate
DATE=$(date +%Y-%m-%d)
python3 -c "
from tasks.anomaly_tasks import send_daily_emails_fanout
send_daily_emails_fanout.delay(
    '${DATE}',
    '📊 Informe Ejecutivo del Sector Eléctrico — ${DATE}',
    'whatsapp_bot/informes/Informe_Ejecutivo_MME_${DATE}.html',
    'whatsapp_bot/informes/Informe_Ejecutivo_MME_${DATE}.pdf',
)
print('Fanout encolado')
"
```

Para forzar reenvío a un destinatario específico, borrar su lock Redis antes:

```bash
redis-cli -n 1 DEL "daily_email_sent_${DATE}_correo@minenergia.gov.co"
```

Logs estructurados de email: buscar `[EMAIL]` en logs Celery. El callback `email_batch_complete` lista destinatarios fallidos.

---

## 4. Umbrales de alerta configurados

> Corregido 2026-09-01: P_NT tenía un solo umbral (8%) documentado, el código real (`domain/services/losses_nt_service.py`, perfil nacional) usa 2 umbrales distintos (`pnt_warn_pct=6.0`, `pnt_crit_pct=10.0`). Los umbrales de embalses también se corrigieron para coincidir con la unificación IDEAM/UNGRD (`core/umbrales_ideam_ungrd.py`, ver `docs/tecnicos/ANALISIS_HIDROLOGIA_SEMAFORO.md` §10) — **distinto** del Índice NE regulatorio de la CREG (compara contra la senda de referencia mensual, no un umbral fijo).

| Indicador | Umbral | Severidad | Acción |
|---|---|---|---|
| CU > 400 COP/kWh | ALERTA | Monitorear | Revisar precio de bolsa |
| CU > 600 COP/kWh | CRÍTICO | Urgente | Posible crisis energética — escalar |
| P_NT > 6% | ALERTA | Monitorear | Revisar metodología o datos fuente |
| P_NT > 10% | CRÍTICO | Urgente | Escalar — pérdidas no técnicas fuera de rango |
| Embalses < 27% | CRÍTICO — RACIONAMIENTO | Urgente | Riesgo de racionamiento (IDEAM) |
| Embalses 27%-40% | ALERTA — NIVEL BAJO | Monitorear | Aumentar vigilancia (IDEAM) |
| Embalses > 90% | ALERTA/CRÍTICO — NIVEL ALTO | Monitorear/Urgente | Riesgo de desbordamiento (UNGRD) |
| Índice NE (CREG, agregado SIN) | vs. senda de referencia mensual, no un % fijo | Variable | Ver `core/umbrales_oficiales.py::clasificar_indice_ne()` — nunca confundir con el umbral de embalses de arriba |
| Datos > 24h sin actualizar | ALERTA | Monitorear | Verificar ETL y XM API |

---

## 5. Logs importantes

> **⚠️ Corrección crítica 2026-09-01**: las rutas `logs/api-access.log` / `logs/api-error.log` de la versión anterior de esta tabla **no existen**. El `portal-api.service` real (verificado en `/etc/systemd/system/portal-api.service`) corre `uvicorn` plano y redirige todo su stdout/stderr fuera del repo, a `/var/log/portal-api.log` — un operador buscando errores en `logs/api-error.log` durante un incidente real no encontraría nada.

| Log | Ubicación real |
|---|---|
| **API (stdout+stderr combinados)** | **`/var/log/portal-api.log`** — fuera del repo, vía `StandardOutput=append:...`/`StandardError=append:...` del systemd unit |
| Dashboard acceso | `/home/admonctrlxm/server/logs/gunicorn_access.log` |
| Dashboard errores | `/home/admonctrlxm/server/logs/gunicorn_error.log` |
| Bot de Telegram | `/home/admonctrlxm/server/whatsapp_bot/logs/telegram_polling.log` / `telegram_polling_error.log` |
| Celery / ETL | `/home/admonctrlxm/server/logs/celery/*.log`, `/home/admonctrlxm/server/logs/etl/*.log` |
| Systemd services | `journalctl -u portal-api -f` / `journalctl -u dashboard-mme -f` / `journalctl -u telegram-polling -f` |

```bash
# Ver errores recientes API (ruta REAL, fuera del repo):
tail -50 /var/log/portal-api.log
# o, equivalente, vía journalctl:
journalctl -u portal-api.service -f

# Ver errores recientes Dashboard:
tail -50 /home/admonctrlxm/server/logs/gunicorn_error.log

# Ver logs de celery en tiempo real:
journalctl -u celery-worker@1 -f

# Buscar errores CRÍTICOS del último día en la API real:
grep -i "CRITICAL\|ERROR" /var/log/portal-api.log | tail -20
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

> Corregido 2026-09-01: la clave real es `"services"`, no `"checks"`, y hay un bloque `predictions` adicional no documentado antes. Ejemplo real capturado hoy:

```json
{
  "status": "healthy",
  "timestamp": "2026-09-01T01:22:12.560775",
  "environment": "production",
  "version": "1.0.0",
  "services": {
    "database": { "status": "healthy", "latency_ms": 215.1, "rows": 10069439 },
    "redis": { "status": "healthy", "latency_ms": 0.2 },
    "xm_api": { "status": "healthy", "circuit_state": "closed", "consecutive_failures": 0, "times_opened": 0 },
    "data_freshness": { "status": "healthy", "last_date": "2027-07-15", "hours_since_update": -7606.6 },
    "predictions": { "status": "healthy", "total": 1877 }
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
  └─→ Telegram Bot : systemd (telegram-polling.service)

Celery Worker + Beat ──→ PostgreSQL :5432
                     ──→ Redis :6379 (cache + broker)
                     ──→ XM API (SIMEM) [con circuit breaker]
```
