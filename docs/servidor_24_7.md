# 🖥 Servidor 24/7 — análisis y plan

Documento de planificación para tener los bots de Telegram corriendo
24/7 sin depender del portátil de trabajo. **Pendiente de decisión
del usuario** sobre la opción a implementar.

---

## ¿Qué necesita correr 24/7?

### Procesos críticos (deben estar siempre activos)
- **`telegram_bot/bot.py`** — bot personal de Arkaitz (@InterFS_bot).
  Recibe comandos para `/sesion`, `/consolidar`, `/oliver_sync`, etc.
- **`telegram_bot_datos/bot_datos.py`** — bot del cuerpo técnico
  (@InterFS_datos_bot). Multi-usuario.
- **`gastos_bot/bot.py`** — bot de gastos personales.

### Procesos cron (corren a horarios concretos)
- Renovación de token Oliver al arrancar la sesión / diariamente.
- Sync de Oliver semanal automático (ya programado en JobQueue).
- (Futuro) Recordatorios programados, reports semanales, etc.

### NO necesita correr 24/7
- Streamlit Cloud → ya está en cloud, independiente.
- `calcular_vistas.py` → solo se ejecuta tras `/consolidar` desde el bot.

---

## Opciones disponibles

### Opción A — Mac viejo en casa (lo que el usuario propuso)

**Pros**:
- 0 € de coste mensual.
- Hardware ya en propiedad.
- Acceso físico para depurar.
- Gran capacidad (Whisper local funciona bien).

**Contras**:
- Cortes de luz / internet en casa = parón.
- Hay que mantenerlo encendido siempre.
- Si se rompe, hay que arreglarlo manualmente.
- Consumo eléctrico continuo (~25-50W = ~50-100€/año).

**Setup**:
1. Instalar Homebrew, Python 3.11+, dependencias del proyecto.
2. Clonar el repo y configurar `.env` con tokens.
3. Configurar **launchd** (sistema nativo de macOS para servicios)
   con archivos `.plist` que arranquen los 3 bots al boot.
4. Configurar logrotate para no llenar el disco.
5. Configurar Tailscale o ngrok para acceso remoto si hace falta.
6. Configurar reinicio automático tras crash (con `KeepAlive` en plist).

### Opción B — VPS cloud (DigitalOcean, Hetzner, Contabo)

**Pros**:
- Uptime 99.9% (corriente y red profesionales).
- Acceso SSH desde cualquier sitio.
- Snapshot/backup automático.
- IP fija (útil para webhooks).

**Contras**:
- Coste mensual: 5-10€/mes (60-120€/año).
- Hay que aprender básicos de Linux.
- Whisper local NO viable en máquinas baratas (necesita >2GB RAM
  + buen CPU). Hay que migrar a Whisper API o similar.

**Setup**:
1. Crear droplet/VPS Ubuntu 22.04 con 2GB RAM (~6€/mes Contabo).
2. SSH, instalar dependencias (`apt install python3.11 git`).
3. Clonar repo, configurar `.env`.
4. Configurar **systemd** con archivos `.service` para los bots
   (similar a launchd pero más extendido en Linux).
5. UFW firewall + SSH keys (no contraseñas).
6. Reverse proxy con Caddy si más adelante hace falta servir HTTP.

### Opción C — Raspberry Pi 4 (8GB)

**Pros**:
- 1 sola compra (~80€). Cero coste mensual de cloud.
- Bajísimo consumo (~5W).
- Pequeña, silenciosa.
- Compatible con todo lo del Mac (Python en Linux ARM).

**Contras**:
- Compra inicial.
- Whisper "tiny" o "base" funciona pero "small"/"medium" muy
  lento.
- Disco SSD externo recomendado para evitar romper la SD.

**Setup**:
1. Raspberry Pi OS 64-bit Lite (sin GUI).
2. Igual que Opción B pero en hardware local.
3. Conectar a tu router por Ethernet para mejor estabilidad.

### Opción D — Mantener como está (Mac de trabajo)

**Pros**:
- 0 € coste, 0 esfuerzo.

**Contras**:
- Bots se caen cada vez que el Mac se apaga / hace reboot.
- Hay que arrancar manualmente con `arrancar_bots.sh`.

---

## 💡 Recomendación

Si tienes un Mac viejo (>= 2015, con macOS Big Sur o superior)
**Opción A** es la mejor: 0 coste, control total, todo lo que ya
funciona seguirá funcionando sin migrar. Solo hay que configurar
launchd y Tailscale para acceso remoto.

Si NO tienes Mac viejo o quieres más fiabilidad → **Opción B
(VPS)** por 6€/mes en Contabo. Migrar Whisper a API si es necesario
(coste extra de ~5€ al mes de uso real).

**Opción C (Raspberry Pi)** si te gusta cacharrear y aceptas que
Whisper sea lento. Inversión única.

---

## Plan de implementación para Opción A (Mac viejo)

