"""
estado_jugador.py — Resumen profesional del estado de un jugador.

Devuelve UN análisis COMPLETO, contextualizado y accionable, listo para
copiar/pegar en Telegram sin que el LLM tenga que razonar nada por encima.
Está pensado para sustituir al LLM en consultas tipo:

  "Cómo está Pirata"
  "Qué tal Raya, su carga últimas 10 sesiones"
  "Resumen de Carlos esta semana"

Uso:
  /usr/bin/python3 src/estado_jugador.py JUGADOR [N_SESIONES]

Ejemplos:
  /usr/bin/python3 src/estado_jugador.py PIRATA
  /usr/bin/python3 src/estado_jugador.py RAYA 10
  /usr/bin/python3 src/estado_jugador.py CARLOS 5

El nombre se normaliza vía aliases_jugadores (admite minúsculas, sin
tildes, sufijos, etc.). Imprime un bloque Markdown que el bot envía
tal cual al usuario.
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
sys.path.insert(0, str(ROOT / "src"))
from aliases_jugadores import norm_jugador as _norm_jugador_central  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ─── Helpers genéricos ────────────────────────────────────────────────────

def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES,
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _df_vista(ss, nombre: str) -> pd.DataFrame:
    """Lee una hoja _VISTA_* y devuelve DataFrame con números formato real."""
    ws = ss.worksheet(nombre)
    rows = ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted,
    )
    return pd.DataFrame(rows)


def _to_num(s: pd.Series) -> pd.Series:
    """Coma decimal española → float, NaN si no es número."""
    return pd.to_numeric(
        s.astype(str).str.replace(",", ".", regex=False), errors="coerce"
    )


# ─── Análisis ──────────────────────────────────────────────────────────────

def _semaforo_acwr(acwr: float | None) -> tuple[str, str]:
    """Devuelve (emoji, etiqueta) para ACWR según el modelo del proyecto."""
    if acwr is None or pd.isna(acwr):
        return "⚪", "sin datos"
    if acwr < 0.8:
        return "🔵", "infra-carga"
    if acwr < 1.3:
        return "🟢", "óptimo"
    if acwr < 1.5:
        return "🟡", "carga alta"
    return "🔴", "sobrecarga"


def _semaforo_monotonia(monot: float | None) -> tuple[str, str]:
    if monot is None or pd.isna(monot):
        return "⚪", "sin datos"
    if monot < 1.5:
        return "🟢", "variada"
    if monot < 2.0:
        return "🟡", "atención"
    return "🔴", "riesgo (>2)"


def _semaforo_wellness(w: float | None) -> tuple[str, str]:
    if w is None or pd.isna(w):
        return "⚪", "sin datos"
    if w <= 10:
        return "🔴", "muy bajo"
    if w <= 13:
        return "🟠", "bajo"
    return "🟢", "OK"


def _fmt_num(x, decimals=1) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:.{decimals}f}"


def _analizar(jugador: str, n: int) -> str:
    ss = _open_sheet()

    # ── Normalizar nombre ──
    canon = _norm_jugador_central(jugador, roster=None)
    if not canon:
        return (
            f"No encuentro a *{jugador}* en el roster. "
            "Comprueba el nombre."
        )

    # ── 1) _VISTA_CARGA → últimas N sesiones + media histórica ──
    carga_df = _df_vista(ss, "_VISTA_CARGA")
    carga_df["CARGA"] = _to_num(carga_df["CARGA"])
    carga_df["BORG"] = _to_num(carga_df["BORG"])
    carga_df["MINUTOS"] = _to_num(carga_df["MINUTOS"])
    carga_df["FECHA"] = pd.to_datetime(carga_df["FECHA"], errors="coerce")

    # Histórico del jugador (todas las sesiones donde participó con carga real)
    jug_all = carga_df[
        (carga_df["JUGADOR"] == canon) & (carga_df["CARGA"].notna())
    ].sort_values("FECHA", ascending=False)

    if jug_all.empty:
        return (
            f"No tengo datos de carga de *{canon}* esta temporada. "
            "Puede que no haya entrenado o que falten Borgs."
        )

    ultimas = jug_all.head(n)
    n_real = len(ultimas)

    carga_media_n = ultimas["CARGA"].mean()
    borg_medio_n = ultimas["BORG"].mean()
    minutos_total_n = ultimas["MINUTOS"].sum()

    carga_media_hist = jug_all["CARGA"].mean()
    borg_medio_hist = jug_all["BORG"].mean()

    # Equipo: media de carga últimas N sesiones del jugador (mismas fechas)
    fechas_n = set(ultimas["FECHA"].dropna().dt.date.tolist())
    equipo_mismas = carga_df[
        carga_df["FECHA"].dt.date.isin(fechas_n) & carga_df["CARGA"].notna()
    ]
    carga_media_equipo = equipo_mismas["CARGA"].mean() if not equipo_mismas.empty else None

    # ── 2) _VISTA_SEMANAL → ACWR, monotonía, fatiga semana actual ──
    sem_df = _df_vista(ss, "_VISTA_SEMANAL")
    sem_df["ACWR"] = _to_num(sem_df["ACWR"])
    sem_df["MONOTONIA"] = _to_num(sem_df["MONOTONIA"])
    sem_df["FATIGA"] = _to_num(sem_df["FATIGA"])
    sem_df["CARGA_SEMANAL"] = _to_num(sem_df["CARGA_SEMANAL"])
    sem_df["FECHA_LUNES"] = pd.to_datetime(sem_df["FECHA_LUNES"], errors="coerce")

    sem_jug = sem_df[sem_df["JUGADOR"] == canon].sort_values(
        "FECHA_LUNES", ascending=False
    )
    sem_actual = sem_jug.head(1)
    sem_anterior = sem_jug.iloc[1] if len(sem_jug) > 1 else None

    acwr = sem_actual["ACWR"].iloc[0] if not sem_actual.empty else None
    monot = sem_actual["MONOTONIA"].iloc[0] if not sem_actual.empty else None
    fatiga = sem_actual["FATIGA"].iloc[0] if not sem_actual.empty else None
    carga_sem = sem_actual["CARGA_SEMANAL"].iloc[0] if not sem_actual.empty else None
    carga_sem_ant = sem_anterior["CARGA_SEMANAL"] if sem_anterior is not None else None

    # ── 3) _VISTA_WELLNESS → wellness reciente ──
    try:
        wel_df = _df_vista(ss, "_VISTA_WELLNESS")
        wel_df["TOTAL"] = _to_num(wel_df["TOTAL"])
        wel_df["WELLNESS_7D"] = _to_num(wel_df["WELLNESS_7D"])
        wel_df["FECHA"] = pd.to_datetime(wel_df["FECHA"], errors="coerce")
        wel_jug = wel_df[wel_df["JUGADOR"] == canon].sort_values(
            "FECHA", ascending=False
        )
        wel_7d = wel_jug["WELLNESS_7D"].iloc[0] if not wel_jug.empty else None
        wel_ultimo = wel_jug["TOTAL"].iloc[0] if not wel_jug.empty else None
    except Exception:
        wel_7d = None
        wel_ultimo = None

    # ── Comparaciones cualitativas ──
    def _vs(actual, ref, etiqueta_ref):
        if actual is None or ref is None or pd.isna(actual) or pd.isna(ref):
            return ""
        diff = actual - ref
        pct = (diff / ref * 100) if ref else 0
        if abs(pct) < 8:
            tendencia = "en línea con"
        elif diff > 0:
            tendencia = "por encima de"
        else:
            tendencia = "por debajo de"
        return f"{tendencia} {etiqueta_ref} ({_fmt_num(ref)})"

    vs_hist = _vs(carga_media_n, carga_media_hist, "su media histórica")
    vs_equipo = _vs(carga_media_n, carga_media_equipo, "la media del equipo")

    # ── Semáforos ──
    em_acwr, txt_acwr = _semaforo_acwr(acwr)
    em_mon, txt_mon = _semaforo_monotonia(monot)
    em_wel, txt_wel = _semaforo_wellness(wel_7d)

    # ── Recomendación final ──
    alertas: list[str] = []
    if acwr is not None and not pd.isna(acwr):
        if acwr >= 1.5:
            alertas.append("ACWR en rojo (sobrecarga). Bajar volumen esta semana.")
        elif acwr >= 1.3:
            alertas.append("ACWR amarillo, vigilar carga semanal.")
        elif acwr < 0.8:
            alertas.append("Infra-carga, valorar si está cumpliendo el plan.")
    if monot is not None and not pd.isna(monot) and monot >= 2:
        alertas.append("Monotonía alta (>2): variar tipo de sesión.")
    if wel_7d is not None and not pd.isna(wel_7d) and wel_7d <= 10:
        alertas.append("Wellness muy bajo, hablar con el jugador.")
    elif wel_7d is not None and not pd.isna(wel_7d) and wel_7d <= 13:
        alertas.append("Wellness por debajo del óptimo, atento.")

    if not alertas:
        recomendacion = "✅ **Todo dentro de lo esperado.** Sigue el plan."
    else:
        recomendacion = "⚠️ **Atención:** " + " ".join(alertas)

    # ── Output Markdown ──
    fecha_min = ultimas["FECHA"].min()
    fecha_max = ultimas["FECHA"].max()
    rango = f"{fecha_min:%d/%m} → {fecha_max:%d/%m}" if pd.notna(fecha_min) else "—"

    lineas = [
        f"📊 **{canon}** · últimas {n_real} sesiones ({rango})",
        "",
        f"• Carga media: **{_fmt_num(carga_media_n, 0)}** "
        f"({vs_hist}"
        + (f"; {vs_equipo}" if vs_equipo else "")
        + ")",
        f"• Borg medio: **{_fmt_num(borg_medio_n)}** "
        f"(histórico: {_fmt_num(borg_medio_hist)})",
        f"• Minutos: **{_fmt_num(minutos_total_n, 0)}** acumulados",
        "",
        f"📅 Semana actual:",
        f"   {em_acwr} ACWR **{_fmt_num(acwr, 2)}** ({txt_acwr})",
        f"   {em_mon} Monotonía **{_fmt_num(monot, 2)}** ({txt_mon})",
        f"   Carga semanal: **{_fmt_num(carga_sem, 0)}**"
        + (
            f" (vs anterior {_fmt_num(carga_sem_ant, 0)})"
            if carga_sem_ant is not None and not pd.isna(carga_sem_ant)
            else ""
        ),
        f"   Fatiga (carga × monotonía): {_fmt_num(fatiga, 0)}",
        "",
        f"😴 Wellness 7 días: {em_wel} **{_fmt_num(wel_7d)}** ({txt_wel})"
        + (
            f" — último parte: {_fmt_num(wel_ultimo, 0)}"
            if wel_ultimo is not None and not pd.isna(wel_ultimo)
            else ""
        ),
        "",
        recomendacion,
    ]
    return "\n".join(lineas)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Uso: estado_jugador.py JUGADOR [N_SESIONES]", file=sys.stderr)
        sys.exit(2)
    jugador = sys.argv[1]
    # N_SESIONES: validar que es entero positivo. Si no lo es, usar default
    # 10 sin crashear (antes el script reventaba con int("abc") → ValueError
    # → traceback al usuario).
    n = 10
    if len(sys.argv) > 2:
        try:
            n_candidato = int(sys.argv[2])
            if n_candidato < 1 or n_candidato > 200:
                print(f"⚠️ N_SESIONES {n_candidato} fuera de rango (1-200). Uso 10 por defecto.",
                      file=sys.stderr)
            else:
                n = n_candidato
        except (ValueError, TypeError):
            print(f"⚠️ N_SESIONES '{sys.argv[2]}' no es un número. Uso 10 por defecto.",
                  file=sys.stderr)
            n = 10
    try:
        out = _analizar(jugador, n)
        print(out)
    except Exception as e:
        print(f"⚠️ Error generando estado de {jugador}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
