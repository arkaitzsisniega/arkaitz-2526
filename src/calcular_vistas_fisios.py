"""
calcular_vistas_fisios.py — Recalcula los campos automáticos del Sheet
de Lesiones y Tratamientos:

  · LESIONES (columnas calculadas):
      - dias_baja_real (fecha_alta - fecha_lesion, si hay alta)
      - diferencia_dias (real - estimado)
      - total_sesiones    \\
      - entrenos_perdidos  \\
      - gym_perdidos        > contadas contra SESIONES del Sheet principal
      - partidos_perdidos  /
      - recup_perdidos    /
      - minutos_perdidos
      - estado_actual (si vacío y no hay fecha_alta → ACTIVA;
                         si fecha_alta → ALTA)

  · _VISTA_LESIONES: tabla limpia para el dashboard
  · _VISTA_RESUMEN: agregado por jugador
  · _VISTA_TRATAMIENTOS_RESUMEN: tratamientos por jugador

Ejecutar:
  /usr/bin/python3 src/calcular_vistas_fisios.py

Tras /consolidar o tras añadir lesiones/tratamientos, se ejecuta
automáticamente desde el bot.
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


def _connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def _to_date(x):
    """Convierte serial Google Sheets, string ISO o europea, a Timestamp."""
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


def _to_minutos(x):
    """Convierte un valor de minutos: puede ser int (60), float (60.5),
    string ('60'), o formato HH:MM:SS / MM:SS."""
    if x is None or x == "":
        return 0
    if isinstance(x, (int, float)):
        return float(x) if not pd.isna(x) else 0
    s = str(x).strip()
    if ":" in s:
        partes = s.split(":")
        try:
            if len(partes) == 3:
                h, m, sec = int(partes[0]), int(partes[1]), int(partes[2])
                return h * 60 + m + sec / 60
            elif len(partes) == 2:
                m, sec = int(partes[0]), int(partes[1])
                return m + sec / 60
        except ValueError:
            return 0
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return 0


def _leer_sesiones(sh_principal) -> pd.DataFrame:
    """Lee SESIONES del Sheet principal, devuelve DataFrame con columnas
    útiles (FECHA, TIPO_SESION, MINUTOS)."""
    ws = sh_principal.worksheet("SESIONES")
    data = ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted
    )
    df = pd.DataFrame(data)
    if df.empty:
        return df
    # Normalizar
    if "FECHA" in df.columns:
        df["FECHA"] = df["FECHA"].apply(_to_date)
    if "MINUTOS" in df.columns:
        df["MINUTOS"] = df["MINUTOS"].apply(_to_minutos)
    if "TIPO_SESION" in df.columns:
        df["TIPO_SESION"] = df["TIPO_SESION"].astype(str).str.upper().str.strip()
    return df


def _calcular_columnas_lesiones(lesiones: pd.DataFrame,
                                  sesiones: pd.DataFrame) -> pd.DataFrame:
    """Calcula campos automáticos: días baja real, diferencia, sesiones
    perdidas por tipo, minutos perdidos, estado actual."""
    df = lesiones.copy()
    if df.empty:
        return df

    # Asegurar dtypes
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
                "total_sesiones": "",
                "entrenos_perdidos": "",
                "gym_perdidos": "",
                "partidos_perdidos": "",
                "recup_perdidos": "",
                "minutos_perdidos": "",
                "estado_calc": row.get("estado_actual", "") or "ACTIVA",
            })
        fa_eff = fa if pd.notna(fa) else hoy
        dias_real = max(0, (fa_eff - fl).days)
        est = row["dias_baja_estimados"]
        diff = (dias_real - est) if est is not None else ""

        # Filtrar sesiones en el rango
        if not sesiones.empty and "FECHA" in sesiones.columns:
            mask = (sesiones["FECHA"] >= fl) & (sesiones["FECHA"] <= fa_eff)
            ses_rango = sesiones[mask]
            total = len(ses_rango)
            tipos = ses_rango.get("TIPO_SESION", pd.Series(dtype=str))
            entrenos = (~tipos.isin(["PARTIDO", "GYM", "RECUP"])).sum()
            gym = (tipos == "GYM").sum()
            partidos = (tipos == "PARTIDO").sum()
            recup = (tipos == "RECUP").sum()
            mins = ses_rango.get("MINUTOS", pd.Series(dtype=float)).sum()
        else:
            total = entrenos = gym = partidos = recup = 0
            mins = 0

        # Estado
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
            "total_sesiones": int(total),
            "entrenos_perdidos": int(entrenos),
            "gym_perdidos": int(gym),
            "partidos_perdidos": int(partidos),
            "recup_perdidos": int(recup),
            "minutos_perdidos": round(float(mins), 1),
            "estado_calc": estado_calc,
        })

    calculados = df.apply(calc, axis=1)
    for col in calculados.columns:
        if col == "estado_calc":
            df["estado_actual"] = calculados[col]
        else:
            df[col] = calculados[col]
    return df


def _escribir_lesiones(sh_fisios, df: pd.DataFrame):
    """Escribe las columnas calculadas de vuelta en LESIONES (mantiene
    el resto intacto). Solo actualiza valores, no estructura."""
    ws = sh_fisios.worksheet("LESIONES")
    cab = ws.row_values(1)
    if not cab:
        print("   ⚠️ Hoja LESIONES sin cabecera")
        return

    # Convertir df a lista de listas (orden de cabecera)
    df = df.copy()
    # Convertir fechas a string ISO
    for c in ("fecha_lesion", "fecha_alta", "fecha_revision",
                "vuelta_programada"):
        if c in df.columns:
            df[c] = df[c].apply(
                lambda v: v.strftime("%Y-%m-%d")
                if pd.notna(v) and isinstance(v, pd.Timestamp) else (v or ""))
    # Reemplazar NaN
    df = df.fillna("")
    # Construir filas en orden de cabecera
    filas = []
    for _, r in df.iterrows():
        fila = []
        for c in cab:
            v = r.get(c, "")
            if pd.isna(v):
                v = ""
            fila.append(str(v) if v != "" else "")
        filas.append(fila)

    # Escribir desde fila 2 en adelante (preservando cabecera)
    if filas:
        last_col = chr(64 + len(cab))
        rng = f"A2:{last_col}{1+len(filas)}"
        ws.update(values=filas, range_name=rng,
                    value_input_option="USER_ENTERED")
        print(f"   ✅ {len(filas)} lesiones actualizadas en LESIONES")


def _escribir_vista(sh_fisios, nombre_hoja: str, df: pd.DataFrame):
    """Crea o actualiza una hoja vista. Limpia y reescribe entera."""
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

    titulos = [w.title for w in sh_fisios.worksheets()]
    if nombre_hoja in titulos:
        ws = sh_fisios.worksheet(nombre_hoja)
        ws.clear()
        time.sleep(0.5)
    else:
        ws = sh_fisios.add_worksheet(title=nombre_hoja,
                                       rows=max(len(valores) + 5, 100),
                                       cols=len(cab) + 5)
        time.sleep(0.5)
    if cab:
        ws.update(values=[cab] + valores,
                    range_name=f"A1:{chr(64+len(cab))}{1+len(valores)}",
                    value_input_option="USER_ENTERED")
    print(f"   ✅ {nombre_hoja}: {len(valores)} filas")


def _vista_lesiones(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla limpia con las columnas más relevantes para el dashboard."""
    if df.empty:
        return df
    cols = ["id_lesion", "jugador", "dorsal", "fecha_lesion", "fecha_alta",
            "tipo_lesion", "zona_corporal", "lado", "mecanismo",
            "estado_actual", "dias_baja_estimados", "dias_baja_real",
            "diferencia_dias", "total_sesiones", "entrenos_perdidos",
            "gym_perdidos", "partidos_perdidos", "recup_perdidos",
            "minutos_perdidos", "recaida"]
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def _vista_resumen(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen por jugador: total lesiones, días baja totales,
    último estado, fecha última lesión."""
    if df.empty:
        return df
    df = df.copy()
    df["fecha_lesion"] = df["fecha_lesion"].apply(_to_date)
    df["dias_baja_real"] = pd.to_numeric(df["dias_baja_real"], errors="coerce")
    df["minutos_perdidos"] = pd.to_numeric(df["minutos_perdidos"], errors="coerce")

    hoy = pd.Timestamp.now().normalize()
    grouped = df.groupby("jugador").agg(
        lesiones_total=("id_lesion", "count"),
        lesiones_activas=("estado_actual", lambda s: (s.astype(str).str.upper()
                                                        .isin(["ACTIVA", "EN_RECUP", "RECAÍDA"])).sum()),
        dias_baja_total=("dias_baja_real", "sum"),
        minutos_perdidos_total=("minutos_perdidos", "sum"),
        ultima_fecha_lesion=("fecha_lesion", "max"),
    ).reset_index()

    grouped["dias_desde_ultima_lesion"] = grouped["ultima_fecha_lesion"].apply(
        lambda d: (hoy - d).days if pd.notna(d) else "")
    return grouped


def _vista_tratamientos(sh_fisios) -> pd.DataFrame:
    """Resumen de tratamientos por jugador."""
    try:
        ws = sh_fisios.worksheet("TRATAMIENTOS")
    except Exception:
        return pd.DataFrame()
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "fecha" in df.columns:
        df["fecha"] = df["fecha"].apply(_to_date)
    if "duracion_min" in df.columns:
        df["duracion_min"] = df["duracion_min"].apply(_to_minutos)

    if "jugador" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby("jugador").agg(
        tratamientos_total=("id_tratamiento", "count"),
        minutos_total=("duracion_min", "sum"),
        ultima_fecha=("fecha", "max"),
    ).reset_index()
    return grouped


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

    print("📥 Leyendo LESIONES del Sheet de fisios…")
    ws = sh_fisios.worksheet("LESIONES")
    data = ws.get_all_records()
    lesiones = pd.DataFrame(data)
    print(f"   ✅ {len(lesiones)} lesiones cargadas")
    print()

    if lesiones.empty:
        print("ℹ️ No hay lesiones que procesar todavía.")
    else:
        print("🧮 Calculando columnas automáticas…")
        lesiones = _calcular_columnas_lesiones(lesiones, sesiones)
        time.sleep(1)
        _escribir_lesiones(sh_fisios, lesiones)
        time.sleep(1)
        print()

    print("📊 Generando vistas…")
    _escribir_vista(sh_fisios, "_VISTA_LESIONES", _vista_lesiones(lesiones))
    time.sleep(1)
    _escribir_vista(sh_fisios, "_VISTA_RESUMEN", _vista_resumen(lesiones))
    time.sleep(1)
    _escribir_vista(sh_fisios, "_VISTA_TRATAMIENTOS_RESUMEN",
                      _vista_tratamientos(sh_fisios))

    print()
    print("=" * 70)
    print("✅ Vistas fisios actualizadas")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
