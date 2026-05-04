"""
oliver_login.py — Login automático en Oliver Sports vía HTTP.

Sin Playwright. Solo una request POST a /v1/auth/login con:
  - email
  - password
  - device_id (UUID estable, generado y guardado en .env)

Devuelve token (2h) + refresh_token (14 días) y los escribe en .env.

Variables .env necesarias:
  OLIVER_EMAIL     = email de la cuenta
  OLIVER_PASSWORD  = contraseña
  OLIVER_DEVICE_ID = UUID (se genera automáticamente la primera vez)

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
import uuid
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


def _asegurar_device_id(env: dict) -> str:
    """Devuelve el OLIVER_DEVICE_ID. Si no existe, lo genera y guarda."""
    did = env.get("OLIVER_DEVICE_ID", "").strip()
    if not did:
        did = str(uuid.uuid4())
        _guardar_env({"OLIVER_DEVICE_ID": did})
        print(f"🆕 OLIVER_DEVICE_ID generado y guardado en .env")
    return did


def oliver_login() -> bool:
    """Hace login en Oliver con email+password+device_id y guarda los
    tokens nuevos en .env. Devuelve True/False."""
    env = _leer_env()

    email = env.get("OLIVER_EMAIL", "").strip()
    password = env.get("OLIVER_PASSWORD", "").strip()
    if not email or not password:
        print("❌ Faltan OLIVER_EMAIL y/o OLIVER_PASSWORD en .env")
        print()
        print("Añade al final del archivo .env:")
        print("  OLIVER_EMAIL=tu-email@dominio.com")
        print("  OLIVER_PASSWORD=tu-contraseña")
        print()
        print("Después ejecuta:")
        print("  /usr/bin/python3 src/oliver_login.py")
        return False

    device_id = _asegurar_device_id(env)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-from": "portal",
        "x-version": OLIVER_VERSION,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3.1 "
            "Safari/605.1.15"),
        "Accept-Language": "es-ES,es;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
    }
    payload = {
        "email": email,
        "password": password,
        "device_id": device_id,
    }

    print(f"🔐 Login en Oliver con email {email[:3]}***@***")
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
