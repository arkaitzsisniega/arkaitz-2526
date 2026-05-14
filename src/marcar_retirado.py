"""
marcar_retirado.py — Marca a un jugador como "retirado a mitad de sesión
por lesión / molestia". Distinto de marcar_lesion.py:

- marcar_lesion.py = el jugador NO entrenó (Borg='L').
- marcar_retirado.py = el jugador SÍ entrenó parte (Borg numérico) PERO
  se retiró antes de acabar. Queda registrada la incidencia para que
  aparezca en el Semáforo y en el Recuento.

Uso:
  /usr/bin/python3 src/marcar_retirado.py JUGADOR FECHA MINUTO MOTIVO [TURNO]

  JUGADOR  HERRERO, PANI, etc.
  FECHA    YYYY-MM-DD.
  MINUTO   Minuto de la sesión en que se retiró (entero).
  MOTIVO   Texto libre entre comillas. Ej: "gemelo derecho", "tirón aductor".
  TURNO    M o T. Si se omite, se autodetecta de SESIONES.

Flags:
  --borg N      Valor de Borg que reportó (si lo dio). Por defecto se
                deja la fila BORG sin valor numérico (queda como "NC").
  --dry-run     No escribe nada, solo enseña qué haría.
  --no-lesion   No añade fila a LESIONES (solo BORG.INCIDENCIA).

Comportamiento:
1. Asegura que BORG tiene columna `INCIDENCIA` (la crea si no existe).
2. Apunta/actualiza la fila BORG del jugador-fecha-turno con:
   - BORG = valor si --borg dado, "NC" si no.
   - INCIDENCIA = "Retirado min N - <motivo>".
3. Si --no-lesion NO está, añade fila a LESIONES con la fecha y motivo
   (idempotente: no duplica si ya hay fila para JUGADOR + FECHA).
4. Imprime resumen tras MSG_SEP.
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


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def detectar_turno(ss, fecha: str) -> str:
    """Autodetecta TURNO mirando SESIONES para esa fecha.
    Si hay 1 sesión, usa su turno. Si hay 2, devuelve 'M' (primera). Si no hay, 'M'."""
    try:
        rows = ss.worksheet("SESIONES").get_all_records()
        del_fecha = [r for r in rows if str(r.get("FECHA", "")).strip() == fecha]
        if not del_fecha:
            return "M"
        if len(del_fecha) == 1:
            return str(del_fecha[0].get("TURNO", "M")).strip().upper() or "M"
        # Múltiples → M
        return "M"
    except Exception:
        return "M"


def asegurar_columna_incidencia(ws) -> int:
    """Si la hoja BORG no tiene columna INCIDENCIA, la añade al final.
    Devuelve el índice (1-based) de la columna."""
    headers = ws.row_values(1)
    if "INCIDENCIA" in headers:
        return headers.index("INCIDENCIA") + 1
    # Añadir al final
    next_col = len(headers) + 1
    ws.update_cell(1, next_col, "INCIDENCIA")
    return next_col


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jugador")
    ap.add_argument("fecha")     # YYYY-MM-DD
    ap.add_argument("minuto", type=int)
    ap.add_argument("motivo")    # texto libre
    ap.add_argument("turno", nargs="?", default=None)
    ap.add_argument("--borg", type=int, default=None,
                     help="Valor Borg numérico si lo reportó")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-lesion", action="store_true",
                     help="No añadir fila a LESIONES (solo INCIDENCIA en BORG)")
    args = ap.parse_args()

    jugador = args.jugador.strip().upper()
    fecha = args.fecha.strip()
    minuto = args.minuto
    motivo = args.motivo.strip()
    incidencia = f"Retirado min {minuto} - {motivo}"

    ss = conectar()
    turno = args.turno.strip().upper() if args.turno else detectar_turno(ss, fecha)

    cambios = []
    # ── BORG ──
    borg_ws = ss.worksheet("BORG")
    col_incid = asegurar_columna_incidencia(borg_ws)
    headers = borg_ws.row_values(1)
    idx_fecha = headers.index("FECHA") + 1
    idx_turno = headers.index("TURNO") + 1
    idx_jug = headers.index("JUGADOR") + 1
    idx_borg = headers.index("BORG") + 1

    todas = borg_ws.get_all_values()
    fila_encontrada = None
    for i, row in enumerate(todas[1:], start=2):
        f_v = row[idx_fecha - 1] if len(row) >= idx_fecha else ""
        t_v = row[idx_turno - 1] if len(row) >= idx_turno else ""
        j_v = row[idx_jug - 1] if len(row) >= idx_jug else ""
        if str(f_v).strip() == fecha and str(t_v).strip().upper() == turno \
           and str(j_v).strip().upper() == jugador:
            fila_encontrada = i
            break

    valor_borg = str(args.borg) if args.borg is not None else "NC"
    if fila_encontrada:
        cambios.append(f"Actualizar BORG fila {fila_encontrada}: BORG={valor_borg}, INCIDENCIA={incidencia!r}")
        if not args.dry_run:
            borg_ws.update_cell(fila_encontrada, idx_borg, valor_borg)
            borg_ws.update_cell(fila_encontrada, col_incid, incidencia)
    else:
        # Construir fila completa con valores en su sitio
        nueva = [""] * len(headers)
        nueva[idx_fecha - 1] = fecha
        nueva[idx_turno - 1] = turno
        nueva[idx_jug - 1] = jugador
        nueva[idx_borg - 1] = valor_borg
        nueva[col_incid - 1] = incidencia
        cambios.append(f"Añadir fila nueva a BORG: {fecha} {turno} {jugador} BORG={valor_borg} INCIDENCIA={incidencia!r}")
        if not args.dry_run:
            borg_ws.append_row(nueva)

    # ── LESIONES ──
    if not args.no_lesion:
        try:
            les_ws = ss.worksheet("LESIONES")
            # Cabecera en fila 2
            les_vals = les_ws.get_all_values()
            if len(les_vals) >= 2:
                hdr = les_vals[1]
                try:
                    idx_les_jug = hdr.index("JUGADOR")
                except ValueError:
                    idx_les_jug = -1
                try:
                    # Probar variantes del nombre de columna
                    for nombre_col in ("FECHA LESIÓN", "FECHA LESION", "FECHA"):
                        if nombre_col in hdr:
                            idx_les_fecha = hdr.index(nombre_col)
                            break
                    else:
                        idx_les_fecha = -1
                except Exception:
                    idx_les_fecha = -1

                ya_existe = False
                if idx_les_jug >= 0 and idx_les_fecha >= 0:
                    for row in les_vals[2:]:
                        if len(row) > max(idx_les_jug, idx_les_fecha) and \
                           row[idx_les_jug].strip().upper() == jugador and \
                           row[idx_les_fecha].strip() == fecha:
                            ya_existe = True
                            break

                if not ya_existe:
                    nueva_les = [""] * len(hdr)
                    if idx_les_jug >= 0:
                        nueva_les[idx_les_jug] = jugador
                    if idx_les_fecha >= 0:
                        nueva_les[idx_les_fecha] = fecha
                    # Buscar columna de tipo / motivo / observaciones
                    for nombre_col in ("TIPO LESIÓN", "TIPO LESION", "MOTIVO",
                                         "OBSERVACIONES", "NOTAS"):
                        if nombre_col in hdr:
                            nueva_les[hdr.index(nombre_col)] = motivo
                            break
                    cambios.append(f"Añadir fila a LESIONES: {jugador} {fecha} - {motivo}")
                    if not args.dry_run:
                        les_ws.append_row(nueva_les)
                else:
                    cambios.append(f"LESIONES: ya existe entrada para {jugador} {fecha}, no añado.")
        except Exception as e:
            cambios.append(f"⚠ LESIONES no actualizada: {e}")

    # ── Resumen ──
    print(MSG_SEP)
    head = "🔬 *DRY-RUN — sin escribir*" if args.dry_run else "✅ *Retirada apuntada*"
    print(head)
    print(f"Jugador: *{jugador}*  ·  Fecha: *{fecha}*  ·  Turno: *{turno}*")
    print(f"Incidencia: _{incidencia}_")
    if args.borg is not None:
        print(f"Borg reportado: *{args.borg}*")
    print()
    for c in cambios:
        print(f"  • {c}")
    if not args.dry_run:
        print()
        print(MSG_SEP)
        print("Recalcula vistas: lanza `/consolidar` o espera al próximo recálculo.")


if __name__ == "__main__":
    main()
