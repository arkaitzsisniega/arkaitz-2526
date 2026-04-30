"""
pdf_planilla_blank.py — Genera planillas A4 horizontal en blanco para
apuntar a boli durante el partido.

Dos planillas:
  - 'arkaitz': la del usuario (Arkaitz). Cabecera + tabla jugadores con
    métricas de portería/disparos + 2 mapas de campo (Inter / rival) +
    portería + tabla goles + tabla faltas.
  - 'compa': la del compañero. Cabecera + tabla jugadores con acciones
    individuales (PF, PNF, ROBOS, CORTES, BDG, BDP) + tabla córners y
    bandas (tipos específicos del equipo).

Cada planilla en dos versiones:
  - 1T: campo Inter atacando a la derecha
  - 2T: campo Inter atacando a la izquierda (cambio de campo en 2ª parte)

Uso:
  /usr/bin/python3 src/pdf_planilla_blank.py --modo arkaitz --parte 1T \\
      --partido J27.PEÑISCOLA --salida /tmp/planilla.pdf

  Sin --partido: genera planilla con cabecera y plantilla VACÍAS.
  Sin --salida: imprime los bytes del PDF en stdout (útil para Streamlit).

API pública:
  generar_planilla(modo, parte, partido_id=None, sh=None) -> bytes
"""
from __future__ import annotations

import argparse
import io
import sys
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage,
)

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
LOGOS = ASSETS / "logos"
PLANILLA = ASSETS / "planilla"
SHEET_NAME = "Arkaitz - Datos Temporada 2526"

# Estilos
AZUL = colors.HexColor("#1B3A6B")
VERDE = colors.HexColor("#2E7D32")
ROJO = colors.HexColor("#B71C1C")
GRIS = colors.HexColor("#666666")
GRIS_CLARO = colors.HexColor("#F5F5F5")

# Tipos canónicos de córners y bandas (sacados de la pestaña ALEX/Txubas)
TIPOS_CORNERS = ["VOLEA 1", "VOLEA 2", "3 -- 1", "3 -- 2",
                  "CAPITÁN 1", "CAPITÁN 2", "CORTA"]
TIPOS_BANDAS = ["MANOS", "TRIÁN. 1", "TRIÁN. 2", "CAM-SAC", "VERTICAL",
                 "TALAVERA", "PEGA", "SPORTING", "1 x 1", "JOKIC",
                 "VALDEPEÑ."]


# ─── Conexión Sheet ─────────────────────────────────────────────────────────
def _connect():
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds_path = ROOT / "google_credentials.json"
    if creds_path.exists():
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    else:
        try:
            import streamlit as st
            info = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise FileNotFoundError(f"No google_credentials.json y st.secrets no disponible: {e}")
    return gspread.authorize(creds).open(SHEET_NAME)


# ─── Datos del partido (cabecera + plantilla) ─────────────────────────────
def _datos_partido(sh, partido_id: str) -> dict:
    """Devuelve dict con cabecera y plantilla (jugadores convocados).
    Si no hay datos, devuelve estructuras vacías."""
    out = {"rival": "", "fecha": "", "lugar": "", "hora": "",
           "competicion": "", "local_visitante": "", "jugadores": []}
    if not partido_id:
        return out
    # EST_TOTALES_PARTIDO para cabecera
    try:
        ws = sh.worksheet("EST_TOTALES_PARTIDO")
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty:
            f = df[df["partido_id"].astype(str) == partido_id]
            if not f.empty:
                r = f.iloc[0]
                out["rival"] = str(r.get("rival", ""))
                out["fecha"] = str(r.get("fecha", ""))
                out["lugar"] = str(r.get("lugar", ""))
                out["hora"] = str(r.get("hora", ""))
                out["competicion"] = str(r.get("categoria", "") or r.get("competicion", ""))
                out["local_visitante"] = str(r.get("local_visitante", ""))
    except Exception:
        pass
    # EST_PLANTILLAS para los convocados
    try:
        ws = sh.worksheet("EST_PLANTILLAS")
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty:
            f = df[df["partido_id"].astype(str) == partido_id]
            if not f.empty:
                jugs = []
                for _, r in f.iterrows():
                    d = r.get("dorsal", "")
                    try:
                        d = int(float(d)) if d not in ("", None) else None
                    except (TypeError, ValueError):
                        d = None
                    jugs.append({
                        "dorsal": d,
                        "jugador": str(r.get("jugador", "") or "").upper(),
                        "posicion": str(r.get("posicion", "") or "").upper(),
                    })
                # Ordenar: porteros primero (por dorsal), luego campo (por dorsal)
                porteros = sorted([j for j in jugs if j["posicion"] == "PORTERO"],
                                    key=lambda j: (j["dorsal"] or 999))
                campo = sorted([j for j in jugs if j["posicion"] != "PORTERO"],
                                 key=lambda j: (j["dorsal"] or 999))
                out["jugadores"] = porteros + campo
    except Exception:
        pass
    # Fallback: si no hay plantilla del partido, usar JUGADORES_ROSTER
    if not out["jugadores"]:
        try:
            ws = sh.worksheet("JUGADORES_ROSTER")
            df = pd.DataFrame(ws.get_all_records())
            if not df.empty:
                df = df[df.get("activo", "TRUE").astype(str).str.upper() == "TRUE"]
                jugs = []
                for _, r in df.iterrows():
                    d = r.get("dorsal", "")
                    try:
                        d = int(float(d)) if d not in ("", None) else None
                    except (TypeError, ValueError):
                        d = None
                    jugs.append({
                        "dorsal": d,
                        "jugador": str(r.get("nombre", "") or "").upper(),
                        "posicion": str(r.get("posicion", "") or "").upper(),
                    })
                porteros = sorted([j for j in jugs if j["posicion"] == "PORTERO"],
                                    key=lambda j: (j["dorsal"] or 999))
                campo = sorted([j for j in jugs if j["posicion"] != "PORTERO"],
                                 key=lambda j: (j["dorsal"] or 999))
                # Limitar a 14 (filas estándar de la planilla)
                out["jugadores"] = (porteros + campo)[:14]
        except Exception:
            pass
    return out


