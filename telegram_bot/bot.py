#!/usr/bin/env python3
"""
Bot de Telegram para interactuar con Claude Code desde el móvil.
Proyecto: Arkaitz 25/26

Lee configuración desde .env y ejecuta `claude -p` sobre el proyecto.
Solo responde al chat_id autorizado (ALLOWED_CHAT_ID).
"""
from __future__ import annotations

import os
import io
import re
import asyncio
import datetime as _dt
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any

from dotenv import load_dotenv
from telegram import Update, constants, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
    CallbackQueryHandler,
)

# Gemini (Google AI Studio) — backend LLM gratuito.
import google.generativeai as genai

# Whisper es opcional: si no está instalado, el bot sigue funcionando solo con texto.
try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception:
    _WHISPER_OK = False

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PROJECT_DIR     = Path(os.getenv("PROJECT_DIR", str(HERE.parent))).expanduser().resolve()
LLM_TIMEOUT     = int(os.getenv("LLM_TIMEOUT", "600"))
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_MAX_STEPS = int(os.getenv("GEMINI_MAX_STEPS", "12"))
HISTORY_MAX_TURNS = int(os.getenv("HISTORY_MAX_TURNS", "16"))

MAX_MSG_LEN = 4000  # margen sobre el límite 4096 de Telegram
BOT_NAME    = "InterFS_bot"  # identificador en los logs espejados

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("arkaitz-bot")


# ─── Validación previa ───────────────────────────────────────────────────────
def _fail(msg: str) -> None:
    log.error(msg)
    raise SystemExit(f"\n❌ {msg}\n")


if not TOKEN:
    _fail("Falta TELEGRAM_BOT_TOKEN en el archivo .env (ver LEEME.md).")

if not ALLOWED_CHAT_ID:
    _fail("Falta ALLOWED_CHAT_ID en el archivo .env (ver LEEME.md).")

try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID)
except ValueError:
    _fail("ALLOWED_CHAT_ID debe ser un número entero (tu chat_id de Telegram).")

if not PROJECT_DIR.is_dir():
    _fail(f"PROJECT_DIR no existe: {PROJECT_DIR}")

if not GEMINI_API_KEY:
    _fail("Falta GEMINI_API_KEY en .env (consíguela gratis en aistudio.google.com/apikey).")

genai.configure(api_key=GEMINI_API_KEY)

log.info("Backend LLM: Gemini (%s)", GEMINI_MODEL)
log.info("Proyecto: %s", PROJECT_DIR)
log.info("Autorizado chat_id: %s", ALLOWED_CHAT_ID)


# ─── Espejo de conversaciones (para sincronizar móvil ↔ ordenador) ───────────
LOGS_DIR = PROJECT_DIR / "telegram_logs"
LOGS_DIR.mkdir(exist_ok=True)


def _append_log(chat_id: int, user_name: str, user_msg: str, bot_reply: str, kind: str = "texto") -> None:
    """Guarda un intercambio en telegram_logs/YYYY-MM-DD.md.
    Pensado para que el siguiente 'claude' que se abra (aquí o en Desktop)
    pueda leer esto y retomar el hilo sin perderse nada."""
    try:
        hoy = _dt.datetime.now().strftime("%Y-%m-%d")
        hora = _dt.datetime.now().strftime("%H:%M:%S")
        path = LOGS_DIR / f"{hoy}.md"
        etiqueta = f"🎤 (voz)" if kind == "voz" else "💬"
        bloque = (
            f"\n---\n"
            f"### {hora} · {BOT_NAME} · chat `{chat_id}` · {etiqueta}\n\n"
            f"**{user_name or 'Arkaitz'}:**\n{user_msg.strip()}\n\n"
            f"**Claude:**\n{bot_reply.strip()}\n"
        )
        with path.open("a", encoding="utf-8") as f:
            f.write(bloque)
    except Exception as e:
        log.warning("No pude escribir log de conversación: %s", e)


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _authorized(update: Update) -> bool:
    return bool(update.effective_chat) and update.effective_chat.id == ALLOWED_CHAT_ID


def _chunks(text: str, size: int = MAX_MSG_LEN):
    """Parte texto en trozos <= size, intentando cortar por saltos de línea."""
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
    """Mantiene activo el indicador 'escribiendo...' hasta que stop.set()."""
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


# Memoria conversacional: conjunto de chats que deben empezar sesión nueva
# (vacío = continuar sesión previa con -c)
_fresh_chats: set = set()

# Acciones locales (slash commands) ejecutadas DESDE el último prompt mandado
# a Claude. Se inyectan como contexto al próximo prompt para que Claude no
# pierda el hilo (porque los slash commands los ejecuta el bot directamente,
# Claude no se entera de que se han disparado).
_acciones_pendientes: dict = {}  # chat_id -> list[str]


def _registrar_accion_local(chat_id: int, descripcion: str) -> None:
    """Apunta que el usuario ha ejecutado un comando local (no via Claude).

    En el próximo prompt a Claude, le contaremos qué pasó mientras tanto.
    `descripcion` debe ser una frase corta tipo:
      "/enlaces (enlaces genéricos del día, mandados al usuario)"
      "/consolidar (consolidó Forms y recalculó vistas, OK)"
    """
    _acciones_pendientes.setdefault(chat_id, []).append(
        f"{_dt.datetime.now().strftime('%H:%M')} — {descripcion}"
    )

# Modo "/ejercicios_voz": chat_id → timestamp de activación (vence a los 15 min)
_modo_ejercicios_voz: dict = {}
EJVOZ_TTL_SEG = 15 * 60

# Modo "/sesion": chat_id → timestamp de activación (vence a los 15 min)
_modo_sesion_voz: dict = {}
_modo_goles_voz: dict = {}
GOLESVOZ_TTL_SEG = 15 * 60  # 15 minutos
SESVOZ_TTL_SEG = 15 * 60

# Modelo Whisper (lazy load; primera vez descarga ~150MB, luego cacheado)
_whisper_model = None
_whisper_lock = asyncio.Lock()
WHISPER_SIZE = os.getenv("WHISPER_MODEL", "base")


async def get_whisper():
    global _whisper_model
    if not _WHISPER_OK:
        return None
    if _whisper_model is not None:
        return _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            log.info("Cargando modelo Whisper (%s)…", WHISPER_SIZE)
            def _load():
                return WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
            _whisper_model = await asyncio.get_event_loop().run_in_executor(None, _load)
            log.info("Whisper listo.")
    return _whisper_model


async def _transcribir(audio_path: str) -> str:
    model = await get_whisper()
    if model is None:
        raise RuntimeError("Whisper no disponible.")
    def _run():
        segments, info = model.transcribe(
            audio_path, language="es", beam_size=5, vad_filter=True,
        )
        return " ".join(s.text for s in segments).strip()
    return await asyncio.get_event_loop().run_in_executor(None, _run)


# ─── Backend Gemini con tool-use ─────────────────────────────────────────────
# El bot dev usa Gemini con tools de lectura/escritura/ejecución para poder
# investigar el proyecto, modificar archivos y ejecutar scripts.
#
# Conversación en memoria por chat_id. Al reiniciar el bot, se pierde.

_conv_history: Dict[int, List[Dict[str, Any]]] = {}


