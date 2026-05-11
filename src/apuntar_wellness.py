"""
apuntar_wellness.py — Inserta o actualiza una fila en la hoja WELLNESS.

Uso:
  /usr/bin/python3 src/apuntar_wellness.py JUGADOR FECHA \\
      [--sueno N] [--fatiga N] [--molestias N] [--animo N]

Ejemplos:
  /usr/bin/python3 src/apuntar_wellness.py PIRATA 2026-05-11 \\
      --sueno 4 --fatiga 3 --molestias 4 --animo 5
  /usr/bin/python3 src/apuntar_wellness.py JAVI 2026-05-11 --molestias 2 --animo 3
  /usr/bin/python3 src/apuntar_wellness.py CECILIO 2026-05-11 \\
      --sueno 4 --fatiga 4 --molestias 4 --animo 4 --dry-run

Argumentos:
  JUGADOR   En mayúsculas (HERRERO, GARCIA, etc.). Acepta aliases típicos
            (J.Herrero, Gonza, etc.) via aliases_jugadores.py.
  FECHA     YYYY-MM-DD.

Flags (1-5 cada uno, opcional individualmente):
  --sueno N      Sueño (1 = mal, 5 = bien).
  --fatiga N     Fatiga (1 = agotado, 5 = fresco).
  --molestias N  Molestias musculares (1 = mucho dolor, 5 = sin molestias).
  --animo N      Ánimo (1 = bajo, 5 = alto).
  --dry-run      No escribe, solo muestra qué haría.

Comportamiento:
  · Si existe fila JUGADOR+FECHA → actualiza solo las columnas
    proporcionadas (las omitidas se mantienen).
  · Si no existe → añade fila nueva.
  · TOTAL = sueno + fatiga + molestias + animo (4-20).
  · Idempotente: si los valores ya están, no hace nada.

Nota: Wellness se reporta UNA VEZ al día (no por turno). El form PRE
del primer entrenamiento del día es donde lo rellenan los jugadores.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "src"))
from aliases_jugadores import norm_jugador  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"

CAMPOS_WELLNESS = ("sueno", "fatiga", "molestias", "animo")
CAMPOS_COLUMNAS = {
    "sueno": ("SUENO", "SUEÑO"),
    "fatiga": ("FATIGA",),
    "molestias": ("MOLESTIAS",),
    "animo": ("ANIMO", "ÁNIMO"),
}


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _idx_col(cabecera, nombres):
    def norm(s):
        return ((s or "").strip().upper()
                .replace("Á", "A").replace("É", "E").replace("Í", "I")
                .replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N"))
    objetivos = {norm(n) for n in nombres}
    for i, c in enumerate(cabecera):
        if norm(c) in objetivos:
            return i
    return None


def _parsear_score(v, nombre_campo):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        n = float(s.replace(",", "."))
    except ValueError:
        raise ValueError(f"{nombre_campo} inválido: {v!r}. Debe ser número 1-5.")
    if not (1 <= n <= 5):
        raise ValueError(f"{nombre_campo} fuera de rango (1-5): {n}")
    if n == int(n):
        return str(int(n))
    return str(n)


def actualizar_wellness(ss, jugador, fecha, valores, dry):
    """valores: dict {sueno, fatiga, molestias, animo} con strings o None."""
    ws = ss.worksheet("WELLNESS")
    rows = ws.get_all_values()
    if not rows:
        return "WELLNESS: hoja vacía"
    cabecera = rows[0]
    i_fecha = _idx_col(cabecera, ["FECHA"])
    i_jug = _idx_col(cabecera, ["JUGADOR"])
    if i_fecha is None or i_jug is None:
        return f"WELLNESS: cabecera no reconocida ({cabecera[:6]})"

    i_campos = {}
    for campo, alias_cols in CAMPOS_COLUMNAS.items():
        i_campos[campo] = _idx_col(cabecera, list(alias_cols))
    i_total = _idx_col(cabecera, ["TOTAL"])

    fila_idx = None
    for n, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_fecha, i_jug):
            continue
        if r[i_fecha].strip() == fecha and r[i_jug].strip().upper() == jugador:
            fila_idx = n
            break

    if fila_idx is not None:
        fila_actual = rows[fila_idx - 1]
        updates = []
        for campo, val in valores.items():
            if val is None:
                continue
            col = i_campos.get(campo)
            if col is None:
                continue
            actual = (fila_actual[col] if len(fila_actual) > col else "")
            if actual.strip() != val:
                updates.append((col, val, actual))

        # Recalcular TOTAL si tenemos al menos un valor o si ya había todos
        nuevos_valores = {}
        for campo in CAMPOS_WELLNESS:
            col = i_campos.get(campo)
            if col is None:
                continue
            v_nuevo = valores.get(campo)
            if v_nuevo is not None:
                nuevos_valores[campo] = v_nuevo
            else:
                nuevos_valores[campo] = (
                    fila_actual[col] if len(fila_actual) > col else ""
                ).strip()

        nums = []
        for v in nuevos_valores.values():
            try:
                nums.append(float(str(v).replace(",", ".")))
            except (ValueError, TypeError):
                pass
        nuevo_total = str(int(sum(nums))) if len(nums) == 4 else ""

        if i_total is not None and nuevo_total:
            actual_total = (fila_actual[i_total]
                            if len(fila_actual) > i_total else "")
            if actual_total.strip() != nuevo_total:
                updates.append((i_total, nuevo_total, actual_total))

        if not updates:
            return f"WELLNESS: fila {fila_idx} ya tenía esos valores"
        if dry:
            partes = [f"col {cabecera[c]} {v_old!r} → {v_new!r}"
                      for c, v_new, v_old in updates]
            return f"WELLNESS (dry-run) fila {fila_idx}: " + "; ".join(partes)
        for c, v_new, _ in updates:
            ws.update_cell(fila_idx, c + 1, v_new)
        return (f"WELLNESS: fila {fila_idx} actualizada en "
                f"{[cabecera[c] for c, _, _ in updates]}")
    else:
        nueva = [""] * len(cabecera)
        nueva[i_fecha] = fecha
        nueva[i_jug] = jugador
        nums = []
        for campo, val in valores.items():
            col = i_campos.get(campo)
            if col is not None and val is not None:
                nueva[col] = val
                try:
                    nums.append(float(val.replace(",", ".")))
                except (ValueError, TypeError):
                    pass
        if i_total is not None and len(nums) == 4:
            nueva[i_total] = str(int(sum(nums)))
        if dry:
            return f"WELLNESS (dry-run): añadiría fila nueva {nueva}"
        ws.append_row(nueva, value_input_option="USER_ENTERED")
        return f"WELLNESS: fila nueva añadida {nueva}"


def main():
    ap = argparse.ArgumentParser(description="Apunta o actualiza wellness.")
    ap.add_argument("jugador")
    ap.add_argument("fecha")
    ap.add_argument("--sueno", default=None, help="1-5")
    ap.add_argument("--fatiga", default=None, help="1-5")
    ap.add_argument("--molestias", default=None, help="1-5")
    ap.add_argument("--animo", default=None, help="1-5")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jugador = norm_jugador(args.jugador.strip())
    fecha = args.fecha.strip()
    if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
        print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
        sys.exit(2)

    try:
        valores = {
            "sueno": _parsear_score(args.sueno, "Sueño"),
            "fatiga": _parsear_score(args.fatiga, "Fatiga"),
            "molestias": _parsear_score(args.molestias, "Molestias"),
            "animo": _parsear_score(args.animo, "Ánimo"),
        }
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(2)

    if all(v is None for v in valores.values()):
        print("❌ Tienes que pasar al menos uno de --sueno/--fatiga/--molestias/--animo.")
        sys.exit(2)

    ss = _open_sheet()
    msg = actualizar_wellness(ss, jugador, fecha, valores, args.dry_run)

    print(MSG_SEP)
    cab = "💤 *Wellness actualizado*" if not args.dry_run else "🔍 *Dry-run WELLNESS*"
    partes = []
    for campo in CAMPOS_WELLNESS:
        v = valores.get(campo)
        if v is not None:
            partes.append(f"{campo}=*{v}*")
    print(
        f"{cab}\n\n"
        f"Jugador: *{jugador}*  ·  Fecha: {fecha}\n"
        f"{' · '.join(partes)}\n\n"
        f"• {msg}"
    )


if __name__ == "__main__":
    main()
