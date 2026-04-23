"""
calcular_vistas.py
Lee SESIONES, BORG, PESO y WELLNESS del Google Sheet,
calcula todas las métricas y escribe hojas de vista
que Looker Studio consumirá directamente.

Ejecutar después de cada actualización de datos.
"""

import warnings, time
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

CREDS_FILE = "google_credentials.json"
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Conexión ──────────────────────────────────────────────────────────────────

def connect():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def to_num(x):
    """Convierte a float tolerando coma decimal española (71,5 → 71.5)."""
    if x is None or x == "":
        return np.nan
    if isinstance(x, (int, float)):
        return float(x)
    return pd.to_numeric(str(x).strip().replace(",", "."), errors="coerce")


# ── Lectura de datos crudos ───────────────────────────────────────────────────

def _to_date(x):
    """Convierte serial de Google Sheets o string a pd.Timestamp de forma robusta.
    - Seriales (int/float): días desde 1899-12-30 (solo si está en rango razonable).
    - Strings: intenta formato ISO primero (sin dayfirst, evita que '2025-08-04'
      se interprete erróneamente como '2025-04-08')."""
    if x is None or x == "":
        return pd.NaT
    if isinstance(x, (int, float)):
        if isinstance(x, float) and pd.isna(x):
            return pd.NaT
        try:
            n = int(x)
        except (ValueError, TypeError):
            return pd.NaT
        # rango razonable: 1 (1899-12-31) a 60000 (~2063). Rechaza seriales raros.
        if not (1 <= n <= 60000):
            return pd.NaT
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=n)
    # String: ISO primero, europeo después
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(x, dayfirst=True, errors="coerce")
    return ts


def leer_hoja(ss, nombre, parse_dates=None):
    ws = ss.worksheet(nombre)
    # value_render_option unformatted → números como float puro, sin formato de locale
    # (evita que Google Sheets en locale español devuelva "71,5" en vez de 71.5)
    data = ws.get_all_records(
        value_render_option=gspread.utils.ValueRenderOption.unformatted
    )
    df = pd.DataFrame(data)
    if parse_dates:
        for col in parse_dates:
            if col in df.columns:
                df[col] = df[col].apply(_to_date)
    return df

# ── Escritura de vista en Google Sheets ──────────────────────────────────────

def escribir_vista(ss, nombre_hoja, df):
    df = df.copy()
    # Convertir fechas a string para Google Sheets
    for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]):
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    # Reemplazar NaN, inf
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.where(pd.notnull(df), None)

    existing = {ws.title for ws in ss.worksheets()}
    if nombre_hoja in existing:
        ws = ss.worksheet(nombre_hoja)
        ws.clear()
        time.sleep(0.5)
    else:
        ws = ss.add_worksheet(title=nombre_hoja, rows=max(len(df)+10, 100), cols=len(df.columns)+2)
        time.sleep(1)

    headers = [df.columns.tolist()]
    rows    = df.astype(object).where(pd.notnull(df), "").values.tolist()
    ws.update("A1", headers + rows)
    time.sleep(1)
    print(f"  ✓ {nombre_hoja}: {len(df)} filas")
    return ws

# ── VISTA 1: CARGA POR SESIÓN ─────────────────────────────────────────────────
# Une SESIONES + BORG. Una fila por (jugador × sesión).

def vista_carga(ses, borg):
    # Unir BORG con info de sesión
    df = borg.merge(
        ses[["FECHA", "TURNO", "TIPO_SESION", "MINUTOS", "SEMANA", "COMPETICION"]],
        on=["FECHA", "TURNO"],
        how="left"
    )
    # Convertir BORG a numérico (las letras de estado S/A/L/N/D/NC → NaN)
    # BORG crudo con letras se preserva en `borg` (entrada) para vista_recuento.
    df["BORG"]  = pd.to_numeric(df["BORG"], errors="coerce")
    df["CARGA"] = df["BORG"] * pd.to_numeric(df["MINUTOS"], errors="coerce")
    df["FECHA_STR"]  = df["FECHA"].dt.strftime("%Y-%m-%d")
    df["DIA_SEMANA"] = df["FECHA"].dt.day_name()
    df = df.sort_values(["FECHA", "JUGADOR"])
    return df[["FECHA", "FECHA_STR", "SEMANA", "DIA_SEMANA", "TURNO",
               "JUGADOR", "TIPO_SESION", "COMPETICION", "MINUTOS", "BORG", "CARGA"]]