# ─── Helpers de layout ──────────────────────────────────────────────────────
def _logo(path: Path, w_cm: float, h_cm: float, proporcional: bool = True,
           crop_borde: int = 0):
    """Devuelve una RLImage si el path existe; si no, un placeholder vacío.

    proporcional=True (default): mantiene el ratio original de la imagen
    (puede salir más pequeña que w×h si el ratio no encaja).
    proporcional=False: estira la imagen a w×h exacto (deformación leve).
    crop_borde: si >0, recorta ese nº de píxeles de cada borde antes de
    embeber (útil para PNGs que ya traen borde rojo dentro y queremos
    poner el nuestro propio sin que se sobrepongan).
    """
    if path.exists():
        try:
            src = str(path)
            if crop_borde > 0:
                # Recortar el borde con PIL → escribir a buffer en memoria
                try:
                    from PIL import Image as PILImage
                    pil = PILImage.open(src)
                    w_px, h_px = pil.size
                    box = (crop_borde, crop_borde,
                           w_px - crop_borde, h_px - crop_borde)
                    pil = pil.crop(box)
                    buf = io.BytesIO()
                    pil.save(buf, format="PNG")
                    buf.seek(0)
                    src = buf
                except Exception:
                    src = str(path)  # si PIL falla, embebe sin recortar
            kwargs = {"width": w_cm * cm, "height": h_cm * cm}
            if proporcional:
                kwargs["kind"] = "proportional"
            img = RLImage(src, **kwargs)
            img.hAlign = "CENTER"
            return img
        except Exception:
            pass
    return Paragraph("", ParagraphStyle("blank"))


