"""
prepost_estado.py — Devuelve quién ha rellenado PRE, POST y BORG de la
última sesión (o las dos últimas si fue doble M+T el mismo día).

Uso:
  /usr/bin/python3 src/prepost_estado.py
  /usr/bin/python3 src/prepost_estado.py 2026-05-11   (fecha concreta)

Para cada turno de la fecha procesada, clasifica el roster activo en:
  ✅ Completos (PRE + POST + BORG numérico)
  ⚠️ Falta solo POST
  ⚠️ Falta solo BORG
  ⚠️ Falta solo PRE
  ⚠️ Faltan dos (combinaciones)
  ❌ No han hecho nada
  🟦 Fuera por estado (BORG con letra S/A/L/N/D/NC → no se le pide)

Imprime resumen con MSG_SEP para que Alfred lo capte tal cual.
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
import forms_utils as fu  # noqa: E402
from aliases_jugadores import (  # noqa: E402
    ALIASES_JUGADOR, norm_jugador as _norm_jugador_central,
)

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"

ESTADOS_BORG = {"S", "A", "L", "N", "D", "NC", "NJ"}
ETIQUETAS_ESTADO = {
    "S": "Selección", "A": "Ausencia", "L": "Lesión",
    "N": "No entrena", "D": "Descanso", "NC": "No calificado",
    "NJ": "No juega",
}

def _norm_jugador(nombre: str, roster: set[str]) -> str:
    """Wrapper que delega en src/aliases_jugadores.norm_jugador con el
    roster activo pasado como argumento. Mantenido como alias local
    por compatibilidad con el resto del módulo."""
    return _norm_jugador_central(nombre, roster=roster)


def _open_sheet():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES,
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def _leer_roster(ss) -> list[str]:
    """Devuelve la lista de jugadores activos del roster."""
    try:
        ws = ss.worksheet("JUGADORES_ROSTER")
        rows = ws.get_all_records()
    except Exception:
        return []
    out = []
    for r in rows:
        nombre = str(r.get("nombre", "")).strip().upper()
        activo = str(r.get("activo", "")).strip().upper()
        if not nombre:
            continue
        if activo in ("FALSE", "FALSO", "NO", "0"):
            continue
        out.append(nombre)
    return out


def _ultima_fecha_sesiones(ss) -> str | None:
    """Devuelve la fecha más reciente de SESIONES (YYYY-MM-DD)."""
    ws = ss.worksheet("SESIONES")
    rows = ws.get_all_values()
    if len(rows) < 2:
        return None
    fechas = [r[0].strip() for r in rows[1:] if r and len(r) > 0 and r[0].strip()]
    fechas = [f for f in fechas if len(f) == 10 and f[4] == "-"]
    if not fechas:
        return None
    return max(fechas)


def _turnos_y_tipo_de_fecha(ss, fecha: str) -> list[tuple[str, str, str]]:
    """Devuelve lista de (turno, tipo_sesion, minutos) para esa fecha."""
    ws = ss.worksheet("SESIONES")
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    header = rows[0]
    # Estructura: FECHA, SEMANA(o ID), TURNO, TIPO_SESION, MINUTOS, COMPETICION
    # Para máxima robustez busca por nombre de columna
    def idx(*nombres):
        for i, c in enumerate(header):
            if c.strip().upper() in {n.upper() for n in nombres}:
                return i
        return None
    i_fec = idx("FECHA")
    i_turno = idx("TURNO")
    i_tipo = idx("TIPO_SESION", "TIPO")
    i_min = idx("MINUTOS")
    if None in (i_fec, i_turno):
        return []
    out = []
    for r in rows[1:]:
        if len(r) <= max(i_fec, i_turno):
            continue
        if r[i_fec].strip() != fecha:
            continue
        turno = (r[i_turno] or "").strip().upper()
        tipo = (r[i_tipo] or "").strip() if i_tipo is not None else ""
        mins = (r[i_min] or "").strip() if i_min is not None else ""
        if turno:
            out.append((turno, tipo, mins))
    # Orden M primero, luego T
    out.sort(key=lambda x: 0 if x[0] == "M" else 1)
    return out


def _leer_borg(ss, fecha: str, turno: str, roster: set[str]) -> dict[str, str]:
    """Devuelve {JUGADOR_CANONICO: valor_borg_str} para fecha+turno.
    Valor puede ser número o estado (S/A/L/N/D/NC/NJ). Normaliza nombres
    aplicando ALIASES_JUGADOR (src/aliases_jugadores.py) para mapear
    nombres no canónicos al canónico (ej. 'J.Herrero' → 'HERRERO',
    'Gonza' → 'GONZALO')."""
    ws = ss.worksheet("BORG")
    rows = ws.get_all_values()
    if len(rows) < 2:
        return {}
    header = rows[0]
    i_fec = header.index("FECHA") if "FECHA" in header else 0
    i_tur = header.index("TURNO") if "TURNO" in header else 1
    i_jug = header.index("JUGADOR") if "JUGADOR" in header else 2
    i_borg = header.index("BORG") if "BORG" in header else 3
    out = {}
    for r in rows[1:]:
        if len(r) <= max(i_fec, i_tur, i_jug, i_borg):
            continue
        if r[i_fec].strip() == fecha and r[i_tur].strip().upper() == turno:
            jug = _norm_jugador(r[i_jug], roster)
            val = r[i_borg].strip()
            if jug:
                out[jug] = val
    return out


def _leer_form_post_raw(ss, fecha: str, turno: str,
                         roster: set[str]) -> dict[str, str]:
    """Lee _FORM_POST y devuelve {JUGADOR_CANONICO: borg_str_literal}.
    A diferencia de forms_utils.leer_respuestas_post, NO convierte el
    BORG a float, así preservamos los estados (NJ, S, A, L, etc.) que
    Arkaitz puede haber escrito a mano en esa columna.
    """
    try:
        ws = ss.worksheet("_FORM_POST")
        rows = ws.get_all_values()
    except Exception:
        return {}
    if len(rows) < 2:
        return {}
    header = rows[0]
    # Encontrar columnas por nombre flexible (Forms pone el texto de la
    # pregunta como cabecera).
    i_jug = next((i for i, c in enumerate(header)
                  if "jugador" in c.lower()), None)
    i_fec = next((i for i, c in enumerate(header)
                  if "fecha" in c.lower()), None)
    i_tur = next((i for i, c in enumerate(header)
                  if "turno" in c.lower()), None)
    i_borg = next((i for i, c in enumerate(header)
                   if "borg" in c.lower()), None)
    if None in (i_jug, i_fec, i_tur, i_borg):
        return {}

    out = {}
    for r in rows[1:]:
        if len(r) <= max(i_jug, i_fec, i_tur, i_borg):
            continue
        # Fecha: puede venir como string YYYY-MM-DD o con otro formato
        fecha_raw = (r[i_fec] or "").strip()
        if fecha_raw != fecha:
            # _FORM_POST suele tener formato dd/mm/yyyy o dd/m/yyyy. Hay que
            # parsear con dayfirst=True para no confundir día y mes.
            try:
                f_parsed = pd.to_datetime(fecha_raw, errors="coerce", dayfirst=True)
                if pd.isna(f_parsed) or f_parsed.strftime("%Y-%m-%d") != fecha:
                    continue
            except Exception:
                continue
        # Turno: en _FORM_POST suele venir como "Mañana"/"Tarde"
        turno_raw = (r[i_tur] or "").strip().upper()
        if turno_raw.startswith("MA"):
            turno_norm = "M"
        elif turno_raw.startswith("TA"):
            turno_norm = "T"
        else:
            turno_norm = turno_raw
        if turno_norm != turno:
            continue
        jug = _norm_jugador(r[i_jug], roster)
        if not jug:
            continue
        out[jug] = (r[i_borg] or "").strip()
    return out


def _set_jugadores_pre(ss, fecha: str, turno: str, roster: set[str]) -> set[str]:
    df = fu.leer_respuestas_pre(ss)
    if df.empty:
        return set()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    fecha_ts = pd.Timestamp(fecha)
    mask = (df["FECHA"] == fecha_ts) & (df["TURNO"].astype(str).str.upper() == turno)
    return {_norm_jugador(j, roster) for j in df.loc[mask, "JUGADOR"].astype(str)}


def _set_jugadores_post(ss, fecha: str, turno: str, roster: set[str]) -> set[str]:
    df = fu.leer_respuestas_post(ss)
    if df.empty:
        return set()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    fecha_ts = pd.Timestamp(fecha)
    mask = (df["FECHA"] == fecha_ts) & (df["TURNO"].astype(str).str.upper() == turno)
    return {_norm_jugador(j, roster) for j in df.loc[mask, "JUGADOR"].astype(str)}


def _es_numero(v: str) -> bool:
    if not v:
        return False
    try:
        float(v.replace(",", "."))
        return True
    except ValueError:
        return False


def _formatear_lista(jugadores: list[str]) -> str:
    """Para usar en la salida: 'A, B, C' o '-' si vacía."""
    if not jugadores:
        return "—"
    return ", ".join(sorted(jugadores))


def procesar_turno(ss, fecha: str, turno: str, tipo: str, mins: str,
                   roster: list[str]) -> str:
    roster_set = set(roster)
    pre = _set_jugadores_pre(ss, fecha, turno, roster_set)
    post = _set_jugadores_post(ss, fecha, turno, roster_set)

    # ── Fuentes del BORG / estado ──
    # _FORM_POST: lo que rellena el jugador o lo que Arkaitz modifica a mano
    #             (suele ser su lugar canónico de cambio).
    # BORG: hoja consolidada (se actualiza con /consolidar o con scripts
    #       como apuntar_borg.py / marcar_lesion.py).
    # Reglas: _FORM_POST gana si tiene valor; BORG es fallback.
    borg_form = _leer_form_post_raw(ss, fecha, turno, roster_set)
    borg_consolidado = _leer_borg(ss, fecha, turno, roster_set)
    borg_dict = dict(borg_consolidado)
    for jug, val in borg_form.items():
        if val:  # solo sobrescribir si _FORM_POST tiene contenido
            borg_dict[jug] = val

    # Set de jugadores con BORG NUMÉRICO (han entrenado y se les ha apuntado)
    borg_numerico = {j for j, v in borg_dict.items() if _es_numero(v)}
    # Estado por jugador (S/A/L/N/D/NC/NJ)
    borg_estado = {j: v.upper() for j, v in borg_dict.items()
                   if v.upper() in ESTADOS_BORG}

    # Clasificación sobre el roster activo. Filosofía: si un jugador tiene
    # un ESTADO especial (NJ, S, L, etc.) en BORG / _FORM_POST, ya "está
    # completo" — su info para esa sesión es ese estado y no se le pide
    # PRE/POST/BORG numérico. Adicionalmente lo listamos también en
    # "🟦 Fuera por estado" como contexto informativo.
    esperados = set(roster)
    fuera_estado = {j: borg_estado[j] for j in esperados if j in borg_estado}

    completos = []   # lista de tuplas (jugador, label_estado_o_cadena_vacia)
    falta_post = []
    falta_borg = []
    falta_pre = []
    falta_dos = []
    nada = []

    for j in esperados:
        if j in fuera_estado:
            completos.append((j, fuera_estado[j]))
            continue
        tiene_pre = j in pre
        tiene_post = j in post
        tiene_borg = j in borg_numerico
        n_tiene = tiene_pre + tiene_post + tiene_borg
        if n_tiene == 3:
            completos.append((j, ""))
        elif n_tiene == 2:
            if not tiene_post:
                falta_post.append(j)
            elif not tiene_borg:
                falta_borg.append(j)
            else:
                falta_pre.append(j)
        elif n_tiene == 1:
            faltas = []
            if not tiene_pre:
                faltas.append("PRE")
            if not tiene_post:
                faltas.append("POST")
            if not tiene_borg:
                faltas.append("BORG")
            falta_dos.append(f"{j} (falta {'+'.join(faltas)})")
        else:
            nada.append(j)

    # Construir mensaje
    cab = f"📊 *Sesión {fecha} {turno}*"
    if tipo:
        cab += f" — {tipo}"
    if mins:
        cab += f" · {mins} min"

    lineas = [
        cab,
        f"_{len(esperados)} jugadores · {len(fuera_estado)} con estado especial_",
        "",
    ]

    lineas.append(f"✅ *Completos*: {len(completos)}")
    if completos:
        # Formatear: si tiene estado, "NOMBRE (NJ)"; si no, solo "NOMBRE".
        formato = []
        for j, est in sorted(completos):
            formato.append(f"{j} ({est})" if est else j)
        lineas.append(f"   {', '.join(formato)}")
    lineas.append("")

    lineas.append(f"⚠️ Falta solo POST: {len(falta_post)}")
    if falta_post:
        lineas.append(f"   {_formatear_lista(falta_post)}")

    lineas.append(f"⚠️ Falta solo BORG: {len(falta_borg)}")
    if falta_borg:
        lineas.append(f"   {_formatear_lista(falta_borg)}")

    lineas.append(f"⚠️ Falta solo PRE: {len(falta_pre)}")
    if falta_pre:
        lineas.append(f"   {_formatear_lista(falta_pre)}")

    if falta_dos:
        lineas.append("")
        lineas.append(f"⚠️ Faltan 2 cosas: {len(falta_dos)}")
        for f in sorted(falta_dos):
            lineas.append(f"   · {f}")

    lineas.append("")
    lineas.append(f"❌ *No han hecho nada*: {len(nada)}")
    if nada:
        lineas.append(f"   {_formatear_lista(nada)}")

    if fuera_estado:
        lineas.append("")
        lineas.append(f"🟦 *Fuera por estado*: {len(fuera_estado)}")
        for j in sorted(fuera_estado.keys()):
            est = fuera_estado[j]
            lineas.append(f"   · {j} ({ETIQUETAS_ESTADO.get(est, est)})")

    return "\n".join(lineas)


def main():
    fecha_arg = sys.argv[1] if len(sys.argv) > 1 else None
    ss = _open_sheet()

    if fecha_arg:
        fecha = fecha_arg.strip()
        if len(fecha) != 10 or fecha[4] != "-":
            print(f"❌ Fecha inválida: {fecha!r}. Usa YYYY-MM-DD.")
            sys.exit(2)
    else:
        fecha = _ultima_fecha_sesiones(ss)
        if not fecha:
            print(MSG_SEP)
            print("ℹ️ No encuentro ninguna sesión en SESIONES.")
            return

    turnos = _turnos_y_tipo_de_fecha(ss, fecha)
    if not turnos:
        print(MSG_SEP)
        print(f"ℹ️ No hay sesiones registradas el {fecha}.")
        return

    roster = _leer_roster(ss)
    if not roster:
        print(MSG_SEP)
        print("⚠️ No pude leer JUGADORES_ROSTER. Usa la hoja para definir convocados.")
        return

    bloques = []
    for turno, tipo, mins in turnos:
        bloques.append(procesar_turno(ss, fecha, turno, tipo, mins, roster))

    print(MSG_SEP)
    print("\n\n".join(bloques))


if __name__ == "__main__":
    main()
