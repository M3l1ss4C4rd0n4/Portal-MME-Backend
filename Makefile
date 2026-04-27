# ═══════════════════════════════════════════════════════════════════════════════
# Makefile - Portal Energético MME
# Comandos simplificados para Docker Compose
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help up down restart rebuild logs status backup migrate shell-api shell-bot

# Variables
COMPOSE = docker compose
SERVICE_API = api
SERVICE_BOT = telegram-bot

# Colores
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
NC := \033[0m

help: ## Muestra esta ayuda
	@echo "$(BLUE)Portal Energético MME - Comandos Docker$(NC)"
	@echo "=========================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'

# ═══════════════════════════════════════════════════════════════════════════════
# COMANDOS PRINCIPALES
# ═══════════════════════════════════════════════════════════════════════════════

up: ## Iniciar todos los servicios
	@echo "$(BLUE)🚀 Iniciando servicios...$(NC)"
	$(COMPOSE) up -d
	@echo "$(GREEN)✅ Servicios iniciados:$(NC)"
	@echo "  API:       http://localhost:8000"
	@echo "  Dashboard: http://localhost:8050"

down: ## Detener todos los servicios
	@echo "$(YELLOW)🛑 Deteniendo servicios...$(NC)"
	$(COMPOSE) down
	@echo "$(GREEN)✅ Servicios detenidos$(NC)"

restart: ## Reiniciar todos los servicios
	@echo "$(YELLOW)🔄 Reiniciando servicios...$(NC)"
	$(COMPOSE) restart
	@echo "$(GREEN)✅ Servicios reiniciados$(NC)"

restart-api: ## Reiniciar solo la API
	@echo "$(YELLOW)🔄 Reiniciando API...$(NC)"
	$(COMPOSE) restart $(SERVICE_API)
	@echo "$(GREEN)✅ API reiniciada$(NC)"

restart-bot: ## Reiniciar solo el Bot
	@echo "$(YELLOW)🔄 Reiniciando Bot...$(NC)"
	$(COMPOSE) restart $(SERVICE_BOT)
	@echo "$(GREEN)✅ Bot reiniciado$(NC)"

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD & DEPLOY
# ═══════════════════════════════════════════════════════════════════════════════

build: ## Construir imágenes
	@echo "$(BLUE)🏗️  Construyendo imágenes...$(NC)"
	$(COMPOSE) build

rebuild: ## Reconstruir imágenes y reiniciar
	@echo "$(YELLOW)🏗️  Reconstruyendo imágenes...$(NC)"
	$(COMPOSE) down
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d
	@echo "$(GREEN)✅ Rebuild completado$(NC)"

update: ## Actualizar código y redeploy
	@echo "$(BLUE)📥 Actualizando código...$(NC)"
	git pull origin main || echo "No es repo git o sin cambios"
	$(COMPOSE) build
	$(COMPOSE) up -d
	@echo "$(GREEN)✅ Actualización completada$(NC)"

# ═══════════════════════════════════════════════════════════════════════════════
# LOGS
# ═══════════════════════════════════════════════════════════════════════════════

logs: ## Ver logs en tiempo real (todos)
	$(COMPOSE) logs -f --tail=100

logs-api: ## Ver logs de la API
	$(COMPOSE) logs -f $(SERVICE_API) --tail=100

logs-bot: ## Ver logs del Bot
	$(COMPOSE) logs -f $(SERVICE_BOT) --tail=100

logs-postgres: ## Ver logs de PostgreSQL
	$(COMPOSE) logs -f postgres --tail=50

# ═══════════════════════════════════════════════════════════════════════════════
# MONITOREO & DEBUG
# ═══════════════════════════════════════════════════════════════════════════════

status: ## Ver estado de los servicios
	@echo "$(BLUE)📊 Estado de servicios:$(NC)"
	$(COMPOSE) ps

stats: ## Ver uso de recursos
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

shell-api: ## Abrir shell en el contenedor de API
	$(COMPOSE) exec $(SERVICE_API) /bin/bash

shell-bot: ## Abrir shell en el contenedor del Bot
	$(COMPOSE) exec $(SERVICE_BOT) /bin/bash

shell-db: ## Abrir shell en PostgreSQL
	$(COMPOSE) exec postgres psql -U postgres -d portal_energetico

# ═══════════════════════════════════════════════════════════════════════════════
# BACKUPS
# ═══════════════════════════════════════════════════════════════════════════════

backup: ## Crear backup de base de datos
	@mkdir -p backups
	@echo "$(BLUE)💾 Creando backup...$(NC)"
	$(COMPOSE) exec -T postgres pg_dump -U postgres portal_energetico > backups/db-backup-$$(date +%Y%m%d-%H%M%S).sql
	@echo "$(GREEN)✅ Backup creado$(NC)"

restore: ## Restaurar backup (especificar archivo: make restore FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(YELLOW)⚠️  Uso: make restore FILE=backups/backup.sql$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)🔄 Restaurando backup: $(FILE)$(NC)"
	$(COMPOSE) exec -T postgres psql -U postgres -d portal_energetico < $(FILE)
	@echo "$(GREEN)✅ Backup restaurado$(NC)"

# ═══════════════════════════════════════════════════════════════════════════════
# MIGRACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

migrate: ## Migrar desde Systemd a Docker
	@echo "$(BLUE)🐳 Iniciando migración...$(NC)"
	./scripts/migrate-to-docker.sh

# ═══════════════════════════════════════════════════════════════════════════════
# LIMPIEZA
# ═══════════════════════════════════════════════════════════════════════════════

clean: ## Limpiar contenedores detenidos
	@echo "$(YELLOW)🧹 Limpiando contenedores...$(NC)"
	docker container prune -f

clean-images: ## Limpiar imágenes no usadas
	@echo "$(YELLOW)🧹 Limpiando imágenes...$(NC)"
	docker image prune -af

clean-all: ## ⚠️ Limpiar TODO (incluyendo volúmenes)
	@echo "$(RED)⚠️  Esto eliminará TODOS los datos$(NC)"
	@read -p "¿Estás seguro? (s/N): " confirm && [ $$confirm = s ] || exit 1
	$(COMPOSE) down -v
	docker system prune -af
	@echo "$(GREEN)✅ Sistema limpiado$(NC)"

# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

test-api: ## Test de health API
	@echo "$(BLUE)🔍 Verificando API...$(NC)"
	@curl -s http://localhost:8000/health | jq . || echo "$(RED)❌ API no responde$(NC)"

test-dashboard: ## Test de Dashboard
	@echo "$(BLUE)🔍 Verificando Dashboard...$(NC)"
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:8050 | grep -q "200\|302" && echo "$(GREEN)✅ Dashboard OK$(NC)" || echo "$(RED)❌ Dashboard no responde$(NC)"

test-all: test-api test-dashboard ## Test de todos los servicios
	@echo "$(GREEN)✅ Tests completados$(NC)"
