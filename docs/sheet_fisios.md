# 🏥 Sheet de Lesiones, Tratamientos y Temperatura para fisios

Documento separado del Sheet principal con **3 pestañas principales**
para que los fisios y Arkaitz introduzcan datos. Los fisios solo tienen
acceso a este documento, no al principal.

URL: la del Sheet `Arkaitz - Lesiones y Tratamientos 2526` que ya creaste.

---

## Estructura

| Pestaña | Cuándo se rellena |
|---|---|
| **🔴 LESIONES** | Cuando un jugador se retira de un entrenamiento o partido y va a perder sesiones |
| **🟢 TRATAMIENTOS** | Cada vez que un fisio aplica algo: PRE entreno, POST entreno, o tratamiento al jugador lesionado durante la sesión |
| **🟠 TEMPERATURA** | Cada vez que se hace una medición con la cámara térmica para detectar asimetrías |
| `JUGADORES` | Referencia (auto-sincronizada con el roster del Sheet principal) |
| `_LISTAS` | Opciones de los dropdowns (oculta) |
| `_META` | Metadatos internos (oculta) |
| `_VISTA_*` | Tablas calculadas que consume el dashboard (ocultas) |

**Todas las celdas tienen dropdown** salvo:
- IDs (auto-generados)
- Diagnóstico y notas (texto libre)
- Columnas calculadas (las rellena el script automáticamente)

---

## 🔴 LESIONES — qué meter

| Columna | Tipo | Cómo se rellena |
|---|---|---|
| `id_lesion` | L0001… | Auto |
| `fecha_lesion` | fecha | Manual |
| `turno` | M / T / P | Dropdown |
| `tipo_sesion` | ENTRENO / PARTIDO / GYM / RECUP / GYM+TEC-TAC / FISICO+TEC-TAC / MATINAL / PORTEROS / FISICO / TEC-TAC / AMISTOSO | Dropdown |
| `jugador` | (lista de tu roster) | Dropdown |
| `dorsal` | int | Auto desde JUGADORES |
| `zona_corporal` | (lista de zonas) | Dropdown |
| `lado` | IZDA / DCHA / BILATERAL / N.A. | Dropdown |
| `tipo_tejido` | MUSCULAR / TENDINOSA / LIGAMENTOSA / ÓSEA / ARTICULAR / CARTILAGINOSA / MENISCAL / CONTUSIÓN / ESGUINCE / FRACTURA / NEUROLÓGICA / OTRO | Dropdown |
| `mecanismo` | CONTACTO / NO_CONTACTO / SOBREUSO / RECIDIVA / MAL_GESTO / DESCONOCIDO / OTRO | Dropdown |
| `gravedad` | LEVE / MODERADA / GRAVE | Dropdown |
| `dias_baja_estimados` | número | Manual |
| `pruebas_medicas` | NINGUNA / ECO / RM / RX / TAC / ANÁLISIS / VARIAS | Dropdown |
| `diagnostico` | texto libre | Manual |
| `estado_actual` | ACTIVA / EN_RECUP / ALTA / RECAÍDA | Dropdown (auto al cerrar) |
| `fecha_alta` | fecha | Manual al cerrar |
| `dias_baja_real` | número | **Auto** |
| `diferencia_dias` | número | **Auto** (real − estimado) |
| `total_sesiones_perdidas` | número | **Auto** |
| `entrenos_perdidos` | número | **Auto** |
| `partidos_perdidos` | número | **Auto** |
| `recaida` | SÍ / NO | Dropdown |
| `notas` | texto libre | Manual |

---

## 🟢 TRATAMIENTOS — qué meter

