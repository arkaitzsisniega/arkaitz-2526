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
        data = ws.get_all_records()
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


def fecha_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
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

    for df in [carga, semanal]:
        num_cols(df, ["BORG", "MINUTOS", "CARGA", "ACWR", "CARGA_AGUDA",
                      "CARGA_CRONICA", "MONOTONIA", "FATIGA", "CARGA_SEMANAL", "SESIONES"])
    num_cols(peso,    ["PESO_PRE", "PESO_POST", "DIFERENCIA", "PCT_PERDIDA"])
    num_cols(df_well, ["SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL",
                       "WELLNESS_7D", "DESVIACION_BASELINE"])
    num_cols(sem,     ["ACWR", "MONOTONIA", "WELLNESS_MEDIO", "PESO_PRE_DESV_KG",
                       "WELLNESS_BELOW15", "ALERTAS_ACTIVAS"])

    return carga, semanal, peso, df_well, sem, rec, les


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
        carga, semanal, peso, df_well, sem, rec, les = datos()
        data_ok = True
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

    fecha_min = carga["FECHA"].min().date()
    fecha_max = carga["FECHA"].max().date()
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

tab_sem, tab_carga, tab_peso, tab_well, tab_les, tab_rec = st.tabs([
    "🚦 Semáforo",
    "📊 Carga",
    "⚖️ Peso",
    "💤 Wellness",
    "🏥 Lesiones",
    "📋 Recuento",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SEMÁFORO DE RIESGO
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sem:
    st.markdown("### Estado actual del equipo")
    st.caption("Semáforo calculado con ACWR, Wellness y Pérdida de peso de los últimos 7 días.")

    sem_f = sem[sem["JUGADOR"].isin(sel_jugadores)].copy()

    # ── KPIs generales ──
    n_rojo    = (sem_f["SEMAFORO_GLOBAL"] == "ROJO").sum()
    n_naranja = (sem_f["SEMAFORO_GLOBAL"] == "NARANJA").sum()
    n_verde   = (sem_f["SEMAFORO_GLOBAL"] == "VERDE").sum()
    acwr_med  = sem_f["ACWR"].mean()
    well_med  = sem_f["WELLNESS_MEDIO"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, lbl, color in [
        (c1, n_rojo,    "🔴 En riesgo",     ROJO),
        (c2, n_naranja, "🟠 Precaución",     NARANJA),
        (c3, n_verde,   "🟢 OK",             VERDE),
        (c4, f"{acwr_med:.2f}" if not np.isnan(acwr_med) else "—", "ACWR medio", AZUL),
        (c5, f"{well_med:.1f}" if not np.isnan(well_med) else "—", "Wellness medio", GRIS),
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

            acwr        = row.get("ACWR")
            well_med    = row.get("WELLNESS_MEDIO")
            peso_desv   = row.get("PESO_PRE_DESV_KG")
            well_below  = row.get("WELLNESS_BELOW15")
            alertas     = int(row.get("ALERTAS_ACTIVAS", 0))

            acwr_txt  = f"{acwr:.2f}" if pd.notna(acwr) else "—"
            well_txt  = (f"{well_med:.1f}/20" if pd.notna(well_med) else "—")
            below_txt = (f" ({int(well_below)}/7 bajo 15)" if pd.notna(well_below) and int(well_below) > 0 else "")
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

    # ── Selector de semana (como el Excel) ──
    semanas = sorted(semanal["FECHA_LUNES"].dropna().unique())
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
        pivot_rpe["CARGA SEMANA"] = sem_df.groupby("JUGADOR")["CARGA"].sum().reindex(pivot_rpe.index)
        pivot_rpe["MEDIA BORG"]   = sem_df.groupby("JUGADOR")["BORG"].mean().round(2).reindex(pivot_rpe.index)

        def color_borg(val):
            if pd.isna(val) or not isinstance(val, (int, float)):
                return ""
            if val >= 8:    return "background-color: #FFCDD2; font-weight:bold"
            if val >= 6:    return "background-color: #FFE0B2"
            if val >= 4:    return "background-color: #FFF9C4"
            return "background-color: #E8F5E9"

        styled = pivot_rpe.style.map(color_borg)
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

    # Selector de semana (como Excel PESO SEMANA)
    semanas_peso = sorted(peso["FECHA"].dropna().dt.to_period("W").unique())
    semana_peso_str = st.select_slider(
        "📅 Semana",
        options=[str(s) for s in semanas_peso],
        value=str(semanas_peso[-1]) if len(semanas_peso) else None,
        key="sl_peso",
    )
    # Convertir a fechas
    sp = pd.Period(semana_peso_str, freq="W")
    sp_ini = pd.Timestamp(sp.start_time.date())
    sp_fin = pd.Timestamp(sp.end_time.date())

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

        subtabs = st.tabs(["PRE", "POST", "DIFERENCIA (kg)", "% Pérdida"])
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
        fig_heat.update_xaxes(tickformat="%d/%m", tickangle=-45)
        fig_heat.update_layout(**LAYOUT, height=450, coloraxis_showscale=True)
        st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("---")
    st.markdown("### Wellness semanal")

    # Selector semana wellness
    semanas_w = sorted(semanal["FECHA_LUNES"].dropna().unique())
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
        st.dataframe(pivot_well_dia.style.map(color_well), use_container_width=True)

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
                        x=jug_well_df["FECHA"], y=jug_well_df[col],
                        name=nombre, line=dict(color=color, width=2),
                        mode="lines+markers", marker=dict(size=4),
                    ))
            # Media 7 días
            if "WELLNESS_7D" in jug_well_df.columns:
                # Normalizar a escala /4 para comparar con componentes (1-5)
                fig_comp.add_trace(go.Scatter(
                    x=jug_well_df["FECHA"], y=jug_well_df["WELLNESS_7D"] / 4,
                    name="Wellness medio 7d (÷4)", line=dict(color="black", width=2, dash="dot"),
                ))
            fig_comp.update_layout(
                **LAYOUT, height=350,
                title=f"Componentes de Wellness — {jug_w}",
                yaxis=dict(range=[0.5, 5.5]),
            )
            st.plotly_chart(fig_comp, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — LESIONES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_les:
    st.markdown("### Registro de lesiones")

    les_f = les.copy()
    # Filtrar columnas vacías
    les_f = les_f[[c for c in les_f.columns if les_f[c].replace("", pd.NA).notna().any()]]

    # Lesiones activas (sin fecha de alta)
    les_activas = les_f[les_f["FECHA ALTA"].isna() & les_f["FECHA LESIÓN"].notna()]
    les_activas = les_activas[les_activas["JUGADOR"].isin(sel_jugadores)] if "JUGADOR" in les_activas.columns else les_activas

    if not les_activas.empty:
        st.error(f"🔴 {len(les_activas)} lesión/es activa/s ahora mismo")
        st.dataframe(les_activas, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No hay lesiones activas en este momento")

    st.markdown("---")
    st.markdown("### Historial completo")

    les_hist = les_f[les_f["JUGADOR"].isin(sel_jugadores)] if "JUGADOR" in les_f.columns else les_f
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
    st.markdown("### Recuento de sesiones — Temporada completa")

    rec_f = rec[rec["JUGADOR"].isin(sel_jugadores)] if "JUGADOR" in rec.columns else rec

    if rec_f.empty:
        st.info("Sin datos de recuento.")
    else:
        # Tabla principal de recuento (como Excel RECUENTO)
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
