"""
parse_ejercicios_voz.py — Procesa una transcripción de audio describiendo
los ejercicios de un entrenamiento, los estructura con Gemini, los
inserta en la hoja _EJERCICIOS y lanza la sincronización con Oliver.

Uso (lee transcripción de stdin):
  echo "Hoy hemos hecho 10 min de movilidad..." | python3 src/parse_ejercicios_voz.py

Variables de entorno:
  GEMINI_API_KEY   (obligatoria) — key de aistudio.google.com.
  GEMINI_MODEL     (opcional, default gemini-2.5-flash-lite).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

# Silenciar warnings ANTES de imports que emitan FutureWarning
# (google.generativeai está deprecated). Si no, el subprocess devuelve
# stderr ruidoso y el bot lo interpreta como error.
warnings.filterwarnings("ignore")

import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# Cargar .env del bot (si lo encuentra) para tener GEMINI_API_KEY disponible
try:
    from dotenv import load_dotenv
    _ROOT_TMP = Path(__file__).parent.parent.resolve()
    for _envp in [_ROOT_TMP / "telegram_bot" / ".env", _ROOT_TMP / ".env"]:
        if _envp.is_file():
            load_dotenv(_envp)
            break
except Exception:
    pass

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


# ─── Configurar Gemini ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ─── Pedir a Claude Code que estructure los ejercicios ──────────────────────
PROMPT_EXTRACTOR = """\
Tarea: extraer ejercicios de un texto sobre un entrenamiento de fútbol sala.

REGLA ABSOLUTA: tu salida COMPLETA debe ser un único objeto JSON. Nada de
explicaciones, nada de markdown, nada de comentarios. La respuesta debe
empezar con una llave de apertura y terminar con una llave de cierre.
Si no estás seguro de algún campo, usa null.

Esquema exacto:
{
  "duracion_total_min": <number o null, suma total incluyendo descansos>,
  "hora_inicio": "<HH:MM 24h o null>",
  "ejercicios": [
    {
      "nombre": "<descripción concisa>",
      "duracion_min": <number, decimales OK: 11.5 → 11.5>,
      "tipo": "<CALENTAMIENTO|MOVILIDAD|TECNICA|TACTICO|FISICO|BALON_PARADO|PARTIDILLO|FINALIZACION|VUELTA_A_LA_CALMA|OTRO>",
      "descanso_despues_min": <number, 0 si no hay; decimales OK: 2.5>,
      "gps_activo": <true|false>,
      "notas": "<detalles o cadena vacía>"
    }
  ]
}

🛰  IMPORTANTÍSIMO — GPS:
El usuario suele decir cuándo SE ENCIENDE el GPS (a veces tras movilidad
o calentamiento). Frases típicas: "activamos GPS", "encendemos GPS",
"GPS encendido", "ponemos pulsómetros", "ahora con GPS".

Reglas:
- Si el usuario menciona explícitamente que el GPS se activa en algún
  punto, todos los ejercicios ANTERIORES tienen `gps_activo: false` y
  todos los POSTERIORES `gps_activo: true`.
- Si NO se menciona el GPS en absoluto, asume `gps_activo: true` para
  todos los ejercicios.
- La movilidad/calentamiento inicial NO se asume sin GPS por defecto;
  solo si el usuario lo dice.

🧘  DESCANSOS:
El usuario suele decir "X minutos + Y de descanso", "después N min de
descanso", etc. Captúralos como `descanso_despues_min` del ejercicio
que ACABA DE TERMINAR (no del siguiente).

Si no se menciona descanso, usa 0.

Reglas de tipo:
- "movilidad" → MOVILIDAD; "calentamiento" → CALENTAMIENTO
- "rondo", "técnica" → TECNICA; "finalización" → FINALIZACION
- "salidas de presión", "transiciones", "defensa" → TACTICO
- "balón parado", "corners", "bandas", "ABP" → BALON_PARADO
- "juego real", "partidillo", "5 contra 5", "5x4" → PARTIDILLO
- En duda → OTRO

Mantén el orden cronológico. Si menciona variantes (3v3 + 2v1 en otra pista),
añade el detalle al campo notas.

EJEMPLO:
Texto: "Movilidad 17 min, después activamos GPS y 2 min y medio de
descanso. Rondo 5x5 11 min y medio + 3 de descanso. Partidillo 16 min."

