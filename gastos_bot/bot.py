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
from clasificador_gemini import clasificar as clasificar_con_claude  # nombre histórico, ahora Gemini
from intencion import detectar_intencion
from parser import GastoParseado, parsear
import gastos_fijos
import sheets

# Zona horaria Madrid para JobQueue (gastos fijos se aplican a las 09:00
# hora local, no UTC).
try:
    from zoneinfo import ZoneInfo
    TZ_MADRID = ZoneInfo("Europe/Madrid")
except Exception:
    TZ_MADRID = None  # fallback: usará UTC

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


NOMBRES_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


AYUDA_TXT = (
    "Te puedo ayudar con esto:\n"
    "  • Apuntar un gasto: «Lidl 15,85» o «cena 23 euros» (texto o voz).\n"
    "  • Resumen agregado del mes: «resumen del mes», «resumen de abril».\n"
    "  • Lista detallada: «todos los gastos de abril uno a uno», "
    "«detállame los gastos de mayo».\n"
    "  • Última semana: «resumen de la semana» o «gastos de la semana uno a uno».\n"
    "  • Últimos gastos: «últimos gastos».\n\n"
    "Comandos: /resumen_mes, /resumen_semana, /ultimos, /borrar, /categorias."
)


async def _despachar_intencion(update: Update, intencion) -> bool:
    """Ejecuta la intención. Devuelve True si la ha manejado, False si no.

    `intencion` puede ser:
      - tupla (tipo, param)  ← formato heurístico legacy
      - dict con keys tipo/param/cantidad/concepto/categoria  ← formato Claude
    """
    if not intencion:
        return False
    if isinstance(intencion, tuple):
        tipo, param = intencion
        cantidad = concepto = categoria = None
    else:
        tipo = intencion.get("tipo")
        param = intencion.get("param")
        cantidad = intencion.get("cantidad")
        concepto = intencion.get("concepto")
        categoria = intencion.get("categoria")

    if tipo == "resumen_semana":
        await _enviar_resumen_semana(update); return True
    if tipo == "resumen_mes":
        await _enviar_resumen_mes_actual(update); return True
    if tipo == "resumen_mes_de":
        await _enviar_resumen_mes_de(update, param); return True
    if tipo == "lista_semana":
        await _enviar_lista_semana(update); return True
    if tipo == "lista_mes":
        await _enviar_lista_mes_actual(update); return True
    if tipo == "lista_mes_de":
        await _enviar_lista_mes_de(update, param); return True
    if tipo == "lista_todos":
        await _enviar_lista_todos(update); return True
    if tipo == "ultimos":
        await _enviar_ultimos(update); return True
    if tipo == "cambiar_categoria_ultimo":
        await _cambiar_categoria_ultimo(update, categoria); return True
    if tipo == "ayuda":
        await update.message.reply_text(AYUDA_TXT); return True
    return False


