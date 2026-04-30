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


def _cabecera(datos: dict, parte_label: str, ancho_cm: float = 27.0) -> Table:
    """Tabla de cabecera: [logo Inter] [PARTIDO ... vs ... · COMP · LUGAR ·
    FECHA · HORA · 1ª/2ª] [logo dorado]."""
    styles = getSampleStyleSheet()
    p_lbl = ParagraphStyle("lbl", parent=styles["BodyText"], fontSize=8,
                             textColor=GRIS, alignment=1, leading=10)
    p_val = ParagraphStyle("val", parent=styles["BodyText"], fontSize=11,
                             textColor=AZUL, alignment=1, leading=13,
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

    # Decidir orden por local/visitante (si Inter es visitante, rival a la izda)
    lv = (datos.get("local_visitante") or "").upper()
    if lv == "VISITANTE":
        izq, dcha = rival, "MOVISTAR INTER"
    else:
        izq, dcha = "MOVISTAR INTER", rival

    info = [
        [Paragraph("PARTIDO", p_lbl),
         Paragraph("CATEGORÍA", p_lbl),
         Paragraph("LUGAR", p_lbl),
         Paragraph("FECHA", p_lbl),
         Paragraph("HORA", p_lbl),
         Paragraph("PARTE", p_lbl)],
        [Paragraph(f"<b>{izq}</b>&nbsp;vs&nbsp;<b>{dcha}</b>", p_val),
         Paragraph(competicion, p_val),
         Paragraph(lugar, p_val),
         Paragraph(fecha_fmt, p_val),
         Paragraph(hora, p_val),
         Paragraph(f"<b>{parte_label}</b>", p_val)],
    ]
    t_info = Table(info,
                    colWidths=[6.5*cm, 4.0*cm, 4.0*cm, 3.0*cm, 2.0*cm, 1.6*cm],
                    rowHeights=[0.55*cm, 0.85*cm])
    t_info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("BACKGROUND", (0, 1), (-1, 1), GRIS_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    cab = Table(
        [[_logo(LOGOS / "inter_verde.png", 1.7, 1.6),
          t_info,
          _logo(LOGOS / "inter_dorado.png", 1.7, 1.6)]],
        colWidths=[1.9*cm, 21.1*cm, 1.9*cm],
    )
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return cab


# ─── Planilla "Arkaitz" ─────────────────────────────────────────────────────
def _planilla_arkaitz(jugadores, parte_label, mapa_inter, mapa_rival,
                       img_porteria) -> list:
    """Devuelve lista de Flowables para la planilla de Arkaitz."""
    styles = getSampleStyleSheet()
    p_th = ParagraphStyle("th", parent=styles["BodyText"], fontSize=7,
                            textColor=colors.white, alignment=1, leading=9,
                            fontName="Helvetica-Bold")
    p_td = ParagraphStyle("td", parent=styles["BodyText"], fontSize=8,
                            textColor=AZUL, alignment=0, leading=10)

    # ── Tabla de jugadores (NUM | JUG | T.A | ROJ | DP | DPalo | DB | DF
    #    | FUERA | POSTE | BLOQUEADO | PARADA | GOL)
    cabeceras = ["Nº", "JUGADOR", "T.A", "ROJ",
                 "DP", "DPalo", "DB", "DF",
                 "FUERA", "POSTE", "BLOQ.", "PARADA", "GOL"]
    rows = [[Paragraph(c, p_th) for c in cabeceras]]
    # 14 filas (rellenas las que tengamos, vacías el resto)
    for i in range(14):
        if i < len(jugadores):
            j = jugadores[i]
            d = str(j["dorsal"]) if j["dorsal"] is not None else ""
            n = j["jugador"]
        else:
            d, n = "", ""
        rows.append([d, n, "", "", "", "", "", "", "", "", "", "", ""])
    anchos = [0.7*cm, 2.6*cm] + [0.95*cm]*4 + [1.15*cm]*5 + [1.0*cm]*2
    t_jug = Table(rows, colWidths=anchos,
                   rowHeights=[0.55*cm] + [0.5*cm]*14)
    t_jug.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        # Distinguir grupo "campo" (cols 4-7) de "portería" (cols 8-12)
        ("BACKGROUND", (8, 0), (12, 0), colors.HexColor("#7F1010")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    # ── Tabla de goles (10 filas vacías)
    rows_goles = [[Paragraph(c, p_th) for c in
                    ["EQUIPO", "Nº", "RESULTADO", "MIN", "ASIST", "ACCIÓN", "ROTACIÓN"]]]
    for _ in range(10):
        rows_goles.append(["", "", "", "", "", "", ""])
    t_goles = Table(rows_goles,
                     colWidths=[1.5*cm, 0.8*cm, 1.6*cm, 1.0*cm, 1.5*cm, 2.5*cm, 2.0*cm],
                     rowHeights=[0.55*cm] + [0.45*cm]*10)
    t_goles.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))

    # ── Tabla de faltas (Inter): Nº · TIEMPO · JUG. — 6 filas
    def _tabla_faltas(titulo, color_titulo):
        h = [[Paragraph(titulo, p_th)] * 3]
        h.append([Paragraph("Nº", p_th), Paragraph("TIEMPO", p_th),
                   Paragraph("JUG.", p_th)])
        for i in range(1, 7):
            h.append([str(i), "", ""])
        t = Table(h, colWidths=[0.8*cm, 1.4*cm, 1.6*cm],
                   rowHeights=[0.4*cm, 0.4*cm] + [0.4*cm]*6)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), color_titulo),
            ("BACKGROUND", (0, 1), (-1, 1), AZUL),
            ("SPAN", (0, 0), (-1, 0)),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        return t

    t_faltas_inter = _tabla_faltas("FALTAS · MOVISTAR INTER (TM:____)", VERDE)
    t_faltas_rival = _tabla_faltas("FALTAS · RIVAL (TM:____)", ROJO)

    # ── Mapas de campo (Inter borde verde, rival borde rojo)
    img_inter = _logo(mapa_inter, 9.5, 4.8) if mapa_inter and mapa_inter.exists() else Paragraph("(falta mapa)", p_td)
    img_rival = _logo(mapa_rival, 9.5, 4.8) if mapa_rival and mapa_rival.exists() else Paragraph("(falta mapa)", p_td)
    img_port_af = _logo(img_porteria, 3.0, 2.0) if img_porteria and img_porteria.exists() else Paragraph("", p_td)
    img_port_ec = _logo(img_porteria, 3.0, 2.0) if img_porteria and img_porteria.exists() else Paragraph("", p_td)

    # ── Layout principal: 2 columnas
    # Columna izquierda: Tabla jugadores arriba + mapa Inter + porteria AF + faltas Inter
    # Columna derecha: Tabla goles + mapa rival + porteria EC + faltas rival

    # Bloque de mapas+porteria+faltas: 3 sub-elementos lado a lado por equipo
    def _bloque_mapa(titulo, color, img_campo, img_port, t_faltas):
        """Devuelve un mini-Table con: título + (mapa | porteria | faltas)."""
        styles = getSampleStyleSheet()
        p_titulo = ParagraphStyle("blq_t", parent=styles["BodyText"],
                                    fontSize=9, fontName="Helvetica-Bold",
                                    textColor=color, alignment=0)
        return Table([
            [Paragraph(titulo, p_titulo)],
            [Table([[img_campo, img_port, t_faltas]],
                    colWidths=[10*cm, 3.4*cm, 4.0*cm])],
        ], colWidths=[17.4*cm])

    bloque_inter = _bloque_mapa(
        "⚽ DISPAROS / GOLES A FAVOR · ataca: " + parte_label,
        VERDE, img_inter, img_port_af, t_faltas_inter)
    bloque_rival = _bloque_mapa(
        "🥅 DISPAROS / GOLES EN CONTRA · ataca rival",
        ROJO, img_rival, img_port_ec, t_faltas_rival)

    flowables = [
        t_jug,
        Spacer(1, 6),
        # Tabla goles + leyenda
        Table([[t_goles, Paragraph(
            "<b>Leyenda:</b><br/>"
            "▢ DISPARO FUERA<br/>"
            "△ DISPARO A PUERTA<br/>"
            "● GOL<br/><br/>"
            "<b>RESULTADO</b>: marcador en el gol (ej. 2-1)<br/>"
            "<b>ROTACIÓN</b>: nº de la rotación cuando ocurre",
            ParagraphStyle("ley", parent=styles["BodyText"], fontSize=7,
                            leading=10, textColor=GRIS))]],
            colWidths=[12.0*cm, 6.0*cm])
        ,
        Spacer(1, 6),
        bloque_inter,
        Spacer(1, 4),
        bloque_rival,
    ]
    return flowables


