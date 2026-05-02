# 📋 Estado del proyecto Arkaitz 25/26 — `2026-04-30`

Documento maestro. **Léelo al empezar cualquier sesión nueva con Claude.**
Resume todo lo que está construido, cómo funciona, qué hay pendiente y
qué decisiones hemos tomado. Si discrepa con `CLAUDE.md`, gana este.

---

## 🔔 RECORDATORIOS PROGRAMADOS

> Si hoy **lunes 4 de mayo 2026 o posterior** y el usuario aún no ha
> mencionado los temas de abajo, recordárselos en cuanto arranquemos.
> Apuntados el 30/04 y 02/05/2026 a petición suya.
>
> **1. Oliver auto-refresh token** — script Playwright + LaunchAgent
> macOS para que al encender el Mac cada mañana se renueve el token
> sin intervención manual. Estimación: 3-4h.
>
> **2. Planillas de Lesiones + Tratamientos para fisios** — DESPUÉS de
> Oliver. Objetivo: que los fisios metan datos directamente (sin pasar
> por Arkaitz como intermediario). Considerar:
> - Pestaña dentro del dashboard con permisos de fisio (form de
>   creación/edición de lesiones y tratamientos), o
> - Form separado (Google Forms, similar al sistema PRE/POST que ya
>   existe), o
> - Bot de Telegram dedicado a fisios.
> - Importante: cuando un usuario que NO sea fisio/médico/admin acceda
>   a la info de lesiones, los nombres deben aparecer **anonimizados
>   por dorsal** ("el 8" en vez de "RAYA"). Esto está apuntado en la
>   sección "🔐 ROLES Y PERMISOS — pendiente para más adelante" de
>   este mismo documento.

---

## 🔐 ROLES Y PERMISOS — pendiente para más adelante

Hoy 1/5/2026 hemos activado **una contraseña única** (st.secrets
`APP_PASSWORD`) para que el cuerpo técnico vea el dashboard. Cuando
quiera diferenciar accesos, montar **opción A: múltiples contraseñas
con roles**:

- **Admin (solo Arkaitz)**: lo único que puede hacer es **editar
  partidos** (todos los botones "💾 Guardar partido / cambios" del
  módulo Estadísticas). El resto de usuarios deben verlos en modo
  lectura — botón oculto o deshabilitado. Razón: Arkaitz quiere
  evitar que toquen donde no deben.
- **Cuerpo técnico**: ve todo en lectura, no edita partidos.
- **Fisios / médicos**: pestaña 🏥 Lesiones con datos
  **anonimizados por dorsal**. En vez de "RAYA se ha lesionado",
  debe mostrar "El 8 se ha lesionado". Razón: protección de datos
  de salud — los nombres no pueden aparecer asociados a lesiones
  para terceros distintos del cuerpo médico-fisio.
- **Jugadores (futuro)**: cada uno solo se ve a sí mismo
  (filtro auto-aplicado por su contraseña/rol).

Implementación cuando toque (estimación: 2-3h):
1. En `st.secrets` definir `APP_USERS = {"clave1": "admin", ...}`.
2. En el gate, asignar `st.session_state["rol"]` según la clave.
3. Pestaña Editar partido: `if rol != "admin": ocultar botón guardar`.
4. Pestaña Lesiones: `if rol in ("fisio","medico","admin"): mostrar
   nombres; else: mostrar dorsal en su lugar`. Hay que cambiar
   las queries de `_VISTA_LESIONES` o filtrar a posteriori — añadir
   columna `dorsal` si no la tiene.

---

