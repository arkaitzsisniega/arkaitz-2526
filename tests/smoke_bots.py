"""
smoke_bots.py — Suite de smoke tests para los dos bots de Telegram.

Verifica:
1. Que ambos bots compilan (sintaxis OK).
2. Que ambos pueden hacer import end-to-end con env vars mock.
3. Que el cinturón de seguridad bloquea operaciones peligrosas y NO
   bloquea operaciones legítimas (15+13 casos).
4. Que los detectores de intent matchean correctamente.
5. Que los scripts curados funcionan con args válidos y manejan args
   inválidos sin crashear.
6. Que el SYSTEM_PROMPT no tiene f-string roto.

Uso:
  /usr/bin/python3 tests/smoke_bots.py

Salida:
  ✓ todas las pruebas → exit 0.
  ✗ alguna falla → exit 1 con detalle de qué falló.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
BOT_DEV = ROOT / "telegram_bot" / "bot.py"
BOT_DATOS = ROOT / "telegram_bot_datos" / "bot_datos.py"
VENV_DEV = ROOT / "telegram_bot" / "venv" / "bin" / "python"
VENV_DATOS = ROOT / "telegram_bot_datos" / "venv" / "bin" / "python"

ENV_MOCK = {
    "GEMINI_API_KEY": "fake_key",
    "TELEGRAM_BOT_TOKEN": "fake:AAA",
    "ALLOWED_CHAT_IDS": "6357476517",
    "ALLOWED_CHAT_ID": "6357476517",
}

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m⚠\033[0m"

fallos = []


def run_test(nombre, func):
    try:
        func()
        print(f"{OK} {nombre}")
    except AssertionError as e:
        print(f"{FAIL} {nombre}")
        print(f"   {e}")
        fallos.append(nombre)
    except Exception as e:
        print(f"{FAIL} {nombre} ({type(e).__name__}: {e})")
        fallos.append(nombre)


def test_sintaxis_bot_dev():
    import ast
    ast.parse(BOT_DEV.read_text())


def test_sintaxis_bot_datos():
    import ast
    ast.parse(BOT_DATOS.read_text())


def test_import_e2e_bot_datos():
    env = {**os.environ, **ENV_MOCK}
    code = """
