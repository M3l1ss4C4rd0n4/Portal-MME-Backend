# ⏰ Cron Jobs — Portal Energético MME

**Última actualización de este documento**: 2026-09-01, reescrito directamente contra `crontab -l` real (el documento anterior decía "7 entradas" en el encabezado y "9 cron jobs" en el pie, ninguno de los dos correcto — el crontab real tiene **31 entradas**).

**Fuente de verdad**: `crontab -l` (usuario `admonctrlxm`, el mismo que corre `portal-api.service`). Este documento es un snapshot legible de esa salida — si difieren, `crontab -l` manda.

> Nota de arquitectura: esto es el cron del **sistema operativo** — no confundir con **Celery Beat** (`server/tasks/__init__.py::beat_schedule`), un scheduler completamente distinto que corre dentro de `celery-beat.service` y programa tareas como el sanador de vistas de la ontología, diagnósticos IA de HomeSlider, vigilancia normativa CREG, etc. Ambos coexisten en este servidor; ver `RUNBOOK_PRODUCCION.md` §2 para el detalle de Celery Beat.

---

## 📋 Crontab completo (31 entradas)

### ETL núcleo de XM

| Horario | Script | Descripción | Log |
|---|---|---|---|
| Diario 6:30 AM | `etl/etl_transmision.py --days 7 --clean` | Líneas de transmisión SIMEN | `logs/etl/transmision.log` |
| Cada 6h (0:00/0:30, 6:00/6:30, 12:00/12:30, 18:00/18:30) | `etl/etl_todas_metricas_xm.py --dias 7` | ETL principal — todas las métricas XM (~193 códigos) | `logs/etl_postgresql_cron.log` |
| Cada 3 días 2:30 AM | `scripts/actualizar_predicciones.sh` | Reentrenamiento de predicciones ML (Prophet+SARIMAX) | — |
| Diario 22:00 | `scripts/monitor_predictions_quality.py` | Verifica predicciones vs. datos reales ya conocidos (MAPE ex-post), envía alertas de drift | `logs/etl/quality_monitor.log` |
| Diario 12:30 PM | `etl/etl_despacho_diario.py` | Disponibilidad de plantas + precio predespacho ideal | `logs/etl/despacho_diario_cron.log` |
| Diario 5:20 AM | `etl/etl_condicion_riesgo.py` | Condición del Estatuto de Riesgo de Desabastecimiento (SIMEM) | `logs/etl/condicion_riesgo_cron.log` |
| Diario 10:30 AM | `etl/etl_senda_referencia.py --pdf-diario` | Senda de Referencia CREG 209/2020, extraída del informe diario de XM | `logs/etl/senda_referencia_pdf_cron.log` |

### ETL de métricas derivadas (leen de `metrics`, sin llamar a la API de XM)

| Horario | Script | Descripción |
|---|---|---|
| Cada 6h, min 35 | `etl/etl_commercial_metrics.py` | Métricas comerciales, ventana móvil 15 días |
| Cada 6h, min 40 | `etl/etl_restriction_metrics.py` | Métricas de restricciones, ventana móvil 15 días |
| Cada 6h, min 45 | `etl/etl_loss_metrics.py` | Métricas de pérdidas, ventana móvil 15 días |
| Cada 6h, min 35 | `etl/etl_xm_to_postgres.py` | `metrics_hourly` incremental, ventana móvil 10 días |
| Cada 6h, min 50 | `etl/etl_losses_detailed.py` | Pérdidas no técnicas (PNT) detallado, incremental |
| Cada 6h (0,30 0,6,12,18) | `etl/etl_anomalies_pnt.py` | Detección de anomalías PNT vía Isolation Forest → tabla `anomalies` |

### Clima e índices climáticos (mensuales — alineados a la fecha de publicación real de cada fuente)

