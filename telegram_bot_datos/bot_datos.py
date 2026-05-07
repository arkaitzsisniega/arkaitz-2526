#!/usr/bin/env python3
"""
Bot de Telegram de CONSULTAS DE DATOS para el cuerpo técnico del
Movistar Inter FS (@InterFS_datos_bot).

Diferencias respecto al bot dev (@InterFS_bot):
  - Multi-usuario con lista de chat_ids autorizados (ALLOWED_CHAT_IDS en .env).
  - Solo LECTURA: no puede editar archivos ni hacer commits.
  - Sesión por usuario (directorios separados) para que cada uno tenga su hilo.
  - System prompt que orienta a Claude a responder como "asistente de datos"
    en lenguaje humano, no técnico.
"""
from __future__ import annotations

import os
import re
import json
import asyncio
import datetime as _dt
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Set, Dict, List, Any

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

# Gemini (Google AI Studio) — backend LLM gratuito para este bot.
import google.generativeai as genai

# Whisper es opcional: si falla el import, el bot sigue funcionando solo con texto.
try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception as _e:
    _WHISPER_OK = False
    _WHISPER_IMPORT_ERR = str(_e)

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

TOKEN               = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS_ST = os.getenv("ALLOWED_CHAT_IDS", "").strip()
PROJECT_DIR         = Path(os.getenv("PROJECT_DIR", str(HERE.parent))).expanduser().resolve()
LLM_TIMEOUT         = int(os.getenv("LLM_TIMEOUT", "300"))
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
# Cuántas iteraciones de tool-use permitir antes de cortar (defensa anti-bucle).
GEMINI_MAX_STEPS    = int(os.getenv("GEMINI_MAX_STEPS", "8"))
# Cuántas vueltas (user+model) guardamos en memoria por chat antes de truncar.
HISTORY_MAX_TURNS   = int(os.getenv("HISTORY_MAX_TURNS", "12"))

SESIONES_DIR = HERE / "sesiones"
MAX_MSG_LEN  = 4000
BOT_NAME     = "InterFS_datos_bot"

# Parsear lista de chat_ids permitidos (separados por comas, espacios o saltos de línea)
ALLOWED_CHAT_IDS: Set[int] = set()
for raw in re.split(r"[,\s]+", ALLOWED_CHAT_IDS_ST):
    raw = raw.strip()
    if raw:
        try:
            ALLOWED_CHAT_IDS.add(int(raw))
        except ValueError:
            pass

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("arkaitz-datos")


# ─── Validación ──────────────────────────────────────────────────────────────
def _fail(msg: str) -> None:
    log.error(msg)
    raise SystemExit(f"\n❌ {msg}\n")


if not TOKEN:
    _fail("Falta TELEGRAM_BOT_TOKEN en .env")
if not ALLOWED_CHAT_IDS:
    _fail("Falta ALLOWED_CHAT_IDS en .env (al menos un chat_id separado por comas).")
if not PROJECT_DIR.is_dir():
    _fail(f"PROJECT_DIR no existe: {PROJECT_DIR}")
if not GEMINI_API_KEY:
    _fail("Falta GEMINI_API_KEY en .env (consíguela gratis en aistudio.google.com/apikey).")

SESIONES_DIR.mkdir(parents=True, exist_ok=True)

# Configurar cliente Gemini
genai.configure(api_key=GEMINI_API_KEY)

log.info("Backend LLM: Gemini (%s)", GEMINI_MODEL)
log.info("Proyecto: %s", PROJECT_DIR)
log.info("Autorizados: %s", sorted(ALLOWED_CHAT_IDS))


# ─── Espejo de conversaciones (para móvil ↔ ordenador) ───────────────────────
LOGS_DIR = PROJECT_DIR / "telegram_logs"
LOGS_DIR.mkdir(exist_ok=True)


