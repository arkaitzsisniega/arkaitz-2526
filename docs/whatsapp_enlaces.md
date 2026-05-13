# Envío de enlaces de Forms por WhatsApp — `/enlaces_wa`

Resumen para Arkaitz de cómo se manda el bloque PRE+POST personalizado a
cada jugador por WhatsApp.

## Lo que existe ahora (operativo, sin coste, sin permisos)

Comando del bot Alfred: **`/enlaces_wa`** (también responde a frases tipo
*"enlaces para los jugadores"*, *"enlaces wa.me"*, *"manda los enlaces a
cada jugador por whatsapp"*).

### Qué hace, paso a paso

1. Lee la hoja **`TELEFONOS_JUGADORES`** del Sheet (creada
   automáticamente). Allí están los 22 jugadores activos del roster con
   columnas: `dorsal`, `jugador`, `telefono`, `usar_whatsapp`, `notas`.
2. Lee la sesión (o las dos sesiones) de hoy de `SESIONES`.
3. Para cada jugador con teléfono válido y `usar_whatsapp` distinto de
   `FALSE`, genera un enlace `https://wa.me/<tel>?text=<mensaje>` donde el
   mensaje ya contiene:
   - Saludo "¡Hola NOMBRE!"
   - Enlace al Form PRE con su nombre + fecha + turno pre-rellenados.
   - Enlace al Form POST con su nombre + fecha + turno pre-rellenados.
   - Aviso si es la 2ª sesión del día (sin wellness).
4. Devuelve por Telegram un mensaje con un enlace `wa.me` por jugador.
5. **Tú pulsas cada enlace** → se abre WhatsApp con el chat del jugador y
   el mensaje ya escrito → solo le das a **Enviar**.

### Lo que tienes que hacer UNA VEZ

1. Abre el Sheet → pestaña **`TELEFONOS_JUGADORES`**.
2. En la columna `telefono` de cada jugador, mete su número. Admite
   formatos varios:
   - `612345678` (móvil español, se le añade el 34 automáticamente)
   - `34612345678`
   - `+34 612 345 678` (con espacios o guiones, da igual)
3. Si por lo que sea NO quieres que algún jugador reciba el WhatsApp
   automáticamente (lesionado, recién fichado, etc.), pon `FALSE` en
   `usar_whatsapp`. Por defecto está en `TRUE`.

A partir de ahí, cada día (o el día que toque entreno) basta con
`/enlaces_wa` en Alfred.

### Ejemplo de salida en Telegram

```
📲 Enlaces WhatsApp · 2026-05-14
Sesiones: 1 · Jugadores con teléfono: 22
Pulsa cada enlace de abajo y dale a *Enviar* en WhatsApp.

📌 Sesión 1/1 · turno M
🧠 Incluye wellness

#1 HERRERO
📲 https://wa.me/34612345678?text=¡Hola%20HERRERO%21...

#2 CECILIO
📲 https://wa.me/34611111111?text=...

(etc, 22 enlaces)

✅ Listo. Cada enlace abre WhatsApp con el chat y el mensaje preparado.
   Solo te falta darle a *Enviar*.
```

### Caveats

- **Necesita 1 tap por jugador**: no es 100% automático. Para 22
  jugadores son 22 taps al día. Mejor que copiar/pegar, pero no
  "se manda solo".
- **El jugador tiene que tener tu número guardado** para que el chat se
  abra como un chat normal en WhatsApp.
- **No funciona en grupos**, solo en chats individuales.

## Si en el futuro quieres envío 100% automático

Hay tres caminos posibles. Mi recomendación: empezar con `/enlaces_wa` y
si los 22 taps al día siguen siendo demasiado, pasar a una de estas:

### Opción A — WhatsApp Business Cloud API (oficial Meta) — RECOMENDADA si se decide

- **Coste**: gratis los primeros 1000 mensajes de "servicio" al mes
  (con conversaciones iniciadas por usuario) y unos €0,05 por mensaje
  "utilidad" iniciado por nosotros. 22 jugadores × 4 entrenos × 4 semanas
  = ~350/mes ≈ €18/mes.
- **Setup**: 1 a 2 semanas (Meta Business Manager + verificación + número
  dedicado + templates aprobados).
- **Pros**: oficial, sin riesgo de baneo, mensajes "templates" se mandan
  solos al pulsar un botón.

### Opción B — whatsapp-web.js / pywhatkit (no oficial)

- **Coste**: 0 €.
- **Setup**: Bot en el servidor que mantiene una sesión de WhatsApp Web
  abierta con un escaneo de QR inicial.
- **Pros**: gratis, automático, código abierto.
- **Contras**: Meta puede banear el número si detecta automatización.
  Con 22 mensajes/día es muy bajo y poco probable, pero existe el riesgo.
- **Sería un cambio importante**: el bot pasa de "genera wa.me y tú envías"
  a "tú lanzas /enviar_wa y el server envía solo". Una sola configuración
  inicial y luego cero clicks.

### Opción C — bot de Telegram para los jugadores

- Si los jugadores estuvieran abiertos a usar Telegram en vez de WhatsApp,
  esto sería trivial: un bot que les manda los enlaces automáticamente sin
  setup.
- Pero implica que los 22 jugadores se instalen Telegram. No realista en
  un cuerpo de fútbol sala.

## Estado actual

- ✅ `/enlaces_wa` operativo en Alfred (auto-pull en server lo coge en 5
  min tras este push).
- ✅ Hoja `TELEFONOS_JUGADORES` creada con los 22 jugadores activos
  pre-listados. **Falta que rellenes los teléfonos.**
- ✅ Script `src/enlaces_wa.py` normaliza formatos varios de teléfono.
- ✅ Mensajes en español, con saludo, enlaces y aviso de doble sesión.

## TL;DR para empezar a usarlo

1. Abre Sheet → `TELEFONOS_JUGADORES`.
2. Rellena la columna `telefono` con el móvil de cada jugador.
3. Al día siguiente, en Alfred: `/enlaces_wa` o "manda los enlaces a los
   jugadores por whatsapp".
4. Pulsa los 22 enlaces uno a uno → "Enviar" en cada uno.
