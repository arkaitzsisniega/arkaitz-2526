#!/usr/bin/env python3
"""
Calcula métricas AVANZADAS por jugador a partir de las hojas crudas
del Sheet maestro. Las escribe a `_VISTA_EST_AVANZADAS`.

Métricas calculadas:
  - Goles por 40' (un partido completo)
  - Asistencias por 40'
  - G+A por 40'
  - % goles del equipo (qué fracción aporta)
  - % asistencias del equipo
  - % minutos del equipo
  - +/- (goles a favor con él en pista − goles en contra con él en pista)
  - +/- por 40'

También calcula `_VISTA_EST_CUARTETOS`: ranking de cuartetos por +/- y minutos.

Lee de:
  - EST_PARTIDOS (jugador × partido con minutos)
  - EST_EVENTOS (eventos de gol con cuarteto)

Uso:
  /usr/bin/python3 src/estadisticas_avanzadas.py --upload
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
CREDS_FILE = "google_credentials.json"


def _conectar():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


def _leer(sh, hoja: str) -> pd.DataFrame:
    ws = sh.worksheet(hoja)
    return pd.DataFrame(ws.get_all_records())


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def calcular_avanzadas(part: pd.DataFrame, evt: pd.DataFrame) -> pd.DataFrame:
    if part.empty:
        return pd.DataFrame()
    part = part.copy()
    for c in ("min_total", "min_1t", "min_2t", "goles_a_favor", "asistencias"):
        if c in part.columns:
            part[c] = _to_num(part[c])
    if "participa" in part.columns:
        part["participa"] = part["participa"].astype(str).map(
            lambda v: 1 if v in ("1", "True", "true") else 0
        )

    # Totales del EQUIPO (sumas de jugador-partido)
    total_min_equipo = part["min_total"].sum()
    # Goles del equipo desde EVENTOS (más fiable que sumar goles_a_favor)
    if not evt.empty and "equipo_marca" in evt.columns:
        total_gol_equipo_af = (evt["equipo_marca"] == "INTER").sum()
        total_gol_equipo_ec = (evt["equipo_marca"] == "RIVAL").sum()
    else:
        total_gol_equipo_af = part["goles_a_favor"].sum()
        total_gol_equipo_ec = 0
    total_asist_equipo = part["asistencias"].sum()

    # Agrupar por jugador
    agr = part.groupby("jugador", as_index=False).agg(
        partidos_convocado=("convocado", "count"),
        partidos_jugados=("participa", "sum"),
        min_total=("min_total", "sum"),
        goles=("goles_a_favor", "sum"),
        asists=("asistencias", "sum"),
    )
    agr["g+a"] = agr["goles"] + agr["asists"]

    # +/-: para cada jugador, contar goles cuando estaba en pista
    if not evt.empty and "cuarteto" in evt.columns:
        evt = evt.copy()
        evt["cuarteto_set"] = evt["cuarteto"].apply(
            lambda s: set(filter(None, str(s).split("|")))
        )
        evt["portero"] = evt["portero"].fillna("").astype(str)

        plusminus = []
        for j in agr["jugador"]:
            mask_en_pista = evt.apply(
                lambda r: (j in r["cuarteto_set"]) or (r["portero"] == j), axis=1
            )
            af_en_pista = ((evt["equipo_marca"] == "INTER") & mask_en_pista).sum()
            ec_en_pista = ((evt["equipo_marca"] == "RIVAL") & mask_en_pista).sum()
            plusminus.append({
                "jugador": j,
                "gf_en_pista": int(af_en_pista),
                "gc_en_pista": int(ec_en_pista),
                "plus_minus": int(af_en_pista - ec_en_pista),
            })
        agr = agr.merge(pd.DataFrame(plusminus), on="jugador", how="left")
        agr[["gf_en_pista", "gc_en_pista", "plus_minus"]] = (
            agr[["gf_en_pista", "gc_en_pista", "plus_minus"]].fillna(0)
        )

    # Métricas por 40'
    factor40 = 40 / agr["min_total"].clip(lower=1)
    agr["goles_por_40"] = (agr["goles"] * factor40).round(2)
    agr["asists_por_40"] = (agr["asists"] * factor40).round(2)
    agr["g+a_por_40"] = (agr["g+a"] * factor40).round(2)
    if "plus_minus" in agr.columns:
        agr["plus_minus_por_40"] = (agr["plus_minus"] * factor40).round(2)

    # % sobre el equipo
    agr["pct_minutos_equipo"] = ((agr["min_total"] / max(total_min_equipo, 1)) * 100).round(1)
    agr["pct_goles_equipo"]   = ((agr["goles"]    / max(total_gol_equipo_af, 1)) * 100).round(1)
    agr["pct_asists_equipo"]  = ((agr["asists"]   / max(total_asist_equipo, 1)) * 100).round(1)

    # Filas con minutos = 0 (porteros suplentes que nunca jugaron) → métricas 0
    agr.loc[agr["min_total"] <= 0, ["goles_por_40", "asists_por_40", "g+a_por_40"]] = 0
    if "plus_minus_por_40" in agr.columns:
        agr.loc[agr["min_total"] <= 0, "plus_minus_por_40"] = 0

    # Orden de columnas: identificadoras → totales → por 40' → % → +/-
    cols = ["jugador", "partidos_convocado", "partidos_jugados", "min_total",
            "goles", "asists", "g+a",
            "goles_por_40", "asists_por_40", "g+a_por_40",
            "pct_minutos_equipo", "pct_goles_equipo", "pct_asists_equipo"]
    if "plus_minus" in agr.columns:
        cols += ["gf_en_pista", "gc_en_pista", "plus_minus", "plus_minus_por_40"]
    return agr[cols].sort_values("goles", ascending=False)


def calcular_cuartetos(part: pd.DataFrame, evt: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """Devuelve los cuartetos más comunes con sus goles a favor y en contra.

    Cuarteto = combinación de los 3-5 jugadores en pista (campo + portero).
    Lo ordenamos alfabéticamente para deduplicar permutaciones.
    """
    if evt.empty:
        return pd.DataFrame()
    e = evt.copy()
    e["portero"] = e["portero"].fillna("").astype(str)
    e["cuarteto"] = e["cuarteto"].fillna("").astype(str)
    def _formacion(r):
        miembros = list(filter(None, r["cuarteto"].split("|")))
        if r["portero"]:
            miembros.append(r["portero"])
        return " | ".join(sorted(set(miembros)))
    e["formacion"] = e.apply(_formacion, axis=1)
    if "equipo_marca" not in e.columns:
        return pd.DataFrame()

    agr = e.groupby("formacion", as_index=False).agg(
        n_eventos=("formacion", "count"),
        goles_a_favor=("equipo_marca", lambda s: (s == "INTER").sum()),
        goles_en_contra=("equipo_marca", lambda s: (s == "RIVAL").sum()),
    )
    agr["plus_minus"] = agr["goles_a_favor"] - agr["goles_en_contra"]
    agr = agr.sort_values(["plus_minus", "n_eventos"], ascending=[False, False])
    return agr.head(top_n)


def subir(sh, hoja: str, df: pd.DataFrame):
    if df.empty:
        print(f"  (omito {hoja}: dataframe vacío)")
        return
    try:
        ws = sh.worksheet(hoja)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=hoja, rows=max(len(df) + 5, 30), cols=max(len(df.columns), 6))
    out = df.where(pd.notnull(df), "")
    valores = [list(out.columns)] + out.astype(str).values.tolist()
    ws.update(values=valores, range_name="A1")
    ws.format(f"A1:{chr(64 + min(len(out.columns), 26))}1", {"textFormat": {"bold": True}})
    print(f"✅ {hoja}: {len(out)} filas, {len(out.columns)} cols")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    sh = _conectar()
    part = _leer(sh, "EST_PARTIDOS")
    evt = _leer(sh, "EST_EVENTOS")
    print(f"EST_PARTIDOS: {len(part)} filas")
    print(f"EST_EVENTOS:  {len(evt)} filas")
    print()

    avanz = calcular_avanzadas(part, evt)
    cuart = calcular_cuartetos(part, evt)

    print("Top 5 jugadores por +/-:")
    cols_show = ["jugador", "partidos_jugados", "min_total", "goles", "asists",
                 "goles_por_40", "pct_goles_equipo", "plus_minus", "plus_minus_por_40"]
    cols_show = [c for c in cols_show if c in avanz.columns]
    print(avanz.sort_values("plus_minus", ascending=False)[cols_show].head().to_string(index=False))
    print()
    print(f"Cuartetos detectados: {len(cuart)}")
    if not cuart.empty:
        print("Top 3 cuartetos por +/-:")
        print(cuart.head(3).to_string(index=False))

    if args.upload:
        subir(sh, "_VISTA_EST_AVANZADAS", avanz)
        subir(sh, "_VISTA_EST_CUARTETOS", cuart)


if __name__ == "__main__":
    main()
