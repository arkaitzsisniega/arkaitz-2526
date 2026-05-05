#!/bin/bash
# uninstall.sh — Desactiva los bots launchd y borra los .plist.
# Útil si quieres revertir el setup o probar de cero.

set -e
LAUNCH_DIR="$HOME/Library/LaunchAgents"

for f in com.arkaitz.bot com.arkaitz.bot_datos com.arkaitz.gastos_bot; do
    plist="$LAUNCH_DIR/${f}.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm "$plist"
        echo "🗑  Eliminado: $f"
    else
        echo "ℹ️  No estaba: $f"
    fi
done

echo ""
echo "Estado:"
launchctl list | grep arkaitz || echo "  ✅ Limpio (sin servicios arkaitz cargados)"
