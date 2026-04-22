"""
checks.py
---------
Validaciones de calidad sobre los datos ya cargados en DuckDB.

Cada check devuelve un DataFrame con las filas problemáticas. `run_all()`
las agrupa en un único DataFrame con la columna `check` indicando la regla
que se incumple.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import duckdb
import pandas as pd

from src.ingest import PLANTILLA

DBPathLike = Union[str, Path, duckdb.DuckDBPyConnection]


def _con(db: DBPathLike) -> duckdb.DuckDBPyConnection:
    if isinstance(db, duckdb.DuckDBPyConnection):
        return db
    return duckdb.connect(str(db), read_only=True)


# --- Checks individuales ------------------------------------------------------

def jugadores_fuera_de_plantilla(db: DBPathLike) -> pd.DataFrame:
    """Nombres presentes en borg/peso/wellness que no están en la plantilla."""
    con = _con(db)
    df = con.execute(
        """
        SELECT jugador, 'borg' AS tabla, COUNT(*) AS n FROM borg GROUP BY 1
        UNION ALL
        SELECT jugador, 'peso' AS tabla, COUNT(*) AS n FROM peso GROUP BY 1
        UNION ALL
        SELECT jugador, 'wellness' AS tabla, COUNT(*) AS n FROM wellness GROUP BY 1
        """
    ).df()
    df = df[~df["jugador"].isin(PLANTILLA)]
    return df.sort_values(["jugador", "tabla"]).reset_index(drop=True)


def borg_fuera_de_rango(db: DBPathLike) -> pd.DataFrame:
    """Valores numéricos de Borg fuera de [0, 10]."""
    con = _con(db)
    return con.execute(
        """
        SELECT sesion_id, fecha, turno, jugador, borg
        FROM borg
        WHERE borg IS NOT NULL AND (borg < 0 OR borg > 10)
        ORDER BY fecha, jugador
        """
    ).df()


def wellness_fuera_de_rango(db: DBPathLike) -> pd.DataFrame:
    """Wellness fuera de [1, 5] en cualquier componente."""
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, jugador, sueno, fatiga, molestias, animo, total
        FROM wellness
        WHERE
            (sueno    IS NOT NULL AND (sueno    < 1 OR sueno    > 5)) OR
            (fatiga   IS NOT NULL AND (fatiga   < 1 OR fatiga   > 5)) OR
            (molestias IS NOT NULL AND (molestias < 1 OR molestias > 5)) OR
            (animo    IS NOT NULL AND (animo    < 1 OR animo    > 5))
        ORDER BY fecha, jugador
        """
    ).df()


def duplicados_borg(db: DBPathLike) -> pd.DataFrame:
    """Clave natural (fecha, turno, jugador) duplicada en BORG."""
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, turno, jugador, COUNT(*) AS n
        FROM borg
        GROUP BY 1,2,3
        HAVING COUNT(*) > 1
        ORDER BY n DESC, fecha
        """
    ).df()


def duplicados_peso(db: DBPathLike) -> pd.DataFrame:
    """Clave natural duplicada en PESO."""
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, turno, jugador, COUNT(*) AS n
        FROM peso
        GROUP BY 1,2,3
        HAVING COUNT(*) > 1
        ORDER BY n DESC, fecha
        """
    ).df()


def duplicados_wellness(db: DBPathLike) -> pd.DataFrame:
    """Wellness duplicado por (fecha, jugador)."""
    con = _con(db)
    return con.execute(
        """
        SELECT fecha, jugador, COUNT(*) AS n
        FROM wellness
        GROUP BY 1,2
        HAVING COUNT(*) > 1
        ORDER BY n DESC, fecha
        """
    ).df()


def borg_sin_sesion(db: DBPathLike) -> pd.DataFrame:
    """Registros de Borg cuya (fecha, turno) no coincide con ninguna sesión en T1."""
    con = _con(db)
    return con.execute(
        """
        SELECT b.fecha, b.turno, b.jugador, b.borg, b.estado
        FROM borg b
        LEFT JOIN sesiones s USING (sesion_id)
        WHERE s.sesion_id IS NULL
        ORDER BY b.fecha, b.jugador
        """
    ).df()


def peso_incoherente(db: DBPathLike, tolerancia: float = 0.05) -> pd.DataFrame:
    """
    H2O declarada (peso_pre - peso_post) vs valor de columna H2O: diferencias
    mayores que `tolerancia` kg.
    """
    con = _con(db)
    return con.execute(
        f"""
        SELECT fecha, turno, jugador, peso_pre, peso_post, h2o_l, h2o_l_calc,
               (h2o_l - h2o_l_calc) AS diff
        FROM peso
        WHERE h2o_l IS NOT NULL AND h2o_l_calc IS NOT NULL
          AND ABS(h2o_l - h2o_l_calc) > {tolerancia}
        ORDER BY ABS(h2o_l - h2o_l_calc) DESC
        """
    ).df()


def peso_atipico(db: DBPathLike, min_kg: float = 50, max_kg: float = 110) -> pd.DataFrame:
    """Pesos fuera de un rango razonable (probables errores de tecleo)."""
    con = _con(db)
    return con.execute(
        f"""
        SELECT fecha, turno, jugador, peso_pre, peso_post
        FROM peso
        WHERE (peso_pre IS NOT NULL AND (peso_pre < {min_kg} OR peso_pre > {max_kg}))
           OR (peso_post IS NOT NULL AND (peso_post < {min_kg} OR peso_post > {max_kg}))
        ORDER BY fecha, jugador
        """
    ).df()


# --- Agrupador ----------------------------------------------------------------

def run_all(db: DBPathLike) -> pd.DataFrame:
    """Ejecuta todos los checks y devuelve un DataFrame plano con todos los hallazgos."""
    registros = []

    def _add(nombre, df):
        if df is None or df.empty:
            return
        tmp = df.copy()
        tmp.insert(0, "check", nombre)
        # Normalizar columnas: stringify todo para que apilen sin problema
        tmp = tmp.astype(str)
        registros.append(tmp)

    _add("jugadores_fuera_plantilla", jugadores_fuera_de_plantilla(db))
    _add("borg_fuera_rango", borg_fuera_de_rango(db))
    _add("wellness_fuera_rango", wellness_fuera_de_rango(db))
    _add("duplicados_borg", duplicados_borg(db))
    _add("duplicados_peso", duplicados_peso(db))
    _add("duplicados_wellness", duplicados_wellness(db))
    _add("borg_sin_sesion", borg_sin_sesion(db))
    _add("peso_incoherente", peso_incoherente(db))
    _add("peso_atipico", peso_atipico(db))

    if not registros:
        return pd.DataFrame(columns=["check"])
    return pd.concat(registros, ignore_index=True, sort=False)


def resumen(db: DBPathLike) -> pd.DataFrame:
    """Tabla resumen: un contador de hallazgos por check."""
    hallazgos = run_all(db)
    if hallazgos.empty:
        return pd.DataFrame({"check": [], "n_hallazgos": []})
    return (
        hallazgos.groupby("check", as_index=False)
        .size()
        .rename(columns={"size": "n_hallazgos"})
        .sort_values("n_hallazgos", ascending=False)
    )


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "data/temporada_2526.duckdb"
    print(resumen(db).to_string(index=False))