## 🏗 Arquitectura general

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Google Sheets (BBDD central)                    │
│  ┌────────────────────────┐   ┌──────────────────────────────────┐ │
│  │ Hojas crudas (input)   │   │ Hojas vista calculadas (output)  │ │
│  │  • SESIONES            │   │  • _VISTA_CARGA, _VISTA_SEMANAL  │ │
│  │  • BORG, PESO, WELLNESS│ → │  • _VISTA_PESO, _VISTA_WELLNESS  │ │
│  │  • LESIONES, FISIO     │   │  • _VISTA_SEMAFORO, _VISTA_RECUENTO│ │
│  │  • _FORM_PRE/POST      │   │  • _VISTA_OLIVER, _VISTA_EJERCICIOS│ │
│  │  • OLIVER, _OLIVER_DEEP│   │                                  │ │
│  │  • _EJERCICIOS         │   │                                  │ │
│  └────────────────────────┘   └──────────────────────────────────┘ │
└──────────────┬──────────────────────────────┬────────────────────────┘
               │                              │
               ▼                              ▼
    ┌──────────────────────┐      ┌─────────────────────────┐
    │  src/calcular_vistas │      │  dashboard/app.py       │
    │  (pipeline)          │      │  Streamlit Cloud        │
    │  Lee crudas →        │      │  Lee vistas →           │
    │  calcula métricas →  │      │  renderiza 8 pestañas   │
    │  escribe vistas      │      │                         │
    └──────────────────────┘      └─────────────────────────┘
               ▲                              ▲
               │                              │
    ┌──────────┴──────────────────────────────┴────────────┐
    │      Bots Telegram (proxy a Claude Code)             │
    │  • @InterFS_bot (dev, solo Arkaitz)                  │
    │  • @InterFS_datos_bot (cuerpo técnico, lectura)      │
    └──────────────────────────────────────────────────────┘
               ▲
               │
    ┌──────────┴──────────┐
    │  Oliver Sports API   │
    │  (sensores GPS)      │
    └──────────────────────┘
```

---

## 📋 Componentes construidos (todo funcionando)

### 1. Pipeline de métricas (`src/calcular_vistas.py`)

Lee SESIONES + BORG + PESO + WELLNESS y calcula:
- **sRPE** = BORG × MINUTOS.
- **ACWR** EWMA: λ_aguda=0.1316 (~7 días), λ_crónica=0.0339 (~28 días).
  - <0.8 azul (infra-carga) · 0.8–1.3 verde · 1.3–1.5 amarillo · >1.5 rojo.
- **Monotonía** = media diaria / desviación diaria. >2 = riesgo.
- **Fatiga** = carga_semanal × monotonía.
- **Wellness**: suma 1-5 de SUEÑO + FATIGA + MOLESTIAS + ÁNIMO. 4-20.
  Rojo ≤10, naranja ≤13, verde >13.
- **Peso PRE semáforo**: media últimas 3 sesiones vs media 2 últimos meses.
  Rojo <-3kg, naranja <-1.5kg, verde ≥-1.5kg.
  Filtro fisiológico 40-200kg.
- **Vista Oliver cruzada**: ratio_borg_oliver, eficiencia_sprint,
  asimetria_acc, densidad_metabolica, pct_hsr, acwr_mecanico.

Ejecutar: `/usr/bin/python3 src/calcular_vistas.py` (NUNCA con anaconda,
sino con el python del sistema que tiene gspread global).

### 2. Dashboard Streamlit (`dashboard/app.py`)

Repo: `arkaitzsisniega/arkaitz-2526` branch `main`. Autodeploy a
Streamlit Cloud al hacer `git push`.

8 pestañas:
- 🚦 **Semáforo** · 📊 **Carga** · ⚖️ **Peso** · 💤 **Wellness**
- 🏥 **Lesiones** · 📋 **Recuento** · 🏃 **Oliver** · 🎯 **Ejercicios**

Auth Google Sheets vía service account (st.secrets en cloud,
google_credentials.json en local).

### 3. Forms para jugadores

2 Forms creados por Arkaitz desde su cuenta de Google. IDs y entry.XXX
mapeados en `src/forms_config.json`.

- **PRE** ("Inter — Antes del entreno"): peso_pre + wellness (4 items 1-5).
  Wellness OPCIONAL para 2ª sesión del día.
- **POST** ("Inter — POST entreno"): peso_post + Borg (1-10).
- Validación: peso 50-120kg respuesta corta. Borg desplegable 1-10.
  Estados S/A/L/N/D/NC los mete Arkaitz a mano (no en el Form).
- Respuestas → hojas `_FORM_PRE` y `_FORM_POST`.
- 18 jugadores en el desplegable (la lista la mantiene Arkaitz al día).

### 4. Oliver Sports

Endpoint base: `https://api-prod.tryoliver.com/v1/`.
Auth: Bearer JWT + headers `x-user-id`, `x-version`, `x-from: portal`,
y los del propio JWT (`User-Agent`, `Accept-Language`, `Accept-Encoding`).

