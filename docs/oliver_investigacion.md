# Investigación Oliver Sports — 23/04/2026 (actualizado 24/04/2026)

## Plataforma
- URL: `https://platform.oliversports.ai/#/main/team-managers`
- Versión: `2.0.35`
- Equipo: Inter Movistar — `team_id=1728` / `club_id=444`
- Usuario de Arkaitz: `user_id=32194`

## API REST
**Base**: `https://api-prod.tryoliver.com/v1/`

### Autenticación (confirmada funcionando)
Todas las peticiones requieren TODOS estos headers:
```
Authorization: Bearer <JWT_token>
Accept: application/json
x-user-id: 32194
x-version: 2.0.35
x-from: portal
```
El JWT se obtiene iniciando sesión; en el navegador vive en
`localStorage["OLIVER-Platform.session"].token` (~531 chars).
También hay `refresh_token` con misma longitud.

Si se usa solo `Authorization: Bearer ...` sin los demás → 401 Unauthorized.

### Endpoints descubiertos

| Método | Ruta | Qué devuelve |
|---|---|---|
| GET | `/v1/sessions/?team_id={team_id}` | Lista paginada de sesiones del equipo (`{sessions: [...], total, success}`). 250 por página. Total actual: **414 sesiones**. |
| GET | `/v1/sessions/{id}` | Metadata de una sesión: id, name, type (TRAINING/MATCH), start (ms unix), end, team_id, md_tag, status, indoor. |
| GET | `/v1/sessions/{id}/average?raw_data=1` | **⭐ El bueno**. Devuelve `player_sessions: [...]` con 14 jugadores y 68 métricas cada uno. |
| GET | `/v1/sessions/{id}/thresholds` | Umbrales (fijos o personales) usados en la plataforma. |
| GET | `/v1/player-sessions/` | Sesiones por jugador. |

### Estructura de una sesión (endpoint `/sessions/{id}`)
```json
{
  "session": {
    "id": 110057,
    "name": "Tec-tac",
    "type": "TRAINING",          // TRAINING | MATCH
    "team_id": 1728,
    "thresholds_id": 734,
    "workload_settings_id": 73,
    "status": "PROCESSED",
    "md_tag": "",                 // MD, MD-1, MD+1 etc.
    "start": 1776933837000,       // ms unix
    "end": 1776937954000,
    "indoor": 1,
    "created_at": "2026-04-23T09:52:54.000Z"
  }
}
```

### Estructura de `player_sessions` (una fila por jugador)
```json
{
  "id": 2084250,
  "player_id": 28433,
  "session_id": 110057,
  "oli_id": 5668,               // ID del sensor físico
  "status": "PROCESSED",
  "invalid_time": 0,
  "rpe": ...,                    // el Borg que mete Oliver (ojo, puede duplicar el tuyo)
  "player": { ... },             // info del jugador
  "player_session_info": {
    "metrics": { ... 68 métricas ... }
  }
}
```

## Las 68 métricas por jugador/sesión

### Movimiento
- `stats.speed.max`, `stats.speed.mean`, `stats.speed.dist`
- `stats.speed.segments.walking.{avg,count,dist,limits}`
- `stats.speed.segments.jogging.{avg,count,dist,limits}`
- `stats.speed.segments.lsprint.{avg,count,dist,limits}` (low sprint)
- `stats.speed.segments.sprint.{avg,count,dist,limits}`

### Aceleraciones/Deceleraciones (⭐ las que te interesan)
- `stats.acceleration.high.pos.{count,dist}` — Acc. alta intensidad
- `stats.acceleration.high.neg.{count,dist}` — Dec. alta intensidad
- `stats.acceleration.max.pos.{count,dist}` — Acc. máx intensidad
- `stats.acceleration.max.neg.{count,dist}` — Dec. máx intensidad
- `meter_minute_ratio.acc.{high,max}` — ratio por minuto
- `meter_minute_ratio.decc.{high,max}`

