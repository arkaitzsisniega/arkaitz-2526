#!/bin/bash
# ────────────────────────────────────────────────────────────────
# Arranca el bot de datos (@InterFS_datos_bot).
# Para pararlo: Ctrl+C
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

source venv/bin/activate
echo "🤖 Arrancando bot de DATOS (@InterFS_datos_bot)…"
echo "   (Ctrl+C para parar)"
echo ""
exec python bot_datos.py