**Endpoints utilizados**:
- `GET /v1/sessions/?team_id=1728` — lista sesiones (paginada 250/pág).
- `GET /v1/sessions/{id}/average?raw_data=1` — métricas agregadas.
- `GET /v1/players/?team_id=1728&include=user` — jugadores + nombres.
- `GET /v1/player-sessions/{id}?include=player_session_info:attr:timeline`
  — **timeline minuto a minuto** (clave para ejercicios).
- `POST /v1/auth/token` con `{refresh_token}` — refresh.

**Tokens**:
- Token de acceso: 2 horas.
- Refresh token: 14 días, **rotativo** (cada uso devuelve uno nuevo PERO
  el original sigue válido hasta su exp).
- ⚠️ Hacer login desde el navegador INVALIDA todos los tokens previos
  (campo `force-logout-N` del JWT).

**Scripts**:
- `src/oliver_sync.py` — incremental, escribe hoja OLIVER (15 cols MVP).
- `src/oliver_sync.py --deep` — 68 métricas a `_OLIVER_DEEP` (quincenal).
- `src/oliver_ejercicios.py` — lee `_EJERCICIOS`, baja timelines de los
  jugadores de cada sesión, agrega métricas en cada rango de minutos,
  escribe `_VISTA_EJERCICIOS` (37 columnas).
- `src/parse_ejercicios_voz.py` — recibe transcripción de audio por
  stdin, llama a Claude Code con `--output-format json --json-schema`
  para estructurar los ejercicios, escribe `_EJERCICIOS` y lanza
  `oliver_ejercicios.py`.

### 5. Bots Telegram

#### `@InterFS_bot` — DEV (solo Arkaitz, chat_id=6357476517)
Carpeta: `telegram_bot/`. Permisos full (`--dangerously-skip-permissions`).

Comandos:
- `/start`, `/id`, `/nuevo`
- `/oliver_sync` · `/oliver_deep` · `/oliver_token` (regenerar token)
- `/enlaces` (genéricos para WhatsApp del equipo)
- `/enlaces_hoy` (pares pre-rellenados por jugador)
- `/consolidar` (Forms → BORG/PESO/WELLNESS + recalcula vistas auto)
- `/ejercicios_sync` (procesa hoja _EJERCICIOS)
- `/ejercicios_voz` (modo: el siguiente audio se estructura como
  ejercicios y se vuelca al Sheet automáticamente)

JobQueue:
- Cada 24h: chequea si han pasado >14 días desde último `/oliver_deep`
  y avisa.
- Cada 24h: lee `.recordatorios.json` y envía los que han llegado a su
  fecha (mecanismo genérico).

#### `@InterFS_datos_bot` — CUERPO TÉCNICO (multi-usuario)
Carpeta: `telegram_bot_datos/`. Permisos restringidos.

Lista de chat_ids autorizados en `.env` (separados por coma). Sesiones
aisladas por chat_id en `sesiones/<chat_id>/`. System prompt enforces
"solo consultas de datos, nunca tocar código".

Comandos: `/start`, `/yo`, `/nuevo`, `/oliver_sync`.

#### Características compartidas
- Memoria conversacional (`claude -c`).
- Soporte de voz (Whisper local, modelo "base", español).
- Logs espejados a `telegram_logs/YYYY-MM-DD.md` (gitignored).
- Arranque conjunto: `~/Desktop/Arkaitz/arrancar_bots.sh`.

---

## 🗓 Rutina diaria (Arkaitz)

### Antes del entreno
1. Sheet → **SESIONES** → añadir fila (FECHA, SEMANA, TURNO, TIPO_SESION,
   MINUTOS, COMPETICION).
2. Bot → `/enlaces`. Pegar el PRE y el POST al WhatsApp del equipo.

