#!/usr/bin/env python3
"""
Generador de PDF para un partido. Lee del Sheet maestro y produce un
PDF con cabecera + métricas individuales + minutos + rotaciones +
eventos de gol + mapas SVG (campo y portería).

API pública: `generar_pdf_partido(partido_id) -> bytes`.

Uso desde el dashboard:
  pdf_bytes = generar_pdf_partido("J5.ELPOZO")
  st.download_button("📄 PDF", pdf_bytes, file_name="J5_ELPOZO.pdf")

Dependencia: reportlab (incluido en requirements.txt).
"""
from __future__ import annotations

import io
import datetime as _dt
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage,
)
from reportlab.graphics import renderPM
from reportlab.graphics.shapes import Drawing

# Backend de matplotlib SIEMPRE Agg (sin GUI). Importante en Streamlit
# Cloud porque matplotlib se carga con backend interactivo por defecto.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon
import numpy as np

# svglib es opcional: si la instalación falla (p.ej. en Streamlit Cloud),
# generamos el PDF sin los mapas SVG.
try:
    from svglib.svglib import svg2rlg
    SVG_DISPONIBLE = True
except Exception:
    svg2rlg = None
    SVG_DISPONIBLE = False

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "google_credentials.json"
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ── Colores y estilos ────────────────────────────────────────────────────────
AZUL = colors.HexColor("#1B3A6B")
VERDE = colors.HexColor("#2E7D32")
ROJO = colors.HexColor("#B71C1C")
GRIS = colors.HexColor("#666666")
GRIS_CLARO = colors.HexColor("#F5F5F5")
GRIS_MUY_CLARO = colors.HexColor("#FAFAFA")


