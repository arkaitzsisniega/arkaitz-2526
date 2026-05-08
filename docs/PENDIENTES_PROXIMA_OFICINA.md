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

## 🤖 Detector de intención para el bot dev (pedido 08/05/2026)

Antes de pasar el mensaje a Gemini, mirar si matchea con palabras clave
y disparar el handler local correspondiente. Beneficios: instantáneo,
sin coste Gemini, mismos mensajes de progreso que el slash command.

Mapeo inicial (ampliable):
- "consolida" / "consolidar" / "lanza consolidar" / "actualiza datos" → `cmd_consolidar`
- "enlaces" / "enlaces de hoy" / "mándame los enlaces" → `cmd_enlaces`
- "sync oliver" / "sincroniza oliver" / "actualiza oliver" → `cmd_oliver_sync`
- "oliver deep" / "análisis profundo oliver" → `cmd_oliver_deep`
- "ejercicios sync" / "sync ejercicios" → `cmd_ejercicios_sync`
- "apunta la sesión" / "modo sesión" → `cmd_sesion_voz`
- "apunta ejercicios" / "modo ejercicios" → `cmd_ejercicios_voz`
- "nuevo" / "olvida" / "empieza de cero" → `cmd_nuevo`

Implementación: nueva función `_detectar_intent(texto: str) -> Optional[callable]`
en `telegram_bot/bot.py`. Antes de llamar a `_process_prompt` desde
`on_message`, comprobar el intent y, si matchea, llamar al handler.
Si no matchea, seguir con Gemini como ahora.

Tiempo estimado: 20-30 min.

## 🚀 Más optimización del Mac de oficina (continuación 07/05/2026)

Ya hicimos primera tanda (desactivamos 18 launchd plists no usados).
Mejoras siguientes a estudiar:

1. **Spotlight / mdworker_shared**: aparecen varios procesos
   `mdworker_shared` en `top`. Es la indexación de Spotlight. Si está
   constantemente trabajando, significa que está reindexando algo (a
   menudo carpetas grandes recién copiadas o un disco externo). Mirar:
   ```bash
   sudo mdutil -s /
   sudo mdutil -s /Volumes/*  # discos externos
   ```
   Si está en "Indexing enabled" pero el progreso nunca acaba, se puede
   forzar reindex limpio o excluir carpetas pesadas (Time Machine,
   Google Drive cache, etc.).

2. **Caches de Safari/WebKit**: el WebKit estaba consumiendo ~475 MB
   en varios procesos. Mirar pestañas abiertas y extensiones:
   - Safari → Preferencias → Extensiones (desactivar las que no uses).
   - Cerrar pestañas viejas que llevan días/semanas abiertas.

3. **Plugins de la barra de menús** (icons arriba a la derecha): cada
   uno suele ser un proceso. Revisar cuáles son innecesarios.

4. **Análisis de uso de disco**:
   ```bash
   df -h /
   du -sh ~/Library/Caches/* 2>/dev/null | sort -rh | head -10
   du -sh ~/Library/Application\ Support/* 2>/dev/null | sort -rh | head -10
   ```
   Si hay caches enormes de apps que ya no usas, se pueden limpiar.

5. **Apps abiertas en background sin necesidad**: revisar apps que
   abren al iniciar sesión. Hoy solo había Google Drive, pero a veces
   apps añaden agentes de menú que arrancan implícitamente.

6. **Instalar Caffeinate o equivalente** para estudios de impacto: no
   prioritario.

## 🖱 Arreglar ratón Logitech MX Master 2s (pedido 07/05/2026)

**Síntomas reportados por Arkaitz**:
- Scroll lateral (rueda horizontal) **no funciona**.
- Botón lateral "ir hacia atrás" **no funciona**.
- El resto sí funciona (clicks, scroll vertical, otros botones).
- Al abrir Logi Options+, dice que **no tiene permisos** para modificar
  algo del Mac, y se queda atascado ahí.
- Antes funcionaba todo bien, "de la noche a la mañana" se desconfiguró.

**Diagnóstico probable**:
Caso clásico de permisos de macOS reseteados (suele pasar tras actualizar
el SO). Logi Options+ necesita 2 permisos críticos:
- **Accesibilidad** (Accessibility) → para emular eventos de teclado/ratón.
- **Monitorización de entrada** (Input Monitoring) → para leer botones
  custom del ratón.

**Plan a aplicar mañana**:

1. **Verificar permisos actuales**:
   - Abrir: Apple → Ajustes del Sistema → Privacidad y seguridad →
     **Accesibilidad** → buscar "Logi Options" / "Logi Options+" / "Logi".
   - Si NO aparece, está mal instalado. Si aparece pero el toggle está
     OFF, activar.
   - Hacer lo mismo en **Monitorización de entrada** (Input Monitoring).

2. **Si los toggles están en ON pero igualmente no funciona**:
   - Probar quitar el toggle, esperar 5s, volver a activarlo.
   - Reiniciar el Mac y probar.

3. **Si sigue sin ir**:
   - **Desinstalar Logi Options+ completamente**:
     ```bash
     # Buscar el desinstalador oficial:
     ls /Applications | grep -i logi
     ls /Library/Application\ Support/ | grep -i logi
     # Si hay un Uninstaller, ejecutarlo. Si no:
     # (lo investigamos juntos antes de borrar nada a mano)
     ```
   - Reinstalar la versión más reciente desde:
     https://www.logitech.com/es-es/software/logi-options-plus.html
     (o la versión "Logitech Options" estándar si Options+ no
     soporta el MX Master 2S — verificar en la web).
   - Tras instalar, conceder los permisos cuando los pida.

4. **Si tras reinstalar sigue mal**:
   - El **MX Master 2S** se conecta por Bluetooth o por dongle USB
     (Unifying Receiver). Probar la otra opción.
   - Reset del ratón: hay un botón pequeño en la base del MX Master que
     hace reset si lo mantienes 5s.

5. **Plan B mínimo**:
   - Si todo falla, los botones básicos siguen funcionando con macOS
     nativo, pero pierdes el scroll lateral y el botón "atrás" custom.
   - Opciones de software alternativas: SteerMouse (de pago, ~$20),
     BetterTouchTool (de pago).

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
