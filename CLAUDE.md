# Proyecto Arkaitz 25/26 — Notas para Claude

> **📖 LEER PRIMERO**: `docs/estado_proyecto.md`. Es el documento maestro
> con todo lo construido, decisiones tomadas, hilos abiertos y la rutina
> diaria de Arkaitz. Si algo aquí discrepa, **gana ese archivo**.

## Sobre el usuario

- **Arkaitz** (`@arkaitzsisniega`) — director técnico / preparador físico de Movistar Inter FS.
- **No es técnico**. Sabe lo que necesita funcionalmente pero no programa. Explícale lo justo, con pasos copiables y claros. Evita jerga salvo que sea imprescindible y, si la usas, defínela.
- Trabaja sobre todo desde Mac en la oficina y desde móvil (Telegram, vía `telegram_bot/`).
- Idioma: **siempre en español**.

## Cómo le gusta que trabaje

- **Proactividad**: guíale los siguientes pasos. Tiende a irse a otra cosa y perder el hilo de temas abiertos. Si una tarea deja un hilo suelto (verificar algo, revisar datos, probar un cambio desplegado), recuérdaselo al cerrar.
- **Mantén un hilo de pendientes** en la cabeza entre mensajes. Cuando termines una tanda de cambios, termina siempre con un "próximos pasos" o "cosas por revisar".
- **No te lances a hacer cambios grandes sin confirmar el plan primero** cuando sean cambios estructurales. Para fixes pequeños, adelante.
- **Muéstrame lo que cambias** y por qué, no solo el resultado.

## Stack y arquitectura

- **Datos**: Google Sheets (`Arkaitz - Datos Temporada 2526`) como base de datos central.
  - Hojas crudas: `SESIONES`, `BORG`, `PESO`, `WELLNESS`, `LESIONES`, `FISIO`.
  - Hojas vista pre-calculadas: `_VISTA_CARGA`, `_VISTA_SEMANAL`, `_VISTA_PESO`, `_VISTA_WELLNESS`, `_VISTA_SEMAFORO`, `_VISTA_RECUENTO`.
- **Pipeline**: `src/calcular_vistas.py` lee hojas crudas → calcula métricas (ACWR EWMA, monotonía, fatiga, baselines, semáforos) → escribe hojas `_VISTA_*`.
- **Dashboard**: `dashboard/app.py` (Streamlit). Lee solo las `_VISTA_*` y renderiza 6 pestañas (Semáforo, Carga, Peso, Wellness, Lesiones, Recuento).
- **Deploy**: Streamlit Cloud, autodeploy desde GitHub `arkaitzsisniega/arkaitz-2526` branch `main`. Credenciales en `st.secrets`.
- **Auth Google Sheets**: service account `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com`. Credenciales locales en `google_credentials.json` (gitignored).
- **Bot Telegram**: `telegram_bot/` — proxy a Claude Code CLI. Solo responde a `ALLOWED_CHAT_ID`.

## Python

- El Python del sistema (`/usr/bin/python3`, v3.9) es el que tiene gspread y pandas instalados globalmente.
- El `python3` del PATH apunta a Anaconda y **no** tiene gspread — no usarlo para `calcular_vistas.py`.
- Para ejecutar el pipeline: `/usr/bin/python3 src/calcular_vistas.py`.

## Métricas de dominio (futsal / sports science)

- **sRPE** = BORG × MINUTOS (carga de sesión).
- **ACWR** (Acute:Chronic Workload Ratio) con EWMA: λ_aguda=0.1316 (~7 días), λ_crónica=0.0339 (~28 días).
  - <0.8 = azul (infra-carga) · 0.8–1.3 = verde · 1.3–1.5 = amarillo · >1.5 = rojo.
- **Monotonía** = media diaria / desviación diaria (>2 = riesgo).
- **Fatiga** = carga_semanal × monotonía.
- **Wellness**: suma de SUEÑO + FATIGA + MOLESTIAS + ÁNIMO (cada una 1-5). Total 4-20. Rojo ≤10, naranja ≤13, verde >13.
- **Peso PRE semáforo**: última sesión vs media últimos 2 meses. Rojo <-3kg, naranja <-1.5kg, verde >=-1.5kg. Filtro fisiológico 40-200kg para excluir entradas erróneas tipo `71,5→715`.

## Hilos abiertos / cosas a recordar

### ✅ Cerrados (abril 2026)
- Dashboard completo funcionando en Streamlit Cloud.
- Fix de coma decimal española (lectura con UNFORMATTED_VALUE).
- Fix de fechas ISO mal parseadas (dayfirst=True corrompía YYYY-MM-DD).
- Filtro fisiológico 40-200 kg en `vista_peso`.
- Semanas fantasma eliminadas en `vista_semanal` (skip carga=0).
- Recuento con estados S/A/L/N reales y PCT_PARTICIPACION capado.
- Bot Telegram @InterFS_bot (dev, uso personal) + bot @InterFS_datos_bot
  (consultas de datos, multi-usuario con lista chat_id en .env).
- Ambos bots con memoria conversacional (`claude -c`) y soporte de voz
  (Whisper local, modelo "base", español).
