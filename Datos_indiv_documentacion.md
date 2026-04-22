# Documentación técnica — `Datos_indiv.xlsx`

**Proyecto:** Datos aplicados a fútbol sala (indoor soccer)
**Archivo:** `Datos_indiv.xlsx`
**Objetivo:** Registro individual de carga, peso, RPE/BORG y wellness por jugador a lo largo de la temporada.

---

## 1. Visión general

El libro está organizado en torno a **una única pestaña de entrada (`INPUT`)** y múltiples pestañas derivadas que consultan esa fuente mediante fórmulas (`SUMPRODUCT`, `SUMIFS`, `COUNTIFS`, `AVERAGEIFS`, `LET`, arrays dinámicos, etc.). Tres pestañas ocultas (prefijo `_`) alimentan las listas desplegables y el calendario semanal.

**Temporada cubierta:** 2025-07-28 (pretemporada) → 2026-06-22 aprox. (fin de temporada 2025/26).

**Plantilla de jugadores** (25 slots, algunos vacíos como `J21`–`J25`):

> HERRERO, GARCIA, OSCAR, CECILIO, CHAGUINHA, RAUL, HARRISON, RAYA, JAVI, PANI, PIRATA, BARONA, CARLOS, GONZALO, SEGO, RUBIO, DANI, JAIME, ANCHU, NACHO, J21, J22, J23, J24, J25

**Mapa de pestañas:**

| Pestaña | Tipo | Propósito |
|---|---|---|
| `INPUT` | Entrada | Única hoja donde se introducen datos crudos (4 tablas). |
| `PESO SEMANA` | Visualización | Peso PRE/POST por jugador, día y turno — vista de una semana. |
| `BD PESO` | Base de datos | Histórico longitudinal de pesajes. |
| `RPE v2` | Visualización | Control de carga y asistencia por sesión de una semana. |
| `RECUENTO` | Visualización | Recuento de sesiones por jugador y tipo + estados de asistencia. |
| `SEMANAL v2` | Visualización | Resumen de cargas por microciclo — toda la temporada + **4 gráficos**. |
| `PSE v2` | Visualización | Carga semanal (Borg × minutos) por jugador — matriz jugador × semana. |
| `WELLNESS v2` | Visualización | Wellness diario (sueño, fatiga, molestias, ánimo) de una semana. |
| `WELLNESS DIARIO` | Visualización | Matriz jugador × fecha con el `TOTAL` wellness del día. |
| `_LISTAS_PESO` | Auxiliar | Listas dinámicas para desplegables (peso). |
| `_LISTAS_WELLNESS` | Auxiliar | Listas dinámicas para desplegables (wellness). |
| `_Lunes` | Auxiliar | Lista maestra de lunes del año. |

---

## 2. Pestaña `INPUT` — Fuente única de datos

La pestaña contiene **4 tablas independientes** dispuestas en bloques de columnas. Las columnas `G`, `L`, `O`(entre T3 y T4, en la posición `S`) funcionan como separadores visuales.

### T1 · SESIONES (columnas A–F)

| Col | Campo | Descripción |
|---|---|---|
| A | `FECHA` | Fecha de la sesión. |
| B | `SEMANA` | Número de semana ISO. **Fórmula:** `=IFERROR(ISOWEEKNUM(A3),"")` |
| C | `TURNO` | `M` (mañana) o `T` (tarde). |
| D | `TIPO SESIÓN` | `FISICO`, `GYM`, `TEC-TAC`, `RECUP`, `PARTIDO`. |
| E | `MINUTOS` | Duración de la sesión. |
| F | `COMPETICIÓN` | Fase (p. ej. `PRE-TEMPORADA`, liga, etc.). |

### T2 · BORG (columnas H–K)

| Col | Campo | Descripción |
|---|---|---|
| H | `FECHA` | Fecha de la sesión. |
| I | `TURNO` | `M` / `T`. |
| J | `JUGADOR` | Nombre del jugador. |
| K | `BORG` | Valoración subjetiva de esfuerzo (escala 1–10; también se admite `N` para "no jugó"). |

### T3 · PESO (columnas M–R)

