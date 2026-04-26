"""
parse_ejercicios_voz.py — Procesa una transcripción de audio describiendo
los ejercicios de un entrenamiento, los estructura con Claude Code, los
inserta en la hoja _EJERCICIOS y lanza la sincronización con Oliver.

Uso (lee transcripción de stdin):
  echo "Hoy hemos hecho 10 min de movilidad..." | /usr/bin/python3 src/parse_ejercicios_voz.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MSG_SEP = "---MSG---"


# ─── Localizar Claude Code (mismo método que el bot) ────────────────────────
def find_claude_bin():
    in_path = shutil.which("claude")
    if in_path:
        return in_path
    base = Path.home() / "Library/Application Support/Claude/claude-code"
    if not base.is_dir():
        return None
    versions = sorted(
        (v for v in base.iterdir() if v.is_dir() and re.match(r"^\d", v.name)),
        key=lambda p: tuple(int(x) for x in p.name.split(".") if x.isdigit()),
        reverse=True,
    )
    for v in versions:
        c = v / "claude.app/Contents/MacOS/claude"
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


CLAUDE_BIN = find_claude_bin()


# ─── Pedir a Claude Code que estructure los ejercicios ──────────────────────
PROMPT_EXTRACTOR = """\
Tarea: extraer ejercicios de un texto sobre un entrenamiento de fútbol sala.

REGLA ABSOLUTA: tu salida COMPLETA debe ser un único objeto JSON. Nada de
explicaciones, nada de markdown, nada de comentarios. La respuesta debe
empezar con una llave de apertura y terminar con una llave de cierre.
Si no estás seguro de algún campo, usa null.

Esquema exacto:
{
  "duracion_total_min": <int o null>,
  "hora_inicio": "<HH:MM 24h o null>",
  "ejercicios": [
    {
      "nombre": "<descripción concisa>",
      "duracion_min": <int>,
      "tipo": "<CALENTAMIENTO|MOVILIDAD|TECNICA|TACTICO|FISICO|BALON_PARADO|PARTIDILLO|FINALIZACION|VUELTA_A_LA_CALMA|OTRO>",
      "notas": "<detalles o cadena vacía>"
    }
  ]
}

Reglas de tipo:
- "movilidad" → MOVILIDAD; "calentamiento" → CALENTAMIENTO
- "rondo", "técnica" → TECNICA; "finalización" → FINALIZACION
- "salidas de presión", "transiciones", "defensa" → TACTICO
- "balón parado", "corners", "bandas", "ABP" → BALON_PARADO
- "juego real", "partidillo", "5 contra 5" → PARTIDILLO
- En duda → OTRO

Mantén el orden cronológico. Si menciona variantes (3v3 + 2v1 en otra pista),
añade el detalle al campo notas.

Texto del entrenamiento:
__TEXTO__