JSON:
{
  "duracion_total_min": 49.5,
  "hora_inicio": null,
  "ejercicios": [
    {"nombre": "Movilidad", "duracion_min": 17, "tipo": "MOVILIDAD",
     "descanso_despues_min": 2.5, "gps_activo": false, "notas": ""},
    {"nombre": "Rondo 5x5", "duracion_min": 11.5, "tipo": "TECNICA",
     "descanso_despues_min": 3, "gps_activo": true, "notas": ""},
    {"nombre": "Partidillo", "duracion_min": 16, "tipo": "PARTIDILLO",
     "descanso_despues_min": 0, "gps_activo": true, "notas": ""}
  ]
}

Texto del entrenamiento:
__TEXTO__

Devuelve SOLO el JSON.
"""


# ─── Parser regex (sin LLM) para texto ESTRUCTURADO ────────────────────────
# Si el usuario manda los ejercicios con formato regular del tipo:
#   1.- Minibands + escaleras: 12 minutos + 1 descanso
#   2.- Coordinación de 2: 11 minutos + 4 descanso
# parseamos sin pasar por Gemini. Ahorra 30-60s + descarta riesgo de safety
# filter. Si CUALQUIER línea no matchea, devolvemos None y el flujo sigue
# con Gemini como antes (no rompe nada).
_RE_LINEA_EJ = re.compile(
    r"""^\s*
        (?:\d+\s*[\.\)\-]?\s*[\-–]?\s*|[\-•*]\s+)?  # opcional: "1.-", "1)", "•", etc.
        (?P<nombre>.+?)\s*[:\-]\s*                   # "Nombre:" o "Nombre -"
        (?P<dur>\d+(?:[,.]\d+)?)\s*min(?:utos?)?     # "12 min" / "12 minutos"
        (?:\s*[+y]\s*
            (?P<desc>\d+(?:[,.]\d+)?)\s*
            (?:min(?:utos?)?\s*)?
            (?:de\s+)?descanso
        )?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _inferir_tipo(nombre: str) -> str:
    """Heurística para clasificar el ejercicio por su nombre. Réplica simple
    de las reglas del prompt de Gemini para que el parser regex sea
    autosuficiente."""
    n = nombre.lower()
    # Orden importante: más específico primero
    if any(k in n for k in ("calentamiento", "miniband", "escalera", "activación")):
        # Si tiene "miniband" o "escaleras" claramente físico-coordinativo.
        # Usamos FISICO (es lo que Gemini venía clasificando en estos casos).
        if any(k in n for k in ("miniband", "escalera")):
            return "FISICO"
        return "CALENTAMIENTO"
    if "movilidad" in n:
        return "MOVILIDAD"
    if any(k in n for k in ("balón parado", "balon parado", "abp", "córner", "corner",
                              "banda lateral", "bandas")):
        return "BALON_PARADO"
    if any(k in n for k in ("partidillo", "juego real", "5x5", "5x4", "5v5", "5v4")):
        return "PARTIDILLO"
    if any(k in n for k in ("finalización", "finalizacion", "ataques continuados",
                              "tiros", "remate")):
        return "FINALIZACION"
    if any(k in n for k in ("presión", "presion", "transicion", "transición",
                              "defensa", "táctico", "tactico", "2x2", "3x3", "4x4",
                              "incorporación", "incorporacion", "salida de balón",
                              "salida de balon", "circulación", "circulacion",
                              "nombre y lado", "nombre + lado")):
        return "TACTICO"
    if any(k in n for k in ("rondo", "técnica", "tecnica", "coordinación",
                              "coordinacion", "pase ", "conducción", "conduccion",
                              "control")):
        return "TECNICA"
    if any(k in n for k in ("vuelta a la calma", "estiramientos", "estiramiento")):
        return "VUELTA_A_LA_CALMA"
    if any(k in n for k in ("físico", "fisico", "fuerza", "potencia", "velocidad",
                              "carrera", "sprint")):
        return "FISICO"
    return "OTRO"


def _to_num(s: str | None) -> float:
    if not s:
        return 0.0
    return float(s.replace(",", "."))


