"""
crear_sheet_fisios.py — Configura el Sheet de Lesiones, Tratamientos
y Temperatura muscular para fisios. Es un sheet SEPARADO del principal
para que los fisios solo accedan a estos datos.

Estructura: 3 pestañas principales + auxiliares
  · LESIONES        ← cuando un jugador se retira
  · TRATAMIENTOS    ← PRE / POST / LESIONADO
  · TEMPERATURA     ← cámara térmica, asimetrías musculares
  · JUGADORES       ← referencia (sincronizada con roster principal)
  · _LISTAS         ← opciones de los dropdowns (oculta lateralmente)
  · _META           ← metadatos internos

⚠️ La cuenta de servicio NO puede crear sheets nuevos. El usuario tiene
que crear el Sheet a mano y compartirlo con la cuenta de servicio.
Después este script crea las hojas, las cabeceras y las VALIDACIONES
(dropdowns) en cada columna.

Idempotente: ejecutarlo varias veces NO duplica datos.

Uso:
  /usr/bin/python3 src/crear_sheet_fisios.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_PRINCIPAL = "Arkaitz - Datos Temporada 2526"
SHEET_FISIOS = "Arkaitz - Lesiones y Tratamientos 2526"
EMAIL_OWNER = "arkaitzsisniega@gmail.com"

# ═══════════════════════════════════════════════════════════════════════
# LISTAS DE OPCIONES (van a la hoja _LISTAS y se referencian con ONE_OF_RANGE)
# ═══════════════════════════════════════════════════════════════════════

TURNOS = ["M", "T", "P"]
LADOS = ["IZDA", "DCHA", "BILATERAL", "N.A."]
SI_NO = ["SÍ", "NO"]

TIPOS_SESION = [
    "ENTRENO", "PARTIDO", "GYM", "RECUP",
    "GYM+TEC-TAC", "FISICO+TEC-TAC", "MATINAL",
    "PORTEROS", "FISICO", "TEC-TAC", "AMISTOSO",
]

ZONAS_CORPORALES = [
    "CABEZA", "CUELLO",
    "PECHO", "ESPALDA", "ABDOMEN", "LUMBAR",
    "HOMBRO", "BÍCEPS", "TRÍCEPS", "CODO", "ANTEBRAZO", "MUÑECA", "MANO",
    "CADERA", "GLÚTEO", "INGLE",
    "CUÁDRICEPS", "ISQUIOTIBIALES", "ADUCTORES", "ABDUCTORES",
    "RODILLA",
    "PANTORRILLA / GEMELO", "TIBIAL ANTERIOR", "TENDÓN DE AQUILES",
    "TOBILLO", "PIE", "TALÓN",
]

TIPOS_TEJIDO = [
    "MUSCULAR", "TENDINOSA", "LIGAMENTOSA", "ÓSEA",
    "ARTICULAR", "CARTILAGINOSA", "MENISCAL",
    "CONTUSIÓN", "ESGUINCE", "FRACTURA",
    "NEUROLÓGICA", "OTRO",
]

MECANISMOS = [
    "CONTACTO", "NO_CONTACTO", "SOBREUSO",
    "RECIDIVA", "MAL_GESTO", "DESCONOCIDO", "OTRO",
]

GRAVEDADES = ["LEVE", "MODERADA", "GRAVE"]

ESTADOS_LESION = ["ACTIVA", "EN_RECUP", "ALTA", "RECAÍDA"]

PRUEBAS_MEDICAS = [
    "NINGUNA", "ECO", "RM", "RX", "TAC", "ANÁLISIS", "VARIAS",
]

# Tratamientos
BLOQUES_TRATAMIENTO = ["PRE_ENTRENO", "POST_ENTRENO", "LESIONADO"]

ACCIONES_TRATAMIENTO = [
    "VENDAJE_FUNCIONAL", "VENDAJE_NEUROMUSCULAR", "VENDAJE_COMPRESIVO",
    "MASAJE", "MASAJE_DESCARGA",
    "ELECTRO_TENS", "ELECTRO_EMS", "ELECTRO_INTERFER.",
    "PUNCIÓN_SECA",
    "CRIOTERAPIA", "TERMOTERAPIA", "CONTRASTES",
    "MOVILIZACIÓN", "ESTIRAMIENTOS", "AUTOMASAJE",
    "READAPTACIÓN", "PROPIOCEPCIÓN", "FUERZA_EXCÉNTRICA",
    "ULTRASONIDO", "ONDAS_DE_CHOQUE", "INDIBA", "MAGNETOTERAPIA",
    "OSTEOPATÍA", "ACTIVACIÓN", "OTRO",
]

FISIOS = ["PELU", "ARKAITZ", "OTRO"]

# Temperatura
MOMENTOS_TERMICOS = [
    "PRE_ENTRENO", "POST_ENTRENO",
    "PRE_PARTIDO", "POST_PARTIDO",
    "RECUP_24H", "RECUP_48H", "RECUP_72H",
]

ZONAS_TERMICAS = [
    "CUÁDRICEPS_ANT", "ISQUIOTIBIALES_POST", "ADUCTORES_INT",
    "GLÚTEO", "PANTORRILLA_POST", "GEMELO_LATERAL",
    "TIBIAL_ANTERIOR", "TENDÓN_AQUILES",
    "RODILLA_ANT", "RODILLA_POST",
    "TOBILLO_ANT", "TOBILLO_POST",
    "ESPALDA_BAJA", "ESPALDA_ALTA", "LUMBAR",
    "HOMBRO", "PSOAS",
]

# Mapeo nombre listo → columna en _LISTAS
LISTAS = {
    "TURNOS": TURNOS,
    "LADOS": LADOS,
    "SI_NO": SI_NO,
    "TIPOS_SESION": TIPOS_SESION,
    "ZONAS_CORPORALES": ZONAS_CORPORALES,
    "TIPOS_TEJIDO": TIPOS_TEJIDO,
    "MECANISMOS": MECANISMOS,
    "GRAVEDADES": GRAVEDADES,
    "ESTADOS_LESION": ESTADOS_LESION,
    "PRUEBAS_MEDICAS": PRUEBAS_MEDICAS,
    "BLOQUES_TRATAMIENTO": BLOQUES_TRATAMIENTO,
    "ACCIONES_TRATAMIENTO": ACCIONES_TRATAMIENTO,
    "FISIOS": FISIOS,
    "MOMENTOS_TERMICOS": MOMENTOS_TERMICOS,
    "ZONAS_TERMICAS": ZONAS_TERMICAS,
}

# ═══════════════════════════════════════════════════════════════════════
# ESTRUCTURA DE LAS PESTAÑAS
# Cada columna es: (nombre, validacion_lista_o_None)
# validacion = nombre de la lista en LISTAS, "JUGADOR", "FECHA", "NUMERO", o None
# ═══════════════════════════════════════════════════════════════════════

COLS_LESIONES = [
    ("id_lesion", None),                  # auto
    ("fecha_lesion", "FECHA"),
    ("turno", "TURNOS"),
    ("tipo_sesion", "TIPOS_SESION"),
    ("jugador", "JUGADOR"),
    ("dorsal", None),                     # auto desde JUGADORES
    ("zona_corporal", "ZONAS_CORPORALES"),
    ("lado", "LADOS"),
    ("tipo_tejido", "TIPOS_TEJIDO"),
    ("mecanismo", "MECANISMOS"),
    ("gravedad", "GRAVEDADES"),
    ("dias_baja_estimados", "NUMERO"),
    ("pruebas_medicas", "PRUEBAS_MEDICAS"),
    ("diagnostico", None),                # texto libre
    ("estado_actual", "ESTADOS_LESION"),
    ("fecha_alta", "FECHA"),
    ("dias_baja_real", None),             # auto
    ("diferencia_dias", None),            # auto
    ("total_sesiones_perdidas", None),    # auto
    ("entrenos_perdidos", None),          # auto
    ("partidos_perdidos", None),          # auto
    ("recaida", "SI_NO"),
    ("notas", None),                      # texto libre
]

COLS_TRATAMIENTOS = [
    ("id_tratamiento", None),
    ("fecha", "FECHA"),
    ("turno", "TURNOS"),
    ("bloque", "BLOQUES_TRATAMIENTO"),    # PRE / POST / LESIONADO
    ("jugador", "JUGADOR"),
    ("dorsal", None),
    ("fisio", "FISIOS"),
    ("accion", "ACCIONES_TRATAMIENTO"),
    ("zona_corporal", "ZONAS_CORPORALES"),
    ("lado", "LADOS"),
    ("duracion_min", "NUMERO"),
    ("id_lesion_relacionada", None),      # opcional, dropdown dinámico
    ("notas", None),
]

COLS_TEMPERATURA = [
    ("id_medicion", None),
    ("fecha", "FECHA"),
    ("turno", "TURNOS"),
    ("momento", "MOMENTOS_TERMICOS"),
    ("jugador", "JUGADOR"),
    ("dorsal", None),
    ("zona", "ZONAS_TERMICAS"),
    ("temp_izda_c", "NUMERO"),            # °C
    ("temp_dcha_c", "NUMERO"),
    ("asimetria_c", None),                # auto = izda - dcha
    ("alerta", None),                     # auto = "ALERTA" si |asimetria|>0.5
    ("temp_ambiente_c", "NUMERO"),
    ("notas", None),
]

COLS_JUGADORES = ["dorsal", "nombre", "posicion", "equipo", "activo"]

COLS_META = ["clave", "valor", "actualizado"]


def _connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def _abrir_sheet(client) -> gspread.Spreadsheet:
    """Abre el Sheet de fisios. Falla con instrucciones si no existe."""
    try:
        sh = client.open(SHEET_FISIOS)
        print(f"📂 Sheet encontrado: '{SHEET_FISIOS}' (id: {sh.id})")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        print()
        print("=" * 70)
        print(f"❌ No encuentro el Sheet '{SHEET_FISIOS}'")
        print("=" * 70)
        print()
        print("Crea el Sheet a mano y compártelo con la cuenta de servicio:")
        print(f"  arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com")
        print()
        print("Pasos:")
        print("  1. https://sheets.google.com → '+ En blanco'")
        print(f"  2. Renombrar a: {SHEET_FISIOS}")
        print("  3. Compartir → email de arriba como Editor")
        print("  4. Reejecutar este script")
        print()
        sys.exit(1)


def _idx_col(idx: int) -> str:
    """0 → A, 1 → B, ..., 25 → Z, 26 → AA"""
    out = ""
    while idx >= 0:
        out = chr(65 + (idx % 26)) + out
        idx = idx // 26 - 1
    return out


def _crear_hoja_listas(sh: gspread.Spreadsheet):
    """Crea/actualiza la hoja _LISTAS con todas las opciones de los dropdowns."""
    titulos = [w.title for w in sh.worksheets()]
    if "_LISTAS" in titulos:
        ws = sh.worksheet("_LISTAS")
        ws.clear()
        time.sleep(0.5)
    else:
        # Suficientes filas para la lista más larga
        max_filas = max(len(v) for v in LISTAS.values()) + 5
        ws = sh.add_worksheet(title="_LISTAS",
                                rows=max(max_filas, 100),
                                cols=len(LISTAS) + 2)
        time.sleep(0.5)
    # Cabecera
    headers = list(LISTAS.keys())
    cols_data = []
    max_filas = max(len(v) for v in LISTAS.values())
    for i in range(max_filas):
        row = []
        for k in headers:
            row.append(LISTAS[k][i] if i < len(LISTAS[k]) else "")
        cols_data.append(row)
    valores = [headers] + cols_data
    last_col = _idx_col(len(headers) - 1)
    ws.update(values=valores,
                range_name=f"A1:{last_col}{1+len(cols_data)}",
                value_input_option="RAW")
    # Formato cabecera
    ws.format(f"A1:{last_col}1", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "backgroundColor": {"red": 0.10, "green": 0.23, "blue": 0.42},
    })
    ws.freeze(rows=1)
    print(f"   ✅ _LISTAS creada con {len(headers)} listas")
    return ws


def _asegurar_hoja(sh: gspread.Spreadsheet, nombre: str,
                    cabeceras: list[str], color_rgb=(0.10, 0.23, 0.42)):
    """Asegura que la hoja existe con las cabeceras correctas."""
    titulos = [w.title for w in sh.worksheets()]
    if nombre in titulos:
        ws = sh.worksheet(nombre)
        actual = ws.row_values(1)
        if actual != cabeceras:
            # Reescribir solo cabecera, sin tocar datos
            last_col = _idx_col(len(cabeceras) - 1)
            ws.update(values=[cabeceras], range_name=f"A1:{last_col}1")
            print(f"   ⚠️ Cabecera de '{nombre}' actualizada (datos preservados)")
        else:
            print(f"   ✓ Hoja OK: {nombre}")
    else:
        ws = sh.add_worksheet(title=nombre,
                                rows=500, cols=len(cabeceras) + 5)
        last_col = _idx_col(len(cabeceras) - 1)
        ws.update(values=[cabeceras], range_name=f"A1:{last_col}1")
        ws.format(f"A1:{last_col}1", {
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "backgroundColor": {"red": color_rgb[0], "green": color_rgb[1], "blue": color_rgb[2]},
        })
        ws.freeze(rows=1)
        print(f"   ✅ Hoja creada: {nombre}")
    time.sleep(0.5)
    return ws


def _aplicar_validaciones(sh: gspread.Spreadsheet, ws_target,
                            cols_estructura: list[tuple],
                            ws_listas, ws_jugadores):
    """Aplica validaciones (dropdowns) a cada columna de la pestaña.

    cols_estructura: lista de (nombre, validacion) donde validacion es:
       - clave de LISTAS → ONE_OF_RANGE apuntando a _LISTAS!<col>2:<col>1000
       - "JUGADOR" → ONE_OF_RANGE apuntando a JUGADORES!B2:B100
       - "FECHA" → DATE_IS_VALID
       - "NUMERO" → NUMBER_GREATER_THAN_EQ 0
       - None → sin validación (texto libre)
    """
    listas_cols = list(LISTAS.keys())  # mismo orden que en _crear_hoja_listas
    requests = []

    for col_idx, (nombre, val) in enumerate(cols_estructura):
        if val is None:
            continue
        rango = {
            "sheetId": ws_target.id,
            "startRowIndex": 1,    # excluir cabecera
            "endRowIndex": 1000,
            "startColumnIndex": col_idx,
            "endColumnIndex": col_idx + 1,
        }
        condition = None
        if val == "JUGADOR":
            condition = {
                "type": "ONE_OF_RANGE",
                "values": [{"userEnteredValue":
                            f"=JUGADORES!B2:B{ws_jugadores.row_count}"}],
            }
        elif val == "FECHA":
            condition = {"type": "DATE_IS_VALID"}
        elif val == "NUMERO":
            condition = {
                "type": "NUMBER_GREATER_THAN_EQ",
                "values": [{"userEnteredValue": "0"}],
            }
        elif val in LISTAS:
            col_letra = _idx_col(listas_cols.index(val))
            condition = {
                "type": "ONE_OF_RANGE",
                "values": [{"userEnteredValue":
                            f"=_LISTAS!{col_letra}2:{col_letra}{1+len(LISTAS[val])}"}],
            }
        else:
            continue

        requests.append({
            "setDataValidation": {
                "range": rango,
                "rule": {
                    "condition": condition,
                    # showCustomUi=True → muestra dropdown UI
                    "showCustomUi": True,
                    # strict=False → permite valores fuera de la lista
                    # (útil si añaden uno nuevo sin actualizar _LISTAS)
                    "strict": False,
                }
            }
        })

    if requests:
        sh.batch_update({"requests": requests})
        print(f"   ✅ {len(requests)} validaciones aplicadas")


def _ocultar_hojas_internas(sh: gspread.Spreadsheet):
    """Marca _LISTAS y _META como ocultas para que los fisios no las vean."""
    requests = []
    for nombre in ("_LISTAS", "_META"):
        try:
            ws = sh.worksheet(nombre)
            requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "hidden": True},
                    "fields": "hidden",
                }
            })
        except Exception:
            pass
    if requests:
        sh.batch_update({"requests": requests})
        print(f"   ✅ Hojas internas ocultas")


def _sincronizar_jugadores(sh_fisios, sh_principal):
    """Copia el roster del Sheet principal a la hoja JUGADORES del de fisios."""
    print("👥 Sincronizando JUGADORES desde roster principal…")
    ws_src = sh_principal.worksheet("JUGADORES_ROSTER")
    src_data = ws_src.get_all_records()
    if not src_data:
        print("   ⚠️ JUGADORES_ROSTER vacío, no se copia nada")
        return

    ws_dst = sh_fisios.worksheet("JUGADORES")
    ws_dst.batch_clear(["A2:Z"])
    time.sleep(1)

    nombres_primer = {"HERRERO", "GARCIA", "J.HERRERO", "J.GARCIA",
                       "CECILIO", "CHAGUINHA", "RAUL", "HARRISON",
                       "RAYA", "JAVI", "PANI", "PIRATA", "BARONA", "CARLOS"}

    filas = []
    for j in src_data:
        nombre = str(j.get("nombre", "")).strip().upper()
        if not nombre:
            continue
        d = j.get("dorsal", "")
        try:
            d = int(float(d)) if d not in ("", None) else ""
        except (ValueError, TypeError):
            d = ""
        equipo = "PRIMER" if nombre in nombres_primer else "FILIAL"
        activo = str(j.get("activo", "TRUE")).upper()
        if activo not in ("TRUE", "FALSE"):
            activo = "TRUE"
        filas.append([str(d) if d != "" else "",
                       nombre,
                       str(j.get("posicion", "")).upper(),
                       equipo,
                       activo])

    if filas:
        ws_dst.update(values=filas, range_name=f"A2:E{len(filas)+1}",
                        value_input_option="USER_ENTERED")
        print(f"   ✅ {len(filas)} jugadores sincronizados")


def _migrar_lesiones(sh_fisios, sh_principal):
    """Migra las lesiones del Sheet principal al de fisios.
    Solo añade lesiones nuevas (idempotente)."""
    print("🏥 Migrando LESIONES desde Sheet principal…")
    try:
        ws_src = sh_principal.worksheet("LESIONES")
        src = ws_src.get_all_values()
    except Exception as e:
        print(f"   ⚠️ No se pudo leer LESIONES del principal: {e}")
        return
    if len(src) < 3:
        print("   ⚠️ LESIONES vacía o sin datos")
        return

    cab_viejas = src[1]  # fila 2 son las cabeceras reales
    data_viejas = src[2:]

    # Mapping cabeceras viejas → nuevas
    map_cols = {
        "JUGADOR": "jugador",
        "FECHA LESIÓN": "fecha_lesion",
        "MOMENTO": "turno",       # M/T/P
        "TIPO LESIÓN": "tipo_tejido",
        "ZONA CORPORAL": "zona_corporal",
        "LADO": "lado",
        "MECANISMO": "mecanismo",
        "DIAGNÓSTICO": "diagnostico",
        "DÍAS BAJA EST.": "dias_baja_estimados",
        "PRUEBAS MÉDICAS": "pruebas_medicas",
        "ESTADO ACTUAL": "estado_actual",
        "FECHA ALTA": "fecha_alta",
        "RECAÍDA": "recaida",
        "NOTAS INICIALES": "notas",
    }

    # Roster para mapear jugador → dorsal
    ws_roster = sh_fisios.worksheet("JUGADORES")
    roster_rows = ws_roster.get_all_records()
    nombre_a_dorsal = {str(r.get("nombre", "")).strip().upper(): r.get("dorsal", "")
                          for r in roster_rows if r.get("nombre")}

    # Lesiones ya existentes en destino (idempotencia)
    ws_dst = sh_fisios.worksheet("LESIONES")
    existing = ws_dst.get_all_records()
    existing_keys = {(str(r.get("jugador", "")).upper(),
                       str(r.get("fecha_lesion", "")))
                       for r in existing if r.get("jugador") and r.get("fecha_lesion")}
    print(f"   Lesiones ya en destino: {len(existing_keys)}")

    cab_nueva = [c[0] for c in COLS_LESIONES]
    nuevas = []
    siguiente_id = len(existing) + 1
    for fila in data_viejas:
        if not fila or all(not str(c).strip() or str(c).strip().startswith("=")
                            for c in fila):
            continue
        row_dict_vieja = {cab_viejas[j]: (fila[j] if j < len(fila) else "")
                            for j in range(len(cab_viejas))}
        if not row_dict_vieja.get("JUGADOR") or row_dict_vieja["JUGADOR"].startswith("="):
            continue
        jugador = str(row_dict_vieja.get("JUGADOR", "")).strip().upper()
        fecha = str(row_dict_vieja.get("FECHA LESIÓN", "")).strip()
        if not jugador or not fecha:
            continue
        if (jugador, fecha) in existing_keys:
            continue

        row_dict_nueva = {}
        for col_vieja, col_nueva in map_cols.items():
            val = row_dict_vieja.get(col_vieja, "")
            if isinstance(val, str) and val.startswith("="):
                val = ""
            row_dict_nueva[col_nueva] = val

        row_dict_nueva["id_lesion"] = f"L{siguiente_id:04d}"
        siguiente_id += 1
        row_dict_nueva["dorsal"] = nombre_a_dorsal.get(jugador, "")
        # turno por defecto si no está
        if not row_dict_nueva.get("turno"):
            row_dict_nueva["turno"] = ""
        # tipo_sesion por defecto: ENTRENO
        if not row_dict_nueva.get("tipo_sesion"):
            row_dict_nueva["tipo_sesion"] = "ENTRENO"
        # gravedad: si dias_baja_est es alto, deducir
        try:
            dias_est = int(float(row_dict_nueva.get("dias_baja_estimados") or 0))
            if dias_est >= 30:
                row_dict_nueva["gravedad"] = "GRAVE"
            elif dias_est >= 7:
                row_dict_nueva["gravedad"] = "MODERADA"
            elif dias_est > 0:
                row_dict_nueva["gravedad"] = "LEVE"
        except (ValueError, TypeError):
            pass

        fila_nueva = [str(row_dict_nueva.get(h, "")) for h in cab_nueva]
        nuevas.append(fila_nueva)

    if not nuevas:
        print("   ✓ No hay lesiones nuevas que migrar")
        return

    todas_dst = ws_dst.get_all_values()
    primera_libre = len(todas_dst) + 1
    last_col = _idx_col(len(cab_nueva) - 1)
    ws_dst.update(values=nuevas,
                    range_name=f"A{primera_libre}:{last_col}{primera_libre+len(nuevas)-1}",
                    value_input_option="USER_ENTERED")
    print(f"   ✅ {len(nuevas)} lesiones migradas")


def _guardar_meta(sh_fisios):
    """Guarda metadatos del último sync."""
    import datetime as dt
    ws = sh_fisios.worksheet("_META")
    ws.batch_clear(["A2:C"])
    time.sleep(0.5)
    rows = [
        ["sheet_id", sh_fisios.id, dt.datetime.now().isoformat()],
        ["sheet_principal", SHEET_PRINCIPAL, dt.datetime.now().isoformat()],
        ["estructura_version", "v2_3pestanas", dt.datetime.now().isoformat()],
    ]
    ws.update(values=rows, range_name=f"A2:C{1+len(rows)}",
                value_input_option="USER_ENTERED")
    print(f"   ✅ _META actualizada")


def main():
    print("=" * 70)
    print("CONFIGURAR SHEET DE LESIONES, TRATAMIENTOS Y TEMPERATURA")
    print("=" * 70)
    print()

    client = _connect()
    sh = _abrir_sheet(client)

    # 1) _LISTAS (auxiliar)
    print("📋 Hoja _LISTAS (opciones de los dropdowns)…")
    _crear_hoja_listas(sh)

    # 2) JUGADORES (referencia, debe estar antes de las pestañas que la usan)
    print()
    print("📋 Hoja JUGADORES…")
    ws_jug = _asegurar_hoja(sh, "JUGADORES", COLS_JUGADORES,
                              color_rgb=(0.30, 0.50, 0.30))

    # Sincronizar jugadores ANTES de aplicar validaciones (que dependen de ella)
    print()
    sh_principal = client.open(SHEET_PRINCIPAL)
    _sincronizar_jugadores(sh, sh_principal)

    # 3) Pestañas principales
    print()
    print("📋 Hoja LESIONES…")
    cab_les = [c[0] for c in COLS_LESIONES]
    ws_les = _asegurar_hoja(sh, "LESIONES", cab_les,
                              color_rgb=(0.72, 0.11, 0.11))

    print()
    print("📋 Hoja TRATAMIENTOS…")
    cab_tr = [c[0] for c in COLS_TRATAMIENTOS]
    ws_tr = _asegurar_hoja(sh, "TRATAMIENTOS", cab_tr,
                             color_rgb=(0.10, 0.45, 0.30))

    print()
    print("📋 Hoja TEMPERATURA…")
    cab_temp = [c[0] for c in COLS_TEMPERATURA]
    ws_temp = _asegurar_hoja(sh, "TEMPERATURA", cab_temp,
                                color_rgb=(0.85, 0.45, 0.10))

    print()
    print("📋 Hoja _META…")
    _asegurar_hoja(sh, "_META", COLS_META, color_rgb=(0.5, 0.5, 0.5))

    # 4) Aplicar validaciones (dropdowns) en cada pestaña
    print()
    print("✅ Aplicando validaciones en LESIONES…")
    ws_listas = sh.worksheet("_LISTAS")
    _aplicar_validaciones(sh, ws_les, COLS_LESIONES, ws_listas, ws_jug)
    time.sleep(1)
    print("✅ Aplicando validaciones en TRATAMIENTOS…")
    _aplicar_validaciones(sh, ws_tr, COLS_TRATAMIENTOS, ws_listas, ws_jug)
    time.sleep(1)
    print("✅ Aplicando validaciones en TEMPERATURA…")
    _aplicar_validaciones(sh, ws_temp, COLS_TEMPERATURA, ws_listas, ws_jug)
    time.sleep(1)

    # 5) Ocultar hojas internas (_LISTAS, _META)
    print()
    print("🙈 Ocultando hojas internas…")
    _ocultar_hojas_internas(sh)

    # 6) Migrar lesiones del sheet principal
    print()
    _migrar_lesiones(sh, sh_principal)

    # 7) Metadatos
    print()
    print("📌 Guardando metadatos…")
    _guardar_meta(sh)

    print()
    print("=" * 70)
    print(f"✅ Sheet de fisios listo: '{SHEET_FISIOS}'")
    print(f"   ID: {sh.id}")
    print(f"   URL: https://docs.google.com/spreadsheets/d/{sh.id}/")
    print()
    print("Próximos pasos:")
    print("  1. Abre la URL → entra a la pestaña LESIONES.")
    print("     Comprueba que los dropdowns funcionan al hacer click en una celda.")
    print("  2. Comparte con los fisios (botón 'Compartir' en Sheets):")
    print("     · Email del fisio + permiso Editor")
    print("     · IMPORTANTE: NO les des acceso al Sheet principal")
    print("  3. Ejecuta src/calcular_vistas_fisios.py para rellenar")
    print("     las columnas calculadas (días baja real, sesiones perdidas, asimetrías).")


if __name__ == "__main__":
    sys.exit(main())
