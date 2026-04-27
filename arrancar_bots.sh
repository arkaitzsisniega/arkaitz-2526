#!/bin/bash
# ────────────────────────────────────────────────────────────────
# Arranca los tres bots de Telegram en ventanas separadas de Terminal.
#   • @InterFS_bot                   (Inter — desarrollo, solo Arkaitz)
#   • @InterFS_datos_bot             (Inter — consultas, cuerpo técnico)
#   • @GastosComunes_ArkaitzLis_bot  (Gastos comunes — Arkaitz + Lis)
#
# Uso:
#   Desde Terminal:       ./arrancar_bots.sh
#   Desde Finder:         doble-click sobre el archivo
# ────────────────────────────────────────────────────────────────

BASE="$HOME/Desktop/Arkaitz"

# Comprueba que existen los tres bots
for sub in telegram_bot telegram_bot_datos gastos_bot; do
    if [ ! -x "$BASE/$sub/iniciar.sh" ]; then
        echo "❌ No encuentro $BASE/$sub/iniciar.sh (o no es ejecutable)"
        exit 1
    fi
done

# Mata cualquier instancia previa para evitar conflictos de getUpdates
pkill -f "telegram_bot/bot.py"        2>/dev/null
pkill -f "telegram_bot_datos/bot_datos.py" 2>/dev/null
pkill -f "gastos_bot/bot.py"          2>/dev/null
sleep 1

# Abre una ventana de Terminal para cada bot (macOS AppleScript)
osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$BASE/telegram_bot' && ./iniciar.sh"
    delay 0.5
    do script "cd '$BASE/telegram_bot_datos' && ./iniciar.sh"
    delay 0.5
    do script "cd '$BASE/gastos_bot' && ./iniciar.sh"
end tell
EOF

echo "✓ Lanzadas tres ventanas de Terminal con los bots."
echo "  Para parar: cierra las ventanas o pulsa Ctrl+C en cada una."