def _append_log(chat_id: int, user_name: str, user_msg: str, bot_reply: str, kind: str = "texto") -> None:
    try:
        hoy = _dt.datetime.now().strftime("%Y-%m-%d")
        hora = _dt.datetime.now().strftime("%H:%M:%S")
        path = LOGS_DIR / f"{hoy}.md"
        etiqueta = "🎤 (voz)" if kind == "voz" else "💬"
        bloque = (
            f"\n---\n"
            f"### {hora} · {BOT_NAME} · chat `{chat_id}` · {etiqueta}\n\n"
            f"**{user_name or 'usuario'}:**\n{user_msg.strip()}\n\n"
            f"**Claude:**\n{bot_reply.strip()}\n"
        )
        with path.open("a", encoding="utf-8") as f:
            f.write(bloque)
    except Exception as e:
        log.warning("No pude escribir log: %s", e)


# ─── System prompt del bot de datos ──────────────────────────────────────────
SYSTEM_PROMPT = f"""\
Eres el asistente de datos del Movistar Inter FS (equipo profesional de fútbol sala).
Estás respondiendo desde Telegram a miembros del cuerpo técnico y, más adelante, a jugadores.

TU PAPEL:
- Contestar preguntas sobre los datos de la temporada 25/26: pesos, cargas
  de entrenamiento (Borg, sRPE, ACWR), wellness (sueño/fatiga/molestias/ánimo),
  lesiones, asistencia/recuento.
- Siempre en español, con tono cercano y claro, como un preparador físico
  hablando con un compañero. Evita jerga técnica salvo que te la pidan.
- Da números concretos con nombre y fecha. Ejemplo: "Carlos perdió 1,2 kg el
  lunes 14/04" mejor que "el jugador presenta variación ponderal".
- Si te piden tendencia, hazlo en 1-2 frases claras.

REGLAS ESTRICTAS:
1. SOLO LECTURA. No modifiques NINGÚN archivo, no hagas commits, no toques git.
2. No ejecutes scripts que escriban a disco fuera de /tmp.
3. Si te preguntan por código, arquitectura, fixes, commits o cambios técnicos,
   responde amablemente: "Eso mejor pregúntaselo al bot del cuerpo técnico
   (@InterFS_bot). Yo solo respondo consultas de datos."

CÓMO CONSULTAR LOS DATOS:
Los datos están en Google Sheets. El proyecto está en {PROJECT_DIR}.
**Usa SIEMPRE la herramienta `python`** (no `bash`) para ejecutar código
Python — pasa el código tal cual, sin envoltorios ni escapados. Mete TODO
el script en una sola llamada (importar credenciales + abrir Sheet + leer
datos + print). NO partas el script en varias llamadas: cada llamada es
un proceso nuevo y pierdes la conexión.

Plantilla SIEMPRE válida (cópiala, ajusta el contenido tras `# >>> tu código`):

```python
import pandas as pd, gspread
from google.oauth2.service_account import Credentials
creds = Credentials.from_service_account_file(
    '{PROJECT_DIR}/google_credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'])
ss = gspread.authorize(creds).open('Arkaitz - Datos Temporada 2526')
# Hojas disponibles:
#   crudas:   SESIONES, BORG, PESO, WELLNESS, LESIONES, FISIO
#   vistas:   _VISTA_CARGA, _VISTA_SEMANAL, _VISTA_PESO, _VISTA_WELLNESS,
#             _VISTA_SEMAFORO, _VISTA_RECUENTO
ws = ss.worksheet('NOMBRE_DE_HOJA')
df = pd.DataFrame(ws.get_all_records(
    value_render_option=gspread.utils.ValueRenderOption.unformatted))
# >>> tu código sobre df
print(df.head().to_string())
```

REGLAS PARA QUERIES (importantísimas, evítate errores):

1. Para CONTAR filas reales de una hoja, usa **`len(df)`** después de cargarla
   con `get_all_records`. No uses `ws.row_count` (devuelve el tamaño del
   grid de Google Sheets, no las filas con datos).
2. Si solo te piden un conteo y no el contenido, no hace falta importar
   pandas: `print(len(ws.get_all_values()) - 1)` también vale (resta el header).
3. Nombres de jugadores: el Sheet **siempre** los guarda en MAYÚSCULAS y
   con un único nombre corto (ver ROSTER abajo). Si el usuario te dice
   "Javi Mínguez", "Javier", "el 10" → es **JAVI** en el Sheet. Usa
   `str.contains` en mayúsculas para tolerar variantes:
   `df[df['JUGADOR'].astype(str).str.upper().str.contains('JAVI', na=False)]`.
   Para el nombre exacto preferentemente `==` con la versión corta.
4. Fechas: las columnas FECHA vienen como strings ISO (`YYYY-MM-DD`) o
   como ints serializados. Si filtras por rango, parsea con pandas:
   `df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')`.
5. "Esta semana" = lunes-domingo de la semana del usuario (hoy es
   `__HOY__`). "Última semana" = ese mismo rango menos 7 días.
6. Cuando agregas, devuelve a la respuesta del usuario números concretos
   (ej "Carlos: 5 sesiones, sRPE total 1840"). NO pegues dicts/JSON
   crudos al usuario, RESUMELO en lenguaje natural.

Si el código falla, la salida que recibirás incluirá el traceback.
Léelo, corrige y vuelve a llamar a `python`. No te quedes en bucle:
si el mismo error sale 2 veces seguidas, dile al usuario que no has
podido obtener los datos y por qué.

ROSTER OFICIAL (cómo se guarda cada jugador en la hoja JUGADOR):
- PORTEROS primer equipo: J.HERRERO (apodado HERRERO o "1"), J.GARCIA ("Javi García")
- CAMPO primer equipo: CECILIO, CHAGUINHA (a.k.a. CHAGAS), RAUL, HARRISON,
  RAYA, JAVI (Javi Mínguez, "el 10"), PANI, PIRATA, BARONA, CARLOS
- PORTERO filial: OSCAR
- CAMPO filial: RUBIO (Sergio Vizuete), JAIME, SEGO, DANI, GONZA, PABLO, GABRI

Si te dicen un nombre que no encaja exactamente, intenta el match parcial
(`str.contains`) antes de decir "no encuentro al jugador".

ESQUEMA DE COLUMNAS (las más usadas — abre la hoja para ver el resto):
- **BORG**: JUGADOR, FECHA, TURNO, BORG, MINUTOS. Una fila **por jugador y por sesión**.
  La columna BORG contiene un número (0-10 si entrenó) o una letra (S/A/L/N/D/NC
  si no entrenó normalmente — Selección, Ausencia, Lesión, No entrena, Descanso, NC).
- **PESO**: JUGADOR, FECHA, TURNO, PESO_PRE, PESO_POST.
- **WELLNESS**: JUGADOR, FECHA, SUEÑO, FATIGA, MOLESTIAS, ANIMO, TOTAL.
- **LESIONES**: JUGADOR, FECHA_INICIO, FECHA_FIN, ZONA, TIPO, BAJA_DIAS.
- **SESIONES**: FECHA, TURNO, TIPO, MINUTOS. NO tiene columna JUGADOR — es la
  lista de entrenamientos del equipo (calendario, no asistencia individual).
- **FISIO**: tratamientos por jugador. JUGADOR, FECHA, FISIO, ZONA, NOTAS.
- **_VISTA_CARGA**: JUGADOR, FECHA, sRPE, MEDIA_AGUDA, MEDIA_CRONICA, ACWR,
  MONOTONIA, FATIGA, SEMAFORO.
- **_VISTA_SEMANAL**: JUGADOR, SEMANA_ISO, SEMANA_INICIO, sRPE_TOTAL, MIN_TOTAL.
- **_VISTA_PESO**: JUGADOR, FECHA, TURNO, PESO_PRE, PESO_POST, DELTA, PCT_DELTA,
  **DESVIACION_BASELINE** (diferencia vs media personal últimos 2 meses).
- **_VISTA_WELLNESS**: JUGADOR, FECHA, TOTAL, SEMAFORO.
- **_VISTA_SEMAFORO**: JUGADOR, ESTADO_GENERAL, ALERTA_CARGA, ALERTA_PESO, ALERTA_WELLNESS.

Notas importantes sobre dónde mirar:
- **DESVIACION_BASELINE solo está en `_VISTA_PESO`**, no en `PESO` cruda.
- **"Cuántas sesiones ha entrenado X jugador"** → usa `BORG`, filtrando por
  jugador y contando filas donde la columna BORG es **numérica** (no letra
  S/A/L/N/D/NC). Ej:
  ```python
  df = pd.DataFrame(ss.worksheet('BORG').get_all_records(value_render_option=...))
  d = df[df['JUGADOR'].astype(str).str.upper().str.contains('PIRATA', na=False)]
  d['BORG_num'] = pd.to_numeric(d['BORG'], errors='coerce')
  print('Sesiones entrenadas:', d['BORG_num'].notna().sum())
  print('Total filas (incluyendo S/A/L/...):', len(d))
  ```
- **"Cuántos entrenamientos lleva el equipo"** → cuenta filas en `SESIONES`
  (esa hoja sí lleva el calendario del equipo).

MÉTRICAS CLAVE:
- Borg (RPE): 0-10. Percepción subjetiva del esfuerzo. Las letras S/A/L/N/D/NC
  son estados no-entrenables (Selección, Ausencia, Lesión, No entrena, Descanso, NC).
- sRPE = Borg × minutos = "carga de sesión".
- ACWR: ratio de carga aguda/crónica. 0.8-1.3 zona óptima, >1.5 riesgo.
- Monotonía: >2 indica riesgo.
- Wellness: suma de 4 items (1-5 cada uno) = 4-20. <15 es flojo, <10 es alerta.
- Peso PRE: antes del entrenamiento. DESVIACION_BASELINE: diferencia vs media
  personal histórica.
"""


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _authorized(update: Update) -> bool:
    return bool(update.effective_chat) and update.effective_chat.id in ALLOWED_CHAT_IDS


