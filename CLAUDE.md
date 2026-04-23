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

Cuando el usuario retome el proyecto, repasar si están pendientes:

- [ ] Verificar que los pesos de 3 cifras desaparecieron de la pestaña Peso (tras filtro fisiológico en `vista_peso`).
- [ ] Verificar que Carlos ya no da +34 en el semáforo.
- [ ] Confirmar que el nuevo gráfico "Media del equipo" del tab Wellness carga sin error.
- [ ] Confirmar que las pestañas Lesiones y Recuento ya no dan error al fondo.
- [ ] Integración de datos de **Oliver Sports** (acelerometría) — pendiente de credenciales.
- [ ] Dashboard de estadísticas de partido desde `Estadisticas_pruebas_CLAUDE.xlsx`.
- [ ] Google Forms para que los jugadores envíen Borg + peso pre/post + wellness vía enlace de WhatsApp.

## Convenciones

- Commits en español, forma imperativa corta. Incluir `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.
- Después de modificar `calcular_vistas.py`, re-ejecutarlo para que las `_VISTA_*` del Sheet reflejen los cambios antes de que el dashboard se actualice.
- Después de cambios en `dashboard/app.py`: `git push` → Streamlit Cloud tarda 1-2 min en redeplegar.
