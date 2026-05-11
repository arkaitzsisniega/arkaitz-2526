"""
parse_goles_voz.py — Procesa la transcripción de Arkaitz describiendo
los goles de un partido EN ORDEN CRONOLÓGICO y rellena la columna
`descripcion` de cada gol en EST_EVENTOS.

Uso:
  Stdin: transcripción (audio→Whisper o texto directo).
  Arg1 (opcional): partido_id. Si no se pasa, se usa el último partido
                   en EST_TOTALES_PARTIDO con eventos.

Ejemplo de transcripción:
  "El 1-0 fue de Raúl al primer palo tras pase de Pani desde la banda
   derecha. El 1-1 el rival tras una mala salida nuestra. El 2-1 lo
   marcó Javi de cabeza en córner."

Lógica:
  1. Whisper o texto ya viene del bot.
  2. Gemini extrae lista cronológica de descripciones.
  3. Localizar todos los eventos de gol (equipo_marca INTER + RIVAL)
     del partido en EST_EVENTOS, ordenados por minuto.
  4. Asignar cada descripción al evento correspondiente (por orden).
  5. Si hay descripciones extra o eventos sin descripción, avisar.
  6. Escribir columna `descripcion` con batch_update.
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "src"))

# Cargar .env del bot para tener GEMINI_API_KEY
try:
    from dotenv import load_dotenv
    for env_path in (ROOT / "telegram_bot" / ".env", ROOT / ".env"):
        if env_path.exists():
            load_dotenv(env_path)
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


PROMPT_EXTRACTOR = """\
Eres un asistente que extrae descripciones de goles de un partido de
fútbol sala a partir del relato del entrenador.

El entrenador describe los goles EN ORDEN CRONOLÓGICO (1-0, luego 1-1
o 2-0, etc.). Cada descripción suele empezar por el marcador del gol
(ej. "El 1-0...", "El 2-1...", "El segundo gol del rival..."), pero
no siempre.

Devuelve un JSON con esta estructura EXACTA:

{
  "goles": [
    {
      "marcador": "1-0",
      "equipo": "INTER",
      "descripcion": "Pase de Pani desde la banda al pivot, Raúl marca a la media vuelta."
    },
    {
      "marcador": "1-1",
      "equipo": "RIVAL",
      "descripcion": "Mala salida nuestra, ellos roban y marcan a puerta vacía."
    }
  ]
}

REGLAS:
- equipo = "INTER" si lo mete nuestro equipo, "RIVAL" si lo mete el rival.
- marcador = el marcador justo TRAS el gol descrito (formato "GF-GC"
  desde la perspectiva de INTER), si Arkaitz lo menciona. Si no lo
  menciona, déjalo "".
- descripcion = lo que cuenta Arkaitz, parafraseado/limpio en una sola
  línea. Mantén nombres de jugadores en MAYÚSCULAS (PANI, RAUL, JAVI,
  HERRERO, GARCIA, etc.).
- ORDEN: igual que en el relato, cronológico.

Si el texto no parece describir goles (ej. habla de otra cosa), devuelve
{"goles": []}.

