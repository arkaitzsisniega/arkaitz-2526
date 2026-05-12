#!/bin/bash
# run_smoke.sh — Wrapper para ejecutar los smoke tests en local o server.
#
# Uso:
#   ./tests/run_smoke.sh            # ejecuta todos los tests
#   ./tests/run_smoke.sh --offline  # salta tests que necesitan Sheet

set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Preferimos el Python del venv del bot si existe (tiene gspread, etc.)
PY=""
for candidato in \
    "$HOME/Desktop/Arkaitz/telegram_bot/venv/bin/python" \
    "/usr/bin/python3" \
    "$(which python3)"; do
    if [ -x "$candidato" ]; then
        PY="$candidato"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "❌ No encuentro Python ejecutable"
    exit 1
fi

echo "🐍 Python: $PY"
echo "📁 Cwd:    $(pwd)"
echo ""

"$PY" tests/test_smoke.py "$@"
