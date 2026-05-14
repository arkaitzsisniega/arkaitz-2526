"""
carga_ultima_sesion.py — Devuelve la carga jugador por jugador de la
última sesión registrada, cruzando TODAS las métricas: Borg, minutos
reales (de EST_PARTIDOS si es partido), multiplicador GYM/MIXTA y, si
hay, datos Oliver (distancia, HSR, sprints).

Script CURADO (sin LLM): el bot_datos y Alfred lo llaman directo cuando
detectan intent del tipo "carga jugador por jugador de la última sesión"
/ "borg del último entreno" / "carga del entreno de hoy".

Fuentes:
- `_VISTA_CARGA` → ya cruza Borg con minutos REALES por jugador (no
  los minutos generales de SESIONES) y aplica los multiplicadores
  GYM (×1.25) o GYM+TEC-TAC (mixta).
- `_VISTA_OLIVER` → si hay Oliver para esa fecha, mostramos distancia,
  HSR, sprints y aceleraciones por jugador.
- `BORG` → solo para detectar estados no numéricos (L/A/D/S/N/NC/NJ)
  y la columna INCIDENCIA de los retirados.

Salida:

  📊 Última sesión: 2026-05-14 · turno M · TEC-TAC · COMPETICION
     (minutos generales: 95 min)

  *Carga por jugador (Borg × Minutos REALES × mult. GYM):*
    · CECILIO   Borg 7 · 92 min · carga 644
    · ...

  *Métricas Oliver (si disponibles):*
    · CECILIO  dist 5430m · HSR 320m · sprints 4
    · ...

  *Estados no entrenables:* PANI (L), BARONA (A)…

Uso:
  /usr/bin/python3 src/carga_ultima_sesion.py [YYYY-MM-DD]
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


def _leer(ss, hoja):
    try:
        return pd.DataFrame(ss.worksheet(hoja).get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted))
    except Exception:
        return pd.DataFrame()


def main():
    fecha_arg = sys.argv[1] if len(sys.argv) > 1 else None

    ss = conectar()
    ses = _leer(ss, "SESIONES")
    vista_carga = _leer(ss, "_VISTA_CARGA")
    vista_oliver = _leer(ss, "_VISTA_OLIVER")
    borg = _leer(ss, "BORG")

    if ses.empty:
        print("⚠️ No hay sesiones registradas.")
        return

    ses["FECHA_ISO"] = ses["FECHA"].apply(_iso)
    ses = ses[ses["FECHA_ISO"] != ""]

    # ── Determinar la sesión objetivo ──
    if fecha_arg:
        fecha_obj = fecha_arg
        ses_f = ses[ses["FECHA_ISO"] == fecha_obj]
        if ses_f.empty:
            print(f"⚠️ No hay sesión registrada para {fecha_obj}.")
            return
    else:
        fecha_obj = ses["FECHA_ISO"].max()
        ses_f = ses[ses["FECHA_ISO"] == fecha_obj]

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

    cab = f"📊 *Última sesión: {fecha_obj}* · turno *{turno}*"
    if tipo:
        cab += f" · {tipo}"
    if competicion:
        cab += f" · {competicion}"
    if minutos_ses:
        cab += f"\n_(minutos generales: {minutos_ses} min — los individuales pueden variar)_"
    print(cab)
    print()

    # ── Carga real: usar _VISTA_CARGA ──
    # _VISTA_CARGA ya tiene CARGA calculada con minutos REALES por
    # jugador (cruza con EST_PARTIDOS si es partido) y multiplicador
    # GYM 1.25 si aplica.
    if not vista_carga.empty and "FECHA" in vista_carga.columns:
        vista_carga["FECHA_ISO"] = vista_carga["FECHA"].apply(_iso)
        vc_f = vista_carga[
            (vista_carga["FECHA_ISO"] == fecha_obj) &
            (vista_carga["TURNO"].astype(str).str.upper() == turno)
        ].copy()
    else:
        vc_f = pd.DataFrame()

    if not vc_f.empty:
        for c in ("BORG", "MINUTOS", "CARGA"):
            if c in vc_f.columns:
                vc_f[c] = pd.to_numeric(vc_f[c], errors="coerce")
        vc_f = vc_f.dropna(subset=["CARGA"]).copy()
        vc_f = vc_f.sort_values("CARGA", ascending=False)

        print("*Carga por jugador (Borg × Minutos REALES + mult. GYM/MIXTA):*")
        for _, r in vc_f.iterrows():
            jug = str(r["JUGADOR"]).strip()
            borg_v = r.get("BORG", 0)
            min_v = r.get("MINUTOS", 0)
            carga = r.get("CARGA", 0)
            try:
                borg_s = f"{int(borg_v)}" if pd.notna(borg_v) else "—"
            except: borg_s = "—"
            try:
                min_s = f"{int(min_v)}" if pd.notna(min_v) else "—"
            except: min_s = "—"
            try:
                carga_s = f"{int(round(carga))}"
            except: carga_s = "—"
            print(f"  · *{jug:<10}*  Borg {borg_s} · {min_s} min · carga *{carga_s}*")
        # Estadística rápida
        media_b = vc_f["BORG"].mean()
        media_c = vc_f["CARGA"].mean()
        print()
        print(f"_Total: {len(vc_f)} jugadores · Borg medio: {media_b:.1f} · "
              f"Carga media: {int(round(media_c))}_")
    else:
        # Fallback: leer BORG crudo (sin minutos reales)
        if not borg.empty and "FECHA" in borg.columns:
            borg["FECHA_ISO"] = borg["FECHA"].apply(_iso)
            b_f = borg[(borg["FECHA_ISO"] == fecha_obj) &
                       (borg["TURNO"].astype(str).str.upper() == turno)].copy()
            b_f["BORG_NUM"] = pd.to_numeric(b_f["BORG"], errors="coerce")
            entrenaron = b_f[b_f["BORG_NUM"].notna()].copy()
            if not entrenaron.empty:
                print("_⚠️ Sin _VISTA_CARGA actualizada todavía. Mostrando Borg crudo:_")
                print()
                entrenaron = entrenaron.sort_values("BORG_NUM", ascending=False)
                for _, r in entrenaron.iterrows():
                    jug = str(r["JUGADOR"]).strip()
                    borg_v = int(r["BORG_NUM"])
                    print(f"  · *{jug:<10}*  Borg {borg_v}")
                print()
                print("_Para ver carga real con minutos cruzados, lanza /consolidar._")

    # ── Métricas Oliver (si las hay) ──
    # Mostramos solo las métricas COMPUESTAS útiles (oliver_load y
    # acwr_mecanico): la distancia cruda de _VISTA_OLIVER viene con
    # unidades raras (datos de la API Oliver con escala no documentada),
    # así que evitamos confundir al user con números que no representan
    # metros reales.
    if not vista_oliver.empty and "FECHA" in vista_oliver.columns:
        vista_oliver["FECHA_ISO"] = vista_oliver["FECHA"].apply(_iso)
        vo_f = vista_oliver[vista_oliver["FECHA_ISO"] == fecha_obj].copy()
        if not vo_f.empty:
            for c in ("oliver_load", "acwr_mecanico", "oliver_load_ewma_ag",
                       "oliver_load_ewma_cr", "ratio_borg_oliver"):
                if c in vo_f.columns:
                    vo_f[c] = pd.to_numeric(vo_f[c], errors="coerce")
            vo_useful = vo_f[vo_f.get("oliver_load", pd.Series(dtype=float)).notna()]
            if not vo_useful.empty:
                print()
                print("*Métricas Oliver (carga mecánica):*")
                vo_useful = vo_useful.sort_values("oliver_load", ascending=False)
                for _, r in vo_useful.iterrows():
                    jug = str(r["JUGADOR"]).strip()
                    load = r.get("oliver_load", None)
                    acwr_m = r.get("acwr_mecanico", None)
                    ratio = r.get("ratio_borg_oliver", None)
                    trozos = []
                    if pd.notna(load):
                        trozos.append(f"load *{int(load)}*")
                    if pd.notna(acwr_m):
                        sem = ("🔴" if acwr_m > 1.5 else "🟡" if acwr_m > 1.3 else
                               "🟢" if acwr_m >= 0.8 else "🔵")
                        trozos.append(f"ACWR-mec {sem} {acwr_m:.2f}")
                    if pd.notna(ratio):
                        trozos.append(f"Borg/Oliver {ratio:.2f}")
                    if trozos:
                        print(f"  · *{jug:<10}*  " + " · ".join(trozos))

    # ── Estados no entrenables ──
    if not borg.empty and "FECHA" in borg.columns:
        if "FECHA_ISO" not in borg.columns:
            borg["FECHA_ISO"] = borg["FECHA"].apply(_iso)
        b_f = borg[(borg["FECHA_ISO"] == fecha_obj) &
                   (borg["TURNO"].astype(str).str.upper() == turno)].copy()
        b_f["BORG_NUM"] = pd.to_numeric(b_f["BORG"], errors="coerce")
        estados = b_f[b_f["BORG_NUM"].isna() & (b_f["BORG"].astype(str).str.strip() != "")]
        if not estados.empty:
            print()
            print("*Estados no entrenables:*")
            for _, r in estados.iterrows():
                jug = str(r["JUGADOR"]).strip()
                estado = str(r["BORG"]).strip().upper()
                etiqueta = ESTADOS_NO_ENTRENABLES.get(estado, estado)
                incidencia = str(r.get("INCIDENCIA", "") or "").strip()
                extra = f" — ⚠ _{incidencia}_" if incidencia else ""
                print(f"  · *{jug:<10}* {estado} ({etiqueta}){extra}")


if __name__ == "__main__":
    main()
