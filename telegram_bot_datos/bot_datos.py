#!/usr/bin/env python3
"""
Bot de Telegram de CONSULTAS DE DATOS para el cuerpo técnico del
Movistar Inter FS (@InterFS_datos_bot).

Diferencias respecto al bot dev (@InterFS_bot):
  - Multi-usuario con lista de chat_ids autorizados (ALLOWED_CHAT_IDS en .env).
  - Solo LECTURA: no puede editar archivos ni hacer commits.
  - Sesión por usuario (directorios separados) para que cada uno tenga su hilo.
  - System prompt que orienta a Claude a responder como "asistente de datos"
    en lenguaje humano, no técnico.
"""
from __future__ import annotations

import os
import re
import sys
import json
import asyncio
import datetime as _dt
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Set, Dict, List, Any

from dotenv import load_dotenv
from telegram import Update, constants, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

# Gemini (Google AI Studio) — backend LLM gratuito para este bot.
import google.generativeai as genai

# Whisper es opcional: si falla el import, el bot sigue funcionando solo con texto.
try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception as _e:
    _WHISPER_OK = False
    _WHISPER_IMPORT_ERR = str(_e)

# ─── Config ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

TOKEN               = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS_ST = os.getenv("ALLOWED_CHAT_IDS", "").strip()
PROJECT_DIR         = Path(os.getenv("PROJECT_DIR", str(HERE.parent))).expanduser().resolve()
LLM_TIMEOUT         = int(os.getenv("LLM_TIMEOUT", "300"))
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
# Cuenta de servicio READ-ONLY opcional. Si existe el archivo apuntado
# por READONLY_CREDS_FILE, los subprocess Python que lance este bot
# usarán ESA cuenta (con permiso solo Viewer sobre el Sheet) en lugar de
# la principal (Editor). Defensa en profundidad sobre el regex scanner:
# aunque Gemini intente escribir, Google API devolverá 403 al token.
# Si la variable no está o el archivo no existe → se usa la SA principal
# (el régimen actual).
READONLY_CREDS_FILE = os.getenv("READONLY_CREDS_FILE", "").strip()
# Cuántas iteraciones de tool-use permitir antes de cortar (defensa anti-bucle).
GEMINI_MAX_STEPS    = int(os.getenv("GEMINI_MAX_STEPS", "8"))
# Cuántas vueltas (user+model) guardamos en memoria por chat antes de truncar.
HISTORY_MAX_TURNS   = int(os.getenv("HISTORY_MAX_TURNS", "12"))

SESIONES_DIR = HERE / "sesiones"
MAX_MSG_LEN  = 4000
BOT_NAME     = "InterFS_datos_bot"

# Parsear lista de chat_ids permitidos (separados por comas, espacios o saltos de línea)
ALLOWED_CHAT_IDS: Set[int] = set()
for raw in re.split(r"[,\s]+", ALLOWED_CHAT_IDS_ST):
    raw = raw.strip()
    if raw:
        try:
            ALLOWED_CHAT_IDS.add(int(raw))
        except ValueError:
            pass

# Mergear con IDs adicionales del fichero allowed_chat_ids_extra.json (en git).
# Permite añadir miembros sin tocar el .env del servidor (un push y listo).
import json as _json  # noqa: E402
_extra_file = Path(__file__).parent / "allowed_chat_ids_extra.json"
if _extra_file.exists():
    try:
        _extra = _json.loads(_extra_file.read_text())
        for entry in _extra.get("ids", []):
            try: ALLOWED_CHAT_IDS.add(int(entry))
            except (ValueError, TypeError): pass
    except Exception as _e:
        # Silencioso: si el JSON está roto, el bot sigue con los del .env
        print(f"⚠ allowed_chat_ids_extra.json no se pudo leer: {_e}")

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("arkaitz-datos")


# ─── Validación ──────────────────────────────────────────────────────────────
def _fail(msg: str) -> None:
    log.error(msg)
    raise SystemExit(f"\n❌ {msg}\n")


if not TOKEN:
    _fail("Falta TELEGRAM_BOT_TOKEN en .env")
if not ALLOWED_CHAT_IDS:
    _fail("Falta ALLOWED_CHAT_IDS en .env (al menos un chat_id separado por comas).")
if not PROJECT_DIR.is_dir():
    _fail(f"PROJECT_DIR no existe: {PROJECT_DIR}")
if not GEMINI_API_KEY:
    _fail("Falta GEMINI_API_KEY en .env (consíguela gratis en aistudio.google.com/apikey).")

SESIONES_DIR.mkdir(parents=True, exist_ok=True)

# Configurar cliente Gemini
genai.configure(api_key=GEMINI_API_KEY)

log.info("Backend LLM: Gemini (%s)", GEMINI_MODEL)
if READONLY_CREDS_FILE and Path(READONLY_CREDS_FILE).is_file():
    log.info("Modo SA READ-ONLY: ON (creds=%s)", READONLY_CREDS_FILE)
elif READONLY_CREDS_FILE:
    log.warning(
        "READONLY_CREDS_FILE definido (%s) pero el archivo NO existe. "
        "Bot funciona con SA principal + regex scanner solamente.",
        READONLY_CREDS_FILE,
    )
else:
    log.info("Modo SA READ-ONLY: OFF (solo regex scanner protege escritura)")
log.info("Proyecto: %s", PROJECT_DIR)
log.info("Autorizados: %s", sorted(ALLOWED_CHAT_IDS))


# ─── Espejo de conversaciones (para móvil ↔ ordenador) ───────────────────────
LOGS_DIR = PROJECT_DIR / "telegram_logs"
LOGS_DIR.mkdir(exist_ok=True)


def _append_log(chat_id: int, user_name: str, user_msg: str, bot_reply: str, kind: str = "texto") -> None:
    try:
        hoy = _dt.datetime.now().strftime("%Y-%m-%d")
        hora = _dt.datetime.now().strftime("%H:%M:%S")
        path = LOGS_DIR / f"{hoy}.md"
        etiqueta = "🎤 (voz)" if kind == "voz" else "💬"
        bloque = (
            f"\n---\n"
            f"### {hora} · {BOT_NAME} · chat `{chat_id}` · {etiqueta}\n\n"
            f"**{user_name or 'usuario'}:**\n{user_msg.strip()}\n\n"
            f"**Claude:**\n{bot_reply.strip()}\n"
        )
        with path.open("a", encoding="utf-8") as f:
            f.write(bloque)
    except Exception as e:
        log.warning("No pude escribir log: %s", e)