| Col | Campo | Descripción |
|---|---|---|
| M | `FECHA` | Fecha del pesaje. |
| N | `TURNO` | `M` / `T`. |
| O | `JUGADOR` | Nombre del jugador. |
| P | `PESO PRE` | Peso antes de la sesión (kg). |
| Q | `PESO POST` | Peso tras la sesión (kg). |
| R | `H2O (L)` | Pérdida hídrica en litros. **Fórmula:** `=IFERROR(P3-Q3,"")` |

### T4 · WELLNESS (columnas T–Z)

| Col | Campo | Descripción |
|---|---|---|
| T | `FECHA` | Fecha del reporte (normalmente diario). |
| U | `JUGADOR` | Nombre del jugador. |
| V | `SUEÑO` | Escala 1–5. |
| W | `FATIGA` | Escala 1–5. |
| X | `MOLESTIAS` | Escala 1–5. |
| Y | `ÁNIMO` | Escala 1–5. |
| Z | `TOTAL` | Suma de los cuatro. **Fórmula:** `=SUM(V3:Y3)` |

**Ayudas de navegación (fila 1):** enlaces internos `HYPERLINK` que saltan a la próxima fila vacía de cada tabla, p. ej.

```excel
=HYPERLINK("#'INPUT'!A"&(COUNTA($A$3:$A$5000)+3),"▼ Siguiente fila vacía — TABLA 1 SESIONES")
```

**Rangos de fórmulas:** las pestañas derivadas leen `INPUT!$X$3:$X$5000` (o `$X$1000` en algunos casos), por lo que hay capacidad para ~5.000 filas por tabla.

---

## 3. Pestaña `PESO SEMANA` — Vista semanal de peso

**Propósito:** mostrar `PESO PRE`, `PESO POST` y `DIF` (diferencia) de cada jugador para los 7 días de una semana concreta, separando turnos de mañana y tarde.

**Control del usuario:** celda `B3` contiene un **desplegable** con los lunes válidos (leído de `_LISTAS_PESO` / `_Lunes`). El número de semana (`B2`) y el año (`D2`) se calculan automáticamente.

**Diseño:**

- Fila 4: cabeceras dinámicas `="LUNES "&TEXT($B$3+0,"dd-mm-yyyy")` … hasta `DOMINGO ($B$3+6)`.
- Cada día ocupa 3 columnas: `PRE | POST | DIF`.
- Filas 6 en adelante: un par de filas por jugador (una para `M`, otra para `T`).

**Fórmulas tipo:**

`PRE` (ejemplo celda `D6`, jugador HERRERO, turno M, día Lunes):

```excel
=IFERROR(IF(SUMPRODUCT((INPUT!$M$3:$M$1000=$B$3+0)
                      *(INPUT!$N$3:$N$1000="M")
                      *(INPUT!$O$3:$O$1000="HERRERO"))=0,
            "",
            SUMPRODUCT((INPUT!$M$3:$M$1000=$B$3+0)
                      *(INPUT!$N$3:$N$1000="M")
                      *(INPUT!$O$3:$O$1000="HERRERO")
                      *INPUT!$P$3:$P$1000)),"")
```

`POST` es idéntica cambiando `$P` por `$Q`. `DIF` es `=IFERROR(IF(OR(D6="",E6=""),"",D6-E6),"")`.

**Fuente de datos:** tabla T3 (`INPUT!M:R`).

---

## 4. Pestaña `BD PESO` — Histórico de pesajes

**Propósito:** base de datos plana con todos los registros de peso de la temporada (hasta ~5.000 filas). Se usa como origen para derivar listas de fechas disponibles y para análisis longitudinal.

**Columnas esperadas:** `FECHA | TURNO | JUGADOR | PESO PRE | PESO POST | H2O (L)`, reflejando T3 de `INPUT`.

**Observación técnica:** el rango declarado llega hasta la fila 5007 con entradas presentes en los primeros miles; las filas vacías del final son espacio reservado para futuras temporadas.

---

## 5. Pestaña `RPE v2` — Control de cargas y asistencia semanal

