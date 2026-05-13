"""
enlaces_wa.py — Igual que enlaces_hoy.py, pero genera enlaces wa.me
listos para tocar y enviar por WhatsApp a cada jugador.

Uso:
  /usr/bin/python3 src/enlaces_wa.py [YYYY-MM-DD] [JUGADOR]

Sin argumentos usa la fecha de hoy y todos los jugadores con teléfono.
Si pasas un JUGADOR (p.ej. HERRERO), solo genera el suyo. Si pasas una
fecha (YYYY-MM-DD), usa esa fecha en vez de hoy. Los argumentos pueden
ir en cualquier orden.

Devuelve al stdout un texto con bloque por jugador, cada bloque con UN
enlace `https://wa.me/<tel>?text=...` que al pulsarlo abre WhatsApp con
el chat del jugador y el mensaje prerredactado conteniendo los Forms
PRE + POST.

Lee teléfonos de la hoja `TELEFONOS_JUGADORES` (columnas: dorsal, jugador,
telefono, usar_whatsapp, notas). Si un jugador no tiene teléfono o tiene
usar_whatsapp=FALSE, se omite y se avisa al final.

Formato de salida (mismos `---MSG---` que enlaces_hoy.py para que el bot
los parsee igual):

  ---MSG---
  🗓 Sesiones del 2026-05-13 ...
  ---MSG---
  📌 Sesión 1/1 · turno M · 🧠 Incluye wellness
  ---MSG---
  *#1 HERRERO*
  📲 Enviar por WhatsApp: https://wa.me/34xxx?text=...

  *#2 CECILIO*
  📲 Enviar por WhatsApp: https://wa.me/34xxx?text=...
  ---MSG---
  ✅ Listo. Pulsa cada enlace, se abrirá WhatsApp con el chat y mensaje
     preparados. Solo te falta darle a "Enviar".
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))
import forms_utils as fu  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MSG_SEP = "---MSG---"


def _normaliza_telefono(t: str) -> str | None:
    """Acepta formatos varios y devuelve solo dígitos con prefijo internacional.
    - "612345678"        → "34612345678"
    - "+34 612 345 678"  → "34612345678"
    - "34 612345678"     → "34612345678"
    - "0034 612345678"   → "34612345678"  (limpia el prefijo 00)
    - "+351 912345678"   → "351912345678" (otros países)
    Si tiene <9 dígitos o queda vacío, devuelve None.
    """
    if not t:
        return None
    d = "".join(c for c in str(t) if c.isdigit())
    if not d:
        return None
    # Limpiar prefijo internacional "00" → solo dígitos del país
    if d.startswith("00"):
        d = d[2:]
    # Si empieza por 6/7/8/9 y tiene 9 dígitos → móvil español sin prefijo
    if len(d) == 9 and d[0] in "6789":
        d = "34" + d
    if len(d) < 11:
        return None
    return d


def _msg_para_jugador(nombre: str, fecha: str, turno: str, incluir_wellness: bool, doble: bool) -> str:
    """Texto del mensaje que va dentro del wa.me?text=... (sin URL-encode)."""
    pre = fu.enlace_pre(nombre, fecha, turno, incluir_wellness=incluir_wellness)
    post = fu.enlace_post(nombre, fecha, turno)
    bloque_wellness = "" if incluir_wellness else "\n_Esta es la 2ª sesión del día: salta las preguntas de wellness en el PRE._"
    msg = (
        f"¡Hola {nombre}! 👋\n"
        f"Estos son tus enlaces de hoy ({fecha} · turno {turno}):\n\n"
        f"⏪ ANTES del entreno (peso PRE + wellness):\n{pre}\n\n"
        f"⏩ DESPUÉS del entreno (peso POST + Borg):\n{post}"
        f"{bloque_wellness}\n\n"
        f"¡Gracias! 💪"
    )
    return msg


def main():
    # Parseo flexible: cualquier arg con guiones largo lo asumo fecha; el resto, jugador.
    fecha_obj: str | None = None
    filtro_jugador: str | None = None
    for a in sys.argv[1:]:
        if not a:
            continue
        if len(a) == 10 and a[4] == "-" and a[7] == "-":
            fecha_obj = a
        else:
            filtro_jugador = a.strip().upper()
    if not fecha_obj:
        fecha_obj = date.today().isoformat()

    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    ss = gspread.authorize(creds).open(SHEET_NAME)

    # ── Sesiones de hoy ──
    ses_ws = ss.worksheet("SESIONES")
    ses_rows = ses_ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted
    )

    def _iso(v):
        if isinstance(v, (int, float)) and 1 <= v <= 60000:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).date().isoformat()
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
        return ""

    ses_hoy = [s for s in ses_rows if _iso(s.get("FECHA")) == fecha_obj]
    if not ses_hoy:
        print(MSG_SEP)
        print(f"📭 No hay sesiones registradas en SESIONES para {fecha_obj}.")
        return

    def _turno_orden(s):
        return 0 if str(s.get("TURNO", "")).upper().startswith("M") else 1
    ses_hoy.sort(key=_turno_orden)
    doble = len(ses_hoy) > 1

    # ── Leer hoja TELEFONOS_JUGADORES ──
    try:
        tel_ws = ss.worksheet("TELEFONOS_JUGADORES")
        tel_rows = tel_ws.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        print(MSG_SEP)
        print(
            "❌ Falta la hoja `TELEFONOS_JUGADORES` en el Sheet.\n\n"
            "Crea una con columnas: dorsal · jugador · telefono · usar_whatsapp · notas\n"
            "Y rellena el teléfono de cada jugador (con o sin prefijo +34)."
        )
        return

    # Mapa jugador → (telefono_normalizado, activo_wa)
    info = {}
    sin_tel = []
    inactivos = []
    for r in tel_rows:
        nombre = str(r.get("jugador", "")).strip().upper()
        if not nombre:
            continue
        tel_raw = str(r.get("telefono", "")).strip()
        usar = str(r.get("usar_whatsapp", "TRUE")).strip().upper()
        tel = _normaliza_telefono(tel_raw)
        if usar in ("FALSE", "NO", "0"):
            inactivos.append(nombre)
            continue
        if not tel:
            sin_tel.append(nombre)
            continue
        info[nombre] = (tel, r.get("dorsal", ""))

    if not info:
        print(MSG_SEP)
        avisos = []
        if sin_tel:
            avisos.append(f"Sin teléfono: {', '.join(sin_tel)}")
        if inactivos:
            avisos.append(f"Marcados FALSE: {', '.join(inactivos)}")
        avisos_txt = "\n".join(avisos) if avisos else "(hoja vacía o todos sin datos)"
        print(
            "❌ No hay ningún jugador con teléfono configurado.\n\n"
            f"{avisos_txt}\n\n"
            "Rellena la columna `telefono` en la hoja TELEFONOS_JUGADORES y vuelve a lanzar."
        )
        return

    # Lista de jugadores ordenada por dorsal numérico (los que tengan tel)
    def _ord_dorsal(j):
        d = info[j][1]
        try: return int(d)
        except (TypeError, ValueError): return 999
    jugadores = sorted(info.keys(), key=_ord_dorsal)

    # Si llega filtro_jugador, reducir a uno.
    if filtro_jugador:
        # Búsqueda flexible: case insensitive, contains
        coincidencias = [j for j in jugadores if filtro_jugador in j.upper()]
        if not coincidencias:
            print(MSG_SEP)
            print(
                f"❌ No encuentro a *{filtro_jugador}* con teléfono configurado "
                f"en TELEFONOS_JUGADORES.\n\n"
                f"Jugadores con teléfono: {', '.join(jugadores) if jugadores else '(ninguno)'}"
            )
            return
        if len(coincidencias) > 1:
            print(MSG_SEP)
            print(
                f"⚠️ *{filtro_jugador}* coincide con varios: {', '.join(coincidencias)}.\n"
                f"Sé más específico."
            )
            return
        jugadores = coincidencias

    # ── Cabecera ──
    print(MSG_SEP)
    aviso_doble = "\n⚠️ Doble sesión: el wellness solo en la 1ª." if doble else ""
    print(
        f"📲 *Enlaces WhatsApp · {fecha_obj}*\n"
        f"Sesiones: *{len(ses_hoy)}* · Jugadores con teléfono: *{len(jugadores)}*"
        f"{aviso_doble}\n\n"
        "Pulsa cada enlace de abajo y dale a *Enviar* en WhatsApp."
    )

    # ── Por cada sesión, bloque ──
    for idx, ses in enumerate(ses_hoy):
        turno = str(ses.get("TURNO", "")).strip() or ("M" if idx == 0 else "T")
        es_primera = (idx == 0)
        incluir_wellness = (es_primera or not doble)

        wellness_flag = "🧠 Incluye wellness" if incluir_wellness else "🚫 Sin wellness (2ª sesión del día)"
        print(MSG_SEP)
        print(f"📌 *Sesión {idx+1}/{len(ses_hoy)}* · turno {turno}\n{wellness_flag}")

        bloques = []
        for j in jugadores:
            tel, dorsal = info[j]
            msg = _msg_para_jugador(j, fecha_obj, turno, incluir_wellness, doble)
            wa_link = f"https://wa.me/{tel}?text={quote(msg, safe='')}"
            etiq_dorsal = f"#{dorsal} " if dorsal else ""
            bloques.append(f"*{etiq_dorsal}{j}*\n📲 {wa_link}")

        # Empaquetar en mensajes ≤3800 chars
        buffer = ""
        for b in bloques:
            if len(buffer) + len(b) + 2 > 3800:
                print(MSG_SEP)
                print(buffer)
                buffer = b
            else:
                buffer = (buffer + "\n\n" + b) if buffer else b
        if buffer:
            print(MSG_SEP)
            print(buffer)

    # ── Avisos finales ──
    if sin_tel or inactivos:
        print(MSG_SEP)
        avs = []
        if sin_tel:
            avs.append(f"⚠ Sin teléfono en la hoja: *{', '.join(sin_tel)}*")
        if inactivos:
            avs.append(f"ℹ Marcados como usar_whatsapp=FALSE: *{', '.join(inactivos)}*")
        print("\n".join(avs) + "\n\nRellena/activa en la hoja TELEFONOS_JUGADORES si quieres incluirlos.")

    print(MSG_SEP)
    print(
        "✅ Listo. Cada enlace abre WhatsApp con el chat del jugador y el "
        "mensaje preparado. Solo te falta darle a *Enviar*.\n\n"
        "_Cuando respondan, lanza `/consolidar` para integrar al Sheet._"
    )


if __name__ == "__main__":
    main()
