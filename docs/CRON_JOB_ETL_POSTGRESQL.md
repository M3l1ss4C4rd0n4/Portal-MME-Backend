# ⏰ Cron Jobs — Portal Energético MME

**Fecha de configuración**: 9 de febrero de 2026  
**Última actualización**: 20 de febrero de 2026  
**Estado**: ✅ **ACTIVO** — 9 entradas crontab operacionales

---

## 📋 Crontab Completo Actual

```bash
# ============================================
# CRONTAB - Portal Energético MME
# Actualizado: 2026-02-19 (dual ArcGIS)
# ============================================

# 1. ETL Transmisión (diario a las 6:30 AM)
30 6 * * * cd /home/admonctrlxm/server && /usr/bin/python3 etl/etl_transmision.py --days 7 --clean >> logs/etl/transmision.log 2>&1

# 2. Auto-start API al reinicio del servidor
@reboot sleep 30 && /home/admonctrlxm/server/api/start_api_daemon.sh >> logs/api-startup.log 2>&1

# 3. Monitoreo y auto-recuperación de la API (cada 5 min)
*/5 * * * * /home/admonctrlxm/server/scripts/monitor_api.sh

# 4. Actualización HORARIA de datos XM en ArcGIS Enterprise (DUAL: Vice_Energia + Adminportal)
0 * * * * /home/admonctrlxm/server/tests/ARGIS/ejecutar_dual.sh xm >> logs/arcgis_dual.log 2>&1

# 5. ETL PostgreSQL — Todas las métricas XM (cada 6 horas: 0:00, 6:00, 12:00, 18:00)
0 */6 * * * cd /home/admonctrlxm/server && /usr/bin/python3 etl/etl_todas_metricas_xm.py --dias 7 >> logs/etl_postgresql_cron.log 2>&1

# 6. Actualización semanal de predicciones energéticas (Domingos 2:00 AM)
0 2 * * 0 /home/admonctrlxm/server/scripts/actualizar_predicciones.sh

# 7. Backup semanal de tabla metrics (Domingos 3:00 AM) — retiene últimos 28 días
0 3 * * 0 pg_dump -U postgres -h localhost -d portal_energetico -t metrics --no-owner -Fc -f backups/database/metrics_$(date +%Y%m%d).dump && find backups/database/ -name "metrics_*.dump" -mtime +28 -delete

# 8. Backfill mensual de métricas Sistema (1ro de cada mes 4:00 AM)
0 4 1 * * cd /home/admonctrlxm/server && /usr/bin/python3 scripts/backfill_sistema_metricas.py --dias 90 >> logs/backfill_mensual.log 2>&1

# 9. Actualización cada 30 min de archivos OneDrive/SharePoint en ArcGIS Enterprise (DUAL)
30 * * * * /home/admonctrlxm/server/tests/ARGIS/ejecutar_dual.sh onedrive >> logs/arcgis_dual.log 2>&1
```

---

## 📅 Cronograma Completo

| # | Frecuencia | Hora | Script | Descripción | Log |
|---|-----------|------|--------|-------------|-----|
| 1 | Diaria | 6:30 AM | `etl/etl_transmision.py` | Líneas de transmisión SIMEN (7 días, limpia duplicados) | `logs/etl/transmision.log` |
| 2 | @reboot | 30s post-boot | `api/start_api_daemon.sh` | Inicia API FastAPI automáticamente | `logs/api-startup.log` |
| 3 | Cada 5 min | `*/5 * * * *` | `scripts/monitor_api.sh` | Monitoreo + auto-recuperación API | `logs/api-monitor.log` |
| 4 | Cada hora | `:00` | `ejecutar_dual.sh xm` | ArcGIS Enterprise — datos XM (dual) | `logs/arcgis_dual.log` |
| 5 | **Cada 6h** | 0/6/12/18 | **`etl_todas_metricas_xm.py`** | **ETL PostgreSQL — todas las métricas** ⭐ | `logs/etl_postgresql_cron.log` |
| 6 | Semanal | Dom 2:00 AM | `actualizar_predicciones.sh` | Reentrenamiento predicciones ML | — |
| 7 | Semanal | Dom 3:00 AM | `pg_dump` + `find` | Backup tabla `metrics` (retención 28 días) | `logs/backup_metrics.log` |
| 8 | Mensual | 1ro 4:00 AM | `backfill_sistema_metricas.py` | Relleno de huecos métricas Sistema (90 días) | `logs/backfill_mensual.log` |
| 9 | Cada 30 min | `:30` | `ejecutar_dual.sh onedrive` | ArcGIS Enterprise — OneDrive/SharePoint (dual) | `logs/arcgis_dual.log` |

---

## ⭐ ETL Principal — Detalle (`etl_todas_metricas_xm.py`)

### Configuración actual

| Parámetro | Valor | Nota |
|-----------|-------|------|
| **Frecuencia** | Cada 6 horas | `0 */6 * * *` — 0:00, 6:00, 12:00, 18:00 |
| **Script** | `etl/etl_todas_metricas_xm.py` | ETL principal |
| **Días** | `--dias 7` | Descarga últimos 7 días |
| **Validación** | Pre-insert con `etl_rules.py` | 69 reglas centralizadas |

### ¿Qué hace?

