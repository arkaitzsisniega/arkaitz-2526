# 📌 Pendientes — Movistar Inter FS

> Doc reordenado el **11 de mayo 2026** (Madrid).
> Lista maestra de pendientes ordenada por momento.

---

## 🔥 MAÑANA NADA MÁS ABRIR (12 mayo, según conectes al server)

- [ ] **Investigar fallo audios Telegram** (11/5 tarde-noche): mandó 2
      audios (uno a Alfred, otro a bot_datos) preguntando por Raya y sus
      últimas 10 sesiones. **NINGUNO de los dos respondió**. Acciones:
      1. `ps aux | grep -E "telegram_bot.*bot\.py|bot_datos" | grep -v grep`
         para ver si los bots siguen vivos.
      2. `tail -60 ~/Desktop/Arkaitz/logs/bot.err.log` y
         `tail -60 ~/Desktop/Arkaitz/logs/bot_datos.err.log` para ver
         excepciones.
      3. Test de control: mandar el MISMO mensaje pero en texto. Si
         responde con texto → problema en Whisper (transcripción).
         Si no responde con texto → problema Gemini o flujo.
      4. Hipótesis principales:
         - Whisper se atascó al cargar modelo tras un reinicio del bot.
         - Gemini 2.5 Flash rate-limit / caída de Google AI Studio.
         - on_voice atrapó excepción que no se envió al usuario.

---

## ✅ Hecho hoy 11 mayo 2026 (lunes — sesión larga)

- Activación de cambios pendientes del sábado en server (bots dev y
  datos en gemini-2.5-flash + recovery automático + apuntar_borg.py /
  apuntar_peso.py / marcar_lesion.py).
- Nuevo comando `/prepost` en Alfred + detector de intent en lenguaje
  natural. Script `src/prepost_estado.py` con clasificación
  completos / falta solo X / faltan 2 / no han hecho nada / fuera por
  estado. Lee tanto `_FORM_POST` (con detalle táctico) como `BORG`
  (consolidado).
- Estado **NJ (No juega)** añadido como estado válido de BORG en todo
  el sistema (forms_utils, calcular_vistas, apuntar_borg, prompts).
  Aparece en Completos con etiqueta `(NJ)` y también en "Fuera por
  estado". `EST_NJ` añadida a `_VISTA_RECUENTO`.
- **Normalización de nombres**: nuevo módulo `src/aliases_jugadores.py`
  con canónicos HERRERO/GARCIA/GONZALO. Migración de 333 celdas en
  Sheet (JUGADORES_ROSTER, EST_PARTIDOS, EST_PLANTILLAS, EST_EVENTOS).
  Scripts y dashboard refactorizados para no tener nombres hardcoded.
- JUG 16 (basura) eliminada de BORG y _VISTA_RECUENTO.
- **Scouting penaltis/10m refactor completo**:
  - Hoja `EST_SCOUTING_PEN_10M` con 17 columnas de detalle táctico.
  - Pestaña ✏️ Editar scouting con form completo.
  - Pestaña 🎯 Penaltis/10m con filtros + KPIs + rankings + zonas.
  - Editor de penaltis en "✏️ Editar partido" ampliado con 4 columnas
    nuevas (lateralidad, dirección portero, forma, avance). Al guardar
    escribe en AMBAS hojas (EST_PENALTIS_10M para compat + 
    EST_SCOUTING_PEN_10M para detalle).
  - Vistas detalladas (paso 3): drill por tirador, por portero, mapa
    por zona, matriz dirección×forma.
- **vista_carga con minutos REALES en partidos**: cruzar con
  EST_PARTIDOS. Antes la carga del suplente (2 min) se inflaba a 40
  min. Ahora cada jugador refleja su realidad. Aplica solo a
  TIPO_SESION=PARTIDO (no a entrenamientos del mismo día). Caso
  partido sin extraer → fallback a MINUTOS de SESIONES.
