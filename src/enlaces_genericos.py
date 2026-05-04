"""
enlaces_genericos.py — Devuelve los enlaces del Form PRE/POST con FECHA y
TURNO ya pre-rellenados. Pensado para enviar al grupo de WhatsApp del
equipo: el jugador SOLO tiene que elegir su nombre, fecha y turno ya
están puestos.

Uso:
  /usr/bin/python3 src/enlaces_genericos.py            # hoy + turno auto
  /usr/bin/python3 src/enlaces_genericos.py 2026-05-04 # fecha específica
  /usr/bin/python3 src/enlaces_genericos.py --crudo    # 100% genéricos

Comportamiento por defecto (sin args):
  - Lee SESIONES del Sheet y detecta los turnos del día.
  - Si hay 1 sesión: 1 par PRE+POST con fecha + turno reales.
  - Si hay 2 sesiones (doble): 2 pares (M y T), el PRE de la 2ª SIN
    wellness para evitar duplicados.
  - Si no hay sesiones registradas: usa fecha de hoy + turno M (mañana)
    como heurística sensata, y avisa.

Modo --crudo: enlaces sin pre-rellenado (jugador y fecha/turno los
elige el jugador en cada Form). Útil para mandar al principio de la
temporada y reusar.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

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


def _iso_date(v) -> str:
    """Convierte serial de Google Sheets o string a YYYY-MM-DD."""
    if isinstance(v, (int, float)) and 1 <= v <= 60000:
        import pandas as pd
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).date().isoformat()
    if isinstance(v, str) and len(v) >= 10:
        return v[:10]
    return ""


def _detectar_sesiones_dia(fecha_obj: str) -> list[dict]:
    """Lee SESIONES y devuelve las del día, ordenadas M → T → P."""
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    try:
        ss = gspread.authorize(creds).open(SHEET_NAME)
        ws = ss.worksheet("SESIONES")
        rows = ws.get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        )
    except Exception:
        return []
    ses_hoy = [s for s in rows if _iso_date(s.get("FECHA")) == fecha_obj]

    def _orden(s):
        t = str(s.get("TURNO", "")).upper().strip()
        return {"M": 0, "T": 1, "P": 2}.get(t[:1] if t else "", 1)
    ses_hoy.sort(key=_orden)
    return ses_hoy


def _print_par_enlaces(fecha: str, turno: str, incluir_wellness: bool,
                         contexto: str):
    pre_url = fu.enlace_pre("", fecha, turno, incluir_wellness=incluir_wellness)
    post_url = fu.enlace_post("", fecha, turno)
    wellness_flag = ("🧠 Incluye wellness" if incluir_wellness
                       else "🚫 Sin wellness (2ª sesión del día)")
    print(MSG_SEP)
    print(f"📌 *{contexto}* · turno {turno}\n{wellness_flag}\n\n"
          f"🟦 *ANTES del entreno* (peso PRE"
          f"{' + wellness' if incluir_wellness else ''}):\n{pre_url}\n\n"
          f"🟥 *DESPUÉS del entreno* (peso POST + Borg):\n{post_url}")


def main():
    # Modo crudo: enlaces 100% genéricos (sin fecha ni turno)
    if "--crudo" in sys.argv:
        cfg = fu.load_config()
        pre_url = f"https://docs.google.com/forms/d/e/{cfg['pre']['form_id']}/viewform"
        post_url = f"https://docs.google.com/forms/d/e/{cfg['post']['form_id']}/viewform"
        print(MSG_SEP)
        print("📋 *Enlaces genéricos del Form*\n\n"
              "El jugador elige su nombre, fecha y turno en cada Form.")
        print(MSG_SEP)
        print(f"🟦 *ANTES del entreno*:\n{pre_url}")
        print(MSG_SEP)
        print(f"🟥 *DESPUÉS del entreno*:\n{post_url}")
        return

    # Determinar fecha
    args_fecha = [a for a in sys.argv[1:] if not a.startswith("--")]
    fecha = args_fecha[0] if args_fecha else date.today().isoformat()

    # Detectar sesiones del día
    sesiones = _detectar_sesiones_dia(fecha)

    if not sesiones:
        # No hay sesiones → heurística: turno M, con wellness
        print(MSG_SEP)
        print(f"📋 *Enlaces del Form para {fecha}*\n\n"
              f"⚠️ No encuentro sesiones registradas para esta fecha en "
              f"SESIONES. Genero los enlaces con turno *M* (mañana) y "
              f"wellness incluido. Si la sesión es por la tarde, añade "
              f"primero la sesión al Sheet y vuelve a lanzar /enlaces.")
        _print_par_enlaces(fecha, "M", incluir_wellness=True,
                              contexto=f"Sesión de {fecha}")
        print(MSG_SEP)
        print("ℹ️ El jugador SOLO tiene que elegir su nombre del "
              "desplegable. Fecha y turno ya están pre-rellenados.")
        return

    # 1 o 2 sesiones detectadas
    doble = len(sesiones) > 1
    aviso = "\n⚠️ Doble sesión: el wellness solo en la 1ª." if doble else ""
    print(MSG_SEP)
    print(f"🗓 Enlaces del Form para *{fecha}*: "
          f"{len(sesiones)} sesión(es){aviso}")

    for idx, ses in enumerate(sesiones):
        turno = str(ses.get("TURNO", "")).strip() or ("M" if idx == 0 else "T")
        es_primera = (idx == 0)
        incluir_wellness = (es_primera or not doble)
        contexto = (f"Sesión {idx+1}/{len(sesiones)} de {fecha}"
                    if doble else f"Sesión de {fecha}")
        _print_par_enlaces(fecha, turno, incluir_wellness, contexto)

    print(MSG_SEP)
    print("ℹ️ El jugador SOLO tiene que elegir su nombre del desplegable. "
          "Fecha y turno ya están pre-rellenados.")


if __name__ == "__main__":
    main()
