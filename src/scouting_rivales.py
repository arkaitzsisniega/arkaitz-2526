#!/usr/bin/env python3
"""
Importador de SCOUTING de rivales desde `Est. Goles rivales.xlsx`.

Origen: ~/Mi unidad/.../Estadisticas/Est. Goles rivales.xlsx
Hojas: 15 hojas con códigos de 3 letras (ALZ, BAR, CAR, ...).
Cada hoja: cómo marca ese rival cuando juega contra OTROS equipos
(no contra Inter). Datos partido a partido.

Estructura de cada hoja (filas 8+):
  Col B: Competición (ej. "LIGA 25/26")
  Col C: Equipo rival del scoutado (contra quién jugó)
  Col D: Fecha
  Col F: TOTAL goles a favor del scoutado
  Cols G-W: desglose por origen (BANDA, CÓRNER, SAQUE CENTRO, FALTA, ...)

Uso:
  /usr/bin/python3 src/scouting_rivales.py --upload
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
import warnings
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

import pandas as pd
from openpyxl import load_workbook

XLSX_DEFAULT = (
    "/Users/mac/Mi unidad/Deporte/Futbol sala/Movistar Inter/"
    "2025-26/Estadisticas/Est. Goles rivales.xlsx"
)

# Diccionario código → nombre completo (temporada 25/26)
RIVALES_NOMBRES = {
    "ALZ": "Alzira FS",
    "BAR": "FC Barcelona",
    "CAR": "Jimbee Cartagena",
    "COR": "Córdoba Patrimonio",
    "ELP": "ElPozo Murcia",
    "IND": "Industrias Santa Coloma",
    "JAE": "Jaen Paraiso Interior",
    "MAN": "Manzanares Quesos Hidalgo",
    "NOI": "Noia Portus Apostoli",
    "OPA": "O Parrulo",
    "PAL": "Palma Futsal",
    "PEÑ": "Peñiscola Rehabmedic",
    "RIB": "Ribera de Navarra",
    "VAL": "Valdepeñas Viña Albali",
    "XOT": "Osasuna Magna",
}

# Columnas (1-indexed, openpyxl) → nombre canónico
COLUMNAS_ORIGEN = {
    7:  "Banda",
    8:  "Córner",
    9:  "Saque de Centro",
    10: "Falta",
    11: "2ª jugada",
    12: "10 metros",
    13: "Penalti",
    14: "Falta sin barrera",
    15: "Salida de presión",
    16: "Ataque Posicional 4x4",
    17: "1x1 en banda",
    18: "2ª jugada de ABP",
    19: "Incorporación del portero",
    20: "5x4",
    21: "4x3",
    22: "4x5",
    23: "3x4",
    24: "Contraataque",
    25: "Robo en zona alta",
    26: "No calificado",
}


def _to_int(v) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except Exception:
            return 0


def _to_date_iso(v) -> str:
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    return ""


def cargar(xlsx_path: str = XLSX_DEFAULT) -> pd.DataFrame:
    wb = load_workbook(xlsx_path, data_only=True)
    filas: list[dict] = []

    for codigo, nombre_full in RIVALES_NOMBRES.items():
        if codigo not in wb.sheetnames:
            print(f"⚠️  Hoja '{codigo}' no encontrada, salto.")
            continue
        ws = wb[codigo]
        # Datos a partir de fila 8 según la inspección
        for row in ws.iter_rows(min_row=8, values_only=True):
            if not row:
                continue
            comp = row[1] if len(row) > 1 else None
            contra = row[2] if len(row) > 2 else None
            fecha = row[3] if len(row) > 3 else None
            total_af = row[5] if len(row) > 5 else None
            if not comp or not contra:
                continue
            base = {
                "rival_codigo": codigo,
                "rival_nombre": nombre_full,
                "competicion": str(comp).strip(),
                "contra_quien": str(contra).strip(),
                "fecha": _to_date_iso(fecha),
                "total_a_favor": _to_int(total_af),
            }
            # Conteos por origen de gol
            for col_idx, accion in COLUMNAS_ORIGEN.items():
                # Col idx 1-based en openpyxl, pero row es 0-based con tuple
                v = row[col_idx - 1] if len(row) > (col_idx - 1) else None
                base[accion] = _to_int(v)
            filas.append(base)

    cols_base = ["rival_codigo", "rival_nombre", "competicion",
                 "contra_quien", "fecha", "total_a_favor"]
    cols_acciones = list(COLUMNAS_ORIGEN.values())
    return pd.DataFrame(filas, columns=cols_base + cols_acciones)


def calcular_agregado_rival(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por rival con totales y % por origen."""
    if df.empty:
        return pd.DataFrame()
    cols_acciones = list(COLUMNAS_ORIGEN.values())
    g = df.groupby(["rival_codigo", "rival_nombre"], as_index=False).agg(
        partidos=("contra_quien", "count"),
        total_goles=("total_a_favor", "sum"),
        **{c: (c, "sum") for c in cols_acciones},
    )
    # Porcentajes por origen
    for c in cols_acciones:
        pct_col = f"%{c}"
        g[pct_col] = (g[c] / g["total_goles"].replace(0, pd.NA) * 100).round(1)
    return g.sort_values("total_goles", ascending=False)


def subir_a_sheet(df_raw: pd.DataFrame, df_agr: pd.DataFrame) -> None:
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open("Arkaitz - Datos Temporada 2526")

    def _write(hoja: str, df: pd.DataFrame):
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

    _write("SCOUTING_RIVALES", df_raw)
    _write("_VISTA_SCOUTING_RIVAL", df_agr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX_DEFAULT)
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    df_raw = cargar(args.xlsx)
    df_agr = calcular_agregado_rival(df_raw)

    print(f"Filas raw: {len(df_raw)}")
    print(f"Rivales scouted: {df_raw['rival_codigo'].nunique()}")
    print()
    print("Top rivales por goles registrados:")
    print(df_agr[["rival_codigo", "rival_nombre", "partidos", "total_goles"]]
          .head(15).to_string(index=False))

    if args.upload:
        subir_a_sheet(df_raw, df_agr)


if __name__ == "__main__":
    main()
