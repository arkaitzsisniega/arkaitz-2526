# 🚀 Pasos para activar bot dev + gastos_bot en el Mac viejo

Cuando vuelvas, sigue esta guía **paso a paso**. Cada bloque es un pegote
en el SSH del Mac viejo. Tiempo total ~20-30 min (la mayoría espera).

---

## 0. Prerequisitos (verificación)

```bash
ssh arkaitz@10.48.0.113
```

Si pide contraseña, la pones. Una vez dentro:

```bash
launchctl list | grep arkaitz 2>/dev/null  # debería estar vacío (ya no usamos launchd)
ps aux | grep bot_datos.py | grep -v grep   # debería listar el bot_datos corriendo
```

Si bot_datos no está corriendo, primero arregla eso:
```bash
cd ~/Desktop/Arkaitz/telegram_bot_datos
nohup ./venv/bin/python bot_datos.py >> ~/Desktop/Arkaitz/logs/bot_datos.log 2>&1 &
disown
```

---

## 1. Pull el código nuevo

```bash
cd ~/Desktop/Arkaitz
git pull
git log --oneline -3
```

Deberías ver arriba commits `docs: arquitectura nueva del servidor 24/7...` y
`bots: migra dev y gastos a Gemini, anade watchdog comun`.

---

## 2. Añadir `GEMINI_API_KEY` a los 2 .env que faltan

El `.env` de `telegram_bot_datos` ya tiene la key. Falta en los otros dos:

### Bot dev (telegram_bot/.env)

```bash
nano ~/Desktop/Arkaitz/telegram_bot/.env
```

Al final del archivo (línea nueva):
```
GEMINI_API_KEY=AIza...tu_key_completa...
GEMINI_MODEL=gemini-2.5-flash-lite
```

(Usa la **misma key** que ya tienes en bot_datos. Funciona para los 3 bots.)

`Ctrl+O`, Enter, `Ctrl+X`.

### Gastos bot (gastos_bot/.env)

```bash
nano ~/Desktop/Arkaitz/gastos_bot/.env
```

Al final, igual:
```
GEMINI_API_KEY=AIza...tu_key_completa...
GEMINI_MODEL=gemini-2.5-flash-lite
```

`Ctrl+O`, Enter, `Ctrl+X`.

---

## 3. Instalar dependencias Python nuevas en los 2 venvs

### Bot dev

```bash
cd ~/Desktop/Arkaitz/telegram_bot
./venv/bin/pip install google-generativeai gspread pandas openpyxl google-auth
```

⏱ ~3-5 min. Cuando vuelva el prompt, sigue.

### Gastos bot

```bash
cd ~/Desktop/Arkaitz/gastos_bot
./venv/bin/pip install --upgrade pip
./venv/bin/pip install google-generativeai gspread google-auth python-dotenv python-telegram-bot faster-whisper
```

⏱ Más lento la primera vez (5-15 min) si compila Whisper otra vez.

---

## 4. Probar arrancar el bot dev manualmente

```bash
cd ~/Desktop/Arkaitz/telegram_bot
./venv/bin/python bot.py
```

Verás:
```
[INFO] Backend LLM: Gemini (gemini-2.5-flash-lite)
[INFO] Proyecto: /Users/arkaitz/Desktop/Arkaitz
[INFO] Autorizado chat_id: 6357476517
[INFO] Bot arrancado (voz: ON). Escuchando mensajes...
[INFO] Application started
```

**Desde el móvil**, manda al bot dev `@InterFS_bot` un mensaje:
> "hola, ¿estás vivo?"

Si responde algo, va bien.

Para probar tools: `/nuevo` y luego "léeme la primera línea del CLAUDE.md".
Si invoca `read_file` y devuelve contenido, las tools funcionan.

`Ctrl+C` para parar el bot manual cuando hayas terminado de probar.

---

## 5. Probar arrancar el gastos_bot manualmente

```bash
cd ~/Desktop/Arkaitz/gastos_bot
./venv/bin/python bot.py
```

Verás líneas similares de arranque.

Manda al `@GastosComunes_ArkaitzLis_bot` algo como:
> "12 euros en el mercado"

