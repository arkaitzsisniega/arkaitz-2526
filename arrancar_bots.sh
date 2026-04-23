#!/bin/bash
# ────────────────────────────────────────────────────────────────
# Arranca los dos bots de Telegram en ventanas separadas de Terminal.
#   • @InterFS_bot        (desarrollo, solo Arkaitz)
#   • @InterFS_datos_bot  (consultas de datos, cuerpo técnico)
#
# Uso:
#   Desde Terminal:       ./arrancar_bots.sh
#   Desde Finder:         doble-click sobre el archivo
# ────────────────────────────────────────────────────────────────

BASE="$HOME/Desktop/Arkaitz"

# Comprueba que existen ambos bots
if [ ! -x "$BASE/telegram_bot/iniciar.sh" ] || [ ! -x "$BASE/telegram_bot_datos/iniciar.sh" ]; then
    echo "❌ No encuentro los scripts de los bots en $BASE"
    exit 1
fi

# Mata cualquier instancia previa para evitar conflictos de getUpdates
pkill -f "python bot.py"       2>/dev/null
pkill -f "python bot_datos.py" 2>/dev/null
sleep 1

# Abre una ventana de Terminal para cada bot (macOS AppleScript)
osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$BASE/telegram_bot' && ./iniciar.sh"
    delay 0.5
    do script "cd '$BASE/telegram_bot_datos' && ./iniciar.sh"
end tell
EOF

echo "✓ Lanzadas dos ventanas de Terminal con los bots."
echo "  Para parar: cierra las ventanas o pulsa Ctrl+C en cada una."
