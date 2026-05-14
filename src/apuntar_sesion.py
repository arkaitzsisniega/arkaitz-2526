"""
apuntar_sesion.py — Inserta o actualiza una sesión en SESIONES.

Hermano directo de parse_sesion_voz.py (que parsea voz a JSON).
Aquí recibes los parámetros por CLI sin intermediarios, ideal para que
Alfred llame esto cuando ya sabe los datos exactos.

Uso:
  /usr/bin/python3 src/apuntar_sesion.py FECHA TURNO TIPO MIN [--comp X] \\
      [--dry-run]

Ejemplos:
  /usr/bin/python3 src/apuntar_sesion.py 2026-05-12 M TEC-TAC 75
  /usr/bin/python3 src/apuntar_sesion.py 2026-05-12 T GYM+TEC-TAC 90
  /usr/bin/python3 src/apuntar_sesion.py 2026-05-15 T PARTIDO 40 --comp LIGA
  /usr/bin/python3 src/apuntar_sesion.py 2026-05-12 M TEC-TAC 75 --dry-run

Argumentos:
  FECHA   YYYY-MM-DD.
  TURNO   M / T / P (M=mañana, T=tarde, P=partido).
  TIPO    FISICO · TEC-TAC · GYM · RECUP · PARTIDO · PORTEROS ·
          MATINAL · GYM+TEC-TAC · FISICO+TEC-TAC.
  MIN     Duración en minutos (entero).

Flags:
  --comp NOMBRE   Competición (solo para PARTIDO/AMISTOSO).
                  LIGA · COPA DEL REY · COPA ESPAÑA · COPA MOSTOLES ·
                  COPA RIBERA · SUPERCOPA · PRE-TEMPORADA · AMISTOSO.
  --dry-run       No escribe, solo muestra qué haría.

Comportamiento:
  · Si existe fila (FECHA + TURNO + TIPO) → actualiza esa fila.
  · Si no existe → añade nueva.
  · Calcula SEMANA ISO automáticamente.
  · Idempotente.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime
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

TIPOS_VALIDOS = [
    "FISICO", "TEC-TAC", "GYM", "RECUP", "PARTIDO", "PORTEROS",
    "MATINAL", "GYM+TEC-TAC", "FISICO+TEC-TAC",
]
TURNOS_VALIDOS = ["M", "T", "P"]
COMPETICIONES_VALIDAS = [
    "LIGA", "COPA DEL REY", "COPA ESPAÑA", "COPA MOSTOLES",
    "COPA RIBERA", "SUPERCOPA", "PRE-TEMPORADA", "AMISTOSO",
]


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _semana_iso(fecha_iso: str) -> str:
    d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    return str(d.isocalendar().week)


def apuntar_en_sesiones(ss, fecha_iso, turno, tipo_sesion, minutos,
                         competicion, dry=False, hora_inicio: str = "") -> str:
    """Inserta o actualiza una fila en SESIONES (columnas A-G).

    A=FECHA, B=SEMANA, C=TURNO, D=TIPO, E=MINUTOS, F=COMPETICION, G=HORA_INICIO.

    Si `hora_inicio` viene vacío, NO sobrescribe la hora existente en
    el caso de actualización — solo añade hora_inicio cuando se proporciona
    explícitamente (así una llamada vieja sin --hora no borra una hora
    apuntada previamente).
    """
    ws = ws_sesiones = ss.worksheet("SESIONES")
    rows = ws.get_all_values()
    d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    fecha_alt = d.strftime("%d-%m-%Y")

    # Defensa: asegurar cabecera G1 = HORA_INICIO (idempotente, no hace
    # nada si ya está).
    cab = rows[0] if rows else []
    if len(cab) < 7 or (len(cab) >= 7 and cab[6] != "HORA_INICIO"):
        if not dry and len(cab) < 7:
            try:
                ws.update_cell(1, 7, "HORA_INICIO")
                rows = ws.get_all_values()  # recargar
            except Exception:
                pass

    row_idx = None
    for i, r in enumerate(rows[1:], start=2):
        if (r and len(r) >= 4
                and r[0].strip() in (fecha_iso, fecha_alt)
                and r[2].strip() == turno
                and r[3].strip() == tipo_sesion):
            row_idx = i
            break
    semana = _semana_iso(fecha_iso)
    base = [fecha_iso, semana, turno, tipo_sesion,
            str(minutos) if minutos is not None else "",
            competicion or ""]

    if row_idx is not None:
        actual = rows[row_idx - 1]
        # Determinar hora final: si vienen vacía, preservar la existente
        hora_existente = actual[6].strip() if len(actual) > 6 else ""
        hora_final = hora_inicio if hora_inicio else hora_existente
        fila = base + [hora_final]
        actual_padded = (actual + [""] * 7)[:7]
        if actual_padded == fila:
            return f"SESIONES: fila {row_idx} ya estaba con esos valores"
        if dry:
            return (f"SESIONES (dry-run): actualizaría fila {row_idx} "
                    f"de {actual_padded} a {fila}")
        ws.update(values=[fila], range_name=f"A{row_idx}:G{row_idx}")
        return f"SESIONES: fila {row_idx} actualizada → {fila}"
    else:
        next_row = len(rows) + 1
        fila = base + [hora_inicio]
        if dry:
            return f"SESIONES (dry-run): añadiría fila nueva {next_row} → {fila}"
        ws.update(values=[fila], range_name=f"A{next_row}:G{next_row}")
        return f"SESIONES: fila nueva {next_row} → {fila}"


def main():
    ap = argparse.ArgumentParser(description="Apunta una sesión en SESIONES.")
    ap.add_argument("fecha", help="YYYY-MM-DD")
    ap.add_argument("turno", help="M / T / P")
    ap.add_argument("tipo", help=f"Tipo: {' · '.join(TIPOS_VALIDOS)}")
    ap.add_argument("minutos", help="Duración en minutos (entero)")
    ap.add_argument("--comp", default="",
                     help=f"Competición (solo PARTIDO/AMISTOSO): {' · '.join(COMPETICIONES_VALIDAS)}")
    ap.add_argument("--hora", default="",
                     help="Hora de inicio en formato HH:MM (24h). Opcional.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fecha = args.fecha.strip()
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
        sys.exit(2)

    turno = args.turno.strip().upper()
    if turno not in TURNOS_VALIDOS:
        print(f"❌ Turno inválido: {turno!r}. Usa: {TURNOS_VALIDOS}.")
        sys.exit(2)

    tipo = args.tipo.strip().upper()
    if tipo not in TIPOS_VALIDOS:
        print(f"❌ Tipo inválido: {tipo!r}. Válidos: {TIPOS_VALIDOS}.")
        sys.exit(2)

    try:
        mins = int(args.minutos)
        if mins <= 0 or mins > 300:
            raise ValueError(f"Minutos fuera de rango (1-300): {mins}")
    except ValueError as e:
        print(f"❌ Minutos inválidos: {args.minutos!r} ({e})")
        sys.exit(2)

    comp = args.comp.strip().upper() if args.comp else ""
    if comp and comp not in COMPETICIONES_VALIDAS:
        # Intentar match aproximado por substring
        match = None
        for c in COMPETICIONES_VALIDAS:
            if c in comp or comp in c:
                match = c
                break
        if match:
            comp = match
        else:
            print(f"⚠️ Competición no reconocida: {args.comp!r}. "
                  f"Válidas: {COMPETICIONES_VALIDAS}. Se guarda igual.")
    # Si tipo=PARTIDO y no hay comp, avisar pero no bloquear
    if tipo == "PARTIDO" and not comp:
        print(f"⚠️ Tipo=PARTIDO sin --comp. Se guarda sin competición.")

    # Validar --hora (opcional). Acepta HH:MM 24h (admite "9:15" sin
    # leading zero; se normaliza a "09:15").
    hora_inicio = args.hora.strip() if args.hora else ""
    if hora_inicio:
        try:
            dt = datetime.strptime(hora_inicio, "%H:%M")
            hora_inicio = dt.strftime("%H:%M")  # normaliza a HH:MM
        except ValueError:
            print(f"❌ Hora inválida: {args.hora!r}. Usa HH:MM (24h), ej. 18:00.")
            sys.exit(2)

    ss = _open_sheet()
    msg = apuntar_en_sesiones(ss, fecha, turno, tipo, mins, comp,
                                 args.dry_run, hora_inicio=hora_inicio)

    print(MSG_SEP)
    cab = "📋 *Sesión apuntada*" if not args.dry_run else "🔍 *Dry-run SESIÓN*"
    extras = ""
    if comp:
        extras += f"  ·  {comp}"
    if hora_inicio:
        extras += f"  ·  🕐 {hora_inicio}"
    print(
        f"{cab}\n\n"
        f"📅 {fecha}  ·  Turno *{turno}*  ·  Tipo *{tipo}*  ·  "
        f"{mins} min{extras}\n\n"
        f"• {msg}"
    )


if __name__ == "__main__":
    main()