- Script `arrancar_bots.sh` en la raíz para lanzar ambos con un comando.

### 🕐 Pospuesto (por decisión del usuario)
- Mejorar pestaña Lesiones (el usuario dijo "es mejorable, pero más adelante").
  Temas candidatos: gráfico de días baja por zona, tiempos medios de retorno,
  lesiones activas con countdown, etc.

### 🔜 Pendientes (próximos, por orden sugerido)
- [x] **Integración Oliver Sports**: API + script + pestaña + recordatorio quincenal
      (abril 2026). Ver `docs/oliver_investigacion.md` y `src/oliver_sync.py`.
      Token JWT caduca cada ~24h; el usuario regenera con snippet en consola.
- [x] **Planilla de partidos en Streamlit** (iters 1-8, abril 2026). Form
      completo en pestaña ✏️ Editar partido: cabecera, plantilla, eventos
      mm:ss, métricas, rotaciones variables, totales 1T/2T, faltas con
      alerta 6ª=10m, penaltis/10m, zonas (campo+portería). Plan completo
      en `docs/plan_planilla.md`.
- [ ] **Iter 9 — Dashboard faltas/penaltis** (visualización de las hojas
      `EST_FALTAS` y `EST_PENALTIS_10M`).
- [ ] **Iter 10 — Scouting de equipos rivales** (orden cambiado el
      29/04/2026: VA ANTES que PWA). Hojas `EST_SCOUTING_GOLES` y
      `EST_SCOUTING_PEN_10M`. Incluye histórico de penaltis y 10m
      (nuestros y rivales).
- [ ] **Iter 11 — Mejoras del form** (acumuladas):
      - Colores en rotaciones del form (hoy solo en PDF).
      - Tabla zonas duplicada por parte (1T/2T).
      - Campo `marcador` autorrellenado en penaltis/10m.
- [ ] **Iter 12 — PWA offline** (mini-app para meter datos sin conexión).
- [ ] **Google Forms para jugadores** (envío auto de Borg + peso PRE/POST +
      wellness tras cada entrenamiento, enlace vía WhatsApp). Ahorra mucho
      tiempo diario a Arkaitz.
