# 📌 Pendientes para la próxima vez en la oficina

> Tareas que requieren estar físicamente delante del Mac viejo (servidor),
> o al menos en la misma red WiFi para SSH. Mientras Arkaitz esté en
> casa NO se pueden hacer.

## 🟢 Bots — aplicar refinamientos pusheados

Hay commits en `main` que aún no están aplicados en el Mac viejo:
- `e6b1749 bots: reescritura completa de system prompts (esquema verificado + ejemplos)`
- `d651d8b bots: ejemplos extras + watchdog mas robusto bajo cron`

**Lo primero al llegar a la oficina** (1 minuto):

```bash
ssh arkaitz@10.48.0.113
cd ~/Desktop/Arkaitz
git pull
pkill -f bot_datos.py
pkill -f telegram_bot/bot.py
```

(El watchdog cron los relanza con los prompts nuevos en menos de 1 minuto.)

Verificar después con una pregunta al bot de datos:
> "¿Cuánto pesa Carlos en el último entreno?"

Tiene que devolver un número correcto en kg (no algo como 740 kg).

## 🌐 Tailscale — acceso remoto al servidor

Para poder gestionar los bots desde casa también, no solo desde la oficina.
Pasos:
1. En el Mac viejo: instalar Tailscale (https://tailscale.com/download), 
   iniciar sesión con la cuenta de Arkaitz.
2. En el Mac de oficina y/o el iPhone: instalar Tailscale, iniciar sesión 
   con la misma cuenta.
3. A partir de ahí, en lugar de `ssh arkaitz@10.48.0.113` se usa
   `ssh arkaitz@<nombre-tailscale-del-mac-viejo>` y funciona desde cualquier
   red.

Coste: **gratis** (free tier de Tailscale cubre hasta 100 dispositivos personales).

## 📋 Otras cosas para revisar al estar delante

- Que la tapa del Mac viejo esté cerrada y los bots sigan funcionando.
- `crontab -l` debería tener 4 líneas (3 @reboot + 1 watchdog).
- `launchctl list | grep arkaitz` debería estar **vacío** (ya no usamos launchd).
- `ps aux | grep -E "bot.py|bot_datos.py" | grep -v grep` debería listar 3 procesos Python.