- **`src/apuntar_wellness.py`**: tercer script de la trilogía
  apuntar_*. Recibe sueno/fatiga/molestias/animo (1-5 cada uno),
  calcula TOTAL. Idempotente. Alfred lo usa via prompt.

## 🔥 AHORA MISMO (sesión actual)

- [ ] **Ralenti al picar partido** — al saltar entre fecha/hora/campos en
      el form de Editar partido en Streamlit, la web se queda pensando.
      Investigar si es debouncing, re-render del editor o consulta
      innecesaria al Sheet en cada keystroke.

### Cierre de sesión (antes de irse)
- [ ] **Bundle Claude Desktop 10 GB** — cerrar Claude Desktop y mover
      `~/Library/Application Support/Claude/vm_bundles/claudevm.bundle`
      a `/tmp/`. Al reabrir Claude se regenera vacío.
- [ ] **Verificar Mail.app** — cuando termine de descargar, comprobar
      que aparecen los correos de marzo de Txubas. (Otro día, sigue en marcha.)

---

## 📅 ESTA SEMANA (a partir del lunes 11/5)

### 🟢 Lunes 11/5 — primera cosa nada más abrir

- [ ] **Activar nuevas versiones de Alfred Y bot_datos en el Mac viejo** —
      pendientes desde el sábado 9/5. Cambios:

      **Alfred (telegram_bot/bot.py)**:
      - Modelo: `gemini-2.0-flash` → `gemini-2.5-flash` (consistencia con
        bot_datos, mejor function calling).
      - Recovery automático finish_reason=1 (mismo que bot_datos).
      - Diagnóstico fino de errores Gemini.
      - Nuevos scripts curados que sustituyen el "escribir Python a mano":
        - `src/apuntar_borg.py` para apuntar BORG (número o estado S/A/L/N/D/NC).
        - `src/apuntar_peso.py` para apuntar peso PRE/POST/H2O.
        - `src/marcar_lesion.py` ya existía. Suma 3 ahora.
      - System prompt actualizado con instrucciones de cuándo usar cada
        script + regla "respuesta natural tras cada tool".

      **bot_datos (telegram_bot_datos/bot_datos.py)**, ya en la nota de
      antes (commit `39fec29`):
      - Modelo: `gemini-2.0-flash` → `gemini-2.5-flash` (mejor function
        calling, sigue gratis).
      - Recovery automático cuando Gemini "termina mudo" tras un tool call
        (bug conocido — antes salía error fatal "finish_reason=1", ahora
        hace 1 retry forzado pidiendo respuesta natural).
      - Diagnóstico fino de errores (distingue STOP/SAFETY/MAX_TOKENS/
        MALFORMED_TOOL con mensaje distinto).
      - System prompt ampliado con sección "PREGUNTAS ANALÍTICAS"
        (combinar carga + wellness + peso + semáforo en una tool call
        para preguntas tipo "cómo está X esta semana") + ejemplo 13 con
        código.

      **Comando a pegar en el Mac viejo (ssh) — reinicia AMBOS bots:**

      ```bash
      cd ~/Desktop/Arkaitz && git pull && \
        launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot && \
        launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos && \
        sleep 4 && ps aux | grep -E "telegram_bot.*bot\.py|bot_datos" | grep -v grep
      ```

      Espero ver 2 PIDs nuevos (Alfred y bot_datos), distintos a los
      últimos conocidos.

- [ ] **Verificar Alfred** tras reiniciarlo — pruebas sugeridas por
      Telegram:

      > "Alfred, apunta a Carlos un Borg de 7 hoy"
      > → debería llamar `apuntar_borg.py` y confirmar.

      > "Apunta el peso pre de Pirata, 78 kg hoy"
      > → debería llamar `apuntar_peso.py --pre 78`.

      > "Cómo está Cecilio esta semana?"
      > → debería responder en lenguaje natural tipo "Cecilio: 3
      >    sesiones, carga 2.180, ACWR 1,1 verde…".

