#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  Monitoreo del Portal Energético — EXTREMO A EXTREMO (por el WAF)
#  Cron sugerido: */5 * * * *
#
#  POR QUÉ EXISTE
#  Del 2026-09-10 20:59 al 2026-10-09 08:48 el portal estuvo caído 29 días con
#  un bucle de redirecciones, y NINGUNO de los 4 monitoreos que lo vigilaban
#  (AppManager, Apache-HttpClient, Uptime-Kuma, UptimeRobot — ~69.000 consultas
#  diarias) lo detectó: todos aceptan un 301 como "el sitio responde".
#
#  Por eso este check es distinto en tres cosas:
#    1. Consulta la URL PÚBLICA, por el WAF, igual que un usuario. Un check
#       contra 127.0.0.1:8050 habría dicho "OK" durante los 29 días, porque la
#       aplicación siempre estuvo sana: lo roto era el salto WAF↔nginx.
#    2. NO sigue redirecciones (sin -L) y exige HTTP 200. Un 301 es FALLO.
#    3. Verifica que el HTML sea realmente el portal, no una página de error
#       ni un redirect de 162 bytes.
#
#  Procesos involucrados (para quien atienda la alerta):
#    - Aplicación Dash, puerto 8050 → systemd: dashboard-mme.service
#    - nginx                        → /etc/nginx/sites-available/portalenergetico
#    - WAF perimetral               → 172.17.10.146 (reenvía desde 172.17.0.70)
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# ─────────────────────────── Configuración ───────────────────────────
# MONITOR_URL_PRUEBA permite apuntar el check a otra URL para verificar el
# script contra un endpoint roto conocido. En cron NO se define, así que
# siempre usa la URL pública real.
URL_PUBLICA="${MONITOR_URL_PRUEBA:-https://portalenergetico.minenergia.gov.co/}"
URL_LOCAL="http://127.0.0.1:8050/"
MARCADOR="react-entry-point"      # punto de montaje de Dash en el HTML
BYTES_MINIMOS=5000                # el redirect de nginx mide 162 bytes
REINTENTOS=3
ESPERA_REINTENTO=5
TIMEOUT=15

PROJECT_DIR="/home/admonctrlxm/server"
VENV_PY="$PROJECT_DIR/venv/bin/python3"
LOG="$PROJECT_DIR/logs/monitor_portalenergetico.log"
ESTADO="$PROJECT_DIR/logs/.monitor_portalenergetico_estado"

# ─────────────────────────── Notificaciones ───────────────────────────
# IMPORTANTE: estas dos listas DEBEN quedar como listas, aunque estén vacías.
#   - vacías  → no se envía nada a nadie (solo queda el registro en el log)
#   - con IDs → se envía SOLO a esos destinatarios
# Nunca cambiar a None/null: en notification_service.py, None significa
# "enviar a TODOS los usuarios registrados" (3 corridas de un script así
# mandaron 12 correos y 21 mensajes de Telegram el 2026-10-08).
#
# Para obtener tu chat_id de Telegram:
#   cd /home/admonctrlxm/server && venv/bin/python3 -c \
#     "from domain.services.notification_service import get_telegram_users; print(get_telegram_users())"
ALERTA_TELEGRAM_CHAT_IDS="5084190952"            # Melissa Cardona
ALERTA_EMAIL="mjcardona@minenergia.gov.co"       # Melissa Cardona

# Solo se notifica en los CAMBIOS de estado (OK→FALLO y FALLO→OK), nunca en
# cada corrida. Aunque el portal esté caído un mes, se envía un único aviso.

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# ─────────────────────────── Verificación ───────────────────────────
# Imprime "<codigo> <bytes> <marcador_ok>" y retorna 0 si todo está correcto.
verificar_url() {
    local url="$1"
    local cuerpo codigo bytes marcador

    cuerpo=$(mktemp)
    # Sin -L a propósito: una redirección debe contar como fallo.
    codigo=$(curl -s -k -o "$cuerpo" -w '%{http_code}' --max-time "$TIMEOUT" "$url" 2>/dev/null)
    bytes=$(wc -c < "$cuerpo" 2>/dev/null || echo 0)

    if grep -q "$MARCADOR" "$cuerpo" 2>/dev/null; then marcador="si"; else marcador="no"; fi
    rm -f "$cuerpo"

    echo "$codigo $bytes $marcador"

    [ "$codigo" = "200" ] && [ "$bytes" -ge "$BYTES_MINIMOS" ] && [ "$marcador" = "si" ]
}

# Clasifica dónde está el fallo, para que la alerta sea accionable.
clasificar_fallo() {
    local res_local
    if res_local=$(verificar_url "$URL_LOCAL"); then
        echo "PERIMETRO|La aplicación responde bien en local ($URL_LOCAL → $res_local) pero la URL pública falla. El problema está en nginx o en el WAF, NO en la aplicación. Reiniciar dashboard-mme.service no lo va a resolver. Revisar /etc/nginx/sites-available/portalenergetico y el salto desde el WAF (172.17.10.146)."
    else
        echo "APLICACION|La aplicación tampoco responde en local ($URL_LOCAL → $res_local). Revisar: systemctl status dashboard-mme.service"
    fi
}

