"""
metrics.py
----------
Cálculos derivados sobre el DuckDB de la temporada:
    - Carga individual por sesión (Borg × minutos)
    - Carga semanal (microciclo) por jugador y equipo
    - Monotonía, fatiga, ACWR 1:4
    - Baseline de peso y desviaciones
    - Wellness total y media semanal
    - Semáforo de riesgo por jugador
    - Correlación wellness ↔ carga

Cada función acepta una conexión DuckDB ya abierta o una ruta.

Convenciones:
    - "semana" = lunes de esa semana (lunes 00:00 como ancla).
    - Umbrales de alerta basados en literatura (ACWR 1:4, monotonía Foster).
      Son orientativos; revisar con el cuerpo técnico.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import duckdb
import numpy as np
import pandas as pd

DBPathLike = Union[str, Path, duckdb.DuckDBPyConnection]


# --- Conexión -----------------------------------------------------------------

def _con(db: DBPathLike) -> duckdb.DuckDBPyConnection:
    if isinstance(db, duckdb.DuckDBPyConnection):
        return db
    return duckdb.connect(str(db), read_only=True)


# --- Carga por sesión / día / semana -----------------------------------------

def carga_por_sesion(db: DBPathLike) -> pd.DataFrame:
    """Una fila por (sesión, jugador) con la carga = borg × minutos."""
    con = _con(db)
    return con.execute(
        """
        SELECT sesion_id, fecha, turno, jugador, tipo_sesion, minutos,
               borg, estado, competicion, semana, carga
        FROM carga_sesion
        ORDER BY fecha, turno, jugador
        """
    ).df()


def carga_diaria(db: DBPathLike) -> pd.DataFrame:
    """Carga total del día (sumando turnos) por jugador."""
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, jugador, SUM(carga) AS carga_diaria
        FROM carga_sesion
        WHERE carga IS NOT NULL
        GROUP BY fecha, jugador
        ORDER BY fecha, jugador
        """
    ).df()


