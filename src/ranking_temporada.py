"""
ranking_temporada.py — Devuelve rankings agregados de la temporada por
jugador. Script CURADO (sin LLM): el bot_datos lo llama directo cuando
detecta preguntas tipo:
  - "lista de asistencias del equipo en liga"
  - "ranking goleadores"
  - "quién mete más disparos"
  - "top robos"

Evita falsos positivos del safety filter de Gemini (finish_reason=10)
con preguntas que mezclan "equipo" + "asistencias" + nombres propios.

Uso:
  /usr/bin/python3 src/ranking_temporada.py CATEGORIA [COMPETICION]

  CATEGORIA: goles · asistencias · disparos · puerta · faltas · amarillas
             · rojas · perdidas · robos · cortes · bdg · bdp · plus_minus
             · minutos
  COMPETICION (opcional): LIGA · COPA_REY · COPA_ESPANA · COPA_MUNDO ·
             AMISTOSO · PLAYOFF · SUPERCOPA · TODAS (default)

Lee de EST_PARTIDOS y EST_EVENTOS del Sheet principal.
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

# Cómo agregar cada categoría (col en EST_PARTIDOS → operación + label).
CATEGORIAS = {
    "goles":       ("goles_a_favor", "Goles"),
    "asistencias": ("asistencias",   "Asistencias"),
    "disparos":    (("dp","dpalo","db","df"), "Disparos totales"),
    "puerta":      ("dp",            "Disparos a puerta"),
    "faltas":      ("faltas",        "Faltas cometidas"),
    "amarillas":   ("ta",            "Tarjetas amarillas"),
    "rojas":       ("tr",            "Tarjetas rojas"),
    "perdidas":    (("pf","pnf"),    "Pérdidas (PF+PNF)"),
    "robos":       ("robos",         "Robos"),
    "cortes":      ("cortes",        "Cortes"),
    "bdg":         ("bdg",           "Balones divididos ganados"),
    "bdp":         ("bdp",           "Balones divididos perdidos"),
    "minutos":     ("min_total",     "Minutos jugados"),
}

ALIAS_COMP = {
    "LIGA": "LIGA",
    "COPA_REY": "COPA_REY", "COPA REY": "COPA_REY", "COPA DEL REY": "COPA_REY",
    "COPA_ESPANA": "COPA_ESPANA", "COPA ESPANA": "COPA_ESPANA",
    "COPA DE ESPAÑA": "COPA_ESPANA", "COPA ESPAÑA": "COPA_ESPANA",
    "COPA_MUNDO": "COPA_MUNDO", "COPA MUNDO": "COPA_MUNDO",
    "MUNDIAL": "COPA_MUNDO", "COPA DEL MUNDO": "COPA_MUNDO",
    "AMISTOSO": "AMISTOSO",
    "PLAYOFF": "PLAYOFF", "PLAY-OFF": "PLAYOFF", "PLAY OFF": "PLAYOFF",
    "SUPERCOPA": "SUPERCOPA",
    "TODAS": "TODAS", "TODA": "TODAS", "TEMPORADA": "TODAS",
}


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def main():
    args = sys.argv[1:]
    CAT_VALIDAS = list(CATEGORIAS.keys()) + ["plus_minus"]
    if not args:
        print("Uso: ranking_temporada.py CATEGORIA [COMPETICION]")
        print(f"Categorías: {', '.join(CAT_VALIDAS)}")
        return
    cat_raw = args[0].lower().strip()
    cat = cat_raw
    # Sinónimos
    sinon = {"asist": "asistencias", "asistencia": "asistencias",
             "asistencias": "asistencias",
             "gol": "goles", "goleador": "goles", "goleadores": "goles",
             "disparo": "disparos", "tiros": "disparos",
             "a_puerta": "puerta", "a puerta": "puerta", "tiros_puerta": "puerta",
             "amarilla": "amarillas", "amarilas": "amarillas",
             "roja": "rojas",
             "perdida": "perdidas", "pérdidas": "perdidas",
             "robo": "robos",
             "corte": "cortes",
             "min": "minutos", "minuto": "minutos",
             "+/-": "plus_minus", "plusminus": "plus_minus"}
    cat = sinon.get(cat, cat)
    if cat not in CAT_VALIDAS:
        print(f"❌ Categoría desconocida: {cat_raw!r}")
        print(f"Disponibles: {', '.join(CAT_VALIDAS)}")
        return

    comp_raw = " ".join(args[1:]).strip().upper() if len(args) > 1 else "TODAS"
    # Si pasa competición pero no la reconocemos, AVISAR claramente en vez
    # de devolver silenciosamente TODAS (antes el user creía que tenía
    # ranking de su competición y era de toda la temporada).
    if comp_raw and comp_raw not in ALIAS_COMP and comp_raw not in set(ALIAS_COMP.values()):
        comps_legibles = sorted(set(ALIAS_COMP.values()))
        print(f"⚠️ Competición no reconocida: *{comp_raw}*. Te paso TODAS las competiciones.")
        print(f"_Competiciones válidas: {', '.join(comps_legibles)}_")
        print()
        comp = "TODAS"
    else:
        comp = ALIAS_COMP.get(comp_raw, comp_raw if comp_raw in set(ALIAS_COMP.values()) else "TODAS")

    ss = conectar()
    ep = pd.DataFrame(ss.worksheet("EST_PARTIDOS").get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted))
    ev = pd.DataFrame(ss.worksheet("EST_EVENTOS").get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted))

    if ep.empty:
        print("⚠️ EST_PARTIDOS está vacío. No hay datos de partidos cargados.")
        return

    # Filtrar competición
    if comp != "TODAS" and "tipo" in ep.columns:
        ep_f = ep[ep["tipo"].astype(str).str.upper() == comp].copy()
        ev_f = ev[ev["partido_id"].isin(ep_f["partido_id"].unique())].copy() if not ev.empty else pd.DataFrame()
    else:
        ep_f = ep.copy()
        ev_f = ev.copy()

    if ep_f.empty:
        print(f"⚠️ No hay partidos en la competición *{comp}*.")
        return

    label_comp = "Toda la temporada" if comp == "TODAS" else comp.replace("_", " ").title()

    # Plus/minus se calcula con eventos en pista
    if cat == "plus_minus":
        print(f"📊 *Plus/Minus por jugador · {label_comp}*")
        print()
        if ev_f.empty:
            print("⚠️ No hay eventos para calcular plus/minus.")
            return
        # Para cada jugador del roster: contar goles a favor / contra estando él en pista
        jugadores = sorted(ep_f["jugador"].dropna().astype(str).unique().tolist())
        rows = []
        for j in jugadores:
            mask = ev_f.apply(
                lambda r: (j in str(r.get("cuarteto", "")).split("|"))
                          or (str(r.get("portero", "")) == j), axis=1
            )
            af = int(((ev_f["equipo_marca"] == "INTER") & mask).sum())
            ec = int(((ev_f["equipo_marca"] == "RIVAL") & mask).sum())
            rows.append((j, af, ec, af - ec))
        rows = [r for r in rows if r[1] + r[2] > 0]  # solo con presencia
        rows.sort(key=lambda r: r[3], reverse=True)
        for j, af, ec, pm in rows:
            sign = "+" if pm >= 0 else ""
            print(f"  · *{j:<10}*  {sign}{pm}  (GF en pista: {af} · GC en pista: {ec})")
        return

    # Categorías agregables de EST_PARTIDOS
    col_or_tuple, label = CATEGORIAS[cat]
    if isinstance(col_or_tuple, tuple):
        for c in col_or_tuple:
            ep_f[c] = pd.to_numeric(ep_f[c], errors="coerce").fillna(0)
        ep_f["_total"] = sum(ep_f[c] for c in col_or_tuple)
    else:
        ep_f["_total"] = pd.to_numeric(ep_f[col_or_tuple], errors="coerce").fillna(0)

    agr = (ep_f.groupby("jugador", as_index=False)["_total"].sum()
              .sort_values("_total", ascending=False))
    agr = agr[agr["_total"] > 0]
    if agr.empty:
        print(f"⚠️ Nadie tiene {label.lower()} registrados en *{label_comp}*.")
        return

    print(f"📊 *{label} por jugador · {label_comp}*")
    print()
    es_minutos = (cat == "minutos")
    for _, r in agr.iterrows():
        jug = str(r["jugador"]).strip()
        v = r["_total"]
        if es_minutos:
            total_min = int(round(v))
            print(f"  · *{jug:<10}*  {total_min} min")
        else:
            print(f"  · *{jug:<10}*  *{int(v)}*")

    total = int(round(agr["_total"].sum()))
    media = agr["_total"].mean()
    print()
    if es_minutos:
        print(f"_Total equipo: {total} min · Media por jugador: {int(round(media))} min_")
    else:
        print(f"_Total equipo: {total} · Media por jugador: {media:.1f}_")


if __name__ == "__main__":
    main()