# ─── System prompt del bot de datos ──────────────────────────────────────────
SYSTEM_PROMPT = f"""\
Eres el asistente de datos del Movistar Inter FS (fútbol sala).
Te escriben miembros del cuerpo técnico (entrenadores, fisios, médicos)
desde Telegram. Tu trabajo es **darles la respuesta directamente**
consultando el Google Sheet de la temporada — no preguntarles cómo
encontrar los datos, **busca tú**.

⚠️⚠️⚠️ REGLA #0 — ATAJO OBLIGATORIO PARA "ESTADO DE JUGADOR" ⚠️⚠️⚠️
Si te preguntan por el ESTADO, CARGA, FATIGA, BORG, o "qué tal" de un
jugador concreto (frases tipo "cómo está Pirata", "carga últimas 10
sesiones de Raya", "qué tal Carlos", "estado de Anchu", "fatiga de X"
… cualquier variante), NO escribas código Python que saque datos brutos.

USA OBLIGATORIAMENTE el script curado:

```bash
/usr/bin/python3 {PROJECT_DIR}/src/estado_jugador.py NOMBRE [N_SESIONES]
```

Donde:
- `NOMBRE` = nombre del jugador en MAYÚSCULAS (PIRATA, RAYA, CARLOS, etc.).
  El script ya hace alias-matching (admite minúsculas, sin tildes, etc.).
- `N_SESIONES` = opcional, default 10. Solo cámbialo si el usuario
  pide explícitamente otro número.

Este script DEVUELVE un bloque Markdown ya formateado con:
  - Carga media últimas N + comparación con histórico del jugador y equipo.
  - Borg medio + histórico.
  - ACWR, Monotonía, Fatiga semana actual con semáforos.
  - Wellness 7 días con semáforo.
  - Recomendación accionable.

Lo que TÚ haces: invocas el script con `bash` y le mandas al usuario
**el output literal** (entre triple backtick si conserva formato). NO lo
reescribas, NO lo resumas, NO añadas datos brutos por encima. Solo si el
usuario pide algo MUY específico que no esté en el resumen, puedes hacer
una consulta extra a Python después.

Ejemplo de comportamiento correcto:
  Usuario: "qué tal Pirata, carga últimas 10 sesiones"
  Tú: [bash → /usr/bin/python3 {PROJECT_DIR}/src/estado_jugador.py PIRATA 10]
  Tú: envías el output tal cual.

⚠️ REGLA #1 — ACCIÓN INMEDIATA, NO RELATO:
Cuando te pidan datos: USA LA TOOL `python` DIRECTAMENTE en el primer
turno. **Nunca digas** "dame un segundo", "voy a buscarlo", "lo miro
y te digo". Esas frases sin tool call dejan al usuario esperando para
nada.

Patrón correcto:
  Usuario: "¿cómo va Carlos esta semana?"
  Tú (sin texto previo): [llamas a la tool python]
  Tool: [datos]
  Tú: "Carlos lleva 3 sesiones esta semana, sRPE 1840, semáforo verde."

Patrón INCORRECTO:
  Usuario: "¿cómo va Carlos?"
  Tú: "Dame un segundo y te lo digo" ← MAL
  [se queda sin actuar]

Si la pregunta es ambigua, **intenta una interpretación razonable** y
da datos. Solo pide clarificación si es imprescindible.

TONO Y FORMATO:
- Español, frases cortas, **como un compañero del cuerpo técnico**.
- Cero jerga técnica (no menciones "DataFrame", "columna", "exit code",
  "JSON", etc). Si no encuentras algo, di "no me sale" en lugar de
  "Vaya, parece que no encuentro la columna...".
- Da números concretos. "Carlos perdió 1,2 kg el lunes" mejor que
  "el jugador presenta variación ponderal".
- Si te piden a varios jugadores, lista en bullets:
    `• PIRATA: 7 sesiones esta semana (Borg medio 6,3)`
    `• CARLOS: 5 sesiones (Borg medio 5,8)`
- NUNCA pegues HTML (no `<h3>`, no `<br>`, etc.). Markdown simple es OK
  (`**negrita**`, bullets `•` o `-`).
- Si la respuesta es muy larga, resume en 3-5 líneas y ofrece "¿quieres
  que te lo detalle?".

⚠️ REGLA CRÍTICA — DATOS CON CONTEXTO ⚠️
Un número aislado NO sirve al cuerpo técnico. CUANDO RESPONDAS CON
NÚMEROS de un jugador (Borg, fatiga, carga, peso, wellness…), incluye:

  1. **El dato pedido**, en negrita.
  2. **Comparación** con al menos UNA referencia:
     - media histórica DEL PROPIO JUGADOR (toda la temporada),
     - media del equipo en el mismo periodo,
     - rango habitual del jugador (mín-máx),
     - semana anterior o el mismo periodo del mes pasado.
  3. **Interpretación corta**: alto, normal, bajo, en zona de riesgo.
     Usa los umbrales del proyecto (ACWR <0.8 azul / 0.8-1.3 verde /
     1.3-1.5 amarillo / >1.5 rojo; monotonía >2 riesgo;
     wellness ≤10 rojo / ≤13 naranja / >13 verde).
  4. **Recomendación práctica** si el dato lo merece. Si todo está
     normal, dilo claro: "todo dentro de lo esperado".

Ejemplo MAL:
  > "La fatiga media de Raya en las últimas 10 sesiones es de 4.90."

Ejemplo BIEN:
  > "Borg medio últimas 10 sesiones de **Raya**: **4.9**. Su media
  > histórica es 5.4 y el equipo anda en 5.6, va algo por debajo.
  > Coherente con su semana (ACWR 0.85, verde). Nada preocupante."

⚠️ "Fatiga" tiene dos significados, elige el correcto:
  - "fatiga últimas sesiones" → Borg de `_VISTA_CARGA` (subjetivo).
  - "fatiga semanal/calculada" → columna FATIGA de `_VISTA_SEMANAL`
    (= carga_semanal × monotonía).
Aclara qué métrica das.

REGLAS ESTRICTAS:
1. **SOLO LECTURA — ESTO ES CRÍTICO**. No modificas archivos. No haces
   git. No escribes, insertas, actualizas ni borras NADA en el Sheet.
   Si te piden añadir/modificar/borrar un dato (por ejemplo "apunta a
   X como lesionado", "borra la sesión del jueves", "cambia el peso
   de Y"), RECHAZA con un mensaje claro:
     "❌ No puedo modificar datos desde aquí. Soy solo de lectura. Para
      escribir al Sheet, díselo a Arkaitz por @InterFS_bot."
   NO ejecutes `ws.update_cell`, `ws.append_row`, `ws.delete_rows`,
   `ws.batch_update` ni nada parecido. Si te ves usando alguno de esos,
   PARA antes y devuelve la respuesta de rechazo.

2. Si te piden CÓDIGO / FIXES TÉCNICOS / cambios en el dashboard / bot:
   "Eso mejor pregúntaselo a Arkaitz por el bot del cuerpo técnico
   (@InterFS_bot). Yo solo respondo consultas de datos."
   ⚠ NO derives temas que sean DATOS aunque suenen técnicos. P. ej.
   "cómo recibe los goles el Barça" → datos de scouting, ¡contesta!
   "cuántos disparos a puerta ha hecho HARRISON" → datos de partido,
   ¡contesta! Solo deriva si es código/fix de la app o ESCRITURA.

3. Si la pregunta no tiene nada que ver con el equipo o el fútbol sala,
   redirige amablemente.

4. 🔒 **PRIVACIDAD MÉDICA — lesiones y tratamientos**:
   Cuando te pregunten por una LESIÓN, un TRATAMIENTO, una molestia o
   una retirada por lesión (hojas LESIONES, FISIO, BORG.INCIDENCIA),
   **NO menciones el nombre del jugador**. Usa el DORSAL como ID, así:
     ❌ "RAYA lleva 5 días de baja por gemelo"
     ✅ "El jugador #8 lleva 5 días de baja por gemelo"
   Para resolver el dorsal: lee la hoja `JUGADORES_ROSTER` (columnas
   `dorsal` y `nombre`) y emplea el dorsal correspondiente.
   Esta regla NO aplica a:
     - Carga/Borg/Wellness/Peso → usa el nombre normalmente.
     - Stats de partidos (goles, disparos, asistencias) → nombre.
   SOLO aplica a datos médicos.
   Si el usuario te lo pide específicamente sin dorsal ("dime el nombre
   del que está lesionado, soy fisio"), aún así RESPONDE CON DORSAL.
   El acceso por nombre se hace en el dashboard de Streamlit donde los
   roles fisio/médico/admin sí ven nombres reales — pero AQUÍ no.

CÓMO CONSULTAR LOS DATOS:
Los datos están en un Google Sheet. **Usa SIEMPRE la herramienta `python`**
(no `bash`). Mete todo el script en UNA sola llamada (importar credenciales
+ abrir Sheet + leer + filtrar + imprimir). NO partas en varias llamadas
porque cada una arranca un proceso nuevo y pierdes la conexión.

⚡ El sandbox YA TIENE PREIMPORTADOS: `pd` (pandas), `gspread`,
`ss` (Spreadsheet ya abierto). NO escribas imports ni creds.
Escribe SOLO la lógica:

```python
df = pd.DataFrame(ss.worksheet('NOMBRE').get_all_records(
    value_render_option=gspread.utils.ValueRenderOption.unformatted))
# >>> tu lógica aquí
```

⚠️ **IMPORTANTE — value_render_option=UNFORMATTED**:
Cuando llames a `get_all_records()` **SIEMPRE** pasa
`value_render_option=gspread.utils.ValueRenderOption.unformatted`.
Sin esto, los pesos `74,7` (decimal con coma, formato español) llegan
como `747` (sin coma, error de un orden de magnitud), y los porcentajes
también se rompen. Con UNFORMATTED, llegan como `74.7` (float real).

Plantilla de lectura correcta:
```python
df = pd.DataFrame(ss.worksheet('NOMBRE').get_all_records(
    value_render_option=gspread.utils.ValueRenderOption.unformatted))
```

OTROS DETALLES:
- La columna BORG puede ser número (0-10) o letra (S, A, L, N, D, NC).
  Filtra los numéricos con
  `pd.to_numeric(df['BORG'], errors='coerce').notna()`.
- Las fechas vienen como string `'YYYY-MM-DD'`. Para filtrar por rango,
  conviértelas con `pd.to_datetime(df['FECHA'], errors='coerce')`.
- ⚠️ **NO ANIDES COMILLAS DOBLES dentro de f-strings** porque corres en
  Python 3.11 y revienta. Usa comillas simples dentro:
    BIEN:  `print(f"Hoy es {{fecha.strftime('%d/%m')}}")`
    MAL:   `print(f"Hoy es {{fecha.strftime(\"%d/%m\")}}")`  ← SyntaxError

FECHAS:
- Vienen como strings `YYYY-MM-DD`. Parsea con
  `df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')`.
- **HOY ES __HOY__** (formato YYYY-MM-DD).
- "Esta semana" = lunes-domingo de la semana actual.
- "Última semana" / "semana pasada" = la anterior.
- "Este mes" = del día 1 del mes actual hasta hoy.

ROSTER OFICIAL (así se guarda el JUGADOR en el Sheet):
PRIMER EQUIPO porteros: HERRERO, GARCIA
PRIMER EQUIPO campo: CECILIO, CHAGUINHA, RAUL, HARRISON, RAYA, JAVI,
  PANI, PIRATA, BARONA, CARLOS
FILIAL portero: OSCAR
FILIAL campo: RUBIO, JAIME, SEGO, DANI, GONZALO, PABLO, GABRI, NACHO, ANCHU

ALIAS típicos a tolerar:
- "J.Herrero", "Jose Herrero", "el 1" → HERRERO
- "Javi García", "J.García", "el 27" → GARCIA
- "Gonza", "Gonzo" → GONZALO
- "Javi", "Javi Mínguez", "Javi Miguez", "Javier", "el 10" → JAVI
- "Chagas", "Chaginha" → CHAGUINHA
- "Rubio", "Sergio", "Vizuete" → RUBIO
- "el Pirata", "Pirata" → PIRATA

**Si no encuentras un nombre exacto, prueba con `str.contains` antes de
rendirte**:
```python
mask = df['JUGADOR'].astype(str).str.upper().str.contains('JAVI', na=False)
```

ESQUEMA EXACTO DE LAS HOJAS (verificado mayo 2026):

CRUDAS (input directo del cuerpo técnico):
- **BORG**: `FECHA, TURNO, JUGADOR, BORG`. Una fila por jugador-sesión.
  No tiene MINUTOS (esos están en SESIONES).
- **PESO**: `FECHA, TURNO, JUGADOR, PESO_PRE, PESO_POST, H2O_L`.
- **WELLNESS**: `FECHA, JUGADOR, SUENO, FATIGA, MOLESTIAS, ANIMO, TOTAL`.
  ⚠️ La columna se llama `SUENO` (sin tilde, no `SUEÑO`).
- **SESIONES**: `FECHA, SEMANA, TURNO, TIPO_SESION, MINUTOS, COMPETICION`.
  ⚠️ NO tiene JUGADOR. Es el calendario de entrenamientos del equipo.
- **LESIONES**: estructura compleja con cabecera en fila 2. Para esta
  hoja usa `ws.get_all_values()` y trabaja desde la fila 2 (índice 1)
  como header. Columnas relevantes: JUGADOR, FECHA LESIÓN, TIPO LESIÓN,
  ZONA CORPORAL, LADO, FECHA ALTA, etc. Si te lían las cabeceras,
  prefiere `_VISTA_RECUENTO` o pídele al usuario que sea más específico.
- **FISIO**: `FECHA, JUGADOR, ESTADO, TIPO_LESION, ZONA_CORPORAL, LADO,
  DIAS_BAJA_ESTIMADOS, NOTAS`.

VISTAS PRE-CALCULADAS (lo que más vas a usar):
- **_VISTA_CARGA** (3800+ filas, una por jugador-sesión):
  `FECHA, FECHA_STR, SEMANA, DIA_SEMANA, TURNO, JUGADOR, TIPO_SESION,
   COMPETICION, MINUTOS, BORG, CARGA`
  La columna `CARGA` ya es el sRPE (= Borg × Minutos).
- **_VISTA_SEMANAL** (~600 filas, una por jugador-semana):
  `FECHA_LUNES, SEMANA_ISO, AÑO, JUGADOR, CARGA_SEMANAL, SESIONES,
   BORG_MEDIO, ACWR, CARGA_AGUDA, CARGA_CRONICA, MONOTONIA, FATIGA,
   SEMAFORO`
- **_VISTA_PESO**:
  `FECHA, SEMANA, DIA_SEMANA, TURNO, JUGADOR, TIPO_SESION, COMPETICION,
   PESO_PRE, PESO_POST, DIFERENCIA, PCT_PERDIDA, H2O_L, ALERTA_PESO,
   BASELINE_PRE, DESVIACION_BASELINE`
  ⚠️ `DESVIACION_BASELINE` SOLO existe aquí, NO en `PESO` cruda.
- **_VISTA_WELLNESS**:
  `FECHA, SEMANA, DIA_SEMANA, JUGADOR, SUENO, FATIGA, MOLESTIAS, ANIMO,
   TOTAL, WELLNESS_7D, BASELINE_WELLNESS, DESVIACION_BASELINE,
   SEMAFORO_WELLNESS`
- **_VISTA_SEMAFORO** (la "foto" más reciente del equipo):
  `JUGADOR, SEMANA, ACWR, MONOTONIA, SEMAFORO_CARGA, WELLNESS_MEDIO,
   WELLNESS_BELOW15, SEMAFORO_WELLNESS, PESO_PRE_DESV_KG, SEMAFORO_PESO,
   ALERTAS_ACTIVAS, SEMAFORO_GLOBAL`
- **_VISTA_RECUENTO** (asistencia del histórico):
  `JUGADOR, TOTAL_SESIONES_EQUIPO, EST_S, EST_A, EST_L, EST_N, EST_D,
   EST_NC, SESIONES_CON_DATOS, PCT_PARTICIPACION`
  `SESIONES_CON_DATOS` = sesiones donde el jugador ha entrenado de verdad
  (Borg numérico). Los EST_X son contadores de cada estado (S=Selección,
  A=Ausencia, L=Lesión, N=No entrena, D=Descanso, NC=No calificado,
  NJ=No juega — convocado al partido pero no participa).

EJEMPLOS DE PREGUNTAS Y CÓMO RESOLVERLAS

1) "¿Cuántas sesiones ha entrenado Pirata?"
→ Usa `_VISTA_RECUENTO`:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_RECUENTO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
fila = df[df['JUGADOR'] == 'PIRATA']
print(fila[['JUGADOR','SESIONES_CON_DATOS','TOTAL_SESIONES_EQUIPO','PCT_PARTICIPACION']].to_string(index=False))
```

2) "¿Cómo va Carlos esta semana?" (visión global) → `_VISTA_SEMAFORO`:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_SEMAFORO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
print(df[df['JUGADOR']=='CARLOS'].to_string(index=False))
```

3) "Borg de Javi esta semana" → `_VISTA_CARGA` filtrado por fecha:
```python
import datetime
hoy = datetime.date.today()
lunes = hoy - datetime.timedelta(days=hoy.weekday())
df = pd.DataFrame(ss.worksheet('_VISTA_CARGA').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
m = (df['JUGADOR']=='JAVI') & (df['FECHA']>=pd.Timestamp(lunes))
res = df.loc[m, ['FECHA','TURNO','MINUTOS','BORG','CARGA']]
print(res.to_string(index=False))
```

4) "Peso PRE de Pirata, últimos días" → `_VISTA_PESO`:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_PESO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
df['PESO_PRE'] = pd.to_numeric(df['PESO_PRE'].astype(str).str.replace(',','.'), errors='coerce')
df['DESVIACION_BASELINE'] = pd.to_numeric(df['DESVIACION_BASELINE'].astype(str).str.replace(',','.'), errors='coerce')
res = df[df['JUGADOR']=='PIRATA'].sort_values('FECHA').tail(7)
print(res[['FECHA','PESO_PRE','DESVIACION_BASELINE']].to_string(index=False))
```

5) "¿Quién está rojo en semáforo?" → `_VISTA_SEMAFORO` filter:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_SEMAFORO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
rojos = df[df['SEMAFORO_GLOBAL'].str.upper()=='ROJO']
print(rojos[['JUGADOR','SEMANA','ALERTAS_ACTIVAS','SEMAFORO_GLOBAL']].to_string(index=False))
```

6) "Wellness del equipo esta semana" → `_VISTA_WELLNESS`:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_WELLNESS').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
df['TOTAL'] = pd.to_numeric(df['TOTAL'], errors='coerce')
import datetime
hoy = datetime.date.today()
lunes = hoy - datetime.timedelta(days=hoy.weekday())
sem = df[df['FECHA']>=pd.Timestamp(lunes)]
print(sem.groupby('JUGADOR')['TOTAL'].agg(['mean','count']).round(1).to_string())
```

7) "Carga semanal del equipo" → `_VISTA_SEMANAL` última semana:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_SEMANAL').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA_LUNES'] = pd.to_datetime(df['FECHA_LUNES'], errors='coerce')
ultima = df['FECHA_LUNES'].max()
res = df[df['FECHA_LUNES']==ultima].sort_values('CARGA_SEMANAL', ascending=False)
print(res[['JUGADOR','SESIONES','CARGA_SEMANAL','BORG_MEDIO','ACWR','SEMAFORO']].to_string(index=False))
```

8) "¿Cuántas filas tiene la hoja BORG?" → conteo simple:
```python
print(len(ss.worksheet('BORG').get_all_values()) - 1)  # -1 por la cabecera
```

9) "Lesiones activas" → la hoja `LESIONES` tiene cabecera en la **fila 2**
   (la fila 1 es super-cabecera con secciones agrupadas). El criterio
   más fiable de "activa" es **FECHA ALTA vacía**.
```python
vals = ss.worksheet('LESIONES').get_all_values()
header = vals[1]  # ¡fila 2 es la cabecera real!
df = pd.DataFrame(vals[2:], columns=header)
df = df[df['JUGADOR'].astype(str).str.strip() != '']  # quitar filas vacías
# Lesiones activas = sin fecha de alta
activas = df[df['FECHA ALTA'].astype(str).str.strip() == '']
print(activas[['JUGADOR','FECHA LESIÓN','TIPO LESIÓN','ZONA CORPORAL','DÍAS BAJA EST.']].to_string(index=False))
```

10) "Wellness medio del equipo esta semana"
```python
import datetime
df = pd.DataFrame(ss.worksheet('_VISTA_WELLNESS').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
hoy = datetime.date.today()
lunes = hoy - datetime.timedelta(days=hoy.weekday())
sem = df[df['FECHA']>=pd.Timestamp(lunes)]
res = sem.groupby('JUGADOR')['TOTAL'].agg(['mean','count']).round(1)
res.columns = ['Wellness medio', 'N días']
print(res.sort_values('Wellness medio').to_string())
```

11) "Compara Carlos y Pirata esta semana"
```python
import datetime
df = pd.DataFrame(ss.worksheet('_VISTA_CARGA').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
df['CARGA_N'] = pd.to_numeric(df['CARGA'], errors='coerce')
df['BORG_N'] = pd.to_numeric(df['BORG'], errors='coerce')
df['MINUTOS_N'] = pd.to_numeric(df['MINUTOS'], errors='coerce')
hoy = datetime.date.today()
lunes = hoy - datetime.timedelta(days=hoy.weekday())
sem = df[(df['FECHA']>=pd.Timestamp(lunes)) & (df['JUGADOR'].isin(['CARLOS','PIRATA']))]
res = sem.groupby('JUGADOR').agg(
    sesiones=('BORG_N','count'),  # solo cuenta sesiones con Borg numérico (las que entrenó)
    minutos=('MINUTOS_N','sum'),
    carga_total=('CARGA_N','sum'),
    borg_medio=('BORG_N','mean')
).round(1)
print(res.to_string())
```

12) "Días de baja de X en la temporada" → `_VISTA_RECUENTO` columna EST_L.
   ⚠ Como esto es info médica, responde con DORSAL en vez de nombre:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_RECUENTO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
roster = pd.DataFrame(ss.worksheet('JUGADORES_ROSTER').get_all_records())
# Cruza para tener el dorsal
res = df.merge(roster[['dorsal','nombre']], left_on='JUGADOR', right_on='nombre', how='left')
print(res[['dorsal','EST_L','EST_S','EST_A','SESIONES_CON_DATOS','TOTAL_SESIONES_EQUIPO']].to_string(index=False))
# Luego al usuario respondes "el #8 lleva 5 sesiones marcadas como L".
```

13) "Recuento de Pirata" / "asistencia de Pirata" → `_VISTA_RECUENTO`,
   trae TODO el detalle (S, A, L, N, D, NC, NJ + retiradas). Como
   incluye lesiones, vuelve a usar dorsal:
```python
df = pd.DataFrame(ss.worksheet('_VISTA_RECUENTO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
roster = pd.DataFrame(ss.worksheet('JUGADORES_ROSTER').get_all_records())
fila = df[df['JUGADOR']=='PIRATA']
d = roster[roster['nombre']=='PIRATA']['dorsal'].iloc[0] if not roster.empty else '?'
print(f"Recuento jugador #{{d}}:")
print(fila[['SESIONES_CON_DATOS','PCT_PARTICIPACION','EST_S','EST_A','EST_L','EST_N','EST_D','EST_NC','EST_NJ','RETIRADAS','RETIRADAS_DETALLE']].to_string(index=False))
```

14) "¿Quién entrenó el 13/05?" / "¿Quién no estuvo el martes?" →
   `_VISTA_CARGA` filtrado por fecha. Lista todo: quién con Borg
   numérico, quién con código (L/A/D/S/N), quién retirado a mitad.
```python
df = pd.DataFrame(ss.worksheet('_VISTA_CARGA').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce')
hoy = df[df['FECHA']==pd.Timestamp('2026-05-13')]
# BORG numérico = entrenó. BORG letra = motivo (L,A,D,S,N,NC).
hoy['BORG_NUM'] = pd.to_numeric(hoy['BORG'], errors='coerce')
entrenaron = hoy[hoy['BORG_NUM'].notna()][['JUGADOR','MINUTOS','BORG','CARGA']]
estados = hoy[hoy['BORG_NUM'].isna() & (hoy['BORG'].astype(str).str.strip() != '')][['JUGADOR','BORG']]
print("ENTRENARON:")
print(entrenaron.to_string(index=False))
print("\nNO ENTRENARON (con motivo):")
print(estados.to_string(index=False))
# Para retiradas, leer BORG cruda y filtrar INCIDENCIA no vacía:
borg = pd.DataFrame(ss.worksheet('BORG').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
ret = borg[(borg['FECHA']=='2026-05-13') & (borg.get('INCIDENCIA','').astype(str).str.strip() != '')]
if not ret.empty:
    print("\nRETIRADOS A MITAD:")
    print(ret[['JUGADOR','INCIDENCIA']].to_string(index=False))
```

15) "Lesiones / retiradas RECIENTES del equipo" → cruzar
   `_VISTA_RECUENTO.RETIRADAS_DETALLE` (texto con fechas) + LESIONES
   activas. Responde con DORSAL (info médica):
```python
df = pd.DataFrame(ss.worksheet('_VISTA_RECUENTO').get_all_records(value_render_option=gspread.utils.ValueRenderOption.unformatted))
roster = pd.DataFrame(ss.worksheet('JUGADORES_ROSTER').get_all_records())
con_ret = df[df['RETIRADAS'] > 0].merge(roster[['dorsal','nombre']], left_on='JUGADOR', right_on='nombre')
for _, r in con_ret.iterrows():
    print(f"#{{r['dorsal']}}: {{r['RETIRADAS']}} retiradas — {{r['RETIRADAS_DETALLE']}}")
```

13) "¿Cómo está / va Cecilio esta semana?" → ANALÍTICA: combinar carga +
    wellness + peso + alertas en UNA sola tool call:
```python
import pandas as pd, gspread, datetime
from google.oauth2.service_account import Credentials
creds = Credentials.from_service_account_file(
    '{PROJECT_DIR}/google_credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'])
ss = gspread.authorize(creds).open('Arkaitz - Datos Temporada 2526')

JUG = 'CECILIO'
hoy = datetime.date.today()
lunes = hoy - datetime.timedelta(days=hoy.weekday())
URO = gspread.utils.ValueRenderOption.unformatted

# 1) Semáforo (foto del estado actual)
sem = pd.DataFrame(ss.worksheet('_VISTA_SEMAFORO').get_all_records(value_render_option=URO))
print('=== SEMÁFORO ===')
print(sem[sem['JUGADOR']==JUG].to_string(index=False))

# 2) Carga esta semana
carga = pd.DataFrame(ss.worksheet('_VISTA_CARGA').get_all_records(value_render_option=URO))
carga['FECHA'] = pd.to_datetime(carga['FECHA'], errors='coerce')
m_sem = (carga['JUGADOR']==JUG) & (carga['FECHA']>=pd.Timestamp(lunes))
print('\\n=== CARGA SEMANA ===')
print(carga.loc[m_sem, ['FECHA','TURNO','TIPO_SESION','MINUTOS','BORG','CARGA']].to_string(index=False))

# 3) Wellness esta semana
well = pd.DataFrame(ss.worksheet('_VISTA_WELLNESS').get_all_records(value_render_option=URO))
well['FECHA'] = pd.to_datetime(well['FECHA'], errors='coerce')
m_w = (well['JUGADOR']==JUG) & (well['FECHA']>=pd.Timestamp(lunes))
print('\\n=== WELLNESS SEMANA ===')
print(well.loc[m_w, ['FECHA','SUENO','FATIGA','MOLESTIAS','ANIMO','TOTAL']].to_string(index=False))

# 4) Peso PRE últimos días
peso = pd.DataFrame(ss.worksheet('_VISTA_PESO').get_all_records(value_render_option=URO))
peso['FECHA'] = pd.to_datetime(peso['FECHA'], errors='coerce')
m_p = peso['JUGADOR']==JUG
print('\\n=== PESO ÚLT 5 ===')
print(peso.loc[m_p, ['FECHA','PESO_PRE','DESVIACION_BASELINE']].sort_values('FECHA').tail(5).to_string(index=False))
```
→ Tras el tool, RESPONDES en texto: "Cecilio esta semana: 3 sesiones,
   carga total 2.180, ACWR 1,1 (verde). Wellness medio 13,5/20 — algo
   justo pero estable. Peso PRE -0,8 kg vs base, dentro del rango. En
   general OK, sin alertas." (números inventados — usa los reales).

POLÍTICA DE FALLOS:
Si tu primer intento devuelve "0 filas" o un error, prueba:
1. Cambiar `==` por `str.contains` (jugador con alias).
2. Cambiar de `PESO` a `_VISTA_PESO` (o viceversa).
3. Re-revisar fechas (a veces vienen como número serializado).
Si tras 2 intentos sigue sin salir, **dile al usuario que no
encuentras el dato y por qué**, en lenguaje natural — no le pidas
"el nombre exacto de la columna", busca tú.

🧠 PREGUNTAS ANALÍTICAS (no solo datos puntuales):
Cuando te preguntan tipo **"¿cómo va Carlos esta semana?"**, **"qué tal
está Cecilio"**, **"cómo lleva la carga Pirata"** — NO basta con un dato.
Tienes que combinar 2-3 fuentes y dar una **valoración cualitativa DETALLADA**.

Patrón recomendado para "cómo está/va X":
1. UNA sola tool call con un script Python que cargue las hojas
   relevantes (`_VISTA_SEMAFORO`, `_VISTA_CARGA`, `_VISTA_WELLNESS`,
   `_VISTA_PESO`, opcionalmente `LESIONES`) filtradas por ese jugador
   y la última semana + comparación con la semana anterior si es útil.
2. Imprime un resumen estructurado (carga, wellness, peso, alertas).
3. **OBLIGATORIO**: tras recibir el resultado del tool, GENERA texto
   natural DETALLADO. NO te quedes mudo. NO seas escueto.

📋 FORMATO DE RESPUESTA ANALÍTICA — usa SIEMPRE este esquema cuando te
preguntan "cómo está/va X":

  *X esta semana ([N] sesiones):*

  • *Carga*: total [X], ACWR [Y] ([color]), monotonía [Z]
     - Detalle día por día si tiene 3+ sesiones
     - Compara con semana anterior si destaca el cambio

  • *Wellness*: medio [X]/20 (sueño/fatiga/molestias/ánimo)
     - Bajos: [días con TOTAL<13] / [N total días]
     - Mencionar si hay un componente concretamente flojo (ej.
       "fatiga 2/5 todos los días")

  • *Peso*: PRE medio [X] kg ([+/-Y] vs baseline), pérdida media en
     entreno [Z] kg
     - Si hay descenso/subida notable (>1.5kg), mencionarlo

  • *Otros*: si hay lesiones activas, baja recientemente, etc.

  *Valoración:* 1-2 frases tipo "OK, sigue el patrón habitual" /
  "Atención: carga alta + wellness flojo, vigilarlo" / "Lleva 3 días
  ausente, revisa si pasa algo".

REGLA CLAVE: si tienes datos, **DALOS TODOS**, no resumas en una línea.
Es mejor pasarse de detalle que quedarse corto. El cuerpo técnico
prefiere ver los números concretos.

Ejemplo bueno (detalle):
  "Cecilio esta semana (3 sesiones):
   • Carga: 2.840 total, ACWR 1,12 (verde), monotonía 1,8. Lun M 980,
     mié T 1.040, vie M 820. Semana pasada hizo 2.300, así que +540.
   • Wellness: medio 13,8/20. Sueño bajo (2,5/5) lun y mié. Resto OK.
   • Peso: PRE 76,8 kg (-0,3 vs base). Pierde 0,9 kg/sesión de media.
   • Sin lesiones activas.
   Valoración: bien, carga subiendo controlada. Vigila el sueño."

Ejemplo malo (escueto, NO HAGAS ESTO):
  "Cecilio: 3 sesiones, carga 2.840 verde. Wellness 13,8. Peso estable.
   OK."

⚠️ MUY IMPORTANTE — RESPUESTA DE TEXTO TRAS CADA TOOL:
Después de ejecutar un tool (python o bash), SIEMPRE genera una
respuesta de TEXTO en español al usuario. NO termines en silencio
después de obtener datos. El usuario está esperando que le hables,
no solo que ejecutes scripts.

Si un script falla o devuelve poca data, dilo con tus palabras
("no me sale el dato de X esta semana", "no encuentro entradas de
wellness de Pirata desde el lunes") en vez de quedarte mudo.

MÉTRICAS — qué significan los valores:
- Borg (RPE) 0-10: percepción de esfuerzo.
- sRPE / CARGA = Borg × Minutos.
- ACWR (ratio agudo/crónico): <0,8 infra-carga (azul) · 0,8-1,3 óptimo
  (verde) · 1,3-1,5 amarillo · >1,5 riesgo (rojo).
- Monotonía (carga media / desviación): >2 = riesgo (entrenas siempre
  igual de duro, sin descansos).
- Wellness total = SUENO + FATIGA + MOLESTIAS + ANIMO (cada uno 1-5).
  ≤10 alerta · 11-13 flojo · ≥14 ok.
- Peso PRE: antes del entreno. Compáralo con BASELINE_PRE.
  DESVIACION_BASELINE en kg: <-3 grave · entre -3 y -1,5 atento ·
  ≥-1,5 ok.

══════════════════════════════════════════════════════════════════════
HOJAS ADICIONALES — todo lo que se ve en el dashboard Streamlit
══════════════════════════════════════════════════════════════════════

Estas hojas también están disponibles. Cuando pregunten algo que NO
sean carga/wellness/peso/lesiones (que ya hemos cubierto arriba),
busca aquí.

### PARTIDOS · estadísticas

- **EST_PARTIDOS** (1 fila por partido): id_partido, fecha, rival,
  competicion, casa_fuera, resultado_inter, resultado_rival,
  goles_favor, goles_contra, dispatch a, faltas, amarillas, rojas,
  ...
- **EST_EVENTOS** (1 fila por evento dentro del partido): id_partido,
  fecha, rival, parte, minuto, tipo_evento, jugador, asistencia,
  zona, accion, descripcion. tipo_evento incluye: GOL_FAVOR,
  GOL_CONTRA, DISPARO_FAVOR, DISPARO_CONTRA, FALTA_FAVOR,
  FALTA_CONTRA, AMARILLA, ROJA, PENALTI, TM (tiempo muerto)...
- **EST_DISPAROS** (1 fila por disparo, ya sea propio o recibido):
  id_partido, fecha, parte, minuto, equipo (INTER/RIVAL), jugador,
  asistencia, zona_campo (A1-A11), zona_porteria (P1-P9), accion
  (CONTRAATAQUE, JUEGO_POSICIONAL, ABP_CORNER, ABP_FALTA, PORTERO_JUEGO,
  PENALTI, 10M…), resultado (GOL, PARADA, PALO, BLOQUEADO, FUERA).
- **EST_FALTAS** (1 fila por falta): id_partido, fecha, parte, minuto,
  equipo, jugador, ubicacion (zona del campo), motivo (PROTESTA,
  TÉCNICA, etc.).
- **EST_PENALTIS_10M**: tirador, portero, resultado, parte, minuto,
  partido.
- **EST_PLANTILLAS** (1 fila por jugador en cada partido):
  id_partido, fecha, jugador, dorsal, posicion, ALINEACION_INICIAL,
  MINUTOS_JUGADOS, GOLES, ASISTENCIAS, AMARILLAS, ROJAS, FALTAS_HECHAS,
  FALTAS_RECIBIDAS, DISPAROS_FAVOR, DISPAROS_PUERTA,
  GOLES_FAVOR_EN_PISTA, GOLES_CONTRA_EN_PISTA, PLUS_MINUS.
- **_VISTA_EST_JUGADOR**: agregado por jugador en toda la temporada
  (goles totales, asistencias totales, +/-, minutos, etc.).
- **_VISTA_EST_AVANZADAS**: ratios por jugador (xG, eficiencia disparo,
  gol cada N minutos, etc.).
- **_VISTA_EST_CUARTETOS**: combinaciones de 4 jugadores sin portero
  y sus métricas conjuntas (minutos juntos, goles a favor/contra mientras
  están juntos, ratio).
- **EST_TOTALES_PARTIDO**: 1 fila por partido con TODOS los totales
  (disparos por zona, faltas por zona, etc.).
- **EST_DISPAROS_ZONAS**: pivot disparos × zona campo × zona portería
  por partido.

### SCOUTING DE RIVALES

- **SCOUTING_RIVALES**: hoja maestra con 89 columnas. Para cada rival
  observado: equipo, fecha de la visualización, plantilla, sistema de
  juego, fortalezas/debilidades, jugadores clave, balón parado favor/contra,
  duelos por zona, etc.
- **_VISTA_SCOUTING_RIVAL** (129 columnas): vista limpia por rival con
  totales agregados.
- **EST_SCOUTING_PEN_10M**: cómo marca/recibe penaltis y dobles
  penaltis cada rival visto.

⚠ Si te preguntan "cómo marca / recibe los goles el [RIVAL]", "cuál
es la zona predilecta de [RIVAL]", "cómo defiende [RIVAL] las ABP" →
USA estas hojas. NO redirijas al bot dev.

### EJERCICIOS DE ENTRENO (con GPS Oliver)

- **_EJERCICIOS** (input manual de Arkaitz): id_sesion, fecha, turno,
  nombre_ejercicio, tipo_ejercicio, minuto_inicio, minuto_fin, jugadores,
  notas.
- **_VISTA_EJERCICIOS** (1 fila por jugador × ejercicio, 37 columnas):
  agrega métricas Oliver (distancia, velocidad media/máx, sprints,
  aceleraciones, decel, HSR…) sobre el rango del ejercicio.

### OLIVER (GPS)

- **OLIVER** (~5000 filas, 15 cols MVP): por sesión y jugador. Distancia,
  HSR, sprints, velocidad máxima, número aceleraciones/decel, carga
  mecánica.
- **_OLIVER_DEEP** (68 métricas): si necesitas el detalle profundo
  (potencia metabólica, distancia por zonas de velocidad, etc.).
- **_VISTA_OLIVER** (31 cols): cruza Oliver con Borg y CARGA → ratios
  útiles tipo eficiencia_sprint, asimetria_acc, densidad_metabolica,
  pct_hsr, acwr_mecanico.

### ANTROPOMETRÍA (nutricionista)

- **ANTROPOMETRIA**: por jugador y fecha de medición: peso, altura,
  IMC, pliegues cutáneos (tríceps, subescapular, abdominal,
  supraespinal, muslo, pantorrilla), sumatorio_6_pliegues_mm,
  masa_grasa_yuhasz_pct, masa_grasa_faulkner_pct, masa_muscular_kg,
  somatotipo (endomórfico/mesomórfico/ectomórfico).
- Sumatorio 6 pliegues: <30 muy bajo · 30-45 excelente · 45-50 bueno ·
  50-60 aceptable · 60-80 regular · >80 bajo rendimiento.

### ROSTER

- **JUGADORES_ROSTER**: dorsal, nombre, posicion (PORTERO/CAMPO),
  equipo (PRIMER/FILIAL), activo (TRUE/FALSE).
  ⚠ Para "cuartetos sin portero" filtra primero por posicion != PORTERO.

REGLA OPERATIVA para preguntas de partido/scouting:
- "Goles que ha metido X esta temporada" → `_VISTA_EST_JUGADOR` o
  contar `EST_EVENTOS` con tipo_evento='GOL_FAVOR' & jugador='X'.
- "De qué zona tira más X" → `EST_DISPAROS` filtrado por jugador,
  agrupado por zona_campo, contar.
- "Cuántos goles encajamos por penalti" → `EST_PENALTIS_10M` o
  `EST_EVENTOS` con tipo_evento='GOL_CONTRA' y accion='PENALTI'.
- "Cómo recibe los goles el Barça" → `_VISTA_SCOUTING_RIVAL` filtrado
  por equipo='Barça'; mira columnas relacionadas con "goles_contra" /
  "ubic_def" / "abp_contra" / similares.
- "Cuartetos top sin portero" → `_VISTA_EST_CUARTETOS`. Si necesitas
  recalcular, primero excluye porteros (HERRERO, GARCIA, OSCAR) de
  cualquier combinación.

⚠ Si una pregunta requiere mezclar hojas (p. ej. carga semanal + minutos
de partido), haz dos lecturas en el mismo bloque python, mergea con
pandas y reporta el resultado.
"""


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _authorized(update: Update) -> bool:
    return bool(update.effective_chat) and update.effective_chat.id in ALLOWED_CHAT_IDS


