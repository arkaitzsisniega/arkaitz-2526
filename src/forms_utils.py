"""
forms_utils.py — Integración con los Google Forms (PRE y POST entreno).

Dos responsabilidades:
  1. Generar enlaces pre-rellenados para enviar a cada jugador por WhatsApp.
  2. Leer las respuestas de _FORM_PRE y _FORM_POST y consolidarlas en las
     hojas oficiales BORG, PESO y WELLNESS.

Configuración en: src/forms_config.json
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).parent.parent.resolve()
CONFIG_PATH = Path(__file__).parent / "forms_config.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


# ─── Generación de enlaces ──────────────────────────────────────────────────
_BASE = "https://docs.google.com/forms/d/e/{form_id}/viewform?usp=pp_url"


def build_url(form_id: str, prefill: dict) -> str:
    """Construye la URL pre-rellenada a partir del form_id y un dict
    {entry.XXX: valor}. Valores se URL-encodean."""
    params = "&".join(
        f"{k}={urllib.parse.quote(str(v), safe='')}"
        for k, v in prefill.items() if v is not None and v != ""
    )
    return _BASE.format(form_id=form_id) + ("&" + params if params else "")


def enlace_pre(jugador: str, fecha: str, turno: str,
               incluir_wellness: bool = True) -> str:
    """Enlace del Form PRE pre-rellenado. Si `incluir_wellness=False`
    (segunda sesión del día), los campos wellness quedan vacíos."""
    cfg = load_config()["pre"]
    c = cfg["campos"]
    turno_form = load_config()["turno_mapeo"].get(turno, turno)
    prefill = {
        c["jugador"]: jugador,
        c["fecha"]:   fecha,
        c["turno"]:   turno_form,
    }
    # Wellness solo se rellena si es primera sesión; en segunda queda abierto
    return build_url(cfg["form_id"], prefill)


def enlace_post(jugador: str, fecha: str, turno: str) -> str:
    """Enlace del Form POST pre-rellenado."""
    cfg = load_config()["post"]
    c = cfg["campos"]
    turno_form = load_config()["turno_mapeo"].get(turno, turno)
    prefill = {
        c["jugador"]: jugador,
        c["fecha"]:   fecha,
        c["turno"]:   turno_form,
    }
    return build_url(cfg["form_id"], prefill)


def enlaces_para_sesion(jugadores: Iterable[str], fecha: str, turno: str,
                        incluir_wellness: bool = True) -> list[tuple]:
    """Devuelve [(jugador, enlace_pre, enlace_post), …] para la sesión dada.
    `incluir_wellness=False` si es la segunda sesión del mismo día."""
    out = []
    for j in jugadores:
        out.append((
            j,
            enlace_pre(j, fecha, turno, incluir_wellness=incluir_wellness),
            enlace_post(j, fecha, turno),
        ))
    return out


# ─── Consolidación de respuestas → hojas oficiales ──────────────────────────
def _str_turno(v) -> str:
    """Convierte 'Mañana'/'Tarde' a 'M'/'T'."""
    cfg = load_config()["turno_mapeo"]
    s = str(v).strip()
    return cfg.get(s, s[:1].upper())


def _parse_fecha(v) -> str | None:
    """Normaliza fecha a 'YYYY-MM-DD'.

    Acepta '27/04/2026', '27-04-2026', '27/04/26', etc. Devuelve None
    si la fecha resultante cae fuera de un rango razonable (2020-2030)
    porque muchas veces eso indica un parseo erróneo (p. ej. el jugador
    escribió solo "27" y pandas lo interpretó como año 27 → 1927).
    """
    if v is None or v == "":
        return None
    try:
        # Ya viene como YYYY-MM-DD
        if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
            iso = v[:10]
            return iso if "2020" <= iso[:4] <= "2030" else None
        # Serial Google Sheets o timestamp en serial Excel
        if isinstance(v, (int, float)):
            d = (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).date()
            iso = d.isoformat()
            return iso if 2020 <= d.year <= 2030 else None
        # String: probar dayfirst=True (formato es-ES).
        ts = pd.to_datetime(v, dayfirst=True, errors="coerce")
        if pd.notna(ts):
            iso = ts.date().isoformat()
            return iso if 2020 <= ts.year <= 2030 else None
    except Exception:
        pass
    return None


def _parse_timestamp_a_fecha(ts) -> str | None:
    """Saca solo la fecha de un TIMESTAMP de Google Forms.

    Formato típico: '27/04/2026 12:53:40' (es-ES). El timestamp es
    siempre completo y consistente porque lo pone Forms automáticamente,
    así que es la fuente más fiable cuando el campo manual de fecha
    está mal escrito por el jugador."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        try:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(ts))).date().isoformat()
        except Exception:
            return None
    pd_ts = pd.to_datetime(ts, dayfirst=True, errors="coerce")
    if pd.notna(pd_ts):
        return pd_ts.date().isoformat()
    return None


