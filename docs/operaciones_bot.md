# 🛠 Manual operacional del bot Inter FS

> Documento de referencia rápida cuando algo del bot falla. Resume la
> arquitectura, cómo está montado, y los procedimientos típicos.
> Actualizado: **12 mayo 2026** (tras sesión maratoniana de fixes).

---

## 🧭 Arquitectura en 30 segundos

```
                    ┌───────────────────────┐
                    │  Mac viejo servidor   │
                    │  (user: arkaitz)      │
                    │                       │
   Telegram ───────►│  ┌─────────────────┐  │
                    │  │ @InterFS_bot    │  │ ← Alfred (dev/personal Arkaitz)
                    │  └─────────────────┘  │
   Telegram ───────►│  ┌─────────────────┐  │
                    │  │ @InterFS_datos  │  │ ← cuerpo técnico (read-only)
                    │  └─────────────────┘  │
                    │  ┌─────────────────┐  │
                    │  │ @Gastos comunes │  │ ← gastos personales
                    │  └─────────────────┘  │
                    │                       │
                    │   launchd KeepAlive   │
                    │   auto_pull (5 min)   │
                    │   healthcheck (1 h)   │
                    └───────────┬───────────┘
                                │ gspread
                    ┌───────────▼───────────┐
                    │  Google Sheet         │
                    │  "Arkaitz 2526"       │
                    └───────────────────────┘
```

- **3 bots Telegram**, cada uno con su propio venv Python 3.11 + .env.
- **launchd** los mantiene vivos (`KeepAlive=true` + `ThrottleInterval=30s`).
- **auto_pull** (cada 5 min): hace `git pull` y, si hay commits nuevos, reinicia los bots con `launchctl kickstart`. Notifica por Telegram al chat autorizado.
- **healthcheck** (cada hora): verifica Sheet/Whisper/Gemini/scripts curados. Si algo falla, notifica por Telegram.
- **Scripts curados** en `src/` (estado_jugador, parse_*, apuntar_*, etc.). El bot delega aquí siempre que puede, así no depende del razonamiento de Gemini para tareas críticas.

---

## 🚀 Cómo se arranca / se actualiza todo

### Instalación inicial (una sola vez en el server)

```bash
cd ~/Desktop/Arkaitz
./setup_servidor/install.sh
```

Eso:
1. Genera los 3 `.plist` de los bots con tus paths reales.
2. Genera los `.plist` de `auto_pull` y `healthcheck`.
3. Hace `launchctl load -w` de los 5 LaunchAgents.

Resultado: los bots arrancan al iniciar sesión y se auto-actualizan cada 5 min.

### Desinstalar / parar todo

```bash
./setup_servidor/uninstall.sh
```

### Reiniciar manualmente un bot

```bash
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot         # Alfred
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos   # Datos
launchctl kickstart -k gui/$(id -u)/com.arkaitz.gastos_bot  # Gastos
```

(No suele hacer falta: `auto_pull` ya los reinicia al detectar commits nuevos.)

### Forzar un git pull manual

```bash
~/Desktop/Arkaitz/setup_servidor/auto_pull.sh
```

(Acción puntual; el script no espera al cron.)

---

## 🔍 Diagnóstico rápido cuando algo va mal

### "El bot no responde"

```bash
# 1. ¿Están vivos los procesos?
ps aux | grep -E "bot\.py|bot_datos" | grep -v grep

# 2. ¿launchctl los conoce?
launchctl list | grep arkaitz

# 3. ¿Qué dice el log más reciente?
tail -50 ~/Desktop/Arkaitz/logs/bot.err.log
tail -50 ~/Desktop/Arkaitz/logs/bot_datos.err.log

# 4. ¿Health check global?
~/Desktop/Arkaitz/telegram_bot/venv/bin/python ~/Desktop/Arkaitz/src/health_check.py
```

### "Está corriendo código viejo"

```bash
git -C ~/Desktop/Arkaitz log --oneline -3
# Si el commit no es el último de origin, pull manual:
~/Desktop/Arkaitz/setup_servidor/auto_pull.sh
```

### "Conflict 409 / dos instancias"

Indica que hay otro proceso usando el mismo bot token. Casi siempre es un proceso huérfano del Mac de oficina.

```bash
# En cada Mac, matar instancias:
launchctl unload ~/Library/LaunchAgents/com.arkaitz.bot.plist
launchctl unload ~/Library/LaunchAgents/com.arkaitz.bot_datos.plist
sleep 3
launchctl load -w ~/Library/LaunchAgents/com.arkaitz.bot.plist
launchctl load -w ~/Library/LaunchAgents/com.arkaitz.bot_datos.plist
```

El bot debe correr en **un solo sitio** (típicamente el server). Si trabajas en local, para los del server primero.

### "Audio mudo / Whisper no responde"

Suele ser `numpy 2.x` vs `onnxruntime`. Fix:

```bash
~/Desktop/Arkaitz/telegram_bot/venv/bin/pip install "numpy<2"
~/Desktop/Arkaitz/telegram_bot_datos/venv/bin/pip install "numpy<2"
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos
```

