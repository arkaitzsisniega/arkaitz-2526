# Plan de la planilla de partidos — Arkaitz 25/26

> Este documento es la lista maestra de tareas para construir la planilla
> de meter datos de partidos directamente en Streamlit (sin Excel) y
> luego una mini-app PWA para hacerlo offline.
>
> **Modo de uso**: Arkaitz puede editar este archivo libremente para
> añadir cosas que se le ocurran. La sección "📥 Cosas pendientes que
> añadir" del final está pensada para eso.

Última actualización: 2026-04-28

---

## ✅ Iteración 1 — Roster maestro + cabecera completa

- [x] Hoja `JUGADORES_ROSTER` con dorsal, nombre, posición (CAMPO/PORTERO), equipo (PRIMER/FILIAL), activo
- [x] Script `src/setup_roster.py` con la plantilla 25/26 (12 primer equipo + 8 filial)
- [x] Form de cabecera en 3 columnas: Competición · Rival · Fecha | Hora · Lugar · LOCAL/Visitante | GF · GC · ID
- [x] Selector de plantilla del partido (multiselect del roster, default = primer equipo activo, badge de validación 12-16 convocados)
- [x] Hoja `EST_PLANTILLAS` (1 fila por jugador convocado por partido)
- [x] Cabecera persiste en `EST_TOTALES_PARTIDO` (categoria, lugar, hora, local_visitante, gf, gc)

---

## ✅ Iteración 2 — Eventos de gol

- [x] Min en formato `MM:SS` (TextColumn con parseo)
- [x] 5 columnas de pista separadas (Pista 1..5) en lugar de cuarteto string
- [x] Portero separado, 4+portero o 5 sin portero (portero-jugador)
- [x] Selectores filtrados a la plantilla del partido + RIVAL para goleador
- [x] Leyenda colapsable de dorsales encima del editor
- [x] Validación EN VIVO de incoherencias (4+portero ó 5 sin portero) bajo el editor
- [x] `EST_EVENTOS` persiste `minuto_mmss`

---

## 🔜 Iteración 3 — Métricas individuales (campo + portero + tarjetas)

**Datos por jugador convocado (todos):**
- PF (pérdida forzada)
- PNF (pérdida no forzada)
- ROB (robos)
- COR (cortes)
- BDG (balón dividido ganado)
- BDP (balón dividido perdido)
- DP (disparo a puerta)
- DPos (disparo al palo / al poste)
- DB (disparo bloqueado)
- DF (disparo fuera)
- TA (tarjeta amarilla)
- TR (tarjeta roja)

**Extras solo si es portero:**
- P.PAR (parada)
- P.FUE (disparo recibido fuera)
- P.BLO (disparo recibido bloqueado por defensor del rival)
- P.POS (disparo recibido al palo / poste)
- P.Gol (gol recibido)
- P.SAL (salida correcta del portero)
- P.SAL_FALL (salida fallida) — *nueva idea, pedida en iter 2*

**Diseño UI propuesto:**
- Dos `data_editor` separados: uno para jugadores de campo, otro para porteros.
- Las filas se generan automáticamente desde la plantilla seleccionada.
- Dorsales pre-rellenados (no editables).
- Suma agregada en pie de tabla (totales del equipo).

**Persistencia:** `EST_PARTIDOS` (existente, ampliar columnas si faltan).

---

## 🔜 Iteración 4 — Rotaciones variables (3-8 por parte)

- Se sigue manteniendo el esquema actual (8 columnas por parte) en `EST_PARTIDOS`.
- En el form, el usuario añade una rotación con un botón `+ Rotación`.
- Mínimo 1, máximo 8 por parte. Las que no se usen quedan vacías.
- Por jugador, en cada rotación: minutos en `MM:SS`.
- Rendimiento esperado por columna: validar suma ≈ 20:00 por parte (con un margen).

---

## 🔜 Iteración 5 — Zonas de gol editables visual

**Esquema:** la hoja `EST_DISPAROS_ZONAS` ya tiene columnas A1-A11 (campo) y P1-P9 (portería) tanto a favor como en contra.

**UI propuesta:**
- Mapas SVG clickables: cada zona del campo y cada cuadrante de portería se incrementa al click.
- También considerar: botones +/- por zona (más fácil en móvil).
- Distinguir A FAVOR / EN CONTRA con dos pestañas.
- Idealmente, también registrar los disparos (no solo goles) por zona — *requiere pensar la estructura de datos*.

---

## 🔜 Iteración 6 — Totales disparos 1ª / 2ª parte

- Ampliar `EST_TOTALES_PARTIDO` con: `dt_inter_1t`, `dt_inter_2t`, `dt_rival_1t`, `dt_rival_2t`, `dp_inter_1t`, `dp_inter_2t`, etc.
- En el form: 4 número-input (DT Inter 1T/2T, DT Rival 1T/2T) o cálculo automático desde las métricas individuales.
- En el PDF: KPI "Disparos a puerta: 54 (30+24)".

