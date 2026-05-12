"""
script_runner.py — Helper común para que los bots ejecuten scripts
curados de `src/` de forma robusta.

Centraliza el patrón que aparecía 14 veces (`subprocess.run` +
`(err or out)`) con los siguientes fixes:

  - Usa **`sys.executable`** (Python del venv del bot), no
    `/usr/bin/python3` (que en este server es 3.8 del sistema con
    paquetes globales viejos).
  - Pasa `PYTHONWARNINGS=ignore` para que los scripts no emitan
    `FutureWarning` (google.generativeai deprecated, urllib3 OpenSSL, …)
    que el bot interprete como error.
  - Filtra warnings ruidosos del stderr si el script falla.
  - Maneja `MSG_SEP` automáticamente: si el script imprime el separador,
    devuelve el mensaje user-friendly de DESPUÉS del separador.
  - Combina stdout + stderr de forma sensata cuando reporta errores
    (en vez de `err or out` que oculta uno de los dos).

Uso:

    from script_runner import run_curated_script

    res = run_curated_script("src/estado_jugador.py", ["PIRATA", "10"])
    if res.ok:
        return res.salida  # solo lo de DESPUÉS de MSG_SEP, o todo si no hay sep
    else:
        return f"⚠️ {res.error}"

NOTA: el módulo NO depende de Telegram / Gemini. Solo Python stdlib +
los paths del proyecto. Se puede usar desde cualquier script del repo.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

MSG_SEP = "---MSG---"

# Patrones de stderr que NO son errores reales (ruido típico):
_WARNINGS_FILTRO = (
    "FutureWarning",
    "warnings.warn",
    "All support for the",
    "google.generativeai",
    "google.genai",
    "deprecated-generative-ai",
    "google-gemini",
    "NotOpenSSLWarning",
    "urllib3",
    "ABSL",
    "InsecureRequestWarning",
    "PerformanceWarning",
    "DeprecationWarning",
    "UserWarning",
)


@dataclass
class ScriptResult:
    """Resultado de ejecutar un script curado."""
    ok: bool
    returncode: int
    salida: str        # lo que mostrar al usuario (MSG después de SEP, o stdout entero)
    error: str         # mensaje de error (si !ok) o vacío
    stdout: str        # stdout completo (debug)
    stderr: str        # stderr filtrado (debug)


def _filtrar_stderr(stderr: str) -> str:
    """Quita las líneas de warning ruidoso de stderr."""
    if not stderr:
        return ""
    lineas = []
    for ln in stderr.splitlines():
        if any(p in ln for p in _WARNINGS_FILTRO):
            continue
        lineas.append(ln)
    return "\n".join(lineas).strip()


def _extraer_msg(stdout: str) -> str:
    """Si stdout contiene MSG_SEP, devuelve solo lo de DESPUÉS. Si no,
    devuelve stdout entero (recortado)."""
    if not stdout:
        return ""
    if MSG_SEP in stdout:
        return stdout.split(MSG_SEP, 1)[1].strip()
    return stdout.strip()


def run_curated_script(
    script_path: str,
    args: Sequence[str] = (),
    *,
    stdin: Optional[str] = None,
    timeout: int = 120,
    cwd: Optional[str] = None,
    python: Optional[str] = None,
) -> ScriptResult:
    """Ejecuta un script Python con el venv del bot.

    Parámetros:
        script_path: ruta absoluta al script (o relativa a cwd).
        args: argumentos posicionales.
        stdin: texto a pasarle por stdin (None = sin stdin).
        timeout: segundos antes de matar el proceso.
        cwd: directorio de trabajo. Si None, usa el padre del script.
        python: ejecutable Python a usar. Si None, `sys.executable`.

    Devuelve ScriptResult con .ok, .salida (mensaje user-friendly),
    .error (descripción humana del fallo si lo hay), y stdout/stderr
    completos para diagnóstico.
    """
    spath = Path(script_path)
    if not spath.is_absolute():
        # Buscar relativo al cwd actual.
        spath = Path.cwd() / spath
    if not spath.is_file():
        return ScriptResult(
            ok=False, returncode=-1, salida="",
            error=f"No encuentro el script: {spath.name}",
            stdout="", stderr="",
        )

    py_exe = python or sys.executable
    work_dir = cwd or str(spath.parent.parent.resolve())

    cmd = [py_exe, str(spath), *args]
    env = {**os.environ, "PYTHONWARNINGS": "ignore", "PYTHONUNBUFFERED": "1"}

    try:
        res = subprocess.run(
            cmd,
            input=stdin if stdin is not None else None,
            capture_output=True, text=True,
            timeout=timeout,
            cwd=work_dir,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return ScriptResult(
            ok=False, returncode=-1, salida="",
            error=f"Timeout (>{timeout}s) en {spath.name}",
            stdout="", stderr="",
        )
    except Exception as e:
        return ScriptResult(
            ok=False, returncode=-1, salida="",
            error=f"Fallo lanzando {spath.name}: {type(e).__name__}: {e}",
            stdout="", stderr="",
        )

    stdout = res.stdout or ""
    stderr_clean = _filtrar_stderr(res.stderr or "")

    if res.returncode == 0:
        # Éxito. Devolver el mensaje user-friendly (después de MSG_SEP si existe).
        return ScriptResult(
            ok=True, returncode=0,
            salida=_extraer_msg(stdout) or "(sin output)",
            error="", stdout=stdout, stderr=stderr_clean,
        )

    # Error: priorizar el mensaje del propio script (MSG_SEP), si existe.
    msg_user = _extraer_msg(stdout)
    if not msg_user:
        msg_user = stderr_clean or stdout.strip() or "Error sin detalle"
    # Truncar a algo razonable para Telegram (4096 chars máx).
    msg_user = msg_user[:1800]

    return ScriptResult(
        ok=False, returncode=res.returncode,
        salida=msg_user,
        error=f"Error en {spath.name} (rc={res.returncode}): {msg_user[:300]}",
        stdout=stdout, stderr=stderr_clean,
    )


async def run_curated_script_async(
    script_path: str,
    args: Sequence[str] = (),
    *,
    stdin: Optional[str] = None,
    timeout: int = 120,
    cwd: Optional[str] = None,
    python: Optional[str] = None,
) -> ScriptResult:
    """Versión async (para usar dentro de handlers async del bot)."""
    return await asyncio.to_thread(
        run_curated_script,
        script_path, args,
        stdin=stdin, timeout=timeout, cwd=cwd, python=python,
    )
