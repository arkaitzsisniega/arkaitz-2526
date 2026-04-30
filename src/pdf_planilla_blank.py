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
from reportlab.lib.pagesizes import A4, landscape
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
def _logo(path: Path, w_cm: float, h_cm: float):
    """Devuelve una RLImage si el path existe; si no, un placeholder vacío."""
    if path.exists():
        try:
            img = RLImage(str(path), width=w_cm * cm, height=h_cm * cm,
                            kind="proportional")
            img.hAlign = "CENTER"
            return img
        except Exception:
            pass
    return Paragraph("", ParagraphStyle("blank"))


def _cabecera(datos: dict, parte_label: str, modo: str = "arkaitz") -> Table:
    """Cabecera estilo Excel original. Layout:
        [logo Inter] PARTIDO: MOVISTAR INTER vs RIVAL    COMPETICIÓN: ___    [logo Movistar]
                    LUGAR: ___          FECHA: ___      HORA: ___           PARTE: 1ª

    Adaptable al ancho disponible:
      - modo='arkaitz': A4 VERTICAL → ancho útil ~19.6cm
      - modo='compa':   A4 HORIZONTAL → ancho útil ~28cm
    """
    styles = getSampleStyleSheet()
    p_lbl = ParagraphStyle("lbl", parent=styles["BodyText"], fontSize=9,
                             textColor=colors.black, alignment=0, leading=11,
                             fontName="Helvetica")
    p_val = ParagraphStyle("val", parent=styles["BodyText"], fontSize=10,
                             textColor=colors.black, alignment=0, leading=12,
                             fontName="Helvetica-Bold")
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

    # Layout 2 filas, similar al original:
    #   F1: PARTIDO: MOVISTAR INTER  vs  RIVAL          | COMPETICIÓN: ___
    #   F2: LUGAR: ___       FECHA: ___      HORA: ___  | PARTE: 1ª
    info = [
        [Paragraph("<b>PARTIDO:</b>", p_lbl),
         Paragraph(f"<b>MOVISTAR INTER</b>", p_val),
         Paragraph("<b>VS</b>", p_lbl),
         Paragraph(f"<b>{rival}</b>", p_val),
         Paragraph("<b>COMPETICIÓN:</b>", p_lbl),
         Paragraph(competicion, p_val)],
        [Paragraph("<b>LUGAR:</b>", p_lbl),
         Paragraph(lugar, p_val),
         Paragraph("<b>FECHA:</b>", p_lbl),
         Paragraph(fecha_fmt, p_val),
         Paragraph("<b>HORA:</b>", p_lbl),
         Paragraph(f"{hora}    <b>PARTE:</b> {parte_label}", p_val)],
    ]
    # Anchos según modo
    if modo == "arkaitz":
        # A4 vertical: 19cm útiles → cabecera ocupa 16cm (resto logos)
        col_widths = [1.6*cm, 3.0*cm, 0.8*cm, 3.2*cm, 2.4*cm, 5.0*cm]
        ancho_logo = 1.5*cm
        ancho_total = 19.0*cm
    else:
        # A4 horizontal: 28cm útiles → cabecera 25cm
        col_widths = [2.0*cm, 4.5*cm, 1.0*cm, 5.0*cm, 3.0*cm, 9.5*cm]
        ancho_logo = 1.8*cm
        ancho_total = 28.5*cm

    t_info = Table(info, colWidths=col_widths,
                    rowHeights=[0.55*cm, 0.55*cm])
    t_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))

    centro_w = ancho_total - 2 * ancho_logo
    cab = Table(
        [[_logo(LOGOS / "inter_verde.png", ancho_logo / cm * 0.8,
                  1.5),
          t_info,
          _logo(LOGOS / "inter_dorado.png", ancho_logo / cm * 0.8,
                  1.5)]],
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
                              textColor=colors.HexColor("#777"),
                              fontName="Helvetica-Oblique")

    # ═════════════════════════════════════════════════════════════════
    # 1) TABLA DE JUGADORES
    # 13 cols: NUM | JUGADOR | T.A | ROJ | DP | DPalo | DB | DF
    #        | FUERA | POSTE | BLOQUEADO | PARADA | GOL
    # Anchos para 19cm útil:
    # NUM(0.7) JUG(2.6) TA(0.7) ROJ(0.7) DP(0.9) DPalo(1.0) DB(0.9) DF(0.9) | FUERA(2.0) POSTE(2.0) BLOQ(2.5) PARADA(2.0) GOL(1.6)
    # Total: 0.7+2.6+0.7+0.7+0.9+1.0+0.9+0.9 + 2.0+2.0+2.5+2.0+1.6 = 18.5cm
    # ═════════════════════════════════════════════════════════════════
    cabeceras = ["NUM", "JUGADOR", "T.A", "ROJ",
                 "DP", "D.PALO", "DB", "DF",
                 "FUERA", "POSTE", "BLOQUEADO", "PARADA", "GOL"]
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

    # A4 vertical útil ~19cm
    # NUM(0.65) JUG(2.5) TA(0.6) ROJ(0.6) DP(0.85) DPalo(0.95) DB(0.85) DF(0.85)
    # FUERA(2.0) POSTE(2.1) BLOQ(2.5) PARADA(2.0) GOL(1.65) = 18.1cm
    anchos_jug = [0.65*cm, 2.5*cm, 0.6*cm, 0.6*cm,
                   0.85*cm, 0.95*cm, 0.85*cm, 0.85*cm,
                   2.0*cm, 2.1*cm, 2.5*cm, 2.0*cm, 1.65*cm]
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
    bloques_no_p = []
    if no_p:
        ini = no_p[0]; prev = ini
        for i in no_p[1:]:
            if i == prev + 1:
                prev = i
            else:
                bloques_no_p.append((ini, prev)); ini = i; prev = i
        bloques_no_p.append((ini, prev))
    # En el original, el bloque grande tiene texto "DISPAROS DEL PORTERO CONTRARIO"
    # arriba. Hago un solo gran rectángulo (8..12) × bloque entero, con título.
    for (ini, fin) in bloques_no_p:
        if fin - ini >= 0:
            style_jug.append(("SPAN", (8, ini), (12, fin)))
            style_jug.append(("BACKGROUND", (8, ini), (12, fin), colors.white))
            # Texto central
            rows[ini][8] = Paragraph(
                "<b>DISPAROS DEL PORTERO<br/>CONTRARIO</b>", p_nota)

    t_jug = Table(rows, colWidths=anchos_jug, rowHeights=rh_jug)
    t_jug.setStyle(TableStyle(style_jug))

    # ═════════════════════════════════════════════════════════════════
    # 2) TABLA DE GOLES (10 filas, ancho completo ~19cm)
    # Cols: EQUIPO(1.6) Nº JUG(1.0) RESULTADO(1.6) MIN(1.0) ASIST(2.4) ACCIÓN(8.6) ROTACIÓN(2.8)
    # Total: 1.6+1.0+1.6+1.0+2.4+8.6+2.8 = 19cm
    # ═════════════════════════════════════════════════════════════════
    cabeceras_g = ["EQUIPO", "Nº JUG", "RESULTADO", "MIN", "ASIST",
                    "ACCIÓN", "ROTACIÓN"]
    rows_g = [[Paragraph(c, p_th_dark) for c in cabeceras_g]]
    for _ in range(10):
        rows_g.append([""] * 7)
    # Total 18.1cm (mismo ancho que tabla jugadores)
    anchos_g = [1.6*cm, 1.0*cm, 1.6*cm, 1.0*cm, 2.4*cm, 8.0*cm, 2.5*cm]
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
                          colWidths=[18.1*cm], rowHeights=[0.42*cm])
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
    # A4 vertical útil 19cm. Bloque: portería(4cm) + mapa(9cm) + faltas(4cm) = 17cm
    # Altura: 4.2cm cada uno
    img_inter = _logo(mapa_inter, 9.0, 4.2) if mapa_inter and mapa_inter.exists() else Paragraph("", p_th)
    img_rival = _logo(mapa_rival, 9.0, 4.2) if mapa_rival and mapa_rival.exists() else Paragraph("", p_th)
    # Portería: alto = ancho del campo (~4cm), ancho ajustado al ratio 311:204 → 4×1.52 = 6.1cm. Más realista 4×0.5 = 2cm
    # En el original se ve la portería bastante alta. Dimensiones 4×4 cm (cuadrada).
    img_port_af = _logo(img_porteria, 4.0, 4.2) if img_porteria and img_porteria.exists() else Paragraph("", p_th)
    img_port_ec = _logo(img_porteria, 4.0, 4.2) if img_porteria and img_porteria.exists() else Paragraph("", p_th)

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

    # Mapa con borde verde (Inter) o rojo (rival): los PNG ya lo traen.
    # Layout: portería (4cm) | mapa (9cm) | tabla faltas (4cm). Total 17cm.
    # Altura del bloque: 4.5cm
    bloque_af = Table([
        [Paragraph("DISPAROS / GOLES A FAVOR", p_tit_af)],
        [Table([[img_port_af, img_inter, t_faltas_inter]],
                colWidths=[4.0*cm, 9.0*cm, 4.0*cm],
                rowHeights=[4.5*cm])],
    ], colWidths=[17.0*cm])
    bloque_af.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    bloque_ec = Table([
        [Paragraph("DISPAROS / GOLES EN CONTRA", p_tit_ec)],
        [Table([[img_port_ec, img_rival, t_faltas_rival]],
                colWidths=[4.0*cm, 9.0*cm, 4.0*cm],
                rowHeights=[4.5*cm])],
    ], colWidths=[17.0*cm])
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