def _chunks(text: str, size: int = MAX_MSG_LEN):
    if len(text) <= size:
        yield text
        return
    while text:
        if len(text) <= size:
            yield text
            return
        corte = text.rfind("\n", 0, size)
        if corte == -1 or corte < size // 2:
            corte = size
        yield text[:corte]
        text = text[corte:].lstrip("\n")


async def _keep_typing(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE, stop: asyncio.Event):
    try:
        while not stop.is_set():
            try:
                await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        pass


# Chats que quieren empezar conversación nueva (tras /nuevo)
_fresh_chats: Set[int] = set()

# Modelo Whisper (lazy load; primera vez descarga ~150MB)
_whisper_model = None
_whisper_lock = asyncio.Lock()
WHISPER_SIZE = os.getenv("WHISPER_MODEL", "base")  # tiny/base/small/medium


async def get_whisper():
    """Carga perezosa del modelo Whisper, protegida contra carga concurrente."""
    global _whisper_model
    if not _WHISPER_OK:
        return None
    if _whisper_model is not None:
        return _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            log.info("Cargando modelo Whisper (%s) — primera vez tarda…", WHISPER_SIZE)
            # Cargar en un hilo para no bloquear el event loop
            def _load():
                return WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
            _whisper_model = await asyncio.get_event_loop().run_in_executor(None, _load)
            log.info("Whisper listo.")
    return _whisper_model


