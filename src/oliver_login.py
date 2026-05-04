"""
oliver_login.py — Login automático en Oliver Sports vía HTTP.

Replica EXACTAMENTE el payload que envía el frontend de Oliver:
  POST /v1/auth/login  con  {"user_name": ..., "password": ...}

(El frontend tiene una función n(e){e()} que es un placeholder de
reCAPTCHA, pero al llamarse n(i) sin argumentos, rc_token queda
undefined y se omite del JSON. Por tanto solo van user_name y password.)

Devuelve token (2h) + refresh_token (14 días) y los escribe en .env.

Variables .env necesarias:
  OLIVER_USER_NAME = el username de Oliver (ej. "Txubas").
                       También acepta OLIVER_EMAIL por compatibilidad
                       con la versión inicial del .env.
  OLIVER_PASSWORD  = contraseña

Uso:
  /usr/bin/python3 src/oliver_login.py            # login y guardar tokens
  /usr/bin/python3 src/oliver_login.py --force    # ignora token actual

API pública (importable):
  ok = oliver_login()  → True/False, escribe tokens al .env
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OLIVER_API = "https://api-prod.tryoliver.com/v1"
OLIVER_VERSION = "2.0.37"


def _leer_env() -> dict:
    """Lee el .env como dict. Devuelve {} si no existe."""
    out = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        ln = line.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _guardar_env(claves: dict) -> None:
    """Actualiza/añade las claves al .env preservando el resto.
    No comparte ni imprime los valores."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    escritas = set()
    for ln in lines:
        ln_str = ln.strip()
        replaced = False
        for k, v in claves.items():
            if ln_str.startswith(f"{k}="):
                out.append(f"{k}={v}")
                escritas.add(k)
                replaced = True
                break
        if not replaced:
            out.append(ln)
    # Añadir las que no estaban
    for k, v in claves.items():
        if k not in escritas:
            out.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def oliver_login() -> bool:
    """Hace login en Oliver con user_name+password y guarda los
    tokens nuevos en .env. Devuelve True/False."""
    env = _leer_env()

    # Acepta OLIVER_USER_NAME (nuevo) o OLIVER_EMAIL (legacy) por compat.
    user = (env.get("OLIVER_USER_NAME", "").strip()
            or env.get("OLIVER_EMAIL", "").strip())
    password = env.get("OLIVER_PASSWORD", "").strip()
    if not user or not password:
        print("❌ Faltan OLIVER_USER_NAME y/o OLIVER_PASSWORD en .env")
        print()
        print("Añade al final del archivo .env:")
        print("  OLIVER_USER_NAME=Tu_usuario_de_Oliver")
        print("  OLIVER_PASSWORD=tu-contraseña")
        print()
        print("Después ejecuta:")
        print("  /usr/bin/python3 src/oliver_login.py")
        return False

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # IMPORTANTE: el frontend SOLO manda user_name + password.
    # El "rc_token" que aparece en el código del frontend queda undefined
    # cuando el form se envía (función n(i) llama a i() sin argumentos),
    # y JSON.stringify omite los undefined → no llega al backend.
    payload = {
        "user_name": user,
        "password": password,
    }

    print(f"🔐 Login en Oliver con usuario {user[:3]}***")
    try:
        r = requests.post(f"{OLIVER_API}/auth/login",
                            headers=headers, json=payload, timeout=15)
    except Exception as e:
        print(f"❌ Error de red: {type(e).__name__}: {e}")
        return False

    if r.status_code == 423:
        print("❌ HTTP 423 Too Many Attempts. Espera unos minutos antes de "
              "reintentar (probablemente has hecho muchos logins fallidos "
              "recientemente).")
        return False
    if r.status_code == 401 or r.status_code == 403:
        print(f"❌ HTTP {r.status_code} — credenciales incorrectas. "
              f"Revisa OLIVER_EMAIL y OLIVER_PASSWORD en .env")
        print(f"   Respuesta: {r.text[:200]}")
        return False
    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text[:200]}")
        return False

    try:
        data = r.json()
    except Exception:
        print(f"❌ Respuesta no es JSON: {r.text[:200]}")
        return False

    if not data.get("success"):
        print(f"❌ success=False. Error: {data.get('error', '?')}")
        return False

    token = data.get("token")
    refresh = data.get("refresh_token")
    user_id = data.get("user", {}).get("user_id") or data.get("user_id")

    if not token or not refresh:
        print(f"❌ Respuesta sin token / refresh_token. Keys: {list(data.keys())}")
        return False

    nuevos = {"OLIVER_TOKEN": token, "OLIVER_REFRESH_TOKEN": refresh}
    if user_id:
        nuevos["OLIVER_USER_ID"] = str(user_id)
    _guardar_env(nuevos)

    print("✅ Login OK. Tokens guardados en .env")
    print(f"   user_id: {user_id}")
    print(f"   token: {token[:20]}…")
    print(f"   refresh: {refresh[:20]}…")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                     help="Ignora cualquier token actual y fuerza login.")
    ap.parse_args()
    ok = oliver_login()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
