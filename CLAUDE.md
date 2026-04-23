# Proyecto Arkaitz 25/26 — Notas para Claude

## Sobre el usuario

- **Arkaitz** (`@arkaitzsisniega`) — director técnico / preparador físico de Movistar Inter FS.
- **No es técnico**. Sabe lo que necesita funcionalmente pero no programa. Explícale lo justo, con pasos copiables y claros. Evita jerga salvo que sea imprescindible y, si la usas, defínela.
- Trabaja sobre todo desde Mac en la oficina y desde móvil (Telegram, vía `telegram_bot/`).
- Idioma: **siempre en español**.

## Cómo le gusta que trabaje

- **Proactividad**: guíale los siguientes pasos. Tiende a irse a otra cosa y perder el hilo de temas abiertos. Si una tarea deja un hilo suelto (verificar algo, revisar datos, probar un cambio desplegado), recuérdaselo al cerrar.
- **Mantén un hilo de pendientes** en la cabeza entre mensajes. Cuando termines una tanda de cambios, termina siempre con un "próximos pasos" o "cosas por revisar".
- **No te lances a hacer cambios grandes sin confirmar el plan primero** cuando sean cambios estructurales. Para fixes pequeños, adelante.
- **Muéstrame lo que cambias** y por qué, no solo el resultado.

## Stack y arquitectura

- **Datos**: Google Sheets (`Arkaitz - Datos Temporada 2526`) como base de datos central.
  - Hojas crudas: `SESIONES`, `BORG`, `PESO`, `WELLNESS`, `LESIONES`, `FISIO`.
  - Hojas vista pre-calculadas: `_VISTA_CARGA`, `_VISTA_SEMANAL`, `_VISTA_PESO`, `_VISTA_WELLNESS`, `_VISTA_SEMAFORO`, `_VISTA_RECUENTO`.
- **Pipeline**: `src/calcular_vistas.py` lee hojas crudas → calcula métricas (ACWR EWMA, monotonía, fatiga, baselines, semáforos) → escribe hojas `_VISTA_*`.
- **Dashboard**: `dashboard/app.py` (Streamlit). Lee solo las `_VISTA_*` y renderiza 6 pestañas (Semáforo, Carga, Peso, Wellness, Lesiones, Recuento).
- **Deploy**: Streamlit Cloud, autodeploy desde GitHub `arkaitzsisniega/arkaitz-2526` branch `main`. Credenciales en `st.secrets`.
- **Auth Google Sheets**: service account `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com`. Credenciales locales en `google_credentials.json` (gitignored).
- **Bot Telegram**: `telegram_bot/` — proxy a Claude Code CLI. Solo responde a `ALLOWED_CHAT_ID`.

## Python

- El Python del sistema (`/usr/bin/python3`, v3.9) es el que tiene gspread y pandas instalados globalmente.
- El `python3` del PATH apunta a Anaconda y **no** tiene gspread — no usarlo para `calcular_vistas.py`.
- Para ejecutar el pipeline: `/usr/bin/python3 src/calcular_vistas.py`.

## Métricas de dominio (futsal / sports science)

- **sRPE** = BORG × MINUTOS (carga de sesión).
- **ACWR** (Acute:Chronic Workload Ratio) con EWMA: λ_aguda=0.1316 (~7 días), λ_crónica=0.0339 (~28 días).
  - <0.8 = azul (infra-carga) · 0.8–1.3 = verde · 1.3–1.5 = amarillo · >1.5 = rojo.
- **Monotonía** = media diaria / desviación diaria (>2 = riesgo).
- **Fatiga** = carga_semanal × monotonía.
- **Wellness**: suma de SUEÑO + FATIGA + MOLESTIAS + ÁNIMO (cada una 1-5). Total 4-20. Rojo ≤10, naranja ≤13, verde >13.
- **Peso PRE semáforo**: última sesión vs media últimos 2 meses. Rojo <-3kg, naranja <-1.5kg, verde >=-1.5kg. Filtro fisiológico 40-200kg para excluir entradas erróneas tipo `71,5→715`.

## Hilos abiertos / cosas a recordar

### ✅ Cerrados (abril 2026)
- Dashboard completo funcionando en Streamlit Cloud.
- Fix de coma decimal española (lectura con UNFORMATTED_VALUE).
- Fix de fechas ISO mal parseadas (dayfirst=True corrompía YYYY-MM-DD).
- Filtro fisiológico 40-200 kg en `vista_peso`.
- Semanas fantasma eliminadas en `vista_semanal` (skip carga=0).
- Recuento con estados S/A/L/N reales y PCT_PARTICIPACION capado.
- Bot Telegram @InterFS_bot (dev, uso personal) + bot @InterFS_datos_bot
  (consultas de datos, multi-usuario con lista chat_id en .env).
- Ambos bots con memoria conversacional (`claude -c`) y soporte de voz
  (Whisper local, modelo "base", español).
- Script `arrancar_bots.sh` en la raíz para lanzar ambos con un comando.

### 🕐 Pospuesto (por decisión del usuario)
- Mejorar pestaña Lesiones (el usuario dijo "es mejorable, pero más adelante").
  Temas candidatos: gráfico de días baja por zona, tiempos medios de retorno,
  lesiones activas con countdown, etc.

### 🔜 Pendientes (próximos, por orden sugerido)
- [ ] **Integración Oliver Sports** (acelerometría en entrenamientos).
      Pendiente: que el usuario cuente cómo accede hoy (API, export CSV, app web…)
      para decidir cómo tirarle las métricas al dashboard.
- [ ] **Google Forms para jugadores** (envío auto de Borg + peso PRE/POST +
      wellness tras cada entrenamiento, enlace vía WhatsApp). Ahorra mucho
      tiempo diario a Arkaitz.
- [ ] **Dashboard de estadísticas de partido** desde `Estadisticas_pruebas_CLAUDE.xlsx`
      (minutos jugados, goles, asistencias, etc. por jugador).

## Convenciones

- Commits en español, forma imperativa corta. Incluir `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.
- Después de modificar `calcular_vistas.py`, re-ejecutarlo para que las `_VISTA_*` del Sheet reflejen los cambios antes de que el dashboard se actualice.
- Después de cambios en `dashboard/app.py`: `git push` → Streamlit Cloud tarda 1-2 min en redeplegar.

## Sincronización móvil ↔ ordenador

El usuario alterna entre hablar con los bots de Telegram (móvil) y con Claude
Desktop/Code (ordenador). Para no perder contexto:

- Cada intercambio (pregunta + respuesta) se espeja en `telegram_logs/YYYY-MM-DD.md`.
- Cuando inicies sesión y el usuario mencione algo que parezca continuar una
  conversación previa del bot (o simplemente si tiene sentido), **lee el log de
  hoy** con `Read("telegram_logs/YYYY-MM-DD.md")` para recuperar el hilo.
- La carpeta está en `.gitignore` (datos pueden ser sensibles).
