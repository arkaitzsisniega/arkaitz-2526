#!/bin/bash
# install.sh — Instala los 3 bots como servicios launchd en macOS.
# Ejecutar UNA SOLA VEZ tras configurar el Mac viejo.
#
# Pasos previos:
#   1. Tener el repo clonado en /Users/mac/Desktop/Arkaitz/
#   2. Tener google_credentials.json y .env configurados
#   3. Probar manualmente con ./arrancar_bots.sh que todo funciona

set -e

BASE="$HOME/Desktop/Arkaitz"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$BASE/logs"

if [ ! -d "$BASE" ]; then
    echo "❌ No existe $BASE. Clona el repo primero."
    exit 1
fi

# Crear carpeta de logs
mkdir -p "$LOG_DIR"
echo "📁 Logs: $LOG_DIR"

# Copiar los .plist
mkdir -p "$LAUNCH_DIR"
for f in com.arkaitz.bot com.arkaitz.bot_datos com.arkaitz.gastos_bot; do
    src="$BASE/setup_servidor/${f}.plist"
    dst="$LAUNCH_DIR/${f}.plist"
    if [ ! -f "$src" ]; then
        echo "⚠️  No existe $src, saltando."
        continue
    fi
    cp "$src" "$dst"
    echo "✅ Copiado: $dst"

    # Cargar (descargar primero por si ya estaba activo, ignorar error)
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    echo "🚀 Activado: $f"
done

echo ""
echo "Estado:"
launchctl list | grep arkaitz || echo "  (vacío - revisar logs)"

echo ""
echo "Para parar un bot:    launchctl unload ~/Library/LaunchAgents/com.arkaitz.<nombre>.plist"
echo "Para arrancarlo:      launchctl load ~/Library/LaunchAgents/com.arkaitz.<nombre>.plist"
echo "Logs en:              $LOG_DIR"
echo ""
echo "✅ Setup completo. Los bots arrancarán automáticamente al iniciar sesión."