notificar() {
    local asunto="$1" detalle="$2" severidad="$3"

    if [ -z "$ALERTA_TELEGRAM_CHAT_IDS" ] && [ -z "$ALERTA_EMAIL" ]; then
        log "   ℹ️  Notificación omitida: no hay destinatarios configurados en el script."
        return 0
    fi

    TG_IDS="$ALERTA_TELEGRAM_CHAT_IDS" EM="$ALERTA_EMAIL" \
    ASUNTO="$asunto" DETALLE="$detalle" SEV="$severidad" \
    "$VENV_PY" - <<'PY' >> "$LOG" 2>&1
import os, sys
sys.path.insert(0, "/home/admonctrlxm/server")
from domain.services.notification_service import broadcast_alert

# Siempre listas, nunca None: None = enviar a TODOS los registrados.
chat_ids = [int(x) for x in os.environ["TG_IDS"].split(",") if x.strip()]
emails   = [x.strip() for x in os.environ["EM"].split(",") if x.strip()]

asunto, detalle = os.environ["ASUNTO"], os.environ["DETALLE"]
res = broadcast_alert(
    message=f"*{asunto}*\n\n{detalle}",
    severity=os.environ["SEV"],
    email_subject=asunto,
    telegram_chat_ids=chat_ids,
    email_override=emails,
)
print(f"   Envío → telegram={res['telegram']} email={res['email']}")
PY
}

# ─────────────────────────── Modo prueba ───────────────────────────
# ./monitor_portalenergetico.sh --probar
# Verifica e imprime por pantalla sin tocar el estado ni notificar a nadie.
# ./monitor_portalenergetico.sh --probar-alerta
# Envía un mensaje de prueba inofensivo a los destinatarios configurados.
# Útil para confirmar la entrega tras cambiar ALERTA_TELEGRAM_CHAT_IDS o
# ALERTA_EMAIL, sin tener que simular una caída.
if [ "${1:-}" = "--probar-alerta" ]; then
    echo "Enviando alerta de prueba a los destinatarios configurados..."
    echo "  Telegram: ${ALERTA_TELEGRAM_CHAT_IDS:-(ninguno)}"
    echo "  Correo:   ${ALERTA_EMAIL:-(ninguno)}"
    notificar "Prueba de alertas — Portal Energético" \
              "Mensaje de prueba del monitoreo. NO es una caída real. Si lo recibes, la entrega de alertas funciona." \
              "INFO"
    echo "Resultado registrado en: $LOG"
    tail -2 "$LOG"
    exit 0
fi

if [ "${1:-}" = "--probar" ]; then
    echo "Modo prueba — no modifica el estado ni envía notificaciones."
    echo
    printf "  URL pública  %-55s " "$URL_PUBLICA"
    if res=$(verificar_url "$URL_PUBLICA"); then echo "✅ OK   ($res)"; else echo "❌ FALLO ($res)"; fi
    printf "  App local    %-55s " "$URL_LOCAL"
    if res=$(verificar_url "$URL_LOCAL"); then echo "✅ OK   ($res)"; else echo "❌ FALLO ($res)"; fi
    echo
    echo "  (formato: <código HTTP> <bytes> <marcador '$MARCADOR' presente>)"
    echo "  Estado guardado actualmente: $(cat "$ESTADO" 2>/dev/null || echo 'sin registro')"
    exit 0
fi

# ─────────────────────────── Ejecución normal ───────────────────────────
ESTADO_ANTERIOR=$(cat "$ESTADO" 2>/dev/null || echo "DESCONOCIDO")

RESULTADO=""
OK=1
for i in $(seq 1 "$REINTENTOS"); do
    if RESULTADO=$(verificar_url "$URL_PUBLICA"); then
        OK=0
        break
    fi
    [ "$i" -lt "$REINTENTOS" ] && sleep "$ESPERA_REINTENTO"
done

if [ "$OK" -eq 0 ]; then
    echo "OK" > "$ESTADO"
    log "✅ Portal OK ($RESULTADO)"
    if [ "$ESTADO_ANTERIOR" = "FALLO" ]; then
        log "🟢 RECUPERADO tras un fallo previo."
        notificar "✅ Portal Energético recuperado" \
                  "El portal volvió a responder correctamente.\nURL: $URL_PUBLICA\nRespuesta: $RESULTADO" \
                  "INFO"
    fi
    exit 0
fi

CLASIFICACION=$(clasificar_fallo)
DONDE="${CLASIFICACION%%|*}"
EXPLICACION="${CLASIFICACION#*|}"

log "❌ FALLO [$DONDE] — URL pública: $RESULTADO (se esperaba: 200, ≥$BYTES_MINIMOS bytes, marcador '$MARCADOR')"
log "   $EXPLICACION"

if [ "$ESTADO_ANTERIOR" != "FALLO" ]; then
    echo "FALLO" > "$ESTADO"
    notificar "🚨 Portal Energético caído [$DONDE]" \
              "El portal no responde correctamente desde internet.\n\nURL: $URL_PUBLICA\nRecibido: $RESULTADO\nEsperado: código 200, ≥$BYTES_MINIMOS bytes, con el marcador '$MARCADOR'\n\n$EXPLICACION" \
              "CRITICAL"
else
    echo "FALLO" > "$ESTADO"
    log "   (ya se había notificado este fallo; no se repite el aviso)"
fi

exit 1
