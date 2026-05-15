# 📋 Estado del proyecto Arkaitz 25/26 — `2026-05-15`

Documento maestro. **Léelo al empezar cualquier sesión nueva con Claude.**
Resume todo lo que está construido, cómo funciona, qué hay pendiente y
qué decisiones hemos tomado. Si discrepa con `CLAUDE.md`, gana este.

---

## 💶 PRESUPUESTO APROBADO — 75€/mes desde 1 junio 2026

Movistar Inter FS ha aprobado **75 €/mes** para mejora sustancial de
Streamlit + bots. Arranca **1 de junio**. Hasta entonces, mandato de
Arkaitz: **profundizar al máximo, dejar bots niquelados y web volando.**

Plan operativo en `docs/plan_junio_2026.md`. Incluye también el proyecto
futuro de **bot de scouting de partido** (anotaciones de partido por voz
durante el directo).

---

## 🔔 ESTADO 15/5/2026 (NOCHE) — refinamiento crono + atajo duplicados

Sesión corta sobre la sesión TARDE-NOCHE. Dos cierres quirúrgicos para
dejar el crono y el flujo de Forms más sólidos antes del 1/junio.

### Crono iPad — cronos múltiples + avisos de porteros (commits a2e722f source + f0c87f4 deploy)
- **Cronos independientes por expulsado**. Antes había un único crono
  de inferioridad / superioridad (singular). Ahora `cronosInferioridad`
  y `cronosSuperioridad` son arrays: un crono de 2:00 por cada expulsado
  vivo. Regla FIFA futsal: cada gol del rival cancela el crono de
  inferioridad MÁS ANTIGUO (no todos los activos); idem para superioridad
  con goles nuestros.
- Helper `calcularCronosActivos(rojas, goles, tActual)` centraliza la
  lógica: ordena por tiempo, marca canceladas (1 gol = 1 cancelación
  más antigua), devuelve los vivos con su segRestantes.
