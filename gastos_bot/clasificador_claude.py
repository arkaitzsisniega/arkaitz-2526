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
    "cambiar_categoria_ultimo",
    "ayuda",
}

CATEGORIAS_VALIDAS = {
    "Supermercado", "Restaurantes", "Casa", "Alquiler/Hipoteca",
    "Transporte", "Salud", "Ocio", "Compras", "Mascotas",
    "Fin de semana", "Otros",
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
- "apuntar_gasto": registrar un gasto nuevo. Devuelve cantidad, concepto y \
categoría sugerida si se puede inferir.
- "resumen_mes_actual": totales AGREGADOS por categoría del mes en curso.
- "resumen_mes_de": totales AGREGADOS por categoría de un mes concreto (devuelve "mes": 1-12).
- "resumen_semana": totales AGREGADOS de los últimos 7 días.
- "lista_mes_actual": cada gasto FILA A FILA del mes actual.
- "lista_mes_de": cada gasto FILA A FILA de un mes concreto (devuelve "mes": 1-12).
- "lista_semana": cada gasto FILA A FILA de los últimos 7 días.
- "lista_todos": todos los gastos del histórico FILA A FILA.
- "ultimos": los N últimos gastos (sin filtro de tiempo concreto).
- "borrar_ultimo": eliminar el último gasto registrado.
- "cambiar_categoria_ultimo": modificar la categoría del último gasto. Devuelve "categoria".
- "ayuda": pide instrucciones generales o el mensaje no es claro.

Categorías VÁLIDAS (devuelve EXACTAMENTE una de estas en "categoria" cuando aplique):
Supermercado, Restaurantes, Casa, Alquiler/Hipoteca, Transporte, Salud,
Ocio, Compras, Mascotas, Fin de semana, Otros

Pistas de mapeo:
- Lidl, Mercadona, Aldi, BM, Costco, fruteria, panadería, carnicería, pescadería → Supermercado
- Cena, restaurante, bar, café, kebab, pizza, sushi, hamburguesa, asador → Restaurantes
- Luz, agua, gas, internet, alarma, jardinero, limpieza, Iberdrola, Vodafone, Lowi → Casa
- Hipoteca, alquiler, comunidad → Alquiler/Hipoteca
- Gasolina, parking, taxi, Uber, vuelo, ITV, taller → Transporte
- Farmacia, médico, dentista, fisio, masaje, óptica → Salud
- Cine, viaje, hotel, Netflix, Spotify, gimnasio, regalo → Ocio
- Ropa, Amazon, Zara, Decathlon, Veepee, Cheerz → Compras
- Veterinario, pienso, perro, gato → Mascotas
- Castro (escapadas a Castro Urdiales) → Fin de semana
- Si no encaja: Otros

Reglas para extraer datos del apunte:
- "cantidad": número (acepta coma o punto decimal). Ej "11 euros" → 11.
- "concepto": el QUÉ del gasto, en 1-3 palabras limpias. Ej de "11 euros en el mercado" → "Mercado". \
NO uses la frase entera. Quita muletillas como "apunta", "ahora mismo", "de hoy", etc. \
Si el usuario nombra explícitamente una categoría ("en categoría supermercados"), NO la incluyas \
en el concepto. Ej "Apunta 11 euros de hoy en el mercado en categoría supermercados" → concepto="Mercado".
- "categoria": si el usuario la menciona EXPLÍCITAMENTE ("en categoría X", "como X"), úsala. \
En caso contrario, infiérela del concepto. Si no estás seguro: "Otros".

Reglas para identificar listas vs resúmenes:
- Diferencia "resumen" (totales por categoría) de "lista" (fila a fila).
- Frases tipo "uno a uno", "uno por uno", "detallado", "todos los gastos", \
"qué hemos comprado", "enseñame los movimientos" piden LISTA, no resumen.
- Si menciona un mes (enero=1, febrero=2,...,diciembre=12), responde con su número.
- Si dice "mes pasado", calcula respecto a la fecha de hoy.
- Si dice "este mes", "mes actual", "del mes": usa la variante "_mes_actual".
- Si dice "esta semana", "última semana", "últimos 7 días": usa "_semana".
- Si no se menciona periodo y pide ver gastos uno a uno: usa "lista_todos".
- Si pide los últimos gastos sin filtro temporal: usa "ultimos".

Reglas para cambiar categoría del último:
- Frases como "cámbialo a X", "ponlo en X", "el último era X", "está en categoría X, cámbialo" \
→ "cambiar_categoria_ultimo" con la categoría que el usuario menciona.

Si no entiendes o el mensaje no encaja: usa "ayuda".

MENSAJE DEL USUARIO: <<<{texto}>>>

RESPONDE SOLO con un JSON válido en una sola línea, SIN markdown, SIN comentarios.
Estructura del JSON (omite los campos que no apliquen):
{{"intencion": "<una>", "mes": <1-12 o null>, "cantidad": <número o null>, \
"concepto": "<texto o null>", "categoria": "<una de las válidas o null>"}}"""


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


def _mapear(d: dict) -> Optional[dict]:
    """Mapea el JSON de Claude a un dict normalizado para bot.py.

    Devuelve un dict con:
      - tipo: una de las claves válidas usadas por bot.py
      - param: número (mes) o None
      - cantidad, concepto, categoria: solo en apuntar_gasto y cambiar_categoria_ultimo

    Para "apuntar_gasto" devolvemos los datos extraídos de Claude. bot.py
    decide si usarlos directamente (mejor en frases naturales) o caer al
    parser local."""
    intencion = (d.get("intencion") or "").strip()
    if intencion not in INTENCIONES_VALIDAS:
        return None
    mes = d.get("mes")
    if isinstance(mes, str) and mes.isdigit():
        mes = int(mes)
    if not isinstance(mes, int) or not (1 <= mes <= 12):
        mes = None

    cantidad = d.get("cantidad")
    if isinstance(cantidad, str):
        try:
            cantidad = float(cantidad.replace(",", "."))
        except ValueError:
            cantidad = None
    if cantidad is not None and not isinstance(cantidad, (int, float)):
        cantidad = None

    concepto = (d.get("concepto") or "").strip() or None

    categoria = (d.get("categoria") or "").strip() or None
    if categoria and categoria not in CATEGORIAS_VALIDAS:
        # Intentar match insensible
        cat_norm = next((c for c in CATEGORIAS_VALIDAS
                         if c.lower() == categoria.lower()), None)
        categoria = cat_norm

    base = {"cantidad": cantidad, "concepto": concepto, "categoria": categoria}

    if intencion == "apuntar_gasto":
        return {"tipo": "apuntar_gasto", "param": None, **base}
    if intencion == "resumen_mes_actual":
        return {"tipo": "resumen_mes", "param": None, **base}
    if intencion == "resumen_mes_de":
        return {"tipo": "resumen_mes" if mes is None else "resumen_mes_de", "param": mes, **base}
    if intencion == "resumen_semana":
        return {"tipo": "resumen_semana", "param": None, **base}
    if intencion == "lista_mes_actual":
        return {"tipo": "lista_mes", "param": None, **base}
    if intencion == "lista_mes_de":
        return {"tipo": "lista_mes" if mes is None else "lista_mes_de", "param": mes, **base}
    if intencion == "lista_semana":
        return {"tipo": "lista_semana", "param": None, **base}
    if intencion == "lista_todos":
        return {"tipo": "lista_todos", "param": None, **base}
    if intencion == "ultimos":
        return {"tipo": "ultimos", "param": None, **base}
    if intencion == "cambiar_categoria_ultimo":
        return {"tipo": "cambiar_categoria_ultimo", "param": None, **base}
    if intencion == "borrar_ultimo":
        # Sigue mapeando a ayuda por seguridad (que use /borrar manualmente)
        return {"tipo": "ayuda", "param": None, **base}
    return {"tipo": "ayuda", "param": None, **base}


async def clasificar(texto: str) -> Optional[dict]:
    """Punto de entrada. Devuelve dict {tipo, param, cantidad?, concepto?, categoria?}."""
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
