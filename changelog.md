# Changelog — Proyecto Arkaitz

Registro cronológico del trabajo. Entradas más recientes arriba.

---

## 2026-04-22 — Análisis completo de ambos Excel + definición de arquitectura

### Archivos analizados
- `Datos_indiv.xlsx` — 12 hojas
- `Estadisticas_pruebas_CLAUDE.xlsx` — 68 hojas

### Estructura confirmada: Datos_indiv.xlsx

#### Hoja INPUT (fuente de verdad)
Cuatro tablas en paralelo, mismo fichero:
| Tabla | Columnas |
|---|---|
| T1 SESIONES | FECHA · SEMANA · TURNO (M/T) · TIPO SESIÓN · MINUTOS · COMPETICIÓN |
| T2 BORG | FECHA · TURNO · JUGADOR · BORG (0-10) |
| T3 PESO | FECHA · TURNO · JUGADOR · PESO PRE · PESO POST · H2O (L) |
| T4 WELLNESS | FECHA · JUGADOR · SUEÑO · FATIGA · MOLESTIAS · ÁNIMO · TOTAL (4-20) |

#### Hojas de visualización existentes
- **PESO SEMANA** — Peso PRE/POST/DIF por jugador, día y turno. Selector de semana por lunes.
- **BD PESO** — Base de datos filtrable con resumen (registros, max/min/media pre y post).
- **RPE v2** — Carga semanal: matriz jugador × día con Borg, minutos y carga total (Borg×min). Monotonía / Fatiga / ACWR en resumen.
- **RECUENTO** — Asistencia por jugador en toda la temporada: GYM / FÍSICO / TEC-TAC / RECUP / PARTIDO + estados S/A/L/N/D/NC con porcentajes. Detecta fechas faltantes.
- **SEMANAL v2** — Microciclo a microciclo (48 semanas): asistencia media, Borg medio, carga equipo.
- **PSE v2** — Carga individual acumulada: matriz jugador × semana (S1..S52).
- **WELLNESS v2** — Wellness semanal: S/F/M/Á + Σ por jugador y día, con media y días con datos.
- **WELLNESS DIARIO** — Heatmap jugador × fecha (190+ columnas de fechas).

#### Jugadores detectados
BARONA · CARLOS · CECILIO · CHAGUINHA · DANI · GARCIA · GONZALO · HARRISON · HERRERO · JAVI · PANI · PIRATA · RAUL · RAYA · RUBIO · OSCAR + otros (JUG 16 pendiente de aclarar)

### Estructura confirmada: Estadisticas_pruebas_CLAUDE.xlsx

#### Hojas de partido (una por partido)
Formato: `J1.BARCELONA`, `J2.CORDOBA`, ... `J25.INDUSTRIAS`, `PLAYOFF1..10`, `SUP.SEMI`, `C.E.CUARTOS/SEMI/FIN`, `C.M.TORREJON/SEMI/FIN`, `C.R.4ª..FIN`, Amistosos.
Contenido por hoja: rival · categoría · lugar · hora · rotaciones por jugador (hasta 8 rotaciones × 2 tiempos) con minutos exactos.

#### Hojas de estadísticas agregadas
- **GOLES** — Goles a favor por jugador y tipo: BANDA · CORNER · SAQUE CENTRO · FALTA · ABP 2ª JUGADA · 10M · PENALTI · FSB · SALIDA PRESIÓN · 4x4 · 1x1 BANDA · 2ª JUGADA · INC. PORTERO · 5x4 · 4x3 · 4x5 · 3x4 · CONTRA · ROBO ZONA ALTA · N.C. + TOTAL · PARTIDOS · MEDIA
- **TIEMPOS** — Minutos jugados por jugador y competición.
- **EST. x COMP.** — Estadísticas por competición: CONVOCA. · PARTICIPA · HH:MM:SS · MINUTOS · MIN/PART · GOLES · ASISTENCIAS · GOL+ASIS
- **EST.TOTAL** — Mismas métricas agregadas en toda la temporada.
- **CUARTETOS / PIVOT_CUARTETOS** — Rendimiento de combinaciones de cuarteto.

#### Competiciones
Liga 25/26 · Copa del Rey 25/26 · Copa España · Copa Mostoles · Copa Ribera · Supercopa · Amistosos

---

### Decisión de arquitectura

