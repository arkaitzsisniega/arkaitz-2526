"""
sincronizar_lanzamientos.py — Lee el Sheet "Lanzamientos(10m_penaltis)"
(que rellena el cuerpo técnico al visualizar partidos rivales) y vuelca
las filas a la hoja EST_SCOUTING_PEN_10M del Sheet principal.

Caso de uso:
- El cuerpo técnico añade filas al Sheet de Lanzamientos según va viendo
  partidos del rival.
- Este script las normaliza y las copia a EST_SCOUTING_PEN_10M del
  principal, que es lo que Streamlit pinta en la pestaña Scouting →
  Penaltis/10m. Idempotente: borra y reescribe la hoja del principal
  con el contenido actualizado.

Adicionalmente, detecta filas con info INCOMPLETA del portero (faltan
columnas Des./Gesto/Mov del portero) e imprime aviso al final, útil
para que Arkaitz sepa qué le falta meter.

Uso:
  /usr/bin/python3 src/sincronizar_lanzamientos.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_PRINCIPAL = "Arkaitz - Datos Temporada 2526"
SHEET_LANZ = "Lanzamientos(10m_penaltis)"
MSG_SEP = "---MSG---"


def conectar():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _iso(fecha_str: str) -> str:
    """Convierte 'dd/mm/aa' o 'dd/mm/aaaa' o 'aaaa-mm-dd' en 'YYYY-MM-DD'.
    Si no se reconoce, devuelve el original."""
    s = (fecha_str or "").strip()
    if not s:
        return ""
    # Ya en ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # dd/mm/yy o dd/mm/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", s)
    if m:
        d, mo, y = m.groups()
        y = "20" + y if len(y) == 2 else y
        try:
            dt = datetime(int(y), int(mo), int(d))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return s
    return s


def _es_gol(resultado: str) -> str:
    """'gol'→TRUE · 'parada'/'fuera'/'palo'/'bloqueado'→FALSE · vacío→''."""
    r = (resultado or "").strip().lower()
    if not r:
        return ""
    if "gol" in r and "fuera" not in r:
        return "TRUE"
    return "FALSE"


def _pierna(pierna: str) -> str:
    """'d'→'DCHA' · 'i'→'IZDA'. Cualquier otra cosa se pasa tal cual."""
    p = (pierna or "").strip().lower()
    if p in ("d", "dch", "dcha", "derecha"):
        return "DCHA"
    if p in ("i", "izq", "izda", "izquierda"):
        return "IZDA"
    return pierna


def leer_lanzamientos(gc):
    """Lee el Sheet del cuerpo técnico y devuelve lista de dicts
    normalizados (vacíos quitados, sin columnas con \\n raros)."""
    try:
        ss = gc.open(SHEET_LANZ)
    except gspread.exceptions.SpreadsheetNotFound:
        return []
    ws = ss.worksheet("Hoja 1")
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return []
    # Normalizar nombres de columna (quitar saltos y aclaraciones entre paréntesis)
    raw_hdr = vals[0]
    hdr = [re.sub(r"\s*\n\s*\(.*\)", "", h).strip() for h in raw_hdr]
    # Mapeo desde nombre normalizado → clave canónica del principal
    MAPA = {
        "Fecha":                "fecha",
        "Tipo":                 "tipo_lanzamiento",
        "Jugador":              "tirador_nombre",
        "Pierna":               "tirador_lateralidad",
        "Club":                 "tirador_club",
        "Rival":                "rival",  # no existe en principal; se ignora luego
        "Portero":              "portero_nombre",
        "Competición":          "competicion",
        "Zona de disparo":      "zona_destino",
        "Resultado":            "es_gol",     # se convierte a TRUE/FALSE
        "Des. Portero":         "portero_direccion",
        "Gesto portero":        "portero_forma",
        "Mov. Portero":         "portero_avance",
        "Marcador":             "marcador_momento",
    }
    out = []
    for row in vals[1:]:
        if not any(c.strip() for c in row):
            continue  # fila completamente vacía
        rec = {}
        for i, col in enumerate(hdr):
            valor = row[i].strip() if i < len(row) else ""
            clave = MAPA.get(col)
            if clave:
                rec[clave] = valor
        out.append(rec)
    return out


def detectar_incompletos(lanz):
    """Devuelve lista de filas con info insuficiente del portero."""
    incompletos = []
    for r in lanz:
        # Crítico: si falta cómo se desplaza el portero (cualquiera de las 3 cols)
        falta = [c for c in ("portero_direccion", "portero_forma", "portero_avance")
                 if not r.get(c, "").strip()]
        if falta:
            incompletos.append({
                "fecha": r.get("fecha", "?"),
                "tirador": r.get("tirador_nombre", "?"),
                "club": r.get("tirador_club", "?"),
                "rival": r.get("rival", "?"),
                "falta": falta,
            })
    return incompletos


def volcar_a_principal(gc, lanz, dry_run=False):
    """Reemplaza el contenido de EST_SCOUTING_PEN_10M del principal con
    las filas normalizadas."""
    ss = gc.open(SHEET_PRINCIPAL)
    try:
        ws = ss.worksheet("EST_SCOUTING_PEN_10M")
    except gspread.exceptions.WorksheetNotFound:
        # Si no existe, créala con la cabecera estándar
        ws = ss.add_worksheet("EST_SCOUTING_PEN_10M", rows=400, cols=17)

    headers = ws.row_values(1)
    if not headers:
        headers = [
            "partido_id", "fecha", "competicion", "tipo_lanzamiento",
            "equipo_lanzador", "tirador_nombre", "tirador_club",
            "tirador_lateralidad", "portero_nombre", "portero_club",
            "zona_destino", "es_gol", "portero_direccion",
            "portero_forma", "portero_avance", "marcador_momento", "notas",
        ]
        if not dry_run:
            ws.update("A1", [headers])

    filas = []
    for r in lanz:
        fila = []
        for col in headers:
            v = r.get(col, "")
            if col == "fecha":
                v = _iso(v)
            elif col == "es_gol":
                v = _es_gol(r.get("es_gol", ""))
            elif col == "tirador_lateralidad":
                v = _pierna(r.get("tirador_lateralidad", ""))
            elif col == "partido_id":
                # Si no viene del Sheet de Lanzamientos, generamos un id
                # legible "RIVAL.FECHA" para que cruce con el resto.
                fecha = _iso(r.get("fecha", ""))
                rival = (r.get("rival", "") or "").strip().upper().replace(" ", "_")
                v = f"{rival}.{fecha}" if rival and fecha else ""
            elif col == "equipo_lanzador":
                # Si el club del tirador es Movistar Inter (variantes), es AFAVOR
                club = (r.get("tirador_club", "") or "").upper()
                if "INTER" in club or "MOVISTAR" in club:
                    v = "INTER"
                elif club:
                    v = club  # otro equipo (rival lanza)
                else:
                    v = ""
            fila.append(v)
        filas.append(fila)

    print(f"  Filas normalizadas: {len(filas)}")
    if dry_run:
        print("  (DRY-RUN: no escribo en el Sheet principal)")
        return len(filas)

    # Limpiar todo (excepto cabecera) y rescribir
    if ws.row_count > 1:
        rango_clear = f"A2:Q{max(ws.row_count, len(filas) + 1)}"
        try:
            ws.batch_clear([rango_clear])
        except Exception:
            pass
    if filas:
        rng = f"A2:Q{len(filas) + 1}"
        ws.update(rng, filas)
    return len(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="No escribe en el Sheet principal, solo audita.")
    args = ap.parse_args()

    gc = conectar()
    print(f"Leyendo '{SHEET_LANZ}'…")
    lanz = leer_lanzamientos(gc)
    print(f"  → {len(lanz)} filas con datos")

    if not lanz:
        print(MSG_SEP)
        print(
            f"📭 El Sheet *{SHEET_LANZ}* está vacío. Cuando el cuerpo técnico "
            "empiece a meter lanzamientos, este script los volcará a "
            "EST_SCOUTING_PEN_10M y los verás en la pestaña Scouting del dashboard."
        )
        return

    incompletos = detectar_incompletos(lanz)

    print(f"Volcando a EST_SCOUTING_PEN_10M del Sheet principal…")
    n = volcar_a_principal(gc, lanz, dry_run=args.dry_run)

    # ── Resumen para el bot ─────────────────────────────────────────
    print(MSG_SEP)
    head = "🔬 *DRY-RUN — sin escribir*" if args.dry_run else "✅ *Lanzamientos sincronizados*"
    print(head)
    print(f"📥 Leídos:      *{len(lanz)}* lanzamientos del Sheet del cuerpo técnico.")
    print(f"📤 Volcados:    *{n}* filas a EST_SCOUTING_PEN_10M del principal.")
    if incompletos:
        print(f"⚠️  Incompletos: *{len(incompletos)}* lanzamientos sin info del portero.")
        print()
        print("Lanzamientos con datos del portero a medias (faltan Des./Gesto/Mov):")
        # Imprimir máximo 10 para no saturar
        for inc in incompletos[:10]:
            falta = ", ".join(inc["falta"]).replace("portero_", "")
            print(f"  · {inc['fecha']} · {inc['tirador']} ({inc['club']}) vs {inc['rival']} "
                  f"→ falta: {falta}")
        if len(incompletos) > 10:
            print(f"  ... y {len(incompletos) - 10} más.")
        print()
        print(
            "💡 Para completar, abre el Sheet *Lanzamientos(10m_penaltis)* y "
            "rellena las columnas Des./Gesto/Mov del portero en esas filas. "
            "Vuelve a lanzar /consolidar y se vuelven a volcar."
        )
    else:
        print("✓ Todos los lanzamientos tienen info completa del portero.")


if __name__ == "__main__":
    main()
