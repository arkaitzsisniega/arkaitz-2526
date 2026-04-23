# 🤖 Bot de Telegram — Arkaitz 25/26

Este bot te permite hablar con **Claude Code** desde tu móvil a través de Telegram. Escribes una pregunta o petición al bot y él se la pasa a Claude, que tiene acceso completo al proyecto (dashboard, datos, código, git…). Claude te contesta y el bot te reenvía la respuesta.

Todo corre en **tu Mac**. Mientras tu Mac esté encendida y el bot esté arrancado, funciona.

---

## 🔑 Lo que necesitas tener a mano

1. Un **bot de Telegram creado** (@InterFS_bot, según me dijiste ✅).
2. **El token** de ese bot. Si no lo apuntaste, abre Telegram → busca `@BotFather` → escribe `/mybots` → elige tu bot → "API Token". Es un texto largo tipo `7123456789:AAGaLorem...`.
3. **Tu chat_id de Telegram** (lo sacas en 10 segundos, ver paso 2 más abajo).

---

## 🚀 Puesta en marcha (una única vez)

### Paso 1 · Pega el token del bot

Abre el archivo `telegram_bot/.env` con TextEdit (o cualquier editor) y pega el token justo después del `=`:

```
TELEGRAM_BOT_TOKEN=7123456789:AAGaLorem_ipsum_dolor_sit_amet_12345
ALLOWED_CHAT_ID=
```

Guarda el archivo. **Todavía no pongas nada en `ALLOWED_CHAT_ID`**, vamos a averiguarlo ahora.

### Paso 2 · Averigua tu chat_id

Abre Telegram en tu móvil y:

1. Busca el contacto `@userinfobot` (tiene un tic azul de verificación).
2. Escríbele `/start` (o cualquier cosa).
3. Te responde con tus datos. Copia el número que aparece en **"Id"** (algo tipo `123456789`).

O, alternativamente, una vez arrancado el bot (paso 4) puedes escribirle `/id` a tu propio bot y te lo dirá.

### Paso 3 · Pega tu chat_id

Abre otra vez `telegram_bot/.env` y pega ese número:

```
TELEGRAM_BOT_TOKEN=7123456789:AAGaLorem_ipsum_dolor_sit_amet_12345
ALLOWED_CHAT_ID=123456789
```

Guarda.

### Paso 4 · Arranca el bot

Abre la app **Terminal** (⌘+Espacio → "Terminal") y pega este comando (una sola línea):

```bash
cd ~/Desktop/Arkaitz/telegram_bot && ./iniciar.sh
```

Si todo va bien, verás algo así:

```
🤖 Arrancando bot de Telegram…
   (Ctrl+C para parar)

12:34:56 [INFO] Claude encontrado en: /Users/mac/Library/...
12:34:56 [INFO] Proyecto: /Users/mac/Desktop/Arkaitz
12:34:56 [INFO] Autorizado chat_id: 123456789
12:34:56 [INFO] Bot arrancado. Escuchando mensajes… (Ctrl+C para parar)
```

🎉 **Ya puedes escribirle al bot desde Telegram**. Empieza con `/start` para saludar.

---

## ▶️ Uso diario

### Arrancar el bot

Abre Terminal y pega:

```bash
cd ~/Desktop/Arkaitz/telegram_bot && ./iniciar.sh
```

### Parar el bot

En la misma ventana de Terminal, pulsa `Ctrl+C`.

### Mientras el bot está corriendo

- **Deja la ventana de Terminal abierta**. Si la cierras, el bot se para.
- Puedes minimizarla, no molesta.
- Si tu Mac se duerme, el bot deja de responder. Al despertarla, vuelve a funcionar (puede tardar unos segundos en reconectar).

---

## 💬 Qué cosas puedes pedirle

Escribe al bot desde Telegram como si me hablaras a mí. Ejemplos reales:

- «¿qué tal la carga de Carlos esta última semana?»
- «dame los tres jugadores con más alerta roja ahora mismo»
- «revisa el dashboard/app.py y dime si hay algún error evidente»
- «haz un commit con los cambios actuales»
- «qué lesiones hay activas»
- «cuáles son las tres sesiones con más pérdida de peso esta semana»