### Fase 1 — Preparación del Mac viejo (1-2h)

Asumiendo el Mac viejo tiene macOS:

```bash
# 1. Instalar Homebrew (si no está)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Python 3.11 y herramientas
brew install python@3.11 git ffmpeg

# 3. Clonar repo
mkdir -p ~/Desktop/Arkaitz
cd ~/Desktop
git clone https://github.com/arkaitzsisniega/arkaitz-2526.git Arkaitz

# 4. Instalar dependencias Python
cd Arkaitz
/usr/bin/python3 -m pip install -r requirements.txt   # si existe
# o instalar manualmente lo que use:
/usr/bin/python3 -m pip install gspread google-auth requests \
    python-telegram-bot pandas numpy openpyxl pdfplumber pypdf \
    streamlit altair plotly reportlab

# 5. Copiar archivos sensibles del Mac actual:
#    - google_credentials.json (en raíz)
#    - .env (en raíz, telegram_bot/, telegram_bot_datos/, gastos_bot/)
# Usar AirDrop, USB, scp con Tailscale, etc. NUNCA por email/chat.

# 6. Probar manualmente que arranca:
./arrancar_bots.sh
# Mandar /id al @InterFS_bot, verificar respuesta.
# Si funciona, parar con Ctrl+C en cada terminal.
```

### Fase 2 — launchd para arranque automático (1h)

Crear 3 archivos `.plist` en `~/Library/LaunchAgents/`:

`~/Library/LaunchAgents/com.arkaitz.bot.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arkaitz.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/mac/Desktop/Arkaitz/telegram_bot/bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/mac/Desktop/Arkaitz/telegram_bot</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/mac/Desktop/Arkaitz/logs/bot.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/mac/Desktop/Arkaitz/logs/bot.err.log</string>
</dict>
</plist>
```

(Análogos para `com.arkaitz.bot_datos.plist` y
`com.arkaitz.gastos_bot.plist`.)

Activar:
```bash
launchctl load ~/Library/LaunchAgents/com.arkaitz.bot.plist
launchctl load ~/Library/LaunchAgents/com.arkaitz.bot_datos.plist
launchctl load ~/Library/LaunchAgents/com.arkaitz.gastos_bot.plist

# Comprobar:
launchctl list | grep arkaitz
```

### Fase 3 — Acceso remoto con Tailscale (30 min)

1. Instalar **Tailscale** en el Mac viejo y en tu portátil:
   https://tailscale.com/download/mac
2. Login con la misma cuenta Google en ambos.
3. El Mac viejo recibe una IP `100.x.y.z` accesible desde cualquier
   parte (también móvil con la app de Tailscale).
4. SSH al Mac viejo desde el portátil:
   ```bash
   ssh mac@100.x.y.z   # IP del Mac viejo en Tailscale
   ```
5. Si quieres usar Streamlit Cloud apuntando al Mac viejo (en lugar
   de Streamlit Cloud), configurar reverse proxy + dominio. Pero
   dado que Streamlit Cloud ya funciona, no es prioritario.

### Fase 4 — Logrotate (15 min)

Para que los logs no llenen el disco:

```bash
# ~/.logrotate.conf
/Users/mac/Desktop/Arkaitz/logs/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

Tarea cron diaria que ejecuta `logrotate -s ~/.logrotate.state ~/.logrotate.conf`.

### Fase 5 — Monitorización (30 min, opcional)

- **Healthcheck**: cada hora, un script que pinga al bot enviando
  `/ping` y comprueba respuesta.
- **Telegram alert**: si un bot lleva >30 min sin responder, enviar
  alerta a tu @InterFS_bot personal.

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Corte de luz | UPS pequeña (~80€) → 30-60 min autonomía |
| Corte de internet | Tu casa tiene fibra; raro pero posible. Tailscale Funnel para acceso desde fuera no aplica si no hay internet en absoluto |
| Mac viejo se cuelga | `KeepAlive` en launchd reinicia el bot. Si el Mac mismo se cuelga, no hay solución automática |
| Crash de bot | `KeepAlive=true` lo relanza solo |
| Token Oliver caduca | Auto-refresh ya implementado (oliver_login.py) |

---

## Checklist para cuando arranquemos

- [ ] El usuario nos confirma qué Mac viejo tiene (modelo + macOS).
- [ ] AirDrop/copia de archivos sensibles.
- [ ] Probar manual los 3 bots en el Mac viejo.
- [ ] Crear los 3 `.plist`.
- [ ] Activar con `launchctl load`.
- [ ] Probar reboot del Mac viejo y verificar que arrancan solos.
- [ ] Tailscale para acceso remoto.
- [ ] Logrotate.
- [ ] Apagar los bots del Mac de trabajo (`pkill -f telegram_bot`).
- [ ] Documentar el cambio en `CLAUDE.md` y `estado_proyecto.md`.

Tiempo total estimado: **3-4h** una vez tengamos el Mac viejo a mano.
