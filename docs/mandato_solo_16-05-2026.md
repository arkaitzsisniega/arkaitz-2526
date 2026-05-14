# Mandato para Claude — mañana 16/5/2026 ~9:30

> **Trigger**: Arkaitz dirá "nos vamos a entrenar" (o algo similar) hacia
> las 9:30, tras un rato de trabajo conjunto. A partir de ahí Claude se
> queda solo y trabaja sin pausa hasta que vuelva.

> **Mandato literal de Arkaitz (15/5/2026 noche)**:
> "Calcular numero con el presupuesto de 75 al mes para migrar / Revisar
> PROFUNDAMENTE los bots y mejorar todo lo que consideres para que
> vuelen / Revisar PROFUNDAMENTE streamlit para que vuele. Haces todo
> eso, y lo dejas guardado para ponerlo en marcha el 1 de junio."

---

## Tarea 1 — Plan de migración con 75 €/mes (numbers, no intuiciones)

**Output esperado**: `docs/plan_migracion_75eur.md` con números concretos.

Desglosar:
1. Coste actual (todo gratis). Documentar.
2. Opciones para Alfred:
   - Gemini 2.5 Flash (actual, gratis): pros/contras conocidos (safety
     filter, latencia variable).
   - Claude Haiku via API: precio por 1M input/output tokens. Estimar
     volumen mensual (mensajes × tokens medios) y proyectar coste.
   - Claude Sonnet 4.6 via API: ídem.
   - Gemini 2.5 Pro de pago: ídem.
3. Opciones para Streamlit:
   - Streamlit Cloud Community (actual, gratis): límites conocidos
     (recursos, secrets, dominio).
   - Streamlit Teams: precio, qué desbloquea (más recursos, secrets
     cifrados, dominio custom).
4. Opciones para Oliver Sports:
   - Plan actual (token caduca cada 24h): coste real en tiempo de
     mantenimiento.
   - Plan pago (si existe): precio, valor (token estable).
5. **Recomendación final**: combinación concreta que entre en 75 €/mes
   con margen. Justificada con números.

No hace falta probar la migración aún. Solo el plan + cálculos.

---

## Tarea 2 — Niquelar los bots (Alfred + bot_datos)

**Output esperado**: commits a `main` con mejoras + actualización de
`estado_proyecto.md` con qué se ha cerrado.

Direcciones de profundización candidatas (priorizar por impacto):
1. Auditar `/sesion` (voz) con el mismo lente que `/ejercicios`: ¿flujo
   lento bloqueante? Aplicar patrón async background si procede.
2. Otros flujos que aún puedan parecer "esperando 5 min":
   `/oliver_sync`, `/oliver_deep`, `/auditar`. Revisar caso por caso.
3. Más atajos sin LLM si hay consultas frecuentes que aún caen a Gemini.
   Mirar logs de `telegram_logs/` para detectar patrones.
4. Mejor mensajería de error: en lugar de mostrar tracebacks crudos,
   traducir errores comunes a frases que Arkaitz entienda.
5. Tests más profundos en `tests/smoke_bots.py`: cobertura de los
   nuevos atajos (goles_jugador), del flujo async (/consolidar) y del
   /status.
6. Logging estructurado: que cada acción quede registrada con
   timestamp + chat_id + duración. Para detectar drift y problemas
   recurrentes.
7. Revisar SYSTEM_PROMPTS de ambos bots: ¿son del tamaño óptimo? ¿hay
   instrucciones obsoletas? ¿hay contradicciones?

Hacer commits granulares (un foco por commit) para que sea legible.

---

## Tarea 3 — Streamlit volando

**Output esperado**: commits a `main` con mejoras en `dashboard/app.py`
y/o sus helpers. Push → autodeploy en Streamlit Cloud.

Direcciones:
1. **Cache+timeouts del editor de partidos** (lo más urgente que dijo
   Arkaitz que aún suena a parche). Localizar todas las lecturas del
   editor, aplicar `@st.cache_data(ttl=N)`, medir antes/después.
2. Auditar TODAS las pestañas: cualquier `st.spinner("Cargando...")`
   que dure >2 s = candidato a cache.
3. Tablas grandes: usar `st.dataframe` con `use_container_width=True`
   y altura fija para no estirar la página.
4. PDFs (cronograma, fichas jugador): verificar que no crashean en
   navegadores móviles. Si crashean, ofrecer fallback "descargar".
5. Semáforos: que TODAS las pestañas usen la misma lógica de colores
   (verde / amarillo / naranja / rojo) sin discrepancias.
6. Formato numérico global: ya está con 2 decimales por monkey-patch.
   Verificar que sigue cubriendo todas las pestañas tras posibles
   regresiones de hoy.
7. Tooltips: que cada métrica técnica tenga su explicación en hover.

---

## Reglas operativas durante el modo solo

- Antes de cada push: smoke tests verdes (Inter + gastos si toco
  algo del gastos_bot).
- Commits granulares con mensaje claro de "qué y por qué".
- Si algo se quedara a medias, dejar `TODO` en el código y apuntar
  en `estado_proyecto.md`.
- Si toco `gastos_fijos.py`, `requirements.txt`, o cualquier env var
  nueva → apuntar en `docs/pendiente_proxima_oficina.md` el paso
  manual que haga falta en el servidor (recordar que auto_pull NO
  hace pip install).
- No tocar `gastos_bot/gastos_fijos.json` (datos personales reales
  del usuario).
- No bot scouting — eso es post-1-junio, ya está apuntado.

Al volver Arkaitz: ponerle al día con un resumen ejecutivo de qué se
ha hecho, qué se ha mejorado mensurable, y qué queda como riesgo.
