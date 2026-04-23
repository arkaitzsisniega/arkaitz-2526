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
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple, Set

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

TOKEN               = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS_ST = os.getenv("ALLOWED_CHAT_IDS", "").strip()
PROJECT_DIR         = Path(os.getenv("PROJECT_DIR", str(HERE.parent))).expanduser().resolve()
CLAUDE_TIMEOUT      = int(os.getenv("CLAUDE_TIMEOUT", "600"))
CLAUDE_BIN_ENV      = os.getenv("CLAUDE_BIN", "").strip()

SESIONES_DIR = HERE / "sesiones"
MAX_MSG_LEN  = 4000

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


# ─── Autodetección del binario claude ────────────────────────────────────────
def find_claude_bin() -> Optional[str]:
    if CLAUDE_BIN_ENV:
        return CLAUDE_BIN_ENV
    in_path = shutil.which("claude")
    if in_path:
        return in_path
    bundle_base = Path.home() / "Library/Application Support/Claude/claude-code"
    if bundle_base.is_dir():
        def _ver_key(p: Path):
            try:
                return tuple(int(x) for x in p.name.split("."))
            except ValueError:
                return (0,)
        versions = sorted(
            (v for v in bundle_base.iterdir() if v.is_dir() and re.match(r"^\d", v.name)),
            key=_ver_key,
            reverse=True,
        )
        for v in versions:
            cand = v / "claude.app/Contents/MacOS/claude"
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    return None


CLAUDE_BIN = find_claude_bin()


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
if not CLAUDE_BIN or not Path(CLAUDE_BIN).is_file():
    _fail("No encuentro el ejecutable de Claude Code. Revisa LEEME.md.")

SESIONES_DIR.mkdir(parents=True, exist_ok=True)

log.info("Claude: %s", CLAUDE_BIN)
log.info("Proyecto: %s", PROJECT_DIR)
log.info("Autorizados: %s", sorted(ALLOWED_CHAT_IDS))


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
Ejecuta /usr/bin/python3 con snippets como este (adapta la hoja/filtros):

```python
import pandas as pd, gspread
from google.oauth2.service_account import Credentials
creds = Credentials.from_service_account_file(
    '{PROJECT_DIR}/google_credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'])
ss = gspread.authorize(creds).open('Arkaitz - Datos Temporada 2526')
# Hojas disponibles (vistas pre-calculadas): _VISTA_CARGA, _VISTA_SEMANAL,
# _VISTA_PESO, _VISTA_WELLNESS, _VISTA_SEMAFORO, _VISTA_RECUENTO
# Hojas crudas: SESIONES, BORG, PESO, WELLNESS, LESIONES
df = pd.DataFrame(ss.worksheet('_VISTA_PESO').get_all_records(
    value_render_option=gspread.utils.ValueRenderOption.unformatted))
# filtra/agrega y print(...)
```

Después del print, resume el resultado en lenguaje humano. No pegues dataframes
crudos salvo que el usuario los pida explícitamente.

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


async def _run_claude(chat_id: int, prompt: str, continue_session: bool = True) -> Tuple[int, str, str]:
    """Ejecuta claude en un directorio de trabajo específico del usuario
    (para que cada chat_id tenga sesión aislada)."""
    # Cada usuario tiene su CWD → -c no mezcla historial entre usuarios
    user_dir = SESIONES_DIR / str(chat_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    args = [
        CLAUDE_BIN, "-p",
        "--dangerously-skip-permissions",
        "--add-dir", str(PROJECT_DIR),
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    if continue_session:
        args.append("-c")
    args.append(prompt)

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(user_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"Timeout: Claude tardó más de {CLAUDE_TIMEOUT}s."
    return (
        proc.returncode or 0,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )


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
    _fresh_chats.add(update.effective_chat.id)
    await update.message.reply_text(
        "🆕 Vale, el próximo mensaje empezará una conversación nueva "
        "(olvido el contexto anterior)."
    )


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

    chat_id = update.effective_chat.id
    continuar = chat_id not in _fresh_chats
    _fresh_chats.discard(chat_id)

    log.info("[%s] → %s: %s",
             chat_id,
             "continuar" if continuar else "NUEVA",
             prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    try:
        rc, out, err = await _run_claude(chat_id, prompt, continue_session=continuar)
    finally:
        stop.set()
        try:
            await typing_task
        except Exception:
            pass

    if rc != 0:
        detalle = (err or out or "(sin detalles)").strip()
        # No exponer stacktraces completos; resumen amable
        msg = f"⚠️ Algo falló al consultar los datos.\nDetalle técnico (para Arkaitz):\n{detalle[:1500]}"
        for chunk in _chunks(msg):
            await update.message.reply_text(chunk)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 No he podido generar respuesta.")
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    log.info("Bot de DATOS arrancado. Ctrl+C para parar.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