| Horario | Script | Nota |
|---|---|---|
| Diario 5:00 AM | `etl/etl_nasa_power.py --dias 10` | Irradiancia solar satelital (NASA POWER) |
| Diario 5:10 AM | `etl/etl_nasa_power.py --dias 10 --modo hidro` | Precipitación de 4 cuencas hidrológicas |
| Día 13, 2:00 AM | `etl/etl_oni.py` → luego `actualizar_predicciones.sh` | NOAA publica ONI ~día 9-12 del mes siguiente; se reentrena tras actualizar |
| Día 16, 3:00 AM | `etl/etl_pdo_soi.py` → luego `actualizar_predicciones.sh` | NOAA publica PDO+SOI ~día 12-15; se reentrena tras actualizar |
| Día 20, 3:00 AM | `etl/etl_gmst.py` → luego `actualizar_predicciones.sh` | NASA GISTEMP publica con ~6-8 semanas de retraso; se reentrena tras actualizar |
| Domingos 3:30 AM | `etl/etl_ideam.py --dias 10` | Datos climatológicos IDEAM, semanal |
| Domingos 6:30 AM | `etl/etl_commodities_larepublica.py` | WTI/BRENT histórico diario, para el slider de Hidrocarburos |

### SharePoint (informes/Excels del ministerio)

| Horario | Script | Descripción |
|---|---|---|
| Diario 4:02 AM | `etl/etl_sharepoint_sync.py` | Sincroniza 8 Excels de SharePoint → Postgres (evita colisión con el watcher de las 4:00) |
| Cada 5 min | `etl/etl_sharepoint_watcher.py` | Verifica cambios en SharePoint |
| Cada 15 min | `scripts/monitor_sp_watcher.sh` | Healthcheck del watcher — alerta y auto-recupera si lleva >30 min sin completar un ciclo (agregado tras el incidente 2026-08-11→08-19: `msal` sin timeout dejó el proceso colgado 8 días, ver `docs/tecnicos/` para el post-mortem si existe) |
| Cada 5 min | `etl/etl_informes_diarios_watcher.py` | Watcher de informes diarios |

### Ontología, mantenimiento y limpieza

| Horario | Script | Descripción |
|---|---|---|
| Diario 4:30 AM | `scripts/ontologia/refresh_ontologia.py` | Pipeline completo de la ontología: re-resuelve alias geografía/empresa/proyecto, reindexa RAG, refresca las 9 vistas materializadas — corre después del sync de SharePoint (4:02 AM) para reflejar los datos del día |
| Domingos 3:00 AM | `pg_dump` de la tabla `metrics` | Backup semanal, retiene últimos 28 días (`find ... -mtime +28 -delete`) |
| 1ro de cada mes 4:00 AM | `scripts/backfill_sistema_metricas.py --dias 90` | Backfill mensual de métricas Sistema |
| Domingos 3:15 AM | `find ... -mtime +30 -delete` | Limpia informes ejecutivos diarios (`whatsapp_bot/informes/Informe_Ejecutivo_MME_*.pdf`) con más de 30 días |
| Domingos 4:00 AM | `scripts/cleanup_predictions_history.py` | Limpia `predictions_history`, retención 120 días |

### Infraestructura

| Horario | Script | Descripción |
|---|---|---|
| Cada 5 min | `scripts/monitor_api.sh` | Monitoreo y auto-recuperación de `portal-api.service` |
| `@reboot` | `sleep 20 && pm2 resurrect --update-env` | Restaura los procesos PM2 tras un reinicio del servidor — **no** `api/start_api_daemon.sh` (ese script ya no se usa; corregido en esta revisión) |

---

## ⭐ ETL principal — detalle (`etl_todas_metricas_xm.py`)

| Parámetro | Valor |
|---|---|
| Frecuencia | Cada 6 horas, en `:00` y `:30` (`0,30 0,6,12,18 * * *`) |
| Script | `etl/etl_todas_metricas_xm.py` |
| Ventana | `--dias 7` |
| Validación | Pre-insert con `etl/etl_rules.py` |

### ¿Qué hace?

1. Se conecta a la API de XM.
2. Descarga datos de ~193 métricas.
3. Valida con reglas centralizadas (`etl/etl_rules.py`).
4. Inserta/actualiza registros en PostgreSQL.
5. Genera log con el resultado de cada métrica.

---

## 🔍 Verificación y monitoreo

