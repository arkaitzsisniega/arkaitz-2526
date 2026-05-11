"""
importar_antropometria.py — Parsea los PDFs de antropometría del
nutricionista y los vuelca a la hoja ANTROPOMETRIA del Sheet principal.

Cada jugador tiene un PDF en cada carpeta de medición (9ª medición = la
más reciente, contiene TODAS las mediciones históricas en una sola
tabla). Por eso solo procesamos el PDF más reciente de cada jugador.

Estructura del PDF (verificada en J.HERRERO 9ª medición, abril 2026):
  · Datos básicos: Peso, Altura + diferencias
  · Pliegues cutáneos (6): Tríceps, Subescapular, Supraespinal,
    Abdominal, Muslo, Pantorrilla → Sumatorio 6 + Diferencia mm
  · Composición: % Masa grasa Yuhasz, % Masa grasa Faulkner,
    Kg Masa Muscular + diferencia Kg
  · Somatotipo: Endomórfico, Mesomórfico, Ectomórfico

Salida: hoja ANTROPOMETRIA del Sheet principal con una fila por
(jugador, fecha_medicion, métrica_dict).

Uso:
  /usr/bin/python3 src/importar_antropometria.py            # ejecuta y vuelca
  /usr/bin/python3 src/importar_antropometria.py --preview  # solo imprime
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
import warnings
from pathlib import Path


def _norm(s: str) -> str:
    """Normaliza un string Unicode a NFC (macOS usa NFD para nombres de
    archivo: 'Ó' como O+◌́). Sin esto, 'MEDICIÓN' (literal) no matchea
    con el nombre del directorio."""
    return unicodedata.normalize("NFC", s)

import pdfplumber
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Arkaitz - Datos Temporada 2526"

CARPETA_ANTRO = (Path.home() / "Mi unidad" / "Deporte" / "Futbol sala"
                  / "Movistar Inter" / "2025-26" / "Nutricion"
                  / "Antropometrias")

# Mapping nombre del archivo PDF → nombre del roster
MAPPING_NOMBRES = {
    "ADRIAN PIRATA": "PIRATA",
    "BRUNO": "CHAGUINHA",
    "BRUNO CHANGUINHA": "CHAGUINHA",
    "CARLOS": "CARLOS",
    "CARLOS BARTOLOME": "CARLOS",
    "CECILIO": "CECILIO",
    "DANI COLON": "DANI",
    "GONZALO": "GONZALO",
    "HARRISON": "HARRISON",
    "JAIME": "JAIME",
    "JAVIER": "JAVI",
    "JAVIER MINGUEZ": "JAVI",
    "JESUS GARCIA": "GARCIA",
    "JESUS GARCÍA": "GARCIA",
    "JESUS HERRERO": "HERRERO",
    "OSCAR": "OSCAR",
    "PANI": "PANI",
    "RAUL": "RAUL",
    "RAUL GOMEZ": "RAUL",
    "RAÚL GÓMEZ": "RAUL",
    "RAYA": "RAYA",
    "SEGO": "SEGO",
    "SEGO_": "SEGO",
    "SERGIO BARONA": "BARONA",
    "SERGIO VIZUETE": "RUBIO",
}

# Etiquetas exactas de las filas que esperamos en el PDF.
# Mapping label_pdf → nombre_columna (limpio para Sheets)
ETIQUETAS = {
    "Peso (Kg)": "peso_kg",
    "Altura (Cm)": "altura_cm",
    "Tríceps": "tríceps_mm",
    "Subescapular": "subescapular_mm",
    "Supraespinal": "supraespinal_mm",
    "Abdominal": "abdominal_mm",
    "Muslo": "muslo_mm",
    "Pantorrilla": "pantorrilla_mm",
    "Sumatorio 6 Pliegues": "sumatorio_6_pliegues_mm",
    "% Masa grasa (Yuhasz)": "masa_grasa_yuhasz_pct",
    "% Masa grasa (Faulkner)": "masa_grasa_faulkner_pct",
    "Kg Masa Muscular": "masa_muscular_kg",
    "Componente Endomórfico": "somatotipo_endomórfico",
    "Componente Mesomórfico": "somatotipo_mesomórfico",
    "Componente Ectomórfico": "somatotipo_ectomórfico",
}

# Orden de columnas en la hoja final
COLS_HOJA = [
    "fecha_medicion",
    "jugador",
    "dorsal",
    "peso_kg",
    "altura_cm",
    "imc",  # calculado
    "tríceps_mm",
    "subescapular_mm",
    "supraespinal_mm",
    "abdominal_mm",
    "muslo_mm",
    "pantorrilla_mm",
    "sumatorio_6_pliegues_mm",
    "masa_grasa_yuhasz_pct",
    "masa_grasa_faulkner_pct",
    "masa_muscular_kg",
    "somatotipo_endomórfico",
    "somatotipo_mesomórfico",
    "somatotipo_ectomórfico",
    "medicion_n",  # 0, 1, ..., 9 (índice de la medición)
]


def _to_float(s: str) -> float | None:
    s = s.strip()
    if not s or "NUM" in s.upper().replace("¡", ""):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_pdf(pdf_path: Path) -> list[dict]:
    """Devuelve una lista de dicts, uno por medición.
    Cada dict: {fecha_medicion, jugador, peso_kg, altura_cm, ...}"""
    with pdfplumber.open(str(pdf_path)) as p:
        words = p.pages[0].extract_words()

    # Clustering de palabras por línea (top similar ≤1.5)
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
    clusters = []
    for w in words_sorted:
        if not clusters or abs(w["top"] - clusters[-1][0]["top"]) > 1.5:
            clusters.append([w])
        else:
            clusters[-1].append(w)
    for c in clusters:
        c.sort(key=lambda w: w["x0"])

    # Determinar el umbral X de separación etiqueta/valores DINÁMICAMENTE:
    # buscar la fila de fechas (dd/mm/yyyy) y usar la x0 mínima de las
    # fechas como umbral. Si no hay fechas, fallback a 165 (valor original
    # para PDFs con 10 mediciones; con 13 mediciones está sobre 132).
    umbral_x = 165.0
    for c in clusters:
        fechas_en_fila = [w for w in c if re.match(r"\d{2}/\d{2}/\d{4}", w["text"])]
        if len(fechas_en_fila) >= 5:
            umbral_x = min(w["x0"] for w in fechas_en_fila) - 5  # margen
            break

    # Construir dict de filas: {label_normalizado: [valores]}
    filas = {}
    fechas = None
    for c in clusters:
        label = " ".join(w["text"] for w in c if w["x0"] < umbral_x).strip()
        valores = [w["text"] for w in c if w["x0"] >= umbral_x]
        if not label or not valores:
            continue
        # ¿Es la fila de fechas? (contiene "Fecha de Medición")
        if "Fecha de Medición" in label and len(valores) >= 5:
            # Tomar las fechas en el formato dd/mm/yyyy
            fechas_filtrado = [v for v in valores if re.match(r"\d{2}/\d{2}/\d{4}", v)]
            if fechas_filtrado:
                fechas = fechas_filtrado
            continue
        # ¿Coincide con alguna etiqueta conocida?
        if label in ETIQUETAS:
            filas[ETIQUETAS[label]] = valores

    if fechas is None:
        return []

    # Convertir cada fila en lista de mediciones
    n = len(fechas)
    mediciones = []
    for i in range(n):
        m = {"fecha_medicion": _normalizar_fecha(fechas[i]),
             "medicion_n": i}
        for col in ETIQUETAS.values():
            if col in filas and i < len(filas[col]):
                m[col] = _to_float(filas[col][i])
            else:
                m[col] = None
        mediciones.append(m)

    return mediciones


def _normalizar_fecha(s: str) -> str:
    """Convierte 'dd/mm/yyyy' a 'yyyy-mm-dd'."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s.strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s


