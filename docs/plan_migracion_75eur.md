# Plan de migración con €75/mes — 1 junio 2026

> Mandato de Arkaitz (15/5/2026): "calcula números con el presupuesto
> de 75€ al mes para migrar". Apuntado en `docs/mandato_solo_16-05-2026.md`.

---

## TL;DR (recomendación final)

| Componente | Hoy | Propuesta 1 junio | Coste mensual estimado |
|---|---|---|---|
| Alfred (bot dev) | Gemini 2.5 Flash Lite (gratis) | **Claude Haiku 4.5** | **~5 €** |
| bot_datos (CT) | Gemini 2.5 Flash Lite (gratis) | **Claude Haiku 4.5** | **~4 €** |
| Dashboard | Streamlit Cloud Community (gratis) | **mantener Community** | **0 €** |
| Hosting crono | GitHub Pages (gratis) | **mantener GitHub Pages** | **0 €** |
| Oliver Sports | Plan gratis, token 24h | mantener (a evaluar pago) | **0-?? €** |
| **Total esperado** |  |  | **~9 €/mes** |
| **Margen libre 75€** |  |  | **~66 €** |

Conclusión: con 75€/mes hay **muchísimo margen** para migrar Alfred y
bot_datos a Claude (que es la queja recurrente: safety filters de
Gemini, latencia variable) y dejar buffer para imprevistos /
mejoras incrementales sin estresar.

---

## 1. Volumen real medido (no estimado a ojo)

Fuente: `telegram_logs/` del 23/04/2026 al 07/05/2026 (12 días con datos).

**Alfred (bot dev)**:
- 80 mensajes totales en 12 días → **6,7 mensajes/día promedio**
- Pico: 19 mensajes el día con partido (4/05).
- Chars: 15.706 user + 36.345 bot.

Extrapolando a 30 días:
- **~200 mensajes/mes**

**bot_datos**: sin logs detallados (los logs son del `@InterFS_bot`), pero
estimación conservadora basada en uso del CT:
- 5 mensajes/día × 30 = **150 mensajes/mes**

---

## 2. Coste por mensaje (cálculo detallado)

Cada llamada al LLM envía:
- **SYSTEM_PROMPT**: ~26.000 chars (medido) = **~6.500 tokens** input.
- **Tool definitions** (function calling): ~5 tools × 300 tokens = **~1.500 tokens** input.
- **Historial conversacional** (Alfred guarda contexto): media 3-5 turnos previos = **~3.000 tokens** input.
- **Mensaje del usuario**: 40-200 chars = **~50 tokens** input.
- **Respuesta del modelo**: 200-800 chars + posibles tool calls = **~400 tokens** output.

**Por mensaje ≈ 11.000 tokens input + 400 tokens output.**

**Total mensual los 2 bots (200 + 150 = 350 msg):**
- Input: 350 × 11.000 = **3,85 M tokens / mes**
- Output: 350 × 400 = **140 K tokens / mes**

---

## 3. Comparativa de modelos (con tus números reales)

Precios mayo 2026 (público, por 1M tokens):

| Modelo | $/M input | $/M output | Coste mensual real | Notas |
|---|---|---|---|---|
| **Gemini 2.5 Flash Lite** (actual) | $0.10 | $0.40 | $0.45 (~0.40 €) | Free tier. Safety filter problemático. |
| Gemini 2.5 Flash | $0.30 | $2.50 | $1.51 (~1.40 €) | Más reasoning. Aún safety. |
| **Claude Haiku 4.5** | $1.00 | $5.00 | $4.55 (~4.20 €) | Estable, sin safety filter erróneo. **★** |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $13.65 (~12.60 €) | Calidad premium. Mejor tool use. |
| GPT-4o-mini | $0.15 | $0.60 | $0.66 (~0.60 €) | Sería migrar de ecosistema. |
| GPT-4o | $2.50 | $10.00 | $11.03 (~10.20 €) | Idem. |

**Para tu uso de 350 msg/mes**, todos los modelos están bajo 14€/mes.
El presupuesto de 75€ holgadísimo.

---

## 4. Recomendación argumentada

### Para Alfred + bot_datos: **Claude Haiku 4.5**

Razón:
- **Sin safety filter erróneo**: el problema recurrente de Gemini
  (`finish_reason=10` con preguntas inocuas tipo "lista de asistencias")
  desaparece. Claude prácticamente no bloquea contenido legítimo de
  fútbol/medicina deportiva.
