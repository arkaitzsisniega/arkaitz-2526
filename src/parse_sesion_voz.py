"""
parse_sesion_voz.py — Procesa una transcripción de audio describiendo una
sesión de entrenamiento, la estructura con Gemini y la inserta en la
hoja SESIONES.

Uso (lee transcripción de stdin):
  echo "Hoy hemos hecho tec-tac de 75 minutos por la mañana" | \\
    python3 src/parse_sesion_voz.py

  Args opcionales:
    argv[1] = fecha YYYY-MM-DD (default: hoy)

Variables de entorno:
  GEMINI_API_KEY   (obligatoria) — key de aistudio.google.com.
  GEMINI_MODEL     (opcional, default gemini-2.5-flash-lite).
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from datetime import date
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# Cargar .env del bot (si lo encuentra) para tener GEMINI_API_KEY disponible
try:
    from dotenv import load_dotenv
    _ROOT = Path(__file__).parent.parent.resolve()
    for _envp in [_ROOT / "telegram_bot" / ".env", _ROOT / ".env"]:
        if _envp.is_file():
            load_dotenv(_envp)
            break
except Exception:
    pass

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
SHEET_NAME = "Arkaitz - Datos Temporada 2526"
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"

# Tipos válidos en el dropdown de SESIONES (ver src/setup_gsheets.py)
TIPOS_VALIDOS = [
    "FISICO", "TEC-TAC", "GYM", "RECUP", "PARTIDO", "PORTEROS",
    "MATINAL", "GYM+TEC-TAC", "FISICO+TEC-TAC",
]
TURNOS_VALIDOS = ["M", "T", "P"]
COMPETICIONES_VALIDAS = [
    "LIGA", "COPA DEL REY", "COPA ESPAÑA", "COPA MOSTOLES",
    "COPA RIBERA", "SUPERCOPA", "PRE-TEMPORADA", "AMISTOSO",
]


# ─── Configurar Gemini ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ─── Prompt y schema ────────────────────────────────────────────────────────
PROMPT_EXTRACTOR = """\
Tarea: extraer datos de una sesión de entrenamiento de fútbol sala a partir
de una descripción en español.

REGLA ABSOLUTA: tu salida COMPLETA debe ser un único objeto JSON. Nada de
explicaciones, nada de markdown, nada de comentarios. La respuesta debe
empezar con una llave de apertura y terminar con una llave de cierre.

Esquema:
{
  "turno": "M" | "T" | "P",
  "tipo_sesion": "FISICO" | "TEC-TAC" | "GYM" | "RECUP" | "PARTIDO"
                 | "PORTEROS" | "MATINAL" | "GYM+TEC-TAC" | "FISICO+TEC-TAC",
  "minutos": <int>,
  "competicion": "LIGA" | "COPA DEL REY" | "COPA ESPAÑA" | "COPA MOSTOLES"
                 | "COPA RIBERA" | "SUPERCOPA" | "PRE-TEMPORADA"
                 | "AMISTOSO" | null,
  "descripcion": "<resumen breve de los bloques>"
}

Reglas para deducir el TURNO:
- "matinal", "mañana", "antes del partido" → M
- "tarde", "después de comer", "20:30", "21:00" → T
- "partido por la mañana" (excepcional) → P
- Si no se menciona, asumir M

Reglas para deducir el TIPO_SESION:
- "matinal" o sesión corta el día de partido → MATINAL
- "partido", "competición", "liga", "copa" → PARTIDO
- "gym + tec-tac" o "fuerza + táctica" combinado → GYM+TEC-TAC
- "físico + tec-tac" combinado → FISICO+TEC-TAC
- Solo gimnasio / fuerza → GYM
- Solo físico / atletismo → FISICO
- Solo técnico-táctico (rondos, situaciones, partidillos) → TEC-TAC
- Recuperación, regenerativo, descarga → RECUP
- Sesión específica de porteros → PORTEROS
- Si la sesión incluye TANTO técnico-táctico COMO físico/gym, prefiere los
  tipos combinados.

MINUTOS: si se menciona la duración, ponerla. Si dan la suma de bloques
(8+7+8+4+4+3=34), suma. Si no hay duración, pon null.

COMPETICION: solo aplica si TIPO_SESION = PARTIDO. Por defecto LIGA si dice
"partido" sin especificar; null en sesiones de entrenamiento.

DESCRIPCION: texto breve listando los bloques con sus minutos. Ejemplo:
"8 min activación mental + 7 min calentamiento + 8 min rondeo 3v1 + 4 min
banda + 4 min córner + 3 min YO-YO".

Texto a procesar:
__TEXTO__

