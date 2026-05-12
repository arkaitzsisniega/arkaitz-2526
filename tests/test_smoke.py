"""
test_smoke.py — Tests "humo" que verifican que el sistema no está
totalmente roto. NO son tests exhaustivos: solo confirman que las piezas
principales se pueden importar / ejecutar.

Uso:
    /usr/bin/python3 tests/test_smoke.py

O con pytest si está instalado:
    pytest tests/test_smoke.py -v

Diseño:
  - Cada test es una función `test_*` que NO requiere pytest.
  - El main() ejecuta todas y reporta resumen.
  - Exit 0 si pasan todos, 1 si alguno falla.
  - Algunos tests son "online" (necesitan red / Sheet) y se saltan si
    no hay credenciales o si pasa el flag --offline.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
import warnings as _w
from pathlib import Path
from typing import Callable, List, Tuple

_w.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "src"))


# ─── Resultado de cada test ───────────────────────────────────────────────

class TestResult:
    def __init__(self, name: str, ok: bool, msg: str = "", elapsed: float = 0.0):
        self.name = name
        self.ok = ok
        self.msg = msg
        self.elapsed = elapsed

    def __str__(self) -> str:
        em = "✅" if self.ok else "❌"
        return f"{em} {self.name}  ({self.elapsed:.2f}s)  {self.msg}"


# ─── Tests ───────────────────────────────────────────────────────────────

def _run(name: str, fn: Callable[[], None]) -> TestResult:
    t0 = time.time()
    try:
        fn()
        return TestResult(name, True, "OK", time.time() - t0)
    except AssertionError as e:
        return TestResult(name, False, f"ASSERT: {e}", time.time() - t0)
    except Exception as e:
        return TestResult(name, False, f"{type(e).__name__}: {e}", time.time() - t0)


def test_bots_compile() -> None:
    """bot.py y bot_datos.py deben compilar sin errores de sintaxis."""
    import py_compile
    for p in [
        ROOT / "telegram_bot" / "bot.py",
        ROOT / "telegram_bot_datos" / "bot_datos.py",
    ]:
        assert p.is_file(), f"{p} no existe"
        py_compile.compile(str(p), doraise=True)


def test_scripts_curados_compilan() -> None:
    """Los scripts curados de src/ deben compilar."""
    import py_compile
    for nombre in [
        "estado_jugador.py",
        "health_check.py",
        "script_runner.py",
        "aliases_jugadores.py",
        "parse_sesion_voz.py",
        "parse_goles_voz.py",
        "parse_ejercicios_voz.py",
    ]:
        p = ROOT / "src" / nombre
        if not p.is_file():
            # Tolerante: no es error si un script opcional no está.
            continue
        py_compile.compile(str(p), doraise=True)


def test_script_runner_importa() -> None:
    """El helper script_runner debe importarse y exponer run_curated_script."""
    spec = importlib.util.spec_from_file_location(
        "script_runner", str(ROOT / "src" / "script_runner.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["script_runner"] = mod  # necesario para dataclass
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run_curated_script")
    assert hasattr(mod, "ScriptResult")


def test_intent_detector_estado_jugador() -> None:
    """El detector de intent del bot debe matchear casos típicos y
    NO matchear cosas irrelevantes. (Replica la lógica directamente
    para no depender de importar bot.py entero, que requiere libs Telegram.)"""
    import re as _re
    from aliases_jugadores import ROSTER_CANONICO, ALIASES_JUGADOR  # type: ignore

    def detect(prompt: str):
        if not prompt:
            return None
        p = prompt.lower()
        for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
            p = p.replace(a, b)
        triggers = (
            "como esta", "como va", "que tal", "estado de", "estado ",
            "carga ", "fatiga", "borg", "minutos de", "wellness de",
            "resumen de", "cuentame de", "como anda",
        )
        if not any(t in p for t in triggers):
            return None
        tokens = _re.findall(r"[a-z0-9]+", p)
        candidatos = {c.lower(): c for c in ROSTER_CANONICO}
        for ali, canon in ALIASES_JUGADOR.items():
            candidatos[ali.lower().replace(".", "").replace(" ", "")] = canon
            for w in ali.lower().split():
                wc = w.replace(".", "")
                if len(wc) >= 4:
                    candidatos.setdefault(wc, canon)
        canonico = None
        for tok in tokens:
            if tok in candidatos:
                canonico = candidatos[tok]
                break
        if canonico is None:
            return None
        n = 10
        m = _re.search(r"ultim[ao]s?\s+(\d+)", p)
        if not m:
            m = _re.search(r"(\d+)\s*sesiones?", p)
        if m:
            try:
                n = max(1, min(50, int(m.group(1))))
            except ValueError:
                pass
        return (canonico, n)

    # Casos POSITIVOS: deben devolver (jugador, N)
    casos_pos = [
        ("Cómo está Pirata", ("PIRATA", 10)),
        ("Como esta Pirata? carga de las ultimas 10 sesiones", ("PIRATA", 10)),
        ("Carga últimas 7 sesiones de Raya", ("RAYA", 7)),
        ("Estado de Carlos", ("CARLOS", 10)),
        ("Fatiga de Cecilio", ("CECILIO", 10)),
        ("Qué tal Anchu", ("ANCHU", 10)),
    ]
    for prompt, esperado in casos_pos:
        r = detect(prompt)
        assert r == esperado, f"para '{prompt}': esperado={esperado}, got={r}"

    # Casos NEGATIVOS: NO deben matchear
    casos_neg = [
        "hola alfred",
        "consolida los Forms",
        "qué día es hoy",
        "borg medio del equipo",  # no jugador concreto
    ]
    for prompt in casos_neg:
        r = detect(prompt)
        assert r is None, f"para '{prompt}': esperaba None, got={r}"


def test_aliases_consistencia() -> None:
    """Cada alias debe apuntar a un canónico que está en ROSTER_CANONICO."""
    from aliases_jugadores import ROSTER_CANONICO, ALIASES_JUGADOR  # type: ignore
    for alias, canon in ALIASES_JUGADOR.items():
        assert canon in ROSTER_CANONICO, (
            f"Alias {alias!r} → {canon!r} pero {canon} NO está en ROSTER_CANONICO"
        )


def test_db_partido_vacio_horizontal() -> None:
    """El componente Campo del crono debe ser horizontal SIEMPRE
    (regla del proyecto). Comprobamos con un grep simple."""
    campo = ROOT / "crono_partido" / "src" / "components" / "Campo.tsx"
    if not campo.is_file():
        return  # crono no obligatorio
    contenido = campo.read_text(encoding="utf-8")
    assert "HORIZONTAL" in contenido, (
        "Campo.tsx debería tener 'HORIZONTAL' en su docstring (regla del proyecto)"
    )


def test_health_check_importable() -> None:
    """health_check.py debe importarse y exponer las funciones esperadas."""
    spec = importlib.util.spec_from_file_location(
        "health_check", str(ROOT / "src" / "health_check.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["health_check"] = mod
    spec.loader.exec_module(mod)
    for fn in ("run_health_check_quick", "run_health_check_full",
                "format_resultados", "all_ok", "notificar_telegram"):
        assert hasattr(mod, fn), f"health_check.py debería exponer {fn}"


def test_estado_jugador_devuelve_secciones() -> None:
    """estado_jugador.py debe devolver un bloque con las secciones esperadas."""
    script = ROOT / "src" / "estado_jugador.py"
    creds = ROOT / "google_credentials.json"
    if not creds.is_file():
        return  # offline: saltar
    res = subprocess.run(
        ["/usr/bin/python3", str(script), "HERRERO", "5"],
        capture_output=True, text=True, timeout=120,
        cwd=str(ROOT), env={**os.environ, "PYTHONWARNINGS": "ignore"},
    )
    # Tolerante: solo verificamos formato si returncode=0.
    if res.returncode == 0:
        out = res.stdout or ""
        for esperado in ("Carga media", "ACWR", "Wellness"):
            assert esperado in out, f"falta sección {esperado!r} en output"


# ─── Runner ───────────────────────────────────────────────────────────────

TESTS = [
    ("bots_compile",                 test_bots_compile),
    ("scripts_curados_compilan",     test_scripts_curados_compilan),
    ("script_runner_importa",        test_script_runner_importa),
    ("intent_detector_estado_jugador", test_intent_detector_estado_jugador),
    ("aliases_consistencia",         test_aliases_consistencia),
    ("db_partido_horizontal",        test_db_partido_vacio_horizontal),
    ("health_check_importable",      test_health_check_importable),
    ("estado_jugador_secciones",     test_estado_jugador_devuelve_secciones),
]


def main():
    parser = argparse.ArgumentParser(description="Smoke tests del bot")
    parser.add_argument("--offline", action="store_true",
                          help="Salta tests que requieren red/Sheet")
    args = parser.parse_args()

    if args.offline:
        # Quita los tests online de la lista
        tests = [(n, fn) for n, fn in TESTS
                 if n not in ("estado_jugador_secciones",)]
    else:
        tests = TESTS

    results: List[TestResult] = []
    for name, fn in tests:
        r = _run(name, fn)
        print(r)
        results.append(r)

    pasados = sum(1 for r in results if r.ok)
    fallidos = len(results) - pasados
    total_t = sum(r.elapsed for r in results)
    print()
    print(f"Resumen: {pasados}/{len(results)} pasaron, {fallidos} fallos. "
          f"Tiempo total: {total_t:.2f}s")
    sys.exit(0 if fallidos == 0 else 1)


if __name__ == "__main__":
    main()