# ─── Planilla "Compañero" (ALEX) ────────────────────────────────────────────
def _planilla_compa(jugadores, parte_label) -> list:
    """Tabla de acciones individuales por jugador + tabla córners + bandas."""
    styles = getSampleStyleSheet()
    p_th = ParagraphStyle("th", parent=styles["BodyText"], fontSize=8,
                            textColor=colors.white, alignment=1,
                            fontName="Helvetica-Bold")

    cabeceras = ["Nº", "JUGADOR", "T.A", "ROJ",
                 "PF", "PNF", "ROBOS", "CORTES", "BDG", "BDP"]
    rows = [[Paragraph(c, p_th) for c in cabeceras]]
    for i in range(14):
        if i < len(jugadores):
            j = jugadores[i]
            d = str(j["dorsal"]) if j["dorsal"] is not None else ""
            n = j["jugador"]
        else:
            d, n = "", ""
        rows.append([d, n] + [""] * 8)
    anchos = [1.0*cm, 3.5*cm] + [1.4*cm]*8
    t_jug = Table(rows, colWidths=anchos,
                   rowHeights=[0.7*cm] + [0.95*cm]*14)
    t_jug.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))

    # Tabla CÓRNERS (tipos × cuenta)
    rows_corn = [[Paragraph("CÓRNERS", p_th), Paragraph("Nº", p_th)]]
    for t in TIPOS_CORNERS:
        rows_corn.append([t, ""])
    t_corn = Table(rows_corn, colWidths=[3.0*cm, 1.5*cm],
                    rowHeights=[0.6*cm] + [0.7*cm]*len(TIPOS_CORNERS))
    t_corn.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))

    rows_band = [[Paragraph("BANDAS", p_th), Paragraph("Nº", p_th)]]
    for t in TIPOS_BANDAS:
        rows_band.append([t, ""])
    t_band = Table(rows_band, colWidths=[3.0*cm, 1.5*cm],
                    rowHeights=[0.6*cm] + [0.7*cm]*len(TIPOS_BANDAS))
    t_band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))

    # Layout: tabla jugadores izda + (córners arriba, bandas abajo) dcha
    layout = Table([
        [t_jug, Table([[t_corn], [Spacer(1, 4)], [t_band]],
                       colWidths=[5.0*cm])],
    ], colWidths=[19.0*cm, 5.5*cm])
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    return [layout]


