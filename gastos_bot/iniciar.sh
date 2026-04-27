#!/bin/bash
# Arranca el bot de Gastos Comunes en primer plano.
# Para arrancarlo en background al encender el Mac, hacer un launchd después.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PY=/usr/bin/python3
"$PY" -m pip install -q -r requirements.txt
exec "$PY" bot.py
