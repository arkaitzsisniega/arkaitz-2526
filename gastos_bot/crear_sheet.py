#!/usr/bin/env python3
"""
Inicializa la hoja GASTOS dentro de un Google Sheet ya existente.

Pasos previos (los hace Arkaitz, una sola vez):
  1. Ir a sheets.google.com con su cuenta arkaitzsisniega@gmail.com.
  2. Crear un Sheet vacío llamado "Gastos Comunes — Arkaitz & Lis 2526".
  3. Compartir (botón "Compartir") con la service account:
        arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com
     como editor.
  4. Copiar el SHEET_ID de la URL y meterlo en gastos_bot/.env como
        GASTOS_SHEET_ID=...

Después se ejecuta este script:
  /usr/bin/python3 gastos_bot/crear_sheet.py

Crea la hoja GASTOS si no existe, escribe cabeceras y borra "Hoja 1"
si está vacía. Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CREDS = ROOT / "google_credentials.json"

load_dotenv(HERE / ".env")
SHEET_ID = os.getenv("GASTOS_SHEET_ID", "").strip()

HOJA = "GASTOS"
CABECERAS = ["fecha", "concepto", "cantidad", "categoria", "quien_apunta", "notas"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main() -> int:
    if not SHEET_ID:
        print("❌ Falta GASTOS_SHEET_ID en gastos_bot/.env", file=sys.stderr)
        print("   Crea el Sheet en sheets.google.com, compártelo con", file=sys.stderr)
        print("   arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com", file=sys.stderr)
        print("   y pega el ID de la URL en .env como GASTOS_SHEET_ID=...", file=sys.stderr)
        return 1

    creds = Credentials.from_service_account_file(str(CREDS), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print(f"✅ Sheet abierto: {sh.title}")

    try:
        ws = sh.worksheet(HOJA)
        print(f"   Hoja '{HOJA}' ya existía.")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=HOJA, rows=2000, cols=len(CABECERAS))
        print(f"   Hoja '{HOJA}' creada.")

    for w in sh.worksheets():
        if w.title in ("Sheet1", "Hoja 1", "Hoja1") and w.title != HOJA:
            try:
                sh.del_worksheet(w)
                print(f"   Hoja por defecto '{w.title}' eliminada.")
            except Exception:
                pass

    fila1 = ws.row_values(1)
    if fila1 != CABECERAS:
        ws.update(values=[CABECERAS], range_name="A1:F1")
        ws.format("A1:F1", {"textFormat": {"bold": True}})
        print("   Cabeceras escritas.")
    else:
        print("   Cabeceras ya correctas.")

    print()
    print(f"URL: https://docs.google.com/spreadsheets/d/{sh.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
