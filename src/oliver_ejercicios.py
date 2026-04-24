"""
oliver_ejercicios.py — Procesa la hoja _EJERCICIOS y genera _VISTA_EJERCICIOS
con las métricas de Oliver agregadas para cada rango de minutos.

Flujo:
  1. Lee hoja _EJERCICIOS (definida por el usuario): cada fila = un bloque
     del entreno (rondo, ABP, juego real, etc.) con session_id, minuto
     inicio/fin y metadatos.
  2. Para cada sesión única, descarga el TIMELINE de Oliver de todos los
     jugadores que tienen player_session en esa sesión (endpoint:
     /v1/player-sessions/{id}?include=player_session_info:attr:timeline).
  3. Agrega las métricas del timeline entre minuto_inicio y minuto_fin.
  4. Escribe una fila por (ejercicio × jugador) en _VISTA_EJERCICIOS.

Uso:
  /usr/bin/python3 src/oliver_ejercicios.py

Requiere: OLIVER_TOKEN + OLIVER_REFRESH_TOKEN + OLIVER_USER_ID en .env.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))
from oliver_sync import OliverAPI, OLIVER_TOKEN, OLIVER_REFRESH, OLIVER_USER, OLIVER_TEAM  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _connect_sheet():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


def cargar_mapeo_jugadores(ss) -> tuple[dict, dict]:
    """Lee BORG para la lista de nombres 'cortos' del Sheet (BARONA, CARLOS...)
    y la hoja _OLIVER_ALIASES para alias manuales (DAVID SEGOVIA → SEGO).
    Devuelve (dict_upper_to_canonical, dict_alias_upper_to_nombre_sheet)."""
    sheet_upper: dict = {}
    try:
        borg = pd.DataFrame(ss.worksheet("BORG").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        ))
        # Si hay duplicados case-insensitive (ej. "Carlos" y "CARLOS"),
        # preferir la versión TODO MAYÚSCULAS como forma canónica.
        for j in borg["JUGADOR"].dropna().unique():
            j_str = str(j).strip()
            if not j_str or j_str.upper() == "JUG 16":
                continue
            up = j_str.upper()
            canonica = sheet_upper.get(up)
            if canonica is None:
                sheet_upper[up] = j_str
            else:
                # Reemplazar si la nueva es "más mayúscula" o la canonica no lo es
                if j_str == up and canonica != up:
                    sheet_upper[up] = j_str
    except Exception:
        pass

    alias_map = {}
    try:
        aliases = pd.DataFrame(ss.worksheet("_OLIVER_ALIASES").get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        ))
        if not aliases.empty and "nombre_oliver" in aliases.columns and "nombre_sheet" in aliases.columns:
            for _, r in aliases.iterrows():
                ol = str(r.get("nombre_oliver", "")).strip()
                sh = str(r.get("nombre_sheet", "")).strip()
                if ol and sh:
                    alias_map[ol.upper()] = sh
    except Exception:
        pass
    return sheet_upper, alias_map


def normalizar_nombre(nombre_oliver: str, sheet_upper: dict, alias_map: dict) -> str:
    """Convierte 'Sergio Barona' → 'BARONA' si hay match; si no, devuelve el original."""
    if not isinstance(nombre_oliver, str) or not nombre_oliver:
        return nombre_oliver
    # 1. Alias manual exacto (case-insensitive)
    if nombre_oliver.upper() in alias_map:
        return alias_map[nombre_oliver.upper()]
    # 2. Match fuzzy: alguna palabra del nombre Oliver coincide con un jugador del Sheet
    for palabra in nombre_oliver.split():
        up = palabra.upper()
        if up in sheet_upper:
            return sheet_upper[up]
    return nombre_oliver


def leer_ejercicios(ss) -> pd.DataFrame:
    """Lee la hoja _EJERCICIOS y devuelve DataFrame limpio."""
    ws = ss.worksheet("_EJERCICIOS")
    rows = ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Filtrar filas de ejemplo/vacías
    df = df[df["session_id"].astype(str).str.strip().ne("")
            & ~df["session_id"].astype(str).str.startswith("#")]
    # Tipos
    df["session_id"]    = pd.to_numeric(df["session_id"], errors="coerce").astype("Int64")
    df["minuto_inicio"] = pd.to_numeric(df["minuto_inicio"], errors="coerce")
    df["minuto_fin"]    = pd.to_numeric(df["minuto_fin"], errors="coerce")
    df = df.dropna(subset=["session_id", "minuto_inicio", "minuto_fin"])
    return df.reset_index(drop=True)


def descargar_timeline_sesion(api: OliverAPI, session_id: int) -> list[dict]:
    """Descarga el timeline de TODOS los player_sessions de esa sesión.
    Devuelve lista de dicts: [{player_id, oli_id, nombre (si se tiene), timeline}]"""
    # Primero listar player_sessions de la sesión (viene en /sessions/{id}/average)
    avg = api._get(f"/sessions/{session_id}/average", params={"raw_data": 1})
    player_sessions = (avg or {}).get("player_sessions") or []
    resultados = []
    for ps in player_sessions:
        ps_id = ps.get("id")
        if not ps_id:
            continue
        try:
            r = api._get(f"/player-sessions/{ps_id}",
                         params={"include": "player_session_info:attr:timeline"})
        except Exception as e:
            print(f"  [!] fallo timeline ps={ps_id}: {e}", file=sys.stderr)
            continue
        psi = (r.get("player_session", {}) or {}).get("player_session_info", {}) or {}
        timeline = psi.get("timeline") or {}
        resultados.append({
            "player_id": ps.get("player_id"),
            "player_session_id": ps_id,
            "oli_id": ps.get("oli_id"),
            "timeline": timeline,
        })
        time.sleep(0.25)  # respetar rate limit
    return resultados


def _slice_media(arr, ini: int, fin: int):
    """Devuelve la media de arr[ini:fin] (o 0 si vacío)."""
    if not isinstance(arr, list) or ini >= len(arr):
        return 0.0
    sub = arr[ini:min(fin, len(arr))]
    if not sub:
        return 0.0
    try:
        return float(sum(sub) / len(sub))
    except (TypeError, ValueError):
        return 0.0


def _slice_suma(arr, ini: int, fin: int):
    if not isinstance(arr, list) or ini >= len(arr):
        return 0.0
    sub = arr[ini:min(fin, len(arr))]
    if not sub:
        return 0.0
    try:
        return float(sum(sub))
    except (TypeError, ValueError):
        return 0.0


def _slice_max(arr, ini: int, fin: int):
    if not isinstance(arr, list) or ini >= len(arr):
        return 0.0
    sub = arr[ini:min(fin, len(arr))]
    if not sub:
        return 0.0
    try:
        return float(max(sub))
    except (TypeError, ValueError):
        return 0.0


def agregar_metricas(timeline: dict, ini: int, fin: int) -> dict:
    """Agrega las métricas del timeline en el rango [ini, fin) minutos.
    Usa SUMA para las que son "cantidades por minuto" y MAX para las que
    ya son máximos."""
    if not timeline:
        return {}
    tl = timeline
    duracion = max(1, fin - ini)

    out = {
        "duracion_min": int(duracion),
        # Tiempos
        "played_time":      round(_slice_suma(tl.get("played_time"), ini, fin), 2),
        "activity_time":    round(_slice_suma(tl.get("raw_activity_time"), ini, fin), 2),
        "active_rest_time": round(_slice_suma(tl.get("active_rest_time"), ini, fin), 2),
        # Acciones técnicas
        "cods":    int(_slice_suma(tl.get("cods"), ini, fin)),
        "jumps":   int(_slice_suma(tl.get("jumps"), ini, fin)),
        # Velocidad
        "top_speed_ms":   round(_slice_max(tl.get("top_speed"), ini, fin), 2),
        "top_speed_kmh":  round(_slice_max(tl.get("top_speed"), ini, fin) * 3.6, 2),
    }

    # Metabólico
    mp = tl.get("metabolic_power") or {}
    out["kcal"]                  = round(_slice_suma(mp.get("kcal"), ini, fin), 2)
    out["dist_high_intensity"]   = round(_slice_suma(mp.get("dist_high_intensity"), ini, fin), 2)
    out["dist_low_intensity"]    = round(_slice_suma(mp.get("dist_low_intensity"), ini, fin), 2)
    out["perc_time_high_int"]    = round(_slice_media(mp.get("perc_time_high_intensity"), ini, fin), 2)

    # Intensidad Oliver (índices 0-100) — promediar en el rango
    oli = tl.get("oli_session_intensity") or {}
    out["intensity_medio"]     = round(_slice_media(oli.get("intensity"), ini, fin), 2)
    out["acc_intensity_medio"] = round(_slice_media(oli.get("acceleration"), ini, fin), 2)
    out["speed_intensity_medio"] = round(_slice_media(oli.get("speed"), ini, fin), 2)

    # Volumen (array 0-1) — suma = "minutos equivalentes" de volumen alto
    out["oli_volume_sum"] = round(_slice_suma(tl.get("oli_session_volume"), ini, fin), 2)

    # Segmentos de velocidad
    seg_d = tl.get("segments") or {}
    seg_c = tl.get("segments_count") or {}
    out["dist_walking"]  = round(_slice_suma(seg_d.get("walking"), ini, fin), 2)
    out["dist_jogging"]  = round(_slice_suma(seg_d.get("jogging"), ini, fin), 2)
    out["dist_lsprint"]  = round(_slice_suma(seg_d.get("lsprint"), ini, fin), 2)
    out["dist_sprint"]   = round(_slice_suma(seg_d.get("sprint"), ini, fin), 2)
    out["n_walking"]     = int(_slice_suma(seg_c.get("walking"), ini, fin))
    out["n_jogging"]     = int(_slice_suma(seg_c.get("jogging"), ini, fin))
    out["n_lsprint"]     = int(_slice_suma(seg_c.get("lsprint"), ini, fin))
    out["n_sprint"]      = int(_slice_suma(seg_c.get("sprint"), ini, fin))
    out["dist_total"]    = round(
        out["dist_walking"] + out["dist_jogging"] + out["dist_lsprint"] + out["dist_sprint"], 2
    )

    # Aceleraciones (conteos)
    acc_c = tl.get("accelerations_count") or {}
    out["n_acc_alta_pos"] = int(_slice_suma((acc_c.get("high") or {}).get("pos"), ini, fin))
    out["n_acc_alta_neg"] = int(_slice_suma((acc_c.get("high") or {}).get("neg"), ini, fin))
    out["n_acc_max_pos"]  = int(_slice_suma((acc_c.get("max") or {}).get("pos"), ini, fin))
    out["n_acc_max_neg"]  = int(_slice_suma((acc_c.get("max") or {}).get("neg"), ini, fin))

    return out


def main():
    ss = _connect_sheet()
    ej = leer_ejercicios(ss)
    if ej.empty:
        print("⚠️  Hoja _EJERCICIOS vacía o sin filas válidas.")
        print("    Rellena la hoja y vuelve a lanzar este script.")
        return

    print(f"▶ Ejercicios a procesar: {len(ej)}")
    sesiones_unicas = ej["session_id"].astype(int).unique().tolist()
    print(f"▶ Sesiones distintas: {len(sesiones_unicas)}")

    api = OliverAPI(OLIVER_TOKEN, OLIVER_USER, OLIVER_REFRESH)

    # Cache de timelines para no pedir 2 veces la misma sesión
    cache: dict[int, list[dict]] = {}

    # Construir mapa player_id → nombre (de oliver_sync)
    print("▶ Construyendo mapa player_id → nombre…")
    name_map = api.build_player_name_map(OLIVER_TEAM)

    # Cargar mapeo Oliver → Sheet para que los nombres cuadren con el dashboard
    print("▶ Cargando mapeo Oliver ↔ Sheet…")
    sheet_upper, alias_map = cargar_mapeo_jugadores(ss)
    print(f"  → {len(sheet_upper)} jugadores en Sheet · {len(alias_map)} aliases manuales")

    filas_salida = []
    for i, fila in ej.iterrows():
        sid = int(fila["session_id"])
        ini = int(fila["minuto_inicio"])
        fin = int(fila["minuto_fin"])
        nombre_ej = str(fila.get("nombre_ejercicio", "")).strip() or f"Ejercicio {i+1}"
        tipo = str(fila.get("tipo_ejercicio", "")).strip()
        fecha = str(fila.get("fecha", "")).strip()
        turno = str(fila.get("turno", "")).strip()

        print(f"  [{i+1}/{len(ej)}] sesión {sid}, min {ini}-{fin}, '{nombre_ej}'")

        if sid not in cache:
            try:
                cache[sid] = descargar_timeline_sesion(api, sid)
            except Exception as e:
                print(f"    [!] fallo descargando sesión {sid}: {e}", file=sys.stderr)
                cache[sid] = []
        ps_list = cache[sid]

        if not ps_list:
            print(f"    [!] sin timeline para sesión {sid}, saltando")
            continue

        for ps in ps_list:
            pid = ps.get("player_id")
            jugador_oliver = name_map.get(pid, f"player_{pid}")
            # Normalizar a formato Sheet: "Sergio Barona" → "BARONA"
            jugador = normalizar_nombre(jugador_oliver, sheet_upper, alias_map)
            metricas = agregar_metricas(ps["timeline"], ini, fin)
            if not metricas:
                continue
            base = {
                "session_id": sid,
                "fecha": fecha,
                "turno": turno,
                "ejercicio": nombre_ej,
                "tipo_ejercicio": tipo,
                "jugador": jugador,
                "minuto_inicio": ini,
                "minuto_fin": fin,
            }
            base.update(metricas)
            filas_salida.append(base)

    if not filas_salida:
        print("⚠️  No se generó ninguna fila de métricas. Revisa la hoja _EJERCICIOS.")
        return

    df_out = pd.DataFrame(filas_salida)
    print(f"\n▶ Escribiendo {len(df_out)} filas a _VISTA_EJERCICIOS…")

    # Escribir hoja
    existentes = {ws.title for ws in ss.worksheets()}
    if "_VISTA_EJERCICIOS" in existentes:
        ws = ss.worksheet("_VISTA_EJERCICIOS"); ws.clear()
    else:
        ws = ss.add_worksheet(title="_VISTA_EJERCICIOS", rows=max(len(df_out)+10, 200), cols=len(df_out.columns)+2)
    df2 = df_out.where(pd.notnull(df_out), "").astype(object)
    ws.update("A1", [df2.columns.tolist()] + df2.values.tolist())
    print(f"✓ _VISTA_EJERCICIOS: {len(df_out)} filas, {len(df_out.columns)} columnas")
    print(f"  {ss.url}")


if __name__ == "__main__":
    main()
