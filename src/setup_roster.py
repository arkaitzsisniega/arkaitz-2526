#!/usr/bin/env python3
"""
setup_roster.py — Crea/actualiza la hoja `JUGADORES_ROSTER` con la
plantilla maestra del Movistar Inter FS 25/26 (primer equipo + filial).

Esta hoja sirve como referencia única en:
  - Form de "Crear/Editar partido" (dropdowns de jugadores)
  - Formularios de wellness, peso, BORG (validación de nombres)
  - Cálculo de KPIs por jugador (filtrar por activos)

Estructura de la hoja:
  | dorsal | nombre | posicion | equipo | activo |
  |   2    | CECILIO|  CAMPO   | PRIMER |  TRUE  |
  |  27    |J.GARCIA| PORTERO  | PRIMER |  TRUE  |
  |  ...

Uso:
  /usr/bin/python3 src/setup_roster.py            # crea/actualiza
  /usr/bin/python3 src/setup_roster.py --reset    # limpia y recarga

Tras ejecutarlo, el usuario puede editar la hoja directamente para:
  - Cambiar dorsales
  - Marcar inactivo a quien deja el equipo
  - Añadir nuevos (juveniles que suben, fichajes…)
"""
from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import gspread
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = str(ROOT / "google_credentials.json")
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
HOJA = "JUGADORES_ROSTER"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Plantilla 25/26 (datos confirmados por Arkaitz el 28/04/2026)
ROSTER = [
    # PRIMER EQUIPO — porteros
    {"dorsal": 1,  "nombre": "J.HERRERO",  "posicion": "PORTERO", "equipo": "PRIMER", "activo": True},
    {"dorsal": 27, "nombre": "J.GARCIA",   "posicion": "PORTERO", "equipo": "PRIMER", "activo": True},
    # PRIMER EQUIPO — campo
    {"dorsal": 2,  "nombre": "CECILIO",    "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 5,  "nombre": "CHAGUINHA",  "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 6,  "nombre": "RAUL",       "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 7,  "nombre": "HARRISON",   "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 8,  "nombre": "RAYA",       "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 10, "nombre": "JAVI",       "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 11, "nombre": "PANI",       "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 17, "nombre": "PIRATA",     "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 18, "nombre": "BARONA",     "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    {"dorsal": 20, "nombre": "CARLOS",     "posicion": "CAMPO",   "equipo": "PRIMER", "activo": True},
    # FILIAL — porteros
    {"dorsal": 28, "nombre": "OSCAR",      "posicion": "PORTERO", "equipo": "FILIAL", "activo": True},
    # FILIAL — campo
    {"dorsal": 14, "nombre": "RUBIO",      "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    {"dorsal": 15, "nombre": "JAIME",      "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    {"dorsal": 22, "nombre": "SEGO",       "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    {"dorsal": 25, "nombre": "DANI",       "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    {"dorsal": 31, "nombre": "GONZA",      "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    # Filial sin dorsal asignado todavía
    {"dorsal": "", "nombre": "PABLO",      "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
    {"dorsal": "", "nombre": "GABRI",      "posicion": "CAMPO",   "equipo": "FILIAL", "activo": True},
]

CABECERAS = ["dorsal", "nombre", "posicion", "equipo", "activo"]


def _connect():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


def _get_or_create_ws(sh, hoja: str, rows: int, cols: int):
    try:
        ws = sh.worksheet(hoja)
        return ws
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=hoja, rows=rows, cols=cols)


def _col_letra(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main(reset: bool = False):
    sh = _connect()
    ws = _get_or_create_ws(sh, HOJA, rows=max(len(ROSTER) + 5, 50),
                            cols=len(CABECERAS) + 2)

    if reset:
        ws.clear()
        print(f"🧹 Hoja {HOJA} limpiada (modo --reset)")

    # Si tiene contenido y no es reset → preservar lo que el usuario haya
    # editado a mano. Solo añadimos los que faltan.
    existing_rows = ws.get_all_values()
    if not existing_rows or not existing_rows[0]:
        # Hoja vacía → escribir todo
        valores = [CABECERAS] + [
            [r["dorsal"], r["nombre"], r["posicion"], r["equipo"],
             "TRUE" if r["activo"] else "FALSE"]
            for r in ROSTER
        ]
        ws.update(values=valores, range_name="A1")
        ws.format(f"A1:{_col_letra(len(CABECERAS))}1",
                   {"textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.11, "green": 0.23, "blue": 0.42},
                    "horizontalAlignment": "CENTER"})
        ws.format(f"A1:{_col_letra(len(CABECERAS))}1",
                   {"textFormat": {"foregroundColor":
                                    {"red": 1, "green": 1, "blue": 1},
                                    "bold": True}})
        print(f"✅ {HOJA}: {len(ROSTER)} jugadores escritos")
    else:
        print(f"ℹ️  {HOJA} ya tiene {len(existing_rows) - 1} filas. "
              "No sobreescribo (usa --reset para forzar).")
        # Detectar nuevos
        existing_names = {r[1].strip().upper() for r in existing_rows[1:]
                          if len(r) > 1 and r[1].strip()}
        nuevos = [r for r in ROSTER if r["nombre"] not in existing_names]
        if nuevos:
            print(f"   → {len(nuevos)} jugadores nuevos detectados:")
            for r in nuevos:
                print(f"     - {r['nombre']} (#{r['dorsal'] or '?'}, {r['posicion']}, {r['equipo']})")
            print("   Para añadirlos, edítalos manualmente o usa --reset.")

    print(f"\n🔗 Hoja: https://docs.google.com/spreadsheets/d/{sh.id}/edit#gid={ws.id}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="Limpia la hoja y recarga el roster por defecto")
    args = ap.parse_args()
    main(reset=args.reset)
