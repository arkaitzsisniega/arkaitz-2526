# 🏥 Sheet de Lesiones y Tratamientos para fisios

Documento separado del Sheet principal donde los fisios y Arkaitz
introducen lesiones y tratamientos. Los fisios **solo** tienen acceso
a este documento, no al principal.

---

## Por qué un Sheet separado

- El Sheet principal contiene datos sensibles del primer equipo
  (carga, peso, wellness, estadísticas de partido…) que los fisios
  no necesitan ver.
- Los datos médicos tienen requisitos de confidencialidad. Aislar
  el documento limita el daño en caso de fuga.
- Los fisios pueden tener su propio flujo de trabajo sin interferir
  con el resto.

---

## 🔧 Setup inicial (UNA SOLA VEZ)

### Paso 1: Crear el Sheet a mano

La cuenta de servicio de Google **no puede** crear Sheets nuevos
(no tiene cuota de Drive). Los crea Arkaitz desde su cuenta.

1. Ve a https://sheets.google.com → **`+ En blanco`** (Sheet vacío).
2. **Renombra** el documento (arriba a la izquierda) a:
   ```
   Arkaitz - Lesiones y Tratamientos 2526
   ```
3. **Compartir** (botón arriba a la derecha):
   - Escribe el email de la cuenta de servicio:
     ```
     arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com
     ```
   - Permiso: **Editor**
   - Pulsa **Enviar**

### Paso 2: Ejecutar el script de configuración

Desde la terminal:
```bash
cd /Users/mac/Desktop/Arkaitz
/usr/bin/python3 src/crear_sheet_fisios.py
```

Esto crea automáticamente las hojas:
- `LESIONES` con la misma estructura que la del Sheet principal
- `TRATAMIENTOS` desde cero
- `JUGADORES` (sincronizada con tu roster principal)
- `_META` (config interna)

Y migra las lesiones existentes del Sheet principal al nuevo.

### Paso 3: Ejecutar el cálculo de vistas

```bash
/usr/bin/python3 src/calcular_vistas_fisios.py
```

Esto rellena automáticamente:
- Días de baja real (fecha alta − fecha lesión)
- Sesiones perdidas (cruzando con SESIONES del Sheet principal)
- Resumen por jugador
- Vistas que el dashboard usa

### Paso 4: Compartir con los fisios

Cuando ya estés satisfecho con el setup:
1. En el Sheet de fisios → **Compartir**
2. Email del fisio (Pelu, etc.) → permiso **Editor** → Enviar
3. **NO** les des acceso al Sheet principal

---

## 📝 Cómo se rellena el día a día

### Opción A: Directamente en el Sheet (recomendado)

Los fisios abren el Sheet y rellenan:
- **Hoja LESIONES**: una fila por lesión nueva (jugador, fecha, zona, tipo…)
- **Hoja TRATAMIENTOS**: una fila por tratamiento (fecha, jugador, tipo, zona, duración…)

Validaciones:
- `jugador` debe coincidir con el nombre exacto del roster (ver hoja JUGADORES).
- Las columnas marcadas como **calculadas** (días baja real, sesiones
  perdidas, etc.) **NO se rellenan a mano** — las calcula el script.

### Opción B: Google Forms (futuro, más cómodo desde móvil)

Recomendado más adelante: crear dos Google Forms (uno para
lesiones y otro para tratamientos) que los fisios rellenen desde
el móvil. Las respuestas caen automáticamente en el Sheet.

Cuando lo quieras, dímelo y te genero los Forms con los campos exactos.

---

## 🔄 Cuándo ejecutar `calcular_vistas_fisios.py`

- **Cada vez que añades o modificas lesiones manualmente** en el Sheet.
- **Después de cada `/consolidar`** del bot (lo automatizaremos).
- **Cuando se cierre una lesión** (rellenas `fecha_alta`).

El script es **idempotente**: ejecutarlo varias veces no rompe nada.

---

## 🗂️ Estructura del Sheet

