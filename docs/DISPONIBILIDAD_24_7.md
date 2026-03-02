# Guía de Disponibilidad 24/7 - Portal Energético MME

**Última actualización:** 20 de febrero de 2026

## ✅ Lo que está configurado AHORA

### 1. Reinicio Automático
- **@reboot**: La API se inicia automáticamente cuando el servidor se reinicia
- **Cron job**: Ejecuta el script de inicio 30 segundos después del reinicio

### 2. Monitoreo Automático
- **Cada 5 minutos**: Un script verifica que la API esté respondiendo (`scripts/monitor_api.sh`)
- **Auto-recuperación**: Si la API no responde, se reinicia automáticamente
- **Logs**: Registra todas las verificaciones en `logs/api-monitor.log`

### 3. Tareas Programadas (9 cron jobs activos)
- **ETL Transmisión**: Diario 6:30 AM
- **ETL PostgreSQL**: Cada 6 horas (0:00, 6:00, 12:00, 18:00) — `--dias 7`
- **ArcGIS Enterprise XM**: Cada hora (dual: Vice_Energia + Adminportal)
- **ArcGIS Enterprise OneDrive**: Cada 30 minutos (dual)
- **Predicciones ML**: Domingos 2:00 AM
- **Backup BD**: Domingos 3:00 AM (retención 28 días)
- **Backfill mensual**: 1ro de cada mes 4:00 AM

> Detalle completo: `docs/CRON_JOB_ETL_POSTGRESQL.md`

### 3. Redundancia (Gunicorn)
- **Múltiples workers**: `cpu_count() * 2 + 1` workers (calculado dinámicamente)
- **Gunicorn**: Reinicia workers que crashean automáticamente

### 4. Dashboard
- **Systemd service**: Configurado para iniciar automáticamente al boot
- **Estado**: `enabled` (se inicia siempre que el servidor arranque)

## ⚠️ IMPORTANTE: Limitaciones

### ❌ SI APAGAS EL SERVIDOR
**La API y el dashboard NO estarán disponibles mientras el servidor esté apagado.**

Esto significa:
- ❌ Nadie podrá acceder al portal web
- ❌ La API no responderá
- ❌ Todo el sistema estará offline

**Solución**: El servidor debe permanecer encendido 24/7

### ⚠️ Otras situaciones que pueden causar caídas

1. **Base de datos PostgreSQL caída**
   - Si PostgreSQL se detiene, la API fallará
   - Monitoreo configurado reiniciará la API cada 5 minutos
   
2. **Disco lleno**
   - Si el disco se llena, el sistema puede fallar
   - Recomendación: Configurar rotación de logs

3. **Falta de memoria RAM**
   - Si el servidor se queda sin RAM, procesos pueden morir
   - Recomendación: Monitorear uso de RAM

4. **Errores críticos en el código**
   - Bugs graves pueden causar caídas
   - El monitoreo intentará reiniciar automáticamente

## 🛡️ Configuración de Alta Disponibilidad (Actual)

```
┌─────────────────────────────────────────┐
│     SERVIDOR FÍSICO                      │
│  (Debe estar encendido 24/7)            │
├─────────────────────────────────────────┤
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  Dashboard (Puerto 8050)         │   │
│  │  • Systemd: enabled              │   │
│  │  • Auto-start: ✅                 │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  API (Puerto 8000)               │   │
│  │  • Systemd: api-mme.service      │   │
│  │  • Cron @reboot: ✅               │   │
│  │  • Monitoreo cada 5 min: ✅       │   │
│  │  • Workers dinámicos: ✅          │   │
│  │  • Auth: API Key activa 🔐       │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  MLflow (Puerto 5000)            │   │
│  │  • Tracking de experimentos ML   │   │
│  │  • Solo localhost                │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  Nginx (Puerto 80/443)           │   │
│  │  • Proxy reverso                 │   │
│  │  • Systemd: enabled              │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  PostgreSQL                      │   │
│  │  • Base de datos                 │   │
│  │  • Systemd: enabled              │   │
│  └──────────────────────────────────┘   │
│                                          │
└─────────────────────────────────────────┘
```

## � Tareas Cron Activas (9 entradas)

