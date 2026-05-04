"""
pdf_instrucciones_fisios.py — Genera un PDF para los fisios con
instrucciones de cómo rellenar el Sheet de Lesiones, Tratamientos y
Temperatura, incluyendo TODAS las opciones de cada dropdown.

Uso:
  /usr/bin/python3 src/pdf_instrucciones_fisios.py [--salida ruta.pdf]

Salida por defecto: PDFs_J28_JAEN/instrucciones_fisios.pdf
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Importar las constantes del script de creación
from crear_sheet_fisios import (  # noqa: E402
    TURNOS, LADOS, SI_NO, TIPOS_SESION, ZONAS_CORPORALES, TIPOS_TEJIDO,
    MECANISMOS, GRAVEDADES, ESTADOS_LESION, PRUEBAS_MEDICAS,
    BLOQUES_TRATAMIENTO, ACCIONES_TRATAMIENTO, FISIOS,
    MOMENTOS_TERMICOS, ZONAS_TERMICAS,
    COLS_LESIONES, COLS_TRATAMIENTOS, COLS_TEMPERATURA,
)

AZUL = colors.HexColor("#1B3A6B")
ROJO = colors.HexColor("#B71C1C")
VERDE = colors.HexColor("#1B5E20")
NARANJA = colors.HexColor("#E65100")
GRIS_CLARO = colors.HexColor("#F5F5F5")
GRIS = colors.HexColor("#666666")

# Etiquetas humanas para cada validación
LABEL_VAL = {
    "TURNOS": "M / T / P",
    "LADOS": " / ".join(LADOS),
    "SI_NO": " / ".join(SI_NO),
    "TIPOS_SESION": "Lista de tipos de sesión (ENTRENO, PARTIDO…)",
    "ZONAS_CORPORALES": "Lista de zonas corporales",
    "TIPOS_TEJIDO": "Lista de tipos de tejido",
    "MECANISMOS": "Lista de mecanismos de lesión",
    "GRAVEDADES": " / ".join(GRAVEDADES),
    "ESTADOS_LESION": " / ".join(ESTADOS_LESION),
    "PRUEBAS_MEDICAS": " / ".join(PRUEBAS_MEDICAS),
    "BLOQUES_TRATAMIENTO": " / ".join(BLOQUES_TRATAMIENTO),
    "ACCIONES_TRATAMIENTO": "Lista de acciones de tratamiento",
    "FISIOS": " / ".join(FISIOS),
    "MOMENTOS_TERMICOS": "Lista de momentos para medir temperatura",
    "ZONAS_TERMICAS": "Lista de zonas térmicas",
    "JUGADOR": "Lista del roster (selecciona del dropdown)",
    "FECHA": "Fecha (formato AAAA-MM-DD)",
    "NUMERO": "Número (decimal con punto)",
}

# Listas que merece la pena listar EN PLENO en una sección aparte
LISTAS_DETALLADAS = [
    ("ZONAS CORPORALES", ZONAS_CORPORALES),
    ("TIPOS DE TEJIDO / LESIÓN", TIPOS_TEJIDO),
    ("MECANISMOS", MECANISMOS),
    ("ACCIONES DE TRATAMIENTO", ACCIONES_TRATAMIENTO),
    ("ZONAS TÉRMICAS (cámara)", ZONAS_TERMICAS),
    ("MOMENTOS TÉRMICOS", MOMENTOS_TERMICOS),
    ("TIPOS DE SESIÓN", TIPOS_SESION),
    ("PRUEBAS MÉDICAS", PRUEBAS_MEDICAS),
]


def _tabla_columnas(cols, titulo: str, color):
    """Construye una tabla con (nombre_columna, opciones)."""
    styles = getSampleStyleSheet()
    p_titulo = ParagraphStyle(
        "tit_seccion", parent=styles["BodyText"], fontSize=14,
        fontName="Helvetica-Bold", textColor=color,
        spaceAfter=8, alignment=0, leading=16,
    )
    p_cell = ParagraphStyle(
        "cell", parent=styles["BodyText"], fontSize=8.5, leading=11,
    )
    p_cell_b = ParagraphStyle(
        "cell_b", parent=styles["BodyText"], fontSize=8.5, leading=11,
        fontName="Helvetica-Bold",
    )
    p_th = ParagraphStyle(
        "th", parent=styles["BodyText"], fontSize=9,
        fontName="Helvetica-Bold", textColor=colors.white, alignment=1, leading=11,
    )

    rows = [[
        Paragraph("CAMPO", p_th),
        Paragraph("CÓMO SE RELLENA", p_th),
        Paragraph("OPCIONES / NOTAS", p_th),
    ]]
    for col_name, val in cols:
        if val is None:
            como = "Texto libre / auto"
            opciones = ("AUTO" if "id_" in col_name or col_name in (
                "dorsal", "asimetria_c", "alerta", "dias_baja_real",
                "diferencia_dias", "total_sesiones_perdidas",
                "entrenos_perdidos", "partidos_perdidos")
                        else "—")
        elif val == "JUGADOR":
            como = "Dropdown (roster)"
            opciones = "Selecciona del desplegable"
        elif val == "FECHA":
            como = "Fecha"
            opciones = "AAAA-MM-DD (ej. 2026-05-04)"
        elif val == "NUMERO":
            como = "Número"
            opciones = "Decimal con punto (ej. 33.5)"
        else:
            como = "Dropdown"
            opciones = LABEL_VAL.get(val, val)
        rows.append([
            Paragraph(f"<b>{col_name}</b>", p_cell_b),
            Paragraph(como, p_cell),
            Paragraph(opciones, p_cell),
        ])

    t = Table(rows, colWidths=[4.5*cm, 4.0*cm, 9.0*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph(titulo, p_titulo), t, Spacer(1, 14)]


def _tabla_lista(titulo: str, items: list[str]):
    """Tabla con una lista (en columnas) de opciones."""
    styles = getSampleStyleSheet()
    p_titulo = ParagraphStyle(
        "tit_lista", parent=styles["BodyText"], fontSize=11,
        fontName="Helvetica-Bold", textColor=AZUL, spaceAfter=4, leading=13,
    )
    p_cell = ParagraphStyle("cell_l", parent=styles["BodyText"], fontSize=8.5,
                              leading=11)
    # Repartir items en 4 columnas
    n_cols = 4
    n_filas = (len(items) + n_cols - 1) // n_cols
    matriz = [["" for _ in range(n_cols)] for _ in range(n_filas)]
    for idx, it in enumerate(items):
        f, c = idx % n_filas, idx // n_filas
        matriz[f][c] = it
    rows = [[Paragraph(c, p_cell) for c in fila] for fila in matriz]
    t = Table(rows, colWidths=[4.5*cm]*n_cols)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#E0E0E0")),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS),
    ]))
    return [Paragraph(titulo, p_titulo), t, Spacer(1, 8)]


def generar(salida: Path):
    styles = getSampleStyleSheet()
    p_h1 = ParagraphStyle(
        "h1", parent=styles["BodyText"], fontSize=20,
        fontName="Helvetica-Bold", textColor=AZUL, alignment=1, spaceAfter=4, leading=24,
    )
    p_h2 = ParagraphStyle(
        "h2", parent=styles["BodyText"], fontSize=12,
        textColor=GRIS, alignment=1, spaceAfter=14, leading=14,
    )
    p_intro = ParagraphStyle(
        "intro", parent=styles["BodyText"], fontSize=10, leading=14,
        spaceAfter=10, alignment=0,
    )
    p_h_seccion = ParagraphStyle(
        "h_sec", parent=styles["BodyText"], fontSize=14,
        fontName="Helvetica-Bold", textColor=AZUL,
        spaceAfter=6, leading=16,
    )

    doc = SimpleDocTemplate(
        str(salida), pagesize=A4,
        leftMargin=1.4*cm, rightMargin=1.4*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        title="Instrucciones para fisios",
    )

    story = []

    # Portada
    story.append(Paragraph("Hoja de Lesiones, Tratamientos y Temperatura", p_h1))
    story.append(Paragraph("Instrucciones para los fisios · Movistar Inter FS 25/26", p_h2))

    story.append(Paragraph(
        "Este documento explica cómo rellenar el Google Sheet "
        "<b>'Arkaitz - Lesiones y Tratamientos 2526'</b>. Hay 3 pestañas "
        "principales (LESIONES, TRATAMIENTOS, TEMPERATURA) que cubren todo "
        "el seguimiento médico-deportivo del equipo.",
        p_intro))
    story.append(Paragraph(
        "<b>Regla general:</b> casi todas las celdas tienen un "
        "<b>desplegable</b> con las opciones disponibles. Click en la celda "
        "→ aparece la flecha → eliges. Las únicas celdas de texto libre "
        "son: <i>diagnostico</i>, <i>notas</i> y similares.",
        p_intro))
    story.append(Paragraph(
        "Las columnas marcadas como <b>AUTO</b> NO se rellenan a mano: "
        "las calcula el sistema (días de baja real, sesiones perdidas, "
        "asimetría térmica, etc.). Si las rellenas a mano, se sobreescriben "
        "después.",
        p_intro))
    story.append(Spacer(1, 6))

    # Resumen de pestañas
    p_resumen = ParagraphStyle(
        "res", parent=styles["BodyText"], fontSize=10, leading=14,
    )
    resumen = Table([
        ["Pestaña", "Cuándo se rellena"],
        ["🔴 LESIONES",
         Paragraph("Cuando un jugador <b>se retira</b> de un entrenamiento "
                    "o partido y va a perderse sesiones.", p_resumen)],
        ["🟢 TRATAMIENTOS",
         Paragraph("Cada vez que un fisio aplica algo: "
                    "<b>PRE_ENTRENO</b> (vendajes, calentar...), "
                    "<b>POST_ENTRENO</b> (descargas...), "
                    "<b>LESIONADO</b> (tratamiento al jugador lesionado).", p_resumen)],
        ["🟠 TEMPERATURA",
         Paragraph("Cada medición con la <b>cámara térmica</b>. "
                    "El sistema calcula la asimetría y avisa si supera 0.5°C.", p_resumen)],
    ], colWidths=[3.8*cm, 13.7*cm])
    resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(resumen)
    story.append(Spacer(1, 18))

    # Sección 1: LESIONES
    story.append(PageBreak())
    story.extend(_tabla_columnas(
        COLS_LESIONES,
        "1. Pestaña 🔴 LESIONES",
        ROJO,
    ))

    # Sección 2: TRATAMIENTOS
    story.append(PageBreak())
    story.extend(_tabla_columnas(
        COLS_TRATAMIENTOS,
        "2. Pestaña 🟢 TRATAMIENTOS",
        VERDE,
    ))

    # Sección 3: TEMPERATURA
    story.append(PageBreak())
    story.extend(_tabla_columnas(
        COLS_TEMPERATURA,
        "3. Pestaña 🟠 TEMPERATURA",
        NARANJA,
    ))
    story.append(Paragraph(
        "<b>Importante TEMPERATURA:</b> una fila por (jugador, zona, momento). "
        "Si mides 6 zonas a un jugador antes del entreno, son 6 filas. "
        "El sistema calcula la asimetría (izda − dcha) y marca ALERTA si "
        "la diferencia es mayor de <b>0.5°C</b>.",
        p_intro))

    # Sección 4: Listas de opciones detalladas
    story.append(PageBreak())
    story.append(Paragraph("4. Listas de opciones (detalle)", p_h_seccion))
    story.append(Paragraph(
        "Estas son todas las opciones que aparecen en los desplegables, por "
        "si quieres consultarlas sin abrir el Sheet.", p_intro))
    for titulo, items in LISTAS_DETALLADAS:
        story.extend(_tabla_lista(titulo, items))

    # Sección final: tips
    story.append(PageBreak())
    story.append(Paragraph("5. Consejos prácticos", p_h_seccion))
    p_tip = ParagraphStyle(
        "tip", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=8,
    )
    tips = [
        "<b>Si tienes dudas con una opción</b>, mira la sección 4 de este "
        "documento (página anterior).",
        "<b>Una lesión = una fila</b> en LESIONES. Cuando se le da el alta, "
        "vuelves a la fila y rellenas <i>fecha_alta</i> y <i>recaida</i>. "
        "El sistema calcula los días reales y las sesiones perdidas solo.",
        "<b>Tratamientos: una fila por jugador × acción</b>. Si haces a "
        "Cecilio un masaje + un vendaje, son dos filas. El campo <i>bloque</i> "
        "(PRE_ENTRENO / POST_ENTRENO / LESIONADO) es CLAVE: indica el contexto.",
        "<b>Temperatura: si la asimetría es ≥0.5°C</b>, el sistema marca "
        "<i>alerta=ALERTA</i>. Mira los jugadores con alertas frecuentes — "
        "puede indicar sobrecarga o riesgo de lesión.",
        "<b>Si una opción del dropdown no encaja</b>, puedes escribir un "
        "valor diferente. Sheets te avisará pero lo permitirá.",
        "<b>Si tienes que añadir una opción nueva</b> (otro fisio, otra "
        "técnica de tratamiento), avísame y la añado al sistema.",
        "<b>NO toques las hojas ocultas</b> (_LISTAS, _META, _VISTA_*). "
        "Son datos internos del sistema.",
    ]
    for t in tips:
        story.append(Paragraph(f"• {t}", p_tip))

    doc.build(story)
    return salida


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", default="",
                     help="Ruta del PDF (default: PDFs_J28_JAEN/instrucciones_fisios.pdf)")
    args = ap.parse_args()
    salida = (Path(args.salida).resolve() if args.salida
              else ROOT / "PDFs_J28_JAEN" / "instrucciones_fisios.pdf")
    salida.parent.mkdir(parents=True, exist_ok=True)
    generar(salida)
    print(f"✅ PDF generado: {salida}")


if __name__ == "__main__":
    main()
