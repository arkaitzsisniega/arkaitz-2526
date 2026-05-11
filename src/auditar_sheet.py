"""
auditar_sheet.py — Detecta inconsistencias en las hojas crudas del Sheet.

Útil para hacer pasadas periódicas y encontrar errores de apuntado
(jugadores no en roster, fechas raras, BORG con valores imposibles,
pesos fuera de rango, sesiones duplicadas, etc).

Uso:
  /usr/bin/python3 src/auditar_sheet.py
  /usr/bin/python3 src/auditar_sheet.py --verbose

Output: resumen con MSG_SEP por categoría. Si todo OK, lo dice claro.
Si encuentra problemas, lista cada uno con fila/contexto.

Idea de uso: el bot dev podría llamarlo periódicamente (semanal o
cuando el usuario quiera) y avisar de cualquier cosa rara.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "src"))
from aliases_jugadores import norm_jugador, ROSTER_CANONICO  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"

ESTADOS_BORG = {"S", "A", "L", "N", "D", "NC", "NJ"}


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES,
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _parsear_fecha(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _es_numero(v):
    if v is None or v == "":
        return False
    try:
        float(str(v).replace(",", "."))
        return True
    except ValueError:
        return False


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def auditar_borg(ss):
    """Detecta: jugador fuera de roster, BORG fuera de rango 0-10
    (si es numérico), estado inválido."""
    errores = []
    try:
        ws = ss.worksheet("BORG")
        rows = ws.get_all_values()
    except Exception:
        return ["BORG: no encuentro la hoja"]
    if len(rows) < 2:
        return []
    for i, r in enumerate(rows[1:], start=2):
        if not r or len(r) < 4:
            continue
        fecha_s, turno, jugador, valor = r[0], r[1], r[2], r[3]
        # Saltar filas totalmente vacías
        if not jugador.strip() and not fecha_s.strip() and not valor.strip():
            continue
        if not jugador.strip():
            continue
        # 1) Jugador en roster
        canon = norm_jugador(jugador)
        if canon not in ROSTER_CANONICO:
            errores.append(
                f"BORG fila {i}: jugador {jugador!r} → norm {canon!r} "
                f"no está en roster oficial."
            )
        # 2) Valor BORG válido
        v = valor.strip()
        if not v:
            continue
        if v.upper() in ESTADOS_BORG:
            continue
        n = _num(v)
        if n is None:
            errores.append(
                f"BORG fila {i}: valor {v!r} no es número ni estado "
                f"({sorted(ESTADOS_BORG)})."
            )
        elif not (0 <= n <= 10):
            errores.append(
                f"BORG fila {i}: valor {n} fuera de rango 0-10 "
                f"({jugador} {fecha_s} {turno})."
            )
        # 3) Fecha parseable (solo si hay datos relevantes en la fila;
        # filas con solo jugador pero todo lo demás vacío no son error)
        if not fecha_s.strip() and not turno.strip() and not v:
            continue
        if _parsear_fecha(fecha_s) is None:
            errores.append(
                f"BORG fila {i}: fecha {fecha_s!r} no es parseable."
            )
        # 4) Turno válido
        if turno.strip().upper() not in ("M", "T", "P", ""):
            errores.append(
                f"BORG fila {i}: turno {turno!r} no es M/T/P."
            )
    return errores


def auditar_peso(ss):
    """Detecta: jugador fuera de roster, pesos fuera de rango fisiológico
    (40-200 kg), H2O fuera de rango (10-100 L)."""
    errores = []
    try:
        ws = ss.worksheet("PESO")
        rows = ws.get_all_values()
    except Exception:
        return ["PESO: no encuentro la hoja"]
    if len(rows) < 2:
        return []
    header = [c.strip().upper() for c in rows[0]]
    def idx(name):
        try:
            return header.index(name)
        except ValueError:
            return None
    i_jug = idx("JUGADOR")
    i_pre = idx("PESO_PRE")
    i_post = idx("PESO_POST")
    i_h2o = idx("H2O_L")
    if i_jug is None:
        return ["PESO: no encuentro columna JUGADOR"]
    for i, r in enumerate(rows[1:], start=2):
        if not r or len(r) <= i_jug:
            continue
        jugador = r[i_jug].strip()
        if not jugador:
            continue
        canon = norm_jugador(jugador)
        if canon not in ROSTER_CANONICO:
            errores.append(f"PESO fila {i}: jugador {jugador!r} fuera del roster.")
        # H2O_L parece ser delta de agua (ej. -2 a +2 L durante un
        # entreno), no agua corporal total. Rango permisivo -5 a +5.
        for nombre_col, idx_col, rmin, rmax in [
            ("PESO_PRE", i_pre, 40, 200),
            ("PESO_POST", i_post, 40, 200),
            ("H2O_L", i_h2o, -5, 5),
        ]:
            if idx_col is None or idx_col >= len(r):
                continue
            val = r[idx_col].strip()
            if not val:
                continue
            n = _num(val)
            if n is None:
                errores.append(f"PESO fila {i}: {nombre_col}={val!r} no es número.")
            elif not (rmin <= n <= rmax):
                errores.append(
                    f"PESO fila {i}: {nombre_col}={n} fuera de rango "
                    f"({rmin}-{rmax}). Jugador: {jugador}."
                )
    return errores


def auditar_wellness(ss):
    """Detecta: jugador fuera de roster, valores SUENO/FATIGA/MOLESTIAS/
    ANIMO fuera de 1-5, TOTAL fuera de 4-20 o no suma."""
    errores = []
    try:
        ws = ss.worksheet("WELLNESS")
        rows = ws.get_all_values()
    except Exception:
        return ["WELLNESS: no encuentro la hoja"]
    if len(rows) < 2:
        return []
    header = [c.strip().upper() for c in rows[0]]
    def idx(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None
    i_jug = idx("JUGADOR")
    i_s = idx("SUENO", "SUEÑO")
    i_f = idx("FATIGA")
    i_m = idx("MOLESTIAS")
    i_a = idx("ANIMO", "ÁNIMO")
    i_t = idx("TOTAL")
    if i_jug is None:
        return ["WELLNESS: no encuentro columna JUGADOR"]
    for i, r in enumerate(rows[1:], start=2):
        if not r or len(r) <= i_jug:
            continue
        jugador = r[i_jug].strip()
        if not jugador:
            continue
        canon = norm_jugador(jugador)
        if canon not in ROSTER_CANONICO:
            errores.append(f"WELLNESS fila {i}: jugador {jugador!r} fuera del roster.")
        nums = {}
        for nombre, idx_c in [("SUENO", i_s), ("FATIGA", i_f),
                                ("MOLESTIAS", i_m), ("ANIMO", i_a)]:
            if idx_c is None or idx_c >= len(r):
                continue
            v = r[idx_c].strip()
            if not v:
                continue
            n = _num(v)
            if n is None:
                errores.append(f"WELLNESS fila {i}: {nombre}={v!r} no es número.")
            elif not (1 <= n <= 5):
                errores.append(
                    f"WELLNESS fila {i}: {nombre}={n} fuera de 1-5 ({jugador})."
                )
            else:
                nums[nombre] = n
        # TOTAL coherente con la suma
        if i_t is not None and i_t < len(r):
            v_t = r[i_t].strip()
            if v_t:
                n_t = _num(v_t)
                if n_t is not None and len(nums) == 4:
                    suma = sum(nums.values())
                    if abs(suma - n_t) > 0.01:
                        errores.append(
                            f"WELLNESS fila {i}: TOTAL={n_t} pero la suma da "
                            f"{suma} ({jugador})."
                        )
                if n_t is not None and not (4 <= n_t <= 20):
                    errores.append(
                        f"WELLNESS fila {i}: TOTAL={n_t} fuera de 4-20."
                    )
    return errores


def auditar_sesiones(ss):
    """Detecta: fechas no parseables, duplicados (FECHA+TURNO+TIPO),
    minutos fuera de rango."""
    errores = []
    try:
        ws = ss.worksheet("SESIONES")
        rows = ws.get_all_values()
    except Exception:
        return ["SESIONES: no encuentro la hoja"]
    if len(rows) < 2:
        return []
    vistos = set()
    for i, r in enumerate(rows[1:], start=2):
        if not r or len(r) < 5:
            continue
        fecha_s, semana, turno, tipo, mins = r[0], r[1], r[2], r[3], r[4]
        if not fecha_s.strip():
            continue
        if _parsear_fecha(fecha_s) is None:
            errores.append(f"SESIONES fila {i}: fecha {fecha_s!r} no parseable.")
            continue
        clave = (fecha_s.strip(), turno.strip().upper(), tipo.strip().upper())
        if clave in vistos:
            errores.append(
                f"SESIONES fila {i}: DUPLICADO (fecha+turno+tipo): {clave}."
            )
        vistos.add(clave)
        if mins.strip():
            n = _num(mins)
            if n is None:
                errores.append(f"SESIONES fila {i}: minutos {mins!r} no es número.")
            elif not (1 <= n <= 300):
                errores.append(
                    f"SESIONES fila {i}: minutos {n} fuera de rango 1-300."
                )
    return errores


def main():
    ap = argparse.ArgumentParser(description="Audita hojas crudas del Sheet.")
    ap.add_argument("--verbose", action="store_true",
                    help="Imprime cada incidencia (default: agrupa por hoja).")
    args = ap.parse_args()

    print(f"🔎 Auditando Sheet a {date.today().isoformat()}…",
          file=sys.stderr)
    ss = _open_sheet()

    auditores = [
        ("BORG", auditar_borg),
        ("PESO", auditar_peso),
        ("WELLNESS", auditar_wellness),
        ("SESIONES", auditar_sesiones),
    ]

    print(MSG_SEP)
    todo_ok = True
    bloques = []
    for nombre, fn in auditores:
        errs = fn(ss)
        if not errs:
            bloques.append(f"✅ *{nombre}*: sin incidencias.")
        else:
            todo_ok = False
            bloques.append(
                f"⚠️ *{nombre}*: {len(errs)} incidencia(s)."
                + ("\n   · " + "\n   · ".join(errs[:20])
                   if args.verbose else "")
                + ("\n   · …" if len(errs) > 20 and args.verbose else "")
            )

    cabecera = ("✅ *Auditoría del Sheet OK*" if todo_ok
                else "⚠️ *Auditoría del Sheet: hay incidencias*")
    print(cabecera)
    print()
    print("\n".join(bloques))

    if not args.verbose and not todo_ok:
        print("\n_Usa `--verbose` para ver el detalle de cada incidencia._")


if __name__ == "__main__":
    main()
