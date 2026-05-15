# Sesión "trabajo solo" 16/5/2026 (mientras Arkaitz entrena)

> Mandato registrado en `docs/mandato_solo_16-05-2026.md`. Ejecutado
> sin pausa durante ~2 horas. Resumen ejecutivo para que Arkaitz
> revise al volver.

---

## 🎯 Tareas atacadas

### 1. ✅ Plan migración 75 €/mes (con NÚMEROS)
- Output: `docs/plan_migracion_75eur.md`.
- Volumen REAL medido desde `telegram_logs/` (no estimado a ojo):
  **80 mensajes en 12 días = 6,7 msg/día** Alfred.
- Coste real proyectado los 2 bots:
  - Gemini 2.5 Flash Lite (actual): ~0,40 €/mes
  - Claude Haiku 4.5 (propuesta): **~5 €/mes**
  - Claude Sonnet 4.6 (alternativa premium): ~13 €/mes
- **Recomendación**: migrar a **Claude Haiku 4.5** los 2 bots.
  Deja **~66 €/mes de margen** dentro del presupuesto de 75 €.
- Streamlit Cloud Community sigue siendo suficiente (no migrar).
- Wrapper LLM agnóstico previsto para hacer la migración con
  vuelta-atrás trivial (env var `LLM_BACKEND`).

### 2. ✅ Bug Alfred — atajo carga_ultima toleraba mal plurales/sinónimos
- Frase del user que falló: *"Como fue el entrenamiento de ayer? dime
  las cargas"*. Triggers solo cubrían "entreno" (no "entrenamiento") y
  "carga" (no "cargas"). Caía a Gemini → safety filter → bloqueo.
- Refactor del detector con:
  - Sustantivos clave en plural/singular.
  - Word-boundary regex (helper `_palabra_aparece`).
  - Lista de exclusiones para evitar falsos positivos.
- Tests añadidos cubren la frase original + 5 variantes. 12/12 verde.

### 3. ✅ Nuevo atajo SIN LLM: peso de jugador
- Patrón detectado en logs ("peso de Cecilio últimos 10 días" × varias).
- Nuevo `src/peso_jugador.py`: lee `_VISTA_PESO`, devuelve última
  medida + cronología + alerta si está bajo baseline.
- Detector + handler en ambos bots.

### 4. ✅ Mejor mensajería de error en Alfred
- Cubre `finish_reason=10` (safety filter): mensaje específico con
  sugerencia de usar atajo SIN LLM.
- Cubre `403`/`forbidden`, `quota exceeded`, `json/parse`, etc.
- Nuevo `_sugerir_atajo_si_aplica`: cuando Gemini falla pero la
  pregunta huele a algo con atajo, sugiere la reformulación concreta.

### 5. ✅ Mejoras dashboard Streamlit — pestaña Lesiones
- KPI nuevo: "🔁 Recaídas" en la cabecera.
- Bloque **📊 Análisis del periodo** con:
  - Gráfico barras horizontales: días-baja por zona corporal.
  - Gráfico barras: lesiones por mes.
  - Top 3 jugadores más afectados (días totales).
  - Tabla tiempo medio recuperación por gravedad.
- Solo aparece si hay >=3 lesiones (no satura con poca data).

### 7. ✅ Nuevo atajo SIN LLM: recuento de jugador
- Patrón detectado en logs ("cuántas sesiones lleva Jaime esta temporada").
- Nuevo `src/recuento_jugador.py`: lee `_VISTA_RECUENTO`, devuelve
  sesiones totales, sesiones con datos, % participación con semáforo,
  desglose de estados (S/A/L/N/D/NC/NJ) y comparativa con la media
  del equipo.
- Detector + handler en ambos bots.
- Probado: "Pirata 97% participación, +31% sobre la media."

### 8. ✅ Letras más grandes en pestaña Resumen del crono
- Pestaña **General**: cabeceras text-xl, cajas p-6, totales text-xl bold.
- Pestaña **Individual**: tabla text-sm (era [11px]), padding +, columnas
  más anchas (min-w-780px), totales destacados.