### Carga mecánica (⭐ "carga mecánica total")
- `oli_session_load` — índice agregado (Oliver Load)
- `oli_session_intensity.{intensity,acceleration,speed}`
- `meter_minute_ratio.total_distance_ratio` — m/min

### Metabólico
- `metabolic_power.avg_power`, `max_power`
- `metabolic_power.kcal_min`, `kcal_total`
- `metabolic_power.dist_high_intensity`, `dist_low_intensity`
- `metabolic_power.perc_high_intensity`, `time_high_intensity`
- `metabolic_power.total_energy`, `total_time_activity`

### Tiempo (⭐ "tiempo de juego activo")
- `played_time` — tiempo jugado efectivo
- `total_time` — tiempo total incluyendo paradas

### Técnicas (acciones del juego)
- `cods.{count, avg_angle, max_angle}` — cambios de dirección
- `dribbling.{count, dist}` — regates
- `jumps.{count, avg_height, max_height}` — saltos
- `kicks`, `low_kicks`, `medium_kicks`, `high_kicks`, `kick_power`

### Partes (solo para partidos)
- `halves.first_half`, `halves.second_half`

## Exports manuales
- La plataforma tiene botones **"Descargar XLS"** y **"Descargar CSV"** en cada vista de sesión (vista de equipo y vista de jugador).
- No probé a descargar por limitación de entorno; pero son generados en cliente desde los mismos datos de la API.
- **Conclusión: la API es el camino, no los exports manuales**.

## Plantilla del equipo (vista de jugadores)
14 jugadores por sesión. Puestos:
- Cierre: Jose Raya
- Ala Derecha: Bruno Chaguinha, Cecilio Morales, Harrison David, Sergio Barona, Sergio Rubio
- Ala Izquierda: Carlos Bartolomé, Francisco Pani, Javi Mínguez, Rodriguez (cortado)
- (faltan los de la página 2 de la plantilla)

## Bloqueantes / pendiente confirmar
1. **Caducidad del token JWT**: 531 chars. Probablemente 1-24h de vida. Hay `refresh_token` de la misma longitud → habrá endpoint de refresh (buscar `/v1/auth/refresh` o similar).
2. **Endpoint de login**: probable `/v1/auth/login` con `{username, password}` → `{token, refresh_token}`. No lo he probado en vivo.
3. **Rate limits**: desconocidos. Iteraremos con respeto (1 req/segundo).

## Propuesta de integración (borrador)

### Fase A: Script de sincronización
`src/oliver_sync.py`:
1. Login con usuario/password → guarda token en `.oliver_token` (gitignored).
2. Si token caducado → refresh.
3. Pide lista de sesiones del equipo 1728.
4. Compara con las ya sincronizadas (hoja `_VISTA_OLIVER_SESIONES`).
5. Para cada sesión nueva: `GET /sessions/{id}/average?raw_data=1` → aplana las 68 métricas × 14 jugadores.
6. Vuelca a hoja `OLIVER` en el Google Sheet.
7. Ejecuta `calcular_vistas.py` para actualizar vistas agregadas.

### Fase B: Integración con Sheet actual
Dos hojas nuevas:
- `OLIVER` — raw: 1 fila por (jugador × sesión × métrica), o mejor 1 fila por (jugador × sesión) con 68 columnas.
- `_VISTA_OLIVER` — agregaciones por jugador/semana: carga mecánica, aceleraciones totales, etc.

### Fase C: Nueva pestaña dashboard
**🏃 Oliver** con:
- Vista equipo: ranking de carga mecánica semanal
- Vista jugador: evolución temporal de Oliver Load, aceleraciones, etc.
- Cruces: 
  - `ACWR_Borg` (subjetivo) vs `Oliver Load` (objetivo) → detectar incoherencias
  - `Sprints` × `Lesiones blandas` por jugador
  - `HSR` (distancia alta intensidad) × `wellness` del día siguiente (fatiga real)