**Propósito:** calcular la carga de entrenamiento individual (Borg × minutos) sesión a sesión para una semana concreta, con métricas derivadas de fatiga y monotonía.

**Diseño:**

- Cabecera de columnas con los 7 días × 2 turnos (M/T) = hasta 14 sesiones.
- Filas por jugador con su Borg de cada sesión.
- Bloque final de resúmenes (filas 33–42 aprox.):

| Fila | Métrica | Fórmula representativa |
|---|---|---|
| `ASISTENCIA` | nº jugadores con registro | `=COUNT(C7:C31)` |
| `BORG MEDIO` | media de Borg por sesión | `=IFERROR(AVERAGE(C10:C31),"")` |
| `CARGA SESIÓN` | Borg medio × minutos | `=IFERROR(IF(C34="","",C34*C$6),"")` |
| `CARGA DIARIA` | suma M+T | `=IFERROR(IF(AND(C35="",D35=""),"",N(C35)+N(D35)),"")` |
| `CARGA TOTAL SEMANAL` | suma de cargas de la semana | — |
| `CARGA MEDIA` | media de cargas distintas de 0 | — |
| `DESVIACIÓN ESTÁNDAR` | `STDEV` sobre las cargas diarias | — |
| `MONOTONÍA` | media / desviación | `=IFERROR(C39/C40,"")` |
| `FATIGA` | carga total × monotonía | `=IFERROR(C38*C41,"")` |

**Fuente:** tablas T1 (`MINUTOS`, `TIPO SESIÓN`) y T2 (`BORG`).

---

## 6. Pestaña `RECUENTO` — Completitud de sesiones

**Propósito:** auditoría de qué jugadores han tenido datos registrados por tipo de sesión, con rango de fechas configurable.

**Controles:** celdas `B2` (`DESDE`) y `E2` (`HASTA`) permiten limitar el rango temporal del recuento.

**Columnas principales:**

`Nº | JUGADOR | GYM | FÍSICO | TEC-TAC | RECUP | PARTIDO | ENTRENOS | % ENT | S (Sel.) | % S | A (Aus.) | % A | L (Les.) | % L | N (No jug.) | % N | D (Des.) | % D | NC (No Conv.) | % NC | SESIONES TOTALES | DIFERENCIA | FECHAS QUE FALTAN`

**Códigos de estado** (aparecen en `INPUT` T2 col `BORG` cuando no hay valor numérico): `S` Seleccionado · `A` Ausente · `L` Lesionado · `N` No jugó · `D` Descansando · `NC` No convocado.

**Fórmula tipo (COUNTIFS con filtro por rango):**

```excel
=COUNTIFS(INPUT!$H$3:$H$5000,">="&$B$2,
          INPUT!$H$3:$H$5000,"<="&$E$2,
          INPUT!$J$3:$J$5000,"HERRERO",
          INPUT!$K$3:$K$5000,"S")
```

**Indicador visual:** la columna `DIFERENCIA` marca completitud:
`=IF($V$31-V5<=0,"✓ OK","⚠ FALTAN "&($V$31-V5))`.

---

## 7. Pestaña `SEMANAL v2` — Cargas por microciclo (temporada completa)

**Propósito:** panel de temporada con un microciclo (semana) por columna. **Incluye 4 gráficos** que visualizan la evolución a lo largo de la temporada.

**Control del usuario:** celda `B2` (`PRIMER LUNES`) determina el origen; el resto de semanas se calculan como `B2 + (n-1)*7`.

**Estructura de filas:**

| Fila | Métrica | Notas |
|---|---|---|
| 4 | `MICROCICLO` | 1, 2, 3… (número secuencial). |
| 5 | `FECHA LUNES` | `=$B$2+(B4-1)*7` |
| 6 | `SEMANA` | `=ISOWEEKNUM(B5)` |
| 7 | `ASIST. MEDIA` | fórmula array de asistencia semanal. |
| 8 | `BORG MEDIO` | media semanal de Borg. |
| 9 | `CARGA TOTAL` | Σ (Borg × minutos) de la semana. |
| 10 | `MINUTOS` | suma de `INPUT!E` en rango `[lunes, lunes+6]` vía `LET`/`SUMIFS`. |
| 11 | `MONOTONÍA` | `AVERAGE / STDEV` de la carga diaria (L–D). |
| 12 | `FATIGA` | `CARGA TOTAL × MONOTONÍA`. |
| 13 | `ACWR (1:4)` | ratio agudo:crónico (última semana / media 4 semanas). |
| 14–20 | `LUN` … `DOM` | carga diaria desglosada, fórmulas array. |

