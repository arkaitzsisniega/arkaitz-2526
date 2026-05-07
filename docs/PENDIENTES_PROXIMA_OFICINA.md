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

## 🌐 Fase 8 — Tailscale (acceso remoto al servidor)

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

## 🔁 Fase 10 — Test de reboot real (cierre del setup 24/7)

**No hemos verificado todavía** que tras un reinicio del Mac viejo los bots
arranquen solos vía cron @reboot. Plan:

```bash
ssh arkaitz@10.48.0.113
sudo shutdown -r now
# espera 1-2 minutos
ssh arkaitz@10.48.0.113
ps aux | grep -E "bot.py|bot_datos.py" | grep -v grep
```

Tienes que ver **3 procesos Python** corriendo. Después prueba desde el
móvil que los 3 bots responden:
- `@InterFS_bot` → "hola"
- `@InterFS_datos_bot` → "¿cuántos jugadores hay?"
- `@GastosComunes_ArkaitzLis_bot` → "5 euros en café"

Si los 3 contestan tras el reboot → **fase 10 cerrada y servidor 24/7
totalmente verificado**.

## 🧹 Fase 9 (opcional) — Limpiar `arrancar_bots.sh` del portátil

Para evitar lanzar los bots por error en el portátil de oficina (lo que
crearía conflicto de `getUpdates` con Telegram). Opciones:
- Mover `arrancar_bots.sh` a `archive/` o renombrarlo `arrancar_bots_OBSOLETO.sh`.
- O simplemente acordarse de no doble-clicarlo nunca más.

## 🧹 Limpieza profunda del Mac viejo servidor (pedido 07/05/2026)

El Mac viejo aún tiene archivos antiguos de la mujer de Arkaitz + apps
heredadas. Todo se puede borrar: **el Mac viejo solo tiene que servir
como servidor de bots, nada más**.

Plan a aplicar cuando estemos delante (con SSH o físicamente):

### 1. Auditar uso de disco
```bash
# Ver qué carpetas pesan más
du -sh /Users/* 2>/dev/null | sort -rh
du -sh /Applications/* 2>/dev/null | sort -rh | head -30
df -h /
```

### 2. Borrar datos personales antiguos (de la mujer)
Confirmar primero con Arkaitz qué carpetas son. Mover a `/tmp` antes
de borrar de verdad, por si acaso. Documentos, fotos, etc.

### 3. Quitar apps no necesarias
El Mac viejo SOLO necesita:
- Python 3.11 + ffmpeg (Homebrew)
- Git
- SSH server (sshd)
- Terminal
- Caches mínimas del sistema

Todo lo demás (iWork, iLife, navegadores extra, apps de su mujer,
software de oficina, juegos, etc.) → **desinstalar**.

```bash
# Listar apps instaladas
ls /Applications | sort
```

Decidir contigo cuáles borrar y mover a la papelera.

### 4. Quitar login items
```bash
osascript -e 'tell application "System Events" to get the name of every login item'
# Borrar los que no sean del sistema
```

### 5. Limpiar launchd agents/daemons innecesarios
Mismo procedimiento que en el Mac de oficina (mover los `.plist` que
no se usan a `.disabled`). En particular: actualizadores de apps que
ya no estén instaladas, herramientas DRM, VPNs, etc.

### 6. Limpiar caches y logs viejos
```bash
sudo rm -rf /private/var/log/asl/*.asl
rm -rf ~/Library/Caches/*
```

### 7. Verificar que tras la limpieza:
- Los bots siguen corriendo (`ps aux | grep bot`).
- El watchdog sigue activo (`crontab -l`).
- Hay espacio libre razonable (`df -h /`).
- RAM disponible (`top -l 1 | head -10`).

Tras esto, el Mac viejo arrancará MUCHO más rápido (es de 2013 con 4GB
RAM, cualquier cosa que liberemos se nota).

## 🆕 Nueva pestaña Streamlit "Catálogo de ejercicios" (pedido 07/05/2026)

Solo accesible para **cuerpo técnico** (rol `tecnico` y `admin`). Contenido:

- Lista de todos los ejercicios hechos (de `_VISTA_EJERCICIOS`).
- Agrupados por nombre normalizado (mismo ejercicio aunque tenga ortografía distinta).
- **Filtros**:
  - por nombre del ejercicio (multiselect)
  - por categoría/tipo (TACTICO, TECNICA, FINALIZACION, etc.)
  - por **intensidad 1-5** (escala que vamos a inventar a partir de Oliver)
  - por jugador
  - por rango de fechas
- **Escala de intensidad 1-5** automática desde Oliver. Posible fórmula:
  combinar `oliver_load`, `distancia_total_m/min`, `sprints_count`,
  `acc_alta_count`, `dec_alta_count`. Umbrales sugeridos:
  - 1 = muy ligero (movilidad, calentamiento)
  - 2 = ligero (técnica analítica)
  - 3 = moderado (rondos, 2x2)
  - 4 = intenso (1x1, partidillos en espacio reducido)
  - 5 = máximo (finalización, juego real, 4x4)
  Antes de codificar, **acordar contigo los umbrales** mirando datos reales.
- **Por ejercicio mostrar**:
  - Nº de veces hechos: última semana / mes / año / total.
  - Minutos totales acumulados (semana/mes/año).
  - Promedios Oliver (load, distancia, HSR, sprints…).
  - Últimas N ejecuciones (fecha, session_id, min, jugador top).

Plan estimado: 2-4h de trabajo.

## 📋 Otras cosas para revisar al estar delante

- Que la tapa del Mac viejo esté cerrada y los bots sigan funcionando.
- `crontab -l` debería tener 4 líneas (3 @reboot + 1 watchdog).
- `launchctl list | grep arkaitz` debería estar **vacío** (ya no usamos launchd).
- `ps aux | grep -E "bot.py|bot_datos.py" | grep -v grep` debería listar 3 procesos Python.
