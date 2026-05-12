#!/usr/bin/env python3
"""
auto_pull.py — Hace git pull cada N min (vía LaunchAgent) y, si trae
commits nuevos, reinicia los bots para que apliquen los cambios.

Versión Python del antiguo auto_pull.sh. Razón del cambio: en macOS con
TCC activo (Catalina+), launchd no permite que /bin/bash lea archivos
en ~/Desktop/ (sale "Operation not permitted" → exit 126). El Python del
venv del bot SÍ tiene esos permisos (porque el usuario los concedió en
algún momento al instalar los bots), así que usamos Python para todo.

Funciona igual:
  1. git pull --ff-only
  2. Si HEAD cambió: launchctl kickstart -k de cada bot vivo.
  3. Notifica por Telegram al chat autorizado.
  4. Log estructurado en logs/autopull.log.

Idempotente: si no hay cambios remotos, sale en silencio.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BASE = HOME / "Desktop" / "Arkaitz"
LOG_DIR = BASE / "logs"
LOG = LOG_DIR / "autopull.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        # Si no podemos escribir el log, no rompemos por ello.
        print(f"[{ts}] {msg}", file=sys.stderr)


def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run con capture_output y text=True por defecto."""
    return subprocess.run(
        cmd, capture_output=True, text=True, **kwargs,
    )


def leer_env_bot() -> tuple[str, str]:
    """Lee TELEGRAM_BOT_TOKEN y ALLOWED_CHAT_ID del .env del bot dev.
    Devuelve ("", "") si no encuentra credenciales."""
    env_file = BASE / "telegram_bot" / ".env"
    if not env_file.is_file():
        return "", ""
    token = chat = ""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("ALLOWED_CHAT_ID="):
                chat = line.split("=", 1)[1].strip().strip("\"'")
    except Exception as e:
        log(f"WARN: no puedo leer .env: {e}")
    return token, chat


def notificar_telegram(texto: str) -> bool:
    """Envía un mensaje a ALLOWED_CHAT_ID. Devuelve True si funcionó."""
    token, chat = leer_env_bot()
    if not token or not chat:
        return False
    # Trim Telegram (4096 max, dejamos margen).
    if len(texto) > 3800:
        texto = texto[:3800] + "…"
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat,
            "text": texto,
            "disable_notification": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, method="POST",
        )
        urllib.request.urlopen(req, timeout=20).read()
        return True
    except Exception as e:
        log(f"  ! fallo notificación Telegram: {e}")
        return False


def main() -> int:
    # ── Sanity checks ──
    if not (BASE / ".git").is_dir():
        log(f"ERROR: {BASE} no es un repo git. Aborto.")
        return 1

    try:
        os.chdir(BASE)
    except Exception as e:
        log(f"ERROR: cd {BASE} falló: {e}")
        return 1

    # ── git rev-parse HEAD antes del pull ──
    before_proc = run(["git", "rev-parse", "HEAD"])
    if before_proc.returncode != 0:
        log(f"ERROR: git rev-parse HEAD falló: {before_proc.stderr.strip()}")
        return 1
    before = before_proc.stdout.strip()

    # ── git pull ──
    pull_proc = run(["git", "pull", "--quiet", "--ff-only"])
    if pull_proc.returncode != 0:
        # No abortamos: puede ser un conflicto local. Reintentaremos en
        # 5 min. Logueamos para que se vea.
        log(f"WARN: git pull falló (rc={pull_proc.returncode}): "
            f"{pull_proc.stderr.strip()[:300]}")
        return 0

    after = run(["git", "rev-parse", "HEAD"]).stdout.strip()

    if before == after:
        # No hay cambios → salimos silenciosamente.
        return 0

    # ── Hay commits nuevos ──
    log_proc = run(["git", "log", "--oneline", f"{before}..{after}"])
    commits_str = log_proc.stdout.strip()
    commits_lines = [c for c in commits_str.splitlines() if c.strip()]
    nuevos = len(commits_lines)
    resumen = "\n".join(commits_lines[:5])

    log(f"✓ {nuevos} commits nuevos:")
    for c in commits_lines[:10]:
        log(f"    {c}")

    # ── Reiniciar bots activos ──
    user_id = os.getuid()
    list_out = run(["launchctl", "list"]).stdout
    reiniciados: list[str] = []
    for label in ["com.arkaitz.bot", "com.arkaitz.bot_datos", "com.arkaitz.gastos_bot"]:
        if label not in list_out:
            continue
        r = run(["launchctl", "kickstart", "-k", f"gui/{user_id}/{label}"])
        if r.returncode == 0:
            log(f"  → reiniciado {label}")
            reiniciados.append(label)
        else:
            log(f"  ! fallo reiniciando {label}: {r.stderr.strip()[:200]}")

    # ── Notificar por Telegram ──
    msg = (
        f"🔄 Bots actualizados ({nuevos} commits).\n"
        f"Reiniciados: {', '.join(reiniciados) if reiniciados else 'ninguno'}\n"
        f"Últimos:\n{resumen}"
    )
    if notificar_telegram(msg):
        log(f"  → notificación Telegram OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
