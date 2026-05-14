"""
goles_jugador.py — Goles de UN jugador concreto en la temporada. Script
CURADO (sin LLM): el bot lo llama directo cuando detecta preguntas tipo:
  - "goles de Pirata"
  - "cuántos goles ha metido Raya"
  - "Pirata cuántos goles"
  - "goles Javi en liga"

Devuelve:
  - Total de goles.
  - Desglose por competición (LIGA / COPA / etc.).
  - Cronología partido a partido con minuto si está en EST_EVENTOS.

Uso:
  /usr/bin/python3 src/goles_jugador.py NOMBRE [COMPETICION]

Lee de EST_EVENTOS y EST_PARTIDOS del Sheet maestro.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

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

ALIAS_COMP = {
    "LIGA": "LIGA",
    "COPA_REY": "COPA_REY", "COPA REY": "COPA_REY", "COPA DEL REY": "COPA_REY",
    "COPA_ESPANA": "COPA_ESPANA", "COPA ESPANA": "COPA_ESPANA",
    "COPA DE ESPAÑA": "COPA_ESPANA", "COPA ESPAÑA": "COPA_ESPANA",
    "COPA_MUNDO": "COPA_MUNDO", "COPA MUNDO": "COPA_MUNDO",
    "MUNDIAL": "COPA_MUNDO", "COPA DEL MUNDO": "COPA_MUNDO",
    "AMISTOSO": "AMISTOSO",
    "PLAYOFF": "PLAYOFF", "PLAY-OFF": "PLAYOFF", "PLAY OFF": "PLAYOFF",
    "SUPERCOPA": "SUPERCOPA",
    "TODAS": "TODAS", "TODA": "TODAS", "TEMPORADA": "TODAS",
}


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def main():
    args = sys.argv[1:]
    if not args:
        print("Uso: goles_jugador.py NOMBRE [COMPETICION]")
        print(f"Jugadores: {', '.join(sorted(ROSTER_CANONICO))}")
        return

    nombre_raw = args[0]
    nombre = norm_jugador(nombre_raw)
    if not nombre:
        print(f"❌ Jugador desconocido: {nombre_raw!r}")
        print(f"_Conocidos: {', '.join(sorted(ROSTER_CANONICO))}_")
        return

    comp_raw = " ".join(args[1:]).strip().upper() if len(args) > 1 else "TODAS"
    if comp_raw and comp_raw not in ALIAS_COMP and comp_raw not in set(ALIAS_COMP.values()):
        comps_legibles = sorted(set(ALIAS_COMP.values()))
        print(f"⚠️ Competición no reconocida: *{comp_raw}*. Te paso TODAS.")
        print(f"_Competiciones válidas: {', '.join(comps_legibles)}_")
        print()
        comp = "TODAS"
    else:
        comp = ALIAS_COMP.get(comp_raw, comp_raw if comp_raw in set(ALIAS_COMP.values()) else "TODAS")

    ss = conectar()
    try:
        ep = pd.DataFrame(ss.worksheet("EST_PARTIDOS").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted))
        ev = pd.DataFrame(ss.worksheet("EST_EVENTOS").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted))
    except Exception as e:
        print(f"❌ Error leyendo del Sheet: {e}")
        return

    if ep.empty:
        print("⚠️ EST_PARTIDOS está vacío. No hay datos de partidos cargados.")
        return

    # Filtro competición (si aplica)
    if comp != "TODAS" and "competicion" in ep.columns:
        ep = ep[ep["competicion"].astype(str).str.upper() == comp]
    if ep.empty:
        print(f"⚠️ No hay partidos cargados en *{comp}* todavía.")
        return

    partidos_validos = set(ep["partido_id"].astype(str).tolist()) if "partido_id" in ep.columns else None

    # ── 1) Total de goles desde EST_PARTIDOS (suma rápida) ─────────────
    if "jugador" not in ep.columns:
        print("⚠️ EST_PARTIDOS no tiene columna 'jugador'. No puedo calcular.")
        return
    ep_jug = ep[ep["jugador"].astype(str).str.upper() == nombre.upper()]
    if ep_jug.empty:
        print(f"📊 *{nombre}* no aparece en ningún partido de "
              f"{'la temporada' if comp == 'TODAS' else comp}.")
        return

    col_goles = "goles_a_favor" if "goles_a_favor" in ep_jug.columns else (
        "goles" if "goles" in ep_jug.columns else None
    )
    if col_goles is None:
        print("⚠️ EST_PARTIDOS no tiene columna de goles ('goles_a_favor' o 'goles').")
        return

    ep_jug = ep_jug.copy()
    ep_jug["_goles"] = pd.to_numeric(ep_jug[col_goles], errors="coerce").fillna(0).astype(int)
    total = int(ep_jug["_goles"].sum())
    n_partidos = len(ep_jug)
    n_con_gol = int((ep_jug["_goles"] > 0).sum())
    min_total = pd.to_numeric(ep_jug.get("min_total", 0), errors="coerce").fillna(0).sum()
    minutos_total = float(min_total) if min_total else 0.0

    titulo_comp = "temporada" if comp == "TODAS" else comp
    print(f"⚽ *Goles de {nombre}* — {titulo_comp}")
    print()
    print(f"  Total: *{total} goles* en {n_partidos} partidos "
          f"({n_con_gol} con al menos 1 gol)")
    if minutos_total > 0:
        ratio = total / (minutos_total / 40) if minutos_total > 0 else 0
        print(f"  Ratio: {ratio:.2f} goles/40' jugados")

    # ── 2) Desglose por competición (solo si TODAS) ────────────────────
    if comp == "TODAS" and "competicion" in ep_jug.columns:
        por_comp = ep_jug.groupby("competicion")["_goles"].sum().sort_values(ascending=False)
        por_comp = por_comp[por_comp > 0]
        if len(por_comp) > 1:
            print()
            print("*Por competición:*")
            for c, g in por_comp.items():
                print(f"  · {c}: {int(g)}")

    # ── 3) Cronología — partido a partido ──────────────────────────────
    cron = ep_jug[ep_jug["_goles"] > 0].copy()
    if not cron.empty:
        # Ordenar por fecha si existe, si no por jornada
        if "fecha" in cron.columns:
            cron["_fecha"] = pd.to_datetime(cron["fecha"], errors="coerce")
            cron = cron.sort_values("_fecha")
        elif "jornada" in cron.columns:
            cron = cron.sort_values("jornada")

        print()
        print("*Cronología:*")
        for _, row in cron.iterrows():
            ftxt = ""
            f = row.get("_fecha") if "_fecha" in cron.columns else None
            if pd.notna(f):
                ftxt = pd.Timestamp(f).strftime("%d/%m")
            elif row.get("fecha"):
                ftxt = str(row["fecha"])
            partido = str(row.get("partido_id", "?"))
            comp_p = str(row.get("competicion", "?"))
            g = int(row["_goles"])
            sufijo = " (HAT-TRICK)" if g >= 3 else (" (doblete)" if g == 2 else "")
            print(f"  • {ftxt} {partido} _({comp_p})_ — {g}{sufijo}")

        # ── 4) Detalle de minutos desde EST_EVENTOS si está disponible ─
        if not ev.empty and "jugador_principal" in ev.columns and "tipo" in ev.columns:
            ev_gol = ev[
                (ev["jugador_principal"].astype(str).str.upper() == nombre.upper()) &
                (ev["tipo"].astype(str).str.upper().isin(["GOL", "GOL_PROPIO"]))
            ]
            if partidos_validos:
                ev_gol = ev_gol[ev_gol["partido_id"].astype(str).isin(partidos_validos)]
            # Excluir goles en propia puerta del total declarado
            if not ev_gol.empty and "tipo" in ev_gol.columns:
                propios = ev_gol[ev_gol["tipo"].astype(str).str.upper() == "GOL_PROPIO"]
                if not propios.empty:
                    print()
                    print(f"⚠️ De esos, {len(propios)} es/son en propia puerta.")

    print()
    print(f"_Datos: EST_PARTIDOS{' + EST_EVENTOS' if not ev.empty else ''}_")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error inesperado: {type(e).__name__}: {e}")
        sys.exit(1)
