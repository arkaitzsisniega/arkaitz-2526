"""
ingest.py
---------
Lee `data/raw/Datos_indiv.xlsx` (pestaña INPUT, 4 tablas) y carga
`data/temporada_2526.duckdb` con las tablas normalizadas.

Uso:
    python src/ingest.py
    python src/ingest.py --xlsx /ruta/al/fichero.xlsx
    python src/ingest.py --db /ruta/temporada_2526.duckdb

La pestaña INPUT está dispuesta en 4 bloques de columnas separados por
columnas vacías (G, L, S). Cada bloque es una tabla independiente, así que
las leemos por rangos de columnas y reconstruimos los DataFrames.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

# --- Rutas por defecto --------------------------------------------------------

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DEFAULT_XLSX_CANDIDATES = [
    PROJECT_ROOT / "data" / "raw" / "Datos_indiv.xlsx",
    PROJECT_ROOT / "Datos_indiv.xlsx",
]
DEFAULT_DB = PROJECT_ROOT / "data" / "temporada_2526.duckdb"

# --- Constantes ---------------------------------------------------------------

PLANTILLA = [
    "HERRERO", "GARCIA", "OSCAR", "CECILIO", "CHAGUINHA", "RAUL", "HARRISON",
    "RAYA", "JAVI", "PANI", "PIRATA", "BARONA", "CARLOS", "GONZALO", "SEGO",
    "RUBIO", "DANI", "JAIME", "ANCHU", "NACHO",
]

# Filas especiales del Excel que no son jugadores reales
NO_JUGADORES = {"MEDIA", "TOTAL", "PROMEDIO", ""}

# Códigos de estado que aparecen en la columna BORG cuando no hay valor numérico
ESTADOS_BORG = {"S", "A", "L", "N", "D", "NC"}


# --- Utilidades ---------------------------------------------------------------

def _norm_nombre(s) -> Optional[str]:
    """Estandariza un nombre de jugador: mayúsculas y sin espacios extra."""
    if s is None:
        return None
    txt = str(s).strip().upper()
    if not txt or txt in NO_JUGADORES:
        return None
    return txt


def _parse_fecha(v):
    """Convierte valores de fecha (datetime, string, None) a pd.Timestamp o NaT."""
    if v is None or v == "":
        return pd.NaT
    return pd.to_datetime(v, errors="coerce", dayfirst=True)


def _parse_borg(v):
    """Devuelve (borg_numerico, estado). El Excel mezcla números y códigos."""
    if v is None or v == "":
        return (None, None)
    s = str(v).strip().upper()
    if s in ESTADOS_BORG:
        return (None, s)
    try:
        n = float(s)
        return (n, None)
    except ValueError:
        return (None, s if s else None)


# --- Lectura del XLSX ---------------------------------------------------------

def _read_input_sheet(xlsx_path: Path) -> pd.DataFrame:
    """Lee la hoja INPUT completa como DataFrame sin encabezado."""
    # header=None + skiprows=1 para saltar la fila de hipervínculos,
    # luego la fila 2 (índice 0 tras skip) serán los encabezados de cada tabla.
    return pd.read_excel(xlsx_path, sheet_name="INPUT", header=None, skiprows=1)


def _extract_sesiones(raw: pd.DataFrame) -> pd.DataFrame:
    """T1 — columnas A–F (índices 0–5)."""
    cols = ["fecha", "semana", "turno", "tipo_sesion", "minutos", "competicion"]
    df = raw.iloc[1:, 0:6].copy()
    df.columns = cols
    df = df.dropna(subset=["fecha"]).reset_index(drop=True)
    df["fecha"] = df["fecha"].apply(_parse_fecha)
    df = df.dropna(subset=["fecha"])
    df["turno"] = df["turno"].astype(str).str.strip().str.upper()
    df["tipo_sesion"] = df["tipo_sesion"].astype(str).str.strip().str.upper()
    df["competicion"] = df["competicion"].astype(str).str.strip().str.upper()
    df["minutos"] = pd.to_numeric(df["minutos"], errors="coerce")
    df["semana"] = pd.to_numeric(df["semana"], errors="coerce").astype("Int64")
    # ID de sesión sintético: (fecha + turno)
    df["sesion_id"] = df["fecha"].dt.strftime("%Y-%m-%d") + "_" + df["turno"].fillna("?")
    return df.reset_index(drop=True)


def _extract_borg(raw: pd.DataFrame) -> pd.DataFrame:
    """T2 — columnas H–K (índices 7–10)."""
    cols = ["fecha", "turno", "jugador", "borg_raw"]
    df = raw.iloc[1:, 7:11].copy()
    df.columns = cols
    df = df.dropna(subset=["fecha"]).reset_index(drop=True)
    df["fecha"] = df["fecha"].apply(_parse_fecha)
    df = df.dropna(subset=["fecha"])
    df["turno"] = df["turno"].astype(str).str.strip().str.upper()
    df["jugador"] = df["jugador"].apply(_norm_nombre)
    df = df.dropna(subset=["jugador"])
    parsed = df["borg_raw"].apply(_parse_borg)
    df["borg"] = [p[0] for p in parsed]
    df["estado"] = [p[1] for p in parsed]
    df["sesion_id"] = df["fecha"].dt.strftime("%Y-%m-%d") + "_" + df["turno"].fillna("?")
    return df[["sesion_id", "fecha", "turno", "jugador", "borg", "estado"]].reset_index(drop=True)


def _extract_peso(raw: pd.DataFrame) -> pd.DataFrame:
    """T3 — columnas M–R (índices 12–17)."""
    cols = ["fecha", "turno", "jugador", "peso_pre", "peso_post", "h2o_l"]
    df = raw.iloc[1:, 12:18].copy()
    df.columns = cols
    df = df.dropna(subset=["fecha"]).reset_index(drop=True)
    df["fecha"] = df["fecha"].apply(_parse_fecha)
    df = df.dropna(subset=["fecha"])
    df["turno"] = df["turno"].astype(str).str.strip().str.upper()
    df["jugador"] = df["jugador"].apply(_norm_nombre)
    df = df.dropna(subset=["jugador"])
    for c in ["peso_pre", "peso_post", "h2o_l"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Recalcular H2O por si hay inconsistencias
    df["h2o_l_calc"] = df["peso_pre"] - df["peso_post"]
    df["sesion_id"] = df["fecha"].dt.strftime("%Y-%m-%d") + "_" + df["turno"].fillna("?")
    return df.reset_index(drop=True)


def _extract_wellness(raw: pd.DataFrame) -> pd.DataFrame:
    """T4 — columnas T–Z (índices 19–25)."""
    cols = ["fecha", "jugador", "sueno", "fatiga", "molestias", "animo", "total"]
    df = raw.iloc[1:, 19:26].copy()
    df.columns = cols
    df = df.dropna(subset=["fecha"]).reset_index(drop=True)
    df["fecha"] = df["fecha"].apply(_parse_fecha)
    df = df.dropna(subset=["fecha"])
    df["jugador"] = df["jugador"].apply(_norm_nombre)
    df = df.dropna(subset=["jugador"])
    for c in ["sueno", "fatiga", "molestias", "animo", "total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Recalcular total por consistencia
    df["total_calc"] = df[["sueno", "fatiga", "molestias", "animo"]].sum(axis=1, min_count=1)
    return df.reset_index(drop=True)


# --- Carga a DuckDB -----------------------------------------------------------

def _write_duckdb(
    db_path: Path,
    sesiones: pd.DataFrame,
    borg: pd.DataFrame,
    peso: pd.DataFrame,
    wellness: pd.DataFrame,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        # Registrar dataframes
        con.register("sesiones_df", sesiones)
        con.register("borg_df", borg)
        con.register("peso_df", peso)
        con.register("wellness_df", wellness)

        # Tablas (reemplazar si existen)
        con.execute("DROP TABLE IF EXISTS sesiones")
        con.execute("""
            CREATE TABLE sesiones AS
            SELECT
                sesion_id,
                CAST(fecha AS DATE) AS fecha,
                CAST(semana AS INTEGER) AS semana,
                turno,
                tipo_sesion,
                CAST(minutos AS INTEGER) AS minutos,
                competicion
            FROM sesiones_df
        """)

        con.execute("DROP TABLE IF EXISTS borg")
        con.execute("""
            CREATE TABLE borg AS
            SELECT
                sesion_id,
                CAST(fecha AS DATE) AS fecha,
                turno,
                jugador,
                CAST(borg AS DOUBLE) AS borg,
                estado
            FROM borg_df
        """)

        con.execute("DROP TABLE IF EXISTS peso")
        con.execute("""
            CREATE TABLE peso AS
            SELECT
                sesion_id,
                CAST(fecha AS DATE) AS fecha,
                turno,
                jugador,
                CAST(peso_pre AS DOUBLE) AS peso_pre,
                CAST(peso_post AS DOUBLE) AS peso_post,
                CAST(h2o_l AS DOUBLE) AS h2o_l,
                CAST(h2o_l_calc AS DOUBLE) AS h2o_l_calc
            FROM peso_df
        """)

        con.execute("DROP TABLE IF EXISTS wellness")
        con.execute("""
            CREATE TABLE wellness AS
            SELECT
                CAST(fecha AS DATE) AS fecha,
                jugador,
                CAST(sueno AS INTEGER) AS sueno,
                CAST(fatiga AS INTEGER) AS fatiga,
                CAST(molestias AS INTEGER) AS molestias,
                CAST(animo AS INTEGER) AS animo,
                CAST(total AS INTEGER) AS total,
                CAST(total_calc AS INTEGER) AS total_calc
            FROM wellness_df
        """)

        # Vista derivada: carga individual por jugador y sesión (Borg × minutos)
        con.execute("DROP VIEW IF EXISTS carga_sesion")
        con.execute("""
            CREATE VIEW carga_sesion AS
            SELECT
                b.sesion_id,
                b.fecha,
                b.turno,
                b.jugador,
                b.borg,
                b.estado,
                s.tipo_sesion,
                s.minutos,
                s.competicion,
                s.semana,
                CASE
                    WHEN b.borg IS NULL OR s.minutos IS NULL THEN NULL
                    ELSE b.borg * s.minutos
                END AS carga
            FROM borg b
            LEFT JOIN sesiones s USING (sesion_id)
        """)

        # Vista derivada: calendario semanal por fecha (asigna cada fecha al lunes de su semana ISO)
        con.execute("DROP VIEW IF EXISTS calendario_semanal")
        con.execute("""
            CREATE VIEW calendario_semanal AS
            SELECT DISTINCT
                fecha,
                DATE_TRUNC('week', fecha) AS lunes,
                ISOYEAR(fecha) AS iso_anio,
                WEEK(fecha) AS iso_semana
            FROM sesiones
        """)

    finally:
        con.close()


# --- Orquestador --------------------------------------------------------------

def run(xlsx_path: Optional[Path] = None, db_path: Optional[Path] = None) -> dict:
    """Ejecuta la ingesta. Devuelve dict con conteos."""
    if xlsx_path is None:
        for cand in DEFAULT_XLSX_CANDIDATES:
            if cand.exists():
                xlsx_path = cand
                break
        if xlsx_path is None:
            raise FileNotFoundError(
                f"No se encontró el Excel. Probé: {[str(c) for c in DEFAULT_XLSX_CANDIDATES]}"
            )

    if db_path is None:
        db_path = DEFAULT_DB

    print(f"[ingest] Leyendo: {xlsx_path}")
    raw = _read_input_sheet(xlsx_path)

    sesiones = _extract_sesiones(raw)
    borg = _extract_borg(raw)
    peso = _extract_peso(raw)
    wellness = _extract_wellness(raw)

    counts = {
        "sesiones": len(sesiones),
        "borg": len(borg),
        "peso": len(peso),
        "wellness": len(wellness),
    }
    print(f"[ingest] Filas extraídas: {counts}")

    print(f"[ingest] Escribiendo DuckDB: {db_path}")
    _write_duckdb(db_path, sesiones, borg, peso, wellness)
    print("[ingest] OK")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingesta de Datos_indiv.xlsx a DuckDB")
    ap.add_argument("--xlsx", type=Path, default=None, help="Ruta al Excel de entrada")
    ap.add_argument("--db", type=Path, default=None, help="Ruta al fichero DuckDB de salida")
    args = ap.parse_args(argv)
    try:
        run(args.xlsx, args.db)
    except Exception as e:
        print(f"[ingest] ERROR: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
