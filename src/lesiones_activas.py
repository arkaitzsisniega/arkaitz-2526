"""
lesiones_activas.py — Lista las lesiones ACTIVAS del equipo (sin fecha de
alta). Script CURADO sin LLM: lo llama el bot cuando detecta intents tipo
"lesiones activas", "quién está lesionado", "bajas del equipo".

⚠ PRIVACIDAD: en bot_datos (cuerpo técnico) este script debería
ejecutarse con anonimización (mostrar #dorsal en vez de nombre). Pero
como el script es agnóstico al rol, devuelve nombres. El bot decide si
los pasa o no a través de su propia capa de privacidad.

Uso:
  /usr/bin/python3 src/lesiones_activas.py [--por-dorsal]
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
    por_dorsal = "--por-dorsal" in sys.argv

    ss = conectar()
    # LESIONES tiene cabecera en fila 2 (super-cabecera en fila 1).
    try:
        ws = ss.worksheet("LESIONES")
        vals = ws.get_all_values()
    except Exception as e:
        print(f"⚠️ No pude leer LESIONES: {e}")
        return
    if not vals or len(vals) < 3:
        print("📭 No hay lesiones registradas en la hoja LESIONES.")
        return

    hdr = vals[1]  # fila 2 es la cabecera real
    df = pd.DataFrame(vals[2:], columns=hdr)
    # Quitar filas totalmente vacías
    df = df[df["JUGADOR"].astype(str).str.strip() != ""].copy() if "JUGADOR" in df.columns else df
    if df.empty:
        print("📭 No hay lesiones registradas.")
        return

    # Activa = sin fecha de alta
    col_alta = None
    for cand in ("FECHA ALTA", "FECHA_ALTA", "ALTA"):
        if cand in df.columns:
            col_alta = cand
            break
    if col_alta is None:
        print("⚠️ La hoja LESIONES no tiene columna FECHA ALTA. No puedo saber cuáles están activas.")
        return

    df["_activa"] = df[col_alta].astype(str).str.strip() == ""
    activas = df[df["_activa"]].copy()
    if activas.empty:
        print("✅ *No hay lesiones activas* en el equipo. Todos disponibles.")
        return

    # Mapa dorsal si se pide
    if por_dorsal:
        try:
            rdf = pd.DataFrame(ss.worksheet("JUGADORES_ROSTER").get_all_records())
            roster = dict(zip(
                rdf["nombre"].astype(str).str.upper().str.strip(),
                rdf["dorsal"].astype(str).str.strip()
            )) if not rdf.empty else {}
        except Exception:
            roster = {}
    else:
        roster = {}

    print(f"🏥 *Lesiones activas* — {len(activas)} jugador(es):")
    print()
    col_fecha = None
    for cand in ("FECHA LESIÓN", "FECHA_LESION", "FECHA"):
        if cand in activas.columns:
            col_fecha = cand
            break
    col_tipo = None
    for cand in ("TIPO LESIÓN", "TIPO_LESION", "TIPO"):
        if cand in activas.columns:
            col_tipo = cand
            break
    col_zona = None
    for cand in ("ZONA CORPORAL", "ZONA_CORPORAL", "ZONA"):
        if cand in activas.columns:
            col_zona = cand
            break
    col_lado = None
    for cand in ("LADO",):
        if cand in activas.columns:
            col_lado = cand
            break
    col_dias = None
    for cand in ("DÍAS BAJA EST.", "DIAS BAJA EST.", "DIAS_BAJA_EST", "DIAS_BAJA"):
        if cand in activas.columns:
            col_dias = cand
            break

    from datetime import date as _date
    hoy = _date.today()
    activas_show = []
    for _, r in activas.iterrows():
        jug_real = str(r.get("JUGADOR", "")).strip().upper()
        if por_dorsal:
            d = roster.get(jug_real, "?")
            nombre = f"#{d}" if d != "?" else "(?)"
        else:
            nombre = jug_real

        fecha = str(r.get(col_fecha, "")).strip() if col_fecha else ""
        tipo = str(r.get(col_tipo, "")).strip() if col_tipo else ""
        zona = str(r.get(col_zona, "")).strip() if col_zona else ""
        lado = str(r.get(col_lado, "")).strip() if col_lado else ""
        dias = str(r.get(col_dias, "")).strip() if col_dias else ""

        # Días desde la lesión. Cuidado con el formato: si es ISO
        # YYYY-MM-DD, dayfirst=True lo malinterpreta. Detectamos formato.
        dias_off = None
        try:
            import re as _re
            es_iso = bool(_re.match(r"^\d{4}-\d{1,2}-\d{1,2}", fecha))
            f = pd.to_datetime(fecha, dayfirst=not es_iso, errors="coerce")
            if pd.notna(f):
                dias_off = (hoy - f.date()).days
        except Exception:
            pass

        bits = []
        if tipo: bits.append(tipo)
        if zona:
            bits.append(zona + (f" {lado}" if lado else ""))
        descr = " · ".join(bits) if bits else "(sin tipo)"

        activas_show.append((nombre, fecha, descr, dias_off, dias))

    # Orden: más recientes primero
    activas_show.sort(key=lambda x: x[3] if x[3] is not None else 999)

    for nombre, fecha, descr, dias_off, dias_est in activas_show:
        linea = f"  · *{nombre}*  {descr}"
        if fecha:
            linea += f"  ·  lesión: {fecha}"
            if dias_off is not None:
                linea += f" (hace {dias_off}d)"
        if dias_est:
            linea += f"  ·  baja est.: *{dias_est}* días"
        print(linea)


if __name__ == "__main__":
    main()
