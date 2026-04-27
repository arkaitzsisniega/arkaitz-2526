#!/usr/bin/env python3
"""
Bot de Telegram para gastos comunes (Arkaitz + Lis).

@GastosComunes_ArkaitzLis_bot

Acepta texto o voz. Cuando recibe un mensaje:
  1. Parsea cantidad + concepto.
  2. Sugiere categoría por keywords.
  3. Pide confirmación con botones.
  4. Al confirmar, escribe la fila al Sheet.

Comandos:
  /start              — bienvenida + ayuda
  /id                 — devuelve tu chat_id (para autorizar a alguien nuevo)
  /resumen_semana     — total + desglose por categoría últimos 7 días
  /resumen_mes        — total + desglose mes actual
  /ultimos            — últimos 10 gastos
  /borrar             — borra TU último gasto (no el de tu pareja)
  /categoria <nombre> — cambia la categoría de TU último gasto
  /categorias         — lista de categorías disponibles
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception:
    _WHISPER_OK = False

from categorias import CATEGORIAS, categorizar
from parser import GastoParseado, parsear
import sheets

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_RAW = os.getenv("ALLOWED_CHAT_IDS", "").strip()
NOMBRES_RAW = os.getenv("NOMBRES_USUARIOS", "").strip()
SHEET_ID = os.getenv("GASTOS_SHEET_ID", "").strip()

# ALLOWED_CHAT_IDS: "6357476517, 1234567890"
ALLOWED: set[int] = set()
for raw in re.split(r"[,\s]+", ALLOWED_RAW):
    if raw.strip():
        try:
            ALLOWED.add(int(raw))
        except ValueError:
            pass

# NOMBRES_USUARIOS: "6357476517=Arkaitz, 1234567890=Lis"
NOMBRES: dict[int, str] = {}
for par in re.split(r"[,\s]+", NOMBRES_RAW):
    if "=" in par:
        cid, nombre = par.split("=", 1)
        try:
            NOMBRES[int(cid.strip())] = nombre.strip()
        except ValueError:
            pass

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gastos-bot")

# ─── Whisper (lazy) ──────────────────────────────────────────────────────────
_WHISPER: Optional["WhisperModel"] = None


def _whisper() -> Optional["WhisperModel"]:
    global _WHISPER
    if not _WHISPER_OK:
        return None
    if _WHISPER is None:
        log.info("Cargando modelo Whisper 'base' (primera vez tarda)…")
        _WHISPER = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER


# ─── Helpers ─────────────────────────────────────────────────────────────────
def autorizado(update: Update) -> bool:
    if not ALLOWED:
        return True  # sin restricción si no se ha definido
    chat = update.effective_chat
    return bool(chat and chat.id in ALLOWED)


def nombre_de(chat_id: int) -> str:
    return NOMBRES.get(chat_id, f"chat_{chat_id}")


def fmt_eur(n: float) -> str:
    return f"{n:,.2f}€".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_fecha(s: str) -> str:
    """YYYY-MM-DD → DD/MM."""
    try:
        return _dt.date.fromisoformat(s).strftime("%d/%m")
    except Exception:
        return s


# ─── Comandos básicos ────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        await update.message.reply_text(
            "No estás autorizado. Pídele a Arkaitz que añada tu chat_id."
        )
        return
    nombre = nombre_de(update.effective_chat.id)
    await update.message.reply_text(
        f"¡Hola {nombre}! Soy el bot de gastos comunes.\n\n"
        "Mándame texto o voz como:\n"
        "  • «Lidl 15,85»\n"
        "  • «cena restaurante 23 euros»\n"
        "  • «acabo de gastarme 50 en gasolina»\n\n"
        "Comandos útiles:\n"
        "  /resumen_semana – últimos 7 días\n"
        "  /resumen_mes – mes actual\n"
        "  /ultimos – últimos 10 gastos\n"
        "  /borrar – borra TU último gasto\n"
        "  /categoria <nombre> – cambia categoría del último\n"
        "  /categorias – ver categorías disponibles"
    )


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    nombre = (user.first_name + " " + (user.last_name or "")).strip() if user else "?"
    await update.message.reply_text(
        f"Tu chat_id es: {chat.id}\nNombre Telegram: {nombre}"
    )


async def cmd_categorias(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    txt = "Categorías disponibles:\n" + "\n".join(f"• {c}" for c in CATEGORIAS)
    await update.message.reply_text(txt)


# ─── Flujo de gasto: parsear → confirmar → guardar ───────────────────────────
def _kb_confirmacion(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Apuntar", callback_data=f"ok|{token}"),
            InlineKeyboardButton("✏️ Categoría", callback_data=f"cat|{token}"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"no|{token}"),
        ]
    ])


def _kb_categorias(token: str) -> InlineKeyboardMarkup:
    botones = []
    fila = []
    for i, c in enumerate(CATEGORIAS):
        fila.append(InlineKeyboardButton(c, callback_data=f"setcat|{token}|{i}"))
        if len(fila) == 2:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones)


async def _procesar_texto_gasto(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texto: str):
    g = parsear(texto)
    if g.cantidad is None:
        await update.message.reply_text(
            "No he sabido encontrar la cantidad. Prueba con algo como "
            "«Lidl 15,85» o «cena 23 euros»."
        )
        return

    cat_sugerida = categorizar(g.concepto)
    # Guardamos el estado pendiente con un token único en chat_data
    token = _dt.datetime.now().strftime("%H%M%S%f")
    pendientes = ctx.chat_data.setdefault("pendientes", {})
    pendientes[token] = {
        "concepto": g.concepto or "(sin concepto)",
        "cantidad": g.cantidad,
        "categoria": cat_sugerida,
        "raw": g.raw,
    }

    msg = (
        f"💸 *{g.concepto or '(sin concepto)'}* — {fmt_eur(g.cantidad)}\n"
        f"📂 Categoría sugerida: _{cat_sugerida}_"
    )
    await update.message.reply_text(
        msg, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=_kb_confirmacion(token)
    )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    if not update.message or not update.message.text:
        return
    await _procesar_texto_gasto(update, ctx, update.message.text)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    if not update.message:
        return

    w = _whisper()
    if w is None:
        await update.message.reply_text(
            "Whisper no está disponible. Instala faster-whisper o mándame texto."
        )
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await update.message.chat.send_action(constants.ChatAction.TYPING)
    f = await voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await f.download_to_drive(tmp.name)
        path = tmp.name

    try:
        loop = asyncio.get_event_loop()
        def _transcribe():
            segs, _info = w.transcribe(path, language="es", beam_size=1)
            return " ".join(s.text.strip() for s in segs).strip()
        texto = await loop.run_in_executor(None, _transcribe)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass

    if not texto:
        await update.message.reply_text("No he entendido el audio.")
        return

    await update.message.reply_text(f"🎤 _{texto}_", parse_mode=constants.ParseMode.MARKDOWN)
    await _procesar_texto_gasto(update, ctx, texto)


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    q = update.callback_query
    await q.answer()

    data = q.data or ""
    partes = data.split("|")
    accion = partes[0]
    token = partes[1] if len(partes) > 1 else ""

    pendientes = ctx.chat_data.get("pendientes", {})
    p = pendientes.get(token)
    if not p:
        await q.edit_message_text("⚠️ Esta confirmación ha caducado.")
        return

    quien = nombre_de(update.effective_chat.id)

    if accion == "no":
        pendientes.pop(token, None)
        await q.edit_message_text("❌ Cancelado.")
        return

    if accion == "cat":
        await q.edit_message_text(
            f"💸 *{p['concepto']}* — {fmt_eur(p['cantidad'])}\n"
            "Elige categoría:",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=_kb_categorias(token),
        )
        return

    if accion == "setcat":
        idx = int(partes[2])
        p["categoria"] = CATEGORIAS[idx]
        await q.edit_message_text(
            f"💸 *{p['concepto']}* — {fmt_eur(p['cantidad'])}\n"
            f"📂 Categoría: _{p['categoria']}_",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=_kb_confirmacion(token),
        )
        return

    if accion == "ok":
        try:
            sheets.append_gasto(
                concepto=p["concepto"],
                cantidad=p["cantidad"],
                categoria=p["categoria"],
                quien=quien,
            )
        except Exception as e:
            log.exception("Error escribiendo al Sheet")
            await q.edit_message_text(f"❌ Error al guardar: {e}")
            return
        pendientes.pop(token, None)
        await q.edit_message_text(
            f"✅ Apuntado: *{p['concepto']}* — {fmt_eur(p['cantidad'])} "
            f"({p['categoria']})",
            parse_mode=constants.ParseMode.MARKDOWN,
        )


# ─── Resúmenes ───────────────────────────────────────────────────────────────
def _filtrar(rows: list[dict], desde: _dt.date, hasta: _dt.date) -> list[dict]:
    out = []
    for r in rows:
        try:
            f = _dt.date.fromisoformat(str(r.get("fecha", "")))
        except Exception:
            continue
        if desde <= f <= hasta:
            try:
                r["_cantidad"] = float(str(r.get("cantidad", 0)).replace(",", "."))
            except Exception:
                r["_cantidad"] = 0.0
            out.append(r)
    return out


def _formatear_resumen(titulo: str, rows: list[dict]) -> str:
    if not rows:
        return f"*{titulo}*\nSin gastos en este periodo."
    total = sum(r["_cantidad"] for r in rows)
    por_cat: dict[str, float] = defaultdict(float)
    for r in rows:
        por_cat[str(r.get("categoria", "Otros") or "Otros")] += r["_cantidad"]
    lineas = [f"*{titulo}*", f"Total: *{fmt_eur(total)}* ({len(rows)} gastos)", ""]
    for cat, importe in sorted(por_cat.items(), key=lambda x: -x[1]):
        pct = (importe / total * 100) if total else 0
        lineas.append(f"  • {cat}: {fmt_eur(importe)} ({pct:.0f}%)")
    return "\n".join(lineas)


async def cmd_resumen_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    hoy = _dt.date.today()
    desde = hoy - _dt.timedelta(days=6)
    try:
        rows = _filtrar(sheets.leer_todos(), desde, hoy)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    txt = _formatear_resumen(
        f"📅 Últimos 7 días ({desde.strftime('%d/%m')} – {hoy.strftime('%d/%m')})", rows
    )
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)


async def cmd_resumen_mes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    hoy = _dt.date.today()
    desde = hoy.replace(day=1)
    try:
        rows = _filtrar(sheets.leer_todos(), desde, hoy)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    nombre_mes = hoy.strftime("%B %Y").capitalize()
    txt = _formatear_resumen(f"📅 {nombre_mes}", rows)
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)


async def cmd_ultimos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    try:
        rows = sheets.leer_todos()
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    if not rows:
        await update.message.reply_text("Aún no hay gastos.")
        return
    ult = rows[-10:][::-1]
    lineas = ["*Últimos 10 gastos*", ""]
    for r in ult:
        try:
            cant = float(str(r.get("cantidad", 0)).replace(",", "."))
        except Exception:
            cant = 0.0
        lineas.append(
            f"`{fmt_fecha(str(r.get('fecha','')))}` "
            f"{fmt_eur(cant)} — {r.get('concepto','')} "
            f"_({r.get('categoria','')}, {r.get('quien_apunta','')})_"
        )
    await update.message.reply_text(
        "\n".join(lineas), parse_mode=constants.ParseMode.MARKDOWN
    )


async def cmd_borrar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    quien = nombre_de(update.effective_chat.id)
    try:
        info = sheets.borrar_ultimo(quien)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return
    if info is None:
        await update.message.reply_text("No tienes gastos para borrar.")
        return
    await update.message.reply_text(
        f"🗑 Borrado: {info.get('concepto','')} — "
        f"{info.get('cantidad','')}€ ({info.get('categoria','')})"
    )


async def cmd_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    if not ctx.args:
        await update.message.reply_text(
            "Uso: /categoria <nombre>\nMira las opciones con /categorias"
        )
        return
    pedida = " ".join(ctx.args).strip()
    # Match insensible a may/min/tildes contra CATEGORIAS
    import unicodedata
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s.lower())
        return "".join(c for c in s if unicodedata.category(c) != "Mn")
    elegida = next((c for c in CATEGORIAS if norm(c) == norm(pedida)), None)
    if elegida is None:
        await update.message.reply_text(
            f"No conozco esa categoría. Opciones:\n"
            + "\n".join(f"• {c}" for c in CATEGORIAS)
        )
        return

    quien = nombre_de(update.effective_chat.id)
    try:
        info = sheets.actualizar_categoria_ultimo(quien, elegida)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return
    if info is None:
        await update.message.reply_text("No tienes gastos para cambiar.")
        return
    await update.message.reply_text(
        f"✅ Cambiada categoría a *{elegida}* en: {info.get('concepto','')} "
        f"({info.get('cantidad','')}€)",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en gastos_bot/.env")
    if not SHEET_ID:
        raise SystemExit("Falta GASTOS_SHEET_ID en gastos_bot/.env")
    if not ALLOWED:
        log.warning("ALLOWED_CHAT_IDS vacío: el bot aceptará a CUALQUIERA. Configúralo.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("categorias", cmd_categorias))
    app.add_handler(CommandHandler("resumen_semana", cmd_resumen_semana))
    app.add_handler(CommandHandler("resumen_mes", cmd_resumen_mes))
    app.add_handler(CommandHandler("ultimos", cmd_ultimos))
    app.add_handler(CommandHandler("borrar", cmd_borrar))
    app.add_handler(CommandHandler("categoria", cmd_categoria))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot de gastos arrancado. Usuarios autorizados: %s", sorted(ALLOWED) or "TODOS")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
