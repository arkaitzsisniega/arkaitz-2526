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
    import numpy as np
    a = np.radians(np.linspace(ang_ini, ang_fin, n))
    return cx + r * np.cos(a), cy + r * np.sin(a)


def _dibujar_campo_mpl(zonas: dict) -> bytes:
    """Dibuja el campo con 11 zonas + portería + áreas usando matplotlib y
    devuelve un PNG en bytes. Geometría (en "px de SVG"): 1m = 25px →
    campo 1000 × 500. Mitad atacante = 0..500 (izda)."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Polygon as MplPolygon

    z = {k: int(v) if v else 0 for k, v in (zonas or {}).items()}
    max_v = max(max(z.values()), 1) if z else 1

    fig, ax = plt.subplots(figsize=(10.8, 5.3), dpi=180)
    fig.patch.set_facecolor("#A5D6A7")
    ax.set_facecolor("#A5D6A7")
    ax.set_xlim(-50, 1010)
    ax.set_ylim(510, -10)  # invertido para que (0,0) esté arriba a la izda
    ax.set_aspect("equal")
    ax.axis("off")

    BORDE = "#1B5E20"

    def col(zk):
        return _mpl_color_zona(z.get(zk, 0), max_v)

    def texto(zk, x, y):
        v = z.get(zk, 0)
        ax.text(x, y - 7, zk, ha="center", va="center",
                fontsize=8, fontweight="bold", color="#222")
        ax.text(x, y + 13, str(v), ha="center", va="center",
                fontsize=11, fontweight="bold", color="#000")

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

    # ── Portería: 3m, postes con franjas rojo/blanco ─────────────────────
    POSTE_LARGO = 32
    GROSOR = 8
    n_franjas = 5
    franja_h = 75 / n_franjas
    # Larguero (vertical, conectando ambos postes en x=-GROSOR..0)
    for i in range(n_franjas):
        c = "#B71C1C" if i % 2 == 0 else "#FFFFFF"
        ax.add_patch(mpatches.Rectangle(
            (-GROSOR, 212.5 + i * franja_h), GROSOR, franja_h,
            facecolor=c, edgecolor="#7F1010", linewidth=0.4, zorder=5))
    # Poste superior e inferior (saliendo hacia x negativo)
    ax.add_patch(mpatches.Rectangle(
        (-POSTE_LARGO, 212.5 - GROSOR/2), POSTE_LARGO, GROSOR,
        facecolor="#B71C1C", edgecolor="#7F1010", linewidth=0.4, zorder=5))
    ax.add_patch(mpatches.Rectangle(
        (-POSTE_LARGO, 287.5 - GROSOR/2), POSTE_LARGO, GROSOR,
        facecolor="#B71C1C", edgecolor="#7F1010", linewidth=0.4, zorder=5))

    # Guardar a PNG en memoria
    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=180, bbox_inches="tight",
                pad_inches=0.05, facecolor="#A5D6A7")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _dibujar_porteria_mpl(cuadrantes: dict) -> bytes:
    """Portería 3×2m con cuadrícula 3×3 (P1-P9) y postes con franjas."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

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

    # 9 cuadrantes
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
                                          facecolor=color, alpha=0.85,
                                          edgecolor="#888", linewidth=0.6,
                                          linestyle=(0, (3, 2)), zorder=3))
        ax.text(x + cuad_w/2, y + cuad_h/2 - 7, zona,
                ha="center", va="center", fontsize=9,
                fontweight="bold", color="#222", zorder=4)
        ax.text(x + cuad_w/2, y + cuad_h/2 + 12, str(v),
                ha="center", va="center", fontsize=12,
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
    p_caption = ParagraphStyle("caption", parent=styles["BodyText"],
                                fontSize=8, textColor=GRIS, alignment=1)

    story = []

    # ── CABECERA ──────────────────────────────────────────────────────────
    story.append(Paragraph("📋 Informe de partido", h_titulo))
    story.append(Paragraph(
        f"<b>{competicion}</b> · {fecha} · {partido_id}", p_body))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Movistar Inter FS</b> &nbsp;&nbsp; "
        f"<font color='#2E7D32'>{gf}</font> "
        f"– <font color='#B71C1C'>{gc}</font> &nbsp;&nbsp; "
        f"<b>{rival}</b>",
        h_marcador,
    ))

    # ── KPIs (con totales del partido si existen) ────────────────────────
    if tp is not None:
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
            labels_row.append(Paragraph(f"<font size='8' color='#666'>{lbl}</font>", p_body))
            valores_row.append(Paragraph(f"<b><font size='14' color='#1B3A6B'>{v}</font></b>", p_body))
            if len(labels_row) == 4:
                rows_kpi.append(labels_row); rows_kpi.append(valores_row)
                labels_row = []; valores_row = []
        if labels_row:
            rows_kpi.append(labels_row); rows_kpi.append(valores_row)
        t_kpi = Table(rows_kpi, colWidths=[4.4*cm]*4)
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

    # ── Tabla de métricas individuales ──────────────────────────────────────
    story.append(Paragraph("📊 Métricas individuales", h_seccion))
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
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t_met)

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
            min_val = ""
            try:
                m = int(float(r.get("minuto") or 0))
                if m > 0:
                    min_val = str(m)
            except (TypeError, ValueError):
                pass
            rows_ev.append([
                min_val,
                r.get("marcador", ""),
                em_disp,
                Paragraph(str(r.get("accion", "")), p_body),
                r.get("goleador", ""),
                r.get("asistente", ""),
                r.get("portero", ""),
                Paragraph(str(r.get("cuarteto", "")).replace("|", " · "), p_body),
                Paragraph(str(r.get("descripcion", "")), p_body),
            ])
        t_ev = Table(rows_ev, colWidths=[0.9*cm, 1.8*cm, 1.5*cm, 2.5*cm,
                                           2*cm, 2*cm, 2*cm, 4.5*cm, 4*cm],
                      repeatRows=1)
        t_ev.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t_ev)

    # ── Rotaciones ──────────────────────────────────────────────────────────
    if all(c in jp.columns for c in [f"rot_1t_{i}" for i in range(1, 9)]):
        # Solo si hay al menos un valor > 0 en alguna rotación
        rot_cols_1 = [f"rot_1t_{i}" for i in range(1, 9)]
        rot_cols_2 = [f"rot_2t_{i}" for i in range(1, 9)]
        if jp[rot_cols_1 + rot_cols_2].sum().sum() > 0:
            story.append(PageBreak())
            story.append(Paragraph("🔄 Rotaciones individuales", h_seccion))
            for parte_label, cols in [("1ª parte", rot_cols_1), ("2ª parte", rot_cols_2)]:
                story.append(Paragraph(f"<b>{parte_label}</b>", p_body))
                rows_rot = [["Nº", "Jugador", "1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª"]]
                jp_rot = jp[jp["min_total"] > 0].sort_values("min_total", ascending=False)
                for _, r in jp_rot.iterrows():
                    rows_rot.append([
                        int(r.get("dorsal", 0)) if r.get("dorsal", 0) else "",
                        r.get("jugador", ""),
                    ] + [_fmt_minutos(r.get(c, 0)) for c in cols])
                t_rot = Table(rows_rot, colWidths=[0.9*cm, 2.8*cm] + [1.6*cm]*8)
                t_rot.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_MUY_CLARO]),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "LEFT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                story.append(t_rot)
                story.append(Spacer(1, 6))

    # ── Mapas de zona y portería (matplotlib, sin svglib) ───────────────────
    if not df_dz.empty:
        meta_rival = str(rival).upper()
        rival_corto = meta_rival.split()[0] if meta_rival else ""
        df_dz["rival_up"] = df_dz["rival"].astype(str).str.upper()
        match = df_dz[
            (df_dz["rival_up"].str.contains(rival_corto, na=False)) &
            (df_dz["fecha"].astype(str) == str(fecha))
        ]
        if not match.empty:
            fz = match.iloc[0]
            af_zona = {f"A{i}": int(pd.to_numeric(fz.get(f"G_AF_Z{i}", 0), errors="coerce") or 0) for i in range(1, 12)}
            af_port = {f"P{i}": int(pd.to_numeric(fz.get(f"G_AF_P{i}", 0), errors="coerce") or 0) for i in range(1, 10)}
            ec_zona = {f"A{i}": int(pd.to_numeric(fz.get(f"G_EC_Z{i}", 0), errors="coerce") or 0) for i in range(1, 12)}
            ec_port = {f"P{i}": int(pd.to_numeric(fz.get(f"G_EC_P{i}", 0), errors="coerce") or 0) for i in range(1, 10)}

            story.append(PageBreak())
            story.append(Paragraph("🎯 Mapas de zona del partido", h_seccion))

            # A favor
            story.append(Paragraph("<b>⚽ Cómo metemos goles</b>", p_body))
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
            story.append(Paragraph("<b>🥅 Cómo recibimos goles</b>", p_body))
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
