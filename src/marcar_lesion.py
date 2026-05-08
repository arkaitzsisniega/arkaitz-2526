"""
marcar_lesion.py — Marca a un jugador como lesionado escribiendo en
ambas hojas: BORG (con código 'L') y LESIONES (fila nueva).

Uso:
  /usr/bin/python3 src/marcar_lesion.py JUGADOR FECHA [TURNO]
  /usr/bin/python3 src/marcar_lesion.py PANI 2026-05-08 M
  /usr/bin/python3 src/marcar_lesion.py PANI 2026-05-08 --dry-run

Argumentos:
  JUGADOR   En mayúsculas (HERRERO, PANI, etc.).
  FECHA     YYYY-MM-DD.
  TURNO     M o T. Si se omite, se busca en SESIONES; si hay varios, M.

Flags:
  --dry-run     No escribe nada, solo enseña qué haría.
  --tipo TXT    Tipo de lesión opcional (rellena columna TIPO LESIÓN).
  --zona TXT    Zona corporal opcional.
  --lado TXT    Lado opcional (IZQ/DER).

Comportamiento:
  · BORG: si existe fila para JUGADOR+FECHA+TURNO, actualiza columna BORG a 'L'.
          Si no existe, añade fila nueva [FECHA, TURNO, JUGADOR, 'L'].
  · LESIONES: si NO existe fila previa para JUGADOR+FECHA, añade
              [JUGADOR, FECHA, MOMENTO, TIPO, ZONA, LADO]. Idempotente.

Imprime resumen por stdout con MSG_SEP para que el bot lo capte.
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
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _resolver_turno(ss, fecha: str, turno: str | None) -> str:
    """Si turno viene dado, lo respeta. Si no, mira SESIONES de la fecha
    y devuelve 'M' por defecto si hay varios o ninguno."""
    if turno:
        return turno.upper()
    try:
        ws = ss.worksheet("SESIONES")
        rows = ws.get_all_values()
        # cabecera fila 1: FECHA, ID, TURNO, ...
        turnos = [r[2] for r in rows[1:] if len(r) >= 3 and r[0] == fecha]
        turnos = [t for t in turnos if t]
        if len(turnos) == 1:
            return turnos[0].upper()
    except Exception:
        pass
    return "M"


def _idx_col(cabecera: list[str], nombres: list[str]) -> int | None:
    """Devuelve el índice (0-based) de la primera columna cuya cabecera
    coincida (case-insensitive, sin acentos básicos) con cualquiera de
    `nombres`. None si no se encuentra."""
    def norm(s: str) -> str:
        return (
            (s or "")
            .strip()
            .upper()
            .replace("Á", "A").replace("É", "E").replace("Í", "I")
            .replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N")
        )
    objetivos = {norm(n) for n in nombres}
    for i, c in enumerate(cabecera):
        if norm(c) in objetivos:
            return i
    return None


def actualizar_borg(ss, jugador: str, fecha: str, turno: str, dry: bool) -> str:
    ws = ss.worksheet("BORG")
    rows = ws.get_all_values()
    if not rows:
        return "BORG: hoja vacía, abortando"
    cabecera = rows[0]
    i_fecha = _idx_col(cabecera, ["FECHA"])
    i_turno = _idx_col(cabecera, ["TURNO"])
    i_jug = _idx_col(cabecera, ["JUGADOR"])
    i_borg = _idx_col(cabecera, ["BORG"])
    if None in (i_fecha, i_turno, i_jug, i_borg):
        return f"BORG: cabecera no reconocida ({cabecera[:6]})"

    fila_idx = None  # 1-based en gspread
    for n, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_fecha, i_turno, i_jug):
            continue
        if (
            r[i_fecha].strip() == fecha
            and r[i_turno].strip().upper() == turno
            and r[i_jug].strip().upper() == jugador
        ):
            fila_idx = n
            break

    if fila_idx is not None:
        valor_actual = rows[fila_idx - 1][i_borg] if len(rows[fila_idx - 1]) > i_borg else ""
        if valor_actual.strip().upper() == "L":
            return f"BORG: fila {fila_idx} ya estaba como 'L' (sin cambios)"
        if dry:
            return f"BORG (dry-run): actualizaría fila {fila_idx} columna {i_borg+1} de '{valor_actual}' a 'L'"
        ws.update_cell(fila_idx, i_borg + 1, "L")
        return f"BORG: fila {fila_idx} actualizada (era '{valor_actual}' → ahora 'L')"
    else:
        nueva = [""] * len(cabecera)
        nueva[i_fecha] = fecha
        nueva[i_turno] = turno
        nueva[i_jug] = jugador
        nueva[i_borg] = "L"
        if dry:
            return f"BORG (dry-run): añadiría fila nueva {nueva}"
        ws.append_row(nueva, value_input_option="USER_ENTERED")
        return f"BORG: fila nueva añadida {nueva}"


def actualizar_lesiones(
    ss,
    jugador: str,
    fecha: str,
    momento: str = "",
    tipo: str = "",
    zona: str = "",
    lado: str = "",
    dry: bool = False,
) -> str:
    ws = ss.worksheet("LESIONES")
    rows = ws.get_all_values()
    if not rows:
        return "LESIONES: hoja vacía, abortando"

    # Cabecera real (puede estar en fila 1 o fila 2)
    cab_idx = 0
    if rows[0] and not any(c.strip().upper() == "JUGADOR" for c in rows[0]):
        # buscar la primera fila con "JUGADOR"
        for i, r in enumerate(rows[:5]):
            if any((c or "").strip().upper() == "JUGADOR" for c in r):
                cab_idx = i
                break
    cabecera = rows[cab_idx]

    i_jug = _idx_col(cabecera, ["JUGADOR"])
    i_fecha = _idx_col(cabecera, ["FECHA LESION", "FECHA LESIÓN", "FECHA"])
    i_mom = _idx_col(cabecera, ["MOMENTO"])
    i_tipo = _idx_col(cabecera, ["TIPO LESION", "TIPO LESIÓN", "TIPO"])
    i_zona = _idx_col(cabecera, ["ZONA CORPORAL", "ZONA"])
    i_lado = _idx_col(cabecera, ["LADO"])

    if i_jug is None or i_fecha is None:
        return f"LESIONES: cabecera no reconocida ({cabecera[:6]})"

    # Comprobar duplicado: misma jugador+fecha
    for r in rows[cab_idx + 1:]:
        if len(r) <= max(i_jug, i_fecha):
            continue
        if (
            r[i_jug].strip().upper() == jugador
            and r[i_fecha].strip() == fecha
        ):
            return f"LESIONES: ya existía fila para {jugador} {fecha} (sin cambios)"

    nueva = [""] * len(cabecera)
    nueva[i_jug] = jugador
    nueva[i_fecha] = fecha
    if i_mom is not None and momento:
        nueva[i_mom] = momento
    if i_tipo is not None and tipo:
        nueva[i_tipo] = tipo
    if i_zona is not None and zona:
        nueva[i_zona] = zona
    if i_lado is not None and lado:
        nueva[i_lado] = lado

    if dry:
        return f"LESIONES (dry-run): añadiría fila {nueva}"
    ws.append_row(nueva, value_input_option="USER_ENTERED")
    return f"LESIONES: fila nueva añadida {nueva}"


def main():
    ap = argparse.ArgumentParser(description="Marca un jugador como lesionado en BORG + LESIONES.")
    ap.add_argument("jugador", help="JUGADOR en mayúsculas")
    ap.add_argument("fecha", help="YYYY-MM-DD")
    ap.add_argument("turno", nargs="?", default=None, help="M o T (opcional)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tipo", default="")
    ap.add_argument("--zona", default="")
    ap.add_argument("--lado", default="")
    ap.add_argument("--momento", default="")
    args = ap.parse_args()

    jugador = args.jugador.strip().upper()
    fecha = args.fecha.strip()
    # Validación mínima
    if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
        print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
        sys.exit(2)

    ss = _open_sheet()
    turno = _resolver_turno(ss, fecha, args.turno)

    msg_borg = actualizar_borg(ss, jugador, fecha, turno, args.dry_run)
    msg_les = actualizar_lesiones(
        ss, jugador, fecha,
        momento=args.momento, tipo=args.tipo, zona=args.zona, lado=args.lado,
        dry=args.dry_run,
    )

    print(MSG_SEP)
    cabecera = "🚑 *Lesión registrada*" if not args.dry_run else "🔍 *Dry-run: simulación*"
    print(
        f"{cabecera}\n\n"
        f"Jugador: *{jugador}*\n"
        f"Fecha: {fecha}  ·  Turno: {turno}\n\n"
        f"• {msg_borg}\n"
        f"• {msg_les}"
    )


if __name__ == "__main__":
    main()
