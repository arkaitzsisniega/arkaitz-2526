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
from pathlib import Path

# ── Config página ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Arkaitz · 25/26",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ── Conexión Google Sheets ────────────────────────────────────────────────────
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets",
               "https://www.googleapis.com/auth/drive"]


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
        # Fallback para hojas con cabeceras duplicadas o fusionadas (ej. LESIONES)
        rows = ws.get_all_values()
        if not rows:
            return pd.DataFrame()
        # Usar la segunda fila como cabecera real (la primera son grupos de color)
        headers = rows[1] if len(rows) > 1 else rows[0]
        # Desduplicar cabeceras vacías
        seen = {}
        clean = []
        for h in headers:
            h = h.strip()
            if h == "":
                h = "_VACÍO"
            if h in seen:
                seen[h] += 1
                h = f"{h}_{seen[h]}"
            else:
                seen[h] = 0
            clean.append(h)
        data_rows = rows[2:] if len(rows) > 2 else []
        return pd.DataFrame(data_rows, columns=clean)


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
    try:
        est_jug = cargar("_VISTA_EST_JUGADOR")
        est_partidos = cargar("EST_PARTIDOS")
        est_eventos = cargar("EST_EVENTOS")
    except Exception:
        est_jug = pd.DataFrame()
        est_partidos = pd.DataFrame()
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
        scout_raw = cargar("SCOUTING_RIVALES")
        scout_agr = cargar("_VISTA_SCOUTING_RIVAL")
    except Exception:
        scout_raw = pd.DataFrame()
        scout_agr = pd.DataFrame()

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

    return carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 18px 0 10px 0;">
        <div style="font-size:2.2rem; font-weight:900; color:#4CAF50; letter-spacing:2px;">INTER</div>
        <div style="font-size:0.75rem; color:#BBCDE8; letter-spacing:4px; margin-top:-4px;">FUTSAL SALA</div>
        <div style="width:60px; height:3px; background:#4CAF50; margin:8px auto 0 auto; border-radius:2px;"></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    try:
        carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr = datos()
        data_ok = True
    except ValueError as e:
        # Cache obsoleto tras cambiar la firma de datos() → limpiamos y reintentamos
        if "values to unpack" in str(e):
            try:
                st.cache_data.clear()
            except Exception:
                pass
            try:
                carga, semanal, peso, df_well, sem, rec, les, oliver, ejercicios, est_jug, est_partidos, est_eventos, est_avanz, est_cuart, est_disparos, scout_raw, scout_agr = datos()
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
    fecha_min = carga["FECHA"].min().date()
    fecha_max = min(carga["FECHA"].max().date(), _hoy)  # nunca permitir futuro
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

