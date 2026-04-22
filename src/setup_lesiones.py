"""
setup_lesiones.py
Añade la pestaña LESIONES al Google Sheet con:
- Campos de entrada al producirse la lesión
- Campos de cierre al volver el jugador
- Fórmulas automáticas: días reales, diferencia, sesiones/partidos perdidos
- Formato visual con colores por estado
"""

import warnings, json, time
warnings.filterwarnings("ignore")

import gspread
from google.oauth2.service_account import Credentials

CREDS_FILE = "google_credentials.json"
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES     = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Colores
C_WHITE      = {"red": 1.0,  "green": 1.0,  "blue": 1.0}
C_BLACK_TXT  = {"red": 0.13, "green": 0.13, "blue": 0.13}
C_DARK       = {"red": 0.13, "green": 0.13, "blue": 0.13}
C_RED_HD     = {"red": 0.60, "green": 0.10, "blue": 0.10}
C_BLUE_HD    = {"red": 0.17, "green": 0.39, "blue": 0.64}
C_GREEN_HD   = {"red": 0.14, "green": 0.49, "blue": 0.30}
C_ORANGE_HD  = {"red": 0.70, "green": 0.35, "blue": 0.00}
C_GREY_HD    = {"red": 0.40, "green": 0.40, "blue": 0.40}
C_L_RED      = {"red": 0.98, "green": 0.87, "blue": 0.87}
C_L_GREEN    = {"red": 0.85, "green": 0.95, "blue": 0.87}
C_L_ORANGE   = {"red": 1.00, "green": 0.94, "blue": 0.84}
C_L_YELLOW   = {"red": 1.00, "green": 0.98, "blue": 0.82}
C_L_GREY     = {"red": 0.95, "green": 0.95, "blue": 0.95}
C_L_BLUE     = {"red": 0.85, "green": 0.92, "blue": 0.98}


def connect():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def batch(ss, requests):
    ss.batch_update({"requests": requests})
    time.sleep(0.6)


def dropdown(sheet_id, row0, row1, col, values):
    return {
        "setDataValidation": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": row0, "endRowIndex": row1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "showCustomUi": True, "strict": True,
            },
        }
    }


def num_valid(sheet_id, row0, row1, col, mn, mx):
    return {
        "setDataValidation": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": row0, "endRowIndex": row1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {
                "condition": {
                    "type": "NUMBER_BETWEEN",
                    "values": [{"userEnteredValue": str(mn)},
                               {"userEnteredValue": str(mx)}],
                },
                "showCustomUi": True, "strict": False,
            },
        }
    }


def color_range(sheet_id, r0, r1, c0, c1, bg, bold=False, fg=None, size=None, italic=False):
    fmt = {"backgroundColor": bg}
    tf = {}
    if bold:   tf["bold"]           = True
    if fg:     tf["foregroundColor"] = fg
    if size:   tf["fontSize"]        = size
    if italic: tf["italic"]          = True
    if tf:     fmt["textFormat"]     = tf
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": r0, "endRowIndex": r1,
                      "startColumnIndex": c0, "endColumnIndex": c1},
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    }


def col_width(sheet_id, col_idx, px):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col_idx, "endIndex": col_idx + 1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def row_height(sheet_id, r0, r1, px):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": r0, "endIndex": r1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def merge(sheet_id, r0, r1, c0, c1):
    return {
        "mergeCells": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": r0, "endRowIndex": r1,
                      "startColumnIndex": c0, "endColumnIndex": c1},
            "mergeType": "MERGE_ALL",
        }
    }


def cond_fmt(sheet_id, r0, r1, c0, c1, formula, bg):
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id,
                            "startRowIndex": r0, "endRowIndex": r1,
                            "startColumnIndex": c0, "endColumnIndex": c1}],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA",
                                  "values": [{"userEnteredValue": formula}]},
                    "format": {"backgroundColor": bg},
                },
            },
            "index": 0,
        }
    }


