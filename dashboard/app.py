"""
dashboard/app.py — Arkaitz · Panel de Temporada 25/26
Lee directamente de Google Sheets (pestañas _VISTA_*).
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import json, os
import datetime as _dt
from pathlib import Path

# ── Config página ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Arkaitz · 25/26",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Gate de contraseña (cuerpo técnico) ──────────────────────────────────────
# Para activar: define APP_PASSWORD en st.secrets (Streamlit Cloud → Settings →
# Secrets). Si no está definido, el dashboard arranca sin login (modo dev local).
def _check_password():
    """Bloquea el dashboard hasta que el usuario introduzca la contraseña.
    Devuelve True si está autenticado o si no hay contraseña configurada."""
    pwd_correct = None
    err_secret = None
    debug_top = []
    debug_gcp = []
    try:
        # 1) Buscar al nivel raíz de secrets
        if "APP_PASSWORD" in st.secrets:
            pwd_correct = st.secrets["APP_PASSWORD"]
        else:
            pwd_correct = st.secrets.get("APP_PASSWORD", None)
        # 2) Si no está al nivel raíz, probar dentro de [gcp_service_account]
        #    (caso típico: la línea APP_PASSWORD se coló dentro del bloque)
        if not pwd_correct and "gcp_service_account" in st.secrets:
            sub = st.secrets["gcp_service_account"]
            try:
                if "APP_PASSWORD" in sub:
                    pwd_correct = sub["APP_PASSWORD"]
            except Exception:
                pass
        # Recoger nombres de claves visibles (NO sus valores) para debug
        try:
            debug_top = list(st.secrets.keys())
        except Exception:
            debug_top = ["<no disponible>"]
        try:
            if "gcp_service_account" in st.secrets:
                debug_gcp = list(st.secrets["gcp_service_account"].keys())
        except Exception:
            debug_gcp = []
    except Exception as e:
        err_secret = f"{type(e).__name__}: {e}"
    # Si no hay contraseña configurada → acceso libre con debug visible
    if not pwd_correct:
        st.warning(
            "⚠️ **APP_PASSWORD no se está leyendo de `st.secrets`.** "
            "El dashboard está accesible sin contraseña. "
            "Configura el secret en Streamlit Cloud → Settings → Secrets, "
            "y haz **Reboot** de la app."
            + (f"\n\n_Error técnico:_ `{err_secret}`" if err_secret else "")
            + f"\n\n_Claves visibles a nivel raíz:_ `{debug_top}`"
            + (f"\n\n_Claves dentro de `gcp_service_account`:_ `{debug_gcp}`"
               if debug_gcp else "")
        )
        return True
    # Ya autenticado en esta sesión
    if st.session_state.get("auth_ok"):
        return True
    # Pantalla de login
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #1B3A6B; }
    [data-testid="stSidebar"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    # Logo central
    import base64 as _b64
    _logo_path = (Path(__file__).resolve().parent.parent
                   / "assets" / "logos" / "inter_verde.png")
    logo_html = ""
    try:
        if _logo_path.exists():
            logo_html = (f'<img src="data:image/png;base64,'
                         f'{_b64.b64encode(_logo_path.read_bytes()).decode()}" '
                         f'style="height:120px; margin-bottom:18px;"/>')
    except Exception:
        pass

    st.markdown(f"""
    <div style="text-align:center; padding: 80px 0 30px 0;">
        {logo_html}
        <h1 style="color:white; font-size:2rem; margin:0;">Arkaitz · Movistar Inter FS</h1>
        <p style="color:#BBCDE8; font-size:1rem; margin:6px 0 30px 0;">
            Panel de la temporada 25/26 · Acceso restringido al cuerpo técnico
        </p>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns([1, 1, 1])
    with cols[1]:
        pwd = st.text_input("🔐 Contraseña", type="password",
                              key="pwd_input", label_visibility="visible")
        if st.button("Entrar", use_container_width=True, type="primary"):
            if pwd == pwd_correct:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
    return False


if not _check_password():
    st.stop()


# ── Colores globales ──────────────────────────────────────────────────────────
VERDE   = "#2E7D32"
NARANJA = "#E65100"
ROJO    = "#B71C1C"
AZUL    = "#1565C0"
GRIS    = "#616161"

COLORES_JUGADORES = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel

MAP_SEMAFORO = {
    "VERDE":    ("🟢", VERDE),
    "AMARILLO": ("🟡", "#F57F17"),
    "NARANJA":  ("🟠", NARANJA),
    "ROJO":     ("🔴", ROJO),
    "AZUL":     ("🔵", AZUL),
    "GRIS":     ("⚫", GRIS),
}

CSS = """
<style>
[data-testid="stAppViewContainer"] { background: #F0F2F6; }
[data-testid="stSidebar"]          { background: #1B3A6B !important; }
[data-testid="stSidebar"] label    { color: #BBCDE8 !important; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: white !important; }
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stDateInput input,
[data-testid="stSidebar"] [data-testid="stDateInput"] > div > div {
    background: #243F72 !important;
    border: 1px solid #3A5A9B !important;
    color: white !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] { background: #3A5A9B !important; }
[data-testid="stSidebar"] svg { fill: #BBCDE8 !important; }
[data-testid="stSidebar"] button {
    background: #2E5AA0 !important;
    border: 1px solid #4A7AC0 !important;
    color: white !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] button:hover { background: #3A6AB0 !important; }
h1 { color: #1B3A6B; font-weight: 800; }
h2, h3 { color: #1B3A6B; }
.metric-card {
    background: white; border-radius: 12px; padding: 16px 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center;
    border-left: 5px solid #1B3A6B;
}
.metric-card .val { font-size: 2rem; font-weight: 700; color: #1B3A6B; }
.metric-card .lbl { font-size: 0.85rem; color: #888; margin-top: 4px; }
.player-card {
    border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.12);
}
.player-name { font-size: 1.05rem; font-weight: 700; margin-bottom: 6px; }
.player-stats { font-size: 0.82rem; opacity: 0.92; line-height: 1.8; }
.acwr-bar-bg {
    background: rgba(255,255,255,0.25); border-radius: 4px;
    height: 6px; margin-top: 8px; position: relative;
}
.acwr-bar-fill {
    height: 6px; border-radius: 4px;
    background: rgba(255,255,255,0.85);
}
div[data-testid="stTab"] button { font-weight: 600; }

/* Tabs en MULTILINEA: con tantas pestañas (Semáforo, Carga, Peso,
   Wellness, Lesiones, Recuento, Oliver, Ejercicios, Partido, Equipo,
   Eficiencia, Goles, Comp, Scout, Editar...) hace falta envolverlas
   en varias filas en vez de tener una scroll horizontal. */
div[role="tablist"] {
    flex-wrap: wrap !important;
    row-gap: 4px !important;
    border-bottom: 2px solid #E0E5EE !important;
    padding-bottom: 4px !important;
}
div[role="tablist"] button[role="tab"] {
    flex: 0 0 auto !important;
    margin-bottom: 2px !important;
}

/* Zebra striping en tablas de st.dataframe */
[data-testid="stDataFrame"] [data-testid="stVerticalBlock"] div[role="row"]:nth-child(odd):not([role="columnheader"]) {
    background: rgba(0, 0, 0, 0.02);
}
[data-testid="stDataFrame"] table tbody tr:nth-child(odd) {
    background: #f8fafc !important;
}
[data-testid="stDataFrame"] table tbody tr:nth-child(even) {
    background: #ffffff !important;
}
[data-testid="stDataFrame"] table tbody tr:hover {
    background: #e3f2fd !important;
}

/* KPI metric cards con color personalizado */
.kpi-positivo [data-testid="stMetricValue"] { color: #2E7D32 !important; }
.kpi-negativo [data-testid="stMetricValue"] { color: #B71C1C !important; }
.kpi-neutro   [data-testid="stMetricValue"] { color: #1B3A6B !important; }

/* Eliminar la franja blanca al final de la página (espacio en blanco
   inferior generado por el padding/footer por defecto de Streamlit) */
.main .block-container { padding-bottom: 1rem !important; }
[data-testid="stAppViewContainer"] > .main { padding-bottom: 0 !important; }
footer, .stApp > footer { display: none !important; }
.viewerBadge_container__1QSob, ._terminalButton_rix23_138 { display: none !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ── Conexión Google Sheets ────────────────────────────────────────────────────
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets",
               "https://www.googleapis.com/auth/drive"]


def _conexion_sheet_scout():
    """Devuelve el spreadsheet abierto, para los helpers de scouting."""
    return get_client().open(SHEET_NAME)


def _guardar_scout_goles(sh, equipo, fecha_iso, rival, comp, df_edit):
    """Append (no sobreescribe) en EST_SCOUTING_GOLES. Filtra filas vacías."""
    import gspread
    cols = ["equipo", "fecha_partido", "rival_de_ese_partido", "competicion",
             "evento_idx", "condicion", "minuto_mmss", "minuto", "accion",
             "zona_campo", "zona_porteria", "descripcion"]
    try:
        ws = sh.worksheet("EST_SCOUTING_GOLES")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet("EST_SCOUTING_GOLES", rows=400, cols=15)
        ws.update(values=[cols], range_name="A1")
    df = df_edit.copy().fillna("")
    # Filtrar vacías
    mask = (df["condicion"].astype(str).str.strip() != "") | \
            (df["minuto_mmss"].astype(str).str.strip() != "") | \
            (df["accion"].astype(str).str.strip() != "")
    df = df[mask].reset_index(drop=True)
    if df.empty:
        return 0
    # Calcular minuto entero a partir de mm:ss
    def _parse(txt):
        s = str(txt or "").strip().replace(",", ":")
        if ":" in s:
            try:
                mm, ss = s.split(":", 1)
                return int(mm)
            except ValueError:
                return 0
        try:
            return int(s)
        except ValueError:
            return 0
    df["minuto"] = df["minuto_mmss"].apply(_parse)
    df["equipo"] = equipo
    df["fecha_partido"] = fecha_iso
    df["rival_de_ese_partido"] = rival
    df["competicion"] = comp
    # evento_idx: contar las filas existentes del mismo (equipo, fecha)
    existentes = pd.DataFrame(ws.get_all_records())
    if not existentes.empty:
        n_prev = int(((existentes.get("equipo", "") == equipo) &
                       (existentes.get("fecha_partido", "").astype(str) == fecha_iso)).sum())
    else:
        n_prev = 0
    df["evento_idx"] = range(n_prev + 1, n_prev + 1 + len(df))
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    # Append
    valores = df.astype(str).values.tolist()
    ws.append_rows(valores, value_input_option="USER_ENTERED")
    return len(df)


def _guardar_scout_pen(sh, equipo, fecha_iso, rival, comp, df_edit):
    """Append en EST_SCOUTING_PEN_10M. Filtra filas vacías."""
    import gspread
    cols = ["equipo", "fecha_partido", "rival_de_ese_partido", "competicion",
             "tipo_lanzamiento", "condicion", "parte", "minuto_mmss",
             "marcador", "lanzador", "portero", "resultado", "cuadrante",
             "descripcion"]
    try:
        ws = sh.worksheet("EST_SCOUTING_PEN_10M")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet("EST_SCOUTING_PEN_10M", rows=200, cols=15)
        ws.update(values=[cols], range_name="A1")
    df = df_edit.copy().fillna("")
    mask = (df["tipo_lanzamiento"].astype(str).str.strip() != "") | \
            (df["resultado"].astype(str).str.strip() != "") | \
            (df["lanzador"].astype(str).str.strip() != "")
    df = df[mask].reset_index(drop=True)
    if df.empty:
        return 0
    df["equipo"] = equipo
    df["fecha_partido"] = fecha_iso
    df["rival_de_ese_partido"] = rival
    df["competicion"] = comp
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    valores = df.astype(str).values.tolist()
    ws.append_rows(valores, value_input_option="USER_ENTERED")
    return len(df)


@st.cache_resource(show_spinner="Conectando con Google Sheets…")
def get_client():
    # Streamlit Cloud: usar st.secrets
    # Local: usar archivo google_credentials.json
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if creds_path.exists():
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    else:
        info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner=False)
def cargar(hoja: str) -> pd.DataFrame:
    client = get_client()
    ss     = client.open(SHEET_NAME)
    ws     = ss.worksheet(hoja)
    try:
        # UNFORMATTED → números como float puro (no "17,1" que rompe pd.to_numeric)
        data = ws.get_all_records(
            value_render_option=gspread.utils.ValueRenderOption.unformatted
        )
        return pd.DataFrame(data)
    except Exception:
        # Fallback para hojas con cabeceras duplicadas o fusionadas (ej. LESIONES).
        try:
            rows = ws.get(
                value_render_option=gspread.utils.ValueRenderOption.unformatted
            )
        except Exception:
            rows = ws.get_all_values()
        if not rows:
            return pd.DataFrame()
        # Limpiar fórmulas literales (cuando una celda empieza por "=" significa
        # que está guardada como TEXTO, no como fórmula evaluada — caso típico
        # de la hoja LESIONES donde las fórmulas se han pegado como texto).
        rows = [
            [
                "" if (isinstance(c, str) and c.startswith("=")) else c
                for c in fila
            ]
            for fila in rows
        ]
        # Detectar AUTOMÁTICAMENTE qué fila es la cabecera real:
        # - Hojas como _VISTA_CARGA tienen cabecera ya en fila 1.
        # - Hojas como LESIONES tienen 'grupos de color' en fila 1 (mayormente
        #   vacía con celdas merged) y la cabecera real en fila 2.
        # Heurística: si fila 1 tiene más celdas no-vacías que fila 2,
        # fila 1 es la cabecera; si no, es la fila 2.
        def _no_vacias(fila):
            return sum(1 for c in fila if str(c).strip() != "")

        if len(rows) >= 2:
            f1_count = _no_vacias(rows[0])
            f2_count = _no_vacias(rows[1])
            if f1_count >= f2_count and f1_count > 0:
                # Fila 1 ya es la cabecera (caso típico _VISTA_*)
                headers = rows[0]
                data_start = 1
            else:
                # Fila 1 son grupos coloreados, cabecera en fila 2 (LESIONES)
                headers = rows[1]
                data_start = 2
        else:
            headers = rows[0] if rows else []
            data_start = 1
        # Desduplicar cabeceras vacías
        # ⚠️ str(h) primero: si la cabecera viene como int (ej. "8" como dorsal
        # o "2026" como año), .strip() pelea sin convertir antes a string.
        seen = {}
        clean = []
        for h in headers:
            h = str(h).strip() if h is not None else ""
            if h == "":
                h = "_VACÍO"
            if h in seen:
                seen[h] += 1
                h = f"{h}_{seen[h]}"
            else:
                seen[h] = 0
            clean.append(h)
        data_rows = rows[data_start:] if len(rows) > data_start else []
        return pd.DataFrame(data_rows, columns=clean)


SHEET_FISIOS_NAME = "Arkaitz - Lesiones y Tratamientos 2526"


@st.cache_data(ttl=120, show_spinner=False)
def cargar_fisios(hoja: str) -> pd.DataFrame:
    """Lee una hoja del Sheet de fisios (Lesiones y Tratamientos).
    Devuelve DataFrame vacío si el Sheet no existe (aún no creado)."""
    try:
        client = get_client()
        ss = client.open(SHEET_FISIOS_NAME)
        ws = ss.worksheet(hoja)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def _to_date(x):
    """Convierte serial de Google Sheets o string a Timestamp con validación de rango."""
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
    # ISO primero (sin dayfirst: "2025-08-04" NO debe volverse "2025-04-08")
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(x, dayfirst=True, errors="coerce")
    return ts


def fecha_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = df[col].apply(_to_date)
    return df


def num_cols(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ── Helpers defensivos para evitar bugs NaN ──────────────────────────────────
def safe_int(v, default: int = 0) -> int:
    """Convierte v a int de forma segura. Devuelve `default` si no se puede,
    si es NaN, si es None o si es string vacío."""
    if v is None or v == "":
        return default
    try:
        n = pd.to_numeric(v, errors="coerce")
    except Exception:
        return default
    if pd.isna(n):
        return default
    try:
        return int(n)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(v, default: float = 0.0) -> float:
    """Como safe_int pero a float."""
    if v is None or v == "":
        return default
    try:
        n = pd.to_numeric(v, errors="coerce")
    except Exception:
        return default
    if pd.isna(n):
        return default
    try:
        return float(n)
    except (TypeError, ValueError):
        return default


# ── Carga de datos ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Cargando datos…")
def datos():
    carga   = fecha_col(cargar("_VISTA_CARGA"),    "FECHA")
    semanal = fecha_col(cargar("_VISTA_SEMANAL"),  "FECHA_LUNES")
    peso    = fecha_col(cargar("_VISTA_PESO"),      "FECHA")
    df_well = fecha_col(cargar("_VISTA_WELLNESS"),  "FECHA")
    sem     = cargar("_VISTA_SEMAFORO")
    rec     = cargar("_VISTA_RECUENTO")
    les     = fecha_col(fecha_col(cargar("LESIONES"), "FECHA LESIÓN"), "FECHA ALTA")
    # _VISTA_OLIVER es opcional (solo existe si se ha corrido oliver_sync)
    try:
        oliver = fecha_col(cargar("_VISTA_OLIVER"), "FECHA")
    except Exception:
        oliver = pd.DataFrame()
    # _VISTA_EJERCICIOS es opcional (solo existe si se ha corrido oliver_ejercicios.py)
    try:
        ejercicios = fecha_col(cargar("_VISTA_EJERCICIOS"), "fecha")
    except Exception:
        ejercicios = pd.DataFrame()
    # Estadísticas de partido — opcional (solo si se corrió estadisticas_partidos.py --upload)
    # IMPORTANTE: cada hoja en su propio try/except. Antes estaban
    # agrupadas y si una fallaba, las 3 quedaban vacías.
    try:
        est_jug = cargar("_VISTA_EST_JUGADOR")
    except Exception:
        est_jug = pd.DataFrame()
    try:
        est_partidos = cargar("EST_PARTIDOS")
    except Exception:
        est_partidos = pd.DataFrame()
    try:
        est_eventos = cargar("EST_EVENTOS")
    except Exception:
        est_eventos = pd.DataFrame()
    try:
        est_avanz = cargar("_VISTA_EST_AVANZADAS")
    except Exception:
        est_avanz = pd.DataFrame()
    try:
        est_cuart = cargar("_VISTA_EST_CUARTETOS")
    except Exception:
        est_cuart = pd.DataFrame()
    try:
        est_disparos = cargar("EST_DISPAROS")
    except Exception:
        est_disparos = pd.DataFrame()
    try:
        est_disparos_zonas = cargar("EST_DISPAROS_ZONAS")
    except Exception:
        est_disparos_zonas = pd.DataFrame()
    try:
        scout_raw = cargar("SCOUTING_RIVALES")
    except Exception:
        scout_raw = pd.DataFrame()
    try:
        scout_agr = cargar("_VISTA_SCOUTING_RIVAL")
    except Exception:
        scout_agr = pd.DataFrame()
    try:
        est_tot_partido = cargar("EST_TOTALES_PARTIDO")
    except Exception:
        est_tot_partido = pd.DataFrame()
    # Roster maestro de jugadores (creado por src/setup_roster.py)
    try:
        jugadores_roster = cargar("JUGADORES_ROSTER")
    except Exception:
        jugadores_roster = pd.DataFrame()
    # Faltas y penaltis (iter 7-8, se rellenan desde form Editar partido)
    try:
        est_faltas = cargar("EST_FALTAS")
    except Exception:
        est_faltas = pd.DataFrame()
    try:
        est_penaltis = cargar("EST_PENALTIS_10M")
    except Exception:
        est_penaltis = pd.DataFrame()
    # Scouting de equipos rivales (iter 10, granular por gol y por penalti)
    try:
        scout_goles = cargar("EST_SCOUTING_GOLES")
    except Exception:
        scout_goles = pd.DataFrame()
    try:
        scout_pen = cargar("EST_SCOUTING_PEN_10M")
    except Exception:
        scout_pen = pd.DataFrame()

    for df in [carga, semanal]:
        num_cols(df, ["BORG", "MINUTOS", "CARGA", "ACWR", "CARGA_AGUDA",
                      "CARGA_CRONICA", "MONOTONIA", "FATIGA", "CARGA_SEMANAL", "SESIONES"])
    num_cols(peso,    ["PESO_PRE", "PESO_POST", "DIFERENCIA", "PCT_PERDIDA",
                       "BASELINE_PRE", "DESVIACION_BASELINE"])
    num_cols(df_well, ["SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL",
                       "WELLNESS_7D", "BASELINE_WELLNESS", "DESVIACION_BASELINE"])
    num_cols(sem,     ["ACWR", "MONOTONIA", "WELLNESS_MEDIO", "PESO_PRE_DESV_KG",
                       "WELLNESS_BELOW15", "ALERTAS_ACTIVAS"])
    num_cols(rec,     ["TOTAL_SESIONES_EQUIPO", "SESIONES_CON_DATOS", "PCT_PARTICIPACION",
                       "EST_S", "EST_A", "EST_L", "EST_N", "EST_D", "EST_NC"])
    if not oliver.empty:
        num_cols(oliver, [
            "played_time", "distancia_total_m", "distancia_hsr_m", "velocidad_max_kmh",
            "acc_alta_count", "dec_alta_count", "acc_max_count", "dec_max_count",
            "oliver_load", "kcal", "cambios_direccion", "saltos", "sprints_count",
            "BORG", "MINUTOS", "CARGA",
            "ratio_borg_oliver", "eficiencia_sprint", "asimetria_acc",
            "densidad_metabolica", "pct_hsr",
            "oliver_load_ewma_ag", "oliver_load_ewma_cr", "acwr_mecanico",
        ])

    return carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr, est_tot_partido, est_disparos_zonas, jugadores_roster, est_faltas, est_penaltis, scout_goles, scout_pen


# ── Sidebar ───────────────────────────────────────────────────────────────────
import base64 as _base64
def _img_b64(path: Path) -> str | None:
    """Devuelve un PNG como string base64, o None si no existe."""
    try:
        if path.exists():
            return _base64.b64encode(path.read_bytes()).decode()
    except Exception:
        pass
    return None

_LOGOS_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
_LOGO_VERDE_B64 = _img_b64(_LOGOS_DIR / "inter_verde.png")
_LOGO_DORADO_B64 = _img_b64(_LOGOS_DIR / "inter_dorado.png")

with st.sidebar:
    if _LOGO_VERDE_B64 and _LOGO_DORADO_B64:
        st.markdown(f"""
        <div style="text-align:center; padding: 14px 0 10px 0;">
            <div style="display:flex; justify-content:center; align-items:center; gap:18px;">
                <img src="data:image/png;base64,{_LOGO_VERDE_B64}"
                     style="height:128px; width:auto;" alt="Inter verde"/>
                <img src="data:image/png;base64,{_LOGO_DORADO_B64}"
                     style="height:128px; width:auto;" alt="Inter dorado"/>
            </div>
            <div style="font-size:1.4rem; font-weight:900; color:#4CAF50; letter-spacing:2px; margin-top:14px;">INTER</div>
            <div style="font-size:0.75rem; color:#BBCDE8; letter-spacing:4px; margin-top:-2px;">FUTBOL SALA</div>
            <div style="width:60px; height:3px; background:#4CAF50; margin:8px auto 0 auto; border-radius:2px;"></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Fallback al estilo anterior si los logos no se encuentran
        st.markdown("""
        <div style="text-align:center; padding: 18px 0 10px 0;">
            <div style="font-size:2.2rem; font-weight:900; color:#4CAF50; letter-spacing:2px;">INTER</div>
            <div style="font-size:0.75rem; color:#BBCDE8; letter-spacing:4px; margin-top:-4px;">FUTBOL SALA</div>
            <div style="width:60px; height:3px; background:#4CAF50; margin:8px auto 0 auto; border-radius:2px;"></div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")

    try:
        carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr, est_tot_partido, est_disparos_zonas, jugadores_roster, est_faltas, est_penaltis, scout_goles, scout_pen = datos()
        data_ok = True
    except ValueError as e:
        # Cache obsoleto tras cambiar la firma de datos() → limpiamos y reintentamos
        if "values to unpack" in str(e):
            try:
                st.cache_data.clear()
            except Exception:
                pass
            try:
                carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr, est_tot_partido, est_disparos_zonas, jugadores_roster, est_faltas, est_penaltis, scout_goles, scout_pen = datos()
                data_ok = True
            except Exception as e2:
                st.error(f"Error cargando datos (tras limpiar cache): {e2}")
                st.stop()
        else:
            st.error(f"Error cargando datos: {e}")
            st.stop()
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    jugadores_todos = sorted(carga["JUGADOR"].dropna().unique().tolist())
    sel_jugadores = st.multiselect(
        "👤 Jugadores",
        options=jugadores_todos,
        default=jugadores_todos,
        placeholder="Todos",
    )
    if not sel_jugadores:
        sel_jugadores = jugadores_todos

    _hoy = pd.Timestamp.now().normalize().date()
    # Inicio de la temporada 25/26: 1 agosto 2025. No tiene sentido elegir fechas
    # anteriores; los datos viejos del Sheet (si los hay) son ruido.
    INICIO_TEMPORADA = pd.Timestamp("2025-08-01").date()
    fecha_min_data = carga["FECHA"].min().date() if not carga["FECHA"].dropna().empty else INICIO_TEMPORADA
    fecha_min = max(fecha_min_data, INICIO_TEMPORADA)
    fecha_max = min(carga["FECHA"].max().date(), _hoy) if not carga["FECHA"].dropna().empty else _hoy
    if fecha_min > fecha_max:
        fecha_min = fecha_max
    rango = st.date_input(
        "📅 Período",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
    )
    f_desde = pd.Timestamp(rango[0] if isinstance(rango, tuple) else fecha_min)
    f_hasta = pd.Timestamp(rango[1] if isinstance(rango, tuple) and len(rango) == 2 else fecha_max)

    st.markdown("---")
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Datos en tiempo real desde Google Sheets")

    # Cerrar sesión (solo aparece si hay contraseña configurada)
    try:
        _has_pwd = bool(st.secrets.get("APP_PASSWORD", None))
    except Exception:
        _has_pwd = False
    if _has_pwd and st.session_state.get("auth_ok"):
        if st.button("🔒 Cerrar sesión", use_container_width=True):
            st.session_state["auth_ok"] = False
            st.rerun()


# ── Filtros helpers ───────────────────────────────────────────────────────────
_jugs = list(sel_jugadores)  # convertir a lista pura para evitar problemas de tipo

# Wellness del período seleccionado (para semáforo dinámico)
_well_periodo = df_well[
    df_well["JUGADOR"].isin(_jugs) &
    (df_well["FECHA"] >= f_desde) &
    (df_well["FECHA"] <= f_hasta)
]
_well_stats = (
    _well_periodo.groupby("JUGADOR")["TOTAL"]
    .agg(
        well_mean ="mean",
        well_below=lambda x: int((x < 15).sum()),
        well_total="count",
    )
    .reset_index()
) if not _well_periodo.empty else pd.DataFrame(
    columns=["JUGADOR", "well_mean", "well_below", "well_total"]
)


def fj(df, col="JUGADOR"):
    try:
        if not isinstance(df, pd.DataFrame) or col not in df.columns:
            return df
        return df[df[col].isin(_jugs)]
    except Exception:
        return df

def ff(df, col="FECHA"):
    try:
        if not isinstance(df, pd.DataFrame) or col not in df.columns:
            return df
        return df[(df[col] >= f_desde) & (df[col] <= f_hasta)]
    except Exception:
        return df

def fjs(df, col="FECHA_LUNES"):
    return ff(fj(df), col)


# ── Helpers de gráficos ───────────────────────────────────────────────────────
LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Arial", size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

def color_jug(jugadores):
    return {j: COLORES_JUGADORES[i % len(COLORES_JUGADORES)]
            for i, j in enumerate(sorted(jugadores))}


# ═══════════════════════════════════════════════════════════════════════════════
# TÍTULO
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("# 🏆 Panel de Temporada — Arkaitz 25/26")

(tab_sem, tab_carga, tab_peso, tab_well, tab_les, tab_temp, tab_antro, tab_rec,
 tab_oliver, tab_ejer, tab_partido, tab_equipo, tab_efic, tab_goles, tab_comp,
 tab_scout, tab_falt_pen, tab_editar) = st.tabs([
    "🚦 Semáforo",
    "📊 Carga",
    "⚖️ Peso",
    "💤 Wellness",
    "🏥 Lesiones / Tratamientos",
    "🌡️ Temperatura",
    "📐 Antropometría",
    "📋 Recuento",
    "🏃 Oliver",
    "🎯 Ejercicios",
    "🎮 Partido",
    "📊 Equipo",
    "📈 Eficiencia",
    "🥅 Goles",
    "🏅 Competición",
    "🔍 Scouting",
    "🎯 10 metros / Penaltis",
    "✏️ Editar partido",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SEMÁFORO DE RIESGO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sem:
    st.markdown("### Estado actual del equipo")
    st.caption("ACWR = última semana (EWMA). Wellness y Peso = media del período seleccionado en el panel lateral.")

    sem_f = sem[sem["JUGADOR"].isin(sel_jugadores)].copy()

    # ── KPIs generales ──
    n_rojo    = (sem_f["SEMAFORO_GLOBAL"] == "ROJO").sum()
    n_naranja = (sem_f["SEMAFORO_GLOBAL"] == "NARANJA").sum()
    n_verde   = (sem_f["SEMAFORO_GLOBAL"] == "VERDE").sum()
    acwr_med  = sem_f["ACWR"].mean()
    # Wellness medio del período seleccionado (no de la vista pre-calculada)
    well_med_kpi = float(_well_periodo["TOTAL"].mean()) if not _well_periodo.empty else float("nan")

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, lbl, color in [
        (c1, n_rojo,    "🔴 En riesgo",     ROJO),
        (c2, n_naranja, "🟠 Precaución",     NARANJA),
        (c3, n_verde,   "🟢 OK",             VERDE),
        (c4, f"{acwr_med:.2f}" if not np.isnan(acwr_med) else "—", "ACWR medio", AZUL),
        (c5, f"{well_med_kpi:.1f}/20" if not np.isnan(well_med_kpi) else "—", "Wellness medio", GRIS),
    ]:
        col.markdown(
            f'<div class="metric-card">'
            f'<div class="val" style="color:{color}">{val}</div>'
            f'<div class="lbl">{lbl}</div></div>',
            unsafe_allow_html=True
        )

    st.markdown("")

    # ── Tarjetas por jugador ──
    # Orden custom solicitado:
    #  Grupo 1: Porteros 1er equipo  → J.HERRERO, J.GARCIA
    #  Grupo 2: Campo 1er equipo     → CECILIO, CHAGUINHA, RAUL, HARRISON,
    #                                   RAYA, JAVI, PANI, PIRATA, BARONA, CARLOS
    #  Grupo 3: Portero filial        → OSCAR
    #  Grupo 4: Campo filial          → RUBIO, JAIME, SEGO, DANI, NACHO + resto
    # Aliases por si el nombre llega con/sin prefijo "J." (la vista usa
    # "HERRERO"/"GARCIA" pero el roster guarda "J.HERRERO"/"J.GARCIA").
    GRUPO_PORT_1ER = ["HERRERO", "J.HERRERO", "GARCIA", "J.GARCIA"]
    GRUPO_CAMPO_1ER = ["CECILIO", "CHAGUINHA", "RAUL", "HARRISON",
                        "RAYA", "JAVI", "PANI", "PIRATA", "BARONA", "CARLOS"]
    GRUPO_PORT_FIL = ["OSCAR"]
    GRUPO_CAMPO_FIL_PRIO = ["RUBIO", "JAIME", "SEGO", "DANI", "NACHO",
                              "GONZALO", "GONZA", "PABLO", "GABRI"]

    def _grupo_de(nombre: str) -> tuple[int, int]:
        """(idx_grupo, idx_dentro_del_grupo). Cuanto menor mejor."""
        n = (nombre or "").upper().strip()
        if n in GRUPO_PORT_1ER:
            return (1, GRUPO_PORT_1ER.index(n))
        if n in GRUPO_CAMPO_1ER:
            return (2, GRUPO_CAMPO_1ER.index(n))
        if n in GRUPO_PORT_FIL:
            return (3, GRUPO_PORT_FIL.index(n))
        if n in GRUPO_CAMPO_FIL_PRIO:
            return (4, GRUPO_CAMPO_FIL_PRIO.index(n))
        return (5, 0)  # filial resto, alfabético después

    sem_f["_g"] = sem_f["JUGADOR"].apply(lambda j: _grupo_de(j)[0])
    sem_f["_p"] = sem_f["JUGADOR"].apply(lambda j: _grupo_de(j)[1])
    sem_ordenado = sem_f.sort_values(["_g", "_p", "JUGADOR"]).reset_index(drop=True)

    CARD_COLORS = {
        "ROJO":    ("rgba(183,28,28,0.92)",  "#FFCDD2", "#B71C1C"),
        "NARANJA": ("rgba(230,81,0,0.90)",   "#FFE0B2", "#E65100"),
        "AMARILLO":("rgba(245,127,23,0.88)", "#FFF9C4", "#F57F17"),
        "VERDE":   ("rgba(27,94,32,0.88)",   "#C8E6C9", "#1B5E20"),
        "AZUL":    ("rgba(21,101,192,0.88)", "#BBDEFB", "#1565C0"),
        "GRIS":    ("rgba(97,97,97,0.80)",   "#F5F5F5", "#424242"),
    }

    # Etiquetas de grupo para mostrar como cabeceras de sección
    GRUPO_LABELS = {
        1: "🥅 Porteros · Primer equipo",
        2: "⚽ Jugadores · Primer equipo",
        3: "🥅 Portero · Filial",
        4: "⚽ Jugadores · Filial",
        5: "👥 Otros",
    }

    n_cols = 4

    # Renderizar por grupos con separación visual
    for grupo_idx in [1, 2, 3, 4, 5]:
        grupo_df = sem_ordenado[sem_ordenado["_g"] == grupo_idx]
        if grupo_df.empty:
            continue
        # Cabecera de sección
        st.markdown(
            f'<div style="margin: 18px 0 8px 0; padding: 6px 12px; '
            f'background: rgba(27,58,107,0.07); border-left: 4px solid #1B3A6B; '
            f'border-radius: 4px; font-weight: 700; color: #1B3A6B; '
            f'font-size: 0.95rem;">'
            f'{GRUPO_LABELS[grupo_idx]} '
            f'<span style="color:#888; font-weight:400; font-size:0.8rem;">'
            f'· {len(grupo_df)} jugador{"es" if len(grupo_df) != 1 else ""}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        rows_cards = [grupo_df.iloc[i:i+n_cols] for i in range(0, len(grupo_df), n_cols)]
        for row_group in rows_cards:
            cols_sem = st.columns(n_cols)
            for i, (_, row) in enumerate(row_group.iterrows()):
                estado      = row.get("SEMAFORO_GLOBAL", "GRIS")
                bg, _, txt  = CARD_COLORS.get(estado, CARD_COLORS["GRIS"])
                emoji, _    = MAP_SEMAFORO.get(estado, ("⚫", GRIS))

                jugador_nom = row["JUGADOR"]
                acwr        = row.get("ACWR")
                peso_desv   = row.get("PESO_PRE_DESV_KG")
                alertas     = safe_int(row.get("ALERTAS_ACTIVAS", 0))
                # Wellness dinámico del período seleccionado
                _ws = _well_stats[_well_stats["JUGADOR"] == jugador_nom]
                well_med   = float(_ws["well_mean"].iloc[0])  if not _ws.empty else float("nan")
                well_below = int(_ws["well_below"].iloc[0])   if not _ws.empty else 0
                well_total = int(_ws["well_total"].iloc[0])   if not _ws.empty else 0

                acwr_txt  = f"{acwr:.2f}" if pd.notna(acwr) else "—"
                well_txt  = (f"{well_med:.1f}/20" if pd.notna(well_med) else "—")
                below_txt = (f" ({well_below}/{well_total} bajo 15)"
                             if well_total > 0 and well_below > 0 else "")
                well_full = well_txt + below_txt
                peso_txt  = f"{peso_desv:+.1f} kg" if pd.notna(peso_desv) else "—"
                alert_txt = "⚠ " * alertas if alertas else "✓ Sin alertas"

                # Barra de ACWR (0 a 2, zona ok 0.8-1.3 marcada)
                acwr_pct = min(max(float(acwr) / 2.0, 0), 1) * 100 if pd.notna(acwr) else 0
                bar_color = ("#EF9A9A" if (pd.notna(acwr) and float(acwr) > 1.3)
                             else "#A5D6A7")

                # Semáforos individuales de cada métrica
                s_acwr = ("🔴" if pd.notna(acwr) and float(acwr) > 1.5 else
                          "🟠" if pd.notna(acwr) and float(acwr) > 1.3 else
                          "🔵" if pd.notna(acwr) and float(acwr) < 0.8 else "🟢")
                s_well = ("🔴" if pd.notna(well_med) and float(well_med) < 10 else
                          "🟠" if pd.notna(well_med) and float(well_med) < 13 else "🟢")
                s_peso = ("🔴" if pd.notna(peso_desv) and float(peso_desv) < -3.0 else
                          "🟠" if pd.notna(peso_desv) and float(peso_desv) < -1.5 else "🟢")

                cols_sem[i].markdown(f"""
                <div class="player-card" style="background:{bg}; color:white;">
                    <div class="player-name">{emoji} {row['JUGADOR']}</div>
                    <div class="player-stats">
                        {s_acwr} ACWR: <b>{acwr_txt}</b><br>
                        {s_well} Wellness: <b>{well_full}</b><br>
                        {s_peso} Δ Peso PRE: <b>{peso_txt}</b>
                    </div>
                    <div class="acwr-bar-bg">
                        <div class="acwr-bar-fill" style="width:{acwr_pct:.0f}%; background:{bar_color};"></div>
                    </div>
                    <div style="font-size:0.75rem; margin-top:6px; opacity:0.9;">{alert_txt}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # ── ACWR del equipo (evolución temporal) ──
    st.markdown("### Evolución ACWR — Toda la temporada")
    sem_ev = fjs(semanal)
    if not sem_ev.empty:
        cols_linea = st.columns([3, 1])
        with cols_linea[1]:
            modo = st.radio("Vista", ["Individual", "Media equipo"], index=0, key="r_acwr")

        if modo == "Individual":
            fig = px.line(
                sem_ev, x="FECHA_LUNES", y="ACWR", color="JUGADOR",
                color_discrete_map=color_jug(sem_ev["JUGADOR"].unique()),
                title="ACWR por jugador (EWMA)",
            )
        else:
            equipo = sem_ev.groupby("FECHA_LUNES")["ACWR"].mean().reset_index()
            fig = px.line(equipo, x="FECHA_LUNES", y="ACWR", title="ACWR medio del equipo")

        fig.add_hrect(y0=0.8, y1=1.3, fillcolor="green",  opacity=0.08, line_width=0)
        fig.add_hrect(y0=1.3, y1=1.5, fillcolor="orange", opacity=0.10, line_width=0)
        fig.add_hrect(y0=1.5, y1=3.0, fillcolor="red",    opacity=0.08, line_width=0)
        fig.add_hline(y=1.3, line_dash="dash", line_color="orange", line_width=1)
        fig.add_hline(y=0.8, line_dash="dash", line_color=AZUL,    line_width=1)
        fig.update_layout(**LAYOUT, height=380)
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CARGA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_carga:
    carga_f = ff(fj(carga))

    # ── Selector de semana (solo semanas con datos reales, no futuras) ──
    _hoy_ts = pd.Timestamp.now().normalize()
    semanas = [s for s in sorted(semanal["FECHA_LUNES"].dropna().unique())
               if pd.Timestamp(s) <= _hoy_ts]
    semana_sel = st.select_slider(
        "📅 Semana",
        options=semanas,
        value=semanas[-1] if len(semanas) else None,
        format_func=lambda d: pd.Timestamp(d).strftime("S%-V · %d/%m/%Y"),
        key="sl_semana",
    )
    semana_ts = pd.Timestamp(semana_sel)
    semana_fin = semana_ts + pd.Timedelta(days=6)

    st.markdown(f"### RPE semanal — {semana_ts.strftime('%d/%m')} al {semana_fin.strftime('%d/%m/%Y')}")

    # ── Tabla RPE semanal (igual que Excel) ──
    sem_df = carga[(carga["FECHA"] >= semana_ts) & (carga["FECHA"] <= semana_fin)]
    sem_df = sem_df[sem_df["JUGADOR"].isin(sel_jugadores)]

    if sem_df.empty:
        st.info("No hay datos de Borg en esta semana.")
    else:
        # Pivot: jugador × fecha×turno
        sem_df["DIA_TURNO"] = sem_df["FECHA"].dt.strftime("%a %d") + " " + sem_df["TURNO"].fillna("")
        pivot_rpe = (sem_df.pivot_table(
            index="JUGADOR", columns="DIA_TURNO", values="BORG", aggfunc="mean"
        ).round(1))
        # Ordenar columnas cronológicamente (no alfabéticamente).
        # Construir mapping DIA_TURNO → fecha real + orden de turno (M < T < P)
        _orden_t = {"M": 0, "T": 1, "P": 2}
        _key_dia = (sem_df.assign(
            _ord=sem_df["FECHA"].astype("int64") + sem_df["TURNO"].fillna("").map(_orden_t).fillna(99)
        ).groupby("DIA_TURNO")["_ord"].min().to_dict())
        cols_ordenadas = sorted(pivot_rpe.columns, key=lambda c: _key_dia.get(c, 0))
        pivot_rpe = pivot_rpe[cols_ordenadas]

        # Calcular carga y media
        pivot_rpe["CARGA SEMANA"] = sem_df.groupby("JUGADOR")["CARGA"].sum().round(0).reindex(pivot_rpe.index)
        pivot_rpe["MEDIA BORG"]   = sem_df.groupby("JUGADOR")["BORG"].mean().round(2).reindex(pivot_rpe.index)

        def color_borg(val):
            if pd.isna(val) or not isinstance(val, (int, float)):
                return ""
            if val >= 8:    return "background-color: #FFCDD2; font-weight:bold"
            if val >= 6:    return "background-color: #FFE0B2"
            if val >= 4:    return "background-color: #FFF9C4"
            return "background-color: #E8F5E9"

        # color_borg solo sobre columnas de Borg (no sobre CARGA SEMANA ni MEDIA BORG)
        borg_cols_pivot = [c for c in pivot_rpe.columns if c not in ["CARGA SEMANA", "MEDIA BORG"]]
        styled = (
            pivot_rpe.style
            .map(color_borg, subset=borg_cols_pivot)
            .format("{:.1f}", subset=borg_cols_pivot, na_rep="—")
            .format("{:.0f}", subset=["CARGA SEMANA"], na_rep="—")
            .format("{:.2f}", subset=["MEDIA BORG"],   na_rep="—")
        )
        st.dataframe(styled, use_container_width=True)

    st.markdown("---")

    # ── Gráficos de la semana seleccionada ──
    c_izq, c_der = st.columns(2)

    with c_izq:
        st.markdown("#### Carga por sesión esta semana")
        if not sem_df.empty:
            fig = px.bar(
                sem_df.sort_values("FECHA"),
                x="DIA_TURNO", y="CARGA", color="JUGADOR",
                barmode="group",
                color_discrete_map=color_jug(sem_df["JUGADOR"].unique()),
                category_orders={"DIA_TURNO": cols_ordenadas},
            )
            fig.update_layout(**LAYOUT, height=320, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    with c_der:
        st.markdown("#### Borg medio por sesión")
        if not sem_df.empty:
            _borg_medio = (sem_df.groupby("DIA_TURNO")["BORG"].mean()
                           .reindex(cols_ordenadas).reset_index())
            fig2 = px.bar(
                _borg_medio,
                x="DIA_TURNO", y="BORG",
                color="BORG",
                color_continuous_scale=["#81C784", "#FFF176", "#EF9A9A"],
                range_color=[0, 10],
                category_orders={"DIA_TURNO": cols_ordenadas},
            )
            fig2.update_layout(**LAYOUT, height=320, coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.markdown("### PSE — Carga individual por semana (temporada completa)")

    sem_all = fj(semanal)
    if not sem_all.empty:
        pivot_pse = sem_all.pivot_table(
            index="JUGADOR", columns="FECHA_LUNES", values="CARGA_SEMANAL"
        ).fillna(0).astype(int)
        pivot_pse.columns = [pd.Timestamp(c).strftime("S%-V\n%d/%m") for c in pivot_pse.columns]

        # Heatmap
        fig_pse = px.imshow(
            pivot_pse,
            aspect="auto",
            color_continuous_scale=["#E8F5E9", "#FFF9C4", "#FFCCBC", "#EF9A9A"],
            title="Carga semanal (Borg × min) por jugador",
        )
        fig_pse.update_layout(**LAYOUT, height=420)
        st.plotly_chart(fig_pse, use_container_width=True)

    st.markdown("---")
    st.markdown("### Monotonía y Fatiga semanal")

    mono_f = fjs(semanal)
    if not mono_f.empty:
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            fig_mono = px.line(
                mono_f, x="FECHA_LUNES", y="MONOTONIA", color="JUGADOR",
                title="Monotonía (>2 = riesgo)",
                color_discrete_map=color_jug(mono_f["JUGADOR"].unique()),
            )
            fig_mono.add_hline(y=2, line_dash="dash", line_color=ROJO, line_width=1.5)
            fig_mono.update_layout(**LAYOUT, height=300)
            st.plotly_chart(fig_mono, use_container_width=True)

        with c_m2:
            fig_fat = px.line(
                mono_f, x="FECHA_LUNES", y="FATIGA", color="JUGADOR",
                title="Fatiga acumulada",
                color_discrete_map=color_jug(mono_f["JUGADOR"].unique()),
            )
            fig_fat.update_layout(**LAYOUT, height=300)
            st.plotly_chart(fig_fat, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PESO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_peso:
    st.markdown("### Vista semanal de peso")

    # Selector de semana — usando fecha del lunes de cada semana (evita Period deprecado)
    _peso_lunes = (peso["FECHA"].dropna()
                   - pd.to_timedelta(peso["FECHA"].dropna().dt.dayofweek, unit="D"))
    _hoy_ts = pd.Timestamp.now().normalize()
    semanas_peso = [s for s in sorted(_peso_lunes.unique()) if pd.Timestamp(s) <= _hoy_ts]
    sp_ini = pd.Timestamp(st.select_slider(
        "📅 Semana",
        options=semanas_peso,
        value=semanas_peso[-1] if len(semanas_peso) else None,
        format_func=lambda d: pd.Timestamp(d).strftime("%d/%m/%Y"),
        key="sl_peso",
    ))
    sp_fin = sp_ini + pd.Timedelta(days=6)

    peso_sem = peso[(peso["FECHA"] >= sp_ini) & (peso["FECHA"] <= sp_fin)]
    peso_sem = peso_sem[peso_sem["JUGADOR"].isin(sel_jugadores)]

    if peso_sem.empty:
        st.info("Sin datos de peso en esta semana.")
    else:
        st.markdown(f"**{sp_ini.strftime('%d/%m')} — {sp_fin.strftime('%d/%m/%Y')}**")

        # Tabla PRE / POST / DIF como en Excel
        peso_sem["DIA"] = peso_sem["FECHA"].dt.strftime("%a %d/%m")
        # Mapping DIA → fecha real (para ordenar columnas cronológicamente,
        # no alfabéticamente "Fri, Mon, Sat...")
        _key_dia_peso = peso_sem.groupby("DIA")["FECHA"].min().to_dict()
        _cols_orden_peso = sorted(peso_sem["DIA"].unique(),
                                    key=lambda c: _key_dia_peso.get(c, pd.Timestamp.min))
        pivot_pre  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PESO_PRE",  aggfunc="first").round(1)
        pivot_post = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PESO_POST", aggfunc="first").round(1)
        pivot_dif  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="DIFERENCIA",aggfunc="first").round(2)
        pivot_pct  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PCT_PERDIDA",aggfunc="first").round(1)
        # Reordenar columnas cronológicamente
        pivot_pre  = pivot_pre[[c for c in _cols_orden_peso if c in pivot_pre.columns]]
        pivot_post = pivot_post[[c for c in _cols_orden_peso if c in pivot_post.columns]]
        pivot_dif  = pivot_dif[[c for c in _cols_orden_peso if c in pivot_dif.columns]]
        pivot_pct  = pivot_pct[[c for c in _cols_orden_peso if c in pivot_pct.columns]]

        subtabs = st.tabs(["PRE", "POST", "DIFERENCIA (kg)", "% Pérdida", "Δ vs Baseline"])
        with subtabs[0]: st.dataframe(pivot_pre,  use_container_width=True)
        with subtabs[1]: st.dataframe(pivot_post, use_container_width=True)
        with subtabs[2]:
            def color_dif(v):
                if pd.isna(v): return ""
                if v > 2:   return "background-color:#FFCDD2;font-weight:bold"
                if v > 1:   return "background-color:#FFE0B2"
                return "background-color:#E8F5E9"
            st.dataframe(pivot_dif.style.map(color_dif), use_container_width=True)
        with subtabs[3]:
            def color_pct(v):
                if pd.isna(v): return ""
                if v > 3:   return "background-color:#FFCDD2;font-weight:bold"
                if v > 2:   return "background-color:#FFE0B2"
                return "background-color:#E8F5E9"
            st.dataframe(pivot_pct.style.map(color_pct), use_container_width=True)
        with subtabs[4]:
            if "DESVIACION_BASELINE" in peso_sem.columns:
                pivot_dev = peso_sem.pivot_table(
                    index="JUGADOR", columns="DIA", values="DESVIACION_BASELINE", aggfunc="first"
                ).round(2)
                pivot_dev = pivot_dev[[c for c in _cols_orden_peso if c in pivot_dev.columns]]
                def color_dev(v):
                    if pd.isna(v): return ""
                    if v < -3:  return "background-color:#FFCDD2;font-weight:bold"
                    if v < -1.5: return "background-color:#FFE0B2"
                    if v > 1.5:  return "background-color:#E3F2FD"
                    return "background-color:#E8F5E9"
                st.caption("Desviación respecto al baseline personal (últimos 2 meses). Negativo = por debajo del peso habitual.")
                st.dataframe(pivot_dev.style.map(color_dev), use_container_width=True)
            else:
                st.info("Sin datos de baseline disponibles.")

    st.markdown("---")
    st.markdown("### Evolución de peso — temporada completa")

    peso_f = ff(fj(peso))
    if not peso_f.empty:
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            fig_peso = px.line(
                peso_f.sort_values("FECHA"),
                x="FECHA", y="PESO_PRE", color="JUGADOR",
                title="Peso PRE por sesión",
                color_discrete_map=color_jug(peso_f["JUGADOR"].unique()),
            )
            fig_peso.update_layout(**LAYOUT, height=350)
            st.plotly_chart(fig_peso, use_container_width=True)

        with c_p2:
            fig_pct = px.box(
                peso_f, x="JUGADOR", y="PCT_PERDIDA",
                color="JUGADOR",
                color_discrete_map=color_jug(peso_f["JUGADOR"].unique()),
                title="% Pérdida de peso por sesión (distribución)",
            )
            fig_pct.add_hline(y=2, line_dash="dash", line_color=NARANJA, annotation_text="2% (atención)")
            fig_pct.add_hline(y=3, line_dash="dash", line_color=ROJO,    annotation_text="3% (riesgo)")
            fig_pct.update_layout(**LAYOUT, height=350, showlegend=False)
            st.plotly_chart(fig_pct, use_container_width=True)

        # Alertas de pérdida >2%
        alertas_peso = peso_f[peso_f["PCT_PERDIDA"] > 2][
            ["FECHA", "JUGADOR", "TIPO_SESION", "PESO_PRE", "PESO_POST", "DIFERENCIA", "PCT_PERDIDA"]
        ].sort_values("FECHA", ascending=False)

        if not alertas_peso.empty:
            with st.expander(f"⚠ {len(alertas_peso)} sesiones con pérdida > 2% de peso corporal"):
                st.dataframe(alertas_peso, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — WELLNESS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_well:
    st.markdown("### Wellness diario — Heatmap")

    well_f  = ff(fj(df_well))

    if well_f.empty:
        st.info("Sin datos de wellness en el rango seleccionado.")
    else:
        # Heatmap igual que Excel WELLNESS DIARIO
        pivot_w = well_f.pivot_table(
            index="JUGADOR", columns="FECHA", values="TOTAL", aggfunc="mean"
        ).round(1)

        fig_heat = px.imshow(
            pivot_w,
            aspect="auto",
            color_continuous_scale=["#EF9A9A", "#FFF9C4", "#A5D6A7"],
            range_color=[8, 20],
            title="Wellness total (suma S+F+M+Á) · máximo = 20",
        )
        fig_heat.update_traces(hovertemplate="%{x|%d/%m}<br>%{y}: %{z:.1f}<extra></extra>")
        fig_heat.update_xaxes(tickformat="%d/%m", tickangle=-45)
        fig_heat.update_layout(**LAYOUT, height=450, coloraxis_showscale=True)
        st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("---")
    st.markdown("### Wellness semanal")

    # Selector semana wellness (no permitir futuras)
    _hoy_ts = pd.Timestamp.now().normalize()
    semanas_w = [s for s in sorted(semanal["FECHA_LUNES"].dropna().unique())
                 if pd.Timestamp(s) <= _hoy_ts]
    semana_w  = st.select_slider(
        "📅 Semana",
        options=semanas_w,
        value=semanas_w[-1] if semanas_w else None,
        format_func=lambda d: pd.Timestamp(d).strftime("S%-V · %d/%m/%Y"),
        key="sl_wellness",
    )
    sw_ini = pd.Timestamp(semana_w)
    sw_fin = sw_ini + pd.Timedelta(days=6)

    well_sem = df_well[(df_well["FECHA"] >= sw_ini) & (df_well["FECHA"] <= sw_fin)]
    well_sem = well_sem[well_sem["JUGADOR"].isin(sel_jugadores)]

    if not well_sem.empty:
        st.markdown(f"**{sw_ini.strftime('%d/%m')} — {sw_fin.strftime('%d/%m/%Y')}**")

        # Tabla con S/F/M/Á por día (como Excel WELLNESS v2)
        well_sem["DIA"] = well_sem["FECHA"].dt.strftime("%a %d/%m")
        # Ordenar columnas cronológicamente (no alfabéticamente)
        _key_dia_well = well_sem.groupby("DIA")["FECHA"].min().to_dict()
        _cols_orden_well = sorted(well_sem["DIA"].unique(),
                                    key=lambda c: _key_dia_well.get(c, pd.Timestamp.min))
        pivot_well_dia = well_sem.pivot_table(
            index="JUGADOR", columns="DIA", values="TOTAL", aggfunc="mean"
        ).round(1)
        # Reordenar SOLO las columnas de día (las que existan en el pivot)
        _cols_dia_existen = [c for c in _cols_orden_well if c in pivot_well_dia.columns]
        pivot_well_dia = pivot_well_dia[_cols_dia_existen]
        pivot_well_dia["MEDIA SEMANA"] = well_sem.groupby("JUGADOR")["TOTAL"].mean().round(1).reindex(pivot_well_dia.index)
        pivot_well_dia["DÍAS CON DATO"] = well_sem.groupby("JUGADOR")["TOTAL"].count().reindex(pivot_well_dia.index)

        def color_well(v):
            if pd.isna(v) or not isinstance(v, (int, float)): return ""
            if v <= 10: return "background-color:#FFCDD2;font-weight:bold"
            if v <= 13: return "background-color:#FFE0B2"
            return "background-color:#E8F5E9"
        # DÍAS CON DATO es entero; el resto wellness max 1 decimal
        dias_col = ["DÍAS CON DATO"] if "DÍAS CON DATO" in pivot_well_dia.columns else []
        well_cols = [c for c in pivot_well_dia.columns if c not in dias_col]
        styled_w = (
            pivot_well_dia.style
            .map(color_well, subset=well_cols)
            .format("{:.1f}", subset=well_cols, na_rep="—")
            .format("{:.0f}", subset=dias_col, na_rep="—")
        )
        st.dataframe(styled_w, use_container_width=True)

    st.markdown("---")
    st.markdown("### Evolución de los componentes del wellness")

    if not well_f.empty:
        jug_w = st.selectbox(
            "Jugador",
            options=sel_jugadores,
            key="sel_jug_well"
        )
        jug_well_df = well_f[well_f["JUGADOR"] == jug_w].sort_values("FECHA")

        if not jug_well_df.empty:
            fig_comp = go.Figure()
            componentes = {
                "SUENO":     ("Sueño",     "#7986CB"),
                "FATIGA":    ("Fatiga",    "#EF9A9A"),
                "MOLESTIAS": ("Molestias", "#FFCC80"),
                "ANIMO":     ("Ánimo",     "#A5D6A7"),
            }
            for col, (nombre, color) in componentes.items():
                if col in jug_well_df.columns:
                    fig_comp.add_trace(go.Scatter(
                        x=jug_well_df["FECHA"],
                        y=pd.to_numeric(jug_well_df[col], errors="coerce").round(2),
                        name=nombre, line=dict(color=color, width=2),
                        mode="lines+markers", marker=dict(size=4),
                        hovertemplate="%{y:.1f}<extra></extra>",
                    ))
            # Media 7 días
            if "WELLNESS_7D" in jug_well_df.columns:
                # Normalizar a escala /4 para comparar con componentes (1-5)
                fig_comp.add_trace(go.Scatter(
                    x=jug_well_df["FECHA"],
                    y=(jug_well_df["WELLNESS_7D"] / 4).round(2),
                    name="Wellness medio 7d (÷4)", line=dict(color="black", width=2, dash="dot"),
                ))
            fig_comp.update_layout(
                **LAYOUT, height=350,
                title=f"Componentes de Wellness — {jug_w}",
                yaxis=dict(range=[0.5, 5.5]),
            )
            st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("---")
    st.markdown("### Media del equipo — Evolución temporal")

    if not well_f.empty:
        eq_well = (
            well_f.groupby("FECHA")
            .agg(
                Sueño    =("SUENO",     "mean"),
                Fatiga   =("FATIGA",    "mean"),
                Molestias=("MOLESTIAS", "mean"),
                Ánimo    =("ANIMO",     "mean"),
                Total    =("TOTAL",     "mean"),
            )
            .reset_index()
            .round(2)
        )

        fig_eq = go.Figure()
        for comp, color_c in [("Sueño", "#7986CB"), ("Fatiga", "#EF9A9A"),
                               ("Molestias", "#FFCC80"), ("Ánimo", "#A5D6A7")]:
            fig_eq.add_trace(go.Scatter(
                x=eq_well["FECHA"], y=eq_well[comp],
                name=comp, line=dict(color=color_c, width=2),
                mode="lines+markers", marker=dict(size=3),
                hovertemplate=comp + ": %{y:.2f}<extra></extra>",
            ))
        # Total en eje derecho (escala 4-20)
        fig_eq.add_trace(go.Scatter(
            x=eq_well["FECHA"], y=eq_well["Total"],
            name="Total (4-20)", yaxis="y2",
            line=dict(color="#1B3A6B", width=2.5, dash="dot"),
            mode="lines",
            hovertemplate="Total: %{y:.1f}<extra></extra>",
        ))
        # LAYOUT ya incluye `legend`; evitar pasarlo dos veces
        _layout_no_leg = {k: v for k, v in LAYOUT.items() if k != "legend"}
        fig_eq.update_layout(
            **_layout_no_leg, height=400,
            title="Media del equipo — Componentes Wellness (período seleccionado)",
            yaxis =dict(title="Componentes (1-5)", range=[0.5, 5.5]),
            yaxis2=dict(title="Total (4-20)", range=[2, 22],
                        overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_eq, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — LESIONES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_les:
    st.markdown("### 🏥 Lesiones y Tratamientos")
    st.caption("Datos del Sheet de fisios. Si no aparece nada, asegúrate de que "
               "el Sheet 'Arkaitz - Lesiones y Tratamientos 2526' existe y está "
               "compartido con la cuenta de servicio.")

    # ── Cargar de Sheet de fisios ──
    df_les_fis = cargar_fisios("LESIONES")
    df_tra_fis = cargar_fisios("TRATAMIENTOS")

    if df_les_fis.empty and df_tra_fis.empty:
        st.warning("Sheet de fisios sin datos o no accesible. "
                   "Ejecuta `src/crear_sheet_fisios.py` y "
                   "`src/calcular_vistas_fisios.py`.")
    else:
        # ── Filtros locales (jugador + fechas) ──
        st.markdown("#### Filtros")
        cf1, cf2 = st.columns([2, 2])

        # Jugadores disponibles en cualquiera de las 2 hojas
        jugs_dispo = sorted({
            *df_les_fis.get("jugador", pd.Series(dtype=str)).dropna().astype(str).str.strip().unique(),
            *df_tra_fis.get("jugador", pd.Series(dtype=str)).dropna().astype(str).str.strip().unique(),
        } - {""})
        jugs_sel_lt = cf1.multiselect(
            "Jugadores", jugs_dispo,
            default=jugs_dispo,
            key="lt_jugadores",
            help="Selecciona uno o varios jugadores. Por defecto todos.",
        )

        # Rango de fechas: ampliar a min/max entre ambas tablas
        _fechas = []
        for col_df, col_name in [(df_les_fis, "fecha_lesion"),
                                   (df_tra_fis, "fecha")]:
            if col_name in col_df.columns:
                _f = pd.to_datetime(col_df[col_name], errors="coerce").dropna()
                if not _f.empty:
                    _fechas.append(_f)
        if _fechas:
            fmin = min(f.min() for f in _fechas).date()
            fmax = max(f.max() for f in _fechas).date()
        else:
            fmin = pd.Timestamp.now().date()
            fmax = pd.Timestamp.now().date()
        rango_lt = cf2.date_input(
            "Rango de fechas",
            value=(fmin, fmax),
            min_value=fmin, max_value=fmax,
            key="lt_fechas",
        )
        if isinstance(rango_lt, tuple) and len(rango_lt) == 2:
            f_desde_lt = pd.Timestamp(rango_lt[0])
            f_hasta_lt = pd.Timestamp(rango_lt[1])
        else:
            f_desde_lt = pd.Timestamp(fmin)
            f_hasta_lt = pd.Timestamp(fmax)

        st.markdown("---")

        # ── Sección 1: LESIONES ──
        st.markdown("#### 🔴 Lesiones (actuales y pasadas)")
        if df_les_fis.empty:
            st.info("Sin lesiones registradas.")
        else:
            les_show = df_les_fis.copy()
            les_show["fecha_lesion"] = pd.to_datetime(les_show["fecha_lesion"], errors="coerce")
            if "fecha_alta" in les_show.columns:
                les_show["fecha_alta"] = pd.to_datetime(les_show["fecha_alta"], errors="coerce")
            # Filtrar por jugadores seleccionados
            if "jugador" in les_show.columns and jugs_sel_lt:
                les_show = les_show[les_show["jugador"].astype(str).str.strip().isin(jugs_sel_lt)]
            # Filtrar por fechas (lesión)
            if "fecha_lesion" in les_show.columns:
                m = (les_show["fecha_lesion"] >= f_desde_lt) & (les_show["fecha_lesion"] <= f_hasta_lt)
                les_show = les_show[m | les_show["fecha_lesion"].isna()]

            # Eliminar filas vacías (sin jugador ni fecha)
            if "jugador" in les_show.columns and "fecha_lesion" in les_show.columns:
                les_show = les_show[
                    les_show["jugador"].astype(str).str.strip().ne("") &
                    les_show["fecha_lesion"].notna()
                ].reset_index(drop=True)

            if les_show.empty:
                st.info("No hay lesiones para los filtros aplicados.")
            else:
                # KPIs
                _activas = (les_show.get("estado_actual", pd.Series(dtype=str))
                              .astype(str).str.upper()
                              .isin(["ACTIVA", "EN_RECUP", "RECAÍDA"])).sum()
                _alta = (les_show.get("estado_actual", pd.Series(dtype=str))
                            .astype(str).str.upper().eq("ALTA")).sum()
                k1, k2, k3 = st.columns(3)
                k1.metric("Total lesiones (filtrado)", len(les_show))
                k2.metric("🔴 Activas", int(_activas))
                k3.metric("✅ Cerradas", int(_alta))

                # Tabla ordenada por fecha de lesión descendente
                cols_pref = ["fecha_lesion", "jugador", "dorsal", "zona_corporal",
                             "lado", "tipo_tejido", "mecanismo", "gravedad",
                             "estado_actual", "dias_baja_estimados",
                             "dias_baja_real", "diferencia_dias",
                             "total_sesiones_perdidas", "entrenos_perdidos",
                             "partidos_perdidos", "fecha_alta", "recaida",
                             "diagnostico", "notas"]
                cols_pref = [c for c in cols_pref if c in les_show.columns]
                les_show_o = les_show[cols_pref].sort_values(
                    "fecha_lesion", ascending=False)

                # Estilo: marcar filas activas en rojo claro, alta en verde claro
                def _fila_color(row):
                    est = str(row.get("estado_actual", "")).upper()
                    if est in ("ACTIVA", "EN_RECUP", "RECAÍDA"):
                        return ["background-color: #FFCDD2"] * len(row)
                    if est == "ALTA":
                        return ["background-color: #C8E6C9"] * len(row)
                    return [""] * len(row)
                styled_les = les_show_o.style.apply(_fila_color, axis=1)
                st.dataframe(styled_les, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Sección 2: TRATAMIENTOS ──
        st.markdown("#### 🟢 Tratamientos (más reciente arriba)")
        if df_tra_fis.empty:
            st.info("Sin tratamientos registrados.")
        else:
            tra_show = df_tra_fis.copy()
            tra_show["fecha"] = pd.to_datetime(tra_show["fecha"], errors="coerce")
            # Filtros
            if "jugador" in tra_show.columns and jugs_sel_lt:
                tra_show = tra_show[tra_show["jugador"].astype(str).str.strip().isin(jugs_sel_lt)]
            if "fecha" in tra_show.columns:
                m = (tra_show["fecha"] >= f_desde_lt) & (tra_show["fecha"] <= f_hasta_lt)
                tra_show = tra_show[m | tra_show["fecha"].isna()]
            # Eliminar filas vacías
            if "jugador" in tra_show.columns and "fecha" in tra_show.columns:
                tra_show = tra_show[
                    tra_show["jugador"].astype(str).str.strip().ne("") &
                    tra_show["fecha"].notna()
                ].reset_index(drop=True)

            if tra_show.empty:
                st.info("No hay tratamientos para los filtros aplicados.")
            else:
                # KPIs
                k_pre = (tra_show.get("bloque", pd.Series(dtype=str))
                            .astype(str).str.upper().eq("PRE_ENTRENO")).sum()
                k_post = (tra_show.get("bloque", pd.Series(dtype=str))
                             .astype(str).str.upper().eq("POST_ENTRENO")).sum()
                k_les = (tra_show.get("bloque", pd.Series(dtype=str))
                             .astype(str).str.upper().eq("LESIONADO")).sum()
                kt1, kt2, kt3, kt4 = st.columns(4)
                kt1.metric("Total tratamientos", len(tra_show))
                kt2.metric("🟦 PRE", int(k_pre))
                kt3.metric("🟥 POST", int(k_post))
                kt4.metric("🏥 Lesionado", int(k_les))

                cols_pref_t = ["fecha", "turno", "bloque", "jugador", "dorsal",
                               "fisio", "accion", "zona_corporal", "lado",
                               "duracion_min", "id_lesion_relacionada", "notas"]
                cols_pref_t = [c for c in cols_pref_t if c in tra_show.columns]
                tra_show_o = tra_show[cols_pref_t].sort_values(
                    "fecha", ascending=False)

                # Color por bloque
                def _color_bloque(row):
                    b = str(row.get("bloque", "")).upper()
                    if b == "PRE_ENTRENO":
                        return ["background-color: #BBDEFB"] * len(row)
                    if b == "POST_ENTRENO":
                        return ["background-color: #FFE0B2"] * len(row)
                    if b == "LESIONADO":
                        return ["background-color: #FFCDD2"] * len(row)
                    return [""] * len(row)
                styled_tra = tra_show_o.style.apply(_color_bloque, axis=1)
                st.dataframe(styled_tra, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — TEMPERATURA MUSCULAR (cámara térmica)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_temp:
    st.markdown("### 🌡️ Temperatura muscular")
    st.caption("Mediciones con cámara térmica. La asimetría se calcula como "
               "izda − dcha; valores con |asimetría| > 0.5°C aparecen marcados "
               "como ALERTA (posible sobrecarga o riesgo de lesión).")

    df_temp = cargar_fisios("TEMPERATURA")
    if df_temp.empty:
        st.info("Sin mediciones de temperatura registradas todavía.")
    else:
        df_temp = df_temp.copy()
        if "fecha" in df_temp.columns:
            df_temp["fecha"] = pd.to_datetime(df_temp["fecha"], errors="coerce")

        # Filtros
        ct1, ct2 = st.columns([2, 2])
        jugs_temp_dispo = sorted(
            df_temp.get("jugador", pd.Series(dtype=str))
                   .dropna().astype(str).str.strip().unique().tolist())
        jugs_temp_dispo = [j for j in jugs_temp_dispo if j]
        jugs_sel_temp = ct1.multiselect(
            "Jugadores", jugs_temp_dispo,
            default=jugs_temp_dispo,
            key="temp_jugadores",
        )
        _fechas_temp = df_temp["fecha"].dropna() if "fecha" in df_temp.columns else pd.Series(dtype="datetime64[ns]")
        if not _fechas_temp.empty:
            tmin, tmax = _fechas_temp.min().date(), _fechas_temp.max().date()
            rango_t = ct2.date_input(
                "Rango de fechas",
                value=(tmin, tmax),
                min_value=tmin, max_value=tmax,
                key="temp_fechas",
            )
            if isinstance(rango_t, tuple) and len(rango_t) == 2:
                tdesde = pd.Timestamp(rango_t[0])
                thasta = pd.Timestamp(rango_t[1])
            else:
                tdesde, thasta = pd.Timestamp(tmin), pd.Timestamp(tmax)
        else:
            tdesde = thasta = pd.Timestamp.now()

        # Aplicar filtros
        df_show = df_temp.copy()
        if "jugador" in df_show.columns and jugs_sel_temp:
            df_show = df_show[df_show["jugador"].astype(str).str.strip().isin(jugs_sel_temp)]
        if "fecha" in df_show.columns:
            m = (df_show["fecha"] >= tdesde) & (df_show["fecha"] <= thasta)
            df_show = df_show[m | df_show["fecha"].isna()]
        # Filtrar filas vacías
        if "jugador" in df_show.columns and "fecha" in df_show.columns:
            df_show = df_show[
                df_show["jugador"].astype(str).str.strip().ne("") &
                df_show["fecha"].notna()
            ].reset_index(drop=True)

        if df_show.empty:
            st.info("No hay mediciones para los filtros aplicados.")
        else:
            # KPIs
            n_total = len(df_show)
            n_alertas = (df_show.get("alerta", pd.Series(dtype=str))
                            .astype(str).str.upper().eq("ALERTA")).sum()
            n_jug = df_show["jugador"].nunique() if "jugador" in df_show.columns else 0
            kr1, kr2, kr3 = st.columns(3)
            kr1.metric("Mediciones", n_total)
            kr2.metric("🚨 Alertas (>0.5°C)", int(n_alertas))
            kr3.metric("Jugadores", int(n_jug))

            # Tabla, ordenada por fecha desc
            cols_pref_temp = ["fecha", "turno", "momento", "jugador", "dorsal",
                              "zona", "temp_izda_c", "temp_dcha_c",
                              "asimetria_c", "alerta", "temp_ambiente_c", "notas"]
            cols_pref_temp = [c for c in cols_pref_temp if c in df_show.columns]
            df_show_o = df_show[cols_pref_temp].sort_values(
                "fecha", ascending=False)

            # Resaltar filas con ALERTA
            def _color_alerta(row):
                if str(row.get("alerta", "")).upper() == "ALERTA":
                    return ["background-color: #FFCDD2"] * len(row)
                return [""] * len(row)
            styled_temp = df_show_o.style.apply(_color_alerta, axis=1)
            st.dataframe(styled_temp, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB — ANTROPOMETRÍA (datos del nutricionista)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_antro:
    st.markdown("### 📐 Antropometría")
    st.caption("Datos de las mediciones del nutricionista (parseados de los "
               "PDFs). Incluye peso, altura, IMC, pliegues cutáneos, "
               "% masa grasa y composición corporal.")

    df_antro = cargar("ANTROPOMETRIA")
    if df_antro.empty:
        st.warning("Sin datos de antropometría. Ejecuta "
                   "`src/importar_antropometria.py` para cargarlos.")
    else:
        # Normalizar tipos
        df_antro = df_antro.copy()
        df_antro["fecha_medicion"] = pd.to_datetime(
            df_antro["fecha_medicion"], errors="coerce")
        for c in df_antro.columns:
            if c not in ("fecha_medicion", "jugador", "dorsal", "medicion_n"):
                df_antro[c] = pd.to_numeric(df_antro[c], errors="coerce")
        df_antro["dorsal"] = df_antro["dorsal"].astype(str)

        # ── Filtros ──
        ca1, ca2 = st.columns([2, 2])
        jugs_antro = sorted(df_antro["jugador"].dropna().astype(str).str.strip().unique())
        jugs_antro = [j for j in jugs_antro if j]
        sel_jug_antro = ca1.multiselect(
            "Jugadores", jugs_antro,
            default=jugs_antro,
            key="antro_jugs",
            help="Selecciona uno o varios. Por defecto todos.",
        )
        _f_antro = df_antro["fecha_medicion"].dropna()
        if not _f_antro.empty:
            fmin_a, fmax_a = _f_antro.min().date(), _f_antro.max().date()
            rango_antro = ca2.date_input(
                "Rango fechas",
                value=(fmin_a, fmax_a),
                min_value=fmin_a, max_value=fmax_a,
                key="antro_fechas",
            )
            if isinstance(rango_antro, tuple) and len(rango_antro) == 2:
                fa_desde, fa_hasta = pd.Timestamp(rango_antro[0]), pd.Timestamp(rango_antro[1])
            else:
                fa_desde, fa_hasta = pd.Timestamp(fmin_a), pd.Timestamp(fmax_a)
        else:
            fa_desde = fa_hasta = pd.Timestamp.now()

        # Aplicar filtros
        df_a_show = df_antro.copy()
        if sel_jug_antro:
            df_a_show = df_a_show[df_a_show["jugador"].astype(str).str.strip().isin(sel_jug_antro)]
        df_a_show = df_a_show[
            (df_a_show["fecha_medicion"] >= fa_desde) &
            (df_a_show["fecha_medicion"] <= fa_hasta)
        ].reset_index(drop=True)

        if df_a_show.empty:
            st.info("No hay datos para los filtros aplicados.")
        else:
            # ── KPIs ──
            n_med = len(df_a_show)
            n_jug = df_a_show["jugador"].nunique()
            ult_fecha = df_a_show["fecha_medicion"].max()
            kp1, kp2, kp3 = st.columns(3)
            kp1.metric("Mediciones", n_med)
            kp2.metric("Jugadores", n_jug)
            kp3.metric("Última medición",
                        ult_fecha.strftime("%d/%m/%Y") if pd.notna(ult_fecha) else "—")

            st.markdown("---")

            # ── Tabla con la última medición de cada jugador ──
            st.markdown("#### Última medición por jugador")
            ultimas = (df_a_show.sort_values("fecha_medicion")
                          .groupby("jugador").tail(1)
                          .sort_values("jugador").reset_index(drop=True))
            cols_ult = ["fecha_medicion", "jugador", "dorsal", "peso_kg",
                         "altura_cm", "imc", "sumatorio_6_pliegues_mm",
                         "masa_grasa_yuhasz_pct", "masa_grasa_faulkner_pct",
                         "masa_muscular_kg", "somatotipo_endomórfico",
                         "somatotipo_mesomórfico", "somatotipo_ectomórfico"]
            cols_ult = [c for c in cols_ult if c in ultimas.columns]
            ult_show = ultimas[cols_ult].copy()
            ult_show["fecha_medicion"] = ult_show["fecha_medicion"].dt.strftime("%d/%m/%Y")
            st.dataframe(ult_show, use_container_width=True, hide_index=True)

            st.markdown("---")

            # ── Evolución por jugador ──
            st.markdown("#### Evolución temporal")
            metricas_disponibles = {
                "Peso (kg)": "peso_kg",
                "IMC": "imc",
                "% Masa grasa (Yuhasz)": "masa_grasa_yuhasz_pct",
                "% Masa grasa (Faulkner)": "masa_grasa_faulkner_pct",
                "Sumatorio 6 pliegues (mm)": "sumatorio_6_pliegues_mm",
                "Masa muscular (kg)": "masa_muscular_kg",
                "Tríceps (mm)": "tríceps_mm",
                "Subescapular (mm)": "subescapular_mm",
                "Abdominal (mm)": "abdominal_mm",
                "Supraespinal (mm)": "supraespinal_mm",
                "Muslo (mm)": "muslo_mm",
                "Pantorrilla (mm)": "pantorrilla_mm",
                "Endomórfico": "somatotipo_endomórfico",
                "Mesomórfico": "somatotipo_mesomórfico",
                "Ectomórfico": "somatotipo_ectomórfico",
            }
            metrica_sel = st.selectbox(
                "Métrica a graficar",
                list(metricas_disponibles.keys()),
                key="antro_metrica",
            )
            col_metrica = metricas_disponibles[metrica_sel]

            if col_metrica in df_a_show.columns:
                df_plot = df_a_show.dropna(subset=[col_metrica]).sort_values("fecha_medicion")
                if df_plot.empty:
                    st.info(f"No hay datos de {metrica_sel} para los filtros aplicados.")
                else:
                    fig_antro = px.line(
                        df_plot,
                        x="fecha_medicion", y=col_metrica, color="jugador",
                        markers=True,
                        color_discrete_map=color_jug(df_plot["jugador"].unique()),
                        title=f"{metrica_sel} — evolución por jugador",
                    )
                    fig_antro.update_layout(**LAYOUT, height=500,
                                              xaxis_title="Fecha de medición",
                                              yaxis_title=metrica_sel)
                    st.plotly_chart(fig_antro, use_container_width=True)

            st.markdown("---")

            # ── Tabla histórica completa ──
            with st.expander("📊 Ver datos completos (todas las mediciones)"):
                df_full = df_a_show.copy()
                df_full["fecha_medicion"] = df_full["fecha_medicion"].dt.strftime("%Y-%m-%d")
                df_full = df_full.sort_values(
                    ["jugador", "fecha_medicion"]).reset_index(drop=True)
                st.dataframe(df_full, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — RECUENTO DE ASISTENCIA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rec:
    # Selector: temporada completa (vista pre-calculada) vs período del sidebar (dinámico)
    modo_rec = st.radio(
        "Ámbito",
        ["Temporada completa", "Solo el período seleccionado"],
        horizontal=True, key="rec_modo",
    )

    if modo_rec == "Temporada completa":
        st.markdown("### Recuento — Temporada completa")
        rec_f = rec[rec["JUGADOR"].isin(sel_jugadores)].copy() if "JUGADOR" in rec.columns else rec.copy()
    else:
        # Cálculo dinámico desde _VISTA_CARGA filtrado por fechas y jugadores
        st.markdown(f"### Recuento — {f_desde.strftime('%d/%m/%Y')} a {f_hasta.strftime('%d/%m/%Y')}")
        carga_rec = carga[(carga["FECHA"] >= f_desde) & (carga["FECHA"] <= f_hasta)].copy()
        carga_rec = carga_rec[carga_rec["JUGADOR"].isin(sel_jugadores)]

        if carga_rec.empty:
            st.info("Sin datos en el período seleccionado.")
            rec_f = pd.DataFrame()
        else:
            # Sesiones únicas del equipo en el período
            total_ses = carga_rec.drop_duplicates(["FECHA", "TURNO"]).shape[0] \
                if "TURNO" in carga_rec.columns else carga_rec["FECHA"].dt.normalize().nunique()

            rows = []
            estados = ["S", "A", "L", "N", "D", "NC"]
            for jug in sorted(carga_rec["JUGADOR"].unique()):
                jdf = carga_rec[carga_rec["JUGADOR"] == jug].drop_duplicates(["FECHA", "TURNO"]) \
                      if "TURNO" in carga_rec.columns else carga_rec[carga_rec["JUGADOR"] == jug]
                borg_str = jdf["BORG"].astype(str).str.strip()
                borg_num = pd.to_numeric(jdf["BORG"], errors="coerce")
                row = {"JUGADOR": jug, "TOTAL_SESIONES_EQUIPO": total_ses}
                for est in estados:
                    row[f"EST_{est}"] = int((borg_str == est).sum())
                row["SESIONES_CON_DATOS"] = int(borg_num.notna().sum())
                row["PCT_PARTICIPACION"] = round(
                    min(row["SESIONES_CON_DATOS"] / total_ses * 100, 100), 1
                ) if total_ses else 0
                rows.append(row)
            rec_f = pd.DataFrame(rows).sort_values("PCT_PARTICIPACION", ascending=False)

    if not rec_f.empty:
        # Tabla principal
        st.dataframe(rec_f, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Participación por jugador")

        if "PCT_PARTICIPACION" in rec_f.columns and "JUGADOR" in rec_f.columns:
            rec_sort = rec_f.sort_values("PCT_PARTICIPACION", ascending=True)
            fig_rec = px.bar(
                rec_sort,
                x="PCT_PARTICIPACION", y="JUGADOR",
                orientation="h",
                color="PCT_PARTICIPACION",
                color_continuous_scale=["#EF9A9A", "#FFF176", "#A5D6A7"],
                range_color=[50, 100],
                title="% Participación en sesiones del equipo",
                text="PCT_PARTICIPACION",
            )
            fig_rec.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_rec.add_vline(x=80, line_dash="dash", line_color=NARANJA)
            fig_rec.update_layout(**LAYOUT, height=500, coloraxis_showscale=False, showlegend=False)
            st.plotly_chart(fig_rec, use_container_width=True)

        # ── Gráfico apilado horizontal: distribución de estados por jugador ──
        st.markdown("---")
        st.markdown("### Distribución de disponibilidades por jugador")
        st.caption("Cada barra es un jugador. Verde = disponible (Borg 1-10) · "
                   "naranja/rojo/gris = no disponible (selección, ausencia, lesión, descanso, NC).")

        cols_estado = ["SESIONES_CON_DATOS", "EST_S", "EST_A", "EST_L",
                       "EST_N", "EST_D", "EST_NC"]
        cols_estado = [c for c in cols_estado if c in rec_f.columns]
        if cols_estado and "JUGADOR" in rec_f.columns:
            df_disp = rec_f[["JUGADOR"] + cols_estado].copy()
            for c in cols_estado:
                df_disp[c] = pd.to_numeric(df_disp[c], errors="coerce").fillna(0)
            # Renombrar para etiquetas legibles
            mapa_estados = {
                "SESIONES_CON_DATOS": "Disponible",
                "EST_S": "Selección", "EST_A": "Ausente",
                "EST_L": "Lesión", "EST_N": "No entrena",
                "EST_D": "Descanso", "EST_NC": "No calificado",
            }
            df_disp = df_disp.rename(columns=mapa_estados)
            cols_renamed = [mapa_estados[c] for c in cols_estado]
            df_long = df_disp.melt(id_vars="JUGADOR", value_vars=cols_renamed,
                                    var_name="Estado", value_name="Sesiones")
            # Ordenar jugadores por suma total (más arriba los que más jugaron)
            orden_j = (df_disp.set_index("JUGADOR")[cols_renamed]
                       .sum(axis=1).sort_values(ascending=True).index.tolist())
            colores = {
                "Disponible": "#2E7D32", "Selección": "#1565C0",
                "Ausente": "#FB8C00", "Lesión": "#B71C1C",
                "No entrena": "#9E9E9E", "Descanso": "#7B1FA2",
                "No calificado": "#BDBDBD",
            }
            fig_disp = px.bar(
                df_long, y="JUGADOR", x="Sesiones", color="Estado",
                orientation="h",
                category_orders={"JUGADOR": orden_j,
                                 "Estado": cols_renamed},
                color_discrete_map=colores,
                title="",
            )
            fig_disp.update_layout(
                **LAYOUT, height=max(380, 28 * len(orden_j)),
                barmode="stack",
                xaxis_title="Sesiones",
                yaxis_title="",
                legend_title="",
            )
            st.plotly_chart(fig_disp, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7 — OLIVER SPORTS (acelerometría sensores)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_oliver:
    st.markdown("### 🏃 Oliver Sports — Datos de sensores")

    if oliver.empty:
        st.info(
            "No hay datos de Oliver todavía.\n\n"
            "Para sincronizar: abre el bot de Telegram y escribe `/oliver_sync`, "
            "o desde terminal ejecuta `/usr/bin/python3 src/oliver_sync.py`."
        )
    else:
        # Filtrar por jugadores + rango de fechas del sidebar
        oliver_f = oliver[
            oliver["JUGADOR"].isin(sel_jugadores) &
            (oliver["FECHA"] >= f_desde) &
            (oliver["FECHA"] <= f_hasta)
        ].copy()

        if oliver_f.empty:
            st.warning("No hay datos de Oliver en el período / jugadores seleccionados.")
        else:
            # Redondeo defensivo: max 2 decimales en todas las columnas numéricas
            _cols_numericas = oliver_f.select_dtypes(include="number").columns
            oliver_f[_cols_numericas] = oliver_f[_cols_numericas].round(2)

            # ── KPIs del equipo en el período ──
            c1, c2, c3, c4, c5 = st.columns(5)
            kpis = [
                (c1, "Oliver Load medio", f"{oliver_f['oliver_load'].mean():.0f}", AZUL),
                (c2, "Distancia media (m)", f"{oliver_f['distancia_total_m'].mean():.0f}", GRIS),
                (c3, "Sprints/sesión", f"{oliver_f['sprints_count'].mean():.1f}", NARANJA),
                (c4, "Acc. máx/sesión", f"{oliver_f['acc_max_count'].mean():.1f}", ROJO),
                (c5, "Sesiones", f"{oliver_f['session_id'].nunique()}", VERDE),
            ]
            for col, lbl, val, color in kpis:
                col.markdown(
                    f'<div class="metric-card">'
                    f'<div class="val" style="color:{color}">{val}</div>'
                    f'<div class="lbl">{lbl}</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Tabla por jugador (agregado del período) coloreada por cuartiles ──
            st.markdown("#### Resumen por jugador (período seleccionado)")
            st.caption(
                "🟢 por encima de la media del equipo · ⚪ en la media · 🔴 por debajo. "
                "Colores SUTILES para comparar de un vistazo. 'Por debajo' NO es malo necesariamente: "
                "depende del puesto y del rol."
            )
            agg = oliver_f.groupby("JUGADOR", as_index=False).agg(
                sesiones=("session_id", "nunique"),
                oliver_load_total=("oliver_load", "sum"),
                oliver_load_medio=("oliver_load", "mean"),
                dist_total_m=("distancia_total_m", "sum"),
                dist_hsr_m=("distancia_hsr_m", "sum"),
                sprints=("sprints_count", "sum"),
                acc_alta=("acc_alta_count", "sum"),
                dec_alta=("dec_alta_count", "sum"),
                acc_max=("acc_max_count", "sum"),
                dec_max=("dec_max_count", "sum"),
                kcal=("kcal", "sum"),
                velocidad_max=("velocidad_max_kmh", "max"),
            ).round(2)
            agg = agg.sort_values("oliver_load_total", ascending=False)

            # Gradiente rojo→amarillo→verde por columna (sin matplotlib).
            # Rojo claro = valor bajo vs resto del equipo · verde claro = alto.
            def _col_gradient(s: pd.Series):
                vals = pd.to_numeric(s, errors="coerce")
                vmin, vmax = vals.min(), vals.max()
                out = []
                for v in vals:
                    if pd.isna(v) or vmax == vmin:
                        out.append("")
                        continue
                    t = (v - vmin) / (vmax - vmin)
                    t = max(0.0, min(1.0, float(t)))
                    if t < 0.5:
                        ratio = t * 2
                        r = 255
                        g = int(170 + (240 - 170) * ratio)
                        b = int(170 + (190 - 170) * ratio)
                    else:
                        ratio = (t - 0.5) * 2
                        r = int(255 + (170 - 255) * ratio)
                        g = int(240 + (225 - 240) * ratio)
                        b = int(190 + (170 - 190) * ratio)
                    out.append(f"background-color: rgb({r},{g},{b})")
                return out

            num_cols_agg = [c for c in agg.columns if c != "JUGADOR"]
            int_cols = [c for c in ["sesiones", "sprints", "acc_alta", "dec_alta", "acc_max", "dec_max"] if c in agg.columns]
            float_cols = [c for c in num_cols_agg if c not in int_cols]
            styled_agg = (
                agg.style
                .apply(_col_gradient, subset=num_cols_agg, axis=0)
                .format("{:.2f}", subset=float_cols, na_rep="—")
                .format("{:.0f}", subset=int_cols, na_rep="—")
            )
            st.dataframe(styled_agg, use_container_width=True, hide_index=True)

            st.markdown("---")

            # ── Evolución Oliver Load ──
            st.markdown("#### Evolución de Oliver Load (carga mecánica)")
            fig_load = px.line(
                oliver_f.sort_values("FECHA"),
                x="FECHA", y="oliver_load", color="JUGADOR",
                color_discrete_map=color_jug(oliver_f["JUGADOR"].unique()),
                title="Oliver Load por sesión",
            )
            fig_load.update_traces(hovertemplate="%{x|%d/%m/%Y}<br>%{fullData.name}: %{y:.2f}<extra></extra>")
            fig_load.update_layout(**LAYOUT, height=380)
            st.plotly_chart(fig_load, use_container_width=True)

            # ── ACWR mecánico ──
            if "acwr_mecanico" in oliver_f.columns and oliver_f["acwr_mecanico"].notna().any():
                st.markdown("#### ACWR mecánico (objetivo, desde Oliver Load)")
                fig_acwr = px.line(
                    oliver_f.sort_values("FECHA"),
                    x="FECHA", y="acwr_mecanico", color="JUGADOR",
                    color_discrete_map=color_jug(oliver_f["JUGADOR"].unique()),
                    title="ACWR calculado con carga mecánica real (no sRPE subjetivo)",
                )
                fig_acwr.add_hrect(y0=0.8, y1=1.3, fillcolor="green",  opacity=0.08, line_width=0)
                fig_acwr.add_hrect(y0=1.3, y1=1.5, fillcolor="orange", opacity=0.10, line_width=0)
                fig_acwr.add_hrect(y0=1.5, y1=3.0, fillcolor="red",    opacity=0.08, line_width=0)
                fig_acwr.update_traces(hovertemplate="%{x|%d/%m/%Y}<br>%{fullData.name}: %{y:.2f}<extra></extra>")
                fig_acwr.update_layout(**LAYOUT, height=360)
                st.plotly_chart(fig_acwr, use_container_width=True)

            st.markdown("---")

            # ── Ratio Borg/Oliver: coherencia subjetivo vs objetivo ──
            if "ratio_borg_oliver" in oliver_f.columns and oliver_f["ratio_borg_oliver"].notna().any():
                st.markdown("#### Coherencia Borg (subjetivo) vs Oliver Load (objetivo)")
                st.caption(
                    "Ratio = sRPE (Borg × min) / Oliver Load.  "
                    "Muy bajo → el jugador ha hecho mucho mecánicamente pero lo percibe poco.  "
                    "Muy alto → ha sufrido sin gran correlato mecánico (día mentalmente duro)."
                )
                fig_ratio = px.box(
                    oliver_f, x="JUGADOR", y="ratio_borg_oliver",
                    color="JUGADOR",
                    color_discrete_map=color_jug(oliver_f["JUGADOR"].unique()),
                    title="Distribución del ratio Borg/Oliver por jugador",
                )
                fig_ratio.update_traces(hovertemplate="%{y:.2f}<extra></extra>")
                fig_ratio.update_layout(**LAYOUT, height=360, showlegend=False)
                st.plotly_chart(fig_ratio, use_container_width=True)

            st.markdown("---")

            # ═══════════════════════════════════════════════════════════════
            # EVALUACIÓN AUTOMÁTICA POR JUGADOR
            # Para cada jugador del período, genera una ficha con diagnóstico
            # ═══════════════════════════════════════════════════════════════
            st.markdown("### 🩺 Evaluación informativa por jugador")
            st.caption(
                "Análisis automático del estado de cada jugador en el período seleccionado. "
                "Compara sus números con la media del equipo y con su propia historia para "
                "señalar lo relevante. **No sustituye el criterio del staff** — es una ayuda de lectura rápida."
            )

            # Referencias del equipo (medias) para comparar
            team_mean_load_sesion  = oliver_f["oliver_load"].mean()
            team_mean_dist_sesion  = oliver_f["distancia_total_m"].mean()
            team_mean_sprints      = oliver_f["sprints_count"].mean()
            team_mean_accmax       = oliver_f["acc_max_count"].mean()

            for jugador in sorted(oliver_f["JUGADOR"].unique()):
                jsub = oliver_f[oliver_f["JUGADOR"] == jugador].sort_values("FECHA")
                n_ses = int(jsub["session_id"].nunique())
                load_total = float(jsub["oliver_load"].sum())
                load_medio = float(jsub["oliver_load"].mean())
                dist_medio = float(jsub["distancia_total_m"].mean())
                sprints_medio = float(jsub["sprints_count"].mean())
                accmax_medio = float(jsub["acc_max_count"].mean())
                decmax_medio = float(jsub["dec_max_count"].mean())
                acwr_ult = jsub["acwr_mecanico"].dropna().iloc[-1] if "acwr_mecanico" in jsub.columns and jsub["acwr_mecanico"].notna().any() else None
                ratio_medio = jsub["ratio_borg_oliver"].dropna().mean() if "ratio_borg_oliver" in jsub.columns and jsub["ratio_borg_oliver"].notna().any() else None

                # Tendencia: comparar primera mitad del período vs segunda mitad
                tendencia_txt = ""
                if len(jsub) >= 4:
                    mid = len(jsub) // 2
                    load_pre = float(jsub.iloc[:mid]["oliver_load"].mean())
                    load_post = float(jsub.iloc[mid:]["oliver_load"].mean())
                    if load_pre > 0:
                        delta_pct = (load_post - load_pre) / load_pre * 100
                        if abs(delta_pct) >= 15:
                            tendencia_txt = f"tendencia {'↑ subiendo' if delta_pct > 0 else '↓ bajando'} ({delta_pct:+.0f}% entre primera y segunda mitad del período)"
                        else:
                            tendencia_txt = "tendencia estable"
                    else:
                        tendencia_txt = "tendencia indeterminable (load medio 0 en primera mitad)"

                # Comparativa con el equipo
                def _comp(val, ref, margen=0.10):
                    if ref == 0 or pd.isna(val) or pd.isna(ref):
                        return "—"
                    diff_pct = (val - ref) / ref * 100
                    if diff_pct >= margen * 100:
                        return f"por encima ({diff_pct:+.0f}%)"
                    if diff_pct <= -margen * 100:
                        return f"por debajo ({diff_pct:+.0f}%)"
                    return "en la media"

                comp_load = _comp(load_medio, team_mean_load_sesion)
                comp_dist = _comp(dist_medio, team_mean_dist_sesion)
                comp_sprints = _comp(sprints_medio, team_mean_sprints)
                comp_accmax = _comp(accmax_medio, team_mean_accmax)

                # Asimetría acc/dec
                asimetria_txt = ""
                if accmax_medio > 0:
                    asim = abs(accmax_medio - decmax_medio) / max(accmax_medio + decmax_medio, 1)
                    if asim > 0.25:
                        asimetria_txt = f"⚠️ asimetría acc/dec alta ({asim*100:.0f}%) — revisar descompensación tren inferior"

                # Alertas
                alertas = []
                if acwr_ult is not None:
                    if acwr_ult > 1.5:
                        alertas.append(f"🔴 ACWR mecánico {acwr_ult:.2f} — zona de riesgo de sobrecarga")
                    elif acwr_ult > 1.3:
                        alertas.append(f"🟠 ACWR mecánico {acwr_ult:.2f} — precaución")
                    elif acwr_ult < 0.8:
                        alertas.append(f"🔵 ACWR mecánico {acwr_ult:.2f} — infra-carga")
                if ratio_medio is not None:
                    # Ratio Borg/Oliver muy alto = sufre mentalmente más de lo que su cuerpo hace
                    # (valor de referencia depende mucho del contexto; orientativo ±50% sobre la mediana)
                    ratio_equipo = oliver_f["ratio_borg_oliver"].dropna().median()
                    if ratio_equipo and ratio_medio >= ratio_equipo * 1.5:
                        alertas.append(f"🧠 Percepción de esfuerzo elevada sin correlato mecánico (ratio {ratio_medio:.2f})")
                if asimetria_txt:
                    alertas.append(asimetria_txt)
                if not alertas:
                    alertas.append("✅ Sin alertas destacables")

                with st.expander(f"**{jugador}**  ·  {n_ses} sesiones  ·  load total {load_total:.0f}"):
                    c_a, c_b = st.columns(2)
                    with c_a:
                        st.markdown(f"""
**Medias del jugador en este período:**
- Oliver Load por sesión: **{load_medio:.0f}**  ({comp_load} vs equipo)
- Distancia por sesión: **{dist_medio:.0f} m**  ({comp_dist} vs equipo)
- Sprints por sesión: **{sprints_medio:.1f}**  ({comp_sprints} vs equipo)
- Acc. máx por sesión: **{accmax_medio:.1f}**  ({comp_accmax} vs equipo)
- Dec. máx por sesión: **{decmax_medio:.1f}**
""")
                    with c_b:
                        tendencia_line = f"- {tendencia_txt.capitalize()}" if tendencia_txt else ""
                        st.markdown(f"""
**Estado general:**
{tendencia_line}
- ACWR mecánico último: {"**"+f"{acwr_ult:.2f}"+"**" if acwr_ult is not None else "—"}
- Ratio Borg/Oliver medio: {"**"+f"{ratio_medio:.2f}"+"**" if ratio_medio is not None else "— (sin datos Borg)"}

**Alertas:**
""" + "\n".join(f"- {a}" for a in alertas))

            st.markdown("---")

            # ── Detalle expandible ──
            with st.expander("📋 Detalle sesión por sesión (tabla completa)"):
                cols_detalle = [c for c in [
                    "FECHA", "JUGADOR", "session_name", "tipo",
                    "played_time", "distancia_total_m", "distancia_hsr_m",
                    "velocidad_max_kmh", "oliver_load",
                    "acc_alta_count", "dec_alta_count", "acc_max_count", "dec_max_count",
                    "sprints_count", "cambios_direccion", "saltos", "kcal",
                    "BORG", "CARGA", "ratio_borg_oliver", "acwr_mecanico",
                ] if c in oliver_f.columns]
                detalle = oliver_f.sort_values(["FECHA", "JUGADOR"])[cols_detalle].copy()
                # Formatear decimales del detalle también
                num_cols_det = detalle.select_dtypes(include="number").columns
                styled_det = detalle.style.format("{:.2f}", subset=num_cols_det, na_rep="—")
                st.dataframe(styled_det, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8 — EJERCICIOS (timeline Oliver agregado por bloques)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ejer:
    st.markdown("### 🎯 Ejercicios del entrenamiento")
    st.caption(
        "Aquí se agrega el timeline minuto-a-minuto de Oliver en los bloques "
        "que defines en la hoja **`_EJERCICIOS`** del Sheet (nombre, tipo, "
        "minuto inicio, minuto fin). Para regenerar: `/ejercicios_sync` en el bot."
    )

    if ejercicios.empty:
        st.info(
            "Aún no hay datos de ejercicios.\n\n"
            "**Cómo empezar:**\n"
            "1. Abre la hoja `_EJERCICIOS` del Sheet.\n"
            "2. Añade filas con: `session_id`, `fecha`, `turno`, `nombre_ejercicio`, "
            "`tipo_ejercicio`, `minuto_inicio`, `minuto_fin`.\n"
            "3. En Telegram envía `/ejercicios_sync` al bot.\n\n"
            "Ver el ejemplo en la propia hoja."
        )
    else:
        ejer_f = ejercicios.copy()
        # Filtrar por jugadores seleccionados
        if "jugador" in ejer_f.columns:
            ejer_f = ejer_f[ejer_f["jugador"].isin(sel_jugadores)]

        # Redondeo defensivo
        num_cols_e = ejer_f.select_dtypes(include="number").columns
        ejer_f[num_cols_e] = ejer_f[num_cols_e].round(2)

        # ── Selector de ejercicio ──
        ejercicios_list = sorted(ejer_f["ejercicio"].dropna().unique().tolist()) if "ejercicio" in ejer_f.columns else []
        if not ejercicios_list:
            st.warning("Sin ejercicios que mostrar para los jugadores seleccionados.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                ejercicio_sel = st.selectbox(
                    "Ejercicio",
                    options=["(todos)"] + ejercicios_list,
                    index=0,
                    key="ejer_sel",
                )
            with c2:
                tipos = sorted(ejer_f["tipo_ejercicio"].dropna().unique().tolist()) if "tipo_ejercicio" in ejer_f.columns else []
                tipo_sel = st.selectbox(
                    "Tipo",
                    options=["(todos)"] + tipos,
                    index=0,
                    key="tipo_sel",
                )

            # Filtrar
            f = ejer_f.copy()
            if ejercicio_sel != "(todos)":
                f = f[f["ejercicio"] == ejercicio_sel]
            if tipo_sel != "(todos)":
                f = f[f["tipo_ejercicio"] == tipo_sel]

            if f.empty:
                st.warning("No hay datos para la combinación seleccionada.")
            else:
                # ── KPIs del ejercicio ──
                c1, c2, c3, c4, c5 = st.columns(5)
                for col, val, lbl, color in [
                    (c1, f"{f['dist_total'].mean():.0f}", "Distancia media (m)", AZUL),
                    (c2, f"{f['n_sprint'].sum():.0f}",    "Sprints totales", NARANJA),
                    (c3, f"{f['n_acc_alta_pos'].sum():.0f}", "Acc. alta+", ROJO),
                    (c4, f"{f['top_speed_kmh'].max():.1f}", "Vel. máx (km/h)", VERDE),
                    (c5, f"{f['intensity_medio'].mean():.1f}", "Intensidad media", GRIS),
                ]:
                    col.markdown(
                        f'<div class="metric-card">'
                        f'<div class="val" style="color:{color}">{val}</div>'
                        f'<div class="lbl">{lbl}</div></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("---")

                # ── Comparativa por jugador ──
                st.markdown("#### Ranking por jugador")
                st.caption(
                    "Agregado del jugador en el/los ejercicio(s) seleccionado(s). "
                    "**carga** = intensidad × duración + 5·sprints + 1·acc.alta + 0,5·dec.alta. "
                    "Métrica compuesta para resumir el esfuerzo del ejercicio en un solo número."
                )
                # Calcular CARGA por fila antes de agregar (intensity * duracion + bonificadores)
                f_carga = f.copy()
                for col in ("intensity_medio", "duracion_min", "n_sprint",
                             "n_acc_alta_pos", "n_acc_alta_neg"):
                    if col in f_carga.columns:
                        f_carga[col] = pd.to_numeric(f_carga[col], errors="coerce").fillna(0)
                    else:
                        f_carga[col] = 0
                f_carga["carga"] = (
                    f_carga["intensity_medio"] * f_carga["duracion_min"]
                    + 5.0 * f_carga["n_sprint"]
                    + 1.0 * f_carga["n_acc_alta_pos"]
                    + 0.5 * f_carga["n_acc_alta_neg"]
                ).round(1)

                rank = f_carga.groupby("jugador", as_index=False).agg(
                    carga=("carga", "sum"),
                    veces=("ejercicio", "count"),
                    duracion_total=("duracion_min", "sum"),
                    dist_total=("dist_total", "sum"),
                    dist_alta_int=("dist_high_intensity", "sum"),
                    sprints=("n_sprint", "sum"),
                    acc_alta=("n_acc_alta_pos", "sum"),
                    dec_alta=("n_acc_alta_neg", "sum"),
                    intensity=("intensity_medio", "mean"),
                    kcal=("kcal", "sum"),
                    top_speed_kmh=("top_speed_kmh", "max"),
                ).round(2).sort_values("carga", ascending=False)

                # Gradiente suave por columna
                def _grad(s: pd.Series):
                    vals = pd.to_numeric(s, errors="coerce")
                    mn, mx = vals.min(), vals.max()
                    out = []
                    for v in vals:
                        if pd.isna(v) or mx == mn:
                            out.append(""); continue
                        t = max(0, min(1, (v - mn)/(mx - mn)))
                        if t < 0.5:
                            r, g, b = 255, int(170 + 70*t*2), int(170 + 20*t*2)
                        else:
                            r = int(255 - 85*(t-0.5)*2); g = int(240 - 15*(t-0.5)*2); b = int(190 - 20*(t-0.5)*2)
                        out.append(f"background-color: rgb({r},{g},{b})")
                    return out

                cols_num = [c for c in rank.columns if c != "jugador"]
                styled = (
                    rank.style
                    .apply(_grad, subset=cols_num, axis=0)
                    .format("{:.2f}", subset=cols_num, na_rep="—")
                )
                st.dataframe(styled, use_container_width=True, hide_index=True)

                st.markdown("---")

                # ── Si hay múltiples ejercicios, comparativa ──
                if ejercicio_sel == "(todos)":
                    st.markdown("#### Comparativa entre ejercicios (media del equipo)")
                    comp = f.groupby(["ejercicio", "tipo_ejercicio"], as_index=False).agg(
                        duracion_min=("duracion_min", "first"),
                        dist_total_media=("dist_total", "mean"),
                        intensity_media=("intensity_medio", "mean"),
                        sprints_total=("n_sprint", "sum"),
                        acc_alta_total=("n_acc_alta_pos", "sum"),
                    ).round(2)

                    fig = px.bar(
                        comp.sort_values("intensity_media", ascending=False),
                        x="ejercicio", y="intensity_media",
                        color="tipo_ejercicio",
                        title="Intensidad media por ejercicio",
                        hover_data=["duracion_min", "dist_total_media", "sprints_total"],
                    )
                    fig.update_layout(**LAYOUT, height=360)
                    st.plotly_chart(fig, use_container_width=True)

                # ── Detalle expandible ──
                with st.expander("📋 Detalle por jugador y ejercicio"):
                    cols_show = [c for c in [
                        "fecha", "turno", "ejercicio", "tipo_ejercicio", "jugador",
                        "minuto_inicio", "minuto_fin", "duracion_min",
                        "dist_total", "dist_high_intensity", "top_speed_kmh",
                        "n_sprint", "n_acc_alta_pos", "n_acc_alta_neg",
                        "intensity_medio", "kcal",
                    ] if c in f.columns]
                    det = f.sort_values(["fecha", "ejercicio", "jugador"])[cols_show]
                    num_det = det.select_dtypes(include="number").columns
                    st.dataframe(
                        det.style.format("{:.2f}", subset=num_det, na_rep="—"),
                        use_container_width=True, hide_index=True,
                    )

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers compartidos para las pestañas de estadísticas
# ═══════════════════════════════════════════════════════════════════════════════
_EST_METRICAS_NUM = [
    "min_total", "min_1t", "min_2t", "dorsal",
    "pf", "pnf", "robos", "cortes", "bdg", "bdp",
    "dp", "dpalo", "db", "df", "out",
    "poste_p", "bloq_p", "par", "gol_p",
    "ta", "tr",                   # tarjetas (TR añadido iter3)
    "salida", "salida_fallida",   # portería (iter3)
    "goles_a_favor", "asistencias",
]


def _est_num(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for c in _EST_METRICAS_NUM:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    if "participa" in out.columns:
        out["participa"] = out["participa"].astype(str).map(
            lambda v: 1 if v in ("1", "True", "true") else 0
        )
    if "convocado" in out.columns:
        out["convocado"] = out["convocado"].astype(str).map(
            lambda v: 1 if v in ("1", "True", "true") else 0
        )
    return out


def _fmt_minutos(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    # `float(NaN)` no revienta pero deja NaN, que luego rompe int(v).
    # Comparaciones con NaN devuelven False, así que `v <= 0` no filtra NaN.
    if pd.isna(v) or v <= 0:
        return "—"
    m = int(v)
    s = int(round((v - m) * 60))
    return f"{m}:{s:02d}"


# ── Tooltips por columna (st.column_config) ───────────────────────────────────
TOOLTIPS_COLS = {
    # Identificación
    "jugador": "Jugador (nombre canónico)",
    "dorsal": "Número de dorsal",
    "Nº": "Número de dorsal",
    "Jugador": "Jugador",
    "partido_id": "Identificador del partido (pestaña del Excel original)",
    "rival": "Equipo rival",
    "fecha": "Fecha del partido (YYYY-MM-DD)",
    "tipo": "Tipo de competición",
    "competicion": "Competición legible",
    # Minutos
    "min_total": "Minutos totales jugados (1ª + 2ª parte)",
    "min_1t": "Minutos jugados en la 1ª parte",
    "min_2t": "Minutos jugados en la 2ª parte",
    "min_partido": "Media de minutos por partido jugado",
    "min_por_partido": "Media de minutos por partido jugado",
    "1ª parte": "Minutos jugados en la 1ª parte (mm:ss)",
    "2ª parte": "Minutos jugados en la 2ª parte (mm:ss)",
    "Total": "Total minutos jugados (mm:ss)",
    "partidos": "Partidos jugados",
    "partidos_conv": "Partidos convocado (apareció en la lista del partido)",
    "partidos_jug": "Partidos jugados (con minutos > 0)",
    "partidos_convocado": "Partidos convocado",
    "partidos_jugados": "Partidos jugados",
    "convocatorias": "Veces convocado para partido",
    "participa": "Veces que participó (jugó al menos 1 minuto)",
    # Métricas individuales
    "pf": "Pérdidas Forzadas (el rival te roba la pelota presionando)",
    "pnf": "Pérdidas No Forzadas (la pelota se pierde por error propio)",
    "PF": "Pérdidas Forzadas",
    "PNF": "Pérdidas No Forzadas",
    "robos": "Robos de balón al rival",
    "Robos": "Robos de balón al rival",
    "cortes": "Cortes (interceptación de pase rival)",
    "Cortes": "Cortes (interceptación de pase rival)",
    "bdg": "Balón Dividido Ganado (50-50 que ganas)",
    "bdp": "Balón Dividido Perdido",
    "BDG": "Balón Dividido Ganado",
    "BDP": "Balón Dividido Perdido",
    "dif_rec_per": "Diferencia recuperaciones - pérdidas (robos+cortes - PF-PNF)",
    "dif_bd": "Diferencia balones divididos (BDG - BDP)",
    # Disparos
    "dp": "Disparos a Puerta",
    "dpalo": "Disparos al Palo",
    "db": "Disparos Bloqueados (defensa rival los corta)",
    "df": "Disparos Fuera",
    "dt": "Disparos Totales (DP + DPalo + DB + DF)",
    "DP": "Disparos a Puerta",
    "DPalo": "Disparos al Palo",
    "DB": "Disparos Bloqueados",
    "DF": "Disparos Fuera",
    "DT": "Disparos Totales",
    "pct_dp_total": "% disparos que van a puerta (DP / DT)",
    "pct_a_puerta": "% disparos que van a puerta (DP / DT)",
    "pct_conversion": "% conversión (goles / disparos a puerta)",
    "dp_por_40": "Disparos a puerta por cada 40 minutos jugados (un partido completo)",
    "dt_por_40": "Disparos totales por 40 minutos",
    # Goles
    "goles": "Goles a favor marcados",
    "Goles": "Goles a favor",
    "asists": "Asistencias",
    "asistencias": "Asistencias",
    "Asists": "Asistencias",
    "g+a": "Goles + Asistencias",
    "G+A": "Goles + Asistencias",
    "goles_a_favor": "Goles a favor",
    "goles_en_contra": "Goles en contra",
    "gf_pista": "Goles a favor cuando este jugador estaba en pista",
    "gc_pista": "Goles en contra cuando este jugador estaba en pista",
    "gf_en_pista": "Goles a favor cuando este jugador estaba en pista",
    "gc_en_pista": "Goles en contra cuando este jugador estaba en pista",
    "plus_minus": "Plus/Minus: GF en pista − GC en pista (cuanto mejor le va al equipo con él)",
    "plus_minus_por_40": "Plus/Minus por cada 40 minutos jugados",
    # Por minuto
    "robos/min": "Robos por minuto jugado",
    "cortes/min": "Cortes por minuto jugado",
    "pf/min": "Pérdidas forzadas por minuto",
    "pnf/min": "Pérdidas no forzadas por minuto",
    "dp/min": "Disparos a puerta por minuto",
    "goles/min": "Goles por minuto jugado",
    # Por 40 minutos
    "goles/40": "Goles por cada 40 minutos jugados (un partido completo)",
    "asists/40": "Asistencias por 40 minutos",
    "g+a/40": "Goles + Asistencias por 40 minutos",
    "goles_por_40": "Goles por 40 minutos",
    "asists_por_40": "Asistencias por 40 minutos",
    "g+a_por_40": "G+A por 40 minutos",
    # % vs equipo
    "%_min_eq": "% de los minutos del equipo jugados por este jugador",
    "%_goles_eq": "% de los goles del equipo metidos por este jugador",
    "%_asists_eq": "% de las asistencias del equipo dadas por este jugador",
    "%_robos_eq": "% de los robos del equipo hechos por este jugador",
    "%_dp_eq": "% de los disparos a puerta del equipo hechos por este jugador",
    "pct_minutos_equipo": "% minutos del equipo",
    "pct_goles_equipo": "% goles del equipo",
    "pct_asists_equipo": "% asistencias del equipo",
    # Eventos / cuartetos / goles
    "minuto": "Minuto del partido en que sucedió el evento (1-40)",
    "marcador": "Marcador acumulado tras el gol",
    "accion": "Tipo de acción de gol (Banda, Córner, 4x4, Contraataque, etc.)",
    "Acción": "Tipo de acción de gol",
    "goleador": "Jugador que marcó",
    "Goleador": "Jugador que marcó",
    "asistente": "Jugador que dio la asistencia",
    "Asistente": "Jugador que dio la asistencia",
    "portero": "Portero que estaba en pista en ese momento",
    "Portero": "Portero en pista",
    "cuarteto": "Jugadores de campo en pista (3-5 separados por |)",
    "Cuarteto": "Jugadores de campo en pista",
    "equipo_marca": "Equipo que marcó (INTER o RIVAL)",
    "Equipo": "Equipo que marcó",
    "intervalo_5min": "Intervalo de 5 minutos donde cae el gol (0-5, 5-10, ...)",
    "Min": "Minuto del partido",
    "Marcador": "Marcador acumulado",
    "descripcion": "Descripción libre del gol (la rellenas tú a mano en el Sheet)",
    "Descripción": "Descripción libre del gol",
    # Cuartetos
    "formacion": "Combinación de jugadores en pista",
    "n_eventos": "Veces que esta combinación estuvo en pista cuando se marcó un gol (a favor o en contra)",
    # Disparos por partido
    "disparos_a_favor": "Disparos a favor del Inter en el partido",
    "disparos_en_contra": "Disparos en contra del Inter (del rival)",
    "ratio_a_favor": "Disparos por gol a favor (cuanto menor, más eficiente)",
    "ratio_en_contra": "Disparos por gol en contra (del rival, cuanto mayor, mejor defensa)",
    "minutos_jugados": "Minutos del partido (40 normalmente)",
}


def _coltype_help(col_name: str, df: pd.DataFrame):
    """Devuelve un dict {col: column_config} con el tooltip y formato auto-detectado."""
    cfg = {}
    for c in df.columns:
        help_txt = TOOLTIPS_COLS.get(c) or TOOLTIPS_COLS.get(c.lower())
        if help_txt:
            cfg[c] = st.column_config.Column(help=help_txt)
    return cfg


def _gradiente_sutil(styler, columnas, df_subset=None):
    """Aplica gradiente sutil RdYlGn por columna independiente.
    `df_subset` permite calcular el gradiente solo sobre un subconjunto
    (p. ej. excluyendo porteros para el ranking de minutos)."""
    cmap_suave = "RdYlGn"  # rojo-amarillo-verde, suave es más subjetivo, ajustamos vmin/vmax
    for c in columnas:
        if c not in styler.data.columns:
            continue
        try:
            base = pd.to_numeric(
                (df_subset[c] if df_subset is not None else styler.data[c]),
                errors="coerce"
            )
            if base.dropna().empty:
                continue
            vmin = base.min()
            vmax = base.max()
            if vmin == vmax:
                continue
            styler = styler.background_gradient(
                subset=[c], cmap=cmap_suave, vmin=vmin, vmax=vmax,
            )
        except Exception:
            continue
    return styler


def _ensure_numeric(df: pd.DataFrame, num_cols: list) -> pd.DataFrame:
    """Convierte a float las columnas listadas. Imprescindible antes de pasar
    a styler.format con specifiers numéricos: con Python 3.14 + pandas 3.x,
    formatear un string '37' como '{:.0f}' rompe."""
    if df.empty:
        return df
    out = df.copy()
    for c in num_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _color_gradient_rgb(t: float) -> str:
    """t en [0,1] → CSS background-color RdYlGn (0=rojo, 0.5=amarillo, 1=verde)."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        # rojo a amarillo
        r, g, b = 255, int(165 + 90 * (t * 2)), 100
    else:
        # amarillo a verde
        r = int(255 - 145 * ((t - 0.5) * 2))
        g = int(255 - 50 * ((t - 0.5) * 2))
        b = 100
    return f"background-color: rgb({r},{g},{b}); color: black;"


def _color_gradient_inverso(t: float) -> str:
    """Como _color_gradient_rgb pero invertido (0=verde, 1=rojo)."""
    return _color_gradient_rgb(1 - t)


def _aplicar_gradient_columna(df: pd.DataFrame, col: str,
                               filas_excluidas: list = None,
                               invertir: bool = False) -> pd.Series:
    """Devuelve una Series con el style CSS por celda de `col`.

    Las filas en `filas_excluidas` (índices) salen en blanco.
    Si `invertir=True`, valores ALTOS son rojos (vs default ALTOS = verdes).
    """
    if filas_excluidas is None:
        filas_excluidas = []
    base = pd.to_numeric(df[col], errors="coerce")
    base_validos = base.drop(filas_excluidas, errors="ignore").dropna()
    if base_validos.empty:
        return pd.Series([""] * len(df), index=df.index)
    vmin = float(base_validos.min())
    vmax = float(base_validos.max())
    out = []
    for idx, v in base.items():
        if idx in filas_excluidas:
            out.append("background-color: #f5f5f5; color: #666;")
            continue
        if pd.isna(v) or vmin == vmax:
            out.append("")
            continue
        t = (v - vmin) / (vmax - vmin)
        out.append(_color_gradient_inverso(t) if invertir else _color_gradient_rgb(t))
    return pd.Series(out, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════════
# Mapas SVG: campo (11 zonas) y portería (9 cuadrantes)
# ═══════════════════════════════════════════════════════════════════════════════
def _color_zona(valor: int, max_v: int) -> str:
    """Color de relleno para una zona según valor / max."""
    if max_v <= 0 or valor <= 0:
        return "#f5f5f5"  # gris muy claro
    t = max(0.0, min(1.0, valor / max_v))
    if t < 0.5:
        r = 255
        g = int(220 - 50 * (t * 2))
        b = 180
    else:
        r = int(255 - 100 * ((t - 0.5) * 2))
        g = int(170 - 130 * ((t - 0.5) * 2))
        b = int(80 - 30 * ((t - 0.5) * 2))
    return f"rgb({r},{g},{b})"


def _texto_zona(zona: str, valor: int, x: float, y: float) -> str:
    """SVG text del valor (sin etiqueta de zona) centrado en (x, y).
    Etiqueta de zona disponible en tooltip via <title>."""
    return (
        f'<text x="{x}" y="{y + 8}" text-anchor="middle" '
        f'font-size="32" font-weight="800" fill="#000" '
        f'style="pointer-events:none">'
        f'<title>{zona}</title>{valor}</text>'
    )


def generar_svg_campo(zonas: dict, titulo: str = "") -> str:
    """Genera un SVG del campo de futsal con las 11 zonas coloreadas.

    Mejoras: líneas externas marcadas (banda + fondo + medio), círculo
    central, área grande + área pequeña visibles, líneas internas de
    zonas en discontinuas, portería de 3m con franjas rojas/blancas.

    Geometría (1m = 25px → 40m × 20m = 1000 × 500). Mitad atacante 0-500.
    """
    z = {k: int(v) if v else 0 for k, v in (zonas or {}).items()}
    max_v = max(z.values()) if z else 1
    max_v = max(max_v, 1)

    def col(zk):
        return _color_zona(z.get(zk, 0), max_v)

    BORDE = "#1B5E20"   # verde oscuro (línea perimetral)
    SUBLINEA = "#1B5E20"  # también para áreas
    DASH = "4 4"         # patrón de líneas discontinuas (zonas)

    parts = [
        '<svg width="100%" viewBox="-40 -10 1080 530" xmlns="http://www.w3.org/2000/svg" '
        'style="background:#A5D6A7; border-radius:8px;">',
    ]

    # ── Zonas con relleno (capa de color) ─────────────────────────────────
    # A11 (mitad rival)
    parts.append(f'<rect x="500" y="0" width="500" height="500" fill="{col("A11")}"/>')
    parts.append(_texto_zona("A11", z.get("A11", 0), 750, 250))

    # A6, A10, A7, A3, A9, A8 (rectangulares)
    parts.append(f'<rect x="0" y="0" width="250" height="62.5" fill="{col("A6")}"/>')
    parts.append(_texto_zona("A6", z.get("A6", 0), 125, 31))
    parts.append(f'<rect x="0" y="437.5" width="250" height="62.5" fill="{col("A3")}"/>')
    parts.append(_texto_zona("A3", z.get("A3", 0), 125, 469))
    parts.append(f'<rect x="250" y="0" width="250" height="62.5" fill="{col("A10")}"/>')
    parts.append(_texto_zona("A10", z.get("A10", 0), 375, 31))
    parts.append(f'<rect x="250" y="437.5" width="250" height="62.5" fill="{col("A7")}"/>')
    parts.append(_texto_zona("A7", z.get("A7", 0), 375, 469))
    parts.append(f'<rect x="250" y="62.5" width="250" height="187.5" fill="{col("A9")}"/>')
    parts.append(_texto_zona("A9", z.get("A9", 0), 375, 156))
    parts.append(f'<rect x="250" y="250" width="250" height="187.5" fill="{col("A8")}"/>')
    parts.append(_texto_zona("A8", z.get("A8", 0), 375, 343))

    # A5 / A4 (lado externo del área grande)
    parts.append(
        f'<path d="M 0,62.5 L 250,62.5 L 250,250 L 150,250 L 150,212.5 '
        f'A 150,150 0 0,0 0,62.5 Z" fill="{col("A5")}"/>'
    )
    parts.append(_texto_zona("A5", z.get("A5", 0), 200, 156))
    parts.append(
        f'<path d="M 0,437.5 L 250,437.5 L 250,250 L 150,250 L 150,287.5 '
        f'A 150,150 0 0,0 0,437.5 Z" fill="{col("A4")}"/>'
    )
    parts.append(_texto_zona("A4", z.get("A4", 0), 200, 343))

    # A2 / A1 (mitades del área grande)
    parts.append(
        f'<path d="M 0,62.5 A 150,150 0 0,1 150,212.5 L 150,250 L 0,250 Z" '
        f'fill="{col("A2")}"/>'
    )
    parts.append(_texto_zona("A2", z.get("A2", 0), 60, 175))
    parts.append(
        f'<path d="M 0,250 L 150,250 L 150,287.5 A 150,150 0 0,1 0,437.5 Z" '
        f'fill="{col("A1")}"/>'
    )
    parts.append(_texto_zona("A1", z.get("A1", 0), 60, 325))

    # ── Líneas de zona (discontinuas, encima del relleno) ─────────────────
    # Verticales: x=250 (10m) y entre A11 y mitad atacante
    parts.append(f'<line x1="250" y1="0" x2="250" y2="500" stroke="{SUBLINEA}" '
                 f'stroke-width="1.5" stroke-dasharray="{DASH}"/>')
    # Horizontales: y=62.5 (banda sup zona), y=437.5 (banda inf zona)
    parts.append(f'<line x1="0" y1="62.5" x2="500" y2="62.5" stroke="{SUBLINEA}" '
                 f'stroke-width="1.5" stroke-dasharray="{DASH}"/>')
    parts.append(f'<line x1="0" y1="437.5" x2="500" y2="437.5" stroke="{SUBLINEA}" '
                 f'stroke-width="1.5" stroke-dasharray="{DASH}"/>')
    # Línea horizontal del medio del área (y=250) entre x=150 y x=500
    parts.append(f'<line x1="0" y1="250" x2="500" y2="250" stroke="{SUBLINEA}" '
                 f'stroke-width="1.5" stroke-dasharray="{DASH}"/>')

    # ── Líneas oficiales del campo (continuas, marcadas) ──────────────────
    # Perímetro
    parts.append(f'<rect x="0" y="0" width="1000" height="500" fill="none" '
                 f'stroke="{BORDE}" stroke-width="3"/>')
    # Línea media (vertical x=500)
    parts.append(f'<line x1="500" y1="0" x2="500" y2="500" stroke="{BORDE}" stroke-width="3"/>')
    # Círculo central (radio 3m = 75px)
    parts.append(f'<circle cx="500" cy="250" r="75" fill="none" stroke="{BORDE}" stroke-width="2"/>')
    parts.append(f'<circle cx="500" cy="250" r="3" fill="{BORDE}"/>')
    # Círculo central simétrico (la otra mitad lo tiene también, no lo dibujo extra)

    # Área GRANDE: cuarto de círculo de 6m=150px desde cada poste + línea paralela
    # Postes en (0, 212.5) y (0, 287.5). Cuarto sup: (0,62.5) → arco → (150,212.5)
    # → línea hasta (150, 287.5) → arco → (0, 437.5)
    parts.append(
        f'<path d="M 0,62.5 A 150,150 0 0,1 150,212.5 L 150,287.5 '
        f'A 150,150 0 0,1 0,437.5" fill="none" stroke="{BORDE}" stroke-width="2"/>'
    )
    # Área PEQUEÑA: rectángulo desde (0, 237.5) a (60, 262.5)? — En futsal NO hay
    # área pequeña, solo el área grande y el punto de penalti. Dibujo el punto:
    # 6m punto penalti desde la línea de fondo, en el centro de la portería
    parts.append(f'<circle cx="150" cy="250" r="3" fill="{BORDE}"/>')
    # Punto de doble penalti (10m)
    parts.append(f'<circle cx="250" cy="250" r="3" fill="{BORDE}"/>')

    # ── Portería: 3m × 2m. Postes con franjas rojas y blancas ────────────
    # En el SVG: la portería se dibuja "fuera" del campo (x<0) para que no
    # tape A1/A2. Lateral del poste apunta al campo. Tres elementos:
    # poste izquierdo (vertical), poste derecho (vertical), larguero (horizontal).
    # Pero como vemos el campo desde arriba, los dos "postes" son los extremos
    # del segmento de portería y el "larguero" no se ve (es la unión visual).
    # Para que se vean como en la realidad (3 postes), dibujo:
    #   - Poste superior (extremo arriba): segmento corto desde fuera
    #   - Poste inferior: segmento corto desde fuera
    #   - Larguero virtual: la barra que une los dos postes, sale fuera del campo
    # Color: alternancia roja y blanca.
    # Coordenadas: poste sup en (0, 212.5), poste inf en (0, 287.5)
    POSTE_LARGO = 32   # px que sobresale "hacia fuera" del campo
    GROSOR = 8
    # Larguero (vertical line conectando ambos postes), ahí dibujamos franjas
    # alternadas como una bandera de portería.
    n_franjas = 5
    franja_h = 75 / n_franjas
    for i in range(n_franjas):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        parts.append(f'<rect x="-{GROSOR}" y="{212.5 + i * franja_h}" '
                     f'width="{GROSOR}" height="{franja_h}" '
                     f'fill="{c}" stroke="#7F1010" stroke-width="0.5"/>')
    # Poste superior (saliendo hacia "atrás" izquierda)
    parts.append(f'<rect x="-{POSTE_LARGO}" y="{212.5 - GROSOR/2}" '
                 f'width="{POSTE_LARGO}" height="{GROSOR}" '
                 f'fill="#B71C1C" stroke="#7F1010" stroke-width="0.5"/>')
    # Poste inferior
    parts.append(f'<rect x="-{POSTE_LARGO}" y="{287.5 - GROSOR/2}" '
                 f'width="{POSTE_LARGO}" height="{GROSOR}" '
                 f'fill="#B71C1C" stroke="#7F1010" stroke-width="0.5"/>')
    # Cierre trasero (línea de fondo de la portería)
    parts.append(f'<rect x="-{POSTE_LARGO}" y="{212.5}" width="{GROSOR/2}" '
                 f'height="75" fill="#FFFFFF" stroke="#999" stroke-width="0.5"/>')

    if titulo:
        parts.append(f'<text x="500" y="-15" text-anchor="middle" font-size="13" '
                     f'font-weight="600" fill="#1B3A6B">{titulo}</text>')

    parts.append('</svg>')
    return "".join(parts)


def generar_svg_porteria(cuadrantes: dict, titulo: str = "") -> str:
    """SVG de la portería 3m×2m con cuadrícula 3×3 (P1-P9) coloreada.
    Postes y larguero con franjas rojas y blancas estilo portería real."""
    p = {k: int(v) if v else 0 for k, v in (cuadrantes or {}).items()}
    max_v = max(p.values()) if p else 1
    max_v = max(max_v, 1)

    # Escala 1m = 100px. Portería 3×2m → 300×200px. Postes con grosor.
    POSTE = 14         # grosor de los postes (px)
    SVG_W, SVG_H = 360, 250
    POSX = 30          # margen izquierdo donde empieza el poste izq
    POSY = 18          # margen superior donde empieza el larguero
    PORT_W = 300       # ancho útil del campo de la portería
    PORT_H = 200       # alto útil
    parts = [
        f'<svg width="100%" viewBox="0 0 {SVG_W} {SVG_H}" xmlns="http://www.w3.org/2000/svg" '
        'style="background:#FFFFFF; border-radius:8px;">',
    ]
    # Fondo de la portería (rejilla simulada)
    parts.append(f'<rect x="{POSX}" y="{POSY}" width="{PORT_W}" height="{PORT_H}" '
                 f'fill="#FAFAFA"/>')
    # Líneas finas de red (decorativas)
    for i in range(1, 6):
        x = POSX + i * (PORT_W / 6)
        parts.append(f'<line x1="{x}" y1="{POSY}" x2="{x}" y2="{POSY + PORT_H}" '
                     f'stroke="#E0E0E0" stroke-width="0.5"/>')
    for i in range(1, 4):
        y = POSY + i * (PORT_H / 4)
        parts.append(f'<line x1="{POSX}" y1="{y}" x2="{POSX + PORT_W}" y2="{y}" '
                     f'stroke="#E0E0E0" stroke-width="0.5"/>')

    # 9 cuadrantes (con valores y color)
    cuad_w = PORT_W / 3
    cuad_h = PORT_H / 3
    for i in range(9):
        col_idx = i % 3
        row_idx = i // 3
        x = POSX + col_idx * cuad_w
        y = POSY + row_idx * cuad_h
        zona = f"P{i+1}"
        v = p.get(zona, 0)
        color = _color_zona(v, max_v)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cuad_w}" height="{cuad_h}" '
            f'fill="{color}" fill-opacity="0.85" stroke="#888" '
            f'stroke-width="0.8" stroke-dasharray="3 2"/>'
        )
        parts.append(_texto_zona(zona, v, x + cuad_w/2, y + cuad_h/2))

    # Postes con franjas rojas y blancas alternas
    n_v = 6  # franjas verticales (en postes)
    fv_h = PORT_H / n_v
    for i in range(n_v):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        # Poste izquierdo
        parts.append(f'<rect x="{POSX - POSTE}" y="{POSY + i * fv_h}" '
                     f'width="{POSTE}" height="{fv_h}" fill="{c}" stroke="#7F1010" stroke-width="0.5"/>')
        # Poste derecho
        parts.append(f'<rect x="{POSX + PORT_W}" y="{POSY + i * fv_h}" '
                     f'width="{POSTE}" height="{fv_h}" fill="{c}" stroke="#7F1010" stroke-width="0.5"/>')

    # Larguero (franjas horizontales)
    n_h = 8
    fh_w = PORT_W / n_h
    for i in range(n_h):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        parts.append(f'<rect x="{POSX + i * fh_w}" y="{POSY - POSTE}" '
                     f'width="{fh_w}" height="{POSTE}" fill="{c}" stroke="#7F1010" stroke-width="0.5"/>')

    # Línea de campo bajo la portería
    parts.append(f'<line x1="{POSX - POSTE - 10}" y1="{POSY + PORT_H + 4}" '
                 f'x2="{POSX + PORT_W + POSTE + 10}" y2="{POSY + PORT_H + 4}" '
                 f'stroke="#1B5E20" stroke-width="2"/>')

    if titulo:
        parts.append(f'<text x="{SVG_W/2}" y="{SVG_H - 8}" text-anchor="middle" '
                     f'font-size="12" font-weight="600" fill="#1B3A6B">{titulo}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 10 — 📈 EFICIENCIA (disparos, ratios, métricas avanzadas)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_efic:
    try:
        if est_avanz.empty and est_disparos.empty:
            st.info(
                "Aún no hay métricas avanzadas. Ejecuta:\n\n"
                "`/usr/bin/python3 src/estadisticas_disparos.py --upload`\n\n"
                "`/usr/bin/python3 src/estadisticas_avanzadas.py --upload`"
            )
        else:
            st.markdown("### 📈 Eficiencia y métricas avanzadas")
            st.caption(
                "Métricas normalizadas por 40 minutos (un partido completo), "
                "porcentajes sobre el equipo, +/-, y disparos por partido."
            )
    
            # ── KPIs de equipo (de disparos) ──
            if not est_disparos.empty:
                d = est_disparos.copy()
                for c in ("disparos_a_favor","disparos_en_contra","goles_a_favor","goles_en_contra","minutos_jugados"):
                    if c in d.columns:
                        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
                tot_disp_af = int(d["disparos_a_favor"].sum())
                tot_disp_ec = int(d["disparos_en_contra"].sum())
                tot_gol_af = int(d["goles_a_favor"].sum())
                tot_gol_ec = int(d["goles_en_contra"].sum())
                ratio_af = tot_disp_af / max(tot_gol_af, 1)
                ratio_ec = tot_disp_ec / max(tot_gol_ec, 1)
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Disparos a favor", f"{tot_disp_af:,}".replace(",", "."), f"{tot_gol_af} goles")
                k2.metric("Disparos en contra", f"{tot_disp_ec:,}".replace(",", "."), f"{tot_gol_ec} goles")
                k3.metric("Disparos / gol (Inter)", f"{ratio_af:.1f}")
                k4.metric("Disparos / gol (rival)", f"{ratio_ec:.1f}")
    
            st.markdown("---")
    
            # ── Ranking jugadores normalizado ──
            if not est_avanz.empty:
                st.markdown("#### Ranking por jugador (normalizado por 40')")
                a = est_avanz.copy()
                for c in a.columns:
                    if c == "jugador":
                        continue
                    a[c] = pd.to_numeric(a[c], errors="coerce")
                cols_show = [c for c in [
                    "jugador", "partidos_jugados", "min_total",
                    "goles", "asists", "g+a",
                    "goles_por_40", "asists_por_40", "g+a_por_40",
                    "pct_goles_equipo", "pct_asists_equipo", "pct_minutos_equipo",
                    "plus_minus", "plus_minus_por_40",
                ] if c in a.columns]
                df_a = _ensure_numeric(a[cols_show], [c for c in cols_show if c != "jugador"])
                st.dataframe(
                    df_a.style.format({
                        "min_total": "{:.0f}",
                        "goles": "{:.0f}", "asists": "{:.0f}", "g+a": "{:.0f}",
                        "partidos_jugados": "{:.0f}",
                        "goles_por_40": "{:.2f}", "asists_por_40": "{:.2f}", "g+a_por_40": "{:.2f}",
                        "pct_goles_equipo": "{:.1f}%", "pct_asists_equipo": "{:.1f}%",
                        "pct_minutos_equipo": "{:.1f}%",
                        "plus_minus": "{:+.0f}", "plus_minus_por_40": "{:+.2f}",
                    }, na_rep="—").background_gradient(
                        subset=[c for c in ["g+a_por_40", "plus_minus", "plus_minus_por_40"] if c in cols_show],
                        cmap="RdYlGn", vmin=None, vmax=None,
                    ),
                    use_container_width=True, hide_index=True,
                )
    
                # ── Pie de % goles del equipo ──
                st.markdown("#### Reparto de goles del equipo (% por jugador)")
                try:
                    import altair as alt
                    pie_data = a[["jugador", "pct_goles_equipo"]].copy()
                    pie_data = pie_data[pie_data["pct_goles_equipo"] > 0]
                    if not pie_data.empty:
                        ch = (alt.Chart(pie_data)
                              .mark_arc(innerRadius=60)
                              .encode(
                                  theta="pct_goles_equipo:Q",
                                  color=alt.Color("jugador:N", legend=alt.Legend(title="Jugador")),
                                  tooltip=["jugador", alt.Tooltip("pct_goles_equipo:Q", format=".1f")],
                              ).properties(height=350))
                        st.altair_chart(ch, use_container_width=True)
                except Exception:
                    pass
    
            st.markdown("---")
    
            # ── Combinaciones efectivas (tríos / cuartetos / quintetos) ─────────
            if not est_eventos.empty:
                st.markdown("#### 🏅 Combinaciones más efectivas")
                st.caption("Filtra por tamaño y elige incluir o no al portero.")
    
                ce1, ce2 = st.columns([2, 2])
                tamanos_e = ce1.multiselect(
                    "Tamaño combinación", [3, 4, 5], default=[4, 5], key="efic_cuart_tam",
                    help="3 = trío, 4 = cuarteto, 5 = quinteto."
                )
                inc_p_e = ce2.radio(
                    "Incluir portero", ["Sí", "No"], horizontal=True, key="efic_cuart_port"
                )
    
                # Generar TODAS las combinaciones de tamaño N para cada evento.
                # Lógica:
                # - "Incluir portero = Sí": solo eventos con portero canónico
                #   (J.GARCIA / J.HERRERO / OSCAR), y cada combinación generada
                #   debe contener al portero (filtrado al final).
                # - "Incluir portero = No": solo jugadores de campo, ignoramos
                #   el portero. Sirve también para situaciones de portero-jugador
                #   donde no hay portero (5 de campo).
                from itertools import combinations as _combos_e
                _PORTEROS_CANON = {"J.HERRERO", "J.GARCIA", "OSCAR", "HERRERO", "GARCIA"}
                ev_q = est_eventos.copy()
                ev_q["portero"] = ev_q["portero"].fillna("").astype(str)
                ev_q["cuarteto"] = ev_q["cuarteto"].fillna("").astype(str)
                incl = (inc_p_e == "Sí")

                regs_e = []
                for _, r in ev_q.iterrows():
                    cuart = list(filter(None, r["cuarteto"].split("|")))
                    portero_ev = r["portero"].strip().upper() if r["portero"] else ""
                    portero_valido = portero_ev in _PORTEROS_CANON

                    if incl:
                        # Solo eventos con portero canónico
                        if not portero_valido:
                            continue
                        pool = sorted(set(cuart + [portero_ev]))
                    else:
                        pool = sorted(set(cuart))
                    em = r["equipo_marca"]
                    for n in tamanos_e or [3, 4, 5]:
                        if n <= len(pool):
                            for combo in _combos_e(pool, n):
                                # Si "incluir portero", la combinación DEBE
                                # contener al portero (sino es solo de campo).
                                if incl and portero_ev not in combo:
                                    continue
                                regs_e.append({
                                    "formacion": " | ".join(combo),
                                    "tamano": n,
                                    "equipo_marca": em,
                                })
                if not regs_e:
                    st.warning("Sin combinaciones para los filtros aplicados.")
                else:
                    df_regs_e = pd.DataFrame(regs_e)
                    agr_q_e = df_regs_e.groupby(["formacion", "tamano"], as_index=False).agg(
                        n_eventos=("formacion", "count"),
                        goles_a_favor=("equipo_marca", lambda s: (s == "INTER").sum()),
                        goles_en_contra=("equipo_marca", lambda s: (s == "RIVAL").sum()),
                    )
                    agr_q_e["plus_minus"] = agr_q_e["goles_a_favor"] - agr_q_e["goles_en_contra"]
                    agr_q_e = agr_q_e.sort_values(["plus_minus", "n_eventos"],
                                                  ascending=[False, False]).head(15)
                    sty_qe = agr_q_e.style.format({
                        "tamano": "{:.0f}", "n_eventos": "{:.0f}",
                        "goles_a_favor": "{:.0f}", "goles_en_contra": "{:.0f}",
                        "plus_minus": "{:+.0f}",
                    })
                    if "plus_minus" in agr_q_e.columns:
                        css_pm_e = _aplicar_gradient_columna(agr_q_e, "plus_minus")
                        sty_qe = sty_qe.apply(
                            lambda s: css_pm_e.reindex(s.index, fill_value="").tolist(),
                            subset=["plus_minus"], axis=0,
                        )
                    st.dataframe(sty_qe, use_container_width=True, hide_index=True)
    
            st.markdown("---")
    
            # ── Tabla de disparos por partido (2 decimales) ──
            if not est_disparos.empty:
                st.markdown("#### Disparos por partido")
                comp_op = ["TODAS"] + sorted(est_disparos["competicion"].dropna().unique().tolist())
                sel_c = st.selectbox("Competición", comp_op, key="efic_comp")
                df_show = est_disparos.copy()
                if sel_c != "TODAS":
                    df_show = df_show[df_show["competicion"] == sel_c]
                cols_dis = ["competicion","rival","fecha","disparos_a_favor","disparos_en_contra",
                            "goles_a_favor","goles_en_contra","ratio_a_favor","ratio_en_contra"]
                cols_dis = [c for c in cols_dis if c in df_show.columns]
                df_dis = df_show[cols_dis].copy()
                # Convertir cols numéricas a float para que style.format funcione
                for c in ("disparos_a_favor","disparos_en_contra","goles_a_favor",
                          "goles_en_contra","ratio_a_favor","ratio_en_contra"):
                    if c in df_dis.columns:
                        df_dis[c] = pd.to_numeric(df_dis[c], errors="coerce")
                sty_dis = df_dis.style.format({
                    "disparos_a_favor": "{:.0f}", "disparos_en_contra": "{:.0f}",
                    "goles_a_favor": "{:.0f}", "goles_en_contra": "{:.0f}",
                    "ratio_a_favor": "{:.2f}", "ratio_en_contra": "{:.2f}",
                }, na_rep="—")

                # Semáforo (con applies por columna, robusto a Python 3.14):
                # - ratio_a_favor: ALTO = MALO (más disparos por gol) → rojo
                # - ratio_en_contra: ALTO = BUENO (rival le cuesta marcar) → verde
                if "ratio_a_favor" in df_dis.columns:
                    css_af = _aplicar_gradient_columna(df_dis, "ratio_a_favor", invertir=True)
                    sty_dis = sty_dis.apply(
                        lambda s: css_af.reindex(s.index, fill_value="").tolist(),
                        subset=["ratio_a_favor"], axis=0,
                    )
                if "ratio_en_contra" in df_dis.columns:
                    css_ec = _aplicar_gradient_columna(df_dis, "ratio_en_contra", invertir=False)
                    sty_dis = sty_dis.apply(
                        lambda s: css_ec.reindex(s.index, fill_value="").tolist(),
                        subset=["ratio_en_contra"], axis=0,
                    )
                st.dataframe(sty_dis, use_container_width=True, hide_index=True,
                             column_config={c: st.column_config.Column(help=TOOLTIPS_COLS.get(c, ""))
                                            for c in cols_dis if TOOLTIPS_COLS.get(c)})
    
            st.markdown("---")
    
            # ── Eficiencia por jugador (datos individuales del Excel) ──────────
            if not est_partidos.empty:
                st.markdown("#### 🎯 Eficiencia por jugador")
                st.caption(
                    "Disparos individuales de cada jugador (DP=a puerta, DPalo, DB=bloqueado, "
                    "DF=fuera) y conversión a gol."
                )
                ep_e = _est_num(est_partidos)
                agr_e = ep_e.groupby("jugador", as_index=False).agg(
                    partidos=("participa", "sum"),
                    min_total=("min_total", "sum"),
                    dp=("dp", "sum"), dpalo=("dpalo", "sum"),
                    db=("db", "sum"), df=("df", "sum"),
                    goles=("goles_a_favor", "sum"),
                )
                agr_e["dt"] = agr_e["dp"] + agr_e["dpalo"] + agr_e["db"] + agr_e["df"]
                agr_e["pct_a_puerta"] = (agr_e["dp"] / agr_e["dt"].replace(0, np.nan) * 100).round(1)
                agr_e["pct_conversion"] = (agr_e["goles"] / agr_e["dp"].replace(0, np.nan) * 100).round(1)
                inv_min_e = 1 / agr_e["min_total"].clip(lower=1)
                agr_e["dp_por_40"] = (agr_e["dp"] * 40 * inv_min_e).round(2)
                agr_e["dt_por_40"] = (agr_e["dt"] * 40 * inv_min_e).round(2)
                agr_e["goles_por_40"] = (agr_e["goles"] * 40 * inv_min_e).round(2)
                agr_e = agr_e[agr_e["dt"] > 0].sort_values("dt", ascending=False)
    
                cols_e = ["jugador", "partidos", "min_total",
                          "dp", "dpalo", "db", "df", "dt",
                          "pct_a_puerta", "goles", "pct_conversion",
                          "dp_por_40", "dt_por_40", "goles_por_40"]
                cols_e = [c for c in cols_e if c in agr_e.columns]
                st.dataframe(
                    agr_e[cols_e].style.format({
                        "min_total": "{:.0f}",
                        "dp": "{:.0f}", "dpalo": "{:.0f}", "db": "{:.0f}",
                        "df": "{:.0f}", "dt": "{:.0f}",
                        "pct_a_puerta": "{:.1f}%", "pct_conversion": "{:.1f}%",
                        "dp_por_40": "{:.2f}", "dt_por_40": "{:.2f}",
                        "goles_por_40": "{:.2f}",
                    }, na_rep="—"),
                    use_container_width=True, hide_index=True,
                )
    
    
    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 📈 Eficiencia: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 11 — 🔍 SCOUTING DE RIVALES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_scout:
    try:
        if scout_raw.empty or scout_agr.empty:
            st.info(
                "Aún no hay datos de scouting. Ejecuta:\n\n"
                "`/usr/bin/python3 src/scouting_rivales.py --upload`"
            )
        else:
            st.markdown("### 🔍 Scouting de rivales")
            st.caption(
                "Cómo marcan los rivales cuando juegan contra OTROS equipos (no contra Inter). "
                "Útil para preparar partidos."
            )
    
            sub_global, sub_rival = st.tabs(["📊 Global (todos los rivales)", "🎯 Foco en un rival"])
    
            # Abreviaturas para el heatmap (cabeceras cortas, mismo ancho)
            ABREV_ACCION = {
                "Banda": "BAN", "Córner": "COR", "Saque de Centro": "SQC",
                "Falta": "FAL", "2ª jugada de ABP": "2ªA", "10 metros": "10M",
                "Penalti": "PEN", "Falta sin barrera": "FSB",
                "Ataque Posicional 4x4": "4x4", "1x1 en banda": "1x1",
                "Salida de presión": "SAL", "2ª jugada": "2ª",
                "Incorporación del portero": "IPO",
                "Robo en incorporación de portero": "RIP",
                "Pérdida en incorporación de portero": "PIP",
                "5x4": "5x4", "4x5": "4x5", "4x3": "4x3", "3x4": "3x4",
                "Contraataque": "CTR", "Robo en zona alta": "RZA",
                "No calificado": "N/C",
            }
    
            with sub_global:
                st.markdown("#### Comparativa entre rivales")
                agr = scout_agr.copy()
                for c in agr.columns:
                    if c in ("rival_codigo", "rival_nombre"):
                        continue
                    agr[c] = pd.to_numeric(agr[c], errors="coerce")

                # Top: a favor + en contra
                cols_top = ["rival_codigo", "rival_nombre", "partidos",
                            "total_a_favor", "total_en_contra"]
                cols_top = [c for c in cols_top if c in agr.columns]
                if "total_a_favor" in agr.columns and "total_en_contra" in agr.columns:
                    agr["dif_goles"] = agr["total_a_favor"] - agr["total_en_contra"]
                    cols_top.append("dif_goles")
                st.dataframe(
                    agr[cols_top].style
                    .format({"partidos": "{:.0f}",
                             "total_a_favor": "{:.0f}",
                             "total_en_contra": "{:.0f}",
                             "dif_goles": "{:+.0f}"}, na_rep="—")
                    .background_gradient(subset=["total_a_favor"], cmap="Greens")
                    .background_gradient(subset=["total_en_contra"], cmap="Reds")
                    .background_gradient(subset=["dif_goles"], cmap="RdYlGn"),
                    use_container_width=True, hide_index=True,
                )

                # Heatmaps separados: A FAVOR y EN CONTRA
                def _render_heatmap(prefix_pct, titulo):
                    cols_pct = [c for c in agr.columns if c.startswith(prefix_pct)]
                    if not cols_pct:
                        return
                    st.markdown(f"#### {titulo}")
                    st.caption("Cabeceras abreviadas (pasa el ratón para ver el nombre completo).")
                    heat = agr[["rival_codigo"] + cols_pct].set_index("rival_codigo")
                    col_map, long_names = {}, {}
                    for c in heat.columns:
                        # Quitar prefijo "%AF_" o "%EC_"
                        name_full = c.replace(prefix_pct, "")
                        short = ABREV_ACCION.get(name_full, name_full[:3].upper())
                        if short in col_map.values():
                            short = short + "·"
                        col_map[c] = short
                        long_names[short] = name_full
                    heat = heat.rename(columns=col_map)
                    heat = heat.loc[:, heat.max() > 5]
                    cc = {s: st.column_config.NumberColumn(
                        s, help=long_names.get(s, ""), format="%.1f%%")
                          for s in heat.columns}
                    st.dataframe(
                        heat.style.format("{:.1f}%", na_rep="—")
                        .background_gradient(cmap="YlOrRd", axis=None),
                        use_container_width=True,
                        column_config=cc,
                    )

                _render_heatmap("%AF_", "Heatmap: cómo MARCA cada rival (% por origen)")
                _render_heatmap("%EC_", "Heatmap: cómo RECIBE cada rival (% por origen)")
    
            with sub_rival:
                rivales_op = scout_agr["rival_nombre"].tolist() if "rival_nombre" in scout_agr.columns else []
                if rivales_op:
                    rival_sel = st.selectbox("Rival a analizar", rivales_op, key="scout_rival")
                    df_r = scout_raw[scout_raw["rival_nombre"] == rival_sel].copy()
                    agr_r_filter = scout_agr[scout_agr["rival_nombre"] == rival_sel]
                    agr_r = agr_r_filter.iloc[0] if not agr_r_filter.empty else None
                    # Código del rival (3 letras)
                    cod_rival = (agr_r["rival_codigo"] if agr_r is not None
                                 and "rival_codigo" in agr_r.index else "")
    
                    # Detectar el nombre con el que aparece en SCOUTING_RIVALES como
                    # "contra_quien" (lo apuntan distinto cada equipo: "BARCELONA",
                    # "FC BARCELONA"...). Match aproximado por código de 3 letras.
                    rival_corto = (rival_sel.split()[0] if rival_sel else "").upper()
    
                    if agr_r is not None:
                        def _n(v):
                            v = pd.to_numeric(v, errors="coerce")
                            return int(v) if pd.notna(v) else 0
                        partidos = _n(agr_r.get("partidos", 0))
                        gf = _n(agr_r.get("total_a_favor", 0))
                        gc = _n(agr_r.get("total_en_contra", 0))

                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Partidos", partidos)
                        k2.metric("⚽ Goles a favor", gf)
                        k3.metric("🥅 Goles en contra", gc)
                        k4.metric("Diferencial", f"{gf-gc:+d}")

                        # ── A FAVOR (cómo marca este rival) ───────────────────
                        st.markdown(f"#### ⚽ Cómo marca **{rival_sel}**")
                        af_data = []
                        for accion in [a for a in agr_r.index if a.startswith("AF_") and not a.startswith("AF_port") and not a.startswith("AF_zona")]:
                            v = pd.to_numeric(agr_r[accion], errors="coerce")
                            if v and v > 0:
                                af_data.append({"accion": accion.replace("AF_", ""), "goles": int(v)})
                        if af_data:
                            df_af = pd.DataFrame(af_data).sort_values("goles", ascending=False)
                            st.bar_chart(df_af.set_index("accion")["goles"], color="#2E7D32")
                        else:
                            st.caption("Sin datos.")

                        # ── EN CONTRA (cómo recibe este rival) ─────────────────
                        st.markdown(f"#### 🥅 Cómo recibe **{rival_sel}**")
                        ec_data = []
                        for accion in [a for a in agr_r.index if a.startswith("EC_") and not a.startswith("EC_port") and not a.startswith("EC_zona")]:
                            v = pd.to_numeric(agr_r[accion], errors="coerce")
                            if v and v > 0:
                                ec_data.append({"accion": accion.replace("EC_", ""), "goles": int(v)})
                        if ec_data:
                            df_ec = pd.DataFrame(ec_data).sort_values("goles", ascending=False)
                            st.bar_chart(df_ec.set_index("accion")["goles"], color="#B71C1C")
                        else:
                            st.caption("Sin datos.")

                        # ── Mapas SVG: campo (11 zonas) + portería (9 cuadrantes) ─
                        st.markdown("#### 🎯 Mapas de zona")
                        st.caption(
                            "**Verde claro** = pocos goles · **rojo intenso** = muchos goles · "
                            "**gris** = ningún gol registrado desde esa zona."
                        )

                        # Helper: construye dict {A1: v, A2: v, ..., P1: v, ...} desde la fila
                        def _zonas_dict(prefix_campo, prefix_port):
                            d = {}
                            for i in range(1, 12):
                                k_campo = f"A{i}"
                                col_z = f"{prefix_campo}Z{i}"
                                if col_z in agr_r.index:
                                    v = pd.to_numeric(agr_r[col_z], errors="coerce")
                                    d[k_campo] = int(v) if v and v > 0 else 0
                            for i in range(1, 10):
                                k_port = f"P{i}"
                                col_p = f"{prefix_port}P{i}"
                                if col_p in agr_r.index:
                                    v = pd.to_numeric(agr_r[col_p], errors="coerce")
                                    d[k_port] = int(v) if v and v > 0 else 0
                            return d

                        zonas_af = _zonas_dict("AF_zona_", "AF_port_")
                        zonas_ec = _zonas_dict("EC_zona_", "EC_port_")

                        sub_af, sub_ec = st.tabs([
                            f"⚽ Cómo marca {rival_sel}",
                            f"🥅 Cómo recibe {rival_sel}"
                        ])

                        with sub_af:
                            colA, colB = st.columns([3, 2])
                            with colA:
                                st.markdown("**Campo · desde dónde dispara**")
                                st.markdown(
                                    generar_svg_campo({k: zonas_af.get(k, 0)
                                                        for k in [f"A{i}" for i in range(1, 12)]}),
                                    unsafe_allow_html=True,
                                )
                            with colB:
                                st.markdown("**Portería · dónde entra el balón**")
                                st.markdown(
                                    generar_svg_porteria({k: zonas_af.get(k, 0)
                                                           for k in [f"P{i}" for i in range(1, 10)]}),
                                    unsafe_allow_html=True,
                                )

                        with sub_ec:
                            colA, colB = st.columns([3, 2])
                            with colA:
                                st.markdown("**Campo · desde dónde le disparan**")
                                st.markdown(
                                    generar_svg_campo({k: zonas_ec.get(k, 0)
                                                        for k in [f"A{i}" for i in range(1, 12)]}),
                                    unsafe_allow_html=True,
                                )
                            with colB:
                                st.markdown("**Portería · por dónde le entran**")
                                st.markdown(
                                    generar_svg_porteria({k: zonas_ec.get(k, 0)
                                                           for k in [f"P{i}" for i in range(1, 10)]}),
                                    unsafe_allow_html=True,
                                )

                    # ── Tabla partido a partido ─────────────────────────────
                    st.markdown(f"#### Partido a partido — {rival_sel}")
                    cols_show = ["competicion", "contra_quien", "fecha",
                                 "total_a_favor", "total_en_contra"]
                    cols_show = [c for c in cols_show if c in df_r.columns]
                    df_r_show = df_r[cols_show].copy()
                    for c in ("total_a_favor", "total_en_contra"):
                        if c in df_r_show.columns:
                            df_r_show[c] = pd.to_numeric(df_r_show[c], errors="coerce")
                    st.dataframe(
                        df_r_show.sort_values("fecha", ascending=False),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "competicion": st.column_config.Column(help="Competición"),
                            "contra_quien": st.column_config.Column("contra", help="Equipo contra el que jugó"),
                            "fecha": st.column_config.Column(help="Fecha del partido"),
                            "total_a_favor": st.column_config.NumberColumn("GF", help="Goles a favor del rival en ese partido", format="%d"),
                            "total_en_contra": st.column_config.NumberColumn("GC", help="Goles en contra del rival en ese partido", format="%d"),
                        },
                    )

        # ═══════════════════════════════════════════════════════════════
        # ITER 10 — Scouting GRANULAR de equipos rivales
        # ═══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("### 🕵 Scouting granular (iter 10)")
        st.caption(
            "Datos por gol y por penalti/10m de partidos vistos de "
            "equipos rivales. Útil para preparar enfrentamientos "
            "(sobre todo eliminatorias)."
        )

        sg = scout_goles if not scout_goles.empty else pd.DataFrame()
        sp = scout_pen if not scout_pen.empty else pd.DataFrame()
        equipos_disponibles = sorted(set(
            (sg["equipo"].astype(str).tolist() if not sg.empty else []) +
            (sp["equipo"].astype(str).tolist() if not sp.empty else [])
        ))

        s_goles, s_pen, s_edit = st.tabs([
            "⚽ Goles por equipo",
            "🎯 Penaltis/10m por equipo",
            "✏️ Editar scouting",
        ])

        # ─── Sub: GOLES por equipo ───────────────────────────────────
        with s_goles:
            if sg.empty:
                st.info(
                    "Aún no hay goles de scouting registrados. Ve a la "
                    "sub-pestaña '✏️ Editar scouting' para empezar."
                )
            else:
                st.markdown("##### Selecciona equipo")
                equipo_sel = st.selectbox(
                    "Equipo en scouting",
                    options=equipos_disponibles or ["(sin datos)"],
                    key="scout_eq_goles",
                )
                df_eq = sg[sg["equipo"] == equipo_sel].copy()
                if df_eq.empty:
                    st.caption("Sin datos para ese equipo.")
                else:
                    n_part = df_eq["fecha_partido"].astype(str).nunique()
                    n_af = int((df_eq["condicion"] == "A_FAVOR").sum())
                    n_ec = int((df_eq["condicion"] == "EN_CONTRA").sum())
                    cols_kpi = st.columns(3)
                    cols_kpi[0].metric("Partidos vistos", n_part)
                    cols_kpi[1].metric("Goles A FAVOR (mete)", n_af)
                    cols_kpi[2].metric("Goles EN CONTRA (recibe)", n_ec)

                    # Mapas SVG agregados
                    af_zona = {f"A{i}": int(((df_eq["condicion"] == "A_FAVOR") &
                                              (df_eq["zona_campo"] == f"A{i}")).sum())
                                for i in range(1, 12)}
                    af_port = {f"P{i}": int(((df_eq["condicion"] == "A_FAVOR") &
                                              (df_eq["zona_porteria"] == f"P{i}")).sum())
                                for i in range(1, 10)}
                    ec_zona = {f"A{i}": int(((df_eq["condicion"] == "EN_CONTRA") &
                                              (df_eq["zona_campo"] == f"A{i}")).sum())
                                for i in range(1, 12)}
                    ec_port = {f"P{i}": int(((df_eq["condicion"] == "EN_CONTRA") &
                                              (df_eq["zona_porteria"] == f"P{i}")).sum())
                                for i in range(1, 10)}
                    sub_af, sub_ec = st.tabs(["⚽ Cómo mete", "🥅 Cómo recibe"])
                    with sub_af:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Zonas del campo (origen del gol)**")
                            st.markdown(generar_svg_campo(af_zona), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Cuadrantes de portería**")
                            st.markdown(generar_svg_porteria(af_port), unsafe_allow_html=True)
                    with sub_ec:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Zonas del campo (origen del gol)**")
                            st.markdown(generar_svg_campo(ec_zona), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Cuadrantes de portería**")
                            st.markdown(generar_svg_porteria(ec_port), unsafe_allow_html=True)

                    st.markdown("##### 📋 Histórico de goles")
                    cols_hist = ["fecha_partido", "rival_de_ese_partido",
                                  "competicion", "condicion", "minuto_mmss",
                                  "accion", "zona_campo", "zona_porteria",
                                  "descripcion"]
                    cols_hist = [c for c in cols_hist if c in df_eq.columns]
                    st.dataframe(df_eq[cols_hist].sort_values("fecha_partido",
                                                                ascending=False),
                                  use_container_width=True, hide_index=True)

        # ─── Sub: PENALTIS por equipo ────────────────────────────────
        with s_pen:
            if sp.empty:
                st.info(
                    "Aún no hay penaltis/10m de scouting registrados. "
                    "Ve a la sub-pestaña '✏️ Editar scouting' para empezar."
                )
            else:
                equipo_sel_p = st.selectbox(
                    "Equipo en scouting",
                    options=equipos_disponibles or ["(sin datos)"],
                    key="scout_eq_pen",
                )
                df_eq = sp[sp["equipo"] == equipo_sel_p].copy()
                if df_eq.empty:
                    st.caption("Sin datos para ese equipo.")
                else:
                    n_total = len(df_eq)
                    n_pen = int((df_eq["tipo_lanzamiento"] == "PENALTI").sum())
                    n_10m = int((df_eq["tipo_lanzamiento"] == "10M").sum())
                    n_gol = int((df_eq["resultado"] == "GOL").sum())
                    pct = round(n_gol / max(n_total, 1) * 100, 1)
                    cols_kpi = st.columns(4)
                    cols_kpi[0].metric("Total tiros", n_total)
                    cols_kpi[1].metric("Penaltis", n_pen)
                    cols_kpi[2].metric("10m", n_10m)
                    cols_kpi[3].metric("% acierto", f"{pct}%")

                    # Lanzadores y porteros más usados
                    if not df_eq[df_eq["condicion"] == "A_FAVOR"].empty:
                        st.markdown("##### Lanzadores del equipo (a favor)")
                        df_lz = df_eq[df_eq["condicion"] == "A_FAVOR"]
                        rk_lz = (df_lz.groupby("lanzador")
                                 .agg(n=("resultado", "count"),
                                      goles=("resultado", lambda s: (s == "GOL").sum()))
                                 .reset_index().sort_values("n", ascending=False))
                        rk_lz["pct"] = (rk_lz["goles"] / rk_lz["n"] * 100).round(1)
                        st.dataframe(rk_lz, use_container_width=True,
                                      hide_index=True,
                                      column_config={
                                          "lanzador": "Lanzador", "n": "Tiros",
                                          "goles": "Goles",
                                          "pct": st.column_config.NumberColumn(
                                              "% acierto", format="%.1f%%"),
                                      })
                    # Mapa de cuadrantes preferidos por equipo
                    cuad_pref = df_eq[df_eq["cuadrante"].astype(str).str.match(r"P[1-9]", na=False)]
                    if not cuad_pref.empty:
                        st.markdown("##### 🎯 Cuadrantes preferidos del equipo")
                        cuad_dict = {f"P{i}": int((cuad_pref["cuadrante"] == f"P{i}").sum())
                                       for i in range(1, 10)}
                        st.markdown(generar_svg_porteria(cuad_dict),
                                     unsafe_allow_html=True)

                    st.markdown("##### 📋 Histórico de penaltis y 10m")
                    cols_hist = ["fecha_partido", "rival_de_ese_partido",
                                  "tipo_lanzamiento", "condicion", "parte",
                                  "minuto_mmss", "marcador", "lanzador",
                                  "portero", "resultado", "cuadrante",
                                  "descripcion"]
                    cols_hist = [c for c in cols_hist if c in df_eq.columns]
                    st.dataframe(df_eq[cols_hist].sort_values("fecha_partido",
                                                                ascending=False),
                                  use_container_width=True, hide_index=True)

        # ─── Sub: EDITAR SCOUTING ────────────────────────────────────
        with s_edit:
            st.caption(
                "Apunta los goles y penaltis/10m que has visto de un "
                "equipo rival. Puedes ver varios partidos del mismo "
                "equipo (van filtrados por equipo + fecha)."
            )

            colA, colB = st.columns([1, 1])
            with colA:
                equipo_input = st.text_input(
                    "Equipo en scouting",
                    placeholder="Ej: PEÑISCOLA, JIMBEE...",
                    key="scout_edit_eq",
                ).strip().upper()
                fecha_input = st.date_input(
                    "Fecha del partido visto",
                    value=_dt.date.today(),
                    key="scout_edit_fecha",
                )
                rival_input = st.text_input(
                    "Rival de ese partido",
                    placeholder="Ej: BARCELONA",
                    key="scout_edit_rival",
                ).strip().upper()
            with colB:
                comp_input = st.selectbox(
                    "Competición",
                    ["LIGA", "COPA DEL REY", "COPA ESPAÑA", "PLAYOFF",
                      "AMISTOSO", "OTRO"],
                    key="scout_edit_comp",
                )
                st.markdown("&nbsp;")  # espacio
                st.caption(
                    "Solo se guarda si rellenas **equipo** y **fecha**. "
                    "Si añades datos al mismo (equipo, fecha) se **suman** "
                    "(no se sobreescriben los anteriores)."
                )

            # Editor de goles
            st.markdown("##### ⚽ Goles")
            df_goles_init = pd.DataFrame({
                "condicion": pd.Series(dtype="str"),
                "minuto_mmss": pd.Series(dtype="str"),
                "accion": pd.Series(dtype="str"),
                "zona_campo": pd.Series(dtype="str"),
                "zona_porteria": pd.Series(dtype="str"),
                "descripcion": pd.Series(dtype="str"),
            })
            opciones_acc = ["", "Banda", "Córner", "Saque de Centro", "Falta",
                             "2ª jugada de ABP", "10 metros", "Penalti",
                             "Falta sin barrera", "Ataque Posicional 4x4",
                             "1x1 en banda", "Salida de presión", "2ª jugada",
                             "Incorporación del portero",
                             "Robo en incorporación de portero",
                             "Pérdida en incorporación de portero",
                             "5x4", "4x5", "4x3",
                             "3x4", "Contraataque", "Robo en zona alta",
                             "No calificado"]
            df_goles_edit = st.data_editor(
                df_goles_init, num_rows="dynamic",
                use_container_width=True, key="scout_goles_editor",
                hide_index=True,
                column_config={
                    "condicion": st.column_config.SelectboxColumn(
                        "Cond.", options=["", "A_FAVOR", "EN_CONTRA"],
                        width="small"),
                    "minuto_mmss": st.column_config.TextColumn(
                        "Min", max_chars=6, width="small"),
                    "accion": st.column_config.SelectboxColumn(
                        "Acción", options=opciones_acc),
                    "zona_campo": st.column_config.SelectboxColumn(
                        "Zona campo",
                        options=[""] + [f"A{i}" for i in range(1, 12)],
                        width="small"),
                    "zona_porteria": st.column_config.SelectboxColumn(
                        "Cuadr. portería",
                        options=[""] + [f"P{i}" for i in range(1, 10)],
                        width="small"),
                    "descripcion": st.column_config.TextColumn(
                        "Descripción", width="medium"),
                },
            )

            # Editor de penaltis/10m
            st.markdown("##### 🎯 10 metros / Penaltis")
            df_pen_init = pd.DataFrame({
                "tipo_lanzamiento": pd.Series(dtype="str"),
                "condicion": pd.Series(dtype="str"),
                "parte": pd.Series(dtype="str"),
                "minuto_mmss": pd.Series(dtype="str"),
                "marcador": pd.Series(dtype="str"),
                "lanzador": pd.Series(dtype="str"),
                "portero": pd.Series(dtype="str"),
                "resultado": pd.Series(dtype="str"),
                "cuadrante": pd.Series(dtype="str"),
                "descripcion": pd.Series(dtype="str"),
            })
            df_pen_edit = st.data_editor(
                df_pen_init, num_rows="dynamic",
                use_container_width=True, key="scout_pen_editor",
                hide_index=True,
                column_config={
                    "tipo_lanzamiento": st.column_config.SelectboxColumn(
                        "Tipo", options=["", "PENALTI", "10M"], width="small"),
                    "condicion": st.column_config.SelectboxColumn(
                        "Cond.", options=["", "A_FAVOR", "EN_CONTRA"], width="small"),
                    "parte": st.column_config.SelectboxColumn(
                        "P", options=["", "1", "2"], width="small"),
                    "minuto_mmss": st.column_config.TextColumn(
                        "Min", max_chars=6, width="small"),
                    "marcador": st.column_config.TextColumn(
                        "Marc.", max_chars=8, width="small"),
                    "lanzador": st.column_config.TextColumn("Lanzador"),
                    "portero": st.column_config.TextColumn("Portero"),
                    "resultado": st.column_config.SelectboxColumn(
                        "Resultado",
                        options=["", "GOL", "PARADA", "POSTE", "FUERA"],
                        width="small"),
                    "cuadrante": st.column_config.SelectboxColumn(
                        "Cuadr.",
                        options=[""] + [f"P{i}" for i in range(1, 10)],
                        width="small"),
                    "descripcion": st.column_config.TextColumn(
                        "Descripción", width="medium"),
                },
            )

            if st.button("💾 Guardar scouting", type="primary",
                          key="scout_guardar"):
                if not equipo_input:
                    st.error("Pon el nombre del equipo en scouting.")
                else:
                    try:
                        import gspread
                        sh = _conexion_sheet_scout()  # helper definido más abajo
                        # GOLES
                        n_goles_save = 0
                        if not df_goles_edit.empty:
                            n_goles_save = _guardar_scout_goles(
                                sh, equipo_input, fecha_input.isoformat(),
                                rival_input, comp_input, df_goles_edit
                            )
                        # PENALTIS
                        n_pen_save = 0
                        if not df_pen_edit.empty:
                            n_pen_save = _guardar_scout_pen(
                                sh, equipo_input, fecha_input.isoformat(),
                                rival_input, comp_input, df_pen_edit
                            )
                        st.success(
                            f"✅ Scouting guardado: {n_goles_save} goles + "
                            f"{n_pen_save} penaltis/10m."
                        )
                        st.cache_data.clear()
                        st.info("Refresca para verlo en las otras sub-pestañas.")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                        import traceback as _tb
                        st.expander('Detalles').code(_tb.format_exc())

    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 🔍 Scouting: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9 — 🎮 VISTA PARTIDO (replica J26.XOTA del Excel)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_partido:
    try:
        if est_partidos.empty:
            st.info(
                "Aún no hay datos. Ejecuta:\n\n"
                "`/usr/bin/python3 src/estadisticas_partidos.py --upload`"
            )
        else:
            st.markdown("### 🎮 Vista por partido")
            st.caption("Todo el detalle de un partido concreto: rotaciones, métricas individuales, eventos de gol y desglose por intervalos de 5'.")
    
            ep = _est_num(est_partidos)
            ev = est_eventos.copy() if not est_eventos.empty else pd.DataFrame()
            if not ev.empty:
                ev["minuto"] = pd.to_numeric(ev["minuto"], errors="coerce")
    
            # ── Selector de partido en orden CRONOLÓGICO (más reciente arriba)──
            partidos_meta = (ep.groupby("partido_id", as_index=False)
                             .agg(tipo=("tipo", "first"),
                                  competicion=("competicion", "first"),
                                  rival=("rival", "first"),
                                  fecha=("fecha", "first")))
            partidos_meta["_fkey"] = pd.to_datetime(partidos_meta["fecha"], errors="coerce")
            # Orden: por fecha descendente; los partidos sin fecha al final
            partidos_meta = partidos_meta.sort_values(
                "_fkey", ascending=False, na_position="last"
            )
    
            def _label(r):
                f = str(r["fecha"]) if r["fecha"] else "—"
                return f"{f} · {r['partido_id']} — {r['rival']}"
            partidos_meta["label"] = partidos_meta.apply(_label, axis=1)
            labels = partidos_meta["label"].tolist()
            sel_label = st.selectbox("Selecciona partido (orden cronológico, recientes arriba)",
                                      labels, key="partido_sel")
            sel_id = partidos_meta[partidos_meta["label"] == sel_label]["partido_id"].iloc[0]
            meta = partidos_meta[partidos_meta["partido_id"] == sel_id].iloc[0]
    
            # ── Datos del partido ────────────────────────────────────────────
            ep_p = ep[ep["partido_id"] == sel_id].copy()
            ev_p = ev[ev["partido_id"] == sel_id] if not ev.empty else pd.DataFrame()
    
            # Totales del partido (de EST_TOTALES_PARTIDO si está)
            tot_p = None
            if not est_tot_partido.empty:
                row_t = est_tot_partido[est_tot_partido["partido_id"] == sel_id]
                if not row_t.empty:
                    tot_p = row_t.iloc[0]
    
            # Marcador
            gf_p = int((ev_p["equipo_marca"] == "INTER").sum()) if not ev_p.empty else 0
            gc_p = int((ev_p["equipo_marca"] == "RIVAL").sum()) if not ev_p.empty else 0
    
            st.markdown(f"#### Movistar Inter FS  {gf_p} – {gc_p}  {meta['rival']}")
            cap_partes = []
            if meta["competicion"]:
                cap_partes.append(str(meta["competicion"]))
            if meta["fecha"]:
                cap_partes.append(str(meta["fecha"]))
            st.caption(" · ".join(cap_partes) if cap_partes else "")

            # ── Descargar PDF del partido ─────────────────────────────────
            col_pdf_a, col_pdf_b, _ = st.columns([1.2, 1.5, 4])
            with col_pdf_a:
                gen_pdf = st.button("📄 Generar PDF",
                                     key=f"genpdf_btn_{sel_id}",
                                     help="Crea un PDF del partido con cabecera, KPIs, "
                                          "minutos, métricas individuales, eventos, "
                                          "rotaciones y mapas de zona.")
            if gen_pdf:
                try:
                    import sys as _sys
                    from pathlib import Path as _Path
                    _root = _Path(__file__).resolve().parent.parent
                    if str(_root) not in _sys.path:
                        _sys.path.insert(0, str(_root))
                    from src.pdf_partido import generar_pdf_partido as _gen_pdf
                    with st.spinner("Generando PDF…"):
                        _sh = get_client().open(SHEET_NAME)
                        _pdf_bytes = _gen_pdf(
                            sel_id,
                            sh=_sh,
                            svg_campo_fn=generar_svg_campo,
                            svg_porteria_fn=generar_svg_porteria,
                        )
                    st.session_state[f"pdf_data_{sel_id}"] = _pdf_bytes
                except Exception as _e_pdf:
                    st.error(f"❌ No pude generar el PDF: {_e_pdf}")
            with col_pdf_b:
                if st.session_state.get(f"pdf_data_{sel_id}"):
                    _fname = f"{sel_id.replace('.', '_').replace(' ', '_')}.pdf"
                    st.download_button(
                        "⬇️ Descargar PDF",
                        data=st.session_state[f"pdf_data_{sel_id}"],
                        file_name=_fname,
                        mime="application/pdf",
                        key=f"dlpdf_{sel_id}",
                    )
    
            # ── KPIs ampliados (10) ────────────────────────────────────────────
            # Calcular totales (preferir EST_TOTALES_PARTIDO; fallback a sumar de EP)
            if tot_p is not None:
                # `pd.to_numeric(...).fillna(0)` para evitar NaN (que con
                # `or 0` no se convierte porque NaN es "truthy" en Python).
                def _kpi(col):
                    v = pd.to_numeric(tot_p.get(col, 0), errors="coerce")
                    return int(v) if pd.notna(v) else 0
                dt_inter = _kpi("dt_inter")
                dp_inter = _kpi("dp_inter")
                dt_rival = _kpi("dt_rival")
                dp_rival = _kpi("dp_rival")
                pf_total = _kpi("pf_inter")
                pnf_total = _kpi("pnf_inter")
                robos_total = _kpi("robos_inter")
                cortes_total = _kpi("cortes_inter")
            else:
                dt_inter = int((ep_p["dp"] + ep_p["dpalo"] + ep_p["db"] + ep_p["df"]).sum())
                dp_inter = int(ep_p["dp"].sum())
                dt_rival = 0
                dp_rival = int((ep_p["par"] + ep_p["gol_p"]).sum())
                pf_total = int(ep_p["pf"].sum())
                pnf_total = int(ep_p["pnf"].sum())
                robos_total = int(ep_p["robos"].sum())
                cortes_total = int(ep_p["cortes"].sum())
    
            # KPIs en 2 filas de 5
            rfila1 = st.columns(5)
            with rfila1[0]:
                st.markdown('<div class="kpi-positivo">', unsafe_allow_html=True)
                st.metric("⚽ Goles a favor", gf_p)
                st.markdown('</div>', unsafe_allow_html=True)
            with rfila1[1]:
                st.markdown('<div class="kpi-negativo">', unsafe_allow_html=True)
                st.metric("🥅 Goles en contra", gc_p)
                st.markdown('</div>', unsafe_allow_html=True)
            rfila1[2].metric("🎯 Disparos totales", dt_inter)
            rfila1[3].metric("🎯 Disparos a puerta", dp_inter)
            rfila1[4].metric("🛡 Recuperaciones", robos_total + cortes_total,
                             help="Robos + Cortes (interceptaciones)")
    
            rfila2 = st.columns(5)
            rfila2[0].metric("🚫 Disparos rival (total)", dt_rival)
            rfila2[1].metric("🚫 Disparos rival a puerta", dp_rival)
            rfila2[2].metric("🪝 Pérdidas forzadas", pf_total,
                             help="El rival te roba la pelota presionando")
            rfila2[3].metric("⚠️ Pérdidas no forzadas", pnf_total,
                             help="La pelota se pierde por error propio")
            rfila2[4].metric("✋ Robos", robos_total)
    
            st.markdown("---")
    
            # ── Tabla de minutos por jugador (con semáforo, sin porteros) ─────
            st.markdown("#### ⏱ Minutos por jugador y parte")
            st.caption("Color: **verde** = más minutos · **rojo** = menos. Los porteros (J.GARCIA, J.HERRERO, OSCAR) se excluyen del semáforo y aparecen en gris claro.")

            tabla_min = ep_p.sort_values("min_total", ascending=False)[
                ["dorsal", "jugador", "min_1t", "min_2t", "min_total"]
            ].copy()
            # Pre-formatear minutos como mm:ss (string), guardar valores numéricos en cols paralelas
            for c in ("min_1t", "min_2t", "min_total"):
                tabla_min[c + "_num"] = pd.to_numeric(tabla_min[c], errors="coerce")
                tabla_min[c] = tabla_min[c + "_num"].apply(_fmt_minutos)
            tabla_min["dorsal"] = pd.to_numeric(tabla_min["dorsal"], errors="coerce").fillna(0).astype(int)

            # Identificar índices de porteros (canónicos)
            PORT_DASH = {"J.HERRERO", "J.GARCIA", "OSCAR", "HERRERO", "GARCIA"}
            es_p = tabla_min["jugador"].astype(str).str.upper().isin(PORT_DASH)
            idx_porteros = tabla_min[es_p].index.tolist()

            # Construir la tabla a renderizar (sin las cols _num)
            df_tmin = tabla_min[["dorsal", "jugador", "min_1t", "min_2t", "min_total"]]

            # Aplicar gradient por columna usando los valores NUMÉRICOS (de _num)
            # via Styler.apply(axis=0) sobre cada columna numérica
            def _style_min_col(col_label_num):
                def _styler(s_visual):
                    # s_visual son los strings mm:ss; usamos col paralela _num
                    valores = tabla_min[col_label_num]
                    return _aplicar_gradient_columna(
                        tabla_min, col_label_num,
                        filas_excluidas=idx_porteros, invertir=False,
                    ).reindex(s_visual.index, fill_value="").tolist()
                return _styler

            sty = df_tmin.style
            sty = sty.apply(_style_min_col("min_1t_num"), subset=["min_1t"], axis=0)
            sty = sty.apply(_style_min_col("min_2t_num"), subset=["min_2t"], axis=0)
            sty = sty.apply(_style_min_col("min_total_num"), subset=["min_total"], axis=0)

            st.dataframe(
                sty, use_container_width=True, hide_index=True,
                column_config={
                    "dorsal": st.column_config.Column("Nº", help="Número de dorsal"),
                    "jugador": st.column_config.Column("Jugador"),
                    "min_1t": st.column_config.Column("1ª parte", help="Minutos en la 1ª parte (mm:ss)"),
                    "min_2t": st.column_config.Column("2ª parte", help="Minutos en la 2ª parte (mm:ss)"),
                    "min_total": st.column_config.Column("Total", help="Minutos totales (mm:ss)"),
                },
            )
    
            # ── Rotaciones individuales (1ª-8ª de cada parte) ─────────────────
            cols_rot_1t = [f"rot_1t_{i}" for i in range(1, 9)]
            cols_rot_2t = [f"rot_2t_{i}" for i in range(1, 9)]

            def _css_rotacion(v_num):
                """Escala fija: >3' rojo · 2-3' amarillo · 1-2' verde · 0-1' azul · 0 blanco"""
                if pd.isna(v_num) or v_num <= 0:
                    return "background-color: #ffffff;"
                if v_num <= 1:
                    return "background-color: #BBDEFB;"   # azul claro
                if v_num <= 2:
                    return "background-color: #C8E6C9;"   # verde claro
                if v_num <= 3:
                    return "background-color: #FFF59D;"   # amarillo claro
                return "background-color: #FFCDD2;"       # rojo claro

            def _render_rotaciones(tab_rot, cols_rot_orig, total_col_orig, label):
                """Renderiza una mitad (1T o 2T)."""
                # Convertir todos los rot a numérico y formatear como mm:ss en otra col
                tab = tab_rot.copy()
                for c in cols_rot_orig + [total_col_orig]:
                    tab[c + "_num"] = pd.to_numeric(tab[c], errors="coerce")
                    tab[c] = tab[c + "_num"].apply(_fmt_minutos)
                tab["dorsal"] = pd.to_numeric(tab["dorsal"], errors="coerce").fillna(0).astype(int)

                rename = {c: f"{i+1}ª" for i, c in enumerate(cols_rot_orig)}
                rename.update({"dorsal": "Nº", "jugador": "Jugador", total_col_orig: f"Total {label}"})
                tab_view = tab[["dorsal", "jugador"] + cols_rot_orig + [total_col_orig]].rename(columns=rename)

                # Aplicar color por columna usando los valores numéricos
                sty = tab_view.style
                for i, c_orig in enumerate(cols_rot_orig):
                    nombre_col_visual = f"{i+1}ª"
                    serie_num = tab[c_orig + "_num"]
                    css = serie_num.apply(_css_rotacion)
                    # apply axis=0 sobre la columna concreta
                    def _make_styler(css_series):
                        def _f(s):
                            return css_series.reindex(s.index, fill_value="").tolist()
                        return _f
                    sty = sty.apply(_make_styler(css), subset=[nombre_col_visual], axis=0)
                st.dataframe(sty, use_container_width=True, hide_index=True)

            if all(c in ep_p.columns for c in cols_rot_1t):
                with st.expander("⏱ Rotaciones individuales (cada vez que entra al campo)"):
                    st.caption(
                        "Color: **rojo** >3' · **amarillo** 2-3' · **verde** 1-2' · "
                        "**azul** <1' · **blanco** sin minutos."
                    )
                    st.markdown("**1ª parte**")
                    tab1_base = ep_p.sort_values("min_total", ascending=False)[
                        ["dorsal", "jugador"] + cols_rot_1t + ["min_1t"]
                    ]
                    _render_rotaciones(tab1_base, cols_rot_1t, "min_1t", "1T")
                    st.markdown("**2ª parte**")
                    tab2_base = ep_p.sort_values("min_total", ascending=False)[
                        ["dorsal", "jugador"] + cols_rot_2t + ["min_2t"]
                    ]
                    _render_rotaciones(tab2_base, cols_rot_2t, "min_2t", "2T")
    
            # ── Tabla de métricas individuales del partido ──────────────────────
            st.markdown("#### 📊 Métricas individuales del partido")
            cols_met = ["dorsal", "jugador",
                        "pf", "pnf", "robos", "cortes",
                        "bdg", "bdp",
                        "dp", "dpalo", "db", "df",
                        "ta", "tr",
                        "goles_a_favor", "asistencias"]
            cols_met = [c for c in cols_met if c in ep_p.columns]
            # Asegurar que las columnas numéricas no tienen NaN antes de operar
            for c in ("dp", "dpalo", "db", "df", "ta", "tr"):
                if c in ep_p.columns:
                    ep_p[c] = pd.to_numeric(ep_p[c], errors="coerce").fillna(0).astype(int)
            tabla_met = ep_p[cols_met].copy()
            tabla_met["dt"] = (ep_p["dp"] + ep_p["dpalo"] + ep_p["db"] + ep_p["df"]).astype(int)
            # Ordenar por minutos jugados
            tabla_met = tabla_met.assign(_min=ep_p["min_total"].values).sort_values(
                "_min", ascending=False
            ).drop(columns="_min")
    
            cc_part = {
                "dorsal": st.column_config.Column("Nº", help=TOOLTIPS_COLS["dorsal"]),
                "jugador": st.column_config.Column("Jugador"),
                "pf": st.column_config.NumberColumn("PF", help=TOOLTIPS_COLS["pf"], format="%d"),
                "pnf": st.column_config.NumberColumn("PNF", help=TOOLTIPS_COLS["pnf"], format="%d"),
                "robos": st.column_config.NumberColumn("Robos", help=TOOLTIPS_COLS["robos"], format="%d"),
                "cortes": st.column_config.NumberColumn("Cortes", help=TOOLTIPS_COLS["cortes"], format="%d"),
                "bdg": st.column_config.NumberColumn("BDG", help=TOOLTIPS_COLS["bdg"], format="%d"),
                "bdp": st.column_config.NumberColumn("BDP", help=TOOLTIPS_COLS["bdp"], format="%d"),
                "dp": st.column_config.NumberColumn("DP", help=TOOLTIPS_COLS["dp"], format="%d"),
                "dpalo": st.column_config.NumberColumn("DPalo", help=TOOLTIPS_COLS["dpalo"], format="%d"),
                "db": st.column_config.NumberColumn("DB", help=TOOLTIPS_COLS["db"], format="%d"),
                "df": st.column_config.NumberColumn("DF", help=TOOLTIPS_COLS["df"], format="%d"),
                "dt": st.column_config.NumberColumn("DT", help=TOOLTIPS_COLS["dt"], format="%d"),
                "ta": st.column_config.NumberColumn("TA", help="Tarjeta amarilla", format="%d"),
                "tr": st.column_config.NumberColumn("TR", help="Tarjeta roja", format="%d"),
                "goles_a_favor": st.column_config.NumberColumn("Goles", help="Goles marcados", format="%d"),
                "asistencias": st.column_config.NumberColumn("Asists", help="Asistencias", format="%d"),
            }
            st.dataframe(tabla_met, use_container_width=True, hide_index=True,
                         column_config=cc_part)

            # ── Tabla de portería ──────────────────────────────────────────
            cols_port = ["par", "gol_p", "bloq_p", "poste_p"]
            cols_port_extra = ["salida", "salida_fallida"]
            if all(c in ep_p.columns for c in cols_port):
                for c in cols_port + [x for x in cols_port_extra if x in ep_p.columns]:
                    ep_p[c] = pd.to_numeric(ep_p[c], errors="coerce").fillna(0).astype(int)
                porteros_p = ep_p[
                    (ep_p["par"] + ep_p["gol_p"] +
                     ep_p["bloq_p"] + ep_p["poste_p"]) > 0
                ].copy()
                if not porteros_p.empty:
                    st.markdown("#### 🥅 Portería")
                    porteros_p["disp_total_rival"] = (porteros_p["par"]
                                                       + porteros_p["gol_p"]
                                                       + porteros_p["bloq_p"]
                                                       + porteros_p["poste_p"]).astype(int)
                    porteros_p["pct_paradas"] = porteros_p.apply(
                        lambda r: round(r["par"] / max(r["par"] + r["gol_p"], 1) * 100, 1)
                                   if (r["par"] + r["gol_p"]) > 0 else 0.0,
                        axis=1,
                    )
                    cols_show = ["dorsal", "jugador", "par", "gol_p",
                                  "bloq_p", "poste_p"]
                    if "salida" in porteros_p.columns:
                        cols_show.append("salida")
                    if "salida_fallida" in porteros_p.columns:
                        cols_show.append("salida_fallida")
                    cols_show += ["disp_total_rival", "pct_paradas"]
                    cols_show = [c for c in cols_show if c in porteros_p.columns]
                    porteros_p = porteros_p[cols_show].sort_values(
                        "par", ascending=False
                    )
                    cc_port = {
                        "dorsal": st.column_config.Column("Nº"),
                        "jugador": st.column_config.Column("Portero"),
                        "par": st.column_config.NumberColumn("Paradas", format="%d"),
                        "gol_p": st.column_config.NumberColumn("Goles enc.", format="%d"),
                        "bloq_p": st.column_config.NumberColumn("Bloqueos", format="%d"),
                        "poste_p": st.column_config.NumberColumn("Postes", format="%d"),
                        "salida": st.column_config.NumberColumn(
                            "Salidas", format="%d",
                            help="Salidas correctas del portero a balones"),
                        "salida_fallida": st.column_config.NumberColumn(
                            "Sal. fall.", format="%d",
                            help="Salidas fallidas del portero"),
                        "disp_total_rival": st.column_config.NumberColumn(
                            "Disp. rival", format="%d",
                            help="Total de disparos del rival a portería (par + gol + bloq + palo)"),
                        "pct_paradas": st.column_config.NumberColumn(
                            "% Paradas", format="%.1f%%",
                            help="Paradas / (Paradas + Goles encajados)"),
                    }
                    st.dataframe(porteros_p, use_container_width=True,
                                  hide_index=True, column_config=cc_port)

            # ── Faltas del partido (iter 9) ────────────────────────────────
            if not est_faltas.empty:
                fal_p = est_faltas[
                    est_faltas["partido_id"].astype(str) == str(sel_id)
                ].copy()
                if not fal_p.empty:
                    st.markdown("#### 🟨 Faltas del partido")
                    # Resumen por (parte, condicion)
                    resumen_fal = fal_p.groupby(["parte", "condicion"]).size().reset_index(name="n")
                    cols_n = st.columns(4)
                    n_av_1 = int(resumen_fal[(resumen_fal["parte"].astype(str) == "1") &
                                              (resumen_fal["condicion"] == "A_FAVOR")]["n"].sum() or 0)
                    n_ec_1 = int(resumen_fal[(resumen_fal["parte"].astype(str) == "1") &
                                              (resumen_fal["condicion"] == "EN_CONTRA")]["n"].sum() or 0)
                    n_av_2 = int(resumen_fal[(resumen_fal["parte"].astype(str) == "2") &
                                              (resumen_fal["condicion"] == "A_FAVOR")]["n"].sum() or 0)
                    n_ec_2 = int(resumen_fal[(resumen_fal["parte"].astype(str) == "2") &
                                              (resumen_fal["condicion"] == "EN_CONTRA")]["n"].sum() or 0)
                    cols_n[0].metric("1ª · A favor", n_av_1,
                                       delta="6ª llegada" if n_av_1 >= 6 else None,
                                       delta_color="inverse" if n_av_1 >= 6 else "off")
                    cols_n[1].metric("1ª · En contra", n_ec_1,
                                       delta="6ª llegada" if n_ec_1 >= 6 else None,
                                       delta_color="inverse" if n_ec_1 >= 6 else "off")
                    cols_n[2].metric("2ª · A favor", n_av_2,
                                       delta="6ª llegada" if n_av_2 >= 6 else None,
                                       delta_color="inverse" if n_av_2 >= 6 else "off")
                    cols_n[3].metric("2ª · En contra", n_ec_2,
                                       delta="6ª llegada" if n_ec_2 >= 6 else None,
                                       delta_color="inverse" if n_ec_2 >= 6 else "off")
                    # Tabla detallada
                    fal_show = fal_p[["parte", "minuto_mmss", "condicion",
                                        "jugador", "num_falta", "genera_10m",
                                        "descripcion"]].copy()
                    fal_show["genera_10m"] = fal_show["genera_10m"].astype(str).str.upper().map(
                        lambda v: "⚠️ 10M" if v == "TRUE" else "")
                    fal_show = fal_show.sort_values(["parte", "minuto_mmss"])
                    st.dataframe(fal_show, use_container_width=True, hide_index=True,
                                  column_config={
                                      "parte": "Parte", "minuto_mmss": "Min",
                                      "condicion": "Cond.", "jugador": "Jugador",
                                      "num_falta": "Nº",
                                      "genera_10m": "Penaliz.",
                                      "descripcion": st.column_config.Column("Descripción", width="medium"),
                                  })

            # ── 10 metros / Penaltis del partido (iter 9) ────────────────────────
            if not est_penaltis.empty:
                pen_p = est_penaltis[
                    est_penaltis["partido_id"].astype(str) == str(sel_id)
                ].copy()
                if not pen_p.empty:
                    st.markdown("#### 🎯 10 metros / Penaltis del partido")
                    pen_show = pen_p.copy()
                    cols_show_pen = ["tipo_lanzamiento", "condicion", "parte",
                                       "minuto_mmss", "marcador", "lanzador",
                                       "portero", "resultado", "cuadrante",
                                       "descripcion"]
                    cols_show_pen = [c for c in cols_show_pen if c in pen_show.columns]
                    pen_show = pen_show[cols_show_pen].copy()
                    # Emojis para resultado
                    pen_show["resultado"] = pen_show["resultado"].astype(str).map({
                        "GOL": "✅ GOL", "PARADA": "🧤 PARADA",
                        "POSTE": "📌 POSTE", "FUERA": "❌ FUERA",
                    }).fillna(pen_show["resultado"])
                    st.dataframe(pen_show, use_container_width=True, hide_index=True,
                                  column_config={
                                      "tipo_lanzamiento": "Tipo",
                                      "condicion": "Cond.",
                                      "parte": "P", "minuto_mmss": "Min",
                                      "marcador": "Marc.", "lanzador": "Lanzador",
                                      "portero": "Portero",
                                      "resultado": "Resultado",
                                      "cuadrante": "Cuadr.",
                                      "descripcion": st.column_config.Column("Descripción", width="medium"),
                                  })

            # ── Eventos de gol del partido (con descripción) ──────────────────
            st.markdown("#### ⚽ Goles del partido")
            if ev_p.empty:
                st.caption("Sin eventos de gol registrados.")
            else:
                evp = ev_p.copy().sort_values("minuto")
                evp["equipo_emoji"] = evp["equipo_marca"].map({"INTER": "🟢 INTER", "RIVAL": "🔴 RIVAL"})
                cols_ev = ["minuto", "marcador", "equipo_emoji", "accion",
                           "goleador", "asistente", "portero", "cuarteto", "descripcion"]
                cols_ev = [c for c in cols_ev if c in evp.columns]
                cc_ev = {
                    "minuto": st.column_config.NumberColumn("Min", help="Minuto del partido", format="%d"),
                    "marcador": st.column_config.Column("Marcador", help="Marcador acumulado"),
                    "equipo_emoji": st.column_config.Column("Equipo", help="Equipo que marcó"),
                    "accion": st.column_config.Column("Acción", help=TOOLTIPS_COLS["accion"]),
                    "goleador": st.column_config.Column("Goleador"),
                    "asistente": st.column_config.Column("Asistente"),
                    "portero": st.column_config.Column("Portero", help="Portero que estaba en pista"),
                    "cuarteto": st.column_config.Column("Cuarteto", help="Jugadores de campo en pista"),
                    "descripcion": st.column_config.Column("Descripción", help=TOOLTIPS_COLS["descripcion"], width="medium"),
                }
                st.dataframe(evp[cols_ev], use_container_width=True, hide_index=True,
                             column_config=cc_ev)
    
            # ── Goles por intervalos de 5' (lado a lado) ────────────────────────
            st.markdown("#### 📈 Goles por intervalos de 5 minutos")
            if ev_p.empty:
                st.caption("Sin datos.")
            else:
                orden_ints = ["0-5", "5-10", "10-15", "15-20",
                              "20-25", "25-30", "30-35", "35-40"]
                piv = (ev_p.groupby(["intervalo_5min", "equipo_marca"])
                       .size().unstack(fill_value=0).reindex(orden_ints, fill_value=0))
                for col in ("INTER", "RIVAL"):
                    if col not in piv.columns:
                        piv[col] = 0
                piv = piv[["INTER", "RIVAL"]].rename(columns={"INTER": "A favor", "RIVAL": "En contra"})
                # Barras LADO A LADO con altair (no apiladas)
                try:
                    import altair as alt
                    long = piv.reset_index().melt("intervalo_5min", var_name="Tipo", value_name="Goles")
                    ch = (alt.Chart(long).mark_bar()
                          .encode(
                              x=alt.X("intervalo_5min:O", sort=orden_ints, title="Intervalo (min)"),
                              xOffset="Tipo:N",
                              y=alt.Y("Goles:Q"),
                              color=alt.Color("Tipo:N", scale=alt.Scale(
                                  domain=["A favor", "En contra"],
                                  range=["#2E7D32", "#B71C1C"])),
                              tooltip=["intervalo_5min", "Tipo", "Goles"],
                          ).properties(height=280))
                    st.altair_chart(ch, use_container_width=True)
                except Exception:
                    st.bar_chart(piv)

            # ── Mapas SVG del partido (zonas + portería) ────────────────────
            if not est_disparos_zonas.empty:
                # Match robusto rival+fecha. Estrategias:
                #  1) primer token (>=4 letras) + fecha
                #  2) cualquier token + fecha
                #  3) solo fecha (último recurso)
                meta_rival = str(meta.get("rival", "")).upper().strip()
                meta_fecha = str(meta.get("fecha", "")).strip()
                edz = est_disparos_zonas.copy()
                edz["rival_up"] = edz["rival"].astype(str).str.upper().str.strip()
                edz["fecha_str"] = edz["fecha"].astype(str).str.strip()
                rival_tokens = [t for t in meta_rival.replace("-", " ").split()
                                  if len(t) >= 4]
                edz_match = pd.DataFrame()
                # Estrategia 1+2: token + fecha
                for t in rival_tokens:
                    edz_match = edz[
                        (edz["rival_up"].str.contains(t, na=False, regex=False)) &
                        (edz["fecha_str"] == meta_fecha)
                    ]
                    if not edz_match.empty:
                        break
                # Estrategia 3: solo fecha
                if edz_match.empty and meta_fecha:
                    edz_match = edz[edz["fecha_str"] == meta_fecha]
                if not edz_match.empty:
                    fila_z = edz_match.iloc[0]
                    st.markdown("---")
                    st.markdown("#### 🎯 Zonas y portería de este partido")
                    st.caption("Visualización de cuadrantes (P1-P9) y zonas del campo (A1-A11) según los disparos y goles del partido.")

                    # Construir dicts para los SVG. Para portería usamos
                    # los GOLES (G_AF_P1..) y para campo también goles.
                    af_port = {f"P{i}": (lambda _v: int(_v) if pd.notna(_v) else 0)(pd.to_numeric(fila_z.get(f"G_AF_P{i}", 0), errors="coerce")) for i in range(1, 10)}
                    af_zona = {f"A{i}": (lambda _v: int(_v) if pd.notna(_v) else 0)(pd.to_numeric(fila_z.get(f"G_AF_Z{i}", 0), errors="coerce")) for i in range(1, 12)}
                    ec_port = {f"P{i}": (lambda _v: int(_v) if pd.notna(_v) else 0)(pd.to_numeric(fila_z.get(f"G_EC_P{i}", 0), errors="coerce")) for i in range(1, 10)}
                    ec_zona = {f"A{i}": (lambda _v: int(_v) if pd.notna(_v) else 0)(pd.to_numeric(fila_z.get(f"G_EC_Z{i}", 0), errors="coerce")) for i in range(1, 12)}

                    sub_af_p, sub_ec_p = st.tabs([
                        "⚽ Goles a Favor",
                        "🥅 Goles en Contra",
                    ])
                    with sub_af_p:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Campo · zonas desde donde marcamos**")
                            st.markdown(generar_svg_campo(af_zona), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Portería · cuadrantes donde entran nuestros goles**")
                            st.markdown(generar_svg_porteria(af_port), unsafe_allow_html=True)
                    with sub_ec_p:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Campo · zonas desde donde nos disparan al gol**")
                            st.markdown(generar_svg_campo(ec_zona), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Portería · cuadrantes por donde nos meten goles**")
                            st.markdown(generar_svg_porteria(ec_port), unsafe_allow_html=True)
                else:
                    st.markdown("---")
                    st.warning(
                        f"🎯 **No se encontró fila en EST_DISPAROS_ZONAS** "
                        f"para `{meta.get('rival', '')}` · `{meta_fecha}`. "
                        f"Si el partido es reciente, reejecuta "
                        f"`/usr/bin/python3 src/estadisticas_disparos.py --upload`."
                    )


    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 🎮 Partido: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 10 — 📊 EQUIPO (TOTAL) — ranking masivo con todas las métricas
# ═══════════════════════════════════════════════════════════════════════════════
with tab_equipo:
    try:
        if est_partidos.empty:
            st.info("Sin datos. Ejecuta el extractor primero.")
        else:
            st.markdown("### 📊 Equipo — vista global")
            st.caption(
                "Ranking de jugadores con TODAS las métricas. Filtros disponibles arriba: "
                "competición, fechas y jugadores."
            )
    
            ep = _est_num(est_partidos)
            ev = est_eventos.copy() if not est_eventos.empty else pd.DataFrame()
            if not ev.empty:
                ev["minuto"] = pd.to_numeric(ev["minuto"], errors="coerce")
    
            # Filtros locales
            f1, f2, f3 = st.columns([2, 2, 3])
            comp_op = ["TODAS"] + sorted(ep["tipo"].dropna().unique().tolist())
            sel_comp = f1.selectbox("Competición", comp_op, key="eq_comp")
    
            # Rango fechas
            ep["_fdate"] = pd.to_datetime(ep["fecha"], errors="coerce")
            fmin, fmax = ep["_fdate"].min(), ep["_fdate"].max()
            if pd.notna(fmin) and pd.notna(fmax):
                r = f2.date_input("Rango fechas",
                                  value=(fmin.date(), fmax.date()),
                                  min_value=fmin.date(), max_value=fmax.date(),
                                  key="eq_fechas")
                if isinstance(r, tuple) and len(r) == 2:
                    ep = ep[(ep["_fdate"] >= pd.Timestamp(r[0])) & (ep["_fdate"] <= pd.Timestamp(r[1]))]
    
            jug_op = sorted(ep["jugador"].dropna().unique().tolist())
            sel_jug = f3.multiselect("Jugadores", jug_op, default=jug_op, key="eq_jug")
    
            ep_f = ep.copy()
            if sel_comp != "TODAS":
                ep_f = ep_f[ep_f["tipo"] == sel_comp]
            if sel_jug:
                ep_f = ep_f[ep_f["jugador"].isin(sel_jug)]
    
            if ep_f.empty:
                st.warning("Sin datos para los filtros aplicados.")
            else:
                # Filtrar eventos al mismo conjunto de partidos para +/-
                partidos_set = set(ep_f["partido_id"].unique())
                ev_f = ev[ev["partido_id"].isin(partidos_set)] if not ev.empty else pd.DataFrame()
    
                # Agregado por jugador
                agr = ep_f.groupby("jugador", as_index=False).agg(
                    partidos_conv=("convocado", "sum"),
                    partidos_jug=("participa", "sum"),
                    min_total=("min_total", "sum"),
                    pf=("pf", "sum"), pnf=("pnf", "sum"),
                    robos=("robos", "sum"), cortes=("cortes", "sum"),
                    bdg=("bdg", "sum"), bdp=("bdp", "sum"),
                    dp=("dp", "sum"), dpalo=("dpalo", "sum"),
                    db=("db", "sum"), df=("df", "sum"),
                    goles=("goles_a_favor", "sum"),
                    asists=("asistencias", "sum"),
                )
                agr["min_partido"] = (agr["min_total"] / agr["partidos_jug"].clip(lower=1)).round(1)
                agr["dt"] = agr["dp"] + agr["dpalo"] + agr["db"] + agr["df"]
                agr["dif_rec_per"] = agr["robos"] + agr["cortes"] - (agr["pf"] + agr["pnf"])
                agr["dif_bd"] = agr["bdg"] - agr["bdp"]
                agr["g+a"] = agr["goles"] + agr["asists"]
                agr["pct_dp_total"] = (agr["dp"] / agr["dt"].replace(0, np.nan) * 100).round(1)
    
                # +/- desde eventos
                plusminus = []
                for j in agr["jugador"]:
                    if ev_f.empty:
                        plusminus.append({"jugador": j, "gf_pista": 0, "gc_pista": 0, "plus_minus": 0})
                        continue
                    mask = ev_f.apply(
                        lambda r: (j in str(r.get("cuarteto", "")).split("|")) or (str(r.get("portero", "")) == j), axis=1
                    )
                    af = ((ev_f["equipo_marca"] == "INTER") & mask).sum()
                    ec = ((ev_f["equipo_marca"] == "RIVAL") & mask).sum()
                    plusminus.append({"jugador": j, "gf_pista": int(af), "gc_pista": int(ec), "plus_minus": int(af - ec)})
                agr = agr.merge(pd.DataFrame(plusminus), on="jugador", how="left")
    
                # % del equipo y por minuto jugado
                min_eq = agr["min_total"].sum()
                tot = {c: agr[c].sum() for c in ["goles", "asists", "robos", "cortes", "pf", "pnf", "dp", "dt"]}
                agr["%_min_eq"] = (agr["min_total"] / max(min_eq, 1) * 100).round(1)
                agr["%_goles_eq"] = (agr["goles"] / max(tot["goles"], 1) * 100).round(1)
                agr["%_asists_eq"] = (agr["asists"] / max(tot["asists"], 1) * 100).round(1)
                agr["%_robos_eq"] = (agr["robos"] / max(tot["robos"], 1) * 100).round(1)
                agr["%_dp_eq"] = (agr["dp"] / max(tot["dp"], 1) * 100).round(1)
    
                # Por minuto jugado (clave 1/min para evitar dividir por 0)
                inv_min = 1 / agr["min_total"].clip(lower=1)
                agr["robos/min"] = (agr["robos"] * inv_min).round(3)
                agr["cortes/min"] = (agr["cortes"] * inv_min).round(3)
                agr["pf/min"] = (agr["pf"] * inv_min).round(3)
                agr["pnf/min"] = (agr["pnf"] * inv_min).round(3)
                agr["dp/min"] = (agr["dp"] * inv_min).round(3)
                agr["goles/min"] = (agr["goles"] * inv_min).round(3)
    
                # Por 40' (un partido)
                f40 = 40 * inv_min
                agr["goles/40"] = (agr["goles"] * f40).round(2)
                agr["asists/40"] = (agr["asists"] * f40).round(2)
                agr["g+a/40"] = (agr["g+a"] * f40).round(2)
    
                agr = agr.sort_values("goles", ascending=False)
    
                # Helper para construir column_config con tooltip
                def _cc(*cols):
                    return {c: st.column_config.Column(help=TOOLTIPS_COLS.get(c, ""))
                            for c in cols if TOOLTIPS_COLS.get(c)}
    
                # Tabs internos para no agobiar
                sub_total, sub_pct, sub_min = st.tabs(["📋 Totales", "📊 % vs Equipo", "⏱ Por minuto / por 40'"])
    
                with sub_total:
                    cols_t = ["jugador", "partidos_conv", "partidos_jug", "min_total", "min_partido",
                              "pf", "pnf", "robos", "cortes", "dif_rec_per",
                              "bdg", "bdp", "dif_bd",
                              "dp", "dpalo", "db", "df", "dt", "pct_dp_total",
                              "goles", "asists", "g+a",
                              "gf_pista", "gc_pista", "plus_minus"]
                    cols_t = [c for c in cols_t if c in agr.columns]
                    df_t = agr[cols_t]
                    # Semáforo sutil por columna numérica
                    num_cols_t = [c for c in cols_t if c not in ("jugador",)]
                    sty_t = df_t.style.format({
                        "min_total": "{:.0f}", "min_partido": "{:.1f}",
                        "pct_dp_total": "{:.1f}%",
                    }, na_rep="—")
                    sty_t = _gradiente_sutil(sty_t, num_cols_t)
                    st.dataframe(sty_t, use_container_width=True, hide_index=True,
                                 column_config=_cc(*cols_t))
    
                with sub_pct:
                    cols_p = ["jugador", "partidos_jug", "min_total",
                              "%_min_eq", "%_goles_eq", "%_asists_eq", "%_robos_eq", "%_dp_eq"]
                    cols_p = [c for c in cols_p if c in agr.columns]
                    df_p = agr[cols_p]
                    num_cols_p = [c for c in cols_p if c not in ("jugador",)]
                    sty_p = df_p.style.format({
                        "min_total": "{:.0f}",
                        "%_min_eq": "{:.1f}%", "%_goles_eq": "{:.1f}%",
                        "%_asists_eq": "{:.1f}%", "%_robos_eq": "{:.1f}%",
                        "%_dp_eq": "{:.1f}%",
                    }, na_rep="—")
                    sty_p = _gradiente_sutil(sty_p, num_cols_p)
                    st.dataframe(sty_p, use_container_width=True, hide_index=True,
                                 column_config=_cc(*cols_p))
    
                with sub_min:
                    cols_m = ["jugador", "partidos_jug", "min_total",
                              "goles/40", "asists/40", "g+a/40",
                              "robos/min", "cortes/min", "pf/min", "pnf/min", "dp/min",
                              "plus_minus"]
                    cols_m = [c for c in cols_m if c in agr.columns]
                    df_m = agr[cols_m]
                    num_cols_m = [c for c in cols_m if c not in ("jugador",)]
                    sty_m = df_m.style.format({
                        "min_total": "{:.0f}",
                        "goles/40": "{:.2f}", "asists/40": "{:.2f}", "g+a/40": "{:.2f}",
                        "robos/min": "{:.3f}", "cortes/min": "{:.3f}",
                        "pf/min": "{:.3f}", "pnf/min": "{:.3f}", "dp/min": "{:.3f}",
                        "plus_minus": "{:+.0f}",
                    }, na_rep="—")
                    sty_m = _gradiente_sutil(sty_m, num_cols_m)
                    st.dataframe(sty_m, use_container_width=True, hide_index=True,
                                 column_config=_cc(*cols_m))
    
    
    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 📊 Equipo: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 12 — 🥅 GOLES (tabla detallada + 5min lado a lado + cuartetos completos)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_goles:
    try:
        if est_eventos.empty:
            st.info("Sin eventos de gol. Ejecuta `estadisticas_partidos.py --upload`.")
        else:
            st.markdown("### 🥅 Goles del equipo")
            st.caption("Vista detallada de cada gol y de los cuartetos en pista.")
    
            ev = est_eventos.copy()
            ev["minuto"] = pd.to_numeric(ev["minuto"], errors="coerce")
    
            # Filtros
            c1, c2 = st.columns(2)
            comp_op = sorted(ev["tipo"].dropna().unique().tolist())
            sel_comp = c1.multiselect(
                "Competiciones", comp_op,
                default=comp_op,
                key="g_comp_multi",
                help="Puedes elegir varias. Por defecto se muestran todas. "
                     "Deselecciona las que no quieras ver.",
            )
            eq_op = ["TODOS", "A FAVOR (INTER)", "EN CONTRA (RIVAL)"]
            sel_eq = c2.selectbox("Equipo", eq_op, key="g_eq")

            ev_f = ev.copy()
            if sel_comp:
                ev_f = ev_f[ev_f["tipo"].isin(sel_comp)]
            else:
                # Sin ninguna competición seleccionada → vacío (no mostrar nada)
                ev_f = ev_f.iloc[0:0]
            if sel_eq == "A FAVOR (INTER)":
                ev_f = ev_f[ev_f["equipo_marca"] == "INTER"]
            elif sel_eq == "EN CONTRA (RIVAL)":
                ev_f = ev_f[ev_f["equipo_marca"] == "RIVAL"]
    
            # ── Goles por intervalos de 5 min — LADO A LADO ─────────────────────
            st.markdown("#### Goles por intervalo de 5 minutos")
            # Respeta el filtro de competiciones (sel_comp) pero no el de
            # equipo, porque el chart muestra A favor + En contra a la vez.
            ev_chart = ev.copy()
            if sel_comp:
                ev_chart = ev_chart[ev_chart["tipo"].isin(sel_comp)]
            else:
                ev_chart = ev_chart.iloc[0:0]
            orden_ints = ["0-5", "5-10", "10-15", "15-20",
                          "20-25", "25-30", "30-35", "35-40"]
            piv5 = (ev_chart.groupby(["intervalo_5min", "equipo_marca"]).size()
                    .unstack(fill_value=0).reindex(orden_ints, fill_value=0))
            for col in ("INTER", "RIVAL"):
                if col not in piv5.columns:
                    piv5[col] = 0
            piv5 = piv5[["INTER", "RIVAL"]].rename(columns={"INTER": "A favor", "RIVAL": "En contra"})
            try:
                import altair as alt
                long5 = piv5.reset_index().melt("intervalo_5min", var_name="Tipo", value_name="Goles")
                ch5 = (alt.Chart(long5).mark_bar()
                       .encode(
                           x=alt.X("intervalo_5min:O", sort=orden_ints, title="Intervalo"),
                           xOffset="Tipo:N",
                           y="Goles:Q",
                           color=alt.Color("Tipo:N", scale=alt.Scale(
                               domain=["A favor", "En contra"],
                               range=["#2E7D32", "#B71C1C"])),
                           tooltip=["intervalo_5min", "Tipo", "Goles"],
                       ).properties(height=320))
                st.altair_chart(ch5, use_container_width=True)
            except Exception:
                st.bar_chart(piv5)
    
            st.markdown("---")
    
            # ── Tabla de goles con descripción ──────────────────────────────────
            st.markdown(f"#### Tabla de goles ({len(ev_f)} eventos)")
            cols_g = ["partido_id", "tipo", "rival", "fecha", "minuto", "marcador",
                      "equipo_marca", "accion", "goleador", "asistente", "portero",
                      "cuarteto", "descripcion"]
            cols_g = [c for c in cols_g if c in ev_f.columns]
            st.dataframe(
                ev_f[cols_g].sort_values(["fecha", "minuto"]),
                use_container_width=True, hide_index=True,
                column_config={
                    "minuto": st.column_config.NumberColumn("minuto", help="Minuto del partido", format="%d"),
                    "descripcion": st.column_config.Column("descripción", help=TOOLTIPS_COLS["descripcion"], width="medium"),
                    **{c: st.column_config.Column(help=TOOLTIPS_COLS.get(c, ""))
                       for c in cols_g if c in TOOLTIPS_COLS and c not in ("minuto", "descripcion")},
                },
            )
    
            st.markdown("---")
    
            # ── Combinaciones (tríos / cuartetos / quintetos) ───────────────────
            st.markdown("#### Combinaciones de jugadores en pista")
            st.caption("Filtra por tamaño de la combinación, si incluir o no al portero, "
                       "y la situación del gol. Útil para ver qué tríos/cuartetos/quintetos "
                       "funcionan mejor en cada tipo de jugada.")

            col_a, col_b, col_c = st.columns([2, 2, 2])
            tamanos = col_a.multiselect(
                "Tamaño combinación", [3, 4, 5], default=[4, 5],
                key="g_cuart_tam",
                help="3 = trío, 4 = cuarteto, 5 = quinteto. Puedes elegir varios."
            )
            incluir_portero = col_b.radio(
                "Incluir portero", ["Sí", "No"], horizontal=True, key="g_cuart_port",
                help="Si elijes 'No' la combinación se calcula solo con los jugadores de campo."
            )
            min_evt = col_c.slider(
                "Mostrar solo combinaciones con al menos X eventos", 1, 10, 1,
                key="g_cuart_min"
            )

            # Filtro adicional: situación de gol (acción)
            acciones_disp = sorted([a for a in ev["accion"].dropna().astype(str).unique() if a.strip()])
            sel_acciones = st.multiselect(
                "Situación de gol",
                acciones_disp,
                default=acciones_disp,
                key="g_cuart_accion",
                help="Filtra por tipo de jugada (Banda, Córner, 4x4, Contraataque...). "
                     "Por defecto se muestran todas. Deselecciona las que no te interesen.",
            )

            # Generar TODAS las combinaciones de tamaño N a partir de los
            # jugadores en pista en cada evento.
            # Lógica:
            # - "Incluir portero = Sí": solo eventos con portero canónico, y
            #   las combinaciones generadas DEBEN incluir al portero.
            # - "Incluir portero = No": solo jugadores de campo.
            from itertools import combinations as _combos
            _PORTEROS_CANON = {"J.HERRERO", "J.GARCIA", "OSCAR", "HERRERO", "GARCIA"}

            ev_for_q = ev.copy()
            # Aplicar filtro de situación de gol
            if sel_acciones:
                ev_for_q = ev_for_q[ev_for_q["accion"].astype(str).isin(sel_acciones)]
            else:
                ev_for_q = ev_for_q.iloc[0:0]
            ev_for_q["portero"] = ev_for_q["portero"].fillna("").astype(str)
            ev_for_q["cuarteto"] = ev_for_q["cuarteto"].fillna("").astype(str)
            incl = (incluir_portero == "Sí")

            registros = []
            for _, r in ev_for_q.iterrows():
                cuart = list(filter(None, r["cuarteto"].split("|")))
                portero_ev = r["portero"].strip().upper() if r["portero"] else ""
                portero_valido = portero_ev in _PORTEROS_CANON

                if incl:
                    if not portero_valido:
                        continue
                    pool = sorted(set(cuart + [portero_ev]))
                else:
                    pool = sorted(set(cuart))
                em = r["equipo_marca"]
                for n in tamanos or [3, 4, 5]:
                    if n <= len(pool):
                        for combo in _combos(pool, n):
                            if incl and portero_ev not in combo:
                                continue
                            registros.append({
                                "formacion": " | ".join(combo),
                                "tamano": n,
                                "equipo_marca": em,
                            })

            if not registros:
                st.warning("Sin combinaciones para los filtros aplicados.")
            else:
                df_reg = pd.DataFrame(registros)
                agr_q = df_reg.groupby(["formacion", "tamano"], as_index=False).agg(
                    n_eventos=("formacion", "count"),
                    goles_a_favor=("equipo_marca", lambda s: (s == "INTER").sum()),
                    goles_en_contra=("equipo_marca", lambda s: (s == "RIVAL").sum()),
                )
                agr_q["plus_minus"] = agr_q["goles_a_favor"] - agr_q["goles_en_contra"]
                agr_q = agr_q.sort_values(
                    ["plus_minus", "n_eventos"], ascending=[False, False]
                )
                agr_q_f = agr_q[agr_q["n_eventos"] >= min_evt]
                st.caption(
                    f"{len(agr_q_f)} combinaciones / {len(agr_q)} totales · "
                    f"{len(registros)} apariciones contadas"
                )

                sty_q = agr_q_f.style.format({
                    "tamano": "{:.0f}", "n_eventos": "{:.0f}",
                    "goles_a_favor": "{:.0f}", "goles_en_contra": "{:.0f}",
                    "plus_minus": "{:+.0f}",
                })
                if "plus_minus" in agr_q_f.columns:
                    css_pm = _aplicar_gradient_columna(agr_q_f, "plus_minus")
                    sty_q = sty_q.apply(
                        lambda s: css_pm.reindex(s.index, fill_value="").tolist(),
                        subset=["plus_minus"], axis=0,
                    )
                st.dataframe(sty_q, use_container_width=True, hide_index=True,
                             column_config={
                                 "formacion": st.column_config.Column("Combinación", help="Jugadores en pista (orden alfabético)"),
                                 "tamano": st.column_config.NumberColumn("Nº", help="Número de jugadores en la combinación"),
                                 "n_eventos": st.column_config.NumberColumn("Eventos", help="Veces que esta combinación estuvo en pista cuando hubo gol"),
                                 "goles_a_favor": st.column_config.NumberColumn("GF", help="Goles a favor con esta combinación"),
                                 "goles_en_contra": st.column_config.NumberColumn("GC", help="Goles en contra con esta combinación"),
                                 "plus_minus": st.column_config.NumberColumn("+/-", help="GF − GC"),
                             })

            # ── Mapas globales de zona y portería (Inter) ──────────────────
            if not est_disparos_zonas.empty:
                st.markdown("---")
                st.markdown("#### 🎯 Mapas de zona del Inter")
                st.caption(
                    "Agrega TODOS los partidos. Filtra por competición y/o "
                    "rango de fechas para ver patrones."
                )
                edz = est_disparos_zonas.copy()
                edz["_fdate"] = pd.to_datetime(edz["fecha"], errors="coerce")

                # Filtros
                fc1, fc2 = st.columns([2, 3])
                comp_op_z = ["TODAS"] + sorted(edz["competicion"].dropna().unique().tolist())
                sel_comp_z = fc1.selectbox("Competición", comp_op_z, key="goles_zonas_comp")
                fmin_z = edz["_fdate"].min()
                fmax_z = edz["_fdate"].max()
                if pd.notna(fmin_z) and pd.notna(fmax_z):
                    rango_z = fc2.date_input(
                        "Rango fechas",
                        value=(fmin_z.date(), fmax_z.date()),
                        min_value=fmin_z.date(), max_value=fmax_z.date(),
                        key="goles_zonas_fechas",
                    )
                    if isinstance(rango_z, tuple) and len(rango_z) == 2:
                        edz = edz[
                            (edz["_fdate"] >= pd.Timestamp(rango_z[0])) &
                            (edz["_fdate"] <= pd.Timestamp(rango_z[1]))
                        ]
                if sel_comp_z != "TODAS":
                    edz = edz[edz["competicion"] == sel_comp_z]

                if edz.empty:
                    st.warning("Sin datos para los filtros aplicados.")
                else:
                    # Sumar todos los partidos del subset
                    af_port_g = {f"P{i}": int(pd.to_numeric(edz[f"G_AF_P{i}"], errors="coerce").fillna(0).sum()) for i in range(1, 10)}
                    af_zona_g = {f"A{i}": int(pd.to_numeric(edz[f"G_AF_Z{i}"], errors="coerce").fillna(0).sum()) for i in range(1, 12)}
                    ec_port_g = {f"P{i}": int(pd.to_numeric(edz[f"G_EC_P{i}"], errors="coerce").fillna(0).sum()) for i in range(1, 10)}
                    ec_zona_g = {f"A{i}": int(pd.to_numeric(edz[f"G_EC_Z{i}"], errors="coerce").fillna(0).sum()) for i in range(1, 12)}

                    st.caption(f"Datos agregados de {len(edz)} partido(s).")

                    sub_af_g, sub_ec_g = st.tabs([
                        "⚽ Cómo metemos goles",
                        "🥅 Cómo recibimos goles",
                    ])
                    with sub_af_g:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Campo · zonas desde donde marcamos**")
                            st.markdown(generar_svg_campo(af_zona_g), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Portería · cuadrantes donde entran nuestros goles**")
                            st.markdown(generar_svg_porteria(af_port_g), unsafe_allow_html=True)
                    with sub_ec_g:
                        cA, cB = st.columns([3, 2])
                        with cA:
                            st.markdown("**Campo · zonas desde donde nos disparan**")
                            st.markdown(generar_svg_campo(ec_zona_g), unsafe_allow_html=True)
                        with cB:
                            st.markdown("**Portería · cuadrantes por donde nos meten goles**")
                            st.markdown(generar_svg_porteria(ec_port_g), unsafe_allow_html=True)


    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 🥅 Goles: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 13 — 🏅 POR COMPETICIÓN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_comp:
    try:
        if est_partidos.empty:
            st.info("Sin datos.")
        else:
            st.markdown("### 🏅 Estadísticas por competición")
            st.caption("Convocatorias, participaciones, minutos, goles y asistencias por competición × jugador.")
    
            ep = _est_num(est_partidos)
    
            agr_c = ep.groupby(["tipo", "jugador"], as_index=False).agg(
                convocatorias=("convocado", "sum"),
                participa=("participa", "sum"),
                min_total=("min_total", "sum"),
                goles=("goles_a_favor", "sum"),
                asists=("asistencias", "sum"),
            )
            agr_c["min_por_partido"] = (agr_c["min_total"] / agr_c["participa"].clip(lower=1)).round(1)
            agr_c["g+a"] = agr_c["goles"] + agr_c["asists"]
    
            # Selector de competición
            comps = sorted(agr_c["tipo"].dropna().unique().tolist())
            for comp in comps:
                sub = agr_c[agr_c["tipo"] == comp].sort_values("goles", ascending=False)
                with st.expander(f"📌 {comp} — {sub['participa'].sum()} participaciones · {sub['goles'].sum()} goles", expanded=(comp == "LIGA")):
                    cols_c = ["jugador", "convocatorias", "participa", "min_total",
                              "min_por_partido", "goles", "asists", "g+a"]
                    st.dataframe(
                        sub[cols_c].style.format({
                            "convocatorias": "{:.0f}", "participa": "{:.0f}",
                            "min_total": "{:.0f}", "min_por_partido": "{:.1f}",
                            "goles": "{:.0f}", "asists": "{:.0f}", "g+a": "{:.0f}",
                        }),
                        use_container_width=True, hide_index=True,
                    )
    
    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 🏅 Competición: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 15 — 🟨 FALTAS Y PENALTIS (vista global)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_falt_pen:
    try:
        st.markdown("### 🎯 10 metros / Penaltis — Histórico")
        st.caption(
            "Vista agregada de todas las faltas y penaltis/10m de la "
            "temporada. Los datos se rellenan desde la pestaña ✏️ Editar "
            "partido."
        )

        if est_faltas.empty and est_penaltis.empty:
            st.info(
                "No hay datos en `EST_FALTAS` ni `EST_PENALTIS_10M` todavía. "
                "Para empezar a verlos aquí, ve a **✏️ Editar partido**, "
                "selecciona un partido y rellena las secciones de Faltas y "
                "Penaltis y guarda."
            )
        else:
            sub_falt, sub_pen = st.tabs(["🟨 Faltas", "🎯 10 metros / Penaltis"])

            # ── SUB: FALTAS ─────────────────────────────────────────────
            with sub_falt:
                if est_faltas.empty:
                    st.info("Aún no hay faltas registradas.")
                else:
                    df_f = est_faltas.copy()
                    # Resumen general
                    n_total = len(df_f)
                    n_av = int((df_f["condicion"] == "A_FAVOR").sum())
                    n_ec = int((df_f["condicion"] == "EN_CONTRA").sum())
                    n_10m = int((df_f.get("genera_10m", "").astype(str).str.upper() == "TRUE").sum())
                    cols_kpi = st.columns(4)
                    cols_kpi[0].metric("Total faltas", n_total)
                    cols_kpi[1].metric("A favor (rival comete)", n_av)
                    cols_kpi[2].metric("En contra (Inter comete)", n_ec)
                    cols_kpi[3].metric("Generaron 10m", n_10m)

                    st.markdown("#### 🏃 Ranking — faltas COMETIDAS por jugador del Inter")
                    df_ec = df_f[df_f["condicion"] == "EN_CONTRA"]
                    if not df_ec.empty:
                        rank_ec = (df_ec.groupby("jugador").size()
                                   .reset_index(name="faltas_cometidas")
                                   .sort_values("faltas_cometidas", ascending=False))
                        st.dataframe(rank_ec, use_container_width=True, hide_index=True)
                    else:
                        st.caption("Sin faltas en contra registradas.")

                    st.markdown("#### 🤕 Ranking — faltas RECIBIDAS por jugador del Inter")
                    df_av = df_f[df_f["condicion"] == "A_FAVOR"]
                    if not df_av.empty:
                        rank_av = (df_av.groupby("jugador").size()
                                   .reset_index(name="faltas_recibidas")
                                   .sort_values("faltas_recibidas", ascending=False))
                        st.dataframe(rank_av, use_container_width=True, hide_index=True)
                    else:
                        st.caption("Sin faltas a favor registradas.")

                    st.markdown("#### 📋 Histórico completo")
                    cols_show_f = ["partido_id", "rival", "fecha", "parte",
                                    "minuto_mmss", "condicion", "jugador",
                                    "num_falta", "genera_10m", "descripcion"]
                    cols_show_f = [c for c in cols_show_f if c in df_f.columns]
                    df_f_show = df_f[cols_show_f].copy()
                    df_f_show["genera_10m"] = df_f_show["genera_10m"].astype(str).str.upper().map(
                        lambda v: "⚠️ 10M" if v == "TRUE" else "")
                    df_f_show = df_f_show.sort_values(["fecha", "parte", "minuto_mmss"],
                                                        ascending=[False, True, True])
                    st.dataframe(df_f_show, use_container_width=True, hide_index=True)

            # ── SUB: PENALTIS Y 10M ─────────────────────────────────────
            with sub_pen:
                if est_penaltis.empty:
                    st.info("Aún no hay penaltis/10m registrados.")
                else:
                    df_p = est_penaltis.copy()
                    n_total = len(df_p)
                    n_pen = int((df_p["tipo_lanzamiento"] == "PENALTI").sum())
                    n_10m = int((df_p["tipo_lanzamiento"] == "10M").sum())
                    n_av = int((df_p["condicion"] == "A_FAVOR").sum())
                    n_ec = int((df_p["condicion"] == "EN_CONTRA").sum())
                    n_gol = int((df_p["resultado"] == "GOL").sum())
                    cols_kpi = st.columns(5)
                    cols_kpi[0].metric("Total", n_total)
                    cols_kpi[1].metric("Penaltis", n_pen)
                    cols_kpi[2].metric("10m", n_10m)
                    cols_kpi[3].metric("A favor", n_av)
                    cols_kpi[4].metric("En contra", n_ec)

                    # ── A favor: nuestros lanzadores ──────────────────────
                    df_av = df_p[df_p["condicion"] == "A_FAVOR"]
                    if not df_av.empty:
                        st.markdown("#### ⚽ A favor — nuestros lanzadores")
                        rank_av = (df_av.groupby("lanzador")
                                   .agg(intentos=("resultado", "count"),
                                        goles=("resultado", lambda s: (s == "GOL").sum()),
                                        paradas_rec=("resultado", lambda s: (s == "PARADA").sum()),
                                        postes=("resultado", lambda s: (s == "POSTE").sum()),
                                        fueras=("resultado", lambda s: (s == "FUERA").sum()))
                                   .reset_index())
                        rank_av["pct_acierto"] = (rank_av["goles"] / rank_av["intentos"] * 100).round(1)
                        rank_av = rank_av.sort_values("intentos", ascending=False)
                        st.dataframe(rank_av, use_container_width=True, hide_index=True,
                                      column_config={
                                          "lanzador": "Lanzador",
                                          "intentos": "Intentos",
                                          "goles": "Goles",
                                          "paradas_rec": "Parados",
                                          "postes": "Postes",
                                          "fueras": "Fueras",
                                          "pct_acierto": st.column_config.NumberColumn(
                                              "% acierto", format="%.1f%%"),
                                      })
                        # Mapa de calor de cuadrantes a favor (P1-P9)
                        df_av_p = df_av[df_av["cuadrante"].astype(str).str.match(r"P[1-9]", na=False)]
                        if not df_av_p.empty:
                            st.markdown("##### 🎯 Cuadrantes preferidos (a favor)")
                            cuad_af = df_av_p["cuadrante"].value_counts().reindex(
                                [f"P{i}" for i in range(1, 10)], fill_value=0)
                            mapa_af = {f"P{i}": int(cuad_af.get(f"P{i}", 0)) for i in range(1, 10)}
                            st.markdown(
                                generar_svg_porteria(mapa_af),
                                unsafe_allow_html=True,
                            )

                    # ── En contra: % paradas de nuestros porteros ────────
                    df_ec = df_p[df_p["condicion"] == "EN_CONTRA"]
                    if not df_ec.empty:
                        st.markdown("#### 🧤 En contra — nuestros porteros")
                        rank_ec = (df_ec.groupby("portero")
                                   .agg(recibidos=("resultado", "count"),
                                        parados=("resultado", lambda s: (s == "PARADA").sum()),
                                        goles_enc=("resultado", lambda s: (s == "GOL").sum()),
                                        postes=("resultado", lambda s: (s == "POSTE").sum()),
                                        fueras=("resultado", lambda s: (s == "FUERA").sum()))
                                   .reset_index())
                        rank_ec["pct_parados"] = (
                            rank_ec["parados"] / rank_ec["recibidos"].clip(lower=1) * 100
                        ).round(1)
                        rank_ec = rank_ec.sort_values("recibidos", ascending=False)
                        st.dataframe(rank_ec, use_container_width=True, hide_index=True,
                                      column_config={
                                          "portero": "Portero",
                                          "recibidos": "Recibidos",
                                          "parados": "Parados",
                                          "goles_enc": "Goles enc.",
                                          "postes": "Postes",
                                          "fueras": "Fueras",
                                          "pct_parados": st.column_config.NumberColumn(
                                              "% parados", format="%.1f%%"),
                                      })
                        # Mapa de cuadrantes en contra
                        df_ec_p = df_ec[df_ec["cuadrante"].astype(str).str.match(r"P[1-9]", na=False)]
                        if not df_ec_p.empty:
                            st.markdown("##### 🎯 Cuadrantes recibidos (en contra)")
                            cuad_ec = df_ec_p["cuadrante"].value_counts().reindex(
                                [f"P{i}" for i in range(1, 10)], fill_value=0)
                            mapa_ec = {f"P{i}": int(cuad_ec.get(f"P{i}", 0)) for i in range(1, 10)}
                            st.markdown(
                                generar_svg_porteria(mapa_ec),
                                unsafe_allow_html=True,
                            )

                    st.markdown("#### 📋 Histórico completo")
                    cols_show_p = ["partido_id", "rival", "fecha",
                                    "tipo_lanzamiento", "condicion", "parte",
                                    "minuto_mmss", "marcador", "lanzador",
                                    "portero", "resultado", "cuadrante",
                                    "descripcion"]
                    cols_show_p = [c for c in cols_show_p if c in df_p.columns]
                    df_p_show = df_p[cols_show_p].copy()
                    df_p_show["resultado"] = df_p_show["resultado"].astype(str).map({
                        "GOL": "✅ GOL", "PARADA": "🧤 PARADA",
                        "POSTE": "📌 POSTE", "FUERA": "❌ FUERA",
                    }).fillna(df_p_show["resultado"])
                    df_p_show = df_p_show.sort_values(["fecha", "parte", "minuto_mmss"],
                                                        ascending=[False, True, True])
                    st.dataframe(df_p_show, use_container_width=True, hide_index=True)

    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña 🎯 10 metros / Penaltis: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 16 — ✏️ EDITAR PARTIDO (crear nuevo o editar existente)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_editar:
    try:
        st.markdown("### ✏️ Editar partido")
        st.caption(
            "Crea un partido nuevo o edita uno existente. Los cambios se "
            "guardan directo en el Sheet (hojas EST_PARTIDOS y EST_EVENTOS) "
            "y se reflejan en el resto del dashboard tras refrescar."
        )

        if est_partidos.empty:
            st.info("Aún no hay partidos. Vamos a crear el primero.")

        modo = st.radio(
            "Modo",
            ["📝 Editar partido existente", "🆕 Crear partido nuevo"],
            horizontal=True, key="ed_modo",
        )

        # Helpers comunes
        TIPOS_OPCIONES = ["LIGA", "COPA_REY", "COPA_ESPANA", "COPA_MUNDO",
                          "AMISTOSO", "PLAYOFF", "SUPERCOPA", "OTRO"]
        TIPO_LABEL = {
            "LIGA": "Liga 25/26", "COPA_REY": "Copa del Rey",
            "COPA_ESPANA": "Copa de España", "COPA_MUNDO": "Copa del Mundo",
            "AMISTOSO": "Amistoso", "PLAYOFF": "Playoff Liga",
            "SUPERCOPA": "Supercopa", "OTRO": "Otro",
        }
        # ── Roster maestro (JUGADORES_ROSTER, fuente preferida) ─────────
        # Si la hoja existe se usa; si no, fallback a los nombres
        # extraídos de EST_PARTIDOS (compat antigua).
        if not jugadores_roster.empty:
            roster = jugadores_roster.copy()
            for c in ("nombre", "posicion", "equipo"):
                if c in roster.columns:
                    roster[c] = roster[c].astype(str).str.strip().str.upper()
            if "activo" in roster.columns:
                roster["activo"] = roster["activo"].astype(str).str.upper().isin(
                    ("TRUE", "VERDADERO", "SI", "SÍ", "1", "YES"))
            else:
                roster["activo"] = True
            # Solo activos para los selectores
            roster_activo = roster[roster["activo"]].copy()
            jug_porteros = sorted(roster_activo[
                roster_activo.get("posicion", "") == "PORTERO"
            ]["nombre"].tolist())
            jug_campo = sorted(roster_activo[
                roster_activo.get("posicion", "") == "CAMPO"
            ]["nombre"].tolist())
            jug_conocidos = jug_porteros + jug_campo
        elif not est_partidos.empty:
            jug_conocidos = sorted(est_partidos["jugador"].dropna().unique().tolist())
            jug_porteros = ["J.HERRERO", "J.GARCIA", "OSCAR"]
            jug_campo = [j for j in jug_conocidos if j not in jug_porteros]
            roster_activo = pd.DataFrame()
        else:
            jug_conocidos = []
            jug_porteros = []
            jug_campo = []
            roster_activo = pd.DataFrame()

        def _info_jugador(nombre: str) -> dict:
            """Devuelve dict con dorsal/posicion/equipo del roster, o {} si no existe."""
            if roster_activo.empty:
                return {}
            row = roster_activo[roster_activo["nombre"] == nombre]
            if row.empty:
                return {}
            r = row.iloc[0]
            return {
                "dorsal": r.get("dorsal", ""),
                "posicion": r.get("posicion", ""),
                "equipo": r.get("equipo", ""),
            }

        def _label_jugador(nombre: str) -> str:
            """Etiqueta tipo '#10 · JAVI' para los selectboxes."""
            info = _info_jugador(nombre)
            d = info.get("dorsal", "")
            try:
                d_int = int(float(d)) if d not in ("", None) else None
            except (TypeError, ValueError):
                d_int = None
            if d_int is not None:
                return f"#{d_int} · {nombre}"
            return nombre

        # Lista de acciones canónicas
        ACCIONES = [
            "Banda", "Córner", "Saque de Centro", "Falta", "2ª jugada de ABP",
            "10 metros", "Penalti", "Falta sin barrera", "Ataque Posicional 4x4",
            "1x1 en banda", "Salida de presión", "2ª jugada",
            "Incorporación del portero", "Robo en incorporación de portero",
            "Pérdida en incorporación de portero", "5x4", "4x5", "4x3", "3x4",
            "Contraataque", "Robo en zona alta", "No calificado",
        ]

        def _conexion_sheet():
            """Devuelve un objeto Spreadsheet ya abierto. Reusable por los
            helpers de guardado de la pestaña Editar partido."""
            import gspread
            from google.oauth2.service_account import Credentials
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                       "https://www.googleapis.com/auth/drive"]
            creds_path = Path(__file__).parent.parent / "google_credentials.json"
            if creds_path.exists():
                creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
            else:
                info = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            gc = gspread.authorize(creds)
            return gc.open(SHEET_NAME)

        def _guardar_cabecera_totales(cab, totales_disp=None):
            """Crea/actualiza la fila de EST_TOTALES_PARTIDO para este
            partido_id con los campos extra (categoria, lugar, hora,
            local_visitante, gf, gc). Si se pasa `totales_disp` también
            persiste los 8 totales de disparo por parte (iter 6).
            No toca métricas (dt_inter, etc. globales) cuando ya existían.
            """
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_TOTALES_PARTIDO")
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet("EST_TOTALES_PARTIDO", rows=200, cols=30)
                ws.update(values=[["partido_id"]], range_name="A1")

            df_all = pd.DataFrame(ws.get_all_records())
            cols_completas = list(df_all.columns) if not df_all.empty else [
                "partido_id", "tipo", "competicion", "rival", "fecha",
                "categoria", "lugar", "hora", "local_visitante",
                "goles_a_favor", "goles_en_contra",
            ]
            # Asegurar columnas extra (cabecera + totales por parte iter 6)
            for c in ("categoria", "lugar", "hora", "local_visitante",
                       "goles_a_favor", "goles_en_contra",
                       "dt_inter_1t", "dt_inter_2t",
                       "dp_inter_1t", "dp_inter_2t",
                       "dt_rival_1t", "dt_rival_2t",
                       "dp_rival_1t", "dp_rival_2t"):
                if c not in cols_completas:
                    cols_completas.append(c)

            if df_all.empty:
                df_all = pd.DataFrame(columns=cols_completas)
            else:
                for c in cols_completas:
                    if c not in df_all.columns:
                        df_all[c] = ""

            datos_cab = {
                "partido_id": cab["partido_id"],
                "tipo": cab["tipo"],
                "competicion": cab["competicion"],
                "rival": cab["rival"],
                "fecha": cab["fecha"],
                "categoria": cab["competicion"],
                "lugar": cab["lugar"],
                "hora": cab["hora"],
                "local_visitante": cab["local_visitante"],
                "goles_a_favor": cab["gf"],
                "goles_en_contra": cab["gc"],
            }
            # Totales por parte (iter 6) — solo si se pasaron
            if totales_disp:
                for k in ("dt_inter_1t", "dt_inter_2t",
                            "dp_inter_1t", "dp_inter_2t",
                            "dt_rival_1t", "dt_rival_2t",
                            "dp_rival_1t", "dp_rival_2t"):
                    datos_cab[k] = safe_int(totales_disp.get(k, 0))
                # Si DT 1T+2T están y dt_inter global no, calculamos
                dt_i_glob = safe_int(datos_cab.get("dt_inter_1t", 0)) + \
                              safe_int(datos_cab.get("dt_inter_2t", 0))
                dp_i_glob = safe_int(datos_cab.get("dp_inter_1t", 0)) + \
                              safe_int(datos_cab.get("dp_inter_2t", 0))
                dt_r_glob = safe_int(datos_cab.get("dt_rival_1t", 0)) + \
                              safe_int(datos_cab.get("dt_rival_2t", 0))
                dp_r_glob = safe_int(datos_cab.get("dp_rival_1t", 0)) + \
                              safe_int(datos_cab.get("dp_rival_2t", 0))
                if dt_i_glob > 0:
                    datos_cab["dt_inter"] = dt_i_glob
                if dp_i_glob > 0:
                    datos_cab["dp_inter"] = dp_i_glob
                if dt_r_glob > 0:
                    datos_cab["dt_rival"] = dt_r_glob
                if dp_r_glob > 0:
                    datos_cab["dp_rival"] = dp_r_glob
            mask = df_all["partido_id"].astype(str) == cab["partido_id"]
            # Convertir todas las columnas a object/string para evitar
            # "Invalid value 'X' for dtype 'str'" de pandas 3.x al asignar
            df_all = df_all.astype(object)
            if mask.any():
                # Actualizar campos de cabecera, conservar el resto
                for k, v in datos_cab.items():
                    df_all.loc[mask, k] = str(v) if v not in ("", None) else ""
            else:
                # Nueva fila — rellenar con vacío en columnas que no toco
                fila = {c: "" for c in cols_completas}
                fila.update({k: str(v) if v not in ("", None) else ""
                             for k, v in datos_cab.items()})
                df_all = pd.concat([df_all, pd.DataFrame([fila])],
                                     ignore_index=True)
            df_out = df_all[cols_completas].fillna("")
            ws.clear()
            ws.update(values=[cols_completas] + df_out.astype(str).values.tolist(),
                       range_name="A1")
            return True

        def _guardar_plantilla(partido_id, plantilla, cab):
            """Guarda la plantilla del partido en la hoja EST_PLANTILLAS.
            Una fila por jugador convocado. Si ya existían filas para este
            partido_id se reescriben.
            """
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_PLANTILLAS")
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet("EST_PLANTILLAS", rows=400, cols=10)
                ws.update(values=[["partido_id", "tipo", "competicion", "rival",
                                     "fecha", "dorsal", "jugador", "posicion",
                                     "equipo", "convocado"]],
                          range_name="A1")

            df_all = pd.DataFrame(ws.get_all_records())
            cols = ["partido_id", "tipo", "competicion", "rival", "fecha",
                     "dorsal", "jugador", "posicion", "equipo", "convocado"]
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols)
            else:
                for c in cols:
                    if c not in df_all.columns:
                        df_all[c] = ""
            df_otros = df_all[df_all["partido_id"].astype(str) != partido_id]
            filas = [{
                "partido_id": partido_id,
                "tipo": cab["tipo"],
                "competicion": cab["competicion"],
                "rival": cab["rival"],
                "fecha": cab["fecha"],
                "dorsal": p["dorsal"],
                "jugador": p["jugador"],
                "posicion": p["posicion"],
                "equipo": p["equipo"],
                "convocado": "TRUE",
            } for p in plantilla]
            df_nuevos = pd.DataFrame(filas, columns=cols)
            df_final = pd.concat([df_otros[cols], df_nuevos], ignore_index=True)
            df_final = df_final.fillna("")
            ws.clear()
            ws.update(values=[cols] + df_final.astype(str).values.tolist(),
                       range_name="A1")
            return len(filas)

        def _guardar_eventos(partido_id, tipo, competicion, rival, fecha, df_eventos):
            """Reescribe en EST_EVENTOS los eventos de este partido."""
            import gspread
            from google.oauth2.service_account import Credentials
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                       "https://www.googleapis.com/auth/drive"]
            creds_path = Path(__file__).parent.parent / "google_credentials.json"
            if creds_path.exists():
                creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
            else:
                info = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            gc = gspread.authorize(creds)
            sh = gc.open(SHEET_NAME)
            ws = sh.worksheet("EST_EVENTOS")
            # Leer todo lo existente
            all_records = ws.get_all_records()
            df_all = pd.DataFrame(all_records)
            cols_orden = ["partido_id", "tipo", "competicion", "rival", "fecha",
                          "minuto", "minuto_mmss", "intervalo_5min",
                          "accion_raw", "accion",
                          "marcador", "equipo_marca", "goleador", "asistente",
                          "portero", "cuarteto", "descripcion"]
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols_orden)
            else:
                # Asegurar que df_all tiene todas las columnas (para que el
                # concat con df_nuevos no añada filas vacías)
                for c in cols_orden:
                    if c not in df_all.columns:
                        df_all[c] = ""
            # Filtrar fuera los eventos del partido_id (los reescribimos)
            df_otros = df_all[df_all["partido_id"] != partido_id]
            # Construir nuevos eventos
            df_nuevos = df_eventos.copy()
            df_nuevos["partido_id"] = partido_id
            df_nuevos["tipo"] = tipo
            df_nuevos["competicion"] = competicion
            df_nuevos["rival"] = rival
            df_nuevos["fecha"] = fecha
            # Calcular intervalo_5min
            def _intervalo(m):
                try:
                    m = int(m)
                    if m < 1:
                        return ""
                    base = ((m - 1) // 5) * 5
                    return f"{base}-{base + 5}"
                except (TypeError, ValueError):
                    return ""
            df_nuevos["intervalo_5min"] = df_nuevos["minuto"].apply(_intervalo)
            df_nuevos["accion_raw"] = df_nuevos["accion"]
            for c in cols_orden:
                if c not in df_nuevos.columns:
                    df_nuevos[c] = ""
            df_nuevos = df_nuevos[cols_orden]
            # Concatenar
            df_final = pd.concat([df_otros[cols_orden], df_nuevos], ignore_index=True)
            df_final = df_final.where(pd.notnull(df_final), "")
            # Reescribir
            ws.clear()
            ws.update(values=[cols_orden] + df_final.astype(str).values.tolist(),
                       range_name="A1")
            return len(df_nuevos)

        def _formulario_cabecera(rival_def="", fecha_def=None, comp_def="LIGA",
                                  hora_def="", lugar_def="", gf_def=0, gc_def=0,
                                  partido_id_def="", local_def=None,
                                  key_pref="ed"):
            """Devuelve (rival, fecha, tipo, competicion_legible, hora, lugar, local,
            gf, gc, partido_id) tras un form de cabecera.

            local_def: True/False/None. Si None se intenta autodetectar
            por el lugar (Garbajosa/Madrid → LOCAL).
            """
            colA, colB, colC = st.columns([1.1, 1.1, 1])
            with colA:
                tipo = st.selectbox("Competición", TIPOS_OPCIONES,
                                     index=TIPOS_OPCIONES.index(comp_def) if comp_def in TIPOS_OPCIONES else 0,
                                     format_func=lambda x: TIPO_LABEL.get(x, x),
                                     key=f"{key_pref}_tipo")
                rival = st.text_input("Rival", value=rival_def, key=f"{key_pref}_rival",
                                       placeholder="Ej: BARCELONA, ELPOZO")
                fecha = st.date_input("Fecha", value=fecha_def or _dt.date.today(),
                                       key=f"{key_pref}_fecha")
            with colB:
                hora = st.text_input("Hora", value=hora_def,
                                      placeholder="Ej: 18:00", key=f"{key_pref}_hora")
                lugar = st.text_input(
                    "Lugar", value=lugar_def,
                    placeholder="Ej: Jorge Garbajosa, Pabellón Mahón…",
                    key=f"{key_pref}_lugar",
                )
                # Local/Visitante: opciones AUTO/LOCAL/VISITANTE
                lugar_up = lugar.upper()
                auto_local = any(k in lugar_up for k in
                                  ("MADRID", "MAGARI", "GARBAJOSA", "TORREJON",
                                   "ALCALA", "ALCOBENDAS"))
                if local_def is None:
                    auto_index = 0 if auto_local else 1
                else:
                    auto_index = 0 if local_def else 1
                lv = st.radio("Condición", ["🏠 LOCAL", "✈️ Visitante"],
                                index=auto_index, horizontal=True,
                                key=f"{key_pref}_lv")
                local = "LOCAL" in lv
            with colC:
                colG1, colG2 = st.columns(2)
                gf = colG1.number_input("⚽ GF", min_value=0, max_value=99,
                                          value=int(gf_def), key=f"{key_pref}_gf")
                gc = colG2.number_input("🥅 GC", min_value=0, max_value=99,
                                          value=int(gc_def), key=f"{key_pref}_gc")
                partido_id = st.text_input(
                    "ID del partido", value=partido_id_def,
                    placeholder="Ej: J27.PEÑISCOLA", key=f"{key_pref}_id",
                    help="Identificador único. Suele ser J<n>.RIVAL para liga.",
                )

            return {
                "rival": rival.strip().upper(),
                "fecha": fecha.isoformat() if isinstance(fecha, _dt.date) else "",
                "tipo": tipo,
                "competicion": TIPO_LABEL.get(tipo, tipo),
                "hora": hora.strip(),
                "lugar": lugar.strip(),
                "local": local,
                "local_visitante": "LOCAL" if local else "VISITANTE",
                "gf": int(gf),
                "gc": int(gc),
                "partido_id": partido_id.strip(),
            }

        def _formulario_totales_disparos(tot_pre=None, key_pref="ed"):
            """Editor de totales de disparo del partido por parte (iter 6).
            Devuelve dict con dt_inter_1t, dt_inter_2t, dp_inter_1t,
            dp_inter_2t, dt_rival_1t, dt_rival_2t, dp_rival_1t, dp_rival_2t.
            """
            tot_pre = tot_pre or {}
            with st.expander("📈 Totales de disparo por parte (opcional)",
                              expanded=False):
                st.caption(
                    "Si los rellenas, en los KPIs y el PDF aparecerá "
                    "'Disparos a puerta: 27 (15+12)'. Si los dejas a 0 se "
                    "usan solo los totales del partido completo.")
                cols = st.columns(4)
                with cols[0]:
                    st.markdown("**Inter — DT**")
                    dt_i_1 = st.number_input(
                        "1ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dt_inter_1t", 0)),
                        key=f"{key_pref}_dt_i_1")
                    dt_i_2 = st.number_input(
                        "2ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dt_inter_2t", 0)),
                        key=f"{key_pref}_dt_i_2")
                with cols[1]:
                    st.markdown("**Inter — DP (a puerta)**")
                    dp_i_1 = st.number_input(
                        "1ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dp_inter_1t", 0)),
                        key=f"{key_pref}_dp_i_1")
                    dp_i_2 = st.number_input(
                        "2ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dp_inter_2t", 0)),
                        key=f"{key_pref}_dp_i_2")
                with cols[2]:
                    st.markdown("**Rival — DT**")
                    dt_r_1 = st.number_input(
                        "1ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dt_rival_1t", 0)),
                        key=f"{key_pref}_dt_r_1")
                    dt_r_2 = st.number_input(
                        "2ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dt_rival_2t", 0)),
                        key=f"{key_pref}_dt_r_2")
                with cols[3]:
                    st.markdown("**Rival — DP (a puerta)**")
                    dp_r_1 = st.number_input(
                        "1ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dp_rival_1t", 0)),
                        key=f"{key_pref}_dp_r_1")
                    dp_r_2 = st.number_input(
                        "2ª parte", 0, 99,
                        value=safe_int(tot_pre.get("dp_rival_2t", 0)),
                        key=f"{key_pref}_dp_r_2")
            return {
                "dt_inter_1t": dt_i_1, "dt_inter_2t": dt_i_2,
                "dp_inter_1t": dp_i_1, "dp_inter_2t": dp_i_2,
                "dt_rival_1t": dt_r_1, "dt_rival_2t": dt_r_2,
                "dp_rival_1t": dp_r_1, "dp_rival_2t": dp_r_2,
            }

        def _formulario_plantilla(convocados_def=None, key_pref="ed"):
            """Multiselect de jugadores convocados al partido. Devuelve
            lista de dicts {dorsal, jugador, posicion, equipo}.
            Permite añadir un jugador nuevo "ad-hoc" si no está en el roster.
            """
            convocados_def = list(convocados_def or [])
            st.markdown("##### 👥 Plantilla del partido")
            if roster_activo.empty:
                # Si jugadores_roster sí tenía filas pero ninguna está activa
                # (raro), o si la hoja no existe / no tenemos permisos.
                if not jugadores_roster.empty:
                    st.warning(
                        f"La hoja `JUGADORES_ROSTER` tiene "
                        f"{len(jugadores_roster)} filas pero ninguna está "
                        "marcada como `activo=TRUE`. Revisa la columna "
                        "`activo` en el Sheet."
                    )
                else:
                    cA, cB = st.columns([3, 1])
                    cA.warning(
                        "No se pudo cargar la hoja `JUGADORES_ROSTER`. "
                        "Si acabas de crearla, puede ser caché de Streamlit "
                        "(5 min). Pulsa el botón → o **🔄 Actualizar datos** "
                        "en el sidebar."
                    )
                    if cB.button("🔄 Recargar roster",
                                  key=f"{key_pref}_refresh_roster"):
                        st.cache_data.clear()
                        st.rerun()
                return []

            # Default: si no hay convocados_def, sugerir todos los del primer
            # equipo + portero filial
            if not convocados_def:
                convocados_def = roster_activo[
                    (roster_activo.get("equipo", "") == "PRIMER")
                ]["nombre"].tolist()

            opciones = roster_activo["nombre"].tolist()
            elegidos = st.multiselect(
                "Convocados (12-16 habitual; varía por competición)",
                options=opciones,
                default=[n for n in convocados_def if n in opciones],
                format_func=_label_jugador,
                key=f"{key_pref}_convocados",
                help="Solo aparecen los activos. Para añadir uno nuevo, "
                      "edita la hoja `JUGADORES_ROSTER` con su dorsal y posición.",
            )
            if elegidos:
                porteros_n = sum(
                    1 for n in elegidos
                    if _info_jugador(n).get("posicion", "") == "PORTERO"
                )
                campo_n = len(elegidos) - porteros_n
                badge_color = "#2E7D32" if 12 <= len(elegidos) <= 16 else "#B71C1C"
                st.markdown(
                    f"<small><b>{len(elegidos)} convocados</b> "
                    f"(<span style='color:{badge_color}'>"
                    f"{'OK' if 12 <= len(elegidos) <= 16 else 'fuera de rango habitual'}"
                    f"</span>) — {porteros_n} portero(s) + {campo_n} de campo</small>",
                    unsafe_allow_html=True,
                )

            # Devolver con metadata
            plantilla = []
            for n in elegidos:
                info = _info_jugador(n)
                plantilla.append({
                    "jugador": n,
                    "dorsal": info.get("dorsal", ""),
                    "posicion": info.get("posicion", ""),
                    "equipo": info.get("equipo", ""),
                })
            return plantilla

        # Helper: parsear "MM:SS" o "M:SS" → (minuto_int, "mm:ss")
        def _parse_mmss(txt):
            """Devuelve (minuto_entero, 'MM:SS'). Acepta '12:37', '5', '5:00'.
            Si no parseable, (None, '')."""
            s = str(txt or "").strip().replace(",", ":").replace(" ", "")
            if not s:
                return None, ""
            if ":" in s:
                try:
                    mm, ss = s.split(":", 1)
                    mm_i = int(mm)
                    ss_i = int(ss) if ss else 0
                    if 0 <= mm_i <= 50 and 0 <= ss_i < 60:
                        return mm_i if ss_i < 30 else mm_i + 1, f"{mm_i:02d}:{ss_i:02d}"
                except ValueError:
                    return None, ""
            else:
                try:
                    mm_i = int(s)
                    if 0 <= mm_i <= 50:
                        return mm_i, f"{mm_i:02d}:00"
                except ValueError:
                    return None, ""
            return None, ""

        def _ev_dataframe_inicial():
            """DataFrame vacío con las columnas del editor de eventos."""
            return pd.DataFrame({
                "min_mmss": pd.Series(dtype="str"),
                "marcador": pd.Series(dtype="str"),
                "accion": pd.Series(dtype="str"),
                "equipo_marca": pd.Series(dtype="str"),
                "goleador": pd.Series(dtype="str"),
                "asistente": pd.Series(dtype="str"),
                "portero": pd.Series(dtype="str"),
                "p1": pd.Series(dtype="str"),
                "p2": pd.Series(dtype="str"),
                "p3": pd.Series(dtype="str"),
                "p4": pd.Series(dtype="str"),
                "p5": pd.Series(dtype="str"),
                "descripcion": pd.Series(dtype="str"),
            })

        def _ev_desde_df_existente(df_ev):
            """Convierte EST_EVENTOS (con cuarteto string) a las columnas
            del editor (min_mmss, p1..p5)."""
            if df_ev is None or df_ev.empty:
                return _ev_dataframe_inicial()
            out = df_ev.copy()
            # Min: usar minuto_mmss si existe, si no derivar de minuto entero
            if "minuto_mmss" in out.columns:
                out["min_mmss"] = out["minuto_mmss"].fillna("").astype(str)
            else:
                out["min_mmss"] = ""
            # Si min_mmss vacía pero minuto numérico → "MM:00"
            mask_vacio = out["min_mmss"].astype(str).str.strip() == ""
            if mask_vacio.any():
                m_int = pd.to_numeric(out["minuto"], errors="coerce").fillna(0).astype(int)
                out.loc[mask_vacio, "min_mmss"] = m_int[mask_vacio].apply(
                    lambda v: f"{v:02d}:00" if v > 0 else "")
            # Cuarteto string → p1..p5
            for i in range(1, 6):
                out[f"p{i}"] = ""
            cu = out.get("cuarteto", pd.Series([""] * len(out))).astype(str)
            for idx, txt in cu.items():
                partes = [p.strip() for p in txt.split("|") if p.strip()]
                for i, n in enumerate(partes[:5], start=1):
                    out.at[idx, f"p{i}"] = n
            cols_show = ["min_mmss", "marcador", "accion", "equipo_marca",
                          "goleador", "asistente", "portero",
                          "p1", "p2", "p3", "p4", "p5", "descripcion"]
            for c in cols_show:
                if c not in out.columns:
                    out[c] = ""
            return out[cols_show].reset_index(drop=True)

        def _editor_eventos(plantilla_actual, df_pre, key):
            """Render del data_editor con selectores filtrados a la
            plantilla del partido. Devuelve el DataFrame editado."""
            # Lista de jugadores convocados (preferida) o fallback al roster
            if plantilla_actual:
                nombres_pl = [p["jugador"] for p in plantilla_actual]
                porteros_pl = [p["jugador"] for p in plantilla_actual
                               if p.get("posicion", "") == "PORTERO"]
                campo_pl = [p["jugador"] for p in plantilla_actual
                            if p.get("posicion", "") == "CAMPO"]
            else:
                nombres_pl = jug_conocidos
                porteros_pl = jug_porteros
                campo_pl = jug_campo

            opciones_jug = sorted(set(nombres_pl))
            opciones_pista = [""] + opciones_jug
            opciones_porteros = [""] + sorted(set(porteros_pl))
            opciones_goleador = opciones_jug + ["RIVAL"]
            opciones_asist = [""] + opciones_jug

            # Pequeña leyenda con dorsales de los convocados
            if plantilla_actual:
                leyenda_partes = []
                for p in plantilla_actual:
                    d = p.get("dorsal", "")
                    try:
                        d_int = int(float(d)) if d not in ("", None) else None
                    except (TypeError, ValueError):
                        d_int = None
                    leyenda_partes.append(
                        f"#{d_int}·{p['jugador']}" if d_int is not None
                        else p["jugador"])
                with st.expander("💡 Dorsales de los convocados", expanded=False):
                    st.caption(" · ".join(leyenda_partes))

            cfg = {
                "min_mmss": st.column_config.TextColumn(
                    "Min", help="Formato MM:SS (ej. 12:37). También vale '12'.",
                    max_chars=6, width="small"),
                "marcador": st.column_config.TextColumn(
                    "Marcador", help="Ej: 1-0", max_chars=8, width="small"),
                "accion": st.column_config.SelectboxColumn(
                    "Acción", options=[""] + ACCIONES),
                "equipo_marca": st.column_config.SelectboxColumn(
                    "Equipo", options=["", "INTER", "RIVAL"]),
                "goleador": st.column_config.SelectboxColumn(
                    "Goleador", options=opciones_goleador),
                "asistente": st.column_config.SelectboxColumn(
                    "Asistente", options=opciones_asist),
                "portero": st.column_config.SelectboxColumn(
                    "Portero", options=opciones_porteros,
                    help="Vacío si juega portero-jugador (5 de campo)."),
                "p1": st.column_config.SelectboxColumn(
                    "Pista 1", options=opciones_pista),
                "p2": st.column_config.SelectboxColumn(
                    "Pista 2", options=opciones_pista),
                "p3": st.column_config.SelectboxColumn(
                    "Pista 3", options=opciones_pista),
                "p4": st.column_config.SelectboxColumn(
                    "Pista 4", options=opciones_pista),
                "p5": st.column_config.SelectboxColumn(
                    "Pista 5", options=opciones_pista,
                    help="Solo si juega portero-jugador (5 de campo, sin portero)."),
                "descripcion": st.column_config.TextColumn(
                    "Descripción", width="medium"),
            }
            return st.data_editor(
                df_pre, num_rows="dynamic", use_container_width=True,
                key=key, column_config=cfg,
            )

        def _normalizar_eventos_para_guardar(df_edit):
            """Convierte el DataFrame del editor (min_mmss + p1..p5) al
            esquema de EST_EVENTOS (minuto + minuto_mmss + cuarteto).
            Filtra filas vacías. Devuelve (df, list_warnings)."""
            warns = []
            if df_edit is None or df_edit.empty:
                return _ev_dataframe_inicial().assign(minuto=0, minuto_mmss="",
                                                       cuarteto=""), warns
            df = df_edit.copy().fillna("")
            # Filtrar filas vacías (sin min_mmss, sin equipo, sin goleador)
            mask = (df["min_mmss"].astype(str).str.strip() != "") | \
                    (df["equipo_marca"].astype(str).str.strip() != "") | \
                    (df["goleador"].astype(str).str.strip() != "")
            df = df[mask].reset_index(drop=True)
            if df.empty:
                return _ev_dataframe_inicial().assign(minuto=0, minuto_mmss="",
                                                       cuarteto=""), warns
            # Parsear minuto
            minutos_int = []
            mmss = []
            for i, txt in enumerate(df["min_mmss"].astype(str)):
                m_int, m_mmss = _parse_mmss(txt)
                minutos_int.append(m_int if m_int is not None else 0)
                mmss.append(m_mmss)
                if m_int is None and txt.strip():
                    warns.append(f"Fila {i + 1}: minuto '{txt}' no se pudo parsear (formato MM:SS).")
            df["minuto"] = minutos_int
            df["minuto_mmss"] = mmss
            # Construir cuarteto = p1..p5 join "|"
            cuartetos = []
            for _, r in df.iterrows():
                pl = [str(r.get(f"p{i}", "") or "").strip() for i in range(1, 6)]
                pl = [p for p in pl if p]
                cuartetos.append("|".join(pl))
            df["cuarteto"] = cuartetos
            # Validación: número de jugadores en pista coherente con portero
            for idx, r in df.iterrows():
                portero = str(r.get("portero", "") or "").strip()
                n_pista = len([p for p in str(r.get("cuarteto", "")).split("|") if p])
                if portero and n_pista not in (0, 4):
                    warns.append(
                        f"Fila {idx + 1}: hay {n_pista} jugadores en pista pero "
                        f"se especificó portero ({portero}) → debería haber 4 "
                        f"jugadores de campo en pista.")
                if not portero and n_pista not in (0, 5):
                    warns.append(
                        f"Fila {idx + 1}: portero vacío (modo portero-jugador) "
                        f"pero hay {n_pista} jugadores en pista → deberían ser 5.")
            return df, warns

        # ── Métricas individuales (iter 3) ─────────────────────────────
        # Mapeo nombre planilla → columna EST_PARTIDOS
        # Campo:    PF→pf · PNF→pnf · ROB→robos · COR→cortes · BDG→bdg ·
        #           BDP→bdp · DP→dp · DPos→dpalo · DB→db · DF→df · TA→ta · TR→tr
        # Portería: P.PAR→par · P.FUE→out · P.BLO→bloq_p · P.POS→poste_p ·
        #           P.Gol→gol_p · P.SAL→salida · P.SAL_FALL→salida_fallida
        COLS_METRICAS_CAMPO = [
            ("min_1t", "Min 1T"), ("min_2t", "Min 2T"), ("min_total", "Min Total"),
            ("pf", "PF"), ("pnf", "PNF"), ("robos", "ROB"), ("cortes", "COR"),
            ("bdg", "BDG"), ("bdp", "BDP"),
            ("dp", "DP"), ("dpalo", "DPos"), ("db", "DB"), ("df", "DF"),
            ("ta", "TA"), ("tr", "TR"),
        ]
        COLS_METRICAS_PORTERIA = [
            ("par", "P.PAR"), ("out", "P.FUE"), ("bloq_p", "P.BLO"),
            ("poste_p", "P.POS"), ("gol_p", "P.Gol"),
            ("salida", "P.SAL"), ("salida_fallida", "P.SAL_FALL"),
        ]
        COLS_NUMERICAS = (
            ["pf", "pnf", "robos", "cortes", "bdg", "bdp", "dp", "dpalo",
             "db", "df", "ta", "tr"] +
            ["par", "out", "bloq_p", "poste_p", "gol_p", "salida", "salida_fallida"]
        )

        def _df_metricas_inicial(plantilla_actual, partido_id):
            """Construye un DataFrame con una fila por jugador convocado.
            Si el partido ya existía en EST_PARTIDOS, precarga los valores
            actuales (no pisa). Si no, todos los numéricos a 0 y minutos vacíos."""
            if not plantilla_actual:
                return pd.DataFrame(), pd.DataFrame()

            # Filas precargadas del partido si existe
            ep_pid = pd.DataFrame()
            if not est_partidos.empty:
                ep_pid = est_partidos[
                    est_partidos["partido_id"].astype(str) == partido_id
                ].copy()

            def _formato_min(min_val):
                """De minuto float a 'mm:ss'. 0 → ''."""
                try:
                    v = float(min_val or 0)
                except (TypeError, ValueError):
                    return ""
                if v <= 0:
                    return ""
                m = int(v)
                s = int(round((v - m) * 60))
                if s == 60:
                    m += 1; s = 0
                return f"{m:02d}:{s:02d}"

            filas_campo = []
            filas_port = []
            for p in plantilla_actual:
                jug = p["jugador"]
                row_pre = pd.DataFrame()
                if not ep_pid.empty:
                    row_pre = ep_pid[ep_pid["jugador"].astype(str).str.upper() == jug]
                fila = {"dorsal": p.get("dorsal", ""), "jugador": jug}
                # minutos
                if not row_pre.empty:
                    r = row_pre.iloc[0]
                    fila["min_1t"] = _formato_min(r.get("min_1t", 0))
                    fila["min_2t"] = _formato_min(r.get("min_2t", 0))
                    fila["min_total"] = _formato_min(r.get("min_total", 0))
                else:
                    fila["min_1t"] = ""
                    fila["min_2t"] = ""
                    fila["min_total"] = ""
                # numéricos
                for c in COLS_NUMERICAS:
                    if not row_pre.empty:
                        v = pd.to_numeric(row_pre.iloc[0].get(c, 0), errors="coerce")
                        fila[c] = int(v) if pd.notna(v) else 0
                    else:
                        fila[c] = 0
                if p.get("posicion", "") == "PORTERO":
                    filas_port.append(fila)
                else:
                    filas_campo.append(fila)

            # DataFrame de campo (incluye campo + porteros, pero porteros sólo
            # muestran lo común — métricas de portería van en otra tabla)
            cols_camp_full = ["dorsal", "jugador"] + [c for c, _ in COLS_METRICAS_CAMPO]
            df_campo = pd.DataFrame(filas_campo + filas_port, columns=cols_camp_full)
            # DataFrame de portería (solo porteros)
            cols_port_full = ["dorsal", "jugador"] + [c for c, _ in COLS_METRICAS_PORTERIA]
            df_port = pd.DataFrame(filas_port, columns=cols_port_full)
            return df_campo, df_port

        def _editor_metricas_campo(df_pre, key):
            """Renderiza el editor de métricas individuales (campo).
            Aplica a TODOS los convocados (campo + porteros)."""
            cfg = {
                "dorsal": st.column_config.NumberColumn("Nº", disabled=True, width="small", format="%d"),
                "jugador": st.column_config.TextColumn("Jugador", disabled=True, width="medium"),
                "min_1t": st.column_config.TextColumn("Min 1T", width="small",
                            help="MM:SS. Tiempo total jugado en 1ª parte (incluye rotaciones cortas no apuntadas)."),
                "min_2t": st.column_config.TextColumn("Min 2T", width="small",
                            help="MM:SS. Tiempo total jugado en 2ª parte."),
                "min_total": st.column_config.TextColumn("Min Total", width="small",
                            help="MM:SS. Si lo dejas vacío, se calcula como Min 1T + Min 2T."),
            }
            for k, lbl in COLS_METRICAS_CAMPO[3:]:  # saltamos los 3 de minutos (ya en cfg)
                if k in ("ta",):
                    cfg[k] = st.column_config.NumberColumn(lbl, min_value=0, max_value=2, format="%d", width="small",
                                  help="Tarjetas amarillas (0-2). 2 amarillas → expulsión.")
                elif k in ("tr",):
                    cfg[k] = st.column_config.NumberColumn(lbl, min_value=0, max_value=1, format="%d", width="small",
                                  help="Tarjeta roja directa (0-1).")
                else:
                    cfg[k] = st.column_config.NumberColumn(lbl, min_value=0, format="%d", width="small")
            return st.data_editor(
                df_pre, num_rows="fixed", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )

        def _editor_metricas_porteria(df_pre, key):
            """Renderiza el editor de métricas de portería (solo porteros)."""
            if df_pre.empty:
                st.caption("_(Esta tabla aparece cuando hay porteros en la plantilla.)_")
                return df_pre
            cfg = {
                "dorsal": st.column_config.NumberColumn("Nº", disabled=True, width="small", format="%d"),
                "jugador": st.column_config.TextColumn("Portero", disabled=True, width="medium"),
            }
            for k, lbl in COLS_METRICAS_PORTERIA:
                if k == "salida":
                    cfg[k] = st.column_config.NumberColumn(
                        lbl, min_value=0, format="%d", width="small",
                        help="P.SAL: salida CORRECTA del portero a un balón.")
                elif k == "salida_fallida":
                    cfg[k] = st.column_config.NumberColumn(
                        lbl, min_value=0, format="%d", width="small",
                        help="P.SAL_FALL: salida fallida.")
                else:
                    cfg[k] = st.column_config.NumberColumn(
                        lbl, min_value=0, format="%d", width="small")
            return st.data_editor(
                df_pre, num_rows="fixed", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )

        # ── Rotaciones (iter 4) ─────────────────────────────────────────────
        def _df_rotaciones_inicial(plantilla_actual, partido_id, parte: str):
            """Construye un DataFrame con una fila por jugador convocado y
            columnas rot_{parte}_1 .. rot_{parte}_8 con valores en MM:SS.
            Precarga desde EST_PARTIDOS si el partido existía.
            parte: "1t" o "2t"."""
            if not plantilla_actual:
                return pd.DataFrame()
            ep_pid = pd.DataFrame()
            if not est_partidos.empty:
                ep_pid = est_partidos[
                    est_partidos["partido_id"].astype(str) == partido_id
                ].copy()

            def _formato_min(v):
                vf = safe_float(v)
                if vf <= 0:
                    return ""
                m = int(vf)
                s = int(round((vf - m) * 60))
                if s == 60:
                    m += 1; s = 0
                return f"{m:02d}:{s:02d}"

            filas = []
            for p in plantilla_actual:
                jug = p["jugador"]
                row_pre = pd.DataFrame()
                if not ep_pid.empty:
                    row_pre = ep_pid[ep_pid["jugador"].astype(str).str.upper() == jug]
                fila = {"dorsal": p.get("dorsal", ""), "jugador": jug,
                          "posicion": p.get("posicion", "")}
                # Min de la parte (de iter 3)
                if not row_pre.empty:
                    fila["min_parte"] = _formato_min(row_pre.iloc[0].get(f"min_{parte}", 0))
                else:
                    fila["min_parte"] = ""
                # 8 rotaciones
                for i in range(1, 9):
                    if not row_pre.empty:
                        fila[f"r{i}"] = _formato_min(row_pre.iloc[0].get(f"rot_{parte}_{i}", 0))
                    else:
                        fila[f"r{i}"] = ""
                filas.append(fila)
            cols = ["dorsal", "jugador", "min_parte"] + [f"r{i}" for i in range(1, 9)]
            return pd.DataFrame(filas, columns=cols)

        def _editor_rotaciones(df_pre, n_visibles, parte_label, key):
            """Renderiza el editor de rotaciones de una parte. n_visibles: 1-8.
            Las columnas r{n+1}..r8 quedan ocultas (pero se preservan).
            Debajo del editor renderiza una VISTA PREVIA COLOREADA
            (st.dataframe con styler) según el gradiente:
              0=blanco · 0-1'=azul · 1-2'=verde · 2-3'=amarillo · >3'=rojo
            (st.data_editor no acepta colores por celda en Streamlit hoy.)
            """
            if df_pre is None or df_pre.empty:
                st.caption("_(Selecciona la plantilla arriba para editar rotaciones.)_")
                return df_pre
            cfg = {
                "dorsal": st.column_config.NumberColumn(
                    "Nº", disabled=True, width="small", format="%d"),
                "jugador": st.column_config.TextColumn(
                    "Jugador", disabled=True, width="medium"),
                "min_parte": st.column_config.TextColumn(
                    f"Min {parte_label}", disabled=True, width="small",
                    help="Vine de la tabla de métricas. Si está vacío, "
                          "rellena ahí Min 1T o Min 2T primero."),
            }
            for i in range(1, 9):
                if i <= n_visibles:
                    cfg[f"r{i}"] = st.column_config.TextColumn(
                        f"{i}ª", width="small",
                        help=f"Duración de la {i}ª rotación. MM:SS. Vacío = sin rotación.")
                # Las que excedan n_visibles las marcamos con disabled=True
                # para que el usuario no las llene por error. Pero visibles
                # como '—' si tienen valor previo.
            # Si quiere ocultar columnas con st.data_editor no tiene API
            # directa: las dejo todas pero con disabled si i > n_visibles.
            for i in range(n_visibles + 1, 9):
                cfg[f"r{i}"] = st.column_config.TextColumn(
                    f"{i}ª", width="small", disabled=True,
                    help="Aumenta el número de rotaciones para activar esta columna.")
            df_edit = st.data_editor(
                df_pre, num_rows="fixed", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )
            # Vista previa coloreada (no editable) — solo si hay rotaciones
            try:
                _vista_rotaciones_coloreada(df_edit, n_visibles)
            except Exception:
                pass
            return df_edit

        def _vista_rotaciones_coloreada(df_edit, n_visibles):
            """Renderiza un st.dataframe con styler aplicando colores a
            las celdas r1..rN según el gradiente. Se muestra como
            "Vista previa" debajo del editor."""
            if df_edit is None or df_edit.empty:
                return
            cols_show = ["dorsal", "jugador"] + \
                          [f"r{i}" for i in range(1, n_visibles + 1)]
            # Filtrar columnas que existen
            cols_show = [c for c in cols_show if c in df_edit.columns]
            df_show = df_edit[cols_show].copy()

            def _bg(v):
                # v es string mm:ss o vacío
                if not v or str(v).strip() == "":
                    return "background-color: #ffffff;"
                m_int, _ = _parse_mmss(v)
                if m_int is None or m_int <= 0:
                    return "background-color: #ffffff;"
                # Convertimos a minutos float (aproximado: m_int es entero)
                # Para los rangos: usamos m_int directo.
                if m_int < 1:
                    return "background-color: #BBDEFB;"   # azul
                if m_int < 2:
                    return "background-color: #C8E6C9;"   # verde
                if m_int < 3:
                    return "background-color: #FFF59D;"   # amarillo
                return "background-color: #EF9A9A;"       # rojo
            cols_color = [c for c in cols_show if c.startswith("r")]
            sty = df_show.style.applymap(_bg, subset=cols_color)
            st.caption("👁️ Vista previa con colores (no editable):")
            st.dataframe(sty, use_container_width=True, hide_index=True)

        def _validar_rotaciones(df_rot):
            """Avisa si la suma de rotaciones de un jugador supera el Min Parte."""
            warns = []
            if df_rot is None or df_rot.empty:
                return warns
            for _, r in df_rot.iterrows():
                jug = r.get("jugador", "")
                mins_parte = _parse_mmss(r.get("min_parte", ""))[0]
                suma_rot = 0.0
                rotaciones_apuntadas = 0
                for i in range(1, 9):
                    v = r.get(f"r{i}", "")
                    parsed = _parse_mmss(v)[0]
                    if parsed is not None and parsed > 0:
                        suma_rot += parsed
                        rotaciones_apuntadas += 1
                if mins_parte and suma_rot > mins_parte + 0.5:
                    # +0.5 de tolerancia para errores de redondeo
                    warns.append(
                        f"{jug}: suma de rotaciones ({suma_rot:.0f}') "
                        f"> Min de la parte ({mins_parte:.0f}'). "
                        "Las rotaciones cortas no apuntadas también suman al "
                        "Min total, ¿revisa por si has duplicado alguna?")
            return warns

        def _normalizar_rotaciones_para_guardar(df_rot_1t, df_rot_2t):
            """Devuelve dict {jugador → {rot_1t_1..8, rot_2t_1..8}} con valores
            en minutos float (compat extractor)."""
            out = {}
            for parte, df in (("1t", df_rot_1t), ("2t", df_rot_2t)):
                if df is None or df.empty:
                    continue
                for _, r in df.iterrows():
                    jug = str(r.get("jugador", "") or "").strip().upper()
                    if not jug:
                        continue
                    if jug not in out:
                        out[jug] = {}
                    for i in range(1, 9):
                        v = r.get(f"r{i}", "")
                        parsed = _parse_mmss(v)[0]
                        out[jug][f"rot_{parte}_{i}"] = round(parsed, 4) if parsed else 0
            return out

        def _guardar_rotaciones(partido_id, rotaciones_por_jug):
            """Actualiza las columnas rot_*_* de EST_PARTIDOS para los
            jugadores con rotaciones nuevas. PRESERVA el resto de columnas."""
            if not rotaciones_por_jug:
                return 0
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_PARTIDOS")
            except gspread.exceptions.WorksheetNotFound:
                return 0
            df_all = pd.DataFrame(ws.get_all_records())
            if df_all.empty:
                return 0
            # pandas 3.x: forzar object para evitar "Invalid value for dtype"
            df_all = df_all.astype(object)
            # Asegurar que existen las columnas rot
            cols_rot = [f"rot_{p}_{i}" for p in ("1t", "2t") for i in range(1, 9)]
            for c in cols_rot:
                if c not in df_all.columns:
                    df_all[c] = ""
            # Aplicar rotaciones
            mask_part = df_all["partido_id"].astype(str) == partido_id
            for jug, vals in rotaciones_por_jug.items():
                mask = mask_part & (df_all["jugador"].astype(str).str.upper() == jug)
                if not mask.any():
                    continue
                for col, val in vals.items():
                    df_all.loc[mask, col] = str(val) if val not in ("", None) else ""
            # Reescribir
            cols_orden = list(df_all.columns)
            df_out = df_all.fillna("")
            ws.clear()
            ws.update(values=[cols_orden] + df_out.astype(str).values.tolist(),
                       range_name="A1")
            return len(rotaciones_por_jug)

        def _validar_metricas_campo(df):
            """Devuelve lista de avisos sobre tarjetas/minutos."""
            warns = []
            if df is None or df.empty:
                return warns
            for _, r in df.iterrows():
                jug = r.get("jugador", "")
                _ta = pd.to_numeric(r.get("ta", 0), errors="coerce")
                _tr = pd.to_numeric(r.get("tr", 0), errors="coerce")
                ta = int(_ta) if pd.notna(_ta) else 0
                tr = int(_tr) if pd.notna(_tr) else 0
                if ta > 2:
                    warns.append(f"{jug}: TA={ta} (máximo 2 antes de roja por doble amarilla).")
                if tr > 1:
                    warns.append(f"{jug}: TR={tr} (máximo 1).")
                # Comprobar suma min_1t + min_2t = min_total (si los 3 están)
                m1 = _parse_mmss(r.get("min_1t", ""))[0] or 0
                m2 = _parse_mmss(r.get("min_2t", ""))[0] or 0
                mt = _parse_mmss(r.get("min_total", ""))[0]
                if mt is not None and abs(mt - (m1 + m2)) > 1:
                    warns.append(
                        f"{jug}: Min Total ({mt}') ≠ Min 1T + Min 2T ({m1+m2}'). "
                        "Si tienes rotaciones cortas no apuntadas que sumen al "
                        "total, ignora este aviso.")
                if m1 > 21:
                    warns.append(f"{jug}: Min 1T = {m1}' > 20'.")
                if m2 > 21:
                    warns.append(f"{jug}: Min 2T = {m2}' > 20'.")
            return warns

        def _normalizar_metricas_para_guardar(df_campo, df_port):
            """Convierte los DataFrames del editor a un dict por jugador con
            todas las columnas que persistir en EST_PARTIDOS."""
            metricas_por_jug = {}
            if df_campo is not None and not df_campo.empty:
                for _, r in df_campo.iterrows():
                    jug = str(r.get("jugador", "") or "").strip().upper()
                    if not jug:
                        continue
                    m1 = _parse_mmss(r.get("min_1t", ""))[0] or 0
                    m2 = _parse_mmss(r.get("min_2t", ""))[0] or 0
                    mt_parsed = _parse_mmss(r.get("min_total", ""))[0]
                    mt = mt_parsed if mt_parsed is not None else (m1 + m2)
                    fila = {
                        "dorsal": r.get("dorsal", ""),
                        "jugador": jug,
                        "min_1t": m1,
                        "min_2t": m2,
                        "min_total": mt,
                    }
                    for c in [k for k, _ in COLS_METRICAS_CAMPO[3:]]:
                        v = pd.to_numeric(r.get(c, 0), errors="coerce")
                        fila[c] = int(v) if pd.notna(v) else 0
                    # Defaults de portería a 0 (se sobreescribe luego si es portero)
                    for c in [k for k, _ in COLS_METRICAS_PORTERIA]:
                        fila[c] = 0
                    metricas_por_jug[jug] = fila
            # Datos de portería sobre los porteros
            if df_port is not None and not df_port.empty:
                for _, r in df_port.iterrows():
                    jug = str(r.get("jugador", "") or "").strip().upper()
                    if not jug or jug not in metricas_por_jug:
                        continue
                    for c in [k for k, _ in COLS_METRICAS_PORTERIA]:
                        v = pd.to_numeric(r.get(c, 0), errors="coerce")
                        metricas_por_jug[jug][c] = int(v) if pd.notna(v) else 0
            return metricas_por_jug

        def _guardar_metricas(partido_id, metricas_por_jug, cab):
            """Persiste las métricas en EST_PARTIDOS. Crea/actualiza una fila
            por jugador convocado. Preserva las rotaciones (rot_1t_1..rot_2t_8)
            si ya existían para ese (partido_id, jugador)."""
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_PARTIDOS")
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet("EST_PARTIDOS", rows=1000, cols=60)
                ws.update(values=[["partido_id"]], range_name="A1")
            df_all = pd.DataFrame(ws.get_all_records())
            # Schema mínimo
            cols_basicas = [
                "partido_id", "tipo", "competicion", "rival", "fecha",
                "dorsal", "jugador", "min_1t", "min_2t", "min_total",
                "convocado", "participa",
            ]
            cols_rot = [f"rot_{p}_{i}" for p in ("1t", "2t") for i in range(1, 9)]
            cols_metricas_full = [k for k, _ in COLS_METRICAS_CAMPO[3:]] + \
                                  [k for k, _ in COLS_METRICAS_PORTERIA]
            cols_extra = ["goles_a_favor", "asistencias"]
            cols_completas = cols_basicas + cols_rot + cols_metricas_full + cols_extra
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols_completas)
            else:
                for c in cols_completas:
                    if c not in df_all.columns:
                        df_all[c] = ""
            # Filas de OTROS partidos (las preservamos)
            df_otros = df_all[df_all["partido_id"].astype(str) != partido_id].copy()
            # Filas existentes de ESTE partido (para preservar rotaciones)
            df_este = df_all[df_all["partido_id"].astype(str) == partido_id].copy()
            # Construir nuevas filas
            filas_nuevas = []
            for jug, fila in metricas_por_jug.items():
                base = {
                    "partido_id": partido_id,
                    "tipo": cab["tipo"],
                    "competicion": cab["competicion"],
                    "rival": cab["rival"],
                    "fecha": cab["fecha"],
                    "convocado": "TRUE",
                    "participa": "TRUE" if fila.get("min_total", 0) > 0 else "FALSE",
                }
                base.update(fila)
                # Preservar rotaciones existentes para este jugador
                if not df_este.empty:
                    fila_prev = df_este[
                        df_este["jugador"].astype(str).str.upper() == jug
                    ]
                    if not fila_prev.empty:
                        for c in cols_rot:
                            base[c] = fila_prev.iloc[0].get(c, 0) or 0
                        # También preservar goles/asists si vienen del cruce de eventos
                        for c in ("goles_a_favor", "asistencias"):
                            if c in fila_prev.columns:
                                base[c] = fila_prev.iloc[0].get(c, 0) or 0
                # Asegurar columnas que falten
                for c in cols_completas:
                    if c not in base:
                        base[c] = ""
                filas_nuevas.append({c: base.get(c, "") for c in cols_completas})

            df_nuevas = pd.DataFrame(filas_nuevas, columns=cols_completas)
            df_final = pd.concat([df_otros[cols_completas], df_nuevas],
                                   ignore_index=True).fillna("")
            ws.clear()
            ws.update(values=[cols_completas] + df_final.astype(str).values.tolist(),
                       range_name="A1")
            return len(filas_nuevas)

        # ── Iter 7: FALTAS ──────────────────────────────────────────────
        # Esquema EST_FALTAS:
        #   partido_id, tipo, competicion, rival, fecha,
        #   condicion (A_FAVOR/EN_CONTRA), parte (1/2), minuto_mmss,
        #   jugador (quien comete si EN_CONTRA, quien recibe si A_FAVOR),
        #   num_falta (1, 2, 3, ... reinicia en 2T por equipo),
        #   genera_10m (TRUE/FALSE — TRUE si esta es la 6ª de la parte
        #               del rival que comete: la siguiente penalización
        #               sobre nuestro equipo o vice-versa). Lo calcula la
        #               normalización al guardar.
        #   descripcion (texto libre opcional)
        FALTAS_COLS_EDITOR = [
            "parte", "minuto_mmss", "condicion", "jugador",
            "num_falta", "descripcion",
        ]

        def _df_faltas_inicial():
            """DataFrame vacío con las columnas del editor de faltas."""
            return pd.DataFrame({
                "parte": pd.Series(dtype="str"),
                "minuto_mmss": pd.Series(dtype="str"),
                "condicion": pd.Series(dtype="str"),
                "jugador": pd.Series(dtype="str"),
                "num_falta": pd.Series(dtype="object"),
                "descripcion": pd.Series(dtype="str"),
            })

        def _df_faltas_desde_sheet(partido_id):
            """Carga las faltas del partido_id desde EST_FALTAS si existe."""
            try:
                sh = _conexion_sheet()
                ws = sh.worksheet("EST_FALTAS")
                df_all = pd.DataFrame(ws.get_all_records())
            except Exception:
                return _df_faltas_inicial()
            if df_all.empty or "partido_id" not in df_all.columns:
                return _df_faltas_inicial()
            df = df_all[df_all["partido_id"].astype(str) == str(partido_id)].copy()
            if df.empty:
                return _df_faltas_inicial()
            # Reordenar columnas a las del editor (rellenar las que falten)
            for c in FALTAS_COLS_EDITOR:
                if c not in df.columns:
                    df[c] = ""
            df = df[FALTAS_COLS_EDITOR].copy()
            # Tipos: parte como string "1"/"2"
            df["parte"] = df["parte"].astype(str).str.strip()
            return df.reset_index(drop=True)

        def _editor_faltas(plantilla_actual, df_pre, key):
            """data_editor para faltas. Selectores filtrados a la plantilla."""
            if plantilla_actual:
                opciones_jug = sorted({p["jugador"] for p in plantilla_actual})
            else:
                opciones_jug = jug_conocidos
            cfg = {
                "parte": st.column_config.SelectboxColumn(
                    "Parte", options=["", "1", "2"], width="small",
                    help="1ª o 2ª parte"),
                "minuto_mmss": st.column_config.TextColumn(
                    "Min", help="MM:SS (formato 12:37)", max_chars=6,
                    width="small"),
                "condicion": st.column_config.SelectboxColumn(
                    "Condición",
                    options=["", "A_FAVOR", "EN_CONTRA"], width="medium",
                    help="A_FAVOR = falta que recibimos · EN_CONTRA = falta que cometemos"),
                "jugador": st.column_config.SelectboxColumn(
                    "Jugador", options=[""] + opciones_jug,
                    help="Si EN_CONTRA: quién comete. Si A_FAVOR: quién recibe."),
                "num_falta": st.column_config.NumberColumn(
                    "Nº falta", min_value=1, max_value=20, format="%d",
                    width="small",
                    help="Nº correlativo dentro de la parte y la condición. "
                          "Si lo dejas vacío se autocalcula al guardar. "
                          "La 6ª por equipo desencadena 10m."),
                "descripcion": st.column_config.TextColumn(
                    "Descripción", width="medium"),
            }
            return st.data_editor(
                df_pre, num_rows="dynamic", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )

        def _normalizar_faltas_para_guardar(df_edit):
            """Limpia el dataframe, autocalcula num_falta donde falte y
            marca la 6ª como genera_10m. Devuelve (df_normalizado, warns)."""
            warns = []
            if df_edit is None or df_edit.empty:
                return _df_faltas_inicial().assign(genera_10m=""), warns
            df = df_edit.copy().fillna("")
            # Filtrar filas vacías
            mask = (df["minuto_mmss"].astype(str).str.strip() != "") | \
                    (df["condicion"].astype(str).str.strip() != "") | \
                    (df["jugador"].astype(str).str.strip() != "")
            df = df[mask].reset_index(drop=True)
            if df.empty:
                return _df_faltas_inicial().assign(genera_10m=""), warns
            # Normalizar minutos a "MM:SS"
            mmss_norm = []
            min_int = []
            for i, txt in enumerate(df["minuto_mmss"].astype(str)):
                m_int, m_mmss = _parse_mmss(txt)
                if m_int is None and txt.strip():
                    warns.append(f"Falta fila {i+1}: minuto '{txt}' no se pudo parsear (MM:SS).")
                mmss_norm.append(m_mmss)
                min_int.append(m_int if m_int is not None else 0)
            df["minuto_mmss"] = mmss_norm
            df["minuto"] = min_int
            # Parte como string "1" o "2"
            df["parte"] = df["parte"].astype(str).str.strip()
            df["condicion"] = df["condicion"].astype(str).str.strip().str.upper()
            df["jugador"] = df["jugador"].astype(str).str.strip().str.upper()
            # Ordenar por parte y minuto para asignar num_falta
            df["_parte_n"] = pd.to_numeric(df["parte"], errors="coerce").fillna(0).astype(int)
            df["_min_n"] = pd.to_numeric(df["minuto"], errors="coerce").fillna(0)
            df = df.sort_values(["_parte_n", "_min_n"]).reset_index(drop=True)
            # Autocalcular num_falta dentro de cada (parte, condicion)
            df["num_falta"] = pd.to_numeric(df["num_falta"], errors="coerce")
            counters = {}
            num_finales = []
            for _, r in df.iterrows():
                key = (r["_parte_n"], r["condicion"])
                counters[key] = counters.get(key, 0) + 1
                # Si el usuario rellenó num_falta lo respetamos; si no, autocalc
                if pd.isna(r["num_falta"]) or r["num_falta"] <= 0:
                    num_finales.append(counters[key])
                else:
                    num_finales.append(int(r["num_falta"]))
                    counters[key] = max(counters[key], int(r["num_falta"]))
            df["num_falta"] = num_finales
            # Marcar las que generan 10m (la 6ª por (parte, condicion))
            df["genera_10m"] = df.apply(
                lambda r: "TRUE" if int(r["num_falta"]) >= 6 else "FALSE",
                axis=1,
            )
            df = df.drop(columns=["_parte_n", "_min_n"])
            return df, warns

        def _calcular_alertas_faltas(df_norm):
            """Devuelve lista de strings con alertas para mostrar al usuario:
            equipo X llegó a la 6ª en la parte Y → 10m sin barrera."""
            alertas = []
            if df_norm is None or df_norm.empty:
                return alertas
            for parte in ("1", "2"):
                df_p = df_norm[df_norm["parte"].astype(str) == parte]
                for cond, label in (("EN_CONTRA", "Inter (faltas cometidas)"),
                                       ("A_FAVOR", "Rival (faltas cometidas contra nosotros)")):
                    n = len(df_p[df_p["condicion"] == cond])
                    if n >= 6:
                        alertas.append(
                            f"⚠️ **{label}** ha cometido {n} faltas en {parte}ª parte. "
                            f"A partir de la 6ª, las siguientes son **10m sin barrera** "
                            f"contra el equipo que las comete."
                        )
                    elif n == 5:
                        alertas.append(
                            f"🟧 **{label}** lleva 5 faltas en {parte}ª parte. "
                            f"La siguiente sería la 6ª → 10m."
                        )
            return alertas

        def _guardar_faltas(partido_id, df_norm, cab):
            """Persiste en EST_FALTAS. Reescribe las filas del partido_id."""
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_FALTAS")
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet("EST_FALTAS", rows=400, cols=15)
                ws.update(values=[["partido_id"]], range_name="A1")
            df_all = pd.DataFrame(ws.get_all_records())
            cols = [
                "partido_id", "tipo", "competicion", "rival", "fecha",
                "parte", "minuto", "minuto_mmss", "condicion", "jugador",
                "num_falta", "genera_10m", "descripcion",
            ]
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols)
            else:
                for c in cols:
                    if c not in df_all.columns:
                        df_all[c] = ""
            df_otros = df_all[df_all["partido_id"].astype(str) != str(partido_id)]
            if df_norm is None or df_norm.empty:
                df_nuevas = pd.DataFrame(columns=cols)
            else:
                df_nuevas = df_norm.copy()
                df_nuevas["partido_id"] = partido_id
                df_nuevas["tipo"] = cab["tipo"]
                df_nuevas["competicion"] = cab["competicion"]
                df_nuevas["rival"] = cab["rival"]
                df_nuevas["fecha"] = cab["fecha"]
                for c in cols:
                    if c not in df_nuevas.columns:
                        df_nuevas[c] = ""
                df_nuevas = df_nuevas[cols]
            df_final = pd.concat([df_otros[cols], df_nuevas], ignore_index=True).fillna("")
            ws.clear()
            ws.update(values=[cols] + df_final.astype(str).values.tolist(),
                       range_name="A1")
            return len(df_nuevas)

        # ── Iter 8: PENALTIS y 10m ──────────────────────────────────────
        # Esquema EST_PENALTIS_10M:
        #   partido_id, tipo, competicion, rival, fecha,
        #   tipo_lanzamiento (PENALTI / 10M),
        #     PENALTI: 6m, falta dentro del área
        #     10M: 10m, sexta falta del equipo
        #   condicion (A_FAVOR / EN_CONTRA),
        #   parte (1/2), minuto_mmss,
        #   lanzador (jugador Inter si A_FAVOR; "RIVAL" si EN_CONTRA),
        #   portero (portero Inter si EN_CONTRA; "RIVAL" si A_FAVOR),
        #   resultado (GOL / PARADA / POSTE / FUERA),
        #   cuadrante (P1..P9 si va a portería; vacío si FUERA),
        #   descripcion
        PEN_COLS_EDITOR = [
            "tipo_lanzamiento", "condicion", "parte", "minuto_mmss",
            "marcador", "lanzador", "portero", "resultado", "cuadrante",
            "descripcion",
        ]
        PEN_TIPOS = ["", "PENALTI", "10M"]
        PEN_RESULTADOS = ["", "GOL", "PARADA", "POSTE", "FUERA"]
        PEN_CUADRANTES = ["", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]

        def _df_penaltis_inicial():
            return pd.DataFrame({
                "tipo_lanzamiento": pd.Series(dtype="str"),
                "condicion": pd.Series(dtype="str"),
                "parte": pd.Series(dtype="str"),
                "minuto_mmss": pd.Series(dtype="str"),
                "marcador": pd.Series(dtype="str"),
                "lanzador": pd.Series(dtype="str"),
                "portero": pd.Series(dtype="str"),
                "resultado": pd.Series(dtype="str"),
                "cuadrante": pd.Series(dtype="str"),
                "descripcion": pd.Series(dtype="str"),
            })

        def _calcular_marcador_en_minuto(eventos_df, minuto_int, equipo_marca):
            """Calcula el marcador (Inter–Rival) ANTES del evento dado.
            eventos_df: DataFrame de EST_EVENTOS del partido.
            minuto_int: minuto del penalti/10m.
            equipo_marca: ignorado (devolvemos el marcador del momento).
            """
            if eventos_df is None or eventos_df.empty:
                return "0-0"
            ev = eventos_df.copy()
            ev["_min"] = pd.to_numeric(ev.get("minuto", 0), errors="coerce").fillna(99)
            previos = ev[ev["_min"] < minuto_int]
            gf = int((previos.get("equipo_marca", "") == "INTER").sum())
            gc = int((previos.get("equipo_marca", "") == "RIVAL").sum())
            return f"{gf}-{gc}"

        def _autorellenar_marcador_penaltis(df_pen, eventos_df):
            """Si una fila de penaltis tiene minuto pero NO marcador,
            calcula el marcador a partir de los eventos previos a ese
            minuto. No pisa los marcadores que el usuario haya escrito."""
            if df_pen is None or df_pen.empty:
                return df_pen
            out = df_pen.copy()
            for idx, r in out.iterrows():
                marc = str(r.get("marcador", "") or "").strip()
                if marc:
                    continue  # ya rellenado
                m_int, _ = _parse_mmss(r.get("minuto_mmss", ""))
                if m_int is None:
                    continue
                out.at[idx, "marcador"] = _calcular_marcador_en_minuto(
                    eventos_df, m_int, r.get("condicion", ""))
            return out

        def _df_penaltis_desde_sheet(partido_id):
            try:
                sh = _conexion_sheet()
                ws = sh.worksheet("EST_PENALTIS_10M")
                df_all = pd.DataFrame(ws.get_all_records())
            except Exception:
                return _df_penaltis_inicial()
            if df_all.empty or "partido_id" not in df_all.columns:
                return _df_penaltis_inicial()
            df = df_all[df_all["partido_id"].astype(str) == str(partido_id)].copy()
            if df.empty:
                return _df_penaltis_inicial()
            for c in PEN_COLS_EDITOR:
                if c not in df.columns:
                    df[c] = ""
            return df[PEN_COLS_EDITOR].reset_index(drop=True)

        def _editor_penaltis(plantilla_actual, df_pre, key):
            if plantilla_actual:
                jug_lanz = sorted({p["jugador"] for p in plantilla_actual
                                     if p.get("posicion", "") == "CAMPO"})
                jug_porteros = sorted({p["jugador"] for p in plantilla_actual
                                          if p.get("posicion", "") == "PORTERO"})
            else:
                jug_lanz = jug_campo
                jug_porteros = jug_porteros if 'jug_porteros' in dir() else \
                                ["J.HERRERO", "J.GARCIA", "OSCAR"]
            opciones_lanzador = [""] + jug_lanz + ["RIVAL"]
            opciones_portero = [""] + jug_porteros + ["RIVAL"]
            cfg = {
                "tipo_lanzamiento": st.column_config.SelectboxColumn(
                    "Tipo", options=PEN_TIPOS, width="small",
                    help="PENALTI (6m, falta dentro del área) · 10M (10m, sexta falta del equipo)"),
                "condicion": st.column_config.SelectboxColumn(
                    "Cond.", options=["", "A_FAVOR", "EN_CONTRA"], width="small",
                    help="A_FAVOR = lo lanzamos nosotros · EN_CONTRA = lo lanza el rival"),
                "parte": st.column_config.SelectboxColumn(
                    "P", options=["", "1", "2"], width="small"),
                "minuto_mmss": st.column_config.TextColumn(
                    "Min", help="MM:SS", max_chars=6, width="small"),
                "marcador": st.column_config.TextColumn(
                    "Marc.", max_chars=8, width="small",
                    help="Estado del marcador en ese minuto (ej. '1-0'). "
                          "Si lo dejas vacío y rellenas el minuto, se "
                          "autorrellena al guardar a partir de los eventos."),
                "lanzador": st.column_config.SelectboxColumn(
                    "Lanzador", options=opciones_lanzador,
                    help="Si A_FAVOR: nuestro jugador. Si EN_CONTRA: 'RIVAL'."),
                "portero": st.column_config.SelectboxColumn(
                    "Portero", options=opciones_portero,
                    help="Si EN_CONTRA: nuestro portero. Si A_FAVOR: 'RIVAL'."),
                "resultado": st.column_config.SelectboxColumn(
                    "Resultado", options=PEN_RESULTADOS, width="small",
                    help="GOL · PARADA · POSTE · FUERA (FUERA cuenta también como DF del lanzador)"),
                "cuadrante": st.column_config.SelectboxColumn(
                    "Cuadrante", options=PEN_CUADRANTES, width="small",
                    help="A qué zona de portería va (vacío si va FUERA)"),
                "descripcion": st.column_config.TextColumn(
                    "Descripción", width="medium"),
            }
            return st.data_editor(
                df_pre, num_rows="dynamic", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )

        def _normalizar_penaltis_para_guardar(df_edit):
            """Limpia y valida. Devuelve (df, warns)."""
            warns = []
            if df_edit is None or df_edit.empty:
                return _df_penaltis_inicial(), warns
            df = df_edit.copy().fillna("")
            mask = (df["tipo_lanzamiento"].astype(str).str.strip() != "") | \
                    (df["resultado"].astype(str).str.strip() != "") | \
                    (df["lanzador"].astype(str).str.strip() != "")
            df = df[mask].reset_index(drop=True)
            if df.empty:
                return _df_penaltis_inicial(), warns
            # Normalizar minutos
            mmss_norm = []
            min_int = []
            for i, txt in enumerate(df["minuto_mmss"].astype(str)):
                m_int, m_mmss = _parse_mmss(txt)
                if m_int is None and txt.strip():
                    warns.append(f"Penalti fila {i+1}: minuto '{txt}' no se pudo parsear (MM:SS).")
                mmss_norm.append(m_mmss)
                min_int.append(m_int if m_int is not None else 0)
            df["minuto_mmss"] = mmss_norm
            df["minuto"] = min_int
            # Strings normalizados
            for c in ("tipo_lanzamiento", "condicion", "resultado", "cuadrante",
                       "lanzador", "portero"):
                df[c] = df[c].astype(str).str.strip().str.upper()
            df["parte"] = df["parte"].astype(str).str.strip()
            # Marcador como string (sin upper)
            if "marcador" not in df.columns:
                df["marcador"] = ""
            df["marcador"] = df["marcador"].astype(str).str.strip()
            # Validaciones
            for idx, r in df.iterrows():
                tipo = r["tipo_lanzamiento"]
                cond = r["condicion"]
                resu = r["resultado"]
                cuad = r["cuadrante"]
                lanz = r["lanzador"]
                port = r["portero"]
                if tipo and tipo not in ("PENALTI", "10M"):
                    warns.append(f"Penalti fila {idx+1}: tipo '{tipo}' inválido.")
                if cond and cond not in ("A_FAVOR", "EN_CONTRA"):
                    warns.append(f"Penalti fila {idx+1}: condición '{cond}' inválida.")
                if resu and resu not in ("GOL", "PARADA", "POSTE", "FUERA"):
                    warns.append(f"Penalti fila {idx+1}: resultado '{resu}' inválido.")
                # Cuadrante coherente con resultado
                if resu == "FUERA" and cuad:
                    warns.append(f"Penalti fila {idx+1}: resultado=FUERA pero cuadrante='{cuad}' "
                                  "(deja el cuadrante vacío).")
                if resu in ("GOL", "PARADA") and not cuad:
                    warns.append(f"Penalti fila {idx+1}: resultado={resu} sin cuadrante.")
                # Coherencia de lanzador/portero con condición
                if cond == "A_FAVOR" and lanz == "RIVAL":
                    warns.append(f"Penalti fila {idx+1}: A_FAVOR pero lanzador='RIVAL' "
                                  "(debe ser nuestro jugador).")
                if cond == "EN_CONTRA" and lanz and lanz != "RIVAL":
                    warns.append(f"Penalti fila {idx+1}: EN_CONTRA pero lanzador='{lanz}' "
                                  "(debe ser 'RIVAL').")
            return df, warns

        def _guardar_penaltis(partido_id, df_norm, cab):
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_PENALTIS_10M")
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet("EST_PENALTIS_10M", rows=200, cols=15)
                ws.update(values=[["partido_id"]], range_name="A1")
            df_all = pd.DataFrame(ws.get_all_records())
            cols = [
                "partido_id", "tipo", "competicion", "rival", "fecha",
                "tipo_lanzamiento", "condicion", "parte", "minuto",
                "minuto_mmss", "marcador", "lanzador", "portero",
                "resultado", "cuadrante", "descripcion",
            ]
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols)
            else:
                for c in cols:
                    if c not in df_all.columns:
                        df_all[c] = ""
            df_otros = df_all[df_all["partido_id"].astype(str) != str(partido_id)]
            if df_norm is None or df_norm.empty:
                df_nuevas = pd.DataFrame(columns=cols)
            else:
                df_nuevas = df_norm.copy()
                df_nuevas["partido_id"] = partido_id
                df_nuevas["tipo"] = cab["tipo"]
                df_nuevas["competicion"] = cab["competicion"]
                df_nuevas["rival"] = cab["rival"]
                df_nuevas["fecha"] = cab["fecha"]
                for c in cols:
                    if c not in df_nuevas.columns:
                        df_nuevas[c] = ""
                df_nuevas = df_nuevas[cols]
            df_final = pd.concat([df_otros[cols], df_nuevas], ignore_index=True).fillna("")
            ws.clear()
            ws.update(values=[cols] + df_final.astype(str).values.tolist(),
                       range_name="A1")
            return len(df_nuevas)

        # ── Iter 5: ZONAS (campo + portería) ────────────────────────────
        # Schema de EST_DISPAROS_ZONAS (ya existente):
        #   - 11 zonas de campo: G_AF_Z1..Z11 y G_EC_Z1..Z11 (solo goles)
        #   - 9 cuadrantes de portería: D_AF_P1..P9, G_AF_P1..P9 (disparos
        #     y goles a favor), D_EC_P1..P9, G_EC_P1..P9 (en contra)
        # Usamos un solo data_editor con 20 filas (11 zonas campo + 9
        # cuadrantes portería) y 6 columnas: tipo, código, gol_af, gol_ec,
        # disp_af, disp_ec. Para zonas de campo, las cols disp_* se quedan
        # como 0 (no se mide).
        ZONAS_CAMPO = [f"Z{i}" for i in range(1, 12)]    # 11
        ZONAS_PORTERIA = [f"P{i}" for i in range(1, 10)] # 9

        def _localizar_fila_zonas(df_all, partido_id, rival, fecha):
            """Devuelve la fila precargada (DataFrame de 1 fila) si existe."""
            if df_all.empty:
                return pd.DataFrame()
            # Match preferente por partido_id
            if "partido_id" in df_all.columns:
                fila_pre = df_all[
                    df_all["partido_id"].astype(str) == str(partido_id)
                ]
                if not fila_pre.empty:
                    return fila_pre
            # Fallback por (rival contains + fecha exact)
            if "rival" in df_all.columns:
                df_all = df_all.copy()
                df_all["_riv"] = df_all["rival"].astype(str).str.upper().str.strip()
                df_all["_fec"] = df_all["fecha"].astype(str).str.strip()
                rival_up = str(rival or "").upper().strip()
                fec = str(fecha or "").strip()
                tokens = [t for t in rival_up.replace("-", " ").split()
                          if len(t) >= 4]
                for t in tokens:
                    m = df_all[
                        (df_all["_riv"].str.contains(t, na=False, regex=False)) &
                        (df_all["_fec"] == fec)
                    ]
                    if not m.empty:
                        return m
            return pd.DataFrame()

        def _df_zonas_inicial(partido_id, rival, fecha, parte):
            """Construye el DataFrame de zonas para una PARTE concreta
            ("1T" o "2T"). Si existen columnas con sufijo _1T/_2T, las
            usa. Si no (datos viejos), inicializa _1T con el total y _2T
            con 0 — así no se pierde el dato antiguo al editar."""
            assert parte in ("1T", "2T"), f"parte debe ser 1T o 2T (got {parte})"
            try:
                sh = _conexion_sheet()
                ws = sh.worksheet("EST_DISPAROS_ZONAS")
                df_all = pd.DataFrame(ws.get_all_records())
            except Exception:
                df_all = pd.DataFrame()
            fila_pre = _localizar_fila_zonas(df_all, partido_id, rival, fecha)
            tiene_partes = (
                not fila_pre.empty and any(
                    c.endswith("_1T") for c in fila_pre.columns
                )
            )

            def _val(r, base_col):
                """Lee el valor de la columna con sufijo de parte si existe;
                si no, fallback al total (solo para 1T en datos antiguos)."""
                col_part = f"{base_col}_{parte}"
                if col_part in r.index:
                    return safe_int(r.get(col_part, 0))
                if not tiene_partes and parte == "1T":
                    return safe_int(r.get(base_col, 0))
                return 0

            filas = []
            for z in ZONAS_CAMPO:
                idx = z[1:]
                fila = {"tipo": "CAMPO", "zona": z,
                         "gol_af": 0, "gol_ec": 0,
                         "disp_af": 0, "disp_ec": 0}
                if not fila_pre.empty:
                    r = fila_pre.iloc[0]
                    fila["gol_af"] = _val(r, f"G_AF_Z{idx}")
                    fila["gol_ec"] = _val(r, f"G_EC_Z{idx}")
                filas.append(fila)
            for z in ZONAS_PORTERIA:
                idx = z[1:]
                fila = {"tipo": "PORTERÍA", "zona": z,
                         "gol_af": 0, "gol_ec": 0,
                         "disp_af": 0, "disp_ec": 0}
                if not fila_pre.empty:
                    r = fila_pre.iloc[0]
                    fila["gol_af"] = _val(r, f"G_AF_P{idx}")
                    fila["gol_ec"] = _val(r, f"G_EC_P{idx}")
                    fila["disp_af"] = _val(r, f"D_AF_P{idx}")
                    fila["disp_ec"] = _val(r, f"D_EC_P{idx}")
                filas.append(fila)
            return pd.DataFrame(filas, columns=[
                "tipo", "zona", "gol_af", "gol_ec", "disp_af", "disp_ec"])

        def _editor_zonas(df_pre, key):
            """data_editor compacto con 20 filas. Disparos solo se editan
            en cuadrantes de portería (en zonas de campo no se miden)."""
            cfg = {
                "tipo": st.column_config.TextColumn("Tipo", disabled=True, width="small"),
                "zona": st.column_config.TextColumn("Zona", disabled=True, width="small"),
                "gol_af": st.column_config.NumberColumn(
                    "Goles AF", min_value=0, max_value=20, format="%d",
                    help="Goles a FAVOR desde esta zona o en este cuadrante"),
                "gol_ec": st.column_config.NumberColumn(
                    "Goles EC", min_value=0, max_value=20, format="%d",
                    help="Goles EN CONTRA en esta zona o cuadrante"),
                "disp_af": st.column_config.NumberColumn(
                    "Disp. AF", min_value=0, max_value=50, format="%d",
                    help="Disparos a FAVOR (solo cuadrantes de portería)"),
                "disp_ec": st.column_config.NumberColumn(
                    "Disp. EC", min_value=0, max_value=50, format="%d",
                    help="Disparos EN CONTRA (solo cuadrantes de portería)"),
            }
            return st.data_editor(
                df_pre, num_rows="fixed", use_container_width=True,
                key=key, column_config=cfg, hide_index=True,
            )

        def _guardar_zonas(partido_id, df_zonas_1t, df_zonas_2t, cab):
            """Persiste en EST_DISPAROS_ZONAS. Guarda 3 grupos de columnas:
            base_col_1T (de df_zonas_1t), base_col_2T (de df_zonas_2t) y
            base_col (= 1T + 2T, total). Match por partido_id preferente,
            fallback rival+fecha. Si no existe, crea fila nueva."""
            import gspread
            sh = _conexion_sheet()
            try:
                ws = sh.worksheet("EST_DISPAROS_ZONAS")
            except gspread.exceptions.WorksheetNotFound:
                cols_full = ["competicion", "rival", "fecha", "partido_id"]
                # Total
                cols_full += [f"D_AF_P{i}" for i in range(1, 10)]
                cols_full += [f"G_AF_P{i}" for i in range(1, 10)]
                cols_full += [f"G_AF_Z{i}" for i in range(1, 12)]
                cols_full += [f"D_EC_P{i}" for i in range(1, 10)]
                cols_full += [f"G_EC_P{i}" for i in range(1, 10)]
                cols_full += [f"G_EC_Z{i}" for i in range(1, 12)]
                # Por parte
                for p in ("1T", "2T"):
                    cols_full += [f"D_AF_P{i}_{p}" for i in range(1, 10)]
                    cols_full += [f"G_AF_P{i}_{p}" for i in range(1, 10)]
                    cols_full += [f"G_AF_Z{i}_{p}" for i in range(1, 12)]
                    cols_full += [f"D_EC_P{i}_{p}" for i in range(1, 10)]
                    cols_full += [f"G_EC_P{i}_{p}" for i in range(1, 10)]
                    cols_full += [f"G_EC_Z{i}_{p}" for i in range(1, 12)]
                ws = sh.add_worksheet("EST_DISPAROS_ZONAS",
                                        rows=200, cols=len(cols_full) + 5)
                ws.update(values=[cols_full], range_name="A1")
            df_all = pd.DataFrame(ws.get_all_records())
            cols_existentes = list(df_all.columns) if not df_all.empty else []
            # Construir dict de fila nueva con _1T, _2T y total
            datos_nuevos = {
                "competicion": cab.get("competicion", ""),
                "rival": cab.get("rival", ""),
                "fecha": cab.get("fecha", ""),
                "partido_id": partido_id,
            }

            # Indexar por (tipo, zona) para acceso rápido
            def _index(df):
                return {(str(r["tipo"]), str(r["zona"])): r
                        for _, r in df.iterrows()}
            idx_1t = _index(df_zonas_1t)
            idx_2t = _index(df_zonas_2t)

            def _set_cells(base_col, valor_1t, valor_2t):
                v1 = safe_int(valor_1t)
                v2 = safe_int(valor_2t)
                datos_nuevos[f"{base_col}_1T"] = v1
                datos_nuevos[f"{base_col}_2T"] = v2
                datos_nuevos[base_col] = v1 + v2

            # Campo (Z1-Z11): solo goles
            for i in range(1, 12):
                z = f"Z{i}"
                k = ("CAMPO", z)
                r1 = idx_1t.get(k, {})
                r2 = idx_2t.get(k, {})
                _set_cells(f"G_AF_Z{i}", r1.get("gol_af", 0), r2.get("gol_af", 0))
                _set_cells(f"G_EC_Z{i}", r1.get("gol_ec", 0), r2.get("gol_ec", 0))
            # Portería (P1-P9): goles y disparos
            for i in range(1, 10):
                z = f"P{i}"
                k = ("PORTERÍA", z)
                r1 = idx_1t.get(k, {})
                r2 = idx_2t.get(k, {})
                _set_cells(f"G_AF_P{i}", r1.get("gol_af", 0), r2.get("gol_af", 0))
                _set_cells(f"G_EC_P{i}", r1.get("gol_ec", 0), r2.get("gol_ec", 0))
                _set_cells(f"D_AF_P{i}", r1.get("disp_af", 0), r2.get("disp_af", 0))
                _set_cells(f"D_EC_P{i}", r1.get("disp_ec", 0), r2.get("disp_ec", 0))
            # Asegurar columnas en df_all
            for c in datos_nuevos:
                if c not in cols_existentes:
                    cols_existentes.append(c)
                    if not df_all.empty:
                        df_all[c] = ""
            if df_all.empty:
                df_all = pd.DataFrame(columns=cols_existentes)
            # Buscar fila existente del partido
            mask = pd.Series(False, index=df_all.index)
            if "partido_id" in df_all.columns:
                mask = df_all["partido_id"].astype(str) == str(partido_id)
            if not mask.any() and "rival" in df_all.columns:
                rival_up = str(cab.get("rival", "")).upper().strip()
                tokens = [t for t in rival_up.replace("-", " ").split() if len(t) >= 4]
                for t in tokens:
                    candidate = (
                        df_all["rival"].astype(str).str.upper().str.contains(t, na=False) &
                        (df_all["fecha"].astype(str).str.strip() == str(cab.get("fecha", "")).strip())
                    )
                    if candidate.any():
                        mask = candidate
                        break
            # pandas 3.x: forzar object para asignaciones mixtas
            if not df_all.empty:
                df_all = df_all.astype(object)
            if mask.any():
                # Actualizar la fila existente
                idx = df_all.index[mask][0]
                for k, v in datos_nuevos.items():
                    df_all.at[idx, k] = str(v) if v not in ("", None) else ""
            else:
                # Añadir fila nueva (todo como string)
                fila_str = {k: (str(v) if v not in ("", None) else "")
                            for k, v in datos_nuevos.items()}
                df_all = pd.concat([df_all, pd.DataFrame([fila_str])],
                                     ignore_index=True)
            # Reescribir
            for c in cols_existentes:
                if c not in df_all.columns:
                    df_all[c] = ""
            df_out = df_all[cols_existentes].fillna("")
            ws.clear()
            ws.update(values=[cols_existentes] +
                              df_out.astype(str).values.tolist(),
                       range_name="A1")
            return len(df_zonas_1t) + len(df_zonas_2t)

        # ────────────────────────────────────────────────────────────────────
        if modo == "🆕 Crear partido nuevo":
            st.markdown("---")
            st.markdown("#### 🏁 Cabecera del partido")
            cab = _formulario_cabecera(key_pref="cr")

            # Totales de disparo por parte (opcional, expansible)
            totales_disp_cr = _formulario_totales_disparos(key_pref="cr")

            st.markdown("---")
            plantilla = _formulario_plantilla(key_pref="cr")

            st.markdown("---")
            st.markdown("#### ⚽ Eventos de gol")
            st.caption("Una fila por gol. Min en formato **MM:SS**. "
                        "Pistas 1-4 + portero (modo normal), o pistas 1-5 sin "
                        "portero (modo portero-jugador).")
            df_ev_edit = _editor_eventos(plantilla, _ev_dataframe_inicial(),
                                          key="cr_eventos")
            # Validación EN VIVO bajo el editor
            _, warns_live_cr = _normalizar_eventos_para_guardar(df_ev_edit)
            if warns_live_cr:
                st.markdown("**⚠️ Avisos sobre los eventos:**")
                for w in warns_live_cr:
                    st.warning(w)

            st.markdown("---")
            st.markdown("#### 📊 Métricas individuales (campo)")
            st.caption("Una fila por convocado. Min Total se calcula como Min 1T + Min 2T si lo dejas vacío.")
            df_camp_pre, df_port_pre = _df_metricas_inicial(plantilla, "")
            # Defaults vacíos (se rellenan si hay plantilla)
            df_camp_edit = pd.DataFrame()
            df_port_edit = pd.DataFrame()
            df_rot_1t_edit = pd.DataFrame()
            df_rot_2t_edit = pd.DataFrame()
            if not plantilla:
                st.info("Primero selecciona la plantilla del partido arriba.")
            else:
                df_camp_edit = _editor_metricas_campo(df_camp_pre, key="cr_metricas_campo")
                # Validación en vivo
                warns_met = _validar_metricas_campo(df_camp_edit)
                if warns_met:
                    st.markdown("**⚠️ Avisos métricas:**")
                    for w in warns_met:
                        st.warning(w)
                st.markdown("#### 🥅 Métricas de portería")
                st.caption("Solo aparece si hay porteros en la plantilla.")
                df_port_edit = _editor_metricas_porteria(df_port_pre, key="cr_metricas_porteria")

                # ── Rotaciones (iter 4) ────────────────────────────────────
                st.markdown("---")
                st.markdown("#### 🔄 Rotaciones individuales")
                st.caption(
                    "Una fila por convocado, con duración de cada rotación en MM:SS. "
                    "Las rotaciones cortas no apuntadas (≤ algunos segundos) se suman "
                    "al Min Total de la parte aunque no aparezcan aquí. La suma de "
                    "rotaciones de la parte debe ser ≤ Min de la parte.")
                col_rn1, col_rn2 = st.columns(2)
                with col_rn1:
                    n_rot_1t_cr = st.slider(
                        "Rotaciones a mostrar 1ª parte", 1, 8, 4,
                        key="cr_n_rot_1t",
                        help="Sólo muestra las primeras N rotaciones. Las demás se ocultan.")
                with col_rn2:
                    n_rot_2t_cr = st.slider(
                        "Rotaciones a mostrar 2ª parte", 1, 8, 4,
                        key="cr_n_rot_2t")
                st.markdown("**1ª parte**")
                df_rot_1t_pre = _df_rotaciones_inicial(plantilla, "", "1t")
                df_rot_1t_edit = _editor_rotaciones(
                    df_rot_1t_pre, n_rot_1t_cr, "1T", key="cr_rot_1t")
                warns_rot_1 = _validar_rotaciones(df_rot_1t_edit)
                if warns_rot_1:
                    st.markdown("**⚠️ Avisos rotaciones 1T:**")
                    for w in warns_rot_1:
                        st.warning(w)
                st.markdown("**2ª parte**")
                df_rot_2t_pre = _df_rotaciones_inicial(plantilla, "", "2t")
                df_rot_2t_edit = _editor_rotaciones(
                    df_rot_2t_pre, n_rot_2t_cr, "2T", key="cr_rot_2t")
                warns_rot_2 = _validar_rotaciones(df_rot_2t_edit)
                if warns_rot_2:
                    st.markdown("**⚠️ Avisos rotaciones 2T:**")
                    for w in warns_rot_2:
                        st.warning(w)

            # ── Faltas (iter 7) ────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 🟨 Faltas")
            st.caption(
                "Una fila por falta. EN_CONTRA = falta que cometemos · "
                "A_FAVOR = falta que recibimos. La 6ª por equipo en una "
                "parte → 10m sin barrera."
            )
            df_faltas_pre_cr = _df_faltas_inicial()
            df_faltas_edit_cr = _editor_faltas(
                plantilla, df_faltas_pre_cr, key="cr_faltas")
            df_faltas_norm_cr_live, warns_falt_cr = _normalizar_faltas_para_guardar(
                df_faltas_edit_cr)
            alertas_falt_cr = _calcular_alertas_faltas(df_faltas_norm_cr_live)
            for w in warns_falt_cr:
                st.warning(f"⚠️ {w}")
            for a in alertas_falt_cr:
                if a.startswith("⚠️"):
                    st.error(a)
                else:
                    st.warning(a)

            # ── 10 metros / Penaltis (iter 8) ────────────────────────────────
            st.markdown("---")
            st.markdown("#### 🎯 10 metros / Penaltis")
            st.caption(
                "PENALTI: 6m por falta dentro del área. "
                "10M: 10m por la 6ª falta del equipo. "
                "Si va FUERA, además debería sumar como DF del lanzador "
                "en la tabla de métricas."
            )
            df_pen_pre_cr = _df_penaltis_inicial()
            df_pen_edit_cr = _editor_penaltis(
                plantilla, df_pen_pre_cr, key="cr_penaltis")
            _, warns_pen_cr = _normalizar_penaltis_para_guardar(df_pen_edit_cr)
            for w in warns_pen_cr:
                st.warning(f"⚠️ {w}")

            # ── Zonas (iter 5) ────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📍 Zonas de gol y portería")
            st.caption(
                "11 zonas de campo (Z1-Z11) + 9 cuadrantes de portería "
                "(P1-P9). Una tabla por parte. El TOTAL del partido se "
                "calcula como 1ª + 2ª. **No metas penaltis ni 10m aquí** "
                "— van en su sección dedicada (penaltis se tiran en la "
                "convergencia A1+A2+A4+A5; 10m en A4+A5+A8+A9)."
            )
            st.markdown("**1ª parte**")
            df_zonas_pre_cr_1t = _df_zonas_inicial(
                cab["partido_id"], cab["rival"], cab["fecha"], "1T")
            df_zonas_edit_cr_1t = _editor_zonas(
                df_zonas_pre_cr_1t, key="cr_zonas_1t")
            st.markdown("**2ª parte**")
            df_zonas_pre_cr_2t = _df_zonas_inicial(
                cab["partido_id"], cab["rival"], cab["fecha"], "2T")
            df_zonas_edit_cr_2t = _editor_zonas(
                df_zonas_pre_cr_2t, key="cr_zonas_2t")
            # Vista previa del TOTAL (1T + 2T)
            with st.expander("🔢 Total del partido (1T + 2T) — preview"):
                _df_total_cr = df_zonas_edit_cr_1t.copy()
                for c in ("gol_af", "gol_ec", "disp_af", "disp_ec"):
                    _df_total_cr[c] = (
                        pd.to_numeric(df_zonas_edit_cr_1t[c], errors="coerce").fillna(0).astype(int)
                        + pd.to_numeric(df_zonas_edit_cr_2t[c], errors="coerce").fillna(0).astype(int)
                    )
                st.dataframe(_df_total_cr, use_container_width=True, hide_index=True)

            # ── Planillas imprimibles (papel/boli) — modo Crear ─────────
            st.markdown("---")
            st.markdown("#### 🖨 Planillas imprimibles para llevar al partido")
            st.caption(
                "**Genera las planillas ANTES del partido** sin necesidad de "
                "guardarlo todavía. Usa la cabecera y plantilla de arriba. "
                "Imprime, lleva al partido, apunta a boli, y luego "
                "transcribes los datos en este mismo form."
            )
            if not cab.get("rival") or not plantilla:
                st.info(
                    "💡 Rellena al menos el **rival** (cabecera) y la "
                    "**plantilla** para generar la planilla."
                )
            else:
                cpla1_cr, cpla2_cr = st.columns(2)
                # Construir datos directos a partir del form
                _datos_directos_cr = {
                    "rival": cab["rival"],
                    "fecha": cab.get("fecha", ""),
                    "lugar": cab.get("lugar", ""),
                    "hora": cab.get("hora", ""),
                    "competicion": cab.get("competicion", ""),
                    "local_visitante": cab.get("local_visitante", ""),
                    "jugadores": [
                        {"dorsal": p.get("dorsal", ""),
                         "jugador": p.get("jugador", ""),
                         "posicion": p.get("posicion", "")}
                        for p in plantilla
                    ],
                }
                with cpla1_cr:
                    if st.button("🖨 Planilla Arkaitz",
                                  key="pla_ark_cr", use_container_width=True):
                        try:
                            import sys as _sys
                            from pathlib import Path as _Path
                            _root = _Path(__file__).resolve().parent.parent
                            if str(_root) not in _sys.path:
                                _sys.path.insert(0, str(_root))
                            from src.pdf_planilla_blank import generar_planilla as _gen
                            with st.spinner("Generando planillas…"):
                                pdf_1t = _gen("arkaitz", "1T",
                                                datos_directos=_datos_directos_cr)
                                pdf_2t = _gen("arkaitz", "2T",
                                                datos_directos=_datos_directos_cr)
                            st.session_state["pla_ark_1t_cr"] = pdf_1t
                            st.session_state["pla_ark_2t_cr"] = pdf_2t
                        except Exception as e:
                            st.error(f"Error: {e}")
                            import traceback as _tb
                            st.expander("Detalles").code(_tb.format_exc())
                    if st.session_state.get("pla_ark_1t_cr"):
                        st.download_button(
                            "⬇️ Arkaitz 1ª parte",
                            data=st.session_state["pla_ark_1t_cr"],
                            file_name=f"planilla_arkaitz_1T_{cab['rival']}.pdf",
                            mime="application/pdf",
                            key="dl_ark_1t_cr",
                            use_container_width=True,
                        )
                    if st.session_state.get("pla_ark_2t_cr"):
                        st.download_button(
                            "⬇️ Arkaitz 2ª parte",
                            data=st.session_state["pla_ark_2t_cr"],
                            file_name=f"planilla_arkaitz_2T_{cab['rival']}.pdf",
                            mime="application/pdf",
                            key="dl_ark_2t_cr",
                            use_container_width=True,
                        )
                with cpla2_cr:
                    if st.button("🖨 Planilla Compañero",
                                  key="pla_comp_cr", use_container_width=True):
                        try:
                            import sys as _sys
                            from pathlib import Path as _Path
                            _root = _Path(__file__).resolve().parent.parent
                            if str(_root) not in _sys.path:
                                _sys.path.insert(0, str(_root))
                            from src.pdf_planilla_blank import generar_planilla as _gen
                            with st.spinner("Generando planilla…"):
                                # Compa: ahora 1 ÚNICO PDF con ambas partes en
                                # A4 vertical. El parámetro 'parte' se ignora.
                                pdf_compa = _gen("compa", "1T",
                                                  datos_directos=_datos_directos_cr)
                            st.session_state["pla_comp_cr"] = pdf_compa
                        except Exception as e:
                            st.error(f"Error: {e}")
                    if st.session_state.get("pla_comp_cr"):
                        st.download_button(
                            "⬇️ Compañero (1ª + 2ª parte)",
                            data=st.session_state["pla_comp_cr"],
                            file_name=f"planilla_compa_{cab['rival']}.pdf",
                            mime="application/pdf",
                            key="dl_comp_cr",
                            use_container_width=True,
                        )

            if st.button("💾 Guardar partido", type="primary", key="cr_guardar"):
                if not cab["rival"]:
                    st.error("Pon el nombre del rival.")
                elif not cab["partido_id"]:
                    st.error("Pon el ID del partido (ej: J27.PEÑISCOLA).")
                elif not plantilla:
                    st.error("Selecciona al menos un convocado.")
                else:
                    df_ev_norm, warns_ev = _normalizar_eventos_para_guardar(
                        df_ev_edit)
                    metricas_dict = _normalizar_metricas_para_guardar(
                        df_camp_edit, df_port_edit)
                    rot_dict = _normalizar_rotaciones_para_guardar(
                        df_rot_1t_edit, df_rot_2t_edit)
                    df_faltas_norm_cr, warns_falt_save_cr = \
                        _normalizar_faltas_para_guardar(df_faltas_edit_cr)
                    df_pen_norm_cr, warns_pen_save_cr = \
                        _normalizar_penaltis_para_guardar(df_pen_edit_cr)
                    # Autorrellenar marcador desde df_ev_norm
                    df_pen_norm_cr = _autorellenar_marcador_penaltis(
                        df_pen_norm_cr, df_ev_norm)
                    try:
                        with st.spinner("Guardando…"):
                            _guardar_cabecera_totales(cab, totales_disp_cr)
                            n_pl = _guardar_plantilla(
                                cab["partido_id"], plantilla, cab)
                            n_met = _guardar_metricas(
                                cab["partido_id"], metricas_dict, cab)
                            n_rot = _guardar_rotaciones(
                                cab["partido_id"], rot_dict)
                            n_ev = _guardar_eventos(
                                cab["partido_id"], cab["tipo"], cab["competicion"],
                                cab["rival"], cab["fecha"], df_ev_norm
                            )
                            n_falt = _guardar_faltas(
                                cab["partido_id"], df_faltas_norm_cr, cab)
                            n_pen = _guardar_penaltis(
                                cab["partido_id"], df_pen_norm_cr, cab)
                            n_zon = _guardar_zonas(
                                cab["partido_id"],
                                df_zonas_edit_cr_1t, df_zonas_edit_cr_2t,
                                cab)
                        st.success(
                            f"✅ Partido creado. Cabecera + {n_pl} convocados "
                            f"+ {n_met} con métricas + {n_rot} con rotaciones "
                            f"+ {n_ev} eventos + {n_falt} faltas + {n_pen} penaltis/10m "
                            f"+ {n_zon} zonas."
                        )
                        for w in warns_ev:
                            st.warning(f"⚠️ {w}")
                        for w in warns_falt_save_cr:
                            st.warning(f"⚠️ {w}")
                        for w in warns_pen_save_cr:
                            st.warning(f"⚠️ {w}")
                        st.cache_data.clear()
                        st.info("Refresca la página para ver el nuevo partido en otras pestañas.")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

        # ────────────────────────────────────────────────────────────────────
        else:
            # Modo editar
            if est_partidos.empty:
                st.warning("No hay partidos para editar.")
            else:
                st.markdown("---")
                ep_e = est_partidos.copy()
                ep_e["_fdate"] = pd.to_datetime(ep_e["fecha"], errors="coerce")
                meta_e = (ep_e.groupby("partido_id", as_index=False)
                           .agg(tipo=("tipo", "first"),
                                competicion=("competicion", "first"),
                                rival=("rival", "first"),
                                fecha=("fecha", "first"),
                                _fkey=("_fdate", "first")))
                meta_e = meta_e.sort_values("_fkey", ascending=False, na_position="last")
                meta_e["label"] = meta_e.apply(
                    lambda r: f"{r['fecha'] or '—'} · {r['partido_id']} — {r['rival']}",
                    axis=1,
                )
                sel_label = st.selectbox(
                    "Selecciona partido a editar",
                    meta_e["label"].tolist(),
                    key="ed_sel",
                )
                pid_sel = meta_e[meta_e["label"] == sel_label]["partido_id"].iloc[0]
                m = meta_e[meta_e["partido_id"] == pid_sel].iloc[0]

                # Cabecera precargada
                fecha_default = pd.to_datetime(m["fecha"], errors="coerce")
                fecha_default = fecha_default.date() if pd.notna(fecha_default) else _dt.date.today()
                # Goles actuales del partido (de eventos)
                ev_actual = est_eventos[est_eventos["partido_id"] == pid_sel] if not est_eventos.empty else pd.DataFrame()
                gf_act = int((ev_actual["equipo_marca"] == "INTER").sum()) if not ev_actual.empty else 0
                gc_act = int((ev_actual["equipo_marca"] == "RIVAL").sum()) if not ev_actual.empty else 0

                # Defaults extra desde EST_TOTALES_PARTIDO si los hay
                hora_def = lugar_def = ""
                local_def = None
                if not est_tot_partido.empty:
                    fila_t = est_tot_partido[
                        est_tot_partido["partido_id"].astype(str) == pid_sel]
                    if not fila_t.empty:
                        ft = fila_t.iloc[0]
                        hora_def = str(ft.get("hora", "") or "")
                        lugar_def = str(ft.get("lugar", "") or "")
                        lv = str(ft.get("local_visitante", "") or "").upper()
                        if lv == "LOCAL":
                            local_def = True
                        elif lv == "VISITANTE":
                            local_def = False

                st.markdown("#### 🏁 Cabecera del partido")
                cab = _formulario_cabecera(
                    rival_def=m["rival"],
                    fecha_def=fecha_default,
                    comp_def=m["tipo"],
                    hora_def=hora_def, lugar_def=lugar_def,
                    gf_def=gf_act, gc_def=gc_act,
                    partido_id_def=pid_sel,
                    local_def=local_def,
                    key_pref="ed",
                )

                # Plantilla precargada (de EST_PLANTILLAS si existe)
                st.markdown("---")
                convocados_def = []
                try:
                    sh_pl = _conexion_sheet()
                    ws_pl = sh_pl.worksheet("EST_PLANTILLAS")
                    df_pl = pd.DataFrame(ws_pl.get_all_records())
                    if not df_pl.empty:
                        convocados_def = (
                            df_pl[df_pl["partido_id"].astype(str) == pid_sel]
                            ["jugador"].astype(str).str.upper().tolist()
                        )
                except Exception:
                    pass
                # Si no hay plantilla guardada, usar los jugadores con minutos
                # del partido (convocados implícitamente)
                if not convocados_def and not est_partidos.empty:
                    ep_pid = est_partidos[est_partidos["partido_id"] == pid_sel]
                    convocados_def = (
                        ep_pid[pd.to_numeric(ep_pid.get("min_total", 0),
                                                errors="coerce").fillna(0) > 0]
                        ["jugador"].astype(str).str.upper().tolist()
                    )
                plantilla = _formulario_plantilla(
                    convocados_def=convocados_def, key_pref="ed")

                # Totales de disparo por parte (precargados de
                # EST_TOTALES_PARTIDO si existían)
                tot_pre_disp = {}
                if not est_tot_partido.empty:
                    fila_t = est_tot_partido[
                        est_tot_partido["partido_id"].astype(str) == pid_sel]
                    if not fila_t.empty:
                        ft = fila_t.iloc[0]
                        for k in ("dt_inter_1t", "dt_inter_2t",
                                   "dp_inter_1t", "dp_inter_2t",
                                   "dt_rival_1t", "dt_rival_2t",
                                   "dp_rival_1t", "dp_rival_2t"):
                            tot_pre_disp[k] = safe_int(ft.get(k, 0))
                totales_disp_ed = _formulario_totales_disparos(
                    tot_pre=tot_pre_disp, key_pref=f"ed_{pid_sel}")

                st.markdown("---")
                st.markdown("#### ⚽ Eventos de gol")
                st.caption("Una fila por gol. Min en formato **MM:SS**. "
                            "Pistas 1-4 + portero (modo normal), o pistas 1-5 "
                            "sin portero (modo portero-jugador).")
                df_ev_pre_norm = _ev_desde_df_existente(ev_actual)
                df_ev_edit = _editor_eventos(plantilla, df_ev_pre_norm,
                                              key=f"ed_eventos_{pid_sel}")
                # Validación EN VIVO bajo el editor
                _, warns_live_ed = _normalizar_eventos_para_guardar(df_ev_edit)
                if warns_live_ed:
                    st.markdown("**⚠️ Avisos sobre los eventos:**")
                    for w in warns_live_ed:
                        st.warning(w)

                # ── Métricas individuales (precargadas del partido) ───────
                st.markdown("---")
                st.markdown("#### 📊 Métricas individuales (campo)")
                st.caption("Una fila por convocado. Min Total se calcula como Min 1T + Min 2T si lo dejas vacío.")
                df_camp_pre, df_port_pre = _df_metricas_inicial(plantilla, pid_sel)
                # Defaults vacíos
                df_camp_edit_e = pd.DataFrame()
                df_port_edit_e = pd.DataFrame()
                df_rot_1t_edit_e = pd.DataFrame()
                df_rot_2t_edit_e = pd.DataFrame()
                if not plantilla:
                    st.info("Selecciona la plantilla arriba para editar las métricas.")
                else:
                    df_camp_edit_e = _editor_metricas_campo(
                        df_camp_pre, key=f"ed_metricas_campo_{pid_sel}")
                    warns_met_e = _validar_metricas_campo(df_camp_edit_e)
                    if warns_met_e:
                        st.markdown("**⚠️ Avisos métricas:**")
                        for w in warns_met_e:
                            st.warning(w)
                    st.markdown("#### 🥅 Métricas de portería")
                    df_port_edit_e = _editor_metricas_porteria(
                        df_port_pre, key=f"ed_metricas_porteria_{pid_sel}")

                    # ── Rotaciones (iter 4) ────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### 🔄 Rotaciones individuales")
                    st.caption(
                        "Una fila por convocado. La suma de rotaciones de la "
                        "parte debe ser ≤ Min de la parte (las rotaciones "
                        "cortas no apuntadas también suman al Min Total).")
                    col_rn1, col_rn2 = st.columns(2)
                    with col_rn1:
                        n_rot_1t_ed = st.slider(
                            "Rotaciones a mostrar 1ª parte", 1, 8, 8,
                            key=f"ed_n_rot_1t_{pid_sel}")
                    with col_rn2:
                        n_rot_2t_ed = st.slider(
                            "Rotaciones a mostrar 2ª parte", 1, 8, 8,
                            key=f"ed_n_rot_2t_{pid_sel}")
                    st.markdown("**1ª parte**")
                    df_rot_1t_pre = _df_rotaciones_inicial(plantilla, pid_sel, "1t")
                    df_rot_1t_edit_e = _editor_rotaciones(
                        df_rot_1t_pre, n_rot_1t_ed, "1T",
                        key=f"ed_rot_1t_{pid_sel}")
                    warns_rot_1 = _validar_rotaciones(df_rot_1t_edit_e)
                    if warns_rot_1:
                        st.markdown("**⚠️ Avisos rotaciones 1T:**")
                        for w in warns_rot_1:
                            st.warning(w)
                    st.markdown("**2ª parte**")
                    df_rot_2t_pre = _df_rotaciones_inicial(plantilla, pid_sel, "2t")
                    df_rot_2t_edit_e = _editor_rotaciones(
                        df_rot_2t_pre, n_rot_2t_ed, "2T",
                        key=f"ed_rot_2t_{pid_sel}")
                    warns_rot_2 = _validar_rotaciones(df_rot_2t_edit_e)
                    if warns_rot_2:
                        st.markdown("**⚠️ Avisos rotaciones 2T:**")
                        for w in warns_rot_2:
                            st.warning(w)

                # ── Faltas (iter 7) — modo Editar ──────────────────────
                st.markdown("---")
                st.markdown("#### 🟨 Faltas")
                st.caption(
                    "Una fila por falta. EN_CONTRA = falta que cometemos · "
                    "A_FAVOR = falta que recibimos. La 6ª por equipo en una "
                    "parte → 10m sin barrera."
                )
                df_faltas_pre_ed = _df_faltas_desde_sheet(pid_sel)
                df_faltas_edit_ed = _editor_faltas(
                    plantilla, df_faltas_pre_ed,
                    key=f"ed_faltas_{pid_sel}")
                df_faltas_norm_ed_live, warns_falt_ed = \
                    _normalizar_faltas_para_guardar(df_faltas_edit_ed)
                alertas_falt_ed = _calcular_alertas_faltas(df_faltas_norm_ed_live)
                for w in warns_falt_ed:
                    st.warning(f"⚠️ {w}")
                for a in alertas_falt_ed:
                    if a.startswith("⚠️"):
                        st.error(a)
                    else:
                        st.warning(a)

                # ── 10 metros / Penaltis (iter 8) — modo Editar ──────────────
                st.markdown("---")
                st.markdown("#### 🎯 10 metros / Penaltis")
                st.caption(
                    "PENALTI: 6m por falta dentro del área. "
                    "10M: 10m por la 6ª falta del equipo."
                )
                df_pen_pre_ed = _df_penaltis_desde_sheet(pid_sel)
                df_pen_edit_ed = _editor_penaltis(
                    plantilla, df_pen_pre_ed, key=f"ed_penaltis_{pid_sel}")
                _, warns_pen_ed = _normalizar_penaltis_para_guardar(df_pen_edit_ed)
                for w in warns_pen_ed:
                    st.warning(f"⚠️ {w}")

                # ── Zonas (iter 5+11) — modo Editar ──────────────────────
                st.markdown("---")
                st.markdown("#### 📍 Zonas de gol y portería")
                st.caption(
                    "Una tabla por parte. El TOTAL del partido se calcula "
                    "como 1ª + 2ª. **No metas penaltis ni 10m aquí** — van "
                    "en su sección dedicada (penaltis: convergencia "
                    "A1+A2+A4+A5; 10m: A4+A5+A8+A9)."
                )
                st.markdown("**1ª parte**")
                df_zonas_pre_ed_1t = _df_zonas_inicial(
                    pid_sel, m["rival"], str(m["fecha"]), "1T")
                df_zonas_edit_ed_1t = _editor_zonas(
                    df_zonas_pre_ed_1t, key=f"ed_zonas_1t_{pid_sel}")
                st.markdown("**2ª parte**")
                df_zonas_pre_ed_2t = _df_zonas_inicial(
                    pid_sel, m["rival"], str(m["fecha"]), "2T")
                df_zonas_edit_ed_2t = _editor_zonas(
                    df_zonas_pre_ed_2t, key=f"ed_zonas_2t_{pid_sel}")
                with st.expander("🔢 Total del partido (1T + 2T) — preview"):
                    _df_total_ed = df_zonas_edit_ed_1t.copy()
                    for c in ("gol_af", "gol_ec", "disp_af", "disp_ec"):
                        _df_total_ed[c] = (
                            pd.to_numeric(df_zonas_edit_ed_1t[c], errors="coerce").fillna(0).astype(int)
                            + pd.to_numeric(df_zonas_edit_ed_2t[c], errors="coerce").fillna(0).astype(int)
                        )
                    st.dataframe(_df_total_ed, use_container_width=True, hide_index=True)

                # ── Planillas imprimibles (papel/boli) ─────────────────────
                st.markdown("---")
                st.markdown("#### 🖨 Planillas imprimibles para llevar al partido")
                st.caption(
                    "Genera planillas A4 horizontal en blanco para apuntar "
                    "a boli durante el partido. Cabecera y plantilla "
                    "pre-rellenadas con los datos de este partido. "
                    "Se imprimen 2 hojas iguales por planilla (1ª y 2ª "
                    "parte) para usar una en cada parte."
                )
                cpla1, cpla2 = st.columns(2)
                with cpla1:
                    if st.button("🖨 Planilla Arkaitz (4 PDFs)",
                                  key="pla_ark", use_container_width=True,
                                  help="Tu planilla: disparos, mapas Inter/rival, "
                                        "portería, goles, faltas. 1T + 2T."):
                        try:
                            import sys as _sys
                            from pathlib import Path as _Path
                            _root = _Path(__file__).resolve().parent.parent
                            if str(_root) not in _sys.path:
                                _sys.path.insert(0, str(_root))
                            from src.pdf_planilla_blank import generar_planilla as _gen
                            # Usar datos directos del form (sin abrir Sheet
                            # de nuevo → evita 429 quota exceeded)
                            _datos_directos_ed = {
                                "rival": cab.get("rival", ""),
                                "fecha": cab.get("fecha", ""),
                                "lugar": cab.get("lugar", ""),
                                "hora": cab.get("hora", ""),
                                "competicion": cab.get("competicion", ""),
                                "local_visitante": cab.get("local_visitante", ""),
                                "jugadores": [
                                    {"dorsal": p.get("dorsal", ""),
                                     "jugador": p.get("jugador", ""),
                                     "posicion": p.get("posicion", "")}
                                    for p in (plantilla or [])
                                ],
                            }
                            with st.spinner("Generando planillas…"):
                                pdf_1t = _gen("arkaitz", "1T",
                                                datos_directos=_datos_directos_ed)
                                pdf_2t = _gen("arkaitz", "2T",
                                                datos_directos=_datos_directos_ed)
                            st.session_state[f"pla_ark_1t_{pid_sel}"] = pdf_1t
                            st.session_state[f"pla_ark_2t_{pid_sel}"] = pdf_2t
                        except Exception as e:
                            st.error(f"Error: {e}")
                            import traceback as _tb
                            st.expander("Detalles").code(_tb.format_exc())
                    if st.session_state.get(f"pla_ark_1t_{pid_sel}"):
                        st.download_button(
                            "⬇️ Arkaitz 1ª parte",
                            data=st.session_state[f"pla_ark_1t_{pid_sel}"],
                            file_name=f"planilla_arkaitz_1T_{pid_sel}.pdf",
                            mime="application/pdf",
                            key=f"dl_ark_1t_{pid_sel}",
                            use_container_width=True,
                        )
                    if st.session_state.get(f"pla_ark_2t_{pid_sel}"):
                        st.download_button(
                            "⬇️ Arkaitz 2ª parte",
                            data=st.session_state[f"pla_ark_2t_{pid_sel}"],
                            file_name=f"planilla_arkaitz_2T_{pid_sel}.pdf",
                            mime="application/pdf",
                            key=f"dl_ark_2t_{pid_sel}",
                            use_container_width=True,
                        )
                with cpla2:
                    if st.button("🖨 Planilla Compañero (4 PDFs)",
                                  key="pla_comp", use_container_width=True,
                                  help="Para el compañero: PF/PNF/Robos/Cortes/"
                                        "BDG/BDP por jugador + córners + bandas. "
                                        "1T + 2T."):
                        try:
                            import sys as _sys
                            from pathlib import Path as _Path
                            _root = _Path(__file__).resolve().parent.parent
                            if str(_root) not in _sys.path:
                                _sys.path.insert(0, str(_root))
                            from src.pdf_planilla_blank import generar_planilla as _gen
                            _datos_directos_ed = {
                                "rival": cab.get("rival", ""),
                                "fecha": cab.get("fecha", ""),
                                "lugar": cab.get("lugar", ""),
                                "hora": cab.get("hora", ""),
                                "competicion": cab.get("competicion", ""),
                                "local_visitante": cab.get("local_visitante", ""),
                                "jugadores": [
                                    {"dorsal": p.get("dorsal", ""),
                                     "jugador": p.get("jugador", ""),
                                     "posicion": p.get("posicion", "")}
                                    for p in (plantilla or [])
                                ],
                            }
                            with st.spinner("Generando planilla…"):
                                # Compa: 1 PDF con ambas partes en A4 vertical
                                pdf_compa = _gen("compa", "1T",
                                                  datos_directos=_datos_directos_ed)
                            st.session_state[f"pla_comp_{pid_sel}"] = pdf_compa
                        except Exception as e:
                            st.error(f"Error: {e}")
                    if st.session_state.get(f"pla_comp_{pid_sel}"):
                        st.download_button(
                            "⬇️ Compañero (1ª + 2ª parte)",
                            data=st.session_state[f"pla_comp_{pid_sel}"],
                            file_name=f"planilla_compa_{pid_sel}.pdf",
                            mime="application/pdf",
                            key=f"dl_comp_{pid_sel}",
                            use_container_width=True,
                        )

                if st.button("💾 Guardar cambios", type="primary", key="ed_guardar"):
                    df_ev_norm, warns_ev = _normalizar_eventos_para_guardar(
                        df_ev_edit)
                    metricas_dict_e = _normalizar_metricas_para_guardar(
                        df_camp_edit_e, df_port_edit_e)
                    rot_dict_e = _normalizar_rotaciones_para_guardar(
                        df_rot_1t_edit_e, df_rot_2t_edit_e)
                    df_faltas_norm_ed, warns_falt_save_ed = \
                        _normalizar_faltas_para_guardar(df_faltas_edit_ed)
                    df_pen_norm_ed, warns_pen_save_ed = \
                        _normalizar_penaltis_para_guardar(df_pen_edit_ed)
                    # Autorrellenar marcador desde df_ev_norm
                    df_pen_norm_ed = _autorellenar_marcador_penaltis(
                        df_pen_norm_ed, df_ev_norm)
                    try:
                        with st.spinner("Guardando…"):
                            _guardar_cabecera_totales(cab, totales_disp_ed)
                            n_pl = _guardar_plantilla(
                                cab["partido_id"], plantilla, cab) if plantilla else 0
                            n_met = _guardar_metricas(
                                cab["partido_id"], metricas_dict_e, cab) \
                                    if metricas_dict_e else 0
                            n_rot = _guardar_rotaciones(
                                cab["partido_id"], rot_dict_e)
                            n_ev = _guardar_eventos(
                                cab["partido_id"], cab["tipo"], cab["competicion"],
                                cab["rival"], cab["fecha"], df_ev_norm
                            )
                            n_falt = _guardar_faltas(
                                cab["partido_id"], df_faltas_norm_ed, cab)
                            n_pen = _guardar_penaltis(
                                cab["partido_id"], df_pen_norm_ed, cab)
                            n_zon = _guardar_zonas(
                                cab["partido_id"],
                                df_zonas_edit_ed_1t, df_zonas_edit_ed_2t,
                                cab)
                        st.success(
                            f"✅ Guardado: cabecera + {n_pl} convocados + "
                            f"{n_met} con métricas + {n_rot} con rotaciones "
                            f"+ {n_ev} eventos + {n_falt} faltas + {n_pen} penaltis/10m "
                            f"+ {n_zon} zonas."
                        )
                        for w in warns_ev:
                            st.warning(f"⚠️ {w}")
                        for w in warns_falt_save_ed:
                            st.warning(f"⚠️ {w}")
                        for w in warns_pen_save_ed:
                            st.warning(f"⚠️ {w}")
                        st.cache_data.clear()
                        st.info("Refresca para ver los cambios en otras pestañas.")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

    except Exception as _e_tab:
        st.error(f'❌ Error en pestaña ✏️ Editar partido: {_e_tab}')
        import traceback as _tb
        st.expander('Detalles técnicos').code(_tb.format_exc())
