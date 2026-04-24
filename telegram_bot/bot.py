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
import datetime as _dt
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

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
CLAUDE_TIMEOUT  = int(os.getenv("CLAUDE_TIMEOUT", "600"))
CLAUDE_BIN_ENV  = os.getenv("CLAUDE_BIN", "").strip()

MAX_MSG_LEN = 4000  # margen sobre el límite 4096 de Telegram
BOT_NAME    = "InterFS_bot"  # identificador en los logs espejados

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


async def _run_claude(prompt: str, continue_session: bool = True) -> Tuple[int, str, str]:
    """Ejecuta `claude -p <prompt>` en PROJECT_DIR.
    --dangerously-skip-permissions: modo no interactivo, no hay nadie que pueda
    aprobar permisos. Seguro aquí porque solo el ALLOWED_CHAT_ID manda prompts.
    -c (--continue) mantiene el hilo de la conversación previa."""
    args = [CLAUDE_BIN, "-p", "--dangerously-skip-permissions"]
    if continue_session:
        args.append("-c")
    args.append(prompt)
    proc = await asyncio.create_subprocess_exec(
        *args,
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
    _fresh_chats.add(update.effective_chat.id)
    await update.message.reply_text(
        "🆕 Vale, el próximo mensaje empezará una conversación nueva "
        "(sin contexto de lo anterior)."
    )


async def _run_oliver_sync(deep: bool = False) -> Tuple[int, str, str]:
    """Ejecuta el script de sincronización de Oliver en el proyecto."""
    py = "/usr/bin/python3"
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
            "/usr/bin/python3", str(PROJECT_DIR / "src" / "calcular_vistas.py"),
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
        else:
            tail = (err2 or out2 or b"").decode("utf-8", "replace")[-1500:]
            await update.message.reply_text(f"⚠️ Oliver OK pero calcular_vistas falló:\n{tail}")
    else:
        detalle = (err or out or "(sin detalles)").strip()
        for chunk in _chunks(f"❌ Error en oliver_sync:\n{detalle}"):
            await update.message.reply_text(chunk)


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


async def _process_prompt(prompt: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                          kind: str = "texto"):
    """Lógica común para texto y voz transcrita."""
    chat_id = update.effective_chat.id
    user_name = (update.effective_user.first_name if update.effective_user else None) or "usuario"
    continuar = chat_id not in _fresh_chats
    _fresh_chats.discard(chat_id)
    log.info("→ prompt (%s): %s",
             "continuar" if continuar else "NUEVA",
             prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    try:
        rc, out, err = await _run_claude(prompt, continue_session=continuar)
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
        _append_log(chat_id, user_name, prompt, msg, kind=kind)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 Claude no devolvió respuesta.")
        _append_log(chat_id, user_name, prompt, "(sin respuesta)", kind=kind)
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)
    _append_log(chat_id, user_name, prompt, response, kind=kind)


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
    await _process_prompt(text, update, ctx, kind="voz")


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
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("oliver_sync", cmd_oliver_sync))
    app.add_handler(CommandHandler("oliver_deep", cmd_oliver_deep))
    app.add_handler(CommandHandler("oliver_token", cmd_oliver_token))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, on_voice))
    app.add_error_handler(on_error)

    # Recordatorio quincenal: chequea cada 24h si toca
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            _check_recordatorio_deep,
            interval=24 * 3600,  # cada 24 horas
            first=30,            # primer check a los 30 segundos de arrancar
            name="oliver_deep_reminder",
        )
        log.info("Recordatorio quincenal Oliver deep: activo")
    else:
        log.warning("job_queue no disponible (instala python-telegram-bot[job-queue]); "
                    "sin recordatorios automáticos")

    log.info("Bot arrancado (voz: %s). Escuchando mensajes… (Ctrl+C para parar)",
             "ON" if _WHISPER_OK else "OFF")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
