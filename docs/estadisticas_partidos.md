# Estadísticas de partido — modelo y pipeline

## Origen

Archivo manual que Arkaitz mantiene partido a partido:
`/Users/mac/Mi unidad/Deporte/Futbol sala/Movistar Inter/2025-26/Estadisticas/Estadisticas2526.xlsx`

71 pestañas, organizadas así:

| Tipo | Patrón | Ejemplos |
|---|---|---|
| Liga regular | `J<n>.RIVAL` | `J1.BARCELONA`, `J2.CORDOBA`, …, `J26.XOTA` |
| Amistosos pretemporada | `AMIS.RIVAL` | `AMIS.Mostoles`, `AMIS.Corinthians`, … |
| Amistosos en temporada | `AMISTOSO.RIVAL` | `AMISTOSO.JAEN`, `AMISTOSO.VALDEPEÑAS` |
| Playoffs liga | `PLAYOFF<n>` | `PLAYOFF1`, …, `PLAYOFF10` |
| Supercopa | `SUP.SEMI` | |
| Copa España | `C.E.<fase>` | `C.E.CUARTOS`, `C.E.SEMI`, `C.E.FIN` |
| Copa Mundo | `C.M.<rival>/fase` | `C.M.TORREJON`, `C.M.SEMI`, `C.M.FIN` |
| Copa Rey | `C.R.<n>ª.RIVAL` o fase | `C.R.4ª.LUGO`, `C.R.SEMI`, `C.R.FIN` |
| Plantillas vacías | `J27`, `J28`, `J29`, `J30`, `P49`, `CAJA NEGRA` | (sin datos aún) |
| Hojas agregadas | `EST.TOTAL`, `GOLES`, `TIEMPOS`, `EST. x COMP.`, `CUARTETOS`, `PIVOT_CUARTETOS` | con FÓRMULAS no cacheadas |
| Hojas dashboard | `DASH_GOLES`, `DASH_GOLESx5MINS`, `DASH_CUARTETOS` | tablas de resumen, sin gráficos |

---

## Estructura de una hoja de partido

Cada partido es una pestaña con varios bloques en posiciones FIJAS:

### Bloque 1 — Metadatos (filas 1-3)
- `MOVISTAR INTER vs RIVAL` (filas 2-3, cols D-H aprox.)
- CATEGORÍA / LIGA / COPA — col K-L
- LUGAR (E/F? — **🟡 confirmar**)
- HORA — col W
- FECHA — col X-Y

### Bloque 2 — Rotaciones 1ª parte (filas 5-19, cols B-L)
- B: nº dorsal · C: NOMBRE
- D-K: 1ª–8ª rotación (duraciones HH:MM:SS)
- L: total 1ª parte (= suma D-K)

### Bloque 3 — Rotaciones 2ª parte (filas 5-19, cols O-W)
- O-V: 1ª–8ª rotación · W: total 2ª parte

### Bloque 4 — Eventos de gol (filas 41-56, cols A-AA)
Una fila por gol marcado en el partido (a favor o en contra). Columnas:
| Col | Significado |
|---|---|
| B  | RESULTADO acumulado tras el gol (`"0 -- 1"`) |
| D  | MIN exacto (HH:MM:SS) |
| F  | ACCIÓN (EC.4x4, AF.CONTRAATAQUE, AF.FALTA, AF.BANDA…) |
| M  | Portero presente |
| O,Q,S,U | 3 jugadores del cuarteto en pista |
| W  | GOLEADOR (nombre o "RIVAL") |
| Z  | ASISTENTE |

### Bloque 5 — Goles por intervalos de 5 min (filas 58-69)
- A: rangos `0'-5'`, `5'-10'`, …, `35'-40'`
- B: FAVOR · C: CONTRA (cómputos del partido)
- 67-69: subtotales 1ª PARTE, 2ª PARTE, TOTAL

### Bloque 6 — Tabla individual del partido (filas 70-87, cols A-N)
Resumen por jugador del partido (T/S/NJ, goles a favor, en contra, dif, minutos por parte).

### Bloques 7 y 8 — Goles A FAVOR / EN CONTRA por jugador y tipo (filas 89-104, 106-120)
Matriz 14 jugadores × 18 tipos de acción (BANDA, CORNER, FALTA, …).

---

## Estado de las fórmulas