El bot puede tardar de **10 segundos a varios minutos** según la petición. Verás "escribiendo…" mientras trabaja.

### 🎤 Mensajes de voz

Puedes mandar audios en vez de texto. El bot los transcribe localmente con Whisper (la voz no sale de tu Mac), te muestra qué entendió y procesa la petición. La primera vez descarga un modelo de ~150 MB (una sola vez).

### 🧠 Memoria de conversación

El bot **mantiene el hilo** entre mensajes: si pregunta algo y le respondes "sí", "hazlo", "dame más detalle"… se acuerda de qué hablabais. Es como una conversación normal.

Comandos útiles:
- **`/nuevo`** — empezar una conversación nueva, olvidando el contexto anterior. Úsalo cuando cambies totalmente de tema o quieras "borrar la pizarra".
- **`/id`** — ver tu chat_id (solo útil si te lías con la configuración).
- **`/start`** — saludo y pistas de uso.

**Tip**: si haces muchas preguntas sobre un mismo tema, mejor hazlo en una sola conversación sin `/nuevo`. Si empiezas algo totalmente distinto, pulsa `/nuevo` primero para no confundirlo.

---

## 🆘 Qué hacer si deja de funcionar

### Problema: el bot dice "❌ Acceso denegado" cuando le escribo

Tu `ALLOWED_CHAT_ID` en `.env` no coincide con tu chat_id real. Vuelve al paso 2 y revísalo.

### Problema: en Terminal sale "No encuentro el ejecutable de Claude Code"

Significa que Claude Desktop se ha desinstalado, movido o aún no estaba abierto. Abre Claude Desktop al menos una vez y vuelve a arrancar el bot.

Si aún falla, abre `.env` y añade esta línea al final (ajustando la versión si cambia con una actualización):

```
CLAUDE_BIN=/Users/mac/Library/Application Support/Claude/claude-code/2.1.111/claude.app/Contents/MacOS/claude
```

### Problema: "Claude devolvió error (código X)"

Es Claude el que ha fallado, no el bot. Mira el mensaje de error que aparece debajo. Puede ser:
- un timeout (tarea demasiado larga) → súbelo en `.env` con `CLAUDE_TIMEOUT=1200` (20 min).
- un problema con tu cuenta de Claude (raro).
- permisos que Claude pide y no hay nadie delante para confirmar → reformula la petición para que sea más acotada.

### Problema: la Terminal se ha cerrado sola / el Mac se ha reiniciado

El bot se para cuando la Terminal se cierra. Simplemente vuelve a abrir Terminal y pega el comando del arranque.

### Problema: "Conflict: terminated by other getUpdates request"

Ya tienes OTRA instancia del bot corriendo (en otra ventana o en segundo plano). Ciérralas todas antes de arrancar de nuevo. Para matar todas:

```bash
pkill -f "python bot.py"
```

Y arranca de nuevo.

---

## 🔒 Seguridad

- El archivo `.env` **nunca** se sube a git (lo bloquea `.gitignore`).
- Solo responde a tu `chat_id`. Cualquier otra persona que encuentre el bot recibirá "Acceso denegado".
- Si sospechas que alguien tiene tu token del bot, ve a `@BotFather` → `/revoke` y genera uno nuevo.

---

## 🛠 Archivos de esta carpeta

| Archivo | Qué es |
|---|---|
| `bot.py` | El programa del bot. No suele tocarse. |
| `.env` | **Tus** secretos (token + chat_id). Secreto. |
| `.env.example` | Plantilla del `.env`, sí se sube a git. |
| `requirements.txt` | Lista de librerías Python que usa el bot. |
| `iniciar.sh` | Script que arranca el bot con un solo comando. |
| `.gitignore` | Lista de cosas que git debe ignorar. |
| `venv/` | Entorno virtual Python (no tocar, no se sube a git). |
| `LEEME.md` | Este manual. |