def _nombre_jugador(pdf_path: Path) -> str | None:
    """Obtiene el nombre del jugador a partir del nombre del archivo,
    aplicando el mapping al roster."""
    # Normalizar Unicode (NFD → NFC) y limpiar
    stem = _norm(pdf_path.stem).upper().strip().rstrip("_").strip()
    stem = re.sub(r"\s+", " ", stem)
    if stem in MAPPING_NOMBRES:
        return MAPPING_NOMBRES[stem]
    for k, v in MAPPING_NOMBRES.items():
        if k in stem or stem in k:
            return v
    return None


def _seleccionar_pdfs_mas_recientes() -> dict[str, Path]:
    """Por cada jugador, encuentra el PDF más reciente (carpeta con número
    más alto)."""
    if not CARPETA_ANTRO.exists():
        print(f"❌ No encuentro la carpeta {CARPETA_ANTRO}")
        return {}

    # Carpetas de mediciones, ordenadas por número
    # macOS guarda nombres en NFD → normalizar a NFC para que matchee 'MEDICIÓN'
    carpetas = sorted(
        [c for c in CARPETA_ANTRO.iterdir()
         if c.is_dir() and "MEDICIÓN" in _norm(c.name)],
        key=lambda c: int(re.match(r"^(\d+)", _norm(c.name)).group(1)) if re.match(r"^\d+", _norm(c.name)) else 0,
        reverse=True,  # más reciente primero
    )

    seleccion = {}
    for carp in carpetas:
        for pdf in carp.iterdir():
            if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                continue
            if "INFORME" in pdf.stem.upper():
                continue
            jug = _nombre_jugador(pdf)
            if not jug:
                continue
            # Solo añadir si NO tenemos ya un PDF más reciente
            if jug not in seleccion:
                seleccion[jug] = pdf
    return seleccion