1. Se conecta a la API de XM (servicio web de Colombia)
2. Descarga datos de ~193 métricas
3. Valida con reglas centralizadas (`etl/etl_rules.py`)
4. Inserta/actualiza registros en PostgreSQL
5. Genera log con resultado de cada métrica

### Rendimiento típico

| Modo | Duración | Registros |
|------|----------|-----------|
| Normal (`--dias 7`) | 3-5 min | ~10,000 - 25,000 |
| Historial (`--dias 30`) | 10-15 min | ~100,000 - 150,000 |
| Backfill (`--dias 90`) | 20-30 min | ~300,000+ |

---

## 🔍 Verificación y Monitoreo

### Ver cron jobs activos
```bash
crontab -l
```

### Ver log ETL principal en tiempo real
```bash
tail -f /home/admonctrlxm/server/logs/etl_postgresql_cron.log
```

### Buscar errores / bloqueos de validación
```bash
grep -E '🛑|ERROR UNIDAD|Inserción BLOQUEADA' /home/admonctrlxm/server/logs/etl_postgresql_cron.log | tail -20
```

### Verificar última fecha en BD
```bash
psql -U postgres -h localhost -d portal_energetico -c "SELECT MAX(fecha::date) FROM metrics WHERE metrica = 'Gene';"
```

### Verificar que cron está corriendo
```bash
systemctl status cron
grep CRON /var/log/syslog | tail -20
```

---

## ⚡ Ejecución Manual

```bash
cd /home/admonctrlxm/server

# Normal (últimos 7 días)
python3 etl/etl_todas_metricas_xm.py --dias 7

# Solo una métrica
python3 etl/etl_todas_metricas_xm.py --dias 7 --metrica Gene

# Solo una sección
python3 etl/etl_todas_metricas_xm.py --dias 7 --seccion Generación

# Backfill largo
python3 etl/etl_todas_metricas_xm.py --dias 30

# Transmisión
python3 etl/etl_transmision.py --days 7 --clean

# Diagnóstico post-ETL (solo lectura)
python3 scripts/diagnostico_metricas_etl.py --dias 7
```

---

## 🚨 Troubleshooting

### El ETL no se ejecutó
1. `systemctl status cron` — verificar servicio cron activo
2. `grep CRON /var/log/syslog | tail -20` — ver logs del sistema
3. `ls -l etl/etl_todas_metricas_xm.py` — permisos OK

### El ETL falla
1. `tail -100 logs/etl_postgresql_cron.log` — ver log
2. `python3 etl/etl_todas_metricas_xm.py --dias 7` — ejecutar manual
3. `curl -I https://servapibi.xm.com.co/hourly` — API XM accesible
4. `psql -U postgres -h localhost -d portal_energetico -c "SELECT 1"` — BD accesible

### No hay datos nuevos
- XM normalmente demora 1-2 días en publicar datos
- Buscar en log: "⚠️ Sin datos disponibles"

---

## 📁 Archivos Relacionados

| Archivo | Propósito |
|---------|-----------|
| `etl/etl_todas_metricas_xm.py` | ETL principal PostgreSQL |
| `etl/etl_transmision.py` | ETL líneas de transmisión |
| `etl/etl_rules.py` | Reglas centralizadas (69 métricas) |
| `scripts/monitor_api.sh` | Monitor y auto-recuperación API |
| `scripts/actualizar_predicciones.sh` | Reentrenamiento predicciones ML |
| `scripts/backfill_sistema_metricas.py` | Backfill mensual |
| `tests/ARGIS/ejecutar_dual.sh` | ArcGIS Enterprise dual (xm/onedrive) |
| `api/start_api_daemon.sh` | Inicio automático API |

---

## 📝 Historial de Cambios

| Fecha | Cambio |
|-------|--------|
| 2026-02-09 | Cron configurado: ETL a las 7:00 AM, `--dias 3` |
| 2026-02-12 | ETL cambiado a cada 6h (`0 */6`), `--dias 7`. Diagnóstico post-ETL añadido |
| 2026-02-19 | Dual ArcGIS (xm + onedrive), backup semanal, backfill mensual, predicciones semanales |
| 2026-02-20 | Documentación reescrita v2.0 — crontab completo (9 entradas) |

---

## ✅ Checklist de Mantenimiento

### Automático (sin intervención)
- [x] ETL PostgreSQL cada 6 horas
- [x] ETL Transmisión diario 6:30 AM
- [x] Monitoreo API cada 5 min
- [x] ArcGIS XM horario + OneDrive cada 30 min
- [x] Predicciones semanales (Dom 2:00 AM)
- [x] Backup semanal (Dom 3:00 AM, retención 28 días)
- [x] Backfill mensual (1ro cada mes 4:00 AM)

### Semanal (manual recomendado)
- [ ] Revisar logs: `tail -100 logs/etl_postgresql_cron.log`
- [ ] Diagnóstico: `python3 scripts/diagnostico_metricas_etl.py --dias 7`
- [ ] Backups: `ls -lh backups/database/metrics_*.dump`
- [ ] Disco: `df -h /home/admonctrlxm`

### Mensual
- [ ] Rendimiento ETL (duración)
- [ ] Limpiar logs: `find logs/ -name "*.log" -mtime +60 -delete`
- [ ] Cobertura reglas: `python3 scripts/diagnostico_conversores_unidades.py`

---

**Última actualización**: 2026-02-20  
**Estado**: ✅ Operacional — 9 cron jobs activos
