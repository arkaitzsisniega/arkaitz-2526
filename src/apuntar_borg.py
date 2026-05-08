"""
apuntar_borg.py — Inserta o actualiza una entrada en la hoja BORG.

Uso:
  /usr/bin/python3 src/apuntar_borg.py JUGADOR FECHA BORG [TURNO]

Ejemplos:
  /usr/bin/python3 src/apuntar_borg.py CARLOS 2026-05-08 7
  /usr/bin/python3 src/apuntar_borg.py PIRATA 2026-05-08 8 T
  /usr/bin/python3 src/apuntar_borg.py PANI 2026-05-08 S    # Selección
  /usr/bin/python3 src/apuntar_borg.py JAVI 2026-05-08 D --dry-run

Argumentos:
  JUGADOR   En mayúsculas (CARLOS, PIRATA, JAVI, etc.).
  FECHA     YYYY-MM-DD.
  BORG      Número 1-10 o letra de estado:
              S  = Selección nacional
              A  = Ausencia (no convocado)
              L  = Lesión (mejor usar marcar_lesion.py)
              N  = No entrena
              D  = Descanso (rotación)
              NC = No calificado
  TURNO     M o T. Si se omite, se busca en SESIONES; si no hay match, M.

Flags:
  --dry-run         No escribe, solo muestra qué haría.

Comportamiento:
  · Si existe fila JUGADOR+FECHA+TURNO → actualiza columna BORG.
  · Si no existe → añade fila nueva [FECHA, TURNO, JUGADOR, BORG].
  · Idempotente: si el valor ya está, no hace nada.
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
ESTADOS_VALIDOS = {"S", "A", "L", "N", "D", "NC"}


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _resolver_turno(ss, fecha: str, turno: str | None) -> str:
    if turno:
        return turno.upper()
    try:
        ws = ss.worksheet("SESIONES")
        rows = ws.get_all_values()
        turnos = [r[2] for r in rows[1:] if len(r) >= 3 and r[0] == fecha]
        turnos = [t for t in turnos if t]
        if len(turnos) == 1:
            return turnos[0].upper()
    except Exception:
        pass
    return "M"


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


def _validar_borg(valor: str) -> str:
    """Devuelve el valor normalizado o lanza ValueError."""
    v = valor.strip().upper()
    if v in ESTADOS_VALIDOS:
        return v
    try:
        n = float(v.replace(",", "."))
    except ValueError:
        raise ValueError(
            f"BORG inválido: {valor!r}. Debe ser número 1-10 o "
            f"estado {sorted(ESTADOS_VALIDOS)}."
        )
    if not (0 < n <= 10):
        raise ValueError(f"BORG fuera de rango (1-10): {n}")
    if n == int(n):
        return str(int(n))
    return str(n)


def actualizar_borg(ss, jugador: str, fecha: str, turno: str,
                    valor: str, dry: bool) -> str:
    ws = ss.worksheet("BORG")
    rows = ws.get_all_values()
    if not rows:
        return "BORG: hoja vacía"
    cabecera = rows[0]
    i_fecha = _idx_col(cabecera, ["FECHA"])
    i_turno = _idx_col(cabecera, ["TURNO"])
    i_jug = _idx_col(cabecera, ["JUGADOR"])
    i_borg = _idx_col(cabecera, ["BORG"])
    if None in (i_fecha, i_turno, i_jug, i_borg):
        return f"BORG: cabecera no reconocida ({cabecera[:6]})"

    fila_idx = None
    for n, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_fecha, i_turno, i_jug):
            continue
        if (r[i_fecha].strip() == fecha
                and r[i_turno].strip().upper() == turno
                and r[i_jug].strip().upper() == jugador):
            fila_idx = n
            break

    if fila_idx is not None:
        actual = (rows[fila_idx - 1][i_borg]
                  if len(rows[fila_idx - 1]) > i_borg else "")
        if actual.strip().upper() == valor.upper():
            return f"BORG: fila {fila_idx} ya estaba en {valor!r} (sin cambios)"
        if dry:
            return (f"BORG (dry-run): actualizaría fila {fila_idx} "
                    f"de {actual!r} a {valor!r}")
        ws.update_cell(fila_idx, i_borg + 1, valor)
        return f"BORG: fila {fila_idx} actualizada ({actual!r} → {valor!r})"
    else:
        nueva = [""] * len(cabecera)
        nueva[i_fecha] = fecha
        nueva[i_turno] = turno
        nueva[i_jug] = jugador
        nueva[i_borg] = valor
        if dry:
            return f"BORG (dry-run): añadiría fila nueva {nueva}"
        ws.append_row(nueva, value_input_option="USER_ENTERED")
        return f"BORG: fila nueva añadida {nueva}"


def main():
    ap = argparse.ArgumentParser(description="Apunta o actualiza una fila en BORG.")
    ap.add_argument("jugador", help="JUGADOR en mayúsculas")
    ap.add_argument("fecha", help="YYYY-MM-DD")
    ap.add_argument("borg", help="número 1-10 o estado S/A/L/N/D/NC")
    ap.add_argument("turno", nargs="?", default=None, help="M o T (opcional)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jugador = args.jugador.strip().upper()
    fecha = args.fecha.strip()
    if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
        print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
        sys.exit(2)

    try:
        valor = _validar_borg(args.borg)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(2)

    ss = _open_sheet()
    turno = _resolver_turno(ss, fecha, args.turno)
    msg = actualizar_borg(ss, jugador, fecha, turno, valor, args.dry_run)

    print(MSG_SEP)
    cabecera = "📝 *BORG actualizado*" if not args.dry_run else "🔍 *Dry-run BORG*"
    print(
        f"{cabecera}\n\n"
        f"Jugador: *{jugador}*  ·  Fecha: {fecha}  ·  Turno: {turno}\n"
        f"BORG: *{valor}*\n\n"
        f"• {msg}"
    )


if __name__ == "__main__":
    main()
