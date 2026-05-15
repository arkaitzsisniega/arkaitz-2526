"""
recuento_jugador.py — Recuento detallado de UN jugador. Script
CURADO (sin LLM): el bot lo llama directo cuando detecta preguntas tipo:
  - "cuántas sesiones lleva Pirata esta temporada"
  - "cuál es la participación de Raya"
  - "asistencia de Carlos"

Devuelve desglose de:
  - Sesiones del equipo en total.
  - Sesiones con datos del jugador (entrenó/asistió de alguna forma).
  - Estados (S/A/L/N/D/NC/NJ).
  - Retiradas a mitad sesión.
  - % participación.
  - Comparativa con la media del equipo.

Uso:
  /usr/bin/python3 src/recuento_jugador.py NOMBRE

Lee de `_VISTA_RECUENTO`.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))
from aliases_jugadores import norm_jugador, ROSTER_CANONICO  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def main():
    args = sys.argv[1:]
    if not args:
        print("Uso: recuento_jugador.py NOMBRE")
        print(f"Jugadores: {', '.join(sorted(ROSTER_CANONICO))}")
        return

    nombre = norm_jugador(args[0])
    if not nombre:
        print(f"❌ Jugador desconocido: {args[0]!r}")
        return

    ss = conectar()
    try:
        df = pd.DataFrame(ss.worksheet("_VISTA_RECUENTO").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted))
    except Exception as e:
        print(f"❌ Error leyendo _VISTA_RECUENTO: {e}")
        return

    if df.empty or "JUGADOR" not in df.columns:
        print("⚠️ `_VISTA_RECUENTO` vacía o sin columna JUGADOR.")
        return

    # Fila del jugador
    fila = df[df["JUGADOR"].astype(str).str.upper() == nombre.upper()]
    if fila.empty:
        print(f"📊 *{nombre}* no aparece en `_VISTA_RECUENTO`.")
        return

    r = fila.iloc[0]
    total_eq = int(r.get("TOTAL_SESIONES_EQUIPO", 0) or 0)
    con_datos = int(r.get("SESIONES_CON_DATOS", 0) or 0)
    pct = r.get("PCT_PARTICIPACION", "")

    # Estados (las columnas EST_X cuentan veces que aparece ese estado)
    estados = {
        "Entrenó (Borg numérico)": int(r.get("EST_N_NUM", 0) or 0) if "EST_N_NUM" in r else None,
        "S (Selección)": int(r.get("EST_S", 0) or 0),
        "A (Ausencia)": int(r.get("EST_A", 0) or 0),
        "L (Lesionado)": int(r.get("EST_L", 0) or 0),
        "N (No entrena)": int(r.get("EST_N", 0) or 0),
        "D (Descanso)": int(r.get("EST_D", 0) or 0),
        "NC (No calificado)": int(r.get("EST_NC", 0) or 0),
        "NJ (No juega convocado)": int(r.get("EST_NJ", 0) or 0),
    }
    retiradas = int(r.get("RETIRADAS", 0) or 0)

    # ── Output ──
    print(f"📊 *Recuento {nombre}*")
    print()
    print(f"  Total sesiones del equipo: *{total_eq}*")
    print(f"  Sesiones con datos suyos:  *{con_datos}*")
    if pct not in ("", None):
        try:
            pct_f = float(str(pct).replace(",", "."))
            emoji = "🟢" if pct_f >= 80 else "🟡" if pct_f >= 60 else "🔴"
            print(f"  Participación: {emoji} *{pct_f:.0f}%*")
        except (ValueError, TypeError):
            print(f"  Participación: {pct}")

    # Desglose estados (los que tengan valor > 0 o sean None)
    print()
    print("*Desglose de estados:*")
    for nombre_est, val in estados.items():
        if val is None:
            continue
        if val > 0:
            print(f"  · {nombre_est}: {val}")
    if retiradas > 0:
        print(f"  · Retiradas a mitad sesión: {retiradas}")

    # Comparativa con media equipo (solo si hay >=5 jugadores)
    if len(df) >= 5:
        df["_pct"] = pd.to_numeric(df.get("PCT_PARTICIPACION"),
                                       errors="coerce")
        media = df["_pct"].mean()
        if not pd.isna(media):
            try:
                pct_f = float(str(pct).replace(",", "."))
                diff = pct_f - media
                if abs(diff) >= 5:
                    print()
                    if diff > 0:
                        print(f"  ↑ {diff:+.0f}% sobre la media del equipo "
                              f"({media:.0f}%).")
                    else:
                        print(f"  ↓ {diff:+.0f}% por debajo de la media del equipo "
                              f"({media:.0f}%).")
            except (ValueError, TypeError):
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error inesperado: {type(e).__name__}: {e}")
        sys.exit(1)
