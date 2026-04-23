#!/bin/bash
# ────────────────────────────────────────────────────────────────
# Arranca el bot de Telegram.
# Para pararlo: pulsa Ctrl+C en la terminal.
# ────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
    echo "❌ No encuentro el archivo .env."
    echo "   Copia .env.example como .env y rellena los campos."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "⚠️  Falta el entorno virtual. Creándolo ahora…"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

# Activa el venv y arranca
source venv/bin/activate
echo "🤖 Arrancando bot de Telegram…"
echo "   (Ctrl+C para parar)"
echo ""
exec python bot.py