- [ ] **Verificar bot_datos** tras reiniciarlo — pregúntale por Telegram:

      > "Qué tal ha entrenado Cecilio esta semana? Como está?"

      Comportamiento esperado:
      1. Mensaje de progreso "🔧 Consultando los datos del Sheet…".
      2. Respuesta natural tipo "Cecilio: 3 sesiones, carga 2.180,
         ACWR 1,1 verde. Wellness 13,5. Peso estable. En general OK."
      3. **Si vuelve a fallar**, copiar mensaje literal del bot y
         retomarlo en la siguiente sesión de código.

      Riesgo apuntado: Google a veces baja rate-limits del free tier
      sin avisar. Si ves "quota exceeded", bajar a 2.0 Flash con
      `GEMINI_MODEL=gemini-2.0-flash` en `telegram_bot_datos/.env`
      (sin tocar código).

### 🟢 Resto de la semana

- [ ] **Catálogo de ejercicios — uso real** — ir a la pestaña 📚 Catálogo,
      sección 🛠 Limpieza (admin), revisar nombres parecidos y fusionar.
      El bot dev avisará cada lunes a las 8:00.
- [ ] **App live con cronómetro (siguiente proyecto gordo)** — meter datos
      EN DIRECTO desde la banda durante el partido:
      - Cronómetro tipo basket: pausa al balón fuera, sustituciones en juego.
      - Botones grandes con dorsales para cambios.
      - Acciones por tap (mucho más rápido que un form).
      - Auto-cálculo de rotaciones desde los cambios.
      - Modal rápido para gol / tarjeta / falta / penalti.
      Trabajo grande, varias sesiones. **Es el siguiente gran bloque.**
- [ ] **Service account read-only para bot_datos** — el cinturón actual
      bloquea por código (regex). Para blindarlo a nivel Google: crear
      una segunda cuenta de servicio en Google Cloud Console con
      permiso *Viewer* sobre el Sheet, y configurar bot_datos para usar
      esa SA en vez de la actual. Si cualquier escritura llega a Google
      API, devuelve 403 sin posible bypass.
      *(Te explico: ahora el bot usa la misma cuenta de servicio que
      todo lo demás, que tiene permiso de Editor. Aunque mi código
      bloquea las escrituras antes de ejecutar, depende de que el
      escáner regex sea perfecto. Una segunda cuenta con solo lectura
      lo hace imposible aunque alguien encuentre cómo saltarse el
      escáner.)*

- [ ] **Alfred con visión (foto → datos)** — Gemini 2.5 Flash soporta
      imágenes gratis. Caso real: sacas foto de la planilla del partido
      escrita a mano y Alfred extrae los datos al Sheet. Implementación
      ~1-2h. *Riesgo*: la fiabilidad depende de la calidad de la foto y a
      veces el modelo inventa números si la foto está borrosa. Hay que
      hacerlo CON PASO DE VALIDACIÓN: Alfred extrae, te muestra los datos
      antes de guardar, tú confirmas. Cuando lo abordemos, definir
      primero qué tipo de fotos (planilla, hoja Excel impresa, captura
      Oliver…) y qué hojas-destino.

- [ ] **Memoria persistente Alfred / bot_datos** — hoy si launchd
      reinicia el bot (cosa habitual), se pierde el hilo de la
      conversación. Solución: persistir las últimas N interacciones a
      disco (`telegram_bot/conversaciones/<chat_id>.jsonl` o similar).
      *Esfuerzo*: ~2h. *Riesgo*: bajo si lo limitamos a las últimas 10-15
      interacciones por chat. Hacerlo cuando notes que es un problema
      real (si reinicios accidentales te están haciendo perder contexto
      con frecuencia).

---

## 🩺 MIÉRCOLES 13/5 — Reunión con los fisios y temas que salen

Reunión presencial. A partir de ahí decidimos qué cambia. Temas a llevar:

