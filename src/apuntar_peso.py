"""
apuntar_peso.py — Inserta o actualiza una fila en la hoja PESO.

Uso:
  /usr/bin/python3 src/apuntar_peso.py JUGADOR FECHA [TURNO] \\
      [--pre N] [--post N] [--h2o N]

Ejemplos:
  /usr/bin/python3 src/apuntar_peso.py CARLOS 2026-05-08 --pre 75.4
  /usr/bin/python3 src/apuntar_peso.py PIRATA 2026-05-08 T --pre 78.2 --post 77.5
  /usr/bin/python3 src/apuntar_peso.py JAVI 2026-05-08 --pre 71.0 --post 70.4 --h2o 45.2
  /usr/bin/python3 src/apuntar_peso.py PANI 2026-05-08 --pre 70.5 --dry-run

Argumentos:
  JUGADOR   En mayúsculas (CARLOS, PIRATA, JAVI, etc.).
  FECHA     YYYY-MM-DD.
  TURNO     M o T (opcional). Si se omite, se busca en SESIONES; default M.

Flags:
  --pre  N   Peso pre-entreno en kg (40-200). Coma o punto decimal OK.
  --post N   Peso post-entreno en kg.
  --h2o  N   Litros de agua corporal (opcional).
  --dry-run  No escribe, solo muestra qué haría.

Comportamiento:
  · Si existe fila JUGADOR+FECHA+TURNO → actualiza solo las columnas
    proporcionadas (las omitidas no se tocan).
  · Si no existe → añade fila nueva con los valores dados.
  · Validación fisiológica: pesos fuera de 40-200 kg se rechazan.
  · Idempotente: si los valores ya están, no hace nada.
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


def _parsear_peso(v):
    if v is None:
        return None
    txt = str(v).strip().replace(",", ".")
    if not txt:
        return None
    try:
        n = float(txt)
    except ValueError:
        raise ValueError(f"Valor numérico inválido: {v!r}")
    if not (40 <= n <= 200):
        raise ValueError(f"Peso fuera de rango fisiológico (40-200 kg): {n}")
    # Devolver como string sin .0 cuando sea entero
    return f"{n:g}"


def _parsear_h2o(v):
    if v is None:
        return None
    txt = str(v).strip().replace(",", ".")
    if not txt:
        return None
    try:
        n = float(txt)
    except ValueError:
        raise ValueError(f"H2O inválido: {v!r}")
    if not (10 <= n <= 100):
        raise ValueError(f"H2O fuera de rango (10-100 L): {n}")
    return f"{n:g}"


def actualizar_peso(ss, jugador, fecha, turno, pre, post, h2o, dry):
    ws = ss.worksheet("PESO")
    rows = ws.get_all_values()
    if not rows:
        return "PESO: hoja vacía"
    cabecera = rows[0]
    i_fecha = _idx_col(cabecera, ["FECHA"])
    i_turno = _idx_col(cabecera, ["TURNO"])
    i_jug = _idx_col(cabecera, ["JUGADOR"])
    i_pre = _idx_col(cabecera, ["PESO_PRE", "PESO PRE", "PRE"])
    i_post = _idx_col(cabecera, ["PESO_POST", "PESO POST", "POST"])
    i_h2o = _idx_col(cabecera, ["H2O_L", "H2O", "AGUA"])
    if None in (i_fecha, i_turno, i_jug, i_pre, i_post):
        return f"PESO: cabecera no reconocida ({cabecera[:6]})"

    fila_idx = None
    for n, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_fecha, i_turno, i_jug):
            continue
        if (r[i_fecha].strip() == fecha
                and r[i_turno].strip().upper() == turno
                and r[i_jug].strip().upper() == jugador):
            fila_idx = n
            break

    cambios = []
    if fila_idx is not None:
        fila_actual = rows[fila_idx - 1]
        updates = []
        if pre is not None:
            actual_pre = (fila_actual[i_pre] if len(fila_actual) > i_pre else "")
            if actual_pre.strip() != pre:
                updates.append((i_pre, pre, actual_pre))
        if post is not None:
            actual_post = (fila_actual[i_post] if len(fila_actual) > i_post else "")
            if actual_post.strip() != post:
                updates.append((i_post, post, actual_post))
        if h2o is not None and i_h2o is not None:
            actual_h2o = (fila_actual[i_h2o] if len(fila_actual) > i_h2o else "")
            if actual_h2o.strip() != h2o:
                updates.append((i_h2o, h2o, actual_h2o))
        if not updates:
            return f"PESO: fila {fila_idx} ya tenía esos valores (sin cambios)"
        if dry:
            for col, nuevo, viejo in updates:
                cambios.append(
                    f"PESO (dry-run): col {cabecera[col]} fila {fila_idx} "
                    f"{viejo!r} → {nuevo!r}"
                )
            return "; ".join(cambios)
        for col, nuevo, _viejo in updates:
            ws.update_cell(fila_idx, col + 1, nuevo)
        return (f"PESO: fila {fila_idx} actualizada en "
                f"{[cabecera[c] for c, _, _ in updates]}")
    else:
        if pre is None and post is None and h2o is None:
            return "PESO: no hay valores que añadir (omitido)"
        nueva = [""] * len(cabecera)
        nueva[i_fecha] = fecha
        nueva[i_turno] = turno
        nueva[i_jug] = jugador
        if pre is not None:
            nueva[i_pre] = pre
        if post is not None:
            nueva[i_post] = post
        if h2o is not None and i_h2o is not None:
            nueva[i_h2o] = h2o
        if dry:
            return f"PESO (dry-run): añadiría fila nueva {nueva}"
        ws.append_row(nueva, value_input_option="USER_ENTERED")
        return f"PESO: fila nueva añadida {nueva}"


def main():
    ap = argparse.ArgumentParser(description="Apunta o actualiza una fila en PESO.")
    ap.add_argument("jugador")
    ap.add_argument("fecha")
    ap.add_argument("turno", nargs="?", default=None)
    ap.add_argument("--pre", default=None, help="Peso PRE en kg")
    ap.add_argument("--post", default=None, help="Peso POST en kg")
    ap.add_argument("--h2o", default=None, help="Agua corporal en L")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jugador = args.jugador.strip().upper()
    fecha = args.fecha.strip()
    if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
        print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
        sys.exit(2)

    try:
        pre = _parsear_peso(args.pre)
        post = _parsear_peso(args.post)
        h2o = _parsear_h2o(args.h2o)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(2)

    if pre is None and post is None and h2o is None:
        print("❌ Tienes que pasar al menos --pre, --post o --h2o.")
        sys.exit(2)

    ss = _open_sheet()
    turno = _resolver_turno(ss, fecha, args.turno)
    msg = actualizar_peso(ss, jugador, fecha, turno, pre, post, h2o, args.dry_run)

    print(MSG_SEP)
    cabecera = "⚖️ *PESO actualizado*" if not args.dry_run else "🔍 *Dry-run PESO*"
    valores = []
    if pre is not None:
        valores.append(f"PRE *{pre}* kg")
    if post is not None:
        valores.append(f"POST *{post}* kg")
    if h2o is not None:
        valores.append(f"H2O *{h2o}* L")
    print(
        f"{cabecera}\n\n"
        f"Jugador: *{jugador}*  ·  Fecha: {fecha}  ·  Turno: {turno}\n"
        f"{' · '.join(valores)}\n\n"
        f"• {msg}"
    )


if __name__ == "__main__":
    main()