# ── VISTA 2: CARGA SEMANAL + ACWR EWMA ───────────────────────────────────────

def acwr_ewma(serie, lambda_aguda=0.1316, lambda_cronica=0.0339):
    """ACWR con media exponencial ponderada.
       λ_aguda = 2/(14+1)≈0.1316 → ~7 días efectivos
       λ_crónica = 2/(56+1)≈0.0351 → ~28 días efectivos
    """
    aguda   = serie.ewm(alpha=lambda_aguda,  adjust=False).mean()
    cronica = serie.ewm(alpha=lambda_cronica, adjust=False).mean()
    ratio   = aguda / cronica.replace(0, np.nan)
    return aguda, cronica, ratio


def vista_semanal(carga_df):
    resultados = []
    jugadores  = carga_df["JUGADOR"].dropna().unique()

    # Rango completo de lunes
    fecha_min = carga_df["FECHA"].min()
    fecha_max = carga_df["FECHA"].max()
    lunes = pd.date_range(
        start=fecha_min - pd.Timedelta(days=fecha_min.weekday()),
        end  =fecha_max,
        freq ="W-MON"
    )

    for jugador in jugadores:
        jdf = carga_df[carga_df["JUGADOR"] == jugador].copy()
        # Serie diaria de carga (rellenar con 0 los días sin sesión)
        daily = (jdf.groupby("FECHA")["CARGA"].sum()
                   .reindex(pd.date_range(fecha_min, fecha_max), fill_value=0))

        aguda, cronica, ratio = acwr_ewma(daily)

        for lun in lunes:
            semana_mask = (daily.index >= lun) & (daily.index < lun + pd.Timedelta(days=7))
            if semana_mask.sum() == 0:
                continue

            carga_sem  = float(daily[semana_mask].sum())
            # Saltar semanas sin carga real para este jugador (evita semanas fantasma)
            if carga_sem == 0:
                continue

            sesiones   = int((jdf["FECHA"].dt.isocalendar().week ==
                              lun.isocalendar()[1]).sum())
            borg_medio = float(jdf[jdf["FECHA"].dt.isocalendar().week ==
                                   lun.isocalendar()[1]]["BORG"].mean()) if sesiones else np.nan

            # ACWR al último día de la semana (domingo)
            domingo = lun + pd.Timedelta(days=6)
            if domingo in ratio.index:
                acwr_val    = round(float(ratio[domingo]), 3)
                aguda_val   = round(float(aguda[domingo]), 1)
                cronica_val = round(float(cronica[domingo]), 1)
            else:
                acwr_val = aguda_val = cronica_val = np.nan

            # Monotonía = media diaria / desviación diaria
            cargas_dia = daily[semana_mask]
            monotonia  = (float(cargas_dia.mean() / cargas_dia.std())
                          if cargas_dia.std() > 0 else np.nan)
            fatiga     = carga_sem * monotonia if not np.isnan(monotonia) else np.nan

            # Semáforo ACWR
            if np.isnan(acwr_val):
                semaforo = "GRIS"
            elif acwr_val < 0.8:
                semaforo = "AZUL"   # infra-carga
            elif acwr_val <= 1.3:
                semaforo = "VERDE"
            elif acwr_val <= 1.5:
                semaforo = "AMARILLO"
            else:
                semaforo = "ROJO"

            resultados.append({
                "FECHA_LUNES":  lun,
                "SEMANA_ISO":   lun.isocalendar()[1],
                "AÑO":          lun.year,
                "JUGADOR":      jugador,
                "CARGA_SEMANAL": round(carga_sem, 0),
                "SESIONES":     sesiones,
                "BORG_MEDIO":   round(borg_medio, 2) if not np.isnan(borg_medio) else None,
                "ACWR":         acwr_val,
                "CARGA_AGUDA":  aguda_val,
                "CARGA_CRONICA": cronica_val,
                "MONOTONIA":    round(monotonia, 3) if not np.isnan(monotonia) else None,
                "FATIGA":       round(fatiga, 0)    if not np.isnan(fatiga)    else None,
                "SEMAFORO":     semaforo,
            })

    return pd.DataFrame(resultados).sort_values(["FECHA_LUNES", "JUGADOR"])


# ── VISTA 3: PESO ─────────────────────────────────────────────────────────────

