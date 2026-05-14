# Plan junio 2026 — Profundización + presupuesto aprobado

> ✅ **Presupuesto aprobado: 75 €/mes** (Movistar Inter FS) para mejora
> sustancial de Streamlit + bots. **Arranca 1 junio 2026.**

---

## 1. Hasta el 1 de junio — PROFUNDIZAR al máximo

Mandato literal de Arkaitz (15/5/2026 tarde):

> "Apunta bien: PROFUNDIZAR, al máximo. Dejando los bot niquelados y la
> web volando. Que cuando me vaya a entrenar por ejemplo puedas avanzar
> en mejorar todo eso, dejarte listo y el día 1 de junio lo hacemos."

Traducción operativa:

- Mientras Arkaitz no esté en pantalla, trabajar autónomamente en mejorar
  los bots de Inter (Alfred + bot_datos) y el dashboard Streamlit hasta
  dejarlos en estado "presentable, sin parches pendientes".
- Frente "bots niquelados":
  - Sin tiempos de respuesta > 5 s en consultas frecuentes (atajos sin LLM).
  - Sin riesgos de safety filter en preguntas normales (intent detectors).
  - Sin posibilidad de escritura accidental al Sheet (cinturón + SA r/o).
  - Cobertura de smoke tests sobre cualquier camino nuevo que se añada.
  - Respuestas asíncronas en cualquier flujo que tarde >5 s (paradigma
    "✅ Recibido, procesando…" + resultado al terminar — ya aplicado en
    /ejercicios; extender a cualquier otro flujo lento).
- Frente "web volando":
  - Streamlit con cache adecuado en cada lectura pesada.
  - Tooltips + formato consistente (2 decimales globales, no decimales
    espurios).
  - Sin warnings en consola; sin tablas vacías con título;
    semáforos coherentes en TODAS las pestañas.
  - PDFs (cronogramas, fichas jugador) generables desde el dashboard sin
    crashes en navegadores móviles.

**Si Arkaitz se va a entrenar y me dice "sigue trabajando", el norte es
este documento + `estado_proyecto.md`.**

---

## 2. Día 1 de junio — Activación del presupuesto

Cuando entre el dinero (75 €/mes), evaluar:

- ¿Migrar Alfred de Gemini Flash a Claude Haiku/Sonnet (más estable, menos
  safety filter spurious)? — coste mensual estimado, ver si entra en 75 €.
- ¿Streamlit Cloud → Streamlit Teams (más recursos, secrets cifrados)?
- ¿Plan pago de Oliver Sports para que el token no caduque cada 24h?

(Llegar al 1 de junio con NÚMEROS, no con intuiciones.)

---

## 3. Proyecto FUTURO — bot de scouting de partido

Idea de Arkaitz (15/5/2026): un nuevo bot, separado de los dos actuales,
que sirva al cuerpo técnico para anotar lo que ven en un partido **en
directo** y de forma **manos libres**:

- Un miembro del CT dicta por voz al bot ("delantero del 7 ha hecho dos
  paredes con el ala izquierda, presión alta tras pérdida en el 12, mal
  posicionamiento defensivo en el 18…").
- El bot transcribe (Whisper local, ya lo usamos en gastos + Alfred).
- El bot **estructura** la observación: extrae jugador (rival), minuto,
  tipo de acción, calidad/valor, contexto. (Probable LLM con esquema
  estricto, idéntico al de `parse_ejercicios_voz.py`.)
- Lo guarda a una hoja `SCOUTING_BRUTO` con timestamp + minuto del partido.
- Permite pedir resúmenes al vuelo: "qué he dicho del 7 hasta ahora",
  "anotaciones de táctica defensiva", "minutos clave del primer tiempo".

**Requisitos pendientes (cuando se aborde)**:
- Definir taxonomía de observaciones con Arkaitz antes de codificar.
- Distinguir entre "lo que veo" vs "lo que infiero" vs "lo que recomiendo".
- Manejar voz larga (>1 min) sin perder transcripción.
- Botón "marcar momento clave" para flag visual al volver al vídeo.

**Fecha estimada de arranque**: posterior al 1 de junio, una vez los dos
bots actuales estén realmente niquelados.

---

## 4. Lo que se ha entregado el 15/5/2026 (tarde)

Cambios en `gastos_bot` (personal de Arkaitz + Lis, pedidos explícitamente):
- Tras apuntar cualquier gasto, el bot devuelve automáticamente:
  - Resumen del mes en curso (total + por categorías con %).
  - Cronología completa concepto a concepto.
- Comando `/gastos_fijos` + `/gastos_fijos --force` para aplicación manual.
- JobQueue dispara automáticamente día 1 de cada mes a las 09:00 Madrid
  los gastos fijos configurados en `gastos_fijos.json`.
- Si el bot está apagado el día 1, al arrancar comprueba y recupera.
- Plantilla `gastos_fijos_PLANTILLA.json` con ejemplos.
- LEEME.md actualizado.

*Recordatorio: en `bots_alcance.md` está apuntado que gastos_bot es
personal y no entra en smoke tests del Inter. Sigue siendo así. Solo
atendemos cambios cuando Arkaitz lo pide explícitamente, como esta vez.*
