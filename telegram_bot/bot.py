#!/usr/bin/env python3
"""
Bot de Telegram para interactuar con Claude Code desde el móvil.
Proyecto: Arkaitz 25/26

Lee configuración desde .env y ejecuta `claude -p` sobre el proyecto.
Solo responde al chat_id autorizado (ALLOWED_CHAT_ID).
"""
from __future__ import annotations

import os
import re
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PROJECT_DIR     = Path(os.getenv("PROJECT_DIR", str(HERE.parent))).expanduser().resolve()
CLAUDE_TIMEOUT  = int(os.getenv("CLAUDE_TIMEOUT", "600"))
CLAUDE_BIN_ENV  = os.getenv("CLAUDE_BIN", "").strip()

MAX_MSG_LEN = 4000  # margen sobre el límite 4096 de Telegram

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("arkaitz-bot")


# ─── Autodetección del binario claude ────────────────────────────────────────
def find_claude_bin() -> Optional[str]:
    """Busca el ejecutable de Claude Code en este orden:
    1. Variable de entorno CLAUDE_BIN
    2. PATH del sistema (`which claude`)
    3. Claude Desktop bundled en macOS
    """
    if CLAUDE_BIN_ENV:
        return CLAUDE_BIN_ENV

    in_path = shutil.which("claude")
    if in_path:
        return in_path

    # Claude Desktop en macOS incluye Claude Code bundled
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

if not CLAUDE_BIN or not Path(CLAUDE_BIN).is_file():
    _fail(
        "No encuentro el ejecutable de Claude Code.\n"
        "   Si tienes Claude Desktop instalado, ya debería encontrarlo solo.\n"
        "   Si no, añade CLAUDE_BIN=/ruta/al/claude al archivo .env."
    )

log.info("Claude encontrado en: %s", CLAUDE_BIN)
log.info("Proyecto: %s", PROJECT_DIR)
log.info("Autorizado chat_id: %s", ALLOWED_CHAT_ID)


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


async def _run_claude(prompt: str) -> Tuple[int, str, str]:
    """Ejecuta `claude -p <prompt>` en PROJECT_DIR.
    Devuelve (exit_code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        CLAUDE_BIN, "-p", prompt,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"Timeout: Claude tardó más de {CLAUDE_TIMEOUT}s en responder."
    return (
        proc.returncode or 0,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )


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
        "Sé claro y específico; Claude tiene acceso total al proyecto."
    )


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Devuelve el chat_id a cualquiera que lo pida (útil al configurar el bot)."""
    await update.message.reply_text(
        f"Tu chat_id es: `{update.effective_chat.id}`\n"
        "Copia ese número en el campo ALLOWED_CHAT_ID del archivo .env.",
        parse_mode="Markdown",
    )


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

    chat_id = update.effective_chat.id
    log.info("→ prompt: %s", prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    try:
        rc, out, err = await _run_claude(prompt)
    finally:
        stop.set()
        try:
            await typing_task
        except Exception:
            pass

    if rc != 0:
        detalle = (err or out or "(sin detalles)").strip()
        msg = f"❌ Claude devolvió error (código {rc}).\n\n{detalle}"
        for chunk in _chunks(msg):
            await update.message.reply_text(chunk)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 Claude no devolvió respuesta.")
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.exception("Error no controlado: %s", ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(
                update.effective_chat.id,
                f"⚠️ Error interno: {type(ctx.error).__name__}",
            )
        except Exception:
            pass


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    log.info("Bot arrancado. Escuchando mensajes… (Ctrl+C para parar)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