```bash
# Ver cron jobs activos (fuente de verdad real)
crontab -l

# Log ETL principal en tiempo real
tail -f /home/admonctrlxm/server/logs/etl_postgresql_cron.log

# Buscar errores / bloqueos de validación
grep -E '🛑|ERROR UNIDAD|Inserción BLOQUEADA' /home/admonctrlxm/server/logs/etl_postgresql_cron.log | tail -20

# Verificar última fecha en BD
psql -U postgres -h localhost -d portal_energetico -c "SELECT MAX(fecha::date) FROM metrics WHERE metrica = 'Gene';"

# Verificar que cron está corriendo
systemctl status cron
grep CRON /var/log/syslog | tail -20
```

## ⚡ Ejecución manual

```bash
cd /home/admonctrlxm/server

python3 etl/etl_todas_metricas_xm.py --dias 7                    # normal
python3 etl/etl_todas_metricas_xm.py --dias 7 --metrica Gene     # una métrica
python3 etl/etl_todas_metricas_xm.py --dias 7 --seccion Generación
python3 etl/etl_todas_metricas_xm.py --dias 30                   # backfill largo
python3 etl/etl_transmision.py --days 7 --clean
python3 scripts/diagnostico_metricas_etl.py --dias 7             # diagnóstico, solo lectura
```

## 🚨 Troubleshooting

**El ETL no se ejecutó**
1. `systemctl status cron`
2. `grep CRON /var/log/syslog | tail -20`
3. `ls -l etl/etl_todas_metricas_xm.py` — permisos OK

**El ETL falla**
1. `tail -100 logs/etl_postgresql_cron.log`
2. `python3 etl/etl_todas_metricas_xm.py --dias 7` — ejecutar manual
3. `curl -I https://servapibi.xm.com.co/hourly` — API XM accesible
4. `psql -U postgres -h localhost -d portal_energetico -c "SELECT 1"` — BD accesible

**No hay datos nuevos**
- XM normalmente demora 1-2 días en publicar datos.
- Buscar en el log: `"⚠️ Sin datos disponibles"`.

**El watcher de SharePoint quedó colgado**
- Ver `scripts/monitor_sp_watcher.sh` (cada 15 min) — debería auto-recuperarlo. Si no, revisar `logs/sp_watcher.log` y el incidente de referencia (`msal` sin timeout, 2026-08).

## 📁 Archivos relacionados

| Archivo | Propósito |
|---|---|
| `etl/etl_todas_metricas_xm.py` | ETL principal PostgreSQL |
| `etl/etl_transmision.py` | ETL líneas de transmisión |
| `etl/etl_rules.py` | Reglas de validación centralizadas |
| `scripts/monitor_api.sh` | Monitor y auto-recuperación de `portal-api.service` |
| `scripts/monitor_sp_watcher.sh` | Healthcheck del watcher de SharePoint |
| `scripts/actualizar_predicciones.sh` | Reentrenamiento de predicciones ML |
| `scripts/backfill_sistema_metricas.py` | Backfill mensual |
| `scripts/ontologia/refresh_ontologia.py` | Pipeline diario de la ontología |
| `scripts/monitor_predictions_quality.py` | Verificación de calidad de predicciones (MAPE ex-post) |

## 📝 Historial de cambios relevantes

| Fecha | Cambio |
|---|---|
| 2026-02-09 | Cron configurado inicialmente |
| 2026-02-20 | Documentación v2.0 |
| 2026-03-21 | Fix de la entrada de NASA hidro |
| 2026-08-11→08-19 | Incidente: watcher de SharePoint colgado 8 días (`msal` sin timeout) — agregado `scripts/monitor_sp_watcher.sh` cada 15 min como self-healing |
| 2026-08-25 | Retirada la integración ArcGIS Enterprise (llevaba meses fallando con `ModuleNotFoundError: pandas`, sin uso real) |
| 2026-09-01 | Documento reescrito completo contra `crontab -l` real: 31 entradas (antes documentaba 7-9), corregido que `@reboot` usa `pm2 resurrect`, no `start_api_daemon.sh` |

---

**Estado real verificado**: ✅ 31 entradas activas en `crontab -l` (2026-09-01). Este documento es un snapshot legible — ante cualquier duda, `crontab -l` es la fuente de verdad.
