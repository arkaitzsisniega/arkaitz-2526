#!/bin/bash
# watchdog.sh — Comprueba si los bots están corriendo y los relanza si no.
# Pensado para correr cada minuto desde crontab (* * * * *).
#
# Uso: añadir a crontab:
#   * * * * * /Users/arkaitz/Desktop/Arkaitz/setup_servidor/watchdog.sh
#
# El script comprueba cada bot listado en BOTS y, si su proceso no aparece
# en `pgrep`, lo relanza con nohup. Logs van al log normal del bot.

BASE="$HOME/Desktop/Arkaitz"
LOG_DIR="$BASE/logs"
mkdir -p "$LOG_DIR"

# Bots a vigilar: nombre_corto:subdir:script
BOTS=(
    "bot_datos:telegram_bot_datos:bot_datos.py"
    "bot:telegram_bot:bot.py"
    "gastos_bot:gastos_bot:bot.py"
)

for entry in "${BOTS[@]}"; do
    name_short="${entry%%:*}"
    rest="${entry#*:}"
    subdir="${rest%%:*}"
    script="${rest##*:}"

    bot_dir="$BASE/$subdir"
    venv_py="$bot_dir/venv/bin/python"
    script_path="$bot_dir/$script"
    log_file="$LOG_DIR/${name_short}.log"

    # Si no existe el venv o el script, saltar (bot no instalado aún)
    [ -x "$venv_py" ] || continue
    [ -f "$script_path" ] || continue

    # ¿Está corriendo el bot? buscamos el path completo del script
    if pgrep -f "$script_path" > /dev/null 2>&1; then
        continue
    fi

    # No está → lanzarlo
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] watchdog: relanzando $name_short" >> "$log_file"
    cd "$bot_dir" || continue
    nohup "$venv_py" "$script_path" >> "$log_file" 2>&1 &
    disown
done
