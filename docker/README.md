# 🐳 Docker - Portal Energético MME

Guía completa para ejecutar el Portal Energético usando Docker Compose.

## 📋 Índice

- [Requisitos](#requisitos)
- [Estructura](#estructura)
- [Primeros Pasos](#primeros-pasos)
- [Comandos Útiles](#comandos-útiles)
- [Migración desde Systemd](#migración-desde-systemd)
- [Solución de Problemas](#solución-de-problemas)

## 📦 Requisitos

- Docker Engine 20.10+
- Docker Compose 2.0+
- Git (para actualizaciones)

## 🏗️ Estructura

```
├── docker-compose.yml          # Orquestación principal
├── docker/
│   ├── api/
│   │   └── Dockerfile          # API + Dashboard
│   └── telegram/
│       └── Dockerfile          # Telegram Bot
├── scripts/
│   ├── migrate-to-docker.sh    # Migración desde systemd
│   └── docker-deploy.sh        # Deploy simplificado
├── .env.docker                 # Template de variables
└── docker/
    └── README.md               # Este archivo
```

## 🚀 Primeros Pasos

### 1. Migración desde Systemd (Si ya tienes el sistema corriendo)

```bash
./scripts/migrate-to-docker.sh
```

Este script:
- Hace backup de tu BD actual
- Detiene servicios systemd
- Configura el entorno Docker
- Migra los datos

### 2. Instalación Limpia (Nuevo servidor)

```bash
# 1. Clonar o copiar el proyecto
cd /home/admonctrlxm/server

# 2. Configurar variables de entorno
cp .env.docker .env
# Editar .env con tus credenciales

# 3. Crear estructura de directorios
mkdir -p logs/{api,dashboard,celery,telegram} data whatsapp_bot/informes

# 4. Iniciar servicios
docker compose up -d

# 5. Verificar que todo funcione
curl http://localhost:8000/health
```

## 🎮 Comandos Útiles

### Script de Deploy (Recomendado)

```bash
# Iniciar todo
./scripts/docker-deploy.sh up

# Reiniciar servicios
./scripts/docker-deploy.sh restart

# Reiniciar solo API (después de cambios en código)
./scripts/docker-deploy.sh restart-api

# Ver logs
./scripts/docker-deploy.sh logs
./scripts/docker-deploy.sh logs-api
./scripts/docker-deploy.sh logs-bot

# Backup de BD
./scripts/docker-deploy.sh backup

# Ver estado
./scripts/docker-deploy.sh status
```

### Docker Compose Directo

```bash
# Iniciar
docker compose up -d

# Ver logs
docker compose logs -f
docker compose logs -f api
docker compose logs -f telegram-bot

# Reiniciar servicio específico
docker compose restart api
docker compose restart telegram-bot

# Escalar workers (ej: 4 workers)
docker compose up -d --scale celery-worker=4

# Detener todo
docker compose down

# Detener y eliminar volúmenes (⚠️ Pierdes datos)
docker compose down -v
```

## 🔧 Configuración

### Variables de Entorno (.env)

```bash
# Base de datos
POSTGRES_DB=portal_energetico
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password_seguro

# API Keys
GROQ_API_KEY=gsk_...
TELEGRAM_BOT_TOKEN=...

# Ver .env.docker para lista completa
```

### Redes

Los servicios se comunican a través de la red `mme-network`:

- `postgres` → Base de datos PostgreSQL
- `redis` → Cache y broker Celery
- `api` → API REST (puerto 8000)
- `dashboard` → Dashboard Dash (puerto 8050)
- `telegram-bot` → Bot de Telegram
- `celery-worker` → Workers de tareas async
- `celery-beat` → Scheduler de tareas

### Volúmenes Persistentes

- `postgres_data` → Datos de PostgreSQL
- `redis_data` → Datos de Redis
- `celery_beat_data` → Scheduler de Celery
- `./logs` → Logs de aplicaciones
- `./data` → Datos estáticos

## 🔄 Actualizaciones

### Actualizar código y redeploy

```bash
# Opción 1: Usando el script
./scripts/docker-deploy.sh update

# Opción 2: Manual
git pull
docker compose build
docker compose up -d
```

### Solo reiniciar después de cambios

```bash
# Si cambiaste código Python (no Dockerfile)
./scripts/docker-deploy.sh restart-api

# Si cambiaste requirements o Dockerfile
./scripts/docker-deploy.sh rebuild
```

## 📊 Monitoreo

### Flower (Celery Monitoring)

```bash
# Iniciar Flower
docker compose --profile monitoring up -d flower

# Acceder
open http://localhost:5555
```

### Health Checks

Cada servicio tiene health checks configurados:

```bash
# Ver estado de health
docker compose ps

# Health check manual
curl http://localhost:8000/health
curl http://localhost:8050  # Dashboard
```

## 💾 Backups

### Backup automático

```bash
./scripts/docker-deploy.sh backup
# Crea: backups/db-backup-YYYYMMDD-HHMMSS.sql
```

### Backup manual

```bash
docker compose exec postgres pg_dump -U postgres portal_energetico > backup.sql
```

### Restaurar backup

```bash
docker compose exec -T postgres psql -U postgres -d portal_energetico < backup.sql
```

## 🔍 Solución de Problemas

### API no responde

```bash
# Ver logs
docker compose logs api --tail=50

# Reiniciar
docker compose restart api

# Verificar health
curl http://localhost:8000/health
```

### Bot de Telegram no funciona

```bash
# Ver logs
docker compose logs telegram-bot --tail=50

# Verificar que el token esté configurado
docker compose exec telegram-bot env | grep TELEGRAM
```

### Problemas de BD

```bash
# Conectar a PostgreSQL
docker compose exec postgres psql -U postgres -d portal_energetico

# Ver logs
docker compose logs postgres --tail=50
```

### Limpiar todo y empezar de nuevo (⚠️ Pierdes datos)

```bash
docker compose down -v
docker compose up -d
```

## 🏥 Health Checks

Todos los servicios incluyen health checks:

- **PostgreSQL**: `pg_isready`
- **Redis**: `redis-cli ping`
- **API**: `GET /health`
- **Dashboard**: `GET /`
- **Bot**: Proceso corriendo

## 📈 Escalabilidad

### Escalar Celery Workers

```bash
# 4 workers
docker compose up -d --scale celery-worker=4
```

### Recursos por contenedor

Editar `docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## 🔒 Seguridad

### No exponer puertos innecesarios

Por defecto, solo se exponen:
- 8000 (API)
- 8050 (Dashboard)
- 5555 (Flower - opcional)

PostgreSQL y Redis solo son accesibles dentro de la red Docker.

### Variables sensibles

Usa Docker Secrets en producción:

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## 🆘 Soporte

Si encuentras problemas:

1. Revisar logs: `docker compose logs [servicio]`
2. Verificar health: `docker compose ps`
3. Revisar configuración: `docker compose config`
4. Contactar al equipo de desarrollo

---

**Versión**: 2.0.0  
**Última actualización**: Abril 2026