def parsear_estructurado(transcripcion: str) -> dict | None:
    """Intenta parsear texto ESTRUCTURADO sin LLM.

    Devuelve un dict con el mismo esquema que `claude_extraer(...)` si
    consigue parsear TODAS las líneas no vacías. Si falla aunque sea una,
    devuelve None y el flujo continúa con Gemini.

    Reconoce formatos como:
        1.- Minibands + escaleras: 12 minutos + 1 descanso
        2.- Coordinación de 2: 11 min + 4 descanso
        - Movilidad: 8 minutos
        • Partidillo 5x4: 20 min + 2 minutos de descanso
    """
    # Limpiar líneas y descartar vacías
    lineas = [ln.strip() for ln in transcripcion.splitlines() if ln.strip()]
    if len(lineas) < 2:
        # Texto muy corto (probablemente audio largo en una sola línea).
        # No intentamos regex aquí, dejamos que Gemini lo maneje.
        return None

    ejercicios: list[dict] = []
    for ln in lineas:
        m = _RE_LINEA_EJ.match(ln)
        if not m:
            # Una línea no estructurada → abortamos parser regex y dejamos LLM.
            return None
        nombre = m.group("nombre").strip(" .,:-")
        dur = _to_num(m.group("dur"))
        desc = _to_num(m.group("desc"))
        if dur <= 0:
            return None  # número inválido, mejor que decida Gemini
        ejercicios.append({
            "nombre": nombre,
            "duracion_min": dur,
            "tipo": _inferir_tipo(nombre),
            "descanso_despues_min": desc,
            "gps_activo": True,   # default: GPS activo (igual que la regla de Gemini)
            "notas": "",
        })

    if not ejercicios:
        return None

    total = sum(e["duracion_min"] + e["descanso_despues_min"] for e in ejercicios)
    return {
        "duracion_total_min": total,
        "hora_inicio": None,
        "ejercicios": ejercicios,
    }


JSON_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "duracion_total_min": {"type": ["number", "null"]},
        "hora_inicio": {"type": ["string", "null"]},
        "ejercicios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "duracion_min": {"type": "number"},
                    "tipo": {
                        "type": "string",
                        "enum": ["CALENTAMIENTO","MOVILIDAD","TECNICA","TACTICO",
                                 "FISICO","BALON_PARADO","PARTIDILLO","FINALIZACION",
                                 "VUELTA_A_LA_CALMA","OTRO"],
                    },
                    "descanso_despues_min": {"type": ["number", "null"]},
                    "gps_activo": {"type": ["boolean", "null"]},
                    "notas": {"type": "string"},
                },
                "required": ["nombre", "duracion_min", "tipo"],
            },
        },
    },
    "required": ["ejercicios"],
})


