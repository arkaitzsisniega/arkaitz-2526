"""
Wrapper de gspread para la hoja GASTOS.

Operaciones:
  - append_gasto: añade fila.
  - leer_todos: devuelve lista de dicts con todos los gastos.
  - borrar_ultimo (de un usuario concreto): borra la última fila apuntada
    por ese usuario.
  - actualizar_categoria_ultimo: cambia la categoría de la última fila
    apuntada por ese usuario.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Optional

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CREDS = ROOT / "google_credentials.json"

load_dotenv(HERE / ".env")
SHEET_ID = os.getenv("GASTOS_SHEET_ID", "").strip()

HOJA = "GASTOS"
COL_FECHA = 1
COL_CONCEPTO = 2
COL_CANTIDAD = 3
COL_CATEGORIA = 4
COL_QUIEN = 5
COL_NOTAS = 6

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _ws():
    if not SHEET_ID:
        raise RuntimeError(
            "GASTOS_SHEET_ID no está definido. Edita gastos_bot/.env"
        )
    creds = Credentials.from_service_account_file(str(CREDS), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(HOJA)


def _fmt_cantidad(c: float) -> str:
    """Formato español: 15.85 → '15,85'. Necesario porque el Sheet está
    en locale español y, con USER_ENTERED, interpreta el punto como
    separador de miles (15.85 → 1585). Pasando '15,85' lo guarda bien."""
    return f"{round(float(c), 2):.2f}".replace(".", ",")


def append_gasto(
    concepto: str,
    cantidad: float,
    categoria: str,
    quien: str,
    notas: str = "",
    fecha: Optional[_dt.date] = None,
) -> int:
    """Añade un gasto. Devuelve el número de fila (1-indexed)."""
    f = fecha or _dt.date.today()
    ws = _ws()
    fila = [
        f.strftime("%Y-%m-%d"),
        concepto,
        _fmt_cantidad(cantidad),
        categoria,
        quien,
        notas,
    ]
    ws.append_row(fila, value_input_option="USER_ENTERED")
    # gspread no devuelve el row_index al hacer append_row; lo deducimos
    # leyendo la última fila no vacía.
    return len(ws.col_values(COL_FECHA))


def leer_todos() -> list[dict]:
    """Lee todas las filas como list[dict] con todos los valores como
    strings formateados.

    Evitamos `get_all_records()` porque su numericise convierte "9,99"
    a entero 999 (ignora la coma decimal española). Devolvemos strings
    y dejamos que el caller parsee cantidad y fecha con conocimiento
    del locale.
    """
    ws = _ws()
    valores = ws.get_values()
    if not valores:
        return []
    cabeceras = valores[0]
    filas = []
    for fila in valores[1:]:
        fila = list(fila) + [""] * (len(cabeceras) - len(fila))
        filas.append({h: fila[i] for i, h in enumerate(cabeceras)})
    return filas


def _ultima_fila_de(ws, quien: str) -> Optional[int]:
    """Devuelve el número de fila (1-indexed) de la última entrada de 'quien'."""
    valores = ws.get_all_values()
    if len(valores) < 2:
        return None
    # Saltamos la fila 1 (cabeceras). Recorremos de abajo a arriba.
    for idx in range(len(valores) - 1, 0, -1):
        fila = valores[idx]
        if len(fila) >= COL_QUIEN and fila[COL_QUIEN - 1].strip().lower() == quien.lower():
            return idx + 1  # gspread es 1-indexed
    return None


def borrar_ultimo(quien: str) -> Optional[dict]:
    ws = _ws()
    fila = _ultima_fila_de(ws, quien)
    if fila is None:
        return None
    valores = ws.row_values(fila)
    cabeceras = ws.row_values(1)
    info = {h: (valores[i] if i < len(valores) else "") for i, h in enumerate(cabeceras)}
    ws.delete_rows(fila)
    return info


def actualizar_categoria_ultimo(quien: str, nueva_categoria: str) -> Optional[dict]:
    ws = _ws()
    fila = _ultima_fila_de(ws, quien)
    if fila is None:
        return None
    ws.update_cell(fila, COL_CATEGORIA, nueva_categoria)
    valores = ws.row_values(fila)
    cabeceras = ws.row_values(1)
    return {h: (valores[i] if i < len(valores) else "") for i, h in enumerate(cabeceras)}