def _chunks(text: str, size: int = MAX_MSG_LEN):
    if len(text) <= size:
        yield text
        return
    while text:
        if len(text) <= size:
            yield text
            return
        corte = text.rfind("\n", 0, size)
        if corte == -1 or corte < size // 2:
            corte = size
        yield text[:corte]
        text = text[corte:].lstrip("\n")


async def _keep_typing(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE, stop: asyncio.Event):
    try:
        while not stop.is_set():
            try:
                await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        pass


# Chats que quieren empezar conversación nueva (tras /nuevo)
_fresh_chats: Set[int] = set()

# Modelo Whisper (lazy load; primera vez descarga ~150MB)
_whisper_model = None
_whisper_lock = asyncio.Lock()
WHISPER_SIZE = os.getenv("WHISPER_MODEL", "base")  # tiny/base/small/medium


async def get_whisper():
    """Carga perezosa del modelo Whisper, protegida contra carga concurrente."""
    global _whisper_model
    if not _WHISPER_OK:
        return None
    if _whisper_model is not None:
        return _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            log.info("Cargando modelo Whisper (%s) — primera vez tarda…", WHISPER_SIZE)
            # Cargar en un hilo para no bloquear el event loop
            def _load():
                return WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
            _whisper_model = await asyncio.get_event_loop().run_in_executor(None, _load)
            log.info("Whisper listo.")
    return _whisper_model