def freeze(sheet_id, rows=1, cols=2):
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def main():
    print("Conectando con Google Sheets...")
    client = connect()
    ss = client.open(SHEET_NAME)

    # ── Crear pestaña LESIONES ────────────────────────────────────────────────
    existing = {ws.title for ws in ss.worksheets()}
    if "LESIONES" in existing:
        ws = ss.worksheet("LESIONES")
        ws.clear()
        time.sleep(0.5)
        print("  Pestaña LESIONES encontrada — limpiando y rehaciendo.")
    else:
        ws = ss.add_worksheet(title="LESIONES", rows=500, cols=30)
        time.sleep(1)
        print("  Pestaña LESIONES creada.")

    sid = ws.id

    # ── Cabeceras de grupo (fila 1) y columnas (fila 2) ──────────────────────
    #
    # Bloques:
    #   A-K  → REGISTRO DE LESIÓN  (11 cols, rojo)
    #   L-Q  → SEGUIMIENTO MÉDICO  (6 cols, azul)
    #   R-W  → CIERRE / ALTA       (6 cols, verde)
    #   X-AC → SESIONES PERDIDAS   (6 cols, naranja — fórmulas automáticas)
    #
    # Columna index:  0  1  2  3  4  5  6  7  8  9 10 | 11 12 13 14 15 16 | 17 18 19 20 21 22 | 23 24 25 26 27 28

    group_row = [
        "REGISTRO DE LESIÓN", "", "", "", "", "", "", "", "", "", "",
        "SEGUIMIENTO MÉDICO", "", "", "", "", "",
        "CIERRE / ALTA", "", "", "", "", "",
        "SESIONES PERDIDAS (automático)", "", "", "", "", "",
    ]

    col_headers = [
        # REGISTRO (A-K)
        "JUGADOR",          # A  0
        "FECHA LESIÓN",     # B  1
        "MOMENTO",          # C  2
        "TIPO LESIÓN",      # D  3
        "ZONA CORPORAL",    # E  4
        "LADO",             # F  5
        "MECANISMO",        # G  6
        "DIAGNÓSTICO",      # H  7
        "DÍAS BAJA EST.",   # I  8
        "PRUEBAS MÉDICAS",  # J  9
        "NOTAS INICIALES",  # K  10
        # SEGUIMIENTO (L-Q)
        "ESTADO ACTUAL",    # L  11
        "FECHA REVISIÓN",   # M  12
        "TRATAMIENTO",      # N  13
        "EVOLUCIÓN",        # O  14
        "VUELTA PROG.",     # P  15
        "NOTAS SEGUIM.",    # Q  16
        # CIERRE (R-W)
        "FECHA ALTA",       # R  17
        "DÍAS BAJA REALES", # S  18  — fórmula: R - B
        "DIFERENCIA DÍAS",  # T  19  — fórmula: S - I
        "RECAÍDA",          # U  20
        "BAJA ANTERIOR",    # V  21  — mismo jugador, lesión previa
        "NOTAS ALTA",       # W  22
        # SESIONES PERDIDAS (X-AC)
        "TOTAL SESIONES",   # X  23  — COUNTIFS SESIONES entre fechas
        "ENTRENOS",         # Y  24
        "GYM",              # Z  25
        "PARTIDOS",         # AA 26
        "RECUP",            # AB 27
        "MINUTOS PERDIDOS", # AC 28
    ]

    ws.update("A1", [group_row, col_headers])
    time.sleep(1)

    # ── Fórmulas automáticas en filas 3..500 ─────────────────────────────────
    # S = días baja reales       → =IF(AND(B3<>"",R3<>""), R3-B3, "")
    # T = diferencia días        → =IF(AND(S3<>"",I3<>""), S3-I3, "")
    # X = total sesiones         → COUNTIFS(SESIONES!A:A,">="&B3, SESIONES!A:A,"<="&R3)
    # Y = entrenos (no GYM, no RECUP, no PARTIDO)
    # Z = gym
    # AA= partidos
    # AB= recup
    # AC= minutos perdidos

    formula_rows = []
    for r in range(3, 501):
        b = f"B{r}"
        i = f"I{r}"
        r_col = f"R{r}"
        s_col = f"S{r}"

        f_s  = f'=IF(AND({b}<>"",{r_col}<>""),{r_col}-{b},"")'
        f_t  = f'=IF(AND({s_col}<>"",{i}<>""),{s_col}-{i},"")'
        f_x  = (f'=IF({b}="","",COUNTIFS(SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY())))')
        f_y  = (f'=IF({b}="","",COUNTIFS(SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY()),'
                f'SESIONES!D:D,"<>PARTIDO",SESIONES!D:D,"<>GYM",'
                f'SESIONES!D:D,"<>RECUP"))')
        f_z  = (f'=IF({b}="","",COUNTIFS(SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY()),'
                f'SESIONES!D:D,"GYM"))')
        f_aa = (f'=IF({b}="","",COUNTIFS(SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY()),'
                f'SESIONES!D:D,"PARTIDO"))')
        f_ab = (f'=IF({b}="","",COUNTIFS(SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY()),'
                f'SESIONES!D:D,"RECUP"))')
        f_ac = (f'=IF({b}="","",SUMIFS(SESIONES!E:E,SESIONES!A:A,">="&{b},'
                f'SESIONES!A:A,"<="&IF({r_col}<>"",{r_col},TODAY())))')

        formula_rows.append([f_s, f_t, f_x, f_y, f_z, f_aa, f_ab, f_ac])

    # Actualizar columnas S-AC (índice 18-28) para filas 3-500
    # Lo hacemos columna a columna para no superar límite de caracteres
    col_letters = ["S", "T", "X", "Y", "Z", "AA", "AB", "AC"]
    for ci, letter in enumerate(col_letters):
        col_data = [[row[ci]] for row in formula_rows]
        ws.update(f"{letter}3", col_data)
        time.sleep(1.2)

    print("  Fórmulas de cálculo automático escritas.")

    # ── Formato visual ────────────────────────────────────────────────────────
    reqs = []

    # Fila 1: grupos de color
    reqs += [
        color_range(sid, 0, 1, 0, 11,  C_RED_HD,    bold=True, fg=C_WHITE, size=10),
        color_range(sid, 0, 1, 11, 17, C_BLUE_HD,   bold=True, fg=C_WHITE, size=10),
        color_range(sid, 0, 1, 17, 23, C_GREEN_HD,  bold=True, fg=C_WHITE, size=10),
        color_range(sid, 0, 1, 23, 29, C_ORANGE_HD, bold=True, fg=C_WHITE, size=10),
    ]

    # Fila 2: cabeceras individuales
    reqs += [
        color_range(sid, 1, 2, 0, 11,  {"red": 0.75, "green": 0.22, "blue": 0.22},
                    bold=True, fg=C_WHITE, size=9),
        color_range(sid, 1, 2, 11, 17, {"red": 0.27, "green": 0.51, "blue": 0.76},
                    bold=True, fg=C_WHITE, size=9),
        color_range(sid, 1, 2, 17, 23, {"red": 0.22, "green": 0.62, "blue": 0.39},
                    bold=True, fg=C_WHITE, size=9),
        color_range(sid, 1, 2, 23, 29, {"red": 0.85, "green": 0.50, "blue": 0.10},
                    bold=True, fg=C_WHITE, size=9),
    ]

    # Columnas automáticas (S,T,X-AC) con fondo gris claro
    reqs += [
        color_range(sid, 2, 500, 18, 20, C_L_BLUE),   # días reales + diferencia
        color_range(sid, 2, 500, 23, 29, C_L_GREY),   # sesiones perdidas
    ]

    # Anchos de columna
    widths = [
        130, 110, 130, 120, 130, 80, 120, 200, 90, 130, 200,  # A-K
        120, 110, 140, 110, 110, 200,                          # L-Q
        110, 90, 90, 90, 110, 200,                             # R-W
        90, 80, 70, 80, 70, 110,                               # X-AC
    ]
    reqs += [col_width(sid, i, w) for i, w in enumerate(widths)]

    # Altura de filas de cabecera
    reqs += [
        row_height(sid, 0, 1, 30),
        row_height(sid, 1, 2, 45),
    ]

    # Merge celdas de grupo en fila 1
    reqs += [
        merge(sid, 0, 1, 0,  11),
        merge(sid, 0, 1, 11, 17),
        merge(sid, 0, 1, 17, 23),
        merge(sid, 0, 1, 23, 29),
    ]

    # Freeze solo filas (las columnas están dentro de celdas fusionadas)
    reqs.append(freeze(sid, rows=2, cols=0))

    batch(ss, reqs)

    # ── Validaciones (dropdowns) ──────────────────────────────────────────────
    # Obtener lista de jugadores desde pestaña BORG
    ws_borg = ss.worksheet("BORG")
    jugadores_raw = ws_borg.col_values(3)[1:]  # col C, sin cabecera
    jugadores = sorted(set(j for j in jugadores_raw if j and j not in ("JUGADOR", "NAN")))

    n = 500
    reqs2 = [
        dropdown(sid, 2, n, 0,  jugadores),
        dropdown(sid, 2, n, 2,  ["Entrenamiento", "Partido", "Calle / Ocio",
                                  "Calentamiento", "Vuelta a la calma", "Otro"]),
        dropdown(sid, 2, n, 3,  ["Muscular (rotura/distensión)", "Tendinosa",
                                  "Articular (esguince/luxación)", "Ósea (fractura/fisura)",
                                  "Contusión", "Sobrecarga", "Fatiga",
                                  "Herida / Abrasión", "Otro"]),
        dropdown(sid, 2, n, 4,  ["Tobillo", "Rodilla", "Muslo anterior",
                                  "Isquiotibial", "Aductor", "Cadera",
                                  "Lumbar", "Abdominal", "Hombro",
                                  "Codo", "Muñeca", "Cabeza / Cuello",
                                  "Pie / Dedos", "Otro"]),
        dropdown(sid, 2, n, 5,  ["Derecho", "Izquierdo", "Bilateral", "N/A"]),
        dropdown(sid, 2, n, 6,  ["Contacto directo", "Sin contacto",
                                  "Sobrecarga acumulada", "Caída",
                                  "Hiperextensión", "Torsión", "Otro"]),
        num_valid(sid, 2, n, 8, 0, 365),
        dropdown(sid, 2, n, 9,  ["Ninguna", "Ecografía", "Resonancia magnética",
                                  "Radiografía", "TAC", "Analítica",
                                  "Ecografía + Resonancia", "Varias"]),
        dropdown(sid, 2, n, 11, ["En tratamiento", "Recuperación",
                                  "Vuelta progresiva", "Alta médica",
                                  "Pendiente de prueba"]),
        dropdown(sid, 2, n, 13, ["Fisioterapia manual", "Electroterapia",
                                  "Trabajo en piscina", "Trabajo de fuerza",
                                  "Vendaje funcional", "Reposo relativo",
                                  "Reposo absoluto", "Combinado"]),
        dropdown(sid, 2, n, 14, ["Favorable", "Estable", "Sin cambios",
                                  "Desfavorable", "Recaída"]),
        dropdown(sid, 2, n, 15, ["Sí", "No", "En valoración"]),
        dropdown(sid, 2, n, 20, ["Sí", "No"]),
    ]
    batch(ss, reqs2)

    # ── Formato condicional por fila completa ─────────────────────────────────
    reqs3 = [
        # Filas con fecha de lesión pero sin alta → amarillo (sigue lesionado)
        cond_fmt(sid, 2, n, 0, 23, '=$B3>0', C_L_YELLOW),
        # Diferencia positiva (tardó más) → naranja en col T
        cond_fmt(sid, 2, n, 19, 20, '=$T3>0', C_L_ORANGE),
        # Diferencia negativa (antes de lo previsto) → verde en col T
        cond_fmt(sid, 2, n, 19, 20, '=$T3<0', C_L_GREEN),
    ]
    batch(ss, reqs3)

    print("  Validaciones y formato condicional aplicados.")

    # ── Actualizar INSTRUCCIONES ──────────────────────────────────────────────
    ws_inst = ss.worksheet("INSTRUCCIONES")
    existing = ws_inst.get_all_values()
    new_rows = [
        ["", "", ""],
        ["LESIONES — CÓMO USARLA", "", ""],
        ["Quién rellena", "Fisioterapeutas / Staff médico", ""],
        ["Al producirse la lesión",
         "Rellenar columnas A-K: jugador, fecha, momento, tipo, zona, diagnóstico, días estimados, pruebas.",
         ""],
        ["Durante la recuperación",
         "Actualizar columnas L-Q: estado actual, fecha de revisión, tratamiento, evolución.",
         ""],
        ["Al dar el alta",
         "Rellenar R (fecha de alta) — S, T y X-AC se calculan solos.",
         ""],
        ["Columnas automáticas",
         "DÍAS BAJA REALES, DIFERENCIA, TOTAL SESIONES, ENTRENOS, GYM, PARTIDOS, RECUP, MINUTOS: "
         "se calculan solos cuando hay fecha de lesión y (si está disponible) fecha de alta.",
         ""],
        ["Color amarillo", "Lesión activa — jugador aún de baja.", ""],
        ["Color naranja (col. T)", "Tardó MÁS días de lo estimado.", ""],
        ["Color verde (col. T)",   "Se recuperó ANTES de lo estimado.", ""],
        ["Color rojo (col. U)",    "Marcado como recaída.", ""],
    ]
    ws_inst.append_rows(new_rows)
    time.sleep(1)
    print("  INSTRUCCIONES actualizada con sección LESIONES.")

    print("\n" + "=" * 60)
    print("✓ Pestaña LESIONES lista")
    print(f"  {ss.url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
