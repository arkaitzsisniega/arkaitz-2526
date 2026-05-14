#!/usr/bin/env python3
"""
smoke_gastos_bot.py — Tests rápidos del bot de gastos comunes.

Aunque el gastos_bot es personal (NO entra en los smoke tests del Inter),
desde que añadimos features no triviales (resumen automático + gastos
fijos via JobQueue) merece su propia red de seguridad — la regla de
memoria 'test antes de push' aplica también aquí.

Verifica:
  1. bot.py compila (sintaxis).
  2. gastos_fijos.py compila.
  3. bot.py import end-to-end con env vars mock.
  4. gastos_fijos: cargar_config sin fichero → []
  5. gastos_fijos: parser admite campo `meses`.
  6. gastos_fijos: _aplica_este_mes() respeta el filtro de meses.
  7. PLANTILLA JSON es válida.
  8. Funciones nuevas existen en bot.py (resumen post-apunte + job + cmd).
  9. Si hay gastos_fijos.json real, se valida también (datos del usuario).
 10. Compatibilidad: ZoneInfo importa (Python 3.9+ requerido).

Uso:
  /usr/bin/python3 tests/smoke_gastos_bot.py

Salida:
  exit 0 → todo OK.
  exit 1 → algo falla, con detalle de qué.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
GBOT_DIR = ROOT / "gastos_bot"
BOT_PY = GBOT_DIR / "bot.py"
GF_PY = GBOT_DIR / "gastos_fijos.py"
PLANTILLA = GBOT_DIR / "gastos_fijos_PLANTILLA.json"
JSON_REAL = GBOT_DIR / "gastos_fijos.json"

VERDE = "\033[32m"
ROJO = "\033[31m"
RESET = "\033[0m"

results: list[tuple[str, bool, str]] = []


def t(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = f"{VERDE}✓{RESET}" if ok else f"{ROJO}✗{RESET}"
    print(f"{mark} {name}")
    if not ok and detail:
        for line in detail.splitlines():
            print(f"    {line}")


# ─── 1, 2 — sintaxis ─────────────────────────────────────────────────────────
for fname, p in [("bot.py", BOT_PY), ("gastos_fijos.py", GF_PY)]:
    try:
        ast.parse(p.read_text(encoding="utf-8"))
        t(f"Sintaxis {fname}", True)
    except SyntaxError as e:
        t(f"Sintaxis {fname}", False, str(e))


# ─── 3 — import end-to-end de bot.py con env mock ───────────────────────────
def _import_e2e_botpy() -> tuple[bool, str]:
    """Lanza un subproceso Python que importa bot.py con env vars mock.
    Si revienta al cargar (f-string roto, NameError de módulo top-level,
    etc.) lo cazamos aquí en lugar de en producción."""
    import subprocess
    # Algunas deps externas (google.generativeai, faster_whisper) pueden no
    # estar en este Mac aunque sí estén en el servidor. Inyectamos stubs
    # para que la verificación valide NUESTRO código, no las deps externas.
    script = (
        "import os, sys, types; "
        # Stub de google.generativeai si no está
        "import importlib.util as _ilu; "
        "_g = _ilu.find_spec('google.generativeai'); "
        "_stub = types.ModuleType('google.generativeai') if _g is None else None; "
        "_stub.configure = lambda *a, **k: None if _stub else None; "
        "_stub.GenerativeModel = (lambda *a, **k: type('M', (), {'generate_content': lambda self, *a, **k: type('R', (), {'candidates': []})()})()) if _stub else None; "
        "(sys.modules.setdefault('google.generativeai', _stub)) if _stub else None; "
        # faster_whisper opcional
        "_w = _ilu.find_spec('faster_whisper'); "
        "_fwstub = types.ModuleType('faster_whisper') if _w is None else None; "
        "(setattr(_fwstub, 'WhisperModel', type('W', (), {})) if _fwstub else None); "
        "(sys.modules.setdefault('faster_whisper', _fwstub)) if _fwstub else None; "
        f"sys.path.insert(0, {str(GBOT_DIR)!r}); "
        "os.environ.update({"
        "'TELEGRAM_BOT_TOKEN': 'x', "
        "'GASTOS_SHEET_ID': 'x', "
        "'ALLOWED_CHAT_IDS': '1', "
        "'NOMBRES_USUARIOS': '1=Test', "
        "}); "
        "import bot; "
        "print('OK')"
    )
    try:
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Timeout >30s (carga de modelos pesados?)"
    if out.returncode != 0:
        # Filtra warnings ruidosos
        err = out.stderr.strip()
        # Acepta avisos de google-auth EOL y urllib3 (no crítico)
        lineas = [l for l in err.splitlines()
                  if "FutureWarning" not in l and "NotOpenSSLWarning" not in l
                  and "EOL" not in l and "google-auth" not in l
                  and "urllib3" not in l and not l.startswith("  warnings")]
        relevante = "\n".join(lineas[-10:])
        return False, relevante or err[-500:]
    return True, ""


ok, det = _import_e2e_botpy()
t("Import e2e gastos_bot/bot.py", ok, det)


# ─── 4-6 — gastos_fijos.py ───────────────────────────────────────────────────
sys.path.insert(0, str(GBOT_DIR))
try:
    import gastos_fijos as gf
    t("gastos_fijos.py importa", True)
except Exception as e:
    t("gastos_fijos.py importa", False, str(e))
    gf = None

if gf is not None:
    # cargar_config sin archivo → []
    orig_file = gf.CONFIG_FILE
    gf.CONFIG_FILE = Path("/tmp/no_existe_42.json")
    try:
        cfg = gf.cargar_config()
        t("cargar_config sin archivo → []", cfg == [], f"got {cfg!r}")
    finally:
        gf.CONFIG_FILE = orig_file

    # _aplica_este_mes con meses
    gasto_mensual = {"concepto": "X", "cantidad": 10}
    gasto_trimestral = {"concepto": "Y", "cantidad": 20, "meses": [1, 4, 7, 10]}
    casos = [
        (gasto_mensual, 1, True),
        (gasto_mensual, 5, True),
        (gasto_mensual, 12, True),
        (gasto_trimestral, 1, True),
        (gasto_trimestral, 4, True),
        (gasto_trimestral, 7, True),
        (gasto_trimestral, 10, True),
        (gasto_trimestral, 2, False),
        (gasto_trimestral, 5, False),
        (gasto_trimestral, 6, False),
        (gasto_trimestral, 11, False),
        (gasto_trimestral, 12, False),
    ]
    errs = []
    for g, mes, esperado in casos:
        got = gf._aplica_este_mes(g, mes)
        if got != esperado:
            errs.append(f"  {g['concepto']} mes={mes}: esperaba {esperado}, dio {got}")
    t(f"_aplica_este_mes — {len(casos)} casos", not errs, "\n".join(errs))


# ─── 7 — PLANTILLA es JSON válido ────────────────────────────────────────────
try:
    with PLANTILLA.open(encoding="utf-8") as fh:
        d = json.load(fh)
    fijos = d.get("gastos_fijos") or []
    ok = isinstance(fijos, list) and len(fijos) >= 2 and \
         all(g.get("concepto") and g.get("cantidad") is not None for g in fijos)
    t("PLANTILLA JSON válida", ok,
      f"gastos en plantilla: {len(fijos)}; tipos: {[type(g).__name__ for g in fijos]}")
except Exception as e:
    t("PLANTILLA JSON válida", False, str(e))


# ─── 8 — funciones nuevas existen en bot.py ─────────────────────────────────
tree = ast.parse(BOT_PY.read_text(encoding="utf-8"))
funcs = {n.name for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
must_have = [
    "_enviar_resumen_post_apunte",
    "_job_aplicar_gastos_fijos",
    "_chequear_gastos_fijos_al_arrancar",
    "cmd_gastos_fijos",
]
faltan = [f for f in must_have if f not in funcs]
t(f"Funciones nuevas en bot.py ({len(must_have)})", not faltan,
  f"faltan: {faltan}" if faltan else "")


# ─── 9 — gastos_fijos.json del usuario (si existe) ──────────────────────────
if JSON_REAL.is_file() and gf is not None:
    cfg = gf.cargar_config()
    ok = len(cfg) > 0 and all(g.get("concepto") and g.get("cantidad") for g in cfg)
    t(f"gastos_fijos.json real válido ({len(cfg)} gastos)", ok,
      "vacío o malformado" if not ok else "")
else:
    t("gastos_fijos.json del usuario — opcional, no presente", True,
      "(no es error: el archivo es personal y solo está en local)")


# ─── 10 — zoneinfo disponible (necesario para JobQueue Madrid) ──────────────
try:
    from zoneinfo import ZoneInfo
    z = ZoneInfo("Europe/Madrid")
    t("ZoneInfo('Europe/Madrid') disponible", True)
except Exception as e:
    t("ZoneInfo('Europe/Madrid') disponible", False,
      f"{type(e).__name__}: {e}. JobQueue caerá a UTC.")


# ─── Resumen ─────────────────────────────────────────────────────────────────
print()
print("═" * 60)
fallan = [r for r in results if not r[1]]
if fallan:
    print(f"{ROJO}✗ FALLAN {len(fallan)} de {len(results)} tests{RESET}")
    sys.exit(1)
else:
    print(f"{VERDE}✓ TODOS los tests del gastos_bot pasaron ({len(results)}/{len(results)}).{RESET}")
    sys.exit(0)
