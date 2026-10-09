#!/usr/bin/env bash
set -uo pipefail

# ═══════════════════════════════════════════════════════════════════════
#  Deploy del backend — Portal Energético MME
#
#  Existe porque NO había ninguna ruta, manual ni automática, que
#  reiniciara `dashboard-mme`: el tablero estuvo desde el 2026-09-30
#  sirviendo código de hace 12 commits sin que nada lo señalara.
#  `scripts/restart_all.sh` y `restart_all_services.sh` tampoco lo tocan.
#
#  Uso:  ./scripts/deploy-backend.sh [--sin-tests]
# ═══════════════════════════════════════════════════════════════════════

PROJECT_DIR="/home/admonctrlxm/server"
VENV="$PROJECT_DIR/venv/bin/python3"
HEALTH_URL="http://localhost:8000/health"
DASH_URL="http://localhost:8050/"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${G}[DEPLOY]${NC} $*"; }
warn() { echo -e "${Y}[WARN]${NC}  $*"; }
fail() { echo -e "${R}[FAIL]${NC}  $*"; exit 1; }

cd "$PROJECT_DIR" || fail "no se pudo entrar a $PROJECT_DIR"

CORRER_TESTS=1
[[ "${1:-}" == "--sin-tests" ]] && CORRER_TESTS=0

# ── 1. Pre-checks ──────────────────────────────────────────────────────
log "Commit a desplegar: $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    warn "Hay cambios sin commitear; se desplegará el árbol de trabajo:"
    git status --short --untracked-files=no | sed 's/^/        /'
fi

if [[ $CORRER_TESTS -eq 1 ]]; then
    log "Corriendo la suite de tests..."
    if ! "$VENV" -m pytest tests/ -q --tb=line > /tmp/deploy_tests.log 2>&1; then
        tail -20 /tmp/deploy_tests.log
        fail "Los tests no pasan. Use --sin-tests solo si sabe por qué."
    fi
    log "  $(tail -1 /tmp/deploy_tests.log)"
fi

# ── 2. Reinicio escalonado ─────────────────────────────────────────────
# Orden: primero los consumidores, al final la API, para que ningún worker
# quede hablando con una versión del código distinta a la que sirve.
SERVICIOS=(celery-beat celery-worker celery-worker@1 celery-worker@2
           telegram-polling whatsapp-bot dashboard-mme portal-api)

declare -a NO_REINICIADOS=()

for s in "${SERVICIOS[@]}"; do
    # `list-unit-files` no lista las instancias de plantilla (celery-worker@1),
    # así que la existencia se comprueba por el estado de carga de la unidad.
    carga="$(systemctl show "${s}.service" -p LoadState --value 2>/dev/null)"
    if [[ "$carga" != "loaded" ]]; then
        warn "$s no existe como unidad (LoadState=$carga), se omite"
        continue
    fi
    if sudo -n systemctl restart "${s}.service" 2>/dev/null; then
        sleep 3
        estado="$(systemctl is-active "${s}.service" 2>/dev/null)"
        if [[ "$estado" == "active" ]]; then
            log "  ✅ $s reiniciado"
        else
            fail "$s quedó en estado '$estado' tras el reinicio"
        fi
    else
        NO_REINICIADOS+=("$s")
        warn "  ⏭️  $s NO se pudo reiniciar: sudo pide contraseña"
    fi
done

# ── 3. Verificación ────────────────────────────────────────────────────
log "Verificando servicios..."

sleep 5
http_api="$(curl -s -o /dev/null -w '%{http_code}' -m 20 "$HEALTH_URL" || echo 000)"
[[ "$http_api" == "200" ]] || warn "  /health devolvió $http_api (503 = degradado, revisar el detalle)"
[[ "$http_api" == "200" ]] && log "  ✅ API /health 200"

http_dash="$(curl -s -o /dev/null -w '%{http_code}' -m 20 "$DASH_URL" || echo 000)"
[[ "$http_dash" == "200" ]] && log "  ✅ Dash 200" || warn "  Dash devolvió $http_dash"

# ── 4. ¿Quedó algo con código viejo? ───────────────────────────────────
log "Comprobando que ningún servicio quedó atrás..."
"$VENV" - <<'PY'
from domain.services.latidos_service import revisar_servicios
atrasados = [r for r in revisar_servicios() if not r.ok]
if atrasados:
    print(f"  \033[1;33m[WARN]\033[0m  {len(atrasados)} servicio(s) con código anterior al último commit:")
    for r in atrasados:
        print(f"        - {r.latido.que_vigila}")
else:
    print("  \033[0;32m[DEPLOY]\033[0m  ✅ Todos los servicios corren el código desplegado")
PY

if [[ ${#NO_REINICIADOS[@]} -gt 0 ]]; then
    echo
    warn "Faltó reiniciar: ${NO_REINICIADOS[*]}"
    warn "Requiere ampliar la regla sudoers — ver scripts/sudoers-portal-mme.propuesto"
    exit 2
fi

log "Deploy completado."
