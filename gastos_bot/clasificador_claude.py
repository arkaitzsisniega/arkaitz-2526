"""
Fallback de clasificación de intenciones vía Claude Code CLI.

Se usa cuando el detector heurístico (intencion.py) no llega a una
intención clara. Pasamos el mensaje a `claude -p` con un prompt
estricto que pide JSON, parseamos la respuesta y la mapeamos al
mismo formato que devuelve el detector heurístico.

Ventajas:
  - Entiende variaciones naturales ("a ver qué llevamos en mayo",
    "qué hemos pillado este mes", "abre los gastos de la semana"…).
  - Reutiliza la suscripción de Claude Code que ya tiene Arkaitz
    (sin coste adicional).

Coste:
  - ~5-10 segundos por consulta (más lento que keywords pero solo se
    invoca cuando keywords no han llegado a una respuesta).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("gastos-bot.claude")

INTENCIONES_VALIDAS = {
    "apuntar_gasto",
    "resumen_mes_actual",
    "resumen_mes_de",
    "resumen_semana",
    "lista_mes_actual",
    "lista_mes_de",
    "lista_semana",
    "lista_todos",
    "ultimos",
    "borrar_ultimo",
    "ayuda",
}


def find_claude_bin() -> Optional[str]:
    """Localiza el binario `claude` (mismo patrón que telegram_bot)."""
    envbin = os.getenv("CLAUDE_BIN", "").strip()
    if envbin and Path(envbin).is_file():
        return envbin
    p = shutil.which("claude")
    if p:
        return p
    base = Path.home() / "Library/Application Support/Claude/claude-code"
    if base.is_dir():
        # ordenamos por nombre descendente para coger la versión más reciente
        for v in sorted(base.iterdir(), reverse=True):
            cand = v / "claude.app/Contents/MacOS/claude"
            if cand.is_file():
                return str(cand)
    return None


PROMPT_TEMPLATE = """Eres un clasificador de intenciones para un bot de gastos personales \
(de un matrimonio: Arkaitz y Lis) que se usa por Telegram.

Hoy es {fecha_hoy}. El usuario escribe un mensaje y debes decidir qué quiere \
hacer con sus gastos.

Intenciones posibles (elige EXACTAMENTE una):
- "apuntar_gasto": registrar un gasto nuevo (suele llevar cantidad y concepto).
- "resumen_mes_actual": totales AGREGADOS por categoría del mes en curso.
- "resumen_mes_de": totales AGREGADOS por categoría de un mes concreto (devuelve "mes": 1-12).
- "resumen_semana": totales AGREGADOS de los últimos 7 días.
- "lista_mes_actual": cada gasto FILA A FILA del mes actual.
- "lista_mes_de": cada gasto FILA A FILA de un mes concreto (devuelve "mes": 1-12).
- "lista_semana": cada gasto FILA A FILA de los últimos 7 días.
- "lista_todos": todos los gastos del histórico FILA A FILA.
- "ultimos": los N últimos gastos (sin filtro de tiempo concreto).
- "borrar_ultimo": eliminar el último gasto.
- "ayuda": pide instrucciones generales o el mensaje no es claro.

Reglas:
- Diferencia "resumen" (totales por categoría) de "lista" (fila a fila).
- Frases tipo "uno a uno", "uno por uno", "detallado", "todos los gastos", \
"qué hemos comprado", "enseñame los movimientos" piden LISTA, no resumen.
- Si menciona un mes (enero=1, febrero=2,...,diciembre=12), responde con su número.
- Si dice "mes pasado", calcula respecto a la fecha de hoy.
- Si dice "este mes", "mes actual", "del mes": usa la variante "_mes_actual".
- Si dice "esta semana", "última semana", "últimos 7 días": usa "_semana".
- Si no se menciona periodo y pide ver gastos uno a uno: usa "lista_todos".
- Si pide los últimos gastos sin filtro temporal: usa "ultimos".
- Si no entiendes o el mensaje no encaja: usa "ayuda".

MENSAJE DEL USUARIO: <<<{texto}>>>

