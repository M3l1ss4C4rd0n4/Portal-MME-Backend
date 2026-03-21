# 🔧 Guía de Troubleshooting - Portal Energético MME

**Fecha:** Marzo 2026  
**Versión:** 1.0

Guía rápida para diagnosticar y resolver problemas comunes en el Portal Energético.

---

## 🚨 Problemas Críticos

### 1. Dashboard no responde (puerto 8050)

```bash
# Verificar si el servicio está activo
sudo systemctl status dashboard-mme

# Ver logs recientes
sudo journalctl -u dashboard-mme -n 50 --no-pager

# Reiniciar servicio
sudo systemctl restart dashboard-mme

# Verificar puerto
ss -tlnp | grep 8050
```

**Soluciones comunes:**
- Si hay error de memoria: `sudo systemctl restart dashboard-mme`
- Si el puerto está ocupado: `sudo lsof -ti:8050 | xargs kill -9`

---

### 2. API no responde (puerto 8000)

```bash
# Verificar estado
sudo systemctl status api-mme

# Ver logs
tail -f /home/admonctrlxm/server/logs/gunicorn_error.log

# Reiniciar
sudo systemctl restart api-mme

# Verificar health check
curl -s http://localhost:8000/health | python3 -m json.tool
```

**Códigos de error comunes:**
- `503`: Problema de conexión a base de datos
- `500`: Error interno, revisar logs
- `429`: Rate limit excedido

---

### 3. Base de datos no conecta

```bash
# Verificar PostgreSQL
sudo systemctl status postgresql

# Probar conexión
psql -U postgres -d portal_energetico -c "SELECT 1;"

# Verificar espacio en disco
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('portal_energetico'));"

# Ver conexiones activas
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
```

**Errores comunes:**
- `FATAL: too many connections`: Reiniciar PostgreSQL o aumentar max_connections
- `disk full`: Limpiar logs o aumentar espacio

---

### 4. Celery no ejecuta tareas

```bash
# Verificar workers
ps aux | grep celery | grep -v grep

# Verificar Flower (monitor)
curl -s http://localhost:5555/api/workers

# Reiniciar workers
sudo systemctl restart celery-worker@1
sudo systemctl restart celery-worker@2
sudo systemctl restart celery-beat

# Ver logs
tail -f /home/admonctrlxm/server/logs/celery/worker-*.log
```

---

## ⚠️ Problemas Medios

### Bot de Telegram no responde

```bash
# Verificar servicio
sudo systemctl status telegram-polling

# Ver logs
tail -f /home/admonctrlxm/server/whatsapp_bot/logs/telegram_bot.log

# Verificar token
psql -U postgres -d portal_energetico -c "SELECT COUNT(*) FROM telegram_users;"
```

---

### ETL no actualiza datos

```bash
# Ejecutar ETL manualmente
python3 /home/admonctrlxm/server/etl/etl_todas_metricas_xm.py

# Verificar última fecha de datos
psql -U postgres -d portal_energetico -c "SELECT MAX(fecha) FROM metrics;"

# Verificar logs de Celery
tail -f /home/admonctrlxm/server/logs/celery/beat.log
```

---

### Predicciones ML no se generan

```bash
# Verificar MLflow
systemctl status mlflow

# Ejecutar predicciones manualmente
python3 /home/admonctrlxm/server/scripts/actualizar_predicciones.py

# Verificar tabla de predicciones
psql -U postgres -d portal_energetico -c "SELECT COUNT(*), MAX(fecha_prediccion) FROM predictions;"
```

---

## 📊 Monitoreo y Diagnóstico

### Comandos útiles

```bash
# Estado general de servicios
sudo systemctl status dashboard-mme api-mme postgresql redis-server

# Uso de recursos
htop
# o
ps aux --sort=-%mem | head -20

# Espacio en disco
df -h

# Logs en tiempo real
tail -f /home/admonctrlxm/server/logs/*.log

# Conexiones de red
ss -tlnp
```

---

### Health Checks