- **Mejor tool use**: function calling más fiable, sigue mejor el
  formato esperado.
- **Latencia más estable**: menos picos de 7+ minutos.
- **Coste asumible**: ~4-5€/mes los dos bots juntos.

### NO recomiendo Sonnet salvo necesidad

Razón: Haiku ya cubre todo lo que hace Alfred (parseo de texto,
clasificación de intent, redacción de respuestas). Sonnet es 3x más
caro y la mejora en este uso concreto es marginal.

Excepción: si el **bot de scouting de partido** (proyecto futuro)
necesita razonamiento más fino para extraer estructura compleja de
descripciones largas, usar Sonnet solo para ese bot tendría sentido.
Y aún así, en 75€/mes cabe.

### Streamlit: mantener Community

El plan Community gratuito **ya cubre el uso del Inter** sin problemas:
- App pública con auth básica.
- Recursos suficientes para el dashboard actual.
- Auto-deploy desde GitHub.

Streamlit Teams (~25€/mes) añade:
- Secrets cifrados en infraestructura.
- Dominio custom.
- Más recursos de cómputo.

**Pero los secretos ya están bien manejados** en `st.secrets` (no se
exponen) y el dominio actual `interfs-datos.streamlit.app` funciona.
No hay justificación de cambiar.

### Oliver Sports: evaluación pendiente

El plan gratis tiene el token de 24h que caduca. Es molesto pero
manejable con el script de regeneración.

Plan pago: no he encontrado precio público. Habría que preguntar al
vendor. Si es <30€/mes y soluciona token de 24h, vale la pena.

---

## 5. Plan de migración paso a paso (cuando arranque junio)

### Día 1 — Setup
1. Crear cuenta Anthropic API si no la hay (Arkaitz).
2. Generar API key.
3. Apuntar a `.env` del bot dev y del bot_datos.
4. Añadir `anthropic` al `requirements.txt` de ambos bots.
5. Por SSH: `pip install` en los venvs del servidor.

### Día 1-2 — Migración Alfred
1. Crear `telegram_bot/llm.py` con wrapper que abstrae proveedor.
2. Modificar `bot.py` para usar el wrapper en lugar de `genai`.
3. Smoke test local con la API real.
4. Push → auto_pull → probar en producción con preguntas reales.
5. Plan B: si algo cojea, env var `LLM_BACKEND=gemini` permite
   volver al modelo viejo sin re-deploy.

### Día 3 — Migración bot_datos
- Aplicar el mismo wrapper.
- Smoke tests del lado del CT.

### Día 4-5 — Observación y ajuste
- Medir consumo real de tokens (Anthropic da dashboard).
- Ajustar SYSTEM_PROMPT si Claude necesita formato distinto que
  Gemini.
- Confirmar que no se rompen los atajos (los atajos SIN LLM no
  afectados).

### Día 6+ — Buffer / mejoras
- Con el ahorro (75€ − 10€ ≈ 65€ libres):
  - Posible plan pago de Oliver (si tiene sentido).
  - Imprevistos.
  - Acumular para temporada 26/27.

---

## 6. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Claude da respuestas con tono diferente al de Gemini, Arkaitz no se acostumbra | Media | Ajustar SYSTEM_PROMPT primer día. Iteración corta. |
| Algún flujo concreto se rompe en la migración (tool call que Claude llama distinto) | Media-baja | Wrapper LLM neutral + variable LLM_BACKEND para volver atrás sin esfuerzo. |
| Coste real > estimado (más historial, más tokens) | Baja | Dashboard de Anthropic. Si supera 20€/mes los 2 bots, revisar. |
| Anthropic API se cae | Muy baja | Fallback automático a Gemini en wrapper si Anthropic da error. |

---

## 7. Pendiente DECISIÓN de Arkaitz

Al volver de entrenar y leer esto:

1. **¿OK con la propuesta Claude Haiku** para los 2 bots?
   (Si dudas, alternativa Sonnet por +8€/mes).
2. **¿Algo más que quieras meter** en el presupuesto?
   - Plan pago Oliver (consultar precio).
   - Streamlit Teams si el club quiere dominio custom.
   - Otros servicios.
3. **¿Migración el 1 de junio exacto, o antes/después?**
   - Antes (esta semana): test con tráfico real, menos riesgo.
   - Después (después del 1): cuando el presupuesto entre.

Cuando confirmes, lo dejo todo preparado para enchufar.