RESPONDE SOLO con un JSON válido en una sola línea, SIN markdown, SIN comentarios:
{{"intencion": "<una_de_las_anteriores>", "mes": <número 1-12 o null>}}"""


async def _ejecutar_claude(prompt: str, timeout_s: int = 30) -> Optional[str]:
    """Llama al CLI de Claude y devuelve su salida cruda (string), o None."""
    bin_claude = find_claude_bin()
    if not bin_claude:
        log.warning("No se ha encontrado el binario de Claude Code.")
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            bin_claude, "-p", prompt, "--output-format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            log.warning("Claude clasificador timed out tras %ds.", timeout_s)
            return None
        if proc.returncode != 0:
            log.warning("Claude clasificador exit %s. stderr=%s",
                        proc.returncode, stderr.decode("utf-8", errors="replace")[:300])
            return None
        return stdout.decode("utf-8", errors="replace")
    except Exception:
        log.exception("Error invocando Claude")
        return None


def _extraer_json_intencion(salida: str) -> Optional[dict]:
    """Saca el dict {intencion, mes} de la salida de Claude.

    Claude `--output-format json` devuelve un wrapper con la respuesta
    del asistente dentro de algún campo string. Buscamos un objeto JSON
    con clave "intencion" en cualquier nivel."""
    if not salida:
        return None

    # 1) Si Claude devuelve directamente JSON sin wrapper
    m = re.search(r'\{[^{}]*"intencion"[^{}]*\}', salida)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 2) Wrapper de --output-format json
    try:
        wrapper = json.loads(salida)
    except json.JSONDecodeError:
        return None
    # Buscar recursivamente strings que contengan {"intencion":...}
    candidatos: list = [wrapper]
    while candidatos:
        x = candidatos.pop()
        if isinstance(x, str):
            m = re.search(r'\{[^{}]*"intencion"[^{}]*\}', x)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
        elif isinstance(x, dict):
            if "intencion" in x:
                return x
            candidatos.extend(x.values())
        elif isinstance(x, list):
            candidatos.extend(x)
    return None


def _mapear(d: dict) -> Optional[Tuple[str, Optional[int]]]:
    """Mapea el JSON de Claude al formato (tipo, param) que usa bot.py.

    Devuelve None para "apuntar_gasto" para que bot.py caiga en el
    parser de gastos. "borrar_ultimo" se mapea a "ayuda" porque borrar
    sin confirmación es destructivo (que use /borrar)."""
    intencion = (d.get("intencion") or "").strip()
    if intencion not in INTENCIONES_VALIDAS:
        return None
    mes = d.get("mes")
    if isinstance(mes, str) and mes.isdigit():
        mes = int(mes)
    if not isinstance(mes, int) or not (1 <= mes <= 12):
        mes = None

    if intencion == "apuntar_gasto":
        return None  # señal: que el parser intente apuntar
    if intencion == "resumen_mes_actual":
        return ("resumen_mes", None)
    if intencion == "resumen_mes_de":
        if mes is None:
            return ("resumen_mes", None)
        return ("resumen_mes_de", mes)
    if intencion == "resumen_semana":
        return ("resumen_semana", None)
    if intencion == "lista_mes_actual":
        return ("lista_mes", None)
    if intencion == "lista_mes_de":
        if mes is None:
            return ("lista_mes", None)
        return ("lista_mes_de", mes)
    if intencion == "lista_semana":
        return ("lista_semana", None)
    if intencion == "lista_todos":
        return ("lista_todos", None)
    if intencion == "ultimos":
        return ("ultimos", None)
    if intencion == "borrar_ultimo":
        # El bot.py mostrará ayuda explicando que use /borrar
        return ("ayuda", None)
    return ("ayuda", None)


async def clasificar(texto: str) -> Optional[Tuple[str, Optional[int]]]:
    """Punto de entrada. Devuelve (tipo, param) o None si no lo logra."""
    fecha_hoy = _dt.date.today().strftime("%Y-%m-%d")
    prompt = PROMPT_TEMPLATE.format(
        fecha_hoy=fecha_hoy,
        texto=texto.replace("\n", " ").strip(),
    )
    salida = await _ejecutar_claude(prompt)
    if not salida:
        return None
    d = _extraer_json_intencion(salida)
    if not d:
        log.warning("Claude no devolvió un JSON parseable: %r", salida[:200])
        return None
    return _mapear(d)
