# ⏰ Cron Job ETL PostgreSQL - Configuración

**Fecha de configuración**: 9 de febrero de 2026  
**Estado**: ✅ **ACTIVO**

---

## 📋 Configuración Actual

### Línea de Crontab

```bash
0 7 * * * cd /home/admonctrlxm/server && /usr/bin/python3 etl/etl_todas_metricas_xm.py --dias 3 >> /home/admonctrlxm/server/logs/etl_postgresql_cron.log 2>&1
```

### Parámetros

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| **Frecuencia** | Diaria | Se ejecuta todos los días |
| **Hora** | 7:00 AM | Después del ETL de transmisión (6:30 AM) |
| **Script** | `etl/etl_todas_metricas_xm.py` | ETL principal de PostgreSQL |
| **Días** | `--dias 3` | Descarga últimos 3 días de datos |
| **Log** | `/home/admonctrlxm/server/logs/etl_postgresql_cron.log` | Archivo de log |

---

## 🎯 ¿Qué hace?

El cron job ejecuta diariamente el ETL que:

1. **Se conecta** a la API de XM (servicio web de Colombia)
2. **Descarga** datos de aproximadamente **193 métricas** diferentes
3. **Procesa** y transforma los datos
4. **Inserta/actualiza** registros en PostgreSQL
5. **Genera log** con el resultado de la ejecución

### Métricas Descargadas

El ETL descarga automáticamente:

- **Generación**: Gene, GeneFueraMerito, GeneIdea, CapEfecNeta, etc.
- **Demanda**: DemaCome, DemaReal, DemaComeReg, etc.
- **Precios**: PrecBolsNaci, PrecEsca, PrecPromCont, etc.
- **Hidrología**: AporEner, VoluUtilDiarEner, PorcVoluUtilDiar, etc.
- **Transacciones**: CompBolsNaciEner, VentBolsNaciEner, etc.
- **Emisiones**: EmisionesCO2, EmisionesCH4, EmisionesN2O, etc.
- Y **100+ métricas** más

---

## 📅 Cronograma Completo de ETLs

| Hora | Script | Descripción |
|------|--------|-------------|
| 6:30 AM | `etl/etl_transmision.py` | Líneas de transmisión |
| **7:00 AM** | **`etl/etl_todas_metricas_xm.py`** | **PostgreSQL (TODAS las métricas)** ⭐ |
| Cada hora | `tests/ARGIS/actualizar_datos_xm_online.py` | ArcGIS Enterprise (visualizaciones) |
| Cada 5 min | `scripts/monitor_api.sh` | Monitoreo y auto-recuperación API |

---

## 🔍 Verificación y Monitoreo

### Ver el log en tiempo real

```bash
tail -f /home/admonctrlxm/server/logs/etl_postgresql_cron.log
```

### Ver últimas 50 líneas del log

```bash
tail -50 /home/admonctrlxm/server/logs/etl_postgresql_cron.log
```

### Ver últimas 100 líneas del log

```bash
tail -100 /home/admonctrlxm/server/logs/etl_postgresql_cron.log
```

### Ver todos los cron jobs activos

```bash
crontab -l
```

### Verificar última fecha en BD

```bash
psql -U tu_usuario -d tu_database -c "SELECT MAX(fecha::date) FROM metrics WHERE metrica = 'Gene';"
```

O con Python:

```bash
cd /home/admonctrlxm/server
python3 verificar_fechas_bd.py
```

---

## ⚡ Ejecución Manual

Si necesitas ejecutar el ETL manualmente (sin esperar al cron job):

```bash
cd /home/admonctrlxm/server
python3 etl/etl_todas_metricas_xm.py --dias 3
```

### Opciones del ETL

```bash
# Ayuda
python3 etl/etl_todas_metricas_xm.py --help

# Cargar solo métricas nuevas
python3 etl/etl_todas_metricas_xm.py --dias 10 --solo-nuevas

# Cargar solo una métrica específica
python3 etl/etl_todas_metricas_xm.py --dias 7 --metrica Gene

# Cargar solo una sección
python3 etl/etl_todas_metricas_xm.py --dias 7 --seccion Generación
```

---

## 📧 Notificaciones por Email (Opcional)

Si quieres recibir emails cuando el ETL falle:

1. Editar crontab:
   ```bash
   crontab -e
   ```

2. Cambiar la línea a:
   ```bash
   0 7 * * * cd /home/admonctrlxm/server && \
   /usr/bin/python3 etl/etl_todas_metricas_xm.py --dias 3 \
   >> /home/admonctrlxm/server/logs/etl_postgresql_cron.log 2>&1 || \
   echo "ETL PostgreSQL falló el $(date)" | mail -s "Error ETL PostgreSQL" admin@minenergia.gov.co
   ```

