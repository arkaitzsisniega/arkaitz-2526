#!/bin/bash
# auto_pull.sh — Hace `git pull` cada N minutos (vía LaunchAgent) y, si
# trae commits nuevos, reinicia los bots para que apliquen los cambios.
#
# Diseñado para correr en el Mac viejo servidor (~/Desktop/Arkaitz como
# clon del repo). Idempotente: si no hay cambios remotos, no hace nada
# (excepto un log silencioso). Si los hay:
#   1. git pull --quiet
#   2. launchctl kickstart -k de los bots que estén instalados como
#      LaunchAgents (com.arkaitz.bot, com.arkaitz.bot_datos,
#      com.arkaitz.gastos_bot).
#   3. (Opcional) manda un Telegram a ALLOWED_CHAT_ID avisando.
#
# Lanzado por com.arkaitz.autopull.plist (LaunchAgent) cada 5 minutos.

set -u

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
[ -z "${HOME:-}" ] && export HOME="$(eval echo ~$(whoami))"

BASE="$HOME/Desktop/Arkaitz"
LOG_DIR="$BASE/logs"
LOG="$LOG_DIR/autopull.log"

mkdir -p "$LOG_DIR"

# ── Función de log con timestamp ──
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

# ── Sanity checks ──
if [ ! -d "$BASE/.git" ]; then
    log "ERROR: $BASE no es un repo git. Aborto."
    exit 1
fi

cd "$BASE" || { log "ERROR: cd $BASE falló."; exit 1; }

# ── git pull ──
BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -z "$BEFORE" ]; then
    log "ERROR: no puedo leer HEAD. Aborto."
    exit 1
fi

# fetch + pull. Capturamos stderr para tenerlo si falla.
PULL_OUT=$(git pull --quiet --ff-only 2>&1)
PULL_RC=$?
if [ $PULL_RC -ne 0 ]; then
    log "WARN: git pull falló (rc=$PULL_RC): $PULL_OUT"
    # No abortamos: el pull puede fallar por conflicto local pero el
    # cron seguirá intentándolo; aviso una vez y salgo.
    exit 0
fi

AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    # No hay cambios. Salimos silenciosamente (no spameamos el log).
    exit 0
fi

# ── Hay commits nuevos ──
NUEVOS=$(git log --oneline "$BEFORE..$AFTER" | wc -l | tr -d ' ')
RESUMEN=$(git log --oneline "$BEFORE..$AFTER" | head -5)
log "✓ $NUEVOS commits nuevos:"
echo "$RESUMEN" | while read -r line; do log "    $line"; done

# ── Reiniciar bots activos ──
USER_ID=$(id -u)
REINICIADOS=()
for label in com.arkaitz.bot com.arkaitz.bot_datos com.arkaitz.gastos_bot; do
    if launchctl list 2>/dev/null | grep -q "^[0-9-]\+[[:space:]]\+[0-9]\+[[:space:]]\+${label}$"; then
        if launchctl kickstart -k "gui/$USER_ID/$label" 2>>"$LOG"; then
            log "  → reiniciado $label"
            REINICIADOS+=("$label")
        else
            log "  ! fallo reiniciando $label"
        fi
    fi
done

# ── Notificar por Telegram (si tenemos credenciales) ──
ENV_FILE="$BASE/telegram_bot/.env"
if [ -f "$ENV_FILE" ]; then
    TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d "\"'" | xargs)
    CHAT=$(grep -E "^ALLOWED_CHAT_ID=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d "\"'" | xargs)
    if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
        # Mensaje plano (sin Markdown para evitar errores de parseo si los
        # commits llevan caracteres especiales).
        MSG="🔄 Bots actualizados ($NUEVOS commits)."
        MSG+=$'\n'"Reiniciados: ${REINICIADOS[*]:-ninguno}"
        MSG+=$'\n'"Últimos:"
        MSG+=$'\n'"$RESUMEN"
        # Limit Telegram message length
        if [ ${#MSG} -gt 3500 ]; then
            MSG="${MSG:0:3500}…"
        fi
        curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${CHAT}" \
            --data-urlencode "text=${MSG}" \
            --data-urlencode "disable_notification=true" \
            >>"$LOG" 2>&1
        log "  → notificado a chat $CHAT"
    fi
fi

exit 0