- [ ] **Pestaña Lesiones del dashboard — mejoras** que ellos pidan.
      Ideas candidatas (decide con ellos):
      - Gráfico de días-baja por zona corporal.
      - Tiempos medios de retorno por tipo de lesión.
      - Lesiones activas con countdown de retorno previsto.
- [ ] **Sheet de fisios en producción — seguimiento** — verificar con
      Pelu/Miguel/Practicas que el Sheet "Lesiones y Tratamientos 2526"
      está fluyendo bien y que los datos llegan al dashboard.
- [ ] **Decidir cómo ve la info el cuerpo técnico** — tras la reunión:
      ¿web pública? ¿login? ¿tablet en sesiones? ¿solo móvil?
- [ ] **Activar roles y permisos** — código ya listo, falta meter
      contraseñas en `st.secrets` (5 min) y que cada rol vea lo suyo:
      admin (Arkaitz), tecnico, fisio, medico.

---

## 🛠 PRÓXIMA SESIÓN DE CÓDIGO (cuando toque)

- [ ] **Iteración 11 plantilla — 4 mejoras pequeñas del form de Editar
      partido**:
      - Colores en rotaciones (gradiente del PDF también en el editor).
      - Tabla de zonas duplicada (1ª parte / 2ª parte).
      - Marcador autorrellenado en penaltis/10m.
      - Validar 6ª falta en vivo (meter 6 reales y ver alerta).
- [ ] **Marcador final del partido — extraer de D69/F69** —
      *📍 ubicación confirmada por Arkaitz (8/5/2026)*: en cada pestaña
      de partido del Excel `Estadisticas2526.xlsx`, las celdas **D69 y
      F69** contienen los goles a favor y en contra. Hay que añadir la
      lectura al parser `src/estadisticas_partidos.py` y poblar el
      marcador final en `EST_TOTALES_PARTIDO`.
- [ ] **Asistencias — confirmar lógica** — Arkaitz aclara que la
      asistencia se cuenta desde los Google Forms y de lo que él le
      pase a Alfred. Confirmar que el dashboard refleja eso bien y que
      no hay otro origen mezclado.

---

## 📅 MEDIADOS DE JUNIO 2026 — Pre-temporada

- [ ] **🆕 Planilla de evaluación inicial de jugadores (PRINCIPIO DE
      TEMPORADA)** — ficha individual de cada jugador para arrancar la
      pretemporada con un buen estudio basal. Contenidos a incluir:
      - **Datos personales y trayectoria**: fecha de nacimiento, edad,
        clubes anteriores, años jugando profesional.
      - **Historial médico y de lesiones**: lesiones previas, cirugías,
        problemas crónicos, medicación, alergias.
      - **Tests físicos** con las herramientas del staff:
        - Movilidad (rangos articulares, tobillo, cadera, etc.).
        - Fuerza (encoder, press de pierna, sentadilla, etc.).
        - Salto (CMJ, Squat Jump, etc. — con app de móvil o My Jump).
        - Sprint / aceleración si tenemos forma de medir.
        - Wellness baseline (puntuación de inicio).
      - **Antropometría inicial**: peso, % grasa, agua, masa muscular.
      - **Objetivo**: que en septiembre tengamos una ficha completa por
        jugador, con su baseline objetivo, lesiones que arrastra, y
        plan individualizado para arrancar.
      - **Decisión**: implementar como hoja `JUGADORES_FICHA` en el
        Sheet + pestaña dashboard de "Ficha individual" + posible
        Form para que cada jugador rellene sus datos personales.
- [ ] **Plantilla 26/27** — Arkaitz pasa lista oficial nueva temporada
      (porteros + jugadores 1er equipo + filial que sube). Actualizar
      `_OLIVER_ALIASES` y archivar datos históricos de los que se vayan.

---

## 📅 ALGÚN DÍA (sin urgencia)

- [ ] **Iteración 12 plantilla — PWA offline** — app web móvil/tablet
      que funciona sin internet (en bus, pista sin wifi) y sincroniza
      al volver la red. Next.js + IndexedDB + Service Worker + sync
      Sheets. Trabajo grande, varias sesiones.