#### Propuesta adoptada: Google Ecosystem + Looker Studio

```
ENTRADA DE DATOS
├── Google Forms (jugadores) → Borg + Peso + Wellness tras cada sesión
├── Google Sheets - Hoja SESIONES (staff) → fecha, turno, tipo, minutos, competición  
├── Google Sheets - Hoja ESTADÍSTICAS (staff/preparador) → datos partido a partido
└── Google Sheets - Hoja FISIOS (fisioterapeutas) → lesiones, estados, notas médicas

ALMACENAMIENTO
└── Google Sheets (base de datos central)
    ├── Pestaña: sesiones
    ├── Pestaña: borg (desde Forms)
    ├── Pestaña: peso (desde Forms)
    ├── Pestaña: wellness (desde Forms)
    ├── Pestaña: estadisticas_partidos
    └── Pestaña: fisio_jugadores

AUTOMATIZACIÓN
└── Google Apps Script
    ├── Envío semiautomático del Form tras cada sesión
    ├── Alertas de Borg/Wellness fuera de rango
    └── Resumen automático semanal por email/WhatsApp

VISUALIZACIÓN
└── Looker Studio (Google Data Studio)
    ├── Dashboard CARGA (RPE, Borg, ACWR, Monotonía, Fatiga)
    ├── Dashboard PESO (PRE/POST, pérdida hídrica, tendencias)
    ├── Dashboard WELLNESS (heatmap diario, alertas, evolución)
    ├── Dashboard ACELEROMETRÍA (cruce con Oliver Sports)
    └── Dashboard ESTADÍSTICAS (goles por tipo, minutos, competición, cuartetos)
```

**Por qué esta elección:**
- Sin servidor que mantener — todo en la nube de Google
- Acceso desde cualquier dispositivo con link
- Looker Studio: filtros interactivos nativos (jugador, competición, fecha, tipo), colores automáticos, gráficos de calidad
- Forms: validación estricta (desplegables, rangos numéricos), sin texto libre
- Cero coste

#### Nuevas métricas propuestas (cruce con acelerometría Oliver Sports)
1. **Índice de impacto neuromuscular** = carga RPE × PlayerLoad acelerométrico
2. **Ratio esfuerzo percibido vs. real** = Borg / PlayerLoad (detecta jugadores que subestiman carga)
3. **Fatiga acumulada multifuente** = ACWR + wellness descendente + pérdida de peso >2% + descenso PlayerLoad
4. **Zona de riesgo combinada** = semáforo rojo si ≥2 de los 4 indicadores anteriores en rojo
5. **Eficiencia de minutos en partido** = goles+asist / minutos jugados (estadísticas)

---

### Próximos pasos (en orden)
1. [x] Confirmar acceso a Google Workspace (cuenta de Google del equipo)
2. [x] Crear estructura Google Sheets base + migrar datos históricos
3. [x] Construir dashboard Streamlit completo (lee de Google Sheets, 6 secciones)
4. [ ] Publicar dashboard en Streamlit Cloud (URL pública permanente)
5. [ ] Diseñar y publicar Google Form para jugadores (Borg + Peso + Wellness vía WhatsApp)
6. [ ] Solicitar formato de exportación de Oliver Sports (para acelerometría)
7. [ ] Construir dashboard de estadísticas de partido (Estadisticas_pruebas_CLAUDE.xlsx)
8. [ ] Configurar Apps Script para envío automático del Form tras cada sesión
9. [ ] Formar al staff en el flujo de trabajo nuevo

---

## 2026-04-22 — Dashboard Streamlit completo

### `dashboard/app.py` — reescrito completo
- Lee directamente de Google Sheets (pestañas `_VISTA_*`)
- Sin necesidad de DuckDB para correr el dashboard
- Credenciales: local vía `google_credentials.json`, cloud vía `st.secrets`

### Secciones (6 tabs)
| Tab | Contenido |
|---|---|
| 🚦 **Semáforo** | Tarjetas por jugador (ACWR + Wellness + Δ Peso), KPIs del equipo, evolución ACWR temporal |
| 📊 **Carga** | Tabla RPE semanal con colores (como Excel), barras por sesión, heatmap PSE temporada, monotonía/fatiga |
| ⚖️ **Peso** | Tabla PRE/POST/DIF/% por semana, evolución temporal, boxplot deshidratación, alertas >2% |
| 💤 **Wellness** | Heatmap jugador×día (como Excel WELLNESS DIARIO), tabla semanal S/F/M/Á, gráfico de componentes por jugador |
| 🏥 **Lesiones** | Lesiones activas en rojo, historial completo, gráficos por zona y tipo |
| 📋 **Recuento** | Tabla de asistencia por jugador, gráfico de % participación |

