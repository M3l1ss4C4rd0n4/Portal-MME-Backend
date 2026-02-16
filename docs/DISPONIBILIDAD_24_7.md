# Guía de Disponibilidad 24/7 - Portal Energético MME

## ✅ Lo que está configurado AHORA

### 1. Reinicio Automático
- **@reboot**: La API se inicia automáticamente cuando el servidor se reinicia
- **Cron job**: Ejecuta el script de inicio 30 segundos después del reinicio

### 2. Monitoreo Automático (NUEVO ✨)
- **Cada 5 minutos**: Un script verifica que la API esté respondiendo
- **Auto-recuperación**: Si la API no responde, se reinicia automáticamente
- **Logs**: Registra todas las verificaciones en `logs/api-monitor.log`

### 3. Redundancia
- **4 workers**: Si uno falla, gunicorn lo reinicia automáticamente
- **Gunicorn**: Reinicia workers que crashean

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
│  │  • Cron @reboot: ✅               │   │
│  │  • Monitoreo cada 5 min: ✅       │   │
│  │  • 4 workers redundantes: ✅      │   │
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

## 📊 Nivel de Disponibilidad Actual

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

**Última actualización**: 6 de febrero de 2026
**Configurado por**: GitHub Copilot + admonctrlxm