SYSTEM_PROMPT_DEV = f"""\
Eres el asistente personal de Arkaitz (director técnico de Movistar Inter FS,
fútbol sala). Le respondes desde Telegram. Hoy es __HOY__.

ESTILO DE COMUNICACIÓN — IMPORTANTE:
- **Conversacional, natural, como un compañero de trabajo**. Arkaitz te
  escribe en lenguaje suelto ("oye", "y qué tal va X", "puedes mirar Y")
  y tú respondes igual. NO formal, NO acartonado, NO listas siempre.
- Frases cortas. Va al grano. Si la respuesta cabe en una línea, una línea.
- Markdown simple (negritas para nombres y números). NO HTML, NO emojis a
  cada paso (uno o dos en mensajes largos como mucho).
- Si lo que pide se puede hacer ya con tools, hazlo y entrega la respuesta.
  No describas tu plan.
- Tono: el de WhatsApp con un colega. Tutea siempre. "Vale, mira",
  "Ya está", "Pues sale X", "Lo he hecho" en vez de "Procedo a ejecutar
  la consulta solicitada".
- Cuando algo falla, díselo en humano: "no me sale", "hay un fallo en
  la hoja X" en vez de "exit code 1: ImportError".

⚠️⚠️⚠️ REGLA #0a — ATAJO OBLIGATORIO PARA "ESTADO DE JUGADOR" ⚠️⚠️⚠️
Si te preguntan por el ESTADO, CARGA, FATIGA, BORG, o "qué tal" de un
jugador concreto (frases tipo "cómo está Pirata", "carga últimas 10
sesiones de Raya", "qué tal Carlos"…), NO escribas código Python que
saque datos brutos.

USA OBLIGATORIAMENTE el script:
```bash
/usr/bin/python3 {PROJECT_DIR}/src/estado_jugador.py NOMBRE [N_SESIONES]
```
Devuelve un Markdown ya analizado (carga + histórico + equipo + ACWR +
monotonía + wellness + recomendación). Tú le mandas a Arkaitz el output
LITERAL. NO lo resumas ni lo reescribas. Solo si pregunta algo extra
específico, complementas con una consulta Python después.

Ejemplo:
  Arkaitz: "¿qué tal va Anchu?"
  Tú: [bash → /usr/bin/python3 {PROJECT_DIR}/src/estado_jugador.py ANCHU]
  Tú: envías el output tal cual.

⚠️ REGLA #0a-bis — CARGA POR JUGADOR DE LA ÚLTIMA SESIÓN ⚠️
Si Arkaitz pregunta:
  "carga jugador por jugador de la última sesión"
  "borg del último entreno"
  "carga del entreno de hoy"
  "qué tal la sesión de hoy"
  "borg del 13/05" (cualquier fecha)

USA OBLIGATORIAMENTE este script:
```bash
/usr/bin/python3 {PROJECT_DIR}/src/carga_ultima_sesion.py [YYYY-MM-DD]
```
- Sin argumento → última sesión registrada.
- Con fecha YYYY-MM-DD → la de esa fecha.

Cruza Borg con minutos REALES de cada jugador (no los minutos generales
de SESIONES), aplica multiplicadores GYM/MIXTA, e incluye métricas Oliver
(carga mecánica, ACWR mecánico, ratio Borg/Oliver) si las hay.

NO escribas Python a mano con `BORG × SESIONES.MINUTOS` — eso da carga
idéntica a todos los que tienen mismo Borg porque ignora minutos reales
en partido. Usa el script.

Mandas el output LITERAL a Arkaitz. Si pregunta algo extra ("por qué
PIRATA tiene tan poca carga"), respondes con un análisis pero
manteniendo los datos del script como base.

⚠️ REGLA #0b — RESPUESTAS CON DATOS NUMÉRICOS LIBRES: SIEMPRE CON CONTEXTO ⚠️
Arkaitz es director técnico. Un número aislado NO le sirve para tomar
decisiones. CUANDO DEVUELVAS DATOS NUMÉRICOS de un jugador (Borg, fatiga,
carga, peso, wellness, etc.), tu respuesta DEBE incluir:

  1. **El dato pedido**, en negrita.
  2. **Comparación** con al menos UNA de:
     - la media histórica DEL PROPIO JUGADOR (toda la temporada),
     - la media del equipo en el mismo periodo,
     - el rango habitual del jugador (mín-máx),
     - la semana anterior o el mismo periodo del mes pasado.
  3. **Interpretación corta**: ¿está dentro de lo normal? ¿alto, bajo,
     en zona de riesgo? Usa los umbrales del proyecto cuando apliquen
     (ACWR, monotonía, wellness ≤10/13, etc.).
  4. **Recomendación práctica** si el dato lo merece (controlar carga,
     descanso, hablar con el jugador, sin alarma). Si todo está normal,
     dilo: "todo dentro de lo esperado".

Ejemplo MAL (lo que NO debes hacer):
  > "La fatiga media de Raya en las últimas 10 sesiones es de 4.90."

Ejemplo BIEN:
  > "Borg medio últimas 10 sesiones de **Raya**: **4.9** (esfuerzo
  > medio-bajo). Su media histórica esta temporada es 5.4 y el equipo
  > anda en 5.6, así que va algo por debajo. Coherente con su última
  > semana de carga (ACWR 0.85). Nada preocupante, pero si lo notas
  > apagado en pista, podemos meterle una sesión más exigente."

Si el dato es BORG medio (esfuerzo subjetivo 0-10), no lo llames
"fatiga" — fatiga es la métrica calculada (carga × monotonía) en
_VISTA_SEMANAL. Si el usuario dice "fatiga", elige la fuente correcta:
  - "fatiga últimas sesiones" → Borg de _VISTA_CARGA (subjetivo del jugador).
  - "fatiga semanal" / "métrica de fatiga" → FATIGA de _VISTA_SEMANAL.
Aclara qué métrica le estás dando.

⚠️ REGLA #1 — ACCIÓN INMEDIATA, NO RELATO:
Cuando Arkaitz te pida datos del Sheet, código del proyecto, o ejecutar
algo: USA LAS TOOLS DIRECTAMENTE. **No digas "dame un segundo"**, "OK,
me pongo a ello", "voy a buscarlo", "lo miro". Esas frases sin tool call
son INACEPTABLES porque te quedas sin actuar y Arkaitz cree que estás
trabajando cuando no estás haciendo nada.

Patrón correcto:
  Usuario: "dame X"
  Tú (sin texto previo): [llamas a la tool python con el código]
  Tool devuelve: [resultado]
  Tú: "Aquí tienes: <respuesta humana con los datos>"

Patrón INCORRECTO (no hagas esto):
  Usuario: "dame X"
  Tú: "Claro, dame un segundo y te lo busco"  ← MAL, falta tool call
  [conversación termina, Arkaitz cree que estás trabajando pero no]

Si la pregunta es ambigua, primero **intenta** una interpretación razonable
y devuelve datos. Solo pregunta clarificación si NO HAY MANERA de adivinar.

PROYECTO:
- Repo: {PROJECT_DIR}
- README maestro: {PROJECT_DIR}/CLAUDE.md (léelo si necesitas contexto del
  stack, decisiones, estado o convenciones).
- Estado: {PROJECT_DIR}/docs/estado_proyecto.md
- Logs Telegram: {PROJECT_DIR}/telegram_logs/YYYY-MM-DD.md (te ayudan a
  recuperar el hilo si Arkaitz dice "qué te dije antes" o "ponme al día").

QUÉ TE PIDE TÍPICAMENTE:
- "Consolida los Forms" / "/consolidar" → ese es un slash command, lo
  ejecuta el bot, tú no haces nada.
- "Mándame los enlaces de hoy" / "/enlaces" → idem.
- "Apunta la sesión" / "/sesion" → idem.
- "Investiga por qué X" / "ponme al día" / "qué tal Carlos" → aquí sí
  entras tú: lees Sheets, lees código, contestas.
- "Arregla el bug en X" → editas el archivo correspondiente (con `edit_file`)
  y le confirmas qué cambiaste. Para refactors grandes, pregunta antes.

HERRAMIENTAS:
- `python`: ejecuta Python (venv del bot tiene gspread, pandas, etc).
  Mete TODO el script en una sola llamada. NO partas en varias llamadas
  porque cada una arranca un proceso nuevo.
- `bash`: shell (ls, head, grep, git diff/log/status). Para Python usa
  `python`, no `bash`.
- `read_file`: lee un archivo del proyecto.
- `write_file`: crea/sobrescribe un archivo.
- `edit_file`: sustituye un fragmento exacto en un archivo (más quirúrgico).

DATOS DEL EQUIPO (Google Sheets):
El Sheet "Arkaitz - Datos Temporada 2526" tiene las hojas crudas
(SESIONES, BORG, PESO, WELLNESS, LESIONES, FISIO) y vistas pre-calculadas
(_VISTA_CARGA, _VISTA_SEMANAL, _VISTA_PESO, _VISTA_WELLNESS,
_VISTA_SEMAFORO, _VISTA_RECUENTO). Cuando le respondas a Arkaitz sobre
datos del equipo, **prefiere las _VISTA_*** (ya tienen los cálculos
hechos: ACWR, monotonía, sRPE, semáforo, desviaciones de baseline).

Esquema COMPLETO (verificado 12 mayo 2026, columnas exactas):
- BORG: FECHA, TURNO, JUGADOR, BORG (número 0-10 o letra S/A/L/N/D/NC)
- PESO: FECHA, TURNO, JUGADOR, PESO_PRE, PESO_POST, H2O_L (decimales con coma)
- WELLNESS: FECHA, JUGADOR, SUENO, FATIGA, MOLESTIAS, ANIMO, TOTAL
- SESIONES: FECHA, SEMANA, TURNO, TIPO_SESION, MINUTOS, COMPETICION (sin JUGADOR)
- _VISTA_CARGA: FECHA, FECHA_STR, SEMANA, DIA_SEMANA, TURNO, JUGADOR,
  TIPO_SESION, COMPETICION, MINUTOS, BORG, CARGA (sRPE).
  ★ USA ESTA VISTA para preguntas POR SESIÓN ("últimas N sesiones").
- _VISTA_SEMANAL: FECHA_LUNES, SEMANA_ISO, AÑO, JUGADOR, CARGA_SEMANAL,
  SESIONES, BORG_MEDIO, ACWR, CARGA_AGUDA, CARGA_CRONICA, MONOTONIA,
  FATIGA, SEMAFORO.
  ★ USA ESTA VISTA para preguntas POR SEMANA. ⚠️ NO TIENE columna 'FECHA',
  la columna fecha se llama FECHA_LUNES.
- _VISTA_PESO: FECHA, SEMANA, DIA_SEMANA, TURNO, JUGADOR, TIPO_SESION,
  COMPETICION, PESO_PRE, PESO_POST, DIFERENCIA, PCT_PERDIDA, H2O_L,
  ALERTA_PESO, BASELINE_PRE, DESVIACION_BASELINE.
- _VISTA_WELLNESS: FECHA, SEMANA, DIA_SEMANA, JUGADOR, SUENO, FATIGA,
  MOLESTIAS, ANIMO, TOTAL, WELLNESS_7D, BASELINE_WELLNESS,
  DESVIACION_BASELINE, SEMAFORO_WELLNESS.
- _VISTA_SEMAFORO: JUGADOR, SEMANA, ACWR, MONOTONIA, SEMAFORO_CARGA,
  WELLNESS_MEDIO, WELLNESS_BELOW15, SEMAFORO_WELLNESS, PESO_PRE_DESV_KG,
  SEMAFORO_PESO, ALERTAS_ACTIVAS, SEMAFORO_GLOBAL.
- _VISTA_RECUENTO: JUGADOR, TOTAL_SESIONES_EQUIPO, EST_S, EST_A, EST_L,
  EST_N, EST_D, EST_NC, EST_NJ, SESIONES_CON_DATOS, PCT_PARTICIPACION.

⚡ MUY IMPORTANTE — SANDBOX PYTHON PARA EL SHEET ⚡
El sandbox Python YA TIENE PREIMPORTADOS y listos para usar:
  - `pd` (pandas)
  - `gspread`
  - `ss` ← objeto Spreadsheet ya abierto ("Arkaitz - Datos Temporada 2526")
  - `creds`, `gc` (por si los necesitas)

NO escribas `import gspread`, NO escribas `Credentials.from_service_account_file(...)`,
NO escribas `creds = ...`. Solo usa `ss.worksheet(...)` directamente.

Plantilla MÍNIMA (escribe solo lo de debajo, sin imports ni creds):
```python
df = pd.DataFrame(ss.worksheet('NOMBRE_HOJA').get_all_records(
    value_render_option=gspread.utils.ValueRenderOption.unformatted))
# ⚠️ SIEMPRE con value_render_option=UNFORMATTED: sin esto los números
# con coma decimal (74,7) llegan como 747.
# ⚠️ NO ANIDES comillas dobles dentro de f-strings (Python 3.11). Usa
# comillas simples dentro:
#   BIEN:  print(f"Hoy es {{f.strftime('%d/%m')}}")
#   MAL:   print(f"Hoy es {{f.strftime(\"%d/%m\")}}")  ← SyntaxError
# pesos con coma decimal:
# df['PESO_PRE'] = pd.to_numeric(df['PESO_PRE'].astype(str).str.replace(',','.'), errors='coerce')
# fechas:
# df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
```

ACCIONES COMUNES DE ESCRITURA AL SHEET:

1) **Marcar jugador como LESIONADO hoy** (ej. "apunta a Pani como lesionado"):
   → USA SIEMPRE el script `src/marcar_lesion.py`. NO escribas Python a mano.
     El script ya escribe en BORG (con 'L') y en LESIONES de forma idempotente.

   Llamada estándar (turno se autodetecta de SESIONES si lo omites):
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_lesion.py JUGADOR YYYY-MM-DD
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_lesion.py PANI 2026-05-08
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_lesion.py PIRATA 2026-05-08 T
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_lesion.py PANI 2026-05-08 --dry-run
   ```

   El script imprime un resumen tras `---MSG---` que puedes pasar tal cual a
   Arkaitz. Si falla algo, NO inventes Python alternativo: dile a Arkaitz el
   error literal y para.

1b) **Jugador RETIRADO a mitad de sesión por lesión/molestia** (ej.
   "Pirata se retiró hoy en el minuto 25 por molestia en el gemelo",
   "Pani no acabó el entreno, paró en el 40 por aductor"):
   → USA SIEMPRE el script `src/marcar_retirado.py`.
     Es DISTINTO de marcar_lesion: aquí SÍ entrenó parte de la sesión.
     Escribe en BORG (con valor numérico si lo dio, o "NC" si no) más
     la columna INCIDENCIA = "Retirado min X - motivo". Y añade fila
     a LESIONES.

   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_retirado.py JUGADOR YYYY-MM-DD MIN "MOTIVO" [TURNO]
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_retirado.py PIRATA 2026-05-14 25 "gemelo derecho"
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_retirado.py PANI 2026-05-14 40 "aductor" T
   /usr/bin/python3 {PROJECT_DIR}/src/marcar_retirado.py RAYA 2026-05-14 15 "molestia rodilla" --borg 6
   ```

   Si Arkaitz mencionó el Borg ("…se retiró pero apuntó un 7"), usa
   `--borg 7`. Si no, omítelo (queda como NC).

2) **Otros estados en BORG (S/A/D/N/NC) o Borg numérico**:
   → USA SIEMPRE el script `src/apuntar_borg.py`. NO escribas Python a mano.
     Es idempotente: si la fila existe se actualiza, si no se añade.

   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_borg.py JUGADOR YYYY-MM-DD VALOR [TURNO]
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_borg.py CARLOS 2026-05-08 7
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_borg.py PANI 2026-05-08 S        # Selección
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_borg.py JAVI 2026-05-08 D T      # Descanso, turno T
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_borg.py CARLOS 2026-05-08 7 --dry-run
   ```

   Estados: S=Selección · A=Ausencia · L=Lesión (mejor marcar_lesion.py) ·
            N=No entrena · D=Descanso · NC=No calificado ·
            NJ=No juega (convocado al partido pero no participa).

3a) **Apuntar WELLNESS (Sueño/Fatiga/Molestias/Ánimo)**:
   → USA SIEMPRE el script `src/apuntar_wellness.py`. Idempotente.
     Calcula TOTAL automáticamente. Cada componente 1-5.

   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_wellness.py JUGADOR YYYY-MM-DD \
       --sueno N --fatiga N --molestias N --animo N
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_wellness.py PIRATA 2026-05-11 --sueno 4 --fatiga 3 --molestias 4 --animo 5
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_wellness.py JAVI 2026-05-11 --molestias 2 --animo 3
   ```

   Notas:
   - Solo wellness UNA VEZ AL DÍA (no por turno).
   - Puedes pasar uno o varios componentes; los omitidos se mantienen
     si la fila ya existía. Si no existía, se quedan vacíos.
   - Cada componente: 1 (mal) a 5 (bien).
   - El TOTAL (4-20) se calcula solo: ≤10 rojo · 11-13 naranja · ≥14 verde.

3) **Apuntar PESO (PRE / POST / H2O)**:
   → USA SIEMPRE el script `src/apuntar_peso.py`. Idempotente.
     Solo se actualizan los campos que pasas; los demás se quedan como están.

   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_peso.py JUGADOR YYYY-MM-DD [TURNO] --pre N --post N --h2o N
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_peso.py CARLOS 2026-05-08 --pre 75.4
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_peso.py PIRATA 2026-05-08 T --pre 78.2 --post 77.5
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_peso.py JAVI 2026-05-08 --pre 71 --post 70.4 --h2o 45.2
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_peso.py PANI 2026-05-08 --pre 70.5 --dry-run
   ```

   Validación: pesos fuera de 40-200 kg se rechazan automáticamente
   (filtro fisiológico). Coma o punto decimal funcionan ambos.

4) **Apuntar SESIÓN nueva** (a la hoja SESIONES):
   → USA SIEMPRE el script `src/apuntar_sesion.py`. Idempotente.

   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_sesion.py FECHA TURNO TIPO MIN [--comp X]
   ```

   Ejemplos:
   ```bash
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_sesion.py 2026-05-12 M TEC-TAC 75
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_sesion.py 2026-05-12 T GYM+TEC-TAC 90
   /usr/bin/python3 {PROJECT_DIR}/src/apuntar_sesion.py 2026-05-15 T PARTIDO 40 --comp LIGA
   ```

   Tipos: FISICO · TEC-TAC · GYM · RECUP · PARTIDO · PORTEROS · MATINAL ·
   GYM+TEC-TAC · FISICO+TEC-TAC.
   Turnos: M · T · P.
   Competiciones: LIGA · COPA DEL REY · COPA ESPAÑA · COPA MOSTOLES ·
   COPA RIBERA · SUPERCOPA · PRE-TEMPORADA · AMISTOSO.

5) **NO escribas a Forms (`_FORM_PRE`, `_FORM_POST`)** — esas hojas las
   alimenta Google Forms automáticamente. Tampoco a `_VISTA_*` (se
   regeneran solas). Solo escribe a hojas crudas: BORG, PESO, WELLNESS,
   LESIONES, FISIO, SESIONES, _EJERCICIOS.

6) **REGLA GENERAL para escribir al Sheet**: si existe un script
   `src/apuntar_*.py` o `src/marcar_*.py` para la acción, **úsalo SIEMPRE**.
   Scripts disponibles ahora mismo:
   · `apuntar_borg.py JUGADOR FECHA VALOR [TURNO]`
   · `apuntar_peso.py JUGADOR FECHA [TURNO] --pre N --post N --h2o N`
   · `apuntar_wellness.py JUGADOR FECHA --sueno N --fatiga N --molestias N --animo N`
   · `apuntar_sesion.py FECHA TURNO TIPO MIN [--comp X]`
   · `marcar_lesion.py JUGADOR FECHA [TURNO]`
   Solo escribe Python con gspread directamente cuando NO existe un script
   curado para la operación que necesitas.

⚠️ MUY IMPORTANTE — RESPUESTA TRAS CADA TOOL CALL:
Después de ejecutar un tool (python, bash, write_file, edit_file), SIEMPRE
genera una respuesta de TEXTO en español al usuario. NO termines mudo
después de obtener datos. El usuario está esperando que le hables, no
solo que ejecutes scripts. Si un script falla, dilo en humano
("no me sale", "el script ha dado un error en X") en lugar de quedarte
en silencio.

ROSTER OFICIAL (cómo se guarda cada jugador):
PORTEROS PRIMER: HERRERO, GARCIA
CAMPO PRIMER: CECILIO, CHAGUINHA, RAUL, HARRISON, RAYA, JAVI, PANI,
  PIRATA, BARONA, CARLOS
PORTERO FILIAL: OSCAR
CAMPO FILIAL: RUBIO, JAIME, SEGO, DANI, GONZALO, PABLO, GABRI, NACHO, ANCHU

Alias comunes a tolerar: "J.Herrero"→HERRERO, "Javi García"/"J.García"→GARCIA, "Gonza"→GONZALO,
"Javi Mínguez"/"Javier"→JAVI, "Chagas"→CHAGUINHA, "Sergio"/"Vizuete"→RUBIO.
Si no encuentras un nombre, prueba `str.contains` antes de rendirte.

REGLAS DE ORO:
1. Español, frases cortas, sin rodeos. Markdown simple OK, **NO HTML**.
2. Da números concretos con nombre y fecha. Sin jerga ("DataFrame",
   "exit code", "JSON"). Si algo falla, di "no me sale" en lugar de
   "Vaya, parece que no encuentro la columna...".
3. Si el mismo error sale 2 veces seguidas, **explícaselo a Arkaitz en
   lenguaje natural** y para — no te quedes en bucle.
4. Cambios de código no triviales → pregunta antes y di qué archivos
   tocarás. Fixes pequeños obvios → tira directo.
5. **NO** escribas en .env, google_credentials.json, ni hagas git push
   sin pedir confirmación.
6. Después de modificar código del dashboard o vistas, comenta a Arkaitz
   "haz `git push` cuando quieras desplegar; Streamlit Cloud auto-despliega
   en 1-2 min".

CONTEXTO DEL BOT (lo que el bot ejecuta sin tu intervención):
- /consolidar: lee FORM_PRE/POST → BORG/PESO/WELLNESS → recalcula vistas.
- /enlaces: genera enlaces PRE+POST genéricos del día (un solo enlace
  para reenviar al grupo). El jugador elige su nombre.
- /enlaces_wa: genera UN enlace wa.me POR JUGADOR (lee teléfonos de la
  hoja TELEFONOS_JUGADORES). Cada enlace abre el chat de WhatsApp con
  ese jugador y el mensaje (PRE+POST personalizado) ya escrito; Arkaitz
  solo pulsa "Enviar". Si algún jugador no tiene teléfono configurado
  en la hoja, aparece al final como aviso.
- /prepost: lista quién ha hecho PRE/POST/BORG de la última sesión
  (o de la fecha que se pase: /prepost 2026-05-10).
- /golespartido: tras un partido, modo voz/texto para describir los
  goles en orden cronológico ('el 1-0 fue de Raúl tras pase de Pani…').
  Gemini extrae cada descripción y la guarda en la columna `descripcion`
  del evento correspondiente en EST_EVENTOS.
- /auditar: audita BORG/PESO/WELLNESS/SESIONES y detecta errores
  (jugador fuera del roster, BORG fuera de rango 0-10, pesos imposibles,
  H2O raros, sesiones duplicadas, fechas vacías). Añade "verbose" para
  ver el detalle: `/auditar verbose`.
- /oliver_sync, /oliver_deep: sync con Oliver Sports.
- /ejercicios_sync: lee hoja _EJERCICIOS y descarga timelines.
- /sesion: apunta una sesión a SESIONES.
- /ejercicios_voz: graba ejercicios del día a _EJERCICIOS.

Si Arkaitz acaba de mandar uno de estos comandos, lo verás como bloque
"[Contexto del bot — acciones que el usuario ha disparado…]" al principio
del mensaje. Ese es el resumen, no se lo vuelvas a preguntar.

📸 SI EL USUARIO MANDA FOTO (con caption opcional):
Antes de tu turno alguien habrá analizado la imagen y te habrá dejado en
el historial los datos extraídos. Lo verás como bloque tipo:

  [IMAGEN ANALIZADA — caption: 'planilla del partido'
   Datos extraídos:
   (lo que el modelo de visión vio)]

Tu tarea: leer los datos extraídos, PRESENTARLOS al usuario de forma
clara, y preguntar si quiere que los guarde antes de tocar el Sheet.
Por ejemplo:
  "📸 De la foto saco esto:
   · Sesión: 11/05/2026 M TEC-TAC 75 min
   · BORG: HERRERO=7, PIRATA=8, …
   ¿Quieres que apunte la sesión y los BORG?"

NO escribas al Sheet directamente sin confirmación del usuario. La
visión a veces falla.

Cuando confirme, usa los scripts `apuntar_*` / `marcar_lesion` como
siempre. Si los datos no son claros, díselo en humano y pídele detalle.

══════════════════════════════════════════════════════════════════════
ESQUEMA COMPLETO DEL SHEET (mayo 2026)
══════════════════════════════════════════════════════════════════════

Para consultas necesitas saber QUÉ hoja contiene CADA tipo de dato.
Para escrituras puntuales (Borg, peso, wellness, lesión) usa los
scripts apuntar_*.py / marcar_lesion.py. Para consultas amplias, lee
directamente la hoja con gspread.

### CARGA / ENTRENO

- **SESIONES** (crudo): FECHA, SEMANA, TURNO, TIPO_SESION, MINUTOS,
  COMPETICION. Calendario del equipo, NO tiene jugador.
- **BORG** (crudo, 1 fila/jugador-sesión): FECHA, TURNO, JUGADOR, BORG.
  BORG puede ser número 0-10 o letra S/A/L/N/D/NC/NJ.
- **_VISTA_CARGA**: FECHA, TURNO, JUGADOR, TIPO_SESION, COMPETICION,
  MINUTOS, BORG, CARGA (=Borg×Minutos), SEMANA, DIA_SEMANA.
- **_VISTA_SEMANAL** (1 fila/jugador-semana): FECHA_LUNES, JUGADOR,
  CARGA_SEMANAL, SESIONES, BORG_MEDIO, ACWR (EWMA agudo/crónico),
  CARGA_AGUDA, CARGA_CRONICA, MONOTONIA, FATIGA, SEMAFORO.
- **_VISTA_SEMAFORO** (foto reciente): JUGADOR, ACWR, MONOTONIA,
  WELLNESS_MEDIO, WELLNESS_BELOW15, PESO_PRE_DESV_KG, ALERTAS_ACTIVAS,
  SEMAFORO_GLOBAL (ROJO/NARANJA/VERDE).
- **_VISTA_RECUENTO** (histórico asistencia): JUGADOR,
  TOTAL_SESIONES_EQUIPO, EST_S/A/L/N/D/NC/NJ, SESIONES_CON_DATOS,
  PCT_PARTICIPACION.

### PESO Y WELLNESS

- **PESO** (crudo): FECHA, TURNO, JUGADOR, PESO_PRE, PESO_POST, H2O_L.
- **_VISTA_PESO**: ídem + DIFERENCIA, PCT_PERDIDA, ALERTA_PESO,
  BASELINE_PRE, DESVIACION_BASELINE.
- **WELLNESS** (crudo): FECHA, JUGADOR, SUENO, FATIGA, MOLESTIAS, ANIMO,
  TOTAL. ⚠ La col se llama `SUENO` (sin tilde).
- **_VISTA_WELLNESS**: ídem + WELLNESS_7D, BASELINE_WELLNESS,
  DESVIACION_BASELINE, SEMAFORO_WELLNESS.

### LESIONES / FISIO

- **LESIONES** (crudo, cabecera en fila 2): JUGADOR, FECHA LESIÓN,
  TIPO LESIÓN, ZONA CORPORAL, LADO, FECHA ALTA, GRAVEDAD, etc.
  Para escribir SIEMPRE usa marcar_lesion.py (es idempotente).
- **FISIO**: FECHA, JUGADOR, ESTADO, TIPO_LESION, ZONA_CORPORAL, LADO,
  DIAS_BAJA_ESTIMADOS, NOTAS.

### PARTIDOS · estadísticas

- **EST_PARTIDOS** (1 fila por jugador × partido, ~600 filas):
  partido_id, tipo, competicion, rival, fecha, dorsal, jugador,
  min_1t, min_2t, min_total, convocado, participa,
  rot_1t_1..8 / rot_2t_1..8 (rotaciones de cada parte),
  pf/pnf, robos, cortes, bdg, bdp, dp (puerta) / dpalo / db / df (fuera),
  par/gol_p/bloq_p/poste_p (portería), goles_a_favor, asistencias.
- **EST_EVENTOS** (1 fila por gol): partido_id, fecha, rival, parte,
  minuto, equipo_marca (INTER/RIVAL), accion (Contraataque, ABP, Banda,
  Córner, 4x4, Penalti, 10m, Portero-jugador, etc.), zona_campo (A1-A11),
  zona_porteria (P1-P9), jugador (goleador), asistencia, cuarteto
  (jugadores de campo en pista separados por |), portero, descripcion.
- **EST_DISPAROS** (1 fila por disparo): igual que EVENTOS pero TODOS
  los disparos (gol y no-gol). Columnas: competicion, rival, fecha,
  parte, minuto, equipo (INTER/RIVAL), jugador, asistencia, zona_campo,
  zona_porteria, accion, resultado (GOL/PARADA/PALO/BLOQUEADO/FUERA).
- **EST_DISPAROS_ZONAS**: pivot de disparos × zona campo × zona portería.
- **EST_TOTALES_PARTIDO**: 1 fila por partido con totales (dt_inter,
  dp_inter, dt_rival, dp_rival, pf_inter, pnf_inter, robos_inter,
  cortes_inter, faltas_inter, faltas_rival, etc.).
- **EST_FALTAS**: partido_id, parte, minuto_mmss, condicion
  (A_FAVOR/EN_CONTRA), jugador, num_falta, genera_10m, descripcion.
- **EST_PENALTIS_10M**: tirador, portero, resultado, parte, minuto,
  partido, tipo (PENALTI/10M).
- **EST_PLANTILLAS**: alineación inicial del partido.
- **_VISTA_EST_JUGADOR**: agregado por jugador en toda la temporada.
- **_VISTA_EST_AVANZADAS**: ratios (xG, eficiencia disparo, gol/min, …).
- **_VISTA_EST_CUARTETOS**: combinaciones de jugadores en pista y su
  rendimiento (minutos juntos, GF/GC en pista, plus_minus).

### SCOUTING DE RIVALES

- **SCOUTING_RIVALES**: hoja maestra (89 cols) por rival y fecha
  observada — plantilla, sistema, fortalezas, debilidades, balón
  parado favor/contra, duelos por zona, ABP, etc.
- **_VISTA_SCOUTING_RIVAL** (129 cols): vista limpia por rival con
  totales agregados.
- **EST_SCOUTING_PEN_10M**: cómo marcan / reciben penaltis y 10m
  cada rival visto. Tirador, portero, club, dirección, forma, zona,
  es_gol, etc.

### OLIVER (GPS)

- **OLIVER** (~5000 filas, MVP 15 cols): session_id, fecha, jugador,
  distancia, hsr, sprints, vel_max, aceleraciones, deceleraciones,
  carga_mecanica.
- **_OLIVER_DEEP** (68 métricas): detalle profundo.
- **_VISTA_OLIVER** (31 cols): cruza Oliver con Borg y CARGA →
  ratio_borg_oliver, eficiencia_sprint, asimetria_acc,
  densidad_metabolica, pct_hsr, acwr_mecanico.

### EJERCICIOS DE ENTRENO

- **_EJERCICIOS** (input manual): id_sesion, fecha, turno,
  nombre_ejercicio, tipo_ejercicio, minuto_inicio, minuto_fin,
  jugadores, notas.
- **_VISTA_EJERCICIOS**: 1 fila/jugador×ejercicio con métricas Oliver
  agregadas sobre el rango del ejercicio.

### ANTROPOMETRÍA (nutricionista)

- **ANTROPOMETRIA**: jugador, fecha_medicion, peso_kg, altura_cm, imc,
  pliegues (tríceps_mm, subescapular_mm, abdominal_mm, supraespinal_mm,
  muslo_mm, pantorrilla_mm), sumatorio_6_pliegues_mm,
  masa_grasa_yuhasz_pct, masa_grasa_faulkner_pct, masa_muscular_kg,
  somatotipo_endomórfico/mesomórfico/ectomórfico.
- Sumatorio 6 pliegues: <30 muy bajo · 30-45 excelente · 45-50 bueno ·
  50-60 aceptable · 60-80 regular · >80 bajo rendimiento.

### TELÉFONOS / FORMS

- **TELEFONOS_JUGADORES**: dorsal, jugador, telefono, usar_whatsapp,
  notas. Usado por /enlaces_wa.
- **_FORM_PRE / _FORM_POST**: respuestas crudas de los Google Forms.

### ROSTER

- **JUGADORES_ROSTER**: dorsal, nombre, posicion (PORTERO/CAMPO),
  equipo (PRIMER/FILIAL), activo (TRUE/FALSE).
  ⚠ Cuartetos "sin portero" deben EXCLUIR HERRERO/GARCIA/OSCAR del
  pool incluso si juegan de portero-jugador.

### GUÍA OPERATIVA RÁPIDA — qué hoja usar por pregunta

- "Goles X esta temporada" → _VISTA_EST_JUGADOR (rápido) o contar
  EST_EVENTOS con jugador=X & equipo_marca=INTER.
- "De qué zona tira más X" → EST_DISPAROS filtrado por jugador,
  agrupar por zona_campo.
- "Cuántos goles encajamos por penalti" → EST_PENALTIS_10M o
  EST_EVENTOS con accion='PENALTI' & equipo_marca=RIVAL.
- "Cómo marca/recibe goles el rival X" → _VISTA_SCOUTING_RIVAL.
- "Cómo nos meten goles" → EST_EVENTOS con equipo_marca=RIVAL,
  agrupar por accion / zona_porteria.
- "Cómo metemos goles" → EST_EVENTOS con equipo_marca=INTER,
  agrupar por accion / zona_campo.
- "Cuartetos top" → _VISTA_EST_CUARTETOS.
- "Quién jugó más minutos el partido X" → EST_PARTIDOS filtrado por
  partido_id, ordenado por min_total.
- "Rotaciones de X en el partido Y" → EST_PARTIDOS, columnas
  rot_1t_1..8 y rot_2t_1..8.
- "Recuento de X" / "asistencia de X esta temporada" → _VISTA_RECUENTO
  (incluye EST_S/A/L/N/D/NC/NJ + RETIRADAS + RETIRADAS_DETALLE).
- "¿Quién entrenó el [fecha]?" → _VISTA_CARGA filtrado por FECHA.
  Lista entrenaron (Borg numérico) + estados (Borg letra) + retirados
  (BORG.INCIDENCIA no vacía).
- "¿Quién está lesionado / se ha retirado?" → LESIONES activas (FECHA
  ALTA vacía) + _VISTA_RECUENTO.RETIRADAS_DETALLE.

### ⚠ CONVENCIÓN DE LECTURA

Para `get_all_records` pasa SIEMPRE
`value_render_option=gspread.utils.ValueRenderOption.unformatted`.
Sin esto, "74,7" (decimal con coma) llega como 747 (rompe los datos).
"""


