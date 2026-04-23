# 📊 Bot de Datos — @InterFS_datos_bot

Bot de Telegram para consultar datos del equipo (pesos, carga, wellness, lesiones, asistencia) sin tocar código. Pensado para **cuerpo técnico y, más adelante, jugadores**.

Este bot es **solo lectura**: no modifica nada. Para tareas de desarrollo (fixes, commits, cambios en el dashboard) usa el otro bot **@InterFS_bot**.

---

## 🆚 Diferencias con el otro bot

| | **@InterFS_bot** | **@InterFS_datos_bot** (éste) |
|---|---|---|
| Para quién | Solo Arkaitz | Cuerpo técnico (lista configurable) |
| Qué hace | Dev: código, commits, arreglos | Solo consultas de datos |
| Permisos | Full | Solo lectura |

---

## 🔑 Puesta en marcha (primera vez, 10 min)

### Paso 1 · Crear el bot en Telegram

Esto solo lo haces UNA VEZ:

1. Abre Telegram en el móvil.
2. Busca `@BotFather` (el oficial, con tic azul).
3. Escribe `/newbot`.
4. Te pedirá un **nombre** (lo que verán los usuarios) → pon algo como `Arkaitz · Datos equipo`.
5. Te pedirá un **username** → debe acabar en `_bot` → pon `InterFS_datos_bot` (si está libre) o similar.
6. Te dará un **token** largo, tipo `7123456789:AAG...`. **Cópialo**, lo necesitas en el paso 2.

### Paso 2 · Pegar el token

Abre `telegram_bot_datos/.env` con TextEdit y pega el token:

```
TELEGRAM_BOT_TOKEN=7123456789:AAGLorem_ipsum_dolor_sit_amet
ALLOWED_CHAT_IDS=
```

### Paso 3 · Tu chat_id en la lista de autorizados

Tu chat_id ya lo sabes (el mismo que usas en el otro bot: `6357476517`). Pégalo:

```
TELEGRAM_BOT_TOKEN=7123456789:AAGLorem_ipsum_dolor_sit_amet
ALLOWED_CHAT_IDS=6357476517
```

Guarda el archivo.

### Paso 4 · Arrancar el bot

En **otra ventana de Terminal** (distinta a la del bot @InterFS_bot):

```bash
cd ~/Desktop/Arkaitz/telegram_bot_datos && ./iniciar.sh
```

Verás:

```
🤖 Arrancando bot de DATOS (@InterFS_datos_bot)…
09:20:00 [INFO] Claude: /Users/mac/Library/...
09:20:00 [INFO] Proyecto: /Users/mac/Desktop/Arkaitz
09:20:00 [INFO] Autorizados: [6357476517]
09:20:00 [INFO] Bot de DATOS arrancado. Ctrl+C para parar.
```

### Paso 5 · Probar

Desde Telegram, busca `@InterFS_datos_bot` (o el username que elegiste) y escríbele:

- `/start` → mensaje de bienvenida
- `¿cuánto peso perdió Carlos ayer?` → consulta real

---

## 👥 Cómo añadir más personas después

Cuando quieras dar acceso a alguien (entrenador, jugador, fisio…):

### Paso A · Esa persona te pasa su chat_id

Le dices: *"Escribe a @userinfobot en Telegram. Te dará un número. Envíamelo."*

(Alternativa: que le escriba a `@InterFS_datos_bot` y use el comando `/yo`. El bot le dirá su chat_id sin darle acceso.)

### Paso B · Tú añades el chat_id a tu `.env`

Edita `telegram_bot_datos/.env` y añade el nuevo chat_id separado por coma:

```
ALLOWED_CHAT_IDS=6357476517, 111222333, 444555666
```

Guarda.

### Paso C · Reinicia el bot

En la terminal del bot de datos: `Ctrl+C` para pararlo, y:

```bash
./iniciar.sh
```

(Solo ese bot, no hace falta tocar el otro.)

Ya está: esa persona puede hablar con el bot. Los demás siguen funcionando igual.

### Para QUITAR acceso

Borra el chat_id de `ALLOWED_CHAT_IDS` y reinicia el bot.

---

## 💬 Qué le puedes preguntar

Ejemplos reales, en lenguaje natural:

**Pesos:**
- «¿cuánto peso perdió Carlos el último día?»
- «¿qué jugadores tuvieron más pérdida de peso esta semana?»
- «dame la evolución del peso de Barona las últimas 4 semanas»

**Carga:**
- «¿qué ACWR tiene Gonzalo ahora?»
- «¿quién tiene sobrecarga esta semana?»
- «dame la carga semanal del equipo»

**Wellness:**
- «¿cómo está el equipo de ánimo estos días?»
- «¿quién tiene wellness bajo (<13) ahora?»
- «dame la media de sueño de Raya las últimas 7 sesiones»

**Lesiones / asistencia:**
- «¿cuántas sesiones se ha perdido Oscar?»
- «¿qué jugadores han faltado esta semana por lesión?»

El bot entiende el contexto: si preguntas por Carlos y luego dices «¿y Pirata?», se entiende.

---

## 🎛 Comandos útiles

| Comando | Qué hace |
|---|---|
| `/start` | Saludo + ejemplos |
| `/yo` | Te dice tu chat_id (útil para pedir acceso) |
| `/nuevo` | Empezar una conversación nueva (olvida el contexto) |

---

## 🆘 Problemas

### "Falta ALLOWED_CHAT_IDS en .env"

No pusiste tu chat_id. Vuelve al paso 3.

### El bot dice "🚫 Acceso denegado"

Tu chat_id no coincide con los autorizados. Comprueba tu `.env` y reinicia el bot.

### El bot no responde nada / se queda colgado

- Puede tardar hasta 10 min en consultas pesadas (mientras ejecuta scripts). Paciencia.
- Si pasan más de 10 min, te dice "Timeout". Reformula la pregunta más concreta.

### "Conflict: terminated by other getUpdates request"

Ya tienes otra copia de ESTE mismo bot arrancada. Para todas:

```bash
pkill -f "python bot_datos.py"
```

Y arranca de nuevo.

### Los dos bots pueden correr a la vez

Sí. Tienen tokens distintos y procesos distintos. Dos ventanas de Terminal, cada una con su `./iniciar.sh`. Lo normal es arrancar ambos al empezar el día:

```bash
# Terminal 1 (dev):
cd ~/Desktop/Arkaitz/telegram_bot && ./iniciar.sh

# Terminal 2 (datos):
cd ~/Desktop/Arkaitz/telegram_bot_datos && ./iniciar.sh
```

---

## 🔒 Qué hay en cada archivo

| Archivo | Qué es |
|---|---|
| `bot_datos.py` | El programa del bot |
| `.env` | **Tus** secretos (token + lista de autorizados) |
| `.env.example` | Plantilla del `.env` (sin secretos) |
| `requirements.txt` | Dependencias Python |
| `iniciar.sh` | Arranque con un comando |
| `.gitignore` | Bloquea `.env` y `sesiones/` de git |
| `sesiones/` | Historial de cada usuario (no tocar) |
| `venv/` | Entorno virtual (no tocar) |
| `LEEME.md` | Este manual |

---

## 🧠 Por qué tengo que reiniciar cada vez que añado a alguien

Porque la lista de autorizados se lee al arrancar. Para no leerla cada mensaje (más eficiente). Es una limitación aceptable: mientras no añadas gente nueva, no necesitas reiniciarlo.

Si en algún momento añades gente a menudo y te molesta reiniciar, dímelo y lo cambio para que recargue en caliente.
