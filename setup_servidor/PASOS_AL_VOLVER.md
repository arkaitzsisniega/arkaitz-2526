# 🚀 Pasos para activar el setup completo en el server

> Actualizado **12 mayo 2026**. Reemplaza el sistema antiguo basado en cron
> por **launchd** (LaunchAgents) + `auto_pull` + `health_check`.

---

## TL;DR — primera vez

```bash
ssh arkaitz@<ip-del-server>
cd ~/Desktop/Arkaitz
git pull
./setup_servidor/install.sh
launchctl list | grep arkaitz   # debe haber 5 entradas
```

Eso es todo. A partir de ahí:
- Los **3 bots** corren 24/7 (`KeepAlive=true`).
- **auto_pull** hace `git pull` cada 5 min y reinicia bots si hay cambios.
- **health_check** comprueba cada hora todo el sistema y avisa por Telegram si algo falla.

---

## Detalle paso a paso

### 0. Prerequisitos (una vez)

- Repo clonado en `~/Desktop/Arkaitz/`.
- `google_credentials.json` en la raíz del repo.
- Cada bot con su `.env` configurado (`TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_ID`/`ALLOWED_CHAT_IDS`, `GEMINI_API_KEY`, `GEMINI_MODEL`).
- Cada bot con su `venv/` y dependencias instaladas:

```bash
cd ~/Desktop/Arkaitz/telegram_bot && ./venv/bin/pip install -r requirements.txt
cd ~/Desktop/Arkaitz/telegram_bot_datos && ./venv/bin/pip install -r requirements.txt
cd ~/Desktop/Arkaitz/gastos_bot && ./venv/bin/pip install -r requirements.txt
```

⚠️ **Importante**: `numpy<2` en los venvs de telegram_bot y telegram_bot_datos
(faster-whisper / onnxruntime 1.16.3 no son compatibles con numpy 2.x):

```bash
~/Desktop/Arkaitz/telegram_bot/venv/bin/pip install "numpy<2"
~/Desktop/Arkaitz/telegram_bot_datos/venv/bin/pip install "numpy<2"
```

### 1. Arrancar el setup

```bash
cd ~/Desktop/Arkaitz
./setup_servidor/install.sh
```

Eso genera y carga 5 LaunchAgents:
- `com.arkaitz.bot` — bot dev (Alfred)
- `com.arkaitz.bot_datos` — bot de datos (cuerpo técnico)
- `com.arkaitz.gastos_bot` — bot de gastos
- `com.arkaitz.autopull` — `git pull` cada 5 min + reinicio si hay cambios
- `com.arkaitz.healthcheck` — verificación horaria con notificación si falla

### 2. Verificar

```bash
launchctl list | grep arkaitz
```

Debe mostrar 5 servicios con PIDs reales (no `-`).

```bash
tail -20 ~/Desktop/Arkaitz/logs/bot.err.log
```

Debe ver "Bot arrancado..." y "Application started" reciente.

### 3. Probar desde móvil

- `@InterFS_bot` (Alfred) → debe mandarte automáticamente al arrancar un mensaje "✅ Bot dev arrancado — health check OK".
- `@InterFS_datos_bot` → mandar "cómo está Pirata" → debe responder con el bloque profesional del script `estado_jugador.py`.

---

## Comandos útiles del día a día

| Acción | Comando |
|---|---|
| Ver estado de los 5 servicios | `launchctl list \| grep arkaitz` |
| Reiniciar un bot manualmente | `launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot` |
| Forzar un git pull ahora mismo | `~/Desktop/Arkaitz/setup_servidor/auto_pull.sh` |
| Ejecutar health check ahora | `~/Desktop/Arkaitz/telegram_bot/venv/bin/python ~/Desktop/Arkaitz/src/health_check.py` |
| Ver log de un bot | `tail -50 ~/Desktop/Arkaitz/logs/bot.err.log` |
| Ver log del auto_pull | `tail -30 ~/Desktop/Arkaitz/logs/autopull.log` |
| Ver log del health_check | `tail -30 ~/Desktop/Arkaitz/logs/healthcheck.out.log` |
| Desinstalar todo | `~/Desktop/Arkaitz/setup_servidor/uninstall.sh` |
| Tests humo del proyecto | `~/Desktop/Arkaitz/tests/run_smoke.sh` |

---

## ⚠️ Si algo falla

1. **Comprueba el log del bot** (`tail -50 ~/Desktop/Arkaitz/logs/bot.err.log`).
2. **Ejecuta el health check manualmente** para ver qué pieza está rota:
   ```bash
   ~/Desktop/Arkaitz/telegram_bot/venv/bin/python ~/Desktop/Arkaitz/src/health_check.py
   ```
3. Consulta `docs/operaciones_bot.md` para los diagnósticos típicos (Whisper, Gemini, 409 Conflict, etc.).

Si nada funciona y necesitas el bot para una demo / partido inminente,
ejecuta los **scripts curados a mano**:

```bash
~/Desktop/Arkaitz/telegram_bot/venv/bin/python ~/Desktop/Arkaitz/src/estado_jugador.py PIRATA 10
```

Eso te da el análisis del jugador sin Telegram, sin Gemini, solo Python + Sheet.