---

## 🔜 Iteración 7 — Faltas + alerta 6ª falta

**Schema nueva hoja `EST_FALTAS`:**
| col | descripción |
|-----|-------------|
| partido_id | ID del partido |
| tipo | A_FAVOR / EN_CONTRA |
| parte | 1 / 2 |
| minuto_mmss | mm:ss |
| jugador | quién recibe (a favor) o quién comete (en contra) |
| descripcion | texto libre opcional |

**UI:** dos `data_editor` (a favor / en contra), con pre-cuento por parte y badge "⚠️ 6ª falta del rival → próxima penalización: 10m sin barrera".

**Lógica:** cada vez que cualquier equipo llega a la 6ª falta de la parte, mostrar aviso en el dashboard.

---

## 🔜 Iteración 8 — Penaltis y 10m

**Schema nueva hoja `EST_PENALTIS_10M`:**
| col | descripción |
|-----|-------------|
| partido_id | ID |
| tipo | PENALTI / 10M |
| condicion | A_FAVOR / EN_CONTRA |
| parte | 1 / 2 |
| minuto_mmss | mm:ss |
| lanzador | jugador que dispara (Inter o "RIVAL" si en contra) |
| portero | portero que ataja |
| es_gol | TRUE/FALSE |
| cuadrante | P1..P9 (a qué zona de portería va) |
| descripcion | texto libre |

**UI:** un `data_editor` con todos los campos.

---

## 🔜 Iteración 9 — Dashboard visualizar faltas/penaltis

- Pestaña **🟨 Faltas y penaltis** en el dashboard:
  - Histórico de faltas por jugador (ranking).
  - Penaltis a favor: % acierto, lanzadores más usados.
  - Penaltis en contra: % parados por nuestros porteros.
  - Mapa de calor de zonas de portería para penaltis.
- Cada partido en la pestaña 🎮 Partido también muestra:
  - Tabla de faltas del partido.
  - Tabla de penaltis/10m.

---

## 🔜 Iteración 10 — PWA offline (mini-app)

**Objetivo:** poder meter datos sin conexión (en el bus, en una pista
sin wifi) desde el móvil/iPad y sincronizar cuando vuelve la red.

**Arquitectura propuesta:**
- App web (Next.js + IndexedDB para persistencia local).
- Service Worker para cache offline.
- Sincronización con Google Sheets vía API REST cuando hay conexión.
- UI optimizada para tablet/móvil (touch friendly).
- Login con Google para limitar acceso.

**Funcionalidades:**
- Mismas que el form de Streamlit (cabecera + plantilla + eventos +
  métricas + zonas + faltas + penaltis).
- Guardado local automático cada N segundos.
- Indicador de "sincronizado / pendiente de subir".
- Botón "Sincronizar ahora" cuando vuelva la conexión.

---

## 🌟 Iteración 11 (futuro lejano) — App live tablet con cronómetro

Para meter datos **EN DIRECTO** durante el partido desde la banda.

- Cronómetro tipo basket: se pausa al balón fuera, sustituciones en juego.
- Gestión rápida de cambios (botones grandes con dorsales).
- Acciones por tap (mucho más rápido que un form).
- Auto-cálculo de rotaciones desde los cambios.
- Botón de gol (abre modal con goleador, asistente, cuadrante…).
- Tarjetas, faltas, penaltis al toque.

---

## 📥 Cosas pendientes que añadir

> **Arkaitz, escribe aquí lo que quieras añadir a la lista.**
> Cuando quieras que algo se haga, lo movemos a la iteración que toque.

- [ ] (ej.) Permitir adjuntar foto/video del gol al evento
- [ ]
- [ ]
- [ ]
- [ ]

---

## 🔍 Otras cosas pendientes (no relacionadas con la planilla)

Estas tareas son de otras partes del proyecto que han quedado abiertas.

- [ ] Tabla de goles **por tipo de jugada** en PDF (página 3 estilo Cartagena: BANDA / CORNER / SAQUE CENTRO / FALTA / 4x4 / 5x4 ...)
- [ ] Disparos 1T/2T breakdown ("54 (30+24)") — requiere extraer del Excel
- [ ] Mejorar pestaña Lesiones (días baja por zona, tiempos medios de retorno, lesiones activas con countdown)
- [ ] Google Forms para jugadores (Borg + peso PRE/POST + wellness). El usuario ya tiene 2 forms creados, falta integrar al flujo diario
- [ ] Mac viejo como servidor 24/7 para correr bots y scripts sin tener que dejar el portátil encendido
- [ ] Web access para cuerpo técnico (otros entrenadores) con permisos limitados