(tab_sem, tab_carga, tab_peso, tab_well, tab_les, tab_rec, tab_oliver,
 tab_ejer, tab_estad, tab_efic, tab_scout) = st.tabs([
    "🚦 Semáforo",
    "📊 Carga",
    "⚖️ Peso",
    "💤 Wellness",
    "🏥 Lesiones",
    "📋 Recuento",
    "🏃 Oliver",
    "🎯 Ejercicios",
    "🏆 Estadísticas",
    "📈 Eficiencia",
    "🔍 Scouting",
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
    sem_ordenado = sem_f.sort_values("ALERTAS_ACTIVAS", ascending=False)

    CARD_COLORS = {
        "ROJO":    ("rgba(183,28,28,0.92)",  "#FFCDD2", "#B71C1C"),
        "NARANJA": ("rgba(230,81,0,0.90)",   "#FFE0B2", "#E65100"),
        "AMARILLO":("rgba(245,127,23,0.88)", "#FFF9C4", "#F57F17"),
        "VERDE":   ("rgba(27,94,32,0.88)",   "#C8E6C9", "#1B5E20"),
        "AZUL":    ("rgba(21,101,192,0.88)", "#BBDEFB", "#1565C0"),
        "GRIS":    ("rgba(97,97,97,0.80)",   "#F5F5F5", "#424242"),
    }

    n_cols = 4
    rows_cards = [sem_ordenado.iloc[i:i+n_cols] for i in range(0, len(sem_ordenado), n_cols)]

    for row_group in rows_cards:
        cols_sem = st.columns(n_cols)
        for i, (_, row) in enumerate(row_group.iterrows()):
            estado      = row.get("SEMAFORO_GLOBAL", "GRIS")
            bg, _, txt  = CARD_COLORS.get(estado, CARD_COLORS["GRIS"])
            emoji, _    = MAP_SEMAFORO.get(estado, ("⚫", GRIS))

            jugador_nom = row["JUGADOR"]
            acwr        = row.get("ACWR")
            peso_desv   = row.get("PESO_PRE_DESV_KG")
            alertas     = int(row.get("ALERTAS_ACTIVAS", 0))
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
            )
            fig.update_layout(**LAYOUT, height=320, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    with c_der:
        st.markdown("#### Borg medio por sesión")
        if not sem_df.empty:
            fig2 = px.bar(
                sem_df.groupby("DIA_TURNO")["BORG"].mean().reset_index(),
                x="DIA_TURNO", y="BORG",
                color="BORG",
                color_continuous_scale=["#81C784", "#FFF176", "#EF9A9A"],
                range_color=[0, 10],
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
        pivot_pre  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PESO_PRE",  aggfunc="first").round(1)
        pivot_post = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PESO_POST", aggfunc="first").round(1)
        pivot_dif  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="DIFERENCIA",aggfunc="first").round(2)
        pivot_pct  = peso_sem.pivot_table(index="JUGADOR", columns="DIA", values="PCT_PERDIDA",aggfunc="first").round(1)

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
        pivot_well_dia = well_sem.pivot_table(
            index="JUGADOR", columns="DIA", values="TOTAL", aggfunc="mean"
        ).round(1)
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
    st.markdown("### Registro de lesiones")

    les_f = les.copy()
    # Filtrar columnas vacías de forma segura (evita TypeError con datetime64 en pandas 2.x)
    def _col_tiene_datos(s):
        try:
            return s.astype(str).str.strip().ne("").any()
        except Exception:
            return True
    les_f = les_f[[c for c in les_f.columns
                   if not c.startswith("_VACÍO") and _col_tiene_datos(les_f[c])]]

    # Filtrar filas vacías o de plantilla: exige JUGADOR + FECHA LESIÓN válidas
    if "JUGADOR" in les_f.columns and "FECHA LESIÓN" in les_f.columns:
        jug_ok = les_f["JUGADOR"].astype(str).str.strip().ne("") & les_f["JUGADOR"].notna()
        fecha_ok = les_f["FECHA LESIÓN"].notna()
        les_f = les_f[jug_ok & fecha_ok].reset_index(drop=True)

    # Lesiones activas (sin fecha de alta)
    try:
        if "FECHA ALTA" in les_f.columns and "FECHA LESIÓN" in les_f.columns:
            les_activas = les_f[les_f["FECHA ALTA"].isna() & les_f["FECHA LESIÓN"].notna()]
            if "JUGADOR" in les_activas.columns:
                les_activas = les_activas[les_activas["JUGADOR"].isin(sel_jugadores)]
        else:
            les_activas = pd.DataFrame()
    except Exception:
        les_activas = pd.DataFrame()

    if not les_activas.empty:
        st.error(f"🔴 {len(les_activas)} lesión/es activa/s ahora mismo")
        st.dataframe(les_activas, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No hay lesiones activas en este momento")

    st.markdown("---")
    st.markdown("### Historial completo")

    try:
        les_hist = les_f[les_f["JUGADOR"].isin(sel_jugadores)] if "JUGADOR" in les_f.columns else les_f
    except Exception:
        les_hist = les_f

    if les_hist.empty:
        st.info("Aún no hay lesiones registradas.")
    else:
        st.dataframe(les_hist, use_container_width=True, hide_index=True)

    # Estadísticas si hay suficientes datos
    if len(les_hist) >= 3:
        st.markdown("---")
        st.markdown("### Estadísticas de lesiones")
        c_l1, c_l2 = st.columns(2)

        with c_l1:
            if "ZONA CORPORAL" in les_hist.columns:
                zona_cnt = les_hist["ZONA CORPORAL"].value_counts().reset_index()
                zona_cnt.columns = ["Zona", "Lesiones"]
                fig_zona = px.bar(zona_cnt, x="Lesiones", y="Zona", orientation="h",
                                  title="Lesiones por zona corporal",
                                  color="Lesiones", color_continuous_scale="Reds")
                fig_zona.update_layout(**LAYOUT, height=350, coloraxis_showscale=False)
                st.plotly_chart(fig_zona, use_container_width=True)

        with c_l2:
            if "TIPO LESIÓN" in les_hist.columns:
                tipo_cnt = les_hist["TIPO LESIÓN"].value_counts().reset_index()
                tipo_cnt.columns = ["Tipo", "Nº"]
                fig_tipo = px.pie(tipo_cnt, names="Tipo", values="Nº",
                                  title="Tipo de lesión",
                                  color_discrete_sequence=px.colors.qualitative.Set3)
                fig_tipo.update_layout(**LAYOUT, height=350)
                st.plotly_chart(fig_tipo, use_container_width=True)


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
                st.caption("Agregado del jugador en el/los ejercicio(s) seleccionado(s).")
                rank = f.groupby("jugador", as_index=False).agg(
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
                ).round(2).sort_values("dist_total", ascending=False)

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
# TAB 9 — 🏆 ESTADÍSTICAS DE PARTIDO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_estad:
    if est_jug.empty or est_partidos.empty:
        st.info(
            "Aún no hay datos de estadísticas de partido en el Sheet.\n\n"
            "Para subirlos, ejecuta:\n\n"
            "`/usr/bin/python3 src/estadisticas_partidos.py --upload`"
        )
    else:
        st.markdown("### Estadísticas de partido — Temporada 25/26")
        st.caption(
            f"{est_partidos['partido_id'].nunique()} partidos procesados · "
            f"{int((est_partidos['participa'] == '1').sum() + (est_partidos['participa'] == 1).sum() + (est_partidos['participa'] == True).sum())} "
            f"participaciones · {len(est_eventos)} goles registrados."
        )

        # ── Normalización de tipos ──
        ep = est_partidos.copy()
        ev = est_eventos.copy()
        ej = est_jug.copy()

        for c in ["min_total", "min_1t", "min_2t", "goles_a_favor", "asistencias", "dorsal"]:
            if c in ep.columns:
                ep[c] = pd.to_numeric(ep[c], errors="coerce").fillna(0)
        for c in ej.columns:
            if c == "jugador":
                continue
            ej[c] = pd.to_numeric(ej[c], errors="coerce").fillna(0)
        if "minuto" in ev.columns:
            ev["minuto"] = pd.to_numeric(ev["minuto"], errors="coerce")

        # ── Filtros ──
        cf1, cf2 = st.columns([2, 2])
        with cf1:
            tipos = ["TODAS"] + sorted(ep["tipo"].dropna().unique().tolist()) if "tipo" in ep.columns else ["TODAS"]
            tipo_sel = st.selectbox("Competición", tipos, key="estad_tipo")
        with cf2:
            jugadores_op = sorted(ep["jugador"].dropna().unique().tolist())
            jug_sel = st.multiselect("Jugadores", jugadores_op, default=jugadores_op, key="estad_jug")

        # Aplicar filtros
        ep_f = ep.copy()
        ev_f = ev.copy()
        if tipo_sel != "TODAS":
            ep_f = ep_f[ep_f["tipo"] == tipo_sel]
            ev_f = ev_f[ev_f["tipo"] == tipo_sel]
        if jug_sel:
            ep_f = ep_f[ep_f["jugador"].isin(jug_sel)]

        # ── KPIs cabecera ──
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Partidos", int(ep_f["partido_id"].nunique()))
        kc2.metric("Goles a favor",
                   int(ev_f[ev_f["equipo_marca"] == "INTER"].shape[0]) if not ev_f.empty else 0)
        kc3.metric("Goles en contra",
                   int(ev_f[ev_f["equipo_marca"] == "RIVAL"].shape[0]) if not ev_f.empty else 0)
        kc4.metric("Min. totales jugados", f"{ep_f['min_total'].sum():.0f}")

        st.markdown("---")

        # ── Ranking goleadores ──
        st.markdown("#### Ranking goleadores")
        ranking = ep_f.groupby("jugador", as_index=False).agg(
            partidos=("participa", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0).astype(int) > 0).sum()),
            min_total=("min_total", "sum"),
            goles=("goles_a_favor", "sum"),
            asists=("asistencias", "sum"),
        )
        ranking["g+a"] = ranking["goles"] + ranking["asists"]
        ranking["min/partido"] = (ranking["min_total"] / ranking["partidos"].clip(lower=1)).round(1)
        ranking = ranking.sort_values("goles", ascending=False)

        st.dataframe(
            ranking.style.format({
                "min_total": "{:.0f}",
                "min/partido": "{:.1f}",
                "goles": "{:.0f}", "asists": "{:.0f}", "g+a": "{:.0f}",
                "partidos": "{:.0f}",
            }, na_rep="—").background_gradient(subset=["goles", "g+a"], cmap="Greens"),
            use_container_width=True, hide_index=True,
        )

        # ── Distribución goles por jugador (barras) ──
        st.markdown("#### Goles a favor por jugador")
        try:
            import altair as alt
            chart_data = ranking[ranking["goles"] > 0].copy()
            if not chart_data.empty:
                ch = (alt.Chart(chart_data)
                      .mark_bar()
                      .encode(
                          x=alt.X("goles:Q", title="Goles"),
                          y=alt.Y("jugador:N", sort="-x", title=""),
                          color=alt.Color("goles:Q", scale=alt.Scale(scheme="greens"), legend=None),
                          tooltip=["jugador", "goles", "asists", "g+a", "partidos", "min_total"],
                      )
                      .properties(height=max(220, 26 * len(chart_data))))
                st.altair_chart(ch, use_container_width=True)
        except Exception as _e:
            st.bar_chart(ranking.set_index("jugador")["goles"])

        st.markdown("---")

        # ── Goles por intervalos de 5 minutos ──
        st.markdown("#### Goles por minuto del partido (intervalos de 5')")
        if not ev_f.empty and "intervalo_5min" in ev_f.columns:
            orden_ints = ["0-5", "5-10", "10-15", "15-20", "20-25",
                          "25-30", "30-35", "35-40"]
            piv = (ev_f.groupby(["intervalo_5min", "equipo_marca"])
                   .size()
                   .unstack(fill_value=0)
                   .reindex(orden_ints, fill_value=0))
            for col in ("INTER", "RIVAL"):
                if col not in piv.columns:
                    piv[col] = 0
            piv = piv[["INTER", "RIVAL"]].rename(columns={"INTER": "A favor", "RIVAL": "En contra"})
            st.bar_chart(piv)
        else:
            st.caption("Sin eventos de gol para este filtro.")

        st.markdown("---")

        # ── Goles por tipo de acción ──
        st.markdown("#### Goles a favor por tipo de acción")
        if not ev_f.empty and "accion" in ev_f.columns:
            acciones = (ev_f[ev_f["equipo_marca"] == "INTER"]
                        .groupby("accion").size().sort_values(ascending=False))
            if not acciones.empty:
                st.bar_chart(acciones)
            else:
                st.caption("Sin goles a favor para este filtro.")
        else:
            st.caption("Sin datos.")

        # ── Detalle expandible ──
        with st.expander("📋 Detalle por partido"):
            cols = ["partido_id", "tipo", "rival", "fecha", "dorsal", "jugador",
                    "min_1t", "min_2t", "min_total", "goles_a_favor", "asistencias"]
            cols = [c for c in cols if c in ep_f.columns]
            st.dataframe(
                ep_f[cols].sort_values(["partido_id", "jugador"]),
                use_container_width=True, hide_index=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 10 — 📈 EFICIENCIA (disparos, ratios, métricas avanzadas)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_efic:
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
            st.dataframe(
                a[cols_show].style.format({
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

        # ── Cuartetos más efectivos ──
        if not est_cuart.empty:
            st.markdown("#### Cuartetos más efectivos (+/- por eventos en pista)")
            c = est_cuart.copy()
            for col in ("n_eventos", "goles_a_favor", "goles_en_contra", "plus_minus"):
                if col in c.columns:
                    c[col] = pd.to_numeric(c[col], errors="coerce").fillna(0).astype(int)
            st.dataframe(
                c.head(15).style.background_gradient(subset=["plus_minus"], cmap="RdYlGn"),
                use_container_width=True, hide_index=True,
            )

        st.markdown("---")

        # ── Tabla de disparos por partido ──
        if not est_disparos.empty:
            st.markdown("#### Disparos por partido")
            comp_op = ["TODAS"] + sorted(est_disparos["competicion"].dropna().unique().tolist())
            sel_c = st.selectbox("Competición", comp_op, key="efic_comp")
            df_show = est_disparos.copy()
            if sel_c != "TODAS":
                df_show = df_show[df_show["competicion"] == sel_c]
            st.dataframe(
                df_show[["competicion","rival","fecha","disparos_a_favor","disparos_en_contra",
                         "goles_a_favor","goles_en_contra","ratio_a_favor","ratio_en_contra"]],
                use_container_width=True, hide_index=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 11 — 🔍 SCOUTING DE RIVALES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_scout:
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

        with sub_global:
            st.markdown("#### Comparativa entre rivales")
            agr = scout_agr.copy()
            for c in agr.columns:
                if c in ("rival_codigo", "rival_nombre"):
                    continue
                agr[c] = pd.to_numeric(agr[c], errors="coerce")

            # Top: ordenable por total
            cols_top = ["rival_codigo", "rival_nombre", "partidos", "total_goles"]
            cols_top = [c for c in cols_top if c in agr.columns]
            st.dataframe(
                agr[cols_top].style
                .format({"partidos": "{:.0f}", "total_goles": "{:.0f}"}, na_rep="—")
                .background_gradient(subset=["total_goles"], cmap="Reds"),
                use_container_width=True, hide_index=True,
            )

            # Heatmap de % por origen × rival
            cols_pct = [c for c in agr.columns if c.startswith("%")]
            if cols_pct:
                st.markdown("#### Heatmap: % goles por origen × rival")
                heat = agr[["rival_codigo"] + cols_pct].set_index("rival_codigo")
                # Renombrar quitar "%"
                heat.columns = [c.lstrip("%") for c in heat.columns]
                # Solo dejar columnas con al menos un valor > 5%
                heat = heat.loc[:, heat.max() > 5]
                st.dataframe(
                    heat.style.format("{:.1f}%", na_rep="—")
                    .background_gradient(cmap="YlOrRd", axis=None),
                    use_container_width=True,
                )

        with sub_rival:
            rivales_op = scout_agr["rival_nombre"].tolist() if "rival_nombre" in scout_agr.columns else []
            if rivales_op:
                rival_sel = st.selectbox("Rival a analizar", rivales_op, key="scout_rival")
                df_r = scout_raw[scout_raw["rival_nombre"] == rival_sel].copy()
                agr_r = scout_agr[scout_agr["rival_nombre"] == rival_sel].iloc[0] if not scout_agr[scout_agr["rival_nombre"] == rival_sel].empty else None

                if agr_r is not None:
                    cols_acc = [c for c in agr_r.index if not c.startswith("%") and c not in (
                        "rival_codigo", "rival_nombre", "partidos", "total_goles")]
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Partidos analizados", int(pd.to_numeric(agr_r["partidos"], errors="coerce") or 0))
                    k2.metric("Goles totales (a favor)", int(pd.to_numeric(agr_r["total_goles"], errors="coerce") or 0))
                    media = pd.to_numeric(agr_r["total_goles"], errors="coerce") / max(pd.to_numeric(agr_r["partidos"], errors="coerce") or 1, 1)
                    k3.metric("Goles por partido", f"{media:.2f}")

                    st.markdown(f"#### Cómo marca **{rival_sel}** (% por origen)")
                    pct_data = []
                    for c in cols_acc:
                        v = pd.to_numeric(agr_r[c], errors="coerce")
                        if v and v > 0:
                            pct_data.append({"accion": c, "goles": int(v)})
                    if pct_data:
                        df_pct = pd.DataFrame(pct_data).sort_values("goles", ascending=False)
                        st.bar_chart(df_pct.set_index("accion")["goles"])

                st.markdown(f"#### Partido a partido — {rival_sel}")
                cols_show = ["competicion", "contra_quien", "fecha", "total_a_favor"]
                cols_show = [c for c in cols_show if c in df_r.columns]
                st.dataframe(
                    df_r[cols_show].sort_values("fecha", ascending=False),
                    use_container_width=True, hide_index=True,
                )