### Fase D: Métricas cruzadas (análisis)
- Semáforo de coherencia: si Borg=9 pero Oliver Load bajo → día mental flojo.
- Alertas: acumulado de aceleraciones máximas > umbral → riesgo lumbar.
- Rendimiento comparado: sprints por puesto.

## 🎯 TIMELINE minuto a minuto (descubierto 24/04/2026)

**Endpoint clave:**
```
GET /v1/player-sessions/{player_session_id}?include=player_session_info:attr:timeline
```

Descubierto interceptando la opción "Métricas por Minuto" del dropdown de
la vista de jugador. Devuelve el detalle **por minuto de sesión**.

### Estructura (ejemplo de una sesión de 67 min)

Cada métrica es un **array de N valores** donde N = `total_time` (minutos).
El valor en la posición `i` corresponde al minuto `i` de la sesión.

**Metadatos:**
- `total_time`: duración total en minutos (int).
- `session_prefix`: array con "antes de empezar" (calentamiento previo).
- `session_suffix`: array con "después de terminar".

**Métricas simples (array[N] por minuto):**
- `played_time` (0-1): fracción del minuto "en juego".
- `raw_activity_time` (0-1): fracción del minuto con actividad real.
- `active_rest_time` (0-1): fracción descanso activo.
- `top_speed` (m/s): velocidad máxima registrada en ese minuto.
- `cods` (int): cambios de dirección.
- `jumps` (int): saltos.
- `kicks` (int): golpeos (puede venir vacío).
- `oli_session_volume` (0-1): volumen de carga.

**Metabólico (`metabolic_power.*`, arrays[N]):**
- `kcal`: kcal quemadas ese minuto.
- `dist_high_intensity`: metros en alta intensidad.
- `dist_low_intensity`: metros en baja intensidad.
- `met_energy_high_intensity`, `met_energy_low_intensity`: energía metabólica (kJ/kg aprox).
- `perc_time_high_intensity`: % del minuto en alta intensidad.

**Intensidad Oliver (`oli_session_intensity.*`, arrays[N]):**
- `intensity`: índice compuesto (0-100).
- `acceleration`: intensidad de acc/dec (0-100).
- `speed`: intensidad de velocidad (0-100).

**Segmentos por zona de velocidad (`segments.*` y `segments_count.*`, arrays[N]):**
Por minuto, distancia y conteo de:
- `walking`, `jogging`, `lsprint` (low sprint), `sprint`

**Aceleraciones (`accelerations.*` y `accelerations_count.*`, arrays[N]):**
Por minuto, para cada intensidad (`high`, `max`):
- `pos`: aceleraciones positivas.
- `neg`: deceleraciones (negativas).

**Ratio m/min por intensidad:** `meter_minute_ratio_for_intensity.*`
(escalares + arrays para tendencias lineales).

### Uso práctico

Con estos 30+ arrays por jugador × 14 jugadores × 414 sesiones se puede:
1. **Marcar ejercicios**: Arkaitz apunta "sesión X, minuto 10-30 = rondo 3x1".
2. **Agregar métricas en ese rango**: sumamos/promediamos los valores de
   arrays[10:30] para ese jugador.
3. **Comparar ejercicios** entre sí, entre jugadores, o el mismo ejercicio
   repetido en distintos días.
4. **Cruzar con resultados** (goles recibidos/marcados) en el futuro.

### Peso de los datos

67 minutos × ~30 métricas × 14 jugadores × 414 sesiones ≈ 11 millones de
datapoints. No cabe en una sola hoja de Sheet sin sufrir. Estrategias:
- **On-demand**: solo descargar timeline al calcular un ejercicio concreto.
- **Cache local**: JSON por sesión en `data/oliver_timelines/`.
- **Hoja resumen**: escribir solo el agregado por ejercicio en `_EJERCICIOS_METRICAS`.

---

## Credenciales pegadas en chat (⚠ cambiar)
Usuario `Txubas` / Contraseña `@Inter1977`. Anotado aquí temporalmente.
Tras terminar la integración, **cambiar la contraseña** y guardarla en
`.env` (gitignored) para el script.