### Tras el entreno
1. Bot → `/ejercicios_voz`.
2. Mandar audio describiendo los ejercicios (qué, cuánto, en qué orden).
   - Si el GPS se encendió tarde (movilidad sin sensor), mencionarlo.
3. Esperar el resumen del bot.

### Al final del día (o mañana siguiente)
1. Bot → `/consolidar` (integra Forms a hojas + recalcula vistas).
2. Bot → `/oliver_sync` (datos sensores + recalcula).
3. Abrir Streamlit Cloud y revisar.

### Mantenimiento
- Cada 14 días: `/oliver_deep` (te avisa el bot).
- Si bot dice "Token Oliver caducado" → Safari → consola → snippet →
  `/oliver_token` con las 3 líneas. **NO hacer login en Oliver entre
  regeneraciones**: invalida tokens previos.

---

## 🧠 Decisiones tomadas

- **Match fuzzy nombres Oliver↔Sheet**: si una palabra del nombre Oliver
  ("Sergio Barona") coincide con un JUGADOR del Sheet ("BARONA"),
  se normaliza. Caso especial: alias manual `_OLIVER_ALIASES` para
  "DAVID SEGOVIA → SEGO".
- **Carlos/CARLOS**: cuando hay duplicados case-insensitive en BORG,
  preferir versión TODO MAYÚSCULAS.
- **Forms**: enlace único por sesión (no 1 por jugador). Confianza.
- **Doble sesión del día**: wellness solo en la 1ª. En el Form PRE el
  wellness es OPCIONAL.
- **Estados S/A/L/N/D/NC**: los rellena Arkaitz a mano en BORG (selección,
  lesionados, etc.). NO se piden en el Form.
- **Filtro fisiológico peso**: 40-200kg. Valores fuera → NaN.
- **Semáforo peso**: media últimas 3 sesiones vs media 2 últimos meses.
- **Tokens Oliver**: refresh dura 14 días, se renueva solo. NO abrir
  Oliver en navegador entre tanto.

---

## 🔜 Hilos abiertos (orden sugerido)

### Próxima sesión — pendientes inmediatos
1. ⚠️ **J25.INDUSTRIAS no se está extrayendo**: tras el sync sigue sin
   aparecer en EST_PARTIDOS. Investigar por qué (¿hoja vacía? ¿filtro
   descarta? ¿nombre con espacios o tilde?). Listar partidos en
   `Estadisticas2526.xlsx` y comparar con los que llegan al Sheet.
2. ✏️ **Fecha J17.ELPOZO**: Arkaitz la corrigió en Excel; ahora aparece
   2026-10-10 en EST_PARTIDOS. Confirmar con él si esa es la fecha
   correcta tras su edición.
3. 📋 **Planilla web para meter datos del partido**: principal trabajo.
   Pestaña en el dashboard con form para crear/editar partido, con
   marcador final, local/visitante (heurística "Jorge Garbajosa"),
   descripciones de gol, posibles correcciones manuales.
4. 🏥 **Planilla fisios**: form para lesiones + tratamientos. Sólo
   accesible para fisios + Arkaitz (auth aparte del bot).
5. 👀 **Cómo ve la info el cuerpo técnico**: web pública? login? tablet?
   Decisión después de #3 y #4.
6. 🖥️ **Mac viejo como servidor 24/7**: documentar setup launchd para
   que arranque bots + dashboard al encender.

### En curso
- **Bot de gastos personales** ✅ funcionando. Carpeta `gastos_bot/`.
  Sheet propio (independiente del de Inter) con 80 gastos históricos
  importados desde el Numbers (ene-abr 2026). Pendiente: añadir chat_id
  de Lis tras `/id` y monitorizar la categorización en uso real.