### Hoja `LESIONES`

| Columna | Tipo | ¿Quién rellena? |
|---|---|---|
| `id_lesion` | L0001, L0002… | Auto (script) |
| `jugador` | NOMBRE | Manual |
| `dorsal` | int | Auto desde JUGADORES |
| `fecha_lesion` | YYYY-MM-DD | Manual |
| `momento` | ENTRENO/PARTIDO/GYM | Manual |
| `tipo_lesion` | MUSCULAR/LIGAMENTOSA/… | Manual |
| `zona_corporal` | MUSLO/RODILLA/… | Manual |
| `lado` | IZQUIERDA/DERECHA/BILATERAL/N.A. | Manual |
| `mecanismo` | CONTACTO/NO_CONTACTO/SOBREUSO/… | Manual |
| `diagnostico` | texto libre | Manual |
| `dias_baja_estimados` | int | Manual |
| `pruebas_medicas` | texto libre | Manual |
| `notas_iniciales` | texto libre | Manual |
| `estado_actual` | ACTIVA/EN_RECUP/ALTA/RECAÍDA | Auto (calculado) |
| `fecha_revision` | YYYY-MM-DD | Manual |
| `tratamiento` | texto libre | Manual |
| `evolucion` | texto libre | Manual |
| `vuelta_programada` | YYYY-MM-DD | Manual |
| `notas_seguimiento` | texto libre | Manual |
| `fecha_alta` | YYYY-MM-DD | Manual al cerrar |
| `dias_baja_real` | int | **Auto** |
| `diferencia_dias` | int | **Auto** |
| `recaida` | SÍ/NO | Manual |
| `baja_anterior` | SÍ/NO | Manual |
| `notas_alta` | texto libre | Manual |
| `total_sesiones` | int | **Auto** |
| `entrenos_perdidos` | int | **Auto** |
| `gym_perdidos` | int | **Auto** |
| `partidos_perdidos` | int | **Auto** |
| `recup_perdidos` | int | **Auto** |
| `minutos_perdidos` | float | **Auto** |

### Hoja `TRATAMIENTOS`

| Columna | Tipo | ¿Quién rellena? |
|---|---|---|
| `id_tratamiento` | T0001, T0002… | Auto |
| `fecha` | YYYY-MM-DD | Manual |
| `jugador` | NOMBRE | Manual |
| `dorsal` | int | Auto |
| `fisio` | nombre del fisio | Manual |
| `tipo_tratamiento` | MASAJE/ELECTRO/PUNCIÓN_SECA/… | Manual |
| `zona` | zona del cuerpo | Manual |
| `lado` | IZDA/DCHA/N.A. | Manual |
| `duracion_min` | int | Manual |
| `es_vendaje` | SÍ/NO | Manual |
| `id_lesion_relacionada` | L0001 (vacío si preventivo) | Manual |
| `preventivo_o_curativo` | PREVENTIVO/CURATIVO | Manual |
| `observaciones` | texto libre | Manual |

### Hojas vista (auto)

- `_VISTA_LESIONES`: tabla limpia con todas las lesiones
- `_VISTA_RESUMEN`: agregado por jugador (lesiones totales, días baja
  totales, última lesión, etc.)
- `_VISTA_TRATAMIENTOS_RESUMEN`: tratamientos por jugador

---

## 🔐 Privacidad y permisos

- **Cuenta de servicio**: Editor (necesario para que los scripts lean/escriban).
- **Arkaitz**: Editor (creador del Sheet, control total).
- **Fisios**: Editor solo de este Sheet (no tienen acceso al principal).

Cuando un usuario que **no sea fisio/médico/admin** acceda al
dashboard principal, los nombres de las lesiones aparecerán
**anonimizados por dorsal** ("el 8 se ha lesionado" en vez de "RAYA").
Esto se implementa en la pestaña Lesiones del dashboard cuando
montemos el sistema de roles (apuntado en `docs/estado_proyecto.md`).
