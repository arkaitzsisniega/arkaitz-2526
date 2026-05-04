"""
calcular_vistas_fisios.py — Recalcula campos automáticos del Sheet de
Lesiones, Tratamientos y Temperatura. Actualiza también las vistas
agregadas que el dashboard consume.

Campos calculados en LESIONES:
  - dias_baja_real           (fecha_alta - fecha_lesion)
  - diferencia_dias          (real - estimados)
  - total_sesiones_perdidas  (contadas contra SESIONES del principal)
  - entrenos_perdidos        (no PARTIDO/GYM/RECUP)
  - partidos_perdidos
  - estado_actual            (si vacío y hay fecha_alta → ALTA)

Campos calculados en TEMPERATURA:
  - asimetria_c (= temp_izda_c - temp_dcha_c)
  - alerta       (= "ALERTA" si |asimetria| > 0.5°C)

Vistas generadas:
  - _VISTA_LESIONES               (todas las lesiones limpias)
  - _VISTA_RESUMEN_JUGADOR        (lesiones, días baja, etc.)
  - _VISTA_TRATAMIENTOS           (resumen)
  - _VISTA_TEMPERATURA_ALERTAS    (asimetrías recientes)

Ejecutar:
  /usr/bin/python3 src/calcular_vistas_fisios.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_PRINCIPAL = "Arkaitz - Datos Temporada 2526"
SHEET_FISIOS = "Arkaitz - Lesiones y Tratamientos 2526"

# Umbral de asimetría térmica (°C) para marcar ALERTA
UMBRAL_ASIMETRIA = 0.5


def _connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def _to_date(x):
    if x is None or x == "":
        return pd.NaT
    if isinstance(x, (int, float)):
        if isinstance(x, float) and pd.isna(x):
            return pd.NaT
        try:
            n = int(x)
        except (ValueError, TypeError):
            return pd.NaT
        if not (1 <= n <= 60000):
            return pd.NaT
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=n)
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(x, dayfirst=True, errors="coerce")
    return ts


def _to_int(x):
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return None


def _to_float(x):
    if x is None or x == "":
        return None
    try:
        return float(str(x).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _leer_sesiones(sh_principal) -> pd.DataFrame:
    ws = sh_principal.worksheet("SESIONES")
    data = ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted
    )
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "FECHA" in df.columns:
        df["FECHA"] = df["FECHA"].apply(_to_date)
    if "TIPO_SESION" in df.columns:
        df["TIPO_SESION"] = df["TIPO_SESION"].astype(str).str.upper().str.strip()
    return df


def _calcular_columnas_lesiones(df: pd.DataFrame,
                                  sesiones: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["fecha_lesion"] = df["fecha_lesion"].apply(_to_date)
    df["fecha_alta"] = df["fecha_alta"].apply(_to_date)
    df["dias_baja_estimados"] = df["dias_baja_estimados"].apply(_to_int)

    hoy = pd.Timestamp.now().normalize()

    def calc(row):
        fl = row["fecha_lesion"]
        fa = row["fecha_alta"]
        if pd.isna(fl):
            return pd.Series({
                "dias_baja_real": "",
                "diferencia_dias": "",
                "total_sesiones_perdidas": "",
                "entrenos_perdidos": "",
                "partidos_perdidos": "",
                "estado_calc": row.get("estado_actual", "") or "ACTIVA",
            })
        fa_eff = fa if pd.notna(fa) else hoy
        dias_real = max(0, (fa_eff - fl).days)
        est = row["dias_baja_estimados"]
        diff = (dias_real - est) if est is not None else ""

        if not sesiones.empty and "FECHA" in sesiones.columns:
            mask = (sesiones["FECHA"] >= fl) & (sesiones["FECHA"] <= fa_eff)
            ses_rango = sesiones[mask]
            total = len(ses_rango)
            tipos = ses_rango.get("TIPO_SESION", pd.Series(dtype=str))
            entrenos = (~tipos.isin(["PARTIDO", "GYM", "RECUP"])).sum()
            partidos = (tipos == "PARTIDO").sum()
        else:
            total = entrenos = partidos = 0

        est_actual = (row.get("estado_actual") or "").strip().upper()
        if pd.notna(fa):
            estado_calc = "ALTA" if not est_actual else est_actual
        elif est_actual:
            estado_calc = est_actual
        else:
            estado_calc = "ACTIVA"

        return pd.Series({
            "dias_baja_real": dias_real,
            "diferencia_dias": diff,
            "total_sesiones_perdidas": int(total),
            "entrenos_perdidos": int(entrenos),
            "partidos_perdidos": int(partidos),
            "estado_calc": estado_calc,
        })

    calculados = df.apply(calc, axis=1)
    for col in calculados.columns:
        if col == "estado_calc":
            df["estado_actual"] = calculados[col]
        else:
            df[col] = calculados[col]
    return df


def _calcular_columnas_temperatura(df: pd.DataFrame) -> pd.DataFrame:
    """asimetria_c = temp_izda_c - temp_dcha_c
    alerta = 'ALERTA' si |asimetria| > UMBRAL_ASIMETRIA, '' si no."""
    if df.empty:
        return df
    df = df.copy()
    df["temp_izda_c"] = df["temp_izda_c"].apply(_to_float)
    df["temp_dcha_c"] = df["temp_dcha_c"].apply(_to_float)

    def calc(row):
        izda = row["temp_izda_c"]
        dcha = row["temp_dcha_c"]
        if izda is None or dcha is None:
            return pd.Series({"asimetria_c": "", "alerta": ""})
        asim = round(izda - dcha, 2)
        alerta = "ALERTA" if abs(asim) > UMBRAL_ASIMETRIA else ""
        return pd.Series({"asimetria_c": asim, "alerta": alerta})

    calculados = df.apply(calc, axis=1)
    df["asimetria_c"] = calculados["asimetria_c"]
    df["alerta"] = calculados["alerta"]
    return df


def _escribir_columnas_calculadas(ws, df: pd.DataFrame):
    """Reescribe SOLO las columnas calculadas para no pisar lo manual.
    Asume que el orden de columnas en la hoja coincide con df."""
    if df.empty:
        return
    cab = ws.row_values(1)
    if not cab:
        return
    df = df.copy()
    # Convertir fechas a string ISO
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].apply(
                lambda v: v.strftime("%Y-%m-%d") if pd.notna(v) else "")
    df = df.fillna("")
    filas = []
    for _, r in df.iterrows():
        fila = [str(r.get(c, "")) if r.get(c, "") != "" else "" for c in cab]
        filas.append(fila)
    if filas:
        last_col_letter = chr(64 + min(len(cab), 26)) if len(cab) <= 26 else (
            chr(64 + (len(cab) - 1) // 26) + chr(65 + (len(cab) - 1) % 26))
        ws.update(values=filas,
                    range_name=f"A2:{last_col_letter}{1+len(filas)}",
                    value_input_option="USER_ENTERED")


def _escribir_vista(sh, nombre: str, df: pd.DataFrame):
    if df.empty:
        cab = ["_VACÍO"]
        valores = []
    else:
        df = df.copy()
        for c in df.select_dtypes(include=["datetime64[ns]"]).columns:
            df[c] = df[c].dt.strftime("%Y-%m-%d")
        df = df.fillna("")
        cab = list(df.columns)
        valores = df.astype(str).values.tolist()

    titulos = [w.title for w in sh.worksheets()]
    if nombre in titulos:
        ws = sh.worksheet(nombre)
        ws.clear()
        time.sleep(0.5)
    else:
        ws = sh.add_worksheet(title=nombre,
                                rows=max(len(valores) + 5, 100),
                                cols=len(cab) + 5)
        time.sleep(0.5)
    if cab:
        last_col = chr(64 + len(cab)) if len(cab) <= 26 else 'Z'
        ws.update(values=[cab] + valores,
                    range_name=f"A1:{last_col}{1+len(valores)}",
                    value_input_option="USER_ENTERED")
        # Ocultar la vista (interna)
        sh.batch_update({"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "hidden": True},
                "fields": "hidden",
            }
        }]})
    print(f"   ✅ {nombre}: {len(valores)} filas")


def _vista_lesiones(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = ["id_lesion", "jugador", "dorsal", "fecha_lesion", "fecha_alta",
            "tipo_tejido", "zona_corporal", "lado", "mecanismo", "gravedad",
            "estado_actual", "dias_baja_estimados", "dias_baja_real",
            "diferencia_dias", "total_sesiones_perdidas", "entrenos_perdidos",
            "partidos_perdidos", "recaida"]
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def _vista_resumen_jugador(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "jugador" not in df.columns:
        return df
    df = df.copy()
    df["fecha_lesion"] = df["fecha_lesion"].apply(_to_date)
    df["dias_baja_real"] = pd.to_numeric(df["dias_baja_real"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    grouped = df.groupby("jugador").agg(
        lesiones_total=("id_lesion", "count"),
        lesiones_activas=("estado_actual",
                            lambda s: s.astype(str).str.upper()
                            .isin(["ACTIVA", "EN_RECUP", "RECAÍDA"]).sum()),
        dias_baja_total=("dias_baja_real", "sum"),
        ultima_fecha_lesion=("fecha_lesion", "max"),
    ).reset_index()
    grouped["dias_desde_ultima_lesion"] = grouped["ultima_fecha_lesion"].apply(
        lambda d: (hoy - d).days if pd.notna(d) else "")
    return grouped


def _vista_tratamientos(sh) -> pd.DataFrame:
    try:
        ws = sh.worksheet("TRATAMIENTOS")
    except Exception:
        return pd.DataFrame()
    df = pd.DataFrame(ws.get_all_records())
    if df.empty or "jugador" not in df.columns:
        return df
    if "fecha" in df.columns:
        df["fecha"] = df["fecha"].apply(_to_date)
    if "duracion_min" in df.columns:
        df["duracion_min"] = df["duracion_min"].apply(_to_float)
    grouped = df.groupby(["jugador", "bloque"]).agg(
        tratamientos=("id_tratamiento", "count"),
        minutos_total=("duracion_min", "sum"),
        ultima_fecha=("fecha", "max"),
    ).reset_index()
    return grouped


def _vista_temperatura_alertas(df: pd.DataFrame) -> pd.DataFrame:
    """Mediciones con asimetría > umbral, ordenadas por fecha desc."""
    if df.empty:
        return df
    df = df.copy()
    df = df[df["alerta"].astype(str).str.upper() == "ALERTA"]
    if df.empty:
        return df
    if "fecha" in df.columns:
        df["fecha"] = df["fecha"].apply(_to_date)
    df = df.sort_values("fecha", ascending=False)
    cols = ["fecha", "jugador", "dorsal", "zona", "temp_izda_c",
            "temp_dcha_c", "asimetria_c", "momento", "notas"]
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def main():
    print("=" * 70)
    print("RECALCULAR VISTAS FISIOS")
    print("=" * 70)
    print()
    client = _connect()
    try:
        sh_fisios = client.open(SHEET_FISIOS)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ No encuentro '{SHEET_FISIOS}'. Ejecuta primero "
              f"src/crear_sheet_fisios.py")
        return 1
    sh_principal = client.open(SHEET_PRINCIPAL)

    print("📥 Leyendo SESIONES del Sheet principal…")
    sesiones = _leer_sesiones(sh_principal)
    print(f"   ✅ {len(sesiones)} sesiones cargadas")
    print()

    # ── LESIONES ───────────────────────────────────────────────
    print("📥 Leyendo LESIONES…")
    ws_les = sh_fisios.worksheet("LESIONES")
    lesiones = pd.DataFrame(ws_les.get_all_records())
    print(f"   ✅ {len(lesiones)} lesiones")

    if not lesiones.empty:
        print("🧮 Calculando columnas LESIONES…")
        lesiones = _calcular_columnas_lesiones(lesiones, sesiones)
        time.sleep(1)
        _escribir_columnas_calculadas(ws_les, lesiones)
        print("   ✅ LESIONES actualizadas")
    print()

    # ── TEMPERATURA ────────────────────────────────────────────
    print("📥 Leyendo TEMPERATURA…")
    ws_temp = sh_fisios.worksheet("TEMPERATURA")
    temperatura = pd.DataFrame(ws_temp.get_all_records())
    print(f"   ✅ {len(temperatura)} mediciones")

    if not temperatura.empty:
        print("🧮 Calculando asimetrías TEMPERATURA…")
        temperatura = _calcular_columnas_temperatura(temperatura)
        time.sleep(1)
        _escribir_columnas_calculadas(ws_temp, temperatura)
        print("   ✅ TEMPERATURA actualizada")
    print()

    # ── VISTAS ─────────────────────────────────────────────────
    print("📊 Generando vistas…")
    _escribir_vista(sh_fisios, "_VISTA_LESIONES", _vista_lesiones(lesiones))
    time.sleep(1)
    _escribir_vista(sh_fisios, "_VISTA_RESUMEN_JUGADOR",
                      _vista_resumen_jugador(lesiones))
    time.sleep(1)
    _escribir_vista(sh_fisios, "_VISTA_TRATAMIENTOS",
                      _vista_tratamientos(sh_fisios))
    time.sleep(1)
    _escribir_vista(sh_fisios, "_VISTA_TEMPERATURA_ALERTAS",
                      _vista_temperatura_alertas(temperatura))

    print()
    print("=" * 70)
    print("✅ Vistas fisios actualizadas")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
