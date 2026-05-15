"""
peso_jugador.py — Evolución de peso de UN jugador concreto. Script
CURADO (sin LLM): el bot lo llama directo cuando detecta preguntas tipo:
  - "peso de Cecilio"
  - "dime el peso de Pirata los últimos 10 días"
  - "peso de Carlos esta semana"
  - "peso Raya"

Devuelve:
  - Última medida (PRE, POST, H2O).
  - Media de los últimos N días.
  - Evolución cronológica (PRE pre-sesión vs media).
  - Baseline (promedio últimos 2 meses).
  - Alerta si la última PRE está por debajo del rango habitual.

Uso:
  /usr/bin/python3 src/peso_jugador.py NOMBRE [N_DIAS]

Lee de `_VISTA_PESO` (cruzado y procesado por calcular_vistas.py).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from datetime import date, timedelta

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))
from aliases_jugadores import norm_jugador, ROSTER_CANONICO  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def main():
    args = sys.argv[1:]
    if not args:
        print("Uso: peso_jugador.py NOMBRE [N_DIAS]")
        print(f"Jugadores: {', '.join(sorted(ROSTER_CANONICO))}")
        return

    nombre_raw = args[0]
    nombre = norm_jugador(nombre_raw)
    if not nombre:
        print(f"❌ Jugador desconocido: {nombre_raw!r}")
        print(f"_Conocidos: {', '.join(sorted(ROSTER_CANONICO))}_")
        return

    # N_DIAS opcional: por defecto 14, max 90 (para no saturar)
    n_dias = 14
    if len(args) > 1:
        try:
            n_dias = max(1, min(90, int(args[1])))
        except (ValueError, TypeError):
            print(f"⚠️ N_DIAS '{args[1]}' no es número. Usando default 14.")

    ss = conectar()
    try:
        df = pd.DataFrame(ss.worksheet("_VISTA_PESO").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted))
    except Exception as e:
        print(f"❌ Error leyendo _VISTA_PESO: {e}")
        return

    if df.empty:
        print("⚠️ `_VISTA_PESO` está vacía.")
        return
    if "JUGADOR" not in df.columns:
        print("⚠️ `_VISTA_PESO` no tiene columna JUGADOR. Revisa calcular_vistas.")
        return

    # Filtrar por jugador
    df = df[df["JUGADOR"].astype(str).str.upper() == nombre.upper()].copy()
    if df.empty:
        print(f"📊 *{nombre}* no tiene registros de peso aún.")
        return

    # Normalizar fechas
    df["FECHA_DT"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA_DT"]).sort_values("FECHA_DT")

    # Filtrar por N_DIAS desde hoy
    hoy = pd.Timestamp.now().normalize()
    desde = hoy - pd.Timedelta(days=n_dias)
    df_n = df[df["FECHA_DT"] >= desde].copy()

    if df_n.empty:
        print(f"📊 *{nombre}* — sin registros en los últimos {n_dias} días.")
        # Mostrar la última disponible aunque sea fuera de rango
        ultima = df.iloc[-1]
        print()
        print(f"⏳ Última medida disponible: {pd.Timestamp(ultima['FECHA_DT']).strftime('%d/%m/%Y')}")
        print(f"   PRE: {ultima.get('PESO_PRE', '?')} kg · POST: {ultima.get('PESO_POST', '?')} kg")
        return

    # ── Resumen cabecera ──
    print(f"⚖️ *Peso de {nombre}* — últimos {n_dias} días")
    print()

    # Última medida
    ultima = df_n.iloc[-1]
    f_ult = pd.Timestamp(ultima["FECHA_DT"]).strftime("%d/%m/%Y")
    pre_ult = ultima.get("PESO_PRE", "")
    post_ult = ultima.get("PESO_POST", "")
    h2o_ult = ultima.get("H2O_L", "")
    desv = ultima.get("DESVIACION_BASELINE", "")
    base = ultima.get("BASELINE_PRE", "")
    print(f"📍 Última: {f_ult}")
    if pre_ult not in ("", None):
        print(f"   PRE: *{pre_ult} kg*", end="")
        if base not in ("", None):
            print(f" (baseline {base} kg, "
                  f"{'desv ' + str(desv) + ' kg' if desv not in ('', None) else 'sin desv'})", end="")
        print()
    if post_ult not in ("", None):
        print(f"   POST: {post_ult} kg")
    if h2o_ult not in ("", None):
        print(f"   H2O: {h2o_ult} L")

    # Alerta si la última PRE está bajo
    try:
        desv_f = float(str(desv).replace(",", "."))
        if desv_f < -3:
            print()
            print(f"🔴 *Atención*: PRE {abs(desv_f):.1f} kg por debajo de baseline.")
        elif desv_f < -1.5:
            print()
            print(f"🟠 PRE {abs(desv_f):.1f} kg por debajo de baseline.")
    except (ValueError, TypeError):
        pass

    # ── Cronología ──
    print()
    print("📈 *Cronología:*")
    for _, r in df_n.iterrows():
        f = pd.Timestamp(r["FECHA_DT"]).strftime("%d/%m")
        turno = str(r.get("TURNO", "")).strip() or "-"
        pre = r.get("PESO_PRE", "")
        post = r.get("PESO_POST", "")
        dif = r.get("DIFERENCIA", "")
        pct = r.get("PCT_PERDIDA", "")
        linea = f"  · {f} ({turno})"
        if pre not in ("", None):
            linea += f" — PRE *{pre}*"
        if post not in ("", None):
            linea += f" → POST {post}"
        if dif not in ("", None) and dif != 0:
            try:
                dif_f = float(str(dif).replace(",", "."))
                pct_str = ""
                if pct not in ("", None):
                    pct_str = f" ({pct}%)"
                linea += f" [Δ {dif_f:+.2f} kg{pct_str}]"
            except (ValueError, TypeError):
                pass
        print(linea)

    # ── Estadísticas ──
    print()
    try:
        pres = pd.to_numeric(df_n["PESO_PRE"], errors="coerce").dropna()
        if not pres.empty:
            print(f"📊 PRE últimos {n_dias} días: media *{pres.mean():.1f} kg* "
                  f"(min {pres.min():.1f}, max {pres.max():.1f})")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error inesperado: {type(e).__name__}: {e}")
        sys.exit(1)