Devuelve SOLO el JSON.
"""


JSON_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "turno": {"type": "string", "enum": ["M", "T", "P"]},
        "tipo_sesion": {"type": "string", "enum": TIPOS_VALIDOS},
        "minutos": {"type": ["integer", "null"]},
        "competicion": {"type": ["string", "null"], "enum": COMPETICIONES_VALIDAS + [None]},
        "descripcion": {"type": "string"},
    },
    "required": ["turno", "tipo_sesion", "descripcion"],
})


def claude_extraer(transcripcion: str) -> dict:
    """Mantiene el nombre histórico por compatibilidad. Internamente usa Gemini."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en el entorno.")
    prompt = PROMPT_EXTRACTOR.replace("__TEXTO__", transcripcion)
    model = genai.GenerativeModel(model_name=GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "max_output_tokens": 512,
        },
    )
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("Gemini devolvió respuesta vacía.")
    cand = candidates[0]
    content = getattr(cand, "content", None)
    if not content or not getattr(content, "parts", None):
        finish = getattr(cand, "finish_reason", "?")
        raise RuntimeError(f"Gemini terminó sin contenido (finish_reason={finish}).")
    text = ""
    for p in content.parts:
        t = getattr(p, "text", None)
        if t:
            text += t
    text = text.strip()
    # Intentar parsear directamente
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: buscar el primer objeto JSON
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"Gemini no devolvió JSON parseable: {text[:300]}")
    return json.loads(m.group(0))


# ─── Conexión Sheet ─────────────────────────────────────────────────────────
def gs_client():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


def calcular_semana_iso(fecha_iso: str) -> str:
    """Devuelve el número de semana (entero ISO) como string."""
    from datetime import datetime
    d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    return str(d.isocalendar().week)


def apuntar_en_sesiones(sh, fecha_iso: str, turno: str, tipo_sesion: str,
                          minutos, competicion) -> dict:
    """Inserta o actualiza una fila en la hoja SESIONES.
    Si ya existe (FECHA, TURNO, TIPO_SESION) la sobreescribe.
    Devuelve dict con la fila guardada y el rango."""
    ws = sh.worksheet("SESIONES")
    rows = ws.get_all_values()
    # Buscar fila existente con misma fecha+turno+tipo (formato fecha
    # puede variar: 2026-04-30 o 30-04-2026)
    from datetime import datetime
    d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    fecha_alt = d.strftime("%d-%m-%Y")
    row_idx = None
    for i, r in enumerate(rows[1:], start=2):  # 1-indexed sheet
        if (r and len(r) >= 4
                and r[0].strip() in (fecha_iso, fecha_alt)
                and r[2].strip() == turno
                and r[3].strip() == tipo_sesion):
            row_idx = i
            break
    semana = calcular_semana_iso(fecha_iso)
    fila = [
        fecha_iso,
        semana,
        turno,
        tipo_sesion,
        str(minutos) if minutos is not None else "",
        competicion or "",
    ]
    if row_idx is not None:
        ws.update(values=[fila], range_name=f"A{row_idx}:F{row_idx}")
        return {"accion": "ACTUALIZADA", "fila": row_idx, "datos": fila}
    else:
        # Append al final
        next_row = len(rows) + 1
        ws.update(values=[fila], range_name=f"A{next_row}:F{next_row}")
        return {"accion": "AÑADIDA", "fila": next_row, "datos": fila}


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    transcripcion = sys.stdin.read().strip()
    if not transcripcion:
        print(MSG_SEP)
        print("❌ No he recibido transcripción para procesar.")
        return 1

    fecha_iso = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"📝 Transcripción ({len(transcripcion)} chars): {transcripcion[:200]}...",
          file=sys.stderr)
    print(f"📅 Fecha: {fecha_iso}", file=sys.stderr)

    try:
        datos = claude_extraer(transcripcion)
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Error parseando con Claude: {e}")
        return 1

    turno = datos.get("turno", "M")
    tipo_sesion = datos.get("tipo_sesion", "TEC-TAC")
    minutos = datos.get("minutos")
    competicion = datos.get("competicion")
    descripcion = datos.get("descripcion", "")

    # Validar
    if turno not in TURNOS_VALIDOS:
        turno = "M"
    if tipo_sesion not in TIPOS_VALIDOS:
        # Buscar cualquier match aproximado, sino TEC-TAC
        for t in TIPOS_VALIDOS:
            if t.upper() in tipo_sesion.upper():
                tipo_sesion = t
                break
        else:
            tipo_sesion = "TEC-TAC"

    try:
        sh = gs_client()
        resultado = apuntar_en_sesiones(sh, fecha_iso, turno, tipo_sesion,
                                          minutos, competicion)
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Error escribiendo en SESIONES: {e}")
        return 1

    # Mensaje al usuario
    print(MSG_SEP)
    print(f"✅ *Sesión {resultado['accion'].lower()}*\n")
    print(f"📅 *Fecha:* {fecha_iso}")
    print(f"🕐 *Turno:* {turno}")
    print(f"🏃 *Tipo:* {tipo_sesion}")
    if minutos is not None:
        print(f"⏱ *Minutos:* {minutos}")
    if competicion:
        print(f"🏆 *Competición:* {competicion}")
    if descripcion:
        print(f"\n📋 *Descripción:* {descripcion}")
    print(f"\n_Fila {resultado['fila']} de SESIONES._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