def _cabecera(datos: dict, parte_label: str, modo: str = "arkaitz") -> Table:
    """Cabecera estilo Excel original. Layout 2 filas con celdas anchas
    (no 6 columnas estrechas — eso rompía las palabras en 2 líneas):

      [logo Inter]  PARTIDO: MOVISTAR INTER vs RIVAL  | COMPETICIÓN: ___  [logo dorado]
                    LUGAR: ___    FECHA: ___    HORA: ___    PARTE: 1ª

    Cada fila usa 1 sola Paragraph con todo el contenido (label+valor+...)
    para que el motor pueda envolver naturalmente si hace falta.
    """
    styles = getSampleStyleSheet()
    p_inline = ParagraphStyle("hd_inline", parent=styles["BodyText"],
                                 fontSize=10, alignment=0, leading=13,
                                 fontName="Helvetica", textColor=colors.black,
                                 spaceAfter=0, spaceBefore=0)
    rival = datos.get("rival") or "_____________"
    competicion = datos.get("competicion") or "_____________"
    lugar = datos.get("lugar") or "_____________"
    fecha_fmt = datos.get("fecha") or "__/__/____"
    try:
        d = pd.to_datetime(fecha_fmt, errors="coerce")
        if pd.notnull(d):
            fecha_fmt = d.strftime("%d/%m/%Y")
    except Exception:
        pass
    hora = datos.get("hora") or "____"

    lv = (datos.get("local_visitante") or "").upper()
    if lv == "VISITANTE":
        izq, dcha = rival, "MOVISTAR INTER"
    else:
        izq, dcha = "MOVISTAR INTER", rival

    # 3 filas:
    #   Fila 1: PARTIDO (SPAN ambas cols, en 1 línea)
    #   Fila 2: LUGAR | COMPETICIÓN
    #   Fila 3: FECHA · HORA · PARTE  (compa omite PARTE)
    fila3 = (
        f"<b>FECHA:</b> &nbsp;{fecha_fmt} &nbsp;&nbsp; "
        f"<b>HORA:</b> &nbsp;{hora}"
    )
    if modo != "compa":
        fila3 += f" &nbsp;&nbsp; <b>PARTE:</b> &nbsp;{parte_label}"
    info = [
        [Paragraph(
            f"<b>PARTIDO:</b> &nbsp;<b>{izq}</b> &nbsp;vs&nbsp; <b>{dcha}</b>",
            p_inline), ""],
        [Paragraph(f"<b>LUGAR:</b> &nbsp;{lugar}", p_inline),
         Paragraph(f"<b>COMPETICIÓN:</b> &nbsp;{competicion}", p_inline)],
        [Paragraph(fila3, p_inline), ""],
    ]

    # Tanto arkaitz como compa son A4 VERTICAL → 19cm útil
    # 2 logos (1.4cm) + centro 16.2cm
    ancho_logo = 1.4*cm
    ancho_total = 19.0*cm
    # Dcha más ancha para que "FECHA: 02/05/2026  HORA: 12:00  PARTE: 1ª"
    # quepa en 1 línea sin saltos.
    col_widths = [7.2*cm, 9.0*cm]

    t_info = Table(info, colWidths=col_widths,
                    rowHeights=[0.55*cm, 0.55*cm, 0.55*cm])
    t_info.setStyle(TableStyle([
        # PARTIDO ocupa toda la anchura → SPAN cols 0-1 en fila 0
        ("SPAN", (0, 0), (1, 0)),
        # FECHA·HORA·PARTE ocupa toda la anchura → SPAN cols 0-1 en fila 2
        ("SPAN", (0, 2), (1, 2)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    centro_w = ancho_total - 2 * ancho_logo
    cab = Table(
        [[_logo(LOGOS / "inter_verde.png", 1.3, 1.65),
          t_info,
          _logo(LOGOS / "inter_dorado.png", 1.3, 1.65)]],
        colWidths=[ancho_logo, centro_w, ancho_logo],
    )
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return cab


# ─── Planilla "Arkaitz" (A4 VERTICAL, fiel al Excel original) ────────────
def _planilla_arkaitz(jugadores, parte_label, mapa_inter, mapa_rival,
                       img_porteria) -> list:
    """Planilla A4 VERTICAL · UNA HOJA. Layout fiel al Excel original:

    ┌─────────────────────────────────────────────────┐
    │ Cabecera: PARTIDO Inter vs ___ · COMP · LUGAR   │
    │ FECHA · HORA  (logos a los lados)               │
    ├─────────────────────────────────────────────────┤
    │ Tabla 14 jugadores. Cols:                        │
    │ NUM JUG TA ROJ DP DPalo DB DF | FUERA POSTE     │
    │ BLOQ PARADA GOL (cols portería solo en filas    │
    │ porteros; resto = gran rectángulo "DISPAROS DEL │
    │ PORTERO CONTRARIO")                              │
    ├─────────────────────────────────────────────────┤
    │ Tabla GOLES (10 filas, ancho completo)          │
    │ EQUIPO Nº JUG RESULTADO MIN ASIST ACCIÓN ROT.   │
    ├─────────────────────────────────────────────────┤
    │ DISPAROS / GOLES A FAVOR (verde)                │
    │ [portería] [mapa Inter (verde)] [faltas Inter]  │
    ├─────────────────────────────────────────────────┤
    │ DISPAROS / GOLES EN CONTRA (rojo)               │
    │ [portería] [mapa rival (rojo)] [faltas Rival]   │
    │                                                  │
    │ Leyenda: ✗ FUERA · ⊙ A PUERTA · ⊗ GOL           │
    └─────────────────────────────────────────────────┘

    A4 vertical = 21cm × 29.7cm (útil ~19.6 × 28.3).
    """
    styles = getSampleStyleSheet()
    p_th = ParagraphStyle("th", parent=styles["BodyText"], fontSize=7,
                            textColor=colors.white, alignment=1, leading=8,
                            fontName="Helvetica-Bold")
    p_th_dark = ParagraphStyle("th_d", parent=styles["BodyText"], fontSize=7,
                                  textColor=colors.black, alignment=1, leading=8,
                                  fontName="Helvetica-Bold")
    p_nota = ParagraphStyle("nota", parent=styles["BodyText"], fontSize=8,
                              alignment=1, leading=10,
                              textColor=colors.HexColor("#666"),
                              fontName="Helvetica-Oblique")

    # ═════════════════════════════════════════════════════════════════
    # 1) TABLA DE JUGADORES
    # 13 cols: NUM | JUGADOR | T.A | ROJ | DP | DPalo | DB | DF
    #        | FUERA | POSTE | BLOQUEADO | PARADA | GOL
    # Anchos para 19cm útil:
    # NUM(0.7) JUG(2.6) TA(0.7) ROJ(0.7) DP(0.9) DPalo(1.0) DB(0.9) DF(0.9) | FUERA(2.0) POSTE(2.0) BLOQ(2.5) PARADA(2.0) GOL(1.6)
    # Total: 0.7+2.6+0.7+0.7+0.9+1.0+0.9+0.9 + 2.0+2.0+2.5+2.0+1.6 = 18.5cm
    # ═════════════════════════════════════════════════════════════════
    # Headers cortos para que NO se rompan en 2 líneas en columnas estrechas
    cabeceras = ["Nº", "JUGADOR", "T.A", "T.R",
                 "DP", "DPalo", "DB", "DF",
                 "FUERA", "POSTE", "BLOQ.", "PARADA", "GOL"]
    cabeceras_p = []
    for i, c in enumerate(cabeceras):
        if c == "T.A":
            cabeceras_p.append(Paragraph(c, p_th_dark))
        else:
            cabeceras_p.append(Paragraph(c, p_th))
    rows = [cabeceras_p]
    n_filas = 14
    es_portero_idx = []  # 1-indexed
    for i in range(n_filas):
        if i < len(jugadores):
            j = jugadores[i]
            d = str(j["dorsal"]) if j["dorsal"] is not None else ""
            n = j["jugador"]
            if (j.get("posicion", "") or "").upper() == "PORTERO":
                es_portero_idx.append(i + 1)
        else:
            d, n = "", ""
        rows.append([d, n, "", "", "", "", "", "", "", "", "", "", ""])

    # A4 vertical útil ~19cm. Las 11 columnas de métricas (TA, ROJ, DP,
    # DPalo, DB, DF, FUERA, POSTE, BLOQ, PARADA, GOL) iguales: 1.4cm.
    # NUM(0.7) + JUG(2.6) + 11×1.4 = 18.7cm
    anchos_jug = [0.7*cm, 2.6*cm] + [1.4*cm] * 11
    h_header = 0.55*cm
    h_fila = 0.45*cm
    rh_jug = [h_header] + [h_fila] * n_filas

    style_jug = [
        # Header en azul oscuro (excepto T.A amarillo y ROJ rojo)
        ("BACKGROUND", (0, 0), (1, 0), AZUL),
        ("BACKGROUND", (4, 0), (7, 0), AZUL),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FFEB3B")),  # TA header amarillo
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#D32F2F")),  # ROJ header rojo
        ("BACKGROUND", (8, 0), (12, 0), colors.HexColor("#E91E63")),  # Cols portería header rosa
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    # Coloreado de columnas TA y ROJ en filas de datos
    for r_i in range(1, n_filas + 1):
        style_jug.append(("BACKGROUND", (2, r_i), (2, r_i),
                           colors.HexColor("#FFF59D")))   # TA amarillo claro
        style_jug.append(("BACKGROUND", (3, r_i), (3, r_i),
                           colors.HexColor("#FF5252")))   # ROJ rojo medio (fiel al original)
    # Coloreado de columnas DP, DPalo, DB, DF en filas de datos: azul claro
    for r_i in range(1, n_filas + 1):
        for c_i in (4, 5, 6, 7):
            style_jug.append(("BACKGROUND", (c_i, r_i), (c_i, r_i),
                               colors.HexColor("#D6E5F4")))
    # Coloreado de columnas portería para PORTEROS (filas 1-2): rosa claro
    for r_i in es_portero_idx:
        for c_i in range(8, 13):
            style_jug.append(("BACKGROUND", (c_i, r_i), (c_i, r_i),
                               colors.HexColor("#FFD9E0")))

    # FUSIONAR las celdas de portería para los NO porteros en bloques contiguos.
    no_p = [i for i in range(1, n_filas + 1) if i not in es_portero_idx]
    # En el ORIGINAL hay 2 zonas en las cols porteria de los no-porteros:
    #   1) JUSTO DEBAJO de los 2 porteros (1ª fila no-portero):
    #      "DISPAROS DEL PORTERO CONTRARIO" como título, con celdas
    #      a la derecha para apuntar.
    #   2) Resto (2ª no-portero hasta el final): rectángulo blanco grande.
    if no_p:
        primera_no_p = no_p[0]      # ej. 3 (justo debajo de los 2 porteros)
        resto_no_p = no_p[1:]       # filas 4..14 → un solo gran rectángulo
        # 1) Fila "DISPAROS DEL PORTERO CONTRARIO": SPAN cols 8-11 con texto
        #    (4 cols = 5.6cm — texto cómodo en 1 línea con fuente normal),
        #    solo col 12 (GOL) queda blanca para apuntar.
        style_jug.append(("SPAN", (8, primera_no_p), (11, primera_no_p)))
        style_jug.append(("BACKGROUND", (8, primera_no_p), (11, primera_no_p),
                            colors.HexColor("#FFD9E0")))  # rosa claro
        rows[primera_no_p][8] = Paragraph(
            "<b>DISPAROS DEL PORTERO CONTRARIO</b>", p_nota)
        # Solo la col 12 (GOL) queda blanca con borde para apuntar.
        style_jug.append(("BACKGROUND", (12, primera_no_p),
                            (12, primera_no_p), colors.white))
        # 2) Resto de no-porteros: SPAN entera 8..12 en blanco (notas)
        if resto_no_p:
            style_jug.append(("SPAN", (8, resto_no_p[0]), (12, resto_no_p[-1])))
            style_jug.append(("BACKGROUND", (8, resto_no_p[0]),
                                (12, resto_no_p[-1]), colors.white))

    t_jug = Table(rows, colWidths=anchos_jug, rowHeights=rh_jug)
    t_jug.setStyle(TableStyle(style_jug))

    # ═════════════════════════════════════════════════════════════════
    # 2) TABLA DE GOLES (10 filas, ancho completo ~19cm)
    # Cols: EQUIPO(1.6) Nº JUG(1.0) RESULTADO(1.6) MIN(1.0) ASIST(2.4) ACCIÓN(8.6) ROTACIÓN(2.8)
    # Total: 1.6+1.0+1.6+1.0+2.4+8.6+2.8 = 19cm
    # ═════════════════════════════════════════════════════════════════
    # Headers más cortos para evitar quiebres en 2 líneas
    cabeceras_g = ["EQUIPO", "Nº", "MARCADOR", "MIN", "ASIST",
                    "ACCIÓN", "ROTACIÓN"]
    rows_g = [[Paragraph(c, p_th_dark) for c in cabeceras_g]]
    for _ in range(10):
        rows_g.append([""] * 7)
    # Total 18.7cm (mismo ancho que tabla jugadores).
    # ROTACIÓN ancha para escribir 4-5 jugadores en pista. ACCIÓN
    # estrecha porque solo va el tipo (Banda, Córner, 4x4...).
    anchos_g = [1.5*cm, 0.8*cm, 1.9*cm, 1.0*cm, 2.4*cm, 4.0*cm, 7.1*cm]
    h_g = 0.42*cm
    t_goles = Table(rows_g, colWidths=anchos_g,
                     rowHeights=[0.5*cm] + [h_g] * 10)
    t_goles.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-BoldOblique"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
    ]))

    # Título "GOLES" sobre la tabla (estilo barra gris fina)
    p_tit_goles = ParagraphStyle("tg", parent=styles["BodyText"], fontSize=9,
                                    fontName="Helvetica-BoldOblique",
                                    alignment=1, leading=10,
                                    textColor=colors.black)
    barra_goles = Table([[Paragraph("GOLES", p_tit_goles)]],
                          colWidths=[18.7*cm], rowHeights=[0.42*cm])
    barra_goles.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # ═════════════════════════════════════════════════════════════════
    # 3) BLOQUES MAPAS (A FAVOR / EN CONTRA)
    # Cada bloque: título + 3 columnas:
    #   [portería 4cm × 4.5cm] [mapa 9cm × 4.5cm] [tabla faltas 4cm × 4.5cm]
    # Total ancho: 4 + 9 + 4 = 17cm; centrado en 19cm útil
    # ═════════════════════════════════════════════════════════════════
    # A4 vertical útil ~19cm.
    # Bloque: portería(6.5cm) + mapa(8.0cm) + faltas(4.0cm) = 18.5cm
    # Altura del bloque: 5.5cm. Mapa y portería con la MISMA altura.
    # crop_borde=4: recorta el borde rojo que el PNG ya trae para que el
    # borde verde/rojo del TableStyle no se solape con él.
    img_inter = _logo(mapa_inter, 8.0, 5.5,
                        proporcional=False, crop_borde=8) if mapa_inter and mapa_inter.exists() else Paragraph("", p_th)
    img_rival = _logo(mapa_rival, 8.0, 5.5,
                        proporcional=False, crop_borde=8) if mapa_rival and mapa_rival.exists() else Paragraph("", p_th)
    # Portería: ESTIRADA a 6.5×5.5 (más ancha que antes, sin proporcional)
    # para que ocupe más espacio y se vea bien.
    img_port_af = _logo(img_porteria, 6.5, 5.5,
                          proporcional=False) if img_porteria and img_porteria.exists() else Paragraph("", p_th)
    img_port_ec = _logo(img_porteria, 6.5, 5.5,
                          proporcional=False) if img_porteria and img_porteria.exists() else Paragraph("", p_th)

    def _tabla_faltas(equipo_label, color_borde):
        """Tabla de faltas estilo original: titulito + cabecera Nº/TIEMPO/JUG.
        + 6 filas. La 6ª en rojo claro."""
        h = []
        # Título "INTER MOVISTAR" o "RIVAL"
        h.append([Paragraph(equipo_label, p_th_dark), "", ""])
        # T.M.: ___
        h.append([Paragraph("T.M.: ____", p_th_dark), "", ""])
        # FALTAS
        h.append([Paragraph("FALTAS", p_th_dark), "", ""])
        # Cabecera
        h.append([Paragraph("Nº", p_th_dark),
                   Paragraph("TIEMPO", p_th_dark),
                   Paragraph("JUG.", p_th_dark)])
        for i in range(1, 7):
            h.append([str(i), "", ""])
        t = Table(h, colWidths=[0.7*cm, 1.7*cm, 1.4*cm],
                   rowHeights=[0.4*cm]*4 + [0.35*cm]*6)
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (2, 0)),
            ("SPAN", (0, 1), (2, 1)),
            ("SPAN", (0, 2), (2, 2)),
            ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO),
            ("BACKGROUND", (0, 1), (-1, 1), GRIS_CLARO),
            ("BACKGROUND", (0, 2), (-1, 2), GRIS_CLARO),
            ("BACKGROUND", (0, 3), (-1, 3), GRIS_CLARO),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # Borde principal del color del equipo
            ("BOX", (0, 0), (-1, -1), 1.2, color_borde),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
            # 6ª falta en rojo claro
            ("BACKGROUND", (0, 9), (-1, 9), colors.HexColor("#FF5252")),
            ("TEXTCOLOR", (0, 9), (0, 9), colors.white),
            ("FONTNAME", (0, 9), (0, 9), "Helvetica-Bold"),
        ]))
        return t

    t_faltas_inter = _tabla_faltas("INTER MOVISTAR", VERDE)
    t_faltas_rival = _tabla_faltas("RIVAL", ROJO)

    # Título de cada bloque
    p_tit_af = ParagraphStyle("af", parent=styles["BodyText"], fontSize=10,
                                 fontName="Helvetica-Bold", textColor=VERDE,
                                 alignment=1, leading=12)
    p_tit_ec = ParagraphStyle("ec", parent=styles["BodyText"], fontSize=10,
                                 fontName="Helvetica-Bold", textColor=ROJO,
                                 alignment=1, leading=12)

    # Layout: portería (5.5cm) | mapa (9cm) | tabla faltas (4cm). Total 18.5cm.
    # Altura del bloque: 5.5cm (mismo alto en portería, mapa y faltas)
    # BORDE del bloque: VERDE para A FAVOR, ROJO para EN CONTRA (siempre
    # coincide con el título). El borde lo añadimos al Table, no al PNG.
    bloque_af = Table([
        [Paragraph("DISPAROS / GOLES A FAVOR", p_tit_af)],
        [Table([[img_port_af, img_inter, t_faltas_inter]],
                colWidths=[6.5*cm, 8.0*cm, 4.0*cm],
                rowHeights=[5.5*cm],
                style=TableStyle([
                    # Borde verde alrededor del MAPA (col 1).
                    # El PNG ya viene recortado (crop_borde=8) para que su
                    # borde rojo/verde interno no se solape con éste.
                    ("BOX", (1, 0), (1, 0), 2.0, VERDE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (1, 0), (1, 0), 1),
                    ("RIGHTPADDING", (1, 0), (1, 0), 1),
                    ("TOPPADDING", (1, 0), (1, 0), 1),
                    ("BOTTOMPADDING", (1, 0), (1, 0), 1),
                ]))],
    ], colWidths=[18.5*cm])
    bloque_af.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    bloque_ec = Table([
        [Paragraph("DISPAROS / GOLES EN CONTRA", p_tit_ec)],
        [Table([[img_port_ec, img_rival, t_faltas_rival]],
                colWidths=[6.5*cm, 8.0*cm, 4.0*cm],
                rowHeights=[5.5*cm],
                style=TableStyle([
                    # Borde rojo alrededor del MAPA (col 1).
                    # El PNG ya viene recortado (crop_borde=8) para que su
                    # borde rojo/verde interno no se solape con éste.
                    ("BOX", (1, 0), (1, 0), 2.0, ROJO),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (1, 0), (1, 0), 1),
                    ("RIGHTPADDING", (1, 0), (1, 0), 1),
                    ("TOPPADDING", (1, 0), (1, 0), 1),
                    ("BOTTOMPADDING", (1, 0), (1, 0), 1),
                ]))],
    ], colWidths=[18.5*cm])
    bloque_ec.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    # Leyenda
    p_leyenda = ParagraphStyle("ley", parent=styles["BodyText"], fontSize=9,
                                  fontName="Helvetica-Bold", alignment=1,
                                  leading=11)

    flowables = [
        t_jug,
        Spacer(1, 4),
        barra_goles,
        t_goles,
        Spacer(1, 4),
        bloque_af,
        Spacer(1, 2),
        bloque_ec,
        Spacer(1, 3),
        Paragraph("✗ DISPARO FUERA &nbsp;&nbsp;&nbsp;&nbsp; "
                   "⊙ DISPARO A PUERTA &nbsp;&nbsp;&nbsp;&nbsp; "
                   "⊗ GOL", p_leyenda),
    ]
    return flowables


