# ═══════════════════════════════════════════════════════════════════════════════
# Makefile - Portal Energético MME
#
# Nota (2026-09-30): se retiraron los comandos de Docker Compose — Docker nunca
# llegó a instalarse en el servidor real; producción corre 100% por systemd
# (ver RUNBOOK_PRODUCCION.md). Quedan solo los smoke-tests, que funcionan igual
# contra los servicios systemd porque solo hacen curl a localhost.
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help test-api test-dashboard test-all

help: ## Muestra esta ayuda
	@echo "Portal Energético MME"
	@echo "======================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

test-api: ## Test de health de la API (systemd: portal-api.service)
	@echo "🔍 Verificando API..."
	@curl -s http://localhost:8000/health | jq . || echo "❌ API no responde"

test-dashboard: ## Test del tablero Dash (systemd: dashboard-mme.service)
	@echo "🔍 Verificando Dashboard..."
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:8050 | grep -q "200\|302" && echo "✅ Dashboard OK" || echo "❌ Dashboard no responde"

test-all: test-api test-dashboard ## Test de todos los servicios
	@echo "✅ Tests completados"
