"""
carga_ultima_sesion.py — Devuelve la carga jugador por jugador de la
última sesión registrada. Script CURADO (sin LLM): el bot_datos lo llama
directo cuando detecta intent del tipo "carga jugador por jugador de la
última sesión" / "borg del último entreno" / "carga de hoy".

Salida tipo:

  📊 Última sesión: 2026-05-14 · turno M · TEC-TAC · 95 min

  Carga por jugador:
    · HERRERO   Borg 7 · 95 min · carga 665
    · CECILIO   Borg 6 · 80 min · carga 480
    · ...

  Estados no entrenables:
    · PANI       L (lesión)
    · BARONA     A (ausencia)

Uso:
  /usr/bin/python3 src/carga_ultima_sesion.py [YYYY-MM-DD]

Sin argumento → última sesión registrada. Con fecha → la sesión de esa
fecha (la primera del día si hay doble).
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
ESTADOS_NO_ENTRENABLES = {
    "L": "lesión", "A": "ausencia", "D": "descanso",
    "N": "no entrena", "S": "selección", "NC": "no calificado",
    "NJ": "no juega",
}


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _iso(v):
    if isinstance(v, (int, float)) and 1 < v < 60000:
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).date().isoformat()
    if isinstance(v, str) and len(v) >= 10:
        return v[:10]
    return ""


def main():
    fecha_arg = sys.argv[1] if len(sys.argv) > 1 else None

    ss = conectar()
    ses = pd.DataFrame(ss.worksheet("SESIONES").get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted))
    borg = pd.DataFrame(ss.worksheet("BORG").get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted))

    if ses.empty:
        print("⚠️ No hay sesiones registradas.")
        return

    ses["FECHA_ISO"] = ses["FECHA"].apply(_iso)
    ses = ses[ses["FECHA_ISO"] != ""]

    # Filtrar fecha
    if fecha_arg:
        fecha_obj = fecha_arg
        ses_f = ses[ses["FECHA_ISO"] == fecha_obj]
        if ses_f.empty:
            print(f"⚠️ No hay sesión registrada para {fecha_obj}.")
            return
    else:
        # Última sesión = última fecha (no necesariamente hoy)
        fecha_obj = ses["FECHA_ISO"].max()
        ses_f = ses[ses["FECHA_ISO"] == fecha_obj]

    # Si hay doble sesión, tomar la primera (M, sino la primera del df)
    if len(ses_f) > 1:
        turnos = ses_f["TURNO"].astype(str).str.upper().tolist()
        if "M" in turnos:
            ses_data = ses_f[ses_f["TURNO"].astype(str).str.upper() == "M"].iloc[0]
        else:
            ses_data = ses_f.iloc[0]
    else:
        ses_data = ses_f.iloc[0]

    turno = str(ses_data.get("TURNO", "")).strip().upper()
    tipo = str(ses_data.get("TIPO_SESION", "")).strip()
    minutos_ses = ses_data.get("MINUTOS", "")
    try:
        minutos_ses = int(float(minutos_ses)) if str(minutos_ses).strip() else 0
    except (ValueError, TypeError):
        minutos_ses = 0
    competicion = str(ses_data.get("COMPETICION", "")).strip()

    # Cabecera
    cab = f"📊 *Última sesión: {fecha_obj}* · turno *{turno}*"
    if tipo:
        cab += f" · {tipo}"
    if minutos_ses:
        cab += f" · {minutos_ses} min"
    if competicion:
        cab += f" · {competicion}"
    print(cab)
    print()

    # Filas de BORG para esta fecha + turno
    if "FECHA" in borg.columns:
        borg["FECHA_ISO"] = borg["FECHA"].apply(_iso)
        b_f = borg[(borg["FECHA_ISO"] == fecha_obj) &
                   (borg["TURNO"].astype(str).str.upper() == turno)].copy()
    else:
        b_f = pd.DataFrame()

    if b_f.empty:
        print("_No hay datos de Borg registrados para esta sesión todavía._")
        return

    # Separar numéricos (entrenaron) vs letras (estados)
    b_f["BORG_NUM"] = pd.to_numeric(b_f["BORG"], errors="coerce")
    entrenaron = b_f[b_f["BORG_NUM"].notna()].copy()
    estados = b_f[b_f["BORG_NUM"].isna()].copy()

    if not entrenaron.empty:
        entrenaron["CARGA"] = entrenaron["BORG_NUM"] * minutos_ses
        entrenaron = entrenaron.sort_values("CARGA", ascending=False)
        print("*Carga por jugador (Borg × minutos):*")
        for _, r in entrenaron.iterrows():
            jug = str(r["JUGADOR"]).strip()
            borg_val = int(r["BORG_NUM"])
            carga = int(r["CARGA"])
            incidencia = str(r.get("INCIDENCIA", "") or "").strip()
            extra = f"  ⚠ _{incidencia}_" if incidencia else ""
            print(f"  · *{jug:<10}*  Borg {borg_val} · {minutos_ses} min · carga *{carga}*{extra}")
        # Estadística rápida
        media = entrenaron["BORG_NUM"].mean()
        total_jugadores = len(entrenaron)
        print()
        print(f"_Total: {total_jugadores} jugadores · Borg medio: {media:.1f}_")

    if not estados.empty:
        print()
        print("*Estados no entrenables:*")
        for _, r in estados.iterrows():
            jug = str(r["JUGADOR"]).strip()
            estado = str(r["BORG"]).strip().upper()
            etiqueta = ESTADOS_NO_ENTRENABLES.get(estado, estado)
            incidencia = str(r.get("INCIDENCIA", "") or "").strip()
            extra = f"  ⚠ _{incidencia}_" if incidencia else ""
            print(f"  · *{jug:<10}* — {estado} ({etiqueta}){extra}")


if __name__ == "__main__":
    main()
