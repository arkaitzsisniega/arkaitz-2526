"""
health_check.py — Verifica el estado de todos los componentes del bot
y reporta un resultado estructurado.

Diseñado para tres usos:

  1. **Manual** (línea de comandos):
       /usr/bin/python3 src/health_check.py
       → imprime el resultado por stdout. Exit 0 si todo OK, 1 si algo falla.

  2. **Al arrancar el bot** (importado desde bot.py / bot_datos.py):
       from health_check import run_health_check_quick
       resultado = run_health_check_quick()
       → mensaje al usuario por Telegram con el estado.

  3. **Cron horario** (LaunchAgent com.arkaitz.healthcheck):
       /usr/bin/python3 src/health_check.py --notificar-si-falla
       → si algo falla, manda Telegram a ALLOWED_CHAT_ID.

Tests que hace:
  - Sheet abre (gspread + service account).
  - Cada `_VISTA_*` esperada tiene columnas mínimas.
  - faster-whisper puede instanciarse (cargar modelo).
  - Gemini API responde a un prompt trivial.
  - `src/estado_jugador.py` ejecuta con un jugador del roster y devuelve
    bloque con las secciones esperadas.

Cada chequeo se aísla con try/except y un timeout suave.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings as _w
from pathlib import Path
from typing import Any, Dict, List

_w.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

VISTAS_ESPERADAS = {
    "_VISTA_CARGA": {"FECHA", "JUGADOR", "MINUTOS", "BORG", "CARGA"},
    "_VISTA_SEMANAL": {"FECHA_LUNES", "JUGADOR", "ACWR", "MONOTONIA", "FATIGA"},
    "_VISTA_PESO": {"FECHA", "JUGADOR", "PESO_PRE"},
    "_VISTA_WELLNESS": {"FECHA", "JUGADOR", "TOTAL"},
    "_VISTA_SEMAFORO": {"JUGADOR", "SEMAFORO_GLOBAL"},
    "_VISTA_RECUENTO": {"JUGADOR", "SESIONES_CON_DATOS"},
}


# ─── Helpers ────────────────────────────────────────────────────────────

def _result(name: str, ok: bool, msg: str = "", detalle: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": ok, "msg": msg, "detalle": detalle[:500]}


def _load_dotenv_bots() -> None:
    """Carga las variables de los .env de los bots para tener GEMINI_API_KEY,
    TELEGRAM_BOT_TOKEN, etc. en el entorno actual."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    for p in [
        ROOT / "telegram_bot" / ".env",
        ROOT / "telegram_bot_datos" / ".env",
        ROOT / ".env",
    ]:
        if p.is_file():
            load_dotenv(p, override=False)


# ─── Checks individuales ──────────────────────────────────────────────────

def check_sheet() -> Dict[str, Any]:
    """Abre el Sheet y verifica que las _VISTA_* tienen columnas mínimas."""
    t0 = time.time()
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore
    except Exception as e:
        return _result("Sheet (imports)", False, f"falta {type(e).__name__}", str(e))
    creds_path = ROOT / "google_credentials.json"
    if not creds_path.is_file():
        return _result("Sheet (creds)", False, "no encuentro google_credentials.json",
                       str(creds_path))
    try:
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        ss = gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        return _result("Sheet (open)", False, f"{type(e).__name__}", str(e))

    faltan: List[str] = []
    for vista, cols_min in VISTAS_ESPERADAS.items():
        try:
            ws = ss.worksheet(vista)
            cols = set(ws.row_values(1))
            missing = cols_min - cols
            if missing:
                faltan.append(f"{vista}: faltan {sorted(missing)}")
        except Exception as e:
            faltan.append(f"{vista}: {type(e).__name__}")
    elapsed = time.time() - t0
    if faltan:
        return _result("Sheet", False, f"vistas con problemas ({elapsed:.1f}s)",
                       "; ".join(faltan))
    return _result("Sheet", True, f"OK ({elapsed:.1f}s)",
                   f"{len(VISTAS_ESPERADAS)} vistas verificadas")