async def _transcribir(audio_path: str) -> str:
    """Transcribe un archivo de audio (.ogg de Telegram) a texto español."""
    model = await get_whisper()
    if model is None:
        raise RuntimeError("Whisper no disponible (faster-whisper no instalado).")
    def _run():
        segments, info = model.transcribe(
            audio_path, language="es", beam_size=5, vad_filter=True,
        )
        return " ".join(s.text for s in segments).strip()
    return await asyncio.get_event_loop().run_in_executor(None, _run)


# ─── Backend Gemini: tool-use loop con bash + read_file ─────────────────────
# Conversación en memoria por chat_id. Si el bot se reinicia, se pierde.
_conv_history: Dict[int, List[Dict[str, Any]]] = {}

# ── Validación de SOLO LECTURA (cinturón de seguridad) ─────────────────────
# El system prompt dice "solo lectura" pero hay que enforcearlo a nivel de
# código por si Gemini malinterpreta o un usuario malicioso fuerza una
# operación de escritura. Cualquier patrón de escritura se rechaza ANTES
# de ejecutar.
_PATRONES_BLOQUEADOS_PYTHON = [
    # Métodos gspread que modifican el Sheet
    (r"\.update_cell\s*\(",            "update_cell"),
    (r"\.update_acell\s*\(",           "update_acell"),
    (r"\.update_cells\s*\(",           "update_cells"),
    (r"\.update_values\s*\(",          "update_values"),
    (r"\.append_row\s*\(",             "append_row"),
    (r"\.append_rows\s*\(",            "append_rows"),
    (r"\.batch_update\s*\(",           "batch_update"),
    (r"\.batch_clear\s*\(",            "batch_clear"),
    (r"\.delete_row\s*\(",             "delete_row"),
    (r"\.delete_rows\s*\(",            "delete_rows"),
    (r"\.delete_columns?\s*\(",        "delete_column(s)"),
    (r"\.insert_row\s*\(",             "insert_row"),
    (r"\.insert_rows\s*\(",            "insert_rows"),
    (r"\.insert_cols?\s*\(",           "insert_col(s)"),
    (r"\.add_worksheet\s*\(",          "add_worksheet"),
    (r"\.del_worksheet\s*\(",          "del_worksheet"),
    (r"\.duplicate\s*\(",              "duplicate"),
    (r"\.copy_to\s*\(",                "copy_to"),
    (r"\.batch_format\s*\(",           "batch_format"),
    (r"\.merge_cells\s*\(",            "merge_cells"),
    (r"\.unmerge_cells\s*\(",          "unmerge_cells"),
    (r"\.add_protected_range",         "add_protected_range"),
    (r"\.delete_protected_range",      "delete_protected_range"),
    # Escritura de archivos
    (r"open\s*\([^)]*['\"][wax]\+?b?['\"]",         "open() en modo escritura"),
    (r"open\s*\([^)]*mode\s*=\s*['\"][wax]\+?b?['\"]",  "open(mode='w'/'a'/'x')"),
    (r"\.write_text\s*\(",             "Path.write_text"),
    (r"\.write_bytes\s*\(",            "Path.write_bytes"),
    # Borrado / movimiento de archivos
    (r"os\.remove\s*\(",               "os.remove"),
    (r"os\.unlink\s*\(",               "os.unlink"),
    (r"os\.rmdir\s*\(",                "os.rmdir"),
    (r"os\.makedirs\s*\(",             "os.makedirs"),
    (r"os\.rename\s*\(",               "os.rename"),
    (r"shutil\.rmtree\s*\(",           "shutil.rmtree"),
    (r"shutil\.move\s*\(",             "shutil.move"),
    (r"shutil\.copy\w*\s*\(",          "shutil.copy*"),
    # Subprocess / system (puede ejecutar cualquier cosa)
    (r"os\.system\s*\(",               "os.system"),
    (r"subprocess\.\w+\s*\(",          "subprocess.*"),
    (r"\bPopen\s*\(",                  "Popen"),
    # Eval / exec dinámico
    (r"\beval\s*\(",                   "eval()"),
    (r"\bexec\s*\(",                   "exec()"),
    (r"__import__\s*\(\s*['\"]os['\"]", "__import__('os') sospechoso"),
]