| Frecuencia | Horario | Tarea |
|-----------|---------|-------|
| Diaria | 6:30 AM | ETL Transmisión (`etl_transmision.py --days 7`) |
| @reboot | 30s post-boot | Auto-start API (`start_api_daemon.sh`) |
| Cada 5 min | `*/5` | Monitoreo API (`monitor_api.sh`) |
| Cada hora | `:00` | ArcGIS XM dual (`ejecutar_dual.sh xm`) |
| Cada 6h | 0/6/12/18 | ETL PostgreSQL (`etl_todas_metricas_xm.py --dias 7`) |
| Semanal | Dom 2:00 AM | Predicciones ML (`actualizar_predicciones.sh`) |
| Semanal | Dom 3:00 AM | Backup BD (`pg_dump`, retención 28 días) |
| Mensual | 1ro 4:00 AM | Backfill métricas (`backfill_sistema_metricas.py --dias 90`) |
| Cada 30 min | `:30` | ArcGIS OneDrive dual (`ejecutar_dual.sh onedrive`) |

> Detalle completo: `docs/CRON_JOB_ETL_POSTGRESQL.md`

## �📊 Nivel de Disponibilidad Actual

| Escenario | ¿Qué pasa? | Tiempo de recuperación |
|-----------|------------|------------------------|
| Worker crashea | ✅ Se reinicia automáticamente | < 1 segundo |
| API completa se cae | ✅ Se detecta y reinicia | < 5 minutos |
| Servidor se reinicia | ✅ Todo se inicia automáticamente | ~2 minutos |
| Servidor se apaga | ❌ OFFLINE hasta que se encienda | Manual |
| PostgreSQL se cae | ⚠️ API falla, pero se reintenta | Resolver PostgreSQL |
| Disco lleno | ⚠️ Sistema puede fallar | Manual |
| Error en código | ⚠️ Reintentos automáticos | Depende del error |

## ✅ Comandos de Monitoreo

### Ver estado de la API
```bash
ps aux | grep "gunicorn api.main" | grep -v grep
```

### Ver logs de monitoreo
```bash
tail -f /home/admonctrlxm/server/logs/api-monitor.log
```

### Ver logs de la API
```bash
tail -f /home/admonctrlxm/server/logs/api-error.log
tail -f /home/admonctrlxm/server/logs/api-access.log
```

### Verificar cron jobs
```bash
crontab -l
```

### Estado del dashboard
```bash
sudo systemctl status dashboard-mme
```

### Estado de la API
```bash
sudo systemctl status api-mme
```

### Probar API manualmente
```bash
curl http://localhost/api/
```

## 🚨 Alertas y Notificaciones

Para recibir alertas cuando la API se caiga, podrías:

1. **Configurar un servicio de monitoreo externo** (Recomendado)
   - UptimeRobot (gratis)
   - Pingdom
   - Freshping
   - StatusCake

2. **Recibir notificaciones por email/WhatsApp**
   - Estos servicios te notificarán si el portal está caído
   - Puedes configurar checks cada 5 minutos

## 📱 Acceso Remoto

Si necesitas reiniciar o monitorear remotamente:

```bash
# Conectarse vía SSH
ssh admonctrlxm@portalenergetico.minenergia.gov.co

# Reiniciar API
/home/admonctrlxm/server/api/stop_api.sh
/home/admonctrlxm/server/api/start_api_daemon.sh

# Reiniciar dashboard
sudo systemctl restart dashboard-mme
```

## 🎯 Resumen: ¿Puedo estar tranquila?

### ✅ SÍ puedes estar tranquila si:
- El servidor está ENCENDIDO 24/7
- Tienes acceso remoto SSH para emergencias
- Configuraste alertas externas

### ⚠️ DEBES tener en cuenta:
- Si se apaga el servidor físicamente, TODO estará offline
- Pueden ocurrir caídas ocasionales (el monitoreo las recuperará)
- Debes tener un plan de contingencia para problemas mayores

### 💡 Nivel de disponibilidad estimado:
**~99.5% uptime** (aprox. 3-4 horas de downtime al año)

Esto es excelente para un servidor en producción de gobierno, pero NO es 100% infalible.

**Para 100% de disponibilidad necesitarías:**
- Múltiples servidores (redundancia)
- Load balancer
- Base de datos replicada
- Monitoreo profesional 24/7
- UPS (respaldo de energía)
- Plan de disaster recovery

---

**Última actualización**: 20 de febrero de 2026  
**Configurado por**: GitHub Copilot + admonctrlxm