- [ ] **Bot apunta sesión por voz** (pedido 29/04/2026):
      Antes de mandar `/enlaces_hoy`, Arkaitz quiere poder dictarle al bot
      la sesión de entrenamiento (descripción tipo "FÍSICO + 2v2 + finalización
      45 min total") y que el bot:
      1. Transcriba con Whisper (ya está integrado en ambos bots).
      2. Añada/actualice una fila en la hoja `SESIONES` (fecha = hoy,
         descripción = lo dictado, tipo si lo detecta, etc.).
      3. Confirme con un mensaje del estilo "✅ Sesión apuntada para hoy
         (DD/MM): «descripción»".
      4. Opcional: ofrecer botón inline para mandar `/enlaces_hoy` justo
         después.
      Implementación: comando nuevo `/sesion` (o `/apunta`) en
      `telegram_bot/bot.py` que reciba audio o texto y use gspread para
      escribir en `SESIONES`. Añadir helper `apuntar_sesion(texto, fecha)`
      en `src/sesiones_utils.py`. Schema de SESIONES está en
      `src/setup_gsheets.py`.

      **AMPLIACIÓN (29/04/2026, antes de irse):**
      - Añadir nuevo tipo de sesión: **MATINAL** — sesión corta que se
        hace los días de partido por la mañana.
      - Permitir **tipos combinados** en una misma sesión (ej. "GYM +
        tec-tac"). Hoy `tipo` parece ser un solo valor; pasar a
        multi-select o string libre con separador (p.ej. "GYM+TEC_TAC").
        Revisar también el extractor / dashboard para que muestren los
        tipos combinados sin romper agregaciones.
      - Revisar `src/setup_gsheets.py` (donde se definen los tipos
        canónicos) y `dashboard/app.py` (donde se filtran por tipo).

### 🔴 Reglas de dominio importantes (no olvidar)

**Geometría de penaltis y 10m** (acordada 29/04/2026):
- **Penalti** (6m) se tira en convergencia de `A1`, `A2`, `A4`, `A5`.
- **10 metros** se tira en convergencia de `A4`, `A5`, `A8`, `A9`.
- Por tanto NO se suman a ninguna zona del campo Z1-Z11. Van a su
  propia hoja `EST_PENALTIS_10M` con `cuadrante` (P1-P9 portería).
- Al pintar el SVG del campo serán dos marcadores discretos en los
  puntos de convergencia, con su contador.

## Google Forms (PRE/POST por entreno)
- 2 Forms creados por Arkaitz en su Google (IDs en `src/forms_config.json`).
  - Form PRE: peso + wellness (4 items 1-5). Wellness OPCIONAL (para 2ª sesión del día).
  - Form POST: peso + Borg (1-10).
- Respuestas caen a `_FORM_PRE` y `_FORM_POST` (automático, vía Forms).
- `src/forms_utils.py`: leer_respuestas_* + consolidar_a_sheet + detectar_duplicados.
- `src/consolidar_forms.py` + `/consolidar` del bot: consolida a BORG/PESO/WELLNESS,
  avisa de duplicados y **relanza automáticamente `calcular_vistas`**.
- Enlaces al jugador:
  - `/enlaces` → 2 enlaces genéricos (sin prefill, jugador elige su nombre).
  - `/enlaces_hoy` → pares PRE+POST pre-rellenados por jugador para la sesión del día.

## Ejercicios (timeline Oliver por bloques)
- Hoja `_EJERCICIOS` (editable por el usuario): session_id, fecha, turno,
  nombre_ejercicio, tipo_ejercicio, minuto_inicio, minuto_fin, jugadores, notas.
- Endpoint Oliver:
  `GET /v1/player-sessions/{id}?include=player_session_info:attr:timeline`
  → devuelve arrays de 67 valores (1 por minuto) para cada métrica.
- `src/oliver_ejercicios.py` + comando `/ejercicios_sync` del bot:
  lee `_EJERCICIOS`, descarga timeline de cada jugador, agrega métricas en el
  rango [minuto_inicio, minuto_fin), escribe una fila por jugador×ejercicio
  en `_VISTA_EJERCICIOS` (37 columnas).
- Dashboard pestaña **🎯 Ejercicios**: filtros por ejercicio/tipo, ranking por
  jugador con gradiente de colores, comparativa entre ejercicios.

## Oliver Sports — funcionamiento
- `src/oliver_sync.py` — sync incremental (modo MVP) o `--deep` (68 métricas).
  Lee token de `.env` raíz (OLIVER_TOKEN, OLIVER_USER_ID, OLIVER_TEAM_ID).
- Hojas generadas: `OLIVER` (MVP 15 cols), `_OLIVER_DEEP` (68 métricas),
  `_OLIVER_SESIONES` (índice de ids ya sincronizados).
- `calcular_vistas.py` → crea `_VISTA_OLIVER` cruzando con Borg/CARGA:
  ratio_borg_oliver, eficiencia_sprint, asimetria_acc, densidad_metabolica,
  pct_hsr, acwr_mecanico.
- Dashboard pestaña **🏃 Oliver** lee de `_VISTA_OLIVER`.
- Bots: `/oliver_sync` (ambos) y `/oliver_deep` (solo bot dev).
- Recordatorio quincenal: JobQueue del bot dev chequea cada 24h si pasaron
  >14 días desde el último `/oliver_deep` y te avisa por Telegram.
  Marca de última ejecución: `.oliver_deep_ultimo` (no en git).
- Si el token caduca, el script muestra el snippet exacto que el usuario
  debe pegar en la consola del navegador de Oliver para regenerarlo.

## Convenciones

- Commits en español, forma imperativa corta. Incluir `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.
- Después de modificar `calcular_vistas.py`, re-ejecutarlo para que las `_VISTA_*` del Sheet reflejen los cambios antes de que el dashboard se actualice.
- Después de cambios en `dashboard/app.py`: `git push` → Streamlit Cloud tarda 1-2 min en redeplegar.

## Sincronización móvil ↔ ordenador — **LEER AL ARRANCAR**

El usuario alterna entre hablar con los bots de Telegram (móvil) y con Claude
Desktop/Code (ordenador). Para que no pierda el hilo al saltar de un sitio a otro:

### Regla obligatoria al iniciar cada conversación nueva en Claude Desktop/Code

**ANTES de contestar al primer mensaje del usuario** en una nueva sesión:

1. Mira si existe el archivo `telegram_logs/YYYY-MM-DD.md` del día de hoy
   (usa `Read`). Si no existe o está vacío, sigue normal y no menciones nada.
2. Si existe y tiene contenido:
   - Empieza tu primera respuesta con un bloque corto: **"📱 Hilo de Telegram hoy:"**
     seguido de un resumen en 3-6 bullets de lo que el usuario preguntó al bot
     y lo que el bot respondió (no pegues el log entero, resume).
   - Incluye la hora de los mensajes más recientes.
   - Después de ese resumen, contesta normalmente al mensaje del usuario.
3. Si el usuario escribe algo que claramente continúa un hilo del bot ("sí",
   "sigue con lo de antes", "hazlo", "y Pirata qué tal?"…), asume contexto
   del log.

### Cómo se genera ese log
- Ambos bots (`telegram_bot/bot.py` y `telegram_bot_datos/bot_datos.py`)
  escriben cada intercambio en `telegram_logs/YYYY-MM-DD.md` con timestamp,
  bot que atendió, chat_id y texto (tanto del usuario como de Claude).
- El formato de cada entrada:
  ```
  ### HH:MM:SS · <bot_name> · chat <id> · 💬 o 🎤 (voz)
  **Usuario:** ...
  **Claude:** ...
  ```
- La carpeta `telegram_logs/` está en `.gitignore` (contenido sensible).

### Comandos explícitos del usuario
Si el usuario dice **"ponme al día"**, **"recap"**, **"qué ha pasado por Telegram"**
o similar → abre el log del día y pégalo o resúmelo más a fondo (bajo demanda
puedes ser más detallado que en el preview automático).
