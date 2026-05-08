# 📌 Pendientes — Movistar Inter FS

> Doc reordenado el **8 de mayo 2026** (Madrid) — sesión tarde.
> Lista maestra de pendientes ordenada por momento. Si pisamos algo en
> sesión, lo movemos de bloque. Si surge algo nuevo, lo metemos al
> bloque que toque.

---

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

- [ ] **Activar nueva versión de bot_datos en el Mac viejo** — pendiente
      desde el sábado 9/5 (commit `39fec29`). Cambios incluidos:
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

      **Comando a pegar en el Mac viejo (ssh) tras conectarse:**

      ```bash
      cd ~/Desktop/Arkaitz && git pull && launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos && sleep 4 && ps aux | grep bot_datos | grep -v grep
      ```

      Espero ver un PID nuevo (distinto del 1225 actual) en la salida.

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