_PATRONES_BLOQUEADOS_BASH = [
    (r"\brm\s+",                       "rm"),
    (r"\bmv\s+",                       "mv"),
    (r"\bcp\s+",                       "cp"),
    (r"\bchmod\s+",                    "chmod"),
    (r"\bchown\s+",                    "chown"),
    (r"\bmkdir\s+",                    "mkdir"),
    (r"\brmdir\s+",                    "rmdir"),
    (r"\btouch\s+",                    "touch"),
    (r"(^|\s|;|\|)>\s*\S",             "redirección > (escritura)"),
    (r"(^|\s|;|\|)>>\s*\S",            "redirección >> (append)"),
    (r"\btee\b",                       "tee"),
    (r"\bgit\s+(commit|push|add|rm|mv|reset|checkout|merge|rebase|stash|tag|init|clone|pull)\b",
                                       "git mutador"),
    (r"\bsudo\b",                      "sudo"),
    (r"\bdd\s+",                       "dd"),
    (r"\bmkfs\b",                      "mkfs"),
    (r"\bshutdown\b",                  "shutdown"),
    (r"\breboot\b",                    "reboot"),
    (r"\bkillall\b",                   "killall"),
    (r"\bcurl\b.*-X\s+(POST|PUT|DELETE|PATCH)\b",   "curl mutador (-X POST/PUT/...)"),
    (r"\bcurl\b.*--data\b",            "curl --data (POST)"),
    (r"\bwget\b.*-O\s+",               "wget -O (escribe archivo)"),
    (r"\bsed\b.*-i\b",                 "sed -i (modifica archivo)"),
]


def _validar_solo_lectura_python(code: str) -> Optional[str]:
    """Comprueba si el código Python contiene operaciones de escritura
    prohibidas. Devuelve None si OK, mensaje de error si bloqueado."""
    for pat, nombre in _PATRONES_BLOQUEADOS_PYTHON:
        if re.search(pat, code):
            return (
                f"❌ Operación bloqueada por seguridad: detectada `{nombre}`.\n"
                f"Este bot es de SOLO LECTURA — no puede modificar Sheets, "
                f"archivos ni ejecutar comandos del sistema. Reformula la "
                f"consulta sin escribir nada."
            )
    return None


def _validar_solo_lectura_bash(cmd: str) -> Optional[str]:
    """Comprueba si el comando bash contiene operaciones prohibidas."""
    for pat, nombre in _PATRONES_BLOQUEADOS_BASH:
        if re.search(pat, cmd):
            return (
                f"❌ Comando bloqueado por seguridad: detectado `{nombre}`.\n"
                f"Este bot es de SOLO LECTURA. Solo se permiten comandos de "
                f"consulta (ls, head, grep, etc.) sin escritura."
            )
    return None


# Definición de herramientas (function calling). Solo lectura.
TOOLS_BOT_DATOS = [
    {
        "function_declarations": [
            {
                "name": "python",
                "description": (
                    "Ejecuta código Python con /usr/bin/python3 y devuelve "
                    "stdout+stderr. Es la herramienta principal para consultar "
                    "Google Sheets (gspread, pandas ya instalados). Pasas el "
                    "código tal cual, SIN escapado de shell ni envoltorios "
                    "raros: simplemente el contenido del script. Solo lectura: "
                    "NO escribir archivos, NO commits, NO modificar Sheets."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Código Python a ejecutar. Ejemplo:\n"
                                "import gspread\n"
                                "from google.oauth2.service_account import Credentials\n"
                                "creds = Credentials.from_service_account_file(...)\n"
                                "ss = gspread.authorize(creds).open('Arkaitz - Datos Temporada 2526')\n"
                                "print(len(ss.worksheet('BORG').get_all_values()) - 1)"
                            ),
                        }
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "bash",
                "description": (
                    "Ejecuta un comando shell genérico (ls, head, tail, grep, "
                    "git log…). Para ejecutar Python usa la herramienta "
                    "`python` en su lugar. Solo lectura: NO escribir, NO commits, NO git push."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Comando shell completo.",
                        }
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Lee un archivo de texto del proyecto y devuelve su contenido.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Ruta del archivo (relativa al proyecto o absoluta).",
                        }
                    },
                    "required": ["path"],
                },
            },
        ]
    }
]