async def _transcribir(audio_path: str) -> str:
    """Transcribe un archivo de audio (.ogg de Telegram) a texto español."""
    model = await get_whisper()
    if model is None:
        raise RuntimeError("Whisper no disponible (faster-whisper no instalado).")
    def _run():
        segments, info = model.transcribe(
            audio_path, language="es", beam_size=5, vad_filter=True,
        )
        return " ".join(s.text for s in segments).strip()
    return await asyncio.get_event_loop().run_in_executor(None, _run)


# ─── Backend Gemini: tool-use loop con bash + read_file ─────────────────────
# Conversación en memoria por chat_id. Si el bot se reinicia, se pierde.
_conv_history: Dict[int, List[Dict[str, Any]]] = {}

# Definición de herramientas (function calling). Solo lectura.
TOOLS_BOT_DATOS = [
    {
        "function_declarations": [
            {
                "name": "python",
                "description": (
                    "Ejecuta código Python con /usr/bin/python3 y devuelve "
                    "stdout+stderr. Es la herramienta principal para consultar "
                    "Google Sheets (gspread, pandas ya instalados). Pasas el "
                    "código tal cual, SIN escapado de shell ni envoltorios "
                    "raros: simplemente el contenido del script. Solo lectura: "
                    "NO escribir archivos, NO commits, NO modificar Sheets."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Código Python a ejecutar. Ejemplo:\n"
                                "import gspread\n"
                                "from google.oauth2.service_account import Credentials\n"
                                "creds = Credentials.from_service_account_file(...)\n"
                                "ss = gspread.authorize(creds).open('Arkaitz - Datos Temporada 2526')\n"
                                "print(len(ss.worksheet('BORG').get_all_values()) - 1)"
                            ),
                        }
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "bash",
                "description": (
                    "Ejecuta un comando shell genérico (ls, head, tail, grep, "
                    "git log…). Para ejecutar Python usa la herramienta "
                    "`python` en su lugar. Solo lectura: NO escribir, NO commits, NO git push."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Comando shell completo.",
                        }
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Lee un archivo de texto del proyecto y devuelve su contenido.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Ruta del archivo (relativa al proyecto o absoluta).",
                        }
                    },
                    "required": ["path"],
                },
            },
        ]
    }
]