def _to_float(v):
    """Convierte a float tolerando porquerías: '€8,60', '71,1', '60.5', '  72  '.
    Limpia símbolos de moneda y acepta coma o punto decimal."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip()
        if not s:
            return None
        # Quitar símbolos de moneda y caracteres no numéricos típicos
        s = s.replace("€", "").replace("$", "").replace("£", "")
        s = s.replace("kg", "").replace("Kg", "").replace("KG", "")
        s = s.strip()
        # Aceptar coma o punto como decimal
        s = s.replace(",", ".")
        # Si quedan varios puntos (ej. "1.234.5"), quedarse con el último
        if s.count(".") > 1:
            partes = s.split(".")
            s = "".join(partes[:-1]) + "." + partes[-1]
        return float(s)
    except (ValueError, TypeError):
        return None


def _to_borg(v):
    """Convierte BORG: si es número devuelve float, si es estado válido
    (S/A/L/N/D/NC/NJ) devuelve la letra en mayúsculas, si está vacío o
    es basura devuelve None.

    El BORG admite tanto un RPE numérico (1-10) como una letra de
    estado para sesiones que el jugador NO entrenó. Hay que preservar
    los estados al consolidar (antes se perdían porque _to_float los
    convertía a NaN)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Probar primero estado de letra (case-insensitive)
    su = s.upper()
    if su in ("S", "A", "L", "N", "D", "NC", "NJ"):
        return su
    # Si no, intentar numérico
    return _to_float(s)


def _to_peso(v):
    """Como _to_float pero con filtro fisiológico 30-200kg.
    Valores fuera del rango (típico error '€8,60' → 8.6, o '716' por error
    al teclear '71,6') se descartan."""
    f = _to_float(v)
    if f is None:
        return None
    if not (30 <= f <= 200):
        return None
    return f


def leer_respuestas_pre(ss) -> pd.DataFrame:
    """Lee la hoja del Form PRE y devuelve DF normalizado con columnas:
    FECHA, TURNO, JUGADOR, PESO_PRE, SUENO, FATIGA, MOLESTIAS, ANIMO
    + TIMESTAMP (para detectar duplicados)."""
    import gspread
    nombre = load_config()["pre"].get("hoja_respuestas", "_FORM_PRE")
    try:
        ws = ss.worksheet(nombre)
        rows = ws.get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Intentar detectar columnas (los nombres los pone Forms con el título de cada pregunta)
    # Marca temporal / Timestamp es la primera columna siempre
    col_ts = next((c for c in df.columns if c.lower().startswith("marca temporal") or c.lower().startswith("timestamp")), None)
    col_jug = next((c for c in df.columns if "jugador" in c.lower()), None)
    col_fecha = next((c for c in df.columns if "fecha" in c.lower()), None)
    col_turno = next((c for c in df.columns if "turno" in c.lower()), None)
    col_peso = next((c for c in df.columns if "peso" in c.lower() and "pre" in c.lower()), None)
    col_sueno = next((c for c in df.columns if "sue" in c.lower() or "sueño" in c.lower()), None)
    col_fat = next((c for c in df.columns if "fatiga" in c.lower()), None)
    col_mol = next((c for c in df.columns if "molestia" in c.lower()), None)
    col_ani = next((c for c in df.columns if "ánim" in c.lower() or "animo" in c.lower() or "anim" in c.lower()), None)

    # Fecha: PRIMERO intentamos del campo manual (por si el jugador la pone bien),
    # PERO si está mal/vacío caemos al TIMESTAMP (siempre fiable porque lo pone
    # Forms automáticamente con la fecha de envío).
    def _fecha_robusta(row):
        v_manual = row.get(col_fecha) if col_fecha else None
        f = _parse_fecha(v_manual)
        if f:
            return f
        return _parse_timestamp_a_fecha(row.get(col_ts) if col_ts else None)

    out = pd.DataFrame({
        "TIMESTAMP": df[col_ts] if col_ts else "",
        "JUGADOR":   df[col_jug].astype(str).str.strip() if col_jug else "",
        "FECHA":     df.apply(_fecha_robusta, axis=1),
        "TURNO":     df[col_turno].apply(_str_turno) if col_turno else "",
        "PESO_PRE":  df[col_peso].apply(_to_peso) if col_peso else None,
        "SUENO":     df[col_sueno].apply(_to_float) if col_sueno else None,
        "FATIGA":    df[col_fat].apply(_to_float) if col_fat else None,
        "MOLESTIAS": df[col_mol].apply(_to_float) if col_mol else None,
        "ANIMO":     df[col_ani].apply(_to_float) if col_ani else None,
    })
    # Descarta filas sin jugador/fecha (con el fallback a TIMESTAMP esto solo
    # debería pasar si el envío es totalmente raro)
    out = out[out["JUGADOR"].astype(str).str.strip().ne("") & out["FECHA"].notna()]
    return out.reset_index(drop=True)


