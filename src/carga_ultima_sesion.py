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
    """Convierte cualquier formato de fecha a 'YYYY-MM-DD'. Maneja:
    - Serial date de Google Sheets (entero o float, ej. 46155).
    - String ISO 'YYYY-MM-DD' (10 chars).
    - String 'DD/MM/YYYY' o 'DD-MM-YYYY' (formato Form de Google en español).
    Devuelve "" si no reconoce."""
    if v is None:
        return ""
    if isinstance(v, (int, float)) and 1 < v < 60000:
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).date().isoformat()
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return ""
        # ISO YYYY-MM-DD
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        # DD/MM/YYYY o DD-MM-YYYY (formato Forms Google España)
        try:
            d = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.notna(d):
                return d.date().isoformat()
        except Exception:
            pass
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
    # _FORM_POST: respuestas crudas del Form de jugadores (PRE/POST).
    # Las leemos como fallback si BORG no tiene datos para la fecha
    # pedida (caso: el equipo rellenó pero Arkaitz aún no /consolidar).
    form_post = _leer(ss, "_FORM_POST")

    if ses.empty:
        print("⚠️ No hay sesiones registradas.")
        return

    ses["FECHA_ISO"] = ses["FECHA"].apply(_iso)
    ses = ses[ses["FECHA_ISO"] != ""]

    # Helper: encuentra la última fecha de SESIONES con BORG numérico
    # registrado (al menos 1 jugador). Útil para sugerir como fallback.
    def _ultima_fecha_con_datos():
        if borg.empty or "FECHA" not in borg.columns:
            return None
        b = borg.copy()
        b["FECHA_ISO"] = b["FECHA"].apply(_iso)
        b["BORG_NUM"] = pd.to_numeric(b["BORG"], errors="coerce")
        con_datos = b[b["BORG_NUM"].notna()]["FECHA_ISO"].dropna()
        return con_datos.max() if not con_datos.empty else None

    # ── Determinar la sesión objetivo ──
    if fecha_arg:
        fecha_obj = fecha_arg
        ses_f = ses[ses["FECHA_ISO"] == fecha_obj]
        if ses_f.empty:
            ult = _ultima_fecha_con_datos()
            print(f"⚠️ No hay sesión registrada para *{fecha_obj}*.")
            if ult:
                print(f"\nÚltima sesión con datos completos: *{ult}*.")
                print(f"Si quieres esos datos: _'carga jugador por jugador del {ult}'_")
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
        # _VISTA_CARGA NO tiene datos para esta fecha. Tres posibles causas:
        # 1) BORG sí tiene datos pero _VISTA_CARGA no se ha recalculado (falta /consolidar).
        # 2) BORG está vacío para esa fecha → los jugadores no han rellenado el Form.
        # 3) Solo hay estados (L/A/D/N/S/NC/NJ), nadie con Borg numérico.
        if "FECHA_ISO" not in borg.columns:
            borg["FECHA_ISO"] = borg["FECHA"].apply(_iso)
        b_f = borg[(borg["FECHA_ISO"] == fecha_obj) &
                   (borg["TURNO"].astype(str).str.upper() == turno)].copy()
        b_f["BORG_NUM"] = pd.to_numeric(b_f["BORG"], errors="coerce")
        entrenaron = b_f[b_f["BORG_NUM"].notna()].copy()

        if not entrenaron.empty:
            # Caso 1: BORG sí, _VISTA_CARGA no → mostrar Borg crudo
            print("*Carga por jugador (Borg crudo, sin minutos reales aún):*")
            entrenaron = entrenaron.sort_values("BORG_NUM", ascending=False)
            for _, r in entrenaron.iterrows():
                jug = str(r["JUGADOR"]).strip()
                borg_v = int(r["BORG_NUM"])
                carga_aprox = borg_v * minutos_ses if minutos_ses else borg_v
                print(f"  · *{jug:<10}*  Borg {borg_v} · ~carga {carga_aprox}")
            print()
            print(f"_Total: {len(entrenaron)} jugadores. "
                  f"⚠ Carga calculada con minutos GENERALES de la sesión, "
                  f"no individuales. Lanza /consolidar para que cruce con "
                  f"minutos reales de partido._")
        else:
            # Caso 2 o 3: BORG vacío o solo estados.
            # FALLBACK: probar _FORM_POST (respuestas del Form sin consolidar).
            fp_filas = []
            if not form_post.empty:
                fp = form_post.copy()
                fc = "Fecha del entreno" if "Fecha del entreno" in fp.columns else None
                tc = "Turno" if "Turno" in fp.columns else None
                jc = "Jugador" if "Jugador" in fp.columns else None
                bc = "Borg (esfuerzo percibido)" if "Borg (esfuerzo percibido)" in fp.columns else None
                if fc and tc and jc and bc:
                    fp["_iso"] = fp[fc].apply(_iso)
                    # Mapear "Mañana"/"Tarde" a "M"/"T"
                    fp["_turno"] = fp[tc].astype(str).str.strip().str.upper().map(
                        lambda v: "M" if v.startswith("M") else ("T" if v.startswith("T") else v)
                    )
                    fp_f = fp[(fp["_iso"] == fecha_obj) & (fp["_turno"] == turno)].copy()
                    if not fp_f.empty:
                        fp_f["BORG_NUM"] = pd.to_numeric(fp_f[bc], errors="coerce")
                        # Última respuesta por jugador (si rellenó varias veces, gana la última)
                        fp_f = fp_f.dropna(subset=["BORG_NUM"]).sort_values(
                            "Marca temporal" if "Marca temporal" in fp_f.columns else fc
                        ).drop_duplicates(subset=[jc], keep="last")
                        fp_filas = fp_f

            if isinstance(fp_filas, pd.DataFrame) and not fp_filas.empty:
                print("*Carga por jugador (Borg del Form, sin consolidar todavía):*")
                fp_filas = fp_filas.sort_values("BORG_NUM", ascending=False)
                for _, r in fp_filas.iterrows():
                    jug = str(r["Jugador"]).strip().upper()
                    borg_v = int(r["BORG_NUM"])
                    carga_aprox = borg_v * minutos_ses if minutos_ses else borg_v
                    print(f"  · *{jug:<10}*  Borg {borg_v} · ~carga {carga_aprox}")
                print()
                media = fp_filas["BORG_NUM"].mean()
                print(f"_Total: {len(fp_filas)} jugadores · Borg medio: {media:.1f}. "
                      f"⚠ Estos datos están en *_FORM_POST* (respuestas del jugador) "
                      f"pero todavía no se han consolidado a BORG ni a _VISTA_CARGA. "
                      f"Cuando Arkaitz lance `/consolidar` en el bot dev, "
                      f"los verás también en el dashboard con carga real._")
            else:
                # Ni BORG, ni _VISTA_CARGA, ni _FORM_POST tienen Borg numérico.
                # Distinguimos: hay estados apuntados (L/A/D/…) o no hay nada.
                n_estados = len(b_f[b_f["BORG_NUM"].isna() &
                                     (b_f["BORG"].astype(str).str.strip() != "")])
                ult = _ultima_fecha_con_datos()
                if n_estados == 0:
                    print(f"❌ *No hay nadie con Borg apuntado para {fecha_obj} ({turno}).*")
                    print()
                    print("He buscado en BORG, _VISTA_CARGA y _FORM_POST y no hay nada.")
                    print()
                    print("Posibles causas:")
                    print("  · El cuerpo técnico aún no ha rellenado los Google Forms")
                    print("    PRE/POST de esa sesión. Recuérdaselo al equipo.")
                    print("  · La fecha o el turno no coinciden con el Form rellenado.")
                    if ult:
                        print()
                        print(f"📅 Última sesión con datos completos: *{ult}*.")
                        print(f"   Para verla: _'carga jugador por jugador del {ult}'_")
                    return
                else:
                    print(f"⚠️ *Para {fecha_obj} solo hay estados apuntados* "
                          f"(lesiones/ausencias/etc.). Nadie ha registrado Borg "
                          f"numérico del entreno todavía.")
                    print()
                    print("Los demás jugadores aún no han rellenado el Form de "
                          "POST (Borg) o no se ha consolidado al Sheet.")
                    if ult and ult != fecha_obj:
                        print()
                        print(f"📅 Última sesión con datos completos: *{ult}*.")
                    # NO return → debajo se muestran los estados

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