# ─── Planilla "Compañero" (ALEX) — A4 VERTICAL, ambas partes en 1 hoja ──
def _bloque_parte_compa(jugadores, titulo_parte: str) -> Table:
    """Genera UN bloque (1ª o 2ª parte) de la planilla del compañero.
    Layout vertical:
        Mini-título "1ª PARTE" / "2ª PARTE"
        Tabla 14 jugadores + EQUIPO (cols PF/PNF/ROBOS/CORTES/BDG/BDP)
        Tabla CÓRNERS horizontal (1 columna por tipo, 1 fila para escribir)
        Tabla BANDAS horizontal (idem)
    """
    styles = getSampleStyleSheet()
    p_th_dark = ParagraphStyle("th_d", parent=styles["BodyText"], fontSize=8,
                                  textColor=colors.black, alignment=1,
                                  fontName="Helvetica-Bold", leading=10)
    p_titulo_parte = ParagraphStyle("tp", parent=styles["BodyText"], fontSize=10,
                                       fontName="Helvetica-Bold", alignment=1,
                                       leading=12, textColor=AZUL)
    p_th_corn = ParagraphStyle("thc", parent=styles["BodyText"], fontSize=9,
                                  textColor=colors.white, alignment=1,
                                  fontName="Helvetica-Bold", leading=11)
    p_corn_tipo = ParagraphStyle("ct", parent=styles["BodyText"], fontSize=7.5,
                                    textColor=colors.black, alignment=1,
                                    fontName="Helvetica-Bold", leading=9)

    # ═════════════════════════════════════════════════════════════════
    # Tabla principal jugadores: Nº | JUGADOR | T.A | T.R | PF | PNF | ROBOS | CORTES | BDG | BDP
    # A4 vertical útil ~19cm. T.A y T.R estrechas (0.95cm), CORTES en 1 línea.
    # Total: 1.1 + 3.5 + 0.95 + 0.95 + 6×1.92 = 18.02cm
    # ═════════════════════════════════════════════════════════════════
    cabeceras = ["NUM", "JUGADOR", "T.A", "T.R",
                 "PF", "PNF", "ROBOS", "CORTES", "BDG", "BDP"]
    rows = [[Paragraph(c, p_th_dark) for c in cabeceras]]
    for i in range(14):
        if i < len(jugadores):
            j = jugadores[i]
            d = str(j["dorsal"]) if j["dorsal"] is not None else ""
            n = j["jugador"]
        else:
            d, n = "", ""
        rows.append([d, n] + [""] * 8)
    # Fila final EQUIPO (totales del equipo)
    rows.append([Paragraph("<b>EQUIPO</b>", p_th_dark), "", "", "",
                  "", "", "", "", "", ""])

    anchos = [1.1*cm, 3.5*cm, 0.95*cm, 0.95*cm,
              1.92*cm, 1.92*cm, 1.92*cm, 1.92*cm, 1.92*cm, 1.92*cm]
    h_h = 0.5*cm
    h_f = 0.42*cm
    rh = [h_h] + [h_f]*14 + [h_h]
    t_jug = Table(rows, colWidths=anchos, rowHeights=rh)

    style_compa = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        # Headers
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FFEB3B")),  # T.A amarillo
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#D32F2F")),  # T.R rojo
        ("TEXTCOLOR", (3, 0), (3, 0), colors.white),
        ("BACKGROUND", (0, 0), (1, 0), GRIS_CLARO),
        ("BACKGROUND", (4, 0), (-1, 0), GRIS_CLARO),
        # Última fila EQUIPO en gris claro
        ("BACKGROUND", (0, -1), (-1, -1), GRIS_CLARO),
        ("SPAN", (0, -1), (1, -1)),
    ]
    # Fondos por columna en filas de datos
    for r_i in range(1, 16):
        style_compa.append(("BACKGROUND", (2, r_i), (2, r_i),
                              colors.HexColor("#FFF59D")))
        style_compa.append(("BACKGROUND", (3, r_i), (3, r_i),
                              colors.HexColor("#FF5252")))
        n_oscuro = colors.HexColor("#FFAB91")
        n_claro = colors.HexColor("#FFCCBC")
        col_pfpnf = n_oscuro if r_i % 2 == 1 else n_claro
        style_compa.append(("BACKGROUND", (4, r_i), (5, r_i), col_pfpnf))
        v_oscuro = colors.HexColor("#A5D6A7")
        v_claro = colors.HexColor("#C8E6C9")
        col_rc = v_oscuro if r_i % 2 == 1 else v_claro
        style_compa.append(("BACKGROUND", (6, r_i), (7, r_i), col_rc))
        g_oscuro = colors.HexColor("#BDBDBD")
        g_claro = colors.HexColor("#E0E0E0")
        col_bd = g_oscuro if r_i % 2 == 1 else g_claro
        style_compa.append(("BACKGROUND", (8, r_i), (9, r_i), col_bd))
    t_jug.setStyle(TableStyle(style_compa))

    # ═════════════════════════════════════════════════════════════════
    # Tabla CÓRNERS horizontal:
    #   [CÓRNERS]  ← header SPAN todas las cols, centrado
    #   [VOLEA 1 | VOLEA 2 | 3-1 | 3-2 | CAPITÁN 1 | CAPITÁN 2 | CORTA]  ← centrado
    #   [        |         |     |     |           |           |       ]  ← celda escritura (izquierda)
    # ═════════════════════════════════════════════════════════════════
    n_corn = len(TIPOS_CORNERS)  # 7
    ancho_col_corn = 18.0*cm / n_corn  # ≈2.57cm
    rows_corn = [
        [Paragraph("CÓRNERS", p_th_corn)] + [""] * (n_corn - 1),
        [Paragraph(t, p_corn_tipo) for t in TIPOS_CORNERS],
        [""] * n_corn,  # fila para escribir
    ]
    t_corn = Table(rows_corn, colWidths=[ancho_col_corn] * n_corn,
                    rowHeights=[0.45*cm, 0.4*cm, 0.7*cm])
    t_corn.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("BACKGROUND", (0, 1), (-1, 1), GRIS_CLARO),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),    # título y header tipos centrados
        ("ALIGN", (0, 2), (-1, 2), "LEFT"),      # fila de escritura → izquierda
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        ("LEFTPADDING", (0, 2), (-1, 2), 4),
        ("RIGHTPADDING", (0, 2), (-1, 2), 2),
    ]))

    # ═════════════════════════════════════════════════════════════════
    # Tabla BANDAS horizontal (11 tipos)
    # ═════════════════════════════════════════════════════════════════
    n_band = len(TIPOS_BANDAS)  # 11
    ancho_col_band = 18.0*cm / n_band  # ≈1.64cm
    rows_band = [
        [Paragraph("BANDAS", p_th_corn)] + [""] * (n_band - 1),
        [Paragraph(t, p_corn_tipo) for t in TIPOS_BANDAS],
        [""] * n_band,
    ]
    t_band = Table(rows_band, colWidths=[ancho_col_band] * n_band,
                    rowHeights=[0.45*cm, 0.4*cm, 0.7*cm])
    t_band.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("BACKGROUND", (0, 1), (-1, 1), GRIS_CLARO),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (0, 2), (-1, 2), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        ("LEFTPADDING", (0, 2), (-1, 2), 4),
        ("RIGHTPADDING", (0, 2), (-1, 2), 2),
    ]))

    # ═════════════════════════════════════════════════════════════════
    # Empaquetar en una tabla externa con mini-título
    # ═════════════════════════════════════════════════════════════════
    bloque = Table([
        [Paragraph(f"<b>{titulo_parte}</b>", p_titulo_parte)],
        [t_jug],
        [Spacer(1, 3)],
        [t_corn],
        [Spacer(1, 2)],
        [t_band],
    ], colWidths=[18.02*cm])
    bloque.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return bloque