# ─── Generador principal ────────────────────────────────────────────────────
def generar_planilla(modo: str, parte: str,
                       partido_id: Optional[str] = None,
                       sh=None) -> bytes:
    """Genera el PDF en memoria.

    modo: 'arkaitz' o 'compa'.
    parte: '1T' o '2T' (cambia el sentido del campo en planilla arkaitz).
    partido_id: opcional. Si se da, pre-rellena cabecera y plantilla.
    sh: opcional, gspread Spreadsheet ya abierto. Si None se conecta.
    """
    assert modo in ("arkaitz", "compa"), f"modo desconocido: {modo}"
    assert parte in ("1T", "2T"), f"parte desconocida: {parte}"

    if partido_id:
        if sh is None:
            sh = _connect()
        datos = _datos_partido(sh, partido_id)
    else:
        datos = {"rival": "", "fecha": "", "lugar": "", "hora": "",
                 "competicion": "", "local_visitante": "", "jugadores": []}

    parte_label = "1ª PARTE" if parte == "1T" else "2ª PARTE"

    # Buffer del PDF
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=0.7*cm, rightMargin=0.7*cm,
        topMargin=0.7*cm, bottomMargin=0.7*cm,
        title=f"Planilla {modo} {parte}",
    )

    story = []
    story.append(_cabecera(datos, parte_label))
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
