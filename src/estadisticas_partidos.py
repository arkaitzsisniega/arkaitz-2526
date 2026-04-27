#!/usr/bin/env python3
"""
Extractor de estadísticas de partido desde el Excel manual de Arkaitz.

Origen: ~/Mi unidad/Deporte/Futbol sala/Movistar Inter/2025-26/Estadisticas/Estadisticas2526.xlsx

Estrategia (ver docs/estadisticas_partidos.md):
- Solo leemos las hojas raw de cada partido (J*.RIVAL, AMIS.*, PLAYOFF*, C.*.*).
- Reimplementamos los agregados (EST.TOTAL, GOLES, TIEMPOS) en Python desde
  los eventos crudos. El Excel se edita en Numbers y sus fórmulas no
  están cacheadas; J.HERRERO sí lo está y nos sirve de validación.

Estructura fija dentro de cada hoja de partido:
  - Filas 5-19 (1-indexed) = 4-18 (0-indexed): rotaciones 1ª y 2ª parte
      cols B-K = 1ª-8ª rot 1T, col L = total 1T
      cols O-V = 1ª-8ª rot 2T, col W = total 2T
  - Filas 41-56 (40-55 0-indexed): eventos de goles
      col B (1) = marcador, D (3) = minuto, F (5) = acción,
      M (12) = portero, O,Q,S,U (14,16,18,20) = cuarteto,
      W (22) = goleador, Z (25) = asistente
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Optional

warnings.filterwarnings("ignore")

import pandas as pd
from openpyxl import load_workbook

from acciones import normalizar_accion

XLSX_DEFAULT = (
    "/Users/mac/Mi unidad/Deporte/Futbol sala/Movistar Inter/"
    "2025-26/Estadisticas/Estadisticas2526.xlsx"
)

# Patrones de hojas que SON partidos (con datos)
PATRON_PARTIDO = re.compile(
    r"^(?:J\d+\..+|AMIS\..+|AMISTOSO\..+|PLAYOFF\d+|SUP\..+|"
    r"C\.E\..+|C\.M\..+|C\.R\..+)$",
    re.IGNORECASE,
)

# Hojas que parecen partidos pero están vacías (plantillas no usadas)
HOJAS_VACIAS = {"J27", "J28", "J29", "J30", "P49", "CAJA NEGRA"}

# Filas/columnas de los bloques (0-indexed)
ROT_FILA_INI, ROT_FILA_FIN = 4, 19          # 5..19 → idx 4..18, slice 4:19
ROT_COL_DORSAL, ROT_COL_NOMBRE = 1, 2       # B, C
# Rotaciones individuales: D..K (1ª-8ª rot 1T), O..V (1ª-8ª rot 2T).
# Col L y W son los totales calculados por Excel; los ignoramos para no
# duplicar al sumar.
ROT_COL_1T_INI, ROT_COL_1T_FIN = 3, 11      # D..K  (rangos slice)
ROT_COL_2T_INI, ROT_COL_2T_FIN = 14, 22     # O..V

EVT_FILA_INI, EVT_FILA_FIN = 41, 56         # 42..56 → idx 41..55, slice 41:56
EVT_COL_MARCADOR = 1   # B
EVT_COL_MIN = 3        # D
EVT_COL_ACCION = 5     # F
EVT_COL_PORTERO = 12   # M
EVT_COL_C1, EVT_COL_C2, EVT_COL_C3, EVT_COL_C4 = 14, 16, 18, 20  # O, Q, S, U
EVT_COL_GOLEADOR = 22  # W
EVT_COL_ASIST = 25     # Z


def clasificar_competicion(nombre_hoja: str) -> tuple[str, str]:
    """Devuelve (tipo, competicion_legible)."""
    n = nombre_hoja.upper()
    if n.startswith("J") and "." in n and re.match(r"^J\d+\.", n):
        return ("LIGA", "Liga 25/26")
    if n.startswith("AMISTOSO."):
        return ("AMISTOSO", "Amistoso (temporada)")
    if n.startswith("AMIS."):
        return ("AMISTOSO", "Amistoso pretemporada")
    if n.startswith("PLAYOFF"):
        return ("PLAYOFF", "Playoff Liga")
    if n.startswith("SUP."):
        return ("SUPERCOPA", "Supercopa")
    if n.startswith("C.E."):
        return ("COPA_ESPANA", "Copa de España")
    if n.startswith("C.M."):
        return ("COPA_MUNDO", "Copa del Mundo de Clubes")
    if n.startswith("C.R."):
        return ("COPA_REY", "Copa del Rey")
    return ("OTRO", "Otro")


def extraer_rival(nombre_hoja: str) -> str:
    """Saca el rival del nombre de la pestaña."""
    n = nombre_hoja
    # Quitar prefijo Jx., AMIS., etc.
    n = re.sub(r"^J\d+\.\s*", "", n)
    n = re.sub(r"^AMIS\.\s*", "", n)
    n = re.sub(r"^AMISTOSO\.\s*", "", n)
    n = re.sub(r"^C\.[EMR]\.(?:\d+ª\.)?\s*", "", n)
    n = re.sub(r"^SUP\.\s*", "", n)
    return n.strip().upper()


def _to_minutes(v) -> float:
    """Convierte una celda con duración a minutos float.
    Acepta: time, timedelta, datetime, str 'H:MM:SS', float (días)."""
    if v is None or v == "" or (isinstance(v, str) and not v.strip()):
        return 0.0
    if isinstance(v, _dt.time):
        return v.hour * 60 + v.minute + v.second / 60.0
    if isinstance(v, _dt.timedelta):
        return v.total_seconds() / 60.0
    if isinstance(v, _dt.datetime):
        return v.hour * 60 + v.minute + v.second / 60.0
    if isinstance(v, (int, float)):
        # Excel almacena duraciones como fracción de día
        if 0 <= v <= 1:
            return v * 24 * 60
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        # Acepta ":2:57" (typo de Arkaitz, sin la hora)
        if s.startswith(":"):
            s = "0" + s
        m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})$", s)
        if m:
            h, mi, se = map(int, m.groups())
            return h * 60 + mi + se / 60.0
        m = re.match(r"^(\d+):(\d{1,2})$", s)
        if m:
            mi, se = map(int, m.groups())
            return mi + se / 60.0
    return 0.0


def _to_minute_int(v) -> Optional[int]:
    """Convierte el campo MIN del evento a minuto entero (1..40)."""
    m = _to_minutes(v)
    if m <= 0:
        return None
    return int(round(m))


def _norm_nombre(s) -> str:
    if s is None:
        return ""
    return str(s).strip().upper()


@dataclass
class JugadorEnPartido:
    partido_id: str
    tipo: str
    competicion: str
    rival: str
    fecha: Optional[_dt.date]
    dorsal: Optional[int]
    jugador: str
    min_1t: float
    min_2t: float
    min_total: float
    convocado: bool
    participa: bool


@dataclass
class EventoGol:
    partido_id: str
    tipo: str
    competicion: str
    rival: str
    fecha: Optional[_dt.date]
    minuto: Optional[int]
    intervalo_5min: str
    accion_raw: str         # texto bruto del Excel (ej. "AF.4x4")
    accion: str             # canónico (ej. "Ataque Posicional 4x4")
    marcador: str
    equipo_marca: str
    goleador: str
    asistente: str
    portero: str
    cuarteto: list[str]


def _intervalo_5min(minuto: Optional[int]) -> str:
    if not minuto:
        return ""
    if minuto < 1:
        return ""
    # 1..5 → "0-5", 6..10 → "5-10", etc.
    base = ((minuto - 1) // 5) * 5
    return f"{base}-{base + 5}"


def parsear_fecha_hora(ws_values) -> Optional[_dt.date]:
    """Busca una fecha en filas 1-3, cols X-Y aprox."""
    for r_idx in range(0, 4):
        if r_idx >= len(ws_values):
            continue
        row = ws_values[r_idx]
        for c_idx in range(15, min(len(row), 30)):
            v = row[c_idx]
            if isinstance(v, (_dt.date, _dt.datetime)):
                return v.date() if isinstance(v, _dt.datetime) else v
    return None


def parsear_partido(
    nombre_hoja: str, valores: list[list]
) -> tuple[list[JugadorEnPartido], list[EventoGol]]:
    """Devuelve (jugadores_en_partido, eventos_de_gol)."""
    tipo, competicion = clasificar_competicion(nombre_hoja)
    rival = extraer_rival(nombre_hoja)
    fecha = parsear_fecha_hora(valores)

    jugadores: list[JugadorEnPartido] = []
    eventos: list[EventoGol] = []

    # ─── Rotaciones (filas 5-19, idx 4-18) ─────────────────────────────────
    for r_idx in range(ROT_FILA_INI, min(ROT_FILA_FIN, len(valores))):
        row = valores[r_idx]
        if not row or len(row) <= ROT_COL_NOMBRE:
            continue
        nombre = _norm_nombre(row[ROT_COL_NOMBRE])
        if not nombre or nombre in ("NOMBRE", "JUGADOR"):
            continue
        try:
            dorsal = int(row[ROT_COL_DORSAL]) if row[ROT_COL_DORSAL] is not None else None
        except (TypeError, ValueError):
            dorsal = None

        # 1T: cols D..L (idx 3..11). La última (L) es el total, lo recalculamos
        # nosotros sumando D..K para ser robustos.
        min_1t = 0.0
        for c in range(ROT_COL_1T_INI, ROT_COL_1T_FIN):  # D..K
            if c < len(row):
                min_1t += _to_minutes(row[c])
        min_2t = 0.0
        for c in range(ROT_COL_2T_INI, ROT_COL_2T_FIN):  # O..V
            if c < len(row):
                min_2t += _to_minutes(row[c])

        min_total = min_1t + min_2t
        # convocado = aparece en la tabla; participa = jugó algo
        convocado = True
        participa = min_total > 0

        jugadores.append(JugadorEnPartido(
            partido_id=nombre_hoja,
            tipo=tipo,
            competicion=competicion,
            rival=rival,
            fecha=fecha,
            dorsal=dorsal,
            jugador=nombre,
            min_1t=round(min_1t, 2),
            min_2t=round(min_2t, 2),
            min_total=round(min_total, 2),
            convocado=convocado,
            participa=participa,
        ))

    # ─── Eventos de gol (filas 41-56, idx 40-55) ───────────────────────────
    for r_idx in range(EVT_FILA_INI - 1, min(EVT_FILA_FIN, len(valores))):
        row = valores[r_idx]
        if not row or len(row) <= EVT_COL_GOLEADOR:
            continue
        goleador = _norm_nombre(row[EVT_COL_GOLEADOR])
        accion = _norm_nombre(row[EVT_COL_ACCION]) if EVT_COL_ACCION < len(row) else ""
        minuto = _to_minute_int(row[EVT_COL_MIN]) if EVT_COL_MIN < len(row) else None
        if not goleador and not accion and not minuto:
            continue
        if goleador in ("GOLEADOR", "RIVAL/JUGADOR"):  # cabeceras residuales
            continue

        marcador = ""
        if EVT_COL_MARCADOR < len(row) and row[EVT_COL_MARCADOR] is not None:
            marcador = str(row[EVT_COL_MARCADOR]).strip()

        equipo_marca = "RIVAL" if goleador == "RIVAL" else "INTER"
        portero = _norm_nombre(row[EVT_COL_PORTERO]) if EVT_COL_PORTERO < len(row) else ""
        cuarteto = []
        for c in (EVT_COL_C1, EVT_COL_C2, EVT_COL_C3, EVT_COL_C4):
            if c < len(row):
                v = _norm_nombre(row[c])
                if v:
                    cuarteto.append(v)

        asist = ""
        if EVT_COL_ASIST < len(row):
            asist = _norm_nombre(row[EVT_COL_ASIST])

        accion_canon = normalizar_accion(accion, equipo_marca)
        eventos.append(EventoGol(
            partido_id=nombre_hoja,
            tipo=tipo,
            competicion=competicion,
            rival=rival,
            fecha=fecha,
            minuto=minuto,
            intervalo_5min=_intervalo_5min(minuto),
            accion_raw=accion,
            accion=accion_canon,
            marcador=marcador,
            equipo_marca=equipo_marca,
            goleador=goleador,
            asistente=asist,
            portero=portero,
            cuarteto=cuarteto,
        ))

    return jugadores, eventos


def hoja_es_partido(nombre: str) -> bool:
    if nombre in HOJAS_VACIAS:
        return False
    return bool(PATRON_PARTIDO.match(nombre))


def cargar_valores_hoja(wb, nombre: str) -> list[list]:
    """Devuelve la hoja como lista de listas, valores Python."""
    ws = wb[nombre]
    return [list(row) for row in ws.iter_rows(values_only=True)]


def procesar_excel(xlsx_path: str = XLSX_DEFAULT) -> tuple[pd.DataFrame, pd.DataFrame]:
    wb = load_workbook(xlsx_path, data_only=True)
    todos_jug: list[dict] = []
    todos_evt: list[dict] = []

    for nombre in wb.sheetnames:
        if not hoja_es_partido(nombre):
            continue
        valores = cargar_valores_hoja(wb, nombre)
        jugadores, eventos = parsear_partido(nombre, valores)
        # Saltamos hojas vacías (sin ningún jugador convocado)
        if not jugadores:
            continue
        # Y aquellas en las que NADIE haya participado (plantilla aún sin rellenar)
        if not any(j.participa for j in jugadores):
            continue
        for j in jugadores:
            todos_jug.append(asdict(j))
        for e in eventos:
            d = asdict(e)
            d["cuarteto"] = "|".join(d["cuarteto"])
            todos_evt.append(d)

    df_jug = pd.DataFrame(todos_jug)
    df_evt = pd.DataFrame(todos_evt)

    # Cruzar: goles a favor, en contra, asistencias por (partido_id, jugador)
    if not df_evt.empty and not df_jug.empty:
        # Goles: solo los de INTER cuentan como "goles_a_favor" del goleador
        gf = df_evt[df_evt["equipo_marca"] == "INTER"].groupby(
            ["partido_id", "goleador"]).size().reset_index(name="goles_a_favor")
        gf = gf.rename(columns={"goleador": "jugador"})
        df_jug = df_jug.merge(gf, on=["partido_id", "jugador"], how="left")
        df_jug["goles_a_favor"] = df_jug["goles_a_favor"].fillna(0).astype(int)

        # Asistencias: las que aparecen en col Z
        ast = df_evt[df_evt["asistente"].astype(bool)].groupby(
            ["partido_id", "asistente"]).size().reset_index(name="asistencias")
        ast = ast.rename(columns={"asistente": "jugador"})
        df_jug = df_jug.merge(ast, on=["partido_id", "jugador"], how="left")
        df_jug["asistencias"] = df_jug["asistencias"].fillna(0).astype(int)
    else:
        df_jug["goles_a_favor"] = 0
        df_jug["asistencias"] = 0

    return df_jug, df_evt


def calcular_agregados_jugador(df_jug: pd.DataFrame) -> pd.DataFrame:
    """Construye _VISTA_EST_JUGADOR: una fila por jugador con totales.

    Incluye también desgloses por competición (LIGA, COPA_*, AMISTOSO).
    """
    if df_jug.empty:
        return pd.DataFrame()

    # Total por jugador
    g = df_jug.groupby("jugador", as_index=False).agg(
        partidos_convocado=("convocado", "sum"),
        partidos_jugados=("participa", "sum"),
        min_total=("min_total", "sum"),
        min_1t=("min_1t", "sum"),
        min_2t=("min_2t", "sum"),
        goles=("goles_a_favor", "sum"),
        asistencias=("asistencias", "sum"),
    )
    g["min_por_partido"] = (g["min_total"] / g["partidos_jugados"].clip(lower=1)).round(2)
    g["gol_y_asist"] = g["goles"] + g["asistencias"]

    # Pivot por competición (solo minutos y goles para no inflar)
    pivot_min = (df_jug.groupby(["jugador", "tipo"])["min_total"].sum()
                 .unstack(fill_value=0))
    pivot_min.columns = [f"min_{c.lower()}" for c in pivot_min.columns]
    pivot_gol = (df_jug.groupby(["jugador", "tipo"])["goles_a_favor"].sum()
                 .unstack(fill_value=0))
    pivot_gol.columns = [f"goles_{c.lower()}" for c in pivot_gol.columns]
    g = g.merge(pivot_min, on="jugador", how="left").merge(pivot_gol, on="jugador", how="left")
    g = g.fillna(0)
    return g.sort_values("goles", ascending=False)


def subir_a_sheet(df_jug: pd.DataFrame, df_evt: pd.DataFrame, df_agr: pd.DataFrame) -> None:
    """Sube las 3 hojas al Sheet maestro (mismo Sheet que el resto del proyecto)."""
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    SHEET_NAME = "Arkaitz - Datos Temporada 2526"
    creds = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open(SHEET_NAME)

    def _write(hoja: str, df: pd.DataFrame):
        # Convertir fechas a string ISO para evitar serializaciones raras
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%d").fillna("")
            elif out[col].dtype == "object":
                out[col] = out[col].apply(
                    lambda v: v.strftime("%Y-%m-%d") if isinstance(v, _dt.date) and not isinstance(v, _dt.datetime)
                    else (v.strftime("%Y-%m-%d") if isinstance(v, _dt.datetime) else v)
                )
        # Reemplazar NaN/None por ""
        out = out.where(pd.notnull(out), "")
        # Convertir bool a int (Sheets los guarda mejor)
        for col in out.columns:
            if out[col].dtype == bool:
                out[col] = out[col].astype(int)

        try:
            ws = sh.worksheet(hoja)
            ws.clear()
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=hoja, rows=max(len(out) + 10, 100), cols=max(len(out.columns), 6))

        valores = [list(out.columns)] + out.astype(str).values.tolist()
        ws.update(values=valores, range_name="A1")
        ws.format(f"A1:{chr(64 + len(out.columns))}1", {"textFormat": {"bold": True}})
        print(f"  ✅ {hoja}: {len(out)} filas, {len(out.columns)} cols")

    print("Subiendo a Google Sheet:")
    _write("EST_PARTIDOS", df_jug)
    _write("EST_EVENTOS", df_evt)
    _write("_VISTA_EST_JUGADOR", df_agr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX_DEFAULT)
    ap.add_argument("--validar", action="store_true",
                    help="Imprime la validación contra HERRERO (cacheado en EST.TOTAL).")
    ap.add_argument("--upload", action="store_true",
                    help="Sube los datos al Google Sheet (hojas EST_PARTIDOS, EST_EVENTOS, _VISTA_EST_JUGADOR).")
    args = ap.parse_args()

    df_jug, df_evt = procesar_excel(args.xlsx)

    print(f"Partidos procesados: {df_jug['partido_id'].nunique()}")
    print(f"Filas jugador-partido: {len(df_jug)}")
    print(f"Eventos de gol: {len(df_evt)}")
    print()

    # Resumen por jugador
    if not df_jug.empty:
        agr = df_jug.groupby("jugador", as_index=False).agg(
            partidos_conv=("convocado", "sum"),
            partidos_jug=("participa", "sum"),
            min_total=("min_total", "sum"),
            goles=("goles_a_favor", "sum"),
            asists=("asistencias", "sum"),
        ).sort_values("goles", ascending=False)
        print("Top 10 goleadores:")
        print(agr.head(10).to_string(index=False))
        print()

    if args.validar:
        print("─" * 60)
        print("VALIDACIÓN contra J.HERRERO (cacheado: 40 conv, 30 part, 1022 min)")
        h = df_jug[df_jug["jugador"] == "J.HERRERO"]
        if not h.empty:
            print(f"  Convocatorias calc:      {int(h['convocado'].sum())}")
            print(f"  Participaciones calc:    {int(h['participa'].sum())}")
            print(f"  Minutos calc:            {h['min_total'].sum():.1f}")
            print(f"  Goles a favor calc:      {int(h['goles_a_favor'].sum())}")
            print(f"  Asistencias calc:        {int(h['asistencias'].sum())}")

    if args.upload:
        df_agr = calcular_agregados_jugador(df_jug)
        subir_a_sheet(df_jug, df_evt, df_agr)


if __name__ == "__main__":
    main()