| Columna | Tipo | Cómo |
|---|---|---|
| `id_tratamiento` | T0001… | Auto |
| `fecha` | fecha | Manual |
| `turno` | M / T / P | Dropdown |
| `bloque` | **PRE_ENTRENO / POST_ENTRENO / LESIONADO** | Dropdown ⭐ |
| `jugador` | (roster) | Dropdown |
| `dorsal` | int | Auto |
| `fisio` | PELU / ARKAITZ / OTRO | Dropdown |
| `accion` | (lista larga: VENDAJE_FUNCIONAL, MASAJE, ELECTRO_TENS, PUNCIÓN_SECA, CRIOTERAPIA, READAPTACIÓN, etc.) | Dropdown |
| `zona_corporal` | (zonas) | Dropdown |
| `lado` | IZDA / DCHA / BILATERAL / N.A. | Dropdown |
| `duracion_min` | número | Manual |
| `id_lesion_relacionada` | L0001 (opcional) | Manual si es LESIONADO |
| `notas` | texto libre | Manual |

⭐ El campo `bloque` es la clave para distinguir:
- `PRE_ENTRENO`: vendajes, calentamiento, activación antes de entrenar
- `POST_ENTRENO`: descargas, recuperación tras entrenar
- `LESIONADO`: tratamiento al jugador lesionado mientras el resto entrena

Una **misma sesión puede tener varias filas**: una por jugador × tipo de
acción aplicada. Por ejemplo:
- 14:00 PRE_ENTRENO · CECILIO · vendaje_funcional · tobillo dcha · 5 min
- 14:00 PRE_ENTRENO · RAYA · masaje · cuádriceps izda · 8 min
- 16:30 POST_ENTRENO · BARONA · masaje_descarga · pantorrillas · 10 min

---

## 🟠 TEMPERATURA — qué meter

| Columna | Tipo | Cómo |
|---|---|---|
| `id_medicion` | M0001… | Auto |
| `fecha` | fecha | Manual |
| `turno` | M / T / P | Dropdown |
| `momento` | PRE_ENTRENO / POST_ENTRENO / PRE_PARTIDO / POST_PARTIDO / RECUP_24H / RECUP_48H / RECUP_72H | Dropdown |
| `jugador` | (roster) | Dropdown |
| `dorsal` | int | Auto |
| `zona` | (zonas térmicas: CUÁDRICEPS_ANT, ISQUIOTIBIALES_POST, ADUCTORES_INT, GLÚTEO, PANTORRILLA_POST, GEMELO_LATERAL, etc.) | Dropdown |
| `temp_izda_c` | °C (decimal con punto) | Manual |
| `temp_dcha_c` | °C | Manual |
| `asimetria_c` | °C | **Auto** (= izda − dcha) |
| `alerta` | "ALERTA" si \|asimetria\| > 0.5°C | **Auto** |
| `temp_ambiente_c` | °C | Manual |
| `notas` | texto libre | Manual |

> Una fila por **(jugador, zona, momento)**. Si mides 6 zonas a un
> jugador, son 6 filas. Igual para los demás.

---

## 🔄 Cuándo ejecutar `calcular_vistas_fisios.py`

```bash
cd /Users/mac/Desktop/Arkaitz
/usr/bin/python3 src/calcular_vistas_fisios.py
```

Lo recalcula:
- Días baja real, diferencia, sesiones perdidas (LESIONES)
- Asimetría y alerta (TEMPERATURA)
- Vistas resumen para el dashboard

Cuándo:
- **Después de añadir o modificar lesiones** manualmente.
- **Después de cada `/consolidar`** del bot (lo automatizaremos cuando confirmes que el flujo funciona).
- **Cuando se cierre una lesión** (rellenas `fecha_alta`).

Idempotente: ejecutarlo varias veces no rompe nada.

---

## 🔐 Privacidad y permisos

- **Cuenta de servicio**: Editor (necesario para que los scripts lean/escriban).
- **Arkaitz**: Editor.
- **Fisios**: Editor solo de este Sheet (NO del principal).

Cuando un usuario que no sea fisio/médico/admin acceda al dashboard
principal, los nombres de las lesiones aparecerán **anonimizados por
dorsal** ("el 8 se ha lesionado" en vez de "RAYA"). Apuntado en
`docs/estado_proyecto.md` para cuando montemos el sistema de roles.