# Tools (function declarations Gemini)
TOOLS_BOT_DEV = [
    {
        "function_declarations": [
            {
                "name": "python",
                "description": (
                    "Ejecuta código Python con el python del venv del bot. "
                    "Tiene gspread, pandas, openpyxl, google-auth, etc. "
                    "Pasa el código tal cual; SIN escapado de shell."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Código Python."},
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "bash",
                "description": (
                    "Ejecuta un comando shell genérico (ls, cat, head, tail, "
                    "grep, find, git diff, git log, git status). Para ejecutar "
                    "Python usa la tool `python`. NO uses git push/commit aquí "
                    "(eso lo pide Arkaitz directamente)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Comando shell."},
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
                        "path": {"type": "string", "description": "Ruta (relativa o absoluta)."},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": (
                    "Escribe o sobrescribe un archivo. Pide confirmación al "
                    "usuario antes de tocar archivos importantes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Ruta del archivo."},
                        "content": {"type": "string", "description": "Contenido nuevo completo."},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "edit_file",
                "description": (
                    "Sustituye una porción exacta de texto en un archivo "
                    "existente. Más quirúrgico que write_file. Falla si "
                    "old_text no aparece exactamente o aparece varias veces."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string", "description": "Fragmento a buscar (literal, único en el archivo)."},
                        "new_text": {"type": "string", "description": "Fragmento que lo sustituye."},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
        ]
    }
]


def _resolve_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


_PY_PRELUDIO_GSHEET = (
    "# --- Auto-prelude inyectado por el bot (NO lo escribió el modelo) ---\n"
    "import pandas as pd\n"
    "import gspread\n"
    "from google.oauth2.service_account import Credentials\n"
    "_creds = Credentials.from_service_account_file(\n"
    f"    {repr(str(PROJECT_DIR / 'google_credentials.json'))},\n"
    "    scopes=['https://www.googleapis.com/auth/spreadsheets',\n"
    "            'https://www.googleapis.com/auth/drive'])\n"
    "_gc = gspread.authorize(_creds)\n"
    "ss = _gc.open('Arkaitz - Datos Temporada 2526')\n"
    "# Aliases por compatibilidad con código que el modelo ya conozca:\n"
    "creds, gc = _creds, _gc\n"
    "# --- Fin del prelude ---\n"
)

def _exec_tool(name: str, args: Dict[str, Any]) -> str:
    try:
        if name == "python":
            code = args.get("code", "")
            if not code.strip():
                return "ERROR: código vacío."
            # Si el código menciona el Sheet (ss, gspread, creds, gc.open…),
            # inyectamos el prelude para que no falle por imports ni creds
            # olvidados (típico atajo de Gemini Lite).
            # PERO si el código YA TIENE los imports completos, no inyectamos
            # el prelude (sería duplicar 2 llamadas a Sheets/Drive API y a
            # veces falla por throttle).
            needs_sheet = any(
                k in code
                for k in ("ss.", "gspread", "creds", "gc.open", "from google.oauth2")
            )
            has_full_imports = (
                "from google.oauth2" in code
                and "from_service_account_file" in code
                and "gspread.authorize" in code
            )
            if needs_sheet and not has_full_imports:
                code = _PY_PRELUDIO_GSHEET + "\n" + code
            result = subprocess.run(
                [sys.executable], input=code,
                capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=180,
            )
            out = result.stdout or ""
            if result.stderr:
                stderr_clean = "\n".join(
                    ln for ln in result.stderr.splitlines()
                    if "FutureWarning" not in ln and "ev_poll_posix" not in ln
                    and "ABSL" not in ln and "warnings.warn" not in ln
                ).strip()
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
            BLOCK = ["rm -rf /", "rm -rf ~", "git push", "git reset --hard",
                     "git checkout --", "shutdown", "reboot",
                     ":(){:|:&};:", "mkfs", "dd if=", "> /dev/sda"]
            if any(b in cmd for b in BLOCK):
                return f"ERROR: comando bloqueado por seguridad ({cmd[:60]})"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=180,
            )
            out = (result.stdout or "")
            if result.stderr:
                out += "\n[STDERR]\n" + result.stderr
            if result.returncode != 0:
                out += f"\n[exit code: {result.returncode}]"
            if len(out) > 50000:
                out = out[:50000] + f"\n[...truncado, total {len(out)} chars]"
            return out or "(sin output)"
        elif name == "read_file":
            p = _resolve_path(args.get("path", ""))
            try:
                p.relative_to(PROJECT_DIR.resolve())
            except Exception:
                return f"ERROR: ruta fuera del proyecto: {p}"
            if not p.is_file():
                return f"ERROR: no es un archivo: {p}"
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 80000:
                content = content[:80000] + f"\n[...truncado, total {len(content)} chars]"
            return content
        elif name == "write_file":
            p = _resolve_path(args.get("path", ""))
            try:
                p.relative_to(PROJECT_DIR.resolve())
            except Exception:
                return f"ERROR: ruta fuera del proyecto: {p}"
            content = args.get("content", "")
            # Defensa: no permitir escribir credenciales sin querer
            forbidden = ["google_credentials.json", ".env"]
            if p.name in forbidden:
                return f"ERROR: tocar {p.name} solo a través de Arkaitz a mano (seguridad)."
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"✅ Escrito {p} ({len(content)} chars)"
        elif name == "edit_file":
            p = _resolve_path(args.get("path", ""))
            try:
                p.relative_to(PROJECT_DIR.resolve())
            except Exception:
                return f"ERROR: ruta fuera del proyecto: {p}"
            if not p.is_file():
                return f"ERROR: no existe el archivo: {p}"
            old_text = args.get("old_text", "")
            new_text = args.get("new_text", "")
            if not old_text:
                return "ERROR: old_text vacío."
            content = p.read_text(encoding="utf-8")
            count = content.count(old_text)
            if count == 0:
                return "ERROR: no encuentro el fragmento `old_text` en el archivo."
            if count > 1:
                return (f"ERROR: el fragmento aparece {count} veces; "
                        f"añade contexto a `old_text` para que sea único.")
            new_content = content.replace(old_text, new_text, 1)
            p.write_text(new_content, encoding="utf-8")
            return f"✅ Editado {p} (1 reemplazo)."
        else:
            return f"ERROR: herramienta desconocida '{name}'."
    except subprocess.TimeoutExpired:
        return "ERROR: comando excedió el timeout."
    except Exception as e:
        return f"ERROR ejecutando {name}: {type(e).__name__}: {e}"


def _truncate_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(history) <= HISTORY_MAX_TURNS * 2:
        return history
    return history[-HISTORY_MAX_TURNS * 2:]


async def _gemini_call_with_retry(model, history, max_retries: int = 3):
    """Retry con backoff ante errores transitorios de Gemini.
    Reintenta: rate limits per-minute, timeouts, 5xx, errores de red.
    NO reintenta: daily quota, autenticación, InvalidArgument."""
    delays = [2, 5, 10]
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(model.generate_content, history)
        except Exception as e:
            last_err = e
            err_low = str(e).lower()
            non_retryable = (
                "api key" in err_low,
                "authentication" in err_low,
                "permission denied" in err_low,
                "invalid argument" in err_low,
                "perdayperprojectpermodel" in err_low,
            )
            if any(non_retryable):
                raise
            if attempt >= max_retries:
                raise
            wait_s = delays[min(attempt, len(delays) - 1)]
            log.warning("[gemini retry %d/%d] %s: %s. Reintentando en %ds.",
                        attempt + 1, max_retries, type(e).__name__,
                        str(e)[:200], wait_s)
            await asyncio.sleep(wait_s)
    raise last_err


async def _run_gemini(prompt: str, continue_session: bool = True,
                       progress_cb=None) -> Tuple[int, str, str]:
    """Llama a Gemini con tool-use loop. Mantiene historial conversacional.

    `progress_cb`: callable async opcional que se llama UNA vez al detectar
    el primer tool call (señal de respuesta lenta). No se llama en queries
    instantáneas.
    """
    chat_id = ALLOWED_CHAT_ID  # bot dev es mono-usuario; key por chat_id
    if not continue_session:
        _conv_history.pop(chat_id, None)
    history = _conv_history.get(chat_id, [])
    history.append({"role": "user", "parts": [{"text": prompt}]})

    hoy_iso = _dt.date.today().isoformat()
    system_eff = SYSTEM_PROMPT_DEV.replace("__HOY__", hoy_iso)

    # Safety: deshabilitamos filtros (uso interno club, datos deportivos
    # neutros — falsos positivos con apodos "Pirata"+"carga"/"fatiga").
    _safety_off = [
        {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_eff,
        tools=TOOLS_BOT_DEV,
        safety_settings=_safety_off,
    )

    progress_sent = False
    # Wake-up automático cuando Gemini "termina mudo" (bug conocido de Gemini
    # Flash con function calling, también pasa a veces en step 0 sin tool).
    # Subido de 1 a 2 tras ver que "apunta a X lesionado" fallaba pese al
    # primer wake-up (13/5/2026, Arkaitz).
    wake_ups_usados = 0
    WAKE_UPS_MAX = 2

    try:
        async with asyncio.timeout(LLM_TIMEOUT):
            for step in range(GEMINI_MAX_STEPS):
                response = await _gemini_call_with_retry(model, history)
                candidates = getattr(response, "candidates", None) or []
                if not candidates:
                    return -1, "", "Gemini devolvió respuesta vacía (sin candidates)."
                cand = candidates[0]
                content = getattr(cand, "content", None)
                if not content or not getattr(content, "parts", None):
                    # Diagnóstico fino del finish_reason
                    # 1=STOP, 2=MAX_TOKENS, 3=SAFETY, 4=RECITATION, 5=OTHER,
                    # 6=BLOCKLIST, 7=PROHIBITED, 8=SPII, 9=MALFORMED_FUNCTION_CALL,
                    # 10=IMAGE_SAFETY, 12=UNEXPECTED_TOOL_CALL, 13=TOO_MANY_TOOL_CALLS
                    finish_raw = getattr(cand, "finish_reason", None)
                    try:
                        finish_int = int(finish_raw) if finish_raw is not None else -1
                    except (TypeError, ValueError):
                        finish_int = -1

                    # Caso 1: STOP sin contenido → wake-up forzado.
                    # Antes solo en step>0 (tras tool call). Ahora también en
                    # step 0 (Gemini se queda mudo de salida): le pedimos que
                    # use las herramientas o produzca texto.
                    if (finish_int == 1 and wake_ups_usados < WAKE_UPS_MAX):
                        wake_ups_usados += 1
                        en_step_0 = (step == 0)
                        log.warning(
                            "[%s] finish_reason=STOP sin contenido (step=%d). "
                            "Forzando wake-up (%d/%d).",
                            chat_id, step, wake_ups_usados, WAKE_UPS_MAX,
                        )
                        # Mensaje distinto si es step 0 (sin tool todavía) o
                        # tras tool call (con resultado disponible).
                        wake_msg = (
                            "Lee la última petición del usuario y responde "
                            "ahora. Si necesitas escribir al Sheet (marcar "
                            "lesionado, apuntar Borg, etc.), lanza el script "
                            "correspondiente del system prompt. Si solo te "
                            "piden información, contesta directamente. No te "
                            "quedes en blanco: produce algo."
                        ) if en_step_0 else (
                            "Produce ahora una respuesta en español, en "
                            "lenguaje natural, basándote en lo que acabas de "
                            "obtener. Sigue el tono y formato del system "
                            "prompt (frases cortas, números concretos, tono "
                            "de compañero). No uses más herramientas, solo "
                            "responde."
                        )
                        history.append({
                            "role": "user",
                            "parts": [{"text": wake_msg}],
                        })
                        continue

                    # SAFETY / filtros
                    if finish_int in (3, 6, 7, 8, 10):
                        return (-1, "",
                                f"Gemini bloqueó por filtros de contenido "
                                f"(finish_reason={finish_int}). Reformula la "
                                f"petición.")

                    # MAX_TOKENS
                    if finish_int == 2:
                        return (-1, "",
                                "Respuesta cortada por longitud. Pide en bloques "
                                "más pequeños.")

                    # Tools rotos
                    if finish_int in (9, 12, 13):
                        return (-1, "",
                                f"Problema al usar las herramientas "
                                f"(finish_reason={finish_int}). Simplifica la "
                                f"petición.")

                    return (-1, "",
                            f"Gemini terminó sin contenido (finish_reason={finish_int}).")

                parts = list(content.parts)
                fcalls = []
                for p in parts:
                    fc = getattr(p, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        fcalls.append(fc)

                if fcalls:
                    # Notificar al usuario en el primer tool call
                    if progress_cb is not None and not progress_sent:
                        try:
                            await progress_cb("🔧 Trabajando en ello, dame un momento…")
                            progress_sent = True
                        except Exception:
                            pass
                    history.append({"role": "model", "parts": parts})
                    tool_response_parts = []
                    for fc in fcalls:
                        try:
                            args = dict(fc.args) if fc.args else {}
                        except Exception:
                            args = {}
                        if fc.name == "python":
                            log.info("[%s] >>> PYTHON:\n%s", chat_id, args.get("code", ""))
                        elif fc.name == "bash":
                            log.info("[%s] >>> BASH:\n%s", chat_id, args.get("command", ""))
                        elif fc.name == "write_file":
                            log.info("[%s] >>> WRITE %s (%d chars)", chat_id,
                                     args.get("path", ""), len(args.get("content", "")))
                        elif fc.name == "edit_file":
                            log.info("[%s] >>> EDIT %s", chat_id, args.get("path", ""))
                        else:
                            log.info("[%s] >>> %s args=%s", chat_id, fc.name, str(args)[:200])
                        result = await asyncio.to_thread(_exec_tool, fc.name, args)
                        log.info("[%s] <<< %s (%d chars):\n%s",
                                 chat_id, fc.name, len(result), result[:3000])
                        tool_response_parts.append({
                            "function_response": {
                                "name": fc.name,
                                "response": {"result": result},
                            }
                        })
                    history.append({"role": "user", "parts": tool_response_parts})
                    continue

                text = ""
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        text += t
                history.append({"role": "model", "parts": [{"text": text}]})
                _conv_history[chat_id] = _truncate_history(history)
                return 0, text.strip(), ""

            _conv_history[chat_id] = _truncate_history(history)
            return -1, "", f"Límite de iteraciones alcanzado ({GEMINI_MAX_STEPS})."
    except asyncio.TimeoutError:
        return -1, "", f"Timeout: Gemini tardó más de {LLM_TIMEOUT}s."
    except Exception as e:
        log.exception("Error en _run_gemini: %s", e)
        return -1, "", f"{type(e).__name__}: {e}"


# Compat: por si algo del repo aún llama _run_claude
_run_claude = _run_gemini


# ─── Handlers ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    await update.message.reply_text(
        "👋 Hola! Escríbeme cualquier pregunta o petición sobre el proyecto "
        "Arkaitz y se la paso a Claude Code.\n\n"
        "Por ejemplo:\n"
        "• «¿cómo va la carga de Carlos esta semana?»\n"
        "• «revisa los últimos commits»\n"
        "• «arregla el warning que sale en dashboard/app.py»\n\n"
        "Mantengo el hilo de la conversación: puedes decir «sí», «hazlo», "
        "«detállalo más» y sé de qué hablamos.\n\n"
        "Comandos:\n"
        "• /nuevo → empezar conversación nueva (olvida el contexto anterior)\n"
        "• /id → ver tu chat_id\n\n"
        "Sé claro y específico; Claude tiene acceso total al proyecto."
    )


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Devuelve el chat_id a cualquiera que lo pida (útil al configurar el bot)."""
    await update.message.reply_text(
        f"Tu chat_id es: `{update.effective_chat.id}`\n"
        "Copia ese número en el campo ALLOWED_CHAT_ID del archivo .env.",
        parse_mode="Markdown",
    )


async def cmd_nuevo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Empieza una conversación nueva con Claude (descarta contexto previo)."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    _fresh_chats.add(chat_id)
    # Sesión nueva = no tiene sentido arrastrar acciones locales pendientes
    _acciones_pendientes.pop(chat_id, None)
    # Limpiamos también el historial Gemini de ese chat
    _conv_history.pop(chat_id, None)
    await update.message.reply_text(
        "🆕 Vale, el próximo mensaje empezará una conversación nueva "
        "(sin contexto de lo anterior)."
    )


async def _run_oliver_sync(deep: bool = False) -> Tuple[int, str, str]:
    """Ejecuta el script de sincronización de Oliver en el proyecto."""
    py = sys.executable
    args = [py, str(PROJECT_DIR / "src" / "oliver_sync.py")]
    if deep:
        args.append("--deep")
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=1200)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        return -1, "", "Timeout: oliver_sync tardó más de 20 minutos."
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def cmd_oliver_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sincroniza Oliver Sports (métricas MVP, rápido)."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🏃 Sincronizando Oliver Sports (MVP)…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        rc, out, err = await _run_oliver_sync(deep=False)
    finally:
        stop.set()
        try: await task
        except Exception: pass
    # Después, relanza calcular_vistas.py para que el cruce Oliver+Borg se actualice
    if rc == 0:
        await update.message.reply_text("✓ Oliver sincronizado. Recalculando cruces…")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "calcular_vistas.py"),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out2, err2 = await asyncio.wait_for(proc.communicate(), timeout=600)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            await update.message.reply_text("⚠️ calcular_vistas tardó demasiado.")
            return
        if proc.returncode == 0:
            await update.message.reply_text(
                "✅ Todo al día. Abre el dashboard y mira la pestaña **🏃 Oliver**."
            )
            _registrar_accion_local(
                chat_id,
                "/oliver_sync ejecutado: sincronización MVP de Oliver + recálculo "
                "de cruces (calcular_vistas) terminado correctamente."
            )
        else:
            tail = (err2 or out2 or b"").decode("utf-8", "replace")[-1500:]
            await update.message.reply_text(f"⚠️ Oliver OK pero calcular_vistas falló:\n{tail}")
            _registrar_accion_local(
                chat_id,
                "/oliver_sync ejecutado: sync OK pero el recálculo de vistas falló."
            )
    else:
        detalle = (err or out or "(sin detalles)").strip()
        for chunk in _chunks(f"❌ Error en oliver_sync:\n{detalle}"):
            await update.message.reply_text(chunk)
        _registrar_accion_local(
            chat_id, "/oliver_sync FALLÓ — el sync de Oliver dio error, no se actualizó."
        )


async def _run_script(path: Path, *args, timeout: int = 600) -> Tuple[int, str, str]:
    """Ejecuta un script Python del proyecto con el Python del sistema
    (que tiene gspread instalado globalmente)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(path), *args,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        return -1, "", f"Timeout tras {timeout}s."
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def _enviar_bloques(update: Update, stdout: str):
    """El script separa bloques con '---MSG---'. Cada bloque = 1 mensaje Telegram."""
    bloques = [b.strip() for b in stdout.split("---MSG---") if b.strip()]
    for b in bloques:
        # Limitar 4000 chars por si acaso
        if len(b) > 4000:
            b = b[:3997] + "…"
        try:
            await update.message.reply_text(b, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            # Si falla el Markdown, reintentar como texto plano
            await update.message.reply_text(b, disable_web_page_preview=True)


async def cmd_enlaces(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Devuelve los 2 enlaces genéricos (PRE y POST) del Form.
    Ideal para mandar al grupo de WhatsApp una sola vez."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    rc, out, err = await _run_script(PROJECT_DIR / "src" / "enlaces_genericos.py")
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error generando enlaces (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        update.effective_chat.id,
        "/enlaces ejecutado: enviados al usuario los enlaces PRE+POST genéricos del día (con fecha y turno pre-rellenados). El usuario ya los tiene; NO le preguntes si quiere los enlaces."
    )


async def cmd_enlaces_wa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Devuelve un enlace wa.me por cada jugador con teléfono, listo para
    pulsar y enviar por WhatsApp con el mensaje (PRE+POST) prerredactado.
    Lee teléfonos de la hoja `TELEFONOS_JUGADORES` del Sheet."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        # Permitir args opcionales:
        #   /enlaces_wa                      → hoy, todos los jugadores
        #   /enlaces_wa 2026-05-13           → esa fecha, todos
        #   /enlaces_wa HERRERO              → hoy, solo HERRERO
        #   /enlaces_wa HERRERO 2026-05-13   → esa fecha, solo HERRERO
        args_cli = list(ctx.args) if ctx and ctx.args else []
        rc, out, err = await _run_script(PROJECT_DIR / "src" / "enlaces_wa.py", *args_cli)
    finally:
        stop.set()
        try: await task
        except Exception: pass
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error generando enlaces WhatsApp (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        chat_id,
        "/enlaces_wa ejecutado: enviados al usuario los enlaces wa.me "
        "personalizados por jugador (uno por jugador con teléfono "
        "configurado). El usuario solo tiene que pulsar cada enlace y "
        "darle a Enviar en WhatsApp. NO le preguntes si quiere los enlaces."
    )


async def cmd_enlaces_hoy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """[DEPRECATED] El comando individual por jugador queda descartado.
    Redirige al comando /enlaces (genérico con fecha+turno automático)."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    await update.message.reply_text(
        "ℹ️ /enlaces_hoy ha sido descartado. Usa /enlaces — ahora genera "
        "los enlaces del día con FECHA y TURNO ya pre-rellenados, listos "
        "para mandar al grupo de WhatsApp.")
    chat_id = update.effective_chat.id
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        rc, out, err = await _run_script(PROJECT_DIR / "src" / "enlaces_genericos.py")
    finally:
        stop.set()
        try: await task
        except Exception: pass

    if rc != 0:
        await update.message.reply_text(
            f"❌ Error generando enlaces (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        chat_id,
        "/enlaces_hoy (deprecated, redirigido a /enlaces) ejecutado: enlaces "
        "PRE+POST genéricos del día enviados al usuario. NO le preguntes "
        "si quiere los enlaces."
    )


async def cmd_consolidar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lee _FORM_PRE y _FORM_POST, los integra en BORG/PESO/WELLNESS y
    luego recalcula todas las vistas para que el dashboard se actualice."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔄 Consolidando respuestas de los Forms…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        rc, out, err = await _run_script(PROJECT_DIR / "src" / "consolidar_forms.py", timeout=300)
    finally:
        stop.set()
        try: await task
        except Exception: pass
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error consolidando (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)

    # Después de consolidar, recalcular vistas para que el dashboard refleje los datos
    await update.message.reply_text("🧮 Recalculando vistas para el dashboard…")
    stop2 = asyncio.Event()
    task2 = asyncio.create_task(_keep_typing(chat_id, ctx, stop2))
    try:
        rc2, out2, err2 = await _run_script(PROJECT_DIR / "src" / "calcular_vistas.py", timeout=600)
    finally:
        stop2.set()
        try: await task2
        except Exception: pass
    if rc2 != 0:
        await update.message.reply_text(
            f"⚠️ Consolidación OK pero el recálculo de vistas falló:\n{(err2 or out2)[-1500:]}"
        )
        return

    # Recalcular vistas FISIOS (Lesiones, Tratamientos, Temperatura)
    await update.message.reply_text("🏥 Recalculando vistas de fisios…")
    stop3 = asyncio.Event()
    task3 = asyncio.create_task(_keep_typing(chat_id, ctx, stop3))
    try:
        rc3, out3, err3 = await _run_script(
            PROJECT_DIR / "src" / "calcular_vistas_fisios.py", timeout=300)
    finally:
        stop3.set()
        try: await task3
        except Exception: pass
    if rc3 != 0:
        await update.message.reply_text(
            f"⚠️ Vistas principales OK pero las de fisios fallaron:\n{(err3 or out3)[-1000:]}"
        )
        # No abortamos: el dashboard principal sigue actualizado

    # Sincronizar Sheet de Lanzamientos (cuerpo técnico) → EST_SCOUTING_PEN_10M.
    # Imprime también lista de lanzamientos con info incompleta del portero.
    await update.message.reply_text("🎯 Sincronizando lanzamientos del cuerpo técnico…")
    stop4 = asyncio.Event()
    task4 = asyncio.create_task(_keep_typing(chat_id, ctx, stop4))
    try:
        rc4, out4, err4 = await _run_script(
            PROJECT_DIR / "src" / "sincronizar_lanzamientos.py", timeout=120)
    finally:
        stop4.set()
        try: await task4
        except Exception: pass
    if rc4 != 0:
        await update.message.reply_text(
            f"⚠️ Lanzamientos no se sincronizaron:\n{(err4 or out4)[-800:]}"
        )
    else:
        # Enviamos el bloque de lanzamientos (incluye lista de incompletos si los hay)
        await _enviar_bloques(update, out4)

    await update.message.reply_text(
        "✅ Todo actualizado. Abre el dashboard de Streamlit y verás los nuevos datos."
    )
    _registrar_accion_local(
        chat_id,
        "/consolidar ejecutado: respuestas de Forms volcadas a BORG/PESO/WELLNESS, "
        "vistas principales + fisios recalculadas, y Sheet de Lanzamientos del "
        "cuerpo técnico sincronizado con EST_SCOUTING_PEN_10M. Si había "
        "lanzamientos con info incompleta del portero, ya se ha avisado al usuario. "
        "El dashboard YA está actualizado."
    )


async def cmd_ejercicios_voz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Activa modo captura: el siguiente audio se procesa como descripción
    de los ejercicios del entreno y se vuelca a _EJERCICIOS + se sincroniza
    con Oliver. Caduca a los 15 min."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    _modo_ejercicios_voz[chat_id] = _dt.datetime.now().timestamp()
    await update.message.reply_text(
        "🎤 *Modo ejercicios activado.*\n\n"
        "Mándame ahora un audio (o un texto) describiendo los ejercicios "
        "del entreno (qué hicisteis, en qué orden y duración aproximada). "
        "En cuanto lo reciba lo transcribo, lo estructuro, lo meto en "
        "`_EJERCICIOS` y lanzo el cruce con Oliver automáticamente.\n\n"
        "_Si el GPS se encendió después de algún ejercicio (movilidad, etc.), "
        "menciónalo en el audio y lo tendré en cuenta._\n\n"
        "Tienes 15 min para mandar el audio.",
        parse_mode="Markdown",
    )


async def _procesar_audio_ejercicios(transcripcion: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Procesa la descripción del entreno.

    ⚡ ASYNC: responde al usuario **inmediatamente** con un acuse de recibo
    y lanza el subprocess de parse_ejercicios_voz.py EN BACKGROUND. Cuando
    termine (puede ser 30s o 2 min), envía un nuevo mensaje al chat con
    el resultado. El usuario no se queda mirando el "escribiendo…" eterno.
    """
    chat_id = update.effective_chat.id

    # Conteo rápido de ejercicios para el mensaje inmediato (solo si es texto
    # estructurado; si es audio narrativo, no hay forma fiable de contarlos).
    n_pistas = sum(
        1 for ln in transcripcion.splitlines()
        if re.match(r"^\s*\d+\s*[\.\)\-]", ln)
    )
    if n_pistas >= 2:
        msg_acuse = (
            f"✅ Recibido. Procesando *{n_pistas}* ejercicios en segundo plano.\n"
            "_Te aviso aquí mismo cuando termine (~30s-2min según Oliver)._"
        )
    else:
        msg_acuse = (
            "✅ Recibido. Procesando los ejercicios en segundo plano.\n"
            "_Te aviso aquí mismo cuando termine (~30s-2min según Oliver)._"
        )
    await update.message.reply_text(msg_acuse, parse_mode="Markdown")

    # Disparar el trabajo pesado y soltarlo. No await aquí: la handler
    # vuelve enseguida y el bot queda libre para responder a otros mensajes.
    asyncio.create_task(
        _ejercicios_worker(chat_id, transcripcion, update, ctx)
    )


async def _ejercicios_worker(
    chat_id: int,
    transcripcion: str,
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
):
    """Tarea de fondo que hace el trabajo pesado y envía el resultado."""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "parse_ejercicios_voz.py"),
            cwd=str(PROJECT_DIR),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(input=transcripcion.encode("utf-8")),
                timeout=900,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            try:
                await ctx.bot.send_message(chat_id, "⚠️ Timeout (>15 min) procesando ejercicios.")
            except Exception:
                pass
            return

        if proc.returncode != 0:
            try:
                await ctx.bot.send_message(
                    chat_id,
                    f"❌ Error procesando ejercicios (código {proc.returncode}):\n"
                    f"{(err or out).decode('utf-8', 'replace')[-1500:]}",
                )
            except Exception:
                pass
            return

        salida_decoded = out.decode("utf-8", "replace")
        # Reutilizamos _enviar_bloques, que parte por MSG_SEP y envía
        # mensajes separados al chat. Le pasamos update para que use
        # update.message.reply_text — sigue funcionando aunque vengamos
        # de una tarea de fondo.
        try:
            await _enviar_bloques(update, salida_decoded)
        except Exception:
            # Fallback robusto: enviar todo de una si _enviar_bloques falla
            try:
                await ctx.bot.send_message(chat_id, salida_decoded[-3500:])
            except Exception:
                pass

        # ── Inyectar en el historial conversacional de Gemini ──
        # Así, si después Arkaitz dice "revísalo" o "corrige el GPS de la
        # movilidad", Alfred tiene el contexto de qué se acaba de procesar.
        try:
            history = _conv_history.get(chat_id, [])
            salida_limpia = salida_decoded.replace("---MSG---", "").strip()
            history.append({
                "role": "user",
                "parts": [{"text": f"[modo /ejercicios] {transcripcion}"}],
            })
            history.append({
                "role": "model",
                "parts": [{"text": (
                    "He procesado los ejercicios del entreno. Resultado:\n\n"
                    + salida_limpia[:3000]
                )}],
            })
            _conv_history[chat_id] = _truncate_history(history)
        except Exception as _e:
            log.warning("No pude inyectar /ejercicios en historial: %s", _e)
    except Exception as e:
        log.exception("Worker /ejercicios falló: %s", e)
        try:
            await ctx.bot.send_message(chat_id, f"❌ Error inesperado en /ejercicios: {e}")
        except Exception:
            pass


async def cmd_golespartido(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Activa modo /golespartido: el siguiente audio o texto se procesa
    como descripción CRONOLÓGICA de los goles del último partido y se
    vuelca a la columna descripcion de EST_EVENTOS.

    También acepta texto directo:
      /golespartido el 1-0 fue de Raul tras pase de Pani...
    """
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    args_text = " ".join(ctx.args).strip() if ctx.args else ""
    if args_text:
        await _procesar_audio_goles(args_text, update, ctx)
        return
    _modo_goles_voz[chat_id] = _dt.datetime.now().timestamp()
    await update.message.reply_text(
        "⚽ *Modo descripción de goles activado.*\n\n"
        "Mándame ahora un audio (o texto) describiendo los goles del "
        "último partido EN ORDEN CRONOLÓGICO (el 1-0, luego el 1-1, "
        "el 2-1…). Yo extraigo cada descripción y la guardo en la "
        "columna `descripcion` del evento correspondiente.\n\n"
        "_Ejemplo: «El 1-0 fue de Raúl tras pase de Pani desde la "
        "banda derecha. El 1-1 el rival tras una mala salida nuestra. "
        "El 2-1 lo metió Javi de cabeza en córner.»_\n\n"
        "Tienes 15 min para mandar el audio o el texto.",
        parse_mode="Markdown",
    )


async def _procesar_audio_goles(transcripcion: str, update: Update,
                                  ctx: ContextTypes.DEFAULT_TYPE):
    """Llama al script parse_goles_voz.py con la transcripción."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "⚽ Estructurando los goles con Gemini…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "parse_goles_voz.py"),
            cwd=str(PROJECT_DIR),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(input=transcripcion.encode("utf-8")),
                timeout=300,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            await update.message.reply_text("⚠️ Timeout (>5 min).")
            return
    finally:
        stop.set()
        try:
            await task
        except Exception:
            pass
    out_txt = out.decode("utf-8", errors="replace")
    err_txt = err.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        await update.message.reply_text(
            f"❌ Error al procesar goles (código {proc.returncode}).\n\n"
            f"{(err_txt or out_txt)[:1500]}"
        )
        return
    await _enviar_bloques(update, out_txt)
    _registrar_accion_local(
        chat_id,
        "/golespartido ejecutado: descripciones cronológicas de los goles "
        "guardadas en EST_EVENTOS columna descripcion. NO le preguntes al "
        "usuario si lo quiere apuntar, ya está hecho."
    )
    # Inyectar al historial para que recuerde lo procesado.
    try:
        history = _conv_history.get(chat_id, [])
        salida_limpia = out_txt.replace("---MSG---", "").strip()
        history.append({
            "role": "user",
            "parts": [{"text": f"[modo /golespartido] {transcripcion}"}],
        })
        history.append({
            "role": "model",
            "parts": [{"text": (
                "He procesado los goles. Resumen:\n\n" + salida_limpia[:2500]
            )}],
        })
        _conv_history[chat_id] = _truncate_history(history)
    except Exception as _e:
        log.warning("No pude inyectar /goles en historial: %s", _e)


async def cmd_sesion_voz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Activa modo /sesion: el siguiente audio se procesa como descripción
    de una sesión de entrenamiento y se vuelca a la hoja SESIONES.
    También acepta texto directo: /sesion FÍSICO 75 minutos por la mañana"""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    # Si hay argumentos, procesar directamente como texto
    args_text = " ".join(ctx.args).strip() if ctx.args else ""
    if args_text:
        await _procesar_audio_sesion(args_text, update, ctx)
        return
    # Si no, activar modo captura
    _modo_sesion_voz[chat_id] = _dt.datetime.now().timestamp()
    await update.message.reply_text(
        "🎤 *Modo sesión activado.*\n\n"
        "Mándame ahora un audio (o un texto) describiendo la sesión "
        "de entrenamiento de hoy. Yo me encargo de:\n"
        "  • detectar el tipo (FÍSICO, TEC-TAC, GYM, MATINAL, PARTIDO…)\n"
        "  • el turno (M/T/P)\n"
        "  • la duración total\n"
        "  • un resumen breve con los bloques\n\n"
        "Y lo apunto en la hoja SESIONES.\n\n"
        "_Ejemplo: «matinal de 35 minutos: 8 min activación mental, 7 min "
        "calentamiento, 8 min rondeo 3v1, 4 min banda, 4 min córner, 3 "
        "min YO-YO»_\n\n"
        "Tienes 15 min para mandar el audio.",
        parse_mode="Markdown",
    )


async def _procesar_audio_sesion(transcripcion: str, update: Update,
                                   ctx: ContextTypes.DEFAULT_TYPE):
    """Llama al script parse_sesion_voz.py con la transcripción."""
    chat_id = update.effective_chat.id
    await update.message.reply_text("🧠 Estructurando la sesión con Claude…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "parse_sesion_voz.py"),
            cwd=str(PROJECT_DIR),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(input=transcripcion.encode("utf-8")),
                timeout=300,
            )
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            await update.message.reply_text("⚠️ Timeout (>5 min).")
            return
    finally:
        stop.set()
        try: await task
        except Exception: pass
    if proc.returncode != 0:
        # Combinamos stdout + stderr filtrando warnings ruidosos para que
        # el mensaje real del script (que puede ir por stdout tras MSG_SEP)
        # NO quede oculto por el FutureWarning de google.generativeai.
        salida_out = out.decode("utf-8", "replace")
        salida_err = err.decode("utf-8", "replace")
        err_lines = [
            ln for ln in salida_err.splitlines()
            if "FutureWarning" not in ln
            and "warnings.warn" not in ln
            and "All support for the" not in ln
            and "google.generativeai" not in ln
            and "google.genai" not in ln
            and "deprecated-generative-ai" not in ln
            and "google-gemini" not in ln
            and "NotOpenSSLWarning" not in ln
            and "urllib3" not in ln
        ]
        err_clean = "\n".join(err_lines).strip()
        # Si el script escribió un mensaje user-friendly tras MSG_SEP, ése
        # prevalece sobre stderr.
        if "---MSG---" in salida_out:
            msg_user = salida_out.split("---MSG---", 1)[1].strip()
        else:
            msg_user = (err_clean or salida_out.strip())[-1500:]
        await update.message.reply_text(
            f"❌ Error procesando sesión (código {proc.returncode}):\n{msg_user}"
        )
        return
    # El script imprime el mensaje al usuario tras "---MSG---"
    salida = out.decode("utf-8", "replace")
    if "---MSG---" in salida:
        msg = salida.split("---MSG---", 1)[1].strip()
    else:
        msg = salida.strip()
    # Botón inline opcional: mandar enlaces genéricos del día (fecha+turno
    # auto). El antiguo /enlaces_hoy (individual por jugador) está
    # descartado por petición del usuario.
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Mandar enlaces de hoy",
                              callback_data="run_enlaces"),
    ]])
    await update.message.reply_text(msg, parse_mode="Markdown",
                                     reply_markup=kb)
    _registrar_accion_local(
        chat_id,
        f"/sesion ejecutado: nueva sesión de entreno volcada a la hoja SESIONES. "
        f"Mensaje resumen mandado al usuario: {msg[:200].replace(chr(10), ' ')}"
    )

    # Inyectar al historial conversacional para que Alfred pueda
    # razonar sobre lo procesado si el usuario dice "revísalo".
    try:
        history = _conv_history.get(chat_id, [])
        history.append({
            "role": "user",
            "parts": [{"text": f"[modo /sesion] {transcripcion}"}],
        })
        history.append({
            "role": "model",
            "parts": [{"text": (
                "He procesado la sesión. Resumen:\n\n" + msg[:2000]
            )}],
        })
        _conv_history[chat_id] = _truncate_history(history)
    except Exception as _e:
        log.warning("No pude inyectar /sesion en historial: %s", _e)


async def on_callback_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja botones inline."""
    q = update.callback_query
    await q.answer()
    if not _authorized(update):
        await q.edit_message_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    if q.data == "run_enlaces":
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await ctx.bot.send_message(chat_id, "⏳ Generando enlaces de hoy…")
        rc, out, err = await _run_script(
            PROJECT_DIR / "src" / "enlaces_genericos.py")
        if rc != 0:
            await ctx.bot.send_message(
                chat_id,
                f"❌ Error generando enlaces (código {rc}):\n{(err or out)[:1500]}"
            )
            return
        # enlaces_genericos.py imprime bloques separados por ---MSG---
        # Reintentar sin Markdown si Telegram rechaza el bloque (URLs con
        # `_` o `-` pueden romper el parseo Markdown legacy).
        salida = out
        bloques = [b.strip() for b in salida.split("---MSG---") if b.strip()]
        for b in bloques:
            if len(b) > 4000:
                b = b[:3997] + "…"
            try:
                await ctx.bot.send_message(chat_id, b, parse_mode="Markdown",
                                             disable_web_page_preview=True)
            except Exception:
                await ctx.bot.send_message(chat_id, b,
                                             disable_web_page_preview=True)
        _registrar_accion_local(
            chat_id,
            "[botón inline tras /sesion] enlaces PRE+POST genéricos del día "
            "enviados al usuario. NO le preguntes si quiere los enlaces."
        )


async def cmd_auditar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ejecuta src/auditar_sheet.py y devuelve el resumen de incidencias
    detectadas en BORG/PESO/WELLNESS/SESIONES."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    args = ctx.args if hasattr(ctx, "args") else []
    # /auditar verbose → detalle. Default: agrupado.
    script_args = ["--verbose"] if any(a.lower() == "verbose" for a in args) else []
    rc, out, err = await _run_script(
        PROJECT_DIR / "src" / "auditar_sheet.py",
        *script_args,
    )
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error en auditoría (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        update.effective_chat.id,
        "/auditar ejecutado: enviada al usuario la auditoría de hojas crudas. "
        "NO le preguntes si quiere las incidencias, ya las tiene."
    )


async def cmd_prepost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Devuelve el estado PRE/POST/BORG de la última sesión. Si hubo doble
    (M+T) el mismo día, muestra ambos. Si pasan una fecha como argumento
    (ej. /prepost 2026-05-10), procesa esa."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    # Argumento opcional: fecha YYYY-MM-DD
    args = ctx.args if hasattr(ctx, "args") else []
    fecha_arg = args[0] if args else None
    script_args = [str(fecha_arg)] if fecha_arg else []
    rc, out, err = await _run_script(
        PROJECT_DIR / "src" / "prepost_estado.py",
        *script_args,
    )
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error generando estado PRE/POST (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        update.effective_chat.id,
        "/prepost ejecutado: enviado al usuario el estado de PRE/POST/BORG de la última sesión. NO le preguntes si lo quiere; ya lo tiene."
    )


async def cmd_retirado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Apunta que un jugador se retiró a mitad de sesión por lesión.

    Uso: /retirado JUGADOR FECHA MINUTO MOTIVO [TURNO]

    Ejemplos:
      /retirado PANI 2026-05-14 25 "gemelo derecho"
      /retirado HERRERO 2026-05-14 40 "hombro" T
      /retirado RAYA 2026-05-14 15 "molestia aductor" --borg 7

    Si el bot recibe el mensaje por voz/texto natural ("Pirata se retiró
    hoy en el minuto 25 por molestia en el gemelo"), Alfred lo interpreta
    via Gemini y llama a este comando por debajo."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    args = ctx.args if hasattr(ctx, "args") else []
    if len(args) < 4:
        await update.message.reply_text(
            "Uso: `/retirado JUGADOR FECHA MINUTO MOTIVO [TURNO]`\n"
            "Ej:  `/retirado PANI 2026-05-14 25 \"gemelo derecho\"`",
            parse_mode="Markdown",
        )
        return
    # Reordenar: el motivo puede contener espacios → lo "junto" hasta el último arg
    # si éste parece TURNO (M/T).
    posible_turno = args[-1].upper() if len(args) > 4 and args[-1].upper() in ("M", "T") else None
    if posible_turno:
        motivo = " ".join(args[3:-1])
        script_args = [args[0], args[1], args[2], motivo, posible_turno]
    else:
        motivo = " ".join(args[3:])
        script_args = [args[0], args[1], args[2], motivo]
    rc, out, err = await _run_script(
        PROJECT_DIR / "src" / "marcar_retirado.py",
        *script_args,
    )
    if rc != 0:
        await update.message.reply_text(
            f"❌ No pude apuntar la retirada (código {rc}):\n{(err or out)[:1500]}"
        )
        return
    await _enviar_bloques(update, out)
    _registrar_accion_local(
        update.effective_chat.id,
        f"/retirado ejecutado: marcado {script_args[0]} como retirado en {script_args[1]} "
        f"min {script_args[2]} por '{motivo}'. INCIDENCIA escrita en BORG y "
        f"entrada añadida a LESIONES. NO le preguntes nada más, ya está hecho."
    )


async def cmd_ejercicios_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Procesa la hoja _EJERCICIOS: baja timelines de Oliver, agrega métricas
    por rango de minutos y escribe _VISTA_EJERCICIOS."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "🎯 Procesando ejercicios…\n"
        "Esto puede tardar un par de minutos si hay muchas sesiones (baja los "
        "timelines de Oliver por jugador)."
    )
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        rc, out, err = await _run_script(
            PROJECT_DIR / "src" / "oliver_ejercicios.py", timeout=1500
        )
    finally:
        stop.set()
        try: await task
        except Exception: pass
    if rc != 0:
        await update.message.reply_text(
            f"❌ Error (código {rc}):\n{(err or out)[-1500:]}"
        )
        return
    # Resumen de lo que devolvió el script
    lineas = out.strip().split("\n")
    resumen = "\n".join(lineas[-15:])
    await update.message.reply_text(
        f"✅ Ejercicios procesados.\n\n```\n{resumen}\n```",
        parse_mode="Markdown",
    )
    _registrar_accion_local(
        chat_id,
        "/ejercicios_sync ejecutado: timelines de Oliver descargados y agregados "
        "por bloques. _VISTA_EJERCICIOS regenerada."
    )


async def cmd_oliver_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recibe un token nuevo por Telegram y lo escribe al .env.
    El usuario pega las 3 líneas (OLIVER_TOKEN=..., OLIVER_REFRESH_TOKEN=..., OLIVER_USER_ID=...)
    directamente desde el snippet del navegador."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    texto = (update.message.text or "").replace("/oliver_token", "", 1).strip()
    if not texto:
        await update.message.reply_text(
            "📋 Cómo usarlo:\n"
            "1. En Safari → platform.oliversports.ai → consola (⌥⌘C)\n"
            "2. Ejecuta el snippet de siempre para sacar las 3 líneas.\n"
            "3. Cópialas TODAS y mándame:\n"
            "`/oliver_token`\n"
            "seguido de las 3 líneas (copia+pega tal cual).",
            parse_mode="Markdown",
        )
        return

    # Parsear líneas "CLAVE=VALOR"
    nuevos = {}
    for ln in texto.splitlines():
        ln = ln.strip()
        # Quitar el prefijo "[Log] " que mete Safari al copiar de la consola
        if ln.startswith("[Log]"):
            ln = ln[5:].strip()
        if "=" in ln:
            k, v = ln.split("=", 1)
            k = k.strip(); v = v.strip()
            if k in ("OLIVER_TOKEN", "OLIVER_REFRESH_TOKEN", "OLIVER_USER_ID"):
                nuevos[k] = v

    if "OLIVER_TOKEN" not in nuevos or "OLIVER_REFRESH_TOKEN" not in nuevos:
        await update.message.reply_text(
            "⚠️ No encuentro OLIVER_TOKEN y OLIVER_REFRESH_TOKEN en tu mensaje.\n"
            "Copia LAS TRES LÍNEAS del snippet (tal cual salen en la consola) y mándalas."
        )
        return

    env_path = PROJECT_DIR / ".env"
    try:
        if env_path.exists():
            lineas = env_path.read_text(encoding="utf-8").splitlines()
        else:
            lineas = []
        escritas = set()
        out = []
        for ln in lineas:
            matched = False
            for k in nuevos:
                if ln.startswith(k + "="):
                    out.append(f"{k}={nuevos[k]}")
                    escritas.add(k); matched = True; break
            if not matched:
                out.append(ln)
        for k, v in nuevos.items():
            if k not in escritas:
                out.append(f"{k}={v}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        await update.message.reply_text(
            f"✅ Token actualizado en .env ({len(nuevos)} claves).\n"
            "Ya puedes lanzar /oliver_sync."
        )
        _registrar_accion_local(
            update.effective_chat.id,
            "/oliver_token ejecutado: claves OLIVER_* actualizadas en .env. "
            "El próximo /oliver_sync usará el token nuevo."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error guardando .env: {e}")


async def cmd_oliver_deep(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sincronización profunda quincenal (las 68 métricas)."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    await update.message.reply_text("🔬 Sincronización profunda de Oliver (68 métricas)…")
    chat_id = update.effective_chat.id
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        rc, out, err = await _run_oliver_sync(deep=True)
    finally:
        stop.set()
        try: await task
        except Exception: pass
    if rc == 0:
        # Marcar recordatorio como hecho hoy
        try:
            (LOGS_DIR.parent / ".oliver_deep_ultimo").write_text(_dt.date.today().isoformat())
        except Exception: pass
        await update.message.reply_text(
            "✅ Análisis profundo al día. Reviso las 68 métricas en hoja `_OLIVER_DEEP`. "
            "Si quieres que te resalte cosas raras, dime '*repásame el último deep*'."
        )
        _registrar_accion_local(
            chat_id,
            "/oliver_deep ejecutado: sync profundo de Oliver (68 métricas) terminado, "
            "hoja _OLIVER_DEEP actualizada y .oliver_deep_ultimo marcado."
        )
    else:
        detalle = (err or out or "(sin detalles)").strip()
        for chunk in _chunks(f"❌ Error:\n{detalle}"):
            await update.message.reply_text(chunk)


# ─── Recordatorio quincenal Oliver deep ──────────────────────────────────────
RECORDATORIO_PATH = None  # se define tras LOGS_DIR
RECORDATORIO_DIAS = 14


async def _check_recordatorio_deep(ctx: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta cada 24h. Si llevan >14 días sin deep, avisa al usuario."""
    try:
        path = PROJECT_DIR / ".oliver_deep_ultimo"
        ultima_str = path.read_text().strip() if path.exists() else None
        hoy = _dt.date.today()
        if ultima_str:
            try:
                ultima = _dt.date.fromisoformat(ultima_str)
            except ValueError:
                ultima = hoy - _dt.timedelta(days=RECORDATORIO_DIAS + 1)
        else:
            # Primera vez: no recordar hasta pasados 14 días desde ahora
            path.write_text((hoy - _dt.timedelta(days=0)).isoformat())
            return
        dias = (hoy - ultima).days
        if dias >= RECORDATORIO_DIAS:
            await ctx.bot.send_message(
                ALLOWED_CHAT_ID,
                f"📊 *Recordatorio quincenal — Oliver deep*\n\n"
                f"Han pasado {dias} días desde tu último análisis profundo "
                f"de las 68 métricas de Oliver.\n\n"
                f"Cuando puedas, lanza `/oliver_deep` y yo actualizo la hoja "
                f"`_OLIVER_DEEP` con el detalle completo para que revises "
                f"si se nos escapa algo.",
                parse_mode="Markdown",
            )
    except Exception as e:
        log.warning("Error en check de recordatorio: %s", e)


# ─── Keep-alive de Streamlit Cloud ──────────────────────────────────────────
# Streamlit Community Cloud (plan gratuito) duerme las apps tras varios días
# sin tráfico. Este job hace un GET silencioso a la URL del dashboard cada
# 12 horas para mantenerla "calentita" y que el cuerpo técnico no se
# encuentre el botón "wake up" al entrar. CAVEAT: a veces Streamlit
# requiere clic humano real para despertar; si pese a este ping observas
# que sigue durmiéndose, hay que volver al plan A (avisar al equipo).
STREAMLIT_URL = "https://arkaitz-2526-xj9bbsjmsdq84zzpaxudt6.streamlit.app/"

async def _streamlit_keepalive(ctx: ContextTypes.DEFAULT_TYPE):
    """Cada 12h, ping silencioso al dashboard de Streamlit. NO avisa a nadie:
    si falla, queda solo en el log; si va bien, también."""
    try:
        import urllib.request as _ur
        req = _ur.Request(STREAMLIT_URL, headers={
            "User-Agent": "Alfred-keepalive/1.0 (Movistar Inter FS)",
        })
        # 30s de timeout: Streamlit a veces tarda al despertar.
        with _ur.urlopen(req, timeout=30) as resp:
            code = resp.status
            log.info("Streamlit keepalive OK (HTTP %s)", code)
    except Exception as e:
        # No molestamos al user: solo log. Si falla 1 ping no pasa nada.
        log.warning("Streamlit keepalive falló: %s", e)


# ─── Recordatorio semanal: revisar catálogo de ejercicios ───────────────────
async def _check_auditoria_semanal(ctx: ContextTypes.DEFAULT_TYPE):
    """Lunes a las 8:05 (Madrid). Lanza src/auditar_sheet.py y, si hay
    incidencias, las envía a Arkaitz. Si todo OK, no envía nada para no
    saturar."""
    try:
        rc, out, err = await _run_script(
            PROJECT_DIR / "src" / "auditar_sheet.py",
            "--verbose",
        )
        if rc != 0:
            await ctx.bot.send_message(
                ALLOWED_CHAT_ID,
                f"⚠️ Auditoría semanal falló (código {rc}):\n{(err or out)[:800]}"
            )
            return
        # Si todo OK, no enviar nada. Solo enviar si hay incidencias.
        if "✅ *Auditoría del Sheet OK*" in out:
            log.info("Auditoría semanal: OK, no se envía aviso.")
            return
        # Hay incidencias → enviar
        cabecera = "🔍 *Auditoría semanal (lunes 8h)*\n\n"
        msg = cabecera + out.split("---MSG---", 1)[-1].strip()
        for chunk in _chunks(msg):
            try:
                await ctx.bot.send_message(
                    ALLOWED_CHAT_ID, chunk,
                    parse_mode="Markdown",
                )
            except Exception:
                # Fallback texto plano si Markdown se rompe
                await ctx.bot.send_message(ALLOWED_CHAT_ID, chunk)
    except Exception as e:
        log.warning("Error en auditoría semanal: %s", e)


async def _check_ejercicios_lunes(ctx: ContextTypes.DEFAULT_TYPE):
    """Cada lunes a las 8:00 (Madrid). Lee `_EJERCICIOS` y avisa al usuario
    de cuántos ejercicios distintos se han registrado la semana pasada,
    invitándole a pasar por la pestaña 📚 Catálogo del dashboard para
    revisar si hay nombres parecidos que fusionar.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_path = PROJECT_DIR / "google_credentials.json"
        if not creds_path.exists():
            return
        creds = Credentials.from_service_account_file(
            str(creds_path),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        ss = gspread.authorize(creds).open("Arkaitz - Datos Temporada 2526")
        ws = ss.worksheet("_EJERCICIOS")
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return
        header = rows[0]
        try:
            i_fecha = header.index("fecha")
            i_nombre = header.index("nombre_ejercicio")
        except ValueError:
            return

        hoy = _dt.date.today()
        hace_7 = hoy - _dt.timedelta(days=7)
        nuevos = set()
        total_filas_semana = 0
        for r in rows[1:]:
            if len(r) <= max(i_fecha, i_nombre):
                continue
            fecha_txt = (r[i_fecha] or "").strip()
            nombre = (r[i_nombre] or "").strip()
            if not fecha_txt or not nombre or nombre.startswith("#"):
                continue
            try:
                f = _dt.date.fromisoformat(fecha_txt[:10])
            except ValueError:
                continue
            if hace_7 <= f <= hoy:
                nuevos.add(nombre)
                total_filas_semana += 1

        if not nuevos:
            return  # nada que revisar esta semana

        listado = "\n".join(f"• {n}" for n in sorted(nuevos)[:20])
        suf = ("\n…" if len(nuevos) > 20 else "")
        await ctx.bot.send_message(
            ALLOWED_CHAT_ID,
            f"📋 *Revisión semanal del catálogo*\n\n"
            f"La semana pasada se han registrado {total_filas_semana} "
            f"ejercicio(s) en {len(nuevos)} nombre(s) distinto(s):\n\n"
            f"{listado}{suf}\n\n"
            f"Pásate por la pestaña *📚 Catálogo* del dashboard "
            f"(sección 🛠 Limpieza, sólo admin) por si hay nombres "
            f"parecidos que conviene fusionar.",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.warning("Error en recordatorio semanal de ejercicios: %s", e)


# ─── Recordatorios con fecha específica ──────────────────────────────────────
# Archivo JSON con lista de {"fecha": "YYYY-MM-DD", "mensaje": "...", "hecho": bool}
# Se revisa cada 24h; los que lleguen a su fecha y no estén hechos se envían.
RECORDATORIOS_FILE = PROJECT_DIR / ".recordatorios.json"


def _leer_recordatorios() -> list:
    try:
        if RECORDATORIOS_FILE.exists():
            import json as _json
            return _json.loads(RECORDATORIOS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("No pude leer recordatorios.json: %s", e)
    return []


def _guardar_recordatorios(lista: list) -> None:
    try:
        import json as _json
        RECORDATORIOS_FILE.write_text(
            _json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("No pude escribir recordatorios.json: %s", e)


async def _check_recordatorios_fecha(ctx: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta cada 24h. Envía los recordatorios cuya fecha ya haya llegado."""
    try:
        recs = _leer_recordatorios()
        if not recs:
            return
        hoy = _dt.date.today()
        cambios = False
        for r in recs:
            if r.get("hecho"):
                continue
            try:
                fecha = _dt.date.fromisoformat(r.get("fecha", ""))
            except ValueError:
                continue
            if hoy >= fecha:
                mensaje = r.get("mensaje", "").strip() or "(recordatorio vacío)"
                try:
                    await ctx.bot.send_message(
                        ALLOWED_CHAT_ID,
                        f"⏰ *Recordatorio programado*\n\n{mensaje}",
                        parse_mode="Markdown",
                    )
                    r["hecho"] = True
                    r["enviado_en"] = hoy.isoformat()
                    cambios = True
                except Exception as e:
                    log.warning("Fallo enviando recordatorio: %s", e)
        if cambios:
            _guardar_recordatorios(recs)
    except Exception as e:
        log.warning("Error en check de recordatorios con fecha: %s", e)


def _detectar_intent_estado(prompt: str):
    """Idem a bot_datos: detecta 'estado/carga/qué tal X' y devuelve
    (canónico, N_sesiones) o None. Ver _detectar_intent_estado en bot_datos.py."""
    if not prompt:
        return None
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from aliases_jugadores import ROSTER_CANONICO, ALIASES_JUGADOR  # type: ignore
    except Exception:
        return None
    import re as _re
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
    candidatos: Dict[str, str] = {}
    for canon in ROSTER_CANONICO:
        candidatos[canon.lower()] = canon
    for ali, canon in ALIASES_JUGADOR.items():
        ali_low = ali.lower().replace(".", "").replace(" ", "")
        candidatos[ali_low] = canon
        for w in ali.lower().split():
            w_clean = w.replace(".", "")
            if len(w_clean) >= 4:
                candidatos.setdefault(w_clean, canon)
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


def _detectar_intent_carga_ultima(prompt: str):
    """Ídem que bot_datos: matchea 'carga jugador por jugador', 'borg del entreno',
    'qué tal la sesión de ayer', etc. Devuelve fecha YYYY-MM-DD o '' (última)."""
    if not prompt:
        return None
    p = prompt.lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        p = p.replace(a, b)
    sesion_triggers = (
        "ultima sesion", "ultimo entreno", "ultimo entrenamiento",
        "del entreno de hoy", "sesion de hoy", "entreno de hoy",
        "que tal el entreno", "que tal la sesion",
        "que tal el ultimo entreno", "que tal la ultima sesion",
        "como ha ido el entreno", "como ha ido la sesion",
        "entreno de ayer", "sesion de ayer", "entreno ayer",
    )
    carga_triggers = (
        "carga jugador", "carga por jugador", "carga del equipo",
        "carga de la sesion", "carga del entreno", "borg de hoy",
        "borg de la sesion", "borg del entreno", "borg jugador",
        "como fue la carga", "que carga", "que borg",
        "borg del ", "carga del ", "borg de ayer", "carga de ayer",
        "carga de hoy", "carga jugador por jugador",
    )
    if not (any(t in p for t in carga_triggers) or any(t in p for t in sesion_triggers)):
        return None
    import re as _re
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo as _ZI
        hoy = _dt.datetime.now(tz=_ZI("Europe/Madrid")).date()
    except Exception:
        hoy = _dt.date.today()
    if "anteayer" in p:
        return (hoy - _dt.timedelta(days=2)).isoformat()
    if "ayer" in p:
        return (hoy - _dt.timedelta(days=1)).isoformat()
    if "hoy" in p:
        return hoy.isoformat()
    m = _re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", p)
    if m:
        return m.group(0)
    m = _re.search(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b", p)
    if m:
        d, mo, y = m.groups()
        if not y: y = str(hoy.year)
        elif len(y) == 2: y = "20" + y
        try: return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError: pass
    MESES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
             "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
             "noviembre":11,"diciembre":12}
    pat = _re.compile(r"\b(\d{1,2})\s+(?:de\s+)?(" + "|".join(MESES.keys()) + r")(?:\s+(?:de\s+)?(\d{4}))?\b")
    m = pat.search(p)
    if m:
        d, mes_n, y = m.groups()
        if not y: y = str(hoy.year)
        try: return _dt.date(int(y), int(MESES[mes_n]), int(d)).isoformat()
        except ValueError: pass
    return ""


def _detectar_intent_ranking(prompt: str):
    """Ídem que bot_datos: matchea 'lista asistencias liga', 'ranking goleadores'.
    Devuelve (categoria, competicion) o None."""
    if not prompt:
        return None
    p = prompt.lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        p = p.replace(a, b)
    CAT_TRIGGERS = {
        "asistencias": ("asistencias", "asistencia", "asistente", "asistentes"),
        "goles":       ("goles", "goleadores", "goleador", "maximo goleador",
                          "ranking de goles", "quien mete", "quien marca"),
        "disparos":    ("disparos", "tiros totales", "ranking disparos"),
        "puerta":      ("a puerta", "disparos a puerta", "tiros a puerta"),
        "faltas":      ("faltas",),
        "amarillas":   ("amarillas", "tarjetas amarillas"),
        "rojas":       ("rojas", "tarjetas rojas", "expulsiones"),
        "perdidas":    ("perdidas", "pérdidas"),
        "robos":       ("robos", "robo", "recuperaciones"),
        "cortes":      ("cortes", "intercepciones"),
        "bdg":         ("balones ganados", "bdg"),
        "bdp":         ("balones perdidos", "bdp"),
        "minutos":     ("minutos jugados", "ranking minutos"),
        "plus_minus":  ("plus minus", "plus/minus", "+/-",
                          "diferencia goles en pista"),
    }
    triggers_ranking = (
        "lista de", "ranking", "top ", "quien ", "quién ",
        "mas ", "más ", "mayor", "mejor", "del equipo",
        "de la temporada", "en liga", "en la liga", "en copa",
        "por jugador", "por jugadores",
    )
    if not any(t in p for t in triggers_ranking):
        return None
    cat_found = None
    for cat, kws in CAT_TRIGGERS.items():
        if any(kw in p for kw in kws):
            cat_found = cat; break
    if cat_found is None:
        return None
    comp = "TODAS"
    for kw, val in (
        ("liga", "LIGA"), ("copa del rey", "COPA_REY"), ("copa rey", "COPA_REY"),
        ("copa de espana", "COPA_ESPANA"), ("copa espana", "COPA_ESPANA"),
        ("copa del mundo", "COPA_MUNDO"), ("mundial", "COPA_MUNDO"),
        ("amistoso", "AMISTOSO"), ("playoff", "PLAYOFF"), ("play off", "PLAYOFF"),
        ("supercopa", "SUPERCOPA"), ("temporada", "TODAS"),
    ):
        if kw in p:
            comp = val; break
    return (cat_found, comp)


def _detectar_intent_lesiones(prompt: str) -> bool:
    """'lesiones activas' / 'quién está lesionado' / 'bajas del equipo'."""
    if not prompt:
        return False
    p = prompt.lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        p = p.replace(a, b)
    triggers = (
        "lesiones activas", "lesiones activos", "lesion activa",
        "quien esta lesionado", "quienes estan lesionados",
        "que jugadores estan lesionados",
        "bajas del equipo", "bajas actuales", "que bajas",
        "jugadores lesionados", "lista de lesionados",
        "lesionados actuales", "quien tiene lesion",
    )
    return any(t in p for t in triggers)


def _run_carga_ultima(fecha: str = "") -> str:
    """Ejecuta src/carga_ultima_sesion.py."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    args = [fecha] if fecha else []
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "carga_ultima_sesion.py"),
        args, timeout=60,
    )
    return (f"⚠️ Error al consultar carga: {res.salida}" if not res.ok else res.salida)


def _run_ranking_temporada(categoria: str, competicion: str = "TODAS") -> str:
    """Ejecuta src/ranking_temporada.py."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    args = [categoria]
    if competicion and competicion != "TODAS":
        args.append(competicion)
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "ranking_temporada.py"),
        args, timeout=60,
    )
    return (f"⚠️ Error al consultar ranking: {res.salida}" if not res.ok else res.salida)


def _run_lesiones_activas(por_dorsal: bool = False) -> str:
    """Ejecuta src/lesiones_activas.py. Alfred es admin: nombres reales (no
    dorsal)."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    args = ["--por-dorsal"] if por_dorsal else []
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "lesiones_activas.py"),
        args, timeout=60,
    )
    return (f"⚠️ Error al consultar lesiones: {res.salida}" if not res.ok else res.salida)


def _run_estado_jugador(canonico: str, n: int) -> str:
    """Ejecuta src/estado_jugador.py vía el helper común. Sin paths
    hardcodeados ni filtros de warning duplicados (eso lo hace el helper)."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "estado_jugador.py"),
        [canonico, str(n)],
        timeout=60,
    )
    if not res.ok:
        return f"⚠️ Error al consultar {canonico}: {res.salida}"
    return res.salida


async def _process_prompt(prompt: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                          kind: str = "texto"):
    """Lógica común para texto y voz transcrita."""
    chat_id = update.effective_chat.id
    user_name = (update.effective_user.first_name if update.effective_user else None) or "usuario"
    continuar = chat_id not in _fresh_chats
    _fresh_chats.discard(chat_id)

    # ── ATAJOS SIN LLM (evitan safety filters + son deterministas) ──
    # Orden de prioridad: más específico primero. Si matchea uno, ejecuta
    # el script curado y retorna sin pasar por Gemini.
    if _detectar_intent_lesiones(prompt):
        log.info("ATAJO intent=lesiones_activas (prompt='%s')", prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        # Alfred = admin: nombres reales (sin --por-dorsal)
        salida = await asyncio.to_thread(_run_lesiones_activas, False)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            try: await update.message.reply_text(trozo, parse_mode="Markdown")
            except Exception: await update.message.reply_text(trozo)
        return

    intent_r = _detectar_intent_ranking(prompt)
    if intent_r is not None:
        cat, comp = intent_r
        log.info("ATAJO intent=ranking cat=%s comp=%s (prompt='%s')",
                 cat, comp, prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        salida = await asyncio.to_thread(_run_ranking_temporada, cat, comp)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            try: await update.message.reply_text(trozo, parse_mode="Markdown")
            except Exception: await update.message.reply_text(trozo)
        return

    intent_cu = _detectar_intent_carga_ultima(prompt)
    if intent_cu is not None:
        log.info("ATAJO intent=carga_ultima fecha=%r (prompt='%s')",
                 intent_cu, prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        salida = await asyncio.to_thread(_run_carga_ultima, intent_cu)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            try: await update.message.reply_text(trozo, parse_mode="Markdown")
            except Exception: await update.message.reply_text(trozo)
        return

    intent = _detectar_intent_estado(prompt)
    if intent:
        canonico, n = intent
        log.info("ATAJO intent=estado_jugador jugador=%s n=%d (prompt='%s')",
                 canonico, n, prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        salida = await asyncio.to_thread(_run_estado_jugador, canonico, n)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            await update.message.reply_text(trozo, parse_mode="Markdown")
        return

    # Si hay acciones locales (slash commands) ejecutadas desde el último
    # prompt a Claude, le contamos qué pasó. Si no, prompt va tal cual.
    pendientes = _acciones_pendientes.pop(chat_id, [])
    if pendientes and continuar:
        contexto = (
            "[Contexto del bot — acciones que el usuario ha disparado por "
            "comandos del bot DESDE TU ÚLTIMO MENSAJE; el bot las ejecutó "
            "directamente, no las viste pasar:]\n"
            + "\n".join(f"  - {p}" for p in pendientes)
            + "\n\n[Mensaje del usuario:]\n"
            + prompt
        )
        prompt_final = contexto
        log.info("→ prompt (%s, +%d accs): %s",
                 "continuar" if continuar else "NUEVA",
                 len(pendientes),
                 prompt[:100].replace("\n", " "))
    else:
        prompt_final = prompt
        log.info("→ prompt (%s): %s",
                 "continuar" if continuar else "NUEVA",
                 prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    async def _progress(text: str):
        try:
            await update.message.reply_text(text)
        except Exception:
            pass

    try:
        rc, out, err = await _run_gemini(prompt_final,
                                            continue_session=continuar,
                                            progress_cb=_progress)
    finally:
        stop.set()
        try:
            await typing_task
        except Exception:
            pass

    if rc != 0:
        detalle = (err or out or "(sin detalles)").strip()
        # Traducción a lenguaje humano
        det_low = detalle.lower()
        if "perdayperprojectpermodel" in det_low or "limit: 0" in det_low:
            msg_user = (
                "⚠️ Hoy ya no me quedan llamadas en la cuota gratis de Gemini. "
                "Reintenta mañana o mira el panel de Google AI Studio."
            )
        elif "resourceexhausted" in det_low or "429" in detalle[:50]:
            msg_user = "⚠️ Rate limit de Gemini. Dame 1 minuto y reintenta."
        elif "timeout" in det_low or "deadline" in det_low:
            msg_user = "⚠️ Tardé demasiado. Reformula más concreto y reintenta."
        elif "networkerror" in det_low or "connecterror" in det_low:
            msg_user = "⚠️ Se cayó la red del servidor. Reintenta en 1-2 min."
        else:
            msg_user = "⚠️ No me sale ahora."
        # IMPORTANTE: enviar como TEXTO PLANO (no Markdown). El detalle del
        # error puede contener ^, paréntesis desbalanceados, _, *, etc., que
        # rompen el parser de Markdown de Telegram (BadRequest).
        msg_full = msg_user
        if len(detalle) > 30:
            msg_full += f"\n\n(detalle técnico: {detalle[:600]}...)"
        for chunk in _chunks(msg_full):
            try:
                await update.message.reply_text(chunk)  # sin parse_mode = texto plano
            except Exception as _send_err:
                log.warning("No pude enviar el msg de error: %s", _send_err)
        _append_log(chat_id, user_name, prompt, msg_full, kind=kind)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 Claude no devolvió respuesta.")
        _append_log(chat_id, user_name, prompt, "(sin respuesta)", kind=kind)
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)
    _append_log(chat_id, user_name, prompt, response, kind=kind)


def _detectar_intent(texto: str) -> Optional[str]:
    """Detecta si un mensaje en lenguaje natural pide ejecutar un slash
    command conocido. Devuelve el nombre del comando (sin barra) o None.

    Diseño: matching de palabras clave/expresiones regulares simples.
    Filosofía: si tengo dudas, devuelvo None y el mensaje va al LLM.
    """
    t = texto.strip().lower()
    # Quitar el "alfred" / "asistente" / "bot" / signos de puntuación al inicio
    t = re.sub(r'^(?:alfred|asistente|bot|hey|oye|hola)[,\.\s]+', '', t)
    t = t.rstrip('.?!')

    # Detección palabra por palabra. Orden = prioridad (más específico
    # primero). El primero que matchee gana.
    INTENTS = [
        # /golespartido — describir los goles del último partido en orden
        ("golespartido", [
            r'\bgolespartido\b',
            r'\bgoles\s+(?:del\s+)?partido\b',
            r'\bdescrib(?:i|e|ir)?\s+(?:los\s+)?goles\b',
            r'\bvoy\s+a\s+(?:describir|contar)\s+(?:los\s+)?goles\b',
            r'\bcuento\s+(?:los\s+)?goles\b',
        ]),
        # /auditar — auditar hojas crudas en busca de errores
        ("auditar", [
            r'\baudita(?:r|me)?\b',
            r'\baudit(?:o|or[ií]a)?\b',
            r'\brevisa(?:r)?\s+(?:el\s+)?(?:sheet|excel|datos)\b',
            r'\bbusca(?:r)?\s+(?:los\s+)?(?:errores|inconsistencias|fallos)\b',
            r'\bhay\s+(?:algun(?:os?)?\s+)?(?:error|fallo|inconsistencia)\b',
            r'\binconsistencias?\b',
        ]),
        # /prepost — estado de PRE/POST/BORG de la última sesión.
        ("prepost", [
            r'\bprepost\b',
            r'\bpre\s*[/\-y]\s*post\b',
            r'\bestado\s+(?:del?\s+)?(?:pre|post)\b',
            r'\bestado\s+(?:de\s+)?(?:la\s+)?(?:sesi[oó]n|entreno)\b',
            r'\b(?:qui[eé]n|quien(?:es)?)\s+(?:falta|ha\s+hecho|ha\s+rellenado)\b',
            r'\bfalta(?:n)?\s+(?:de\s+)?(?:los\s+)?(?:pre|post|borg)\b',
            r'\bpendientes?\s+(?:del?\s+)?(?:pre|post|borg|entreno|sesi[oó]n)\b',
            r'\bcontrol\s+(?:de\s+)?(?:la\s+)?sesi[oó]n\b',
        ]),
        # /oliver_deep DEBE ir antes que /oliver_sync porque "deep" es más
        # específico que el genérico "oliver".
        ("oliver_deep", [
            r'\boliver\s+deep\b',
            r'\bdeep\s+oliver\b',
            r'\b(?:an[aá]lisis\s+)?profundo\s+(?:de\s+)?oliver\b',
            r'\boliver\s+profundo\b',
            r'\bsync\s+profundo\s+(?:de\s+)?oliver\b',
        ]),
        ("oliver_sync", [
            r'\bsync\s+oliver\b',
            r'\bsincron[ií]za(?:r)?\s+(?:el\s+)?oliver\b',
            r'\boliver\s+sync\b',
            r'\bactualiza(?:r)?\s+(?:el\s+)?oliver\b',
            r'\bbaja(?:r)?\s+(?:los\s+)?datos\s+(?:de\s+)?oliver\b',
            r'\bsincron[ií]za(?:r)?\s+gps\b',
        ]),
        ("ejercicios_sync", [
            r'\bsync\s+(?:de\s+)?ejercicios\b',
            r'\bejercicios\s+sync\b',
            r'\bsincron[ií]za(?:r)?\s+(?:los\s+)?ejercicios\b',
            r'\bactualiza(?:r)?\s+(?:los\s+)?ejercicios\b',
            r'\brecalcula(?:r)?\s+(?:los\s+)?ejercicios\b',
            r'\bproc[ée]sa(?:r)?\s+(?:los\s+)?ejercicios\b',
        ]),
        ("ejercicios_voz", [
            r'^apunta(?:r)?\s+(?:los\s+)?ejercicios\b',
            r'\bmodo\s+ejercicios\b',
            r'\b(?:quiero|voy\s+a)\s+apuntar\s+(?:los\s+)?ejercicios\b',
            r'\bvamos\s+a\s+apuntar\s+(?:los\s+)?ejercicios\b',
            r'\bdictar?\s+(?:los\s+)?ejercicios\b',
        ]),
        ("sesion", [
            r'^apunta(?:r)?\s+(?:la\s+)?sesi[oó]n\b',
            r'\bmodo\s+sesi[oó]n\b',
            r'^sesi[oó]n$',
            r'\b(?:quiero|voy\s+a)\s+apuntar\s+(?:la\s+)?sesi[oó]n\b',
            r'\bvamos\s+a\s+apuntar\s+(?:la\s+)?sesi[oó]n\b',
            r'\bdictar?\s+(?:la\s+)?sesi[oó]n\b',
        ]),
        ("consolidar", [
            r'\bconsolida(?:r|me|los)?\b',
            r'\blanza(?:r)?\s+consolidar?\b',
            r'\bactualiza(?:r)?\s+(?:los\s+)?(?:datos|forms?)\b',
            r'\bvuelca(?:r)?\s+(?:los\s+)?forms?\b',
            r'\brecalcula(?:r)?\s+(?:las\s+)?vistas\b',
            r'\bactualiza(?:r)?\s+(?:el\s+)?dashboard\b',
            r'\binteg(?:r|ra)(?:r|alo)?\s+(?:los\s+)?forms?\b',
        ]),
        # Más específico primero: enlaces por jugador (wa.me) tiene que
        # matchear ANTES que el genérico /enlaces.
        ("enlaces_wa", [
            r'\benlaces?\b.*\bjugadores?\b',                # "enlaces para/a/de los jugadores"
            r'\bjugadores?\b.*\benlaces?\b',                # "a cada jugador los enlaces"
            r'\benlaces?\b.*\bcada\s+(?:uno|jugador)\b',    # "enlaces a cada uno"
            r'\benv[ií]a\b.*\b(?:cada\s+jugador|los\s+jugadores)\b',
            r'\bm[aá]nda\b.*\b(?:cada\s+jugador|los\s+jugadores)\b',
            r'\bwa\.?me\b',
            r'\benlaces?\s+wh?atsapp\s+(?:individual|personal|por\s+jugador)\b',
            r'^/?enlaces_wa\b',
        ]),
        ("enlaces", [
            r'^enlaces?\.?$',
            r'\bdame\s+(?:los\s+)?enlaces?\b',
            r'\bm[aá]ndame\s+(?:los\s+)?enlaces?\b',
            r'\bp[aá]same\s+(?:los\s+)?enlaces?\b',
            r'\benlaces?\s+(?:de\s+)?hoy\b',
            r'\benlaces?\s+(?:del\s+)?d[ií]a\b',
            r'\bgenera(?:r)?\s+(?:los\s+)?enlaces?\b',
            r'\benv[ií]a(?:me)?\s+(?:los\s+)?enlaces?\b',
            r'\benlaces?\s+(?:al\s+grupo\s+)?(?:de\s+)?whatsapp\b',
        ]),
        ("nuevo", [
            r'^/?nuevo\.?$',
            r'^empiez(?:a|alo|amos)\s+de\s+cero\.?$',
            r'^olv[ií]da(?:r|lo)?\s+(?:el\s+)?contexto\.?$',
            r'^nueva\s+conversaci[oó]n\.?$',
            r'^reset\.?$',
            r'^empezar?\s+de\s+nuevo\.?$',
        ]),
    ]

    for cmd, patterns in INTENTS:
        for pat in patterns:
            if re.search(pat, t, flags=re.IGNORECASE):
                return cmd
    return None


# Mapping de intent → handler async
def _intent_handler(cmd: str):
    """Devuelve el handler async asociado al intent (None si no matchea)."""
    return {
        "consolidar": cmd_consolidar,
        "enlaces": cmd_enlaces,
        "enlaces_wa": cmd_enlaces_wa,
        "prepost": cmd_prepost,
        "auditar": cmd_auditar,
        "golespartido": cmd_golespartido,
        "oliver_sync": cmd_oliver_sync,
        "oliver_deep": cmd_oliver_deep,
        "ejercicios_sync": cmd_ejercicios_sync,
        "sesion": cmd_sesion_voz,
        "ejercicios_voz": cmd_ejercicios_voz,
        "nuevo": cmd_nuevo,
    }.get(cmd)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        log.warning("Acceso denegado desde chat_id=%s (@%s)",
                    update.effective_chat.id,
                    update.effective_user.username if update.effective_user else "?")
        await update.message.reply_text("🚫 Acceso denegado.")
        return

    prompt = (update.message.text or "").strip()
    if not prompt:
        return

    # Si el chat está en modo /ejercicios_voz o /sesion (vivos < 15 min),
    # también aceptamos TEXTO (no solo audio). Útil cuando es más rápido
    # escribir que dictar.
    chat_id = update.effective_chat.id
    ahora = _dt.datetime.now().timestamp()

    ts_ej = _modo_ejercicios_voz.get(chat_id)
    if ts_ej and (ahora - ts_ej) < EJVOZ_TTL_SEG:
        _modo_ejercicios_voz.pop(chat_id, None)
        _append_log(chat_id,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    prompt, "(procesado como /ejercicios_voz)", kind="texto")
        await _procesar_audio_ejercicios(prompt, update, ctx)
        return

    ts_se = _modo_sesion_voz.get(chat_id)
    if ts_se and (ahora - ts_se) < SESVOZ_TTL_SEG:
        _modo_sesion_voz.pop(chat_id, None)
        _append_log(chat_id,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    prompt, "(procesado como /sesion)", kind="texto")
        await _procesar_audio_sesion(prompt, update, ctx)
        return

    ts_g = _modo_goles_voz.get(chat_id)
    if ts_g and (ahora - ts_g) < GOLESVOZ_TTL_SEG:
        _modo_goles_voz.pop(chat_id, None)
        _append_log(chat_id,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    prompt, "(procesado como /golespartido)", kind="texto")
        await _procesar_audio_goles(prompt, update, ctx)
        return

    # Detector de intención: si el mensaje matchea con un slash command
    # conocido, ejecutamos el handler local sin pasar por Gemini (más
    # rápido, más fiable, mismos mensajes de progreso que el slash).
    intent = _detectar_intent(prompt)
    if intent:
        handler = _intent_handler(intent)
        if handler:
            log.info("[%s] intent detectado: %s -> %s",
                     chat_id, prompt[:80].replace('\n', ' '), intent)
            _append_log(chat_id,
                        (update.effective_user.first_name if update.effective_user else None) or "usuario",
                        prompt, f"(detectado como /{intent})", kind="texto")
            await handler(update, ctx)
            return

    await _process_prompt(prompt, update, ctx)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Audio/voz → Whisper → trata el texto como un prompt normal."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return

    if not _WHISPER_OK:
        await update.message.reply_text(
            "🎤 Audio no soportado (faster-whisper no instalado).\n"
            "Manda el mensaje escrito, o instala con: "
            "`cd telegram_bot && ./venv/bin/pip install faster-whisper`"
        )
        return

    voice = update.message.voice or update.message.audio or update.message.video_note
    if voice is None:
        return

    chat_id = update.effective_chat.id
    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)

    tmp = tempfile.NamedTemporaryFile(prefix="tg_voice_", suffix=".ogg", delete=False)
    tmp.close()
    audio_path = tmp.name

    try:
        tg_file = await voice.get_file()
        await tg_file.download_to_drive(audio_path)
        log.info("🎤 audio %.1fs → transcribiendo",
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
            "🤷 No he entendido el audio. ¿Puedes repetirlo o escribirlo?"
        )
        return

    await update.message.reply_text(f"🎤 Entendido: «{text}»")

    # Si el chat está en modo /ejercicios_voz y no ha caducado → procesar como ejercicios
    chat_id_v = update.effective_chat.id
    ts = _modo_ejercicios_voz.get(chat_id_v)
    ahora = _dt.datetime.now().timestamp()
    if ts and (ahora - ts) < EJVOZ_TTL_SEG:
        _modo_ejercicios_voz.pop(chat_id_v, None)
        _append_log(chat_id_v,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    text, "(procesado como ejercicios_voz)", kind="voz")
        await _procesar_audio_ejercicios(text, update, ctx)
        return

    # Si el chat está en modo /sesion y no ha caducado → procesar como sesión
    ts_s = _modo_sesion_voz.get(chat_id_v)
    if ts_s and (ahora - ts_s) < SESVOZ_TTL_SEG:
        _modo_sesion_voz.pop(chat_id_v, None)
        _append_log(chat_id_v,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    text, "(procesado como sesion_voz)", kind="voz")
        await _procesar_audio_sesion(text, update, ctx)
        return

    # Si el chat está en modo /golespartido → procesar como descripción goles
    ts_g = _modo_goles_voz.get(chat_id_v)
    if ts_g and (ahora - ts_g) < GOLESVOZ_TTL_SEG:
        _modo_goles_voz.pop(chat_id_v, None)
        _append_log(chat_id_v,
                    (update.effective_user.first_name if update.effective_user else None) or "usuario",
                    text, "(procesado como /golespartido)", kind="voz")
        await _procesar_audio_goles(text, update, ctx)
        return

    await _process_prompt(text, update, ctx, kind="voz")


SYSTEM_PROMPT_VISION = """\
Eres un extractor de datos de imágenes para Movistar Inter FS.
El cuerpo técnico te manda fotos de:
  - Planillas de partido escritas a mano (con dorsales, minutos por
    rotación, faltas, eventos de gol, marcador, etc.).
  - Capturas de pantalla del Excel `Estadisticas2526.xlsx`.
  - Fotos de papel con BORG o peso de un día.
  - Capturas de WhatsApp con un dato concreto que un jugador mandó
    (peso, lesión, comentario).
  - Cualquier otra imagen relevante.

Tu tarea: EXTRAER los datos visibles y devolverlos en español como
texto claro y estructurado. NO inventes nada. Si una celda está
borrosa o no se entiende, marca "?" o "no legible".

FORMATO de salida (siempre en español, sin Markdown HTML):
  - Si es planilla de partido, devuelve por bloques:
      · Cabecera (fecha, rival, lugar, marcador final)
      · Plantilla (lista de DORSAL · NOMBRE · MIN_1T · MIN_2T · MIN_TOTAL)
      · Eventos de gol (min · goleador · acción)
      · Faltas (min · equipo)
  - Si es BORG/peso, devuelve por cada fila visible:
      · JUGADOR · valor
  - Si es algo libre, descríbelo brevemente y extrae la info clave.

Aplica el roster oficial al normalizar nombres:
  HERRERO, GARCIA, OSCAR (porteros) · CECILIO, CHAGUINHA, RAUL,
  HARRISON, RAYA, JAVI, PANI, PIRATA, BARONA, CARLOS · RUBIO, JAIME,
  SEGO, DANI, GONZALO, PABLO, GABRI, NACHO, ANCHU.

Aliases: J.HERRERO→HERRERO, J.GARCIA→GARCIA, GONZA→GONZALO,
SERGIO/VIZUETE→RUBIO, CHAGAS→CHAGUINHA, SEGOVIA→SEGO.

Si la imagen no contiene datos relevantes (paisaje, meme, etc.),
dilo y para.
"""


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Foto → Gemini Vision OCR/extracción → inyecta resultado al
    historial conversacional → Alfred responde al usuario en el siguiente
    turno con la info estructurada y pregunta si quiere guardarla."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return

    chat_id = update.effective_chat.id
    msg = update.message
    photos = msg.photo or []
    if not photos:
        return

    caption = (msg.caption or "").strip()
    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
    progress = await msg.reply_text("📸 Analizando la imagen, dame un momento…")

    try:
        # Telegram da varios tamaños de la misma foto; cogemos la mejor.
        photo = photos[-1]
        tg_file = await photo.get_file()
        img_bytes = await tg_file.download_as_bytearray()

        # Cargar como PIL Image
        try:
            from PIL import Image as _PILImage
        except ImportError:
            await progress.edit_text(
                "⚠️ Pillow no instalado en la venv del bot. "
                "Pega en el server: `cd ~/Desktop/Arkaitz/telegram_bot && "
                "./venv/bin/pip install Pillow` y reinicia el bot."
            )
            return
        img = _PILImage.open(io.BytesIO(bytes(img_bytes)))

        # Construir prompt: caption del usuario + system prompt
        if caption:
            prompt_text = (
                f"El usuario manda esta imagen con la nota: «{caption}».\n\n"
                f"Extrae los datos visibles siguiendo las reglas del system prompt."
            )
        else:
            prompt_text = (
                "El usuario ha mandado esta imagen SIN comentario. "
                "Decide tú qué tipo de imagen es y extrae los datos relevantes."
            )

        # Llamada a Gemini Vision (modelo multimodal). Sin tools — solo
        # extracción de texto. Después Alfred normal verá los datos y
        # actuará.
        model_v = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT_VISION,
        )
        response = await asyncio.to_thread(
            model_v.generate_content,
            [prompt_text, img],
        )
        # Sacar texto
        try:
            extraccion = response.text or ""
        except Exception:
            cand = (response.candidates or [None])[0]
            content = getattr(cand, "content", None) if cand else None
            parts = getattr(content, "parts", None) if content else None
            extraccion = ""
            if parts:
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        extraccion += t

        if not extraccion.strip():
            await progress.edit_text(
                "⚠️ La imagen no me dio nada que extraer. ¿Está borrosa o "
                "es de algo que no reconozco? Mándame caption tipo "
                "«planilla del partido», «borg de hoy», etc."
            )
            _append_log(chat_id,
                        (update.effective_user.first_name
                         if update.effective_user else None) or "usuario",
                        f"[FOTO sin extracción] caption={caption!r}",
                        "(extracción vacía)", kind="foto")
            return

        # Inyectar el resultado en el historial de Alfred para que pueda
        # actuar en el siguiente turno (decir "sí guarda" y Alfred sabe
        # de qué hablamos).
        bloque_contexto = (
            f"[IMAGEN ANALIZADA — caption: {caption!r}]\n\n"
            f"Datos extraídos por Gemini Vision:\n{extraccion}"
        )
        history = _conv_history.get(ALLOWED_CHAT_ID, [])
        history.append({"role": "user", "parts": [{"text": bloque_contexto}]})
        # No metemos "model" turn aún — dejamos que Alfred decida cómo
        # presentárselo al usuario en su próximo turno.
        _conv_history[ALLOWED_CHAT_ID] = _truncate_history(history)

        # Mostrar al usuario el resultado tal cual (sin Markdown para
        # evitar BadRequest si Gemini usó caracteres especiales).
        await progress.delete()
        cabecera = f"📸 Extraído de la imagen{(' (' + caption + ')') if caption else ''}:\n\n"
        # Trocear si es muy largo
        for chunk in _chunks(cabecera + extraccion):
            try:
                await msg.reply_text(chunk)
            except Exception as e:
                log.warning("Error enviando extracción: %s", e)
        cierre = ("\n¿Quieres que apunte algo de aquí (sesión, BORG, "
                   "peso, lesión…)? Dime sí y qué.")
        await msg.reply_text(cierre)

        _append_log(chat_id,
                    (update.effective_user.first_name
                     if update.effective_user else None) or "usuario",
                    f"[FOTO] caption={caption!r}",
                    extraccion[:1500], kind="foto")

    except Exception as e:
        log.exception("Error procesando foto: %s", e)
        try:
            await progress.edit_text(
                f"⚠️ No pude analizar la imagen: {type(e).__name__}. "
                f"Detalle: {str(e)[:200]}"
            )
        except Exception:
            await msg.reply_text(
                f"⚠️ No pude analizar la imagen: {type(e).__name__}"
            )


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    # Log más detallado: tipo + mensaje + (si es BadRequest de Telegram, el
    # mensaje específico). Antes solo aparecía "Error no controlado" sin pista.
    err = ctx.error
    err_type = type(err).__name__
    err_msg = str(err) if err else "(sin mensaje)"
    log.error("on_error: tipo=%s msg=%s", err_type, err_msg)
    log.exception("Traceback completo del error no controlado:")
    if isinstance(update, Update) and update.effective_chat:
        try:
            # Mensaje al usuario MÁS informativo: si es BadRequest de Telegram
            # incluir un snippet del motivo (suele decir 'can't parse entities'
            # o similar) para diagnosticar sin tener que abrir logs.
            detalle = ""
            if "BadRequest" in err_type:
                detalle = f"\n(Telegram rechazó el mensaje: {err_msg[:120]})"
            await ctx.bot.send_message(
                update.effective_chat.id,
                f"⚠️ Error interno: {err_type}{detalle}",
            )
        except Exception:
            pass


# ─── Lista de comandos visible en el menú de Telegram (al pulsar "/") ─────────
# Estos son TODOS los comandos del bot, en el orden y formato que el usuario
# verá cuando escriba "/" en el chat. Telegram pinta uno por línea.
BOT_COMMANDS_ALFRED = [
    BotCommand("sesion",         "Apuntar sesión del día (voz/texto)"),
    BotCommand("ejercicios",     "Apuntar ejercicios de un entreno (voz/texto)"),
    BotCommand("consolidar",     "Volcar Forms PRE/POST → Sheet + recalcular vistas"),
    BotCommand("prepost",        "Quién ha hecho PRE/POST/BORG de la última sesión"),
    BotCommand("enlaces",        "Enlaces PRE+POST del día (genérico, 1 link)"),
    BotCommand("enlaces_wa",     "1 enlace WhatsApp por jugador (lee TELEFONOS_JUGADORES)"),
    BotCommand("retirado",       "Marcar a un jugador retirado a mitad de sesión por lesión"),
    BotCommand("golespartido",   "Describir goles de un partido (voz, vuelca a EST_EVENTOS)"),
    BotCommand("auditar",        "Audita BORG/PESO/WELLNESS/SESIONES (errores y duplicados)"),
    BotCommand("oliver_sync",    "Sync incremental con Oliver Sports (MVP)"),
    BotCommand("oliver_deep",    "Sync profundo Oliver (68 métricas)"),
    BotCommand("oliver_token",   "Regenerar token de Oliver (cuando caduca)"),
    BotCommand("ejercicios_sync", "Procesar hoja _EJERCICIOS (descarga timelines Oliver)"),
    BotCommand("nuevo",          "Resetear contexto / nueva conversación con Alfred"),
    BotCommand("id",             "Ver tu chat_id"),
    BotCommand("start",          "Mensaje de bienvenida"),
]


async def _post_init(app: "Application") -> None:
    """Se ejecuta tras conectar con Telegram. Registramos el menú de comandos."""
    try:
        await app.bot.set_my_commands(BOT_COMMANDS_ALFRED)
        log.info("Menú de comandos registrado (%d entradas).", len(BOT_COMMANDS_ALFRED))
    except Exception as e:
        log.warning("No pude registrar el menú de comandos: %s", e)


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    app = (Application.builder()
              .token(TOKEN)
              .post_init(_post_init)
              .build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("oliver_sync", cmd_oliver_sync))
    app.add_handler(CommandHandler("oliver_deep", cmd_oliver_deep))
    app.add_handler(CommandHandler("oliver_token", cmd_oliver_token))
    app.add_handler(CommandHandler("enlaces", cmd_enlaces))
    app.add_handler(CommandHandler("enlaces_wa", cmd_enlaces_wa))
    app.add_handler(CommandHandler("enlaces_hoy", cmd_enlaces_hoy))
    app.add_handler(CommandHandler("consolidar", cmd_consolidar))
    app.add_handler(CommandHandler("prepost", cmd_prepost))
    app.add_handler(CommandHandler("auditar", cmd_auditar))
    app.add_handler(CommandHandler("retirado", cmd_retirado))
    app.add_handler(CommandHandler("golespartido", cmd_golespartido))
    app.add_handler(CommandHandler("ejercicios_sync", cmd_ejercicios_sync))
    # /ejercicios = activa modo voz/texto + tras procesar lanza oliver_ejercicios
    # automáticamente (parse_ejercicios_voz.py ya hace el chain). El nombre
    # antiguo /ejercicios_voz se mantiene como alias por retrocompatibilidad.
    app.add_handler(CommandHandler("ejercicios", cmd_ejercicios_voz))
    app.add_handler(CommandHandler("ejercicios_voz", cmd_ejercicios_voz))
    app.add_handler(CommandHandler("sesion", cmd_sesion_voz))
    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_error_handler(on_error)

    # Recordatorio quincenal: chequea cada 24h si toca
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            _check_recordatorio_deep,
            interval=24 * 3600,  # cada 24 horas
            first=30,            # primer check a los 30 segundos de arrancar
            name="oliver_deep_reminder",
        )
        app.job_queue.run_repeating(
            _check_recordatorios_fecha,
            interval=24 * 3600,  # cada 24 horas
            first=45,            # 15s después del otro check
            name="recordatorios_fecha",
        )
        # Recordatorio semanal de ejercicios: lunes 8:00 hora Madrid
        try:
            from zoneinfo import ZoneInfo
            hora_lunes = _dt.time(8, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        except Exception:
            hora_lunes = _dt.time(8, 0)  # fallback sin tz
        app.job_queue.run_daily(
            _check_ejercicios_lunes,
            time=hora_lunes,
            days=(0,),  # 0 = lunes en python-telegram-bot
            name="ejercicios_revision_semanal",
        )
        # Auditoría semanal del Sheet: lunes 8:05 (5 min después de
        # ejercicios). Solo avisa si hay incidencias.
        try:
            hora_audit = _dt.time(8, 5, tzinfo=ZoneInfo("Europe/Madrid"))
        except Exception:
            hora_audit = _dt.time(8, 5)
        app.job_queue.run_daily(
            _check_auditoria_semanal,
            time=hora_audit,
            days=(0,),
            name="auditoria_semanal",
        )
        # Keep-alive de Streamlit cada 12h (primer ping a los 60s de arrancar)
        app.job_queue.run_repeating(
            _streamlit_keepalive,
            interval=12 * 3600,
            first=60,
            name="streamlit_keepalive",
        )
        log.info("Recordatorios automáticos: ON (quincenal Oliver + fechas + lunes 8h ejercicios + 8:05h auditoría + keepalive Streamlit 12h)")
    else:
        log.warning("job_queue no disponible (instala python-telegram-bot[job-queue]); "
                    "sin recordatorios automáticos")

    log.info("Bot arrancado (voz: %s). Escuchando mensajes… (Ctrl+C para parar)",
             "ON" if _WHISPER_OK else "OFF")

    # ── Validación al arrancar: mandar Telegram a Arkaitz con el estado ──
    # No bloqueamos si falla, pero avisamos si hay algún componente roto.
    # Esto detecta a tiempo problemas tras reinicio (Sheet sin acceso,
    # paquetes Python rotos, etc.) en lugar de descubrirlos al usar el bot.
    try:
        sys.path.insert(0, str(PROJECT_DIR / "src"))
        from health_check import (  # type: ignore
            run_health_check_quick, format_resultados, all_ok,
        )
        _hc = run_health_check_quick()
        _hc_txt = format_resultados(_hc)
        if all_ok(_hc):
            _msg = f"✅ *Bot dev arrancado* — health check OK\n```\n{_hc_txt}\n```"
        else:
            _msg = f"⚠️ *Bot dev arrancado con avisos*\n```\n{_hc_txt}\n```"
        # Mandamos por sendMessage HTTP directo para no depender del polling
        import urllib.parse as _u
        import urllib.request as _r
        _data = _u.urlencode({
            "chat_id": str(ALLOWED_CHAT_ID),
            "text": _msg,
            "parse_mode": "Markdown",
            "disable_notification": "true",
        }).encode()
        _req = _r.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=_data, method="POST",
        )
        try:
            _r.urlopen(_req, timeout=20).read()
        except Exception:
            pass
    except Exception as _e:
        log.warning("health check al arrancar falló: %s", _e)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