**Fórmula de minutos semanales:**

```excel
=IFERROR(LET(x,SUMIFS(INPUT!$E$3:$E$5000,
                      INPUT!$A$3:$A$5000,">="&B5,
                      INPUT!$A$3:$A$5000,"<="&B5+6),
            IF(x=0,NA(),x)),NA())
```

**Gráficos detectados:** 4 objetos de gráfico (típicamente líneas para carga, fatiga y ACWR — los títulos no están en texto rich legible desde el dump).

---

## 8. Pestaña `PSE v2` — Carga semanal por jugador

**Propósito:** matriz **jugador × semana** con la carga semanal individual (Σ Borg × minutos). Espacio reservado para ~48+ semanas (`S1 … S48+`).

**Estructura:**

- Fila 2: `PRIMER LUNES` toma valor de `'SEMANAL v2'!B2` (sincronizado con el otro panel).
- Fila 3: fechas de lunes de cada semana (`=$B$2`, `=C3+7`, …).
- Fila 4: cabeceras `S1`, `S2`, …
- Filas 5–29: 25 jugadores (slots fijos). Cada celda es un array formula que evalúa la carga individual de ese jugador en esa semana.
- Fila 30: `MEDIA EQUIPO` con `AVERAGEIFS` sobre cargas positivas:
  ```excel
  =IFERROR(AVERAGEIFS(C8:C29,C8:C29,">0"),0)
  ```

**Fuente:** combinación de T1 (MINUTOS) y T2 (BORG) filtradas por jugador y por rango semanal.

---

## 9. Pestaña `WELLNESS v2` — Wellness de una semana

**Propósito:** vista semanal de la tabla T4 (`SUEÑO`, `FATIGA`, `MOLESTIAS`, `ÁNIMO`) por jugador y día, con totales y promedios.

**Control:** desplegable en la parte superior (típicamente `I2`) para elegir el lunes.

**Estructura por día** (bloque de 5 columnas × 7 días):

`S (SUEÑO) | F (FATIGA) | M (MOLESTIAS) | Á (ÁNIMO) | Σ (suma diaria)`

Más dos columnas finales: `MEDIA` (promedio de los `Σ` diarios) y `DÍAS` (número de días con datos registrados).

**Fórmulas tipo:**

```excel
Σ diaria       : =IFERROR(IF(COUNT(C5:F5)=0,"",SUM(C5:F5)),"")
MEDIA semanal  : =IFERROR(AVERAGE(G5,L5,Q5,V5,AA5,AF5,AK5),"")
DÍAS con datos : =(COUNT(C5:F5)>0)*1 + (COUNT(H5:K5)>0)*1 + … + (COUNT(AH5:AK5)>0)*1
```

**Fuente:** tabla T4 (`INPUT!T:Z`).

---

## 10. Pestaña `WELLNESS DIARIO` — Matriz jugador × fecha

**Propósito:** vista "heatmap" con un jugador por fila y una fecha por columna; cada celda es la **suma TOTAL de wellness** (`SUEÑO+FATIGA+MOLESTIAS+ÁNIMO`) de ese jugador en ese día.

**Cabecera fila 1:** "WELLNESS DIARIO — Suma por jugador y día".
**Cabecera fila 2:** `JUGADOR | <fecha 1> | <fecha 2> | …` (cada fecha del dataset, hasta 190 columnas).
**Filas 3–20:** una fila por jugador; contenido generado por array formulas que buscan la entrada correspondiente en T4.

Uso típico: detectar a ojo desviaciones, faltas de datos y patrones a lo largo del tiempo.

---