def _exec_tool(name: str, args: Dict[str, Any]) -> str:
    """Ejecuta una herramienta y devuelve el resultado (texto)."""
    try:
        if name == "python":
            code = args.get("code", "")
            if not code.strip():
                return "ERROR: código vacío."
            # Usamos el mismo Python con el que corre el bot (venv 3.11), que
            # tiene gspread/pandas/etc. instalados con versiones coherentes.
            # /usr/bin/python3 (sistema 3.8 en Catalina) crasheaba con SIGSEGV
            # al importar pandas 2.x compilado contra numpy nuevo.
            import sys as _sys
            python_exe = _sys.executable
            # Pasamos el código por stdin para evitar escapado de shell
            result = subprocess.run(
                [python_exe],
                input=code,
                capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=120,
            )
            out = (result.stdout or "")
            if result.stderr:
                # Filtrar warnings ruidosos de gRPC/google.auth (no son errores)
                stderr_lines = []
                for ln in result.stderr.splitlines():
                    if ("FutureWarning" in ln or "ev_poll_posix" in ln
                            or "warnings.warn" in ln or "ABSL" in ln):
                        continue
                    stderr_lines.append(ln)
                stderr_clean = "\n".join(stderr_lines).strip()
                if stderr_clean:
                    out += "\n[STDERR]\n" + stderr_clean
            if result.returncode != 0:
                out += f"\n[exit code: {result.returncode}]"
            if len(out) > 50000:
                out = out[:50000] + f"\n[...truncado, total {len(out)} chars]"
            return out or "(sin output)"
        elif name == "bash":
            cmd = args.get("command", "").strip()
            if not cmd:
                return "ERROR: comando vacío."
            # Heurística defensiva: bloquear comandos obviamente destructivos
            BLOCK = ["rm -rf /", "git push", "git commit", "git reset --hard",
                     "git checkout --", "shutdown", "reboot"]
            if any(b in cmd for b in BLOCK):
                return f"ERROR: comando bloqueado por seguridad ({cmd[:60]})"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=120,
            )
            out = (result.stdout or "") + ("\n[STDERR]\n" + result.stderr if result.stderr else "")
            if len(out) > 50000:
                out = out[:50000] + f"\n[...truncado, total {len(out)} chars]"
            return out or "(sin output)"
        elif name == "read_file":
            p = Path(args.get("path", ""))
            if not p.is_absolute():
                p = PROJECT_DIR / p
            try:
                p = p.resolve()
                # Cinturón: que no se salga del proyecto
                p.relative_to(PROJECT_DIR.resolve())
            except Exception:
                return f"ERROR: ruta fuera del proyecto: {p}"
            if not p.is_file():
                return f"ERROR: no es un archivo: {p}"
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 80000:
                content = content[:80000] + f"\n[...truncado, total {len(content)} chars]"
            return content
        else:
            return f"ERROR: herramienta desconocida '{name}'."
    except subprocess.TimeoutExpired:
        return "ERROR: comando excedió 120s."
    except Exception as e:
        return f"ERROR ejecutando {name}: {type(e).__name__}: {e}"