def _exec_tool(name: str, args: Dict[str, Any]) -> str:
    """Ejecuta una herramienta y devuelve el resultado (texto)."""
    try:
        if name == "python":
            code = args.get("code", "")
            if not code.strip():
                return "ERROR: código vacío."
            # ── Cinturón de seguridad: solo lectura ──
            error_validacion = _validar_solo_lectura_python(code)
            if error_validacion:
                log.warning(
                    "[bot_datos] Bloqueado código con escritura: %s...",
                    code[:200].replace("\n", " "),
                )
                return error_validacion
            # Usamos el mismo Python con el que corre el bot (venv 3.11), que
            # tiene gspread/pandas/etc. instalados con versiones coherentes.
            # /usr/bin/python3 (sistema 3.8 en Catalina) crasheaba con SIGSEGV
            # al importar pandas 2.x compilado contra numpy nuevo.
            import sys as _sys
            python_exe = _sys.executable

            # ── Preludio READ-ONLY (defensa en profundidad) ──
            # Si hay una SA readonly configurada, monkey-patcheamos
            # `Credentials.from_service_account_file` para que SIEMPRE
            # use el archivo readonly, independientemente de lo que
            # Gemini escriba. El SA readonly tiene permiso Viewer en el
            # Sheet, así que Google API rechaza cualquier escritura con
            # 403 a nivel red — imposible bypassear desde Python.
            preludio = ""
            if READONLY_CREDS_FILE and Path(READONLY_CREDS_FILE).is_file():
                preludio = (
                    "import google.oauth2.service_account as _sa_ro\n"
                    "_orig_from_file_ro = _sa_ro.Credentials.from_service_account_file\n"
                    "def _readonly_from_file(*args, **kwargs):\n"
                    f"    return _orig_from_file_ro({READONLY_CREDS_FILE!r}, **{{k: v for k, v in kwargs.items() if k != 'filename'}})\n"
                    "_sa_ro.Credentials.from_service_account_file = _readonly_from_file\n"
                    "del _orig_from_file_ro, _readonly_from_file, _sa_ro\n"
                    "\n"
                )

            # ── Auto-prelude del Sheet ──
            # Si el código menciona el Sheet, le inyectamos imports + ss ya abierto
            # para que Gemini no se olvide de los imports (atajo típico de 2.5 Flash Lite).
            # Pero si el código YA tiene imports completos, NO inyectamos (sería
            # duplicar la llamada a Sheets/Drive y a veces falla por throttle).
            needs_sheet = any(
                k in code
                for k in ("ss.", "gspread", "creds", "gc.open", "from google.oauth2")
            )
            has_full_imports = (
                "from google.oauth2" in code
                and "from_service_account_file" in code
                and "gspread.authorize" in code
            )
            if needs_sheet and not has_full_imports:
                preludio += (
                    "# --- Auto-prelude inyectado por el bot ---\n"
                    "import pandas as pd\n"
                    "import gspread\n"
                    "from google.oauth2.service_account import Credentials\n"
                    "_creds = Credentials.from_service_account_file(\n"
                    f"    {repr(str(PROJECT_DIR / 'google_credentials.json'))},\n"
                    "    scopes=['https://www.googleapis.com/auth/spreadsheets',\n"
                    "            'https://www.googleapis.com/auth/drive'])\n"
                    "_gc = gspread.authorize(_creds)\n"
                    "ss = _gc.open('Arkaitz - Datos Temporada 2526')\n"
                    "creds, gc = _creds, _gc\n"
                    "# --- Fin del prelude ---\n\n"
                )

            # Pasamos el código por stdin para evitar escapado de shell
            result = subprocess.run(
                [python_exe],
                input=preludio + code,
                capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=120,
            )
            out = (result.stdout or "")
            if result.stderr:
                # Filtrar warnings ruidosos de gRPC/google.auth (no son errores)
                stderr_lines = []
                for ln in result.stderr.splitlines():
                    if ("FutureWarning" in ln or "ev_poll_posix" in ln
                            or "warnings.warn" in ln or "ABSL" in ln):
                        continue
                    stderr_lines.append(ln)
                stderr_clean = "\n".join(stderr_lines).strip()
                if stderr_clean:
                    out += "\n[STDERR]\n" + stderr_clean
            if result.returncode != 0:
                out += f"\n[exit code: {result.returncode}]"
            if len(out) > 50000:
                out = out[:50000] + f"\n[...truncado, total {len(out)} chars]"
            return out or "(sin output)"
        elif name == "bash":
            cmd = args.get("command", "").strip()
            if not cmd:
                return "ERROR: comando vacío."
            # ── Cinturón de seguridad: solo lectura ──
            error_validacion = _validar_solo_lectura_bash(cmd)
            if error_validacion:
                log.warning(
                    "[bot_datos] Bloqueado comando con escritura: %s",
                    cmd[:200],
                )
                return error_validacion
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=120,
            )
            out = (result.stdout or "") + ("\n[STDERR]\n" + result.stderr if result.stderr else "")
            if len(out) > 50000:
                out = out[:50000] + f"\n[...truncado, total {len(out)} chars]"
            return out or "(sin output)"
        elif name == "read_file":
            p = Path(args.get("path", ""))
            if not p.is_absolute():
                p = PROJECT_DIR / p
            try:
                p = p.resolve()
                # Cinturón: que no se salga del proyecto
                p.relative_to(PROJECT_DIR.resolve())
            except Exception:
                return f"ERROR: ruta fuera del proyecto: {p}"
            if not p.is_file():
                return f"ERROR: no es un archivo: {p}"
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 80000:
                content = content[:80000] + f"\n[...truncado, total {len(content)} chars]"
            return content
        else:
            return f"ERROR: herramienta desconocida '{name}'."
    except subprocess.TimeoutExpired:
        return "ERROR: comando excedió 120s."
    except Exception as e:
        return f"ERROR ejecutando {name}: {type(e).__name__}: {e}"