## 11. Pestañas auxiliares (`_LISTAS_PESO`, `_LISTAS_WELLNESS`, `_Lunes`)

### `_LISTAS_PESO`

Listas alimentadoras de los desplegables de la vista de peso. Cada columna es un array dinámico:

| Col | Rango | Contenido |
|---|---|---|
| A | `FECHAS_CON_PESO` | Fechas distintas con pesajes registrados (ordenadas). |
| C | `AÑOS` | Años presentes en los datos (actualmente `2026`). |
| E | `SEMANAS_DEL_AÑO_SELECCIONADO` | Números de semana con datos en el año elegido. |
| G | `LUNES_CON_DATOS` | Lunes con registros de peso. |
| I | `JUGADORES_PESO` | Nombres únicos de jugadores que han sido pesados. |
| K | `JUGADORES_CON_TODOS` | Plantilla completa (incluye `TODOS` para filtros sin jugador fijo). |

### `_LISTAS_WELLNESS`

Análoga a la anterior, pero sobre T4:

| Col | Rango | Contenido |
|---|---|---|
| A | `FECHAS_CON_WELLNESS` | Fechas distintas con entradas de wellness. |
| C | `LUNES_CON_DATOS` | Lunes con registros de wellness. |

### `_Lunes`

Columna única con la lista maestra de **todos los lunes** del calendario cubierto por el libro (366 filas ≈ 7 años). Actúa como calendario de referencia del que se derivan los lunes válidos para los desplegables.

---

## 12. Resumen de dependencias entre pestañas

```
INPUT  ─┬──▶ PESO SEMANA       (SUMPRODUCT sobre T3)
        ├──▶ BD PESO           (copia/histórico)
        ├──▶ RPE v2            (COUNT/AVERAGE/STDEV sobre T2 + T1 minutos)
        ├──▶ RECUENTO          (COUNTIFS sobre T2 estados)
        ├──▶ SEMANAL v2        (SUMIFS/LET sobre T1+T2)  ──▶ 4 gráficos
        ├──▶ PSE v2            (array formulas de Borg × minutos)
        ├──▶ WELLNESS v2       (SUMPRODUCT sobre T4)
        └──▶ WELLNESS DIARIO   (SUMPRODUCT sobre T4)

_Lunes ──────────▶ _LISTAS_PESO ──┐
                   _LISTAS_WELLNESS┴──▶ Desplegables (Data Validation)
```

---

## 13. Notas técnicas para el proyecto de análisis

Aspectos a tener en cuenta a la hora de convertir este modelo en un pipeline de datos o un dashboard externo:

- **Fuente única limpia:** toda la inteligencia nace de la pestaña `INPUT` (≤ 5.000 filas por tabla). Es el único punto donde se *escribe*. Cualquier proceso ETL debería partir de las 4 tablas separando por columnas (A–F, H–K, M–R, T–Z).
- **Claves implícitas:** no hay ID de sesión ni de jugador único; la clave compuesta natural es `(FECHA, TURNO, JUGADOR)`. Tener en cuenta que los jugadores se identifican por **apodo/apellido en mayúsculas**.
- **Códigos no numéricos en `BORG`:** la columna K acepta tanto números 1–10 como códigos de estado (`S`, `A`, `L`, `N`, `D`, `NC`). Convertir con cuidado si se cargan en un tipo numérico.
- **Uso intensivo de arrays dinámicos:** muchas celdas son `ArrayFormula` (requieren Excel 365 o equivalente). Al exportar a otros formatos las fórmulas se evalúan y producen valores estáticos.
- **Rango temporal:** 2025-07-28 → ~2026-06-22 (primera temporada). Los lunes futuros ya están pre-cargados en `_Lunes` y en las listas auxiliares.
- **Métricas clave que ya están calculadas en el libro** (reusar en el nuevo sistema): asistencia, Borg medio, carga sesión/diaria/semanal, monotonía, fatiga, ACWR 1:4, TOTAL wellness.
- **Ausencia de gráficos salvo en `SEMANAL v2`:** el resto de pestañas funcionan como tablas/heatmaps planos; todos los gráficos detectables (4) están concentrados en `SEMANAL v2`.