(Documentado en `docs/PENDIENTES_PROXIMA_OFICINA.md` con detalle.)

### "Gemini bloquea con finish_reason=10 (PROHIBITED_CONTENT)"

Falso positivo de safety filters con apodos del roster + términos como "carga"/"fatiga". Ya está fixed en código (safety_settings=BLOCK_NONE en ambos bots y en parse_*_voz.py).

Si vuelve a aparecer: la solución estructural es **NO pasar la consulta por Gemini**, sino usar el detector de intent + script curado (como `estado_jugador.py`).

### "Gemini devuelve JSON truncado"

Gemini 2.5 Flash consume "thinking tokens" de `max_output_tokens`. Asegurar que está en ≥4096.

---

## 🧪 Tests smoke

Antes de pushear cambios grandes, correr:

```bash
~/Desktop/Arkaitz/tests/run_smoke.sh
```

O en modo rápido (sin red/Sheet):

```bash
~/Desktop/Arkaitz/tests/run_smoke.sh --offline
```

Verifica:
- bot.py y bot_datos.py compilan.
- Scripts curados de src/ compilan.
- Detector de intent matchea casos típicos (Pirata, Raya, …) y NO matchea irrelevantes ("hola alfred").
- Aliases consistentes (cada alias apunta a un canónico válido).
- Crono iPad sigue siendo horizontal (regla del proyecto).
- `estado_jugador.py HERRERO 5` devuelve bloque con secciones "Carga media / ACWR / Wellness".

---

## 📐 Cómo añadir un script curado nuevo (recetas)

Cuando el cuerpo técnico te pida un tipo de consulta nuevo frecuente, **no la dejes a Gemini**. Hazle un script curado.

### Receta:

1. Crea `src/<nombre>.py` siguiendo el patrón de `src/estado_jugador.py`:
   - Imports + warnings.filterwarnings("ignore") al inicio.
   - Función que devuelve string Markdown listo.
   - `main()` que parsea sys.argv y llama a esa función.
   - `print(out)` al final, `sys.exit(0)` o `sys.exit(1)` según resultado.

2. Añade detector de intent en `telegram_bot_datos/bot_datos.py` (función `_detectar_intent_*`) y al inicio de `_process_prompt`, llamarlo. Si matchea, ejecuta el script vía `script_runner.run_curated_script(...)` y devuelve el output sin pasar por Gemini.

3. Añade un test smoke en `tests/test_smoke.py` que verifique las secciones esperadas del output.

4. Documenta el atajo en `docs/operaciones_bot.md` (este fichero).

---

## 📂 Archivos clave del repo (post-12/5)

```
~/Desktop/Arkaitz/
├── src/
│   ├── estado_jugador.py     ← script curado de estado (carga + ACWR + wellness + recomendación)
│   ├── health_check.py       ← verifica todos los componentes; usado al arrancar y por cron
│   ├── script_runner.py      ← helper común para ejecutar scripts (sys.executable + filtro warnings)
│   ├── aliases_jugadores.py  ← normalización de nombres
│   ├── parse_sesion_voz.py   ← parse de "fecha X, sesión Y" → SESIONES
│   ├── parse_goles_voz.py    ← parse de goles dictados → EST_EVENTOS
│   ├── parse_ejercicios_voz.py
│   └── …
├── telegram_bot/             ← Alfred (dev)
├── telegram_bot_datos/       ← bot de datos (cuerpo técnico)
├── gastos_bot/               ← bot de gastos
├── setup_servidor/
│   ├── install.sh            ← instala los 5 LaunchAgents
│   ├── auto_pull.sh          ← script de git pull periódico
│   ├── com.arkaitz.bot.plist.template (generado por install.sh)
│   ├── com.arkaitz.autopull.plist.template
│   └── com.arkaitz.healthcheck.plist.template
├── tests/
│   ├── test_smoke.py         ← tests humo
│   └── run_smoke.sh          ← wrapper
├── docs/
│   ├── estado_proyecto.md
│   ├── operaciones_bot.md    ← ESTE archivo
│   └── PENDIENTES_PROXIMA_OFICINA.md
└── logs/
    ├── bot.err.log           ← log Alfred
    ├── bot_datos.err.log     ← log datos
    ├── autopull.log          ← log auto_pull
    └── healthcheck.out.log   ← log health check
```

---

## 🆘 Si todo falla

Si nada del bot responde y los logs no aclaran:

1. Comprobar que el server tiene internet (`ping 8.8.8.8`).
2. Reiniciar el Mac viejo (los LaunchAgents arrancarán solos).
3. Si aún falla: `./setup_servidor/install.sh` para reinstalar los 5 servicios.

Y si todo lo anterior falla y necesitas el bot YA mañana, los scripts curados (`src/*.py`) se pueden ejecutar a mano:

```bash
~/Desktop/Arkaitz/telegram_bot/venv/bin/python ~/Desktop/Arkaitz/src/estado_jugador.py PIRATA 10
```

Eso te da la respuesta sin Telegram, sin Gemini, solo Python + Sheet.