def _fmt_minutos(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    m = int(v)
    s = int(round((v - m) * 60))
    return f"{m}:{s:02d}"


def _connect():
    """Conexión por defecto (CLI/local).

    Para Streamlit Cloud se debe pasar `sh` ya conectado a
    `generar_pdf_partido(..., sh=...)` desde el dashboard, porque allí no
    existe `google_credentials.json` (las credenciales viven en
    `st.secrets`).
    """
    if CREDS_FILE.exists():
        creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
        return gspread.authorize(creds).open(SHEET_NAME)
    # Intentar st.secrets como fallback (si se llama desde Streamlit sin
    # pasar sh)
    try:
        import streamlit as st  # type: ignore
        info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        raise FileNotFoundError(
            f"No encuentro {CREDS_FILE} y tampoco hay st.secrets disponible: {e}"
        )


def _leer(sh, hoja: str) -> pd.DataFrame:
    try:
        return pd.DataFrame(sh.worksheet(hoja).get_all_records())
    except Exception:
        return pd.DataFrame()


# ── Carga lazy de los generadores SVG del dashboard ──────────────────────────
def _cargar_dashboard_module():
    """Carga `dashboard/app.py` como módulo sin que ejecute Streamlit.
    Lo cacheamos a nivel de proceso para no recargar.
    """
    import importlib.util, sys
    if "_dashboard_app_pdf" in sys.modules:
        return sys.modules["_dashboard_app_pdf"]
    app_path = ROOT / "dashboard" / "app.py"
    spec = importlib.util.spec_from_file_location("_dashboard_app_pdf", app_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_dashboard_app_pdf"] = mod
    spec.loader.exec_module(mod)
    return mod


def _svg_campo(zonas, svg_campo_fn=None):
    if svg_campo_fn is not None:
        return svg_campo_fn(zonas)
    return _cargar_dashboard_module().generar_svg_campo(zonas)


def _svg_porteria(cuadrantes, svg_porteria_fn=None):
    if svg_porteria_fn is not None:
        return svg_porteria_fn(cuadrantes)
    return _cargar_dashboard_module().generar_svg_porteria(cuadrantes)


def _svg_to_image(svg_str: str, width: float, height: float) -> RLImage:
    """Convierte un string SVG en un objeto RLImage para reportlab.
    (Solo se usa si svglib está disponible; caso contrario usar mpl).
    """
    if not SVG_DISPONIBLE:
        raise RuntimeError("svglib no disponible — saltando mapa")
    drawing = svg2rlg(io.BytesIO(svg_str.encode("utf-8")))
    if drawing is None:
        return RLImage(io.BytesIO(b""), width=width, height=height)
    sx = width / drawing.width if drawing.width else 1
    sy = height / drawing.height if drawing.height else 1
    s = min(sx, sy)
    drawing.scale(s, s)
    drawing.width *= s
    drawing.height *= s
    buf = io.BytesIO()
    renderPM.drawToFile(drawing, buf, fmt="PNG", dpi=150)
    buf.seek(0)
    return RLImage(buf, width=drawing.width, height=drawing.height)


# ── Generadores nativos con matplotlib (sin SVG) ─────────────────────────────
def _mpl_color_zona(valor: int, max_v: int):
    """Mismo gradiente que `_color_zona` del dashboard pero como tuple RGB."""
    if max_v <= 0 or valor <= 0:
        return (0.96, 0.96, 0.96)  # gris muy claro
    t = max(0.0, min(1.0, valor / max_v))
    if t < 0.5:
        r = 255
        g = int(220 - 50 * (t * 2))
        b = 180
    else:
        r = int(255 - 100 * ((t - 0.5) * 2))
        g = int(170 - 130 * ((t - 0.5) * 2))
        b = int(80 - 30 * ((t - 0.5) * 2))
    return (r/255, g/255, b/255)


def _arco_xy(cx, cy, r, ang_ini, ang_fin, n=40):
    """Devuelve (xs, ys) de un arco de radio r centrado en (cx,cy), de
    ang_ini a ang_fin (en grados, sentido matemático estándar). Se usa
    para construir polígonos compuestos con arcos."""
    a = np.radians(np.linspace(ang_ini, ang_fin, n))
    return cx + r * np.cos(a), cy + r * np.sin(a)


def _dibujar_campo_mpl(zonas: dict) -> bytes:
    """Dibuja el campo con 11 zonas + portería + áreas usando matplotlib y
    devuelve un PNG en bytes. Geometría (en "px de SVG"): 1m = 25px →
    campo 1000 × 500. Mitad atacante = 0..500 (izda)."""
    z = {k: int(v) if v else 0 for k, v in (zonas or {}).items()}
    max_v = max(max(z.values()), 1) if z else 1

    fig, ax = plt.subplots(figsize=(10.8, 5.3), dpi=180)
    fig.patch.set_facecolor("#A5D6A7")
    ax.set_facecolor("#A5D6A7")
    ax.set_xlim(-15, 1015)
    ax.set_ylim(510, -10)  # invertido para que (0,0) esté arriba a la izda
    ax.set_aspect("equal")
    ax.axis("off")

    BORDE = "#1B5E20"

    def col(zk):
        return _mpl_color_zona(z.get(zk, 0), max_v)

    def texto(zk, x, y):
        # Solo el valor (sin la etiqueta de la zona). Más grande.
        v = z.get(zk, 0)
        ax.text(x, y, str(v), ha="center", va="center",
                fontsize=22, fontweight="bold", color="#000",
                zorder=4)

    # ── Zonas rectangulares ───────────────────────────────────────────────
    rects_z = [
        # (zk, x, y, w, h, tx, ty)
        ("A11", 500, 0, 500, 500, 750, 250),
        ("A6",  0,   0, 250, 62.5, 125, 31),
        ("A3",  0,   437.5, 250, 62.5, 125, 469),
        ("A10", 250, 0, 250, 62.5, 375, 31),
        ("A7",  250, 437.5, 250, 62.5, 375, 469),
        ("A9",  250, 62.5, 250, 187.5, 375, 156),
        ("A8",  250, 250,  250, 187.5, 375, 343),
    ]
    for zk, x, y, w, h, tx, ty in rects_z:
        ax.add_patch(mpatches.Rectangle((x, y), w, h, facecolor=col(zk),
                                          edgecolor="none", zorder=1))
        texto(zk, tx, ty)

    # ── Zonas con arco (A5, A4, A2, A1) ──────────────────────────────────
    # OJO: el eje Y está invertido (ylim 510→-10), por lo que los ángulos
    # estándar de matplotlib se "invierten" visualmente: ángulo positivo
    # va hacia ABAJO en pantalla. Por eso A5 (arriba) usa ángulo NEGATIVO.

    # A5: zona externa SUPERIOR — polígono cerrado por arco de (150,212.5) →
    #      (0,62.5). Centro (0,212.5), r=150, ang 0° → -90°.
    xs_a, ys_a = _arco_xy(0, 212.5, 150, 0, -90)
    poly_a5 = list(zip([0, 250, 250, 150, 150] + list(xs_a),
                        [62.5, 62.5, 250, 250, 212.5] + list(ys_a)))
    ax.add_patch(MplPolygon(poly_a5, closed=True, facecolor=col("A5"),
                              edgecolor="none", zorder=1))
    texto("A5", 200, 156)

    # A4: simétrica abajo. Arco de (150,287.5) → (0,437.5).
    xs_a, ys_a = _arco_xy(0, 287.5, 150, 0, 90)
    poly_a4 = list(zip([0, 250, 250, 150, 150] + list(xs_a),
                        [437.5, 437.5, 250, 250, 287.5] + list(ys_a)))
    ax.add_patch(MplPolygon(poly_a4, closed=True, facecolor=col("A4"),
                              edgecolor="none", zorder=1))
    texto("A4", 200, 343)

    # A2: dentro del área SUPERIOR. Arco (0,62.5) → (150,212.5), -90° → 0°.
    xs_a, ys_a = _arco_xy(0, 212.5, 150, -90, 0)
    poly_a2 = list(zip(list(xs_a) + [150, 0],
                        list(ys_a) + [250, 250]))
    ax.add_patch(MplPolygon(poly_a2, closed=True, facecolor=col("A2"),
                              edgecolor="none", zorder=1))
    texto("A2", 60, 175)

    # A1: dentro del área INFERIOR. Polígono (0,250) → (150,250) →
    #      (150,287.5) → arco → (0,437.5). Ángulos 0° → 90°.
    xs_a, ys_a = _arco_xy(0, 287.5, 150, 0, 90)
    poly_a1 = list(zip([0, 150] + list(xs_a),
                        [250, 250] + list(ys_a)))
    ax.add_patch(MplPolygon(poly_a1, closed=True, facecolor=col("A1"),
                              edgecolor="none", zorder=1))
    texto("A1", 60, 325)

    # ── Líneas discontinuas de zonas ─────────────────────────────────────
    dash_kw = dict(color=BORDE, linewidth=1, linestyle=(0, (4, 3)), zorder=3)
    ax.plot([250, 250], [0, 500], **dash_kw)
    ax.plot([0, 500], [62.5, 62.5], **dash_kw)
    ax.plot([0, 500], [437.5, 437.5], **dash_kw)
    ax.plot([0, 500], [250, 250], **dash_kw)

    # ── Líneas oficiales (continuas, marcadas) ───────────────────────────
    line_kw = dict(color=BORDE, linewidth=2.5, zorder=4)
    # Perímetro
    ax.add_patch(mpatches.Rectangle((0, 0), 1000, 500, fill=False,
                                      edgecolor=BORDE, linewidth=2.5,
                                      zorder=4))
    # Línea media
    ax.plot([500, 500], [0, 500], **line_kw)
    # Círculo central
    ax.add_patch(mpatches.Circle((500, 250), 75, fill=False,
                                   edgecolor=BORDE, linewidth=2, zorder=4))
    ax.add_patch(mpatches.Circle((500, 250), 4, color=BORDE, zorder=4))
    # Área grande (arco de 6m desde cada poste + segmento medio)
    # Top: de (0,62.5) → (150,212.5), centro (0,212.5)
    xs_top, ys_top = _arco_xy(0, 212.5, 150, -90, 0)
    ax.plot(xs_top, ys_top, color=BORDE, linewidth=2, zorder=4)
    # Bot: de (150,287.5) → (0,437.5), centro (0,287.5)
    xs_bot, ys_bot = _arco_xy(0, 287.5, 150, 0, 90)
    ax.plot(xs_bot, ys_bot, color=BORDE, linewidth=2, zorder=4)
    ax.plot([150, 150], [212.5, 287.5], color=BORDE, linewidth=2, zorder=4)
    # Punto de penalti (6m) y doble penalti (10m)
    ax.add_patch(mpatches.Circle((150, 250), 4, color=BORDE, zorder=4))
    ax.add_patch(mpatches.Circle((250, 250), 4, color=BORDE, zorder=4))

    # ── Portería: solo los DOS PALOS pegados a la línea de fondo (x=0) ─
    # Ya no hay red detrás. Cada palo es un cuadrado rojo pequeño centrado
    # en x=0, en (0, 212.5) y (0, 287.5).
    PALO_W = 10  # ancho del palo (atravesando la línea de fondo)
    PALO_H = 10  # alto del palo
    for cy in (212.5, 287.5):
        ax.add_patch(mpatches.Rectangle(
            (-PALO_W/2, cy - PALO_H/2), PALO_W, PALO_H,
            facecolor="#B71C1C", edgecolor="#5D0D0D", linewidth=0.6,
            zorder=6))

    # Guardar a PNG en memoria
    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=180, bbox_inches="tight",
                pad_inches=0.05, facecolor="#A5D6A7")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _dibujar_porteria_mpl(cuadrantes: dict) -> bytes:
    """Portería 3×2m con cuadrícula 3×3 (P1-P9) y postes con franjas."""
    p = {k: int(v) if v else 0 for k, v in (cuadrantes or {}).items()}
    max_v = max(max(p.values()), 1) if p else 1

    POSTE = 14
    SVG_W, SVG_H = 360, 250
    POSX, POSY = 30, 18
    PORT_W, PORT_H = 300, 200

    fig, ax = plt.subplots(figsize=(7.2, 5.0), dpi=180)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    ax.set_xlim(0, SVG_W)
    ax.set_ylim(SVG_H, 0)  # invertido
    ax.set_aspect("equal")
    ax.axis("off")

    # Fondo de la portería
    ax.add_patch(mpatches.Rectangle((POSX, POSY), PORT_W, PORT_H,
                                      facecolor="#FAFAFA", edgecolor="none",
                                      zorder=1))
    # Líneas de red decorativas
    for i in range(1, 6):
        x = POSX + i * (PORT_W / 6)
        ax.plot([x, x], [POSY, POSY + PORT_H], color="#E0E0E0",
                linewidth=0.5, zorder=2)
    for i in range(1, 4):
        y = POSY + i * (PORT_H / 4)
        ax.plot([POSX, POSX + PORT_W], [y, y], color="#E0E0E0",
                linewidth=0.5, zorder=2)

    # 9 cuadrantes — solo el VALOR (sin etiqueta P1..P9), más grande
    cuad_w = PORT_W / 3
    cuad_h = PORT_H / 3
    for i in range(9):
        col_idx = i % 3
        row_idx = i // 3
        x = POSX + col_idx * cuad_w
        y = POSY + row_idx * cuad_h
        zona = f"P{i+1}"
        v = p.get(zona, 0)
        color = _mpl_color_zona(v, max_v)
        ax.add_patch(mpatches.Rectangle((x, y), cuad_w, cuad_h,
                                          facecolor=color, alpha=0.9,
                                          edgecolor="#888", linewidth=0.6,
                                          linestyle=(0, (3, 2)), zorder=3))
        ax.text(x + cuad_w/2, y + cuad_h/2, str(v),
                ha="center", va="center", fontsize=24,
                fontweight="bold", color="#000", zorder=4)

    # Postes verticales con franjas
    n_v = 6
    fv_h = PORT_H / n_v
    for i in range(n_v):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        ax.add_patch(mpatches.Rectangle((POSX - POSTE, POSY + i * fv_h),
                                          POSTE, fv_h, facecolor=c,
                                          edgecolor="#7F1010", linewidth=0.4,
                                          zorder=5))
        ax.add_patch(mpatches.Rectangle((POSX + PORT_W, POSY + i * fv_h),
                                          POSTE, fv_h, facecolor=c,
                                          edgecolor="#7F1010", linewidth=0.4,
                                          zorder=5))
    # Larguero
    n_h = 8
    fh_w = PORT_W / n_h
    for i in range(n_h):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        ax.add_patch(mpatches.Rectangle((POSX + i * fh_w, POSY - POSTE),
                                          fh_w, POSTE, facecolor=c,
                                          edgecolor="#7F1010", linewidth=0.4,
                                          zorder=5))

    # Línea de campo bajo la portería
    ax.plot([POSX - POSTE - 10, POSX + PORT_W + POSTE + 10],
            [POSY + PORT_H + 4, POSY + PORT_H + 4],
            color="#1B5E20", linewidth=2, zorder=4)

    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=180, bbox_inches="tight",
                pad_inches=0.05, facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _png_to_image(png_bytes: bytes, width: float, height: float) -> RLImage:
    """Wrapping a PNG byte buffer en un RLImage con tamaño deseado."""
    img = RLImage(io.BytesIO(png_bytes), width=width, height=height)
    img.hAlign = "CENTER"
    return img


def _dibujar_goles_5min_mpl(ev_p: pd.DataFrame) -> bytes:
    """Genera un gráfico de barras apiladas con goles a favor (verde) y en
    contra (rojo) por intervalos de 5 minutos. 8 bins de 5' = 40 minutos."""
    bins = list(range(0, 41, 5))      # [0,5,10,...,40]
    labels = [f"{bins[i]}–{bins[i+1]}'" for i in range(len(bins) - 1)]

    af = [0] * (len(bins) - 1)
    ec = [0] * (len(bins) - 1)
    if not ev_p.empty and "minuto" in ev_p.columns:
        for _, r in ev_p.iterrows():
            m = pd.to_numeric(r.get("minuto"), errors="coerce")
            if pd.isna(m) or m < 0:
                continue
            idx = min(int(m // 5), len(bins) - 2)
            if r.get("equipo_marca") == "INTER":
                af[idx] += 1
            elif r.get("equipo_marca") == "RIVAL":
                ec[idx] += 1

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")
    x = np.arange(len(labels))
    w = 0.38
    bars_af = ax.bar(x - w/2, af, w, color="#2E7D32", label="Inter (a favor)",
                     edgecolor="#1B5E20", linewidth=0.6)
    bars_ec = ax.bar(x + w/2, ec, w, color="#C62828", label="Rival (en contra)",
                     edgecolor="#7F1010", linewidth=0.6)
    # Etiquetas de valor encima de cada barra (solo si > 0)
    for bar_set in (bars_af, bars_ec):
        for b in bar_set:
            h = b.get_height()
            if h > 0:
                ax.text(b.get_x() + b.get_width()/2, h + 0.05, f"{int(h)}",
                        ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Goles", fontsize=9)
    ax.set_title("Goles cada 5'", fontsize=11, fontweight="bold",
                 color="#1B3A6B", pad=8)
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    # Línea vertical entre 1ª y 2ª parte (entre bin 3 y 4 → x=3.5)
    ax.axvline(x=3.5, color="#999", linestyle="--", linewidth=1, alpha=0.7)
    ax.text(3.5, ax.get_ylim()[1] * 0.95, "Descanso",
            ha="center", va="top", fontsize=8, color="#666",
            bbox=dict(facecolor="white", edgecolor="#CCC",
                       boxstyle="round,pad=0.2"))
    max_y = max(max(af), max(ec), 1)
    ax.set_ylim(0, max_y + 1)

    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=160, bbox_inches="tight",
                pad_inches=0.1, facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Generador principal ──────────────────────────────────────────────────────
def generar_pdf_partido(partido_id: str, sh=None,
                          svg_campo_fn=None, svg_porteria_fn=None) -> bytes:
    """Genera el PDF en memoria y devuelve los bytes.

    Args:
        partido_id: identificador del partido (ej. "J5.ELPOZO").
        sh: opcional, spreadsheet ya abierto (gspread). Si no se pasa, se
            crea uno nuevo. El dashboard pasa el suyo para reusar credenciales.
        svg_campo_fn / svg_porteria_fn: opcionales, callables que generan los
            SVG. Si se pasan se usan directamente (evita reimportar el
            dashboard). Si no, se carga el módulo `dashboard/app.py`.
    """
    if sh is None:
        sh = _connect()
    df_jug = _leer(sh, "EST_PARTIDOS")
    df_evt = _leer(sh, "EST_EVENTOS")
    df_tot = _leer(sh, "EST_TOTALES_PARTIDO")
    df_dz = _leer(sh, "EST_DISPAROS_ZONAS")

    # Filtrar al partido
    jp = df_jug[df_jug["partido_id"] == partido_id].copy() if not df_jug.empty else pd.DataFrame()
    if jp.empty:
        raise ValueError(f"Partido {partido_id!r} no encontrado en EST_PARTIDOS")
    ep = df_evt[df_evt["partido_id"] == partido_id].copy() if not df_evt.empty else pd.DataFrame()
    tp_row = df_tot[df_tot["partido_id"] == partido_id]
    tp = tp_row.iloc[0] if not tp_row.empty else None

    # Convertir tipos
    num_cols = ["min_total", "min_1t", "min_2t", "pf", "pnf", "robos", "cortes",
                "bdg", "bdp", "dp", "dpalo", "db", "df", "dorsal",
                "goles_a_favor", "asistencias", "par", "gol_p", "bloq_p", "poste_p"]
    for c in num_cols:
        if c in jp.columns:
            jp[c] = pd.to_numeric(jp[c], errors="coerce").fillna(0)
    rot_cols = [f"rot_{p}_{i}" for p in ("1t", "2t") for i in range(1, 9)]
    for c in rot_cols:
        if c in jp.columns:
            jp[c] = pd.to_numeric(jp[c], errors="coerce").fillna(0)
    if not ep.empty and "minuto" in ep.columns:
        ep["minuto"] = pd.to_numeric(ep["minuto"], errors="coerce")

    rival = jp["rival"].iloc[0]
    fecha = jp["fecha"].iloc[0]
    competicion = jp["competicion"].iloc[0]
    gf = int((ep["equipo_marca"] == "INTER").sum()) if not ep.empty else 0
    gc = int((ep["equipo_marca"] == "RIVAL").sum()) if not ep.empty else 0

    # Cabecera completa (categoría/lugar/hora/local-visitante) si existen
    categoria = ""
    lugar = ""
    hora = ""
    local_visitante = ""
    if tp is not None:
        categoria = str(tp.get("categoria", "") or "").strip() or competicion
        lugar = str(tp.get("lugar", "") or "").strip()
        hora = str(tp.get("hora", "") or "").strip()
        local_visitante = str(tp.get("local_visitante", "") or "").strip()
    else:
        categoria = competicion
    # Formatear fecha como dd/mm/aa
    fecha_fmt = str(fecha)
    try:
        _f = pd.to_datetime(fecha, errors="coerce")
        if pd.notnull(_f):
            fecha_fmt = _f.strftime("%d/%m/%Y")
    except Exception:
        pass

    # Decidir orden Inter / rival según local/visitante
    if local_visitante == "VISITANTE":
        equipo_izq, equipo_der = rival, "Movistar Inter FS"
        gol_izq, gol_der = gc, gf
    else:
        equipo_izq, equipo_der = "Movistar Inter FS", rival
        gol_izq, gol_der = gf, gc

    # Buffer del PDF
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        title=f"{partido_id} · {rival}",
    )

    styles = getSampleStyleSheet()
    h_titulo = ParagraphStyle("titulo", parent=styles["Heading1"],
                               fontSize=18, textColor=AZUL, spaceAfter=4)
    h_marcador = ParagraphStyle("marcador", parent=styles["Heading1"],
                                 fontSize=24, textColor=AZUL, alignment=1, spaceAfter=10)
    h_seccion = ParagraphStyle("seccion", parent=styles["Heading2"],
                                fontSize=12, textColor=AZUL, spaceBefore=10, spaceAfter=4)
    p_body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9)
    p_cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8,
                              leading=10)
    p_caption = ParagraphStyle("caption", parent=styles["BodyText"],
                                fontSize=8, textColor=GRIS, alignment=1)

    story = []

    # ── CABECERA estilo Movistar (logos + tabla info + marcador) ─────────
    LOGO_DIR = ROOT / "assets" / "logos"
    logo_izq_path = LOGO_DIR / "inter_verde.png"
    logo_der_path = LOGO_DIR / "inter_dorado.png"

    def _logo_or_blank(path, w=2.0*cm, h=2.4*cm):
        if path.exists():
            try:
                img = RLImage(str(path), width=w, height=h, kind="proportional")
                img.hAlign = "CENTER"
                return img
            except Exception:
                pass
        return Paragraph("", p_body)

    # Texto del partido con vs centrado
    p_partido = ParagraphStyle("partido_lbl", parent=styles["BodyText"],
                                 fontSize=10, alignment=1, leading=12)
    p_partido_v = ParagraphStyle("partido_val", parent=styles["BodyText"],
                                   fontSize=11, alignment=1, leading=13,
                                   fontName="Helvetica-Bold", textColor=AZUL)
    p_celda_lbl = ParagraphStyle("c_lbl", parent=styles["BodyText"],
                                   fontSize=8, alignment=1, leading=10,
                                   textColor=colors.whitesmoke,
                                   fontName="Helvetica-Bold")
    p_celda_val = ParagraphStyle("c_val", parent=styles["BodyText"],
                                   fontSize=10, alignment=1, leading=12,
                                   fontName="Helvetica-Bold", textColor=AZUL)

    # Tabla informativa (header en azul, valores debajo)
    info_header = [
        Paragraph("PARTIDO", p_celda_lbl),
        Paragraph("CATEGORÍA", p_celda_lbl),
        Paragraph("LUGAR", p_celda_lbl),
        Paragraph("HORA", p_celda_lbl),
        Paragraph("FECHA", p_celda_lbl),
    ]
    partido_txt = (f"<b>{equipo_izq.upper()}</b> &nbsp;<i>vs</i>&nbsp; "
                    f"<b>{equipo_der.upper()}</b>")
    info_valores = [
        Paragraph(partido_txt, p_celda_val),
        Paragraph(categoria or "—", p_celda_val),
        Paragraph(lugar or "—", p_celda_val),
        Paragraph(hora or "—", p_celda_val),
        Paragraph(fecha_fmt, p_celda_val),
    ]
    t_info = Table([info_header, info_valores],
                    colWidths=[5.4*cm, 3.0*cm, 3.0*cm, 2.0*cm, 2.4*cm],
                    rowHeights=[0.55*cm, 0.85*cm])
    t_info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("BACKGROUND", (0, 1), (-1, 1), GRIS_MUY_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))

    # Tabla principal: [logo_izq | info | logo_der]
    t_cab = Table(
        [[_logo_or_blank(logo_izq_path),
          t_info,
          _logo_or_blank(logo_der_path)]],
        colWidths=[2.4*cm, 15.8*cm, 2.4*cm],
    )
    t_cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t_cab)
    story.append(Spacer(1, 6))

    # Marcador grande centrado
    if local_visitante:
        sub_lv = f" — <font size='9' color='#666'>({local_visitante})</font>"
    else:
        sub_lv = ""
    story.append(Paragraph(
        f"<b>{equipo_izq}</b> &nbsp;&nbsp;"
        f"<font color='#2E7D32'>{gol_izq}</font> "
        f"– <font color='#B71C1C'>{gol_der}</font> &nbsp;&nbsp;"
        f"<b>{equipo_der}</b>{sub_lv}",
        h_marcador,
    ))
    story.append(Paragraph(
        f"<font size='8' color='#666'>Partido: {partido_id}</font>",
        ParagraphStyle("pid", parent=styles["BodyText"], alignment=1)))
    story.append(Spacer(1, 4))

    # ── KPIs (con totales del partido si existen) ────────────────────────
    if tp is not None:
        # Style centrado para que los textos queden en mitad de cada celda
        p_kpi_label = ParagraphStyle("kpi_label", parent=styles["BodyText"],
                                       fontSize=8, textColor=GRIS,
                                       alignment=1, spaceAfter=0, leading=10)
        p_kpi_valor = ParagraphStyle("kpi_valor", parent=styles["BodyText"],
                                       fontSize=14, textColor=AZUL,
                                       alignment=1, spaceAfter=0, leading=16,
                                       fontName="Helvetica-Bold")
        kpis = [
            ("Disparos totales", int(pd.to_numeric(tp.get("dt_inter", 0), errors="coerce") or 0)),
            ("Disparos a puerta", int(pd.to_numeric(tp.get("dp_inter", 0), errors="coerce") or 0)),
            ("Disparos rival", int(pd.to_numeric(tp.get("dt_rival", 0), errors="coerce") or 0)),
            ("Disp. rival a puerta", int(pd.to_numeric(tp.get("dp_rival", 0), errors="coerce") or 0)),
            ("Pérdidas forzadas", int(pd.to_numeric(tp.get("pf_inter", 0), errors="coerce") or 0)),
            ("Pérdidas no forzadas", int(pd.to_numeric(tp.get("pnf_inter", 0), errors="coerce") or 0)),
            ("Robos", int(pd.to_numeric(tp.get("robos_inter", 0), errors="coerce") or 0)),
            ("Cortes", int(pd.to_numeric(tp.get("cortes_inter", 0), errors="coerce") or 0)),
        ]
        # Tabla de 4 columnas con título + valor
        rows_kpi = []
        labels_row = []
        valores_row = []
        for lbl, v in kpis:
            labels_row.append(Paragraph(lbl, p_kpi_label))
            valores_row.append(Paragraph(str(v), p_kpi_valor))
            if len(labels_row) == 4:
                rows_kpi.append(labels_row); rows_kpi.append(valores_row)
                labels_row = []; valores_row = []
        if labels_row:
            rows_kpi.append(labels_row); rows_kpi.append(valores_row)
        t_kpi = Table(rows_kpi, colWidths=[4.4*cm]*4, rowHeights=[0.55*cm, 0.85*cm]*2)
        t_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GRIS_MUY_CLARO),
            ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 8))

    # ── Tabla de minutos ────────────────────────────────────────────────────
    story.append(Paragraph("⏱ Minutos por jugador", h_seccion))
    cols_min = ["dorsal", "jugador", "min_1t", "min_2t", "min_total"]
    cols_min = [c for c in cols_min if c in jp.columns]
    jpe = jp[jp["min_total"] > 0].sort_values("min_total", ascending=False)[cols_min]
    rows = [["Nº", "Jugador", "1ª parte", "2ª parte", "Total"]]
    for _, r in jpe.iterrows():
        rows.append([
            int(r.get("dorsal", 0)) if r.get("dorsal", 0) else "",
            r.get("jugador", ""),
            _fmt_minutos(r.get("min_1t", 0)),
            _fmt_minutos(r.get("min_2t", 0)),
            _fmt_minutos(r.get("min_total", 0)),
        ])
    t_min = Table(rows, colWidths=[1.2*cm, 4*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    t_min.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_min)

    # ── Tabla de métricas individuales (campo) ──────────────────────────
    story.append(Paragraph("📊 Métricas individuales (campo)", h_seccion))
    cols_met = ["dorsal", "jugador", "pf", "pnf", "robos", "cortes",
                "bdg", "bdp", "dp", "dpalo", "db", "df",
                "goles_a_favor", "asistencias"]
    cols_met = [c for c in cols_met if c in jp.columns]
    jpm = jp[jp["min_total"] > 0].sort_values("min_total", ascending=False)[cols_met]
    rows_met = [["Nº", "Jugador", "PF", "PNF", "Rob", "Cor",
                  "BDG", "BDP", "DP", "DPalo", "DB", "DF", "G", "A"]]
    for _, r in jpm.iterrows():
        rows_met.append([
            int(r.get("dorsal", 0)) if r.get("dorsal", 0) else "",
            r.get("jugador", ""),
            int(r.get("pf", 0)) or "",
            int(r.get("pnf", 0)) or "",
            int(r.get("robos", 0)) or "",
            int(r.get("cortes", 0)) or "",
            int(r.get("bdg", 0)) or "",
            int(r.get("bdp", 0)) or "",
            int(r.get("dp", 0)) or "",
            int(r.get("dpalo", 0)) or "",
            int(r.get("db", 0)) or "",
            int(r.get("df", 0)) or "",
            int(r.get("goles_a_favor", 0)) or "",
            int(r.get("asistencias", 0)) or "",
        ])
    t_met = Table(rows_met, colWidths=[0.9*cm, 2.8*cm] + [1.05*cm]*12)
    t_met.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_met)

    # ── Tabla de portería (solo jugadores con datos de portero) ─────────
    cols_port = ["dorsal", "jugador", "par", "gol_p", "bloq_p", "poste_p"]
    if all(c in jp.columns for c in cols_port):
        jpp = jp[(jp["par"] + jp["gol_p"] + jp["bloq_p"] + jp["poste_p"]) > 0] \
                .sort_values(["par", "min_total"], ascending=[False, False])
        if not jpp.empty:
            story.append(Spacer(1, 6))
            story.append(Paragraph("🥅 Portería", h_seccion))
            rows_p = [["Nº", "Portero", "Paradas", "Goles enc.",
                        "Bloqueos", "Postes", "Disp. total", "% Paradas"]]
            for _, r in jpp.iterrows():
                par_v = int(r.get("par", 0))
                gp = int(r.get("gol_p", 0))
                bl = int(r.get("bloq_p", 0))
                po = int(r.get("poste_p", 0))
                disp_total = par_v + gp + bl + po  # disparos del rival al portero
                pct = round(par_v / max(par_v + gp, 1) * 100, 1) if (par_v + gp) > 0 else 0.0
                rows_p.append([
                    int(r.get("dorsal", 0)) if r.get("dorsal", 0) else "",
                    r.get("jugador", ""),
                    par_v or "",
                    gp or "",
                    bl or "",
                    po or "",
                    disp_total or "",
                    f"{pct}%" if pct > 0 else "",
                ])
            t_port = Table(rows_p, colWidths=[1*cm, 3*cm, 2*cm, 2*cm,
                                                 1.8*cm, 1.5*cm, 2*cm, 2*cm])
            t_port.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (1, 1), (1, -1), "LEFT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t_port)

    # ── Eventos de gol ──────────────────────────────────────────────────────
    if not ep.empty:
        story.append(PageBreak())
        story.append(Paragraph("⚽ Goles del partido", h_seccion))
        evp = ep.copy().sort_values("minuto")
        rows_ev = [["Min", "Marcador", "Equipo", "Acción",
                     "Goleador", "Asistente", "Portero", "Cuarteto", "Descripción"]]
        for _, r in evp.iterrows():
            em = r.get("equipo_marca", "")
            em_disp = "INTER" if em == "INTER" else "RIVAL"
            # Minuto en formato mm:ss (preferir minuto_mmss; si no, mm:00)
            min_val = ""
            mmss = str(r.get("minuto_mmss", "") or "").strip()
            if mmss:
                min_val = mmss
            else:
                try:
                    m = int(float(r.get("minuto") or 0))
                    if m > 0:
                        min_val = f"{m:02d}:00"
                except (TypeError, ValueError):
                    pass
            rows_ev.append([
                min_val,
                r.get("marcador", ""),
                em_disp,
                Paragraph(str(r.get("accion", "")), p_cell),
                r.get("goleador", ""),
                r.get("asistente", ""),
                r.get("portero", ""),
                Paragraph(str(r.get("cuarteto", "")).replace("|", " · "), p_cell),
                Paragraph(str(r.get("descripcion", "")), p_cell),
            ])
        # Anchos: ajustados para que la tabla NO sobresalga del A4 al
        # imprimir. A4 = 21 cm, márgenes 2.4 cm → ancho útil 18.6 cm.
        # Min más ancho para mm:ss: 1.2 cm.
        t_ev = Table(rows_ev, colWidths=[1.2*cm, 1.5*cm, 1.4*cm, 2.0*cm,
                                           1.7*cm, 1.7*cm, 1.7*cm, 3.3*cm, 3.3*cm],
                      repeatRows=1)
        t_ev.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t_ev)

        # ── Gráfico: goles cada 5' (más espaciado y más alto) ───────────────
        try:
            png_chart = _dibujar_goles_5min_mpl(evp)
            story.append(Spacer(1, 24))
            story.append(_png_to_image(png_chart, 17*cm, 8.5*cm))
        except Exception as _ec:
            story.append(Paragraph(f"(Error gráfico goles 5': {_ec})", p_caption))

    # ── Rotaciones ──────────────────────────────────────────────────────────
    # Colores según minutos en una rotación (criterio del usuario):
    #   0 min → blanco · 0-1 → azul · 1-2 → verde · 2-3 → amarillo · >3 → rojo
    # Los porteros NO se colorean (juegan partido entero, no compite con
    # el resto de jugadores en duración de rotación).
    def _color_rotacion(mins: float, es_portero: bool = False):
        if es_portero or mins <= 0:
            return colors.white
        if mins < 1:
            return colors.HexColor("#BBDEFB")   # azul claro
        if mins < 2:
            return colors.HexColor("#C8E6C9")   # verde claro
        if mins < 3:
            return colors.HexColor("#FFF59D")   # amarillo claro
        return colors.HexColor("#EF9A9A")       # rojo claro

    if all(c in jp.columns for c in [f"rot_1t_{i}" for i in range(1, 9)]):
        # Solo si hay al menos un valor > 0 en alguna rotación
        rot_cols_1 = [f"rot_1t_{i}" for i in range(1, 9)]
        rot_cols_2 = [f"rot_2t_{i}" for i in range(1, 9)]
        if jp[rot_cols_1 + rot_cols_2].sum().sum() > 0:
            story.append(PageBreak())
            story.append(Paragraph("🔄 Rotaciones individuales", h_seccion))
            story.append(Paragraph(
                "<font size='8' color='#666'>Color por duración: "
                "<font backcolor='#BBDEFB'>&nbsp;0-1'&nbsp;</font> "
                "<font backcolor='#C8E6C9'>&nbsp;1-2'&nbsp;</font> "
                "<font backcolor='#FFF59D'>&nbsp;2-3'&nbsp;</font> "
                "<font backcolor='#EF9A9A'>&nbsp;>3'&nbsp;</font></font>",
                p_body))
            story.append(Spacer(1, 4))
            for parte_label, cols in [("1ª parte", rot_cols_1), ("2ª parte", rot_cols_2)]:
                story.append(Paragraph(f"<b>{parte_label}</b>", p_body))
                rows_rot = [["Nº", "Jugador", "1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª"]]
                jp_rot = jp[jp["min_total"] > 0].sort_values("min_total", ascending=False)
                # Recoger valores numéricos y marcar si es portero
                valores_rot = []
                porteros_set = set(("J.GARCIA", "J.HERRERO", "OSCAR"))
                es_portero_rows = []
                for _, r in jp_rot.iterrows():
                    fila_vals = [float(r.get(c, 0) or 0) for c in cols]
                    nombre = str(r.get("jugador", "")).upper().strip()
                    # Portero canónico O cualquier jugador con datos de portero
                    es_p = (nombre in porteros_set or
                            float(r.get("par", 0) or 0) > 0 or
                            float(r.get("gol_p", 0) or 0) > 0 or
                            float(r.get("bloq_p", 0) or 0) > 0 or
                            float(r.get("poste_p", 0) or 0) > 0)
                    es_portero_rows.append(es_p)
                    valores_rot.append(fila_vals)
                    rows_rot.append([
                        int(r.get("dorsal", 0)) if r.get("dorsal", 0) else "",
                        r.get("jugador", ""),
                    ] + [_fmt_minutos(v) if v > 0 else "" for v in fila_vals])
                # Estilos base
                style_cmds = [
                    ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "LEFT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
                # Pintar cada celda de rotación según su valor
                for i_row, (vals, es_p) in enumerate(
                        zip(valores_rot, es_portero_rows), start=1):
                    for i_col, v in enumerate(vals):
                        c_idx = 2 + i_col  # 0=Nº, 1=Jugador, 2..9=rotaciones
                        style_cmds.append(
                            ("BACKGROUND", (c_idx, i_row), (c_idx, i_row),
                             _color_rotacion(v, es_p)))
                t_rot = Table(rows_rot, colWidths=[0.9*cm, 2.8*cm] + [1.6*cm]*8)
                t_rot.setStyle(TableStyle(style_cmds))
                story.append(t_rot)
                story.append(Spacer(1, 8))

    # ── Mapas de zona y portería (matplotlib, sin svglib) ───────────────────
    story.append(PageBreak())
    story.append(Paragraph("🎯 Mapas de zona del partido", h_seccion))
    if df_dz.empty:
        story.append(Paragraph(
            "<i>No hay datos en la hoja <b>EST_DISPAROS_ZONAS</b>. "
            "Ejecuta <code>/usr/bin/python3 src/estadisticas_disparos.py "
            "--upload</code> para cargar la hoja ZONA GOLES.</i>", p_caption))
        match = pd.DataFrame()
    else:
        # Match robusto: probamos varias estrategias de búsqueda
        # 1) rival contiene el primer token + fecha exacta
        # 2) rival contiene el primer token (sin filtrar fecha)
        # 3) cualquier palabra de >=4 letras del rival + fecha exacta
        meta_rival = str(rival).upper().strip()
        df_dz["rival_up"] = df_dz["rival"].astype(str).str.upper().str.strip()
        df_dz["fecha_str"] = df_dz["fecha"].astype(str).str.strip()
        fecha_str = str(fecha).strip()

        rival_tokens = [t for t in meta_rival.replace("-", " ").split()
                          if len(t) >= 4]
        match = pd.DataFrame()
        estrategia = ""
        # Estrategia 1: primer token + fecha
        if rival_tokens:
            t0 = rival_tokens[0]
            match = df_dz[
                (df_dz["rival_up"].str.contains(t0, na=False, regex=False)) &
                (df_dz["fecha_str"] == fecha_str)
            ]
            estrategia = f"rival contiene '{t0}' + fecha = {fecha_str}"
        # Estrategia 2: cualquier token + fecha
        if match.empty and rival_tokens:
            for t in rival_tokens:
                m = df_dz[
                    (df_dz["rival_up"].str.contains(t, na=False, regex=False)) &
                    (df_dz["fecha_str"] == fecha_str)
                ]
                if not m.empty:
                    match = m
                    estrategia = f"rival contiene '{t}' + fecha = {fecha_str}"
                    break
        # Estrategia 3: solo por fecha (último recurso)
        if match.empty:
            match = df_dz[df_dz["fecha_str"] == fecha_str]
            if not match.empty:
                estrategia = f"solo por fecha = {fecha_str}"
        if match.empty:
            # Diagnóstico claro
            disp = (df_dz[["rival", "fecha"]].astype(str)
                    .head(15).agg(" · ".join, axis=1).tolist())
            story.append(Paragraph(
                f"<b>⚠️ No se encontró fila en EST_DISPAROS_ZONAS para "
                f"este partido.</b><br/>"
                f"Partido buscado: <b>{rival}</b> · <b>{fecha}</b><br/>"
                f"Tokens probados: {rival_tokens or '(sin tokens largos)'}<br/>"
                f"Primeras filas disponibles en la hoja: "
                f"{'; '.join(disp[:8])}",
                p_caption))
    if not match.empty:
            fz = match.iloc[0]
            af_zona = {f"A{i}": int(pd.to_numeric(fz.get(f"G_AF_Z{i}", 0), errors="coerce") or 0) for i in range(1, 12)}
            af_port = {f"P{i}": int(pd.to_numeric(fz.get(f"G_AF_P{i}", 0), errors="coerce") or 0) for i in range(1, 10)}
            ec_zona = {f"A{i}": int(pd.to_numeric(fz.get(f"G_EC_Z{i}", 0), errors="coerce") or 0) for i in range(1, 12)}
            ec_port = {f"P{i}": int(pd.to_numeric(fz.get(f"G_EC_P{i}", 0), errors="coerce") or 0) for i in range(1, 10)}

            # A favor
            story.append(Paragraph("<b>⚽ Goles a Favor</b>", p_body))
            try:
                img_campo_af = _png_to_image(_dibujar_campo_mpl(af_zona), 12*cm, 6*cm)
                img_port_af = _png_to_image(_dibujar_porteria_mpl(af_port), 6.5*cm, 4.5*cm)
                t = Table([[img_campo_af, img_port_af]],
                           colWidths=[12*cm, 6.5*cm])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
                story.append(t)
            except Exception as _emap:
                story.append(Paragraph(f"(Error generando mapa: {_emap})", p_caption))
            story.append(Spacer(1, 6))

            # En contra
            story.append(Paragraph("<b>🥅 Goles en Contra</b>", p_body))
            try:
                img_campo_ec = _png_to_image(_dibujar_campo_mpl(ec_zona), 12*cm, 6*cm)
                img_port_ec = _png_to_image(_dibujar_porteria_mpl(ec_port), 6.5*cm, 4.5*cm)
                t = Table([[img_campo_ec, img_port_ec]],
                           colWidths=[12*cm, 6.5*cm])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
                story.append(t)
            except Exception as _emap:
                story.append(Paragraph(f"(Error generando mapa: {_emap})", p_caption))

    # ── Footer ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Generado el {_dt.datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        "Movistar Inter FS — Dashboard Arkaitz 25/26",
        p_caption,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: pdf_partido.py <partido_id>")
        sys.exit(1)
    pid = sys.argv[1]
    out = ROOT / f"{pid.replace('.', '_').replace(' ', '_')}.pdf"
    out.write_bytes(generar_pdf_partido(pid))
    print(f"✅ PDF generado: {out}")