def _truncate_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Limita el histórico a las últimas HISTORY_MAX_TURNS entradas usuario+modelo."""
    if len(history) <= HISTORY_MAX_TURNS * 2:
        return history
    return history[-HISTORY_MAX_TURNS * 2:]


async def _run_gemini(chat_id: int, prompt: str, continue_session: bool = True) -> Tuple[int, str, str]:
    """Llama a Gemini con tool-use loop. Mantiene historial por chat_id."""
    if not continue_session:
        _conv_history.pop(chat_id, None)
    history = _conv_history.get(chat_id, [])
    history.append({"role": "user", "parts": [{"text": prompt}]})

    # Sustitución dinámica: hoy ISO en el system prompt
    hoy_iso = _dt.date.today().isoformat()
    system_eff = SYSTEM_PROMPT.replace("__HOY__", hoy_iso)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_eff,
        tools=TOOLS_BOT_DATOS,
    )

    try:
        async with asyncio.timeout(LLM_TIMEOUT):
            for step in range(GEMINI_MAX_STEPS):
                # Llamar al modelo (en thread aparte, porque genai es bloqueante)
                response = await asyncio.to_thread(model.generate_content, history)

                # Extraer parts de la respuesta
                candidates = getattr(response, "candidates", None) or []
                if not candidates:
                    return -1, "", "Gemini devolvió respuesta vacía (sin candidates)."
                cand = candidates[0]
                content = getattr(cand, "content", None)
                if not content or not getattr(content, "parts", None):
                    # Puede ser un block por safety u otra causa
                    finish = getattr(cand, "finish_reason", "?")
                    return -1, "", f"Gemini terminó sin contenido (finish_reason={finish})."

                parts = list(content.parts)

                # Detectar function_calls
                fcalls = []
                for p in parts:
                    fc = getattr(p, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        fcalls.append(fc)

                if fcalls:
                    # Guardar el mensaje del modelo (con sus tool calls) en historial
                    history.append({"role": "model", "parts": parts})
                    # Ejecutar todas las herramientas y devolver resultados
                    tool_response_parts = []
                    for fc in fcalls:
                        # fc.args es un dict-like (proto MapComposite)
                        try:
                            args = dict(fc.args) if fc.args else {}
                        except Exception:
                            args = {}
                        # Log completo del comando para debugging
                        if fc.name == "python":
                            log.info("[%s] >>> PYTHON:\n%s", chat_id, args.get("code", ""))
                        elif fc.name == "bash":
                            log.info("[%s] >>> BASH:\n%s", chat_id, args.get("command", ""))
                        else:
                            log.info("[%s] tool '%s' args=%s", chat_id, fc.name, str(args))
                        result = await asyncio.to_thread(_exec_tool, fc.name, args)
                        # Log del resultado (truncado a 800 chars para no saturar)
                        log.info("[%s] <<< RESULT (%s, %d chars):\n%s",
                                 chat_id, fc.name, len(result), result[:800])
                        tool_response_parts.append({
                            "function_response": {
                                "name": fc.name,
                                "response": {"result": result},
                            }
                        })
                    history.append({"role": "user", "parts": tool_response_parts})
                    continue

                # Sin function_calls: respuesta final en texto
                text = ""
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        text += t
                history.append({"role": "model", "parts": [{"text": text}]})
                _conv_history[chat_id] = _truncate_history(history)
                return 0, text.strip(), ""

            # Salimos del bucle por límite de pasos
            _conv_history[chat_id] = _truncate_history(history)
            return -1, "", f"Límite de iteraciones alcanzado ({GEMINI_MAX_STEPS})."
    except asyncio.TimeoutError:
        return -1, "", f"Timeout: Gemini tardó más de {LLM_TIMEOUT}s."
    except Exception as e:
        log.exception("Error en _run_gemini: %s", e)
        return -1, "", f"{type(e).__name__}: {e}"
    # NB: si llegamos aquí, devolvemos algo válido para que el helper original
    # de _process_prompt no pete; el envoltorio antiguo esperaba (rc, out, err).
    return 0, "(sin texto)", ""


# Compat: dejamos un alias por si algún sitio del repo aún llama _run_claude.
_run_claude = _run_gemini


# ─── Handlers ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text(
            "🚫 Acceso denegado.\n\n"
            "Si eres miembro del cuerpo técnico o jugador y crees que deberías "
            "tener acceso, escríbele a Arkaitz con tu chat_id.\n\n"
            f"Tu chat_id es: {update.effective_chat.id if update.effective_chat else '?'}"
        )
        return
    await update.message.reply_text(
        "👋 Hola! Soy el asistente de datos del equipo.\n\n"
        "Pregúntame cualquier cosa sobre los datos de la temporada:\n"
        "• «¿cuánto peso perdió Carlos ayer?»\n"
        "• «dame el ACWR del equipo esta semana»\n"
        "• «qué jugadores tienen wellness bajo últimamente»\n"
        "• «cuántas sesiones lleva Gonzalo esta temporada»\n\n"
        "Mantengo el hilo entre mensajes: puedes preguntar «y Pirata?» "
        "después de preguntar por Carlos, y entiendo el contexto.\n\n"
        "Comandos:\n"
        "• /nuevo → empezar conversación nueva\n"
        "• /yo → ver tu chat_id"
    )


async def cmd_yo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    user = update.effective_user.username if update.effective_user else None
    await update.message.reply_text(
        f"Tu chat_id es: `{chat_id}`\n"
        f"Usuario: @{user if user else 'sin_username'}\n\n"
        f"{'✅ Estás autorizado.' if _authorized(update) else '❌ NO estás autorizado todavía. Pídele acceso a Arkaitz.'}",
        parse_mode="Markdown",
    )


async def cmd_nuevo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    _fresh_chats.add(chat_id)
    # Limpiamos también el histórico de Gemini de ese chat
    _conv_history.pop(chat_id, None)
    await update.message.reply_text(
        "🆕 Vale, el próximo mensaje empezará una conversación nueva "
        "(olvido el contexto anterior)."
    )


async def cmd_oliver_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Permite al cuerpo técnico disparar la sincronización de Oliver."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🏃 Sincronizando Oliver Sports (MVP)…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/python3", str(PROJECT_DIR / "src" / "oliver_sync.py"),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=1200)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            await update.message.reply_text("⚠️ Timeout (>20 min).")
            return
    finally:
        stop.set()
        try: await task
        except Exception: pass

    if proc.returncode == 0:
        # Recalcular cruces
        proc2 = await asyncio.create_subprocess_exec(
            "/usr/bin/python3", str(PROJECT_DIR / "src" / "calcular_vistas.py"),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc2.communicate(), timeout=600)
        except asyncio.TimeoutError:
            proc2.kill(); await proc2.wait()
        await update.message.reply_text("✅ Sincronizado. Ya están los datos actualizados.")
    else:
        detalle = (err or out or b"").decode("utf-8", "replace").strip()
        for chunk in _chunks(f"❌ Error:\n{detalle[-1500:]}"):
            await update.message.reply_text(chunk)


async def _process_prompt(prompt: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                          kind: str = "texto"):
    """Pasa el prompt a Claude y devuelve la respuesta al chat.
    Misma lógica se usa para mensajes de texto y mensajes de voz transcritos."""
    chat_id = update.effective_chat.id
    user_name = (update.effective_user.first_name if update.effective_user else None) or "usuario"
    continuar = chat_id not in _fresh_chats
    _fresh_chats.discard(chat_id)

    log.info("[%s] → %s: %s",
             chat_id,
             "continuar" if continuar else "NUEVA",
             prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    try:
        rc, out, err = await _run_gemini(chat_id, prompt, continue_session=continuar)
    finally:
        stop.set()
        try:
            await typing_task
        except Exception:
            pass

    if rc != 0:
        detalle = (err or out or "(sin detalles)").strip()
        msg = f"⚠️ Algo falló al consultar los datos.\nDetalle técnico (para Arkaitz):\n{detalle[:1500]}"
        for chunk in _chunks(msg):
            await update.message.reply_text(chunk)
        _append_log(chat_id, user_name, prompt, msg, kind=kind)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 No he podido generar respuesta.")
        _append_log(chat_id, user_name, prompt, "(sin respuesta)", kind=kind)
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)
    _append_log(chat_id, user_name, prompt, response, kind=kind)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        user = update.effective_user.username if update.effective_user else "?"
        log.warning("Acceso denegado chat_id=%s (@%s)", chat_id, user)
        await update.message.reply_text(
            f"🚫 Acceso denegado.\n"
            f"Tu chat_id ({chat_id}) no está autorizado.\n"
            f"Pídele acceso a Arkaitz."
        )
        return

    prompt = (update.message.text or "").strip()
    if not prompt:
        return
    await _process_prompt(prompt, update, ctx)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Transcribe audio/voz con Whisper y lo procesa como si fuera texto."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return

    if not _WHISPER_OK:
        await update.message.reply_text(
            "🎤 Audio no soportado en esta instalación.\n"
            "Faltaría instalar `faster-whisper`. Escríbemelo en texto por ahora."
        )
        return

    voice = update.message.voice or update.message.audio or update.message.video_note
    if voice is None:
        return

    chat_id = update.effective_chat.id
    # Mientras transcribe, mostrar "grabando audio" emoji
    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)

    tmp = tempfile.NamedTemporaryFile(prefix="tg_voice_", suffix=".ogg", delete=False)
    tmp.close()
    audio_path = tmp.name

    try:
        tg_file = await voice.get_file()
        await tg_file.download_to_drive(audio_path)
        log.info("[%s] 🎤 audio %.1fs → transcribiendo", chat_id,
                 getattr(voice, "duration", 0) or 0)
        text = await _transcribir(audio_path)
    except Exception as e:
        log.exception("Error transcribiendo: %s", e)
        await update.message.reply_text(
            f"⚠️ No he podido transcribir el audio: {type(e).__name__}"
        )
        return
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass

    if not text:
        await update.message.reply_text(
            "🤷 No he entendido el audio. ¿Puedes repetirlo más claro o escribirlo?"
        )
        return

    # Confirmar al usuario qué he entendido (por si hay error de transcripción)
    await update.message.reply_text(f"🎤 Entendido: «{text}»")

    await _process_prompt(text, update, ctx, kind="voz")


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.exception("Error: %s", ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(
                update.effective_chat.id,
                f"⚠️ Error interno: {type(ctx.error).__name__}",
            )
        except Exception:
            pass


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("yo", cmd_yo))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("oliver_sync", cmd_oliver_sync))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, on_voice))
    app.add_error_handler(on_error)
    log.info("Bot de DATOS arrancado (voz: %s). Ctrl+C para parar.",
             "ON" if _WHISPER_OK else "OFF")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
