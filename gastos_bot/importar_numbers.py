#!/usr/bin/env python3
"""
Importa los gastos de 2026 desde el archivo Numbers histórico al Sheet
de gastos comunes.

Pestañas a importar (las que tocan 2026): Enero26, Feb26, Mar26, Abr26.
Estructura: col A=fecha, col B=concepto, col C=cantidad.

Reglas:
  - Si la celda fecha está vacía, se hereda la última fecha escrita arriba
    (forward-fill, como hace el usuario en Numbers).
  - Si una fila tiene una fecha cuyo AÑO no coincide con el de la pestaña
    (típico typo de copiar mes anterior), se corrige al año de la pestaña.
  - Filas con concepto y cantidad pero sin fecha aún (no hemos visto
    ninguna) → se usa el día 1 del mes de la pestaña.
  - Se ignoran filas totalmente vacías y la fila de cabecera.

Uso:
  /usr/bin/python3 gastos_bot/importar_numbers.py --dry-run
  /usr/bin/python3 gastos_bot/importar_numbers.py --apply

El dry-run imprime cuántas filas se importarían y un preview, sin tocar
el Sheet. --apply escribe al Sheet.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")

from numbers_parser import Document  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from categorias import categorizar  # noqa: E402
import sheets  # noqa: E402

NUMBERS_PATH = "/Users/mac/Desktop/Gastos comunes.numbers"

# pestaña → (año, mes)
PESTAÑAS = {
    "Enero26": (2026, 1),
    "Feb26":   (2026, 2),
    "Mar26":   (2026, 3),
    "Abr26":   (2026, 4),
}

QUIEN = "Histórico"
NOTA_IMPORT = "import_numbers"


def cargar_filas() -> list[dict]:
    doc = Document(NUMBERS_PATH)
    salida: list[dict] = []
    for sheet in doc.sheets:
        if sheet.name not in PESTAÑAS:
            continue
        año_pest, mes_pest = PESTAÑAS[sheet.name]
        tbl = sheet.tables[0]
        ultima_fecha: _dt.date | None = None

        for row in tbl.rows(values_only=False):
            # row es lista de Cell. Esperamos 3 columnas: fecha, concepto, cantidad
            fecha_raw = row[0].value if len(row) > 0 else None
            concepto = row[1].value if len(row) > 1 else None
            cantidad = row[2].value if len(row) > 2 else None

            # Filas sin concepto y sin cantidad: ignorar
            if not concepto and cantidad in (None, ""):
                continue

            # Fecha: usar la del cell si existe; si no, forward-fill
            if isinstance(fecha_raw, _dt.datetime):
                fecha = fecha_raw.date()
            elif isinstance(fecha_raw, _dt.date):
                fecha = fecha_raw
            else:
                fecha = ultima_fecha

            # Corregir año si claramente no es el de la pestaña
            if fecha is not None and fecha.year != año_pest:
                try:
                    fecha = fecha.replace(year=año_pest)
                except ValueError:
                    # 29 feb que no existe en año destino: pasar al 28
                    fecha = fecha.replace(year=año_pest, day=28)

            # Si seguimos sin fecha (ninguna escrita aún en la pestaña): día 1 del mes
            if fecha is None:
                fecha = _dt.date(año_pest, mes_pest, 1)

            ultima_fecha = fecha

            # Validaciones de concepto/cantidad
            if not concepto:
                continue
            if cantidad in (None, ""):
                continue
            try:
                cantidad_f = float(cantidad)
            except (TypeError, ValueError):
                continue
            if cantidad_f <= 0:
                continue

            concepto_limpio = str(concepto).strip()
            categoria = categorizar(concepto_limpio)

            salida.append({
                "fecha": fecha,
                "concepto": concepto_limpio,
                "cantidad": round(cantidad_f, 2),
                "categoria": categoria,
                "pestaña_origen": sheet.name,
            })
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Escribe al Sheet")
    ap.add_argument("--dry-run", action="store_true", help="Solo previsualiza")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        print("Pasa --dry-run o --apply.")
        return 1

    filas = cargar_filas()
    print(f"Se importarían {len(filas)} filas:")
    print()
    # Resumen por pestaña
    from collections import Counter
    por_pest = Counter(f["pestaña_origen"] for f in filas)
    for nombre in PESTAÑAS:
        print(f"  {nombre}: {por_pest.get(nombre, 0)} filas")
    print()
    # Resumen por categoría
    por_cat = Counter(f["categoria"] for f in filas)
    print("Por categoría:")
    for cat, n in por_cat.most_common():
        print(f"  {cat}: {n}")
    print()
    # Total
    total = sum(f["cantidad"] for f in filas)
    print(f"Total importe: {total:,.2f}€")
    print()
    # Preview primeras 10
    print("Preview (primeras 10):")
    for f in filas[:10]:
        print(f"  {f['fecha']}  {f['concepto']:<25}  {f['cantidad']:>8.2f}€  [{f['categoria']}]")
    print("  ...")
    print("Preview (últimas 5):")
    for f in filas[-5:]:
        print(f"  {f['fecha']}  {f['concepto']:<25}  {f['cantidad']:>8.2f}€  [{f['categoria']}]")
    print()

    if args.dry_run:
        print("✋ Dry-run. No se ha escrito nada. Vuelve a ejecutar con --apply para escribir al Sheet.")
        return 0

    print("✍️  Escribiendo al Sheet…")
    # Bulk append: construir matriz y un solo append_rows (más rápido y barato en cuotas)
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    ROOT = HERE.parent
    creds = Credentials.from_service_account_file(str(ROOT / "google_credentials.json"), scopes=SCOPES)
    gc = gspread.authorize(creds)
    import os
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
    sh = gc.open_by_key(os.getenv("GASTOS_SHEET_ID", "").strip())
    ws = sh.worksheet("GASTOS")

    matriz = [
        [
            f["fecha"].strftime("%Y-%m-%d"),
            f["concepto"],
            f["cantidad"],
            f["categoria"],
            QUIEN,
            NOTA_IMPORT,
        ]
        for f in filas
    ]
    ws.append_rows(matriz, value_input_option="USER_ENTERED")
    print(f"✅ Escritas {len(matriz)} filas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