### Características visuales
- Colores semáforo: 🟢 Verde (<1.3 ACWR, >13 wellness) · 🟠 Naranja · 🔴 Rojo (>1.5 ACWR, <10 wellness)
- Zonas de riesgo ACWR sombreadas en el gráfico
- Tablas con colores por valor (verde/amarillo/naranja/rojo según umbrales)
- Filtros globales en sidebar: jugadores y rango de fechas
- Botón de actualización de datos en tiempo real

---

## 2026-04-22 — Migración a Google Sheets

### Google Cloud
- Proyecto creado: `norse-ward-494106-q6`
- Cuenta de servicio: `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com`
- Credenciales guardadas en `google_credentials.json` (no subir a git)
- APIs habilitadas: Google Sheets API · Google Drive API

### Script de migración (`src/setup_gsheets.py`)
- Creado y ejecutado con éxito.
- Google Sheet: **Arkaitz - Datos Temporada 2526**
  - URL: https://docs.google.com/spreadsheets/d/19LVmQHLP3xovR8JRsdkTwqwobpL4ixYW7CnD3LeIWDk

### Pestaña LESIONES (nueva, `src/setup_lesiones.py`)
Diseñada en 4 bloques visuales con colores distintos:

| Bloque | Columnas | Quién lo rellena | Cuándo |
|---|---|---|---|
| **REGISTRO** (rojo) | Jugador · Fecha · Momento · Tipo · Zona · Lado · Mecanismo · Diagnóstico · Días est. · Pruebas · Notas | Fisio / Staff | Al producirse la lesión |
| **SEGUIMIENTO** (azul) | Estado · Fecha revisión · Tratamiento · Evolución · Vuelta prog. · Notas | Fisio | Durante la recuperación |
| **CIERRE** (verde) | Fecha alta · Días reales* · Diferencia* · Recaída · Baja anterior · Notas alta | Fisio | Al dar el alta |
| **SESIONES PERDIDAS** (naranja) | Total · Entrenos · GYM · Partidos · Recup · Minutos* | — | Automático |

*Calculado automáticamente con fórmulas que cruzan con la pestaña SESIONES.

**Formato condicional:**
- Fila amarilla → lesión activa (sin fecha de alta)
- Columna T naranja → tardó más días de lo estimado
- Columna T verde → se recuperó antes de lo previsto

### Datos migrados
| Pestaña | Filas | Detalles |
|---|---|---|
| SESIONES | 242 | Con desplegables: Turno (M/T/P) · Tipo · Competición |
| BORG | 3.702 | Con desplegable de jugadores y validación numérica 0-10 |
| PESO | 2.530 | Con desplegable de jugadores y validación kg (40-120) |
| WELLNESS | 2.738 | Con desplegable de jugadores y validación 1-5 por ítem |
| FISIO | — | Nueva pestaña vacía para fisioterapeutas |
| INSTRUCCIONES | — | Guía de uso con escalas Borg y Wellness |

### Pestaña FISIO (nueva)
Diseñada para fisioterapeutas con campos controlados:
- **Estado**: Disponible / Limitado / Baja / Vuelta progresiva / Duda
- **Tipo de lesión**: Muscular / Tendinosa / Articular / Ósea / Contusión / Sobrecarga / Fatiga / Otro
- **Zona corporal**: Tobillo / Rodilla / Muslo anterior / Isquiotibial / Aductor / Cadera / Lumbar / Abdominal / Hombro / Codo / Muñeca / Cabeza / Otro
- **Lado**: Derecho / Izquierdo / Bilateral / N/A
- **Días de baja estimados**: número (0-365)
- **Notas**: texto libre
- Formato visual con color por estado: verde (Disponible) · naranja (Limitado) · rojo (Baja)

---

## 2026-04-21 — Verificación del estado

