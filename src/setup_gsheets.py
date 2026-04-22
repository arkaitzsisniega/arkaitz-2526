"""
setup_gsheets.py
Crea el Google Sheet "Arkaitz - Datos Temporada 2526",
migra todos los datos históricos del Excel y configura
validaciones y pestañas para fisios.
"""

import json
import warnings
import pandas as pd
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
import time

warnings.filterwarnings("ignore")

CREDS_FILE = "google_credentials.json"
EXCEL_FILE = "Datos_indiv.xlsx"
SHEET_NAME = "Arkaitz - Datos Temporada 2526"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Colores corporativos ──────────────────────────────────────────────────────
COLOR_HEADER_DARK  = {"red": 0.13, "green": 0.13, "blue": 0.13}   # casi negro
COLOR_HEADER_BLUE  = {"red": 0.17, "green": 0.39, "blue": 0.64}   # azul oscuro
COLOR_HEADER_GREEN = {"red": 0.14, "green": 0.49, "blue": 0.30}   # verde oscuro
COLOR_HEADER_ORANGE= {"red": 0.78, "green": 0.35, "blue": 0.00}   # naranja
COLOR_HEADER_RED   = {"red": 0.60, "green": 0.10, "blue": 0.10}   # rojo oscuro
COLOR_WHITE        = {"red": 1.0,  "green": 1.0,  "blue": 1.0}
COLOR_LIGHT_GREY   = {"red": 0.95, "green": 0.95, "blue": 0.95}
COLOR_LIGHT_BLUE   = {"red": 0.85, "green": 0.92, "blue": 0.98}
COLOR_LIGHT_GREEN  = {"red": 0.85, "green": 0.95, "blue": 0.87}
COLOR_LIGHT_ORANGE = {"red": 1.00, "green": 0.94, "blue": 0.84}
COLOR_LIGHT_RED    = {"red": 0.98, "green": 0.87, "blue": 0.87}


def connect():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def safe_update(worksheet, data, range_name=None):
    """Actualiza en bloques para no superar el límite de la API."""
    if not data:
        return
    if range_name:
        worksheet.update(range_name, data)
    else:
        worksheet.update("A1", data)
    time.sleep(1)


def format_header_row(spreadsheet, sheet_id, header_color, n_cols, row=0):
    """Pinta la fila de cabecera con fondo de color y texto blanco en negrita."""
    requests = [{
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row,
                "endRowIndex": row + 1,
                "startColumnIndex": 0,
                "endColumnIndex": n_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": header_color,
                    "textFormat": {"bold": True, "foregroundColor": COLOR_WHITE, "fontSize": 10},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }
    }]
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


def freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=0, col_widths=None):
    requests = [{
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": freeze_rows, "frozenColumnCount": freeze_cols},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }]
    if col_widths:
        for i, w in enumerate(col_widths):
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                              "startIndex": i, "endIndex": i + 1},
                    "properties": {"pixelSize": w},
                    "fields": "pixelSize",
                }
            })
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


def add_dropdown(spreadsheet, sheet_id, start_row, end_row, col, values):
    condition_values = [{"userEnteredValue": v} for v in values]
    requests = [{
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "rule": {
                "condition": {"type": "ONE_OF_LIST", "values": condition_values},
                "showCustomUi": True,
                "strict": True,
            },
        }
    }]
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