TEXTO DEL ENTRENADOR:
__TEXTO__
"""


def _open_sheet():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


def gemini_extraer(transcripcion: str) -> list[dict]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en el entorno.")
    prompt = PROMPT_EXTRACTOR.replace("__TEXTO__", transcripcion)
    model = genai.GenerativeModel(model_name=GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "max_output_tokens": 2048,
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
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise RuntimeError(f"Gemini no devolvió JSON parseable: {text[:300]}")
        data = json.loads(m.group(0))
    return data.get("goles", []) or []


def _ultimo_partido_con_eventos(ss) -> str | None:
    """Devuelve el partido_id del último partido (por fecha) que tenga
    al menos un evento de gol en EST_EVENTOS."""
    ws_e = ss.worksheet("EST_EVENTOS")
    rows = ws_e.get_all_values()
    if len(rows) < 2:
        return None
    header = rows[0]
    try:
        i_pid = header.index("partido_id")
        i_fec = header.index("fecha")
    except ValueError:
        return None
    partidos = {}
    for r in rows[1:]:
        if len(r) <= max(i_pid, i_fec):
            continue
        pid = r[i_pid].strip()
        fec = r[i_fec].strip()
        if pid and fec:
            partidos[pid] = fec
    if not partidos:
        return None
    return max(partidos.keys(), key=lambda p: partidos[p])


def _eventos_del_partido(ss, partido_id: str):
    """Devuelve lista de filas (en EST_EVENTOS) del partido dado,
    cada una con {fila_idx, minuto, equipo_marca, goleador, ...}.
    Ordenadas por minuto cronológico."""
    ws_e = ss.worksheet("EST_EVENTOS")
    rows = ws_e.get_all_values()
    if len(rows) < 2:
        return ws_e, [], []
    header = rows[0]
    try:
        i_pid = header.index("partido_id")
        i_min = header.index("minuto")
        i_eq = header.index("equipo_marca")
        i_gol = header.index("goleador")
    except ValueError:
        return ws_e, header, []

    eventos = []
    for fila_1idx, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_pid, i_min, i_eq):
            continue
        if r[i_pid].strip() != partido_id:
            continue
        try:
            minuto = float(r[i_min].replace(",", "."))
        except (ValueError, TypeError):
            minuto = 999
        eventos.append({
            "fila_idx": fila_1idx,  # 1-based para batch_update
            "minuto": minuto,
            "equipo_marca": r[i_eq].strip().upper(),
            "goleador": r[i_gol].strip() if len(r) > i_gol else "",
            "raw_row": r,
        })
    eventos.sort(key=lambda e: e["minuto"])
    return ws_e, header, eventos


def actualizar_descripciones(ss, partido_id: str, goles_extraidos: list[dict],
                              dry: bool = False) -> dict:
    ws_e, header, eventos = _eventos_del_partido(ss, partido_id)
    if not eventos:
        return {
            "ok": False,
            "mensaje": f"No hay eventos para {partido_id} en EST_EVENTOS.",
            "stats": {},
        }
    try:
        i_desc = header.index("descripcion")
    except ValueError:
        return {
            "ok": False,
            "mensaje": "EST_EVENTOS no tiene columna 'descripcion'.",
            "stats": {},
        }
    col_desc_letter = gspread.utils.rowcol_to_a1(1, i_desc + 1).rstrip("1")

    # Emparejar por orden cronológico: el N-ésimo evento recibe la
    # N-ésima descripción.
    n_ev = len(eventos)
    n_gx = len(goles_extraidos)
    updates = []
    aplicados = []
    extras = []
    sin_describir = []
    for i, ev in enumerate(eventos):
        if i < n_gx:
            g = goles_extraidos[i]
            desc = (g.get("descripcion") or "").strip()
            marc = (g.get("marcador") or "").strip()
            eq_extraido = (g.get("equipo") or "").strip().upper()
            # Coherencia: si Gemini dice INTER pero el evento es RIVAL, avisar
            warn = ""
            if eq_extraido and eq_extraido != ev["equipo_marca"]:
                warn = f" ⚠️ Gemini dijo {eq_extraido} pero el evento es {ev['equipo_marca']}"
            # Construir texto a guardar
            texto_guardar = desc
            if marc and marc not in desc:
                texto_guardar = f"[{marc}] {desc}"
            if texto_guardar:
                updates.append({
                    "range": f"{col_desc_letter}{ev['fila_idx']}",
                    "values": [[texto_guardar]],
                })
                aplicados.append({
                    "minuto": ev["minuto"],
                    "equipo": ev["equipo_marca"],
                    "goleador": ev["goleador"],
                    "desc": texto_guardar,
                    "warn": warn,
                })
        else:
            sin_describir.append({
                "minuto": ev["minuto"],
                "equipo": ev["equipo_marca"],
                "goleador": ev["goleador"],
            })
    if n_gx > n_ev:
        extras = goles_extraidos[n_ev:]

    if dry:
        return {
            "ok": True,
            "partido_id": partido_id,
            "stats": {
                "eventos_partido": n_ev,
                "descripciones_extraidas": n_gx,
                "aplicados": len(aplicados),
                "sin_describir": len(sin_describir),
                "extras": len(extras),
            },
            "aplicados": aplicados,
            "sin_describir": sin_describir,
            "extras": extras,
        }

    if updates:
        ws_e.batch_update(updates)

    return {
        "ok": True,
        "partido_id": partido_id,
        "stats": {
            "eventos_partido": n_ev,
            "descripciones_extraidas": n_gx,
            "aplicados": len(aplicados),
            "sin_describir": len(sin_describir),
            "extras": len(extras),
        },
        "aplicados": aplicados,
        "sin_describir": sin_describir,
        "extras": extras,
    }


def main():
    transcripcion = sys.stdin.read().strip()
    if not transcripcion:
        print(MSG_SEP)
        print("❌ No he recibido transcripción para procesar.")
        return 1
    partido_id_arg = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"📝 Transcripción ({len(transcripcion)} chars): {transcripcion[:200]}…",
          file=sys.stderr)
    if partido_id_arg:
        print(f"🎯 Partido fijado: {partido_id_arg}", file=sys.stderr)

    try:
        goles_extraidos = gemini_extraer(transcripcion)
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Error parseando con Gemini: {e}")
        return 1

    if not goles_extraidos:
        print(MSG_SEP)
        print(
            "⚠️ No he detectado descripciones de goles en tu texto. "
            "¿Seguro que el audio/texto describe los goles del partido?"
        )
        return 0

    try:
        ss = _open_sheet()
        partido_id = partido_id_arg or _ultimo_partido_con_eventos(ss)
        if not partido_id:
            print(MSG_SEP)
            print("❌ No he podido determinar el partido. Pásalo como arg.")
            return 1
        resultado = actualizar_descripciones(ss, partido_id, goles_extraidos)
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Error accediendo al Sheet: {e}")
        return 1

    if not resultado["ok"]:
        print(MSG_SEP)
        print(f"❌ {resultado['mensaje']}")
        return 1

    s = resultado["stats"]
    print(MSG_SEP)
    print(f"⚽ *Goles descritos en {resultado['partido_id']}*")
    print()
    print(f"📊 {s['eventos_partido']} eventos · {s['descripciones_extraidas']} descripciones · {s['aplicados']} aplicadas")
    print()
    for a in resultado["aplicados"]:
        marca = "INTER" if a["equipo"] == "INTER" else "RIVAL"
        print(f"  · min {a['minuto']:.0f} ({marca}, {a['goleador']}): {a['desc']}{a['warn']}")
    if resultado["sin_describir"]:
        print()
        print(f"⚠️ {len(resultado['sin_describir'])} evento(s) sin descripción:")
        for s_ev in resultado["sin_describir"]:
            print(f"  · min {s_ev['minuto']:.0f} ({s_ev['equipo']}, {s_ev['goleador']})")
    if resultado["extras"]:
        print()
        print(f"⚠️ {len(resultado['extras'])} descripción(es) sobrantes "
              f"(más que eventos):")
        for ex in resultado["extras"]:
            print(f"  · {ex.get('marcador', '?')}: {ex.get('descripcion', '')}")


if __name__ == "__main__":
    main()