def _truncate_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Limita el histórico a las últimas HISTORY_MAX_TURNS entradas usuario+modelo."""
    if len(history) <= HISTORY_MAX_TURNS * 2:
        return history
    return history[-HISTORY_MAX_TURNS * 2:]


async def _gemini_call_with_retry(model, history, max_retries: int = 3):
    """Llama a Gemini con retry exponencial ante errores transitorios.

    Reintenta hasta `max_retries + 1` veces con backoff [2, 5, 10] segundos.
    Reintenta: rate limits per-minute, timeouts, 5xx, errores de red.
    NO reintenta: daily quota agotada, autenticación, InvalidArgument.
    """
    delays = [2, 5, 10]
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(model.generate_content, history)
        except Exception as e:
            last_err = e
            err_str = str(e)
            err_low = err_str.lower()
            non_retryable = (
                "api key" in err_low,
                "authentication" in err_low,
                "permission denied" in err_low,
                "invalid argument" in err_low,
                "perdayperprojectpermodel" in err_low,
            )
            if any(non_retryable):
                raise
            if attempt >= max_retries:
                raise
            wait_s = delays[min(attempt, len(delays) - 1)]
            log.warning("[gemini retry %d/%d] %s: %s. Reintentando en %ds.",
                        attempt + 1, max_retries, type(e).__name__,
                        err_str[:200], wait_s)
            await asyncio.sleep(wait_s)
    raise last_err  # no debería llegar


async def _run_gemini(chat_id: int, prompt: str, continue_session: bool = True,
                       progress_cb=None) -> Tuple[int, str, str]:
    """Llama a Gemini con tool-use loop. Mantiene historial por chat_id.

    `progress_cb`: callable async opcional. Si está, se llama UNA vez
    con un mensaje de progreso cuando el modelo decide hacer la primera
    tool call (señal de que la respuesta tardará algo más). No se llama
    para queries instantáneas (saludos, preguntas que no requieren datos)."""
    if not continue_session:
        _conv_history.pop(chat_id, None)
    history = _conv_history.get(chat_id, [])
    history.append({"role": "user", "parts": [{"text": prompt}]})

    # Sustitución dinámica: hoy ISO en el system prompt
    hoy_iso = _dt.date.today().isoformat()
    system_eff = SYSTEM_PROMPT.replace("__HOY__", hoy_iso)

    # Safety: deshabilitamos los filtros (uso interno club, datos
    # deportivos neutros, falsos positivos frecuentes con apodos como
    # "Pirata" + "fatiga"/"carga").
    _safety_off = [
        {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_eff,
        tools=TOOLS_BOT_DATOS,
        safety_settings=_safety_off,
    )

    progress_sent = False
    # Cuántas veces hemos forzado un "wake up" del modelo cuando termina mudo
    # tras un tool call. Lo limitamos para evitar bucles si está realmente mal.
    wake_ups_usados = 0
    WAKE_UPS_MAX = 1

    try:
        async with asyncio.timeout(LLM_TIMEOUT):
            for step in range(GEMINI_MAX_STEPS):
                # Llamar al modelo con retry+backoff ante errores transitorios
                response = await _gemini_call_with_retry(model, history)

                # Extraer parts de la respuesta
                candidates = getattr(response, "candidates", None) or []
                if not candidates:
                    return -1, "", "Gemini devolvió respuesta vacía (sin candidates)."
                cand = candidates[0]
                content = getattr(cand, "content", None)
                if not content or not getattr(content, "parts", None):
                    # ── Diagnóstico fino de finish_reason ──
                    # Códigos de Gemini API:
                    #   1=STOP, 2=MAX_TOKENS, 3=SAFETY, 4=RECITATION, 5=OTHER,
                    #   6=BLOCKLIST, 7=PROHIBITED_CONTENT, 8=SPII,
                    #   9=MALFORMED_FUNCTION_CALL, 10=IMAGE_SAFETY,
                    #   12=UNEXPECTED_TOOL_CALL, 13=TOO_MANY_TOOL_CALLS
                    finish_raw = getattr(cand, "finish_reason", None)
                    try:
                        finish_int = int(finish_raw) if finish_raw is not None else -1
                    except (TypeError, ValueError):
                        finish_int = -1

                    # Caso 1: STOP (1) sin contenido tras un tool call. Es el bug
                    # conocido de Gemini 2.0/2.5 Flash con function calling: el
                    # modelo "termina" sin generar texto final. Forzamos un
                    # mensaje al usuario para que produzca la respuesta natural.
                    if (finish_int == 1
                            and step > 0
                            and wake_ups_usados < WAKE_UPS_MAX):
                        wake_ups_usados += 1
                        log.warning(
                            "[%s] finish_reason=STOP sin contenido tras tool call. "
                            "Forzando wake-up (%d/%d).",
                            chat_id, wake_ups_usados, WAKE_UPS_MAX,
                        )
                        history.append({
                            "role": "user",
                            "parts": [{"text": (
                                "Produce ahora una respuesta en español, en "
                                "lenguaje natural, basándote en los datos que "
                                "acabas de obtener. Sigue el tono y formato del "
                                "system prompt (frases cortas, números concretos, "
                                "como compañero del cuerpo técnico). "
                                "No uses más herramientas, solo responde."
                            )}],
                        })
                        continue

                    # Caso 2: SAFETY o filtros similares
                    if finish_int in (3, 6, 7, 8, 10):
                        return (-1, "",
                                f"Gemini bloqueó la respuesta por filtros de "
                                f"contenido (finish_reason={finish_int}). Si crees "
                                f"que es un falso positivo, reformula la pregunta.")

                    # Caso 3: MAX_TOKENS
                    if finish_int == 2:
                        return (-1, "",
                                "La respuesta de Gemini fue cortada por longitud. "
                                "Pídele datos en bloques más pequeños.")

                    # Caso 4: tool call malformado o exceso de tools
                    if finish_int in (9, 12, 13):
                        return (-1, "",
                                f"Gemini tuvo un problema al usar las "
                                f"herramientas (finish_reason={finish_int}). "
                                f"Reformula la pregunta más simple.")

                    # Otros casos (incl. 1 sin tool previo, o desconocidos)
                    return (-1, "",
                            f"Gemini terminó sin contenido (finish_reason={finish_int}).")

                parts = list(content.parts)

                # Detectar function_calls
                fcalls = []
                for p in parts:
                    fc = getattr(p, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        fcalls.append(fc)

                if fcalls:
                    # Notificar al usuario en el primer tool call (la respuesta
                    # va a tardar más de lo habitual)
                    if progress_cb is not None and not progress_sent:
                        try:
                            await progress_cb("🔧 Consultando los datos del Sheet, dame un momento…")
                            progress_sent = True
                        except Exception:
                            pass
                    # Guardar el mensaje del modelo (con sus tool calls) en historial
                    history.append({"role": "model", "parts": parts})
                    # Ejecutar todas las herramientas y devolver resultados
                    tool_response_parts = []
                    for fc in fcalls:
                        # fc.args es un dict-like (proto MapComposite)
                        try:
                            args = dict(fc.args) if fc.args else {}
                        except Exception:
                            args = {}
                        # Log completo del comando para debugging
                        if fc.name == "python":
                            log.info("[%s] >>> PYTHON:\n%s", chat_id, args.get("code", ""))
                        elif fc.name == "bash":
                            log.info("[%s] >>> BASH:\n%s", chat_id, args.get("command", ""))
                        else:
                            log.info("[%s] tool '%s' args=%s", chat_id, fc.name, str(args))
                        result = await asyncio.to_thread(_exec_tool, fc.name, args)
                        # Log del resultado (truncado a 800 chars para no saturar)
                        log.info("[%s] <<< RESULT (%s, %d chars):\n%s",
                                 chat_id, fc.name, len(result), result[:800])
                        tool_response_parts.append({
                            "function_response": {
                                "name": fc.name,
                                "response": {"result": result},
                            }
                        })
                    history.append({"role": "user", "parts": tool_response_parts})
                    continue

                # Sin function_calls: respuesta final en texto
                text = ""
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        text += t
                history.append({"role": "model", "parts": [{"text": text}]})
                _conv_history[chat_id] = _truncate_history(history)
                return 0, text.strip(), ""

            # Salimos del bucle por límite de pasos
            _conv_history[chat_id] = _truncate_history(history)
            return -1, "", f"Límite de iteraciones alcanzado ({GEMINI_MAX_STEPS})."
    except asyncio.TimeoutError:
        return -1, "", f"Timeout: Gemini tardó más de {LLM_TIMEOUT}s."
    except Exception as e:
        log.exception("Error en _run_gemini: %s", e)
        return -1, "", f"{type(e).__name__}: {e}"
    # NB: si llegamos aquí, devolvemos algo válido para que el helper original
    # de _process_prompt no pete; el envoltorio antiguo esperaba (rc, out, err).
    return 0, "(sin texto)", ""


# Compat: dejamos un alias por si algún sitio del repo aún llama _run_claude.
_run_claude = _run_gemini


# ─── Handlers ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text(
            "🚫 Acceso denegado.\n\n"
            "Si eres miembro del cuerpo técnico o jugador y crees que deberías "
            "tener acceso, escríbele a Arkaitz con tu chat_id.\n\n"
            f"Tu chat_id es: {update.effective_chat.id if update.effective_chat else '?'}"
        )
        return
    await update.message.reply_text(
        "👋 Hola! Soy el asistente de datos del equipo.\n\n"
        "Pregúntame cualquier cosa sobre los datos de la temporada:\n"
        "• «¿cuánto peso perdió Carlos ayer?»\n"
        "• «dame el ACWR del equipo esta semana»\n"
        "• «qué jugadores tienen wellness bajo últimamente»\n"
        "• «cuántas sesiones lleva Gonzalo esta temporada»\n\n"
        "Mantengo el hilo entre mensajes: puedes preguntar «y Pirata?» "
        "después de preguntar por Carlos, y entiendo el contexto.\n\n"
        "Comandos:\n"
        "• /nuevo → empezar conversación nueva\n"
        "• /yo → ver tu chat_id"
    )


async def cmd_yo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    user = update.effective_user.username if update.effective_user else None
    await update.message.reply_text(
        f"Tu chat_id es: `{chat_id}`\n"
        f"Usuario: @{user if user else 'sin_username'}\n\n"
        f"{'✅ Estás autorizado.' if _authorized(update) else '❌ NO estás autorizado todavía. Pídele acceso a Arkaitz.'}",
        parse_mode="Markdown",
    )


async def cmd_nuevo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    _fresh_chats.add(chat_id)
    # Limpiamos también el histórico de Gemini de ese chat
    _conv_history.pop(chat_id, None)
    await update.message.reply_text(
        "🆕 Vale, el próximo mensaje empezará una conversación nueva "
        "(olvido el contexto anterior)."
    )


async def cmd_oliver_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Permite al cuerpo técnico disparar la sincronización de Oliver."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🏃 Sincronizando Oliver Sports (MVP)…")
    stop = asyncio.Event()
    task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "oliver_sync.py"),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=1200)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            await update.message.reply_text("⚠️ Timeout (>20 min).")
            return
    finally:
        stop.set()
        try: await task
        except Exception: pass

    if proc.returncode == 0:
        # Recalcular cruces
        proc2 = await asyncio.create_subprocess_exec(
            sys.executable, str(PROJECT_DIR / "src" / "calcular_vistas.py"),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc2.communicate(), timeout=600)
        except asyncio.TimeoutError:
            proc2.kill(); await proc2.wait()
        await update.message.reply_text("✅ Sincronizado. Ya están los datos actualizados.")
    else:
        detalle = (err or out or b"").decode("utf-8", "replace").strip()
        for chunk in _chunks(f"❌ Error:\n{detalle[-1500:]}"):
            await update.message.reply_text(chunk)


def _detectar_intent_estado(prompt: str) -> Optional[Tuple[str, int]]:
    """Detecta si el prompt es del tipo 'estado/carga/qué tal de JUGADOR'.

    Devuelve (canónico, N_sesiones) si lo detecta, None si no.
    Cuando detecta, el bot ejecuta directamente `estado_jugador.py` sin
    pasar por Gemini (más rápido y robusto: zero LLM, zero safety filters).
    """
    if not prompt:
        return None
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from aliases_jugadores import ROSTER_CANONICO, ALIASES_JUGADOR  # type: ignore
    except Exception:
        return None

    # Normalizar: minúsculas, sin acentos
    p = prompt.lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        p = p.replace(a, b)

    # Triggers: palabras que indican intent de "estado del jugador"
    triggers = (
        "como esta", "como va", "que tal", "estado de", "estado ",
        "carga ", "fatiga", "borg", "minutos de", "wellness de",
        "resumen de", "cuentame de", "como anda",
    )
    if not any(t in p for t in triggers):
        return None

    # Buscar nombre del jugador (tokenizado por espacios y signos)
    tokens = re.findall(r"[a-z0-9]+", p)
    canonico: Optional[str] = None

    # Construir mapa de candidatos: aliases + canónicos normalizados.
    candidatos: Dict[str, str] = {}
    for canon in ROSTER_CANONICO:
        candidatos[canon.lower()] = canon
    for ali, canon in ALIASES_JUGADOR.items():
        ali_low = ali.lower().replace(".", "").replace(" ", "")
        candidatos[ali_low] = canon
        for w in ali.lower().split():
            w_clean = w.replace(".", "")
            if len(w_clean) >= 4:  # evita matches de "j", "de", etc.
                candidatos.setdefault(w_clean, canon)

    for tok in tokens:
        if tok in candidatos:
            canonico = candidatos[tok]
            break
    if canonico is None:
        return None

    # N de sesiones (default 10)
    n = 10
    m = re.search(r"ultim[ao]s?\s+(\d+)", p)
    if not m:
        m = re.search(r"(\d+)\s*sesiones?", p)
    if m:
        try:
            n = max(1, min(50, int(m.group(1))))
        except ValueError:
            pass

    return (canonico, n)


def _detectar_intent_carga_ultima(prompt: str) -> Optional[str]:
    """Detecta si el prompt es del tipo 'carga jugador por jugador de la
    última sesión' / 'borg del último entreno' / 'carga de hoy' / 'qué tal
    la última sesión'. Devuelve fecha YYYY-MM-DD si especifica una,
    "" si es la última, None si no matchea.

    Reconoce fechas en MUCHOS formatos: "13/05", "13-05-2026", "2026-05-13",
    "13 de mayo", "13 mayo", "hoy", "ayer", "anteayer", "el lunes".
    """
    if not prompt:
        return None
    p = prompt.lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        p = p.replace(a, b)

    sesion_triggers = (
        "ultima sesion", "ultimo entreno", "ultimo entrenamiento",
        "del entreno de hoy", "sesion de hoy", "entreno de hoy",
        "que tal el entreno", "que tal la sesion",
        "que tal el ultimo entreno", "que tal la ultima sesion",
        "como ha ido el entreno", "como ha ido la sesion",
        "entreno de ayer", "sesion de ayer", "entreno ayer",
    )
    carga_triggers = (
        "carga jugador", "carga por jugador", "carga del equipo",
        "carga de la sesion", "carga del entreno", "borg de hoy",
        "borg de la sesion", "borg del entreno", "borg jugador",
        "como fue la carga", "que carga", "que borg",
        "borg del ", "carga del ", "borg de ayer", "carga de ayer",
        "carga de hoy", "carga jugador por jugador",
    )

    matches_carga = any(t in p for t in carga_triggers)
    matches_sesion = any(t in p for t in sesion_triggers)
    if not (matches_carga or matches_sesion):
        return None

    import re as _re
    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    hoy = _dt.datetime.now(tz=_ZI("Europe/Madrid")).date()

    # 1) Palabras clave temporales
    if "anteayer" in p:
        return (hoy - _dt.timedelta(days=2)).isoformat()
    if "ayer" in p:
        return (hoy - _dt.timedelta(days=1)).isoformat()
    if "hoy" in p:
        return hoy.isoformat()

    # 2) ISO YYYY-MM-DD
    m = _re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", p)
    if m:
        return m.group(0)

    # 3) DD/MM/YYYY o DD-MM-YYYY o DD/MM (asume año actual)
    m = _re.search(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b", p)
    if m:
        d, mo, y = m.groups()
        if not y:
            y = str(hoy.year)
        elif len(y) == 2:
            y = "20" + y
        try:
            return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass

    # 4) "13 de mayo" / "13 mayo" / "del 13 de mayo de 2026"
    MESES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
             "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
             "noviembre":11,"diciembre":12}
    pat = _re.compile(r"\b(\d{1,2})\s+(?:de\s+)?(" + "|".join(MESES.keys()) + r")(?:\s+(?:de\s+)?(\d{4}))?\b")
    m = pat.search(p)
    if m:
        d, mes_n, y = m.groups()
        mo = MESES[mes_n]
        if not y:
            y = str(hoy.year)
        try:
            return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass

    # 5) Sin fecha explícita → última sesión
    return ""


def _run_carga_ultima(fecha: str = "") -> str:
    """Ejecuta src/carga_ultima_sesion.py vía script_runner curado."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    args = [fecha] if fecha else []
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "carga_ultima_sesion.py"),
        args, timeout=60,
    )
    if not res.ok:
        return f"⚠️ Error al consultar carga última sesión: {res.salida}"
    return res.salida