---

## 🔧 Modificar la Configuración

### Cambiar la hora de ejecución

Por ejemplo, para ejecutar a las 8:00 AM en lugar de 7:00 AM:

```bash
crontab -e
# Cambiar: 0 7 * * * ...
# Por:     0 8 * * * ...
```

### Cambiar el número de días

Para descargar más días (por ejemplo, 7 días):

```bash
crontab -e
# Cambiar: --dias 3
# Por:     --dias 7
```

### Ejecutar dos veces al día

Para ejecutar a las 7:00 AM y 7:00 PM:

```bash
crontab -e
# Agregar segunda línea:
0 7,19 * * * cd /home/admonctrlxm/server && /usr/bin/python3 etl/etl_todas_metricas_xm.py --dias 3 >> /home/admonctrlxm/server/logs/etl_postgresql_cron.log 2>&1
```

---

## 🚨 Troubleshooting

### El ETL no se ejecutó

1. **Verificar que cron está activo**:
   ```bash
   systemctl status cron
   ```

2. **Ver logs del sistema**:
   ```bash
   grep CRON /var/log/syslog | tail -20
   ```

3. **Verificar permisos del script**:
   ```bash
   ls -l /home/admonctrlxm/server/etl/etl_todas_metricas_xm.py
   chmod +x /home/admonctrlxm/server/etl/etl_todas_metricas_xm.py
   ```

### El ETL falla

1. **Ver el log completo**:
   ```bash
   cat /home/admonctrlxm/server/logs/etl_postgresql_cron.log
   ```

2. **Ejecutar manualmente para ver el error**:
   ```bash
   cd /home/admonctrlxm/server
   python3 etl/etl_todas_metricas_xm.py --dias 3
   ```

3. **Verificar conexión a la API de XM**:
   ```bash
   curl -I https://servapibi.xm.com.co/hourly
   ```

4. **Verificar conexión a PostgreSQL**:
   ```bash
   psql -U tu_usuario -d tu_database -c "SELECT 1"
   ```

### No hay datos nuevos

Si el ETL se ejecuta pero no carga datos nuevos:

- **Causa**: XM no ha publicado datos aún (normal, demora 1-2 días)
- **Verificar**: El log dirá "⚠️ Sin datos disponibles"
- **Solución**: Esperar a que XM publique los datos

---

## 📊 Métricas de Rendimiento

### Ejecución Típica (últimos 3 días)

- **Duración**: 3-4 minutos
- **Métricas procesadas**: ~193
- **Métricas exitosas**: ~155
- **Registros insertados**: ~10,000 - 20,000
- **Sin datos**: ~38 métricas (normal)

### Ejecución Completa (últimos 10 días)

- **Duración**: 10-15 minutos
- **Registros insertados**: ~100,000 - 150,000

---

## 📁 Archivos Relacionados

- **Script ETL**: `/home/admonctrlxm/server/etl/etl_todas_metricas_xm.py`
- **Log del cron**: `/home/admonctrlxm/server/logs/etl_postgresql_cron.log`
- **Verificación BD**: `/home/admonctrlxm/server/verificar_fechas_bd.py`
- **Crontab backup**: `/tmp/crontab_backup_*.txt`

---

## 📝 Historial de Cambios

| Fecha | Cambio | Responsable |
|-------|--------|-------------|
| 2026-02-09 | Cron job configurado inicialmente a las 7:00 AM, --dias 3 | GitHub Copilot |

---

## ✅ Checklist de Mantenimiento

### Diario (Automático)
- [x] ETL se ejecuta a las 7:00 AM
- [x] Log se genera correctamente
- [x] Datos se insertan en PostgreSQL

### Semanal (Manual)
- [ ] Revisar logs para detectar errores: `tail -100 /home/admonctrlxm/server/logs/etl_postgresql_cron.log`
- [ ] Verificar última fecha en BD: `python3 verificar_fechas_bd.py`
- [ ] Revisar espacio en disco: `df -h /home/admonctrlxm/server/logs`

### Mensual (Manual)
- [ ] Limpiar logs antiguos: `find /home/admonctrlxm/server/logs -name "*.log" -mtime +30 -delete`
- [ ] Verificar rendimiento del ETL (duración)
- [ ] Actualizar documentación si hay cambios

---

**Última actualización**: 2026-02-09 13:52  
**Estado**: ✅ Operacional  
**Próxima ejecución**: 2026-02-10 07:00 AM