- **Aviso 2 porteros en pista** → banner amarillo destacado ("Hay 2
  porteros en pista (…). Revísalo: solo uno puede estar."). Caso que
  nunca debe pasar.
- **Aviso 0 porteros en pista** → línea pequeña gris ("Sin portero en
  pista (portero-jugador)."). Caso habitual al final de partido perdiendo.
- **Cambio portero ↔ jugador** ya estaba soportado: `ModalCambio` y
  `cambiarJugador` del store no filtran por posición.
- Validado contra cita literal del user: "Si hay dos expulsados hay dos
  cronos de dos minutos. Uno por cada expulsado", "un gol cancela el
  crono más antiguo".

### Forms — atajo `/limpiar_duplicados` sin recalcular vistas (commit 0519045)
- Comando nuevo en Alfred: borra duplicados de `_FORM_PRE` / `_FORM_POST`
  conservando la respuesta más reciente por TIMESTAMP. NO toca
  BORG/PESO/WELLNESS ni recalcula vistas. Útil cuando caen duplicados
  tarde y no quieres re-disparar el pipeline completo de ~10 min.
- Script standalone `src/limpiar_duplicados.py`. Reutiliza
  `fu.eliminar_duplicados_form` (ya probada, commit e254857 del
  consolidar auto-limpieza).
- Intents en lenguaje natural matcheados ANTES que `/consolidar` para
  evitar solapamiento: "limpia los duplicados", "borra duplicados",
  "elimina duplicados", "duplicados fuera". 10/10 smoke tests.
- BotCommand en menú `/` para descubrimiento. SYSTEM_PROMPT actualizado
  para que Alfred elija correctamente entre `/consolidar` (consolidación
  + recálculo completo) y `/limpiar_duplicados` (solo housekeeping).
- Al pushear: auto_pull en el servidor reinicia los bots solo (≤5 min).
  Sin acción manual del usuario en la oficina.

### Estado real del Sheet al cerrar la sesión
- 2 duplicados reales pendientes detectados en dry-run: `DANI PRE 13/5 M`
  y `GARCIA POST 14/5 M`. NO se borraron desde aquí — Arkaitz hará el
  primer test en vivo del comando lanzando `/limpiar_duplicados` desde
  Telegram cuando le llegue el aviso de "🔄 Bots actualizados" del
  auto_pull.

---

## 🔔 ESTADO 15/5/2026 (TARDE-NOCHE) — segunda tanda con Arkaitz

Resumen de qué se cerró tras la sesión sola de la mañana. Detalle completo
en `docs/sesion_15-05-2026_tarde_pendiente.md` y `docs/pendiente_manana_16-05-2026.md`.

### Crono iPad — fix definitivo
- Causa raíz del "no me deja clickar": Turbopack del dev server no
  hidrataba en iOS Safari. Confirmado con página de diagnóstico `/test-tap`.
- Solución: build estático (`output: 'export'`) + despliegue en GitHub Pages.
- URL nueva: `https://arkaitzsisniega.github.io/arkaitz-2526/crono/`
- Defensas en profundidad: `hoyISO()` ahora local (no UTC); `useState(fecha)`
  se inicializa vacío y rellena en useEffect.

### Alfred — niquelado funcional
- 3 palancas en `/ejercicios` (parser regex sin LLM cuando el texto
  está estructurado · cache `_OLIVER_SESIONES` antes de paginar API ·
  respuesta async "Recibido, procesando" + worker background).
- Mismo patrón async aplicado a `/consolidar` (4 subprocesos chained
  que ahora corren en background con progress messages 1/4, 2/4…).
- Comando nuevo `/status` — health check en vivo (Sheet, vistas,
  Gemini, Oliver token, faster-whisper, estado_jugador).
- Atajo nuevo SIN LLM: "goles de X jugador" (`src/goles_jugador.py`).
  Diferenciado del ranking general — específico por jugador con
  cronología partido a partido. En ambos bots.

### Gastos bot — features pedidas por Arkaitz
- Tras apuntar cualquier gasto, mensaje automático con: resumen del
  mes (total + por categorías + %) + cronología concepto a concepto.
- Gastos fijos automáticos día 1 a las 09:00 Madrid vía JobQueue.
- Campo opcional `meses: [...]` para gastos no mensuales (alarma
  trimestral, seguros anuales).
- Datos reales de Arkaitz guardados en `gastos_bot/gastos_fijos.json`
  (gitignored): jardinero/Tatiana/Netflix/préstamo placas/Lowi + alarma
  trimestral. 477,90 €/mes + 104,59 € en ene/abr/jul/oct.
- Smoke test independiente `tests/smoke_gastos_bot.py` (10/10).
- `requirements.txt` extendido con `python-telegram-bot[job-queue]`.

### SA read-only del bot_datos
- En Mac casa: SA creada, JSON descargado, Sheet compartido como Lector,
  `.env` local actualizado.
- En servidor (mañana, vía SSH desde LAN del Inter): `scp` del JSON,
  edit `.env`, `pip install` (auto_pull NO instala deps), reinicio del
  bot_datos.

### Infra documentada
- Memoria persistente `feedback_infra_bots.md`: bots en mac viejo de
  oficina 24/7, auto_pull cada 5 min (solo git pull + kickstart, NO
  pip install), SSH solo en LAN del Inter, SÍ hay LaunchAgents
  (`com.arkaitz.bot/.bot_datos/.gastos_bot/.autopull`).
- Arkaitz siempre en casa salvo visitas a oficina. Cualquier acción
  que requiera SSH se acumula para la próxima visita.

### Pendiente para mañana 16/5 (oficina, vía SSH/LAN)
1. Probar crono en iPad real.
2. `pip install -r requirements.txt` en gastos_bot del servidor.
3. `scp gastos_fijos.json` al servidor.
4. Cerrar SA read-only en el servidor.
5. Confirmar Alfred `/ejercicios` + `/status` + nuevo atajo "goles de X"
   en producción.

---

## 🔔 ESTADO 15/5/2026 (MAÑANA) — sesión profundización (3h trabajando solo)

Antes de presentar presupuesto al club Arkaitz pidió endurecer TODO.
Sesión sola con auditoría exhaustiva. Detalle completo en
`docs/sesion_15-05-2026_profundizacion.md`. Resumen:

### Bots (críticos cerrados)
- **bot_datos: cinturón blindado** — 30+ patrones nuevos. Bloquea
  `worksheet.update()`, `clear()`, `format()`, `share()`,
  `to_csv/excel/pickle/parquet/etc`, `requests.post/put/delete`,
  `socket`, `os.popen/exec`, `compile`. Verificado 15/15 bloqueado +
  11/11 legítimos no bloqueados.
- **Pendiente tuyo**: activar SA read-only (`READONLY_CREDS_FILE`).
- **4 atajos SIN LLM** en AMBOS bots (Alfred + datos):
  - `lesiones_activas` → "quién está lesionado" (con dorsales en datos)
  - `ranking_temporada` → "ranking goleadores", "asistencias en liga"
  - `carga_ultima_sesion` → "carga de ayer", "borg del 13 de mayo"
    (entiende ayer/hoy/anteayer/"13 de mayo"/2026-05-13/13/05/...)
  - `estado_jugador` → "cómo está Pirata" (ya existía)
- **estado_jugador.py**: ya no crashea con N_SESIONES inválido.
- **ranking_temporada.py**: avisa de competición no reconocida.
- **carga_ultima_sesion.py**: fallback automático a `_FORM_POST` si
  BORG no tiene datos (cuando jugadores rellenaron Form pero no se
  ha hecho `/consolidar` aún).

### Crono iPad
- **iniciarPartido refactorizado**: persistencia Dexie síncrona ANTES
  de setPartido. Resuelve race condition con /partido.
- **Bug stale state pista_inicial**: useEffect sincroniza selects con
  convocados. Validación en "Empezar" si jugador en pista no convocado.
- **PWA básica**: manifest.json + apple-touch-icon + iconos
  120/152/167/180/192/512 + maskable. Instalable en iPad como app
  con escudo Inter (standalone mode).

### Streamlit
- **FACTOR_GYM configurable** vía env var. Default 1.25, sube a 1.5
  con `FACTOR_GYM=1.5 python3 src/calcular_vistas.py`.
- ACWR en semáforo: verificado, ya funciona.

### Infra de pruebas
- **`tests/smoke_bots.py`**: 10 tests automáticos (sintaxis, cinturón
  bloquea/permite, scripts curados, intents, system prompts).
  Salida actual: 10/10 OK.
- **`verificar_todo.sh`**: pre-flight check antes de presentar al
  club. Verifica 12 puntos (URLs públicas + dev server + git + smoke
  tests + scripts). Salida actual: 12/12 OK.

---

## 🔔 ESTADO 13/5/2026 — landing pública, icono Inter, /enlaces_wa

### Cuerpo técnico puede entrar al dashboard como "app"
- URL oficial nueva para repartir: `https://arkaitzsisniega.github.io/arkaitz-2526/`
  (GitHub Pages, rama `gh-pages`). Es una landing con el escudo verde del
  Inter + botón "Abrir panel" que lleva a `https://interfs-datos.streamlit.app/`
  (URL custom de Streamlit, esa SÍ permite acceso público sin login GitHub;
  la URL autogenerada larga sigue exigiendo login).
- Iconos cuadrados (180/192/512) con fondo blanco para iOS/Android
  (`apple-touch-icon-180.png`, `icon-192.png`, `icon-512.png`,
  `icon-512-maskable.png`). Al "Añadir a pantalla de inicio" sale el
  escudo del Inter.
- La landing detecta `navigator.standalone` (iOS) /
  `display-mode: standalone` (Android): si se abre desde el icono del
  escritorio, redirige automáticamente al panel; si se abre desde el
  navegador normal, espera a que pulses "Abrir panel" (así Safari no
  redirige antes de capturar el icono).

### Streamlit keepalive
- Alfred hace ping cada 12h a la URL del dashboard (job en JobQueue).
  Caveat: a veces Streamlit endurece el sleep y exige clic humano para
  despertar; si pasa, volver a "plan A" (avisar al cuerpo técnico).

### /enlaces_wa — envío de enlaces de Forms por WhatsApp
- Comando nuevo en Alfred. Lee hoja `TELEFONOS_JUGADORES` (creada hoy con
  los 22 jugadores activos del roster, columnas
  `dorsal/jugador/telefono/usar_whatsapp/notas`).
- Genera UN enlace `https://wa.me/<tel>?text=<mensaje>` por jugador con
  los enlaces PRE+POST prefilled. Arkaitz pulsa cada uno → WhatsApp abre
  el chat con el mensaje listo → solo pulsar Enviar.
- Pendiente del usuario: rellenar la columna `telefono` de la hoja.
- Detalles y opciones futuras (Business API, whatsapp-web.js):
  `docs/whatsapp_enlaces.md`.

### Otros cambios
- Tooltip de Semáforo: ahora aparece al instante con CSS hover (antes
  delay ~700ms con `title=`). Detalla cada motivo concreto de alerta
  (ACWR, wellness, peso, monotonía).
- Antropometría: floats a 2 decimales en todas las tablas (era
  `70.100000` → ahora `70.10`).

---

## 🔔 ESTADO 11/5/2026 — sesión larga: prepost, NJ, nombres, scouting, minutos reales

Mucho avance hoy. Cambios clave:

- **Comando `/prepost`** en Alfred (+ lenguaje natural). Lista de quién
  ha hecho PRE/POST/BORG de la última sesión, con clasificación completa
  (completos/falta uno/faltan 2/nada/fuera por estado).
- **Estado NJ (No juega)** integrado en todo el sistema. Aparece en
  Completos con etiqueta y en "Fuera por estado". EST_NJ en
  _VISTA_RECUENTO.
- **Nombres canónicos del roster**: HERRERO / GARCIA / GONZALO. Módulo
  central `src/aliases_jugadores.py` con todos los mapeos. 333 celdas
  migradas en Sheet. Scripts y dashboard refactorizados.
- **Scouting penaltis/10m refactor completo**: 17 columnas con detalle
  táctico (tirador_lateralidad, portero_direccion/forma/avance, zona
  destino P1..P9/FUERA, marcador). Pestaña editor + visualizaciones
  drill-down (por tirador, por portero, mapa de zonas, matriz
  dirección×forma). El editor de "Editar partido" también escribe a
  esa hoja al guardar (mantiene compat con EST_PENALTIS_10M).
- **vista_carga con minutos reales en partidos**: ya no se sobreestima
  al suplente que entró 2 min ni se subestima al titular de 25. Cruza
  BORG con EST_PARTIDOS.min_total.
- **`src/apuntar_wellness.py`**: completa la trilogía con
  apuntar_borg.py / apuntar_peso.py / marcar_lesion.py. Alfred los usa
  todos vía system prompt.
- **Mejoras de bot_datos**: respuestas analíticas detalladas (no
  escuetas) tras "cómo está X esta semana".
- **Recovery automático Gemini finish_reason=1** en bot_datos y Alfred.

---

## 🔔 ESTADO 8/5/2026 — Limpieza profunda + fix marcar lesión

### Servidor 24/7 → producción confirmada
- Los 3 bots corren con launchd KeepAlive=true en el Mac viejo.
- 9 apps borradas del Mac viejo (Big Sur installer 12 GB, Chrome,
  Keynote, Zoom, SmowlCM, VLC, AnyDesk, RDP, Tuxera) → ~14,7 GB.
- 3 daemons huérfanos eliminados (Tuxera NTFS agent, Zoom daemon,
  Office licensing helper).
- Spotlight desactivado en todos los volúmenes (≈80 MB RAM persistente).
- `/Users/Shared/Previously Relocated Items` y caches limpiadas.
- `purge` ejecutado → 800+ MB RAM liberados al instante.
- Resultado RAM: 3272 MB usados → 2460 MB · libres: 823 MB → 1635 MB.
- Bots verificados vivos tras toda la limpieza (PIDs 959, 912, 427).

### Mac de oficina (Mac personal del usuario) → segunda tanda
- ~8,6 GB liberados eliminando apps que no usa (Steam, Minecraft,
  Amazon Music, uTorrent, Wondershare, Claude ShipIt) y bloat de Google
  (GoogleUpdater 697 MB + Chrome OptGuideOnDeviceModel 4 GB).
- Pendiente para el final de la próxima sesión: 10 GB del bundle
  `~/Library/Application Support/Claude/vm_bundles/claudevm.bundle`
  (la VM local de Claude Desktop, hay que cerrar Claude para borrarla).

### Mail.app del Mac de oficina
- Síntoma: correos enviados desde Gmail móvil no aparecían en Mail Mac.
- Descartado: tipo de cuenta (IMAP correcto), límite de carpeta IMAP
  en Gmail (configurado a "sin límite"), reconstrucción de buzón.
- Plan B en marcha: eliminar cuenta Txubas y re-añadirla. Forzando
  re-descarga limpia desde Gmail. Pendiente verificación final tras
  sincronización completa (5-15 min).

### Marcar jugador como lesionado desde el bot
- Síntoma anterior: el bot dev "Alfred" intentaba copiar 50 líneas de
  Python para escribir a BORG y LESIONES, y Gemini metía typos
  (`ueva` por `nueva`, etc.) → la mitad de las veces fallaba.
- Solución: nuevo script `src/marcar_lesion.py` con API limpia
  (`JUGADOR FECHA [TURNO]`, flags `--dry-run/--tipo/--zona/--lado`),
  idempotente, autodetecta turno consultando SESIONES.
- System prompt de Alfred simplificado: ahora invoca el script con
  bash en una sola línea en vez de copiar código complejo.
- Probado real con PANI (8/5/2026): BORG fila 3881='L', LESIONES fila
  501 añadida. Idempotencia OK.
- Commit: `5eda501` (`marcar lesion: script idempotente + prompt simplificado`).

### Pendiente del usuario tras esta sesión
- Verificar que tras re-añadir cuenta Txubas, los correos de marzo
  aparecen en Mail.app.
- Borrar el bundle de Claude (10 GB) cuando cerremos Claude Desktop.

---

## 🔔 ESTADO 6/5/2026 — Servidor 24/7 en marcha (Fase 3 de 11)

Hoy 6/5/2026 (tarde) arrancamos el setup del Mac viejo como servidor 24/7.

**Mac viejo**: MacBook Air probable (2013-2014), Catalina 10.15.7,
i5 1.3GHz dual-core, 4GB RAM, SSD 251GB, IP local `10.48.0.113`,
hostname `InterFS-Servidor.local`.

**Estado actual**:
- ✅ Fase 1: Usuario `arkaitz` admin creado, Apple ID logout previo.
- ✅ Fase 2: Mac configurado (energía sin suspender + arranque tras
  fallo eléctrico + Sharing/SSH activos via launchctl directo).
  Usuario antiguo de la mujer eliminado.
- ✅ Fase 3 (en curso): Xcode CLT instalado (tardó 2.5h), Homebrew
  5.1.9 instalado, Python 3.11 + ffmpeg en instalación.

**Continúa MAÑANA con la Fase 4**:
- Clonar el repo desde GitHub en el Mac viejo
- Instalar dependencias Python con pip
- Copiar credenciales (.env, google_credentials.json) via AirDrop
- Probar `arrancar_bots.sh` manual
- Activar launchd con `setup_servidor/install.sh`
- Configurar Tailscale para acceso remoto
- Apagar bots del Mac de trabajo

**Reconexión SSH**: `ssh arkaitz@10.48.0.113` (o `.local`).

---

## 🔔 ESTADO 6/5/2026 — roles implementados (esperando contraseñas)

Hoy 6/5/2026 se implementó el sistema de roles y permisos completo
en autonomía. **Pendiente del usuario**: configurar las contraseñas
en `st.secrets` (~5 min). Ver `docs/roles_y_permisos.md`.

### Orden del backlog (acordado con el usuario)

1. **🔐 Roles y permisos** — ✅ código completo, esperando configuración.
2. **🖥 Servidor 24/7** con Mac viejo (siguiente).
3. **⏰ App de tiempos y estadísticas en directo** (cronómetro,
   faltas acumuladas, buzzer 5ª falta, posiblemente PWA).
4. **📱 Iter 12 — PWA offline del dashboard** (último).

### Roles implementados (✅ 6/5/2026)

4 roles: **admin** (Arkaitz), **tecnico** (cuerpo técnico),
**fisio** (Jose, Miguel, Practicas), **medico** (futuro médico).

Lo que cambia según rol:
- `admin`: TODO accesible. Único que edita partidos y scouting.
- `tecnico`: lectura. Pestaña 'Editar partido' bloqueada. Botón
  'Guardar scouting' oculto. Lesiones/Tratamientos/Temperatura
  ANONIMIZADAS por dorsal ('el 8' en vez de 'RAYA').
- `fisio`/`medico`: igual que tecnico PERO ven nombres reales en
  lesiones (necesario para su trabajo).

Implementación en `dashboard/app.py`:
- `_leer_users_secret()` → dict[contraseña] = rol
- `get_rol()`, `es_admin()`, `puede_editar_partidos()`,
  `ve_lesiones_completas()`
- `anonimizar_df(df, col_jugador, col_dorsal)` aplicado en pestañas
  médicas
- Sidebar muestra rol actual con emoji + botón cerrar sesión

**Lo que falta del usuario para activarlo** (5 min):
1. Streamlit Cloud → Settings → Secrets
2. Añadir bloque (ejemplo):
   ```toml
   [APP_USERS]
   "clave-arkaitz-2026" = "admin"
   "clave-cuerpo-tecnico" = "tecnico"
   "clave-fisios" = "fisio"
   ```
3. Save → Reboot → probar con cada contraseña en pestaña incógnito.

Compatible 100% con la configuración actual (`APP_PASSWORD` legacy
sigue funcionando = todos admin).

### Feedback cuerpo técnico (sin prisa)
El usuario va recopilando feedback durante 2-3 semanas. Cuando lo
tenga todo, lo procesamos en una sola tanda. No hay que perseguirlo
mientras tanto.

### ✅ RENDIMIENTO STREAMLIT — resuelto el 6/5/2026

Optimizaciones implementadas que resuelven el problema 429:

- [x] **batch_get (CAMBIO PRINCIPAL)**: nueva función `cargar_todas_hojas()`
      hace UNA SOLA llamada `values_batch_get()` para traer las 23 hojas
      del Sheet principal. Antes eran ~24 llamadas separadas.
      **Medido**: batch 1.1s vs 14.1s extrapolado individual = **13x
      más rápido + 23x menos reads consumidos** del rate-limit.
- [x] **Igual aplicado al Sheet de fisios** (3 hojas): 1 llamada vs 3.
- [x] **TTL de cache** ampliado a 1800s (30 min) para batches.
- [x] `@st.cache_resource` cachea el handle del Sheet para no llamar a
      `client.open()` en cada `cargar()`.
- [x] **Retry exponencial** ante 429 (5/10/20/40s).
- [x] `cargar()` con caso óptimo (busca en batch cacheado) + fallback
      individual si la hoja no está en el batch o el batch falla.

Siguientes mejoras posibles (no críticas):
- [ ] Lazy loading de SCOUTING_RIVALES (89 cols, pesada).
- [ ] Refactorizar Antropometría para usar `_to_date` global en vez de
      `_fecha_robusta` local (cosmético).

Hoy se trabajó autónomamente en dos bloques. Ambos quedan a la
espera de **acciones manuales** del usuario:

Hoy se ha trabajado autónomamente en dos bloques. Ambos quedan a la
espera de **acciones manuales** del usuario:

### 1. Oliver auto-token (✅ código listo)

DESCUBRIMIENTO clave: Oliver expone `POST /v1/auth/login` que acepta
email+password+device_id y devuelve token+refresh_token. Esto elimina
la necesidad de Playwright/headless browser. Sistema de 3 niveles
implementado en `src/oliver_login.py` + integración en
`src/oliver_sync.py`. Ver `docs/oliver_autologin.md`.

**Pendiente del usuario** (5 min):
1. Editar `/Users/mac/Desktop/Arkaitz/.env`
2. Añadir al final:
   ```
   OLIVER_EMAIL=tu-email-oliver@dominio.com
   OLIVER_PASSWORD=tu-contraseña-oliver
   ```
3. Probar: `/usr/bin/python3 src/oliver_login.py` → debería dar "Login OK"
4. Si funciona, el sistema ya hace auto-relogin automáticamente cuando
   el refresh_token caduque o se invalide.

### 2. Sheet de Lesiones y Tratamientos para fisios (✅ código listo)

Sheet SEPARADO del principal para que los fisios solo accedan a estos
datos. Migra las 499 lesiones existentes y crea TRATAMIENTOS desde
cero. Ver `docs/sheet_fisios.md`.

**Pendiente del usuario** (5 min):
1. Ir a https://sheets.google.com → '+ En blanco'
2. Renombrar a `Arkaitz - Lesiones y Tratamientos 2526`
3. Compartir con: `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com` (Editor)
4. Ejecutar: `/usr/bin/python3 src/crear_sheet_fisios.py`
5. Después: `/usr/bin/python3 src/calcular_vistas_fisios.py`

Una vez creado el Sheet:
- El usuario puede compartirlo con los fisios (Pelu, etc.) como Editor
- Los fisios introducirán datos directamente
- En el futuro: adaptar pestaña Lesiones del dashboard para leer del
  nuevo Sheet (con anonimización por dorsal para roles no médicos)

### 3. Importación J28.JAEN ✅ HECHA

Partido de ayer (3/5) importado al Sheet principal. Inter ganó 4-2.
Limpieza del partido fantasma "J28" (sin sufijo) que dejaba el script
viejo. Estado correcto: 14 jugadores en EST_PARTIDOS, 14 en
EST_PLANTILLAS, 6 goles en EST_EVENTOS, 1 cabecera en EST_TOTALES.

---

(Sección detallada de ROLES Y PERMISOS más abajo en este documento.)

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
- `/enlaces_wa` (uno por jugador con su teléfono → wa.me deeplink, abre
  WhatsApp con el mensaje listo. Lee `TELEFONOS_JUGADORES` del Sheet.
  Ver `docs/whatsapp_enlaces.md`)
- `/enlaces_hoy` (pares pre-rellenados por jugador — DEPRECATED, alias de /enlaces)
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

### 🚨 PRIORIDAD ALTA — antes del inicio temporada 26/27

- **Crono iPad → PWA real**. Hoy no es PWA, vive en el dev server del
  Mac de Arkaitz. Si Safari descarga la pestaña de memoria en mitad
  de un partido se cuelga. Para inicio de temporada DEBE estar:
  - manifest.json + service worker que cachee app + IndexedDB.
  - Instalable como app real en el iPad sin necesitar dev server.
  - Funciona offline 100% durante el partido completo.
  - Probado y validado con un partido entero antes de jugar uno
    oficial.
- **Bot de datos rebrand**: ponerle nombre propio (no @InterFS_datos_bot
  por defecto). Pendiente: Arkaitz decidir.

### Próxima sesión — pendientes inmediatos
1. ~~⚠️ J25.INDUSTRIAS no se está extrayendo~~ ✅ CERRADO 8/5/2026:
   verificado, está en EST_PARTIDOS (13 jugadores), EST_EVENTOS (6 goles)
   y EST_TOTALES_PARTIDO (3-3 vs INDUSTRIAS, 2026-04-18 en Barcelona).
   Problema resuelto en algún sync posterior.
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

### 🆕 Mejoras Streamlit pendientes (8/5/2026)

1. **🚦 ACWR no aparece en el semáforo por jugador** — la métrica está
   en `_VISTA_CARGA` (acwr_ewma) y en `_VISTA_SEMAFORO` (acwr_estado),
   pero el render del semáforo no la pinta o queda vacía. Investigar
   qué columna usa la pestaña Semáforo y por qué se queda en blanco.

2. **🏋️ Carga de sesiones de GYM** — cuando hacemos sesión de gimnasio,
   el jugador tiene carga alta (encoder, fuerza), pero como no hay
   Oliver no se cuantifica. Plantear:
   - sRPE (BORG × MIN) ya cubre la carga subjetiva, ¿se está mostrando?
   - Añadir hoja `_ENCODER` o columna en SESIONES con métrica objetiva
     de gym (ej. tonelaje total, reps × peso medio, RPE alto > X reps).
   - Decidir cómo combinarlo con ACWR: ¿inflarlo para que entre en el
     cómputo, o crear ACWR_GYM separado?
   - Hablar con Arkaitz sobre qué dato del encoder es mejor proxy de
     carga (potencia media, n_reps×peso, etc.).

3. **🗂 Normalizar ejercicios y categorización semanal** — la hoja
   `_EJERCICIOS` acumula nombres parecidos (4x5 vs 5x4, mal dictados,
   sinónimos). Crear:
   - Vista en Streamlit con TODOS los nombres únicos + frecuencia +
     fechas + minutos totales.
   - Botón para fusionar nombres (renombrar uno a otro en _EJERCICIOS).
   - Campo de categoría (técnico/táctico/físico/transición/otros).
   - Recordatorio del bot dev una vez por semana ("revisa los
     ejercicios nuevos de la semana") con JobQueue.
   - A futuro: estadísticas por categoría (cuántas veces/mes,
     minutos acumulados, jugador con más participación, etc.).

### Próximos
1. ~~**Documento de fisios**~~ ✅ CERRADO el 5/5/2026: Sheet
   "Arkaitz - Lesiones y Tratamientos 2526" con 3 pestañas
   (LESIONES, TRATAMIENTOS, TEMPERATURA) + dropdowns + PDF de
   instrucciones para Jose, Miguel y Practicas.
2. ~~**Mejorar pestaña Lesiones**~~ ✅ CERRADO el 5/5/2026: dashboard
   tiene ya 2 pestañas nuevas (🏥 Lesiones/Tratamientos y 🌡️
   Temperatura) que sustituyen y mejoran la antigua.
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