- Streamlit levantado y funcionando sobre `data/temporada_2526.duckdb` (confirmado por el usuario).
- Estructura de carpetas consolidada: `data/raw/Datos_indiv.xlsx` presente, `src/{ingest,metrics,checks}.py` y `dashboard/app.py` operativos.
- Estado de la base de datos (recuentos actuales):
  - `sesiones`: 244 · rango 2025-07-30 → 2026-04-21
  - `borg`: 3.702
  - `peso`: 2.530
  - `wellness`: 2.738 *(corrige la estimación previa de 2.926; la cifra antigua era el conteo bruto del Excel antes de descartar filas sin jugador/fecha válidos).*
  - Vistas: `carga_sesion` (3.702 filas; 3.246 con carga no nula) y `calendario_semanal` (198 fechas). *Esta última no aparecía en la entrada previa pero ya está en `ingest.py`.*
- 19 jugadores distintos detectados. Aparece un nombre genérico `JUG 16` y faltan `NACHO`, `ANCHU`, `JAIME` frente a la plantilla declarada — a revisar con el staff si es limpieza de datos o plantilla cambiante.
- `requirements.txt` presente. `.venv/` creado pero vacío; las dependencias están resueltas contra el Python del sistema (`C:\Python311`). Pendiente: instalar en el venv o documentar la decisión.
- Pendiente: `README.md` con instrucciones de arranque (mencionado en la entrada anterior, aún no creado).

---

## 2026-04-21 — Arranque del proyecto

### Estructura inicial
- Creada la estructura de carpetas: `data/raw/`, `src/`, `notebooks/`, `dashboard/`.
- Añadido `changelog.md` (este archivo) y `README.md` con instrucciones de arranque.
- Añadido `requirements.txt` con las dependencias mínimas (duckdb, pandas, openpyxl, streamlit, plotly, numpy).

### Capa de ingesta (`src/ingest.py`)
- Lee `Datos_indiv.xlsx` (pestaña `INPUT`) y extrae las 4 tablas:
  - T1 SESIONES (cols A–F)
  - T2 BORG (cols H–K)
  - T3 PESO (cols M–R)
  - T4 WELLNESS (cols T–Z)
- Normaliza: estandariza nombres de jugadores (mayúsculas + trim), parsea fechas, tipa el Borg en dos columnas (`borg` numérico e `estado` con los códigos S/A/L/N/D/NC).
- Filtra filas especiales que no son jugadores reales (p. ej. `MEDIA`).
- Crea/actualiza `data/temporada_2526.duckdb` con las tablas `sesiones`, `borg`, `peso`, `wellness` + una vista derivada `carga_sesion` (Borg × minutos).

### Capa de métricas (`src/metrics.py`)
- Funciones para:
  - Carga individual por sesión (Borg × minutos).
  - Carga semanal (microciclo) por jugador y agregada del equipo.
  - Monotonía, fatiga, ACWR 1:4.
  - Baseline personal de peso y detección de desviaciones.
  - Wellness total diario y media semanal.
  - Semáforo de riesgo por jugador.
  - Correlación wellness ↔ carga.

### Capa de validaciones (`src/checks.py`)
- Valida nombres de jugadores contra plantilla.
- Rangos de Borg (0–10) y wellness (1–5).
- Duplicados en la clave natural `(fecha, turno, jugador)`.
- Reporta inconsistencias con un `DataFrame` de hallazgos.

### Dashboard (`dashboard/app.py`)
- Streamlit con secciones que reproducen el Excel:
  - **PESO SEMANA** — peso PRE/POST/DIF por día y turno.
  - **RPE semanal** — cargas por sesión con monotonía/fatiga.
  - **SEMANAL (temporada)** — microciclo a microciclo + gráficos de carga, ACWR y fatiga.
  - **PSE matriz** — jugador × semana con media del equipo.
  - **Wellness semanal** y **Wellness diario (heatmap)**.
  - **Recuento** — asistencia y completitud por jugador.
- Vistas nuevas:
  - **Semáforo de riesgo** — combina ACWR fuera de rango, wellness bajo sostenido, pérdida de peso anómala y monotonía alta.
  - **Correlación wellness ↔ carga** — scatter y coeficiente por jugador.

### Validación de la ingesta
- Ejecutado `python src/ingest.py`. DuckDB creado correctamente.
- Recuentos esperados (tomados del Excel): 244 sesiones, 3.702 registros de Borg, 2.530 de peso, 2.926 de wellness.

---
