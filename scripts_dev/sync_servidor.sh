#!/bin/bash
# sync_servidor.sh — Verifica que todo está pusheado y muestra el estado
# del sync local→remoto→server. Si hay commits sin pushear, los pushea.
#
# Pensado para correr al final de una sesión de cambios, o cuando
# quieras asegurarte de que el server tiene tu código más reciente.
#
# Uso:
#   ./scripts_dev/sync_servidor.sh

set -e

cd "$(git rev-parse --show-toplevel)"

# 1. Ver si hay cambios sin commitear
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
if [ "$DIRTY" -gt 0 ]; then
    echo "⚠️  Hay $DIRTY archivos modificados sin commitear:"
    git status --short
    echo ""
    echo "   Commit primero (o stash) antes de sync."
    exit 1
fi

# 2. Fetch para comparar contra origin
git fetch --quiet origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "@{u}")
AHEAD=$(git rev-list --count "$REMOTE..$LOCAL")
BEHIND=$(git rev-list --count "$LOCAL..$REMOTE")

if [ "$AHEAD" -eq 0 ] && [ "$BEHIND" -eq 0 ]; then
    echo "✅ Local sincronizado con origin/main ($LOCAL)"
elif [ "$AHEAD" -gt 0 ] && [ "$BEHIND" -eq 0 ]; then
    echo "📤 $AHEAD commits locales sin pushear. Haciendo push…"
    git log --oneline "@{u}..HEAD"
    echo ""
    git push origin HEAD
    echo ""
    echo "✅ Pusheado a origin."
elif [ "$AHEAD" -eq 0 ] && [ "$BEHIND" -gt 0 ]; then
    echo "📥 $BEHIND commits nuevos en origin. Haciendo pull…"
    git pull --ff-only
elif [ "$AHEAD" -gt 0 ] && [ "$BEHIND" -gt 0 ]; then
    echo "⚠️  Divergencia: $AHEAD locales y $BEHIND remotos. Resuelve manualmente."
    exit 1
fi

echo ""
echo "💡 El server hará 'git pull' automáticamente en máximo 5 min"
echo "   (via auto_pull.sh + LaunchAgent com.arkaitz.autopull)."
echo "   Si quieres forzarlo ahora, en el server:"
echo "     ~/Desktop/Arkaitz/setup_servidor/auto_pull.sh"