# ─── Planilla "Compañero" (ALEX) — A4 horizontal ────────────────────────────
def _planilla_compa(jugadores, parte_label) -> list:
    """Tabla de jugadores con métricas individuales + tablas Córners y
    Bandas a la derecha. Colores fieles al Excel original:
       T.A amarillo, ROJ rojo, PF/PNF naranja claro, ROBOS/CORTES verde
       claro, BDG/BDP gris claro. Filas alternas con tono más oscuro."""
    styles = getSampleStyleSheet()
    p_th_dark = ParagraphStyle("th_d", parent=styles["BodyText"], fontSize=9,
                                  textColor=colors.black, alignment=1,
                                  fontName="Helvetica-Bold", leading=11)
    p_corn = ParagraphStyle("corn", parent=styles["BodyText"], fontSize=14,
                              textColor=colors.black, alignment=1,
                              fontName="Helvetica-Bold", leading=16)

    # ── Tabla principal: Nº | JUGADOR | T.A | ROJ | PF | PNF | ROBOS | CORTES | BDG | BDP
    cabeceras = ["NUM", "JUGADOR", "T.A", "ROJ",
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

    anchos = [1.2*cm, 3.5*cm, 1.5*cm, 1.5*cm,
              1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm]
    h_h = 0.7*cm
    h_f = 0.65*cm
    rh = [h_h] + [h_f]*14 + [h_h]
    t_jug = Table(rows, colWidths=anchos, rowHeights=rh)

    # Estilos
    style_compa = [
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        # Header amarillo en T.A, rojo en ROJ
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FFEB3B")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#D32F2F")),
        ("TEXTCOLOR", (3, 0), (3, 0), colors.white),
        # Header gris claro en el resto
        ("BACKGROUND", (0, 0), (1, 0), GRIS_CLARO),
        ("BACKGROUND", (4, 0), (-1, 0), GRIS_CLARO),
        # Última fila EQUIPO en gris claro
        ("BACKGROUND", (0, -1), (-1, -1), GRIS_CLARO),
        # SPAN para EQUIPO en cols 0-1
        ("SPAN", (0, -1), (1, -1)),
    ]
    # Fondo amarillo para columna T.A (filas datos)
    for r_i in range(1, 16):  # 14 filas + EQUIPO
        style_compa.append(("BACKGROUND", (2, r_i), (2, r_i),
                              colors.HexColor("#FFF59D")))
        style_compa.append(("BACKGROUND", (3, r_i), (3, r_i),
                              colors.HexColor("#FF5252")))
        # PF/PNF naranja claro alternando
        n_oscuro = colors.HexColor("#FFAB91")  # naranja medio
        n_claro = colors.HexColor("#FFCCBC")   # naranja muy claro
        col_pfpnf = n_oscuro if r_i % 2 == 1 else n_claro
        style_compa.append(("BACKGROUND", (4, r_i), (5, r_i), col_pfpnf))
        # ROBOS/CORTES verde claro alternando
        v_oscuro = colors.HexColor("#A5D6A7")
        v_claro = colors.HexColor("#C8E6C9")
        col_rc = v_oscuro if r_i % 2 == 1 else v_claro
        style_compa.append(("BACKGROUND", (6, r_i), (7, r_i), col_rc))
        # BDG/BDP gris alternando
        g_oscuro = colors.HexColor("#BDBDBD")
        g_claro = colors.HexColor("#E0E0E0")
        col_bd = g_oscuro if r_i % 2 == 1 else g_claro
        style_compa.append(("BACKGROUND", (8, r_i), (9, r_i), col_bd))
    t_jug.setStyle(TableStyle(style_compa))

    # ── Tablas CÓRNERS y BANDAS a la derecha ──────────────────────
    # Estilo: header negro grande, filas grandes con texto centrado
    rows_corn = [[Paragraph("CÓRNERS", p_corn)]]
    for t in TIPOS_CORNERS:
        rows_corn.append([t])
    t_corn = Table(rows_corn, colWidths=[4.5*cm],
                    rowHeights=[1.0*cm] + [0.8*cm]*len(TIPOS_CORNERS))
    t_corn.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
    ]))

    rows_band = [[Paragraph("BANDAS", p_corn)]]
    for t in TIPOS_BANDAS:
        rows_band.append([t])
    t_band = Table(rows_band, colWidths=[4.5*cm],
                    rowHeights=[1.0*cm] + [0.8*cm]*len(TIPOS_BANDAS))
    t_band.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
    ]))

    # Layout horizontal: tabla jug | córners | bandas
    layout = Table([
        [t_jug, t_corn, t_band],
    ], colWidths=[18.0*cm, 4.7*cm, 4.7*cm])
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    return [layout]


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

    # Buffer del PDF. Orientación según modo:
    #   - arkaitz: A4 VERTICAL (fiel al Excel original)
    #   - compa:   A4 HORIZONTAL
    buf = io.BytesIO()
    pagesize = A4 if modo == "arkaitz" else landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        leftMargin=0.7*cm, rightMargin=0.7*cm,
        topMargin=0.7*cm, bottomMargin=0.7*cm,
        title=f"Planilla {modo} {parte}",
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
    else:  # compa
        story.extend(_planilla_compa(datos["jugadores"], parte_label))

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