async def _cambiar_categoria_ultimo(update: Update, categoria: Optional[str]):
    if not autorizado(update):
        return
    if not categoria:
        await update.message.reply_text(
            "¿A qué categoría? Mira las opciones con /categorias."
        )
        return
    if categoria not in CATEGORIAS:
        await update.message.reply_text(
            f"No conozco la categoría «{categoria}». Opciones:\n"
            + "\n".join(f"• {c}" for c in CATEGORIAS)
        )
        return
    quien = nombre_de(update.effective_chat.id)
    try:
        info = sheets.actualizar_categoria_ultimo(quien, categoria)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return
    if info is None:
        await update.message.reply_text("No tienes gastos para cambiar.")
        return
    await update.message.reply_text(
        f"✅ Cambiada categoría a *{categoria}* en: {info.get('concepto','')} "
        f"({info.get('cantidad','')}€)",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


def _texto_parece_natural(texto: str) -> bool:
    """Heurística simple: si el texto es "Lidl 15,85" lo manejamos local;
    si es "Apunta 11 euros del mercado en categoría supermercados" lo
    pasamos a Claude porque entiende mejor."""
    s = texto.strip()
    palabras = s.split()
    if len(palabras) > 6:
        return True
    s_low = s.lower()
    senales = (
        "categoria", "categoría", "como ", "ponlo", "ahora mismo",
        "acabo de", "hemos gastado", "me he gastado", "apunta",
        "anota", "anotame", "registra", "guarda", "el último",
        "cambialo", "cámbialo",
    )
    return any(p in s_low for p in senales)


async def _procesar_texto_gasto(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texto: str):
    # ─── 1) Heurística rápida de intención (consultas) ──────────────────────
    intencion = detectar_intencion(texto)
    if intencion is not None and intencion[0] != "ayuda":
        if await _despachar_intencion(update, intencion):
            return

    # ─── 2) Apunte rápido y limpio (regex local) ────────────────────────────
    # Solo cuando el mensaje es claramente "Lidl 15,85" o similar:
    # - Tiene cantidad
    # - NO parece lenguaje natural (frase corta sin muletillas)
    g = parsear(texto)
    if g.cantidad is not None and not _texto_parece_natural(texto):
        await _procesar_apunte(update, ctx, g)
        return

    # ─── 3) Mensaje complejo → Claude (entiende lenguaje natural) ───────────
    await update.message.chat.send_action(constants.ChatAction.TYPING)
    intent_claude = await clasificar_con_claude(texto)

    if intent_claude is not None:
        # Caso especial: Claude dice "apuntar_gasto" y trae cantidad+concepto
        if intent_claude.get("tipo") == "apuntar_gasto":
            cantidad = intent_claude.get("cantidad")
            concepto = intent_claude.get("concepto")
            categoria = intent_claude.get("categoria")
            if cantidad is not None and concepto:
                g_claude = GastoParseado(
                    cantidad=float(cantidad),
                    concepto=str(concepto),
                    raw=texto,
                )
                # Si Claude sugiere una categoría válida, la pasamos
                await _procesar_apunte(update, ctx, g_claude,
                                       categoria_forzada=categoria)
                return
            # Sin cantidad → fallback a parser
            if g.cantidad is not None:
                await _procesar_apunte(update, ctx, g)
                return

        # Otras intenciones (resumen, lista, cambiar categoría, etc.)
        if await _despachar_intencion(update, intent_claude):
            return

    # ─── 4) Nada ha clasificado: si tenemos cantidad → apuntar igualmente ──
    if g.cantidad is not None:
        await _procesar_apunte(update, ctx, g)
        return

    # ─── 5) Total desconocido → ayuda ───────────────────────────────────────
    await update.message.reply_text(
        "🤔 No he sabido si quieres apuntar un gasto o consultar algo.\n\n"
        + AYUDA_TXT
    )


async def _procesar_apunte(update: Update, ctx: ContextTypes.DEFAULT_TYPE, g: GastoParseado,
                           categoria_forzada: Optional[str] = None):
    # Prioridad de categoría: forzada (Claude) > explícita en el texto > sugerida por keywords
    if categoria_forzada and categoria_forzada in CATEGORIAS:
        cat_sugerida = categoria_forzada
    elif getattr(g, "categoria_explicita", None) and g.categoria_explicita in CATEGORIAS:
        cat_sugerida = g.categoria_explicita
    else:
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
        # Tras apuntar, mandamos automáticamente el resumen del mes en
        # curso: total + por categorías + cronología concepto a concepto.
        # Lo hacemos en best-effort: si Sheets va lento, no bloquea ni
        # estropea la confirmación.
        try:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id is not None:
                await _enviar_resumen_post_apunte(ctx, chat_id)
        except Exception as e:
            log.warning("No pude enviar el resumen tras apunte: %s", e)


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


async def _enviar_resumen_semana(update: Update):
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


async def _enviar_resumen_post_apunte(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Tras apuntar un gasto, manda al chat:
      1) Resumen del mes en curso (total + por categorías + %).
      2) Cronología completa concepto a concepto.

    No depende de `update.message` (estamos respondiendo a un callback) —
    usa `ctx.bot.send_message(chat_id, ...)` directamente.
    """
    hoy = _dt.date.today()
    desde = hoy.replace(day=1)
    try:
        todas = sheets.leer_todos()
    except Exception as e:
        log.warning("Resumen post-apunte: error leyendo Sheet: %s", e)
        return

    # ── 1) Resumen por categoría ──────────────────────────────
    rows_cat = _filtrar(todas, desde, hoy)
    nombre_mes = NOMBRES_MESES[hoy.month].capitalize() + f" {hoy.year}"
    txt_resumen = _formatear_resumen(f"📅 {nombre_mes}", rows_cat)
    await ctx.bot.send_message(
        chat_id, txt_resumen, parse_mode=constants.ParseMode.MARKDOWN
    )

    # ── 2) Cronología detallada ──────────────────────────────
    rows_cron = _filtrar_por_periodo(todas, desde, hoy)
    if not rows_cron:
        return
    rows_ord = sorted(
        rows_cron,
        key=lambda r: (r.get("_fecha") or _dt.date.min,
                       -(r.get("_cantidad") or 0)),
    )
    total = sum(r.get("_cantidad", 0) for r in rows_ord)
    cab = (
        f"🧾 *Cronología {nombre_mes}* — {len(rows_ord)} gastos · "
        f"{fmt_eur(total)}\n"
    )
    bloques: list[str] = []
    actual = cab
    for r in rows_ord:
        fecha = r.get("_fecha")
        ftxt = (fecha.strftime("%d/%m") if isinstance(fecha, _dt.date)
                else str(r.get("fecha", "")))
        concepto = str(r.get("concepto", "")).strip()
        cant = r.get("_cantidad", 0)
        cat = str(r.get("categoria", ""))
        quien_apunta = str(r.get("quien_apunta", ""))
        linea = (
            f"`{ftxt}` {fmt_eur(cant):>9} — {concepto} "
            f"_({cat}, {quien_apunta})_"
        )
        if len(actual) + len(linea) + 1 > 3500:
            bloques.append(actual)
            actual = ""
        actual += "\n" + linea
    if actual.strip():
        bloques.append(actual)
    for b in bloques:
        await ctx.bot.send_message(
            chat_id, b, parse_mode=constants.ParseMode.MARKDOWN
        )


async def _enviar_resumen_mes_actual(update: Update):
    hoy = _dt.date.today()
    desde = hoy.replace(day=1)
    try:
        rows = _filtrar(sheets.leer_todos(), desde, hoy)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    nombre_mes = NOMBRES_MESES[hoy.month].capitalize() + f" {hoy.year}"
    txt = _formatear_resumen(f"📅 {nombre_mes}", rows)
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)


async def _enviar_resumen_mes_de(update: Update, mes: int):
    """Resumen del mes 'mes' (1-12). Usa el año en curso, salvo que ya
    estemos en un mes igual o anterior y no haya datos: cae al año previo."""
    hoy = _dt.date.today()
    año = hoy.year
    desde = _dt.date(año, mes, 1)
    if mes == 12:
        hasta = _dt.date(año, 12, 31)
    else:
        hasta = _dt.date(año, mes + 1, 1) - _dt.timedelta(days=1)
    try:
        rows_all = sheets.leer_todos()
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    rows = _filtrar(rows_all, desde, hasta)
    nombre = NOMBRES_MESES[mes].capitalize() + f" {año}"
    txt = _formatear_resumen(f"📅 {nombre}", rows)
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)


def _filtrar_por_periodo(rows, desde, hasta):
    """Filtra rows por rango de fecha (inclusive). desde/hasta = date."""
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
            r["_fecha"] = f
            out.append(r)
    return out


async def _enviar_lista_chunks(update: Update, titulo: str, rows: list[dict]):
    """Envía un listado detallado de gastos. Trocea en mensajes de hasta
    ~3500 chars para no chocar con el límite de Telegram (4096)."""
    if not rows:
        await update.message.reply_text(f"*{titulo}*\nSin gastos en este periodo.",
                                        parse_mode=constants.ParseMode.MARKDOWN)
        return

    # Ordenar por fecha y luego por cantidad descendente para legibilidad
    rows_ord = sorted(rows, key=lambda r: (r.get("_fecha") or _dt.date.min,
                                            -(r.get("_cantidad") or 0)))
    total = sum(r.get("_cantidad", 0) for r in rows_ord)

    cab = f"*{titulo}* — {len(rows_ord)} gastos · {fmt_eur(total)}\n"
    bloques: list[str] = []
    actual = cab
    for i, r in enumerate(rows_ord, 1):
        fecha = r.get("_fecha")
        ftxt = fecha.strftime("%d/%m") if isinstance(fecha, _dt.date) else str(r.get("fecha", ""))
        concepto = str(r.get("concepto", "")).strip()
        cant = r.get("_cantidad", 0)
        cat = str(r.get("categoria", ""))
        quien = str(r.get("quien_apunta", ""))
        linea = f"`{ftxt}` {fmt_eur(cant):>9} — {concepto} _({cat}, {quien})_"
        # +1 por el \n
        if len(actual) + len(linea) + 1 > 3500:
            bloques.append(actual)
            actual = ""
        actual += "\n" + linea
    if actual.strip():
        bloques.append(actual)

    for b in bloques:
        await update.message.reply_text(b, parse_mode=constants.ParseMode.MARKDOWN)


async def _enviar_lista_mes_de(update: Update, mes: int):
    hoy = _dt.date.today()
    año = hoy.year
    desde = _dt.date(año, mes, 1)
    hasta = (_dt.date(año, 12, 31) if mes == 12
             else _dt.date(año, mes + 1, 1) - _dt.timedelta(days=1))
    try:
        rows = _filtrar_por_periodo(sheets.leer_todos(), desde, hasta)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    titulo = f"📅 {NOMBRES_MESES[mes].capitalize()} {año}"
    await _enviar_lista_chunks(update, titulo, rows)


async def _enviar_lista_mes_actual(update: Update):
    hoy = _dt.date.today()
    await _enviar_lista_mes_de(update, hoy.month)


async def _enviar_lista_semana(update: Update):
    hoy = _dt.date.today()
    desde = hoy - _dt.timedelta(days=6)
    try:
        rows = _filtrar_por_periodo(sheets.leer_todos(), desde, hoy)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    titulo = f"📅 Últimos 7 días ({desde.strftime('%d/%m')} – {hoy.strftime('%d/%m')})"
    await _enviar_lista_chunks(update, titulo, rows)


async def _enviar_lista_todos(update: Update):
    try:
        rows = sheets.leer_todos()
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    out = []
    for r in rows:
        try:
            r["_fecha"] = _dt.date.fromisoformat(str(r.get("fecha", "")))
        except Exception:
            r["_fecha"] = None
        try:
            r["_cantidad"] = float(str(r.get("cantidad", 0)).replace(",", "."))
        except Exception:
            r["_cantidad"] = 0.0
        out.append(r)
    await _enviar_lista_chunks(update, "📋 Todos los gastos", out)


async def _enviar_ultimos(update: Update, n: int = 10):
    try:
        rows = sheets.leer_todos()
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo Sheet: {e}")
        return
    if not rows:
        await update.message.reply_text("Aún no hay gastos.")
        return
    ult = rows[-n:][::-1]
    lineas = [f"*Últimos {len(ult)} gastos*", ""]
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


async def cmd_resumen_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    await _enviar_resumen_semana(update)


async def cmd_resumen_mes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    await _enviar_resumen_mes_actual(update)


async def cmd_ultimos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update):
        return
    await _enviar_ultimos(update)


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


# ─── Gastos fijos (día 1 de cada mes) ────────────────────────────────────────
async def _job_aplicar_gastos_fijos(ctx: ContextTypes.DEFAULT_TYPE):
    """Job de JobQueue que se dispara automáticamente el día 1 a las 09:00
    hora Madrid. Aplica los gastos fijos configurados y manda mensaje a
    todos los usuarios autorizados con el detalle de lo aplicado."""
    try:
        insertados, errores = gastos_fijos.aplicar()
    except Exception as e:
        log.exception("Job gastos fijos falló: %s", e)
        return
    if not insertados and not errores:
        # Nada que reportar (ya aplicados o sin config)
        return
    msg = gastos_fijos.resumen_para_telegram(insertados, errores)
    destinatarios = ALLOWED or set()
    for chat_id in destinatarios:
        try:
            await ctx.bot.send_message(
                chat_id, msg, parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            log.warning("No pude avisar de gastos fijos a %s: %s", chat_id, e)


async def _chequear_gastos_fijos_al_arrancar(app: Application):
    """Al iniciar el bot, si estamos en día >= 1 y los gastos fijos del
    mes en curso NO se han aplicado todavía, se aplican ahora (recupera
    el caso de que el bot estuviera apagado el día 1)."""
    hoy = _dt.date.today()
    if gastos_fijos.ya_aplicado():
        log.info("Gastos fijos del mes %s ya aplicados — skip al arrancar.",
                 hoy.strftime("%Y-%m"))
        return
    try:
        insertados, errores = gastos_fijos.aplicar()
    except Exception as e:
        log.exception("Aplicación al arrancar falló: %s", e)
        return
    if not insertados and not errores:
        return
    msg = "🔄 *Recuperando gastos fijos al arrancar:*\n\n" + \
          gastos_fijos.resumen_para_telegram(insertados, errores)
    for chat_id in (ALLOWED or set()):
        try:
            await app.bot.send_message(
                chat_id, msg, parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            log.warning("No pude avisar al arrancar a %s: %s", chat_id, e)


async def cmd_gastos_fijos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Aplica AHORA los gastos fijos del mes (manualmente). Sirve si el
    bot estaba apagado el día 1 o si los has añadido a media."""
    if not autorizado(update):
        return
    args = [a.lower() for a in (ctx.args or [])]
    forzar = "--force" in args or "--forzar" in args or "force" in args
    config = gastos_fijos.cargar_config()
    if not config:
        await update.message.reply_text(
            "ℹ️ No tienes gastos fijos configurados. Copia "
            "`gastos_fijos_PLANTILLA.json` → `gastos_fijos.json` y edítalo.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    try:
        insertados, errores = gastos_fijos.aplicar(forzar=forzar)
    except Exception as e:
        await update.message.reply_text(f"❌ Error aplicando gastos fijos: {e}")
        return
    if not insertados and not forzar:
        await update.message.reply_text(
            "✅ Ya estaban aplicados los gastos fijos de este mes. "
            "Usa `/gastos_fijos --force` para forzar."
        )
        return
    msg = gastos_fijos.resumen_para_telegram(insertados, errores)
    await update.message.reply_text(msg, parse_mode=constants.ParseMode.MARKDOWN)


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en gastos_bot/.env")
    if not SHEET_ID:
        raise SystemExit("Falta GASTOS_SHEET_ID en gastos_bot/.env")
    if not ALLOWED:
        log.warning("ALLOWED_CHAT_IDS vacío: el bot aceptará a CUALQUIERA. Configúralo.")

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(_chequear_gastos_fijos_al_arrancar)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("categorias", cmd_categorias))
    app.add_handler(CommandHandler("resumen_semana", cmd_resumen_semana))
    app.add_handler(CommandHandler("resumen_mes", cmd_resumen_mes))
    app.add_handler(CommandHandler("ultimos", cmd_ultimos))
    app.add_handler(CommandHandler("borrar", cmd_borrar))
    app.add_handler(CommandHandler("categoria", cmd_categoria))
    app.add_handler(CommandHandler("gastos_fijos", cmd_gastos_fijos))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # ── JobQueue: gastos fijos día 1 a las 09:00 Madrid ─────────────────────
    if app.job_queue is not None:
        hora_local = _dt.time(hour=9, minute=0, tzinfo=TZ_MADRID) \
            if TZ_MADRID else _dt.time(hour=7, minute=0)  # 07 UTC ≈ 09 Madrid
        app.job_queue.run_monthly(
            _job_aplicar_gastos_fijos,
            when=hora_local,
            day=1,
            name="gastos_fijos_mensuales",
        )
        log.info("JobQueue: gastos fijos cada día 1 a las %s.", hora_local)
    else:
        log.warning("JobQueue no disponible: no se aplicarán gastos fijos automáticos. "
                    "Instala 'python-telegram-bot[job-queue]'.")

    log.info("Bot de gastos arrancado. Usuarios autorizados: %s", sorted(ALLOWED) or "TODOS")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