def claude_extraer(transcripcion: str) -> dict:
    """Mantiene el nombre histórico por compatibilidad. Internamente usa Gemini."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en el entorno.")
    prompt = PROMPT_EXTRACTOR.replace("__TEXTO__", transcripcion)
    _safety_off = [
        {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    model = genai.GenerativeModel(model_name=GEMINI_MODEL, safety_settings=_safety_off)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
            # 4096 para dejar margen al "thinking" interno de Gemini 2.5
            "max_output_tokens": 4096,
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
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"Gemini no devolvió JSON parseable: {text[:300]}")
    return json.loads(m.group(0))


# ─── Conexión Sheet ─────────────────────────────────────────────────────────
def gs_client():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds).open(SHEET_NAME)


# ─── Identificar sesión Oliver del día ──────────────────────────────────────
def identificar_session_oliver(fecha_iso: str) -> tuple:
    """Busca la sesión Oliver de `fecha_iso`. Devuelve (session_id, duracion_min, nombre)
    o (None, None, None).

    Estrategia OPTIMIZADA (antes paginaba TODAS las 431 sesiones del equipo;
    ~2 min). Ahora:
      1) Mira primero en `_OLIVER_SESIONES` del Sheet (caché local de sesiones
         ya sincronizadas). Si encuentra la fecha, devuelve sin llamar a la API.
      2) Si no está en caché, llama a la API pero **escanea batch a batch** y
         **devuelve en cuanto encuentra** la sesión del día. Como la API
         devuelve por defecto las más recientes primero, normalmente la
         encuentra en el primer batch (10-20 s en lugar de 2 min).
    """
    # 1) Caché local en el Sheet
    try:
        ss = gs_client()
        try:
            ws_cache = ss.worksheet("_OLIVER_SESIONES")
            filas = ws_cache.get_all_records()
        except Exception:
            filas = []
        for fila in filas:
            fecha_fila = str(fila.get("fecha") or fila.get("Fecha") or "").strip()
            # Aceptar tanto "2026-05-14" como "14/05/2026"
            if fecha_fila == fecha_iso:
                sid = fila.get("session_id") or fila.get("id")
                if sid:
                    try:
                        sid = int(sid)
                    except (ValueError, TypeError):
                        pass
                    dur = fila.get("dur_min") or fila.get("duracion_min") or None
                    nombre = fila.get("nombre") or ""
                    print(f"  ⚡ Sesión Oliver encontrada en caché _OLIVER_SESIONES "
                          f"(id={sid}, dur={dur}min) — sin llamar a la API.",
                          flush=True)
                    return sid, (int(dur) if dur else None), str(nombre)
    except Exception as e:
        print(f"[!] No pude consultar caché _OLIVER_SESIONES: {e}", file=sys.stderr)

    # 2) Llamar a la API parando en cuanto se encuentre
    try:
        from oliver_sync import (
            OliverAPI, OLIVER_TOKEN, OLIVER_USER, OLIVER_REFRESH, OLIVER_TEAM,
        )
        api = OliverAPI(OLIVER_TOKEN, OLIVER_USER, OLIVER_REFRESH)
        offset, page_size = 0, 250
        while True:
            r = api._get(
                "/sessions/",
                params={"team_id": OLIVER_TEAM, "limit": page_size, "offset": offset},
            )
            batch = r.get("sessions") or []
            total = r.get("total") or len(batch)
            print(f"  · escaneando {min(offset + len(batch), total)}/{total} "
                  f"(parando en cuanto aparezca {fecha_iso})", flush=True)
            for s in batch:
                start_ms = s.get("start") or 0
                if not start_ms:
                    continue
                fecha = datetime.fromtimestamp(start_ms / 1000,
                                                 tz=timezone.utc).date().isoformat()
                if fecha == fecha_iso and s.get("status") == "PROCESSED":
                    end_ms = s.get("end") or start_ms
                    dur = int((end_ms - start_ms) / 60000)
                    return s["id"], dur, s.get("name", "")
            if len(batch) < page_size or offset + len(batch) >= total:
                break
            offset += len(batch)
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

    # 1. Intentar parser regex (texto estructurado tipo "1.- X: 12 min + 2 descanso").
    #    Si matchea todas las líneas, ahorramos ~30-60s de llamada a Gemini
    #    y eliminamos riesgo de safety filter. Si falla cualquier línea,
    #    caemos a Gemini como antes.
    data = parsear_estructurado(transcripcion)
    if data is not None:
        print(f"⚡ Parser regex matched ({len(data['ejercicios'])} ejercicios) — sin LLM.",
              flush=True)
    else:
        try:
            data = claude_extraer(transcripcion)
        except Exception as e:
            print(MSG_SEP)
            print(f"❌ Gemini no pudo estructurar el audio:\n{e}")
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

    # 3. Calcular rangos de minutos.
    #
    # CONCEPTO CLAVE: los rangos que guardamos en _EJERCICIOS tienen que
    # ser MINUTOS DESDE QUE SE ACTIVÓ EL GPS, porque oliver_ejercicios.py
    # usa esos rangos para indexar el timeline GPS de Oliver (que empieza
    # cuando los jugadores encienden los GPS, no cuando empieza el entreno).
    #
    # Reglas:
    #   - Si gps_activo=False → NO incluir en _EJERCICIOS (no hay datos).
    #     Pero sí lo mostramos al usuario en el resumen.
    #   - Para los gps_activo=True, asignar rangos consecutivos desde 0
    #     incluyendo los descansos entre ellos (porque el GPS sigue
    #     corriendo durante los descansos).
    #   - Si gps_activo no está en el JSON (compat hacia atrás): asumir
    #     True. Si NO hay ningún ejercicio con gps_activo=False explícito
    #     y la suma supera la duración del timeline, aplicar la heurística
    #     antigua (excluir el primero).

    def _to_min(v):
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _gps_activo(e):
        v = e.get("gps_activo")
        if v is None:
            return True  # default: GPS activo
        return bool(v)

    # Suma total del audio (incluyendo descansos) = suma de duracion + descansos
    suma_audio = sum(_to_min(e.get("duracion_min"))
                     + _to_min(e.get("descanso_despues_min"))
                     for e in ejs)

    # ¿El usuario marcó explícitamente algún gps_activo=false?
    hay_gps_explicito = any(e.get("gps_activo") is False for e in ejs)

    # Fallback compat: si no hay marca explícita y la suma supera el
    # timeline, aplicar la heurística antigua (excluir el primer ejercicio).
    aviso_offset = ""
    if (not hay_gps_explicito
            and dur_timeline is not None
            and suma_audio > dur_timeline + 3
            and ejs):
        candidato_dur = _to_min(ejs[0].get("duracion_min"))
        candidato_descanso = _to_min(ejs[0].get("descanso_despues_min"))
        if candidato_dur > 0:
            mejora = abs((suma_audio - candidato_dur - candidato_descanso) - dur_timeline) \
                     < abs(suma_audio - dur_timeline)
            if mejora:
                aviso_offset = (
                    f"⚠️ El audio describe {suma_audio:g} min pero el GPS Oliver duró "
                    f"{dur_timeline} min.\n"
                    f"Asumo que el GPS se encendió DESPUÉS del primer ejercicio "
                    f"('{ejs[0]['nombre']}', {candidato_dur:g} min)."
                )
                # Marcamos el primero como no-GPS
                ejs[0]["gps_activo"] = False

    # 4. Recorrer ejercicios y construir filas + resumen
    #    Tres contadores:
    #      total_t  = minutos desde el inicio del entreno (para mostrar al usuario)
    #      gps_t    = minutos desde que se activó el GPS (para _EJERCICIOS)
    #      gps_iniciado = booleano para saber si ya empezó el GPS
    total_t = 0.0
    gps_t = 0.0
    gps_iniciado = False
    filas = []
    timeline_user = []  # cómo mostrar al usuario (incluye no-GPS)

    for ej in ejs:
        dur = _to_min(ej.get("duracion_min"))
        descanso = _to_min(ej.get("descanso_despues_min"))
        en_gps = _gps_activo(ej)

        if dur <= 0:
            continue

        ini_total = total_t
        fin_total = total_t + dur

        if en_gps:
            if not gps_iniciado:
                gps_iniciado = True
            ini_gps = gps_t
            fin_gps = gps_t + dur
            filas.append([
                session_id or "",
                fecha_iso,
                turno,
                (ej.get("nombre") or "").strip(),
                (ej.get("tipo") or "OTRO").strip(),
                ini_gps, fin_gps,
                "todos",
                (ej.get("notas") or "").strip(),
                f"voz-{fecha_iso}-{ini_gps:g}",
            ])
            gps_t = fin_gps + descanso  # el GPS sigue corriendo en el descanso
        # Si NO está en GPS, no añadimos a filas (oliver_ejercicios.py no
        # tendría timeline para esos minutos).

        timeline_user.append({
            "nombre": ej.get("nombre", "?"),
            "tipo": ej.get("tipo", "OTRO"),
            "ini_total": ini_total,
            "fin_total": fin_total,
            "descanso": descanso,
            "en_gps": en_gps,
            "ini_gps": (filas[-1][5] if en_gps and filas else None),
            "fin_gps": (filas[-1][6] if en_gps and filas else None),
        })
        total_t = fin_total + descanso

    suma_gps = gps_t  # minutos totales con GPS activo

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
    def _fmt(x: float) -> str:
        return f"{x:g}"  # quita decimales innecesarios (17.0 → "17", 11.5 → "11.5")

    print(MSG_SEP)
    resumen = [
        f"✅ *Audio procesado · {fecha_iso} {turno}*",
        f"Ejercicios extraídos: {len(ejs)} · Total entreno: {_fmt(suma_audio)} min "
        f"· Con GPS: {_fmt(suma_gps)} min"
        + (f" · GPS Oliver: {dur_timeline} min" if dur_timeline else ""),
        "",
        "*Cronología completa del entreno:*",
    ]
    for item in timeline_user:
        prefix_total = f"{_fmt(item['ini_total'])}-{_fmt(item['fin_total'])}'"
        if item["en_gps"]:
            rango_gps = f"📡 GPS {_fmt(item['ini_gps'])}-{_fmt(item['fin_gps'])}'"
        else:
            rango_gps = "⚪ sin GPS"
        resumen.append(
            f"• {prefix_total}  {item['nombre']}  _{item['tipo']}_  ·  {rango_gps}"
        )
        if item["descanso"] > 0:
            resumen.append(f"     └─ ⏸  descanso {_fmt(item['descanso'])} min")

    if filas:
        resumen.append("")
        resumen.append(
            f"📝 {len(filas)} ejercicio(s) añadido(s) a `_EJERCICIOS` con "
            f"rangos GPS (0 = momento que se activó el GPS)."
        )
    else:
        resumen.append("")
        resumen.append("⚠️ Ningún ejercicio con GPS activo. No hay nada que cruzar con Oliver.")

    if aviso_offset:
        resumen.append("")
        resumen.append(aviso_offset)

    if dur_timeline is not None and suma_gps > 0:
        diff = dur_timeline - suma_gps
        if abs(diff) > 3:
            resumen.append("")
            resumen.append(
                f"ℹ️ Diferencia entre la duración GPS calculada del audio "
                f"({_fmt(suma_gps)} min) y la del timeline Oliver "
                f"({dur_timeline} min): {diff:+.1f} min. "
                f"Si no cuadra, revisa la duración de algún ejercicio o descanso."
            )

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
            [sys.executable, str(ROOT / "src" / "oliver_ejercicios.py")],
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