def leer_respuestas_post(ss) -> pd.DataFrame:
    """Lee la hoja del Form POST. Columnas salida: FECHA, TURNO, JUGADOR, PESO_POST, BORG, TIMESTAMP."""
    import gspread
    nombre = load_config()["post"].get("hoja_respuestas", "_FORM_POST")
    try:
        ws = ss.worksheet(nombre)
        rows = ws.get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    col_ts = next((c for c in df.columns if c.lower().startswith("marca temporal") or c.lower().startswith("timestamp")), None)
    col_jug = next((c for c in df.columns if "jugador" in c.lower()), None)
    col_fecha = next((c for c in df.columns if "fecha" in c.lower()), None)
    col_turno = next((c for c in df.columns if "turno" in c.lower()), None)
    col_peso = next((c for c in df.columns if "peso" in c.lower() and "post" in c.lower()), None)
    col_borg = next((c for c in df.columns if "borg" in c.lower()), None)

    # Misma lógica robusta de fecha que en PRE: prefer campo manual, fallback timestamp
    def _fecha_robusta(row):
        v_manual = row.get(col_fecha) if col_fecha else None
        f = _parse_fecha(v_manual)
        if f:
            return f
        return _parse_timestamp_a_fecha(row.get(col_ts) if col_ts else None)

    out = pd.DataFrame({
        "TIMESTAMP": df[col_ts] if col_ts else "",
        "JUGADOR":   df[col_jug].astype(str).str.strip() if col_jug else "",
        "FECHA":     df.apply(_fecha_robusta, axis=1),
        "TURNO":     df[col_turno].apply(_str_turno) if col_turno else "",
        "PESO_POST": df[col_peso].apply(_to_peso) if col_peso else None,
        "BORG":      df[col_borg].apply(_to_borg) if col_borg else None,
    })
    out = out[out["JUGADOR"].astype(str).str.strip().ne("") & out["FECHA"].notna()]
    return out.reset_index(drop=True)


def detectar_duplicados(pre: pd.DataFrame, post: pd.DataFrame) -> pd.DataFrame:
    """Detecta envíos duplicados (mismo jugador+fecha+turno). Devuelve DF con
    columnas: tipo, jugador, fecha, turno, n_envios."""
    alertas = []
    for tipo, df in (("PRE", pre), ("POST", post)):
        if df.empty:
            continue
        grp = df.groupby(["JUGADOR", "FECHA", "TURNO"]).size().reset_index(name="n_envios")
        dups = grp[grp["n_envios"] > 1]
        for _, r in dups.iterrows():
            alertas.append({
                "tipo": tipo,
                "jugador": r["JUGADOR"],
                "fecha": r["FECHA"],
                "turno": r["TURNO"],
                "n_envios": int(r["n_envios"]),
            })
    return pd.DataFrame(alertas)