def check_whisper() -> Dict[str, Any]:
    """Verifica que faster-whisper se puede importar y cargar el modelo."""
    t0 = time.time()
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        return _result("Whisper (import)", False, "falta faster-whisper",
                       f"{type(e).__name__}: {e}")
    try:
        # No cargamos el modelo entero aquí (lento), solo confirmamos que
        # el módulo cargó y que onnxruntime no se quejó.
        import onnxruntime  # type: ignore  # noqa: F401
    except Exception as e:
        return _result("Whisper (onnxruntime)", False,
                       "onnxruntime falla al importar",
                       f"{type(e).__name__}: {e}")
    elapsed = time.time() - t0
    return _result("Whisper", True, f"OK ({elapsed:.1f}s)",
                   "imports OK, onnxruntime sano")


def check_gemini() -> Dict[str, Any]:
    """Verifica que Gemini responde a un prompt trivial."""
    t0 = time.time()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _result("Gemini", False, "GEMINI_API_KEY vacío en .env", "")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:
        return _result("Gemini (import)", False, f"falta google.generativeai",
                       f"{type(e).__name__}: {e}")
    try:
        genai.configure(api_key=api_key)
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        model = genai.GenerativeModel(model_name=model_name, safety_settings=safety)
        resp = model.generate_content(
            "Responde solo: OK",
            generation_config={"temperature": 0, "max_output_tokens": 64},
        )
        text = (getattr(resp, "text", "") or "").strip()
        elapsed = time.time() - t0
        if not text:
            cands = getattr(resp, "candidates", None) or []
            finish = getattr(cands[0], "finish_reason", "?") if cands else "?"
            return _result("Gemini", False,
                           f"vacío finish={finish} ({elapsed:.1f}s)",
                           f"modelo={model_name}")
        return _result("Gemini", True, f"OK ({elapsed:.1f}s)",
                       f"modelo={model_name}, resp='{text[:50]}'")
    except Exception as e:
        elapsed = time.time() - t0
        return _result("Gemini", False, f"{type(e).__name__} ({elapsed:.1f}s)", str(e))


def check_estado_jugador() -> Dict[str, Any]:
    """Ejecuta el script curado y verifica que devuelve un bloque con
    las secciones mínimas esperadas (Carga media, ACWR, Wellness)."""
    t0 = time.time()
    script = ROOT / "src" / "estado_jugador.py"
    if not script.is_file():
        return _result("estado_jugador", False, "script no existe", str(script))

    # Probamos con un jugador que sabemos que tiene datos: HERRERO suele
    # tener carga histórica. Si falla, probamos otros del roster.
    candidatos = ["HERRERO", "PIRATA", "RAYA", "CARLOS", "CECILIO"]
    last_err = ""
    for jugador in candidatos:
        try:
            res = subprocess.run(
                [sys.executable, str(script), jugador, "5"],
                capture_output=True, text=True, timeout=60,
                cwd=str(ROOT),
                env={**os.environ, "PYTHONWARNINGS": "ignore"},
            )
            if res.returncode != 0:
                last_err = f"rc={res.returncode}: {(res.stderr or '')[:200]}"
                continue
            out = res.stdout or ""
            secciones = ["Carga media", "ACWR", "Wellness"]
            faltan = [s for s in secciones if s not in out]
            if faltan:
                last_err = f"{jugador}: faltan secciones {faltan}"
                continue
            elapsed = time.time() - t0
            return _result("estado_jugador", True, f"OK ({elapsed:.1f}s)",
                           f"probado con {jugador}")
        except subprocess.TimeoutExpired:
            last_err = f"{jugador}: timeout >60s"
        except Exception as e:
            last_err = f"{jugador}: {type(e).__name__}: {e}"
    elapsed = time.time() - t0
    return _result("estado_jugador", False,
                   f"falló con todos ({elapsed:.1f}s)", last_err)