Debería apuntarlo. `Ctrl+C` para parar.

---

## 6. Configurar cron @reboot para los 3 bots + watchdog

El `bot_datos` ya tiene su `@reboot` puesto. Vamos a sumar los otros 2 + el
watchdog que comprueba cada minuto si los bots viven.

```bash
(crontab -l 2>/dev/null | grep -v -E 'bot_datos.py|telegram_bot/bot.py|gastos_bot/bot.py|watchdog.sh'
echo '@reboot sleep 30 && cd ~/Desktop/Arkaitz/telegram_bot_datos && nohup ./venv/bin/python bot_datos.py >> ~/Desktop/Arkaitz/logs/bot_datos.log 2>&1'
echo '@reboot sleep 35 && cd ~/Desktop/Arkaitz/telegram_bot && nohup ./venv/bin/python bot.py >> ~/Desktop/Arkaitz/logs/bot.log 2>&1'
echo '@reboot sleep 40 && cd ~/Desktop/Arkaitz/gastos_bot && nohup ./venv/bin/python bot.py >> ~/Desktop/Arkaitz/logs/gastos_bot.log 2>&1'
echo '* * * * * /Users/arkaitz/Desktop/Arkaitz/setup_servidor/watchdog.sh >> ~/Desktop/Arkaitz/logs/watchdog.log 2>&1'
) | crontab -
```

Verifica:
```bash
crontab -l
```

Tienes que ver 4 líneas (3 @reboot + 1 watchdog). Pega la salida si quieres
que la verifique.

---

## 7. Lanzar los bots dev y gastos AHORA (sin esperar a reiniciar)

```bash
cd ~/Desktop/Arkaitz/telegram_bot
nohup ./venv/bin/python bot.py >> ~/Desktop/Arkaitz/logs/bot.log 2>&1 &
disown

cd ~/Desktop/Arkaitz/gastos_bot
nohup ./venv/bin/python bot.py >> ~/Desktop/Arkaitz/logs/gastos_bot.log 2>&1 &
disown

sleep 5
ps aux | grep -E "bot.py|bot_datos.py" | grep -v grep
```

Deberías ver **3 procesos Python**, uno por cada bot.

---

## 8. Cierra Terminal y prueba todo desde el móvil

Cierra la sesión SSH y la app Terminal. Desde el móvil:

- `@InterFS_bot` (dev) → "hola, ¿qué tal?"
- `@InterFS_datos_bot` → "¿cuántas filas tiene la hoja BORG?"
- `@GastosComunes_ArkaitzLis_bot` → "5 euros en café"

Si los 3 responden → 🎉 servidor 24/7 con los 3 bots funcionando.

---

## 9. Apaga el portátil de oficina

Cuando confirmes que va todo, ya puedes apagar el portátil. El Mac viejo
sigue solo.

---

## ⚠️ Si algo va mal

```bash
# Ver el log del bot que falla:
tail -50 ~/Desktop/Arkaitz/logs/bot.log         # bot dev
tail -50 ~/Desktop/Arkaitz/logs/bot_datos.log   # bot datos
tail -50 ~/Desktop/Arkaitz/logs/gastos_bot.log  # gastos
tail -50 ~/Desktop/Arkaitz/logs/watchdog.log    # watchdog

# Ver qué procesos Python corren:
ps aux | grep bot.py | grep -v grep

# Matar un bot (el watchdog lo relanzará en <1 min):
pkill -f telegram_bot/bot.py
pkill -f telegram_bot_datos/bot_datos.py
pkill -f gastos_bot/bot.py
```

---

## 📊 Resumen de la arquitectura final

| Bot | Telegram | Modelo Gemini | Tools | Quién lo usa |
|---|---|---|---|---|
| dev | @InterFS_bot | Flash-Lite | python+bash+read+write+edit | Solo Arkaitz |
| datos | @InterFS_datos_bot | Flash-Lite | python+bash+read | Cuerpo técnico (5) |
| gastos | @GastosComunes_ArkaitzLis_bot | Flash-Lite (clasificador JSON) | — | Arkaitz + Lis |

Coste total: **0€/mes** (todo dentro del free tier de Gemini, ~1500 req/día por bot).
