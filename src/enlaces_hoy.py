"""
enlaces_hoy.py — Genera los enlaces pre-rellenados de los Forms PRE/POST
para cada jugador y las sesiones del día actual.

Uso:
  /usr/bin/python3 src/enlaces_hoy.py [YYYY-MM-DD]

Sin argumentos usa la fecha de hoy. Imprime al stdout un texto listo para
reenviar a Telegram, estructurado así:

  ### 2026-04-24 · 1 sesión ###
  ---MSG---
  📌 Sesión 1/1 · turno T · incluye wellness
  ---MSG---
  *CARLOS*
  PRE:  https://...
  POST: https://...

  *BARONA*
  PRE:  ...
  POST: ...
  ---MSG---
  (siguiente bloque)

El bot de Telegram parsea ---MSG--- y envía cada bloque como mensaje aparte.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date, datetime
from pathlib import Path

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


def main():
    # Fecha objetivo
    fecha_obj = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    ss = gspread.authorize(creds).open(SHEET_NAME)

    # Leer SESIONES
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
        print(f"📭 No hay sesiones registradas en SESIONES para {fecha_obj}.\n"
              f"Añade la sesión en el Sheet y vuelve a lanzar /enlaces_hoy.")
        return

    # Ordenar M → T
    def _turno_orden(s):
        return 0 if str(s.get("TURNO", "")).upper().startswith("M") else 1
    ses_hoy.sort(key=_turno_orden)
    doble = len(ses_hoy) > 1

    # Lista de jugadores (del desplegable del Form PRE, vía Sheet BORG)
    # Mejor: leer del desplegable real del Form para coherencia.
    # Usamos fallback: jugadores únicos de BORG ordenados alfabéticamente.
    try:
        borg_ws = ss.worksheet("BORG")
        borg_rows = borg_ws.get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        )
        jugadores = sorted({str(r.get("JUGADOR", "")).strip()
                            for r in borg_rows if str(r.get("JUGADOR", "")).strip()})
    except Exception:
        jugadores = []
    # Excluir entradas raras
    jugadores = [j for j in jugadores if j and not j.startswith("JUG ") and len(j) > 1]

    # Mensaje de cabecera
    print(MSG_SEP)
    aviso_doble = "\n⚠️ Doble sesión: el wellness solo en la 1ª." if doble else ""
    print(f"🗓 Sesiones de {fecha_obj}: *{len(ses_hoy)}*{aviso_doble}")

    # Por cada sesión, imprimir cabecera + bloques de jugadores
    for idx, ses in enumerate(ses_hoy):
        turno = str(ses.get("TURNO", "")).strip() or ("M" if idx == 0 else "T")
        es_primera = (idx == 0)
        incluir_wellness = (es_primera or not doble)

        wellness_flag = "🧠 Incluye wellness" if incluir_wellness else "🚫 Sin wellness (2ª sesión del día)"
        print(MSG_SEP)
        print(f"📌 *Sesión {idx+1}/{len(ses_hoy)}* · turno {turno}\n{wellness_flag}")

        # Construir bloques de jugadores y agruparlos por tamaño
        bloques = []
        for j in jugadores:
            pre = fu.enlace_pre(j, fecha_obj, turno, incluir_wellness=incluir_wellness)
            post = fu.enlace_post(j, fecha_obj, turno)
            bloques.append(f"*{j}*\nPRE:  {pre}\nPOST: {post}")

        # Empaquetar en mensajes de ~3800 chars
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

    print(MSG_SEP)
    print(
        "✅ Listo. Copia el par PRE+POST de cada jugador y pégalo en su WhatsApp.\n\n"
        "Cuando los jugadores respondan, lanza `/consolidar` para integrar al Sheet."
    )


if __name__ == "__main__":
    main()