def carga_semanal(db: DBPathLike) -> pd.DataFrame:
    """Carga semanal por jugador. `lunes` es la fecha del lunes de la semana ISO."""
    con = _con(db)
    df = con.execute(
        """
        SELECT
            DATE_TRUNC('week', fecha) AS lunes,
            jugador,
            SUM(carga) AS carga_semanal,
            COUNT(*) FILTER (WHERE carga IS NOT NULL) AS n_sesiones,
            AVG(borg) AS borg_medio,
            SUM(minutos) FILTER (WHERE borg IS NOT NULL) AS minutos_total
        FROM carga_sesion
        WHERE carga IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()
    df["lunes"] = pd.to_datetime(df["lunes"])
    return df


def carga_semanal_equipo(db: DBPathLike) -> pd.DataFrame:
    """Carga semanal media del equipo (promedio entre jugadores con carga > 0)."""
    df = carga_semanal(db)
    eq = df.groupby("lunes", as_index=False).agg(
        carga_media_equipo=("carga_semanal", "mean"),
        carga_total_equipo=("carga_semanal", "sum"),
        jugadores_con_datos=("jugador", "nunique"),
    )
    return eq


# --- Monotonía, fatiga, ACWR --------------------------------------------------

def monotonia_fatiga_semanal(db: DBPathLike) -> pd.DataFrame:
    """
    Por jugador y semana:
        monotonia = media(carga diaria L-D) / desviacion(carga diaria L-D)
        fatiga    = carga_semanal × monotonia

    Trabaja con un calendario completo L-D, rellenando 0 los días sin sesión.
    """
    diaria = carga_diaria(db)
    if diaria.empty:
        return pd.DataFrame(columns=["lunes", "jugador", "monotonia", "fatiga", "carga_semanal"])

    diaria["fecha"] = pd.to_datetime(diaria["fecha"])
    diaria["lunes"] = diaria["fecha"] - pd.to_timedelta(diaria["fecha"].dt.weekday, unit="D")

    # Para cada (jugador, lunes) construimos vector L-D con 0 por defecto
    out = []
    for (jugador, lunes), grp in diaria.groupby(["jugador", "lunes"]):
        vec = [0.0] * 7
        for _, r in grp.iterrows():
            dia = int((r["fecha"] - lunes).days)
            if 0 <= dia < 7:
                vec[dia] += r["carga_diaria"]
        arr = np.array(vec, dtype=float)
        total = arr.sum()
        mean = arr.mean()
        std = arr.std(ddof=0)  # poblacional, coherente con fórmula Excel STDEVP
        mono = mean / std if std > 1e-9 else np.nan
        fat = total * mono if not np.isnan(mono) else np.nan
        out.append({
            "lunes": lunes,
            "jugador": jugador,
            "carga_semanal": total,
            "monotonia": mono,
            "fatiga": fat,
        })
    return pd.DataFrame(out).sort_values(["lunes", "jugador"]).reset_index(drop=True)


def acwr(db: DBPathLike, agudo_dias: int = 7, cronico_dias: int = 28) -> pd.DataFrame:
    """
    Acute:Chronic Workload Ratio. Por defecto 1:4 (semana vs 4 semanas).
    Devuelve una fila por (jugador, fecha).
    """
    diaria = carga_diaria(db)
    if diaria.empty:
        return pd.DataFrame(columns=["fecha", "jugador", "agudo", "cronico", "acwr"])

    diaria["fecha"] = pd.to_datetime(diaria["fecha"])
    diaria = diaria.sort_values(["jugador", "fecha"])

    out = []
    for jugador, grp in diaria.groupby("jugador"):
        # rellenar calendario diario continuo para cálculos rolling
        if grp.empty:
            continue
        idx = pd.date_range(grp["fecha"].min(), grp["fecha"].max(), freq="D")
        s = grp.set_index("fecha")["carga_diaria"].reindex(idx, fill_value=0.0)
        agudo = s.rolling(agudo_dias, min_periods=1).sum()
        cronico = s.rolling(cronico_dias, min_periods=1).mean() * agudo_dias  # equivalente a media por ventana aguda
        ratio = agudo / cronico.replace(0, np.nan)
        df_j = pd.DataFrame({
            "fecha": idx,
            "jugador": jugador,
            "agudo": agudo.values,
            "cronico": cronico.values,
            "acwr": ratio.values,
        })
        out.append(df_j)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# --- Peso ---------------------------------------------------------------------

def baseline_peso(db: DBPathLike, ventana_dias: int = 28) -> pd.DataFrame:
    """
    Baseline rolling de peso PRE por jugador (media móvil de `ventana_dias`).
    Devuelve una fila por (jugador, fecha) con baseline y desviación %.
    """
    con = _con(db)
    df = con.execute(
        """
        SELECT fecha, jugador, AVG(peso_pre) AS peso_pre
        FROM peso
        WHERE peso_pre IS NOT NULL
        GROUP BY fecha, jugador
        ORDER BY jugador, fecha
        """
    ).df()
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values(["jugador", "fecha"])
    out = []
    for jugador, grp in df.groupby("jugador"):
        grp = grp.copy()
        grp["baseline"] = grp["peso_pre"].rolling(ventana_dias, min_periods=3).mean()
        grp["desviacion_pct"] = (grp["peso_pre"] - grp["baseline"]) / grp["baseline"] * 100
        out.append(grp)
    return pd.concat(out, ignore_index=True)


def deshidratacion_sesion(db: DBPathLike) -> pd.DataFrame:
    """Pérdida hídrica (peso pre - post) como % del peso pre por sesión."""
    con = _con(db)
    df = con.execute(
        """
        SELECT fecha, turno, jugador, peso_pre, peso_post,
               (peso_pre - peso_post) AS perdida_kg,
               CASE WHEN peso_pre > 0 THEN (peso_pre - peso_post) / peso_pre * 100 END AS perdida_pct
        FROM peso
        WHERE peso_pre IS NOT NULL AND peso_post IS NOT NULL
        ORDER BY fecha, jugador
        """
    ).df()
    return df


# --- Wellness -----------------------------------------------------------------

def wellness_diario(db: DBPathLike) -> pd.DataFrame:
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, jugador, sueno, fatiga, molestias, animo, total
        FROM wellness
        ORDER BY fecha, jugador
        """
    ).df()