Devuelve SOLO el JSON.
"""


JSON_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "duracion_total_min": {"type": ["integer", "null"]},
        "hora_inicio": {"type": ["string", "null"]},
        "ejercicios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "duracion_min": {"type": "integer"},
                    "tipo": {
                        "type": "string",
                        "enum": ["CALENTAMIENTO","MOVILIDAD","TECNICA","TACTICO",
                                 "FISICO","BALON_PARADO","PARTIDILLO","FINALIZACION",
                                 "VUELTA_A_LA_CALMA","OTRO"],
                    },
                    "notas": {"type": "string"},
                },
                "required": ["nombre", "duracion_min", "tipo"],
            },
        },
    },
    "required": ["ejercicios"],
})


def claude_extraer(transcripcion: str) -> dict:
    if not CLAUDE_BIN:
        raise RuntimeError("No encuentro el binario de Claude Code.")
    prompt = PROMPT_EXTRACTOR.replace("__TEXTO__", transcripcion)
    proc = subprocess.run(
        [CLAUDE_BIN, "-p", "--dangerously-skip-permissions",
         "--output-format", "json",
         "--json-schema", JSON_SCHEMA, prompt],
        capture_output=True, text=True, timeout=180,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    try:
        envelope = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Salida no es JSON: {e}\n{proc.stdout[:500]}")
    if envelope.get("is_error"):
        raise RuntimeError(f"Claude reportó error: {envelope.get('result') or envelope}")
    structured = envelope.get("structured_output")
    if not structured:
        # Fallback: el `result` puede contener el JSON como texto
        result = (envelope.get("result") or "").strip()
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if not m:
            raise RuntimeError(f"Claude no devolvió structured_output ni JSON en result:\n{envelope}")
        structured = json.loads(m.group(0))
    return structured


# ─── Conexión Sheet ─────────────────────────────────────────────────────────
def gs_client():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


# ─── Identificar sesión Oliver del día ──────────────────────────────────────
def identificar_session_oliver(fecha_iso: str) -> tuple:
    """Busca en _OLIVER_SESIONES (índice) o en la API la sesión del día.
    Devuelve (session_id, duracion_timeline_min, nombre) o (None, None, None)."""
    try:
        from oliver_sync import OliverAPI, OLIVER_TOKEN, OLIVER_USER, OLIVER_REFRESH, OLIVER_TEAM
        api = OliverAPI(OLIVER_TOKEN, OLIVER_USER, OLIVER_REFRESH)
        sesiones = api.list_sessions(OLIVER_TEAM)
        for s in sesiones:
            start_ms = s.get("start") or 0
            if not start_ms:
                continue
            fecha = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat()
            if fecha == fecha_iso and s.get("status") == "PROCESSED":
                end_ms = s.get("end") or start_ms
                dur = int((end_ms - start_ms) / 60000)
                return s["id"], dur, s.get("name", "")
    except Exception as e:
        print(f"[!] No pude consultar Oliver: {e}", file=sys.stderr)
    return None, None, None


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    transcripcion = sys.stdin.read().strip()
    if not transcripcion:
        print(MSG_SEP)
        print("❌ No he recibido transcripción para procesar.")
        return 1

    # Fecha y turno (por defecto hoy / M)
    fecha_iso = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    turno = sys.argv[2] if len(sys.argv) > 2 else "M"

    print(MSG_SEP, flush=True)
    print(f"🎤 Procesando transcripción del entreno {fecha_iso} ({turno})…", flush=True)

    # 1. Pedir a Claude que estructure
    try:
        data = claude_extraer(transcripcion)
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Claude no pudo estructurar el audio:\n{e}")
        return 2

    ejs = data.get("ejercicios") or []
    if not ejs:
        print(MSG_SEP)
        print("❌ No he detectado ejercicios en la transcripción.")
        return 3

    # 2. Identificar sesión Oliver del día
    print(MSG_SEP, flush=True)
    print("🔍 Buscando sesión Oliver del día…", flush=True)
    session_id, dur_timeline, nombre_ses = identificar_session_oliver(fecha_iso)

    # 3. Calcular rangos de minutos: consecutivos desde 0 (excluyendo ejercicios sin duración)
    #    Si la duración total del audio supera la del timeline, asumimos que el primer
    #    ejercicio (típicamente movilidad/calentamiento) NO está en GPS y lo excluimos.
    suma_audio = sum(int(e.get("duracion_min") or 0) for e in ejs)
    aviso_offset = ""
    ejs_para_gps = ejs[:]
    if dur_timeline is not None and suma_audio > dur_timeline + 3:
        # Excluir el primer ejercicio (el GPS no estaba) si su duración acerca el match
        candidato = int(ejs[0].get("duracion_min") or 0)
        if candidato > 0 and abs((suma_audio - candidato) - dur_timeline) < abs(suma_audio - dur_timeline):
            aviso_offset = (
                f"⚠️ El audio describe {suma_audio} min pero el GPS Oliver duró {dur_timeline} min.\n"
                f"Asumo que el GPS se encendió DESPUÉS del primer ejercicio "
                f"('{ejs[0]['nombre']}', {candidato} min) y lo excluyo del cruce con Oliver."
            )
            ejs_para_gps = ejs[1:]

    # 4. Asignar minutos consecutivos desde 0
    cur = 0
    filas = []
    for ej in ejs_para_gps:
        dur = int(ej.get("duracion_min") or 0)
        if dur <= 0:
            continue
        ini, fin = cur, cur + dur
        cur = fin
        filas.append([
            session_id or "",
            fecha_iso,
            turno,
            (ej.get("nombre") or "").strip(),
            (ej.get("tipo") or "OTRO").strip(),
            ini, fin,
            "todos",
            (ej.get("notas") or "").strip(),
            f"voz-{fecha_iso}-{ini}",
        ])

    # 5. Escribir en _EJERCICIOS (append)
    ss = gs_client()
    try:
        ws = ss.worksheet("_EJERCICIOS")
        ws.append_rows(filas, value_input_option="USER_ENTERED")
    except Exception as e:
        print(MSG_SEP)
        print(f"❌ Error escribiendo en _EJERCICIOS:\n{e}")
        return 4

    # 6. Resumen previo a sincronizar
    print(MSG_SEP)
    resumen = [
        f"✅ *Audio procesado · {fecha_iso} {turno}*",
        f"Ejercicios extraídos: {len(ejs)}",
        f"Total audio: {suma_audio} min" + (f" · GPS Oliver: {dur_timeline} min" if dur_timeline else ""),
        "",
        "*Ejercicios añadidos a `_EJERCICIOS`:*",
    ]
    if filas:
        for f in filas:
            resumen.append(f"• {f[5]:>2}-{f[6]:>2}'  {f[3]}  _{f[4]}_")
    if ejs_para_gps != ejs:
        resumen.append("")
        resumen.append("(El primer ejercicio se omite del cruce con Oliver porque no tenía GPS)")
    if aviso_offset:
        resumen.append("")
        resumen.append(aviso_offset)
    if not session_id:
        resumen.append("")
        resumen.append("⚠️ No encontré la sesión de Oliver para este día (puede que aún no esté procesada).")
        resumen.append("Cuando esté disponible, lanza `/ejercicios_sync` para cruzar con datos GPS.")
    print("\n".join(resumen))

    # 7. Si hay sesión Oliver, lanzar oliver_ejercicios.py
    if session_id and filas:
        print(MSG_SEP, flush=True)
        print("🔄 Cruzando con datos de Oliver…", flush=True)
        proc = subprocess.run(
            ["/usr/bin/python3", str(ROOT / "src" / "oliver_ejercicios.py")],
            capture_output=True, text=True, timeout=900, cwd=str(ROOT),
        )
        if proc.returncode == 0:
            print(MSG_SEP)
            print("✅ `_VISTA_EJERCICIOS` actualizado. Mira la pestaña 🎯 Ejercicios del dashboard.")
        else:
            print(MSG_SEP)
            print(f"⚠️ Las filas se añadieron a `_EJERCICIOS` pero el cruce con Oliver falló:\n"
                  f"```\n{(proc.stderr or proc.stdout)[-800:]}\n```")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