def consolidar_a_sheet(ss, pre: pd.DataFrame, post: pd.DataFrame) -> dict:
    """Fusiona las respuestas del Form con las hojas BORG/PESO/WELLNESS existentes.

    Reglas:
    - Si ya existe una fila con mismo (FECHA, TURNO, JUGADOR) en la hoja
      oficial, la respuesta del Form tiene PRIORIDAD (se actualiza).
    - Si no existe, se añade.
    - Si hay duplicados del Form, se queda con el último (por TIMESTAMP).

    Devuelve un dict con contadores de lo consolidado.
    """
    import gspread
    contadores = {"peso_nuevos": 0, "peso_actualizados": 0,
                  "borg_nuevos": 0, "borg_actualizados": 0,
                  "wellness_nuevos": 0, "wellness_actualizados": 0}

    # Deduplicar respuestas Form: si un jugador envía 2 veces para el mismo (día,turno),
    # nos quedamos con la más reciente por TIMESTAMP
    def _dedup_ultimo(df):
        if df.empty:
            return df
        df2 = df.copy()
        df2["__ts"] = pd.to_datetime(df2["TIMESTAMP"], errors="coerce")
        df2 = df2.sort_values("__ts").drop_duplicates(["JUGADOR", "FECHA", "TURNO"], keep="last")
        return df2.drop(columns=["__ts"])

    pre_u = _dedup_ultimo(pre)
    post_u = _dedup_ultimo(post)

    # PESO: combinar PRE + POST por (FECHA, TURNO, JUGADOR)
    if not pre_u.empty or not post_u.empty:
        peso_ws = ss.worksheet("PESO")
        peso_existing = pd.DataFrame(peso_ws.get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        ))
        if peso_existing.empty:
            peso_existing = pd.DataFrame(columns=["FECHA", "TURNO", "JUGADOR", "PESO_PRE", "PESO_POST", "H2O_L"])
        else:
            # Normalizar FECHA a string YYYY-MM-DD
            peso_existing["FECHA"] = peso_existing["FECHA"].apply(_parse_fecha)
            for c in ["PESO_PRE", "PESO_POST", "H2O_L"]:
                if c in peso_existing.columns:
                    peso_existing[c] = peso_existing[c].apply(_to_float)
                else:
                    peso_existing[c] = None

        # Construir combinado de Form
        form_peso = pd.DataFrame()
        if not pre_u.empty:
            form_peso = pre_u[["FECHA", "TURNO", "JUGADOR", "PESO_PRE"]].copy()
        if not post_u.empty:
            post_peso = post_u[["FECHA", "TURNO", "JUGADOR", "PESO_POST"]].copy()
            if form_peso.empty:
                form_peso = post_peso
                form_peso["PESO_PRE"] = None
            else:
                form_peso = form_peso.merge(post_peso, on=["FECHA", "TURNO", "JUGADOR"], how="outer")

        if "PESO_POST" not in form_peso.columns:
            form_peso["PESO_POST"] = None
        form_peso["H2O_L"] = None

        # Merge con existente. Priorizamos Form si está
        merged = peso_existing.merge(
            form_peso, on=["FECHA", "TURNO", "JUGADOR"], how="outer", suffixes=("_old", "_form")
        )
        def _pick(a, b):
            return b if (b is not None and pd.notna(b)) else a
        merged["PESO_PRE"]  = merged.apply(lambda r: _pick(r.get("PESO_PRE_old"),  r.get("PESO_PRE_form")),  axis=1)
        merged["PESO_POST"] = merged.apply(lambda r: _pick(r.get("PESO_POST_old"), r.get("PESO_POST_form")), axis=1)
        merged["H2O_L"]     = merged.apply(lambda r: _pick(r.get("H2O_L_old"),     r.get("H2O_L_form")),     axis=1)
        final_peso = merged[["FECHA", "TURNO", "JUGADOR", "PESO_PRE", "PESO_POST", "H2O_L"]].copy()
        final_peso = final_peso.sort_values(["FECHA", "TURNO", "JUGADOR"]).reset_index(drop=True)
        # Contar nuevos/actualizados
        keys_existing = set(zip(peso_existing.get("FECHA", []), peso_existing.get("TURNO", []), peso_existing.get("JUGADOR", [])))
        keys_form = set(zip(form_peso.get("FECHA", []), form_peso.get("TURNO", []), form_peso.get("JUGADOR", [])))
        contadores["peso_nuevos"] = len(keys_form - keys_existing)
        contadores["peso_actualizados"] = len(keys_form & keys_existing)

        _escribir_hoja(ss, "PESO", final_peso)

    # BORG: del Form POST
    if not post_u.empty:
        borg_ws = ss.worksheet("BORG")
        borg_existing = pd.DataFrame(borg_ws.get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        ))
        if borg_existing.empty:
            borg_existing = pd.DataFrame(columns=["FECHA", "TURNO", "JUGADOR", "BORG"])
        else:
            borg_existing["FECHA"] = borg_existing["FECHA"].apply(_parse_fecha)

        form_borg = post_u[["FECHA", "TURNO", "JUGADOR", "BORG"]].copy()
        merged = borg_existing.merge(form_borg, on=["FECHA", "TURNO", "JUGADOR"], how="outer", suffixes=("_old", "_form"))
        if "BORG_form" in merged.columns:
            merged["BORG"] = merged.apply(lambda r: r.get("BORG_form") if pd.notna(r.get("BORG_form")) else r.get("BORG_old"), axis=1)
        else:
            merged["BORG"] = merged.get("BORG_old")
        final_borg = merged[["FECHA", "TURNO", "JUGADOR", "BORG"]].sort_values(["FECHA", "TURNO", "JUGADOR"]).reset_index(drop=True)
        keys_existing = set(zip(borg_existing.get("FECHA", []), borg_existing.get("TURNO", []), borg_existing.get("JUGADOR", [])))
        keys_form = set(zip(form_borg["FECHA"], form_borg["TURNO"], form_borg["JUGADOR"]))
        contadores["borg_nuevos"] = len(keys_form - keys_existing)
        contadores["borg_actualizados"] = len(keys_form & keys_existing)
        _escribir_hoja(ss, "BORG", final_borg)

    # WELLNESS: del Form PRE (solo filas con al menos un campo wellness relleno)
    if not pre_u.empty:
        well_cols = ["SUENO", "FATIGA", "MOLESTIAS", "ANIMO"]
        form_well = pre_u[pre_u[well_cols].notna().any(axis=1)][["FECHA", "JUGADOR"] + well_cols].copy()
        if not form_well.empty:
            form_well["TOTAL"] = form_well[well_cols].sum(axis=1)
            well_ws = ss.worksheet("WELLNESS")
            well_existing = pd.DataFrame(well_ws.get_all_records(
                value_render_option=gspread.utils.ValueRenderOption.unformatted
            ))
            if well_existing.empty:
                well_existing = pd.DataFrame(columns=["FECHA", "JUGADOR", "SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL"])
            else:
                well_existing["FECHA"] = well_existing["FECHA"].apply(_parse_fecha)
            merged = well_existing.merge(form_well, on=["FECHA", "JUGADOR"], how="outer", suffixes=("_old", "_form"))
            for c in well_cols + ["TOTAL"]:
                col_form = c + "_form"
                col_old  = c + "_old"
                if col_form in merged.columns:
                    merged[c] = merged.apply(lambda r: r.get(col_form) if pd.notna(r.get(col_form)) else r.get(col_old), axis=1)
                else:
                    merged[c] = merged.get(col_old)
            final_well = merged[["FECHA", "JUGADOR"] + well_cols + ["TOTAL"]].sort_values(["FECHA", "JUGADOR"]).reset_index(drop=True)
            keys_existing = set(zip(well_existing.get("FECHA", []), well_existing.get("JUGADOR", [])))
            keys_form = set(zip(form_well["FECHA"], form_well["JUGADOR"]))
            contadores["wellness_nuevos"] = len(keys_form - keys_existing)
            contadores["wellness_actualizados"] = len(keys_form & keys_existing)
            _escribir_hoja(ss, "WELLNESS", final_well)

    return contadores


def _escribir_hoja(ss, nombre, df: pd.DataFrame):
    """Escribe un DataFrame a una hoja existente (la limpia antes)."""
    import time
    ws = ss.worksheet(nombre)
    ws.clear()
    time.sleep(0.3)
    df2 = df.where(pd.notnull(df), "").astype(object)
    rows = [df2.columns.tolist()] + df2.values.tolist()
    ws.update("A1", rows)
    time.sleep(0.3)