def vista_peso(peso, ses):
    df = peso.merge(
        ses[["FECHA", "TURNO", "TIPO_SESION", "SEMANA", "COMPETICION"]],
        on=["FECHA", "TURNO"], how="left"
    )
    df["PESO_PRE"]  = pd.to_numeric(df["PESO_PRE"],  errors="coerce")
    df["PESO_POST"] = pd.to_numeric(df["PESO_POST"], errors="coerce")
    df["H2O_L"]     = pd.to_numeric(df["H2O_L"],     errors="coerce")

    # Sanidad ANTES de calcular derivados: pesos fuera del rango fisiológico (40-200 kg) → NaN
    # Captura errores tipo "71,5→715" o valores de tipeo (9.2 para un adulto).
    for c in ("PESO_PRE", "PESO_POST"):
        df[c] = df[c].where(df[c].between(40, 200), np.nan)

    df["DIFERENCIA"]   = df["PESO_PRE"] - df["PESO_POST"]
    df["PCT_PERDIDA"]  = (df["DIFERENCIA"] / df["PESO_PRE"] * 100).round(2)
    df["ALERTA_PESO"]  = df["PCT_PERDIDA"].apply(
        lambda x: "ROJO" if x > 3 else ("NARANJA" if x > 2 else ("VERDE" if x >= 0 else "GRIS"))
        if pd.notnull(x) else "GRIS"
    )
    df["DIA_SEMANA"] = df["FECHA"].dt.day_name()

    # Baseline personal (media primeras 4 semanas disponibles)
    baseline = (df.groupby("JUGADOR")["PESO_PRE"]
                  .apply(lambda s: s.iloc[:max(1, len(s)//5)].mean())
                  .rename("BASELINE_PRE"))
    df = df.merge(baseline.reset_index(), on="JUGADOR", how="left")
    df["DESVIACION_BASELINE"] = (df["PESO_PRE"] - df["BASELINE_PRE"]).round(2)

    return df[["FECHA", "SEMANA", "DIA_SEMANA", "TURNO", "JUGADOR",
               "TIPO_SESION", "COMPETICION",
               "PESO_PRE", "PESO_POST", "DIFERENCIA", "PCT_PERDIDA",
               "H2O_L", "ALERTA_PESO", "BASELINE_PRE", "DESVIACION_BASELINE"
               ]].sort_values(["FECHA", "JUGADOR"])


# ── VISTA 4: WELLNESS ─────────────────────────────────────────────────────────

def vista_wellness(well, ses):
    df = well.copy()
    df["SUENO"]     = pd.to_numeric(df["SUENO"],     errors="coerce")
    df["FATIGA"]    = pd.to_numeric(df["FATIGA"],    errors="coerce")
    df["MOLESTIAS"] = pd.to_numeric(df["MOLESTIAS"], errors="coerce")
    df["ANIMO"]     = pd.to_numeric(df["ANIMO"],     errors="coerce")
    df["TOTAL"]     = pd.to_numeric(df["TOTAL"],     errors="coerce")
    df["DIA_SEMANA"] = df["FECHA"].dt.day_name()

    # Semana ISO
    semana_map = ses[["FECHA", "SEMANA"]].drop_duplicates()
    df = df.merge(semana_map, on="FECHA", how="left")

    # Media móvil 7 días por jugador
    df = df.sort_values(["JUGADOR", "FECHA"])
    df["WELLNESS_7D"] = (
        df.groupby("JUGADOR")["TOTAL"]
          .transform(lambda s: s.rolling(7, min_periods=1).mean().round(2))
    )

    # Baseline personal
    baseline = (df.groupby("JUGADOR")["TOTAL"]
                  .apply(lambda s: s.iloc[:max(1, len(s)//5)].mean())
                  .rename("BASELINE_WELLNESS"))
    df = df.merge(baseline.reset_index(), on="JUGADOR", how="left")
    df["DESVIACION_BASELINE"] = (df["TOTAL"] - df["BASELINE_WELLNESS"]).round(2)

    # Semáforo wellness
    df["SEMAFORO_WELLNESS"] = df["TOTAL"].apply(
        lambda x: "ROJO" if x <= 10 else ("NARANJA" if x <= 13 else "VERDE")
        if pd.notnull(x) else "GRIS"
    )

    return df[["FECHA", "SEMANA", "DIA_SEMANA", "JUGADOR",
               "SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL",
               "WELLNESS_7D", "BASELINE_WELLNESS", "DESVIACION_BASELINE",
               "SEMAFORO_WELLNESS"]].sort_values(["FECHA", "JUGADOR"])


# ── VISTA 5: SEMÁFORO DE RIESGO COMBINADO ─────────────────────────────────────

def vista_semaforo(semanal_df, wellness_df, peso_df):
    """Una fila por jugador con su estado actual (última semana disponible)."""
    resultados = []
    jugadores = semanal_df["JUGADOR"].unique()

    ultima_semana = semanal_df["FECHA_LUNES"].max()

    for jugador in jugadores:
        # ACWR última semana
        jcarga = semanal_df[
            (semanal_df["JUGADOR"] == jugador) &
            (semanal_df["FECHA_LUNES"] == ultima_semana)
        ]
        acwr       = float(jcarga["ACWR"].iloc[0])       if len(jcarga) else np.nan
        monotonia  = float(jcarga["MONOTONIA"].iloc[0])  if len(jcarga) else np.nan
        sem_acwr   = jcarga["SEMAFORO"].iloc[0]          if len(jcarga) else "GRIS"

        # Wellness — últimas 7 SESIONES (no días)
        jwell_all = wellness_df[wellness_df["JUGADOR"] == jugador].sort_values("FECHA")
        jwell7    = jwell_all.tail(7)
        well_medio   = float(jwell7["TOTAL"].mean())           if len(jwell7) else np.nan
        below_15     = int((jwell7["TOTAL"] < 15).sum())       if len(jwell7) else 0
        sem_well     = ("ROJO"    if well_medio <= 10 else
                        "NARANJA" if well_medio <= 13 else
                        "VERDE")  if not np.isnan(well_medio)  else "GRIS"

        # Peso PRE — media de las últimas 3 sesiones vs baseline (media últimos 2 meses)
        # Usar 3 sesiones evita que un error puntual de tipeo distorsione la alerta.
        jpeso = (peso_df[(peso_df["JUGADOR"] == jugador) & peso_df["FECHA"].notna()]
                 .drop_duplicates(["FECHA", "TURNO"] if "TURNO" in peso_df.columns else ["FECHA"])
                 .sort_values("FECHA"))
        peso_valido = jpeso[["FECHA", "PESO_PRE"]].dropna(subset=["PESO_PRE"])
        if len(peso_valido) >= 1:
            fecha_ult  = peso_valido["FECHA"].max()
            fecha_2m   = fecha_ult - pd.Timedelta(days=60)
            base_serie = peso_valido[peso_valido["FECHA"] >= fecha_2m]["PESO_PRE"]
            baseline_2m = float(base_serie.mean()) if len(base_serie) >= 3 else float(peso_valido["PESO_PRE"].mean())
            ult3 = peso_valido["PESO_PRE"].tail(3)
            peso_reciente = float(ult3.mean()) if len(ult3) >= 1 else np.nan
            if np.isnan(baseline_2m) or np.isnan(peso_reciente):
                desv     = np.nan
                sem_peso = "GRIS"
            else:
                desv = round(peso_reciente - baseline_2m, 2)
                sem_peso = ("ROJO"    if desv < -3.0 else
                            "NARANJA" if desv < -1.5 else
                            "VERDE")
        else:
            desv     = np.nan
            sem_peso = "GRIS"
        pct_ultimo = desv

        # Semáforo global
        alertas = sum([
            sem_acwr   in ("ROJO", "AMARILLO"),
            sem_well   in ("ROJO", "NARANJA"),
            sem_peso   in ("ROJO", "NARANJA"),
            (not np.isnan(monotonia) and monotonia > 2.0),
        ])
        global_sem = "ROJO" if alertas >= 2 else ("NARANJA" if alertas == 1 else "VERDE")

        resultados.append({
            "JUGADOR":          jugador,
            "SEMANA":           ultima_semana,
            "ACWR":             round(acwr, 3)       if not np.isnan(acwr)       else None,
            "MONOTONIA":        round(monotonia, 2)  if not np.isnan(monotonia)  else None,
            "SEMAFORO_CARGA":   sem_acwr,
            "WELLNESS_MEDIO":   round(well_medio, 1) if not np.isnan(well_medio) else None,
            "WELLNESS_BELOW15": below_15,
            "SEMAFORO_WELLNESS": sem_well,
            "PESO_PRE_DESV_KG": round(pct_ultimo, 2) if not np.isnan(pct_ultimo) else None,
            "SEMAFORO_PESO":    sem_peso,
            "ALERTAS_ACTIVAS":  alertas,
            "SEMAFORO_GLOBAL":  global_sem,
        })

    df = pd.DataFrame(resultados).sort_values("ALERTAS_ACTIVAS", ascending=False)
    return df


# ── VISTA 6: RECUENTO DE ASISTENCIA ──────────────────────────────────────────

def vista_recuento(borg, ses):
    # Sesiones únicas del equipo (FECHA + TURNO)
    total_ses = len(ses.drop_duplicates(["FECHA", "TURNO"])) if "TURNO" in ses.columns else len(ses)
    estados_validos = ["S", "A", "L", "N", "D", "NC"]
    jugadores = borg["JUGADOR"].dropna().unique()

    rows = []
    for j in jugadores:
        # Deduplicar: cada sesión (FECHA+TURNO) cuenta una vez por jugador
        jdf = borg[borg["JUGADOR"] == j].drop_duplicates(["FECHA", "TURNO"])
        row = {"JUGADOR": j, "TOTAL_SESIONES_EQUIPO": total_ses}
        for est in estados_validos:
            col = f"EST_{est}"
            # BORG contiene letras (S/A/L/N/D/NC) para estados no-entrenables
            row[col] = int((jdf["BORG"].astype(str).str.strip() == est).sum())
        # Sesiones "con datos" = con un número de Borg válido (no letra, no vacío)
        borg_num = pd.to_numeric(jdf["BORG"], errors="coerce")
        row["SESIONES_CON_DATOS"] = int(borg_num.notna().sum())
        row["PCT_PARTICIPACION"]  = (
            round(min(row["SESIONES_CON_DATOS"] / total_ses * 100, 100), 1)
            if total_ses else 0
        )
        rows.append(row)

    return pd.DataFrame(rows).sort_values("PCT_PARTICIPACION", ascending=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Conectando con Google Sheets...")
    client = connect()
    ss     = client.open(SHEET_NAME)

    print("\nLeyendo datos crudos...")
    ses  = leer_hoja(ss, "SESIONES",  parse_dates=["FECHA"])
    borg = leer_hoja(ss, "BORG",      parse_dates=["FECHA"])
    peso = leer_hoja(ss, "PESO",      parse_dates=["FECHA"])
    well = leer_hoja(ss, "WELLNESS",  parse_dates=["FECHA"])

    # Parseo numérico robusto (tolera coma decimal y strings).
    # OJO: NO aplicamos to_num a borg["BORG"] porque contiene tanto números
    # (RPE 0-10) como letras de estado (S/A/L/N/D/NC) que necesita vista_recuento.
    # vista_carga ya hace su propio pd.to_numeric internamente.
    ses["MINUTOS"]  = ses["MINUTOS"].apply(to_num)
    for col in ["PESO_PRE", "PESO_POST", "H2O_L"]:
        if col in peso.columns:
            peso[col] = peso[col].apply(to_num)
    for col in ["SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL"]:
        if col in well.columns:
            well[col] = well[col].apply(to_num)

    print(f"  Sesiones: {len(ses)} · Borg: {len(borg)} · Peso: {len(peso)} · Wellness: {len(well)}")

    print("\nCalculando métricas...")
    carga_df   = vista_carga(ses, borg)
    semanal_df = vista_semanal(carga_df)
    peso_df    = vista_peso(peso, ses)
    well_df    = vista_wellness(well, ses)
    semaforo_df = vista_semaforo(semanal_df, well_df, peso_df)
    recuento_df = vista_recuento(borg, ses)

    print("\nEscribiendo vistas en Google Sheets...")
    escribir_vista(ss, "_VISTA_CARGA",     carga_df)
    escribir_vista(ss, "_VISTA_SEMANAL",   semanal_df)
    escribir_vista(ss, "_VISTA_PESO",      peso_df)
    escribir_vista(ss, "_VISTA_WELLNESS",  well_df)
    escribir_vista(ss, "_VISTA_SEMAFORO",  semaforo_df)
    escribir_vista(ss, "_VISTA_RECUENTO",  recuento_df)

    print("\n" + "=" * 60)
    print("✓ Todas las vistas calculadas y actualizadas")
    print(f"  {ss.url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