def _planilla_compa(jugadores) -> list:
    """Planilla del compañero — A4 VERTICAL · UNA HOJA con 1ª y 2ª parte
    apiladas. Cabecera común arriba (la pone generar_planilla)."""
    bloque_1 = _bloque_parte_compa(jugadores, "1ª PARTE")
    bloque_2 = _bloque_parte_compa(jugadores, "2ª PARTE")
    return [
        bloque_1,
        Spacer(1, 8),
        bloque_2,
    ]


# ─── Generador principal ────────────────────────────────────────────────────
def generar_planilla(modo: str, parte: str,
                       partido_id: Optional[str] = None,
                       sh=None,
                       datos_directos: Optional[dict] = None) -> bytes:
    """Genera el PDF en memoria.

    modo: 'arkaitz' o 'compa'.
    parte: '1T' o '2T' (cambia el sentido del campo en planilla arkaitz).
    partido_id: opcional. Si se da, pre-rellena cabecera y plantilla
                leyendo de Google Sheets.
    sh: opcional, gspread Spreadsheet ya abierto.
    datos_directos: opcional, dict con keys {rival, fecha, lugar, hora,
                    competicion, local_visitante, jugadores: [{dorsal,
                    jugador, posicion}, ...]}. Si se pasa, IGNORA
                    partido_id y sh (usado para generar antes de guardar
                    desde el form).
    """
    assert modo in ("arkaitz", "compa"), f"modo desconocido: {modo}"
    assert parte in ("1T", "2T"), f"parte desconocida: {parte}"

    if datos_directos is not None:
        # Datos pasados directamente del form (no leemos Sheet)
        datos = {
            "rival": datos_directos.get("rival", ""),
            "fecha": datos_directos.get("fecha", ""),
            "lugar": datos_directos.get("lugar", ""),
            "hora": datos_directos.get("hora", ""),
            "competicion": datos_directos.get("competicion", ""),
            "local_visitante": datos_directos.get("local_visitante", ""),
            "jugadores": list(datos_directos.get("jugadores", [])),
        }
    elif partido_id:
        if sh is None:
            sh = _connect()
        datos = _datos_partido(sh, partido_id)
    else:
        datos = {"rival": "", "fecha": "", "lugar": "", "hora": "",
                 "competicion": "", "local_visitante": "", "jugadores": []}

    parte_label = "1ª PARTE" if parte == "1T" else "2ª PARTE"

    # Buffer del PDF. Ahora AMBOS modos son A4 VERTICAL:
    #   - arkaitz: 1 PDF por parte (1T y 2T separadas, con su mapa).
    #   - compa:   1 ÚNICO PDF con las dos partes apiladas (parte se ignora).
    buf = io.BytesIO()
    pagesize = A4
    titulo = (f"Planilla {modo} {parte}"
              if modo == "arkaitz" else f"Planilla {modo}")
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        leftMargin=0.7*cm, rightMargin=0.7*cm,
        topMargin=0.7*cm, bottomMargin=0.7*cm,
        title=titulo,
    )

    story = []
    story.append(_cabecera(datos, parte_label, modo=modo))
    story.append(Spacer(1, 5))

    if modo == "arkaitz":
        # Mapas según parte: 1T = Inter ataca derecha (campo_der.png)
        # 2T = Inter ataca izquierda (campo_izq.png)
        if parte == "1T":
            mapa_inter = PLANILLA / "campo_der.png"
            mapa_rival = PLANILLA / "campo_izq.png"
        else:
            mapa_inter = PLANILLA / "campo_izq.png"
            mapa_rival = PLANILLA / "campo_der.png"
        img_porteria = PLANILLA / "porteria.png"
        story.extend(_planilla_arkaitz(
            datos["jugadores"], parte_label,
            mapa_inter, mapa_rival, img_porteria,
        ))
    else:  # compa — vertical con 1ª y 2ª parte en la misma hoja
        story.extend(_planilla_compa(datos["jugadores"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["arkaitz", "compa"], default="arkaitz")
    ap.add_argument("--parte", choices=["1T", "2T"], default="1T")
    ap.add_argument("--partido", default="",
                     help="Partido_id para pre-rellenar cabecera y plantilla.")
    ap.add_argument("--salida", default="",
                     help="Ruta donde guardar el PDF (sin esto, stdout).")
    args = ap.parse_args()

    pdf = generar_planilla(args.modo, args.parte, args.partido or None)
    if args.salida:
        Path(args.salida).write_bytes(pdf)
        print(f"✅ PDF generado: {args.salida} ({len(pdf):,} bytes)",
              file=sys.stderr)
    else:
        sys.stdout.buffer.write(pdf)


if __name__ == "__main__":
    main()