```bash
# Dashboard
curl -s -o /dev/null -w "%{http_code}" http://localhost:8050

# API
curl -s http://localhost:8000/health | python3 -m json.tool

# Base de datos
psql -U postgres -d portal_energetico -c "SELECT version();"

# Redis
redis-cli ping
```

---

## � Bugs Conocidos y Solucionados (Marzo 2026)

Los siguientes bugs fueron identificados y corregidos. Si vuelven a aparecer, verificar la integridad de los archivos fuente:

| Error | Archivo | Causa | Fix |
|-------|---------|-------|-----|
| `TypeError: crear_kpi() got unexpected kwarg 'subtitulo'` | `interface/pages/inversiones.py` | Kwarg incorrecto en KPI dicts | Cambiar `"subtitulo"` → `"subtexto"` en `crear_kpi_row()` |
| `NameError: name 'redis_get_json' is not defined` | `domain/services/metrics_service.py` | Import faltante | Agregar `from infrastructure.cache.redis_client import redis_get_json, redis_set_json` |
| `AttributeError: 'DependencyContainer' has no attribute 'get_cu_service'` | `api/dependencies.py`, handlers | Métodos no existen en instancia del contenedor | Usar funciones de módulo `get_cu_service()`, `get_losses_nt_service()`, `get_simulation_service()` de `core.container` |
| `NameError: name 'PostgreSQLConnectionManager' is not defined` | `domain/services/simulation_service.py` | Clase solo disponible dentro de la función lazy-import | Cambiar `PostgreSQLConnectionManager()` → `_get_connection_manager()` |
| `AttributeError: 'str' object has no attribute 'empty'` | `interface/pages/distribucion.py`, `perdidas_nt.py` | `CacheManager` serializaba DataFrames como strings JSON | Fix en `core/cache.py`: usar marker `{"__dataframe__": True, "records": [...]}` para serialización tipada |
| `RecursionError` en servicios | `losses_nt_service.py`, `cu_minorista_service.py` | Auto-referencia en `__init__.py` de `domain/services/` | Eliminar auto-imports circulares del módulo |

### Cache de DataFrames
Si un método con `@cached` retorna un objeto sin atributo `.empty` o `.columns`:
```bash
# Limpiar caché corrupta de Redis
redis-cli -n 0 KEYS "json:distribution*" | xargs redis-cli -n 0 DEL
redis-cli -n 0 KEYS "json:losses*" | xargs redis-cli -n 0 DEL
redis-cli -n 0 KEYS "json:generation*" | xargs redis-cli -n 0 DEL
redis-cli -n 0 KEYS "json:commercial*" | xargs redis-cli -n 0 DEL
# Reiniciar workers
sudo systemctl restart celery-worker@1 celery-worker@2 dashboard-mme
```

---

## �🐛 Errores Comunes

### Error: "Connection refused"
- **Causa:** Servicio no está corriendo
- **Solución:** `sudo systemctl start <servicio>`

### Error: "Too many connections"
- **Causa:** PostgreSQL alcanzó límite de conexiones
- **Solución:** Reiniciar PostgreSQL o cerrar conexiones idle

### Error: "Memory error"
- **Causa:** Python consumió toda la RAM
- **Solución:** Reiniciar servicio o aumentar RAM

### Error: "Permission denied"
- **Causa:** Permisos de archivo incorrectos
- **Solución:** `sudo chown -R admonctrlxm:admonctrlxm /home/admonctrlxm/server`

---

## 📞 Contactos

| Rol | Contacto |
|-----|----------|
| Infraestructura | [Equipo DevOps] |
| Desarrollo | [Equipo Desarrollo] |
| Datos XM | [Equipo Datos] |

---

## 📚 Documentación Relacionada

- [DISPONIBILIDAD_24_7.md](DISPONIBILIDAD_24_7.md) - Guía de disponibilidad
- [GUIA_USO_API.md](GUIA_USO_API.md) - Guía de la API
- [INVENTARIO_SERVIDOR.md](INVENTARIO_SERVIDOR.md) - Inventario del servidor