- **Estadísticas de partido** 🟡 v0 funcional. `src/estadisticas_partidos.py`
  lee el Excel `Estadisticas2526.xlsx` (en `~/Mi unidad/Deporte/...`),
  extrae rotaciones y eventos de gol de las 38 pestañas-partido
  jugadas, y vuelca a 3 hojas del Sheet maestro: `EST_PARTIDOS`,
  `EST_EVENTOS`, `_VISTA_EST_JUGADOR`. Pestaña 🏆 Estadísticas en
  el dashboard (Streamlit Cloud). **Pendientes** (ver
  `docs/estadisticas_partidos.md`):
  - Goles_en_contra atribuidos al cuarteto en pista.
  - Marcador final del partido (no se extrae aún).
  - Asistencias: confirmar que solo se cuentan las nuestras.
  - Fecha del partido: comprobar columna exacta.
  - **Picado cómodo** y **app tablet en directo** aún pendientes.

### Próximos
1. **Documento de fisios** — formulario/Sheet sencillo donde los
   fisios apunten lo que hacen con cada jugador. **Crítico**: el menor
   tiempo posible de cumplimentación. Hay que diseñarlo pensando en
   ergonomía, no en exhaustividad.
2. **Mejorar pestaña Lesiones** — pospuesto. Candidato: gráfico días
   baja por zona, tiempos medios de retorno, lesiones activas con
   countdown.
3. **Plantilla 26/27** (recordatorio programado para 15/06/2026):
   Arkaitz pasará lista oficial de porteros + jugadores primer equipo
   + filial que sube. Actualizar `_OLIVER_ALIASES` y archivar datos
   históricos de jugadores que se vayan.

### Ideas archivadas (por si surgen)
- Cron/launchd para arranque automático del bot al encender el Mac.
- Migrar bots a un servidor 24/7 (cuando el uso lo justifique).

---

## 📁 Archivos importantes

```
Arkaitz/
├── CLAUDE.md                       # Notas para Claude (lectura auto)
├── docs/
│   ├── estado_proyecto.md          # ESTE archivo
│   └── oliver_investigacion.md     # API Oliver completa
├── src/
│   ├── calcular_vistas.py          # Pipeline principal
│   ├── oliver_sync.py              # Sync sensores Oliver
│   ├── oliver_ejercicios.py        # Procesa _EJERCICIOS
│   ├── parse_ejercicios_voz.py     # Audio → Claude → JSON → Sheet
│   ├── forms_utils.py              # Lectura Forms + consolidación
│   ├── forms_config.json           # IDs y entry.XXX de los 2 Forms
│   ├── consolidar_forms.py         # Form → BORG/PESO/WELLNESS
│   ├── enlaces_hoy.py              # Pares pre-rellenados por jugador
│   ├── enlaces_genericos.py        # 2 enlaces para WhatsApp
│   └── inspeccionar.py             # Helper de debug
├── dashboard/
│   └── app.py                      # Streamlit, 8 pestañas
├── telegram_bot/                   # Bot dev
│   └── bot.py
├── telegram_bot_datos/             # Bot consultas
│   └── bot_datos.py
├── arrancar_bots.sh                # Lanza ambos bots
├── .env                            # OLIVER_TOKEN, OLIVER_REFRESH_TOKEN…
├── .recordatorios.json             # Recordatorios fechados (bot)
└── google_credentials.json         # Service account (gitignored)
```

---

## 🔐 Credenciales y secretos

Todos en archivos `.env` (gitignored):
- **Raíz `.env`**: OLIVER_TOKEN, OLIVER_REFRESH_TOKEN, OLIVER_USER_ID, OLIVER_TEAM_ID.
- **`telegram_bot/.env`**: TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_ID.
- **`telegram_bot_datos/.env`**: TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS (lista).

Cuenta servicio Google: `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com`.

**Pendiente cambiar**: contraseña Oliver `@Inter1977` (pegada en chat
hace tiempo). Recordar al usuario cuando termine la temporada.

---

## 📬 Cómo continuar este proyecto en una nueva sesión

1. Abrir Claude Desktop / Code en `/Users/mac/Desktop/Arkaitz/`.
2. Claude leerá automáticamente `CLAUDE.md` (que apunta aquí).
3. Si el usuario menciona algo de "Telegram hoy", leer
   `telegram_logs/YYYY-MM-DD.md` para retomar el hilo del bot.
4. Si discrepa con `CLAUDE.md`, gana este `estado_proyecto.md`.