def wellness_semanal(db: DBPathLike) -> pd.DataFrame:
    """Media semanal del TOTAL wellness y de cada componente."""
    con = _con(db)
    df = con.execute(
        """
        SELECT
            DATE_TRUNC('week', fecha) AS lunes,
            jugador,
            AVG(total)    AS total_medio,
            AVG(sueno)    AS sueno_medio,
            AVG(fatiga)   AS fatiga_medio,
            AVG(molestias) AS molestias_medio,
            AVG(animo)    AS animo_medio,
            COUNT(*)      AS dias_con_datos
        FROM wellness
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()
    df["lunes"] = pd.to_datetime(df["lunes"])
    return df


# --- Asistencia / estado ------------------------------------------------------

def resumen_asistencia(
    db: DBPathLike,
    desde: Optional[pd.Timestamp] = None,
    hasta: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Recuento por jugador de sesiones por tipo y de estados (S/A/L/N/D/NC)."""
    con = _con(db)
    params = []
    where_fecha = ""
    if desde is not None:
        where_fecha += " AND b.fecha >= ?"
        params.append(pd.Timestamp(desde).to_pydatetime().date())
    if hasta is not None:
        where_fecha += " AND b.fecha <= ?"
        params.append(pd.Timestamp(hasta).to_pydatetime().date())

    sql = f"""
        SELECT
            b.jugador,
            COUNT(*) FILTER (WHERE s.tipo_sesion = 'GYM')         AS gym,
            COUNT(*) FILTER (WHERE s.tipo_sesion = 'FISICO')      AS fisico,
            COUNT(*) FILTER (WHERE s.tipo_sesion = 'TEC-TAC')     AS tec_tac,
            COUNT(*) FILTER (WHERE s.tipo_sesion = 'RECUPERACIÓN') AS recup,
            COUNT(*) FILTER (WHERE s.tipo_sesion = 'PARTIDO')     AS partido,
            COUNT(*) FILTER (WHERE b.borg IS NOT NULL)            AS entrenos,
            COUNT(*) FILTER (WHERE b.estado = 'S')  AS seleccionado,
            COUNT(*) FILTER (WHERE b.estado = 'A')  AS ausente,
            COUNT(*) FILTER (WHERE b.estado = 'L')  AS lesionado,
            COUNT(*) FILTER (WHERE b.estado = 'N')  AS no_jugo,
            COUNT(*) FILTER (WHERE b.estado = 'D')  AS descanso,
            COUNT(*) FILTER (WHERE b.estado = 'NC') AS no_convocado,
            COUNT(*) AS total_registros
        FROM borg b
        LEFT JOIN sesiones s USING (sesion_id)
        WHERE TRUE {where_fecha}
        GROUP BY b.jugador
        ORDER BY b.jugador
    """
    return con.execute(sql, params).df()


# --- Semáforo de riesgo -------------------------------------------------------

def semaforo_riesgo(
    db: DBPathLike,
    hoy: Optional[pd.Timestamp] = None,
    acwr_alto: float = 1.5,
    acwr_bajo: float = 0.8,
    monotonia_alta: float = 2.0,
    wellness_bajo: int = 14,
    peso_desv_pct: float = 3.0,
) -> pd.DataFrame:
    """
    Combina varios indicadores en un semáforo por jugador (fecha = última
    observación disponible para cada uno). Niveles:
        - verde  : sin flags
        - amarillo: 1 flag
        - rojo   : ≥ 2 flags

    Flags considerados:
        - ACWR fuera de rango [acwr_bajo, acwr_alto]
        - Monotonía >= monotonia_alta en la última semana
        - TOTAL wellness < wellness_bajo en media de los últimos 3 días
        - Peso PRE desviado > peso_desv_pct % del baseline 28d
    """
    if hoy is None:
        hoy = pd.Timestamp.today().normalize()
    ventana_ini = hoy - pd.Timedelta(days=14)

    ac = acwr(db)
    mf = monotonia_fatiga_semanal(db)
    wd = wellness_diario(db)
    bp = baseline_peso(db)

    # ACWR: último valor por jugador en los últimos 14 días
    ac_last = (
        ac[ac["fecha"].between(ventana_ini, hoy)]
        .sort_values("fecha")
        .groupby("jugador")
        .tail(1)[["jugador", "fecha", "acwr"]]
    )

    # Monotonía: última semana por jugador
    mf_last = (
        mf.sort_values("lunes").groupby("jugador").tail(1)[["jugador", "lunes", "monotonia", "fatiga"]]
    )

    # Wellness: media últimos 3 días con datos
    wd["fecha"] = pd.to_datetime(wd["fecha"])
    wd_recent = wd[wd["fecha"].between(hoy - pd.Timedelta(days=7), hoy)]
    w_last = (
        wd_recent.sort_values("fecha")
        .groupby("jugador")
        .tail(3)
        .groupby("jugador", as_index=False)["total"].mean()
        .rename(columns={"total": "wellness_3d"})
    )

    # Peso: última desviación respecto al baseline
    if not bp.empty:
        bp_last = bp.dropna(subset=["baseline"]).sort_values("fecha").groupby("jugador").tail(1)[
            ["jugador", "fecha", "peso_pre", "baseline", "desviacion_pct"]
        ]
    else:
        bp_last = pd.DataFrame(columns=["jugador", "fecha", "peso_pre", "baseline", "desviacion_pct"])

    # Merge todo por jugador
    sem = ac_last.merge(mf_last, on="jugador", how="outer") \
                 .merge(w_last, on="jugador", how="outer") \
                 .merge(bp_last[["jugador", "desviacion_pct"]], on="jugador", how="outer")

    def _flags(row):
        flags = []
        if pd.notna(row.get("acwr")) and (row["acwr"] > acwr_alto or row["acwr"] < acwr_bajo):
            flags.append("ACWR")
        if pd.notna(row.get("monotonia")) and row["monotonia"] >= monotonia_alta:
            flags.append("MONOTONIA")
        if pd.notna(row.get("wellness_3d")) and row["wellness_3d"] < wellness_bajo:
            flags.append("WELLNESS")
        if pd.notna(row.get("desviacion_pct")) and abs(row["desviacion_pct"]) > peso_desv_pct:
            flags.append("PESO")
        return flags

    sem["flags"] = sem.apply(_flags, axis=1)
    sem["n_flags"] = sem["flags"].apply(len)
    sem["nivel"] = sem["n_flags"].apply(lambda n: "rojo" if n >= 2 else ("amarillo" if n == 1 else "verde"))
    return sem.sort_values(["n_flags", "jugador"], ascending=[False, True]).reset_index(drop=True)


# --- Correlación wellness ↔ carga --------------------------------------------

def correlacion_wellness_carga(db: DBPathLike, desfase_dias: int = 0) -> pd.DataFrame:
    """
    Correlación Pearson por jugador entre el wellness TOTAL del día y la carga
    individual del día (con desfase opcional: desfase_dias=1 usa wellness del
    día siguiente vs carga de hoy).
    """
    diaria = carga_diaria(db)
    wd = wellness_diario(db)
    if diaria.empty or wd.empty:
        return pd.DataFrame(columns=["jugador", "n", "pearson"])

    diaria["fecha"] = pd.to_datetime(diaria["fecha"])
    wd["fecha"] = pd.to_datetime(wd["fecha"])

    if desfase_dias != 0:
        wd = wd.copy()
        wd["fecha"] = wd["fecha"] - pd.Timedelta(days=desfase_dias)

    merged = diaria.merge(wd[["fecha", "jugador", "total"]], on=["fecha", "jugador"], how="inner")

    out = []
    for jugador, grp in merged.groupby("jugador"):
        if len(grp) < 5:
            out.append({"jugador": jugador, "n": len(grp), "pearson": np.nan})
            continue
        r = grp["carga_diaria"].corr(grp["total"])
        out.append({"jugador": jugador, "n": len(grp), "pearson": r})
    return pd.DataFrame(out).sort_values("pearson").reset_index(drop=True)