def add_number_validation(spreadsheet, sheet_id, start_row, end_row, col, min_val, max_val):
    requests = [{
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "rule": {
                "condition": {
                    "type": "NUMBER_BETWEEN",
                    "values": [
                        {"userEnteredValue": str(min_val)},
                        {"userEnteredValue": str(max_val)},
                    ],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }]
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


# ── Extracción de datos del Excel ─────────────────────────────────────────────

def read_excel_data():
    print("  Leyendo Excel...")
    df_raw = pd.read_excel(EXCEL_FILE, sheet_name="INPUT", header=1)

    # ── SESIONES (cols 0-5) ──
    ses = df_raw.iloc[:, 0:6].copy()
    ses.columns = ["FECHA", "SEMANA", "TURNO", "TIPO_SESION", "MINUTOS", "COMPETICION"]
    ses = ses.dropna(subset=["FECHA", "TURNO"])
    ses["FECHA"] = pd.to_datetime(ses["FECHA"]).dt.strftime("%Y-%m-%d")
    ses = ses[ses["TURNO"].isin(["M", "T", "P"])]

    # ── BORG (cols 7-10) ──
    borg = df_raw.iloc[:, 7:11].copy()
    borg.columns = ["FECHA", "TURNO", "JUGADOR", "BORG"]
    borg = borg.dropna(subset=["FECHA", "JUGADOR", "BORG"])
    borg["FECHA"] = pd.to_datetime(borg["FECHA"]).dt.strftime("%Y-%m-%d")
    borg["JUGADOR"] = borg["JUGADOR"].astype(str).str.strip().str.upper()
    borg = borg[~borg["JUGADOR"].isin(["MEDIA", "NAN", ""])]
    borg = borg[borg["TURNO"].isin(["M", "T", "P"])]

    # ── PESO (cols 12-17) ──
    peso = df_raw.iloc[:, 12:18].copy()
    peso.columns = ["FECHA", "TURNO", "JUGADOR", "PESO_PRE", "PESO_POST", "H2O_L"]
    peso = peso.dropna(subset=["FECHA", "JUGADOR", "PESO_PRE"])
    peso["FECHA"] = pd.to_datetime(peso["FECHA"]).dt.strftime("%Y-%m-%d")
    peso["JUGADOR"] = peso["JUGADOR"].astype(str).str.strip().str.upper()
    peso = peso[~peso["JUGADOR"].isin(["MEDIA", "NAN", ""])]

    # ── WELLNESS (cols 19-25) ──
    well = df_raw.iloc[:, 19:26].copy()
    well.columns = ["FECHA", "JUGADOR", "SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL"]
    well = well.dropna(subset=["FECHA", "JUGADOR", "SUENO"])
    well["FECHA"] = pd.to_datetime(well["FECHA"]).dt.strftime("%Y-%m-%d")
    well["JUGADOR"] = well["JUGADOR"].astype(str).str.strip().str.upper()
    well = well[~well["JUGADOR"].isin(["MEDIA", "NAN", ""])]

    print(f"    Sesiones: {len(ses)} · Borg: {len(borg)} · Peso: {len(peso)} · Wellness: {len(well)}")
    return ses, borg, peso, well


# ── Creación de pestañas ──────────────────────────────────────────────────────

def setup_sesiones(spreadsheet, ws, ses_df):
    print("  Configurando pestaña SESIONES...")
    sheet_id = ws.id

    headers = ["FECHA", "SEMANA", "TURNO", "TIPO_SESION", "MINUTOS", "COMPETICION"]
    rows = [headers] + ses_df[headers].astype(str).replace("nan", "").values.tolist()
    safe_update(ws, rows)

    format_header_row(spreadsheet, sheet_id, COLOR_HEADER_BLUE, len(headers))
    freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=1,
                      col_widths=[110, 70, 60, 110, 80, 150])

    n = len(ses_df) + 500
    add_dropdown(spreadsheet, sheet_id, 1, n, 2, ["M", "T", "P"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 3,
                 ["FISICO", "TEC-TAC", "GYM", "RECUP", "PARTIDO", "PORTEROS"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 5,
                 ["LIGA", "COPA DEL REY", "COPA ESPAÑA", "COPA MOSTOLES",
                  "COPA RIBERA", "SUPERCOPA", "PRE-TEMPORADA", "AMISTOSO"])


def setup_borg(spreadsheet, ws, borg_df, jugadores):
    print("  Configurando pestaña BORG...")
    sheet_id = ws.id

    headers = ["FECHA", "TURNO", "JUGADOR", "BORG"]
    rows = [headers] + borg_df[headers].astype(str).replace("nan", "").values.tolist()
    safe_update(ws, rows)

    format_header_row(spreadsheet, sheet_id, COLOR_HEADER_GREEN, len(headers))
    freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=1,
                      col_widths=[110, 60, 130, 70])

    n = len(borg_df) + 500
    add_dropdown(spreadsheet, sheet_id, 1, n, 1, ["M", "T", "P"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 2, jugadores)
    add_number_validation(spreadsheet, sheet_id, 1, n, 3, 0, 10)


def setup_peso(spreadsheet, ws, peso_df, jugadores):
    print("  Configurando pestaña PESO...")
    sheet_id = ws.id

    headers = ["FECHA", "TURNO", "JUGADOR", "PESO_PRE", "PESO_POST", "H2O_L"]
    rows = [headers] + peso_df[headers].astype(str).replace("nan", "").values.tolist()
    safe_update(ws, rows)

    format_header_row(spreadsheet, sheet_id, COLOR_HEADER_ORANGE, len(headers))
    freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=1,
                      col_widths=[110, 60, 130, 90, 90, 80])

    n = len(peso_df) + 500
    add_dropdown(spreadsheet, sheet_id, 1, n, 1, ["M", "T", "P"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 2, jugadores)
    add_number_validation(spreadsheet, sheet_id, 1, n, 3, 40, 120)
    add_number_validation(spreadsheet, sheet_id, 1, n, 4, 40, 120)
    add_number_validation(spreadsheet, sheet_id, 1, n, 5, 0, 5)


def setup_wellness(spreadsheet, ws, well_df, jugadores):
    print("  Configurando pestaña WELLNESS...")
    sheet_id = ws.id

    headers = ["FECHA", "JUGADOR", "SUENO", "FATIGA", "MOLESTIAS", "ANIMO", "TOTAL"]
    rows = [headers] + well_df[headers].astype(str).replace("nan", "").values.tolist()
    safe_update(ws, rows)

    format_header_row(spreadsheet, sheet_id, COLOR_HEADER_GREEN, len(headers))
    freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=1,
                      col_widths=[110, 130, 80, 80, 100, 80, 80])

    n = len(well_df) + 500
    add_dropdown(spreadsheet, sheet_id, 1, n, 1, jugadores)
    for col in [2, 3, 4, 5]:
        add_number_validation(spreadsheet, sheet_id, 1, n, col, 1, 5)


def setup_fisio(spreadsheet, ws, jugadores):
    print("  Configurando pestaña FISIO...")
    sheet_id = ws.id

    headers = [
        "FECHA", "JUGADOR", "ESTADO", "TIPO_LESION",
        "ZONA_CORPORAL", "LADO", "DIAS_BAJA_ESTIMADOS", "NOTAS"
    ]
    # Fila de ejemplo vacía para que los fisios vean el formato
    example = ["2026-04-22", jugadores[0], "Disponible", "", "", "", "", ""]

    safe_update(ws, [headers, example])

    format_header_row(spreadsheet, sheet_id, COLOR_HEADER_RED, len(headers))
    freeze_and_resize(spreadsheet, sheet_id, freeze_rows=1, freeze_cols=2,
                      col_widths=[110, 130, 120, 130, 130, 80, 160, 250])

    n = 1000
    add_dropdown(spreadsheet, sheet_id, 1, n, 1, jugadores)
    add_dropdown(spreadsheet, sheet_id, 1, n, 2,
                 ["Disponible", "Limitado", "Baja", "Vuelta progresiva", "Duda"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 3,
                 ["Muscular", "Tendinosa", "Articular", "Ósea",
                  "Contusión", "Sobrecarga", "Fatiga", "Otro"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 4,
                 ["Tobillo", "Rodilla", "Muslo anterior", "Isquiotibial",
                  "Aductor", "Cadera", "Lumbar", "Abdominal",
                  "Hombro", "Codo", "Muñeca", "Cabeza/Cuello", "Otro"])
    add_dropdown(spreadsheet, sheet_id, 1, n, 5, ["Derecho", "Izquierdo", "Bilateral", "N/A"])
    add_number_validation(spreadsheet, sheet_id, 1, n, 6, 0, 365)

    # Colorear filas alternas para facilitar lectura
    requests = [{
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000}],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA",
                                  "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]},
                    "format": {"backgroundColor": COLOR_LIGHT_GREY},
                },
            },
            "index": 0,
        }
    }, {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 1000,
                    "startColumnIndex": 2, "endColumnIndex": 3,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": "Baja"}]},
                    "format": {"backgroundColor": COLOR_LIGHT_RED},
                },
            },
            "index": 1,
        }
    }, {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 1000,
                    "startColumnIndex": 2, "endColumnIndex": 3,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": "Limitado"}]},
                    "format": {"backgroundColor": COLOR_LIGHT_ORANGE},
                },
            },
            "index": 2,
        }
    }, {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 1000,
                    "startColumnIndex": 2, "endColumnIndex": 3,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": "Disponible"}]},
                    "format": {"backgroundColor": COLOR_LIGHT_GREEN},
                },
            },
            "index": 3,
        }
    }]
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


