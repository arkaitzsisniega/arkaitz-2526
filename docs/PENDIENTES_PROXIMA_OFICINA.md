# 📌 Pendientes para la próxima vez en la oficina

> Doc actualizado el 8 de mayo 2026 (Madrid) — sesión tarde.

## ✅ Hecho 8 mayo 2026 (tarde — limpieza profunda + Mail + lesión)

### Mac viejo (servidor) — limpieza completa
- 9 apps borradas (~14,7 GB): Big Sur installer, Chrome, Keynote, Zoom,
  SmowlCM, VLC, AnyDesk, Remote Desktop Connection, Tuxera Disk Manager.
- Caches usuario, /Users/Shared/Previously Relocated Items, logs ASL.
- Spotlight desactivado en todos los volúmenes (-80 MB RAM permanente).
- 3 daemons huérfanos eliminados (Tuxera, Zoom, Office licensing).
- `sudo purge` → +800 MB RAM libres al instante.
- Resultado RAM: 3272 MB → 2460 MB usados (1635 MB libres tras todo).
- Bots verificados vivos con mismos PIDs (959, 912, 427).

### Mac de oficina — segunda tanda
- ~8,6 GB liberados: Steam (1,2), Minecraft (1,2), Amazon Music (662 M),
  uTorrent Web (83 M), Wondershare leftover (300 M), Claude ShipIt cache
  (681 M), GoogleUpdater (697 M), Chrome OptGuideOnDeviceModel (4 GB),
  Chrome optimization_guide_model_store (126 M).
- Pendiente para CIERRE de la próxima sesión: 10 GB del bundle
  `~/Library/Application Support/Claude/vm_bundles/claudevm.bundle`
  (hay que CERRAR Claude Desktop primero, luego `mv` a /tmp).

### Mail.app
- Síntoma cerrado parcial: correos del móvil ya aparecen en los más
  recientes; faltaban los de marzo. Se descartó tipo de cuenta (IMAP),
  buzones (`[Gmail]/Enviados` correcto) y límite IMAP de Gmail (sin
  límite). Reconstruir buzón no bastó.
- Ejecutado plan B: eliminar cuenta Txubas → re-añadir vía Google.
- **Pendiente verificar** cuando termine la re-descarga: que los
  correos de marzo aparezcan en `Enviados` de Txubas.

### Bot dev (Alfred) — fix marcar lesión
- Nuevo script `src/marcar_lesion.py`: API limpia, idempotente, escribe
  BORG ('L') + LESIONES en una sola llamada bash.
- System prompt simplificado para que Gemini llame al script en lugar
  de copiar 50 líneas de Python (donde metía typos).
- Validado real con PANI (08/05/2026): BORG fila 3881, LESIONES fila 501.
- Commit `5eda501` pusheado, server actualizado y bot reiniciado.

## ✅ Hecho hoy (8 mayo 2026)

- Servidor 24/7 con los 3 bots gestionados por launchd (KeepAlive=true).
- **Fase 10 cerrada**: test de reboot real verificado, los 3 bots arrancan
  solos tras `sudo shutdown -r now`.
- 18 launchd plists desactivados en el Mac de oficina (MySQL, TeamViewer,
  CodeMeter, ExpressVPN, etc.).
- Ratón Logitech MX Master 2s reparado (reinstalado Logi Options+).
- Reposo manual del Mac de oficina arreglado.
- Bots dev y datos refinados (esquema, alias jugadores, tono natural,
  detector de intención para hablar en lenguaje natural).
- Bot dev: `/sesion` y `/ejercicios_voz` migrados a Gemini API.
- Bot gastos: `clasificador_claude.py` reemplazado por `clasificador_gemini.py`.
- Streamlit: pestaña "📚 Catálogo de ejercicios" para cuerpo técnico.
- Streamlit: fix StateError en planilla compañero.

---

## 🚧 Pendientes vivos

### 🌐 Fase 8 — Acceso remoto al servidor (DESCARTADO, "si hace falta")

Tailscale en Catalina **NO es trivial**:
- App Store: requiere macOS 11+.
- .pkg standalone: requiere macOS 11+.
- `brew install tailscale`: necesita Go que requiere macOS Monterey 12+.

Decisión 08/05/2026: Arkaitz va habitualmente a oficina, no necesita
acceso remoto al servidor. Si en algún momento lo necesita, montamos
**ZeroTier** (gratis, soporta Catalina nativo, ~5 min de setup).

### 🧹 Limpieza profunda del Mac viejo servidor — ✅ CERRADO 8/5/2026

Hecho. Resumen arriba en "Hecho 8 mayo 2026 (tarde)". No había datos
antiguos de la mujer (no había user folders extra). Todo lo demás
desinstalado o desactivado.

### 🚀 Más optimización del Mac de oficina — ✅ MAYORÍA HECHA 8/5/2026

Segunda tanda hecha (8,6 GB liberados, ver arriba). Pendiente:
- 10 GB del bundle de Claude Desktop al CIERRE de la próxima sesión.
- Si en algún futuro Safari/WebKit van otra vez pesados: cerrar
  pestañas viejas, revisar extensiones.

### 📧 Sincronización Gmail ↔ Mail.app — 🟡 EN VERIFICACIÓN 8/5/2026

Plan B ejecutado (eliminar cuenta + re-añadirla). Pendiente confirmar
que tras la re-descarga aparecen los correos antiguos. Si vuelve a
fallar: investigar `Mail > Settings > Accounts > Avanzado` o reinstalar
Mail (último recurso).

### 🆕 Pestaña Streamlit "Catálogo de ejercicios" — FUTURAS MEJORAS

Ya está la primera versión en producción. Mejoras que pueden venir bien
con el uso real:

- Ajustar la fórmula de intensidad 1-5 (combinar `intensity_medio` con
  `n_sprint/min`, `dist_high_intensity/min`, `oli_volume_sum/min`).
- Acordar umbrales con Arkaitz tras observar datos reales.
- Añadir charts: evolución temporal de un ejercicio (frecuencia mensual).
- Comparar dos ejercicios lado a lado.

---

## 📋 Otras cosas para revisar al estar delante

- Que la tapa del Mac viejo esté cerrada y los bots sigan funcionando.
- `crontab -l` debería estar **vacío** (todo es launchd ahora).
- `launchctl list | grep arkaitz` → 3 entradas con PIDs.
- `ps aux | grep "python.*bot" | grep -v grep` → 3 procesos.