def _calcular_imc(peso, altura):
    if peso is None or altura is None or altura == 0:
        return None
    altura_m = altura / 100.0
    return round(peso / (altura_m * altura_m), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                     help="No escribe en el Sheet, solo muestra qué haría.")
    args = ap.parse_args()

    print("=" * 70)
    print("IMPORTAR ANTROPOMETRÍA — PDFs nutricionista → ANTROPOMETRIA")
    print("=" * 70)
    print()

    seleccion = _seleccionar_pdfs_mas_recientes()
    if not seleccion:
        print("❌ No encontré PDFs.")
        return 1
    print(f"📂 PDFs seleccionados (último por jugador): {len(seleccion)}")
    for jug, pdf in sorted(seleccion.items()):
        print(f"   · {jug:<14} ← {pdf.parent.name} / {pdf.name}")
    print()

    # Roster para mapear jugador → dorsal
    print("🔗 Conectando con Sheet…")
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    sh = gspread.authorize(creds).open(SHEET_NAME)
    roster_rows = sh.worksheet("JUGADORES_ROSTER").get_all_records()
    nombre_a_dorsal = {}
    for r in roster_rows:
        nom = str(r.get("nombre", "")).strip().upper()
        # Normalizar: quitar "J." prefix
        nom_norm = nom.replace("J.", "").strip()
        if nom:
            nombre_a_dorsal[nom] = r.get("dorsal", "")
            nombre_a_dorsal[nom_norm] = r.get("dorsal", "")

    # Parsear cada PDF
    print()
    print("📖 Parseando PDFs…")
    todas_filas = []
    for jug, pdf in sorted(seleccion.items()):
        try:
            mediciones = _parse_pdf(pdf)
        except Exception as e:
            print(f"   ❌ {jug}: {e}")
            continue
        dorsal = nombre_a_dorsal.get(jug.upper(), "")
        try:
            dorsal_str = str(int(float(dorsal))) if dorsal not in ("", None) else ""
        except (ValueError, TypeError):
            dorsal_str = str(dorsal)
        # Filtrar mediciones sin peso (vacías)
        mediciones_validas = [m for m in mediciones if m.get("peso_kg") is not None]
        print(f"   · {jug:<14} → {len(mediciones_validas)} mediciones válidas "
              f"(de {len(mediciones)} totales en el PDF)")
        for m in mediciones_validas:
            m["jugador"] = jug
            m["dorsal"] = dorsal_str
            m["imc"] = _calcular_imc(m.get("peso_kg"), m.get("altura_cm"))
            todas_filas.append(m)

    if not todas_filas:
        print("❌ No se extrajo ninguna medición válida.")
        return 1

    print()
    print(f"📊 Total filas a escribir: {len(todas_filas)}")

    # Ordenar por (jugador, fecha)
    todas_filas.sort(key=lambda m: (m.get("jugador", ""), m.get("fecha_medicion", "")))

    if args.preview:
        # Mostrar primeras 5 filas
        print()
        print("--- PREVIEW primeras 5 filas ---")
        for f in todas_filas[:5]:
            print(f)
        print()
        print("💡 PREVIEW. No se ha escrito al Sheet. Quita --preview para escribir.")
        return 0

    # Crear/actualizar hoja ANTROPOMETRIA
    print()
    print("📝 Escribiendo hoja ANTROPOMETRIA…")
    titulos = [w.title for w in sh.worksheets()]
    if "ANTROPOMETRIA" in titulos:
        ws = sh.worksheet("ANTROPOMETRIA")
        ws.clear()
        time.sleep(0.5)
    else:
        ws = sh.add_worksheet(title="ANTROPOMETRIA",
                                rows=max(len(todas_filas) + 10, 100),
                                cols=len(COLS_HOJA) + 5)
        time.sleep(0.5)

    # Construir filas. IMPORTANTE: pasar VALORES NATIVOS (no str()) para
    # que Sheets reciba números como number y strings como text. Si paso
    # todo como str() y luego uso value_input_option=USER_ENTERED, Sheets
    # interpreta algunos valores numéricos como FECHAS según locale y los
    # convierte a serial (ej. 21.7 → 46224 = 2026-07-22).
    valores = [COLS_HOJA]
    for m in todas_filas:
        fila = []
        for c in COLS_HOJA:
            v = m.get(c, "")
            if v is None:
                fila.append("")
            elif isinstance(v, (int, float)):
                fila.append(v)  # nativo: Sheets lo guarda como number
            else:
                fila.append(str(v))
        valores.append(fila)

    last_col_letter = chr(64 + len(COLS_HOJA)) if len(COLS_HOJA) <= 26 else (
        chr(64 + (len(COLS_HOJA)-1)//26) + chr(65 + (len(COLS_HOJA)-1) % 26))

    # PRIMERO: forzar formato de TODAS las columnas numéricas a NUMBER
    # plain (sin DATE auto) para evitar que Sheets aplique formato DATE
    # heredado del entorno locale.
    sh = ws.spreadsheet
    requests = []
    # Columna fecha_medicion (idx 0) → DATE
    # Columna jugador (idx 1) → TEXT
    # Columna dorsal (idx 2) → TEXT
    # Columnas peso, altura, imc, ..., medicion_n (idx 3 al final) → NUMBER
    text_cols = [1, 2]  # jugador, dorsal
    date_cols = [0]
    number_cols = [i for i in range(len(COLS_HOJA))
                    if i not in text_cols and i not in date_cols]
    for col_idx in number_cols:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id,
                           "startColumnIndex": col_idx,
                           "endColumnIndex": col_idx + 1,
                           "startRowIndex": 1},  # excluir cabecera
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "NUMBER", "pattern": "0.##"}
                }},
                "fields": "userEnteredFormat.numberFormat",
            }
        })
    for col_idx in text_cols:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id,
                           "startColumnIndex": col_idx,
                           "endColumnIndex": col_idx + 1,
                           "startRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "TEXT"}
                }},
                "fields": "userEnteredFormat.numberFormat",
            }
        })
    for col_idx in date_cols:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id,
                           "startColumnIndex": col_idx,
                           "endColumnIndex": col_idx + 1,
                           "startRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}
                }},
                "fields": "userEnteredFormat.numberFormat",
            }
        })
    if requests:
        sh.batch_update({"requests": requests})

    # AHORA escribir los datos con USER_ENTERED (que respetará el formato)
    ws.update(values=valores,
                range_name=f"A1:{last_col_letter}{len(valores)}",
                value_input_option="USER_ENTERED")
    # Formato cabecera (encima del numberFormat)
    ws.format(f"A1:{last_col_letter}1", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "backgroundColor": {"red": 0.10, "green": 0.23, "blue": 0.42},
    })
    ws.freeze(rows=1)
    print(f"   ✅ {len(todas_filas)} filas escritas en ANTROPOMETRIA")
    print()
    print("=" * 70)
    print("✅ Listo")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
