# 📌 Pendientes para la próxima vez en la oficina

> Doc actualizado el 8 de mayo 2026 (Madrid).

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

### 🧹 Limpieza profunda del Mac viejo servidor

El Mac viejo aún tiene archivos antiguos de la mujer de Arkaitz + apps
heredadas. Todo se puede borrar: el Mac viejo solo tiene que servir como
servidor de bots.

Plan a aplicar cuando estemos delante:

1. Auditar uso de disco
   ```bash
   du -sh /Users/* 2>/dev/null | sort -rh
   du -sh /Applications/* 2>/dev/null | sort -rh | head -30
   df -h /
   ```

2. Borrar datos personales antiguos (de la mujer). Mover a `/tmp` antes
   de borrar de verdad, por si acaso.

3. Quitar apps no necesarias. El Mac viejo SOLO necesita: Python 3.11 +
   ffmpeg, Git, SSH, Terminal. Todo lo demás (iWork, iLife, navegadores
   extra, software de oficina, juegos, etc.) → desinstalar.

4. Quitar login items no esenciales.

5. Limpiar caches y logs viejos:
   ```bash
   sudo rm -rf /private/var/log/asl/*.asl
   rm -rf ~/Library/Caches/*
   ```

6. Verificar tras la limpieza:
   - `ps aux | grep bot` → 3 procesos vivos
   - `df -h /` → espacio libre razonable
   - `top -l 1 | head -10` → RAM disponible

### 🚀 Más optimización del Mac de oficina

Ya hicimos primera tanda. Mejoras siguientes a estudiar:

1. **Spotlight**: revisar `mdworker_shared`. Si está reindexando algo
   constantemente, excluir carpetas pesadas.
2. **Caches de Safari/WebKit**: eran 475 MB en varios procesos. Cerrar
   pestañas viejas, revisar extensiones.
3. **Plugins de la barra de menús**: cada uno suele ser un proceso.
4. **Análisis de uso de disco**:
   ```bash
   df -h /
   du -sh ~/Library/Caches/* 2>/dev/null | sort -rh | head -10
   du -sh ~/Library/Application\ Support/* 2>/dev/null | sort -rh | head -10
   ```

### 📧 Sincronización Gmail ↔ Mail.app

**Síntoma**: correos enviados desde Gmail en el móvil no aparecen en
la app Mail del Mac de oficina.

**Plan**: verificar tipo de cuenta (POP vs IMAP), reconfigurar como IMAP
si está en POP, asegurar mapeo de carpeta "Enviados" a `[Gmail]/Sent Mail`.

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
