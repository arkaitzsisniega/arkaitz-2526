# Presupuesto mensual para acelerar la infra (web + bots)

Análisis honesto del coste real para que Streamlit, Alfred y el bot de
datos vayan **rápidos**, sin caer, y respondan en segundos.

---

## Resumen ejecutivo (lo que le diría yo a la directiva)

Hay 3 piezas:
1. **Streamlit (panel de datos)** — ahora gratuito.
2. **Bots de Telegram** (Alfred + datos) — gratis los bots, pero usan
   APIs de IA que sí cobran si quieres calidad alta.
3. **Servidor 24/7** — actualmente es el Mac viejo. Sale gratis (es de
   Arkaitz) pero tiene single-point-of-failure.

**Recomendación realista**: **45–60 €/mes** te da una mejora notable en
las 3 piezas, sin tirar dinero. Si bajas a **20 €/mes** mejoras solo
Streamlit. Por encima de 100 €/mes ya entra en territorio "no compensa".

| Nivel | Coste/mes | Qué obtienes |
|-------|-----------|--------------|
| **A · Gratis (estado actual)** | 0 € | App duerme, Gemini Flash a veces dura 1-3 s, falla con prompts largos. Server = Mac viejo. |
| **B · Mejora mínima** | ~20 € | Streamlit sin sleep, dashboard 2-3× más rápido. Bots igual. |
| **C · Recomendado** | ~45-60 € | Streamlit pro + IA premium para bots, respuesta <3 s. |
| **D · Premium** | ~120-180 € | Server en la nube, redundancia, soporte. Sin ganancia perceptible para el cuerpo técnico. |

---

## Pieza 1 — Streamlit (panel de datos)

### Hoy
- Streamlit Community Cloud, plan **gratis**.
- La app se duerme tras varios días sin tráfico. Tras 12h sin uso
  reciente, primer usuario que entre puede ver el botón "Yes, get
  this app back up!" (5–30 s de espera).
- Solo 1 GB de RAM. Al cargar el Sheet entero la primera vez tarda
  3-6 s. Las siguientes son instantáneas (cache).

### Opciones de pago
1. **Streamlit Cloud Pro (Snowflake)** — ~25 €/mes
   - **2× RAM** (2 GB), no se duerme, deploys más estables.
   - **Lo que vas a notar**: panel ya nunca pide "wake up", carga
     inicial ~2 s, cambios de pestaña instantáneos.
   - Honesto: con 1 GB y nuestra optimización actual funciona bien;
     el "no dormirse" es la mejora real, no la velocidad.

2. **Streamlit Cloud Team** — ~75 €/mes
   - Hasta 5 usuarios admin, SSO, soporte por email.
   - Para el cuerpo técnico no aporta vs Pro. **No lo recomiendo**.

3. **Hostear nosotros en VPS** (Hetzner CX22, Render, Railway) — 4-15 €/mes
   - VPS 4 GB RAM, control total, sin sleep.
   - **Contra**: configurar y mantener nosotros. Si se cae a las 2 AM
     un viernes, hay que arreglarlo. Yo no recomiendo esta vía para
     un cuerpo técnico sin DevOps.

**Mi recomendación**: **Streamlit Cloud Pro · 25 €/mes**.

---

## Pieza 2 — Bots Telegram (Alfred + datos)

Los bots no tienen coste como tal (Telegram es gratis). El gasto está
en las APIs de IA que usan dentro:

### Hoy
- **Alfred (@InterFS_bot)**: Claude (CLI con permisos full) — usa
  tu suscripción Claude Code Max.
- **Bot de datos (@InterFS_datos_bot)**: Gemini 2.5 Flash, plan
  gratuito de Google.

### Costes reales por modelo (precios mayo 2026, redondeados)

| Modelo | $/1M tokens IN | $/1M OUT | Calidad | Velocidad |
|--------|---------------|----------|---------|-----------|
| Gemini 1.5 Flash | 0.075 | 0.30 | ⭐⭐⭐ | Muy rápido |
| **Gemini 2.5 Flash** *(actual gratuito)* | 0.10 | 0.40 | ⭐⭐⭐⭐ | Rápido |
| Gemini 2.5 Pro | 1.25 | 10.00 | ⭐⭐⭐⭐⭐ | Medio |
| GPT-4o-mini | 0.15 | 0.60 | ⭐⭐⭐⭐ | Rápido |
| Claude Haiku 4.5 | 1.00 | 5.00 | ⭐⭐⭐⭐ | Rápido |
| Claude Sonnet 4.7 | 3.00 | 15.00 | ⭐⭐⭐⭐⭐ | Medio |

### Lo que consume el bot de datos al mes (estimación realista)
- 50-100 consultas/día desde el cuerpo técnico (8 personas × ~10/día).
- Cada consulta: prompt ~3000 tokens IN + 800 tokens OUT (con tools).
- Mensualmente: ~3.000-6.000 consultas → ~10-20 M tokens IN, ~3-5 M OUT.