import sys, warnings; sys.path.insert(0, '.'); warnings.filterwarnings('ignore')
import importlib.util
spec = importlib.util.spec_from_file_location('m','bot_datos.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print('OK')
"""
    r = subprocess.run([str(VENV_DATOS), "-c", code], cwd=str(BOT_DATOS.parent),
                          env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "OK" in r.stdout, f"stderr: {r.stderr[-400:]}"


def test_import_e2e_bot_dev():
    env = {**os.environ, **ENV_MOCK}
    code = """
import sys, warnings; sys.path.insert(0, '.'); warnings.filterwarnings('ignore')
import importlib.util
spec = importlib.util.spec_from_file_location('m','bot.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print('OK')
"""
    r = subprocess.run([str(VENV_DEV), "-c", code], cwd=str(BOT_DEV.parent),
                          env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "OK" in r.stdout, f"stderr: {r.stderr[-400:]}"


def _validar(code: str) -> str | None:
    """Llama al validador del bot_datos. None = legítimo, str = bloqueado."""
    env = {**os.environ, **ENV_MOCK}
    script = f"""
import sys, warnings; sys.path.insert(0, '.'); warnings.filterwarnings('ignore')
import importlib.util
spec = importlib.util.spec_from_file_location('m','bot_datos.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
res = mod._validar_solo_lectura_python({code!r})
print('NONE' if res is None else 'BLOCK')
"""
    r = subprocess.run([str(VENV_DATOS), "-c", script],
                          cwd=str(BOT_DATOS.parent), env=env,
                          capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, f"validador crash: {r.stderr[-300:]}"
    return None if "NONE" in r.stdout else "BLOCK"


def test_cinturon_bloquea_escrituras():
    casos_bloquear = [
        'ws.update("A1", values)',
        'sheet.update("B2", v)',
        'ss.worksheet("X").update("A1", v)',
        'ws.clear()',
        'ws.resize(100, 20)',
        'ws.format("A1:Z", {})',
        'ss.share("x@y.com", role="editor")',
        'df.to_csv("out.csv")',
        'df.to_excel("out.xlsx")',
        'requests.post(url, data=x)',
        'requests.delete(url)',
        'import socket; s = socket.socket()',
        'os.system("ls")',
        'subprocess.run(["rm", "-rf", "/"])',
        'exec("import os; os.remove(\\"x\\")")',
    ]
    for c in casos_bloquear:
        r = _validar(c)
        assert r == "BLOCK", f"NO bloqueado (debería): {c!r}"


def test_cinturon_permite_lecturas():
    casos_permitir = [
        'df = pd.DataFrame(ws.get_all_records())',
        'df.update({"col": vals})',
        'd = {}; d.update({"a": 1})',
        'df = df.copy()',
        'df.merge(other)',
        'df.insert(0, "col", v)',
        'fmt = df.to_string()',
        's = df.to_json()',
        'v = df.to_dict()',
        'r = requests.get(url)',
        'ws = ss.worksheet("X")',
    ]
    for c in casos_permitir:
        r = _validar(c)
        assert r != "BLOCK", f"FALSO POSITIVO (legítimo): {c!r}"


def test_scripts_curados_ejecutan():
    """Verifica que cada script curado se ejecuta sin crashear (con args
    sensatos). Hace una pausa entre llamadas para evitar el rate limit
    de Google Sheets (60 lecturas/min/usuario)."""
    import time
    scripts = [
        ("estado_jugador.py", ["PIRATA", "5"]),
        ("ranking_temporada.py", ["goles"]),
        ("ranking_temporada.py", ["asistencias", "LIGA"]),
        ("lesiones_activas.py", []),
        ("lesiones_activas.py", ["--por-dorsal"]),
        ("carga_ultima_sesion.py", []),
        ("carga_ultima_sesion.py", ["2026-05-09"]),
    ]
    rate_limit_hits = 0
    for i, (nombre, args) in enumerate(scripts):
        path = ROOT / "src" / nombre
        r = subprocess.run(["/usr/bin/python3", "-W", "ignore", str(path), *args],
                              capture_output=True, text=True, timeout=60)
        if r.returncode != 0 and "Quota exceeded" in (r.stderr + r.stdout):
            # 429 → tolerado, no es bug del código
            rate_limit_hits += 1
            print(f"   {WARN} rate limit en {nombre} (Google 429), no es bug")
        else:
            assert r.returncode == 0, f"{nombre} {args}: exit={r.returncode}, stderr={r.stderr[-200:]}"
        if i < len(scripts) - 1:
            time.sleep(2)  # respeta rate limit Sheets
    assert rate_limit_hits < 4, f"Demasiados 429 ({rate_limit_hits}): puede haber problema real"


def test_scripts_args_invalidos_no_crashean():
    casos = [
        ("estado_jugador.py", ["PIRATA", "abc"]),  # N inválido
        ("estado_jugador.py", ["NOEXISTE"]),       # jugador inválido
        ("ranking_temporada.py", ["xyz"]),         # categoría inválida
        ("ranking_temporada.py", ["goles", "XYZ_LIGA"]),  # competición inválida
        ("carga_ultima_sesion.py", ["1999-01-01"]),  # fecha sin datos
    ]
    for nombre, args in casos:
        path = ROOT / "src" / nombre
        r = subprocess.run(["/usr/bin/python3", "-W", "ignore", str(path), *args],
                              capture_output=True, text=True, timeout=60)
        # Aceptar exit 0 (con mensaje útil) o exit ≤ 2 (error controlado)
        assert r.returncode <= 2, f"{nombre} {args}: exit={r.returncode} (debería manejarlo)"
        # NO debe haber traceback en stderr
        assert "Traceback" not in r.stderr, f"{nombre} {args}: crashea con traceback"


def test_intent_detectors():
    """Verifica que los detectores de intent matchean los casos clave."""
    env = {**os.environ, **ENV_MOCK}
    script = """
import sys, warnings; sys.path.insert(0, '.'); warnings.filterwarnings('ignore')
import importlib.util
spec = importlib.util.spec_from_file_location('m','bot_datos.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
tests = [
    ('lesiones activas',         'lesiones'),
    ('quien esta lesionado',     'lesiones'),
    ('lista de asistencias en liga',  'ranking'),
    ('ranking goleadores',       'ranking'),
    ('carga jugador por jugador de ayer',  'carga'),
    ('borg del entreno del 13 de mayo',  'carga'),
    ('estado de Pirata',         'estado'),
    ('goles de Pirata',          'goles_jugador'),
    ('cuantos goles ha metido Raya',  'goles_jugador'),
    ('Javi goles en liga',       'goles_jugador'),
]
results = []
for prompt, expected in tests:
    if mod._detectar_intent_lesiones(prompt): m = 'lesiones'
    elif mod._detectar_intent_goles_jugador(prompt) is not None: m = 'goles_jugador'
    elif mod._detectar_intent_ranking(prompt) is not None: m = 'ranking'
    elif mod._detectar_intent_carga_ultima(prompt) is not None: m = 'carga'
    elif mod._detectar_intent_estado(prompt) is not None: m = 'estado'
    else: m = 'LLM'
    results.append((prompt, expected, m, m == expected))
fallos = [r for r in results if not r[3]]
if fallos:
    for prompt, expected, actual, _ in fallos:
        print(f'FAIL: {prompt!r} → {actual} (esperaba {expected})')
    sys.exit(1)
print('TODOS OK')
"""
    r = subprocess.run([str(VENV_DATOS), "-c", script],
                          cwd=str(BOT_DATOS.parent), env=env,
                          capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"stdout: {r.stdout[-400:]}\nstderr: {r.stderr[-400:]}"


def test_system_prompt_no_fstring_roto():
    """Verifica que SYSTEM_PROMPT NO tiene `{var}` con var no definida."""
    # Si fuera f-string roto, el import end-to-end ya habría fallado.
    # Test redundante pero explícito. Buscamos placeholders fuera de
    # `{PROJECT_DIR}` y `{{...}}` (escapados).
    import re
    for ruta in (BOT_DEV, BOT_DATOS):
        src = ruta.read_text()
        # Buscar bloques f"""...""" o f"...."
        m = re.search(r'(SYSTEM_PROMPT\w*\s*=\s*f"""(.*?)""")', src, re.DOTALL)
        if not m:
            continue
        bloque = m.group(2)
        # Quitar dobles llaves escapadas
        s = bloque.replace("{{", "").replace("}}", "")
        # Buscar {algo} que no sea PROJECT_DIR
        invalid = re.findall(r"\{([^{}]+?)\}", s)
        invalid = [v for v in invalid if v.strip() not in ("PROJECT_DIR",)
                   and not v.startswith(" ")]
        assert not invalid, f"{ruta.name}: f-string con placeholders desconocidos: {invalid[:5]}"


# ─── Runner ────────────────────────────────────────────────────────────────────
TESTS = [
    ("Sintaxis bot.py (Alfred)",        test_sintaxis_bot_dev),
    ("Sintaxis bot_datos.py",           test_sintaxis_bot_datos),
    ("Import e2e bot_datos",            test_import_e2e_bot_datos),
    ("Import e2e bot.py (Alfred)",      test_import_e2e_bot_dev),
    ("Cinturón bloquea 15 casos de escritura",     test_cinturon_bloquea_escrituras),
    ("Cinturón permite 11 casos legítimos",        test_cinturon_permite_lecturas),
    ("Scripts curados ejecutan con args válidos",  test_scripts_curados_ejecutan),
    ("Scripts curados manejan args inválidos",     test_scripts_args_invalidos_no_crashean),
    ("Intent detectors matchean correctamente",    test_intent_detectors),
    ("SYSTEM_PROMPT sin f-string roto",            test_system_prompt_no_fstring_roto),
]


def main():
    print("═" * 60)
    print("  SMOKE TESTS BOTS  ·  Movistar Inter FS")
    print("═" * 60)
    print()
    for nombre, func in TESTS:
        run_test(nombre, func)
    print()
    print("═" * 60)
    if fallos:
        print(f"{FAIL} {len(fallos)} test(s) FALLARON:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"{OK} TODOS los tests pasaron.")
        sys.exit(0)


if __name__ == "__main__":
    main()