- Cumple la queja del user: "respetando la organización aún más grande".

### 6. 🟡 Verificación bundle del crono
- Confirmado: el bundle nuevo con 🟥 Roja, TecladoDorsalRival,
  ModalRoja, etc. **SÍ está desplegado** en gh-pages (MD5 idéntico
  al local cuando se fuerza `Cache-Control: no-cache`).
- El user veía la versión vieja por **caché del CDN de GitHub
  Pages + Safari iOS**. Resolución: refrescar caché en el iPad
  (Ajustes → Safari → Datos de sitios web → eliminar
  `arkaitzsisniega.github.io`).
- Re-deploy forzado realizado para acelerar invalidación.

---

## 📋 Commits empujados durante esta sesión

main:
```
0d5495b fix Alfred: detector carga_ultima tolera entrenamiento/cargas/plurales
ccd5f36 profundizar Alfred: peso_jugador atajo + mensajes error humanos + plan migracion
7479494 dashboard: pestana Lesiones con analisis visual + nota sesion solo
91ecab0 atajo SIN LLM: recuento jugador (cuantas sesiones lleva X)
fe9aa7a crono: letras aun mas grandes en pestana general + individual (source)
```

gh-pages:
```
691bc3f crono: re-deploy para invalidar caché CDN de GH Pages
67b6d16 crono: letras aun mas grandes en resumen general + individual
```

**Total: 7 commits, ~12 features/fixes.**

---

## 📊 Estado del backlog tras esta sesión

### Atajos SIN LLM en producción
1. ✅ Lesiones activas
2. ✅ Ranking temporada (asistencias/goles/etc)
3. ✅ Estado de jugador
4. ✅ Carga última sesión (¡fix hoy del entrenamiento/cargas!)
5. ✅ PRE/POST listado con fecha
6. ✅ Goles de jugador
7. ✅ Peso de jugador (NUEVO hoy)
8. ✅ Recuento de jugador (NUEVO hoy)

**8 atajos SIN LLM = mínimo riesgo de safety filter.**

### Pendientes (sin urgencia)
- Wrapper LLM agnóstico (preparativo migración 1 junio — diseño hecho,
  implementación pendiente).
- Test partido grabado real en iPad (Arkaitz lo apuntó).
- Mini-crono regresivo: validación de casos límite (2 expulsados a la vez).
- Editor partidos: auditoría de cache (Arkaitz dijo "suena a parche").
- Bot scouting (post 1 junio).

---

## ❓ Decisiones pendientes para Arkaitz al volver

1. **¿OK con migración a Claude Haiku** para los 2 bots el 1 de junio?
2. **¿Streamlit Lesiones** te aporta con los gráficos nuevos o lo
   quitamos por sobrecarga visual?
3. **Bundle del crono** — ¿al refrescar caché en el iPad ya ves los
   cambios (botón roja, modal pista con amarilla, teclado rival)?
4. **¿Más atajos SIN LLM a añadir**? Otros patrones detectados:
   "cuántas sesiones lleva X" (recuento individual) — fácil de añadir
   si confirmas que es uso real.

---

## 🎯 Lo que NO se hizo (para próximas sesiones)

- Migración real Alfred → Claude API (espera al 1 de junio).
- Wrapper LLM agnóstico (preparado en diseño, no implementado).
- Auditoría del editor de partidos en Streamlit (lo dejaste como
  "suena a parche" pero no urgió).
- Mejoras adicionales del crono pendientes:
  - Mini-crono regresivo en banner sticky en lugar de banner top.
  - Validación: si pones 2 expulsados a la vez, ¿qué pasa?
  - Tests con partido grabado completo en iPad (lo apuntaste).
- Bot de scouting (proyecto futuro, post-1-junio).

---

Cuando vuelvas, dime "vamos al lío" o "qué tal" y te paso el resumen
ejecutivo otra vez en 30 segundos.