**Coste estimado al mes**:
- Gemini 2.5 Flash (actual, plan gratis cuando entra en cuota free): **0 €**
  pero sufrimos a veces "límite alcanzado" si pico de uso. Plan paid:
  ~3-6 €/mes.
- GPT-4o-mini: ~5-9 €/mes.
- Claude Haiku: ~25-40 €/mes.
- Claude Sonnet: ~100-150 €/mes — overkill para esto, NO recomiendo.

### Latencia real medida
- Gemini 2.5 Flash: 2-4 s por consulta (con 1-2 tool calls).
- Claude Haiku 4.5: 2-3 s por consulta. Mejor razonamiento → menos
  iteraciones → a veces total más rápido.
- GPT-4o-mini: 1.5-3 s.

### Mi recomendación
- **Quedarse con Gemini 2.5 Flash + plan paid** (no gratis) para que
  no se corte: **~5-10 €/mes**. Activar billing en la cuenta Google
  Cloud y poner un cap de gasto a 15 €/mes para evitar sustos.
- Alternativa: **GPT-4o-mini** (~5-9 €/mes), comparable.
- Para Alfred (el bot personal de Arkaitz que es Claude full): sigue
  con tu suscripción Claude Code Max (200 $/mes pero la usas tú para
  TODO, no es coste imputable al equipo).

---

## Pieza 3 — Servidor 24/7

### Hoy
- Mac viejo en oficina, encendido 24/7. Corre Alfred + bot de datos +
  auto-pull cada 5 min. Cuesta 0 €/mes pero:
  - Si falla la luz o el Mac muere → bots caídos hasta que alguien lo
    reinicie.
  - Es un Mac viejo: si se rompe el disco, perdemos sesiones de
    WhatsApp del bot, credenciales locales, etc.

### Opciones para subir a la nube
1. **Hetzner CX22 (Alemania, 4 GB RAM, 2 vCPU)** — 4 €/mes
   - Linux. Necesita migrar los launchd → systemd.
   - Tiempo de setup: 2-3 horas yo, después estable.
2. **DigitalOcean / Linode similar** — 6-10 €/mes
   - Más caro, soporte algo mejor.
3. **Servicios "managed"** (Render, Railway) — 5-15 €/mes por bot
   - No tienes que tocar nada de servidor. Para 2 bots: ~10-20 €/mes.

### Mi recomendación
- **Hetzner CX22 · 4 €/mes** si quieres mover los bots a la nube.
  Mejora la disponibilidad un montón. Migración yo la hago en una
  sesión.
- **Mantener el Mac actual** si el bot raramente se cae. Hoy día está
  bien aguantando.

---

## Propuestas finales

### Plan barato — 20 €/mes
- Streamlit Cloud Pro (~25 €/mes).
- Bots como ahora (Gemini Flash gratis).
- Server: Mac actual.
- Resultado: **panel sin sleep**, todo lo demás igual.

### Plan recomendado — 45 €/mes  ⭐
- Streamlit Cloud Pro (~25 €).
- Gemini Flash paid con cap (~10 €).
- Hetzner CX22 para bots (~4 €).
- Margen para imprevistos (~6 €).
- Resultado: **panel rápido y siempre vivo · bots sin cortes por cuota
  · servidor redundante**.

### Plan premium — 120 €/mes
- Streamlit Cloud Pro (~25 €).
- Claude Haiku para bot de datos (~40 €).
- Hetzner CX22 (~4 €).
- Soporte / monitorización (UptimeRobot Pro, Sentry) (~30 €).
- Margen (~20 €).
- Resultado: respuestas de bot un punto más profundas (mejor
  razonamiento de Claude vs Gemini), pero el cuerpo técnico **no
  notará la diferencia** vs el plan recomendado. **No vale la pena
  salvo capricho**.

---

## Lo que NO te recomiendo aunque te lo pidan

- **Pasarse a Anthropic Sonnet** para el bot de datos. Es overkill,
  costaría ~150 €/mes y la mejora frente a Gemini Flash es marginal
  para preguntas tipo "¿cómo va Cecilio esta semana?".
- **Contratar un PaaS tipo Heroku** para hostear todo. Eran 30-50 €/mes
  por dyno y se duplica el coste sin mejora.
- **Comprar un Mac mini nuevo solo para servidor**. 800 € + electricidad
  + ruido oficina. La nube es mejor opción.

---

## Mi consejo si tienes que decidir mañana

Pide **45 €/mes** (~540 €/año) y queda repartido en:
- 25 €/mes Streamlit Cloud Pro.
- 10 €/mes Gemini API (con cap).
- 4 €/mes Hetzner CX22.
- 6 €/mes colchón para SSL, dominios, herramientas pequeñas.

Eso te da una infra robusta, sin sustos, y deja margen para crecer
sin renegociar presupuesto si el año que viene queremos más jugadores
o más datos.
