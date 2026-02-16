# Instrucciones para configurar la API para que esté corriendo 24/7

## Opción 1: Usar systemd (RECOMENDADO - Requiere sudo)

1. Copiar el archivo de servicio al directorio systemd:
```bash
sudo cp /home/admonctrlxm/server/api-mme.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. Habilitar el servicio para que inicie automáticamente:
```bash
sudo systemctl enable api-mme.service
```

3. Iniciar el servicio:
```bash
sudo systemctl start api-mme.service
```

4. Verificar el estado:
```bash
sudo systemctl status api-mme.service
```

5. Ver logs:
```bash
sudo journalctl -u api-mme.service -f
```

## Opción 2: Usar cron (Sin sudo)

1. Editar crontab:
```bash
crontab -e
```

2. Agregar esta línea al final:
```bash
@reboot sleep 30 && /home/admonctrlxm/server/api/start_api_daemon.sh
```

3. Guardar y salir

## Opción 3: Manual

### Iniciar la API:
```bash
/home/admonctrlxm/server/api/start_api_daemon.sh
```

### Detener la API:
```bash
/home/admonctrlxm/server/api/stop_api.sh
```

### Verificar estado:
```bash
ps aux | grep "gunicorn api.main:app" | grep -v grep
```

### Probar API:
```bash
curl http://localhost/api/
```

## Monitoreo

### Ver logs en tiempo real:
```bash
tail -f /home/admonctrlxm/server/logs/api-error.log
tail -f /home/admonctrlxm/server/logs/api-access.log
```

### Reiniciar la API:
```bash
/home/admonctrlxm/server/api/stop_api.sh
/home/admonctrlxm/server/api/start_api_daemon.sh
```

## Dependencias instaladas

Las siguientes dependencias fueron instaladas para que la API funcione:
- fastapi==0.109.2
- uvicorn[standard]==0.27.0
- gunicorn==21.2.0
- python-multipart
- pydantic
- pydantic-settings
- sqlalchemy
- psycopg2-binary
- python-jose
- passlib
- bcrypt
- slowapi
- redis

**NOTA**: Se desinstalónest_asyncio porque causaba conflictos con uvloop.

## Endpoints disponibles

- API Root: http://portalenergetico.minenergia.gov.co/api/
- Documentación: http://portalenergetico.minenergia.gov.co/api/docs
- Health Check: http://portalenergetico.minenergia.gov.co/api/health
- API v1: http://portalenergetico.minenergia.gov.co/api/v1/

## Estado actual

✅ La API está corriendo actualmente en el puerto 8000
✅ Nginx está configurado para hacer proxy en /api/
✅ Los endpoints están respondiendo correctamente