def setup_instrucciones(spreadsheet, ws):
    print("  Configurando pestaña INSTRUCCIONES...")
    sheet_id = ws.id

    content = [
        ["ARKAITZ — GUÍA RÁPIDA DE USO", "", ""],
        ["", "", ""],
        ["PESTAÑA", "QUIÉN LA RELLENA", "QUÉ INTRODUCE"],
        ["SESIONES", "Staff / Preparador físico",
         "Una fila por sesión: fecha, semana, turno (M/T/P), tipo, minutos, competición"],
        ["BORG", "Jugadores (vía Google Form)", "RPE 0-10 después de cada entrenamiento"],
        ["PESO", "Jugadores (vía Google Form)", "Peso antes y después de entrenar + agua"],
        ["WELLNESS", "Jugadores (vía Google Form)", "Sueño / Fatiga / Molestias / Ánimo (1-5 cada uno)"],
        ["FISIO", "Fisioterapeutas", "Estado del jugador, tipo y zona de lesión, días de baja estimados"],
        ["", "", ""],
        ["CÓDIGOS DE TURNO", "", ""],
        ["M", "Matinal", "Sesión de mañana"],
        ["T", "Tarde", "Sesión de tarde"],
        ["P", "Partido", "Día de competición"],
        ["", "", ""],
        ["ESCALA WELLNESS (1-5)", "", ""],
        ["1", "Muy mal", ""],
        ["2", "Mal", ""],
        ["3", "Normal", ""],
        ["4", "Bien", ""],
        ["5", "Muy bien", ""],
        ["", "", ""],
        ["ESCALA BORG (0-10)", "", ""],
        ["0", "Nada", ""],
        ["1", "Muy, muy suave", ""],
        ["2", "Muy suave", ""],
        ["3", "Suave", ""],
        ["4", "Moderado", ""],
        ["5", "Algo duro", ""],
        ["6", "Duro", ""],
        ["7", "Muy duro", ""],
        ["8", "Muy, muy duro", ""],
        ["9", "Casi máximo", ""],
        ["10", "Máximo", ""],
    ]
    safe_update(ws, content)

    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_DARK,
                    "textFormat": {"bold": True, "foregroundColor": COLOR_WHITE, "fontSize": 14},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3,
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_BLUE,
                    "textFormat": {"bold": True, "foregroundColor": COLOR_WHITE},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 180},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 220},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 2, "endIndex": 3},
                "properties": {"pixelSize": 400},
                "fields": "pixelSize",
            }
        },
    ]
    spreadsheet.batch_update({"requests": requests})
    time.sleep(0.5)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Conectando con Google...")
    client = connect()

    print(f'Creando Google Sheet "{SHEET_NAME}"...')
    try:
        spreadsheet = client.open(SHEET_NAME)
        print("  (Ya existía, reutilizando)")
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
        print(f"  Creado: {spreadsheet.url}")

    # Compartir con cualquiera que tenga el link (solo lectura) para Looker Studio
    spreadsheet.share(None, perm_type="anyone", role="reader")
    time.sleep(1)

    print("\nLeyendo datos del Excel...")
    ses_df, borg_df, peso_df, well_df = read_excel_data()

    jugadores = sorted(
        borg_df["JUGADOR"].unique().tolist()
    )
    # Filtrar valores no válidos
    jugadores = [j for j in jugadores if j not in ("NAN", "", "MEDIA") and len(j) > 1]

    # ── Crear / obtener pestañas ──────────────────────────────────────────────
    tab_config = [
        ("INSTRUCCIONES", None),
        ("SESIONES",      COLOR_HEADER_BLUE),
        ("BORG",          COLOR_HEADER_GREEN),
        ("PESO",          COLOR_HEADER_ORANGE),
        ("WELLNESS",      COLOR_HEADER_GREEN),
        ("FISIO",         COLOR_HEADER_RED),
    ]

    existing = {ws.title: ws for ws in spreadsheet.worksheets()}
    worksheets = {}

    for i, (name, _) in enumerate(tab_config):
        if name in existing:
            worksheets[name] = existing[name]
            worksheets[name].clear()
            time.sleep(0.5)
        else:
            if i == 0:
                ws = spreadsheet.sheet1
                ws.update_title(name)
            else:
                ws = spreadsheet.add_worksheet(title=name, rows=5000, cols=20)
            worksheets[name] = ws
            time.sleep(1)

    # Eliminar "Sheet1" si quedó sobrante
    for ws in spreadsheet.worksheets():
        if ws.title == "Sheet1":
            spreadsheet.del_worksheet(ws)
            time.sleep(0.5)

    print("\nMigrando datos y configurando pestañas...")
    setup_instrucciones(spreadsheet, worksheets["INSTRUCCIONES"])
    setup_sesiones(spreadsheet,  worksheets["SESIONES"],  ses_df)
    setup_borg(spreadsheet,      worksheets["BORG"],      borg_df,  jugadores)
    setup_peso(spreadsheet,      worksheets["PESO"],      peso_df,  jugadores)
    setup_wellness(spreadsheet,  worksheets["WELLNESS"],  well_df,  jugadores)
    setup_fisio(spreadsheet,     worksheets["FISIO"],               jugadores)

    print("\n" + "="*60)
    print("✓ Google Sheet listo")
    print(f"  URL: {spreadsheet.url}")
    print(f"  Email de servicio: ", end="")
    with open(CREDS_FILE) as f:
        print(json.load(f)["client_email"])
    print("\nPróximo paso:")
    print("  Abre el Sheet, haz clic en 'Compartir' y añade")
    print("  el email de arriba como Editor para poder escribir.")
    print("="*60)

    return spreadsheet.url


if __name__ == "__main__":
    main()
