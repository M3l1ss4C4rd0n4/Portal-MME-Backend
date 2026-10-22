#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Monitoreo del Portal Next.js (PM2 'portal-mme', puerto 3001)
#  Cron: */5 * * * *
#
#  monitor_api.sh sólo vigila el backend (systemd, puerto 8000). El portal
#  no tenía monitoreo: el 2026-09-30 quedó en blanco y pasaron 6 días sin
#  alerta, porque la portada seguía respondiendo HTTP 200.
#
#  Este check valida los recursos /_next/static, que es donde se ve el fallo.
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

PROJECT_DIR="/home/admonctrlxm/portal-direccion-mme"
PM2_NAME="portal-mme"
PM2_BIN="/home/admonctrlxm/.nvm/versions/node/v20.20.0/bin/pm2"
BASE="http://127.0.0.1:3001"
LOG="/home/admonctrlxm/server/logs/monitor_portal.log"
STATE="/home/admonctrlxm/server/logs/.monitor_portal_last_restart"
COOLDOWN=1800   # 30 min mínimo entre auto-reinicios (evita bucle de reinicios)

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

RES=$(bash "$PROJECT_DIR/scripts/check-assets.sh" "$BASE" / 2>&1); RC=$?

if [ "$RC" -eq 0 ]; then
  log "✅ $RES"
  exit 0
fi

log "❌ FALLO (rc=$RC) — $RES"

NOW=$(date +%s)
LAST=0
[ -f "$STATE" ] && LAST=$(cat "$STATE" 2>/dev/null || echo 0)

if [ $((NOW - LAST)) -lt "$COOLDOWN" ]; then
  REST=$(( (COOLDOWN - (NOW - LAST)) / 60 ))
  log "⏸️  En cooldown (${REST} min). NO se reinicia: el fallo persiste tras un reinicio previo — requiere revisión manual."
  exit 1
fi

echo "$NOW" > "$STATE"
log "🔄 Reiniciando '$PM2_NAME'..."
"$PM2_BIN" restart "$PM2_NAME" --update-env >> "$LOG" 2>&1

# Esperar readiness sin busy-loop
curl -sL --retry 20 --retry-delay 1 --retry-all-errors --max-time 60 \
     -o /dev/null "$BASE/api/health/" 2>/dev/null

RES2=$(bash "$PROJECT_DIR/scripts/check-assets.sh" "$BASE" / 2>&1); RC2=$?
if [ "$RC2" -eq 0 ]; then
  log "✅ RECUPERADO — $RES2"
  exit 0
fi

log "🚨 SIGUE ROTO tras el reinicio — $RES2 — INTERVENCIÓN MANUAL REQUERIDA"
exit 1
