#!/bin/bash
# install.sh — Instala los 3 bots como servicios launchd en macOS.
# Genera los .plist al vuelo usando $HOME y los venvs de cada bot,
# así sirve igual en el Mac de oficina (user `mac`) como en el Mac
# viejo servidor (user `arkaitz`).
#
# Pasos previos:
#   1. Repo clonado en ~/Desktop/Arkaitz/
#   2. google_credentials.json y .env (uno por bot) configurados
#   3. venv creado en cada bot con sus dependencias instaladas
#   4. Probado manualmente que cada bot arranca con ./iniciar.sh
#
# Uso:
#   ./install.sh           → instala los 3 bots
#   ./install.sh bot_datos → instala solo el bot de datos
#   ./install.sh bot       → instala solo el bot dev
#   ./install.sh gastos    → instala solo el de gastos

set -e

BASE="$HOME/Desktop/Arkaitz"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$BASE/logs"

if [ ! -d "$BASE" ]; then
    echo "❌ No existe $BASE. Clona el repo primero."
    exit 1
fi

# Crear carpetas necesarias
mkdir -p "$LOG_DIR" "$LAUNCH_DIR"
echo "📁 Logs: $LOG_DIR"

# Mapeo bot → carpeta + script
declare -a BOTS
BOTS=(
    "bot:telegram_bot:bot.py"
    "bot_datos:telegram_bot_datos:bot_datos.py"
    "gastos_bot:gastos_bot:bot.py"
)

# Si pasaron filtro por argumento, lo aplicamos
FILTRO="$1"

genera_plist() {
    local label_corto="$1"   # bot, bot_datos, gastos_bot
    local subdir="$2"        # telegram_bot, telegram_bot_datos, gastos_bot
    local script="$3"        # bot.py / bot_datos.py
    local label="com.arkaitz.${label_corto}"

    local bot_dir="$BASE/$subdir"
    local venv_py="$bot_dir/venv/bin/python"
    local script_path="$bot_dir/$script"
    local plist_path="$LAUNCH_DIR/${label}.plist"

    if [ ! -x "$venv_py" ]; then
        echo "⚠️  $label_corto: no encuentro venv en $venv_py — saltando."
        return 1
    fi
    if [ ! -f "$script_path" ]; then
        echo "⚠️  $label_corto: no encuentro $script_path — saltando."
        return 1
    fi

    cat > "$plist_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${venv_py}</string>
        <string>${script_path}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${bot_dir}</string>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${label_corto}.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${label_corto}.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLIST

    echo "✅ Plist generado: $plist_path"

    # (Re)cargar
    launchctl unload "$plist_path" 2>/dev/null || true
    launchctl load -w "$plist_path"
    echo "🚀 Activado: $label_corto"
}

for entry in "${BOTS[@]}"; do
    label_corto="${entry%%:*}"
    rest="${entry#*:}"
    subdir="${rest%%:*}"
    script="${rest##*:}"

    if [ -n "$FILTRO" ] && [ "$FILTRO" != "$label_corto" ]; then
        continue
    fi

    genera_plist "$label_corto" "$subdir" "$script" || true
done

echo ""
echo "Estado:"
launchctl list | grep arkaitz || echo "  (vacío — revisa los logs)"

echo ""
echo "Para parar un bot:    launchctl unload ~/Library/LaunchAgents/com.arkaitz.<nombre>.plist"
echo "Para arrancarlo:      launchctl load -w ~/Library/LaunchAgents/com.arkaitz.<nombre>.plist"
echo "Para ver el log:      tail -f $LOG_DIR/<nombre>.err.log"
echo ""
echo "✅ Setup completo. Los bots arrancarán automáticamente al iniciar sesión."