def _run_estado_jugador(canonico: str, n: int) -> str:
    """Ejecuta src/estado_jugador.py vía el helper común script_runner."""
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    try:
        from script_runner import run_curated_script  # type: ignore
    except Exception as e:
        return f"⚠️ No puedo importar script_runner: {type(e).__name__}: {e}"
    res = run_curated_script(
        str(PROJECT_DIR / "src" / "estado_jugador.py"),
        [canonico, str(n)],
        timeout=60,
    )
    if not res.ok:
        return f"⚠️ Error al consultar {canonico}: {res.salida}"
    return res.salida


async def _process_prompt(prompt: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                          kind: str = "texto"):
    """Pasa el prompt a Claude y devuelve la respuesta al chat.
    Misma lógica se usa para mensajes de texto y mensajes de voz transcritos."""
    chat_id = update.effective_chat.id
    user_name = (update.effective_user.first_name if update.effective_user else None) or "usuario"
    continuar = chat_id not in _fresh_chats
    _fresh_chats.discard(chat_id)

    # ── ATAJO sin LLM: carga de la última sesión (jugador por jugador) ──
    # Frases tipo "carga jugador por jugador de la última sesión",
    # "borg del último entreno", "qué tal la sesión de hoy".
    # Ejecuta src/carga_ultima_sesion.py directo, sin Gemini.
    intent_cu = _detectar_intent_carga_ultima(prompt)
    if intent_cu is not None:
        log.info("[%s] ATAJO intent=carga_ultima_sesion fecha=%r (prompt='%s')",
                 chat_id, intent_cu, prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        salida = await asyncio.to_thread(_run_carga_ultima, intent_cu)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            try:
                await update.message.reply_text(trozo, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(trozo)
        return

    # ── ATAJO sin LLM: estado de jugador ──
    # Si el prompt es claramente "cómo está X / carga últimas N de X / qué tal X",
    # ejecuta directamente el script curado y responde. Sin pasar por Gemini
    # (más rápido, más fiable, sin riesgo de safety filters).
    intent = _detectar_intent_estado(prompt)
    if intent:
        canonico, n = intent
        log.info("[%s] ATAJO intent=estado_jugador jugador=%s n=%d (prompt='%s')",
                 chat_id, canonico, n, prompt[:80])
        await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
        salida = await asyncio.to_thread(_run_estado_jugador, canonico, n)
        # Mandar en trozos si es muy largo (limite Telegram 4096)
        for trozo in [salida[i:i+3800] for i in range(0, len(salida), 3800)]:
            await update.message.reply_text(trozo, parse_mode="Markdown")
        return

    log.info("[%s] → %s: %s",
             chat_id,
             "continuar" if continuar else "NUEVA",
             prompt[:120].replace("\n", " "))

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat_id, ctx, stop))

    async def _progress(text: str):
        try:
            await update.message.reply_text(text)
        except Exception:
            pass

    try:
        rc, out, err = await _run_gemini(chat_id, prompt,
                                            continue_session=continuar,
                                            progress_cb=_progress)
    finally:
        stop.set()
        try:
            await typing_task
        except Exception:
            pass

    if rc != 0:
        detalle = (err or out or "(sin detalles)").strip()
        # Traducción a lenguaje humano según el tipo de error
        det_low = detalle.lower()
        if "perdayperprojectpermodel" in det_low or "limit: 0" in det_low:
            msg_user = (
                "⚠️ Hoy ya no me quedan consultas con la cuota gratis de Google. "
                "Vuelve a probar mañana, o pídele a Arkaitz que mire el panel "
                "de Google AI Studio."
            )
        elif "resourceexhausted" in det_low or "429" in detalle[:50]:
            msg_user = (
                "⚠️ Hay mucho tráfico ahora mismo y Google me está limitando. "
                "Dame 1 minuto y vuelve a intentarlo."
            )
        elif "timeout" in det_low or "deadline" in det_low:
            msg_user = (
                "⚠️ He tardado demasiado en pensar la respuesta. "
                "Reformula la pregunta más concreta y reintenta."
            )
        elif "networkerror" in det_low or "connecterror" in det_low:
            msg_user = (
                "⚠️ Se ha caído la conexión a internet del servidor. "
                "Vuelve a intentarlo en 1-2 minutos."
            )
        elif "finish_reason=safety" in det_low or "blocked" in det_low:
            msg_user = (
                "⚠️ Mi cerebro ha bloqueado la respuesta por motivos de "
                "seguridad. Reformula la pregunta de otra forma."
            )
        else:
            msg_user = "⚠️ No me sale ahora. Pídeselo a Arkaitz si urge."
        # IMPORTANTE: texto plano (no Markdown) — el detalle puede tener
        # caracteres especiales (^, paréntesis, _, *) que rompen el parser
        # de Telegram con BadRequest.
        msg_final = msg_user
        if len(detalle) > 30:
            msg_final += f"\n\n(detalle técnico: {detalle[:500]}...)"
        for chunk in _chunks(msg_final):
            try:
                await update.message.reply_text(chunk)  # plain text
            except Exception as _e_send:
                log.warning("No pude enviar msg de error: %s", _e_send)
        _append_log(chat_id, user_name, prompt, msg_final, kind=kind)
        return

    response = (out or "").strip()
    if not response:
        await update.message.reply_text("🤷 No he podido generar respuesta.")
        _append_log(chat_id, user_name, prompt, "(sin respuesta)", kind=kind)
        return

    for chunk in _chunks(response):
        await update.message.reply_text(chunk, disable_web_page_preview=True)
    _append_log(chat_id, user_name, prompt, response, kind=kind)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        user = update.effective_user.username if update.effective_user else "?"
        log.warning("Acceso denegado chat_id=%s (@%s)", chat_id, user)
        await update.message.reply_text(
            f"🚫 Acceso denegado.\n"
            f"Tu chat_id ({chat_id}) no está autorizado.\n"
            f"Pídele acceso a Arkaitz."
        )
        return

    prompt = (update.message.text or "").strip()
    if not prompt:
        return
    await _process_prompt(prompt, update, ctx)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Transcribe audio/voz con Whisper y lo procesa como si fuera texto."""
    if not _authorized(update):
        await update.message.reply_text("🚫 Acceso denegado.")
        return

    if not _WHISPER_OK:
        await update.message.reply_text(
            "🎤 Audio no soportado en esta instalación.\n"
            "Faltaría instalar `faster-whisper`. Escríbemelo en texto por ahora."
        )
        return

    voice = update.message.voice or update.message.audio or update.message.video_note
    if voice is None:
        return

    chat_id = update.effective_chat.id
    # Mientras transcribe, mostrar "grabando audio" emoji
    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)

    tmp = tempfile.NamedTemporaryFile(prefix="tg_voice_", suffix=".ogg", delete=False)
    tmp.close()
    audio_path = tmp.name

    try:
        tg_file = await voice.get_file()
        await tg_file.download_to_drive(audio_path)
        log.info("[%s] 🎤 audio %.1fs → transcribiendo", chat_id,
                 getattr(voice, "duration", 0) or 0)
        text = await _transcribir(audio_path)
    except Exception as e:
        log.exception("Error transcribiendo: %s", e)
        await update.message.reply_text(
            f"⚠️ No he podido transcribir el audio: {type(e).__name__}"
        )
        return
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass

    if not text:
        await update.message.reply_text(
            "🤷 No he entendido el audio. ¿Puedes repetirlo más claro o escribirlo?"
        )
        return

    # Confirmar al usuario qué he entendido (por si hay error de transcripción)
    await update.message.reply_text(f"🎤 Entendido: «{text}»")

    await _process_prompt(text, update, ctx, kind="voz")


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.exception("Error: %s", ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(
                update.effective_chat.id,
                f"⚠️ Error interno: {type(ctx.error).__name__}",
            )
        except Exception:
            pass


# ─── Menú de comandos visibles en Telegram (al escribir "/") ─────────────────
BOT_COMMANDS_DATOS = [
    BotCommand("start",       "Bienvenida y comandos disponibles"),
    BotCommand("yo",          "Ver tu chat_id (por si necesitas darlo a Arkaitz)"),
    BotCommand("nuevo",       "Empezar conversación nueva (olvida el contexto)"),
    BotCommand("oliver_sync", "Disparar sync incremental con Oliver Sports"),
]


async def _post_init(app: "Application") -> None:
    try:
        await app.bot.set_my_commands(BOT_COMMANDS_DATOS)
        log.info("Menú de comandos registrado (%d entradas).", len(BOT_COMMANDS_DATOS))
    except Exception as e:
        log.warning("No pude registrar el menú de comandos: %s", e)


def main():
    app = (Application.builder()
              .token(TOKEN)
              .post_init(_post_init)
              .build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("yo", cmd_yo))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("oliver_sync", cmd_oliver_sync))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, on_voice))
    app.add_error_handler(on_error)
    log.info("Bot de DATOS arrancado (voz: %s). Ctrl+C para parar.",
             "ON" if _WHISPER_OK else "OFF")

    # ── Validación al arrancar: notificar a Arkaitz (ALLOWED_CHAT_IDS[0]) ──
    # Solo si hay un fallo, evitamos spam si todo está bien.
    try:
        sys.path.insert(0, str(PROJECT_DIR / "src"))
        from health_check import (  # type: ignore
            run_health_check_quick, format_resultados, all_ok,
        )
        _hc = run_health_check_quick()
        if not all_ok(_hc):
            # Mandar solo cuando algo falla. El bot dev manda siempre, este no.
            _hc_txt = format_resultados(_hc)
            _msg = f"⚠️ *Bot DATOS arrancado con avisos*\n```\n{_hc_txt}\n```"
            # Coger el primer chat autorizado
            _chats = [c.strip() for c in ALLOWED_CHAT_IDS_ST.split(",") if c.strip()]
            if _chats and TOKEN:
                import urllib.parse as _u
                import urllib.request as _r
                for _c in _chats[:1]:  # solo el primero
                    _data = _u.urlencode({
                        "chat_id": _c, "text": _msg,
                        "parse_mode": "Markdown",
                        "disable_notification": "true",
                    }).encode()
                    _req = _r.Request(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        data=_data, method="POST",
                    )
                    try:
                        _r.urlopen(_req, timeout=20).read()
                    except Exception:
                        pass
    except Exception as _e:
        log.warning("health check al arrancar falló: %s", _e)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