- [ ] **Limpieza Safari/WebKit del Mac de oficina** — si vuelve a tirar
      pesado, cerrar pestañas viejas y revisar extensiones. No urgente.

---

## ✅ Hecho hoy 8 mayo 2026 (registro)

### Mac viejo (servidor)
- 9 apps borradas (~14,7 GB): Big Sur installer, Chrome, Keynote, Zoom,
  SmowlCM, VLC, AnyDesk, Remote Desktop Connection, Tuxera Disk Manager.
- Caches usuario, /Users/Shared/Previously Relocated Items, logs ASL.
- Spotlight desactivado en todos los volúmenes (-80 MB RAM permanente).
- 3 daemons huérfanos eliminados (Tuxera, Zoom, Office licensing).
- `sudo purge` → +800 MB RAM libres al instante.
- Resultado RAM: 3272 MB → 2460 MB usados (1635 MB libres tras todo).
- Bots verificados vivos.

### Mac de oficina
- ~8,6 GB liberados (Steam, Minecraft, Amazon Music, uTorrent,
  Wondershare, Claude ShipIt, GoogleUpdater, Chrome OptGuide model).

### Bot dev (Alfred) — fix marcar lesión
- Nuevo `src/marcar_lesion.py` idempotente.
- Prompt simplificado para que llame al script en vez de copiar Python.
- Validado real con PANI.

### Streamlit / Dashboard
- ✅ Fix ACWR semáforo: ahora se calcula con el último día disponible,
  no esperando al domingo. 16/18 jugadores con ACWR (antes 0/18).
- ✅ Factor 1,25 sobre carga en sesiones que contienen GYM (corrige
  subestimación mental al reportar BORG combinado).
- ✅ Catálogo de ejercicios → nueva sección 🛠 Limpieza (admin only)
  con tabla de nombres únicos, sugerencias de fusión por similitud
  ≥ 80% (difflib), botón fusionar que renombra en `_EJERCICIOS`.
- ✅ Borrado partido fantasma "PRUEBAS" de EST_*.

### Bots
- ✅ Recordatorio del bot dev cada lunes a las 8:00 (Madrid) para
  revisar el catálogo de ejercicios.
- ✅ Alfred migrado de `gemini-2.5-flash-lite` a `gemini-2.0-flash`
  (más capaz, sigue gratis).
- ✅ Alfred prompt actualizado para tono más conversacional / WhatsApp.
- ✅ Bot datos blindado a solo-lectura por código: escáner que rechaza
  cualquier código Python con `update_cell`/`append_row`/`batch_update`/
  `os.remove`/`subprocess`/etc., y bash con `rm`/`git push`/`>`/etc.
  Tests pasados: 14 casos Python + 12 casos bash.

### Verificaciones de datos
- J25.INDUSTRIAS confirmado correctamente extraído (estaba como
  pendiente en docs, ya estaba bien).
- Comprobado que totales de tiempo por parte (col L y N filas 74-86 del
  Excel) **están bien parseados** — eran minutos por jugador (`min_1t`,
  `min_2t`), no totales por equipo.

---

## 🚮 Eliminados de la lista (cerrados o no aplicables)

- ~~Probar Alfred 2.0 Flash + tono nuevo~~ → se prueba sobre la marcha.
- ~~Probar cinturón bot_datos~~ → se prueba sobre la marcha.
- ~~Bot gastos_bot Lis~~ → ya añadida y funcionando.
- ~~Imprimir planilla~~ → ya hecho y funcionando.
- ~~Fecha J17.ELPOZO~~ → ya corregida.
- ~~EST_TOTALES_PARTIDO disparos por parte~~ → no están en Excel.
- ~~Goles en contra cuarteto~~ → ya funciona en Streamlit.
- ~~Cambiar contraseña Oliver `@Inter1977`~~ → no se va a cambiar
  (datos irrelevantes para Arkaitz).