⚠️ El archivo se edita en **Numbers** (Mac), que **no recalcula** las fórmulas Excel. Por eso las hojas agregadas (`EST.TOTAL`, `GOLES`, `TIEMPOS`, `EST. x COMP.`, `DASH_*`) tienen fórmulas sin valor cacheado: leer con `data_only=True` devuelve `None` o el texto literal de la fórmula.

**Excepción útil**: la fila de `J.HERRERO` en `EST.TOTAL` SÍ tiene valores cacheados de algún momento pasado. Sirve como **referencia de validación** para nuestras reimplementaciones.

---

## Estrategia adoptada (Opción A)

Reimplementamos los agregados en Python desde los datos crudos por partido. Tres ventajas:
1. Reproducible: el Excel deja de ser fuente de verdad, lo es `src/estadisticas_partidos.py`.
2. Sin dependencia de Excel/LibreOffice/Numbers para recalcular.
3. Permite cruzar con otros datos del proyecto (Oliver, Borg, lesiones).

**Validación**: cualquier agregado que calculemos para `J.HERRERO` debe coincidir con el cacheado en `EST.TOTAL` (ej: 72 goles totales).

---

## Modelo de datos en Google Sheets

Se añaden 3 hojas nuevas al Sheet maestro de Inter:

### Hoja `EST_PARTIDOS_RAW` — una fila por (partido × jugador)
| Col | Tipo | Descripción |
|---|---|---|
| `partido_id` | str | Slug único: `J1.BARCELONA` |
| `tipo` | str | `LIGA`, `AMISTOSO`, `PLAYOFF`, `COPA_ESPANA`, `COPA_MUNDO`, `COPA_REY`, `SUPERCOPA` |
| `competicion` | str | etiqueta legible: "Liga 25/26", "Copa España" |
| `rival` | str | "BARCELONA" |
| `fecha` | date | YYYY-MM-DD si está disponible |
| `dorsal` | int | |
| `jugador` | str | nombre normalizado |
| `min_1t` | int | minutos jugados 1ª parte (segundos / 60, redondeo) |
| `min_2t` | int | minutos jugados 2ª parte |
| `min_total` | int | suma |
| `convocado` | bool | aparece en la tabla aunque tenga 0 minutos |
| `participa` | bool | minutos > 0 |
| `goles_a_favor` | int | (goles que marcó él en este partido) |
| `goles_en_contra` | int | (goles encajados estando en pista) |
| `asistencias` | int | |

### Hoja `EST_EVENTOS_GOLES` — una fila por gol
| Col | Descripción |
|---|---|
| `partido_id` · `tipo` · `competicion` · `rival` · `fecha` | (mismos que arriba) |
| `minuto` | int (1..40) |
| `intervalo_5min` | "0-5", "5-10", … |
| `accion` | "EC.4x4", "AF.CONTRAATAQUE", … |
| `marcador` | "0-1" |
| `equipo_marca` | "INTER" o "RIVAL" |
| `goleador` | nombre o "RIVAL" |
| `asistente` | nombre o "" |
| `portero` | nombre del portero en pista |
| `cuarteto_1` `cuarteto_2` `cuarteto_3` | los 3 jugadores de campo |

### Hoja `_VISTA_EST_JUGADOR` — agregados por jugador (calculada)
Una fila por jugador con totales y por competición, lista para el dashboard.

---

## 🟡 Cosas a confirmar con Arkaitz

1. **Asistencias**: en cada hoja de partido, ¿solo se anotan asistencias de goles A FAVOR? ¿O también las del rival?
2. **Goles en contra "estando en pista"**: ¿se cuenta sólo el cuarteto de campo o también el portero? La columna M (PRESENCIA) parece dedicada al portero.
3. **Plantillas vacías** (J27, P49, CAJA NEGRA): ¿son partidos futuros aún por jugar o sobran? Mi pipeline las ignora.
4. **Marcador final**: no es trivial extraerlo del Excel actual. ¿Lo apuntas en algún campo concreto que no he visto?
5. **Hojas DASH_***: ¿quieres que el dashboard de Streamlit replique exactamente esas vistas o tienes en mente algo distinto?

## Siguientes pasos

1. Construir `src/estadisticas_partidos.py` con extractor + validación contra HERRERO.
2. Subir las 3 hojas al Sheet (vía service account, igual que el resto).
3. Tab `🏆 Estadísticas` en `dashboard/app.py`.