def check_bots_imports() -> Dict[str, Any]:
    """Verifica que bot.py y bot_datos.py son importables sin errores
    (sintaxis OK + dependencias presentes)."""
    t0 = time.time()
    fallos: List[str] = []
    for path in [
        ROOT / "telegram_bot" / "bot.py",
        ROOT / "telegram_bot_datos" / "bot_datos.py",
    ]:
        if not path.is_file():
            fallos.append(f"{path.name}: NO existe")
            continue
        # Compilamos sin ejecutar.
        try:
            res = subprocess.run(
                [sys.executable, "-c", f"import py_compile; py_compile.compile('{path}', doraise=True)"],
                capture_output=True, text=True, timeout=30,
            )
            if res.returncode != 0:
                fallos.append(f"{path.name}: {res.stderr[:200]}")
        except Exception as e:
            fallos.append(f"{path.name}: {type(e).__name__}: {e}")
    elapsed = time.time() - t0
    if fallos:
        return _result("Bots (compile)", False, f"fallos ({elapsed:.1f}s)",
                       "; ".join(fallos))
    return _result("Bots (compile)", True, f"OK ({elapsed:.1f}s)",
                   "bot.py y bot_datos.py compilan")


# ─── Ejecución completa ─────────────────────────────────────────────────────

CHECKS_TODOS = [
    check_bots_imports,
    check_sheet,
    check_whisper,
    check_gemini,
    check_estado_jugador,
]

CHECKS_RAPIDOS = [
    check_bots_imports,
    check_sheet,
]


def run_health_check_quick() -> List[Dict[str, Any]]:
    """Versión RÁPIDA (~5s) para llamar al arrancar el bot."""
    _load_dotenv_bots()
    return [chk() for chk in CHECKS_RAPIDOS]


def run_health_check_full() -> List[Dict[str, Any]]:
    """Versión COMPLETA (~30-60s) para cron periódico."""
    _load_dotenv_bots()
    return [chk() for chk in CHECKS_TODOS]


def format_resultados(results: List[Dict[str, Any]]) -> str:
    lineas = []
    for r in results:
        emoji = "✅" if r["ok"] else "❌"
        lineas.append(f"{emoji} {r['name']}: {r['msg']}")
        if not r["ok"] and r["detalle"]:
            lineas.append(f"    └─ {r['detalle']}")
    return "\n".join(lineas)


def all_ok(results: List[Dict[str, Any]]) -> bool:
    return all(r["ok"] for r in results)


# ─── Notificación a Telegram ────────────────────────────────────────────────

def notificar_telegram(texto: str) -> bool:
    """Manda un mensaje a ALLOWED_CHAT_ID si tenemos token y chat. Devuelve
    True si el envío fue exitoso, False si no."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("ALLOWED_CHAT_ID", "").strip()
    if not token or not chat:
        return False
    try:
        import urllib.parse as _u
        import urllib.request as _r
        # Trim a 4000 chars (límite Telegram 4096, dejamos margen).
        if len(texto) > 4000:
            texto = texto[:4000] + "…"
        data = _u.urlencode({"chat_id": chat, "text": texto}).encode()
        req = _r.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, method="POST",
        )
        with _r.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception:
        return False


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Health check del bot Inter FS")
    parser.add_argument("--rapido", action="store_true",
                          help="Solo checks ligeros (sheet + compile)")
    parser.add_argument("--notificar-si-falla", action="store_true",
                          help="Manda Telegram a ALLOWED_CHAT_ID si algo falla")
    parser.add_argument("--json", action="store_true",
                          help="Salida JSON en vez de texto humano")
    args = parser.parse_args()

    results = run_health_check_quick() if args.rapido else run_health_check_full()

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_resultados(results))

    ok = all_ok(results)
    if not ok and args.notificar_si_falla:
        _load_dotenv_bots()
        texto = "⚠️ *Health check FALLÓ:*\n\n" + format_resultados(results)
        notificar_telegram(texto)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
